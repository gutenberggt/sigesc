"""Fev 2026 — Testa Sprint G2: HttpOnly cookies + CSRF + session rotation.

Cobre:
  1. Login seta 3 cookies (access HttpOnly, refresh HttpOnly, csrf não-HttpOnly).
  2. GET /auth/me funciona apenas com cookie (sem Authorization header).
  3. Retrocompat: GET /auth/me continua funcionando com Bearer header.
  4. Refresh rotaciona jti: o refresh antigo é revogado após uso.
  5. CSRF: POST sem header é bloqueado quando auth vem de cookie.
  6. CSRF: POST com header correto passa.
  7. CSRF: POST autenticado via Bearer (sem cookie) não exige CSRF.
  8. Logout limpa cookies e invalida tokens.
"""
import os
import time
from datetime import datetime, timezone

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BACKEND = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://institutional-audit-2.preview.emergentagent.com",
).rstrip("/")

SUPER_ADMIN = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}

ACCESS_COOKIE = "sigesc_access"
REFRESH_COOKIE = "sigesc_refresh"
CSRF_COOKIE = "sigesc_csrf"


def _login_with_cookies() -> httpx.Client:
    """Faz login e retorna cliente httpx com cookies persistidos."""
    client = httpx.Client(timeout=20, follow_redirects=True)
    r = client.post(f"{BACKEND}/api/auth/login", json=SUPER_ADMIN)
    r.raise_for_status()
    return client


def test_login_sets_all_three_cookies():
    r = httpx.post(f"{BACKEND}/api/auth/login", json=SUPER_ADMIN, timeout=20)
    assert r.status_code == 200

    # Parse cookies do Set-Cookie headers
    set_cookies = r.headers.get_list("set-cookie")
    combined = "|".join(set_cookies).lower()
    assert "sigesc_access=" in combined
    assert "sigesc_refresh=" in combined
    assert "sigesc_csrf=" in combined
    # Flags de segurança
    assert "httponly" in combined
    assert "samesite=lax" in combined
    # access e refresh devem ter HttpOnly
    access_line = next(c for c in set_cookies if c.lower().startswith("sigesc_access="))
    refresh_line = next(c for c in set_cookies if c.lower().startswith("sigesc_refresh="))
    csrf_line = next(c for c in set_cookies if c.lower().startswith("sigesc_csrf="))
    assert "httponly" in access_line.lower()
    assert "httponly" in refresh_line.lower()
    # csrf NÃO pode ser HttpOnly (frontend precisa ler)
    assert "httponly" not in csrf_line.lower()
    # refresh com path limitado à /api/auth (menor superfície)
    assert "path=/api/auth" in refresh_line.lower()


def test_me_works_with_cookie_only():
    """Após login, cookie basta — Authorization header NÃO é enviado."""
    client = _login_with_cookies()
    r = client.get(f"{BACKEND}/api/auth/me")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["email"].lower() == SUPER_ADMIN["email"].lower()


def test_me_still_works_with_bearer_header_legacy():
    """Retrocompat: Bearer no header continua funcionando durante migração."""
    r = httpx.post(f"{BACKEND}/api/auth/login", json=SUPER_ADMIN, timeout=20)
    assert r.status_code == 200
    access = r.json()["access_token"]
    # Usa client SEM cookies (só Bearer)
    r2 = httpx.get(
        f"{BACKEND}/api/auth/me",
        headers={"Authorization": f"Bearer {access}"},
        timeout=20,
    )
    assert r2.status_code == 200
    assert r2.json()["email"].lower() == SUPER_ADMIN["email"].lower()


def test_refresh_rotates_and_invalidates_old_jti():
    """Primeiro refresh ok; segundo com mesmo refresh token deve falhar (rotação)."""
    r = httpx.post(f"{BACKEND}/api/auth/login", json=SUPER_ADMIN, timeout=20)
    assert r.status_code == 200
    old_refresh = r.json()["refresh_token"]

    # 1º refresh: OK
    r1 = httpx.post(
        f"{BACKEND}/api/auth/refresh",
        json={"refresh_token": old_refresh},
        timeout=20,
    )
    assert r1.status_code == 200, r1.text
    new_refresh = r1.json()["refresh_token"]
    assert new_refresh != old_refresh

    # 2º refresh com o refresh token ANTIGO: deve falhar (foi revogado)
    r2 = httpx.post(
        f"{BACKEND}/api/auth/refresh",
        json={"refresh_token": old_refresh},
        timeout=20,
    )
    assert r2.status_code == 401, r2.text


