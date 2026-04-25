"""Iteration 59 — regression after dropping legacy db.mantenedora collection.
All endpoints that previously used db.mantenedora (singular) must still work
reading from db.mantenedoras (plural) via get_mantenedora_cached.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend/.env
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL"):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
    except FileNotFoundError:
        pass

CREDS = {"email": "gutenberg@sigesc.com", "password": os.getenv("SIGESC_TEST_ADMIN_PASSWORD", "@Celta2007")}


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=CREDS, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    return body.get("access_token") or body.get("token")


@pytest.fixture(scope="module")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# Endpoints that internally rely on mantenedora doc
ENDPOINTS_MUST_200 = [
    "/api/mantenedora",
    "/api/analytics/overview",
    "/api/classes",
    "/api/schools",
    "/api/users",
    "/api/students",
    "/api/mantenedoras",  # list (super_admin)
]


@pytest.mark.parametrize("path", ENDPOINTS_MUST_200)
def test_endpoint_returns_200(auth_headers, path):
    r = requests.get(f"{BASE_URL}{path}", headers=auth_headers, timeout=30)
    assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:300]}"
    # Basic structural validation
    data = r.json()
    assert data is not None


def test_mantenedora_endpoint_returns_data(auth_headers):
    r = requests.get(f"{BASE_URL}/api/mantenedora", headers=auth_headers, timeout=30)
    assert r.status_code == 200
    data = r.json()
    # Should return a mantenedora doc (dict) since gutenberg is super_admin with tenant context
    assert isinstance(data, (dict, list))


def test_grades_endpoint_uses_cached_mantenedora(auth_headers):
    """grades.py line 249 migrated to get_mantenedora_cached. Test listing grades."""
    r = requests.get(f"{BASE_URL}/api/grades", headers=auth_headers, timeout=30)
    # 200 or 404 acceptable if no grades exist; 500 means legacy call broken
    assert r.status_code != 500, f"grades endpoint exploding: {r.text[:400]}"


def test_attendance_ext_endpoint(auth_headers):
    """attendance_ext.py line 198 migrated. Hit any attendance route."""
    r = requests.get(f"{BASE_URL}/api/attendance", headers=auth_headers, timeout=30)
    assert r.status_code != 500, f"attendance endpoint exploding: {r.text[:400]}"


def test_bolsa_familia_list(auth_headers):
    r = requests.get(f"{BASE_URL}/api/bolsa-familia", headers=auth_headers, timeout=30)
    assert r.status_code != 500, f"bolsa_familia exploding: {r.text[:400]}"


def test_class_details_requires_id_but_no_500(auth_headers):
    # without an id we expect 404/405/422 but NOT 500
    r = requests.get(f"{BASE_URL}/api/class-details/nonexistent", headers=auth_headers, timeout=30)
    assert r.status_code != 500, f"class_details exploding: {r.text[:400]}"


def test_mantenedoras_list_has_data(auth_headers):
    r = requests.get(f"{BASE_URL}/api/mantenedoras", headers=auth_headers, timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    # should have id and name
    assert "id" in data[0]
    # name field may be 'name' or 'nome' depending on schema
    assert "name" in data[0] or "nome" in data[0] or "razao_social" in data[0]
