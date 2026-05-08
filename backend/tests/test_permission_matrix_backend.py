"""
Apr 2026 — Testa a integração do AuthMiddleware.require_permission
(Matriz de Permissões) na camada de API.

Valida quatro comportamentos:
  1. super_admin SEMPRE passa (mesmo com override deny).
  2. Papel NÃO padrão recebe 403 sem override.
  3. Papel NÃO padrão recebe 200 quando override visible=True.
  4. Papel padrão recebe 403 quando override visible=False.

Usa a conta assistencia2@sigesc.com (role=ass_social_2) que existe na base
e NÃO está nos defaults de nav-bolsa-familia-button nem nav-analytics-button
(para nav-bolsa-familia-button, ass_social_2 ESTÁ nos defaults — usamos como
caso "default-allow + override deny").
"""
import os
import pytest
import httpx


BACKEND = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://depend-registry.preview.emergentagent.com",
).rstrip("/")

SUPER_ADMIN = {
    "email": "gutenberg@sigesc.com",
    "password": os.environ.get("SIGESC_TEST_SUPERADMIN_PASSWORD", "@Celta2007"),
}
ASS_SOCIAL = {
    "email": "assistencia2@sigesc.com",
    "password": os.environ.get("SIGESC_TEST_ASS_SOCIAL_PASSWORD", "assistencia2123"),
}


def _login(creds):
    r = httpx.post(f"{BACKEND}/api/auth/login", json=creds, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def super_token():
    return _login(SUPER_ADMIN)


@pytest.fixture(scope="module")
def ass_token():
    return _login(ASS_SOCIAL)


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _set_override(su, item_key, role, visible):
    r = httpx.put(
        f"{BACKEND}/api/admin/permissions/override",
        headers=_h(su),
        json={"item_key": item_key, "role": role, "visible": visible},
        timeout=20,
    )
    r.raise_for_status()


def _del_override(su, item_key, role):
    httpx.delete(
        f"{BACKEND}/api/admin/permissions/override",
        headers=_h(su),
        params={"item_key": item_key, "role": role},
        timeout=20,
    )


def test_super_admin_bypasses_matrix_deny(super_token):
    # bloqueia super_admin no menu (não deve afetar)
    _set_override(super_token, "nav-analytics-button", "super_admin", False)
    try:
        r = httpx.get(
            f"{BACKEND}/api/analytics/enrollments/trend?academic_year=2026",
            headers=_h(super_token),
            timeout=30,
        )
        assert r.status_code == 200, r.text
    finally:
        _del_override(super_token, "nav-analytics-button", "super_admin")


def test_default_deny_without_override_returns_403(super_token, ass_token):
    _del_override(super_token, "nav-analytics-button", "ass_social_2")
    r = httpx.get(
        f"{BACKEND}/api/analytics/enrollments/trend?academic_year=2026",
        headers=_h(ass_token),
        timeout=30,
    )
    assert r.status_code == 403, r.text


def test_override_grants_access_to_non_default_role(super_token, ass_token):
    _set_override(super_token, "nav-analytics-button", "ass_social_2", True)
    try:
        r = httpx.get(
            f"{BACKEND}/api/analytics/enrollments/trend?academic_year=2026",
            headers=_h(ass_token),
            timeout=30,
        )
        assert r.status_code == 200, r.text
    finally:
        _del_override(super_token, "nav-analytics-button", "ass_social_2")


def test_override_denies_default_role(super_token, ass_token):
    # ass_social_2 é default-allow em bolsa-familia → override deny bloqueia
    schools = httpx.get(f"{BACKEND}/api/schools", headers=_h(super_token), timeout=20).json()
    school_id = schools[0]["id"]

    _set_override(super_token, "nav-bolsa-familia-button", "ass_social_2", False)
    try:
        r = httpx.get(
            f"{BACKEND}/api/bolsa-familia/students?school_id={school_id}",
            headers=_h(ass_token),
            timeout=30,
        )
        assert r.status_code == 403, r.text
        assert "Matriz de Permiss" in r.json().get("detail", "")
    finally:
        _del_override(super_token, "nav-bolsa-familia-button", "ass_social_2")

    # Após remover override, volta ao default-allow
    r = httpx.get(
        f"{BACKEND}/api/bolsa-familia/students?school_id={school_id}",
        headers=_h(ass_token),
        timeout=30,
    )
    assert r.status_code == 200, r.text
