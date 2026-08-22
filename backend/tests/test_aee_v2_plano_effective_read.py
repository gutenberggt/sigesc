from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import APIRouter, FastAPI

from aee_v2.contracts import AEEDossierV2
from aee_v2.plano_effective_read import (
    build_plano_effective_fields,
    enrich_plano_effective_response,
    install_aee_v2_plano_effective_read,
)
from aee_v2.plano_shadow import install_aee_v2_plano_shadow
from aee_v2.repository import AEEV2IntegrityError


def _dossier(*, lifecycle_status="active"):
    dossier = AEEDossierV2(
        student_id="student-1",
        school_id="school-1",
        academic_year=2026,
    )
    dossier.lifecycle.status = lifecycle_status
    dossier.study_case.state = "complete"
    dossier.paee.state = "complete"
    dossier.pei.state = "complete"
    return dossier


def _resolved(*, source="sidecar_active"):
    return SimpleNamespace(
        source=source,
        active_snapshot_id="snapshot-1" if source == "sidecar_active" else None,
        document_version=1 if source == "sidecar_active" else None,
        revision=14 if source == "sidecar_active" else None,
        dossier=_dossier(lifecycle_status="active" if source == "sidecar_active" else "draft"),
    )


def test_build_effective_fields_sidecar_active():
    async def resolver(_db, plano_id):
        assert plano_id == "plan-1"
        return _resolved(source="sidecar_active")

    fields = asyncio.run(
        build_plano_effective_fields(object(), "plan-1", resolver=resolver)
    )

    assert fields["effective_source"] == "sidecar_active"
    assert fields["effective_version"] == {
        "active_snapshot_id": "snapshot-1",
        "document_version": 1,
        "revision": 14,
    }
    assert fields["effective_dossier"]["student_id"] == "student-1"
    assert fields["effective_dossier"]["lifecycle"]["status"] == "active"
    assert fields["effective_error"] is None


def test_build_effective_fields_legacy_projection():
    async def resolver(_db, _plano_id):
        return _resolved(source="legacy")

    fields = asyncio.run(
        build_plano_effective_fields(object(), "plan-legacy", resolver=resolver)
    )

    assert fields["effective_source"] == "legacy"
    assert fields["effective_version"] is None
    assert fields["effective_dossier"]["lifecycle"]["status"] == "draft"
    assert fields["effective_error"] is None


def test_integrity_error_is_explicit_and_never_falls_back_to_legacy():
    async def resolver(_db, _plano_id):
        raise AEEV2IntegrityError("snapshot vigente ausente")

    fields = asyncio.run(
        build_plano_effective_fields(object(), "plan-broken", resolver=resolver)
    )

    assert fields["effective_source"] is None
    assert fields["effective_version"] is None
    assert fields["effective_dossier"] is None
    assert fields["effective_error"] == {
        "code": "AEE_V2_SNAPSHOT_INTEGRITY_ERROR",
        "message": "snapshot vigente ausente",
    }


def test_enrichment_is_additive_and_does_not_mutate_legacy_object():
    legacy = {
        "id": "plan-1",
        "status": "ativo",
        "student_name": "Estudante de teste",
        "horario_inicio": "09:30",
        "horario_fim": "11:00",
    }
    original_copy = dict(legacy)

    async def resolver(_db, _plano_id):
        return _resolved(source="sidecar_active")

    enriched = asyncio.run(
        enrich_plano_effective_response(
            object(),
            legacy,
            plano_id="plan-1",
            resolver=resolver,
        )
    )

    assert legacy == original_copy
    assert enriched is not legacy
    for key, value in original_copy.items():
        assert enriched[key] == value
    assert enriched["effective_source"] == "sidecar_active"
    assert enriched["effective_version"]["revision"] == 14
    assert enriched["effective_error"] is None


def test_missing_plan_id_is_explicit_without_destroying_legacy_payload():
    legacy = {"status": "ativo", "custom": 123}
    enriched = asyncio.run(
        enrich_plano_effective_response(object(), legacy)
    )

    assert enriched["status"] == "ativo"
    assert enriched["custom"] == 123
    assert enriched["effective_source"] is None
    assert enriched["effective_dossier"] is None
    assert enriched["effective_error"]["code"] == "AEE_V2_PLANO_EFFECTIVE_PLAN_ID_MISSING"


def test_route_chain_survives_fastapi_include_router_01101():
    router = APIRouter()

    @router.get("/aee/planos/{plano_id}")
    async def get_plano_aee(plano_id: str):
        return {"id": plano_id, "legacy_marker": "preserved", "status": "ativo"}

    async def diagnostics_builder(_db, plano_id):
        return {
            "phase": "6.4A",
            "legacy_plano_id": plano_id,
            "effective_source": "sidecar_active",
            "error": None,
        }

    async def resolver(_db, plano_id):
        assert plano_id == "plan-1"
        return _resolved(source="sidecar_active")

    install_aee_v2_plano_shadow(
        router,
        object(),
        diagnostics_builder=diagnostics_builder,
    )
    install_aee_v2_plano_effective_read(
        router,
        object(),
        resolver=resolver,
    )

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
    assert endpoint.__code__.co_filename.endswith("/aee_v2/plano_effective_read.py")
    assert endpoint.__wrapped__.__code__.co_filename.endswith("/aee_v2/plano_shadow.py")

    payload = asyncio.run(endpoint(plano_id="plan-1"))
    assert payload["legacy_marker"] == "preserved"
    assert payload["status"] == "ativo"
    assert payload["effective_source"] == "sidecar_active"
    assert payload["effective_version"]["document_version"] == 1
    assert payload["effective_dossier"]["pei"]["state"] == "complete"
    assert payload["effective_error"] is None


def test_installer_is_idempotent():
    router = APIRouter()

    @router.get("/aee/planos/{plano_id}")
    async def get_plano_aee(plano_id: str):
        return {"id": plano_id}

    install_aee_v2_plano_effective_read(router, object())
    endpoint_after_first_install = router.routes[0].endpoint

    install_aee_v2_plano_effective_read(router, object())
    assert router.routes[0].endpoint is endpoint_after_first_install
