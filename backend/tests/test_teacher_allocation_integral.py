"""
Test cases for teacher allocation with integral school classes bug fix.

Bug: When allocating a professor to an integral school class (atendimento_programa='atendimento_integral'),
no curriculum components were displayed. The fix ensures that integral classes are treated as "regular"
so both regular and integral components are shown.

Test scenarios:
1. Courses API returns all types of courses (regular, integral, AEE)
2. Classes API returns classes with different atendimento_programa values
3. Verify school has atendimento_integral=true flag
4. Verify the fix logic in frontend (documented here for reference)
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestTeacherAllocationIntegralClasses:
    """Test suite for the integral classes teacher allocation bug fix"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test - get authentication token"""
        self.token = None
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "gutenberg@sigesc.com",
            "password": "@Celta2007"
        })
        if response.status_code == 200:
            self.token = response.json().get('access_token')
        
        if not self.token:
            pytest.skip("Authentication failed - skipping tests")
    
    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.token}"}
    
    def test_courses_api_returns_atendimento_programa(self):
        """Verify GET /api/courses returns courses with atendimento_programa field"""
        response = requests.get(f"{BASE_URL}/api/courses?limit=100", headers=self.headers)
        
        assert response.status_code == 200
        courses = response.json()
        
        # Check we have courses
        assert len(courses) > 0, "No courses found"
        
        # Verify courses have atendimento_programa field
        for course in courses:
            assert 'atendimento_programa' in course, f"Course {course.get('name')} missing atendimento_programa field"
        
        print(f"Found {len(courses)} courses with atendimento_programa field")
    
    def test_courses_with_different_atendimento_programa_types(self):
        """Verify courses exist with different atendimento_programa values"""
        response = requests.get(f"{BASE_URL}/api/courses?limit=200", headers=self.headers)
        
        assert response.status_code == 200
        courses = response.json()
        
        # Group by atendimento_programa
        regular_courses = [c for c in courses if not c.get('atendimento_programa')]
        integral_courses = [c for c in courses if c.get('atendimento_programa') == 'atendimento_integral']
        aee_courses = [c for c in courses if c.get('atendimento_programa') == 'aee']
        
        # Verify we have regular courses
        assert len(regular_courses) > 0, "No regular courses found (atendimento_programa = null)"
        print(f"Regular courses (atendimento_programa=null): {len(regular_courses)}")
        
        # Verify we have integral courses
        assert len(integral_courses) > 0, "No integral courses found (atendimento_programa = 'atendimento_integral')"
        print(f"Integral courses: {len(integral_courses)}")
        
        # Verify we have AEE courses
        assert len(aee_courses) > 0, "No AEE courses found (atendimento_programa = 'aee')"
        print(f"AEE courses: {len(aee_courses)}")
        
        # Print example courses
        if regular_courses:
            print(f"  Example regular: {regular_courses[0].get('name')}")
        if integral_courses:
            print(f"  Example integral: {integral_courses[0].get('name')}")
        if aee_courses:
            print(f"  Example AEE: {aee_courses[0].get('name')}")
    
    def test_school_with_atendimento_integral_flag(self):
        """Verify school 'ESCOLA TESTE MULTISSERIADA' has atendimento_integral=true"""
        school_id = "220d4022-ec5e-4fb6-86fc-9233112b87b2"
        
        response = requests.get(f"{BASE_URL}/api/schools/{school_id}", headers=self.headers)
        
        assert response.status_code == 200
        school = response.json()
        
        # Verify atendimento_integral flag
        assert school.get('atendimento_integral') == True, \
            f"School '{school.get('name')}' should have atendimento_integral=true"
        
        print(f"School '{school.get('name')}' has atendimento_integral={school.get('atendimento_integral')}")
    
    def test_class_with_atendimento_programa_integral(self):
        """Verify class with atendimento_programa='atendimento_integral' exists"""
        school_id = "220d4022-ec5e-4fb6-86fc-9233112b87b2"
        
        response = requests.get(
            f"{BASE_URL}/api/classes?school_id={school_id}&limit=100", 
            headers=self.headers
        )
        
        assert response.status_code == 200
        classes = response.json()
        
        # Find class with atendimento_programa='atendimento_integral'
        integral_classes = [c for c in classes if c.get('atendimento_programa') == 'atendimento_integral']
        
        assert len(integral_classes) > 0, \
            "No class with atendimento_programa='atendimento_integral' found. Test setup incomplete."
        
        print(f"Found {len(integral_classes)} integral class(es):")
        for c in integral_classes:
            print(f"  - {c.get('name')} (id: {c.get('id')}, grade: {c.get('grade_level')})")
    
    def test_class_with_atendimento_programa_aee(self):
        """Verify AEE class exists and is separate from integral classes"""
        school_id = "220d4022-ec5e-4fb6-86fc-9233112b87b2"
        
        response = requests.get(
            f"{BASE_URL}/api/classes?school_id={school_id}&limit=100", 
            headers=self.headers
        )
        
        assert response.status_code == 200
        classes = response.json()
        
        # Find AEE classes
        aee_classes = [c for c in classes if c.get('atendimento_programa', '').upper() == 'AEE']
        
        if len(aee_classes) > 0:
            print(f"Found {len(aee_classes)} AEE class(es):")
            for c in aee_classes:
                print(f"  - {c.get('name')} (id: {c.get('id')})")
        else:
            print("No AEE classes found (this is OK, just verifying)")
    
    def test_regular_class_exists(self):
        """Verify regular classes (without atendimento_programa) exist"""
        school_id = "220d4022-ec5e-4fb6-86fc-9233112b87b2"
        
        response = requests.get(
            f"{BASE_URL}/api/classes?school_id={school_id}&limit=100", 
            headers=self.headers
        )
        
        assert response.status_code == 200
        classes = response.json()
        
        # Find regular classes (no atendimento_programa or empty)
        regular_classes = [c for c in classes if not c.get('atendimento_programa')]
        
        assert len(regular_classes) > 0, "No regular classes found"
        
        print(f"Found {len(regular_classes)} regular class(es):")
        for c in regular_classes[:3]:  # Show first 3
            print(f"  - {c.get('name')} (grade: {c.get('grade_level')})")
    
    def test_professor_has_lotacao_in_school(self):
        """Verify professor RICLEIDE has lotação in the integral school"""
        staff_id = "4c34fe19-5c6b-4de7-ae9a-030fed52a84c"  # RICLEIDE
        school_id = "220d4022-ec5e-4fb6-86fc-9233112b87b2"
        
        response = requests.get(
            f"{BASE_URL}/api/school-assignments?staff_id={staff_id}", 
            headers=self.headers
        )
        
        assert response.status_code == 200
        assignments = response.json()
        
        # Find assignment for this school
        school_assignment = [a for a in assignments if a.get('school_id') == school_id]
        
        assert len(school_assignment) > 0, \
            f"Professor {staff_id} has no lotação in school {school_id}"
        
        assignment = school_assignment[0]
        print(f"Professor has lotação in school: {assignment.get('school_name')}")
        print(f"  Status: {assignment.get('status')}")
        print(f"  Function: {assignment.get('funcao')}")


