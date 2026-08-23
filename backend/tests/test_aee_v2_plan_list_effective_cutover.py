from __future__ import annotations

import asyncio
from copy import deepcopy
import json

from fastapi import APIRouter, FastAPI, HTTPException, Request

from aee_v2.plan_list_effective_cutover import (
    PlanListEffectiveFilterIntegrityBlocked,
    build_effective_candidate_filter,
    build_effective_list_diagnostic,
    install_aee_v2_plan_list_effective_cutover,
    select_effective_page,
)


ALLOWED_ROLES = (
    "admin",
    "admin_teste",
    "super_admin",
    "gerente",
    "coordenador",
    "apoio_pedagogico",
    "auxiliar_secretaria",
    "professor",
    "secretario",
    "diretor",
    "semed",
    "semed1",
    "semed2",
    "semed3",
)


def _plan(index: int, *, status="rascunho", professor="prof-1", created_by="creator-1"):
    return {
        "id": f"plan-{index}",
        "student_id": f"student-{index}",
        "school_id": "school-1",
        "academic_year": 2026,
        "professor_aee_id": professor,
        "created_by": created_by,
        "status": status,
        "dias_atendimento": ["segunda"],
        "student_name": f"Student {index}",
        "publico_alvo": "deficiencia_intelectual",
    }


def _summary(
    plan_id: str,
    *,
    legacy_status="rascunho",
    effective_status="rascunho",
    source="legacy",
    v2_managed=False,
    management_state="legacy_only",
    integrity_error=None,
    working_error=None,
):
    lifecycle = {
        "rascunho": "draft",
        "ativo": "active",
        "revisao": "review",
        "encerrado": "closed",
        "cancelado": "cancelled",
    }.get(effective_status)
    return {
        "legacy_plano_id": plan_id,
        "v2_managed": v2_managed,
        "management_state": management_state,
        "effective_source": source,
        "effective_version": {
            "active_snapshot_id": "active-1" if source == "sidecar_active" else None,
            "document_version": 2 if source == "sidecar_active" else None,
            "revision": 2 if source == "sidecar_active" else None,
            "working_snapshot_id": "working-1" if v2_managed else None,
        },
        "legacy_status": legacy_status,
        "effective_lifecycle_status": lifecycle,
        "effective_legacy_status": effective_status,
        "legacy_days": ["segunda"],
        "effective_days": ["segunda"],
        "schedule_shape": "homogeneous" if source == "sidecar_active" else "legacy_projection",
        "status_parity": legacy_status == effective_status,
        "days_parity": True,
        "integrity_error": integrity_error,
        "working_integrity_error": working_error,
    }


def _batch(summaries, *, head_queries=1, snapshot_queries=1):
    return {
        "items": list(summaries),
        "performance": {
            "head_queries": head_queries,
            "snapshot_queries": snapshot_queries,
            "batch_ms": 3.25,
        },
    }


def _matches(doc, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(doc, clause) for clause in expected):
                return False
            continue
        actual = doc.get(key)
        if isinstance(expected, dict) and "$in" in expected:
            if actual not in expected["$in"]:
                return False
        elif actual != expected:
            return False
    return True


def _project(doc, projection):
    if not projection:
        return deepcopy(doc)
    included = [key for key, enabled in projection.items() if enabled and key != "_id"]
    if included:
        return {key: deepcopy(doc.get(key)) for key in included if key in doc}
    result = deepcopy(doc)
    if projection.get("_id") == 0:
        result.pop("_id", None)
    return result


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, length=None):
        if length is None:
            return deepcopy(self.rows)
        return deepcopy(self.rows[:length])


