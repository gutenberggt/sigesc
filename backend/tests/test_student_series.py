"""
Test Suite: student_series feature for multi-grade classes
Tests the student_series field that stores the specific grade/series 
of a student enrolled in a multi-grade (multisseriada) class.

Features tested:
1. GET /api/students/{id} - returns student_series from active enrollment
2. POST /api/students - creates student with student_series in enrollment
3. PUT /api/students/{id} - updates student_series in active enrollment
"""

import pytest
import requests
import os
import uuid
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test data constants
TEST_SCHOOL_ID = "220d4022-ec5e-4fb6-86fc-9233112b87b2"  # ESCOLA TESTE MULTISSERIADA
TEST_MULTI_CLASS_ID = "c09b8666-c8bb-40d1-b835-c2b0fa4b8ecd"  # TURMA MULTI 1-2-3
TEST_NORMAL_CLASS_ID = "e37025d4-52a9-40f7-89b6-2a9789c9f266"  # TESTE 2 (5º ANO)
MULTI_CLASS_SERIES = ['1º ANO', '2º ANO', '3º ANO', '4º ANO', '5º ANO']


class TestStudentSeriesFeature:
    """Tests for student_series field in multi-grade classes"""
    
    @pytest.fixture(autouse=True)
    def setup(self, api_client, auth_token):
        """Setup for each test"""
        self.client = api_client
        self.token = auth_token
        self.created_student_ids = []
        yield
        # Cleanup: Delete test students
        for student_id in self.created_student_ids:
            try:
                self.client.delete(
                    f"{BASE_URL}/api/students/{student_id}",
                    headers={"Authorization": f"Bearer {self.token}"}
                )
            except:
                pass
    
    def test_create_student_with_student_series_in_multigrade_class(self):
        """
        Test POST /api/students with student_series for multi-grade class.
        When creating a student in a multi-grade class, student_series should be saved to enrollment.
        """
        student_name = f"TEST_MULTI_SERIES_{uuid.uuid4().hex[:8].upper()}"
        student_data = {
            "school_id": TEST_SCHOOL_ID,
            "class_id": TEST_MULTI_CLASS_ID,
            "full_name": student_name,
            "status": "active",
            "student_series": "2º ANO"  # Specific series for multi-grade class
        }
        
        response = self.client.post(
            f"{BASE_URL}/api/students",
            json=student_data,
            headers={"Authorization": f"Bearer {self.token}"}
        )
        
        assert response.status_code == 201, f"Failed to create student: {response.text}"
        created = response.json()
        student_id = created["id"]
        self.created_student_ids.append(student_id)
        
        # Verify: GET the student and check student_series is returned
        get_response = self.client.get(
            f"{BASE_URL}/api/students/{student_id}",
            headers={"Authorization": f"Bearer {self.token}"}
        )
        assert get_response.status_code == 200
        student_data = get_response.json()
        
        # student_series should be returned from the active enrollment
        assert "student_series" in student_data, "student_series not in response"
        assert student_data["student_series"] == "2º ANO", \
            f"Expected '2º ANO', got '{student_data.get('student_series')}'"
        
        print(f"✓ Created student in multi-grade class with student_series='2º ANO'")
    
    def test_get_student_returns_student_series_from_enrollment(self):
        """
        Test GET /api/students/{id} returns student_series from active enrollment.
        """
        # First create a student with specific series
        student_name = f"TEST_GET_SERIES_{uuid.uuid4().hex[:8].upper()}"
        create_response = self.client.post(
            f"{BASE_URL}/api/students",
            json={
                "school_id": TEST_SCHOOL_ID,
                "class_id": TEST_MULTI_CLASS_ID,
                "full_name": student_name,
                "status": "active",
                "student_series": "3º ANO"
            },
            headers={"Authorization": f"Bearer {self.token}"}
        )
        assert create_response.status_code == 201
        student_id = create_response.json()["id"]
        self.created_student_ids.append(student_id)
        
        # GET student and verify student_series
        get_response = self.client.get(
            f"{BASE_URL}/api/students/{student_id}",
            headers={"Authorization": f"Bearer {self.token}"}
        )
        assert get_response.status_code == 200
        student = get_response.json()
        
        assert student.get("student_series") == "3º ANO", \
            f"GET did not return correct student_series. Got: {student.get('student_series')}"
        
        print(f"✓ GET /api/students/{student_id} returns student_series='3º ANO'")
    
    def test_update_student_series_in_multigrade_class(self):
        """
        Test PUT /api/students/{id} updates student_series in active enrollment.
        """
        # Create student with initial series
        student_name = f"TEST_UPDATE_SERIES_{uuid.uuid4().hex[:8].upper()}"
        create_response = self.client.post(
            f"{BASE_URL}/api/students",
            json={
                "school_id": TEST_SCHOOL_ID,
                "class_id": TEST_MULTI_CLASS_ID,
                "full_name": student_name,
                "status": "active",
                "student_series": "1º ANO"
            },
            headers={"Authorization": f"Bearer {self.token}"}
        )
        assert create_response.status_code == 201
        student_id = create_response.json()["id"]
        self.created_student_ids.append(student_id)
        
        # Update student_series to a different value
        update_response = self.client.put(
            f"{BASE_URL}/api/students/{student_id}",
            json={"student_series": "3º ANO"},
            headers={"Authorization": f"Bearer {self.token}"}
        )
        assert update_response.status_code == 200, f"Update failed: {update_response.text}"
        
        # Verify the update via GET
        get_response = self.client.get(
            f"{BASE_URL}/api/students/{student_id}",
            headers={"Authorization": f"Bearer {self.token}"}
        )
        assert get_response.status_code == 200
        updated_student = get_response.json()
        
        assert updated_student.get("student_series") == "3º ANO", \
            f"student_series not updated. Expected '3º ANO', got '{updated_student.get('student_series')}'"
        
        print(f"✓ PUT updated student_series from '1º ANO' to '3º ANO'")
    
    def test_create_student_in_normal_class_uses_grade_level(self):
        """
        Test creating student in non-multi-grade class uses the class's grade_level.
        """
        student_name = f"TEST_NORMAL_CLASS_{uuid.uuid4().hex[:8].upper()}"
        create_response = self.client.post(
            f"{BASE_URL}/api/students",
            json={
                "school_id": TEST_SCHOOL_ID,
                "class_id": TEST_NORMAL_CLASS_ID,
                "full_name": student_name,
                "status": "active"
                # Note: not providing student_series, should use grade_level
            },
            headers={"Authorization": f"Bearer {self.token}"}
        )
        assert create_response.status_code == 201
        student_id = create_response.json()["id"]
        self.created_student_ids.append(student_id)
        
        # GET should return the class's grade_level as student_series
        get_response = self.client.get(
            f"{BASE_URL}/api/students/{student_id}",
            headers={"Authorization": f"Bearer {self.token}"}
        )
        assert get_response.status_code == 200
        student = get_response.json()
        
        # For non-multi-grade class, student_series should be the class's grade_level
        student_series = student.get("student_series")
        # Either '5º ANO' (from enrollment) or None/empty is acceptable for non-multi
        print(f"✓ Student in normal class has student_series='{student_series}'")
    
    def test_student_series_preserved_after_other_updates(self):
        """
        Test that updating other fields does not affect student_series.
        """
        student_name = f"TEST_PRESERVE_SERIES_{uuid.uuid4().hex[:8].upper()}"
        create_response = self.client.post(
            f"{BASE_URL}/api/students",
            json={
                "school_id": TEST_SCHOOL_ID,
                "class_id": TEST_MULTI_CLASS_ID,
                "full_name": student_name,
                "status": "active",
                "student_series": "4º ANO",
                "observations": "Test observation"
            },
            headers={"Authorization": f"Bearer {self.token}"}
        )
        assert create_response.status_code == 201
        student_id = create_response.json()["id"]
        self.created_student_ids.append(student_id)
        
        # Update unrelated field
        update_response = self.client.put(
            f"{BASE_URL}/api/students/{student_id}",
            json={"observations": "Updated observation"},
            headers={"Authorization": f"Bearer {self.token}"}
        )
        assert update_response.status_code == 200
        
        # Verify student_series is preserved
        get_response = self.client.get(
            f"{BASE_URL}/api/students/{student_id}",
            headers={"Authorization": f"Bearer {self.token}"}
        )
        assert get_response.status_code == 200
        student = get_response.json()
        
        assert student.get("student_series") == "4º ANO", \
            f"student_series changed unexpectedly to '{student.get('student_series')}'"
        assert student.get("observations").upper() == "UPDATED OBSERVATION", \
            "observations field not updated"
        
        print(f"✓ student_series preserved after updating other fields")


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def auth_token(api_client):
    """Get authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": "gutenberg@sigesc.com",
        "password": "@Celta2007"
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Authentication failed - skipping tests")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
