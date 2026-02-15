#!/usr/bin/env python3
"""
SIGESC Grades System (Fase 4) - Specific Test Suite
Tests the exact scenarios mentioned in the review request
"""

import requests
import json
import os
from datetime import datetime

# Get backend URL from environment
BACKEND_URL = os.getenv('REACT_APP_BACKEND_URL', 'https://sigesc-data-insights.preview.emergentagent.com')
API_BASE = f"{BACKEND_URL}/api"

# Test credentials from review request
ADMIN_CREDENTIALS = {
    "email": "admin@sigesc.com",
    "password": "password"
}

class SIGESCFase4Tester:
    def __init__(self):
        self.admin_token = None
        
    def log(self, message):
        """Log test messages with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
        
    def login(self):
        """Login as admin"""
        self.log("🔐 Logging in as admin@sigesc.com...")
        
        try:
            response = requests.post(
                f"{API_BASE}/auth/login",
                json=ADMIN_CREDENTIALS,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get('access_token')
                user = data.get('user', {})
                self.log(f"✅ Login successful for {user.get('full_name', 'Admin')}")
                return True
            else:
                self.log(f"❌ Login failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            self.log(f"❌ Login error: {str(e)}")
            return False
    
    def get_headers(self):
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {self.admin_token}",
            "Content-Type": "application/json"
        }
    
    def test_courses_endpoint_detailed(self):
        """Test Courses endpoint as specified in review request"""
        self.log("\n📚 Testing Backend API - Courses endpoint (Review Requirement 1)")
        self.log("Requirement: GET /api/courses - verify returns all courses with proper fields (nivel_ensino, grade_levels, school_id)")
        
        response = requests.get(
            f"{API_BASE}/courses",
            headers=self.get_headers()
        )
        
        if response.status_code == 200:
            courses = response.json()
            self.log(f"✅ Successfully retrieved {len(courses)} courses")
            
            # Check each course for required fields
            required_fields = ['id', 'name', 'nivel_ensino', 'grade_levels', 'school_id']
            
            for i, course in enumerate(courses):
                self.log(f"\n   Course {i+1}: {course.get('name', 'N/A')}")
                
                for field in required_fields:
                    if field in course:
                        value = course[field]
                        if field == 'school_id' and value is None:
                            self.log(f"   ✅ {field}: null (global component)")
                        elif field == 'grade_levels' and isinstance(value, list):
                            self.log(f"   ✅ {field}: {value} (list)")
                        else:
                            self.log(f"   ✅ {field}: {value}")
                    else:
                        self.log(f"   ❌ {field}: MISSING")
                        return False
            
            # Check for fundamental_anos_iniciais components (as mentioned in review)
            fundamental_courses = [c for c in courses if c.get('nivel_ensino') == 'fundamental_anos_iniciais']
            self.log(f"\n   Found {len(fundamental_courses)} courses for 'fundamental_anos_iniciais'")
            
            expected_courses = ['Matemática', 'Língua Portuguesa', 'Arte', 'Educação Física', 'Ciências', 'História', 'Geografia', 'Ensino Religioso', 'Educação Ambiental e Clima']
            found_courses = [c['name'] for c in fundamental_courses]
            
            self.log(f"   Expected courses: {expected_courses}")
            self.log(f"   Found courses: {found_courses}")
            
            missing_courses = [c for c in expected_courses if c not in found_courses]
            if missing_courses:
                self.log(f"   ⚠️ Missing expected courses: {missing_courses}")
            else:
                self.log(f"   ✅ All expected courses found")
            
            return True
        else:
            self.log(f"❌ Failed to retrieve courses: {response.status_code} - {response.text}")
            return False
    
    def test_grades_by_class_specific(self):
        """Test specific class grades as mentioned in review request"""
        self.log("\n📊 Testing Backend API - Grades by Class (Review Requirement 2)")
        self.log("Requirement: GET /api/grades/by-class/{class_id}/{course_id}")
        self.log("Using class_id: 42a876e6-aea3-40a3-8660-e1ef44fc3c4a (3º Ano A)")
        
        # First get a course_id
        courses_response = requests.get(f"{API_BASE}/courses", headers=self.get_headers())
        if courses_response.status_code != 200:
            self.log("❌ Cannot get courses for testing")
            return False
        
        courses = courses_response.json()
        if not courses:
            self.log("❌ No courses available for testing")
            return False
        
        course_id = courses[0]['id']
        course_name = courses[0]['name']
        class_id = "42a876e6-aea3-40a3-8660-e1ef44fc3c4a"
        
        self.log(f"Using course: {course_name} (ID: {course_id})")
        
        response = requests.get(
            f"{API_BASE}/grades/by-class/{class_id}/{course_id}",
            headers=self.get_headers()
        )
        
        if response.status_code == 200:
            class_grades = response.json()
            self.log(f"✅ Successfully retrieved grades for class 3º Ano A")
            self.log(f"   Number of students in class: {len(class_grades)}")
            
            if class_grades:
                # Verify structure as mentioned in review
                student_data = class_grades[0]
                
                if 'student' in student_data and 'grade' in student_data:
                    student = student_data['student']
                    grade = student_data['grade']
                    
                    self.log(f"   ✅ Response structure correct (student + grade objects)")
                    self.log(f"   Student: {student.get('full_name', 'N/A')}")
                    self.log(f"   Enrollment: {student.get('enrollment_number', 'N/A')}")
                    
                    # Check grade data structure
                    expected_grade_fields = ['student_id', 'class_id', 'course_id', 'academic_year', 'b1', 'b2', 'b3', 'b4', 'final_average', 'status']
                    present_fields = [f for f in expected_grade_fields if f in grade]
                    missing_fields = [f for f in expected_grade_fields if f not in grade]
                    
                    self.log(f"   Grade fields present: {present_fields}")
                    if missing_fields:
                        self.log(f"   ⚠️ Grade fields missing: {missing_fields}")
                    
                    return True
                else:
                    self.log("❌ Invalid response structure - missing 'student' or 'grade' keys")
                    return False
            else:
                self.log("ℹ️ Class is empty (no students enrolled)")
                return True
                
        elif response.status_code == 404:
            self.log(f"❌ Class not found: {class_id}")
            return False
        else:
            self.log(f"❌ Failed to retrieve class grades: {response.status_code} - {response.text}")
            return False
    
    def test_weighted_average_formula(self):
        """Test the weighted average formula mentioned in review"""
        self.log("\n🧮 Testing Grade Calculation Formula (Review Requirement)")
        self.log("Formula: (B1×2 + B2×3 + B3×2 + B4×3) / 10")
        self.log("Passing grade: 5.0 or above")
        
        # Get test data
        courses_response = requests.get(f"{API_BASE}/courses", headers=self.get_headers())
        students_response = requests.get(f"{API_BASE}/students", headers=self.get_headers())
        
        if courses_response.status_code != 200 or students_response.status_code != 200:
            self.log("❌ Cannot get test data")
            return False
        
        courses = courses_response.json()
        students = students_response.json()
        
        if not courses or not students:
            self.log("❌ No courses or students available")
            return False
        
        course_id = courses[0]['id']
        student = students[0]
        class_id = "42a876e6-aea3-40a3-8660-e1ef44fc3c4a"
        
        # Test case 1: Passing grade
        self.log("\n   Test Case 1: Passing Grade")
        test_grades = {"b1": 7.0, "b2": 8.0, "b3": 6.0, "b4": 9.0}
        expected_avg = (7.0*2 + 8.0*3 + 6.0*2 + 9.0*3) / 10  # = 7.5
        
        grade_data = {
            "student_id": student['id'],
            "class_id": class_id,
            "course_id": course_id,
            "academic_year": 2025,
            **test_grades
        }
        
        response = requests.post(f"{API_BASE}/grades", json=grade_data, headers=self.get_headers())
        
        if response.status_code in [200, 201]:
            grade = response.json()
            actual_avg = grade.get('final_average')
            status = grade.get('status')
            
            self.log(f"   Grades: B1={test_grades['b1']}, B2={test_grades['b2']}, B3={test_grades['b3']}, B4={test_grades['b4']}")
            self.log(f"   Expected average: {expected_avg}")
            self.log(f"   Actual average: {actual_avg}")
            self.log(f"   Status: {status}")
            
            if actual_avg and abs(actual_avg - expected_avg) < 0.01:
                self.log("   ✅ Formula calculation correct")
            else:
                self.log("   ❌ Formula calculation incorrect")
                return False
            
            if expected_avg >= 5.0 and status == 'aprovado':
                self.log("   ✅ Status correctly set to 'aprovado'")
            else:
                self.log(f"   ❌ Status incorrect for average {expected_avg}")
                return False
            
            # Clean up
            requests.delete(f"{API_BASE}/grades/{grade['id']}", headers=self.get_headers())
            
        else:
            self.log(f"   ❌ Failed to create test grade: {response.status_code}")
            return False
        
        # Test case 2: Failing grade
        self.log("\n   Test Case 2: Failing Grade")
        test_grades_fail = {"b1": 3.0, "b2": 4.0, "b3": 2.0, "b4": 5.0}
        expected_avg_fail = (3.0*2 + 4.0*3 + 2.0*2 + 5.0*3) / 10  # = 3.5
        
        grade_data_fail = {
            "student_id": student['id'],
            "class_id": class_id,
            "course_id": course_id,
            "academic_year": 2025,
            **test_grades_fail
        }
        
        response = requests.post(f"{API_BASE}/grades", json=grade_data_fail, headers=self.get_headers())
        
        if response.status_code in [200, 201]:
            grade = response.json()
            actual_avg = grade.get('final_average')
            status = grade.get('status')
            
            self.log(f"   Grades: B1={test_grades_fail['b1']}, B2={test_grades_fail['b2']}, B3={test_grades_fail['b3']}, B4={test_grades_fail['b4']}")
            self.log(f"   Expected average: {expected_avg_fail}")
            self.log(f"   Actual average: {actual_avg}")
            self.log(f"   Status: {status}")
            
            if actual_avg and abs(actual_avg - expected_avg_fail) < 0.01:
                self.log("   ✅ Formula calculation correct")
            else:
                self.log("   ❌ Formula calculation incorrect")
                return False
            
            if expected_avg_fail < 5.0 and status in ['reprovado_nota', 'cursando']:
                self.log("   ✅ Status correctly set for failing grade")
            else:
                self.log(f"   ❌ Status incorrect for average {expected_avg_fail}")
                return False
            
            # Clean up
            requests.delete(f"{API_BASE}/grades/{grade['id']}", headers=self.get_headers())
            
        else:
            self.log(f"   ❌ Failed to create test grade: {response.status_code}")
            return False
        
        return True
    
    def run_fase4_tests(self):
        """Run all Fase 4 specific tests"""
        self.log("🚀 Starting SIGESC Grades System (Fase 4) Tests")
        self.log("Testing specific requirements from review request")
        self.log(f"🌐 Backend URL: {BACKEND_URL}")
        
        if not self.login():
            return False
        
        success = True
        
        # Test 1: Courses endpoint
        if not self.test_courses_endpoint_detailed():
            success = False
        
        # Test 2: Grades by class
        if not self.test_grades_by_class_specific():
            success = False
        
        # Test 3: Grade calculation formula
        if not self.test_weighted_average_formula():
            success = False
        
        # Final result
        self.log("\n" + "="*60)
        if success:
            self.log("🎉 All SIGESC Fase 4 tests completed successfully!")
            self.log("✅ Backend APIs ready for frontend integration")
        else:
            self.log("❌ Some Fase 4 tests failed - check logs above")
        self.log("="*60)
        
        return success

if __name__ == "__main__":
    tester = SIGESCFase4Tester()
    tester.run_fase4_tests()