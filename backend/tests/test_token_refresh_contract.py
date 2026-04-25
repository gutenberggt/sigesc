"""
Test Suite: Token refresh & parallel auth contract

Garante que o contrato de autenticação não cause "stale auth" durante
janelas de renovação de token. Cenário motivador: o frontend pode ter
closures (em useEffects/useCallback) com o access_token antigo no momento
em que o AuthContext faz refresh em background. Chamadas em flight com o
token antigo NÃO devem falhar enquanto o JWT antigo não estiver expirado.

Cenários cobertos:
  1. Login retorna access_token + refresh_token válidos
  2. GET /api/auth/me funciona com access_token
  3. POST /api/auth/refresh emite NOVO access_token diferente do antigo
  4. NOVO access_token funciona em /api/auth/me
  5. Access_token ANTIGO continua válido após refresh (não há invalidação imediata)
  6. Chamadas paralelas com tokens antigo+novo simultaneamente: AMBAS sucedem
  7. Refresh token inválido → 401
  8. Após /api/auth/logout, access_token é blacklistado (mesmo antes de expirar via JWT)
"""

import os
import asyncio
import pytest
import requests
import httpx

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except Exception:
        pass

ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = os.getenv("SIGESC_TEST_ADMIN_PASSWORD", "@Celta2007")


@pytest.fixture(scope="module")
def fresh_login():
    """Login isolado para esta suíte. Retorna tokens iniciais."""
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    if r.status_code != 200:
        pytest.skip(f"Login falhou ({r.status_code}); pulando suíte")
    body = r.json()
    return {
        "access_token": body.get("access_token") or body.get("token"),
        "refresh_token": body.get("refresh_token"),
        "user": body.get("user"),
    }


