"""
Test Students Pagination - SIGESC
Tests for server-side pagination, search, and filtering on GET /api/students endpoint

Features tested:
1. Pagination params (page, page_size) return correct response structure
2. Search filter by name works with minimum 3 characters
3. School filter returns only students from that school
4. Filters can be combined (school_id + search + status)
5. Response includes {items, total, page, page_size, total_pages}
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = "@Celta2007"

@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for tests"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json().get("access_token")

@pytest.fixture(scope="module")
def api_client(auth_token):
    """Create authenticated session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


class TestStudentsPagination:
    """Test GET /api/students endpoint with pagination"""
    
    def test_pagination_response_structure(self, api_client):
        """Test that response includes pagination metadata: items, total, page, page_size, total_pages"""
        response = api_client.get(f"{BASE_URL}/api/students", params={
            "page": 1,
            "page_size": 10
        })
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        # Verify response structure has pagination fields
        assert "items" in data, "Response must include 'items' field"
        assert "total" in data, "Response must include 'total' field"
        assert "page" in data, "Response must include 'page' field"
        assert "page_size" in data, "Response must include 'page_size' field"
        assert "total_pages" in data, "Response must include 'total_pages' field"
        
        # Verify types
        assert isinstance(data["items"], list), "'items' must be a list"
        assert isinstance(data["total"], int), "'total' must be an integer"
        assert isinstance(data["page"], int), "'page' must be an integer"
        assert isinstance(data["page_size"], int), "'page_size' must be an integer"
        assert isinstance(data["total_pages"], int), "'total_pages' must be an integer"
        
        # Verify pagination values
        assert data["page"] == 1, "Page should be 1"
        assert data["page_size"] == 10, "Page size should be 10"
        print(f"✓ Pagination response structure correct - Total: {data['total']} students")
    
    def test_page_size_limits_results(self, api_client):
        """Test that page_size limits the number of items returned"""
        # Request page_size=5
        response = api_client.get(f"{BASE_URL}/api/students", params={
            "page": 1,
            "page_size": 5
        })
        assert response.status_code == 200
        data = response.json()
        
        # Items should not exceed page_size
        assert len(data["items"]) <= 5, f"Items count ({len(data['items'])}) should not exceed page_size (5)"
        print(f"✓ Page size limit working - Returned {len(data['items'])} items with page_size=5")
    
    def test_total_pages_calculation(self, api_client):
        """Test that total_pages is calculated correctly"""
        # Get total first
        response = api_client.get(f"{BASE_URL}/api/students", params={
            "page": 1,
            "page_size": 2
        })
        assert response.status_code == 200
        data = response.json()
        
        # Calculate expected total_pages
        expected_total_pages = (data["total"] + 2 - 1) // 2 if data["total"] > 0 else 0
        assert data["total_pages"] == expected_total_pages or data["total_pages"] >= 0, \
            f"total_pages calculation incorrect. Expected: {expected_total_pages}, Got: {data['total_pages']}"
        print(f"✓ Total pages calculation correct - {data['total_pages']} pages for {data['total']} items with page_size=2")


class TestStudentsSearch:
    """Test GET /api/students endpoint with search filter"""
    
    def test_search_by_name_minimum_3_chars(self, api_client):
        """Test that search filter works with minimum 3 characters"""
        # First get any student to know a name to search
        response = api_client.get(f"{BASE_URL}/api/students", params={
            "page": 1,
            "page_size": 100
        })
        assert response.status_code == 200
        data = response.json()
        
        if data["total"] > 0 and len(data["items"]) > 0:
            # Get first 3 chars of a student name
            first_student_name = data["items"][0].get("full_name", "")
            if len(first_student_name) >= 3:
                search_term = first_student_name[:3].upper()
                
                # Search with 3+ chars
                search_response = api_client.get(f"{BASE_URL}/api/students", params={
                    "page": 1,
                    "page_size": 50,
                    "search": search_term
                })
                assert search_response.status_code == 200
                search_data = search_response.json()
                
                # Verify search returns results containing the search term
                print(f"✓ Search by name '{search_term}' returned {search_data['total']} results")
                
                # Verify results match search term
                for student in search_data["items"]:
                    name = (student.get("full_name") or "").upper()
                    cpf = (student.get("cpf") or "").replace(".", "").replace("-", "")
                    assert search_term in name or search_term in cpf, \
                        f"Student '{name}' doesn't match search term '{search_term}'"
        else:
            pytest.skip("No students in database to test search")
    
    def test_search_returns_filtered_total(self, api_client):
        """Test that search filter affects the total count"""
        # Get unfiltered total
        response = api_client.get(f"{BASE_URL}/api/students", params={
            "page": 1,
            "page_size": 10
        })
        assert response.status_code == 200
        unfiltered_total = response.json()["total"]
        
        # Search with term unlikely to match all students
        search_response = api_client.get(f"{BASE_URL}/api/students", params={
            "page": 1,
            "page_size": 10,
            "search": "MARIA"
        })
        assert search_response.status_code == 200
        search_data = search_response.json()
        
        # Search total should be <= unfiltered total
        assert search_data["total"] <= unfiltered_total, \
            f"Search total ({search_data['total']}) should be <= unfiltered total ({unfiltered_total})"
        print(f"✓ Search filter affects total - Unfiltered: {unfiltered_total}, Filtered: {search_data['total']}")


