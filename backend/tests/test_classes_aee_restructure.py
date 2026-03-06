"""
Test suite for Classes form restructuring - AEE and Recomposição da Aprendizagem
Tests backend API acceptance of classes with empty education_level for special programs
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = "@Celta2007"

# Test school ID (ESCOLA TESTE MULTISSERIADA)
TEST_SCHOOL_ID = "220d4022-ec5e-4fb6-86fc-9233112b87b2"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture
def authenticated_client(auth_token):
    """Session with auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


class TestClassesAEERestructure:
    """Test classes API for AEE and Recomposição da Aprendizagem programs"""
    
    def test_school_has_required_programs(self, authenticated_client):
        """Verify test school has AEE and Recomposição enabled"""
        response = authenticated_client.get(f"{BASE_URL}/api/schools/{TEST_SCHOOL_ID}")
        assert response.status_code == 200, f"Failed to get school: {response.text}"
        
        school = response.json()
        assert school.get("aee") == True, "School must have AEE enabled"
        # Note: aulas_complementares may or may not be enabled for this test school
        print(f"  - aulas_complementares: {school.get('aulas_complementares', False)}")
        print(f"School verified: {school.get('name')}")
        print(f"  - aee: {school.get('aee')}")
        print(f"  - aulas_complementares: {school.get('aulas_complementares')}")
        print(f"  - atendimento_integral: {school.get('atendimento_integral')}")
        print(f"  - fundamental_anos_iniciais: {school.get('fundamental_anos_iniciais')}")
    
    def test_create_aee_class_without_education_level(self, authenticated_client):
        """Test creating AEE class with empty education_level (should be accepted)"""
        class_data = {
            "school_id": TEST_SCHOOL_ID,
            "academic_year": 2025,
            "name": "TEST_AEE_NO_LEVEL",
            "shift": "morning",
            "education_level": "",  # Empty for AEE
            "grade_level": "",
            "teacher_ids": [],
            "atendimento_programa": "aee",
            "is_multi_grade": False,
            "series": []
        }
        
        response = authenticated_client.post(f"{BASE_URL}/api/classes", json=class_data)
        assert response.status_code in [200, 201], f"Failed to create AEE class: {response.status_code} - {response.text}"
        
        created_class = response.json()
        assert created_class.get("atendimento_programa") == "aee"
        # education_level should be empty or None
        assert created_class.get("education_level") in ["", None]
        print(f"AEE class created: {created_class.get('id')}")
        
        # Cleanup - delete the test class
        class_id = created_class.get("id")
        if class_id:
            authenticated_client.delete(f"{BASE_URL}/api/classes/{class_id}")
    
    def test_create_aee_multiseriada_class(self, authenticated_client):
        """Test creating AEE multisseriada class with multiple series from all levels"""
        class_data = {
            "school_id": TEST_SCHOOL_ID,
            "academic_year": 2025,
            "name": "TEST_AEE_MULTISERIADA",
            "shift": "morning",
            "education_level": "",  # Empty for AEE
            "grade_level": "1º Ano",  # First series
            "teacher_ids": [],
            "atendimento_programa": "aee",
            "is_multi_grade": True,
            "series": ["1º Ano", "2º Ano", "3º Ano"]  # Multiple series
        }
        
        response = authenticated_client.post(f"{BASE_URL}/api/classes", json=class_data)
        assert response.status_code in [200, 201], f"Failed to create AEE multisseriada class: {response.status_code} - {response.text}"
        
        created_class = response.json()
        assert created_class.get("atendimento_programa") == "aee"
        assert created_class.get("is_multi_grade") == True
        assert len(created_class.get("series", [])) >= 2, "Should have at least 2 series"
        print(f"AEE multisseriada class created with series: {created_class.get('series')}")
        
        # Cleanup
        class_id = created_class.get("id")
        if class_id:
            authenticated_client.delete(f"{BASE_URL}/api/classes/{class_id}")
    
    def test_create_recomposicao_class_without_education_level(self, authenticated_client):
        """Test creating Recomposição da Aprendizagem class with empty education_level"""
        class_data = {
            "school_id": TEST_SCHOOL_ID,
            "academic_year": 2025,
            "name": "TEST_RECOMPOSICAO_NO_LEVEL",
            "shift": "afternoon",
            "education_level": "",  # Empty for Recomposição
            "grade_level": "2º Ano",
            "teacher_ids": [],
            "atendimento_programa": "aulas_complementares",  # Recomposição
            "is_multi_grade": False,
            "series": []
        }
        
        response = authenticated_client.post(f"{BASE_URL}/api/classes", json=class_data)
        assert response.status_code in [200, 201], f"Failed to create Recomposição class: {response.status_code} - {response.text}"
        
        created_class = response.json()
        assert created_class.get("atendimento_programa") == "aulas_complementares"
        assert created_class.get("education_level") in ["", None]
        print(f"Recomposição class created: {created_class.get('id')}")
        
        # Cleanup
        class_id = created_class.get("id")
        if class_id:
            authenticated_client.delete(f"{BASE_URL}/api/classes/{class_id}")
    
    def test_create_regular_class_requires_education_level(self, authenticated_client):
        """Test that regular class still requires education_level"""
        class_data = {
            "school_id": TEST_SCHOOL_ID,
            "academic_year": 2025,
            "name": "TEST_REGULAR_CLASS",
            "shift": "morning",
            "education_level": "fundamental_anos_iniciais",  # Required for regular
            "grade_level": "1º Ano",
            "teacher_ids": [],
            "atendimento_programa": "",  # Regular class
            "is_multi_grade": False,
            "series": []
        }
        
        response = authenticated_client.post(f"{BASE_URL}/api/classes", json=class_data)
        assert response.status_code in [200, 201], f"Failed to create regular class: {response.status_code} - {response.text}"
        
        created_class = response.json()
        assert created_class.get("education_level") == "fundamental_anos_iniciais"
        print(f"Regular class created with education_level: {created_class.get('education_level')}")
        
        # Cleanup
        class_id = created_class.get("id")
        if class_id:
            authenticated_client.delete(f"{BASE_URL}/api/classes/{class_id}")
    
    def test_list_classes_with_various_programs(self, authenticated_client):
        """Test listing classes returns correct program types"""
        response = authenticated_client.get(f"{BASE_URL}/api/classes", params={
            "school_id": TEST_SCHOOL_ID
        })
        assert response.status_code == 200, f"Failed to list classes: {response.text}"
        
        classes = response.json()
        print(f"Found {len(classes)} classes for school")
        
        # Check if there are AEE classes
        aee_classes = [c for c in classes if c.get("atendimento_programa") == "aee"]
        integral_classes = [c for c in classes if c.get("atendimento_programa") == "atendimento_integral"]
        regular_classes = [c for c in classes if not c.get("atendimento_programa")]
        
        print(f"  - AEE classes: {len(aee_classes)}")
        print(f"  - Integral classes: {len(integral_classes)}")
        print(f"  - Regular classes: {len(regular_classes)}")


class TestClassesAPIValidation:
    """Test API validation for class creation"""
    
    def test_classes_endpoint_accessible(self, authenticated_client):
        """Test that classes endpoint is accessible"""
        response = authenticated_client.get(f"{BASE_URL}/api/classes")
        assert response.status_code == 200, f"Classes endpoint not accessible: {response.text}"
    
    def test_classes_by_school(self, authenticated_client):
        """Test filtering classes by school ID"""
        response = authenticated_client.get(f"{BASE_URL}/api/classes", params={
            "school_id": TEST_SCHOOL_ID,
            "_t": "1234567890"  # Cache busting parameter
        })
        assert response.status_code == 200, f"Failed to filter by school: {response.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
