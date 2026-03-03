"""
Test for Classes API cache busting parameter (_t)
Tests that GET /api/classes accepts _t parameter without error
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestClassesCacheBusting:
    """Tests for classes API with cache busting parameter"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token before tests"""
        # Login to get token
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "gutenberg@sigesc.com", "password": "@Celta2007"}
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json().get("access_token")
        assert self.token, "No access_token in login response"
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_classes_endpoint_without_t_parameter(self):
        """Test GET /api/classes without _t parameter"""
        response = requests.get(
            f"{BASE_URL}/api/classes",
            headers=self.headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list of classes"
        print(f"✓ GET /api/classes without _t returns {len(data)} classes")
    
    def test_classes_endpoint_with_t_parameter(self):
        """Test GET /api/classes with _t cache busting parameter"""
        import time
        timestamp = int(time.time() * 1000)
        
        response = requests.get(
            f"{BASE_URL}/api/classes",
            params={"_t": timestamp},
            headers=self.headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list of classes"
        print(f"✓ GET /api/classes with _t={timestamp} returns {len(data)} classes")
    
    def test_classes_endpoint_with_school_id_and_t_parameter(self):
        """Test GET /api/classes with both school_id and _t parameters"""
        import time
        timestamp = int(time.time() * 1000)
        
        # First get a school ID
        schools_response = requests.get(
            f"{BASE_URL}/api/schools",
            headers=self.headers
        )
        assert schools_response.status_code == 200, f"Failed to get schools: {schools_response.text}"
        schools = schools_response.json()
        
        if len(schools) > 0:
            school_id = schools[0].get("id")
            
            response = requests.get(
                f"{BASE_URL}/api/classes",
                params={"school_id": school_id, "_t": timestamp},
                headers=self.headers
            )
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            data = response.json()
            assert isinstance(data, list), "Response should be a list of classes"
            print(f"✓ GET /api/classes with school_id and _t returns {len(data)} classes")
        else:
            pytest.skip("No schools available for testing")
    
    def test_classes_creation_and_immediate_list(self):
        """Test creating a class and immediately listing to verify it appears"""
        import time
        
        # Get a school that supports fundamental years
        schools_response = requests.get(
            f"{BASE_URL}/api/schools",
            headers=self.headers
        )
        schools = schools_response.json()
        
        # Find a school that has fundamental_anos_iniciais enabled
        test_school = None
        for school in schools:
            if school.get("fundamental_anos_iniciais"):
                test_school = school
                break
        
        if not test_school:
            pytest.skip("No school with fundamental_anos_iniciais found")
            return
        
        # Create a test class
        test_class_data = {
            "school_id": test_school["id"],
            "academic_year": 2025,
            "name": "TEST_CacheBust_Turma",
            "shift": "morning",
            "education_level": "fundamental_anos_iniciais",
            "grade_level": "1º Ano",
            "teacher_ids": [],
            "is_multi_grade": False,
            "series": []
        }
        
        create_response = requests.post(
            f"{BASE_URL}/api/classes",
            json=test_class_data,
            headers=self.headers
        )
        
        if create_response.status_code not in [200, 201]:
            pytest.skip(f"Could not create test class: {create_response.text}")
            return
        
        created_class = create_response.json()
        created_id = created_class.get("id")
        print(f"✓ Created test class with id: {created_id}")
        
        try:
            # Immediately list classes with cache busting
            timestamp = int(time.time() * 1000)
            list_response = requests.get(
                f"{BASE_URL}/api/classes",
                params={"school_id": test_school["id"], "_t": timestamp},
                headers=self.headers
            )
            
            assert list_response.status_code == 200, f"List failed: {list_response.text}"
            classes = list_response.json()
            
            # Check that the new class appears in the list
            found = any(c.get("id") == created_id for c in classes)
            assert found, f"New class {created_id} not found in list immediately after creation"
            print(f"✓ New class appears in list immediately after creation (cache busting works)")
            
        finally:
            # Cleanup - delete the test class
            if created_id:
                delete_response = requests.delete(
                    f"{BASE_URL}/api/classes/{created_id}",
                    headers=self.headers
                )
                print(f"✓ Cleanup: Deleted test class (status: {delete_response.status_code})")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
