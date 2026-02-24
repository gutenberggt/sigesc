"""
Test School Status Update Bug Fix - SIGESC
Bug: editing a school always saved as 'Inativa' (inactive)
Fix: unified status control to 'Status da Escola' dropdown using 'active'/'inactive' values
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestSchoolStatusUpdate:
    """Test school status update functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token before tests"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login to get token
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "gutenberg@sigesc.com",
            "password": "@Celta2007"
        })
        
        if login_response.status_code != 200:
            pytest.skip(f"Authentication failed: {login_response.status_code}")
        
        token = login_response.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Get existing school for testing
        schools_response = self.session.get(f"{BASE_URL}/api/schools")
        if schools_response.status_code != 200:
            pytest.skip("Could not fetch schools")
        
        schools = schools_response.json()
        if not schools:
            pytest.skip("No schools available for testing")
        
        self.test_school = schools[0]
        self.school_id = self.test_school['id']
        print(f"Testing with school: {self.test_school['name']} (ID: {self.school_id})")
        print(f"Current status: {self.test_school.get('status')}")
    
    def test_update_school_status_to_inactive(self):
        """Test: PUT /api/schools/{id} with status='inactive' should change status"""
        print(f"\n--- Test: Update school status to 'inactive' ---")
        
        # Update to inactive
        response = self.session.put(f"{BASE_URL}/api/schools/{self.school_id}", json={
            "status": "inactive"
        })
        
        print(f"PUT response status: {response.status_code}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        print(f"Updated school status: {data.get('status')}")
        assert data.get('status') == 'inactive', f"Expected 'inactive', got '{data.get('status')}'"
        
        # Verify with GET
        get_response = self.session.get(f"{BASE_URL}/api/schools/{self.school_id}")
        assert get_response.status_code == 200
        fetched = get_response.json()
        print(f"GET verified status: {fetched.get('status')}")
        assert fetched.get('status') == 'inactive', f"GET returned '{fetched.get('status')}' instead of 'inactive'"
        
        print("PASS: School status updated to 'inactive' successfully")
    
    def test_update_school_status_to_active(self):
        """Test: PUT /api/schools/{id} with status='active' should change status"""
        print(f"\n--- Test: Update school status to 'active' ---")
        
        # First ensure it's inactive
        self.session.put(f"{BASE_URL}/api/schools/{self.school_id}", json={
            "status": "inactive"
        })
        
        # Update to active
        response = self.session.put(f"{BASE_URL}/api/schools/{self.school_id}", json={
            "status": "active"
        })
        
        print(f"PUT response status: {response.status_code}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        print(f"Updated school status: {data.get('status')}")
        assert data.get('status') == 'active', f"Expected 'active', got '{data.get('status')}'"
        
        # Verify with GET
        get_response = self.session.get(f"{BASE_URL}/api/schools/{self.school_id}")
        assert get_response.status_code == 200
        fetched = get_response.json()
        print(f"GET verified status: {fetched.get('status')}")
        assert fetched.get('status') == 'active', f"GET returned '{fetched.get('status')}' instead of 'active'"
        
        print("PASS: School status updated to 'active' successfully")
    
    def test_update_school_with_multiple_fields(self):
        """Test: Update school with status and other fields"""
        print(f"\n--- Test: Update school with multiple fields including status ---")
        
        # Update with multiple fields including status
        response = self.session.put(f"{BASE_URL}/api/schools/{self.school_id}", json={
            "status": "active",
            "inep_code": "15175600"
        })
        
        print(f"PUT response status: {response.status_code}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        print(f"Updated school status: {data.get('status')}")
        print(f"Updated school inep_code: {data.get('inep_code')}")
        assert data.get('status') == 'active', f"Status should remain 'active', got '{data.get('status')}'"
        
        print("PASS: School updated with multiple fields including status")
    
    def test_get_schools_list_shows_correct_status(self):
        """Test: GET /api/schools returns correct status for each school"""
        print(f"\n--- Test: GET schools list shows correct status ---")
        
        response = self.session.get(f"{BASE_URL}/api/schools")
        assert response.status_code == 200
        
        schools = response.json()
        print(f"Found {len(schools)} schools")
        
        for school in schools:
            status = school.get('status')
            print(f"  - {school.get('name')}: status='{status}'")
            assert status in ['active', 'inactive', None], f"Invalid status '{status}' for school {school.get('name')}"
        
        print("PASS: All schools have valid status values")


class TestClassCreation:
    """Test class creation functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token and school data before tests"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login to get token
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "gutenberg@sigesc.com",
            "password": "@Celta2007"
        })
        
        if login_response.status_code != 200:
            pytest.skip(f"Authentication failed: {login_response.status_code}")
        
        token = login_response.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Get existing school for class creation
        schools_response = self.session.get(f"{BASE_URL}/api/schools")
        if schools_response.status_code != 200 or not schools_response.json():
            pytest.skip("No schools available for class creation")
        
        self.school = schools_response.json()[0]
        print(f"Using school: {self.school['name']} (ID: {self.school['id']})")
    
    def test_create_class(self):
        """Test: POST /api/classes creates a new class"""
        print(f"\n--- Test: Create new class ---")
        
        import uuid
        unique_name = f"TEST_TURMA_{uuid.uuid4().hex[:6].upper()}"
        
        class_data = {
            "name": unique_name,
            "school_id": self.school['id'],
            "academic_year": 2026,
            "shift": "morning",  # Valid values: 'morning', 'afternoon', 'evening', 'full_time'
            "education_level": "fundamental_anos_iniciais",
            "grade_level": "1º Ano",
            "capacity": 25
        }
        
        print(f"Creating class with data: {class_data}")
        response = self.session.post(f"{BASE_URL}/api/classes", json=class_data)
        
        print(f"POST response status: {response.status_code}")
        print(f"POST response: {response.text[:500] if response.text else 'No body'}")
        
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        
        created_class = response.json()
        assert created_class.get('name') == unique_name.upper(), f"Name mismatch"
        assert created_class.get('school_id') == self.school['id'], f"School ID mismatch"
        
        print(f"PASS: Class created successfully with ID: {created_class.get('id')}")
        
        # Cleanup - delete test class
        class_id = created_class.get('id')
        if class_id:
            delete_response = self.session.delete(f"{BASE_URL}/api/classes/{class_id}")
            print(f"Cleanup: Deleted test class (status: {delete_response.status_code})")
    
    def test_list_classes(self):
        """Test: GET /api/classes returns class list"""
        print(f"\n--- Test: List classes ---")
        
        response = self.session.get(f"{BASE_URL}/api/classes")
        print(f"GET response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        classes = response.json()
        print(f"Found {len(classes)} classes")
        
        for cls in classes[:5]:  # Show first 5
            print(f"  - {cls.get('name')} ({cls.get('academic_year')})")
        
        print("PASS: Classes listed successfully")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
