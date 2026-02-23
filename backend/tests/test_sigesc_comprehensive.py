"""
SIGESC Comprehensive API Tests
Tests all main endpoints: schools, classes, students, users, staff, grades, attendance
"""
import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "gutenberg@sigesc.com"
TEST_PASSWORD = "@Celta2007"


@pytest.fixture(scope="session")
def auth_token():
    """Get authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=30
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    assert "access_token" in data
    return data["access_token"]


@pytest.fixture(scope="session")
def headers(auth_token):
    """Headers with authorization"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


class TestHealthAndAuth:
    """Health check and authentication tests"""
    
    def test_health_endpoint(self):
        """Test health endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=30)
        assert response.status_code == 200
        print("✓ Health endpoint working")
    
    def test_login_success(self):
        """Test login with valid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "user" in data
        assert data["user"]["email"] == TEST_EMAIL
        assert data["user"]["role"] == "admin"
        print("✓ Login successful")
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "invalid@test.com", "password": "wrongpass"},
            timeout=30
        )
        assert response.status_code in [401, 404]
        print("✓ Invalid login correctly rejected")
    
    def test_protected_endpoint_without_token(self):
        """Test protected endpoint returns 401 without token"""
        response = requests.get(f"{BASE_URL}/api/schools", timeout=30)
        assert response.status_code == 401
        print("✓ Protected endpoint requires authentication")


