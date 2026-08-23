from __future__ import annotations

import inspect

from fastapi import APIRouter, FastAPI, Request
from fastapi.routing import APIRoute
from pydantic import BaseModel

from aee_v2.plan_write_governance import install_aee_v2_plan_write_governance
from aee_v2.time_integrity import install_aee_time_integrity


class PlanoCreatePayload(BaseModel):
    horario_inicio: str | None = None
    horario_fim: str | None = None


class PlanoUpdatePayload(BaseModel):
    horario_inicio: str | None = None
    horario_fim: str | None = None


class AtendimentoCreatePayload(BaseModel):
    horario_inicio: str | None = None
    horario_fim: str | None = None


class AtendimentoUpdatePayload(BaseModel):
    horario_inicio: str | None = None
    horario_fim: str | None = None


def _source_router() -> APIRouter:
    router = APIRouter(prefix="/aee")

    @router.post("/planos")
    async def create_plan(plano_data: PlanoCreatePayload, request: Request):
        return {"ok": True}

    @router.put("/planos/{plano_id}")
    async def update_plan(
        plano_id: str,
        plano_update: PlanoUpdatePayload,
        request: Request,
    ):
        return {"ok": True}

    @router.delete("/planos/{plano_id}")
    async def delete_plan(plano_id: str, request: Request):
        return {"ok": True}

    @router.post("/planos/{plano_id}/duplicate")
    async def duplicate_plan(plano_id: str, request: Request):
        return {"ok": True}

    @router.post("/atendimentos")
    async def create_attendance(
        atendimento_data: AtendimentoCreatePayload,
        request: Request,
    ):
        return {"ok": True}

    @router.put("/atendimentos/{atendimento_id}")
    async def update_attendance(
        atendimento_id: str,
        atendimento_update: AtendimentoUpdatePayload,
        request: Request,
    ):
        return {"ok": True}

    return router


def _route(routes, path: str, method: str) -> APIRoute:
    return next(
        route
        for route in routes
        if isinstance(route, APIRoute)
        and route.path == path
        and method in (route.methods or set())
    )


def test_final_fastapi_contract_keeps_body_and_request_after_aee_wrappers():
    """Regressão do 422 visto em produção durante a homologação da Fase 6.6D.

    O caso exige annotations adiadas (este módulo usa ``future.annotations``),
    wrappers em módulos diferentes e a clonagem real do FastAPI 0.110.1 via
    ``include_router``. Esse é o mesmo mecanismo que monta ``server.app``.
    """

    router = _source_router()
    db = {}

    install_aee_time_integrity(router, db)
    install_aee_v2_plan_write_governance(
        router,
        db,
        write_roles=("admin",),
        delete_roles=("admin",),
    )

    app = FastAPI()
    app.include_router(router, prefix="/api")

    expected = {
        ("POST", "/api/aee/planos"): {
            "path": [],
            "body": ["plano_data"],
            "model": PlanoCreatePayload,
        },
        ("PUT", "/api/aee/planos/{plano_id}"): {
            "path": ["plano_id"],
            "body": ["plano_update"],
            "model": PlanoUpdatePayload,
        },
        ("DELETE", "/api/aee/planos/{plano_id}"): {
            "path": ["plano_id"],
            "body": [],
            "model": None,
        },
        ("POST", "/api/aee/planos/{plano_id}/duplicate"): {
            "path": ["plano_id"],
            "body": [],
            "model": None,
        },
        ("POST", "/api/aee/atendimentos"): {
            "path": [],
            "body": ["atendimento_data"],
            "model": AtendimentoCreatePayload,
        },
        ("PUT", "/api/aee/atendimentos/{atendimento_id}"): {
            "path": ["atendimento_id"],
            "body": ["atendimento_update"],
            "model": AtendimentoUpdatePayload,
        },
    }

    for (method, path), contract in expected.items():
        route = _route(app.routes, path, method)

        assert route.dependant.request_param_name == "request"
        assert [param.name for param in route.dependant.path_params] == contract["path"]
        assert [param.name for param in route.dependant.query_params] == []
        assert [param.name for param in route.dependant.body_params] == contract["body"]

        signature = inspect.signature(route.endpoint)
        assert signature.parameters["request"].annotation is Request

        if contract["body"]:
            body_name = contract["body"][0]
            assert signature.parameters[body_name].annotation is contract["model"]


def test_wrapped_source_routes_already_expose_concrete_signatures_before_clone():
    router = _source_router()
    db = {}

    install_aee_time_integrity(router, db)
    install_aee_v2_plan_write_governance(
        router,
        db,
        write_roles=("admin",),
        delete_roles=("admin",),
    )

    targets = (
        ("POST", "/aee/planos"),
        ("PUT", "/aee/planos/{plano_id}"),
        ("DELETE", "/aee/planos/{plano_id}"),
        ("POST", "/aee/planos/{plano_id}/duplicate"),
        ("POST", "/aee/atendimentos"),
        ("PUT", "/aee/atendimentos/{atendimento_id}"),
    )

    for method, path in targets:
        route = _route(router.routes, path, method)
        signature = inspect.signature(route.endpoint)
        assert signature.parameters["request"].annotation is Request
        assert all(
            not isinstance(parameter.annotation, str)
            for parameter in signature.parameters.values()
        )
