"""
Multi-Tenant Phase 2 — Tenant scoping across all core routers.

Validates:
  1. POST endpoints inject mantenedora_id (verified via MongoDB).
  2. GET listings honor X-Mantenedora-Id header (filter by tenant).
  3. assert_same_tenant returns 403 for cross-tenant GET/PUT/DELETE.
  4. super_admin without header sees both tenants' data.
  5. Regression: original mantenedora data still accessible.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://matricula-dedup.preview.emergentagent.com').rstrip('/')
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = os.getenv("SIGESC_TEST_ADMIN_PASSWORD", "@Celta2007")
ORIGINAL_TENANT = "a991c1ac-56b1-46a8-b122-effedbe19b21"


# ------------------------- FIXTURES -------------------------

@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    token = data.get("access_token") or data.get("token")
    assert token, f"No token: {data}"
    return token


@pytest.fixture(scope="module")
def headers(admin_token):
    """Cross-tenant headers (no X-Mantenedora-Id)."""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def headers_t1(admin_token):
    """Headers scoped to original mantenedora."""
    return {"Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
            "X-Mantenedora-Id": ORIGINAL_TENANT}


@pytest.fixture(scope="module")
def secondary_tenant(headers):
    """Create a temporary second mantenedora for isolation tests; cleanup at end."""
    payload = {
        "nome": "TEST_MT_PHASE2_TENANT",
        "cnpj": "00.000.000/0001-99",
        "email": "test_mt_phase2@example.com",
        "telefone": "11999999999",
    }
    r = requests.post(f"{BASE_URL}/api/mantenedoras", json=payload, headers=headers, timeout=30)
    if r.status_code not in (200, 201):
        # try minimal body
        r = requests.post(f"{BASE_URL}/api/mantenedoras",
                          json={"nome": "TEST_MT_PHASE2_TENANT"},
                          headers=headers, timeout=30)
    assert r.status_code in (200, 201), f"Could not create test mantenedora: {r.status_code} {r.text}"
    created = r.json()
    tid = created.get("id") or created.get("_id") or created.get("mantenedora_id")
    assert tid, f"No id in mantenedora response: {created}"
    yield tid
    # Cleanup
    try:
        requests.delete(f"{BASE_URL}/api/mantenedoras/{tid}", headers=headers, timeout=30)
    except Exception:
        pass


@pytest.fixture(scope="module")
def headers_t2(admin_token, secondary_tenant):
    return {"Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
            "X-Mantenedora-Id": secondary_tenant}


# ------------------------- REGRESSION (Phase 1 still passes) -------------------------

class TestRegression:
    def test_super_admin_login(self, headers):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=headers, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("role") == "super_admin"
        assert d.get("mantenedora_id") == ORIGINAL_TENANT

    def test_no_header_sees_all_schools(self, headers):
        r = requests.get(f"{BASE_URL}/api/schools", headers=headers, timeout=30)
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        assert len(items) >= 1, "Expected at least 1 school cross-tenant"

    def test_t1_header_sees_multisseriada(self, headers_t1):
        r = requests.get(f"{BASE_URL}/api/schools", headers=headers_t1, timeout=30)
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        names = [s.get("name") or s.get("nome") for s in items]
        assert any("MULTISSERIADA" in (n or "").upper() for n in names), \
            f"MULTISSERIADA missing from t1 listing: {names}"

    def test_classes_count_t1(self, headers_t1):
        r = requests.get(f"{BASE_URL}/api/classes", headers=headers_t1, timeout=30)
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        assert len(items) >= 6, f"Expected >=6 classes, got {len(items)}"

    def test_students_count_t1(self, headers_t1):
        r = requests.get(f"{BASE_URL}/api/students", headers=headers_t1, timeout=30)
        assert r.status_code == 200
        d = r.json()
        if isinstance(d, dict):
            total = d.get("total") or len(d.get("data", []) or d.get("items", []))
        else:
            total = len(d)
        assert total >= 9, f"Expected >=9 students, got {total}"

    def test_staff_count_t1(self, headers_t1):
        r = requests.get(f"{BASE_URL}/api/staff", headers=headers_t1, timeout=30)
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        assert len(items) >= 1, f"Expected >=1 staff, got {len(items)}"

    def test_courses_count_t1(self, headers_t1):
        r = requests.get(f"{BASE_URL}/api/courses", headers=headers_t1, timeout=30)
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        assert len(items) >= 18, f"Expected >=18 courses for t1, got {len(items)}"

    def test_enrollments_t1_2026(self, headers_t1):
        r = requests.get(f"{BASE_URL}/api/enrollments?academic_year=2026",
                         headers=headers_t1, timeout=30)
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        assert len(items) >= 40, f"Expected >=40 enrollments, got {len(items)}"


# ------------------------- TENANT SCOPING ON CREATE / READ -------------------------

class TestTenantScoping:
    def test_create_school_in_t2_persists_tenant(self, headers_t2, secondary_tenant):
        payload = {"name": "TEST_PHASE2_ESCOLA_T2"}
        r = requests.post(f"{BASE_URL}/api/schools", json=payload,
                          headers=headers_t2, timeout=30)
        assert r.status_code in (200, 201), f"POST /schools t2 failed: {r.status_code} {r.text}"
        created = r.json()
        sid = created.get("id")
        assert sid, f"No id in created school: {created}"
        # Persist sid for downstream tests
        pytest._t2_school_id = sid

        # Verify via MongoDB
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient

        async def _check():
            c = AsyncIOMotorClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
            db = c[os.environ.get('DB_NAME', 'sigesc')]
            return await db.schools.find_one({'id': sid})
        try:
            doc = asyncio.run(_check())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            doc = loop.run_until_complete(_check())
        assert doc is not None, "School not found in DB"
        assert doc.get('mantenedora_id') == secondary_tenant, \
            f"Expected mantenedora_id={secondary_tenant}, got {doc.get('mantenedora_id')}"

    def test_super_admin_no_header_sees_both(self, headers):
        r = requests.get(f"{BASE_URL}/api/schools", headers=headers, timeout=30)
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        names = [s.get("name") or s.get("nome") for s in items]
        assert any("MULTISSERIADA" in (n or "").upper() for n in names), \
            "MULTISSERIADA missing from cross-tenant listing"
        assert any("TEST_PHASE2_ESCOLA_T2" == n for n in names), \
            f"TEST_PHASE2_ESCOLA_T2 missing from cross-tenant listing: {names}"

    def test_super_admin_t1_header_excludes_t2_school(self, headers_t1):
        r = requests.get(f"{BASE_URL}/api/schools", headers=headers_t1, timeout=30)
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        names = [s.get("name") or s.get("nome") for s in items]
        assert not any("TEST_PHASE2_ESCOLA_T2" == n for n in names), \
            f"T1-scoped listing leaked T2 school: {names}"

    def test_super_admin_t2_header_only_sees_t2_schools(self, headers_t2):
        r = requests.get(f"{BASE_URL}/api/schools", headers=headers_t2, timeout=30)
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        names = [s.get("name") or s.get("nome") for s in items]
        assert any(n == "TEST_PHASE2_ESCOLA_T2" for n in names), \
            f"T2 school missing from t2-scoped listing: {names}"
        assert not any("MULTISSERIADA" in (n or "").upper() for n in names), \
            f"T2-scoped listing leaked T1 MULTISSERIADA: {names}"

    def test_cross_tenant_get_school_returns_403(self, headers_t1):
        # Try to GET the t2 school using t1 header → should be 403 (or 404 if assert_same_tenant excluded)
        sid = getattr(pytest, '_t2_school_id', None)
        if not sid:
            pytest.skip("No t2 school id")
        r = requests.get(f"{BASE_URL}/api/schools/{sid}", headers=headers_t1, timeout=30)
        assert r.status_code in (403, 404), \
            f"Expected 403/404 for cross-tenant GET, got {r.status_code}: {r.text}"

    def test_cross_tenant_put_school_returns_403(self, headers_t1):
        sid = getattr(pytest, '_t2_school_id', None)
        if not sid:
            pytest.skip("No t2 school id")
        r = requests.put(f"{BASE_URL}/api/schools/{sid}",
                         json={"name": "HACKED"},
                         headers=headers_t1, timeout=30)
        assert r.status_code in (403, 404), \
            f"Expected 403/404 for cross-tenant PUT, got {r.status_code}: {r.text}"

    def test_cross_tenant_delete_school_returns_403(self, headers_t1):
        sid = getattr(pytest, '_t2_school_id', None)
        if not sid:
            pytest.skip("No t2 school id")
        r = requests.delete(f"{BASE_URL}/api/schools/{sid}",
                            headers=headers_t1, timeout=30)
        assert r.status_code in (403, 404), \
            f"Expected 403/404 for cross-tenant DELETE, got {r.status_code}: {r.text}"


# ------------------------- T2 LISTINGS ARE EMPTY (NEW TENANT) -------------------------

class TestT2EmptyListings:
    def test_t2_classes_empty(self, headers_t2):
        r = requests.get(f"{BASE_URL}/api/classes", headers=headers_t2, timeout=30)
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        assert len(items) == 0, f"Expected 0 classes for new t2, got {len(items)}"

    def test_t2_students_empty(self, headers_t2):
        r = requests.get(f"{BASE_URL}/api/students", headers=headers_t2, timeout=30)
        assert r.status_code == 200
        d = r.json()
        if isinstance(d, dict):
            total = d.get("total") if d.get("total") is not None else len(d.get("data", []) or d.get("items", []))
        else:
            total = len(d)
        assert total == 0, f"Expected 0 students for new t2, got {total}"

    def test_t2_courses_empty(self, headers_t2):
        r = requests.get(f"{BASE_URL}/api/courses", headers=headers_t2, timeout=30)
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        assert len(items) == 0, f"Expected 0 courses for new t2, got {len(items)}"

    def test_t2_staff_empty(self, headers_t2):
        r = requests.get(f"{BASE_URL}/api/staff", headers=headers_t2, timeout=30)
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        assert len(items) == 0, f"Expected 0 staff for new t2, got {len(items)}"

    def test_t2_school_assignments_empty(self, headers_t2):
        r = requests.get(f"{BASE_URL}/api/school-assignments", headers=headers_t2, timeout=30)
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        assert len(items) == 0, f"Expected 0 school_assignments for new t2, got {len(items)}"

    def test_t2_teacher_assignments_empty(self, headers_t2):
        r = requests.get(f"{BASE_URL}/api/teacher-assignments", headers=headers_t2, timeout=30)
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        assert len(items) == 0, f"Expected 0 teacher_assignments for new t2, got {len(items)}"


# ------------------------- CLEANUP T2 SCHOOL -------------------------

class TestCleanup:
    def test_delete_t2_school(self, headers_t2):
        sid = getattr(pytest, '_t2_school_id', None)
        if not sid:
            pytest.skip("No t2 school id")
        r = requests.delete(f"{BASE_URL}/api/schools/{sid}",
                            headers=headers_t2, timeout=30)
        assert r.status_code in (200, 204), \
            f"DELETE t2 school failed: {r.status_code} {r.text}"
