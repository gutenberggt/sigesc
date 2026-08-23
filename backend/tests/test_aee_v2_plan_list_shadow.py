from __future__ import annotations

import asyncio
from copy import deepcopy
import json

from fastapi import APIRouter, FastAPI, Request

from aee_v2.effective_source import resolve_effective_dossier
from aee_v2.legacy_mapper import project_legacy_plan
from aee_v2.plan_list_effective import (
    V2_TO_LEGACY_STATUS,
    resolve_plan_list_effective_batch,
)
from aee_v2.plan_list_shadow import (
    build_plan_list_shadow_diagnostic,
    install_aee_v2_plan_list_shadow,
)
from aee_v2.plano_pdf_effective import _V2_TO_LEGACY_STATUS as PDF_STATUS_MAP
from aee_v2.repository import AEEV2Repository
from aee_v2.versioning import make_snapshot
from scripts.audit_aee_v2_plan_list_6_6a import build_population_report


class FakeCursor:
    def __init__(self, docs):
        self.docs = [deepcopy(doc) for doc in docs]

    async def to_list(self, length):
        if length is None:
            return deepcopy(self.docs)
        return deepcopy(self.docs[:length])


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = [deepcopy(doc) for doc in (docs or [])]
        self.find_calls = []
        self.find_one_calls = []

    @staticmethod
    def _matches(doc, query):
        for key, expected in query.items():
            if key == "$or":
                if not any(FakeCollection._matches(doc, option) for option in expected):
                    return False
                continue
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

    async def find_one(self, query, projection=None):
        self.find_one_calls.append((deepcopy(query), deepcopy(projection)))
        for doc in self.docs:
            if self._matches(doc, query):
                result = deepcopy(doc)
                result.pop("_id", None)
                return result
        return None


class FakeDB:
    def __init__(self, *, plans=None, heads=None, snapshots=None):
        self.planos_aee = FakeCollection(plans)
        self.collections = {
            AEEV2Repository.HEADS: FakeCollection(heads),
            AEEV2Repository.SNAPSHOTS: FakeCollection(snapshots),
        }

    def __getitem__(self, name):
        return self.collections[name]


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
    plan.update(
        {
            "id": f"plan-{index}",
            "student_id": f"student-{index}",
        }
    )
    plan.update(updates)
    return plan


def _snapshot(plan, *, lifecycle_status="active", revision=14):
    dossier = project_legacy_plan(plan).dossier
    dossier.lifecycle.status = lifecycle_status
    return make_snapshot(
        legacy_plano_id=plan["id"],
        dossier=dossier,
        document_version=1,
        revision=revision,
        operation="activate" if lifecycle_status == "active" else "bootstrap",
        actor={"id": "actor-1", "role": "super_admin"},
        changed_section="lifecycle",
    )


def _head(plan, *, active_snapshot_id=None, working_snapshot_id=None):
    return {
        "id": f"head-{plan['id']}",
        "legacy_plano_id": plan["id"],
        "student_id": plan["student_id"],
        "school_id": plan["school_id"],
        "academic_year": plan["academic_year"],
        "active_snapshot_id": active_snapshot_id,
        "working_snapshot_id": working_snapshot_id,
        "head_revision": 14,
    }


def _run_batch(db, plans):
    return asyncio.run(resolve_plan_list_effective_batch(db, plans))


def test_empty_batch_has_zero_v2_queries():
    db = FakeDB()
    result = _run_batch(db, [])

    assert result["items"] == []
    assert result["performance"]["head_queries"] == 0
    assert result["performance"]["snapshot_queries"] == 0
    assert db[AEEV2Repository.HEADS].find_calls == []
    assert db[AEEV2Repository.SNAPSHOTS].find_calls == []


def test_legacy_batch_uses_one_head_query_and_zero_snapshot_queries_for_100_plans():
    plans = [_plan(i) for i in range(1, 101)]
    db = FakeDB(plans=plans)

    result = _run_batch(db, plans)

    assert len(result["items"]) == 100
    assert all(item["effective_source"] == "legacy" for item in result["items"])
    assert result["performance"]["head_queries"] == 1
    assert result["performance"]["snapshot_queries"] == 0
    assert len(db[AEEV2Repository.HEADS].find_calls) == 1
    assert db[AEEV2Repository.SNAPSHOTS].find_calls == []


def test_duplicate_ids_are_deduplicated_in_head_query():
    plan = _plan(1)
    db = FakeDB(plans=[plan])

    _run_batch(db, [plan, deepcopy(plan), deepcopy(plan)])

    query = db[AEEV2Repository.HEADS].find_calls[0][0]
    assert query == {"legacy_plano_id": {"$in": ["plan-1"]}}


def test_working_only_keeps_legacy_effective_and_validates_working_in_same_batch():
    plan = _plan(1)
    working = _snapshot(plan, lifecycle_status="draft", revision=3)
    head = _head(plan, working_snapshot_id=working["id"])
    db = FakeDB(plans=[plan], heads=[head], snapshots=[working])

    result = _run_batch(db, [plan])
    item = result["items"][0]

    assert item["v2_managed"] is True
    assert item["management_state"] == "working_only"
    assert item["effective_source"] == "legacy"
    assert item["working_integrity_error"] is None
    assert result["performance"]["head_queries"] == 1
    assert result["performance"]["snapshot_queries"] == 1


