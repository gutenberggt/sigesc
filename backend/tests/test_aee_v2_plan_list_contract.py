from __future__ import annotations

import asyncio
from copy import deepcopy
import json

from fastapi import APIRouter, FastAPI, HTTPException, Request

from aee_v2.legacy_mapper import project_legacy_plan
from aee_v2.plan_list_contract import (
    PUBLIC_FIELDS,
    PlanListContractError,
    apply_plan_list_contract,
    build_plan_list_additive_diagnostic,
    derive_mutation_policy,
    install_aee_v2_plan_list_contract,
    project_plan_list_contract_item,
    select_effective_ids_for_status,
)
from aee_v2.plan_list_effective import resolve_plan_list_effective_batch
from aee_v2.repository import AEEV2Repository
from aee_v2.versioning import make_snapshot


DB_SENTINEL = object()
_UNSET = object()


BASE_PLAN = {
    "id": "plan-1",
    "student_id": "student-1",
    "school_id": "school-1",
    "academic_year": 2026,
    "professor_aee_id": "prof-1",
    "professor_aee_nome": "Professor",
    "status": "rascunho",
    "dias_atendimento": ["segunda"],
    "horario_inicio": "08:00",
    "horario_fim": "09:00",
    "local_atendimento": "Sala AEE",
}


def _plan(index=1, **updates):
    plan = deepcopy(BASE_PLAN)
    plan.update({"id": f"plan-{index}", "student_id": f"student-{index}"})
    plan.update(updates)
    return plan


def _summary(
    plan_id="plan-1",
    *,
    v2_managed=False,
    management_state="legacy_only",
    source="legacy",
    lifecycle="draft",
    effective_status="rascunho",
    days=_UNSET,
    shape="legacy_projection",
    integrity_error=None,
    working_error=None,
    active_snapshot_id=None,
    working_snapshot_id=None,
    document_version=None,
    revision=None,
):
    return {
        "legacy_plano_id": plan_id,
        "v2_managed": v2_managed,
        "management_state": management_state,
        "effective_source": source,
        "effective_version": {
            "active_snapshot_id": active_snapshot_id,
            "document_version": document_version,
            "revision": revision,
            "working_snapshot_id": working_snapshot_id,
        },
        "legacy_status": "rascunho",
        "effective_lifecycle_status": lifecycle,
        "effective_legacy_status": effective_status,
        "legacy_days": ["segunda"],
        "effective_days": ["segunda"] if days is _UNSET else days,
        "schedule_shape": shape,
        "status_parity": effective_status == "rascunho",
        "days_parity": True,
        "integrity_error": integrity_error,
        "working_integrity_error": working_error,
    }


def _batch(*summaries, head_queries=1, snapshot_queries=1):
    return {
        "items": list(summaries),
        "performance": {
            "head_queries": head_queries,
            "snapshot_queries": snapshot_queries,
            "batch_ms": 2.5,
        },
    }


def test_public_contract_has_exactly_six_additive_fields():
    assert PUBLIC_FIELDS == (
        "v2_managed",
        "effective_source",
        "effective_version",
        "effective_summary",
        "effective_error",
        "mutation_policy",
    )


def test_legacy_only_adds_contract_without_mutating_legacy_item():
    legacy = {
        "id": "plan-1",
        "status": "rascunho",
        "dias_atendimento": ["segunda"],
        "student_name": "Nome legado",
        "custom": {"preservar": True},
    }
    original = deepcopy(legacy)

    projected = project_plan_list_contract_item(legacy, _summary())

    assert legacy == original
    for key, value in original.items():
        assert projected[key] == value
    assert projected["v2_managed"] is False
    assert projected["effective_source"] == "legacy"
    assert projected["effective_summary"] == {
        "lifecycle_status": "draft",
        "legacy_compatible_status": "rascunho",
        "schedule_summary": {
            "days": ["segunda"],
            "shape": "legacy_projection",
        },
    }
    assert projected["effective_error"] is None
    assert projected["mutation_policy"] == "legacy_allowed"


