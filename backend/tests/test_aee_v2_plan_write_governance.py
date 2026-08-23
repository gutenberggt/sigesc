from __future__ import annotations

import asyncio
from copy import deepcopy
import logging

import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request

from aee_v2.delete_guard import install_aee_v2_delete_guard
from aee_v2.legacy_mapper import project_legacy_plan
from aee_v2.plan_write_governance import install_aee_v2_plan_write_governance
from aee_v2.repository import AEEV2Repository
from aee_v2.versioning import make_snapshot


BASE_PLAN = {
    "id": "plan-1",
    "student_id": "student-1",
    "school_id": "school-1",
    "academic_year": 2026,
    "status": "rascunho",
    "dias_atendimento": ["segunda"],
    "professor_aee_id": "prof-1",
    "professor_aee_nome": "Professor",
    "horario_inicio": "08:00",
    "horario_fim": "09:00",
    "local_atendimento": "Sala AEE",
}


def _summary(
    *,
    v2_managed=False,
    source="legacy",
    lifecycle="draft",
    effective_status="rascunho",
    integrity_error=None,
    working_error=None,
    active_snapshot_id=None,
    working_snapshot_id=None,
    document_version=None,
    revision=None,
):
    return {
        "legacy_plano_id": "plan-1",
        "v2_managed": v2_managed,
        "management_state": "active" if active_snapshot_id else ("working_only" if working_snapshot_id else "legacy_only"),
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
        "effective_days": None if source is None else ["segunda"],
        "schedule_shape": None if source is None else ("homogeneous" if source == "sidecar_active" else "legacy_projection"),
        "status_parity": effective_status == "rascunho",
        "days_parity": source is not None,
        "integrity_error": integrity_error,
        "working_integrity_error": working_error,
    }


def _batch(summary, *, head_queries=1, snapshot_queries=1):
    return {
        "items": [summary],
        "performance": {
            "head_queries": head_queries,
            "snapshot_queries": snapshot_queries,
            "batch_ms": 1.0,
        },
    }


class PlanCollection:
    def __init__(self, plan=None):
        self.plan = deepcopy(plan)
        self.find_one_calls = []

    async def find_one(self, query, projection=None):
        self.find_one_calls.append((deepcopy(query), deepcopy(projection)))
        if self.plan and self.plan.get("id") == query.get("id"):
            if not projection:
                return deepcopy(self.plan)
            return {
                key: deepcopy(value)
                for key, value in self.plan.items()
                if projection.get(key) == 1
            }
        return None


class SimpleDB:
    def __init__(self, plan=None):
        self.collections = {"planos_aee": PlanCollection(plan)}

    def __getitem__(self, name):
        return self.collections[name]


async def _super_admin(_request):
    return {"id": "user-1", "role": "super_admin"}


async def _read_only(_request):
    return {"id": "user-2", "role": "semed3"}


def _router(events):
    router = APIRouter()

    @router.put("/aee/planos/{plano_id}")
    async def update_plano(plano_id: str, request: Request, payload: dict | None = None):
        events.append(("update", plano_id, payload))
        return {"ok": "update"}

    @router.post("/aee/planos/{plano_id}/duplicate")
    async def duplicate_plano(plano_id: str, request: Request):
        events.append(("duplicate", plano_id))
        return {"ok": "duplicate"}

    @router.delete("/aee/planos/{plano_id}")
    async def delete_plano(plano_id: str, request: Request):
        events.append(("delete", plano_id))
        return {"ok": "delete"}

    return router


def _endpoint(router, action):
    path, method = {
        "update": ("/aee/planos/{plano_id}", "PUT"),
        "duplicate": ("/aee/planos/{plano_id}/duplicate", "POST"),
        "delete": ("/aee/planos/{plano_id}", "DELETE"),
    }[action]
    return next(
        route.endpoint
        for route in router.routes
        if route.path == path and method in (route.methods or set())
    )


def _run_action(router, action):
    endpoint = _endpoint(router, action)
    if action == "update":
        return asyncio.run(endpoint(plano_id="plan-1", request=None, payload={"status": "ativo"}))
    return asyncio.run(endpoint(plano_id="plan-1", request=None))


def _install(router, db, batch_resolver, *, user_getter=_super_admin):
    return install_aee_v2_plan_write_governance(
        router,
        db,
        write_roles=("super_admin", "professor"),
        delete_roles=("super_admin", "gerente"),
        batch_resolver=batch_resolver,
        user_getter=user_getter,
    )


