"""
Router do Estado do Diário (Fase 4 — Mai/2026).

UM ÚNICO endpoint agregador que cruza:
  - `teacher_class_assignments` (expectativa institucional por slot)
  - `attendance` (frequência lançada)
  - `content_entries` (conteúdo lançado/publicado/corrigido)

Produz "estado semântico" — nunca cor. UI escolhe paleta.

Pipeline híbrido (NÃO $facet puro):
  1) Buscar assignments vigentes da turma no range.
  2) Expandir em memória cada (data × weekly_slot) → slot esperado.
  3) Buscar attendance + content_entries com $in.
  4) Casamento em Python por (date, class_id, aula_numero, [course/component_id]).
  5) Consolidar status por entry, status agregado por dia e summary global.

Endpoint:
  GET /api/calendar/diary-state/{class_id}?from=YYYY-MM-DD&to=YYYY-MM-DD
"""
from datetime import date as date_cls, datetime, timedelta
from typing import Optional
import logging
import time

from fastapi import APIRouter, HTTPException, Query, Request

from auth_middleware import AuthMiddleware
from utils.observability import MetricChannel

logger = logging.getLogger(__name__)

VIEW_ROLES = [
    'admin', 'admin_teste', 'super_admin', 'secretario', 'gerente', 'semed3',
    'diretor', 'coordenador', 'professor', 'ass_social_2', 'auxiliar_secretaria',
]

# Limite defensivo do range — protege contra varredura excessiva.
MAX_RANGE_DAYS = 92  # ~1 trimestre

ATTENDANCE_DONE_STATUSES = {"completed", "validated"}
CONTENT_PUBLISHED_LIKE = {"published", "corrected"}

# Fase 5 (Mai/2026) — canal de observabilidade dedicado.
# Sem cache nesta rodada (diretriz: medir antes de cachear).
diary_state_metrics = MetricChannel(
    "diary_state",
    latency_buckets_ms=[10, 25, 50, 100, 250, 500, 1000, 2500, 5000],
)


def _parse_date(s: str) -> date_cls:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _daterange(d_from: date_cls, d_to: date_cls):
    cur = d_from
    while cur <= d_to:
        yield cur
        cur += timedelta(days=1)


def _is_assignment_active_on(assignment: dict, day: date_cls) -> bool:
    vf = _parse_date(assignment["valid_from"])
    if day < vf:
        return False
    vu = assignment.get("valid_until")
    if vu is not None and day > _parse_date(vu):
        return False
    return True


def _range_bucket(days: int) -> str:
    """Categoriza o tamanho do range para observabilidade (sem PII)."""
    if days <= 1:
        return "1d"
    if days <= 7:
        return "1w"
    if days <= 31:
        return "1m"
    if days <= 62:
        return "2m"
    return "3m"


def _classify_day(
    entries: list,
    has_orphan_evidence: bool,
    is_non_school_day: bool = False,
) -> str:
    """Aggregate status do dia baseado nos entries esperados.

      - non_school: feriado/recesso/fim de semana sem grade. Visualmente
        cinza claro. Nunca dispara inconsistent (mesmo que haja órfão).
      - not_expected: nenhum slot esperado pela grade. Visualmente quase invisível.
      - inconsistent: há evidência (attendance/content) fora de slot esperado.
        Pode ocorrer com OU sem entries esperados.
      - empty: havia slots esperados mas zero evidência (pendência real).
      - corrected: ao menos 1 content_status=='corrected'.
      - complete: TODOS entries esperados completos
        (attendance in DONE + content in PUBLISHED_LIKE).
      - partial: caso contrário.

    A separação `non_school` / `not_expected` / `empty` é semanticamente
    crítica: distingue "dia não-letivo institucional" / "não deveria existir
    lançamento" / "deveria existir mas não veio".
    """
    if is_non_school_day:
        return "non_school"
    if has_orphan_evidence:
        return "inconsistent"
    if not entries:
        return "not_expected"
    any_evidence = any(
        e["attendance_status"] != "missing" or e["content_status"] != "missing"
        for e in entries
    )
    if not any_evidence:
        return "empty"
    has_corrected = any(e["content_status"] == "corrected" for e in entries)
    all_complete = all(
        e["attendance_status"] in ATTENDANCE_DONE_STATUSES
        and e["content_status"] in CONTENT_PUBLISHED_LIKE
        for e in entries
    )
    if all_complete:
        all_validated = all(
            e["attendance_status"] == "validated" for e in entries
        )
        if all_validated:
            return "validated"
        return "corrected" if has_corrected else "complete"
    return "corrected" if has_corrected else "partial"