def test_working_only_keeps_legacy_source_but_requires_dossier_v2():
    projected = project_plan_list_contract_item(
        {"id": "plan-1", "status": "rascunho"},
        _summary(
            v2_managed=True,
            management_state="working_only",
            source="legacy",
            working_snapshot_id="working-1",
        ),
    )

    assert projected["v2_managed"] is True
    assert projected["effective_source"] == "legacy"
    assert projected["effective_version"]["working_snapshot_id"] == "working-1"
    assert projected["mutation_policy"] == "dossier_v2_required"


def test_active_sentinel_preserves_legacy_status_and_exposes_effective_active():
    legacy = {
        "id": "plan-1",
        "status": "rascunho",
        "dias_atendimento": ["segunda"],
        "student_name": "Sentinela",
    }
    projected = project_plan_list_contract_item(
        legacy,
        _summary(
            v2_managed=True,
            management_state="active",
            source="sidecar_active",
            lifecycle="active",
            effective_status="ativo",
            shape="homogeneous",
            active_snapshot_id="active-1",
            document_version=1,
            revision=14,
        ),
    )

    assert projected["status"] == "rascunho"
    assert projected["student_name"] == "Sentinela"
    assert projected["effective_source"] == "sidecar_active"
    assert projected["effective_summary"]["lifecycle_status"] == "active"
    assert projected["effective_summary"]["legacy_compatible_status"] == "ativo"
    assert projected["effective_version"] == {
        "active_snapshot_id": "active-1",
        "document_version": 1,
        "revision": 14,
        "working_snapshot_id": None,
    }
    assert projected["mutation_policy"] == "dossier_v2_required"
    assert projected["effective_error"] is None


def test_primary_integrity_error_is_represented_without_fake_legacy_fallback():
    error = {
        "code": "AEE_V2_PLAN_LIST_ACTIVE_SNAPSHOT_HASH_INVALID",
        "message": "Snapshot ativo falhou na verificação de integridade.",
    }
    projected = project_plan_list_contract_item(
        {"id": "plan-1", "status": "rascunho"},
        _summary(
            v2_managed=True,
            management_state="integrity_error",
            source=None,
            lifecycle=None,
            effective_status=None,
            days=None,
            shape=None,
            integrity_error=error,
            active_snapshot_id="active-1",
        ),
    )

    assert projected["effective_source"] is None
    assert projected["effective_error"] == error
    assert projected["mutation_policy"] == "blocked_integrity"
    assert projected["status"] == "rascunho"


def test_valid_active_with_broken_working_preserves_read_authority_and_blocks_mutation():
    working_error = {
        "code": "AEE_V2_PLAN_LIST_WORKING_SNAPSHOT_MISSING",
        "message": "Snapshot working ausente.",
    }
    summary = _summary(
        v2_managed=True,
        management_state="active",
        source="sidecar_active",
        lifecycle="active",
        effective_status="ativo",
        shape="homogeneous",
        active_snapshot_id="active-1",
        working_snapshot_id="working-missing",
        document_version=2,
        revision=9,
        working_error=working_error,
    )
    projected = project_plan_list_contract_item(
        {"id": "plan-1", "status": "rascunho"}, summary
    )

    assert projected["effective_source"] == "sidecar_active"
    assert projected["effective_error"] is None
    assert projected["mutation_policy"] == "blocked_integrity"
    assert derive_mutation_policy(summary) == "blocked_integrity"


def test_schedule_contract_represents_all_supported_shapes_without_flattening():
    for shape, days in (
        ("legacy_projection", ["segunda"]),
        ("empty", []),
        ("homogeneous", ["segunda", "quarta"]),
        ("heterogeneous", ["terça", "quinta"]),
        (None, None),
    ):
        source = None if shape is None else (
            "legacy" if shape == "legacy_projection" else "sidecar_active"
        )
        error = (
            {"code": "AEE_V2_TEST", "message": "indisponível"}
            if source is None
            else None
        )
        projected = project_plan_list_contract_item(
            {"id": "plan-1", "status": "rascunho"},
            _summary(
                v2_managed=source != "legacy",
                source=source,
                lifecycle=None if source is None else "active",
                effective_status=None if source is None else "ativo",
                days=days,
                shape=shape,
                integrity_error=error,
            ),
        )
        schedule = projected["effective_summary"]["schedule_summary"]
        assert schedule["days"] == days
        assert schedule["shape"] == shape
        assert "start" not in schedule
        assert "end" not in schedule


