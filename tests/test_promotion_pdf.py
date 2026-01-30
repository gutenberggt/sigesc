"""
Test cases for Livro de Promoção PDF generation endpoint
Endpoint: GET /api/documents/promotion/{class_id}

Tests:
- PDF generation for eligible classes (3º-9º Ano)
- Authentication required
- Invalid class_id handling
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://deploy-fix-70.preview.emergentagent.com')

# Test credentials
TEST_EMAIL = "gutenberg@sigesc.com"
TEST_PASSWORD = "@Celta2007"

# Known class IDs for testing (from E M E F MONSENHOR AUGUSTO DIAS DE BRITO)
TEST_CLASSES = {
    "3º Ano A": "68fe60c3-a103-4617-9716-5fa304ac8a38",
    "6º Ano A": "d031e882-b865-411b-89ad-059c2982e48d",
    "9º Ano A": "36d77a13-c5f0-4907-860d-ed6c3db32b8b"
}


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for tests"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json().get("access_token")


@pytest.fixture
def api_client(auth_token):
    """Create authenticated session"""
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    })
    return session


class TestPromotionPDFEndpoint:
    """Tests for /api/documents/promotion/{class_id} endpoint"""
    
    def test_pdf_generation_3ano(self, api_client):
        """Test PDF generation for 3º Ano A"""
        class_id = TEST_CLASSES["3º Ano A"]
        response = api_client.get(
            f"{BASE_URL}/api/documents/promotion/{class_id}?academic_year=2025"
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert response.headers.get("content-type") == "application/pdf"
        assert len(response.content) > 1000, "PDF content too small"
        assert response.content[:4] == b"%PDF", "Response is not a valid PDF"
    
    def test_pdf_generation_6ano(self, api_client):
        """Test PDF generation for 6º Ano A"""
        class_id = TEST_CLASSES["6º Ano A"]
        response = api_client.get(
            f"{BASE_URL}/api/documents/promotion/{class_id}?academic_year=2025"
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert response.headers.get("content-type") == "application/pdf"
        assert len(response.content) > 1000, "PDF content too small"
        assert response.content[:4] == b"%PDF", "Response is not a valid PDF"
    
    def test_pdf_generation_9ano(self, api_client):
        """Test PDF generation for 9º Ano A"""
        class_id = TEST_CLASSES["9º Ano A"]
        response = api_client.get(
            f"{BASE_URL}/api/documents/promotion/{class_id}?academic_year=2025"
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert response.headers.get("content-type") == "application/pdf"
        assert len(response.content) > 1000, "PDF content too small"
        assert response.content[:4] == b"%PDF", "Response is not a valid PDF"
    
    def test_pdf_requires_authentication(self):
        """Test that endpoint requires authentication"""
        class_id = TEST_CLASSES["6º Ano A"]
        response = requests.get(
            f"{BASE_URL}/api/documents/promotion/{class_id}?academic_year=2025"
        )
        
        # Should return 401 or 403 without auth
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
    
    def test_pdf_invalid_class_id(self, api_client):
        """Test with invalid class_id returns 404"""
        invalid_class_id = "00000000-0000-0000-0000-000000000000"
        response = api_client.get(
            f"{BASE_URL}/api/documents/promotion/{invalid_class_id}?academic_year=2025"
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    
    def test_pdf_default_academic_year(self, api_client):
        """Test PDF generation without specifying academic_year (should default to 2025)"""
        class_id = TEST_CLASSES["6º Ano A"]
        response = api_client.get(
            f"{BASE_URL}/api/documents/promotion/{class_id}"
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert response.content[:4] == b"%PDF", "Response is not a valid PDF"


class TestPromotionPageData:
    """Tests for data loading on Promotion page"""
    
    def test_schools_list(self, api_client):
        """Test that schools list is accessible"""
        response = api_client.get(f"{BASE_URL}/api/schools")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0, "No schools found"
    
    def test_classes_list(self, api_client):
        """Test that classes list is accessible"""
        response = api_client.get(f"{BASE_URL}/api/classes")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0, "No classes found"
        
        # Check for eligible classes (3º-9º Ano)
        eligible = [c for c in data if any(
            x in c.get('grade_level', '').lower() 
            for x in ['3º', '4º', '5º', '6º', '7º', '8º', '9º', 'etapa']
        )]
        assert len(eligible) > 0, "No eligible classes for Livro de Promoção"
    
    def test_enrollments_by_class(self, api_client):
        """Test that enrollments can be fetched by class_id"""
        class_id = TEST_CLASSES["6º Ano A"]
        response = api_client.get(f"{BASE_URL}/api/enrollments?class_id={class_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Note: May be empty if no enrollments, but should not error


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
