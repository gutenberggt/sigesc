"""Testes para validar fix do CSRF no Diário AEE (POST/PUT/DELETE)."""
import os
import pytest
import requests
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASS = "@Celta2007"


@pytest.fixture(scope="module")
def auth_data():
    """Login as super_admin and capture access_token + csrf_token."""
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not set")
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
                      timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    token = body.get("access_token") or body.get("token")
    csrf = body.get("csrf_token")
    assert token, f"no access_token in login body keys={list(body.keys())}"
    assert csrf, f"no csrf_token in login body keys={list(body.keys())}"
    return {"token": token, "csrf": csrf}


def _headers(auth, with_csrf=True):
    h = {"Authorization": f"Bearer {auth['token']}", "Content-Type": "application/json"}
    if with_csrf:
        h["X-CSRF-Token"] = auth["csrf"]
    return h


def test_post_planos_without_csrf_returns_403(auth_data):
    """Sem X-CSRF-Token deve retornar 403 e bloquear o POST (reproduz o bug original)."""
    r = requests.post(f"{BASE_URL}/api/aee/planos",
                      headers=_headers(auth_data, with_csrf=False),
                      json={"student_id": "fake", "school_id": "fake", "academic_year": 2026,
                            "publico_alvo": "deficiencia_intelectual", "modalidade": "individual"},
                      timeout=15)
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"
    detail = r.json().get("detail", "")
    assert "CSRF" in detail or "csrf" in detail.lower(), f"unexpected detail: {detail}"


def test_post_atendimentos_without_csrf_returns_403(auth_data):
    r = requests.post(f"{BASE_URL}/api/aee/atendimentos",
                      headers=_headers(auth_data, with_csrf=False),
                      json={}, timeout=15)
    assert r.status_code == 403


def test_post_templates_without_csrf_returns_403(auth_data):
    r = requests.post(f"{BASE_URL}/api/aee/templates",
                      headers=_headers(auth_data, with_csrf=False),
                      json={}, timeout=15)
    assert r.status_code == 403


def test_post_planos_with_csrf_passes_middleware(auth_data):
    """Com CSRF correto, middleware deve liberar — esperamos 404 (aluno fake) ou 422, NUNCA 403."""
    r = requests.post(f"{BASE_URL}/api/aee/planos",
                      headers=_headers(auth_data, with_csrf=True),
                      json={"student_id": "00000000-0000-0000-0000-000000000000",
                            "school_id": "00000000-0000-0000-0000-000000000000",
                            "academic_year": 2026,
                            "publico_alvo": "deficiencia_intelectual",
                            "modalidade": "individual",
                            "data_elaboracao": "2026-01-15"},
                      timeout=15)
    assert r.status_code != 403, f"CSRF still blocking with header set: {r.status_code} {r.text[:200]}"
    # Esperado: 404 aluno não encontrado, ou 422 validação
    assert r.status_code in (200, 201, 400, 404, 422), f"unexpected status {r.status_code}: {r.text[:200]}"


def test_full_create_plano_flow_with_csrf(auth_data):
    """Cria um plano AEE end-to-end com aluno real e valida 201 + GET."""
    # Pega um aluno real com school_id
    r_students = requests.get(f"{BASE_URL}/api/students?page_size=50",
                              headers=_headers(auth_data), timeout=15)
    assert r_students.status_code == 200
    items = r_students.json().get("items") or r_students.json()
    student = next((s for s in items if s.get("school_id") and s.get("id")), None)
    if not student:
        pytest.skip("no students with school_id available for e2e test")
    sid = student["id"]
    school_id = student["school_id"]

    # Limpa qualquer plano pré-existente para esse aluno em 2099 (ano fictício do teste)
    test_year = 2099
    payload = {
        "student_id": sid,
        "school_id": school_id,
        "academic_year": test_year,
        "publico_alvo": "deficiencia_intelectual",
        "modalidade": "individual",
        "data_elaboracao": "2099-01-15",
        "professor_aee_id": "00000000-0000-0000-0000-000000000001",
        "professor_aee_nome": "QA Professor",
    }
    # Limpa via lista+delete se existir
    r_list = requests.get(
        f"{BASE_URL}/api/aee/planos?student_id={sid}&academic_year={test_year}",
        headers=_headers(auth_data), timeout=15)
    if r_list.status_code == 200:
        for p in (r_list.json().get("items") or []):
            requests.delete(f"{BASE_URL}/api/aee/planos/{p['id']}",
                            headers=_headers(auth_data), timeout=15)

    r = requests.post(f"{BASE_URL}/api/aee/planos",
                      headers=_headers(auth_data),
                      json=payload, timeout=20)
    assert r.status_code in (200, 201), f"create plano failed: {r.status_code} {r.text[:300]}"
    plano = r.json()
    assert plano.get("student_id") == sid
    plano_id = plano["id"]

    # Verifica persistência via GET
    r_get = requests.get(f"{BASE_URL}/api/aee/planos/{plano_id}",
                         headers=_headers(auth_data), timeout=15)
    assert r_get.status_code == 200
    assert r_get.json().get("student_id") == sid

    # Cleanup
    r_del = requests.delete(f"{BASE_URL}/api/aee/planos/{plano_id}",
                            headers=_headers(auth_data), timeout=15)
    assert r_del.status_code in (200, 204)
