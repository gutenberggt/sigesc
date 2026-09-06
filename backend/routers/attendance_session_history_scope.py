"""Visibilidade institucional da frequência por sessão — Issue #480.

Para ``assignment_session`` oficial, o vínculo ATUAL autoriza o acesso, mas
``assignment_id``/autor não fragmentam a leitura histórica. A chave operacional
continua turma + componente + data + período + aula_numero.

Registros de outro vínculo são projetados como somente leitura. Nenhum documento
é migrado, reatribuído, copiado ou atualizado por esta camada.
"""
from __future__ import annotations

from datetime import date as date_cls
from typing import Any, Mapping, Optional

from fastapi import HTTPException

from services.attendance_assignment_scope import (
    AttendanceAssignmentScopeError,
    logical_attendance_query,
    resolve_attendance_assignment,
    resolve_session_aula_numero,
)
from services.diary_assignment_contract import AttendanceMode, AttendancePurpose
from tenant_scope import get_mantenedora_scope


class SessionHistoryCollision(RuntimeError):
    pass


def _sid(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _day(value: Any) -> str:
    return _sid(value)[:10]


def _tenant_ok(doc: Mapping[str, Any], tenant_id: Optional[str]) -> bool:
    doc_tenant = _sid(doc.get("mantenedora_id"))
    expected = _sid(tenant_id)
    return not (doc_tenant and expected and doc_tenant != expected)


def _expected_aulas(weekly_slots: list[Mapping[str, Any]], day: str) -> set[str]:
    try:
        weekday = date_cls.fromisoformat(_day(day)).isoweekday()
    except ValueError:
        return set()
    return {
        _sid(slot.get("aula_numero"))
        for slot in (weekly_slots or [])
        if slot.get("weekday") == weekday and _sid(slot.get("aula_numero"))
    }


def _natural_key(doc: Mapping[str, Any]) -> tuple[str, str, str] | None:
    day = _day(doc.get("date"))
    aula = _sid(doc.get("aula_numero"))
    if not day or not aula:
        return None
    return day, _sid(doc.get("period")) or "regular", aula


def normalize_session_history_docs(
    docs: list[Mapping[str, Any]],
    *,
    class_id: str,
    component_id: str,
    current_assignment_id: str,
    tenant_id: Optional[str],
    weekly_slots: list[Mapping[str, Any]],
) -> list[dict]:
    """Normaliza a projeção por sessão sem inventar ``aula_numero``.

    - tenant explicitamente divergente falha fechado por exclusão;
    - ``class_daily``/``pdf_only`` explícitos não entram;
    - colisão real de duas sessões para a mesma chave falha fechado, salvo se
      existir exatamente um documento do assignment atual, que prevalece;
    - agregado sem aula só entra quando há exatamente UM slot esperado e não há
      sessão numerada correspondente;
    - em dias de dois ou mais slots, agregados são preservados no banco mas não
      contam como sessão operacional.
    """
    eligible: list[dict] = []
    for raw in docs:
        if _sid(raw.get("class_id")) != _sid(class_id):
            continue
        if _sid(raw.get("course_id")) != _sid(component_id):
            continue
        if not _tenant_ok(raw, tenant_id):
            continue
        if raw.get("attendance_purpose") not in (None, "official"):
            continue
        if raw.get("attendance_mode") not in (None, "assignment_session"):
            continue
        eligible.append(dict(raw))

    numbered: dict[tuple[str, str, str], list[dict]] = {}
    aggregates: dict[tuple[str, str], list[dict]] = {}
    for doc in eligible:
        key = _natural_key(doc)
        if key is not None:
            numbered.setdefault(key, []).append(doc)
        else:
            day = _day(doc.get("date"))
            if day:
                aggregates.setdefault((day, _sid(doc.get("period")) or "regular"), []).append(doc)

    selected: list[dict] = []
    selected_numbered: set[tuple[str, str, str]] = set()
    for key, group in numbered.items():
        if len(group) == 1:
            chosen = group[0]
        else:
            current = [
                doc for doc in group
                if _sid(doc.get("assignment_id")) == _sid(current_assignment_id)
            ]
            if len(current) != 1:
                raise SessionHistoryCollision(
                    f"SESSION_HISTORY_COLLISION:{key[0]}:{key[1]}:{key[2]}"
                )
            chosen = current[0]
        selected_numbered.add(key)
        selected.append(chosen)

    # Agregado legado só representa evidência operacional quando o calendário
    # atual tem exatamente um slot esperado naquele dia e não existe sessão
    # numerada para esse slot. Nunca há fan-out para duas aulas.
    for (day, period), group in aggregates.items():
        expected = _expected_aulas(weekly_slots, day)
        if len(expected) != 1:
            continue
        aula = next(iter(expected))
        if (day, period, aula) in selected_numbered:
            continue
        if len(group) != 1:
            raise SessionHistoryCollision(f"SESSION_AGGREGATE_COLLISION:{day}:{period}")
        selected.append(group[0])

    out: list[dict] = []
    for raw in selected:
        item = dict(raw)
        is_current = _sid(item.get("assignment_id")) == _sid(current_assignment_id)
        if not is_current:
            item["read_only"] = True
            item["historical_scope_read"] = True
        else:
            item.setdefault("read_only", False)
        out.append(item)
    out.sort(key=lambda doc: (
        _day(doc.get("date")),
        _sid(doc.get("period")) or "regular",
        int(doc.get("aula_numero") or 0),
    ))
    return out


async def _scoped_docs(
    db,
    context,
    academic_year: int,
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Optional[list[dict]]:
    if context.attendance_mode is not AttendanceMode.ASSIGNMENT_SESSION:
        return None
    if context.attendance_purpose is not AttendancePurpose.OFFICIAL:
        return None

    component_id = context.effective_course_id
    class_id = context.assignment.get("class_id")
    if not class_id or not component_id:
        return []
    lower = max(str(start or f"{academic_year}-01-01")[:10], f"{academic_year}-01-01")
    upper = min(str(end or f"{academic_year}-12-31")[:10], f"{academic_year}-12-31")
    if lower > upper:
        return []

    docs = await db.attendance.find(
        {
            "class_id": class_id,
            "course_id": component_id,
            "date": {"$gte": lower, "$lte": upper},
        },
        {"_id": 0},
    ).to_list(10000)
    try:
        return normalize_session_history_docs(
            docs,
            class_id=class_id,
            component_id=component_id,
            current_assignment_id=context.assignment.get("id"),
            tenant_id=context.snapshot.get("mantenedora_id"),
            weekly_slots=context.assignment.get("weekly_slots") or [],
        )
    except SessionHistoryCollision as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ATTENDANCE_HISTORY_COLLISION_REQUIRES_REVIEW",
                "message": "Há mais de uma frequência para a mesma sessão histórica; revisão de integridade necessária.",
                "diagnostic": str(exc),
            },
        ) from exc


