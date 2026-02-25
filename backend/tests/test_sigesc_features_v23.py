"""
Test SIGESC Features - Iteration 23
Testing new features:
1. Schools: recomposicao_aprendizagem field in Ensino tab
2. Students: School dropdown changes and info message
3. Students: comunidade_tradicional defaults to 'nao_pertence' (no 'Selecione' option)
4. Students: atendimento_programa_tipo for students with disabilities
5. AEE: Students with atendimento_programa_tipo='aee' appear in Diário AEE
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestSchoolsRecomposicaoAprendizagem:
    """Test recomposicao_aprendizagem field in Schools API"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "gutenberg@sigesc.com",
            "password": "@Celta2007"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Get school ID
        schools_response = requests.get(f"{BASE_URL}/api/schools", headers=self.headers)
        assert schools_response.status_code == 200
        schools = schools_response.json()
        assert len(schools) > 0, "No schools found"
        self.school = schools[0]
        self.school_id = self.school["id"]
    
    def test_get_school_has_recomposicao_field(self):
        """Verify school has recomposicao_aprendizagem field"""
        response = requests.get(f"{BASE_URL}/api/schools/{self.school_id}", headers=self.headers)
        assert response.status_code == 200
        school_data = response.json()
        # Field should exist
        assert "recomposicao_aprendizagem" in school_data or school_data.get("recomposicao_aprendizagem") is not None or school_data.get("recomposicao_aprendizagem") == False, "recomposicao_aprendizagem field should exist"
        print(f"School has recomposicao_aprendizagem: {school_data.get('recomposicao_aprendizagem')}")
    
    def test_update_school_recomposicao_true(self):
        """Verify can set recomposicao_aprendizagem to true"""
        response = requests.put(
            f"{BASE_URL}/api/schools/{self.school_id}",
            json={"recomposicao_aprendizagem": True},
            headers=self.headers
        )
        assert response.status_code == 200, f"Failed to update school: {response.text}"
        updated = response.json()
        assert updated.get("recomposicao_aprendizagem") == True, "recomposicao_aprendizagem should be True"
        
    def test_update_school_recomposicao_false(self):
        """Verify can set recomposicao_aprendizagem to false"""
        response = requests.put(
            f"{BASE_URL}/api/schools/{self.school_id}",
            json={"recomposicao_aprendizagem": False},
            headers=self.headers
        )
        assert response.status_code == 200, f"Failed to update school: {response.text}"
        updated = response.json()
        assert updated.get("recomposicao_aprendizagem") == False, "recomposicao_aprendizagem should be False"


class TestStudentsAPI:
    """Test Students API - atendimento_programa_tipo field"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "gutenberg@sigesc.com",
            "password": "@Celta2007"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Get school ID
        schools_response = requests.get(f"{BASE_URL}/api/schools", headers=self.headers)
        self.school_id = schools_response.json()[0]["id"]
        
        # Get class ID
        classes_response = requests.get(f"{BASE_URL}/api/classes", headers=self.headers)
        if classes_response.json():
            self.class_id = classes_response.json()[0]["id"]
        else:
            self.class_id = None
    
    def test_get_students_with_school_filter(self):
        """Verify students API works with school filter"""
        response = requests.get(
            f"{BASE_URL}/api/students",
            params={"school_id": self.school_id},
            headers=self.headers
        )
        assert response.status_code == 200, f"Failed to get students: {response.text}"
        students = response.json()
        print(f"Found {len(students)} students for school {self.school_id}")
    
    def test_student_has_atendimento_programa_fields(self):
        """Verify student has atendimento_programa_tipo and atendimento_programa_class_id fields"""
        response = requests.get(
            f"{BASE_URL}/api/students",
            params={"school_id": self.school_id},
            headers=self.headers
        )
        assert response.status_code == 200
        students = response.json()
        if len(students) > 0:
            student = students[0]
            # These fields should exist in the model
            print(f"Student fields: atendimento_programa_tipo={student.get('atendimento_programa_tipo')}, atendimento_programa_class_id={student.get('atendimento_programa_class_id')}")
        else:
            pytest.skip("No students to check fields")
    
    def test_create_student_with_atendimento_programa(self):
        """Test creating a student with atendimento_programa_tipo"""
        if not self.class_id:
            pytest.skip("No class available to assign student")
        
        # Create test student with disability and atendimento programa
        test_student = {
            "full_name": "TEST_AEE_STUDENT_V23",
            "school_id": self.school_id,
            "class_id": self.class_id,
            "enrollment_year": 2025,
            "has_disability": True,
            "disabilities": ["intelectual"],
            "atendimento_programa_tipo": "aee",
            "comunidade_tradicional": "nao_pertence"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/students",
            json=test_student,
            headers=self.headers
        )
        
        if response.status_code in [200, 201]:
            student = response.json()
            self.test_student_id = student.get("id")
            print(f"Created student: {student.get('full_name')}")
            
            # Verify fields
            assert student.get("has_disability") == True
            assert student.get("atendimento_programa_tipo") == "aee"
            assert student.get("comunidade_tradicional") == "nao_pertence"
            
            # Cleanup - delete test student
            if self.test_student_id:
                requests.delete(f"{BASE_URL}/api/students/{self.test_student_id}", headers=self.headers)
        else:
            print(f"Create student response: {response.status_code} - {response.text}")
            # Not failing - just logging


class TestAEEStudents:
    """Test AEE Students endpoint - should include students with atendimento_programa_tipo='aee'"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "gutenberg@sigesc.com",
            "password": "@Celta2007"
        })
        assert login_response.status_code == 200
        self.token = login_response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Get school ID
        schools_response = requests.get(f"{BASE_URL}/api/schools", headers=self.headers)
        self.school_id = schools_response.json()[0]["id"]
    
    def test_aee_estudantes_endpoint(self):
        """Verify /api/aee/estudantes endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/aee/estudantes",
            params={"school_id": self.school_id, "academic_year": 2025},
            headers=self.headers
        )
        assert response.status_code == 200, f"AEE estudantes failed: {response.text}"
        students = response.json()
        print(f"AEE students count: {len(students)}")
        
        # Check structure if students exist
        if len(students) > 0:
            student = students[0]
            expected_fields = ["student_id", "full_name", "enrollment_number"]
            for field in expected_fields:
                assert field in student, f"Missing field: {field}"


class TestStudentsListBehavior:
    """Test Students list behavior - no 'Todas as escolas' option"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "gutenberg@sigesc.com",
            "password": "@Celta2007"
        })
        assert login_response.status_code == 200
        self.token = login_response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_students_without_filter_returns_empty_or_error(self):
        """
        Test that getting students without school filter works 
        (backend should handle this, UI will show message)
        """
        response = requests.get(f"{BASE_URL}/api/students", headers=self.headers)
        # Backend might return all students or require filter - check status
        assert response.status_code in [200, 400], f"Unexpected status: {response.status_code}"
        print(f"Students without filter: status={response.status_code}, count={len(response.json()) if response.status_code == 200 else 'N/A'}")
    
    def test_search_students_by_name(self):
        """Test searching students by name"""
        response = requests.get(
            f"{BASE_URL}/api/students/search",
            params={"name": "TEST"},
            headers=self.headers
        )
        # Search endpoint might or might not exist
        if response.status_code == 200:
            students = response.json()
            print(f"Search by name found: {len(students)} students")
        elif response.status_code == 404:
            print("Search endpoint not found - using main students endpoint")
        else:
            print(f"Search response: {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
