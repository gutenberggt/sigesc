"""
Test for Teacher Allocation - Courses Filtering Bug Fix
Issue: When allocating a professor to a class, the course dropdown appeared empty.
Fix: Made nivel_ensino and grade_levels comparison case-insensitive, and don't filter when education_level is null.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestCoursesAPI:
    """Tests for GET /api/courses endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "gutenberg@sigesc.com",
            "password": "@Celta2007"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json().get("access_token")
    
    def test_courses_list_returns_data(self, auth_token):
        """GET /api/courses should return the seeded courses"""
        response = requests.get(
            f"{BASE_URL}/api/courses",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 9, f"Expected at least 9 courses, got {len(data)}"
        print(f"✓ Courses API returned {len(data)} courses")
    
    def test_courses_have_required_fields(self, auth_token):
        """Each course should have name, nivel_ensino fields"""
        response = requests.get(
            f"{BASE_URL}/api/courses",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        for course in data:
            assert "name" in course, "Course missing name field"
            assert "nivel_ensino" in course, "Course missing nivel_ensino field"
            assert "id" in course, "Course missing id field"
        print(f"✓ All {len(data)} courses have required fields")
    
    def test_courses_have_atendimento_integral_field(self, auth_token):
        """At least one course should have atendimento_programa='atendimento_integral'"""
        response = requests.get(
            f"{BASE_URL}/api/courses",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        integral_courses = [c for c in data if c.get('atendimento_programa') == 'atendimento_integral']
        assert len(integral_courses) >= 1, "No course with atendimento_integral found"
        print(f"✓ Found {len(integral_courses)} course(s) with atendimento_programa='atendimento_integral': {[c['name'] for c in integral_courses]}")


class TestClassesAPI:
    """Tests for GET /api/classes endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "gutenberg@sigesc.com",
            "password": "@Celta2007"
        })
        assert response.status_code == 200
        return response.json().get("access_token")
    
    def test_classes_have_education_level(self, auth_token):
        """Classes should have education_level field (nivel_ensino)"""
        response = requests.get(
            f"{BASE_URL}/api/classes",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        for cls in data:
            # education_level can be null but the field should exist
            assert "education_level" in cls or "nivel_ensino" in cls, f"Class {cls.get('name')} missing education_level"
            assert "grade_level" in cls, f"Class {cls.get('name')} missing grade_level"
        print(f"✓ All {len(data)} classes have education_level and grade_level fields")
    
    def test_classes_match_courses_nivel_ensino(self, auth_token):
        """Verify classes and courses have matching nivel_ensino values"""
        # Get courses
        courses_response = requests.get(
            f"{BASE_URL}/api/courses",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        courses = courses_response.json()
        course_niveis = set(c.get('nivel_ensino', '').lower() for c in courses if c.get('nivel_ensino'))
        
        # Get classes
        classes_response = requests.get(
            f"{BASE_URL}/api/classes",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        classes = classes_response.json()
        class_niveis = set(c.get('education_level', '').lower() for c in classes if c.get('education_level'))
        
        # Check overlap (case-insensitive)
        print(f"Course nivel_ensino values: {course_niveis}")
        print(f"Class education_level values: {class_niveis}")
        
        # At least one match should exist
        overlap = course_niveis.intersection(class_niveis)
        assert len(overlap) > 0, f"No overlap between course nivel_ensino and class education_level"
        print(f"✓ Matching education levels found: {overlap}")


class TestTeacherAllocationFlow:
    """Tests for teacher allocation flow"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "gutenberg@sigesc.com",
            "password": "@Celta2007"
        })
        assert response.status_code == 200
        return response.json().get("access_token")
    
    def test_professor_has_school_assignment(self, auth_token):
        """Professor RICLEIDE should have at least one school assignment"""
        # Get the professor
        staff_response = requests.get(
            f"{BASE_URL}/api/staff?cargo=professor",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert staff_response.status_code == 200
        professors = staff_response.json()
        assert len(professors) >= 1, "No professors found"
        
        professor = professors[0]
        staff_id = professor['id']
        
        # Get schools assigned
        schools_response = requests.get(
            f"{BASE_URL}/api/school-assignments/staff/{staff_id}/schools",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert schools_response.status_code == 200
        schools = schools_response.json()
        assert len(schools) >= 1, f"Professor {professor['nome']} has no school assignments"
        print(f"✓ Professor {professor['nome']} is assigned to {len(schools)} school(s): {[s['name'] for s in schools]}")
    
    def test_school_has_classes(self, auth_token):
        """The school should have classes to allocate"""
        # Get classes
        classes_response = requests.get(
            f"{BASE_URL}/api/classes",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert classes_response.status_code == 200
        classes = classes_response.json()
        assert len(classes) >= 1, "No classes found"
        print(f"✓ Found {len(classes)} class(es): {[c['name'] for c in classes]}")
    
    def test_courses_available_for_class_nivel(self, auth_token):
        """Courses should be available for the class education_level"""
        # Get a class
        classes_response = requests.get(
            f"{BASE_URL}/api/classes",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        classes = classes_response.json()
        test_class = classes[0]
        
        # Get courses
        courses_response = requests.get(
            f"{BASE_URL}/api/courses",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        courses = courses_response.json()
        
        # Filter courses by education level (case-insensitive - the bug fix)
        class_nivel = (test_class.get('education_level') or '').lower()
        matching_courses = [
            c for c in courses 
            if not c.get('nivel_ensino') or c.get('nivel_ensino', '').lower() == class_nivel
        ]
        
        print(f"Class: {test_class['name']}, education_level: {class_nivel}")
        print(f"Total courses: {len(courses)}")
        print(f"Matching courses (case-insensitive): {len(matching_courses)}")
        
        assert len(matching_courses) > 0, f"No courses match class {test_class['name']} with nivel {class_nivel}"
        print(f"✓ {len(matching_courses)} course(s) available for class {test_class['name']}")


class TestSchoolAtendimentoIntegral:
    """Tests for school atendimento_integral field"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "gutenberg@sigesc.com",
            "password": "@Celta2007"
        })
        assert response.status_code == 200
        return response.json().get("access_token")
    
    def test_school_has_atendimento_integral(self, auth_token):
        """ESCOLA TESTE MULTISSERIADA should have atendimento_integral=True"""
        response = requests.get(
            f"{BASE_URL}/api/schools",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        schools = response.json()
        
        test_school = next((s for s in schools if 'MULTISSERIADA' in s.get('name', '')), None)
        assert test_school is not None, "ESCOLA TESTE MULTISSERIADA not found"
        assert test_school.get('atendimento_integral') == True, "School should have atendimento_integral=True"
        print(f"✓ School {test_school['name']} has atendimento_integral={test_school.get('atendimento_integral')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
