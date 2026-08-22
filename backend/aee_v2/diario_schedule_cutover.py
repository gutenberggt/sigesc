"""Fase 6.2B — cutover controlado da agenda efetiva no Diário AEE.

A Fase 6.2A já calcula, por ficha, ``effective_source`` e
``effective_schedule``. Esta camada consome somente esses metadados e troca a
``grade_horarios`` da resposta pela grade efetiva quando TODAS as fichas estão
aptas ao cutover.

Salvaguardas:
- ``grade_horarios_legacy`` preserva uma cópia da grade anterior na resposta;
- o cutover é atômico por resposta: qualquer erro de shadow bloqueia a troca;
- nenhum dado é persistido;
- o formato de cada item da grade permanece compatível com o legado
  (student_id, student_name, horario_inicio, horario_fim).
"""

from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any


_ALLOWED_EFFECTIVE_SOURCES = {"legacy", "sidecar_active"}


def _route_for(base_router, path: str, method: str):
    method = method.upper()
    matches = [
        route
        for route in base_router.routes
        if getattr(route, "path", None) == path
        and method in (getattr(route, "methods", set()) or set())
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"AEE v2 Schedule Cutover esperava exatamente uma rota {method} {path}; "
            f"encontrou {len(matches)}."
        )
    return matches[0]


def _plan_id(ficha: dict) -> str | None:
    plano = ficha.get("plano")
    if not isinstance(plano, dict):
        return None
    value = plano.get("id")
    return str(value) if value else None


def _student_identity(ficha: dict) -> tuple[str | None, str]:
    plano = ficha.get("plano") if isinstance(ficha.get("plano"), dict) else {}
    student = ficha.get("student") if isinstance(ficha.get("student"), dict) else {}
    student_id = student.get("id") or plano.get("student_id")
    student_name = student.get("full_name") or plano.get("student_name") or "N/A"
    return (str(student_id) if student_id else None, str(student_name))


def _cutover_blockers(fichas: list) -> list[dict]:
    blockers: list[dict] = []

    for index, ficha in enumerate(fichas):
        if not isinstance(ficha, dict):
            blockers.append(
                {
                    "code": "AEE_V2_CUTOVER_INVALID_FICHA",
                    "ficha_index": index,
                    "message": "Ficha do Diário AEE possui formato inválido.",
                }
            )
            continue

        plano_id = _plan_id(ficha)
        shadow_error = ficha.get("effective_shadow_error")
        if shadow_error:
            blockers.append(
                {
                    "code": "AEE_V2_CUTOVER_SHADOW_ERROR",
                    "plano_id": plano_id,
                    "shadow_error": deepcopy(shadow_error),
                    "message": "Fonte efetiva da ficha não pôde ser resolvida com segurança.",
                }
            )
            continue

        source = ficha.get("effective_source")
        if source not in _ALLOWED_EFFECTIVE_SOURCES:
            blockers.append(
                {
                    "code": "AEE_V2_CUTOVER_SOURCE_UNRESOLVED",
                    "plano_id": plano_id,
                    "message": "Ficha sem fonte efetiva válida para o cutover da agenda.",
                }
            )
            continue

        schedule = ficha.get("effective_schedule")
        sessions = schedule.get("sessions") if isinstance(schedule, dict) else None
        if not isinstance(sessions, list):
            blockers.append(
                {
                    "code": "AEE_V2_CUTOVER_SCHEDULE_INVALID",
                    "plano_id": plano_id,
                    "message": "Agenda efetiva da ficha não possui uma lista válida de sessões.",
                }
            )
            continue

        for session_index, session in enumerate(sessions):
            if not isinstance(session, dict) or not str(session.get("weekday") or "").strip():
                blockers.append(
                    {
                        "code": "AEE_V2_CUTOVER_SESSION_WEEKDAY_MISSING",
                        "plano_id": plano_id,
                        "session_index": session_index,
                        "message": "Sessão da agenda efetiva sem dia da semana; cutover bloqueado.",
                    }
                )

    return blockers