def test_active_snapshot_projects_rascunho_to_ativo_without_mutating_legacy():
    plan = _plan(1, status="rascunho")
    active = _snapshot(plan, lifecycle_status="active")
    head = _head(plan, active_snapshot_id=active["id"])
    db = FakeDB(plans=[plan], heads=[head], snapshots=[active])
    original = deepcopy(plan)

    result = _run_batch(db, [plan])
    item = result["items"][0]

    assert plan == original
    assert item["management_state"] == "active"
    assert item["effective_source"] == "sidecar_active"
    assert item["effective_lifecycle_status"] == "active"
    assert item["effective_legacy_status"] == "ativo"
    assert item["status_parity"] is False
    assert item["days_parity"] is True
    assert item["integrity_error"] is None
    assert result["performance"]["head_queries"] == 1
    assert result["performance"]["snapshot_queries"] == 1


def test_active_missing_is_integrity_error_and_never_fake_legacy():
    plan = _plan(1)
    head = _head(plan, active_snapshot_id="missing-active")
    db = FakeDB(plans=[plan], heads=[head], snapshots=[])

    item = _run_batch(db, [plan])["items"][0]

    assert item["management_state"] == "integrity_error"
    assert item["effective_source"] is None
    assert item["integrity_error"]["code"] == "AEE_V2_PLAN_LIST_ACTIVE_SNAPSHOT_MISSING"
    assert item["status_parity"] is None


def test_corrupted_active_snapshot_is_detected():
    plan = _plan(1)
    active = _snapshot(plan)
    corrupted = deepcopy(active)
    corrupted["dossier"]["study_case"]["demanda_inicial_contexto"] = "hash quebrado"
    head = _head(plan, active_snapshot_id=active["id"])
    db = FakeDB(plans=[plan], heads=[head], snapshots=[corrupted])

    item = _run_batch(db, [plan])["items"][0]

    assert item["effective_source"] is None
    assert item["integrity_error"]["code"] == "AEE_V2_PLAN_LIST_ACTIVE_SNAPSHOT_HASH_INVALID"


def test_active_snapshot_from_other_plan_is_identity_error():
    plan = _plan(1)
    other = _plan(2)
    active = _snapshot(other)
    head = _head(plan, active_snapshot_id=active["id"])
    db = FakeDB(plans=[plan], heads=[head], snapshots=[active])

    item = _run_batch(db, [plan])["items"][0]

    assert item["effective_source"] is None
    assert item["integrity_error"]["code"] == "AEE_V2_PLAN_LIST_ACTIVE_PLAN_ID_MISMATCH"


def test_valid_active_remains_effective_even_when_working_pointer_is_broken():
    plan = _plan(1)
    active = _snapshot(plan)
    head = _head(
        plan,
        active_snapshot_id=active["id"],
        working_snapshot_id="missing-working",
    )
    db = FakeDB(plans=[plan], heads=[head], snapshots=[active])

    item = _run_batch(db, [plan])["items"][0]

    assert item["effective_source"] == "sidecar_active"
    assert item["management_state"] == "active"
    assert item["integrity_error"] is None
    assert item["working_integrity_error"]["code"] == "AEE_V2_PLAN_LIST_WORKING_SNAPSHOT_MISSING"


def test_batch_agrees_with_central_resolver_for_supported_active_case():
    plan = _plan(1)
    active = _snapshot(plan)
    head = _head(plan, active_snapshot_id=active["id"])
    db = FakeDB(plans=[plan], heads=[head], snapshots=[active])

    batch = _run_batch(db, [plan])["items"][0]
    central = asyncio.run(resolve_effective_dossier(db, plan["id"]))

    assert batch["effective_source"] == central.source
    assert batch["effective_version"]["active_snapshot_id"] == central.active_snapshot_id
    assert batch["effective_version"]["document_version"] == central.document_version
    assert batch["effective_version"]["revision"] == central.revision
    assert batch["effective_lifecycle_status"] == central.dossier.lifecycle.status


def test_6_6a_status_mapping_is_contract_equal_to_6_5b_mapping():
    assert V2_TO_LEGACY_STATUS == PDF_STATUS_MAP


def _active_summary(plan_id="plan-1", *, legacy="rascunho", effective="ativo"):
    return {
        "legacy_plano_id": plan_id,
        "v2_managed": True,
        "management_state": "active",
        "effective_source": "sidecar_active",
        "effective_version": {
            "active_snapshot_id": "snap-1",
            "document_version": 1,
            "revision": 14,
            "working_snapshot_id": None,
        },
        "legacy_status": legacy,
        "effective_lifecycle_status": "active",
        "effective_legacy_status": effective,
        "legacy_days": ["segunda"],
        "effective_days": ["segunda"],
        "schedule_shape": "homogeneous",
        "status_parity": legacy == effective,
        "days_parity": True,
        "integrity_error": None,
        "working_integrity_error": None,
    }


