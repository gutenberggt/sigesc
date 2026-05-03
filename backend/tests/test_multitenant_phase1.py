"""
Multi-Tenant Phase 1 — Regression tests for super_admin (gutenberg@sigesc.com).

Validates that after migrating role 'admin' → 'super_admin', no core endpoint
returns 403 and that data is still visible cross-tenant.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://sigesc-docs.preview.emergentagent.com').rstrip('/')
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = os.getenv("SIGESC_TEST_ADMIN_PASSWORD", "@Celta2007")


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "access_token" in data or "token" in data, f"No token in response: {data}"
    token = data.get("access_token") or data.get("token")
    assert token
    return token


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# --------- AUTH ---------
class TestAuth:
    def test_login_returns_super_admin_with_mantenedora(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                          timeout=30)
        assert r.status_code == 200
        data = r.json()
        user = data.get("user") or {}
        assert user.get("role") == "super_admin", f"Expected super_admin, got {user.get('role')}"
        # mantenedora_id MUST be present on super_admin per request
        assert user.get("mantenedora_id"), f"mantenedora_id missing in login user: {user}"

    def test_auth_me_returns_super_admin_and_mantenedora(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers, timeout=30)
        assert r.status_code == 200, f"/auth/me failed: {r.status_code} {r.text}"
        data = r.json()
        assert data.get("role") == "super_admin"
        assert data.get("mantenedora_id"), f"mantenedora_id missing: {data}"


# --------- LISTING ENDPOINTS (must NOT 403) ---------
class TestListings:
    def test_schools_returns_data(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/schools", headers=auth_headers, timeout=30)
        assert r.status_code == 200, f"GET /schools failed: {r.status_code} {r.text}"
        data = r.json()
        # Could be list or {data:[]}
        items = data if isinstance(data, list) else (data.get("data") or data.get("schools") or [])
        assert len(items) > 0, f"Expected at least 1 school (ESCOLA TESTE MULTISSERIADA), got 0. Body={data}"
        names = [s.get("name") or s.get("nome") for s in items]
        assert any("MULTISSERIADA" in (n or "").upper() for n in names), \
            f"ESCOLA TESTE MULTISSERIADA not in list: {names}"

    def test_classes_returns_data(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/classes", headers=auth_headers, timeout=30)
        assert r.status_code == 200, f"GET /classes failed: {r.status_code} {r.text}"
        data = r.json()
        items = data if isinstance(data, list) else (data.get("data") or [])
        assert len(items) > 0, f"Expected classes for super_admin, got 0. Body keys={list(data.keys()) if isinstance(data, dict) else 'list'}"

    def test_students_paginated(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/students", headers=auth_headers, timeout=30)
        assert r.status_code == 200, f"GET /students failed: {r.status_code} {r.text}"
        data = r.json()
        if isinstance(data, dict):
            total = data.get("total")
            items = data.get("data") or data.get("items") or data.get("students") or []
            assert total is None or total > 0, f"Expected total>0, got {total}"
            assert len(items) > 0, f"Expected students, got 0. Body keys={list(data.keys())}"
        else:
            assert len(data) > 0, "Expected students list"

    def test_staff_returns_200(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/staff", headers=auth_headers, timeout=30)
        assert r.status_code == 200, f"GET /staff failed: {r.status_code} {r.text}"

    def test_courses_returns_200(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/courses", headers=auth_headers, timeout=30)
        assert r.status_code == 200, f"GET /courses failed: {r.status_code} {r.text}"

    def test_enrollments_2026(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/enrollments?academic_year=2026",
                         headers=auth_headers, timeout=30)
        assert r.status_code == 200, f"GET /enrollments?academic_year=2026 failed: {r.status_code} {r.text}"

    def test_mantenedoras_endpoint(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/mantenedoras", headers=auth_headers, timeout=30)
        assert r.status_code == 200, f"GET /mantenedoras failed (super_admin should see it): {r.status_code} {r.text}"
        data = r.json()
        items = data if isinstance(data, list) else (data.get("data") or [])
        assert len(items) > 0, f"Expected at least 1 mantenedora, got 0"

    def test_school_assignments_returns_200(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/school-assignments", headers=auth_headers, timeout=30)
        assert r.status_code == 200, f"GET /school-assignments failed: {r.status_code} {r.text}"

    def test_teacher_assignments_returns_200(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/teacher-assignments", headers=auth_headers, timeout=30)
        assert r.status_code == 200, f"GET /teacher-assignments failed: {r.status_code} {r.text}"


# --------- DIARY (grades, attendance, learning_objects, documents) ---------
class TestDiaryEndpoints:
    def test_grades_endpoint_no_403(self, auth_headers):
        # try a basic listing/filter — accept 200 or 422 (missing params), but NOT 403
        r = requests.get(f"{BASE_URL}/api/grades", headers=auth_headers, timeout=30)
        assert r.status_code != 403, f"/grades returned 403 for super_admin: {r.text}"

    def test_attendance_no_403(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/attendance", headers=auth_headers, timeout=30)
        assert r.status_code != 403, f"/attendance returned 403 for super_admin: {r.text}"

    def test_learning_objects_no_403(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/learning-objects", headers=auth_headers, timeout=30)
        # try alt path
        if r.status_code == 404:
            r = requests.get(f"{BASE_URL}/api/learning_objects", headers=auth_headers, timeout=30)
        assert r.status_code != 403, f"/learning-objects returned 403 for super_admin: {r.text}"

    def test_documents_no_403(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/documents", headers=auth_headers, timeout=30)
        assert r.status_code != 403, f"/documents returned 403 for super_admin: {r.text}"


# --------- TENANT INJECTION ---------
class TestTenantInjection:
    def test_create_school_injects_mantenedora_id(self, auth_headers):
        # super_admin must select a mantenedora context (header or query) to create a school
        # Get the user's own mantenedora_id
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers, timeout=30).json()
        mid = me.get("mantenedora_id")
        assert mid, f"super_admin missing mantenedora_id in /auth/me: {me}"
        scoped_headers = {**auth_headers, "X-Mantenedora-Id": mid}

        payload = {
            "name": "TEST_MULTITENANT_SCHOOL_PHASE1",
            "address": "Rua Teste 123",
            "phone": "999999999",
            "email": "test_mt@example.com"
        }
        r = requests.post(f"{BASE_URL}/api/schools", json=payload,
                          headers=scoped_headers, timeout=30)
        if r.status_code in (400, 422):
            payload2 = {"name": "TEST_MULTITENANT_SCHOOL_PHASE1"}
            r = requests.post(f"{BASE_URL}/api/schools", json=payload2,
                              headers=scoped_headers, timeout=30)
        assert r.status_code in (200, 201), f"POST /schools failed: {r.status_code} {r.text}"
        created = r.json()
        school_id = created.get("id") or created.get("_id")
        assert school_id, f"No id in created school: {created}"

        # GET to verify the school is fetchable
        r2 = requests.get(f"{BASE_URL}/api/schools/{school_id}", headers=scoped_headers, timeout=30)
        assert r2.status_code == 200, f"GET /schools/{school_id} failed: {r2.text}"
        fetched = r2.json()
        # NOTE: The School Pydantic response model does NOT expose 'mantenedora_id' field,
        # so we verify persistence directly via MongoDB instead of via API response.
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
        async def _check():
            c = AsyncIOMotorClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
            db = c[os.environ.get('DB_NAME', 'sigesc')]
            doc = await db.schools.find_one({'id': school_id})
            return doc
        doc = asyncio.get_event_loop().run_until_complete(_check()) if not asyncio.get_event_loop().is_running() else asyncio.run(_check())
        assert doc is not None, "School not found in DB"
        assert doc.get('mantenedora_id') == mid, \
            f"mantenedora_id NOT persisted correctly. Expected {mid}, got {doc.get('mantenedora_id')}"

        # Cleanup
        requests.delete(f"{BASE_URL}/api/schools/{school_id}", headers=scoped_headers, timeout=30)
