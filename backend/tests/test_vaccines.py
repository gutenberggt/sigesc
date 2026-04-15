"""
Test suite for Vaccine Agent (Agente de Vacinas) functionality.
Tests:
- Login and redirect for agente_vacinas role
- Vaccine status CRUD operations
- Batch status retrieval
- Summary statistics
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = "@Celta2007"
VACCINE_AGENT_EMAIL = "vacinas@sigesc.com"
VACCINE_AGENT_PASSWORD = "@Celta2007"

# Test data from context
TEST_STUDENT_ID = "5c63ab15-1e48-4da2-946e-b9543003dae7"  # MARIA SILVA
TEST_CLASS_ID = "3da4e569-6522-432c-9b42-1e344a2f0c69"  # 6º ANO A
ACADEMIC_YEAR = 2026


class TestVaccineAgentAuth:
    """Test authentication for vaccine agent role"""
    
    def test_vaccine_agent_login_success(self):
        """Test that vaccine agent can login successfully"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": VACCINE_AGENT_EMAIL,
            "password": VACCINE_AGENT_PASSWORD
        })
        print(f"Login response status: {response.status_code}")
        print(f"Login response: {response.text[:500]}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "access_token" in data, "Missing access_token in response"
        assert "user" in data, "Missing user in response"
        assert data["user"]["role"] == "agente_vacinas", f"Expected role 'agente_vacinas', got {data['user']['role']}"
        print(f"✓ Vaccine agent login successful, role: {data['user']['role']}")
    
    def test_admin_login_success(self):
        """Test that admin can login successfully"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "access_token" in data
        print(f"✓ Admin login successful, role: {data['user']['role']}")


class TestVaccineAPIs:
    """Test vaccine status CRUD operations"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for vaccine agent"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": VACCINE_AGENT_EMAIL,
            "password": VACCINE_AGENT_PASSWORD
        })
        if response.status_code == 200:
            self.token = response.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            pytest.skip("Could not authenticate vaccine agent")
    
    def test_get_vaccine_summary(self):
        """Test GET /api/vaccines/summary returns statistics"""
        response = requests.get(
            f"{BASE_URL}/api/vaccines/summary?academic_year={ACADEMIC_YEAR}",
            headers=self.headers
        )
        print(f"Summary response status: {response.status_code}")
        print(f"Summary response: {response.text[:500]}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "total_students" in data, "Missing total_students"
        assert "up_to_date" in data, "Missing up_to_date"
        assert "not_up_to_date" in data, "Missing not_up_to_date"
        assert "not_verified" in data, "Missing not_verified"
        
        print(f"✓ Vaccine summary: total={data['total_students']}, up_to_date={data['up_to_date']}, not_up_to_date={data['not_up_to_date']}, not_verified={data['not_verified']}")
    
    def test_list_students_vaccine_status(self):
        """Test GET /api/vaccines/students returns students with vaccine status"""
        response = requests.get(
            f"{BASE_URL}/api/vaccines/students?academic_year={ACADEMIC_YEAR}&page_size=10",
            headers=self.headers
        )
        print(f"Students list response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "items" in data, "Missing items in response"
        assert "total" in data, "Missing total in response"
        
        if data["items"]:
            student = data["items"][0]
            assert "id" in student, "Missing student id"
            assert "full_name" in student, "Missing student full_name"
            assert "vaccine" in student, "Missing vaccine info"
            assert "status" in student["vaccine"], "Missing vaccine status"
            print(f"✓ Students list: {len(data['items'])} students, total={data['total']}")
            print(f"  First student: {student['full_name']}, vaccine status: {student['vaccine']['status']}")
        else:
            print("✓ Students list returned empty (no students)")
    
    def test_update_vaccine_status_up_to_date(self):
        """Test PUT /api/vaccines/status/{student_id} to set status as up_to_date"""
        # First, get a student to update
        response = requests.get(
            f"{BASE_URL}/api/vaccines/students?academic_year={ACADEMIC_YEAR}&page_size=5",
            headers=self.headers
        )
        
        if response.status_code != 200 or not response.json().get("items"):
            pytest.skip("No students available for testing")
        
        student = response.json()["items"][0]
        student_id = student["id"]
        
        # Update vaccine status to up_to_date
        update_response = requests.put(
            f"{BASE_URL}/api/vaccines/status/{student_id}",
            json={"status": "up_to_date", "academic_year": ACADEMIC_YEAR},
            headers=self.headers
        )
        print(f"Update status response: {update_response.status_code}")
        print(f"Update response: {update_response.text[:500]}")
        
        assert update_response.status_code == 200, f"Expected 200, got {update_response.status_code}"
        
        data = update_response.json()
        assert data["student_id"] == student_id
        assert data["status"] == "up_to_date"
        print(f"✓ Updated student {student_id} to 'up_to_date'")
    
    def test_update_vaccine_status_not_up_to_date(self):
        """Test PUT /api/vaccines/status/{student_id} to set status as not_up_to_date"""
        # Get a student
        response = requests.get(
            f"{BASE_URL}/api/vaccines/students?academic_year={ACADEMIC_YEAR}&page_size=5",
            headers=self.headers
        )
        
        if response.status_code != 200 or not response.json().get("items"):
            pytest.skip("No students available for testing")
        
        student = response.json()["items"][1] if len(response.json()["items"]) > 1 else response.json()["items"][0]
        student_id = student["id"]
        
        # Update vaccine status to not_up_to_date
        update_response = requests.put(
            f"{BASE_URL}/api/vaccines/status/{student_id}",
            json={"status": "not_up_to_date", "academic_year": ACADEMIC_YEAR},
            headers=self.headers
        )
        
        assert update_response.status_code == 200, f"Expected 200, got {update_response.status_code}"
        
        data = update_response.json()
        assert data["status"] == "not_up_to_date"
        print(f"✓ Updated student {student_id} to 'not_up_to_date'")
    
    def test_update_vaccine_status_invalid(self):
        """Test PUT /api/vaccines/status/{student_id} with invalid status returns 400"""
        response = requests.get(
            f"{BASE_URL}/api/vaccines/students?academic_year={ACADEMIC_YEAR}&page_size=1",
            headers=self.headers
        )
        
        if response.status_code != 200 or not response.json().get("items"):
            pytest.skip("No students available for testing")
        
        student_id = response.json()["items"][0]["id"]
        
        # Try invalid status
        update_response = requests.put(
            f"{BASE_URL}/api/vaccines/status/{student_id}",
            json={"status": "invalid_status", "academic_year": ACADEMIC_YEAR},
            headers=self.headers
        )
        
        assert update_response.status_code == 400, f"Expected 400, got {update_response.status_code}"
        print(f"✓ Invalid status correctly rejected with 400")
    
    def test_get_vaccine_status_batch(self):
        """Test GET /api/vaccines/status/batch returns statuses for multiple students"""
        # Get some students first
        response = requests.get(
            f"{BASE_URL}/api/vaccines/students?academic_year={ACADEMIC_YEAR}&page_size=5",
            headers=self.headers
        )
        
        if response.status_code != 200 or not response.json().get("items"):
            pytest.skip("No students available for testing")
        
        student_ids = [s["id"] for s in response.json()["items"][:3]]
        ids_param = ",".join(student_ids)
        
        # Get batch status
        batch_response = requests.get(
            f"{BASE_URL}/api/vaccines/status/batch?student_ids={ids_param}&academic_year={ACADEMIC_YEAR}",
            headers=self.headers
        )
        print(f"Batch response status: {batch_response.status_code}")
        print(f"Batch response: {batch_response.text[:500]}")
        
        assert batch_response.status_code == 200, f"Expected 200, got {batch_response.status_code}"
        
        data = batch_response.json()
        assert isinstance(data, dict), "Expected dict response"
        print(f"✓ Batch status returned for {len(data)} students")
        for sid, status in data.items():
            print(f"  {sid}: {status}")
    
    def test_search_students_by_name(self):
        """Test GET /api/vaccines/students with search parameter"""
        response = requests.get(
            f"{BASE_URL}/api/vaccines/students?academic_year={ACADEMIC_YEAR}&search=MARIA&page_size=10",
            headers=self.headers
        )
        print(f"Search response status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        if data["items"]:
            for student in data["items"]:
                assert "MARIA" in student["full_name"].upper(), f"Search result should contain 'MARIA': {student['full_name']}"
            print(f"✓ Search returned {len(data['items'])} students matching 'MARIA'")
        else:
            print("✓ Search returned no results (no students named MARIA)")
    
    def test_filter_students_by_status(self):
        """Test GET /api/vaccines/students with status filter"""
        response = requests.get(
            f"{BASE_URL}/api/vaccines/students?academic_year={ACADEMIC_YEAR}&status=up_to_date&page_size=10",
            headers=self.headers
        )
        print(f"Filter by status response: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        for student in data["items"]:
            assert student["vaccine"]["status"] == "up_to_date", f"Expected up_to_date status, got {student['vaccine']['status']}"
        print(f"✓ Filter by status returned {len(data['items'])} students with 'up_to_date' status")


class TestVaccineAPIPermissions:
    """Test that vaccine APIs require proper authentication"""
    
    def test_summary_requires_auth(self):
        """Test that /api/vaccines/summary requires authentication"""
        response = requests.get(f"{BASE_URL}/api/vaccines/summary")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✓ Summary endpoint requires authentication")
    
    def test_students_requires_auth(self):
        """Test that /api/vaccines/students requires authentication"""
        response = requests.get(f"{BASE_URL}/api/vaccines/students")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✓ Students endpoint requires authentication")
    
    def test_update_status_requires_auth(self):
        """Test that PUT /api/vaccines/status requires authentication"""
        response = requests.put(
            f"{BASE_URL}/api/vaccines/status/test-id",
            json={"status": "up_to_date"}
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✓ Update status endpoint requires authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