def setup_calendar_diary_state_router(db):
    router = APIRouter(prefix="/calendar", tags=["Diário - Calendário"])

    @router.get("/diary-state/{class_id}")
    async def diary_state(
        class_id: str,
        request: Request,
        from_: str = Query(..., alias="from"),
        to: str = Query(...),
    ):
        await AuthMiddleware.require_roles(VIEW_ROLES)(request)
        current_user = await AuthMiddleware.get_current_user(request)
        t0 = time.monotonic()
        is_error = False
        range_days = 0

        try:
            try:
                d_from = _parse_date(from_)
                d_to = _parse_date(to)
            except ValueError:
                is_error = True
                raise HTTPException(
                    status_code=400, detail="Parâmetros 'from' e 'to' devem ser YYYY-MM-DD"
                )
            if d_to < d_from:
                is_error = True
                raise HTTPException(status_code=400, detail="'to' deve ser >= 'from'")
            range_days = (d_to - d_from).days + 1
            if range_days > MAX_RANGE_DAYS:
                is_error = True
                raise HTTPException(
                    status_code=400,
                    detail=f"Range máximo permitido: {MAX_RANGE_DAYS} dias.",
                )

            klass = await db.classes.find_one(
                {"id": class_id},
                {"_id": 0, "id": 1, "name": 1, "school_id": 1,
                 "academic_year": 1, "mantenedora_id": 1,
                 "education_level": 1, "is_multi_grade": 1,
                 "diary_matching_mode": 1},
            )
            if not klass:
                is_error = True
                raise HTTPException(status_code=404, detail="Turma não encontrada")

            # ---------------- Etapa 1: assignments vigentes ----------------
            assignments = await db.teacher_class_assignments.find(
                {
                    "class_id": class_id,
                    "deleted": False,
                    "valid_from": {"$lte": to},
                    "$or": [{"valid_until": None}, {"valid_until": {"$gte": from_}}],
                },
                {"_id": 0},
            ).to_list(2000)

            # ---------------- Etapa 1b: fallback legacy (sem mexer no banco) ----------------
            # Quando a turma não tem assignments no modelo novo, lê do legacy
            # (`class_schedules` + `teacher_assignments`) e constrói assignments
            # sintéticos no mesmo shape. Tratamento aprovado: ordem de resolução
            # — novo TEM PRIORIDADE absoluta; só usa bridge se novo for vazio.
            if not assignments:
                from services.legacy_schedule_bridge import (
                    build_assignments_from_legacy,
                )
                assignments = await build_assignments_from_legacy(
                    db, class_doc=klass,
                )

            # ---------------- Etapa 1c: calendário letivo (Fase 11) ----------------
            # Carrega feriados/recessos e sábados letivos do período. Dias em
            # `non_school_days` não terão slots expandidos — frontend renderiza
            # como "Sem aula" (não-letivo).
            from services.school_calendar_helper import load_school_calendar
            school_cal = await load_school_calendar(
                db,
                academic_year=klass.get("academic_year"),
                period_from=from_,
                period_to=to,
                mantenedora_id=klass.get("mantenedora_id"),
            )
            non_school_days: dict = school_cal["non_school_days"]
            explicit_school_days: dict = school_cal["explicit_school_days"]

            # ---------------- Etapa 2: expandir slots esperados em memória ----------------
            expected_by_date: dict = {}
            for a in assignments:
                for slot in a.get("weekly_slots", []) or []:
                    wd = slot.get("weekday")
                    aula = slot.get("aula_numero")
                    if not wd or not aula:
                        continue
                    for day in _daterange(d_from, d_to):
                        if not _is_assignment_active_on(a, day):
                            continue
                        py_wd = day.isoweekday()
                        if py_wd != wd:
                            continue
                        iso = day.isoformat()
                        # Pula dias não-letivos (feriados/recessos) — vencidos
                        # APENAS por sábado letivo (que está em explicit).
                        if iso in non_school_days and iso not in explicit_school_days:
                            continue
                        expected_by_date.setdefault(iso, []).append({
                            "component_id": a.get("component_id"),
                            "component_name": a.get("component_name") or a.get("component_id"),
                            "aula_numero": aula,
                            "teacher_id": a.get("teacher_id"),
                            "teacher_name": a.get("teacher_name"),
                            "assignment_id": a["id"],
                            "assignment_source": a.get("source") or "canonical",
                            "is_substitute": a.get("is_substitute", False),
                            "attendance_status": "missing",
                            "content_status": "missing",
                            "expected_by_schedule": True,
                            "slot_start": slot.get("start_time"),
                            "slot_end": slot.get("end_time"),
                        })

            # ---------------- Etapa 3: buscar evidências ----------------
            dates_in_range = [day.isoformat() for day in _daterange(d_from, d_to)]
            attendances = await db.attendance.find(
                {"class_id": class_id, "date": {"$in": dates_in_range}},
                {"_id": 0, "id": 1, "date": 1, "course_id": 1, "aula_numero": 1,
                 "records": 1, "validated_by": 1, "validated_by_name": 1,
                 "validated_at": 1, "version": 1, "created_by": 1, "updated_by": 1},
            ).to_list(5000)

            content_entries = await db.content_entries.find(
                {"class_id": class_id, "date": {"$in": dates_in_range}, "deleted": False},
                {"_id": 0, "id": 1, "date": 1, "component_id": 1, "aula_numero": 1,
                 "teacher_id": 1, "status": 1, "version": 1, "published_at": 1},
            ).to_list(5000)

            # Fallback legacy: turmas migradas guardam o conteúdo em
            # `learning_objects`. Mantém modelo novo como fonte canônica.
            if not content_entries:
                from services.legacy_content_bridge import (
                    build_content_entries_from_legacy,
                )
                content_entries = await build_content_entries_from_legacy(
                    db, class_id=class_id, dates_in_range=dates_in_range,
                )

            # ---------------- Etapa 4: casamento ----------------
            att_by_date_aula: dict = {}
            att_by_date_only: dict = {}
            for att in attendances:
                aula = att.get("aula_numero")
                if aula is None:
                    att_by_date_only.setdefault(att["date"], []).append(att)
                else:
                    att_by_date_aula.setdefault((att["date"], aula), []).append(att)

            ce_index: dict = {}
            for ce in content_entries:
                key = (ce["date"], ce.get("component_id"), ce.get("aula_numero"), ce.get("teacher_id"))
                existing = ce_index.get(key)
                if (not existing) or (ce.get("version", 0) > existing.get("version", 0)):
                    ce_index[key] = ce

            used_attendance_ids: set = set()
            used_content_ids: set = set()

            # Resolve modo de matching da turma (strict | flexible).
            # Frontend NUNCA decide. Backend lê do campo persistido ou infere
            # a partir da etapa pedagógica (infantil, anos iniciais, EJA, multi).
            from services.diary_matching_mode import resolve_matching_mode
            matching_mode = resolve_matching_mode(klass)

            def _apply_attendance_status(entry, att):
                if att.get("validated_by"):
                    entry["attendance_status"] = "validated"
                elif att.get("records"):
                    entry["attendance_status"] = "completed"
                else:
                    entry["attendance_status"] = "draft"
                entry["attendance_id"] = att["id"]
                # Fase 7 — exibir metadados da validação na UI sem que ela
                # precise consultar outro endpoint.
                if att.get("validated_by"):
                    entry["validated_by"] = att.get("validated_by")
                    entry["validated_by_name"] = att.get("validated_by_name")
                    entry["validated_at"] = att.get("validated_at")

            # ---- Etapa 4a: matching ESTRITO (sempre roda) ----
            for iso, entries in expected_by_date.items():
                for e in entries:
                    specific = att_by_date_aula.get((iso, e["aula_numero"]), [])
                    if specific:
                        att = next((a for a in specific if a["id"] not in used_attendance_ids), specific[0])
                        used_attendance_ids.add(att["id"])
                        _apply_attendance_status(e, att)
                        e["matched_by"] = "strict"
                    else:
                        day_atts = att_by_date_only.get(iso, [])
                        if day_atts:
                            att = day_atts[0]
                            used_attendance_ids.add(att["id"])
                            _apply_attendance_status(e, att)
                            e["matched_by"] = "strict"
                    ck = (iso, e["component_id"], e["aula_numero"], e["teacher_id"])
                    ce = ce_index.get(ck)
                    if ce:
                        used_content_ids.add(ce["id"])
                        e["content_status"] = ce.get("status", "draft")
                        e["content_entry_id"] = ce["id"]
                        e.setdefault("matched_by", "strict")

            # ---- Etapa 4b: matching FLEXÍVEL (Fase 10) ----
            # Só roda quando a turma é pedagogicamente integrada. Reaproveita
            # attendances/CEs que ficariam órfãos, casando-os com entries do
            # MESMO DIA que tenham (mesmo_professor OU mesmo_componente).
            # NÃO afrouxa: data e vínculo semântico continuam obrigatórios.
            if matching_mode == "flexible":
                # Index reverso: entries por data, ainda sem attendance.
                entries_without_att: dict = {}
                entries_without_ce: dict = {}
                for iso, entries in expected_by_date.items():
                    for e in entries:
                        if not e.get("attendance_id"):
                            entries_without_att.setdefault(iso, []).append(e)
                        if not e.get("content_entry_id"):
                            entries_without_ce.setdefault(iso, []).append(e)

                # 4b.1 — attendance flexível
                for att in attendances:
                    if att["id"] in used_attendance_ids:
                        continue
                    candidates = entries_without_att.get(att["date"], [])
                    if not candidates:
                        continue
                    att_teacher = att.get("created_by") or att.get("updated_by")
                    att_course = att.get("course_id")
                    picked = None
                    reason = None
                    if att_teacher:
                        picked = next(
                            (c for c in candidates if c.get("teacher_id") == att_teacher),
                            None,
                        )
                        if picked:
                            reason = "same_teacher_same_day"
                    if not picked and att_course:
                        picked = next(
                            (c for c in candidates if c.get("component_id") == att_course),
                            None,
                        )
                        if picked:
                            reason = "same_component_same_day"
                    if picked:
                        used_attendance_ids.add(att["id"])
                        _apply_attendance_status(picked, att)
                        picked["matched_by"] = "flexible"
                        picked["flexible_match_reason"] = reason
                        # Remove do pool para não casar 2x
                        entries_without_att[att["date"]] = [
                            c for c in candidates if c is not picked
                        ]
                        logger.info(
                            "[diary_matching] matched_by=flexible reason=%s "
                            "class_id=%s date=%s attendance_id=%s",
                            reason, class_id, att["date"], att["id"],
                        )

                # 4b.2 — content entries flexível
                for ce in content_entries:
                    if ce["id"] in used_content_ids:
                        continue
                    candidates = entries_without_ce.get(ce["date"], [])
                    if not candidates:
                        continue
                    ce_teacher = ce.get("teacher_id")
                    ce_component = ce.get("component_id")
                    picked = None
                    reason = None
                    if ce_teacher:
                        picked = next(
                            (c for c in candidates if c.get("teacher_id") == ce_teacher),
                            None,
                        )
                        if picked:
                            reason = "same_teacher_same_day"
                    if not picked and ce_component:
                        picked = next(
                            (c for c in candidates if c.get("component_id") == ce_component),
                            None,
                        )
                        if picked:
                            reason = "same_component_same_day"
                    if picked:
                        used_content_ids.add(ce["id"])
                        picked["content_status"] = ce.get("status", "draft")
                        picked["content_entry_id"] = ce["id"]
                        picked["matched_by"] = "flexible"
                        picked["flexible_match_reason"] = reason
                        entries_without_ce[ce["date"]] = [
                            c for c in candidates if c is not picked
                        ]
                        logger.info(
                            "[diary_matching] matched_by=flexible reason=%s "
                            "class_id=%s date=%s content_entry_id=%s",
                            reason, class_id, ce["date"], ce["id"],
                        )

                # ---- Etapa 4c: FAN-OUT por dia (regra pedagógica integrada) ----
                # Em modo flexible, a presença de QUALQUER registro de
                # frequência/conteúdo no dia cobre todas as aulas esperadas
                # daquele dia. Reflete a semântica de "aula como continuum"
                # nas etapas integradas (Infantil, Anos Iniciais, EJA-AI).
                attendance_by_date: dict = {}
                for att in attendances:
                    attendance_by_date.setdefault(att["date"], []).append(att)
                content_by_date: dict = {}
                for ce in content_entries:
                    content_by_date.setdefault(ce["date"], []).append(ce)

                for iso, entries in expected_by_date.items():
                    # Fan-out de frequência
                    day_atts = attendance_by_date.get(iso, [])
                    if day_atts:
                        ref_att = next(
                            (a for a in day_atts if a.get("records")),
                            day_atts[0],
                        )
                        for e in entries:
                            if e.get("attendance_id"):
                                continue
                            used_attendance_ids.add(ref_att["id"])
                            _apply_attendance_status(e, ref_att)
                            e["matched_by"] = "flexible"
                            e["flexible_match_reason"] = "day_fanout_attendance"
                    # Fan-out de conteúdo (versão mais alta vence)
                    day_ces = content_by_date.get(iso, [])
                    if day_ces:
                        ref_ce = max(day_ces, key=lambda c: c.get("version") or 0)
                        for e in entries:
                            if e.get("content_entry_id"):
                                continue
                            used_content_ids.add(ref_ce["id"])
                            e["content_status"] = ref_ce.get("status", "draft")
                            e["content_entry_id"] = ref_ce["id"]
                            e["matched_by"] = "flexible"
                            e["flexible_match_reason"] = "day_fanout_content"

            orphan_attendance_dates: set = set()
            for att in attendances:
                if att["id"] in used_attendance_ids:
                    continue
                orphan_attendance_dates.add(att["date"])
            orphan_content_dates: set = set()
            for ce in content_entries:
                if ce["id"] in used_content_ids:
                    continue
                orphan_content_dates.add(ce["date"])

            days: list = []
            summary = {
                "expected_slots": 0,
                "attendance_completed": 0,
                "attendance_validated": 0,
                "content_published": 0,
                "content_corrected": 0,
                "content_drafts": 0,
                "day_status_counts": {
                    "not_expected": 0, "empty": 0, "partial": 0,
                    "complete": 0, "corrected": 0, "validated": 0,
                    "inconsistent": 0, "non_school": 0,
                },
                "orphan_attendance_dates": sorted(orphan_attendance_dates),
                "orphan_content_dates": sorted(orphan_content_dates),
            }
            for day in _daterange(d_from, d_to):
                iso = day.isoformat()
                entries = expected_by_date.get(iso, [])
                entries.sort(key=lambda x: (x["aula_numero"] or 0, x.get("component_id") or ""))
                has_orphan_today = iso in orphan_attendance_dates or iso in orphan_content_dates
                is_non_school = iso in non_school_days
                day_status = _classify_day(entries, has_orphan_today, is_non_school)
                day_obj = {
                    "date": iso,
                    "weekday": day.isoweekday(),
                    "status": day_status,
                    "expected_slots": len(entries),
                    "entries": entries,
                    "has_orphan_evidence": has_orphan_today,
                }
                # Anota metadado institucional (feriado/recesso/sábado letivo)
                if is_non_school:
                    day_obj["school_calendar_event"] = non_school_days[iso]
                elif iso in explicit_school_days:
                    day_obj["school_calendar_event"] = explicit_school_days[iso]
                    day_obj["is_explicit_school_day"] = True
                days.append(day_obj)
                summary["day_status_counts"][day_status] = summary["day_status_counts"].get(day_status, 0) + 1
                summary["expected_slots"] += len(entries)
                for e in entries:
                    if e["attendance_status"] == "completed":
                        summary["attendance_completed"] += 1
                    elif e["attendance_status"] == "validated":
                        summary["attendance_validated"] += 1
                    if e["content_status"] == "published":
                        summary["content_published"] += 1
                    elif e["content_status"] == "corrected":
                        summary["content_corrected"] += 1
                    elif e["content_status"] == "draft":
                        summary["content_drafts"] += 1

            return {
                "class_id": class_id,
                "class_name": klass.get("name"),
                "school_id": klass.get("school_id"),
                "from": from_,
                "to": to,
                "range_days": range_days,
                "matching_mode": matching_mode,
                "summary": summary,
                "days": days,
            }
        finally:
            # Fase 5 — observabilidade (sem cache nesta rodada).
            duration_ms = (time.monotonic() - t0) * 1000
            try:
                diary_state_metrics.record(
                    duration_ms=duration_ms,
                    tenant_id=(current_user or {}).get("mantenedora_id"),
                    labels={
                        "class_id": class_id,
                        "range_bucket": _range_bucket(range_days),
                        "role": (current_user or {}).get("role"),
                    },
                    bucket_counters={
                        "range_days_sum": range_days,
                        "requests_total": 1,
                    },
                    is_error=is_error,
                )
            except Exception as e:
                logger.warning("[diary_state] obs record failed: %s", e)

    return router