def test_shadow_diagnostic_detects_status_transition_and_returned_filter_mismatch():
    legacy_result = {"items": [{"id": "plan-1", "status": "rascunho"}], "total": 1}
    batch = {
        "items": [_active_summary()],
        "performance": {"head_queries": 1, "snapshot_queries": 1, "batch_ms": 2.5},
    }

    diagnostic = build_plan_list_shadow_diagnostic(
        legacy_result,
        batch,
        academic_year=2026,
        school_id="school-secret",
        student_id=None,
        professor_aee_id=None,
        status_filter="rascunho",
        skip=0,
        limit=100,
        role="coordenador",
        shadow_ms=3.0,
    )

    assert diagnostic["status"] == "divergent"
    assert diagnostic["sources"]["sidecar_active"] == 1
    assert diagnostic["status_compare"]["transitions"] == {"rascunho->ativo": 1}
    assert diagnostic["filter_shadow"]["returned_effective_mismatch"] == 1
    assert diagnostic["filter_shadow"]["population_audit_required"] is True
    assert diagnostic["performance"]["head_queries"] == 1
    assert diagnostic["performance"]["snapshot_queries"] == 1

    encoded = json.dumps(diagnostic, ensure_ascii=False)
    assert "school-secret" not in encoded
    assert "student_id" not in encoded
    assert "professor_aee_id" not in encoded


def _router_with_list_endpoint(events=None, response=None):
    router = APIRouter()
    payload = response if response is not None else {
        "items": [{"id": "plan-1", "status": "rascunho", "student_name": "Nome legado"}],
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
        return payload

    return router, payload


def test_wrapper_runs_legacy_first_and_returns_exact_same_object_without_effective_fields():
    events = []
    router, response = _router_with_list_endpoint(events=events)

    async def batch_resolver(db, items):
        assert db is DB_SENTINEL
        assert items is response["items"]
        events.append("shadow")
        return {
            "items": [_active_summary()],
            "performance": {"head_queries": 1, "snapshot_queries": 1, "batch_ms": 1.0},
        }

    install_aee_v2_plan_list_shadow(router, DB_SENTINEL, batch_resolver=batch_resolver)
    endpoint = router.routes[0].endpoint
    result = asyncio.run(endpoint(None, "school-1", None, 2026, None, None, 0, 100))

    assert result is response
    assert result["items"][0] == {
        "id": "plan-1",
        "status": "rascunho",
        "student_name": "Nome legado",
    }
    assert not any(key.startswith("effective_") for key in result["items"][0])
    assert events == ["legacy", "shadow"]


def test_shadow_failure_never_blocks_legacy_response():
    router, response = _router_with_list_endpoint()

    async def broken_batch(db, items):
        raise RuntimeError("shadow indisponível")

    install_aee_v2_plan_list_shadow(router, DB_SENTINEL, batch_resolver=broken_batch)
    result = asyncio.run(router.routes[0].endpoint(None))

    assert result is response
    assert result["total"] == 1


def test_install_is_idempotent():
    router, _ = _router_with_list_endpoint()

    first = install_aee_v2_plan_list_shadow(router, DB_SENTINEL)
    endpoint = router.routes[0].endpoint
    second = install_aee_v2_plan_list_shadow(router, DB_SENTINEL)

    assert first is router
    assert second is router
    assert router.routes[0].endpoint is endpoint


def test_fastapi_include_router_keeps_plan_list_shadow_endpoint():
    router, _ = _router_with_list_endpoint()
    install_aee_v2_plan_list_shadow(router, DB_SENTINEL)

    app = FastAPI()
    app.include_router(router, prefix="/api")

    matches = [
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/aee/planos"
        and "GET" in (getattr(route, "methods", set()) or set())
    ]
    assert len(matches) == 1
    endpoint = matches[0].endpoint
    assert endpoint.__code__.co_filename.endswith("/aee_v2/plan_list_shadow.py")
    assert hasattr(endpoint, "__wrapped__")
    assert endpoint.__wrapped__.__code__.co_filename.endswith(
        "/tests/test_aee_v2_plan_list_shadow.py"
    )


def test_population_auditor_detects_false_positive_and_false_negative():
    plans = [
        _plan(1, status="rascunho"),
        _plan(2, status="ativo"),
    ]
    batch = {
        "items": [
            _active_summary("plan-1", legacy="rascunho", effective="ativo"),
            _active_summary("plan-2", legacy="ativo", effective="rascunho"),
        ],
        "performance": {"head_queries": 1, "snapshot_queries": 1, "batch_ms": 1.0},
    }

    report = build_population_report(plans, batch, page_size=1)

    assert report["filter_compare"]["rascunho"]["false_positive_count"] == 1
    assert report["filter_compare"]["rascunho"]["false_negative_count"] == 1
    assert report["filter_compare"]["ativo"]["false_positive_count"] == 1
    assert report["filter_compare"]["ativo"]["false_negative_count"] == 1
    assert report["filter_compare"]["ativo"]["pagination"]["page_size"] == 1
    assert report["performance"]["head_queries"] == 1
    assert report["performance"]["snapshot_queries"] == 1


DB_SENTINEL = object()
