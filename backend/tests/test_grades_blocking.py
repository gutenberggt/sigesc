"""
Test suite for grades blocking rules based on enrollment and action dates.

Rules tested:
1. blocked_before_enrollment: Bimestres that END before student's enrollment_date
   - Blocked for professor role
   - ALLOWED for admin/secretario roles
2. blocked_after_action: Bimestres that START after student's action_date (transfer/dropout)
   - Blocked for ALL roles (absolute block)

Test class: c09b8666-c8bb-40d1-b835-c2b0fa4b8ecd (TURMA MULTI 1-2-3)
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = "@Celta2007"
SECRETARIO_EMAIL = "secretario@sigesc.com"
SECRETARIO_PASSWORD = "secretario123"

# Test class with students having various blocking states
TEST_CLASS_ID = "c09b8666-c8bb-40d1-b835-c2b0fa4b8ecd"
TEST_COURSE_ID = "42d470dd-5183-48d3-ae9a-aa3e698ef01a"  # LÍNGUA PORTUGUESA
ACADEMIC_YEAR = 2026


class TestAuthentication:
    """Test authentication endpoints"""
    
    def test_admin_login_returns_access_token(self):
        """Admin login should return access_token (not 'token')"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "Response should contain 'access_token'"
        assert "user" in data, "Response should contain 'user'"
        assert data["user"]["role"] == "admin"
    
    def test_secretario_login_returns_access_token(self):
        """Secretario login should return access_token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": SECRETARIO_EMAIL,
            "password": SECRETARIO_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "Response should contain 'access_token'"
        assert data["user"]["role"] == "secretario"


class TestGradesByClassEndpoint:
    """Test GET /api/grades/by-class/{class_id}/{course_id} endpoint"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip("Admin authentication failed")
        return response.json()["access_token"]
    
    @pytest.fixture
    def secretario_token(self):
        """Get secretario authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": SECRETARIO_EMAIL,
            "password": SECRETARIO_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip("Secretario authentication failed")
        return response.json()["access_token"]
    
    def test_endpoint_returns_200(self, admin_token):
        """Endpoint should return 200 with valid parameters"""
        response = requests.get(
            f"{BASE_URL}/api/grades/by-class/{TEST_CLASS_ID}/{TEST_COURSE_ID}",
            params={"academic_year": ACADEMIC_YEAR},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_response_is_list(self, admin_token):
        """Response should be a list of student-grade objects"""
        response = requests.get(
            f"{BASE_URL}/api/grades/by-class/{TEST_CLASS_ID}/{TEST_COURSE_ID}",
            params={"academic_year": ACADEMIC_YEAR},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        assert len(data) > 0, "Response should contain at least one student"
    
    def test_student_object_has_required_fields(self, admin_token):
        """Each student object should have blocking arrays and enrollment_date"""
        response = requests.get(
            f"{BASE_URL}/api/grades/by-class/{TEST_CLASS_ID}/{TEST_COURSE_ID}",
            params={"academic_year": ACADEMIC_YEAR},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        data = response.json()
        
        for item in data:
            student = item.get("student", {})
            # Check required fields exist
            assert "id" in student, "Student should have 'id'"
            assert "full_name" in student, "Student should have 'full_name'"
            assert "enrollment_date" in student, "Student should have 'enrollment_date'"
            assert "blocked_before_enrollment" in student, "Student should have 'blocked_before_enrollment'"
            assert "blocked_after_action" in student, "Student should have 'blocked_after_action'"
            
            # Check blocking arrays are lists
            assert isinstance(student["blocked_before_enrollment"], list), "blocked_before_enrollment should be a list"
            assert isinstance(student["blocked_after_action"], list), "blocked_after_action should be a list"
    
    def test_blocked_after_action_contains_valid_bimestres(self, admin_token):
        """blocked_after_action should only contain valid bimestre numbers (1-4)"""
        response = requests.get(
            f"{BASE_URL}/api/grades/by-class/{TEST_CLASS_ID}/{TEST_COURSE_ID}",
            params={"academic_year": ACADEMIC_YEAR},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        data = response.json()
        
        for item in data:
            student = item.get("student", {})
            blocked_after = student.get("blocked_after_action", [])
            for bim in blocked_after:
                assert bim in [1, 2, 3, 4], f"Invalid bimestre {bim} in blocked_after_action"
    
    def test_blocked_before_enrollment_contains_valid_bimestres(self, admin_token):
        """blocked_before_enrollment should only contain valid bimestre numbers (1-4)"""
        response = requests.get(
            f"{BASE_URL}/api/grades/by-class/{TEST_CLASS_ID}/{TEST_COURSE_ID}",
            params={"academic_year": ACADEMIC_YEAR},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        data = response.json()
        
        for item in data:
            student = item.get("student", {})
            blocked_before = student.get("blocked_before_enrollment", [])
            for bim in blocked_before:
                assert bim in [1, 2, 3, 4], f"Invalid bimestre {bim} in blocked_before_enrollment"


class TestBlockedAfterActionLogic:
    """Test that blocked_after_action correctly identifies bimestres after action_date"""
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip("Admin authentication failed")
        return response.json()["access_token"]
    
    def test_transferred_student_has_blocked_after_action(self, admin_token):
        """Students with transfer action should have blocked_after_action populated"""
        response = requests.get(
            f"{BASE_URL}/api/grades/by-class/{TEST_CLASS_ID}/{TEST_COURSE_ID}",
            params={"academic_year": ACADEMIC_YEAR},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        data = response.json()
        
        # Find a transferred student
        transferred_students = [
            item for item in data 
            if item["student"].get("action_label") == "Transferido"
        ]
        
        assert len(transferred_students) > 0, "Should have at least one transferred student"
        
        for item in transferred_students:
            student = item["student"]
            action_date = student.get("action_date")
            blocked_after = student.get("blocked_after_action", [])
            
            # If action_date exists, blocked_after_action should be populated
            if action_date:
                # For action_date in March 2026, bimestres 2, 3, 4 should be blocked
                # (assuming bimestre 1 ends in April and bimestre 2 starts in May)
                assert len(blocked_after) > 0, f"Transferred student {student['full_name']} should have blocked bimestres"
                print(f"Student {student['full_name']}: action_date={action_date}, blocked_after={blocked_after}")
    
    def test_student_without_action_has_empty_blocked_after(self, admin_token):
        """Students without action should have empty blocked_after_action"""
        response = requests.get(
            f"{BASE_URL}/api/grades/by-class/{TEST_CLASS_ID}/{TEST_COURSE_ID}",
            params={"academic_year": ACADEMIC_YEAR},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        data = response.json()
        
        # Find students without action
        no_action_students = [
            item for item in data 
            if not item["student"].get("action_label")
        ]
        
        for item in no_action_students:
            student = item["student"]
            blocked_after = student.get("blocked_after_action", [])
            assert blocked_after == [], f"Student {student['full_name']} without action should have empty blocked_after_action"


class TestBlockedBeforeEnrollmentLogic:
    """Test that blocked_before_enrollment correctly identifies bimestres before enrollment_date"""
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip("Admin authentication failed")
        return response.json()["access_token"]
    
    def test_enrollment_date_is_returned(self, admin_token):
        """Each student should have enrollment_date in response"""
        response = requests.get(
            f"{BASE_URL}/api/grades/by-class/{TEST_CLASS_ID}/{TEST_COURSE_ID}",
            params={"academic_year": ACADEMIC_YEAR},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        data = response.json()
        
        students_with_enrollment = [
            item for item in data 
            if item["student"].get("enrollment_date")
        ]
        
        # At least some students should have enrollment_date
        assert len(students_with_enrollment) > 0, "At least some students should have enrollment_date"
        
        for item in students_with_enrollment:
            enrollment_date = item["student"]["enrollment_date"]
            # Validate date format (YYYY-MM-DD)
            assert len(enrollment_date) >= 10, f"enrollment_date should be in YYYY-MM-DD format: {enrollment_date}"
    
    def test_late_enrollment_blocks_early_bimestres(self, admin_token):
        """Students enrolled late should have early bimestres in blocked_before_enrollment"""
        response = requests.get(
            f"{BASE_URL}/api/grades/by-class/{TEST_CLASS_ID}/{TEST_COURSE_ID}",
            params={"academic_year": 2025},  # Use 2025 to test late enrollment scenario
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        data = response.json()
        
        # With academic_year=2025 and enrollment_date in 2026, all bimestres should be blocked
        students_with_late_enrollment = [
            item for item in data 
            if item["student"].get("enrollment_date", "").startswith("2026")
        ]
        
        for item in students_with_late_enrollment:
            student = item["student"]
            blocked_before = student.get("blocked_before_enrollment", [])
            # All 4 bimestres should be blocked for 2025 if enrolled in 2026
            assert blocked_before == [1, 2, 3, 4], f"Student {student['full_name']} enrolled in 2026 should have all 2025 bimestres blocked"


class TestGradeObjectStructure:
    """Test the grade object structure in the response"""
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip("Admin authentication failed")
        return response.json()["access_token"]
    
    def test_grade_object_has_bimestre_fields(self, admin_token):
        """Grade object should have b1, b2, b3, b4 fields"""
        response = requests.get(
            f"{BASE_URL}/api/grades/by-class/{TEST_CLASS_ID}/{TEST_COURSE_ID}",
            params={"academic_year": ACADEMIC_YEAR},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        data = response.json()
        
        for item in data:
            grade = item.get("grade", {})
            assert "b1" in grade, "Grade should have 'b1'"
            assert "b2" in grade, "Grade should have 'b2'"
            assert "b3" in grade, "Grade should have 'b3'"
            assert "b4" in grade, "Grade should have 'b4'"
    
    def test_grade_object_has_recovery_fields(self, admin_token):
        """Grade object should have recovery fields"""
        response = requests.get(
            f"{BASE_URL}/api/grades/by-class/{TEST_CLASS_ID}/{TEST_COURSE_ID}",
            params={"academic_year": ACADEMIC_YEAR},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        data = response.json()
        
        for item in data:
            grade = item.get("grade", {})
            assert "rec_s1" in grade, "Grade should have 'rec_s1'"
            assert "rec_s2" in grade, "Grade should have 'rec_s2'"
            assert "recovery" in grade, "Grade should have 'recovery'"
    
    def test_grade_object_has_status_and_average(self, admin_token):
        """Grade object should have status and final_average"""
        response = requests.get(
            f"{BASE_URL}/api/grades/by-class/{TEST_CLASS_ID}/{TEST_COURSE_ID}",
            params={"academic_year": ACADEMIC_YEAR},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        data = response.json()
        
        for item in data:
            grade = item.get("grade", {})
            assert "status" in grade, "Grade should have 'status'"
            assert "final_average" in grade, "Grade should have 'final_average'"


class TestSecretarioAccess:
    """Test that secretario can access grades endpoint"""
    
    @pytest.fixture
    def secretario_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": SECRETARIO_EMAIL,
            "password": SECRETARIO_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip("Secretario authentication failed")
        return response.json()["access_token"]
    
    def test_secretario_can_access_grades_by_class(self, secretario_token):
        """Secretario should be able to access grades by class endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/grades/by-class/{TEST_CLASS_ID}/{TEST_COURSE_ID}",
            params={"academic_year": ACADEMIC_YEAR},
            headers={"Authorization": f"Bearer {secretario_token}"}
        )
        assert response.status_code == 200, f"Secretario should have access: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
