"""Reconciliação canônica do estado do Diário — Issue #480.

O router original continua responsável por RBAC, calendário, sábado letivo,
validade de vínculos e expansão dos slots esperados. Esta camada pós-processa
SOMENTE turmas em ``matching_mode=strict`` e refaz o casamento de frequência e
conteúdo segundo a identidade institucional:

- frequência: turma + data + componente + aula_numero;
- conteúdo: turma + data + componente, sem autoria;
- agregado legado nunca é expandido para duas aulas;
- agregado estruturalmente coberto por todas as sessões exatas não vira órfão.

Nenhuma escrita é executada.
"""
from __future__ import annotations

from typing import Any, Mapping

from fastapi import Query, Request

from services.diary_canonical_evidence_policy import (
    expected_slot_counts,
    select_content_for_slot,
    select_strict_attendance,
    shadowed_legacy_attendance_ids,
)

ATTENDANCE_DONE_STATUSES = {"completed", "validated"}
CONTENT_PUBLISHED_LIKE = {"published", "corrected"}


def _sid(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _day(row: Mapping[str, Any]) -> str:
    return _sid(row.get("date"))[:10]


def _component(row: Mapping[str, Any]) -> str:
    return _sid(row.get("component_id") or row.get("course_id"))


def _classify_day(entries: list[dict], has_orphan: bool, is_non_school: bool) -> str:
    if is_non_school:
        return "non_school"
    if has_orphan:
        return "inconsistent"
    if not entries:
        return "not_expected"
    any_evidence = any(
        entry.get("attendance_status") != "missing"
        or entry.get("content_status") != "missing"
        for entry in entries
    )
    if not any_evidence:
        return "empty"
    has_corrected = any(entry.get("content_status") == "corrected" for entry in entries)
    all_complete = all(
        entry.get("attendance_status") in ATTENDANCE_DONE_STATUSES
        and entry.get("content_status") in CONTENT_PUBLISHED_LIKE
        for entry in entries
    )
    if all_complete:
        if all(entry.get("attendance_status") == "validated" for entry in entries):
            return "validated"
        return "corrected" if has_corrected else "complete"
    return "corrected" if has_corrected else "partial"


def merge_content_sources(canonical: list[dict], legacy: list[dict]) -> list[dict]:
    """Canônico vence somente na mesma data+componente; demais legados permanecem."""
    canonical_keys = {
        (_day(item), _component(item))
        for item in canonical
        if _day(item) and _component(item)
    }
    out = [dict(item) for item in canonical]
    seen_ids = {_sid(item.get("id")) for item in out if _sid(item.get("id"))}
    for raw in legacy:
        if (_day(raw), _component(raw)) in canonical_keys:
            continue
        raw_id = _sid(raw.get("id"))
        if raw_id and raw_id in seen_ids:
            continue
        if raw_id:
            seen_ids.add(raw_id)
        out.append(dict(raw))
    return out


def reconcile_strict_payload(
    payload: dict,
    attendances: list[dict],
    content_entries: list[dict],
) -> dict:
    """Refaz o matching estrito sem alterar expectativa/calendário do payload."""
    if payload.get("matching_mode") != "strict":
        return payload

    result = dict(payload)
    days = [dict(day) for day in (payload.get("days") or [])]
    expected_entries: list[dict] = []
    for day in days:
        iso = _sid(day.get("date"))[:10]
        copied = []
        for raw_entry in (day.get("entries") or []):
            entry = dict(raw_entry)
            # O contrato original mantém a data no objeto do dia. A política de
            # evidência trabalha com entradas autocontidas, então herdamos a
            # data explicitamente antes de qualquer matching.
            entry["date"] = iso
            copied.append(entry)
        day["entries"] = copied
        expected_entries.extend(copied)

    counts = expected_slot_counts(expected_entries)
    used_attendance: set[str] = set()
    used_content: set[str] = set()

    for entry in expected_entries:
        # Remove qualquer casamento produzido pela política antiga.
        for key in (
            "attendance_id", "content_entry_id", "validated_by",
            "validated_by_name", "validated_at", "flexible_match_reason",
        ):
            entry.pop(key, None)
        entry["attendance_status"] = "missing"
        entry["content_status"] = "missing"
        entry.pop("matched_by", None)

        slot_count = counts.get((_day(entry), _component(entry)), 0)
        attendance = select_strict_attendance(
            entry,
            attendances,
            expected_slot_count_for_component_day=slot_count,
            used_ids=used_attendance,
        )
        if attendance:
            att_id = _sid(attendance.get("id"))
            if att_id:
                used_attendance.add(att_id)
            if attendance.get("validated_by"):
                entry["attendance_status"] = "validated"
                entry["validated_by"] = attendance.get("validated_by")
                entry["validated_by_name"] = attendance.get("validated_by_name")
                entry["validated_at"] = attendance.get("validated_at")
            elif attendance.get("records"):
                entry["attendance_status"] = "completed"
            else:
                entry["attendance_status"] = "draft"
            entry["attendance_id"] = attendance.get("id")
            entry["matched_by"] = "canonical_component_slot"

        content = select_content_for_slot(entry, content_entries)
        if content:
            content_id = _sid(content.get("id"))
            if content_id:
                used_content.add(content_id)
            entry["content_status"] = content.get("status") or "draft"
            entry["content_entry_id"] = content.get("id")
            entry.setdefault("matched_by", "canonical_component_day")

    # Agregado legado integralmente substituído por todas as sessões exatas é
    # preservado fisicamente, mas não deve gerar falso órfão/inconsistência.
    used_attendance.update(
        shadowed_legacy_attendance_ids(expected_entries, attendances)
    )

    orphan_attendance_dates = {
        _day(att)
        for att in attendances
        if _sid(att.get("id")) not in used_attendance and _day(att)
    }
    orphan_content_dates = {
        _day(content)
        for content in content_entries
        if _sid(content.get("id")) not in used_content and _day(content)
    }

    summary = {
        "expected_slots": 0,
        "attendance_completed": 0,
        "attendance_validated": 0,
        "content_published": 0,
        "content_corrected": 0,
        "content_drafts": 0,
        "day_status_counts": {
            "not_expected": 0,
            "empty": 0,
            "partial": 0,
            "complete": 0,
            "corrected": 0,
            "validated": 0,
            "inconsistent": 0,
            "non_school": 0,
        },
        "orphan_attendance_dates": sorted(orphan_attendance_dates),
        "orphan_content_dates": sorted(orphan_content_dates),
    }

    for day in days:
        entries = day.get("entries") or []
        entries.sort(key=lambda item: (
            item.get("aula_numero") or 0,
            item.get("component_id") or "",
        ))
        iso = _sid(day.get("date"))[:10]
        has_orphan = iso in orphan_attendance_dates or iso in orphan_content_dates
        # O router original já resolveu o calendário. Preservamos exatamente a
        # decisão de dia não letivo produzida antes da reconciliação.
        is_non_school = day.get("status") == "non_school"
        status = _classify_day(entries, has_orphan, is_non_school)
        day["status"] = status
        day["has_orphan_evidence"] = has_orphan
        day["expected_slots"] = len(entries)
        summary["day_status_counts"][status] = summary["day_status_counts"].get(status, 0) + 1
        summary["expected_slots"] += len(entries)
        for entry in entries:
            if entry.get("attendance_status") == "completed":
                summary["attendance_completed"] += 1
            elif entry.get("attendance_status") == "validated":
                summary["attendance_validated"] += 1
            if entry.get("content_status") == "published":
                summary["content_published"] += 1
            elif entry.get("content_status") == "corrected":
                summary["content_corrected"] += 1
            elif entry.get("content_status") == "draft":
                summary["content_drafts"] += 1

    result["days"] = days
    result["summary"] = summary
    result["canonical_evidence_policy"] = "issue-480-v1"
    return result


async def _reconcile_live(db, payload: dict) -> dict:
    if payload.get("matching_mode") != "strict":
        return payload
    class_id = payload.get("class_id")
    dates = [
        _sid(day.get("date"))[:10]
        for day in (payload.get("days") or [])
        if _sid(day.get("date"))
    ]
    if not class_id or not dates:
        return payload

    attendances = await db.attendance.find(
        {"class_id": class_id, "date": {"$in": dates}},
        {
            "_id": 0,
            "id": 1,
            "date": 1,
            "course_id": 1,
            "aula_numero": 1,
            "number_of_classes": 1,
            "records": 1,
            "validated_by": 1,
            "validated_by_name": 1,
            "validated_at": 1,
            "version": 1,
            "created_by": 1,
            "updated_by": 1,
        },
    ).to_list(5000)

    canonical = await db.content_entries.find(
        {"class_id": class_id, "date": {"$in": dates}, "deleted": False},
        {
            "_id": 0,
            "id": 1,
            "date": 1,
            "component_id": 1,
            "course_id": 1,
            "aula_numero": 1,
            "teacher_id": 1,
            "status": 1,
            "version": 1,
            "published_at": 1,
            "deleted": 1,
        },
    ).to_list(5000)

    # Diferentemente do fallback antigo "somente se canônico vazio", a política
    # #480 precisa preservar datas históricas legadas mesmo quando já existem
    # entries canônicos em outras datas do mesmo range. Na mesma data+componente,
    # porém, o canônico continua vencendo.
    from services.legacy_content_bridge import build_content_entries_from_legacy
    legacy = await build_content_entries_from_legacy(
        db,
        class_id=class_id,
        dates_in_range=dates,
    )
    content = merge_content_sources(canonical, legacy)
    return reconcile_strict_payload(payload, attendances, content)


def _remove_route(router, suffix: str, method: str):
    for route in list(router.routes):
        path = getattr(route, "path", "") or ""
        methods = getattr(route, "methods", set()) or set()
        if path.endswith(suffix) and method in methods:
            router.routes.remove(route)
            return route.endpoint
    return None


def install_calendar_diary_state_canonical_setup(calendar_diary_state_mod):
    """Envolve setup do calendário antes de server.py importar a função."""
    if getattr(calendar_diary_state_mod, "_issue_480_canonical_setup_installed", False):
        return
    original_setup = calendar_diary_state_mod.setup_calendar_diary_state_router

    def setup_calendar_diary_state_router(db):
        router = original_setup(db)
        original = _remove_route(router, "/diary-state/{class_id}", "GET")
        if original is None:
            raise RuntimeError("GET calendar/diary-state não encontrado para #480")

        @router.get("/diary-state/{class_id}")
        async def canonical_diary_state(
            class_id: str,
            request: Request,
            from_: str = Query(..., alias="from"),
            to: str = Query(...),
        ):
            payload = await original(class_id, request, from_, to)
            return await _reconcile_live(db, payload)

        return router

    calendar_diary_state_mod.setup_calendar_diary_state_router = setup_calendar_diary_state_router
    calendar_diary_state_mod._issue_480_canonical_setup_installed = True
