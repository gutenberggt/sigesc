"""Fase 6.2B — regressão do cutover controlado da agenda efetiva."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace

from fastapi import APIRouter, FastAPI, Request

from aee_v2.diario_schedule_cutover import (
    apply_diario_schedule_cutover,
    install_aee_v2_diario_schedule_cutover,
)
from aee_v2.diario_shadow import install_aee_v2_diario_shadow


class FakeSchedule:
    def __init__(self, sessions):
        self.sessions = deepcopy(sessions)

    def model_dump(self, mode="python"):
        assert mode == "json"
        return {"carga_horaria_semanal": None, "sessions": deepcopy(self.sessions)}


def resolved(source, sessions, *, revision=None):
    return SimpleNamespace(
        source=source,
        active_snapshot_id="snapshot-14" if source == "sidecar_active" else None,
        document_version=1 if source == "sidecar_active" else None,
        revision=revision if source == "sidecar_active" else None,
        dossier=SimpleNamespace(schedule=FakeSchedule(sessions)),
    )


def legacy_grade():
    return {
        "segunda": [
            {
                "student_id": "student-v2",
                "student_name": "Estudante V2",
                "horario_inicio": "08:00",
                "horario_fim": "09:00",
            }
        ],
        "quarta": [
            {
                "student_id": "student-legacy",
                "student_name": "Estudante Legado",
                "horario_inicio": "10:00",
                "horario_fim": "11:00",
            }
        ],
    }


def enriched_payload():
    return {
        "school_id": "school-1",
        "academic_year": 2026,
        "grade_horarios": legacy_grade(),
        "fichas": [
            {
                "plano": {"id": "plan-v2", "student_id": "student-v2"},
                "student": {"id": "student-v2", "full_name": "Estudante V2"},
                "effective_source": "sidecar_active",
                "effective_version": {
                    "active_snapshot_id": "snapshot-14",
                    "document_version": 1,
                    "revision": 14,
                },
                "effective_schedule": {
                    "sessions": [
                        {
                            "weekday": "terca",
                            "start": "09:30",
                            "end": "11:00",
                            "local": "Sala V2",
                            "modalidade": "individual",
                        }
                    ]
                },
                "effective_shadow_error": None,
            },
            {
                "plano": {"id": "plan-legacy", "student_id": "student-legacy"},
                "student": {
                    "id": "student-legacy",
                    "full_name": "Estudante Legado",
                },
                "effective_source": "legacy",
                "effective_version": None,
                "effective_schedule": {
                    "sessions": [
                        {
                            "weekday": "quinta",
                            "start": "07:30",
                            "end": "08:30",
                            "local": "Sala AEE",
                            "modalidade": "individual",
                        }
                    ]
                },
                "effective_shadow_error": None,
            },
        ],
    }


def _route(routes, path, method="GET"):
    method = method.upper()
    return next(
        route
        for route in routes
        if getattr(route, "path", None) == path
        and method in (getattr(route, "methods", set()) or set())
    )


def test_cutover_replaces_only_grade_and_keeps_legacy_copy():
    payload = enriched_payload()
    original = deepcopy(payload)

    result = apply_diario_schedule_cutover(payload)

    assert result["grade_horarios_legacy"] == original["grade_horarios"]
    assert result["grade_horarios"] == {
        "terca": [
            {
                "student_id": "student-v2",
                "student_name": "Estudante V2",
                "horario_inicio": "09:30",
                "horario_fim": "11:00",
            }
        ],
        "quinta": [
            {
                "student_id": "student-legacy",
                "student_name": "Estudante Legado",
                "horario_inicio": "07:30",
                "horario_fim": "08:30",
            }
        ],
    }

    # Fichas e metadados do shadow permanecem intactos.
    assert result["fichas"] == original["fichas"]
    assert result["effective_schedule_cutover"] == {
        "status": "effective",
        "grade_source": "effective",
        "fichas_total": 2,
        "sessions_total": 2,
        "sidecar_active_fichas": 1,
        "legacy_fichas": 1,
        "blockers": [],
    }


def test_cutover_is_atomic_and_keeps_legacy_grade_when_shadow_has_error():
    payload = enriched_payload()
    original_grade = deepcopy(payload["grade_horarios"])
    payload["fichas"][1]["effective_source"] = None
    payload["fichas"][1]["effective_schedule"] = None
    payload["fichas"][1]["effective_shadow_error"] = {
        "code": "AEE_V2_SNAPSHOT_INTEGRITY_ERROR",
        "message": "Ponteiro ativo inconsistente",
    }

    result = apply_diario_schedule_cutover(payload)

    assert result["grade_horarios"] == original_grade
    assert result["grade_horarios_legacy"] == original_grade
    status = result["effective_schedule_cutover"]
    assert status["status"] == "blocked"
    assert status["grade_source"] == "legacy"
    assert len(status["blockers"]) == 1
    assert status["blockers"][0]["code"] == "AEE_V2_CUTOVER_SHADOW_ERROR"


def test_cutover_blocks_session_without_weekday_instead_of_hiding_student():
    payload = enriched_payload()
    original_grade = deepcopy(payload["grade_horarios"])
    payload["fichas"][0]["effective_schedule"]["sessions"][0]["weekday"] = None

    result = apply_diario_schedule_cutover(payload)

    assert result["grade_horarios"] == original_grade
    blocker = result["effective_schedule_cutover"]["blockers"][0]
    assert blocker["code"] == "AEE_V2_CUTOVER_SESSION_WEEKDAY_MISSING"
    assert blocker["plano_id"] == "plan-v2"


def test_empty_effective_schedule_is_valid_and_produces_empty_grade():
    payload = enriched_payload()
    payload["fichas"] = [payload["fichas"][0]]
    payload["fichas"][0]["effective_schedule"] = {"sessions": []}

    result = apply_diario_schedule_cutover(payload)

    assert result["grade_horarios"] == {}
    assert result["grade_horarios_legacy"] == legacy_grade()
    assert result["effective_schedule_cutover"]["status"] == "effective"
    assert result["effective_schedule_cutover"]["sessions_total"] == 0


def test_grade_items_are_sorted_by_effective_start_time():
    payload = enriched_payload()
    payload["fichas"] = [
        deepcopy(payload["fichas"][0]),
        deepcopy(payload["fichas"][0]),
    ]
    payload["fichas"][0]["student"] = {"id": "s-late", "full_name": "Mais tarde"}
    payload["fichas"][0]["effective_schedule"]["sessions"][0].update(
        {"weekday": "terca", "start": "10:00", "end": "11:00"}
    )
    payload["fichas"][1]["student"] = {"id": "s-early", "full_name": "Mais cedo"}
    payload["fichas"][1]["effective_schedule"]["sessions"][0].update(
        {"weekday": "terca", "start": "08:00", "end": "09:00"}
    )

    result = apply_diario_schedule_cutover(payload)

    assert [item["student_name"] for item in result["grade_horarios"]["terca"]] == [
        "Mais cedo",
        "Mais tarde",
    ]


def test_shadow_then_cutover_survives_include_router_and_uses_effective_schedule():
    async def scenario():
        router = APIRouter(prefix="/aee")

        @router.get("/diario")
        async def get_diario_aee(request: Request, school_id: str, academic_year: int):
            return {
                "school_id": school_id,
                "academic_year": academic_year,
                "grade_horarios": {
                    "segunda": [
                        {
                            "student_id": "student-1",
                            "student_name": "Estudante",
                            "horario_inicio": "08:00",
                            "horario_fim": "09:00",
                        }
                    ]
                },
                "fichas": [
                    {
                        "plano": {"id": "plan-1", "student_id": "student-1"},
                        "student": {"id": "student-1", "full_name": "Estudante"},
                    }
                ],
            }

        @router.get("/planos")
        async def list_planos():
            return {"items": []}

        async def resolver(_db, plano_id):
            assert plano_id == "plan-1"
            return resolved(
                "sidecar_active",
                [
                    {
                        "weekday": "terca",
                        "start": "09:30",
                        "end": "11:00",
                        "local": "Sala V2",
                        "modalidade": "individual",
                    }
                ],
                revision=14,
            )

        install_aee_v2_diario_shadow(router, object(), resolver=resolver)
        diario = _route(router.routes, "/aee/diario")
        shadow_endpoint = diario.endpoint
        planos_endpoint = _route(router.routes, "/aee/planos").endpoint

        install_aee_v2_diario_schedule_cutover(router)
        assert diario.endpoint is not shadow_endpoint
        assert _route(router.routes, "/aee/planos").endpoint is planos_endpoint

        # Idempotência.
        wrapped = diario.endpoint
        install_aee_v2_diario_schedule_cutover(router)
        assert diario.endpoint is wrapped

        app = FastAPI()
        app.include_router(router, prefix="/api")
        final_route = _route(app.routes, "/api/aee/diario")

        result = await final_route.endpoint(
            request=None,
            school_id="school-1",
            academic_year=2026,
        )

        assert result["effective_schedule_cutover"]["status"] == "effective"
        assert result["grade_horarios_legacy"]["segunda"][0]["horario_inicio"] == "08:00"
        assert result["grade_horarios"]["terca"][0]["horario_inicio"] == "09:30"
        assert result["fichas"][0]["effective_source"] == "sidecar_active"
        assert final_route.endpoint.__name__ == "get_diario_aee"
        assert hasattr(final_route.endpoint, "__wrapped__")

    asyncio.run(scenario())