def test_apply_contract_preserves_order_total_and_every_legacy_pair():
    legacy_result = {
        "items": [
            {"id": "plan-2", "status": "rascunho", "student_name": "B"},
            {"id": "plan-1", "status": "rascunho", "student_name": "A"},
        ],
        "total": 23,
        "other_top_level": "preservar",
    }
    original = deepcopy(legacy_result)
    batch = _batch(_summary("plan-1"), _summary("plan-2"))

    result = apply_plan_list_contract(legacy_result, batch)

    assert legacy_result == original
    assert result["total"] == 23
    assert result["other_top_level"] == "preservar"
    assert [item["id"] for item in result["items"]] == ["plan-2", "plan-1"]
    for before, after in zip(original["items"], result["items"]):
        for key, value in before.items():
            assert after[key] == value


def test_contract_fails_closed_on_unmatchable_or_colliding_structure():
    try:
        apply_plan_list_contract(
            {"items": [{"id": "plan-1"}], "total": 1},
            _batch(_summary("other-plan")),
        )
    except PlanListContractError:
        pass
    else:
        raise AssertionError("Era esperado erro de casamento de summaries")

    try:
        project_plan_list_contract_item(
            {"id": "plan-1", "v2_managed": "legacy-collision"},
            _summary(),
        )
    except PlanListContractError:
        pass
    else:
        raise AssertionError("Era esperado erro de colisão de contrato")


def test_effective_filter_helper_prepares_6_6c_without_changing_runtime_filter():
    legacy_ids_ativo = set()
    legacy_ids_rascunho = {"plan-1", "plan-2"}
    summaries = [
        _summary(
            "plan-1",
            v2_managed=True,
            source="sidecar_active",
            lifecycle="active",
            effective_status="ativo",
            shape="homogeneous",
        ),
        _summary("plan-2"),
    ]

    assert select_effective_ids_for_status(summaries, "ativo") == {"plan-1"}
    assert select_effective_ids_for_status(summaries, "rascunho") == {"plan-2"}
    assert legacy_ids_ativo == set()
    assert legacy_ids_rascunho == {"plan-1", "plan-2"}


def test_additive_diagnostic_is_6_6b_aggregate_without_pii():
    legacy_result = {
        "items": [{"id": "plan-1", "status": "rascunho"}],
        "total": 1,
    }
    batch = _batch(
        _summary(
            v2_managed=True,
            management_state="active",
            source="sidecar_active",
            lifecycle="active",
            effective_status="ativo",
            shape="homogeneous",
        )
    )

    diagnostic = build_plan_list_additive_diagnostic(
        legacy_result,
        batch,
        academic_year=2026,
        school_id="school-secret",
        student_id="student-secret",
        professor_aee_id="prof-secret",
        status_filter=None,
        skip=0,
        limit=100,
        role="super_admin",
        contract_ms=4.0,
    )

    assert diagnostic["phase"] == "6.6B"
    assert diagnostic["mode"] == "additive_contract"
    assert diagnostic["status"] == "divergent"
    assert diagnostic["sources"]["sidecar_active"] == 1
    assert diagnostic["mutation_policies"] == {"dossier_v2_required": 1}
    assert diagnostic["performance"]["head_queries"] == 1
    assert diagnostic["performance"]["snapshot_queries"] == 1
    assert diagnostic["performance"]["contract_ms"] == 4.0
    assert "shadow_ms" not in diagnostic["performance"]

    encoded = json.dumps(diagnostic, ensure_ascii=False)
    assert "school-secret" not in encoded
    assert "student-secret" not in encoded
    assert "prof-secret" not in encoded


