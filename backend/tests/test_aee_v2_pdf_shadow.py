"""Fase 6.3A — contrato do Shadow Mode read-only do PDF do Diário AEE."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace

from fastapi import APIRouter, FastAPI, Request

from aee_v2.pdf_shadow import (
    build_pdf_schedule_shadow,
    install_aee_v2_pdf_shadow,
    legacy_pdf_sessions,
)
from aee_v2.repository import AEEV2IntegrityError


class FakeCursor:
    def __init__(self, docs):
        self.docs = deepcopy(docs)

    async def to_list(self, _length):
        return deepcopy(self.docs)


class FakeCollection:
    def __init__(self, docs):
        self.docs = deepcopy(docs)
        self.last_query = None
        self.last_projection = None

    def find(self, query, projection):
        self.last_query = deepcopy(query)
        self.last_projection = deepcopy(projection)
        return FakeCursor(self.docs)


class FakeDB:
    def __init__(self, planos):
        self.planos_aee = FakeCollection(planos)


def resolved(source, sessions, *, snapshot="snap-14", version=1, revision=14):
    return SimpleNamespace(
        source=source,
        active_snapshot_id=snapshot if source == "sidecar_active" else None,
        document_version=version if source == "sidecar_active" else None,
        revision=revision if source == "sidecar_active" else None,
        dossier=SimpleNamespace(
            schedule=SimpleNamespace(sessions=deepcopy(sessions))
        ),
    )


def plano(
    plan_id,
    *,
    days=None,
    start="09:30",
    end="11:00",
    local="SALA DE RECURSOS MULTIFUNCIONAIS",
    modalidade="individual",
):
    return {
        "id": plan_id,
        "student_id": f"student-{plan_id}",
        "school_id": "school-1",
        "academic_year": 2026,
        "status": "rascunho",
        "professor_aee_id": "prof-1",
        "created_by": "creator-1",
        "dias_atendimento": days or ["terca"],
        "horario_inicio": start,
        "horario_fim": end,
        "local_atendimento": local,
        "modalidade": modalidade,
    }


def session(
    weekday="terca",
    start="09:30",
    end="11:00",
    local="SALA DE RECURSOS MULTIFUNCIONAIS",
    modalidade="individual",
):
    return {
        "weekday": weekday,
        "start": start,
        "end": end,
        "local": local,
        "modalidade": modalidade,
    }


def _route(routes, path, method="GET"):
    method = method.upper()
    return next(
        route
        for route in routes
        if getattr(route, "path", None) == path
        and method in (getattr(route, "methods", set()) or set())
    )


def test_legacy_pdf_sessions_matches_fields_rendered_by_pdf():
    p = plano(
        "plan-1",
        days=["quarta", "terca"],
        local=None,
    )

    sessions = legacy_pdf_sessions(p)

    assert [s["weekday"] for s in sessions] == ["terca", "quarta"]
    assert sessions[0]["start"] == "09:30"
    assert sessions[0]["end"] == "11:00"
    assert sessions[0]["local"] == "Sala de Recursos Multifuncionais"
    assert sessions[0]["modalidade"] == "individual"


def test_pdf_shadow_reports_parity_for_v2_and_legacy_without_mutation():
    async def scenario():
        planos = [
            plano("plan-v2"),
            plano("plan-legacy", days=["terca", "quinta"], start="08:00", end="09:00"),
        ]
        db = FakeDB(planos)
        before = deepcopy(planos)

        async def resolver(_db, plan_id):
            if plan_id == "plan-v2":
                return resolved("sidecar_active", [session()])
            return resolved(
                "legacy",
                [
                    session("terca", "08:00", "09:00"),
                    session("quinta", "08:00", "09:00"),
                ],
            )

        result = await build_pdf_schedule_shadow(
            db,
            school_id="school-1",
            academic_year=2026,
            user={"id": "admin-1", "role": "admin"},
            resolver=resolver,
        )

        assert result["status"] == "parity"
        assert result["plans_total"] == 2
        assert result["sidecar_active_plans"] == 1
        assert result["legacy_plans"] == 1
        assert result["parity_plans"] == 2
        assert result["divergent_plans"] == 0
        assert result["error_plans"] == 0
        assert all(item["parity"] is True for item in result["items"])
        assert db.planos_aee.docs == before

    asyncio.run(scenario())


def test_pdf_shadow_surfaces_real_schedule_divergence():
    async def scenario():
        db = FakeDB([plano("plan-v2")])

        async def resolver(_db, _plan_id):
            return resolved("sidecar_active", [session(start="10:00", end="11:30")])

        result = await build_pdf_schedule_shadow(
            db,
            school_id="school-1",
            academic_year=2026,
            user={"id": "admin-1", "role": "admin"},
            resolver=resolver,
        )

        assert result["status"] == "divergent"
        assert result["divergent_plans"] == 1
        item = result["items"][0]
        assert item["effective_source"] == "sidecar_active"
        assert item["parity"] is False
        assert item["legacy_sessions"][0]["start"] == "09:30"
        assert item["effective_sessions"][0]["start"] == "10:00"

    asyncio.run(scenario())


def test_pdf_shadow_integrity_error_is_diagnostic_only():
    async def scenario():
        db = FakeDB([plano("plan-broken")])

        async def resolver(_db, _plan_id):
            raise AEEV2IntegrityError("Ponteiro ativo inconsistente")

        result = await build_pdf_schedule_shadow(
            db,
            school_id="school-1",
            academic_year=2026,
            user={"id": "admin-1", "role": "admin"},
            resolver=resolver,
        )

        assert result["status"] == "partial_error"
        assert result["error_plans"] == 1
        item = result["items"][0]
        assert item["status"] == "error"
        assert item["effective_sessions"] is None
        assert item["parity"] is None

    asyncio.run(scenario())


def test_pdf_shadow_replicates_professor_scope_filter():
    async def scenario():
        db = FakeDB([])

        await build_pdf_schedule_shadow(
            db,
            school_id="school-1",
            academic_year=2026,
            user={"id": "prof-user", "role": "professor"},
            student_id="student-1",
            professor_aee_id="prof-filter",
            resolver=lambda *_args, **_kwargs: None,
        )

        assert db.planos_aee.last_query == {
            "school_id": "school-1",
            "academic_year": 2026,
            "status": {"$in": ["ativo", "rascunho"]},
            "student_id": "student-1",
            "professor_aee_id": "prof-filter",
            "$or": [
                {"professor_aee_id": "prof-user"},
                {"created_by": "prof-user"},
            ],
        }

    asyncio.run(scenario())


def test_pdf_wrapper_returns_exact_legacy_response_and_runs_after_generation():
    async def scenario():
        router = APIRouter(prefix="/aee")
        order = []
        sentinel = object()

        @router.get("/diario/pdf")
        async def get_diario_aee_pdf(
            request: Request,
            school_id: str,
            academic_year: int,
            student_id: str | None = None,
            professor_aee_id: str | None = None,
        ):
            order.append("legacy_pdf")
            return sentinel

        @router.get("/diario")
        async def get_diario():
            return {"ok": True}

        async def user_getter(_request):
            order.append("user")
            return {"id": "admin-1", "role": "admin"}

        async def builder(_db, **kwargs):
            order.append("shadow")
            assert kwargs["school_id"] == "school-1"
            assert kwargs["academic_year"] == 2026
            return {
                "phase": "6.3A",
                "mode": "shadow_read_only",
                "status": "parity",
                "plans_total": 0,
                "sidecar_active_plans": 0,
                "legacy_plans": 0,
                "parity_plans": 0,
                "divergent_plans": 0,
                "error_plans": 0,
                "scope": {},
                "items": [],
            }

        diario_before = _route(router.routes, "/aee/diario").endpoint
        install_aee_v2_pdf_shadow(
            router,
            object(),
            user_getter=user_getter,
            diagnostics_builder=builder,
        )

        pdf_route = _route(router.routes, "/aee/diario/pdf")
        assert _route(router.routes, "/aee/diario").endpoint is diario_before

        result = await pdf_route.endpoint(
            request=object(),
            school_id="school-1",
            academic_year=2026,
        )

        assert result is sentinel
        assert order == ["legacy_pdf", "user", "shadow"]

        wrapped = pdf_route.endpoint
        install_aee_v2_pdf_shadow(
            router,
            object(),
            user_getter=user_getter,
            diagnostics_builder=builder,
        )
        assert pdf_route.endpoint is wrapped

    asyncio.run(scenario())


def test_pdf_wrapper_failure_never_changes_or_blocks_legacy_response():
    async def scenario():
        router = APIRouter(prefix="/aee")
        sentinel = object()

        @router.get("/diario/pdf")
        async def get_diario_aee_pdf(request: Request, school_id: str, academic_year: int):
            return sentinel

        async def user_getter(_request):
            return {"id": "admin-1", "role": "admin"}

        async def broken_builder(_db, **_kwargs):
            raise RuntimeError("falha proposital do shadow")

        install_aee_v2_pdf_shadow(
            router,
            object(),
            user_getter=user_getter,
            diagnostics_builder=broken_builder,
        )

        result = await _route(router.routes, "/aee/diario/pdf").endpoint(
            request=object(),
            school_id="school-1",
            academic_year=2026,
        )
        assert result is sentinel

    asyncio.run(scenario())


def test_pdf_shadow_wrapper_survives_fastapi_include_router_0_110_contract():
    router = APIRouter(prefix="/aee")

    @router.get("/diario/pdf")
    async def get_diario_aee_pdf(request: Request, school_id: str, academic_year: int):
        return b"PDF-LEGADO"

    async def user_getter(_request):
        return {"id": "admin-1", "role": "admin"}

    async def builder(_db, **_kwargs):
        return {
            "phase": "6.3A",
            "mode": "shadow_read_only",
            "status": "parity",
            "plans_total": 0,
            "sidecar_active_plans": 0,
            "legacy_plans": 0,
            "parity_plans": 0,
            "divergent_plans": 0,
            "error_plans": 0,
            "scope": {},
            "items": [],
        }

    install_aee_v2_pdf_shadow(
        router,
        object(),
        user_getter=user_getter,
        diagnostics_builder=builder,
    )

    app = FastAPI()
    app.include_router(router, prefix="/api")
    final_route = _route(app.routes, "/api/aee/diario/pdf")

    assert final_route.endpoint.__code__.co_filename.endswith("/aee_v2/pdf_shadow.py")
    assert hasattr(final_route.endpoint, "__wrapped__")