class FakeCollection:
    def __init__(self, docs):
        self.docs = [deepcopy(doc) for doc in docs]
        self.find_calls = []
        self.find_one_calls = []
        self.write_calls = []

    def find(self, query, projection=None):
        self.find_calls.append((deepcopy(query), deepcopy(projection)))
        rows = [_project(doc, projection) for doc in self.docs if _matches(doc, query)]
        return FakeCursor(rows)

    async def find_one(self, query, projection=None):
        self.find_one_calls.append((deepcopy(query), deepcopy(projection)))
        for doc in self.docs:
            if _matches(doc, query):
                return _project(doc, projection)
        return None

    async def insert_one(self, *args, **kwargs):
        self.write_calls.append("insert_one")
        raise AssertionError("6.6C não pode escrever")

    async def update_one(self, *args, **kwargs):
        self.write_calls.append("update_one")
        raise AssertionError("6.6C não pode escrever")

    async def update_many(self, *args, **kwargs):
        self.write_calls.append("update_many")
        raise AssertionError("6.6C não pode escrever")

    async def delete_one(self, *args, **kwargs):
        self.write_calls.append("delete_one")
        raise AssertionError("6.6C não pode escrever")

    async def delete_many(self, *args, **kwargs):
        self.write_calls.append("delete_many")
        raise AssertionError("6.6C não pode escrever")

    async def replace_one(self, *args, **kwargs):
        self.write_calls.append("replace_one")
        raise AssertionError("6.6C não pode escrever")

    async def bulk_write(self, *args, **kwargs):
        self.write_calls.append("bulk_write")
        raise AssertionError("6.6C não pode escrever")

    async def create_index(self, *args, **kwargs):
        self.write_calls.append("create_index")
        raise AssertionError("6.6C não pode criar índice")


class FakeDB:
    def __init__(self, plans):
        self.planos_aee = FakeCollection(plans)
        self.students = FakeCollection(
            [
                {"id": plan["student_id"], "full_name": f"Nome {plan['student_id']}"}
                for plan in plans
            ]
        )


def _router(events=None, legacy_payload=None):
    router = APIRouter()
    payload = legacy_payload or {"items": [_plan(1)], "total": 1}

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
            events.append(("legacy", status_filter, skip, limit))
        return deepcopy(payload)

    return router


def _endpoint(router):
    return next(
        route.endpoint
        for route in router.routes
        if getattr(route, "path", None) == "/aee/planos"
    )


def test_candidate_filter_reproduces_legacy_professor_scope_exactly():
    result = build_effective_candidate_filter(
        school_id="school-1",
        student_id="student-1",
        academic_year=2026,
        professor_aee_id="explicit-prof",
        current_user={"role": "professor", "id": "user-prof"},
    )

    assert result == {
        "school_id": "school-1",
        "student_id": "student-1",
        "academic_year": 2026,
        "professor_aee_id": "explicit-prof",
        "$or": [
            {"professor_aee_id": "user-prof"},
            {"created_by": "user-prof"},
        ],
    }
    assert "status" not in result


def test_effective_filter_sentinel_changes_membership_before_pagination():
    candidates = [_plan(1), _plan(2), _plan(3)]
    batch = _batch(
        [
            _summary(
                "plan-1",
                legacy_status="rascunho",
                effective_status="ativo",
                source="sidecar_active",
                v2_managed=True,
                management_state="active",
            ),
            _summary("plan-2"),
            _summary("plan-3"),
        ]
    )

    ativo = select_effective_page(
        candidates, batch, status_filter="ativo", skip=0, limit=100
    )
    rascunho = select_effective_page(
        candidates, batch, status_filter="rascunho", skip=1, limit=1
    )

    assert ativo["effective_ids"] == ["plan-1"]
    assert ativo["effective_total"] == 1
    assert ativo["legacy_matches_preview"] == 0
    assert rascunho["effective_ids"] == ["plan-2", "plan-3"]
    assert rascunho["effective_total"] == 2
    assert rascunho["page_ids"] == ["plan-3"]
    assert rascunho["legacy_matches_preview"] == 3


def test_effective_filter_is_blocked_when_primary_authority_is_indeterminate():
    candidates = [_plan(1), _plan(2)]
    error = {"code": "AEE_V2_PLAN_LIST_ACTIVE_SNAPSHOT_HASH_INVALID", "message": "hash"}
    batch = _batch(
        [
            _summary(
                "plan-1",
                effective_status=None,
                source=None,
                v2_managed=True,
                management_state="integrity_error",
                integrity_error=error,
            ),
            _summary("plan-2"),
        ]
    )

    selection = select_effective_page(
        candidates, batch, status_filter="rascunho", skip=0, limit=100
    )
    assert selection["blocked"] is True
    assert selection["effective_total"] is None
    assert selection["integrity_errors"] == 1


