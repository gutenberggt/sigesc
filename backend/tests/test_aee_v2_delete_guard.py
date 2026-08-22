"""Fase 6.0A — regressão da proteção da âncora legada do Dossiê AEE V2."""

import asyncio

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.routing import APIRoute

from aee_v2.delete_guard import (
    ensure_legacy_plan_delete_allowed,
    install_aee_v2_delete_guard,
)


class FakeHeadCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.last_query = None

    async def find_one(self, query, projection=None):
        self.last_query = query
        for doc in self.docs:
            if doc.get("legacy_plano_id") == query.get("legacy_plano_id"):
                return dict(doc)
        return None


class FakeDB:
    def __init__(self, heads=None):
        self.heads = FakeHeadCollection(heads)

    def __getitem__(self, name):
        assert name == "aee_dossier_v2_heads"
        return self.heads


async def allow_delete(_request):
    return None


def _delete_route(routes, path="/aee/planos/{plano_id}"):
    return next(
        route
        for route in routes
        if isinstance(route, APIRoute)
        and route.path == path
        and "DELETE" in (route.methods or set())
    )


def _guard_calls(route):
    return [
        dependency.call
        for dependency in route.dependant.dependencies
        if getattr(dependency.call, "__name__", None) == "protect_legacy_anchor"
    ]


def test_delete_guard_blocks_plan_with_v2_head():
    async def scenario():
        db = FakeDB([
            {
                "id": "head-1",
                "legacy_plano_id": "legacy-1",
                "active_snapshot_id": "snapshot-active-1",
            }
        ])

        try:
            await ensure_legacy_plan_delete_allowed(db, "legacy-1")
        except HTTPException as exc:
            assert exc.status_code == 409
            assert "Dossiê AEE V2" in exc.detail
            assert "exclusão não é permitida" in exc.detail
        else:
            raise AssertionError("Plano com head V2 deveria ter a exclusão bloqueada")

        assert db.heads.last_query == {"legacy_plano_id": "legacy-1"}

    asyncio.run(scenario())


def test_delete_guard_keeps_legacy_delete_when_no_v2_head():
    async def scenario():
        db = FakeDB()
        result = await ensure_legacy_plan_delete_allowed(db, "legacy-sem-v2")
        assert result is None
        assert db.heads.last_query == {"legacy_plano_id": "legacy-sem-v2"}

    asyncio.run(scenario())


def test_delete_guard_installer_targets_only_legacy_delete_and_is_idempotent():
    router = APIRouter(prefix="/aee")

    @router.get("/planos/{plano_id}")
    async def read_plan(plano_id: str):
        return {"id": plano_id}

    @router.delete("/planos/{plano_id}")
    async def delete_plan(plano_id: str):
        return {"id": plano_id}

    delete_route = _delete_route(router.routes)
    read_route = next(
        route
        for route in router.routes
        if isinstance(route, APIRoute) and "GET" in (route.methods or set())
    )

    delete_dependant_before = len(delete_route.dependant.dependencies)
    delete_declared_before = len(delete_route.dependencies)
    read_dependant_before = len(read_route.dependant.dependencies)
    read_declared_before = len(read_route.dependencies)

    db = FakeDB()
    returned = install_aee_v2_delete_guard(
        router,
        db,
        authorize_delete=allow_delete,
    )

    assert returned is router
    assert len(delete_route.dependant.dependencies) == delete_dependant_before + 1
    assert len(delete_route.dependencies) == delete_declared_before + 1
    assert len(read_route.dependant.dependencies) == read_dependant_before
    assert len(read_route.dependencies) == read_declared_before
    assert delete_route.dependant.dependencies[0].call.__name__ == "protect_legacy_anchor"

    # Uma segunda instalação não pode duplicar nenhuma das duas representações.
    install_aee_v2_delete_guard(
        router,
        db,
        authorize_delete=allow_delete,
    )
    assert len(delete_route.dependant.dependencies) == delete_dependant_before + 1
    assert len(delete_route.dependencies) == delete_declared_before + 1


def test_delete_guard_survives_fastapi_include_router():
    """Reproduz o fluxo real do server.py: APIRouter -> app.include_router()."""

    router = APIRouter(prefix="/aee")

    @router.delete("/planos/{plano_id}")
    async def p0_delete_plan(plano_id: str):
        return {"deleted": plano_id}

    db = FakeDB([{"id": "head-copy", "legacy_plano_id": "legacy-copy"}])
    install_aee_v2_delete_guard(
        router,
        db,
        authorize_delete=allow_delete,
    )

    app = FastAPI()
    app.include_router(router, prefix="/api")

    app_delete_route = _delete_route(
        app.routes,
        path="/api/aee/planos/{plano_id}",
    )

    assert app_delete_route.name == "p0_delete_plan"
    assert len(_guard_calls(app_delete_route)) == 1

    async def scenario():
        guard = _guard_calls(app_delete_route)[0]
        try:
            await guard(plano_id="legacy-copy", request=None)
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError(
                "Guard copiado para o FastAPI deveria bloquear plano com head V2"
            )

    asyncio.run(scenario())


def test_installed_dependency_blocks_before_legacy_delete_executes():
    async def scenario():
        router = APIRouter(prefix="/aee")

        @router.delete("/planos/{plano_id}")
        async def delete_plan(plano_id: str):
            return {"deleted": plano_id}

        db = FakeDB([{"id": "head-2", "legacy_plano_id": "legacy-2"}])
        install_aee_v2_delete_guard(
            router,
            db,
            authorize_delete=allow_delete,
        )

        delete_route = _delete_route(router.routes)
        dependency_call = delete_route.dependant.dependencies[0].call

        try:
            await dependency_call(plano_id="legacy-2", request=None)
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("Dependência instalada deveria bloquear o DELETE")

    asyncio.run(scenario())