def _router_with_list_endpoint(events=None, response=None, legacy_error=None):
    router = APIRouter()
    payload = response if response is not None else {
        "items": [
            {
                "id": "plan-1",
                "status": "rascunho",
                "dias_atendimento": ["segunda"],
                "student_name": "Nome legado",
            }
        ],
        "total": 1,
    }

    @router.get("/aee/planos")
    async def list_planos(
        request: Request,
        school_id: str | None = None,
        student_id: str | None = None,
        academic_year: int | None = None,
        status_filter: str | None = None,
        professor_aee_id: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ):
        if events is not None:
            events.append("legacy")
        if legacy_error is not None:
            raise legacy_error
        return payload

    return router, payload


def test_wrapper_runs_legacy_first_resolves_once_and_returns_additive_contract():
    events = []
    router, payload = _router_with_list_endpoint(events=events)
    original = deepcopy(payload)
    calls = {"batch": 0}

    async def batch_resolver(db, items):
        assert db is DB_SENTINEL
        assert items is payload["items"]
        calls["batch"] += 1
        events.append("batch")
        return _batch(
            _summary(
                v2_managed=True,
                management_state="active",
                source="sidecar_active",
                lifecycle="active",
                effective_status="ativo",
                shape="homogeneous",
                active_snapshot_id="active-1",
                document_version=1,
                revision=14,
            )
        )

    async def user_getter(request):
        return {"role": "super_admin"}

    install_aee_v2_plan_list_contract(
        router,
        DB_SENTINEL,
        batch_resolver=batch_resolver,
        user_getter=user_getter,
    )
    endpoint = router.routes[0].endpoint
    result = asyncio.run(endpoint(None, "school-1", None, 2026, None, None, 0, 100))

    assert events == ["legacy", "batch"]
    assert calls["batch"] == 1
    assert payload == original
    assert result["total"] == 1
    assert result["items"][0]["status"] == "rascunho"
    assert result["items"][0]["effective_source"] == "sidecar_active"
    assert result["items"][0]["effective_summary"]["legacy_compatible_status"] == "ativo"


def test_global_contract_failure_returns_stable_503_instead_of_silent_legacy():
    router, _ = _router_with_list_endpoint()

    async def broken_batch(db, items):
        raise RuntimeError("resolver quebrado")

    install_aee_v2_plan_list_contract(
        router, DB_SENTINEL, batch_resolver=broken_batch
    )
    endpoint = router.routes[0].endpoint

    try:
        asyncio.run(endpoint(None, None, None, 2026, None, None, 0, 100))
    except HTTPException as exc:
        assert exc.status_code == 503
        assert exc.detail["code"] == "AEE_V2_PLAN_LIST_CONTRACT_UNAVAILABLE"
    else:
        raise AssertionError("Era esperado HTTP 503 controlado")


def test_legacy_http_exception_is_preserved_before_v2_layer():
    legacy_error = HTTPException(status_code=418, detail="legado")
    router, _ = _router_with_list_endpoint(legacy_error=legacy_error)

    async def batch_resolver(db, items):
        raise AssertionError("resolver não deve executar")

    install_aee_v2_plan_list_contract(
        router, DB_SENTINEL, batch_resolver=batch_resolver
    )
    endpoint = router.routes[0].endpoint

    try:
        asyncio.run(endpoint(None, None, None, 2026, None, None, 0, 100))
    except HTTPException as exc:
        assert exc.status_code == 418
        assert exc.detail == "legado"
    else:
        raise AssertionError("Era esperado erro legado original")


def test_installer_is_idempotent_and_refuses_shadow_stacking():
    router, _ = _router_with_list_endpoint()

    first = install_aee_v2_plan_list_contract(router, DB_SENTINEL)
    endpoint = router.routes[0].endpoint
    second = install_aee_v2_plan_list_contract(router, DB_SENTINEL)

    assert first is router
    assert second is router
    assert router.routes[0].endpoint is endpoint
    assert getattr(router, "_aee_v2_plan_list_contract_installed") is True

    shadow_router, _ = _router_with_list_endpoint()
    shadow_router._aee_v2_plan_list_shadow_installed = True
    try:
        install_aee_v2_plan_list_contract(shadow_router, DB_SENTINEL)
    except RuntimeError as exc:
        assert "não pode ser empilhada" in str(exc)
    else:
        raise AssertionError("6.6B deveria recusar wrapper 6.6A já instalado")


