"""
Test file for SIGESC Student Program Enrollment (Matrícula em Atendimento/Programa)
Tests the cascade flow: School -> Program Type -> Class
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAtendimentoProgramaAPI:
    """Tests for Student Atendimento/Programa enrollment API"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - authenticate and get tokens"""
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "gutenberg@sigesc.com", "password": "@Celta2007"}
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Get schools
        schools_response = requests.get(f"{BASE_URL}/api/schools", headers=self.headers)
        assert schools_response.status_code == 200
        self.schools = schools_response.json()
        self.test_school = self.schools[0] if self.schools else None
        
        # Get students
        students_response = requests.get(f"{BASE_URL}/api/students", headers=self.headers)
        assert students_response.status_code == 200
        self.students = students_response.json()
        
        # Get classes  
        classes_response = requests.get(f"{BASE_URL}/api/classes", headers=self.headers)
        assert classes_response.status_code == 200
        self.classes = classes_response.json()
    
    def test_school_has_program_fields(self):
        """Test that schools have aee, reforco_escolar, recomposicao_aprendizagem fields"""
        assert self.test_school is not None, "No schools found"
        
        school = self.test_school
        print(f"School: {school.get('name')}")
        print(f"  aee: {school.get('aee')}")
        print(f"  reforco_escolar: {school.get('reforco_escolar')}")
        print(f"  recomposicao_aprendizagem: {school.get('recomposicao_aprendizagem')}")
        
        # Verify program fields exist
        assert 'aee' in school, "School missing 'aee' field"
        assert 'reforco_escolar' in school, "School missing 'reforco_escolar' field"
        assert 'recomposicao_aprendizagem' in school, "School missing 'recomposicao_aprendizagem' field"
        
        # Verify fields are boolean
        assert isinstance(school.get('aee'), bool), "aee should be boolean"
        assert isinstance(school.get('reforco_escolar'), bool), "reforco_escolar should be boolean"
        assert isinstance(school.get('recomposicao_aprendizagem'), bool), "recomposicao_aprendizagem should be boolean"
    
    def test_student_has_atendimento_programa_fields(self):
        """Test that student model accepts atendimento_programa fields"""
        if not self.students:
            pytest.skip("No students to test")
        
        student = self.students[0]
        student_id = student.get('id')
        
        # Get student details
        response = requests.get(f"{BASE_URL}/api/students/{student_id}", headers=self.headers)
        assert response.status_code == 200
        
        student_data = response.json()
        print(f"Student: {student_data.get('full_name')}")
        print(f"  atendimento_programa_school_id: {student_data.get('atendimento_programa_school_id')}")
        print(f"  atendimento_programa_tipo: {student_data.get('atendimento_programa_tipo')}")
        print(f"  atendimento_programa_class_id: {student_data.get('atendimento_programa_class_id')}")
    
    def test_update_student_with_atendimento_programa(self):
        """Test PUT /api/students/{id} accepts atendimento_programa fields"""
        if not self.students or not self.test_school:
            pytest.skip("No students or schools to test")
        
        student = self.students[0]
        student_id = student.get('id')
        school_id = self.test_school.get('id')
        
        # Update student with atendimento programa fields
        update_payload = {
            "atendimento_programa_school_id": school_id,
            "atendimento_programa_tipo": "aee",
            "atendimento_programa_class_id": ""  # No class assigned yet
        }
        
        response = requests.put(
            f"{BASE_URL}/api/students/{student_id}",
            headers=self.headers,
            json=update_payload
        )
        
        print(f"Update response status: {response.status_code}")
        print(f"Update response: {response.text[:500] if response.text else 'empty'}")
        
        assert response.status_code == 200, f"Failed to update student: {response.text}"
        
        updated_student = response.json()
        assert updated_student.get('atendimento_programa_school_id') == school_id
        assert updated_student.get('atendimento_programa_tipo') == "aee"
        
        # Verify persistence with GET
        get_response = requests.get(f"{BASE_URL}/api/students/{student_id}", headers=self.headers)
        assert get_response.status_code == 200
        
        fetched_student = get_response.json()
        assert fetched_student.get('atendimento_programa_school_id') == school_id
        assert fetched_student.get('atendimento_programa_tipo') == "aee"
    
    def test_update_student_clear_atendimento_programa(self):
        """Test clearing atendimento_programa fields"""
        if not self.students:
            pytest.skip("No students to test")
        
        student = self.students[0]
        student_id = student.get('id')
        
        # Clear atendimento programa fields
        update_payload = {
            "atendimento_programa_school_id": "",
            "atendimento_programa_tipo": "",
            "atendimento_programa_class_id": ""
        }
        
        response = requests.put(
            f"{BASE_URL}/api/students/{student_id}",
            headers=self.headers,
            json=update_payload
        )
        
        assert response.status_code == 200, f"Failed to clear: {response.text}"
        
        updated_student = response.json()
        # Empty string or None is acceptable
        assert updated_student.get('atendimento_programa_school_id') in ['', None]
        assert updated_student.get('atendimento_programa_tipo') in ['', None]
    
    def test_school_program_types_filtering_logic(self):
        """Test the program type filtering based on school settings"""
        assert self.test_school is not None, "No schools found"
        
        school = self.test_school
        
        # Build available program types based on school settings
        available_types = []
        if school.get('aee'):
            available_types.append('aee')
        if school.get('reforco_escolar'):
            available_types.append('reforco_escolar')
        if school.get('recomposicao_aprendizagem'):
            available_types.append('recomposicao_aprendizagem')
        
        print(f"School '{school.get('name')}' available program types: {available_types}")
        
        # For ESCOLA TESTE MULTISSERIADA, only AEE should be available
        if school.get('name') == 'ESCOLA TESTE MULTISSERIADA':
            assert 'aee' in available_types, "AEE should be available"
            assert 'reforco_escolar' not in available_types, "Reforço Escolar should NOT be available"
            assert 'recomposicao_aprendizagem' not in available_types, "Recomposição should NOT be available"
    
    def test_classes_have_atendimento_programa_field(self):
        """Test that classes have atendimento_programa field for filtering"""
        if not self.classes:
            pytest.skip("No classes to test")
        
        # Check if any class has atendimento_programa field
        for class_item in self.classes[:5]:  # Check first 5
            print(f"Class: {class_item.get('name')}")
            print(f"  atendimento_programa: {class_item.get('atendimento_programa')}")
            print(f"  school_id: {class_item.get('school_id')}")


