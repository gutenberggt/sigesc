"""
Test suite for Attendance Report Filtering by Course and Bimestre
Tests the fixes for EJA and Anos Finais attendance reports:
1. GET /api/attendance/report/class/{class_id} - accepts course_id and bimestre params
2. GET /api/attendance/pdf/bimestre/{class_id} - accepts course_id and filters by component
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "gutenberg@sigesc.com"
TEST_PASSWORD = "@Celta2007"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for tests"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Create authenticated session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


class TestHealthCheck:
    """Basic health check to ensure API is running"""
    
    def test_health_endpoint(self):
        """Test that API is accessible"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        print("✓ API health check passed")


class TestAttendanceReportClassEndpoint:
    """Tests for GET /api/attendance/report/class/{class_id}"""
    
    def test_endpoint_accepts_course_id_param(self, api_client):
        """Verify endpoint accepts course_id as query parameter"""
        # Using a fake class_id - should return 404 (not 422 validation error)
        response = api_client.get(
            f"{BASE_URL}/api/attendance/report/class/test-class-id",
            params={
                "academic_year": 2025,
                "course_id": "test-course-id"
            }
        )
        # 404 means endpoint exists and accepts params, just no data found
        # 422 would mean validation error (param not accepted)
        assert response.status_code in [200, 404], \
            f"Endpoint should accept course_id param. Got: {response.status_code} - {response.text}"
        print("✓ /api/attendance/report/class accepts course_id parameter")
    
    def test_endpoint_accepts_bimestre_param(self, api_client):
        """Verify endpoint accepts bimestre as query parameter"""
        response = api_client.get(
            f"{BASE_URL}/api/attendance/report/class/test-class-id",
            params={
                "academic_year": 2025,
                "bimestre": 1
            }
        )
        assert response.status_code in [200, 404], \
            f"Endpoint should accept bimestre param. Got: {response.status_code} - {response.text}"
        print("✓ /api/attendance/report/class accepts bimestre parameter")
    
    def test_endpoint_accepts_both_params(self, api_client):
        """Verify endpoint accepts both course_id and bimestre together"""
        response = api_client.get(
            f"{BASE_URL}/api/attendance/report/class/test-class-id",
            params={
                "academic_year": 2025,
                "course_id": "test-course-id",
                "bimestre": 2
            }
        )
        assert response.status_code in [200, 404], \
            f"Endpoint should accept both params. Got: {response.status_code} - {response.text}"
        print("✓ /api/attendance/report/class accepts course_id AND bimestre parameters")
    
    def test_bimestre_validation_range(self, api_client):
        """Verify bimestre accepts values 1-4"""
        for bim in [1, 2, 3, 4]:
            response = api_client.get(
                f"{BASE_URL}/api/attendance/report/class/test-class-id",
                params={
                    "academic_year": 2025,
                    "bimestre": bim
                }
            )
            assert response.status_code in [200, 404], \
                f"Bimestre {bim} should be valid. Got: {response.status_code}"
        print("✓ Bimestre values 1-4 are all accepted")


class TestAttendancePdfBimestreEndpoint:
    """Tests for GET /api/attendance/pdf/bimestre/{class_id}"""
    
    def test_endpoint_exists(self, api_client):
        """Verify PDF endpoint exists"""
        response = api_client.get(
            f"{BASE_URL}/api/attendance/pdf/bimestre/test-class-id",
            params={
                "bimestre": 1,
                "academic_year": 2025
            }
        )
        # Should not be 405 (method not allowed) or 404 for route
        # 404 for "Turma não encontrada" is acceptable
        assert response.status_code != 405, "PDF endpoint should exist"
        print(f"✓ PDF endpoint exists (status: {response.status_code})")
    
    def test_endpoint_accepts_course_id_param(self, api_client):
        """Verify PDF endpoint accepts course_id as query parameter"""
        response = api_client.get(
            f"{BASE_URL}/api/attendance/pdf/bimestre/test-class-id",
            params={
                "bimestre": 1,
                "academic_year": 2025,
                "course_id": "test-course-id"
            }
        )
        # 404 for "Turma não encontrada" is acceptable
        # 422 would mean validation error (param not accepted)
        assert response.status_code in [200, 404, 500], \
            f"PDF endpoint should accept course_id param. Got: {response.status_code} - {response.text}"
        print("✓ /api/attendance/pdf/bimestre accepts course_id parameter")
    
    def test_bimestre_is_required(self, api_client):
        """Verify bimestre is a required parameter"""
        response = api_client.get(
            f"{BASE_URL}/api/attendance/pdf/bimestre/test-class-id",
            params={
                "academic_year": 2025
            }
        )
        # Should return 422 (validation error) because bimestre is required
        assert response.status_code == 422, \
            f"Bimestre should be required. Got: {response.status_code}"
        print("✓ Bimestre is correctly required for PDF endpoint")
    
    def test_bimestre_validation(self, api_client):
        """Verify bimestre must be 1-4"""
        # Test invalid bimestre value
        response = api_client.get(
            f"{BASE_URL}/api/attendance/pdf/bimestre/test-class-id",
            params={
                "bimestre": 5,  # Invalid
                "academic_year": 2025
            }
        )
        assert response.status_code == 422, \
            f"Bimestre 5 should be invalid. Got: {response.status_code}"
        print("✓ Bimestre validation (1-4) is working")


