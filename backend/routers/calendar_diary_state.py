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


def _classify_day(entries: list, has_orphan_evidence: bool) -> str:
    """Aggregate status do dia baseado nos entries esperados.

      - not_expected: nenhum slot esperado pela grade (feriado, fim de semana,
        domingo) E sem evidência órfã. Visualmente quase invisível.
      - inconsistent: há evidência (attendance/content) fora de slot esperado.
        Pode ocorrer com OU sem entries esperados.
      - empty: havia slots esperados mas zero evidência (pendência real).
      - corrected: ao menos 1 content_status=='corrected'.
      - complete: TODOS entries esperados completos
        (attendance in DONE + content in PUBLISHED_LIKE).
      - partial: caso contrário.

    A separação `not_expected` vs `empty` é semanticamente crítica: distingue
    "não deveria existir lançamento" de "deveria existir mas não veio".
    """
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
                {"id": class_id}, {"_id": 0, "id": 1, "name": 1, "school_id": 1}
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
                        expected_by_date.setdefault(iso, []).append({
                            "component_id": a.get("component_id"),
                            "component_name": a.get("component_id"),
                            "aula_numero": aula,
                            "teacher_id": a.get("teacher_id"),
                            "teacher_name": a.get("teacher_name"),
                            "assignment_id": a["id"],
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
                 "records": 1, "validated_by": 1, "version": 1, "created_by": 1, "updated_by": 1},
            ).to_list(5000)

            content_entries = await db.content_entries.find(
                {"class_id": class_id, "date": {"$in": dates_in_range}, "deleted": False},
                {"_id": 0, "id": 1, "date": 1, "component_id": 1, "aula_numero": 1,
                 "teacher_id": 1, "status": 1, "version": 1, "published_at": 1},
            ).to_list(5000)

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

            def _apply_attendance_status(entry, att):
                if att.get("validated_by"):
                    entry["attendance_status"] = "validated"
                elif att.get("records"):
                    entry["attendance_status"] = "completed"
                else:
                    entry["attendance_status"] = "draft"
                entry["attendance_id"] = att["id"]

            for iso, entries in expected_by_date.items():
                for e in entries:
                    specific = att_by_date_aula.get((iso, e["aula_numero"]), [])
                    if specific:
                        att = next((a for a in specific if a["id"] not in used_attendance_ids), specific[0])
                        used_attendance_ids.add(att["id"])
                        _apply_attendance_status(e, att)
                    else:
                        day_atts = att_by_date_only.get(iso, [])
                        if day_atts:
                            att = day_atts[0]
                            used_attendance_ids.add(att["id"])
                            _apply_attendance_status(e, att)
                    ck = (iso, e["component_id"], e["aula_numero"], e["teacher_id"])
                    ce = ce_index.get(ck)
                    if ce:
                        used_content_ids.add(ce["id"])
                        e["content_status"] = ce.get("status", "draft")
                        e["content_entry_id"] = ce["id"]

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
                    "complete": 0, "corrected": 0, "inconsistent": 0,
                },
                "orphan_attendance_dates": sorted(orphan_attendance_dates),
                "orphan_content_dates": sorted(orphan_content_dates),
            }
            for day in _daterange(d_from, d_to):
                iso = day.isoformat()
                entries = expected_by_date.get(iso, [])
                entries.sort(key=lambda x: (x["aula_numero"] or 0, x.get("component_id") or ""))
                has_orphan_today = iso in orphan_attendance_dates or iso in orphan_content_dates
                day_status = _classify_day(entries, has_orphan_today)
                days.append({
                    "date": iso,
                    "weekday": day.isoweekday(),
                    "status": day_status,
                    "expected_slots": len(entries),
                    "entries": entries,
                    "has_orphan_evidence": has_orphan_today,
                })
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