@pytest.mark.parametrize("action", ["update", "duplicate", "delete"])
def test_legacy_allowed_delegates_to_original_exactly_once(action):
    events = []
    db = SimpleDB(BASE_PLAN)
    calls = {"resolver": 0}

    async def resolver(_db, plans):
        calls["resolver"] += 1
        assert plans[0]["id"] == "plan-1"
        return _batch(_summary(), head_queries=1, snapshot_queries=0)

    router = _router(events)
    _install(router, db, resolver)
    result = _run_action(router, action)

    assert result == {"ok": action}
    assert [event[0] for event in events] == [action]
    assert calls["resolver"] == 1
    assert len(db["planos_aee"].find_one_calls) == 1


@pytest.mark.parametrize(
    "action,expected_code",
    [
        ("update", "AEE_V2_PLAN_LEGACY_WRITE_REQUIRES_DOSSIER_V2"),
        ("duplicate", "AEE_V2_PLAN_LEGACY_DUPLICATE_BLOCKED"),
        ("delete", "AEE_V2_PLAN_LEGACY_DELETE_BLOCKED"),
    ],
)
@pytest.mark.parametrize("management", ["working", "active"])
def test_v2_managed_blocks_legacy_mutations_without_calling_original(action, expected_code, management):
    events = []
    db = SimpleDB(BASE_PLAN)

    if management == "working":
        summary = _summary(
            v2_managed=True,
            source="legacy",
            working_snapshot_id="working-1",
        )
    else:
        summary = _summary(
            v2_managed=True,
            source="sidecar_active",
            lifecycle="active",
            effective_status="ativo",
            active_snapshot_id="active-1",
            document_version=2,
            revision=2,
        )

    async def resolver(_db, _plans):
        return _batch(summary)

    router = _router(events)
    _install(router, db, resolver)

    with pytest.raises(HTTPException) as caught:
        _run_action(router, action)

    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == expected_code
    if action == "update":
        assert caught.value.detail["next_action"] == "open_dossier_v2"
    assert events == []


@pytest.mark.parametrize("action", ["update", "duplicate", "delete"])
def test_primary_integrity_error_blocks_every_governed_mutation(action):
    events = []
    db = SimpleDB(BASE_PLAN)
    error = {"code": "AEE_V2_TEST_INTEGRITY", "message": "hash inválido"}

    async def resolver(_db, _plans):
        return _batch(
            _summary(
                v2_managed=True,
                source=None,
                lifecycle=None,
                effective_status=None,
                integrity_error=error,
                active_snapshot_id="active-bad",
            )
        )

    router = _router(events)
    _install(router, db, resolver)

    with pytest.raises(HTTPException) as caught:
        _run_action(router, action)

    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "AEE_V2_PLAN_WRITE_INTEGRITY_BLOCKED"
    assert events == []


def test_valid_active_with_broken_working_is_fail_closed_for_mutation():
    events = []
    db = SimpleDB(BASE_PLAN)

    async def resolver(_db, _plans):
        return _batch(
            _summary(
                v2_managed=True,
                source="sidecar_active",
                lifecycle="active",
                effective_status="ativo",
                active_snapshot_id="active-1",
                working_snapshot_id="working-missing",
                document_version=2,
                revision=4,
                working_error={
                    "code": "AEE_V2_PLAN_LIST_WORKING_SNAPSHOT_MISSING",
                    "message": "working ausente",
                },
            )
        )

    router = _router(events)
    _install(router, db, resolver)

    with pytest.raises(HTTPException) as caught:
        _run_action(router, "update")

    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "AEE_V2_PLAN_WRITE_INTEGRITY_BLOCKED"
    assert events == []


def test_unexpected_resolver_failure_returns_503_and_never_calls_original():
    events = []
    db = SimpleDB(BASE_PLAN)

    async def resolver(_db, _plans):
        raise RuntimeError("resolver indisponível")

    router = _router(events)
    _install(router, db, resolver)

    with pytest.raises(HTTPException) as caught:
        _run_action(router, "duplicate")

    assert caught.value.status_code == 503
    assert caught.value.detail["code"] == "AEE_V2_PLAN_WRITE_GOVERNANCE_UNAVAILABLE"
    assert events == []


def test_query_budget_violation_is_503_fail_closed():
    events = []
    db = SimpleDB(BASE_PLAN)

    async def resolver(_db, _plans):
        return _batch(_summary(), head_queries=2, snapshot_queries=1)

    router = _router(events)
    _install(router, db, resolver)

    with pytest.raises(HTTPException) as caught:
        _run_action(router, "update")

    assert caught.value.status_code == 503
    assert caught.value.detail["code"] == "AEE_V2_PLAN_WRITE_GOVERNANCE_UNAVAILABLE"
    assert events == []