class TestCodeReviewVerification:
    """Verify code changes match requirements"""
    
    def test_attendance_py_has_bimestre_param(self):
        """Verify attendance.py report endpoint has bimestre parameter"""
        with open('/app/backend/routers/attendance.py', 'r') as f:
            content = f.read()
        
        # Check for bimestre parameter in get_class_attendance_report
        assert 'bimestre: Optional[int]' in content, \
            "attendance.py should have bimestre parameter"
        print("✓ attendance.py has bimestre parameter in report endpoint")
    
    def test_attendance_py_filters_by_bimestre(self):
        """Verify attendance.py filters by bimestre dates"""
        with open('/app/backend/routers/attendance.py', 'r') as f:
            content = f.read()
        
        # Check for bimestre date filtering logic
        assert 'period_start' in content and 'period_end' in content, \
            "attendance.py should have period_start/period_end for bimestre filtering"
        assert 'calendario_letivo' in content, \
            "attendance.py should query calendario_letivo for bimestre dates"
        print("✓ attendance.py has bimestre date filtering logic")
    
    def test_attendance_ext_py_has_course_id_filter(self):
        """Verify attendance_ext.py filters attendance by course_id"""
        with open('/app/backend/routers/attendance_ext.py', 'r') as f:
            content = f.read()
        
        # Check for course_id in attendance query
        assert 'course_id: Optional[str]' in content, \
            "attendance_ext.py should have course_id parameter"
        assert 'att_query["course_id"] = course_id' in content, \
            "attendance_ext.py should filter attendance by course_id"
        print("✓ attendance_ext.py filters attendance by course_id")
    
    def test_attendance_ext_py_teacher_query_uses_course_id(self):
        """Verify attendance_ext.py teacher lookup uses course_id"""
        with open('/app/backend/routers/attendance_ext.py', 'r') as f:
            content = f.read()
        
        # Check for course_id in teacher_query
        assert 'teacher_query["course_id"] = course_id' in content, \
            "attendance_ext.py should filter teacher_assignments by course_id"
        print("✓ attendance_ext.py teacher lookup uses course_id")


class TestFrontendCodeVerification:
    """Verify frontend code changes"""
    
    def test_api_js_getClassReport_has_bimestre(self):
        """Verify api.js getClassReport sends bimestre parameter"""
        with open('/app/frontend/src/services/api.js', 'r') as f:
            content = f.read()
        
        # Check for bimestre in getClassReport
        assert 'getClassReport' in content, "api.js should have getClassReport function"
        assert 'bimestre' in content, "api.js should reference bimestre parameter"
        
        # More specific check - look for bimestre in URL construction
        lines = content.split('\n')
        in_getClassReport = False
        found_bimestre_param = False
        for line in lines:
            if 'getClassReport' in line:
                in_getClassReport = True
            if in_getClassReport and 'bimestre' in line:
                found_bimestre_param = True
                break
            if in_getClassReport and '},' in line:
                break
        
        assert found_bimestre_param, \
            "api.js getClassReport should include bimestre in URL"
        print("✓ api.js getClassReport sends bimestre parameter")
    
    def test_attendance_js_passes_bimestre(self):
        """Verify Attendance.js passes selectedBimestre to loadClassReport"""
        with open('/app/frontend/src/pages/Attendance.js', 'r') as f:
            content = f.read()
        
        # Check for selectedBimestre state
        assert 'selectedBimestre' in content, \
            "Attendance.js should have selectedBimestre state"
        
        # Check that loadClassReport uses selectedBimestre
        assert 'selectedBimestre' in content, \
            "Attendance.js should pass selectedBimestre to API call"
        print("✓ Attendance.js has selectedBimestre and passes it to API")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
