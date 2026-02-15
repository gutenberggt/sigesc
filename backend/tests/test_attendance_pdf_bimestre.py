"""
Test cases for the Attendance PDF Bimestre feature
Tests the endpoint: GET /api/attendance/pdf/bimestre/{class_id}
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
    """Get authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def test_class_id(auth_token):
    """Get a valid class ID for testing"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    
    # Get schools first
    schools_response = requests.get(f"{BASE_URL}/api/schools", headers=headers)
    assert schools_response.status_code == 200
    schools = schools_response.json()
    
    if not schools:
        pytest.skip("No schools available for testing")
    
    school_id = schools[0]["id"]
    
    # Get classes for the school
    classes_response = requests.get(
        f"{BASE_URL}/api/classes?school_id={school_id}",
        headers=headers
    )
    assert classes_response.status_code == 200
    classes = classes_response.json()
    
    if not classes:
        pytest.skip("No classes available for testing")
    
    return classes[0]["id"]


class TestAttendancePdfBimestreEndpoint:
    """Tests for the attendance PDF bimestre endpoint"""
    
    def test_pdf_bimestre_1_returns_200(self, auth_token, test_class_id):
        """Test that PDF generation for 1º Bimestre returns 200"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(
            f"{BASE_URL}/api/attendance/pdf/bimestre/{test_class_id}?bimestre=1&academic_year=2025",
            headers=headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert response.headers.get("content-type") == "application/pdf"
        print("✓ 1º Bimestre PDF generated successfully")
    
    def test_pdf_bimestre_2_returns_200(self, auth_token, test_class_id):
        """Test that PDF generation for 2º Bimestre returns 200"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(
            f"{BASE_URL}/api/attendance/pdf/bimestre/{test_class_id}?bimestre=2&academic_year=2025",
            headers=headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert response.headers.get("content-type") == "application/pdf"
        print("✓ 2º Bimestre PDF generated successfully")
    
    def test_pdf_bimestre_3_returns_200(self, auth_token, test_class_id):
        """Test that PDF generation for 3º Bimestre returns 200"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(
            f"{BASE_URL}/api/attendance/pdf/bimestre/{test_class_id}?bimestre=3&academic_year=2025",
            headers=headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert response.headers.get("content-type") == "application/pdf"
        print("✓ 3º Bimestre PDF generated successfully")
    
    def test_pdf_bimestre_4_returns_200(self, auth_token, test_class_id):
        """Test that PDF generation for 4º Bimestre returns 200"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(
            f"{BASE_URL}/api/attendance/pdf/bimestre/{test_class_id}?bimestre=4&academic_year=2025",
            headers=headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert response.headers.get("content-type") == "application/pdf"
        print("✓ 4º Bimestre PDF generated successfully")
    
    def test_pdf_content_is_valid_pdf(self, auth_token, test_class_id):
        """Test that the returned content is a valid PDF"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(
            f"{BASE_URL}/api/attendance/pdf/bimestre/{test_class_id}?bimestre=1&academic_year=2025",
            headers=headers
        )
        assert response.status_code == 200
        # Check PDF magic bytes
        assert response.content[:4] == b'%PDF', "Response is not a valid PDF file"
        print("✓ PDF content is valid")
    
    def test_pdf_invalid_bimestre_returns_422(self, auth_token, test_class_id):
        """Test that invalid bimestre (0 or 5) returns 422"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Test bimestre 0
        response = requests.get(
            f"{BASE_URL}/api/attendance/pdf/bimestre/{test_class_id}?bimestre=0&academic_year=2025",
            headers=headers
        )
        assert response.status_code == 422, f"Expected 422 for bimestre=0, got {response.status_code}"
        
        # Test bimestre 5
        response = requests.get(
            f"{BASE_URL}/api/attendance/pdf/bimestre/{test_class_id}?bimestre=5&academic_year=2025",
            headers=headers
        )
        assert response.status_code == 422, f"Expected 422 for bimestre=5, got {response.status_code}"
        print("✓ Invalid bimestre validation works correctly")
    
    def test_pdf_invalid_class_returns_404(self, auth_token):
        """Test that invalid class_id returns 404"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(
            f"{BASE_URL}/api/attendance/pdf/bimestre/invalid-class-id?bimestre=1&academic_year=2025",
            headers=headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Invalid class_id returns 404")
    
    def test_pdf_without_auth_returns_401(self, test_class_id):
        """Test that request without authentication returns 401"""
        response = requests.get(
            f"{BASE_URL}/api/attendance/pdf/bimestre/{test_class_id}?bimestre=1&academic_year=2025"
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Unauthenticated request returns 401")
    
    def test_pdf_content_disposition_header(self, auth_token, test_class_id):
        """Test that Content-Disposition header is set correctly"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(
            f"{BASE_URL}/api/attendance/pdf/bimestre/{test_class_id}?bimestre=1&academic_year=2025",
            headers=headers
        )
        assert response.status_code == 200
        content_disposition = response.headers.get("content-disposition", "")
        assert "inline" in content_disposition, "Content-Disposition should be inline"
        assert "filename=" in content_disposition, "Content-Disposition should have filename"
        print(f"✓ Content-Disposition header: {content_disposition}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
