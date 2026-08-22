"""Fase 6.0A — regressão da proteção da âncora legada do Dossiê AEE V2."""

import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.routing import APIRoute

from routers.aee_v2_delete_guard import (
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

    delete_route = next(
        route
        for route in router.routes
        if isinstance(route, APIRoute) and "DELETE" in (route.methods or set())
    )
    read_route = next(
        route
        for route in router.routes
        if isinstance(route, APIRoute) and "GET" in (route.methods or set())
    )

    delete_before = len(delete_route.dependant.dependencies)
    read_before = len(read_route.dependant.dependencies)

    db = FakeDB()
    returned = install_aee_v2_delete_guard(router, db)

    assert returned is router
    assert len(delete_route.dependant.dependencies) == delete_before + 1
    assert len(read_route.dependant.dependencies) == read_before
    assert delete_route.dependant.dependencies[0].call.__name__ == "protect_legacy_anchor"

    # Uma segunda instalação não pode duplicar a dependência.
    install_aee_v2_delete_guard(router, db)
    assert len(delete_route.dependant.dependencies) == delete_before + 1
