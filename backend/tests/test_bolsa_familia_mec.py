"""E2E HTTP tests para o módulo Bolsa Família MEC (Fev/2026).

Cobre:
  - Seed dos motivos MEC (presença das collections + counts esperados)
  - GET /api/bolsa-familia/reason-groups
  - GET /api/bolsa-familia/reasons (com filtros)
  - GET /api/bolsa-familia/reasons/grouped
  - PUT /api/bolsa-familia/tracking (reason_id + notes + motive_legacy)
  - PUT /api/bolsa-familia/tracking/bulk
  - Validação 422 para reason_id inválido
  - Compatibilidade com payload legado (motive)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASS = "@Celta2007"


@pytest.fixture(scope="module")
def auth():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not set")
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    token = body.get("access_token") or body.get("token")
    csrf = body.get("csrf_token")
    assert token and csrf
    return {"token": token, "csrf": csrf}


def _headers(auth, with_csrf=True):
    h = {"Authorization": f"Bearer {auth['token']}", "Content-Type": "application/json"}
    if with_csrf:
        h["X-CSRF-Token"] = auth["csrf"]
    return h


def test_reason_groups_returns_25(auth):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/reason-groups",
        headers=_headers(auth, False),
        timeout=15,
    )
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body["total"] == 25
    # mec_code 1 deve ser o primeiro
    assert body["groups"][0]["mec_code"] == "1"
    # mec_version preenchido
    assert body["groups"][0]["mec_version"] == "4.2"


def test_reasons_returns_57_without_legacy(auth):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/reasons",
        headers=_headers(auth, False),
        timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 57  # 58 com legacy, 57 sem
    # Cada reason tem fields esperados
    sample = body["reasons"][0]
    assert "id" in sample
    assert "group_id" in sample
    assert "mec_subcode" in sample
    assert "severity_level" in sample


def test_reasons_with_legacy_returns_58(auth):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/reasons?include_legacy=true",
        headers=_headers(auth, False),
        timeout=15,
    )
    assert r.status_code == 200
    assert r.json()["total"] == 58
    # 24z é o legacy
    subcodes = [r["mec_subcode"] for r in r.json()["reasons"]]
    assert "24z" in subcodes


def test_reasons_filtered_by_group(auth):
    # Pega o primeiro grupo via API
    groups = requests.get(
        f"{BASE_URL}/api/bolsa-familia/reason-groups",
        headers=_headers(auth, False),
        timeout=15,
    ).json()["groups"]
    g3 = next(g for g in groups if g["mec_code"] == "3")
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/reasons?group_id={g3['id']}",
        headers=_headers(auth, False),
        timeout=15,
    )
    assert r.status_code == 200
    # Grupo 3 tem 6 submotivos (3a-3f)
    assert r.json()["total"] == 6
    for reason in r.json()["reasons"]:
        assert reason["mec_group_code"] == "3"


def test_reasons_grouped_shape(auth):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/reasons/grouped",
        headers=_headers(auth, False),
        timeout=15,
    )
    assert r.status_code == 200
    groups = r.json()["groups"]
    assert len(groups) == 25
    g1 = groups[0]
    assert g1["mec_code"] == "1"
    assert "reasons" in g1
    assert len(g1["reasons"]) == 4  # 1a, 1b, 1c, 1d
    # Cada reason dentro do grupo tem mec_subcode
    assert all("mec_subcode" in r for r in g1["reasons"])


def test_tracking_save_with_reason_id(auth):
    # Pega um reason_id válido (3b - Falta de transporte)
    reasons = requests.get(
        f"{BASE_URL}/api/bolsa-familia/reasons",
        headers=_headers(auth, False),
        timeout=15,
    ).json()["reasons"]
    reason_3b = next(r for r in reasons if r["mec_subcode"] == "3b")

    payload = {
        "student_id": "test_student_mec_001",
        "school_id": "test_school_mec_001",
        "month": 3,
        "academic_year": 2026,
        "reason_id": reason_3b["id"],
        "notes": "Aluno relatou que ônibus quebrou 3x no mês",
    }
    r = requests.put(
        f"{BASE_URL}/api/bolsa-familia/tracking",
        headers=_headers(auth, True),
        json=payload,
        timeout=15,
    )
    assert r.status_code == 200, r.text[:200]


def test_tracking_save_invalid_reason_id_returns_422(auth):
    payload = {
        "student_id": "test_student_mec_002",
        "school_id": "test_school_mec_001",
        "month": 3,
        "academic_year": 2026,
        "reason_id": "00000000-aaaa-bbbb-cccc-deadbeef0000",
        "notes": "",
    }
    r = requests.put(
        f"{BASE_URL}/api/bolsa-familia/tracking",
        headers=_headers(auth, True),
        json=payload,
        timeout=15,
    )
    assert r.status_code == 422, r.text[:200]


def test_tracking_save_legacy_motive_backward_compat(auth):
    """Aceita `motive` legacy quando reason_id ausente (compatibilidade)."""
    payload = {
        "student_id": "test_student_mec_legacy",
        "school_id": "test_school_mec_001",
        "month": 4,
        "academic_year": 2026,
        "motive": "Aluno faltou pq choveu (legado)",
    }
    r = requests.put(
        f"{BASE_URL}/api/bolsa-familia/tracking",
        headers=_headers(auth, True),
        json=payload,
        timeout=15,
    )
    assert r.status_code == 200, r.text[:200]


def test_tracking_bulk_with_reason_id(auth):
    reasons = requests.get(
        f"{BASE_URL}/api/bolsa-familia/reasons",
        headers=_headers(auth, False),
        timeout=15,
    ).json()["reasons"]
    r1a = next(r for r in reasons if r["mec_subcode"] == "1a")
    r11a = next(r for r in reasons if r["mec_subcode"] == "11a")
    payload = {
        "items": [
            {"student_id": "bulk_s1", "school_id": "bulk_sc1", "month": 2,
             "academic_year": 2026, "reason_id": r1a["id"], "notes": "doença"},
            {"student_id": "bulk_s2", "school_id": "bulk_sc1", "month": 2,
             "academic_year": 2026, "reason_id": r11a["id"], "notes": ""},
            {"student_id": "bulk_s3", "school_id": "bulk_sc1", "month": 2,
             "academic_year": 2026, "reason_id": "invalid-id", "notes": ""},
        ]
    }
    r = requests.put(
        f"{BASE_URL}/api/bolsa-familia/tracking/bulk",
        headers=_headers(auth, True),
        json=payload,
        timeout=15,
    )
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body["saved"] == 2
    assert len(body["errors"]) == 1
    assert "reason_id" in body["errors"][0]["error"]


def test_tracking_list_returns_new_schema(auth):
    """list_bolsa_familia_students retorna reason_id/notes/motive_legacy nos meses."""
    # Pegar primeira escola disponível
    schools_r = requests.get(
        f"{BASE_URL}/api/schools",
        headers=_headers(auth, False),
        timeout=15,
    )
    if schools_r.status_code != 200 or not schools_r.json():
        pytest.skip("Sem escolas disponíveis para teste")
    school = schools_r.json()[0]
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/students?school_id={school['id']}&academic_year=2026",
        headers=_headers(auth, False),
        timeout=15,
    )
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    if body.get("students"):
        s = body["students"][0]
        any_month = next(iter(s["months"].values()), None)
        if any_month:
            # Schema novo
            assert "reason_id" in any_month
            assert "notes" in any_month
            assert "motive_legacy" in any_month
