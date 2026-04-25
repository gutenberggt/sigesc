"""
Test Suite: authorized_persons sanitization

Garante que campos auxiliares de UI (em particular `_key`, usado no frontend
para estabilidade de chaves React em listas dinâmicas) NUNCA cruzem a fronteira
de persistência do MongoDB.

Comportamento esperado:
- API aceita o payload com `_key` (sanitização, não rejeição) — HTTP 200
- O documento persistido em `students.authorized_persons` NÃO contém `_key`
- O response do GET subsequente também não retorna `_key`

Fluxo testado: PUT /api/students/{id} com authorized_persons[i]._key = "ui-only-uuid"
"""

import os
import uuid

import pytest
import requests

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
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def auth_token(api_client):
    r = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    if r.status_code != 200:
        pytest.skip(f"Login falhou ({r.status_code}); pulando testes")
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="module")
def some_school_id(api_client, auth_headers):
    """Pega o id da primeira escola disponível para o admin."""
    r = api_client.get(f"{BASE_URL}/api/schools", headers=auth_headers, timeout=20)
    assert r.status_code == 200, f"Falha listando escolas: {r.text}"
    body = r.json()
    items = body if isinstance(body, list) else body.get("items", [])
    if not items:
        pytest.skip("Nenhuma escola disponível para o teste")
    return items[0]["id"]


@pytest.fixture
def temp_student(api_client, auth_headers, some_school_id):
    """Cria um aluno temporário (status inativo, sem matrícula) para o teste e remove no teardown."""
    payload = {
        "school_id": some_school_id,
        "full_name": f"TESTE SANITIZACAO {uuid.uuid4().hex[:8]}",
        "birth_date": "01/01/2010",
        "sex": "masculino",
        "status": "inactive",  # evita exigência de turma para aluno ativo
    }
    r = api_client.post(
        f"{BASE_URL}/api/students", json=payload, headers=auth_headers, timeout=20
    )
    assert r.status_code in (200, 201), f"Falha criando aluno: {r.status_code} {r.text}"
    student = r.json()
    student_id = student["id"]
    yield student_id
    # Cleanup
    try:
        api_client.delete(
            f"{BASE_URL}/api/students/{student_id}", headers=auth_headers, timeout=20
        )
    except Exception:
        pass


def _assert_no_ui_keys(authorized_persons, where: str):
    """Falha se qualquer item contém campo `_key` ou outras chaves de UI."""
    forbidden = {"_key", "_id", "__key"}
    assert isinstance(authorized_persons, list), f"{where}: esperado list, veio {type(authorized_persons)}"
    for i, p in enumerate(authorized_persons):
        leaked = forbidden & set(p.keys())
        assert not leaked, f"{where}[{i}] contém chaves de UI vazadas: {leaked}. Item: {p}"


class TestAuthorizedPersonsSanitization:
    def test_put_strips_underscore_key_from_authorized_persons(
        self, api_client, auth_headers, temp_student
    ):
        """PUT com `_key` deve ser aceito (sanitização) e o `_key` não deve persistir."""
        ui_key_a = f"ap-loaded-{uuid.uuid4().hex}"
        ui_key_b = f"ap-loaded-{uuid.uuid4().hex}"
        update_payload = {
            "authorized_persons": [
                {
                    "_key": ui_key_a,  # campo de UI — DEVE ser descartado
                    "name": "MARIA TIA",
                    "relationship": "TIA",
                    "phone": "62999990000",
                    "document": "12345678900",
                },
                {
                    "_key": ui_key_b,
                    "name": "JOAO VIZINHO",
                    "relationship": "VIZINHO",
                    "phone": None,
                    "document": None,
                },
            ]
        }

        r = api_client.put(
            f"{BASE_URL}/api/students/{temp_student}",
            json=update_payload,
            headers=auth_headers,
            timeout=20,
        )
        assert r.status_code == 200, (
            f"Esperado 200 (sanitização, não rejeição), recebido {r.status_code}: {r.text}"
        )

        # 1) Resposta direta do PUT não deve trazer `_key`
        body = r.json()
        if "authorized_persons" in body and body["authorized_persons"] is not None:
            _assert_no_ui_keys(body["authorized_persons"], "PUT response.authorized_persons")

        # 2) GET subsequente também não pode retornar `_key`
        g = api_client.get(
            f"{BASE_URL}/api/students/{temp_student}", headers=auth_headers, timeout=20
        )
        assert g.status_code == 200, f"GET falhou: {g.status_code} {g.text}"
        student = g.json()
        ap = student.get("authorized_persons") or []
        _assert_no_ui_keys(ap, "GET student.authorized_persons")

        # 3) Os campos legítimos devem ter sido salvos corretamente
        assert len(ap) == 2, f"Esperado 2 pessoas autorizadas, veio {len(ap)}: {ap}"
        names = {p.get("name") for p in ap}
        assert "MARIA TIA" in names and "JOAO VIZINHO" in names, (
            f"Pessoas esperadas não persistiram: {names}"
        )

    def test_post_strips_underscore_key_from_authorized_persons(
        self, api_client, auth_headers, some_school_id
    ):
        """POST de novo aluno com `_key` em authorized_persons também deve sanitizar."""
        unique_name = f"TESTE POST SANITIZACAO {uuid.uuid4().hex[:8]}"
        payload = {
            "school_id": some_school_id,
            "full_name": unique_name,
            "birth_date": "01/01/2012",
            "sex": "feminino",
            "status": "inactive",
            "authorized_persons": [
                {
                    "_key": "should-be-stripped",
                    "name": "AVO PATERNA",
                    "relationship": "AVO",
                    "phone": "62988880000",
                    "document": None,
                },
            ],
        }
        r = api_client.post(
            f"{BASE_URL}/api/students", json=payload, headers=auth_headers, timeout=20
        )
        assert r.status_code in (200, 201), (
            f"Esperado 2xx (sanitização), recebido {r.status_code}: {r.text}"
        )
        created = r.json()
        student_id = created.get("id")
        assert student_id, f"Resposta sem id: {created}"

        try:
            ap = created.get("authorized_persons") or []
            _assert_no_ui_keys(ap, "POST response.authorized_persons")

            g = api_client.get(
                f"{BASE_URL}/api/students/{student_id}",
                headers=auth_headers,
                timeout=20,
            )
            assert g.status_code == 200
            ap_get = g.json().get("authorized_persons") or []
            _assert_no_ui_keys(ap_get, "GET student.authorized_persons (after POST)")
            assert any(p.get("name") == "AVO PATERNA" for p in ap_get), (
                f"Pessoa esperada não persistiu: {ap_get}"
            )
        finally:
            api_client.delete(
                f"{BASE_URL}/api/students/{student_id}",
                headers=auth_headers,
                timeout=20,
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