def build_effective_grade(fichas: list) -> tuple[dict, int, int, int]:
    """Constrói grade compatível com o contrato legado a partir do shadow V2."""

    grade: dict[str, list[dict]] = {}
    sessions_total = 0
    sidecar_active_fichas = 0
    legacy_fichas = 0

    for ficha in fichas:
        source = ficha.get("effective_source")
        if source == "sidecar_active":
            sidecar_active_fichas += 1
        elif source == "legacy":
            legacy_fichas += 1

        schedule = ficha.get("effective_schedule") or {}
        sessions = schedule.get("sessions") or []
        student_id, student_name = _student_identity(ficha)

        for session in sessions:
            weekday = str(session.get("weekday") or "").strip()
            grade.setdefault(weekday, []).append(
                {
                    "student_id": student_id,
                    "student_name": student_name,
                    "horario_inicio": session.get("start"),
                    "horario_fim": session.get("end"),
                }
            )
            sessions_total += 1

    for entries in grade.values():
        entries.sort(
            key=lambda item: (
                item.get("horario_inicio") or "00:00",
                item.get("student_name") or "",
            )
        )

    return grade, sessions_total, sidecar_active_fichas, legacy_fichas


def apply_diario_schedule_cutover(payload: Any):
    """Troca a grade somente quando todo o shadow da resposta é confiável.

    Em qualquer bloqueio, ``grade_horarios`` permanece exatamente como veio do
    endpoint legado/shadow. A cópia ``grade_horarios_legacy`` fica disponível
    tanto no sucesso quanto no bloqueio para comparação operacional.
    """

    if not isinstance(payload, dict):
        return payload

    fichas = payload.get("fichas")
    legacy_grade = payload.get("grade_horarios")
    if not isinstance(fichas, list) or not isinstance(legacy_grade, dict):
        return payload

    payload["grade_horarios_legacy"] = deepcopy(legacy_grade)

    blockers = _cutover_blockers(fichas)
    if blockers:
        payload["effective_schedule_cutover"] = {
            "status": "blocked",
            "grade_source": "legacy",
            "fichas_total": len(fichas),
            "blockers": blockers,
        }
        return payload

    effective_grade, sessions_total, sidecar_count, legacy_count = build_effective_grade(fichas)
    payload["grade_horarios"] = effective_grade
    payload["effective_schedule_cutover"] = {
        "status": "effective",
        "grade_source": "effective",
        "fichas_total": len(fichas),
        "sessions_total": sessions_total,
        "sidecar_active_fichas": sidecar_count,
        "legacy_fichas": legacy_count,
        "blockers": [],
    }
    return payload


def install_aee_v2_diario_schedule_cutover(base_router):
    """Envolve somente GET /aee/diario depois do Shadow Mode da Fase 6.2A."""

    if getattr(base_router, "_aee_v2_diario_schedule_cutover_installed", False):
        return base_router

    target = _route_for(base_router, "/aee/diario", "GET")
    current_endpoint = target.endpoint

    @wraps(current_endpoint)
    async def cutover_endpoint(*args, **kwargs):
        result = await current_endpoint(*args, **kwargs)
        return apply_diario_schedule_cutover(result)

    target.endpoint = cutover_endpoint
    target.dependant.call = cutover_endpoint

    setattr(base_router, "_aee_v2_diario_schedule_cutover_installed", True)
    return base_router


def install_aee_v2_diario_schedule_cutover_setup(aee_module):
    """Encadeia o cutover depois dos adapters previamente instalados."""

    if getattr(aee_module, "_aee_v2_diario_schedule_cutover_setup_installed", False):
        return

    original_setup = aee_module.setup_aee_router

    def wrapped_setup(db, audit_service):
        configured = original_setup(db, audit_service)
        return install_aee_v2_diario_schedule_cutover(configured)

    aee_module.setup_aee_router = wrapped_setup
    aee_module._aee_v2_diario_schedule_cutover_setup_installed = True