def test_fastapi_01101_include_router_keeps_additive_endpoint_callable():
    router, _ = _router_with_list_endpoint()

    async def batch_resolver(db, items):
        return _batch(_summary(), head_queries=1, snapshot_queries=0)

    install_aee_v2_plan_list_contract(
        router, DB_SENTINEL, batch_resolver=batch_resolver
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")

    route = next(
        r
        for r in app.routes
        if getattr(r, "path", None) == "/api/aee/planos"
        and "GET" in (getattr(r, "methods", set()) or set())
    )
    assert route.endpoint is router.routes[0].endpoint
    assert route.dependant.call is router.routes[0].endpoint


class FakeCursor:
    def __init__(self, docs):
        self.docs = [deepcopy(doc) for doc in docs]

    async def to_list(self, length):
        return deepcopy(self.docs if length is None else self.docs[:length])


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = [deepcopy(doc) for doc in (docs or [])]
        self.find_calls = []

    @staticmethod
    def _matches(doc, query):
        for key, expected in query.items():
            actual = doc.get(key)
            if isinstance(expected, dict) and "$in" in expected:
                if actual not in expected["$in"]:
                    return False
            elif actual != expected:
                return False
        return True

    def find(self, query, projection=None):
        self.find_calls.append((deepcopy(query), deepcopy(projection)))
        return FakeCursor([doc for doc in self.docs if self._matches(doc, query)])


class FakeDB:
    def __init__(self, *, heads=None, snapshots=None):
        self.collections = {
            AEEV2Repository.HEADS: FakeCollection(heads),
            AEEV2Repository.SNAPSHOTS: FakeCollection(snapshots),
        }

    def __getitem__(self, name):
        return self.collections[name]


def _snapshot(plan, revision=1):
    dossier = project_legacy_plan(plan).dossier
    dossier.lifecycle.status = "active"
    return make_snapshot(
        legacy_plano_id=plan["id"],
        dossier=dossier,
        document_version=1,
        revision=revision,
        operation="activate",
        actor={"id": "actor-1", "role": "super_admin"},
        changed_section="lifecycle",
    )


def _head(plan, snapshot):
    return {
        "legacy_plano_id": plan["id"],
        "student_id": plan["student_id"],
        "school_id": plan["school_id"],
        "academic_year": plan["academic_year"],
        "active_snapshot_id": snapshot["id"],
        "working_snapshot_id": None,
        "head_revision": snapshot["revision"],
    }


def test_query_budget_is_constant_for_0_1_10_and_100_items():
    empty_db = FakeDB()
    empty = asyncio.run(resolve_plan_list_effective_batch(empty_db, []))
    assert empty["performance"]["head_queries"] == 0
    assert empty["performance"]["snapshot_queries"] == 0

    for count in (1, 10, 100):
        plans = [_plan(i) for i in range(1, count + 1)]
        snapshots = [_snapshot(plan, revision=i) for i, plan in enumerate(plans, 1)]
        heads = [_head(plan, snapshot) for plan, snapshot in zip(plans, snapshots)]
        db = FakeDB(heads=heads, snapshots=snapshots)

        result = asyncio.run(resolve_plan_list_effective_batch(db, plans))

        assert len(result["items"]) == count
        assert result["performance"]["head_queries"] == 1
        assert result["performance"]["snapshot_queries"] == 1
        assert len(db[AEEV2Repository.HEADS].find_calls) == 1
        assert len(db[AEEV2Repository.SNAPSHOTS].find_calls) == 1
        assert all(
            item["effective_source"] == "sidecar_active"
            for item in result["items"]
        )