def test_working_error_with_valid_active_does_not_make_read_status_indeterminate():
    candidates = [_plan(1)]
    batch = _batch(
        [
            _summary(
                "plan-1",
                effective_status="ativo",
                source="sidecar_active",
                v2_managed=True,
                management_state="active",
                working_error={"code": "AEE_V2_WORKING_BROKEN", "message": "working"},
            )
        ]
    )
    selection = select_effective_page(
        candidates, batch, status_filter="ativo", skip=0, limit=100
    )
    assert selection["blocked"] is False
    assert selection["effective_ids"] == ["plan-1"]


def test_filtered_wrapper_bypasses_legacy_status_filter_and_materializes_in_order():
    events = []
    plans = [_plan(1), _plan(2), _plan(3)]
    db = FakeDB(plans)
    router = _router(events=events)
    calls = {"batch": 0}

    async def batch_resolver(db_arg, candidates):
        assert db_arg is db
        calls["batch"] += 1
        return _batch(
            [
                _summary(
                    candidate["id"],
                    legacy_status=candidate.get("status"),
                    effective_status="ativo" if candidate["id"] == "plan-1" else "rascunho",
                    source="sidecar_active" if candidate["id"] == "plan-1" else "legacy",
                    v2_managed=candidate["id"] == "plan-1",
                    management_state="active" if candidate["id"] == "plan-1" else "legacy_only",
                )
                for candidate in candidates
            ]
        )

    async def user_getter(request):
        return {"role": "super_admin", "id": "admin-1"}

    install_aee_v2_plan_list_effective_cutover(
        router,
        db,
        allowed_roles=ALLOWED_ROLES,
        batch_resolver=batch_resolver,
        user_getter=user_getter,
    )
    endpoint = _endpoint(router)
    result = asyncio.run(
        endpoint(
            request=object(),
            school_id="school-1",
            academic_year=2026,
            status_filter="rascunho",
            skip=1,
            limit=1,
        )
    )

    assert events == []  # o endpoint legado não pode filtrar antes da Fonte Efetiva
    assert calls["batch"] == 1
    assert result["total"] == 2
    assert [item["id"] for item in result["items"]] == ["plan-3"]
    item = result["items"][0]
    assert item["student_name"] == "Nome student-3"
    assert item["effective_summary"]["legacy_compatible_status"] == "rascunho"
    assert db.planos_aee.write_calls == []
    assert db.students.write_calls == []


def test_filtered_wrapper_includes_real_sentinel_in_ativo_even_if_legacy_is_rascunho():
    plans = [_plan(1), _plan(2)]
    db = FakeDB(plans)
    router = _router()

    async def batch_resolver(db_arg, candidates):
        return _batch(
            [
                _summary(
                    candidate["id"],
                    effective_status="ativo" if candidate["id"] == "plan-1" else "rascunho",
                    source="sidecar_active" if candidate["id"] == "plan-1" else "legacy",
                    v2_managed=candidate["id"] == "plan-1",
                    management_state="active" if candidate["id"] == "plan-1" else "legacy_only",
                )
                for candidate in candidates
            ]
        )

    async def user_getter(request):
        return {"role": "super_admin", "id": "admin-1"}

    install_aee_v2_plan_list_effective_cutover(
        router,
        db,
        allowed_roles=ALLOWED_ROLES,
        batch_resolver=batch_resolver,
        user_getter=user_getter,
    )
    result = asyncio.run(
        _endpoint(router)(
            request=object(),
            school_id="school-1",
            academic_year=2026,
            status_filter="ativo",
            skip=0,
            limit=100,
        )
    )
    assert result["total"] == 1
    assert [item["id"] for item in result["items"]] == ["plan-1"]
    assert result["items"][0]["status"] == "rascunho"
    assert result["items"][0]["effective_summary"]["legacy_compatible_status"] == "ativo"


