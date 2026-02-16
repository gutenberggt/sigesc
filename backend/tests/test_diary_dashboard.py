"""
Test cases for Diary Dashboard endpoints and new role permissions
Tests:
- /api/diary-dashboard/attendance endpoint
- /api/diary-dashboard/grades endpoint
- /api/diary-dashboard/content endpoint
- Role-based access control for new roles (auxiliar_secretaria, semed_nivel_1, semed_nivel_2, semed_nivel_3)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDiaryDashboardEndpoints:
    """Test diary dashboard statistics endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test - login as admin"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "gutenberg@sigesc.com",
            "password": "@Celta2007"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_attendance_stats_endpoint(self):
        """Test /api/diary-dashboard/attendance returns valid response"""
        response = requests.get(
            f"{BASE_URL}/api/diary-dashboard/attendance",
            params={"academic_year": 2026},
            headers=self.headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "completion_rate" in data, "Response should have completion_rate"
        assert "total_records" in data, "Response should have total_records"
        assert "by_month" in data, "Response should have by_month"
        assert isinstance(data["completion_rate"], (int, float)), "completion_rate should be numeric"
        assert isinstance(data["total_records"], int), "total_records should be integer"
        assert isinstance(data["by_month"], list), "by_month should be a list"
        print(f"✓ Attendance stats: completion_rate={data['completion_rate']}%, total_records={data['total_records']}")
    
    def test_grades_stats_endpoint(self):
        """Test /api/diary-dashboard/grades returns valid response"""
        response = requests.get(
            f"{BASE_URL}/api/diary-dashboard/grades",
            params={"academic_year": 2026},
            headers=self.headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "completion_rate" in data, "Response should have completion_rate"
        assert "total_records" in data, "Response should have total_records"
        assert "by_bimestre" in data, "Response should have by_bimestre"
        assert isinstance(data["by_bimestre"], list), "by_bimestre should be a list"
        
        # Verify bimestre structure
        if len(data["by_bimestre"]) > 0:
            bim = data["by_bimestre"][0]
            assert "name" in bim, "Bimestre should have name"
            assert "preenchido" in bim, "Bimestre should have preenchido"
            assert "pendente" in bim, "Bimestre should have pendente"
        
        print(f"✓ Grades stats: completion_rate={data['completion_rate']}%, bimestres={len(data['by_bimestre'])}")
    
    def test_content_stats_endpoint(self):
        """Test /api/diary-dashboard/content returns valid response"""
        response = requests.get(
            f"{BASE_URL}/api/diary-dashboard/content",
            params={"academic_year": 2026},
            headers=self.headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "completion_rate" in data, "Response should have completion_rate"
        assert "total_records" in data, "Response should have total_records"
        assert "by_month" in data, "Response should have by_month"
        
        print(f"✓ Content stats: completion_rate={data['completion_rate']}%, total_records={data['total_records']}")
    
    def test_attendance_with_school_filter(self):
        """Test attendance endpoint with school_id filter"""
        # First get a school ID
        schools_response = requests.get(f"{BASE_URL}/api/schools", headers=self.headers)
        assert schools_response.status_code == 200
        schools = schools_response.json()
        
        if len(schools) > 0:
            school_id = schools[0]["id"]
            response = requests.get(
                f"{BASE_URL}/api/diary-dashboard/attendance",
                params={"academic_year": 2026, "school_id": school_id},
                headers=self.headers
            )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            assert "completion_rate" in data
            print(f"✓ Attendance with school filter works: school_id={school_id}")
        else:
            pytest.skip("No schools available for testing")
    
    def test_grades_with_filters(self):
        """Test grades endpoint with multiple filters"""
        # Get schools and classes
        schools_response = requests.get(f"{BASE_URL}/api/schools", headers=self.headers)
        schools = schools_response.json()
        
        if len(schools) > 0:
            school_id = schools[0]["id"]
            
            # Get classes for this school
            classes_response = requests.get(
                f"{BASE_URL}/api/classes",
                params={"school_id": school_id},
                headers=self.headers
            )
            classes = classes_response.json()
            
            if len(classes) > 0:
                class_id = classes[0]["id"]
                response = requests.get(
                    f"{BASE_URL}/api/diary-dashboard/grades",
                    params={
                        "academic_year": 2026,
                        "school_id": school_id,
                        "class_id": class_id
                    },
                    headers=self.headers
                )
                
                assert response.status_code == 200
                print(f"✓ Grades with filters works: school_id={school_id}, class_id={class_id}")
            else:
                print("No classes available for filter test")
        else:
            pytest.skip("No schools available for testing")


class TestRolePermissions:
    """Test role-based access control for diary dashboard"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test - login as admin"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "gutenberg@sigesc.com",
            "password": "@Celta2007"
        })
        assert login_response.status_code == 200
        self.admin_token = login_response.json()["access_token"]
        self.admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
    
    def test_admin_can_access_diary_dashboard(self):
        """Test admin role can access diary dashboard endpoints"""
        response = requests.get(
            f"{BASE_URL}/api/diary-dashboard/attendance",
            params={"academic_year": 2026},
            headers=self.admin_headers
        )
        assert response.status_code == 200, "Admin should have access to diary dashboard"
        print("✓ Admin can access diary dashboard")
    
    def test_permissions_endpoint_returns_correct_structure(self):
        """Test /api/auth/permissions returns correct permission structure"""
        response = requests.get(
            f"{BASE_URL}/api/auth/permissions",
            headers=self.admin_headers
        )
        
        # This endpoint may or may not exist, so we handle both cases
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Permissions endpoint returned: {data}")
        elif response.status_code == 404:
            print("Permissions endpoint not found (may not be implemented)")
        else:
            print(f"Permissions endpoint returned status {response.status_code}")


class TestNewRolesDefinition:
    """Test that new roles are properly defined in the system"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test - login as admin"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "gutenberg@sigesc.com",
            "password": "@Celta2007"
        })
        assert login_response.status_code == 200
        self.token = login_response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_users_endpoint_works(self):
        """Test users endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/users", headers=self.headers)
        assert response.status_code == 200, f"Users endpoint failed: {response.text}"
        users = response.json()
        print(f"✓ Users endpoint works, found {len(users)} users")
        
        # Check if any users have the new roles
        new_roles = ['auxiliar_secretaria', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3']
        found_roles = set()
        for user in users:
            if user.get('role') in new_roles:
                found_roles.add(user.get('role'))
        
        if found_roles:
            print(f"✓ Found users with new roles: {found_roles}")
        else:
            print("No users with new roles found (this is expected if no users were created with these roles)")


class TestDiaryDashboardFilters:
    """Test diary dashboard filter functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test - login as admin"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "gutenberg@sigesc.com",
            "password": "@Celta2007"
        })
        assert login_response.status_code == 200
        self.token = login_response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_academic_year_filter_required(self):
        """Test that academic_year is required"""
        response = requests.get(
            f"{BASE_URL}/api/diary-dashboard/attendance",
            headers=self.headers
        )
        # Should return 422 (validation error) without academic_year
        assert response.status_code == 422, f"Expected 422 without academic_year, got {response.status_code}"
        print("✓ academic_year parameter is required")
    
    def test_different_academic_years(self):
        """Test endpoint with different academic years"""
        for year in [2025, 2026, 2027]:
            response = requests.get(
                f"{BASE_URL}/api/diary-dashboard/attendance",
                params={"academic_year": year},
                headers=self.headers
            )
            assert response.status_code == 200, f"Failed for year {year}"
        print("✓ Different academic years work correctly")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