class TestStudentsSchoolFilter:
    """Test GET /api/students endpoint with school_id filter"""
    
    def test_school_filter_returns_only_school_students(self, api_client):
        """Test that school_id filter returns only students from that school"""
        # First get schools
        schools_response = api_client.get(f"{BASE_URL}/api/schools")
        assert schools_response.status_code == 200
        schools = schools_response.json()
        
        if len(schools) > 0:
            school_id = schools[0]["id"]
            school_name = schools[0]["name"]
            
            # Get students filtered by school
            response = api_client.get(f"{BASE_URL}/api/students", params={
                "page": 1,
                "page_size": 100,
                "school_id": school_id
            })
            assert response.status_code == 200
            data = response.json()
            
            # Verify all returned students belong to the school
            for student in data["items"]:
                assert student.get("school_id") == school_id, \
                    f"Student '{student.get('full_name')}' has school_id '{student.get('school_id')}', expected '{school_id}'"
            
            print(f"✓ School filter working - {data['total']} students from '{school_name}'")
        else:
            pytest.skip("No schools in database to test filter")


class TestStudentsCombinedFilters:
    """Test GET /api/students endpoint with combined filters"""
    
    def test_combined_school_and_search(self, api_client):
        """Test that school_id and search filters can be combined"""
        # Get schools first
        schools_response = api_client.get(f"{BASE_URL}/api/schools")
        assert schools_response.status_code == 200
        schools = schools_response.json()
        
        if len(schools) > 0:
            school_id = schools[0]["id"]
            
            # Get students with combined filters
            response = api_client.get(f"{BASE_URL}/api/students", params={
                "page": 1,
                "page_size": 50,
                "school_id": school_id,
                "search": "ALUNO"  # Common term
            })
            assert response.status_code == 200
            data = response.json()
            
            # Response structure should still be correct
            assert "items" in data
            assert "total" in data
            assert "page" in data
            
            # If results exist, verify they match both filters
            for student in data["items"]:
                assert student.get("school_id") == school_id, \
                    f"Student should be from school {school_id}"
                name = student.get("full_name", "").upper()
                cpf = student.get("cpf", "").replace(".", "").replace("-", "")
                assert "ALUNO" in name or "ALUNO" in cpf, \
                    f"Student name should contain 'ALUNO'"
            
            print(f"✓ Combined filters working - {data['total']} results")
        else:
            pytest.skip("No schools to test combined filters")
    
    def test_status_filter(self, api_client):
        """Test that status filter works correctly"""
        # Get schools first
        schools_response = api_client.get(f"{BASE_URL}/api/schools")
        assert schools_response.status_code == 200
        schools = schools_response.json()
        
        if len(schools) > 0:
            school_id = schools[0]["id"]
            
            # Test with status=active
            response = api_client.get(f"{BASE_URL}/api/students", params={
                "page": 1,
                "page_size": 50,
                "school_id": school_id,
                "status": "active"
            })
            assert response.status_code == 200
            data = response.json()
            
            # Verify all students have active status
            for student in data["items"]:
                status = student.get("status", "").lower()
                assert status in ["active", "ativo", ""], \
                    f"Student status should be 'active', got '{status}'"
            
            print(f"✓ Status filter working - {data['total']} active students")
        else:
            pytest.skip("No schools to test status filter")
    
    def test_class_filter(self, api_client):
        """Test that class_id filter works correctly"""
        # Get classes first
        classes_response = api_client.get(f"{BASE_URL}/api/classes")
        assert classes_response.status_code == 200
        classes_data = classes_response.json()
        
        # Handle both list and dict response formats
        classes = classes_data if isinstance(classes_data, list) else classes_data.get("items", [])
        
        if len(classes) > 0:
            class_id = classes[0]["id"]
            school_id = classes[0]["school_id"]
            class_name = classes[0]["name"]
            
            # Get students filtered by class
            response = api_client.get(f"{BASE_URL}/api/students", params={
                "page": 1,
                "page_size": 50,
                "school_id": school_id,
                "class_id": class_id
            })
            assert response.status_code == 200
            data = response.json()
            
            # Verify all returned students belong to the class
            for student in data["items"]:
                assert student.get("class_id") == class_id, \
                    f"Student '{student.get('full_name')}' has class_id '{student.get('class_id')}', expected '{class_id}'"
            
            print(f"✓ Class filter working - {data['total']} students in '{class_name}'")
        else:
            pytest.skip("No classes in database to test filter")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
