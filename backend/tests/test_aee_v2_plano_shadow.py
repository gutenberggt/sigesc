from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import APIRouter, FastAPI

from aee_v2.plano_shadow import (
    build_plano_shadow_diagnostic,
    install_aee_v2_plano_shadow,
)
from aee_v2.repository import AEEV2IntegrityError


def _resolved(*, source="sidecar_active", sessions=1):
    dossier = SimpleNamespace(
        lifecycle=SimpleNamespace(status="active"),
        study_case=SimpleNamespace(state="complete"),
        paee=SimpleNamespace(state="complete"),
        pei=SimpleNamespace(state="complete"),
        schedule=SimpleNamespace(sessions=[object() for _ in range(sessions)]),
    )
    return SimpleNamespace(
        source=source,
        active_snapshot_id="snapshot-1" if source == "sidecar_active" else None,
        document_version=1 if source == "sidecar_active" else None,
        revision=14 if source == "sidecar_active" else None,
        dossier=dossier,
    )


def test_diagnostic_sidecar_active_exposes_canonical_states():
    async def resolver(db, plano_id):
        assert db is DB
        assert plano_id == "plan-1"
        return _resolved(source="sidecar_active", sessions=2)

    diagnostic = asyncio.run(
        build_plano_shadow_diagnostic(DB, "plan-1", resolver=resolver)
    )

    assert diagnostic == {
        "phase": "6.4A",
        "mode": "shadow_read_only",
        "legacy_plano_id": "plan-1",
        "effective_source": "sidecar_active",
        "active_snapshot_id": "snapshot-1",
        "document_version": 1,
        "revision": 14,
        "lifecycle_status": "active",
        "study_case_state": "complete",
        "paee_state": "complete",
        "pei_state": "complete",
        "schedule_sessions": 2,
        "error": None,
    }


def test_diagnostic_legacy_keeps_version_fields_empty():
    async def resolver(db, plano_id):
        resolved = _resolved(source="legacy", sessions=0)
        resolved.dossier.lifecycle.status = "draft"
        resolved.dossier.study_case.state = "legacy_projected"
        resolved.dossier.paee.state = "legacy_projected"
        resolved.dossier.pei.state = "legacy_projected"
        return resolved

    diagnostic = asyncio.run(
        build_plano_shadow_diagnostic(DB, "legacy-1", resolver=resolver)
    )

    assert diagnostic["effective_source"] == "legacy"
    assert diagnostic["active_snapshot_id"] is None
    assert diagnostic["document_version"] is None
    assert diagnostic["revision"] is None
    assert diagnostic["lifecycle_status"] == "draft"
    assert diagnostic["study_case_state"] == "legacy_projected"
    assert diagnostic["schedule_sessions"] == 0
    assert diagnostic["error"] is None


def test_integrity_error_is_diagnostic_and_never_fake_legacy():
    async def resolver(db, plano_id):
        raise AEEV2IntegrityError("snapshot vigente ausente")

    diagnostic = asyncio.run(
        build_plano_shadow_diagnostic(DB, "broken-1", resolver=resolver)
    )

    assert diagnostic["effective_source"] is None
    assert diagnostic["error"] == {
        "code": "AEE_V2_SNAPSHOT_INTEGRITY_ERROR",
        "message": "snapshot vigente ausente",
    }


def _router_with_legacy_endpoint(events=None, payload=None):
    router = APIRouter()
    response = payload if payload is not None else {"id": "plan-1", "legacy": True}

    @router.get("/aee/planos/{plano_id}")
    async def get_plano_aee(plano_id: str):
        if events is not None:
            events.append("legacy")
        return response

    return router, response


def test_wrapper_returns_exact_legacy_object_and_runs_shadow_after_legacy():
    events = []
    router, response = _router_with_legacy_endpoint(events=events)

    async def builder(db, plano_id):
        events.append("shadow")
        assert plano_id == "plan-1"
        return {
            "phase": "6.4A",
            "mode": "shadow_read_only",
            "legacy_plano_id": plano_id,
            "error": None,
        }

    install_aee_v2_plano_shadow(router, DB, diagnostics_builder=builder)
    endpoint = router.routes[0].endpoint
    result = asyncio.run(endpoint("plan-1"))

    assert result is response
    assert events == ["legacy", "shadow"]


def test_shadow_failure_never_blocks_or_replaces_legacy_response():
    router, response = _router_with_legacy_endpoint()

    async def broken_builder(db, plano_id):
        raise RuntimeError("shadow unavailable")

    install_aee_v2_plano_shadow(router, DB, diagnostics_builder=broken_builder)
    result = asyncio.run(router.routes[0].endpoint("plan-1"))

    assert result is response
    assert result == {"id": "plan-1", "legacy": True}


def test_install_is_idempotent():
    router, _ = _router_with_legacy_endpoint()

    first = install_aee_v2_plano_shadow(router, DB)
    endpoint = router.routes[0].endpoint
    second = install_aee_v2_plano_shadow(router, DB)

    assert first is router
    assert second is router
    assert router.routes[0].endpoint is endpoint


def test_fastapi_include_router_keeps_shadow_as_final_route_endpoint():
    router, _ = _router_with_legacy_endpoint()
    install_aee_v2_plano_shadow(router, DB)

    app = FastAPI()
    app.include_router(router, prefix="/api")

    matches = [
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/aee/planos/{plano_id}"
        and "GET" in (getattr(route, "methods", set()) or set())
    ]

    assert len(matches) == 1
    endpoint = matches[0].endpoint
    assert endpoint.__code__.co_filename.endswith("/aee_v2/plano_shadow.py")
    assert hasattr(endpoint, "__wrapped__")
    assert endpoint.__wrapped__.__code__.co_filename.endswith(
        "/tests/test_aee_v2_plano_shadow.py"
    )


DB = object()