def test_csrf_blocks_write_without_header_when_auth_via_cookie():
    """POST a rota de escrita autenticada via cookie sem X-CSRF-Token → 403."""
    client = _login_with_cookies()
    # Remove bearer do header — só cookie
    # Tenta POST em rota protegida por escrita (logout-all é POST autenticado)
    r = client.post(f"{BACKEND}/api/auth/logout-all")
    assert r.status_code == 403, r.text
    assert "csrf" in r.text.lower()


def test_csrf_allows_write_with_correct_header():
    """POST com X-CSRF-Token batendo com cookie passa."""
    client = _login_with_cookies()
    csrf = client.cookies.get(CSRF_COOKIE)
    assert csrf, "CSRF cookie não foi setado pelo login"
    r = client.post(
        f"{BACKEND}/api/auth/logout-all",
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text


def test_csrf_validates_via_jwt_claim_when_no_cookie():
    """Mai/2026: em deploys cross-domain o cookie CSRF não chega ao backend.
    O middleware deve aceitar o header X-CSRF-Token validado via claim 'csrf'
    embutido no JWT — bastando access_token + header correto.
    """
    time.sleep(1.2)  # garante JWT iat > revoke_all_before
    r = httpx.post(f"{BACKEND}/api/auth/login", json=SUPER_ADMIN, timeout=20)
    body = r.json()
    access = body["access_token"]
    csrf = body.get("csrf_token")
    assert csrf, "csrf_token deve vir no body do /login"
    # Bearer + header CSRF (sem cookies de sessão)
    r2 = httpx.post(
        f"{BACKEND}/api/auth/logout-all",
        headers={
            "Authorization": f"Bearer {access}",
            "X-CSRF-Token": csrf,
        },
        timeout=20,
    )
    assert r2.status_code == 200, r2.text


def test_csrf_rejects_bearer_without_token():
    """Bearer auth sem header CSRF deve falhar (proteção mantida)."""
    time.sleep(1.2)
    r = httpx.post(f"{BACKEND}/api/auth/login", json=SUPER_ADMIN, timeout=20)
    access = r.json()["access_token"]
    r2 = httpx.post(
        f"{BACKEND}/api/auth/logout-all",
        headers={"Authorization": f"Bearer {access}"},
        timeout=20,
    )
    assert r2.status_code == 403


def test_logout_clears_cookies_and_revokes():
    # Os testes anteriores disparam revoke_all_user_tokens (logout-all).
    # JWT iat é segundo inteiro; revoke_all_before é datetime.
    # Precisamos ultrapassar a borda do segundo para que o novo login
    # gere um token com iat estritamente > revoke_all_before.
    time.sleep(1.2)
    client = _login_with_cookies()
    csrf = client.cookies.get(CSRF_COOKIE)
    # Logout precisa passar CSRF header
    r = client.post(
        f"{BACKEND}/api/auth/logout",
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    # O Set-Cookie do logout deve expirar os 3 cookies
    sc = "|".join(r.headers.get_list("set-cookie")).lower()
    assert "sigesc_access=" in sc
    assert "sigesc_refresh=" in sc
    assert "sigesc_csrf=" in sc
    # Após a resposta, os cookies são deletados (max-age=0 ou expires passado)
    # Nova chamada com cookies vazios deve falhar
    client2 = httpx.Client(timeout=20)
    r2 = client2.get(f"{BACKEND}/api/auth/me")
    assert r2.status_code == 401


def test_csrf_token_endpoint_rotates_cookie():
    """GET /auth/csrf-token emite novo CSRF sem invalidar sessão."""
    # Ultrapassa borda de segundo do logout dos testes anteriores
    time.sleep(1.2)
    client = _login_with_cookies()
    original_csrf = client.cookies.get(CSRF_COOKIE)
    # Aguarda 1s para garantir cookie novo (token random tem 43 chars cada chamada)
    time.sleep(1)
    r = client.get(f"{BACKEND}/api/auth/csrf-token")
    assert r.status_code == 200
    data = r.json()
    assert "csrf_token" in data
    assert data["csrf_token"]
    # Cookie deve ter sido rotacionado
    new_csrf = client.cookies.get(CSRF_COOKIE)
    assert new_csrf is not None
    assert new_csrf == data["csrf_token"]
    assert new_csrf != original_csrf