def _get_me(access_token: str):
    return requests.get(
        f"{BASE_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )


class TestTokenRefreshContract:
    def test_login_returns_both_tokens(self, fresh_login):
        assert fresh_login["access_token"], "access_token ausente no /login"
        assert fresh_login["refresh_token"], "refresh_token ausente no /login"

    def test_old_access_token_works(self, fresh_login):
        r = _get_me(fresh_login["access_token"])
        assert r.status_code == 200, f"/me com token recém-emitido falhou: {r.status_code} {r.text}"
        assert r.json().get("email") == ADMIN_EMAIL

    def test_refresh_emits_distinct_access_token(self, fresh_login):
        r = requests.post(
            f"{BASE_URL}/api/auth/refresh",
            json={"refresh_token": fresh_login["refresh_token"]},
            timeout=20,
        )
        assert r.status_code == 200, f"Refresh falhou: {r.status_code} {r.text}"
        body = r.json()
        new_access = body.get("access_token") or body.get("token")
        assert new_access, "Novo access_token ausente"
        assert new_access != fresh_login["access_token"], (
            "Novo access_token deveria ser diferente do antigo"
        )
        # Salva no fixture para próximos testes (escopo module)
        fresh_login["new_access_token"] = new_access
        fresh_login["new_refresh_token"] = body.get("refresh_token")

    def test_new_access_token_works(self, fresh_login):
        if "new_access_token" not in fresh_login:
            pytest.skip("Refresh anterior não rodou")
        r = _get_me(fresh_login["new_access_token"])
        assert r.status_code == 200, f"/me com novo token falhou: {r.text}"

    def test_old_access_token_still_works_after_refresh(self, fresh_login):
        """
        Ponto crítico para o cenário de 'stale auth' do frontend:
        se um closure ainda tem o token antigo no momento em que o refresh
        ocorre, a chamada com token antigo precisa ser respondida com sucesso
        enquanto o JWT antigo não estiver expirado.
        """
        if "new_access_token" not in fresh_login:
            pytest.skip("Refresh anterior não rodou")
        r = _get_me(fresh_login["access_token"])
        assert r.status_code == 200, (
            f"Token antigo foi invalidado prematuramente após refresh "
            f"(stale auth bug): {r.status_code} {r.text}"
        )

    def test_parallel_requests_with_old_and_new_tokens(self, fresh_login):
        """
        Simula o cenário real: durante a janela de refresh, o frontend pode
        disparar chamadas paralelas — algumas com token antigo (de closures
        capturados antes), outras com token novo. AMBAS precisam funcionar.
        """
        if "new_access_token" not in fresh_login:
            pytest.skip("Refresh anterior não rodou")

        async def one_call(token):
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(
                    f"{BASE_URL}/api/auth/me",
                    headers={"Authorization": f"Bearer {token}"},
                )
                return resp.status_code

        async def run_parallel():
            tasks = []
            for _ in range(5):
                tasks.append(one_call(fresh_login["access_token"]))
                tasks.append(one_call(fresh_login["new_access_token"]))
            return await asyncio.gather(*tasks, return_exceptions=True)

        results = asyncio.run(run_parallel())
        failures = [r for r in results if r != 200]
        assert not failures, (
            f"Chamadas paralelas com tokens antigo+novo: "
            f"{len(failures)} falhas de {len(results)} ({failures})"
        )

    def test_invalid_refresh_token_returns_401(self):
        r = requests.post(
            f"{BASE_URL}/api/auth/refresh",
            json={"refresh_token": "obviously.not.valid"},
            timeout=20,
        )
        assert r.status_code == 401, (
            f"Refresh token inválido deveria retornar 401, retornou {r.status_code}"
        )

    def test_access_token_used_as_refresh_token_returns_401(self, fresh_login):
        """access_token tem type='access'; refresh exige type='refresh'."""
        r = requests.post(
            f"{BASE_URL}/api/auth/refresh",
            json={"refresh_token": fresh_login["access_token"]},
            timeout=20,
        )
        assert r.status_code == 401, (
            f"Usar access_token como refresh deveria 401, retornou {r.status_code}"
        )


class TestLogoutBlacklist:
    """Logout deve invalidar o access_token mesmo antes de seu vencimento natural."""

    def test_logout_blacklists_access_token(self):
        # Login isolado pra não interferir com a outra suíte
        login = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=20,
        )
        if login.status_code != 200:
            pytest.skip("Login falhou")
        token = login.json().get("access_token") or login.json().get("token")
        assert token

        # Confirma que o token funciona ANTES do logout
        ok = _get_me(token)
        assert ok.status_code == 200, f"Token inicial deveria funcionar: {ok.status_code}"

        # Logout
        out = requests.post(
            f"{BASE_URL}/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        assert out.status_code in (200, 204), (
            f"Logout deveria 200/204, retornou {out.status_code}: {out.text}"
        )

        # Após logout, o mesmo token deve ser rejeitado
        after = _get_me(token)
        assert after.status_code == 401, (
            f"Token deveria ser blacklistado após logout. Status: {after.status_code}, body: {after.text}"
        )

    def test_logout_invalidates_refresh_token(self):
        """Após logout, refresh_token também deve ser bloqueado."""
        login = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=20,
        )
        if login.status_code != 200:
            pytest.skip("Login falhou")
        body = login.json()
        access = body.get("access_token") or body.get("token")
        refresh = body.get("refresh_token")

        # Logout enviando refresh_token explicitamente (revoga jti específico)
        requests.post(
            f"{BASE_URL}/api/auth/logout",
            headers={"Authorization": f"Bearer {access}"},
            json={"refresh_token": refresh},
            timeout=20,
        )

        # Tenta usar o refresh — deve ser rejeitado
        r = requests.post(
            f"{BASE_URL}/api/auth/refresh",
            json={"refresh_token": refresh},
            timeout=20,
        )
        assert r.status_code == 401, (
            f"Refresh token deveria ser bloqueado após logout. Status: {r.status_code}"
        )

    def test_logout_revokes_other_concurrent_sessions(self):
        """
        Crítico para ambiente educacional: usuário logado em 2 devices.
        Logout em device A deve invalidar token em device B.
        """
        # Aguarda 1.1s para garantir que iat (segundo) seja > revoke_all_before
        # de testes anteriores deste módulo (microssegundos do mesmo segundo).
        import time
        time.sleep(1.1)
        # Login no device A
        login_a = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=20,
        )
        if login_a.status_code != 200:
            pytest.skip("Login falhou")
        token_a = login_a.json().get("access_token") or login_a.json().get("token")

        # Login no device B (mesmo usuário, sessão separada)
        login_b = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=20,
        )
        token_b = login_b.json().get("access_token") or login_b.json().get("token")

        # Ambos devem funcionar inicialmente
        assert _get_me(token_a).status_code == 200
        assert _get_me(token_b).status_code == 200

        # Logout no device A
        requests.post(
            f"{BASE_URL}/api/auth/logout",
            headers={"Authorization": f"Bearer {token_a}"},
            timeout=20,
        )

        # Token B (de outro device) também deve ser invalidado
        # (revoke_all_user_tokens usa marker user-wide)
        after_b = _get_me(token_b)
        assert after_b.status_code == 401, (
            f"Sessão concorrente do device B deveria ser invalidada após logout. "
            f"Status: {after_b.status_code}, body: {after_b.text}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