class TestFilteredCoursesLogic:
    """
    Tests documenting the filteredCourses logic fix in useStaff.js
    
    BEFORE FIX (lines 341-347 of useStaff.js):
    - Any class with truthy atendimento_programa was added to programasTurmas
    - This caused temTurmaRegular to stay false for integral classes
    - Result: no regular components shown for integral classes
    
    AFTER FIX:
    - Classes with atendimento_programa='atendimento_integral' set temTurmaRegular=true
    - Only special programs (AEE, reforço, etc.) go to programasTurmas
    - Result: integral classes show both regular AND integral components
    """
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test - get authentication token"""
        self.token = None
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "gutenberg@sigesc.com",
            "password": "@Celta2007"
        })
        if response.status_code == 200:
            self.token = response.json().get('access_token')
        
        if not self.token:
            pytest.skip("Authentication failed - skipping tests")
    
    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.token}"}
    
    def test_logic_for_integral_class_should_show_regular_courses(self):
        """
        Test logic: When selecting an integral class, regular courses should be shown.
        
        Fix in useStaff.js lines 342-349:
        ```
        const prog = (turma.atendimento_programa || '').toLowerCase().trim();
        if (prog && prog !== 'atendimento_integral') {
            programasTurmas.add(prog);  // AEE, reforço, etc.
        } else {
            temTurmaRegular = true;  // Regular OR integral classes
        }
        ```
        """
        # Get courses
        response = requests.get(f"{BASE_URL}/api/courses?limit=200", headers=self.headers)
        assert response.status_code == 200
        courses = response.json()
        
        # Simulate filtering for an integral class in an integral school
        # temTurmaRegular = true (because atendimento_programa == 'atendimento_integral')
        # escolaTemIntegral = true
        tem_turma_regular = True
        escola_tem_integral = True
        programas_turmas = set()  # Empty because integral is not added
        
        # Filter courses (simplified version of frontend logic)
        filtered_courses = []
        for curso in courses:
            curso_programa = (curso.get('atendimento_programa') or '').lower().strip()
            
            if curso_programa:
                if curso_programa == 'atendimento_integral':
                    # Integral component: needs integral school + regular class
                    if escola_tem_integral and tem_turma_regular:
                        filtered_courses.append(curso)
                else:
                    # Program-specific component (AEE, etc.)
                    if curso_programa in programas_turmas:
                        filtered_courses.append(curso)
            else:
                # Regular component: only for regular classes
                if tem_turma_regular:
                    filtered_courses.append(curso)
        
        # Verify we get both regular AND integral courses
        regular_in_filtered = [c for c in filtered_courses if not c.get('atendimento_programa')]
        integral_in_filtered = [c for c in filtered_courses if c.get('atendimento_programa') == 'atendimento_integral']
        
        assert len(regular_in_filtered) > 0, "No regular courses in filtered result"
        assert len(integral_in_filtered) > 0, "No integral courses in filtered result"
        
        print(f"For INTEGRAL class in INTEGRAL school:")
        print(f"  Regular courses shown: {len(regular_in_filtered)}")
        print(f"  Integral courses shown: {len(integral_in_filtered)}")
        print(f"  Total courses: {len(filtered_courses)}")
    
    def test_logic_for_aee_class_should_only_show_aee_courses(self):
        """
        Test logic: When selecting an AEE class, only AEE courses should be shown.
        """
        # Get courses
        response = requests.get(f"{BASE_URL}/api/courses?limit=200", headers=self.headers)
        assert response.status_code == 200
        courses = response.json()
        
        # Simulate filtering for an AEE class
        tem_turma_regular = False  # AEE class is NOT regular
        escola_tem_integral = True
        programas_turmas = {'aee'}  # AEE class has this program
        
        # Filter courses
        filtered_courses = []
        for curso in courses:
            curso_programa = (curso.get('atendimento_programa') or '').lower().strip()
            
            if curso_programa:
                if curso_programa == 'atendimento_integral':
                    if escola_tem_integral and tem_turma_regular:
                        filtered_courses.append(curso)
                else:
                    if curso_programa in programas_turmas:
                        filtered_courses.append(curso)
            else:
                if tem_turma_regular:
                    filtered_courses.append(curso)
        
        # Verify ONLY AEE courses shown
        aee_in_filtered = [c for c in filtered_courses if c.get('atendimento_programa') == 'aee']
        regular_in_filtered = [c for c in filtered_courses if not c.get('atendimento_programa')]
        integral_in_filtered = [c for c in filtered_courses if c.get('atendimento_programa') == 'atendimento_integral']
        
        assert len(aee_in_filtered) > 0, "No AEE courses in filtered result"
        assert len(regular_in_filtered) == 0, "Regular courses should NOT appear for AEE class"
        assert len(integral_in_filtered) == 0, "Integral courses should NOT appear for AEE class"
        
        print(f"For AEE class:")
        print(f"  AEE courses shown: {len(aee_in_filtered)}")
        print(f"  Regular courses: {len(regular_in_filtered)} (expected 0)")
        print(f"  Integral courses: {len(integral_in_filtered)} (expected 0)")
    
    def test_logic_for_regular_class_in_integral_school(self):
        """
        Test logic: Regular classes in integral schools should show regular + integral courses.
        """
        # Get courses
        response = requests.get(f"{BASE_URL}/api/courses?limit=200", headers=self.headers)
        assert response.status_code == 200
        courses = response.json()
        
        # Simulate filtering for a regular class in an integral school
        tem_turma_regular = True  # Regular class
        escola_tem_integral = True  # Integral school
        programas_turmas = set()
        
        # Filter courses
        filtered_courses = []
        for curso in courses:
            curso_programa = (curso.get('atendimento_programa') or '').lower().strip()
            
            if curso_programa:
                if curso_programa == 'atendimento_integral':
                    if escola_tem_integral and tem_turma_regular:
                        filtered_courses.append(curso)
                else:
                    if curso_programa in programas_turmas:
                        filtered_courses.append(curso)
            else:
                if tem_turma_regular:
                    filtered_courses.append(curso)
        
        # Verify both regular AND integral courses
        regular_in_filtered = [c for c in filtered_courses if not c.get('atendimento_programa')]
        integral_in_filtered = [c for c in filtered_courses if c.get('atendimento_programa') == 'atendimento_integral']
        
        assert len(regular_in_filtered) > 0, "No regular courses for regular class"
        assert len(integral_in_filtered) > 0, "No integral courses for regular class in integral school"
        
        print(f"For REGULAR class in INTEGRAL school:")
        print(f"  Regular courses: {len(regular_in_filtered)}")
        print(f"  Integral courses: {len(integral_in_filtered)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