def test_authz_occurs_before_plan_lookup_and_policy_resolution():
    events = []
    db = SimpleDB(BASE_PLAN)
    calls = {"resolver": 0}

    async def resolver(_db, _plans):
        calls["resolver"] += 1
        return _batch(_summary())

    router = _router(events)
    _install(router, db, resolver, user_getter=_read_only)

    with pytest.raises(HTTPException) as caught:
        _run_action(router, "update")

    assert caught.value.status_code == 403
    assert db["planos_aee"].find_one_calls == []
    assert calls["resolver"] == 0
    assert events == []


def test_delete_preserves_stricter_role_scope_before_lookup():
    events = []
    db = SimpleDB(BASE_PLAN)

    async def professor(_request):
        return {"id": "prof-1", "role": "professor"}

    async def resolver(_db, _plans):
        raise AssertionError("resolver não deve executar")

    router = _router(events)
    _install(router, db, resolver, user_getter=professor)

    with pytest.raises(HTTPException) as caught:
        _run_action(router, "delete")

    assert caught.value.status_code == 403
    assert db["planos_aee"].find_one_calls == []
    assert events == []


def test_missing_plan_returns_404_after_auth_without_resolving_policy():
    events = []
    db = SimpleDB(None)
    calls = {"resolver": 0}

    async def resolver(_db, _plans):
        calls["resolver"] += 1
        return _batch(_summary())

    router = _router(events)
    _install(router, db, resolver)

    with pytest.raises(HTTPException) as caught:
        _run_action(router, "update")

    assert caught.value.status_code == 404
    assert calls["resolver"] == 0
    assert events == []


def test_diagnostic_omits_plan_id_and_pii(caplog):
    events = []
    db = SimpleDB(BASE_PLAN)

    async def resolver(_db, _plans):
        return _batch(
            _summary(
                v2_managed=True,
                source="sidecar_active",
                lifecycle="active",
                effective_status="ativo",
                active_snapshot_id="active-1",
                document_version=2,
                revision=2,
            )
        )

    router = _router(events)
    _install(router, db, resolver)

    with caplog.at_level(logging.WARNING, logger="aee_v2.plan_write_governance"):
        with pytest.raises(HTTPException):
            _run_action(router, "update")

    text = caplog.text
    assert "AEE_V2_PLAN_WRITE_GOVERNANCE" in text
    assert '"phase": "6.6D"' in text
    assert '"decision": "blocked"' in text
    assert "plan-1" not in text
    assert "student-1" not in text
    assert "Professor" not in text


def _is_old_delete_guard_dependency(value):
    call = getattr(value, "dependency", None) or getattr(value, "call", None)
    return (
        getattr(call, "__module__", None) == "aee_v2.delete_guard"
        and getattr(call, "__name__", None) == "protect_legacy_anchor"
    )


def test_installer_supersedes_6_0a_delete_guard_and_is_idempotent():
    events = []
    db = SimpleDB(BASE_PLAN)
    router = _router(events)

    async def authorize_delete(_request):
        return None

    install_aee_v2_delete_guard(router, db, authorize_delete=authorize_delete)
    delete_route = next(
        r for r in router.routes
        if r.path == "/aee/planos/{plano_id}" and "DELETE" in (r.methods or set())
    )
    assert any(_is_old_delete_guard_dependency(dep) for dep in delete_route.dependencies)
    assert any(_is_old_delete_guard_dependency(dep) for dep in delete_route.dependant.dependencies)

    async def resolver(_db, _plans):
        return _batch(_summary(), snapshot_queries=0)

    first = _install(router, db, resolver)
    endpoints = {action: _endpoint(router, action) for action in ("update", "duplicate", "delete")}
    second = _install(router, db, resolver)

    assert first is router
    assert second is router
    assert getattr(router, "_aee_v2_plan_write_governance_installed") is True
    assert getattr(router, "_aee_v2_delete_guard_superseded_by_6_6d") is True
    assert not any(_is_old_delete_guard_dependency(dep) for dep in delete_route.dependencies)
    assert not any(_is_old_delete_guard_dependency(dep) for dep in delete_route.dependant.dependencies)
    assert {action: _endpoint(router, action) for action in endpoints} == endpoints


