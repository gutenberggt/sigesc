import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import auth_middleware as auth_module
from audit_service import audit_service
from auth_middleware import AuthMiddleware
from tenant_scope import (
    INVALID_TENANT_SENTINEL,
    apply_tenant_filter,
    assert_same_tenant,
    get_mantenedora_scope,
    resolve_operational_tenant_context,
    resolve_tenant_id_for_create,
)


class FakeCollection:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]

    async def find_one(self, query=None, projection=None, **_kwargs):
        query = query or {}
        for doc in self.docs:
            ok = True
            for key, expected in query.items():
                if doc.get(key) != expected:
                    ok = False
                    break
            if not ok:
                continue
            result = dict(doc)
            if projection:
                include = {k for k, v in projection.items() if v and k != "_id"}
                if include:
                    result = {k: result.get(k) for k in include if k in result}
                result.pop("_id", None)
            return result
        return None


class FakeDB:
    def __init__(self):
        self.mantenedoras = FakeCollection(
            [
                {"id": "TENANT_A", "nome": "Tenant A", "ativo": True},
                {"id": "TENANT_B", "nome": "Tenant B", "ativo": True},
                {"id": "TENANT_OFF", "nome": "Tenant Off", "ativo": False},
            ]
        )
        self.schools = FakeCollection(
            [
                {"id": "SCHOOL_A", "mantenedora_id": "TENANT_A"},
                {"id": "SCHOOL_B", "mantenedora_id": "TENANT_B"},
                {"id": "SCHOOL_LEGACY"},
            ]
        )


def make_request(path="/api/schools", tenant=None, query=""):
    headers = [(b"authorization", b"Bearer test-token")]
    if tenant:
        headers.append((b"x-mantenedora-id", tenant.encode("utf-8")))
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": query.encode("utf-8"),
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


def super_admin():
    return {
        "id": "USER_SA",
        "role": "super_admin",
        "school_ids": [],
        "email": "sa@example.test",
        "mantenedora_id": None,
    }


def tenant_user():
    return {
        "id": "USER_A",
        "role": "gerente",
        "school_ids": [],
        "email": "a@example.test",
        "mantenedora_id": "TENANT_A",
    }


def test_super_admin_without_selection_is_fail_closed_operationally():
    user = super_admin()
    request = make_request("/api/schools")

    assert get_mantenedora_scope(user, request) == INVALID_TENANT_SENTINEL
    assert apply_tenant_filter({"status": "active"}, user, request) == {
        "status": "active",
        "mantenedora_id": INVALID_TENANT_SENTINEL,
    }

    with pytest.raises(HTTPException) as exc:
        asyncio.run(resolve_operational_tenant_context(FakeDB(), user, request))
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "TENANT_CONTEXT_REQUIRED"


def test_control_plane_is_the_only_cross_tenant_exception():
    user = super_admin()
    request = make_request("/api/mantenedoras")

    assert get_mantenedora_scope(user, request) is None
    assert apply_tenant_filter({"ativo": True}, user, request) == {"ativo": True}


def test_non_super_admin_cannot_override_tenant_with_header():
    user = tenant_user()
    request = make_request("/api/schools", tenant="TENANT_B")

    assert get_mantenedora_scope(user, request) == "TENANT_A"
    ctx = asyncio.run(resolve_operational_tenant_context(FakeDB(), user, request))
    assert ctx.id == "TENANT_A"
    assert ctx.source == "user"


def test_operational_context_validates_existence_and_active_status():
    user = super_admin()

    ctx = asyncio.run(
        resolve_operational_tenant_context(
            FakeDB(), user, make_request("/api/schools", tenant="TENANT_A")
        )
    )
    assert ctx.id == "TENANT_A"

    with pytest.raises(HTTPException) as missing:
        asyncio.run(
            resolve_operational_tenant_context(
                FakeDB(), user, make_request("/api/schools", tenant="NO_SUCH_TENANT")
            )
        )
    assert missing.value.status_code == 409
    assert missing.value.detail["code"] == "TENANT_CONTEXT_INVALID"

    with pytest.raises(HTTPException) as inactive:
        asyncio.run(
            resolve_operational_tenant_context(
                FakeDB(), user, make_request("/api/schools", tenant="TENANT_OFF")
            )
        )
    assert inactive.value.status_code == 403
    assert inactive.value.detail["code"] == "TENANT_INACTIVE"


