"""
Test suite for Multi-Grade (Turmas Multisseriadas) feature
Tests the backend models and API endpoints for:
1. Class model with is_multi_grade and series fields
2. Enrollment model with student_series field
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "gutenberg@sigesc.com"
TEST_PASSWORD = "@Celta2007"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Shared requests session with auth"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


@pytest.fixture(scope="module")
def test_school(api_client):
    """Create a test school for multi-grade testing"""
    school_data = {
        "name": f"TEST_Escola_MultiGrade_{uuid.uuid4().hex[:8]}",
        "inep_code": "12345678",
        "status": "active",
        # Enable education levels with multiple grades
        "fundamental_anos_iniciais": True,
        "fundamental_inicial_1ano": True,
        "fundamental_inicial_2ano": True,
        "fundamental_inicial_3ano": True,
        "fundamental_inicial_4ano": True,
        "fundamental_inicial_5ano": True
    }
    
    response = api_client.post(f"{BASE_URL}/api/schools", json=school_data)
    assert response.status_code in [200, 201], f"Failed to create school: {response.text}"
    
    school = response.json()
    yield school
    
    # Cleanup
    try:
        api_client.delete(f"{BASE_URL}/api/schools/{school['id']}")
    except:
        pass


class TestClassMultiGradeModel:
    """Test Class model with multi-grade fields"""
    
    def test_create_regular_class(self, api_client, test_school):
        """Test creating a regular (non-multi-grade) class"""
        class_data = {
            "school_id": test_school["id"],
            "academic_year": 2025,
            "name": f"TEST_Turma_Regular_{uuid.uuid4().hex[:6]}",
            "shift": "morning",
            "education_level": "fundamental_anos_iniciais",
            "grade_level": "1º Ano",
            "is_multi_grade": False,
            "series": []
        }
        
        response = api_client.post(f"{BASE_URL}/api/classes", json=class_data)
        assert response.status_code in [200, 201], f"Failed to create class: {response.text}"
        
        created_class = response.json()
        assert created_class["is_multi_grade"] == False
        assert created_class["series"] == []
        assert created_class["grade_level"] == "1º Ano"
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/classes/{created_class['id']}")
    
    def test_create_multi_grade_class(self, api_client, test_school):
        """Test creating a multi-grade class with multiple series"""
        class_data = {
            "school_id": test_school["id"],
            "academic_year": 2025,
            "name": f"TEST_Turma_Multi_{uuid.uuid4().hex[:6]}",
            "shift": "morning",
            "education_level": "fundamental_anos_iniciais",
            "grade_level": "1º Ano",  # Primary grade
            "is_multi_grade": True,
            "series": ["1º Ano", "2º Ano", "3º Ano"]
        }
        
        response = api_client.post(f"{BASE_URL}/api/classes", json=class_data)
        assert response.status_code in [200, 201], f"Failed to create multi-grade class: {response.text}"
        
        created_class = response.json()
        assert created_class["is_multi_grade"] == True
        assert created_class["series"] == ["1º Ano", "2º Ano", "3º Ano"]
        assert len(created_class["series"]) == 3
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/classes/{created_class['id']}")
    
    def test_update_class_to_multi_grade(self, api_client, test_school):
        """Test updating a regular class to multi-grade"""
        # Create regular class first
        class_data = {
            "school_id": test_school["id"],
            "academic_year": 2025,
            "name": f"TEST_Turma_Update_{uuid.uuid4().hex[:6]}",
            "shift": "afternoon",
            "education_level": "fundamental_anos_iniciais",
            "grade_level": "2º Ano",
            "is_multi_grade": False,
            "series": []
        }
        
        response = api_client.post(f"{BASE_URL}/api/classes", json=class_data)
        assert response.status_code in [200, 201]
        created_class = response.json()
        
        # Update to multi-grade
        update_data = {
            "is_multi_grade": True,
            "series": ["2º Ano", "3º Ano"]
        }
        
        update_response = api_client.put(
            f"{BASE_URL}/api/classes/{created_class['id']}", 
            json=update_data
        )
        assert update_response.status_code == 200, f"Failed to update class: {update_response.text}"
        
        updated_class = update_response.json()
        assert updated_class["is_multi_grade"] == True
        assert updated_class["series"] == ["2º Ano", "3º Ano"]
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/classes/{created_class['id']}")
    
    def test_get_class_with_multi_grade_fields(self, api_client, test_school):
        """Test that GET returns multi-grade fields correctly"""
        # Create multi-grade class
        class_data = {
            "school_id": test_school["id"],
            "academic_year": 2025,
            "name": f"TEST_Turma_Get_{uuid.uuid4().hex[:6]}",
            "shift": "morning",
            "education_level": "fundamental_anos_iniciais",
            "grade_level": "1º Ano",
            "is_multi_grade": True,
            "series": ["1º Ano", "2º Ano"]
        }
        
        create_response = api_client.post(f"{BASE_URL}/api/classes", json=class_data)
        assert create_response.status_code in [200, 201]
        created_class = create_response.json()
        
        # GET the class
        get_response = api_client.get(f"{BASE_URL}/api/classes/{created_class['id']}")
        assert get_response.status_code == 200
        
        fetched_class = get_response.json()
        assert "is_multi_grade" in fetched_class
        assert "series" in fetched_class
        assert fetched_class["is_multi_grade"] == True
        assert fetched_class["series"] == ["1º Ano", "2º Ano"]
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/classes/{created_class['id']}")


class TestEnrollmentStudentSeries:
    """Test Enrollment model with student_series field"""
    
    @pytest.fixture
    def test_student(self, api_client, test_school):
        """Create a test student"""
        student_data = {
            "school_id": test_school["id"],
            "enrollment_number": f"TEST_{uuid.uuid4().hex[:8]}",
            "full_name": f"TEST_Aluno_Multi_{uuid.uuid4().hex[:6]}",
            "status": "active"
        }
        
        response = api_client.post(f"{BASE_URL}/api/students", json=student_data)
        assert response.status_code in [200, 201], f"Failed to create student: {response.text}"
        
        student = response.json()
        yield student
        
        # Cleanup
        try:
            api_client.delete(f"{BASE_URL}/api/students/{student['id']}")
        except:
            pass
    
    @pytest.fixture
    def multi_grade_class(self, api_client, test_school):
        """Create a multi-grade class for enrollment testing"""
        class_data = {
            "school_id": test_school["id"],
            "academic_year": 2025,
            "name": f"TEST_Turma_Enroll_{uuid.uuid4().hex[:6]}",
            "shift": "morning",
            "education_level": "fundamental_anos_iniciais",
            "grade_level": "1º Ano",
            "is_multi_grade": True,
            "series": ["1º Ano", "2º Ano", "3º Ano"]
        }
        
        response = api_client.post(f"{BASE_URL}/api/classes", json=class_data)
        assert response.status_code in [200, 201]
        
        created_class = response.json()
        yield created_class
        
        # Cleanup
        try:
            api_client.delete(f"{BASE_URL}/api/classes/{created_class['id']}")
        except:
            pass
    
    def test_create_enrollment_with_student_series(self, api_client, test_school, test_student, multi_grade_class):
        """Test creating enrollment with student_series for multi-grade class"""
        enrollment_data = {
            "student_id": test_student["id"],
            "school_id": test_school["id"],
            "class_id": multi_grade_class["id"],
            "academic_year": 2025,
            "student_series": "2º Ano",  # Student is in 2nd grade within multi-grade class
            "status": "active"
        }
        
        response = api_client.post(f"{BASE_URL}/api/enrollments", json=enrollment_data)
        assert response.status_code in [200, 201], f"Failed to create enrollment: {response.text}"
        
        enrollment = response.json()
        assert enrollment["student_series"] == "2º Ano"
        assert enrollment["class_id"] == multi_grade_class["id"]
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/enrollments/{enrollment['id']}")
    
    def test_enrollment_without_student_series(self, api_client, test_school, test_student, multi_grade_class):
        """Test that enrollment can be created without student_series (optional field)"""
        enrollment_data = {
            "student_id": test_student["id"],
            "school_id": test_school["id"],
            "class_id": multi_grade_class["id"],
            "academic_year": 2025,
            "status": "active"
            # student_series not provided
        }
        
        response = api_client.post(f"{BASE_URL}/api/enrollments", json=enrollment_data)
        assert response.status_code in [200, 201], f"Failed to create enrollment: {response.text}"
        
        enrollment = response.json()
        # student_series should be None or empty
        assert enrollment.get("student_series") is None or enrollment.get("student_series") == ""
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/enrollments/{enrollment['id']}")


class TestClassListWithMultiGrade:
    """Test listing classes with multi-grade information"""
    
    def test_list_classes_includes_multi_grade_fields(self, api_client, test_school):
        """Test that class list includes is_multi_grade and series fields"""
        # Create a multi-grade class
        class_data = {
            "school_id": test_school["id"],
            "academic_year": 2025,
            "name": f"TEST_Turma_List_{uuid.uuid4().hex[:6]}",
            "shift": "morning",
            "education_level": "fundamental_anos_iniciais",
            "grade_level": "1º Ano",
            "is_multi_grade": True,
            "series": ["1º Ano", "2º Ano"]
        }
        
        create_response = api_client.post(f"{BASE_URL}/api/classes", json=class_data)
        assert create_response.status_code in [200, 201]
        created_class = create_response.json()
        
        # List classes
        list_response = api_client.get(f"{BASE_URL}/api/classes")
        assert list_response.status_code == 200
        
        classes = list_response.json()
        
        # Find our test class
        test_class = next((c for c in classes if c["id"] == created_class["id"]), None)
        assert test_class is not None, "Test class not found in list"
        
        # Verify multi-grade fields are present
        assert "is_multi_grade" in test_class
        assert "series" in test_class
        assert test_class["is_multi_grade"] == True
        assert test_class["series"] == ["1º Ano", "2º Ano"]
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/classes/{created_class['id']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