def _overlay_historical_result(result: dict, doc: Mapping[str, Any]) -> dict:
    out = dict(result)
    records = list(doc.get("records") or [])
    records_map = {row.get("student_id"): row.get("status") for row in records}
    dependency_map = {
        row.get("student_id"): row.get("dependency_id")
        for row in records if row.get("dependency_id")
    }
    students = [dict(student) for student in (out.get("students") or [])]
    for student in students:
        sid = student.get("id")
        student["status"] = records_map.get(sid)
        if sid in dependency_map:
            student["dependency_id"] = dependency_map[sid]
            student["is_dependency"] = True
    out.update({
        "attendance_id": doc.get("id"),
        "observations": doc.get("observations"),
        "version": doc.get("version"),
        "total_sessions": 1,
        "sessions": [{
            "id": doc.get("id"),
            "aula_numero": out.get("aula_numero"),
            "number_of_classes": 1,
            "observations": doc.get("observations"),
            "records": records_map,
        }],
        "students": students,
        "read_only": True,
        "historical_read_only": True,
        "historical_scope_read": True,
        "history_assignment_id": doc.get("assignment_id"),
    })
    return out


def install_attendance_session_history_scope(attendance_dvd_mod):
    """Instala ponte read-only após os adaptadores DVD existentes."""
    if getattr(attendance_dvd_mod, "_issue_480_session_history_installed", False):
        return

    original_assignment_docs = attendance_dvd_mod._assignment_docs
    original_get = attendance_dvd_mod._get_dvd_attendance
    original_save = attendance_dvd_mod._save_dvd_attendance

    async def assignment_docs(db, context, academic_year, *, start=None, end=None):
        scoped = await _scoped_docs(
            db, context, academic_year, start=start, end=end
        )
        if scoped is not None:
            return scoped
        return await original_assignment_docs(
            db, context, academic_year, start=start, end=end
        )

    async def get_dvd(db, user, request, *, assignment_id, on_date, aula_numero, period):
        result = await original_get(
            db,
            user,
            request,
            assignment_id=assignment_id,
            on_date=on_date,
            aula_numero=aula_numero,
            period=period,
        )
        if result.get("attendance_id") or result.get("session_selection_required"):
            return result
        if result.get("attendance_mode") != AttendanceMode.ASSIGNMENT_SESSION.value:
            return result
        if result.get("attendance_purpose") != AttendancePurpose.OFFICIAL.value:
            return result
        resolved_aula = result.get("aula_numero")
        if resolved_aula is None:
            return result

        candidates = await db.attendance.find(
            {
                "class_id": result.get("class_id"),
                "course_id": result.get("component_id"),
                "date": on_date,
                "aula_numero": resolved_aula,
            },
            {"_id": 0},
        ).to_list(50)
        candidates = [
            doc for doc in candidates
            if (_sid(doc.get("period")) or "regular") == (_sid(period) or "regular")
            and _tenant_ok(doc, result.get("mantenedora_id"))
            and doc.get("attendance_purpose") in (None, "official")
            and doc.get("attendance_mode") in (None, "assignment_session")
        ]
        if not candidates:
            return result
        if len(candidates) > 1:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ATTENDANCE_HISTORY_COLLISION_REQUIRES_REVIEW",
                    "message": "Há múltiplas frequências históricas para esta sessão.",
                },
            )
        # Se o GET canônico não encontrou o documento, qualquer fallback é
        # deliberadamente somente leitura para impedir apropriação retroativa.
        return _overlay_historical_result(result, candidates[0])

    async def save_dvd(db, user, request, payload, audit_service):
        try:
            context = await resolve_attendance_assignment(
                db,
                user,
                payload.assignment_id,
                on_date=payload.date,
                active_mantenedora_id=get_mantenedora_scope(user, request),
            )
            if (
                context.attendance_mode is AttendanceMode.ASSIGNMENT_SESSION
                and context.attendance_purpose is AttendancePurpose.OFFICIAL
            ):
                aula = resolve_session_aula_numero(context, payload.aula_numero)
                current_query = logical_attendance_query(
                    context,
                    on_date=payload.date,
                    aula_numero=aula,
                    period=payload.period,
                )
                current = await db.attendance.find_one(current_query, {"_id": 0, "id": 1})
                if not current:
                    historical = await db.attendance.find(
                        {
                            "class_id": context.assignment.get("class_id"),
                            "course_id": context.effective_course_id,
                            "date": payload.date,
                            "aula_numero": aula,
                        },
                        {"_id": 0, "id": 1, "assignment_id": 1, "period": 1,
                         "mantenedora_id": 1, "attendance_mode": 1,
                         "attendance_purpose": 1},
                    ).to_list(50)
                    historical = [
                        doc for doc in historical
                        if (_sid(doc.get("period")) or "regular") == (_sid(payload.period) or "regular")
                        and _tenant_ok(doc, context.snapshot.get("mantenedora_id"))
                        and doc.get("attendance_purpose") in (None, "official")
                        and doc.get("attendance_mode") in (None, "assignment_session")
                    ]
                    if historical:
                        raise HTTPException(
                            status_code=409,
                            detail={
                                "code": "HISTORICAL_ATTENDANCE_READ_ONLY",
                                "message": (
                                    "Já existe frequência histórica válida nesta sessão. "
                                    "Ela permanece visível, mas não pode ser apropriada ou duplicada pelo vínculo atual."
                                ),
                            },
                        )
        except AttendanceAssignmentScopeError:
            # O motor original traduz o erro com o contrato HTTP já consolidado.
            pass
        return await original_save(db, user, request, payload, audit_service)

    attendance_dvd_mod._assignment_docs = assignment_docs
    attendance_dvd_mod._get_dvd_attendance = get_dvd
    attendance_dvd_mod._save_dvd_attendance = save_dvd
    attendance_dvd_mod._issue_480_session_history_installed = True
