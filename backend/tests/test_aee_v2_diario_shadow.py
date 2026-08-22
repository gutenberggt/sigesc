"""Fase 6.2A — contrato do Shadow Mode no Diário AEE."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace

from fastapi import APIRouter, FastAPI, Request

from aee_v2.repository import AEEV2IntegrityError
from routers.aee_v2_diario_shadow import (
    enrich_diario_shadow,
    install_aee_v2_diario_shadow,
)


class FakeSchedule:
    def __init__(self, payload):
        self.payload = deepcopy(payload)

    def model_dump(self, mode="python"):
        assert mode == "json"
        return deepcopy(self.payload)


def resolved(
    *,
    source="sidecar_active",
    active_snapshot_id="snapshot-14",
    document_version=1,
    revision=14,
    sessions=None,
):
    schedule = {
        "carga_horaria_semanal": "2h",
        "sessions": sessions
        or [
            {
                "weekday": "terça-feira",
                "start": "09:00",
                "end": "10:00",
                "local": "Sala AEE V2",
                "modalidade": "individual",
                "effective_from": "2026-08-01",
            }
        ],
    }
    return SimpleNamespace(
        source=source,
        active_snapshot_id=active_snapshot_id,
        document_version=document_version,
        revision=revision,
        dossier=SimpleNamespace(schedule=FakeSchedule(schedule)),
    )


def legacy_payload():
    return {
        "school_id": "school-1",
        "academic_year": 2026,
        "grade_horarios": {
            "segunda-feira": [
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
                "plano": {
                    "id": "plan-1",
                    "student_id": "student-1",
                    "dias_atendimento": ["segunda-feira"],
                    "horario_inicio": "08:00",
                    "horario_fim": "09:00",
                    "modalidade": "grupo",
                },
                "student": {"id": "student-1", "full_name": "Estudante"},
                "estatisticas": {"total_atendimentos": 3},
            }
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


def test_shadow_adds_v2_metadata_without_changing_legacy_contract():
    async def scenario():
        payload = legacy_payload()
        legacy_before = deepcopy(payload)

        async def resolver(_db, plano_id):
            assert plano_id == "plan-1"
            return resolved()

        result = await enrich_diario_shadow(object(), payload, resolver=resolver)

        # Campos já existentes continuam byte-a-byte equivalentes em conteúdo.
        assert result["grade_horarios"] == legacy_before["grade_horarios"]
        assert result["fichas"][0]["plano"] == legacy_before["fichas"][0]["plano"]
        assert result["fichas"][0]["student"] == legacy_before["fichas"][0]["student"]
        assert result["fichas"][0]["estatisticas"] == legacy_before["fichas"][0]["estatisticas"]

        ficha = result["fichas"][0]
        assert ficha["effective_source"] == "sidecar_active"
        assert ficha["effective_version"] == {
            "active_snapshot_id": "snapshot-14",
            "document_version": 1,
            "revision": 14,
        }
        assert ficha["effective_schedule"]["sessions"][0]["weekday"] == "terça-feira"
        assert ficha["effective_schedule"]["sessions"][0]["start"] == "09:00"
        assert ficha["effective_shadow_error"] is None

    asyncio.run(scenario())


def test_shadow_keeps_legacy_source_explicit_without_cutover():
    async def scenario():
        payload = legacy_payload()

        async def resolver(_db, _plano_id):
            return resolved(
                source="legacy",
                active_snapshot_id=None,
                document_version=None,
                revision=None,
                sessions=[
                    {
                        "weekday": "segunda-feira",
                        "start": "08:00",
                        "end": "09:00",
                        "local": "Sala AEE",
                        "modalidade": "grupo",
                        "effective_from": None,
                    }
                ],
            )

        result = await enrich_diario_shadow(object(), payload, resolver=resolver)
        ficha = result["fichas"][0]

        assert ficha["effective_source"] == "legacy"
        assert ficha["effective_version"] is None
        assert ficha["effective_schedule"]["sessions"][0]["weekday"] == "segunda-feira"
        # A grade oficial ainda é a legada nesta fase.
        assert "segunda-feira" in result["grade_horarios"]

    asyncio.run(scenario())


def test_shadow_integrity_failure_does_not_break_legacy_diario():
    async def scenario():
        payload = legacy_payload()
        legacy_before = deepcopy(payload)

        async def resolver(_db, _plano_id):
            raise AEEV2IntegrityError("Ponteiro ativo inconsistente")

        result = await enrich_diario_shadow(object(), payload, resolver=resolver)

        assert result["grade_horarios"] == legacy_before["grade_horarios"]
        assert result["fichas"][0]["plano"] == legacy_before["fichas"][0]["plano"]
        ficha = result["fichas"][0]
        assert ficha["effective_source"] is None
        assert ficha["effective_schedule"] is None
        assert ficha["effective_shadow_error"] == {
            "code": "AEE_V2_SNAPSHOT_INTEGRITY_ERROR",
            "message": "Ponteiro ativo inconsistente",
        }

    asyncio.run(scenario())


def test_installer_wraps_only_diario_and_is_idempotent():
    router = APIRouter(prefix="/aee")

    @router.get("/diario")
    async def get_diario_aee(request: Request, school_id: str, academic_year: int):
        return legacy_payload()

    @router.get("/planos")
    async def list_planos():
        return {"items": []}

    diario = _route(router.routes, "/aee/diario")
    planos = _route(router.routes, "/aee/planos")
    original_diario = diario.endpoint
    original_planos = planos.endpoint

    async def resolver(_db, _plano_id):
        return resolved()

    returned = install_aee_v2_diario_shadow(router, object(), resolver=resolver)
    assert returned is router
    assert diario.endpoint is not original_diario
    assert diario.dependant.call is diario.endpoint
    assert planos.endpoint is original_planos
    assert diario.endpoint.__name__ == original_diario.__name__

    wrapped = diario.endpoint
    install_aee_v2_diario_shadow(router, object(), resolver=resolver)
    assert diario.endpoint is wrapped


def test_shadow_wrapper_survives_fastapi_include_router_0_110_contract():
    async def scenario():
        router = APIRouter(prefix="/aee")

        @router.get("/diario")
        async def get_diario_aee(request: Request, school_id: str, academic_year: int):
            return legacy_payload()

        async def resolver(_db, _plano_id):
            return resolved()

        install_aee_v2_diario_shadow(router, object(), resolver=resolver)

        app = FastAPI()
        app.include_router(router, prefix="/api")
        final_route = _route(app.routes, "/api/aee/diario")

        result = await final_route.endpoint(
            request=None,
            school_id="school-1",
            academic_year=2026,
        )

        assert final_route.endpoint.__name__ == "get_diario_aee"
        assert result["fichas"][0]["effective_source"] == "sidecar_active"
        assert result["grade_horarios"]["segunda-feira"][0]["horario_inicio"] == "08:00"

    asyncio.run(scenario())