def test_fastapi_include_router_keeps_6_6d_wrapped_endpoints():
    events = []
    db = SimpleDB(BASE_PLAN)
    router = _router(events)

    async def resolver(_db, _plans):
        return _batch(_summary(), snapshot_queries=0)

    _install(router, db, resolver)
    app = FastAPI()
    app.include_router(router, prefix="/api")

    for action, (path, method) in {
        "update": ("/api/aee/planos/{plano_id}", "PUT"),
        "duplicate": ("/api/aee/planos/{plano_id}/duplicate", "POST"),
        "delete": ("/api/aee/planos/{plano_id}", "DELETE"),
    }.items():
        route = next(
            r for r in app.routes
            if getattr(r, "path", None) == path and method in (getattr(r, "methods", set()) or set())
        )
        assert route.endpoint is _endpoint(router, action)
        assert route.dependant.call is route.endpoint


class ResolverCursor:
    def __init__(self, docs):
        self.docs = [deepcopy(doc) for doc in docs]

    async def to_list(self, length):
        return deepcopy(self.docs if length is None else self.docs[:length])


class ResolverCollection:
    def __init__(self, docs=None):
        self.docs = [deepcopy(doc) for doc in (docs or [])]
        self.find_calls = []
        self.find_one_calls = []

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
        return ResolverCursor([doc for doc in self.docs if self._matches(doc, query)])

    async def find_one(self, query, projection=None):
        self.find_one_calls.append((deepcopy(query), deepcopy(projection)))
        match = next((doc for doc in self.docs if self._matches(doc, query)), None)
        if match is None:
            return None
        if not projection:
            return deepcopy(match)
        return {
            key: deepcopy(value)
            for key, value in match.items()
            if projection.get(key) == 1
        }


class ResolverDB:
    def __init__(self, *, plan, heads=None, snapshots=None):
        self.collections = {
            "planos_aee": ResolverCollection([plan]),
            AEEV2Repository.HEADS: ResolverCollection(heads),
            AEEV2Repository.SNAPSHOTS: ResolverCollection(snapshots),
        }

    def __getitem__(self, name):
        return self.collections[name]


def _active_snapshot(plan, revision=2):
    dossier = project_legacy_plan(plan).dossier
    dossier.lifecycle.status = "active"
    return make_snapshot(
        legacy_plano_id=plan["id"],
        dossier=dossier,
        document_version=2,
        revision=revision,
        operation="activate",
        actor={"id": "actor-1", "role": "super_admin"},
        changed_section="lifecycle",
    )


def _head(plan, active_snapshot, *, working_snapshot_id=None):
    return {
        "legacy_plano_id": plan["id"],
        "student_id": plan["student_id"],
        "school_id": plan["school_id"],
        "academic_year": plan["academic_year"],
        "active_snapshot_id": active_snapshot["id"],
        "working_snapshot_id": working_snapshot_id,
        "head_revision": active_snapshot["revision"],
    }


def test_real_resolver_active_policy_uses_one_head_and_one_snapshot_query():
    from aee_v2.plan_list_effective import resolve_plan_list_effective_batch

    events = []
    snapshot = _active_snapshot(BASE_PLAN)
    db = ResolverDB(
        plan=BASE_PLAN,
        heads=[_head(BASE_PLAN, snapshot)],
        snapshots=[snapshot],
    )
    router = _router(events)
    install_aee_v2_plan_write_governance(
        router,
        db,
        write_roles=("super_admin",),
        delete_roles=("super_admin",),
        batch_resolver=resolve_plan_list_effective_batch,
        user_getter=_super_admin,
    )

    with pytest.raises(HTTPException) as caught:
        _run_action(router, "update")

    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "AEE_V2_PLAN_LEGACY_WRITE_REQUIRES_DOSSIER_V2"
    assert len(db[AEEV2Repository.HEADS].find_calls) == 1
    assert len(db[AEEV2Repository.SNAPSHOTS].find_calls) == 1
    assert events == []


def test_real_resolver_active_plus_missing_working_blocks_integrity_with_same_query_budget():
    from aee_v2.plan_list_effective import resolve_plan_list_effective_batch

    events = []
    snapshot = _active_snapshot(BASE_PLAN, revision=3)
    db = ResolverDB(
        plan=BASE_PLAN,
        heads=[_head(BASE_PLAN, snapshot, working_snapshot_id="working-missing")],
        snapshots=[snapshot],
    )
    router = _router(events)
    install_aee_v2_plan_write_governance(
        router,
        db,
        write_roles=("super_admin",),
        delete_roles=("super_admin",),
        batch_resolver=resolve_plan_list_effective_batch,
        user_getter=_super_admin,
    )

    with pytest.raises(HTTPException) as caught:
        _run_action(router, "delete")

    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "AEE_V2_PLAN_WRITE_INTEGRITY_BLOCKED"
    assert len(db[AEEV2Repository.HEADS].find_calls) == 1
    assert len(db[AEEV2Repository.SNAPSHOTS].find_calls) == 1
    assert events == []