def test_document_without_tenant_and_cross_tenant_are_rejected():
    user = super_admin()
    request = make_request("/api/schools", tenant="TENANT_A")

    assert_same_tenant({"id": "A", "mantenedora_id": "TENANT_A"}, user, request)

    with pytest.raises(HTTPException) as missing:
        assert_same_tenant({"id": "LEGACY"}, user, request)
    assert missing.value.status_code == 403

    with pytest.raises(HTTPException) as mismatch:
        assert_same_tenant(
            {"id": "B", "mantenedora_id": "TENANT_B"},
            user,
            request,
        )
    assert mismatch.value.status_code == 403


def test_create_resolution_no_longer_derives_parent_without_selected_tenant():
    user = super_admin()
    db = FakeDB()

    no_scope = asyncio.run(
        resolve_tenant_id_for_create(
            db,
            user,
            make_request("/api/students"),
            school_id="SCHOOL_A",
        )
    )
    assert no_scope is None

    selected = asyncio.run(
        resolve_tenant_id_for_create(
            db,
            user,
            make_request("/api/students", tenant="TENANT_A"),
            school_id="SCHOOL_A",
        )
    )
    assert selected == "TENANT_A"


def _install_auth_payload(monkeypatch, role="super_admin", mantenedora_id=None):
    payload = {
        "type": "access",
        "sub": "USER_AUTH",
        "role": role,
        "school_ids": [],
        "email": "auth@example.test",
        "mantenedora_id": mantenedora_id,
    }
    monkeypatch.setattr(auth_module, "decode_token", lambda _token: dict(payload))


def test_auth_middleware_resolves_tenant_before_rbac(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(audit_service, "db", db)
    _install_auth_payload(monkeypatch)

    with pytest.raises(HTTPException) as missing:
        asyncio.run(AuthMiddleware.get_current_user(make_request("/api/schools")))
    assert missing.value.status_code == 409
    assert missing.value.detail["code"] == "TENANT_CONTEXT_REQUIRED"

    request_a = make_request("/api/schools", tenant="TENANT_A")
    user = asyncio.run(AuthMiddleware.get_current_user(request_a))
    assert user["active_mantenedora_id"] == "TENANT_A"
    assert request_a.state.operational_tenant_context.id == "TENANT_A"


def test_auth_middleware_keeps_session_and_control_plane_accessible(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(audit_service, "db", db)
    _install_auth_payload(monkeypatch)

    me = asyncio.run(AuthMiddleware.get_current_user(make_request("/api/auth/me")))
    assert me["role"] == "super_admin"
    assert "active_mantenedora_id" not in me

    control = asyncio.run(
        AuthMiddleware.get_current_user(make_request("/api/mantenedoras"))
    )
    assert control["role"] == "super_admin"
    assert "active_mantenedora_id" not in control


def test_verify_school_access_is_fail_closed_for_missing_or_other_tenant(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(audit_service, "db", db)
    _install_auth_payload(monkeypatch)

    ok = asyncio.run(
        AuthMiddleware.verify_school_access(
            make_request("/api/schools/SCHOOL_A", tenant="TENANT_A"),
            "SCHOOL_A",
        )
    )
    assert ok["active_mantenedora_id"] == "TENANT_A"

    with pytest.raises(HTTPException) as mismatch:
        asyncio.run(
            AuthMiddleware.verify_school_access(
                make_request("/api/schools/SCHOOL_B", tenant="TENANT_A"),
                "SCHOOL_B",
            )
        )
    assert mismatch.value.status_code == 403

    with pytest.raises(HTTPException) as legacy:
        asyncio.run(
            AuthMiddleware.verify_school_access(
                make_request("/api/schools/SCHOOL_LEGACY", tenant="TENANT_A"),
                "SCHOOL_LEGACY",
            )
        )
    assert legacy.value.status_code == 403
