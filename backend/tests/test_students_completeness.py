"""Tests for the completeness_band/completeness_counts feature on GET /api/students."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://matricula-dedup.preview.emergentagent.com").rstrip("/")
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


def test_counts_match_unfiltered_total(auth_headers):
    r = _get_students(auth_headers)
    assert r.status_code == 200
    data = r.json()
    counts = data["completeness_counts"]
    total = _get_total(data)
    assert total == counts["green"] + counts["yellow"] + counts["red"], f"total={total}, counts={counts}"