def test_filtered_wrapper_returns_409_for_primary_integrity_error():
    db = FakeDB([_plan(1)])
    router = _router()

    async def batch_resolver(db_arg, candidates):
        return _batch(
            [
                _summary(
                    "plan-1",
                    effective_status=None,
                    source=None,
                    v2_managed=True,
                    management_state="integrity_error",
                    integrity_error={"code": "AEE_V2_BAD_ACTIVE", "message": "bad"},
                )
            ]
        )

    async def user_getter(request):
        return {"role": "super_admin", "id": "admin-1"}

    install_aee_v2_plan_list_effective_cutover(
        router,
        db,
        allowed_roles=ALLOWED_ROLES,
        batch_resolver=batch_resolver,
        user_getter=user_getter,
    )
    try:
        asyncio.run(
            _endpoint(router)(
                request=object(),
                school_id="school-1",
                academic_year=2026,
                status_filter="ativo",
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 409
        assert exc.detail["code"] == "AEE_V2_PLAN_LIST_EFFECTIVE_FILTER_INTEGRITY_BLOCKED"
    else:
        raise AssertionError("Filtro com Fonte Efetiva indeterminada deveria falhar fechado")


def test_filtered_wrapper_preserves_403_for_role_without_aee_access():
    db = FakeDB([_plan(1)])
    router = _router()

    async def user_getter(request):
        return {"role": "role_sem_aee", "id": "x"}

    install_aee_v2_plan_list_effective_cutover(
        router,
        db,
        allowed_roles=ALLOWED_ROLES,
        batch_resolver=lambda *_: None,
        user_getter=user_getter,
    )
    try:
        asyncio.run(
            _endpoint(router)(request=object(), status_filter="ativo")
        )
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Role sem AEE deveria receber 403")


def test_professor_filtered_scope_keeps_professor_or_creator_rule():
    plans = [
        _plan(1, professor="prof-user", created_by="other"),
        _plan(2, professor="other", created_by="prof-user"),
        _plan(3, professor="other", created_by="other"),
    ]
    db = FakeDB(plans)
    router = _router()
    seen_ids = []

    async def batch_resolver(db_arg, candidates):
        seen_ids.extend(candidate["id"] for candidate in candidates)
        return _batch([_summary(candidate["id"]) for candidate in candidates])

    async def user_getter(request):
        return {"role": "professor", "id": "prof-user"}

    install_aee_v2_plan_list_effective_cutover(
        router,
        db,
        allowed_roles=ALLOWED_ROLES,
        batch_resolver=batch_resolver,
        user_getter=user_getter,
    )
    result = asyncio.run(
        _endpoint(router)(
            request=object(),
            school_id="school-1",
            academic_year=2026,
            status_filter="rascunho",
        )
    )
    assert seen_ids == ["plan-1", "plan-2"]
    assert result["total"] == 2


def test_no_status_filter_keeps_legacy_endpoint_as_scope_and_pagination_authority():
    events = []
    legacy = {
        "items": [_plan(2), _plan(1)],
        "total": 23,
        "marker": "legacy-envelope",
    }
    db = FakeDB([_plan(1), _plan(2)])
    router = _router(events=events, legacy_payload=legacy)
    calls = {"batch": 0}

    async def batch_resolver(db_arg, items):
        calls["batch"] += 1
        assert [item["id"] for item in items] == ["plan-2", "plan-1"]
        return _batch([_summary("plan-2"), _summary("plan-1")])

    async def user_getter(request):
        return {"role": "super_admin", "id": "admin-1"}

    install_aee_v2_plan_list_effective_cutover(
        router,
        db,
        allowed_roles=ALLOWED_ROLES,
        batch_resolver=batch_resolver,
        user_getter=user_getter,
    )
    result = asyncio.run(
        _endpoint(router)(
            request=object(),
            school_id="school-1",
            academic_year=2026,
            skip=5,
            limit=10,
        )
    )
    assert events == [("legacy", None, 5, 10)]
    assert calls["batch"] == 1
    assert result["total"] == 23
    assert result["marker"] == "legacy-envelope"
    assert [item["id"] for item in result["items"]] == ["plan-2", "plan-1"]


def test_query_budget_adapter_resolves_once_for_1_10_100_1000_candidates():
    async def run_case(size):
        plans = [_plan(index) for index in range(1, size + 1)]
        db = FakeDB(plans)
        router = _router()
        calls = {"batch": 0}

        async def batch_resolver(db_arg, candidates):
            calls["batch"] += 1
            assert len(candidates) == size
            return _batch(
                [_summary(candidate["id"]) for candidate in candidates],
                head_queries=1,
                snapshot_queries=1,
            )

        async def user_getter(request):
            return {"role": "super_admin", "id": "admin-1"}

        install_aee_v2_plan_list_effective_cutover(
            router,
            db,
            allowed_roles=ALLOWED_ROLES,
            batch_resolver=batch_resolver,
            user_getter=user_getter,
        )
        result = await _endpoint(router)(
            request=object(),
            school_id="school-1",
            academic_year=2026,
            status_filter="rascunho",
            skip=0,
            limit=10,
        )
        assert calls["batch"] == 1
        assert result["total"] == size
        assert len(result["items"]) == min(size, 10)
        assert db.planos_aee.write_calls == []

    for size in (1, 10, 100, 1000):
        asyncio.run(run_case(size))


def test_effective_diagnostic_has_required_metrics_and_no_pii_values():
    summaries = [
        _summary(
            "secret-plan-id",
            effective_status="ativo",
            source="sidecar_active",
            v2_managed=True,
            management_state="active",
        )
    ]
    diagnostic = build_effective_list_diagnostic(
        summaries=summaries,
        academic_year=2026,
        school_id="secret-school-id",
        student_id="secret-student-id",
        professor_aee_id="secret-professor-id",
        status_filter="ativo",
        role="super_admin",
        skip=0,
        limit=100,
        items_returned=1,
        effective_total=1,
        candidate_total=1,
        legacy_matches_preview=0,
        candidate_query_ms=1.2,
        materialize_ms=2.3,
        total_ms=5.6,
        batch_result=_batch(summaries),
    )

    assert diagnostic["phase"] == "6.6C"
    assert diagnostic["mode"] == "effective_read_cutover"
    assert diagnostic["filter"] == {
        "requested_status": "ativo",
        "effective_matches": 1,
        "legacy_matches_preview": 0,
        "total_delta": 1,
    }
    assert diagnostic["performance"]["head_queries"] == 1
    assert diagnostic["performance"]["snapshot_queries"] == 1
    encoded = json.dumps(diagnostic, ensure_ascii=False)
    for secret in (
        "secret-plan-id",
        "secret-school-id",
        "secret-student-id",
        "secret-professor-id",
    ):
        assert secret not in encoded


def test_installer_is_idempotent_rejects_stacking_and_fastapi_110_clone_path():
    db = FakeDB([_plan(1)])
    router = _router()

    async def batch_resolver(db_arg, items):
        return _batch([_summary(item["id"]) for item in items])

    async def user_getter(request):
        return {"role": "super_admin"}

    first = install_aee_v2_plan_list_effective_cutover(
        router,
        db,
        allowed_roles=ALLOWED_ROLES,
        batch_resolver=batch_resolver,
        user_getter=user_getter,
    )
    endpoint_before = _endpoint(router)
    second = install_aee_v2_plan_list_effective_cutover(
        router,
        db,
        allowed_roles=ALLOWED_ROLES,
        batch_resolver=batch_resolver,
        user_getter=user_getter,
    )
    assert first is second is router
    assert _endpoint(router) is endpoint_before

    app = FastAPI()
    app.include_router(router, prefix="/api")
    cloned = next(route for route in app.routes if getattr(route, "path", None) == "/api/aee/planos")
    assert cloned.endpoint is endpoint_before
    assert cloned.dependant.call is endpoint_before

    stacked = _router()
    setattr(stacked, "_aee_v2_plan_list_contract_installed", True)
    try:
        install_aee_v2_plan_list_effective_cutover(
            stacked,
            db,
            allowed_roles=ALLOWED_ROLES,
        )
    except RuntimeError as exc:
        assert "6.6B" in str(exc)
    else:
        raise AssertionError("6.6C não pode ser empilhada sobre 6.6B")
