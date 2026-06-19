"""Tests for the completeness_band/completeness_counts feature on GET /api/students."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://school-reorganize.preview.emergentagent.com").rstrip("/")
SCHOOL_ID = "220d4022-ec5e-4fb6-86fc-9233112b87b2"  # Escola Teste Multisseriada

ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = "@Celta2007"


@pytest.fixture(scope="module")
def auth_headers():
    # try multiple known login endpoints
    candidates = [
        "/api/auth/login",
        "/api/login",
    ]
    token = None
    for path in candidates:
        r = requests.post(f"{BASE_URL}{path}", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
        if r.status_code == 200:
            data = r.json()
            token = data.get("access_token") or data.get("token") or (data.get("data") or {}).get("access_token")
            if token:
                break
    if not token:
        pytest.skip(f"Could not authenticate admin user (last status={r.status_code} body={r.text[:200]})")
    return {"Authorization": f"Bearer {token}"}


def _get_total(data):
    t = data.get("total")
    if t is None:
        t = data.get("pagination", {}).get("total")
    return t


def _get_students(headers, **params):
    params.setdefault("school_id", SCHOOL_ID)
    r = requests.get(f"{BASE_URL}/api/students", params=params, headers=headers, timeout=30)
    return r


def test_completeness_counts_present(auth_headers):
    r = _get_students(auth_headers)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert "completeness_counts" in data, f"Missing completeness_counts in response keys={list(data.keys())}"
    counts = data["completeness_counts"]
    assert set(counts.keys()) >= {"green", "yellow", "red"}
    # Expected by problem statement: green=0, yellow=1, red=3
    assert counts["green"] == 0, counts
    assert counts["yellow"] == 1, counts
    assert counts["red"] == 3, counts


def test_filter_band_red(auth_headers):
    r = _get_students(auth_headers, completeness_band="red")
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    total = _get_total(data)
    assert total == 3, f"expected 3 got {total}; data keys={list(data.keys())}"
    items = data.get("items") or data.get("students") or data.get("data") or []
    for s in items:
        pct = s.get("completeness") or s.get("completeness_percent") or s.get("completeness_pct")
        if pct is not None:
            assert pct < 50, f"Student has completeness {pct}, should be <50 (red band)"


def test_filter_band_yellow(auth_headers):
    r = _get_students(auth_headers, completeness_band="yellow")
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    total = _get_total(data)
    assert total == 1, f"expected 1 got {total}"
    items = data.get("items") or data.get("students") or data.get("data") or []
    for s in items:
        pct = s.get("completeness") or s.get("completeness_percent") or s.get("completeness_pct")
        if pct is not None:
            assert 50 <= pct < 80, f"Student has completeness {pct}, should be 50-79 (yellow band)"


def test_filter_band_green(auth_headers):
    r = _get_students(auth_headers, completeness_band="green")
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    total = _get_total(data)
    assert total == 0, f"expected 0 got {total}"
    items = data.get("items") or data.get("students") or data.get("data") or []
    assert len(items) == 0


def test_counts_match_active_count(auth_headers):
    """A soma das faixas de completude deve igualar o nº de ATIVOS (não o total)."""
    r = _get_students(auth_headers)
    assert r.status_code == 200
    data = r.json()
    counts = data["completeness_counts"]
    active = data.get("active_count")
    assert active is not None, "active_count ausente na resposta"
    assert active == counts["green"] + counts["yellow"] + counts["red"], \
        f"active_count={active}, counts={counts}"


def test_completeness_counts_consider_only_active(auth_headers):
    """Numa escola com aluno ativo + transferido, a completude conta só o ativo."""
    mixed_school = "220d4022-ec5e-4773-8b8b-66cd9dc204ad"  # 1 active + 1 transferred
    r = requests.get(
        f"{BASE_URL}/api/students",
        params={"school_id": mixed_school, "page": 1, "page_size": 20},
        headers=auth_headers, timeout=30,
    )
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    total = _get_total(data)
    active = data.get("active_count")
    counts = data["completeness_counts"]
    soma = counts["green"] + counts["yellow"] + counts["red"]
    # total inclui o transferido; a completude NÃO.
    assert total > active, f"esperava total>{active} (inclui não-ativos), got total={total}"
    assert soma == active, f"soma completude ({soma}) deve == active_count ({active})"
    # Banda também deve retornar apenas ativos
    rb = requests.get(
        f"{BASE_URL}/api/students",
        params={"school_id": mixed_school, "page": 1, "page_size": 20, "completeness_band": "red"},
        headers=auth_headers, timeout=30,
    )
    bd = rb.json()
    for s in (bd.get("items") or []):
        assert s.get("status") == "active", f"banda retornou não-ativo: {s.get('status')}"


def _recompute_frontend_style(s):
    """Espelha utils/registrationCompleteness.js (14 critérios)."""
    def f(v):
        return v is not None and str(v).strip() != ""
    checks = [
        f(s.get("full_name")), f(s.get("birth_date")), f(s.get("sex")),
        f(s.get("nationality")), f(s.get("color_race")), f(s.get("comunidade_tradicional")),
        f(s.get("birth_city")), f(s.get("birth_state")), f(s.get("mother_name")),
        f(s.get("legal_guardian_type")),
        any(f(s.get(k)) for k in ("cpf", "nis", "civil_certificate_number")),
        any(f(s.get(k)) for k in ("mother_phone", "father_phone", "guardian_phone")),
        f(s.get("class_id")), f(s.get("enrollment_number")),
    ]
    return round(sum(1 for c in checks if c) / len(checks) * 100)


def test_list_includes_completeness_source_fields_for_client_recompute(auth_headers):
    """A lista deve trazer os campos-fonte da completude (null se vazios) para o
    frontend recalcular a % com o MESMO util do modal — assim lista e
    'Editar Aluno(a)' nunca divergem."""
    r = _get_students(auth_headers, page=1, page_size=10)
    assert r.status_code == 200, r.text[:300]
    items = r.json().get("items") or r.json().get("students") or []
    if not items:
        pytest.skip("Sem alunos para validar")
    required = [
        "full_name", "birth_date", "sex", "nationality", "color_race",
        "comunidade_tradicional", "birth_city", "birth_state", "mother_name",
        "legal_guardian_type", "cpf", "nis", "civil_certificate_number",
        "mother_phone", "father_phone", "guardian_phone", "class_id",
        "enrollment_number",
    ]
    for s in items:
        for field in required:
            assert field in s, f"campo de completude ausente no payload: {field} (aluno {s.get('full_name')})"
        # O recálculo client-side deve bater com o completeness do backend
        assert _recompute_frontend_style(s) == s.get("completeness"), (
            f"divergência lista×recálculo para {s.get('full_name')}: "
            f"backend={s.get('completeness')} client={_recompute_frontend_style(s)}")