class TestSchoolsAPI:
    """Tests for /api/schools endpoint"""
    
    def test_get_all_schools(self, headers):
        """Test listing all schools"""
        response = requests.get(f"{BASE_URL}/api/schools", headers=headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/schools - Found {len(data)} schools")
        return data
    
    def test_get_school_by_id(self, headers):
        """Test getting a specific school by ID"""
        # First get all schools to get a valid ID
        schools = requests.get(f"{BASE_URL}/api/schools", headers=headers, timeout=30).json()
        if schools:
            school_id = schools[0]["id"]
            response = requests.get(f"{BASE_URL}/api/schools/{school_id}", headers=headers, timeout=30)
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == school_id
            print(f"✓ GET /api/schools/{school_id} - Found school: {data.get('name', 'N/A')}")
        else:
            pytest.skip("No schools to test")


class TestClassesAPI:
    """Tests for /api/classes endpoint"""
    
    def test_get_all_classes(self, headers):
        """Test listing all classes"""
        response = requests.get(f"{BASE_URL}/api/classes", headers=headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/classes - Found {len(data)} classes")
        return data
    
    def test_get_class_by_id(self, headers):
        """Test getting a specific class by ID"""
        classes = requests.get(f"{BASE_URL}/api/classes", headers=headers, timeout=30).json()
        if classes:
            class_id = classes[0]["id"]
            response = requests.get(f"{BASE_URL}/api/classes/{class_id}", headers=headers, timeout=30)
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == class_id
            print(f"✓ GET /api/classes/{class_id} - Found class: {data.get('name', 'N/A')}")
        else:
            pytest.skip("No classes to test")


class TestStudentsAPI:
    """Tests for /api/students endpoint"""
    
    def test_get_all_students(self, headers):
        """Test listing all students"""
        response = requests.get(f"{BASE_URL}/api/students", headers=headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/students - Found {len(data)} students")
        return data
    
    def test_get_student_by_id(self, headers):
        """Test getting a specific student by ID"""
        students = requests.get(f"{BASE_URL}/api/students", headers=headers, timeout=30).json()
        if students:
            student_id = students[0]["id"]
            response = requests.get(f"{BASE_URL}/api/students/{student_id}", headers=headers, timeout=30)
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == student_id
            print(f"✓ GET /api/students/{student_id} - Found student: {data.get('full_name', 'N/A')}")
        else:
            pytest.skip("No students to test")
    
    def test_search_students(self, headers):
        """Test searching students"""
        response = requests.get(
            f"{BASE_URL}/api/students/search?q=teste",
            headers=headers,
            timeout=30
        )
        # Should return 200 or 404 if no results
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            print(f"✓ GET /api/students/search - Found {len(data)} matching students")


class TestUsersAPI:
    """Tests for /api/users endpoint"""
    
    def test_get_all_users(self, headers):
        """Test listing all users"""
        response = requests.get(f"{BASE_URL}/api/users", headers=headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/users - Found {len(data)} users")
        return data
    
    def test_get_current_user(self, headers):
        """Test getting current user info"""
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == TEST_EMAIL
        print(f"✓ GET /api/auth/me - Current user: {data.get('full_name', data['email'])}")


class TestStaffAPI:
    """Tests for /api/staff endpoint"""
    
    def test_get_all_staff(self, headers):
        """Test listing all staff"""
        response = requests.get(f"{BASE_URL}/api/staff", headers=headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        # Staff endpoint may return list or object with items
        if isinstance(data, dict):
            items = data.get('items', [])
        else:
            items = data
        print(f"✓ GET /api/staff - Found {len(items)} staff members")


class TestCoursesAPI:
    """Tests for /api/courses endpoint (components)"""
    
    def test_get_all_courses(self, headers):
        """Test listing all courses/components"""
        response = requests.get(f"{BASE_URL}/api/courses", headers=headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/courses - Found {len(data)} courses/components")


class TestGradesAPI:
    """Tests for /api/grades endpoint"""
    
    def test_get_grades_for_class(self, headers):
        """Test getting grades for a class"""
        # First get a class
        classes = requests.get(f"{BASE_URL}/api/classes", headers=headers, timeout=30).json()
        if classes:
            class_id = classes[0]["id"]
            response = requests.get(
                f"{BASE_URL}/api/grades?class_id={class_id}",
                headers=headers,
                timeout=30
            )
            # Should return 200 even if empty
            assert response.status_code == 200
            print(f"✓ GET /api/grades?class_id={class_id} - Working")
        else:
            pytest.skip("No classes to test grades")


class TestAttendanceAPI:
    """Tests for /api/attendance endpoint"""
    
    def test_get_attendance_settings(self, headers):
        """Test getting attendance settings"""
        response = requests.get(f"{BASE_URL}/api/attendance/settings", headers=headers, timeout=30)
        # May return 200 or 404 if no settings
        assert response.status_code in [200, 404]
        print(f"✓ GET /api/attendance/settings - Status: {response.status_code}")


class TestEnrollmentsAPI:
    """Tests for /api/enrollments endpoint"""
    
    def test_get_all_enrollments(self, headers):
        """Test listing all enrollments"""
        response = requests.get(f"{BASE_URL}/api/enrollments", headers=headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/enrollments - Found {len(data)} enrollments")


class TestCalendarAPI:
    """Tests for /api/calendar endpoint"""
    
    def test_get_calendar_events(self, headers):
        """Test getting calendar events"""
        response = requests.get(f"{BASE_URL}/api/calendar", headers=headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/calendar - Found {len(data)} events")


class TestAnnouncementsAPI:
    """Tests for /api/announcements endpoint"""
    
    def test_get_all_announcements(self, headers):
        """Test listing all announcements"""
        response = requests.get(f"{BASE_URL}/api/announcements", headers=headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        print(f"✓ GET /api/announcements - Response received")


class TestGuardiansAPI:
    """Tests for /api/guardians endpoint"""
    
    def test_get_all_guardians(self, headers):
        """Test listing all guardians"""
        response = requests.get(f"{BASE_URL}/api/guardians", headers=headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/guardians - Found {len(data)} guardians")


class TestSchoolAssignmentsAPI:
    """Tests for /api/school-assignments endpoint"""
    
    def test_get_all_assignments(self, headers):
        """Test listing all school assignments"""
        response = requests.get(f"{BASE_URL}/api/school-assignments", headers=headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        print(f"✓ GET /api/school-assignments - Response received")


class TestTeacherAssignmentsAPI:
    """Tests for /api/teacher-assignments endpoint"""
    
    def test_get_all_teacher_assignments(self, headers):
        """Test listing all teacher assignments"""
        response = requests.get(f"{BASE_URL}/api/teacher-assignments", headers=headers, timeout=30)
        assert response.status_code == 200
        data = response.json()
        print(f"✓ GET /api/teacher-assignments - Response received")


class TestDiaryDashboardAPI:
    """Tests for /api/diary-dashboard endpoint"""
    
    def test_diary_dashboard_endpoint(self, headers):
        """Test diary dashboard endpoint"""
        response = requests.get(f"{BASE_URL}/api/diary-dashboard/stats", headers=headers, timeout=30)
        # May return 200 or 403 based on role
        assert response.status_code in [200, 403, 404]
        print(f"✓ GET /api/diary-dashboard/stats - Status: {response.status_code}")


class TestAnalyticsAPI:
    """Tests for /api/analytics endpoint"""
    
    def test_analytics_summary(self, headers):
        """Test analytics summary endpoint"""
        response = requests.get(f"{BASE_URL}/api/analytics/summary", headers=headers, timeout=30)
        assert response.status_code == 200
        print(f"✓ GET /api/analytics/summary - Response received")


class TestAuditAPI:
    """Tests for /api/audit endpoint"""
    
    def test_audit_logs(self, headers):
        """Test audit logs endpoint"""
        response = requests.get(f"{BASE_URL}/api/audit", headers=headers, timeout=30)
        # May return 200 or 403
        assert response.status_code in [200, 403]
        print(f"✓ GET /api/audit - Status: {response.status_code}")


class TestProfilesAPI:
    """Tests for /api/profiles endpoint"""
    
    def test_get_my_profile(self, headers):
        """Test getting own profile"""
        response = requests.get(f"{BASE_URL}/api/profiles/me", headers=headers, timeout=30)
        # May return 200 or 404 if no profile
        assert response.status_code in [200, 404]
        print(f"✓ GET /api/profiles/me - Status: {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