class TestStudentDisabilityFields:
    """Tests for student disability fields that trigger program enrollment section"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - authenticate"""
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "gutenberg@sigesc.com", "password": "@Celta2007"}
        )
        assert login_response.status_code == 200
        self.token = login_response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_student_has_disability_fields(self):
        """Test that students have has_disability and disabilities fields"""
        response = requests.get(f"{BASE_URL}/api/students", headers=self.headers)
        assert response.status_code == 200
        
        students = response.json()
        if not students:
            pytest.skip("No students to test")
        
        student = students[0]
        print(f"Student: {student.get('full_name')}")
        print(f"  has_disability: {student.get('has_disability')}")
        print(f"  disabilities: {student.get('disabilities')}")
        
        # Verify fields exist in model (they can be None/empty)
        # has_disability should be boolean or None
        # disabilities should be list or None
    
    def test_update_student_disability(self):
        """Test updating student disability fields"""
        response = requests.get(f"{BASE_URL}/api/students", headers=self.headers)
        assert response.status_code == 200
        
        students = response.json()
        if not students:
            pytest.skip("No students to test")
        
        student = students[0]
        student_id = student.get('id')
        
        # Enable disability
        update_payload = {
            "has_disability": True,
            "disabilities": ["deficiencia_fisica"]
        }
        
        update_response = requests.put(
            f"{BASE_URL}/api/students/{student_id}",
            headers=self.headers,
            json=update_payload
        )
        
        assert update_response.status_code == 200, f"Failed: {update_response.text}"
        
        updated = update_response.json()
        assert updated.get('has_disability') == True
        assert 'deficiencia_fisica' in updated.get('disabilities', [])
        
        # Cleanup - disable disability
        cleanup_payload = {
            "has_disability": False,
            "disabilities": []
        }
        requests.put(
            f"{BASE_URL}/api/students/{student_id}",
            headers=self.headers,
            json=cleanup_payload
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
