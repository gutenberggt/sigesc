"""Backend tests for GET /api/students/enrollment-audit (Auditoria de Matrículas)."""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://matricula-dedup.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = "@Celta2007"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=30)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    token = data.get("access_token") or data.get("token")
    assert token, f"No token in login response: {data}"
    return token


class TestEnrollmentAuditAuth:
    """Permissions for /api/students/enrollment-audit"""

    def test_requires_auth_no_token(self):
        r = requests.get(f"{BASE_URL}/api/students/enrollment-audit", timeout=20)
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code} {r.text[:200]}"

    def test_requires_auth_invalid_token(self):
        r = requests.get(f"{BASE_URL}/api/students/enrollment-audit",
                         headers={"Authorization": "Bearer invalid-token-xxx"},
                         timeout=20)
        assert r.status_code in (401, 403)


class TestEnrollmentAuditResponse:
    """Schema and behaviour of audit endpoint"""

    def test_admin_can_access(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/students/enrollment-audit",
                         headers={"Authorization": f"Bearer {admin_token}"},
                         timeout=60)
        assert r.status_code == 200, f"Got {r.status_code}: {r.text[:300]}"

    def test_response_schema(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/students/enrollment-audit",
                         headers={"Authorization": f"Bearer {admin_token}"},
                         timeout=60)
        assert r.status_code == 200
        data = r.json()
        # Top level keys
        for k in ("students", "enrollments", "owner_names", "unique_index"):
            assert k in data, f"Missing top-level key: {k}"

        # students sub-schema
        st = data["students"]
        for k in ("total", "empty", "duplicate_groups", "duplicates", "empty_sample"):
            assert k in st, f"Missing students.{k}"
        assert isinstance(st["total"], int)
        assert isinstance(st["empty"], int)
        assert isinstance(st["duplicate_groups"], int)
        assert isinstance(st["duplicates"], list)
        assert isinstance(st["empty_sample"], list)

        # enrollments sub-schema
        en = data["enrollments"]
        for k in ("total", "empty", "duplicate_groups", "duplicates"):
            assert k in en, f"Missing enrollments.{k}"
        assert isinstance(en["total"], int)
        assert isinstance(en["empty"], int)

        # unique index status
        ui = data["unique_index"]
        assert "students" in ui and "enrollments" in ui
        assert isinstance(ui["students"], bool)
        assert isinstance(ui["enrollments"], bool)

        # owner_names is a dict
        assert isinstance(data["owner_names"], dict)

    def test_unique_index_active(self, admin_token):
        """Spec says uq_enrollment_number must be ACTIVE on both collections."""
        r = requests.get(f"{BASE_URL}/api/students/enrollment-audit",
                         headers={"Authorization": f"Bearer {admin_token}"},
                         timeout=60)
        data = r.json()
        ui = data["unique_index"]
        assert ui["students"] is True, "Unique index uq_enrollment_number should be ACTIVE on students"
        assert ui["enrollments"] is True, "Unique index uq_enrollment_number should be ACTIVE on enrollments"

    def test_demo_empty_student_present(self, admin_token):
        """Spec inserted ALUNO DEMO AUDITORIA without enrollment_number — should appear."""
        r = requests.get(f"{BASE_URL}/api/students/enrollment-audit",
                         headers={"Authorization": f"Bearer {admin_token}"},
                         timeout=60)
        data = r.json()
        assert data["students"]["empty"] >= 1, (
            f"Expected at least 1 empty student (demo), got {data['students']['empty']}")
        names = [s.get("full_name", "") for s in data["students"]["empty_sample"]]
        assert any("ALUNO DEMO AUDITORIA" in (n or "") for n in names), (
            f"Demo student 'ALUNO DEMO AUDITORIA' not in empty_sample. Sample names: {names[:10]}")

    def test_no_mongo_objectid_in_payload(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/students/enrollment-audit",
                         headers={"Authorization": f"Bearer {admin_token}"},
                         timeout=60)
        # If _id leaks, the response often still parses OK but contains the key — check raw text
        assert '"_id"' not in r.text, "Response should not include MongoDB _id field"
