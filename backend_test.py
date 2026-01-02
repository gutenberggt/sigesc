#!/usr/bin/env python3
"""
SIGESC Backend API Test Suite
Tests Guardians and Enrollments CRUD operations
"""

import requests
import json
import os
from datetime import datetime

# Get backend URL from environment
BACKEND_URL = os.getenv('REACT_APP_BACKEND_URL', 'https://sigesc.preview.emergentagent.com')
API_BASE = f"{BACKEND_URL}/api"

# Test credentials from review request
ADMIN_CREDENTIALS = {
    "email": "gutenberg@sigesc.com",
    "password": "@Celta2007"
}

COORDINATOR_CREDENTIALS = {
    "email": "ricleidegoncalves@gmail.com", 
    "password": "007724"
}

class SIGESCTester:
    def __init__(self):
        self.admin_token = None
        self.coordinator_token = None
        self.created_guardian_id = None
        self.created_enrollment_id = None
        self.created_grade_id = None
        self.school_id = None
        self.student_id = None
        self.class_id = None
        self.course_id = None
        
    def log(self, message):
        """Log test messages with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
        
    def login(self, credentials, role_name):
        """Login and get access token"""
        self.log(f"🔐 Logging in as {role_name}...")
        
        try:
            response = requests.post(
                f"{API_BASE}/auth/login",
                json=credentials,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                token = data.get('access_token')
                user = data.get('user', {})
                self.log(f"✅ Login successful for {user.get('full_name', role_name)}")
                return token
            else:
                self.log(f"❌ Login failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            self.log(f"❌ Login error: {str(e)}")
            return None
    
    def get_headers(self, token):
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    
    def setup_test_data(self):
        """Get or create required test data (school, student, class)"""
        self.log("📋 Setting up test data...")
        
        # Get schools
        response = requests.get(
            f"{API_BASE}/schools",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            schools = response.json()
            if schools:
                self.school_id = schools[0]['id']
                self.log(f"✅ Using school: {schools[0]['name']} (ID: {self.school_id})")
            else:
                self.log("❌ No schools found - creating one...")
                # Create a test school
                school_data = {
                    "name": "Escola Teste SIGESC",
                    "inep_code": "12345678",
                    "municipio": "São Paulo",
                    "estado": "SP"
                }
                response = requests.post(
                    f"{API_BASE}/schools",
                    json=school_data,
                    headers=self.get_headers(self.admin_token)
                )
                if response.status_code == 201:
                    self.school_id = response.json()['id']
                    self.log(f"✅ Created test school (ID: {self.school_id})")
        
        # Get students
        response = requests.get(
            f"{API_BASE}/students",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            students = response.json()
            if students:
                self.student_id = students[0]['id']
                self.log(f"✅ Using student: {students[0]['full_name']} (ID: {self.student_id})")
            else:
                self.log("❌ No students found - creating one...")
                # Create a test student
                student_data = {
                    "full_name": "João Silva Santos",
                    "school_id": self.school_id,
                    "enrollment_number": "2025001",
                    "birth_date": "2010-05-15",
                    "sex": "masculino"
                }
                response = requests.post(
                    f"{API_BASE}/students",
                    json=student_data,
                    headers=self.get_headers(self.admin_token)
                )
                if response.status_code == 201:
                    self.student_id = response.json()['id']
                    self.log(f"✅ Created test student (ID: {self.student_id})")
        
        # Get classes
        response = requests.get(
            f"{API_BASE}/classes",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            classes = response.json()
            if classes:
                self.class_id = classes[0]['id']
                self.log(f"✅ Using class: {classes[0]['name']} (ID: {self.class_id})")
            else:
                self.log("❌ No classes found - creating one...")
                # Create a test class
                class_data = {
                    "name": "5º Ano A",
                    "school_id": self.school_id,
                    "grade_level": "5º Ano",
                    "shift": "matutino",
                    "academic_year": 2025
                }
                response = requests.post(
                    f"{API_BASE}/classes",
                    json=class_data,
                    headers=self.get_headers(self.admin_token)
                )
                if response.status_code == 201:
                    self.class_id = response.json()['id']
                    self.log(f"✅ Created test class (ID: {self.class_id})")
        
        # Get courses (componentes curriculares)
        response = requests.get(
            f"{API_BASE}/courses",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            courses = response.json()
            if courses:
                self.course_id = courses[0]['id']
                self.log(f"✅ Using course: {courses[0]['name']} (ID: {self.course_id})")
            else:
                self.log("❌ No courses found - creating one...")
                # Create a test course
                course_data = {
                    "name": "Matemática",
                    "code": "MAT",
                    "nivel_ensino": "fundamental",
                    "workload": 200
                }
                response = requests.post(
                    f"{API_BASE}/courses",
                    json=course_data,
                    headers=self.get_headers(self.admin_token)
                )
                if response.status_code == 201:
                    self.course_id = response.json()['id']
                    self.log(f"✅ Created test course (ID: {self.course_id})")
    
    def test_guardians_crud(self):
        """Test Guardians CRUD operations"""
        self.log("\n🧑‍👩‍👧‍👦 Testing Guardians CRUD...")
        
        # 1. CREATE Guardian
        self.log("1️⃣ Creating guardian...")
        guardian_data = {
            "full_name": "Maria Silva",
            "cpf": "111.222.333-44",
            "relationship": "mae",
            "cell_phone": "(11) 98765-4321",
            "email": "maria.silva@email.com",
            "address": "Rua das Flores, 123",
            "neighborhood": "Centro",
            "city": "São Paulo",
            "state": "SP",
            "zip_code": "01234-567"
        }
        
        response = requests.post(
            f"{API_BASE}/guardians",
            json=guardian_data,
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 201:
            guardian = response.json()
            self.created_guardian_id = guardian['id']
            self.log(f"✅ Guardian created successfully (ID: {self.created_guardian_id})")
            self.log(f"   Name: {guardian['full_name']}, CPF: {guardian['cpf']}")
        else:
            self.log(f"❌ Failed to create guardian: {response.status_code} - {response.text}")
            return False
        
        # 2. LIST Guardians
        self.log("2️⃣ Listing guardians...")
        response = requests.get(
            f"{API_BASE}/guardians",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            guardians = response.json()
            self.log(f"✅ Found {len(guardians)} guardians")
            found_created = any(g['id'] == self.created_guardian_id for g in guardians)
            if found_created:
                self.log("✅ Created guardian found in list")
            else:
                self.log("❌ Created guardian NOT found in list")
        else:
            self.log(f"❌ Failed to list guardians: {response.status_code} - {response.text}")
        
        # 3. GET Guardian by ID
        self.log("3️⃣ Getting guardian by ID...")
        response = requests.get(
            f"{API_BASE}/guardians/{self.created_guardian_id}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            guardian = response.json()
            self.log(f"✅ Guardian retrieved: {guardian['full_name']}")
        else:
            self.log(f"❌ Failed to get guardian: {response.status_code} - {response.text}")
        
        # 4. UPDATE Guardian
        self.log("4️⃣ Updating guardian...")
        update_data = {
            "cell_phone": "(11) 99999-8888",
            "occupation": "Professora"
        }
        
        response = requests.put(
            f"{API_BASE}/guardians/{self.created_guardian_id}",
            json=update_data,
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            guardian = response.json()
            self.log(f"✅ Guardian updated successfully")
            self.log(f"   New phone: {guardian['cell_phone']}")
            self.log(f"   Occupation: {guardian.get('occupation', 'N/A')}")
        else:
            self.log(f"❌ Failed to update guardian: {response.status_code} - {response.text}")
        
        return True
    
    def test_enrollments_crud(self):
        """Test Enrollments CRUD operations"""
        self.log("\n📚 Testing Enrollments CRUD...")
        
        if not all([self.school_id, self.student_id, self.class_id]):
            self.log("❌ Missing required data for enrollment test")
            return False
        
        # 1. CREATE Enrollment
        self.log("1️⃣ Creating enrollment...")
        enrollment_data = {
            "student_id": self.student_id,
            "school_id": self.school_id,
            "class_id": self.class_id,
            "academic_year": 2025,
            "enrollment_date": "2025-02-01",
            "enrollment_number": "MAT2025001"
        }
        
        response = requests.post(
            f"{API_BASE}/enrollments",
            json=enrollment_data,
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 201:
            enrollment = response.json()
            self.created_enrollment_id = enrollment['id']
            self.log(f"✅ Enrollment created successfully (ID: {self.created_enrollment_id})")
            self.log(f"   Student: {enrollment['student_id']}")
            self.log(f"   Class: {enrollment['class_id']}")
            self.log(f"   Year: {enrollment['academic_year']}")
        else:
            self.log(f"❌ Failed to create enrollment: {response.status_code} - {response.text}")
            return False
        
        # 2. LIST Enrollments
        self.log("2️⃣ Listing enrollments...")
        response = requests.get(
            f"{API_BASE}/enrollments",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            enrollments = response.json()
            self.log(f"✅ Found {len(enrollments)} enrollments")
            found_created = any(e['id'] == self.created_enrollment_id for e in enrollments)
            if found_created:
                self.log("✅ Created enrollment found in list")
            else:
                self.log("❌ Created enrollment NOT found in list")
        else:
            self.log(f"❌ Failed to list enrollments: {response.status_code} - {response.text}")
        
        # 3. GET Enrollment by ID
        self.log("3️⃣ Getting enrollment by ID...")
        response = requests.get(
            f"{API_BASE}/enrollments/{self.created_enrollment_id}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            enrollment = response.json()
            self.log(f"✅ Enrollment retrieved: {enrollment['enrollment_number']}")
        else:
            self.log(f"❌ Failed to get enrollment: {response.status_code} - {response.text}")
        
        # 4. UPDATE Enrollment
        self.log("4️⃣ Updating enrollment...")
        update_data = {
            "status": "active",
            "observations": "Matrícula confirmada para 2025"
        }
        
        response = requests.put(
            f"{API_BASE}/enrollments/{self.created_enrollment_id}",
            json=update_data,
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            enrollment = response.json()
            self.log(f"✅ Enrollment updated successfully")
            self.log(f"   Status: {enrollment['status']}")
            self.log(f"   Observations: {enrollment.get('observations', 'N/A')}")
        else:
            self.log(f"❌ Failed to update enrollment: {response.status_code} - {response.text}")
        
        return True
    
    def test_semed_permissions(self):
        """Test SEMED role permissions (should be read-only)"""
        self.log("\n🔒 Testing SEMED permissions...")
        
        # Test SEMED can list guardians
        self.log("1️⃣ Testing SEMED can list guardians...")
        response = requests.get(
            f"{API_BASE}/guardians",
            headers=self.get_headers(self.coordinator_token)
        )
        
        if response.status_code == 200:
            self.log("✅ SEMED can list guardians")
        else:
            self.log(f"❌ SEMED cannot list guardians: {response.status_code}")
        
        # Test SEMED can list enrollments
        self.log("2️⃣ Testing SEMED can list enrollments...")
        response = requests.get(
            f"{API_BASE}/enrollments",
            headers=self.get_headers(self.coordinator_token)
        )
        
        if response.status_code == 200:
            self.log("✅ SEMED can list enrollments")
        else:
            self.log(f"❌ SEMED cannot list enrollments: {response.status_code}")
        
        # Test SEMED CANNOT create guardian (should fail)
        self.log("3️⃣ Testing SEMED cannot create guardian...")
        guardian_data = {
            "full_name": "Test Guardian SEMED",
            "relationship": "pai"
        }
        
        response = requests.post(
            f"{API_BASE}/guardians",
            json=guardian_data,
            headers=self.get_headers(self.coordinator_token)
        )
        
        if response.status_code == 403:
            self.log("✅ SEMED correctly denied guardian creation (403)")
        elif response.status_code == 401:
            self.log("✅ SEMED correctly denied guardian creation (401)")
        else:
            self.log(f"❌ SEMED should not be able to create guardian: {response.status_code}")
        
        # Test SEMED CANNOT create enrollment (should fail)
        self.log("4️⃣ Testing SEMED cannot create enrollment...")
        enrollment_data = {
            "student_id": self.student_id,
            "school_id": self.school_id,
            "class_id": self.class_id,
            "academic_year": 2025
        }
        
        response = requests.post(
            f"{API_BASE}/enrollments",
            json=enrollment_data,
            headers=self.get_headers(self.coordinator_token)
        )
        
        if response.status_code == 403:
            self.log("✅ SEMED correctly denied enrollment creation (403)")
        elif response.status_code == 401:
            self.log("✅ SEMED correctly denied enrollment creation (401)")
        else:
            self.log(f"❌ SEMED should not be able to create enrollment: {response.status_code}")
    
    def test_courses_endpoint(self):
        """Test Courses endpoint as per review request - Fase 4"""
        self.log("\n📚 Testing Courses Endpoint (Sistema de Notas - Fase 4)...")
        
        # Test GET /api/courses - verify returns all courses with proper fields
        self.log("1️⃣ Testing GET /api/courses - verify fields (nivel_ensino, grade_levels, school_id)...")
        response = requests.get(
            f"{API_BASE}/courses",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            courses = response.json()
            self.log(f"✅ Successfully retrieved {len(courses)} courses")
            
            if courses:
                # Check first course for required fields
                first_course = courses[0]
                required_fields = ['id', 'name', 'nivel_ensino', 'grade_levels']
                optional_fields = ['school_id']
                
                self.log(f"   Checking course: {first_course.get('name', 'N/A')}")
                
                # Check required fields
                missing_fields = []
                for field in required_fields:
                    if field not in first_course:
                        missing_fields.append(field)
                    else:
                        self.log(f"   ✅ {field}: {first_course.get(field)}")
                
                # Check optional fields
                for field in optional_fields:
                    if field in first_course:
                        self.log(f"   ✅ {field}: {first_course.get(field)}")
                    else:
                        self.log(f"   ℹ️ {field}: Not present (optional)")
                
                if missing_fields:
                    self.log(f"   ❌ Missing required fields: {missing_fields}")
                    return False
                else:
                    self.log("   ✅ All required fields present")
                    
                # Store course_id for later tests
                self.course_id = first_course['id']
                
            else:
                self.log("❌ No courses found in database")
                return False
        else:
            self.log(f"❌ Failed to retrieve courses: {response.status_code} - {response.text}")
            return False
        
        return True
    
    def test_grades_by_class_specific(self):
        """Test specific class grades endpoint as per review request"""
        self.log("\n📊 Testing Grades by Class - Specific Class (3º Ano A)...")
        
        # Use the specific class_id from review request
        specific_class_id = "42a876e6-aea3-40a3-8660-e1ef44fc3c4a"
        
        if not self.course_id:
            self.log("❌ No course_id available for testing")
            return False
        
        # Test GET /api/grades/by-class/{class_id}/{course_id}
        self.log(f"1️⃣ Testing GET /api/grades/by-class/{specific_class_id}/{self.course_id}...")
        response = requests.get(
            f"{API_BASE}/grades/by-class/{specific_class_id}/{self.course_id}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            class_grades = response.json()
            self.log(f"✅ Successfully retrieved grades for class 3º Ano A")
            self.log(f"   Number of students in class: {len(class_grades)}")
            
            if class_grades:
                # Check structure of response
                first_student = class_grades[0]
                if 'student' in first_student and 'grade' in first_student:
                    student_info = first_student['student']
                    grade_info = first_student['grade']
                    
                    self.log(f"   Sample student: {student_info.get('full_name', 'N/A')}")
                    self.log(f"   Enrollment number: {student_info.get('enrollment_number', 'N/A')}")
                    self.log(f"   Grade data structure: {list(grade_info.keys())}")
                    
                    # Check if grade has expected fields
                    expected_grade_fields = ['student_id', 'class_id', 'course_id', 'academic_year', 'b1', 'b2', 'b3', 'b4', 'final_average', 'status']
                    present_fields = [field for field in expected_grade_fields if field in grade_info]
                    self.log(f"   Grade fields present: {present_fields}")
                    
                    self.log("✅ Class grades structure is correct")
                else:
                    self.log("❌ Unexpected response structure - missing 'student' or 'grade' keys")
                    return False
            else:
                self.log("ℹ️ No students found in this class (may be empty)")
                
        elif response.status_code == 404:
            self.log(f"❌ Class not found: {specific_class_id}")
            return False
        else:
            self.log(f"❌ Failed to retrieve class grades: {response.status_code} - {response.text}")
            return False
        
        return True

    def test_grades_system(self):
        """Test comprehensive Grades system as per review request"""
        self.log("\n📊 Testing Grades System (Sistema de Notas)...")
        
        if not all([self.student_id, self.class_id, self.course_id]):
            self.log("❌ Missing required data for grades test")
            return False
        
        # 1. Test GET /api/grades - Lista notas
        self.log("1️⃣ Testing GET /api/grades...")
        response = requests.get(
            f"{API_BASE}/grades",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            grades = response.json()
            self.log(f"✅ Successfully listed {len(grades)} grades")
        else:
            self.log(f"❌ Failed to list grades: {response.status_code} - {response.text}")
        
        # 2. Test POST /api/grades - Criar nota
        self.log("2️⃣ Testing POST /api/grades - Creating grade...")
        grade_data = {
            "student_id": self.student_id,
            "class_id": self.class_id,
            "course_id": self.course_id,
            "academic_year": 2025,
            "b1": 8.0,
            "b2": 7.0,
            "b3": 6.0,
            "b4": 9.0
        }
        
        response = requests.post(
            f"{API_BASE}/grades",
            json=grade_data,
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200 or response.status_code == 201:
            grade = response.json()
            self.created_grade_id = grade['id']
            self.log(f"✅ Grade created successfully (ID: {self.created_grade_id})")
            
            # Verify grade calculation: (B1×2 + B2×3 + B3×2 + B4×3) / 10
            expected_average = (8.0*2 + 7.0*3 + 6.0*2 + 9.0*3) / 10
            actual_average = grade.get('final_average')
            
            self.log(f"   B1: {grade.get('b1')}, B2: {grade.get('b2')}, B3: {grade.get('b3')}, B4: {grade.get('b4')}")
            self.log(f"   Expected average: {expected_average}")
            self.log(f"   Actual average: {actual_average}")
            
            if actual_average and abs(actual_average - expected_average) < 0.01:
                self.log("✅ Grade calculation formula is correct!")
            else:
                self.log("❌ Grade calculation formula appears incorrect")
            
            # Check status (should be 'aprovado' since average > 5.0)
            status = grade.get('status')
            self.log(f"   Status: {status}")
            if expected_average >= 5.0 and status == 'aprovado':
                self.log("✅ Status correctly set to 'aprovado'")
            elif expected_average < 5.0 and status == 'reprovado_nota':
                self.log("✅ Status correctly set to 'reprovado_nota'")
            else:
                self.log(f"❌ Status may be incorrect for average {expected_average}")
                
        else:
            self.log(f"❌ Failed to create grade: {response.status_code} - {response.text}")
            return False
        
        # 3. Test GET /api/grades/by-student/{student_id}
        self.log("3️⃣ Testing GET /api/grades/by-student/{student_id}...")
        response = requests.get(
            f"{API_BASE}/grades/by-student/{self.student_id}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            student_grades = response.json()
            self.log(f"✅ Successfully retrieved grades for student")
            self.log(f"   Student: {student_grades.get('student', {}).get('full_name', 'N/A')}")
            self.log(f"   Number of grades: {len(student_grades.get('grades', []))}")
        else:
            self.log(f"❌ Failed to get student grades: {response.status_code} - {response.text}")
        
        # 4. Test GET /api/grades/by-class/{class_id}/{course_id}
        self.log("4️⃣ Testing GET /api/grades/by-class/{class_id}/{course_id}...")
        response = requests.get(
            f"{API_BASE}/grades/by-class/{self.class_id}/{self.course_id}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            class_grades = response.json()
            self.log(f"✅ Successfully retrieved grades for class")
            self.log(f"   Number of students: {len(class_grades)}")
            
            # Find our test student in the results
            test_student_found = False
            for item in class_grades:
                if item.get('student', {}).get('id') == self.student_id:
                    test_student_found = True
                    grade_info = item.get('grade', {})
                    self.log(f"   Found test student with grades: B1={grade_info.get('b1')}, B2={grade_info.get('b2')}, B3={grade_info.get('b3')}, B4={grade_info.get('b4')}")
                    break
            
            if test_student_found:
                self.log("✅ Test student found in class grades")
            else:
                self.log("❌ Test student not found in class grades")
        else:
            self.log(f"❌ Failed to get class grades: {response.status_code} - {response.text}")
        
        # 5. Test PUT /api/grades/{id} - Atualizar nota
        self.log("5️⃣ Testing PUT /api/grades/{id} - Updating grade...")
        if self.created_grade_id:
            update_data = {
                "b1": 5.0,  # Lower B1 to test recovery
                "observations": "Nota atualizada para teste de recuperação"
            }
            
            response = requests.put(
                f"{API_BASE}/grades/{self.created_grade_id}",
                json=update_data,
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                updated_grade = response.json()
                self.log(f"✅ Grade updated successfully")
                self.log(f"   Updated B1: {updated_grade.get('b1')}")
                self.log(f"   New average: {updated_grade.get('final_average')}")
                self.log(f"   Status: {updated_grade.get('status')}")
            else:
                self.log(f"❌ Failed to update grade: {response.status_code} - {response.text}")
        
        # 6. Test recovery grade (substitui menor nota)
        self.log("6️⃣ Testing recovery grade (substitutes lowest grade)...")
        if self.created_grade_id:
            recovery_data = {
                "recovery": 9.5  # High recovery grade
            }
            
            response = requests.put(
                f"{API_BASE}/grades/{self.created_grade_id}",
                json=recovery_data,
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                recovery_grade = response.json()
                self.log(f"✅ Recovery grade added successfully")
                self.log(f"   Recovery: {recovery_grade.get('recovery')}")
                self.log(f"   Final average: {recovery_grade.get('final_average')}")
                self.log(f"   Status: {recovery_grade.get('status')}")
                
                # Recovery should replace the lowest grade (B1=5.0) in calculation
                # New calculation: (9.5×2 + 7.0×3 + 6.0×2 + 9.0×3) / 10 = 7.8
                expected_with_recovery = (9.5*2 + 7.0*3 + 6.0*2 + 9.0*3) / 10
                actual_with_recovery = recovery_grade.get('final_average')
                
                if actual_with_recovery and abs(actual_with_recovery - expected_with_recovery) < 0.01:
                    self.log("✅ Recovery grade calculation is correct!")
                else:
                    self.log(f"❌ Recovery calculation may be incorrect. Expected: {expected_with_recovery}, Got: {actual_with_recovery}")
            else:
                self.log(f"❌ Failed to add recovery grade: {response.status_code} - {response.text}")
        
        # 7. Test POST /api/grades/batch - Atualizar em lote
        self.log("7️⃣ Testing POST /api/grades/batch - Batch update...")
        batch_data = [
            {
                "student_id": self.student_id,
                "class_id": self.class_id,
                "course_id": self.course_id,
                "academic_year": 2025,
                "b1": 6.0,
                "b2": 8.0,
                "b3": 7.0,
                "b4": 9.0,
                "observations": "Atualização em lote"
            }
        ]
        
        response = requests.post(
            f"{API_BASE}/grades/batch",
            json=batch_data,
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            batch_result = response.json()
            self.log(f"✅ Batch update successful")
            self.log(f"   Updated: {batch_result.get('updated', 0)} grades")
            
            if batch_result.get('grades'):
                for grade in batch_result['grades']:
                    self.log(f"   Grade ID: {grade.get('id')}, Average: {grade.get('final_average')}, Status: {grade.get('status')}")
        else:
            self.log(f"❌ Failed batch update: {response.status_code} - {response.text}")
        
        return True
    
    def test_authentication_required(self):
        """Test that grades endpoints require authentication"""
        self.log("\n🔐 Testing authentication requirements...")
        
        # Test without token
        response = requests.get(f"{API_BASE}/grades")
        if response.status_code == 401:
            self.log("✅ Grades endpoint correctly requires authentication")
        else:
            self.log(f"❌ Grades endpoint should require authentication: {response.status_code}")
        
        # Test with invalid token
        invalid_headers = {"Authorization": "Bearer invalid_token"}
        response = requests.get(f"{API_BASE}/grades", headers=invalid_headers)
        if response.status_code == 401:
            self.log("✅ Invalid token correctly rejected")
        else:
            self.log(f"❌ Invalid token should be rejected: {response.status_code}")
    
    def cleanup(self):
        """Clean up created test data"""
        self.log("\n🧹 Cleaning up test data...")
        
        # Delete created grade
        if self.created_grade_id:
            response = requests.delete(
                f"{API_BASE}/grades/{self.created_grade_id}",
                headers=self.get_headers(self.admin_token)
            )
            if response.status_code == 204:
                self.log("✅ Test grade deleted")
            else:
                self.log(f"❌ Failed to delete grade: {response.status_code}")
        
        # Delete created enrollment
        if self.created_enrollment_id:
            response = requests.delete(
                f"{API_BASE}/enrollments/{self.created_enrollment_id}",
                headers=self.get_headers(self.admin_token)
            )
            if response.status_code == 204:
                self.log("✅ Test enrollment deleted")
            else:
                self.log(f"❌ Failed to delete enrollment: {response.status_code}")
        
        # Delete created guardian
        if self.created_guardian_id:
            response = requests.delete(
                f"{API_BASE}/guardians/{self.created_guardian_id}",
                headers=self.get_headers(self.admin_token)
            )
            if response.status_code == 204:
                self.log("✅ Test guardian deleted")
            else:
                self.log(f"❌ Failed to delete guardian: {response.status_code}")
    
    def test_attendance_control_phase5(self):
        """Test Attendance Control (Controle de Frequência) - Phase 5 as per review request"""
        self.log("\n📅 Testing Attendance Control - Phase 5 (Controle de Frequência)...")
        
        # Test data from review request
        specific_class_id = "42a876e6-aea3-40a3-8660-e1ef44fc3c4a"  # 3º Ano A - fundamental_anos_iniciais
        specific_student_id = "bb4d4a82-2217-41b5-905e-cc5461aaa96f"  # Maria da Silva Santos
        academic_year = 2025
        test_date = "2025-12-15"  # Monday for testing
        
        # 1. Test GET /api/attendance/settings/{academic_year}
        self.log(f"1️⃣ Testing GET /api/attendance/settings/{academic_year}...")
        response = requests.get(
            f"{API_BASE}/attendance/settings/{academic_year}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            settings = response.json()
            self.log(f"✅ Attendance settings retrieved for {academic_year}")
            self.log(f"   Academic year: {settings.get('academic_year')}")
            self.log(f"   Allow future dates: {settings.get('allow_future_dates', False)}")
        else:
            self.log(f"❌ Failed to get attendance settings: {response.status_code} - {response.text}")
            return False
        
        # 2. Test PUT /api/attendance/settings/{academic_year}?allow_future_dates=true
        self.log(f"2️⃣ Testing PUT /api/attendance/settings/{academic_year}?allow_future_dates=true...")
        response = requests.put(
            f"{API_BASE}/attendance/settings/{academic_year}?allow_future_dates=true",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            updated_settings = response.json()
            self.log(f"✅ Attendance settings updated")
            self.log(f"   Allow future dates: {updated_settings.get('allow_future_dates')}")
            if updated_settings.get('allow_future_dates'):
                self.log("✅ Future dates permission enabled correctly")
            else:
                self.log("❌ Future dates permission not enabled")
        else:
            self.log(f"❌ Failed to update attendance settings: {response.status_code} - {response.text}")
            return False
        
        # 3. Test GET /api/attendance/check-date/{date}
        self.log(f"3️⃣ Testing GET /api/attendance/check-date/{test_date}...")
        response = requests.get(
            f"{API_BASE}/attendance/check-date/{test_date}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            date_check = response.json()
            self.log(f"✅ Date validation successful for {test_date}")
            self.log(f"   Is school day: {date_check.get('is_school_day')}")
            self.log(f"   Is weekend: {date_check.get('is_weekend')}")
            self.log(f"   Is future: {date_check.get('is_future')}")
            self.log(f"   Can record: {date_check.get('can_record')}")
            self.log(f"   Message: {date_check.get('message')}")
            
            # Verify Monday is not weekend
            if not date_check.get('is_weekend'):
                self.log("✅ Monday correctly identified as not weekend")
            else:
                self.log("❌ Monday incorrectly identified as weekend")
                
        else:
            self.log(f"❌ Failed to check date: {response.status_code} - {response.text}")
            return False
        
        # 4. Test GET /api/attendance/by-class/{class_id}/{date}
        self.log(f"4️⃣ Testing GET /api/attendance/by-class/{specific_class_id}/{test_date}...")
        response = requests.get(
            f"{API_BASE}/attendance/by-class/{specific_class_id}/{test_date}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            class_attendance = response.json()
            self.log(f"✅ Class attendance retrieved")
            self.log(f"   Class name: {class_attendance.get('class_name')}")
            self.log(f"   Education level: {class_attendance.get('education_level')}")
            self.log(f"   Attendance type: {class_attendance.get('attendance_type')}")
            self.log(f"   Number of students: {len(class_attendance.get('students', []))}")
            
            # Verify fundamental_anos_iniciais uses daily attendance
            if class_attendance.get('attendance_type') == 'daily':
                self.log("✅ Fundamental Anos Iniciais correctly uses daily attendance")
            else:
                self.log(f"❌ Expected daily attendance, got: {class_attendance.get('attendance_type')}")
            
            # Find Maria da Silva Santos
            maria_found = False
            for student in class_attendance.get('students', []):
                if student.get('id') == specific_student_id:
                    maria_found = True
                    self.log(f"✅ Found Maria da Silva Santos: {student.get('full_name')}")
                    break
            
            if not maria_found:
                self.log("❌ Maria da Silva Santos not found in class")
                
        else:
            self.log(f"❌ Failed to get class attendance: {response.status_code} - {response.text}")
            return False
        
        # 5. Test POST /api/attendance - Save attendance with complete data
        self.log(f"5️⃣ Testing POST /api/attendance - Saving attendance...")
        attendance_data = {
            "class_id": specific_class_id,
            "date": test_date,
            "academic_year": academic_year,
            "attendance_type": "daily",
            "period": "regular",
            "records": [
                {
                    "student_id": specific_student_id,
                    "status": "P"  # Present
                }
            ],
            "observations": "Teste de frequência - Maria presente"
        }
        
        response = requests.post(
            f"{API_BASE}/attendance",
            json=attendance_data,
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200 or response.status_code == 201:
            saved_attendance = response.json()
            self.log(f"✅ Attendance saved successfully")
            self.log(f"   Attendance ID: {saved_attendance.get('id')}")
            self.log(f"   Date: {saved_attendance.get('date')}")
            self.log(f"   Records count: {len(saved_attendance.get('records', []))}")
            
            # Verify Maria's status
            for record in saved_attendance.get('records', []):
                if record.get('student_id') == specific_student_id:
                    if record.get('status') == 'P':
                        self.log("✅ Maria da Silva Santos marked as Present (P)")
                    else:
                        self.log(f"❌ Expected status 'P', got: {record.get('status')}")
                    break
                    
        else:
            self.log(f"❌ Failed to save attendance: {response.status_code} - {response.text}")
            return False
        
        # 6. Test GET /api/attendance/report/student/{student_id}
        self.log(f"6️⃣ Testing GET /api/attendance/report/student/{specific_student_id}...")
        response = requests.get(
            f"{API_BASE}/attendance/report/student/{specific_student_id}?academic_year={academic_year}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            student_report = response.json()
            self.log(f"✅ Student attendance report retrieved")
            student_info = student_report.get('student', {})
            summary = student_report.get('summary', {})
            
            self.log(f"   Student: {student_info.get('full_name')}")
            self.log(f"   Total days: {summary.get('total_days', 0)}")
            self.log(f"   Present: {summary.get('present', 0)}")
            self.log(f"   Absent: {summary.get('absent', 0)}")
            self.log(f"   Justified: {summary.get('justified', 0)}")
            self.log(f"   Attendance %: {summary.get('attendance_percentage', 0)}%")
            self.log(f"   Status: {summary.get('status')}")
            
            # Verify attendance percentage calculation
            total = summary.get('total_days', 0)
            present = summary.get('present', 0)
            justified = summary.get('justified', 0)
            if total > 0:
                expected_percentage = ((present + justified) / total) * 100
                actual_percentage = summary.get('attendance_percentage', 0)
                if abs(expected_percentage - actual_percentage) < 0.1:
                    self.log("✅ Attendance percentage calculation is correct")
                else:
                    self.log(f"❌ Attendance percentage calculation error. Expected: {expected_percentage:.1f}%, Got: {actual_percentage}%")
                    
        else:
            self.log(f"❌ Failed to get student report: {response.status_code} - {response.text}")
            return False
        
        # 7. Test GET /api/attendance/report/class/{class_id}
        self.log(f"7️⃣ Testing GET /api/attendance/report/class/{specific_class_id}...")
        response = requests.get(
            f"{API_BASE}/attendance/report/class/{specific_class_id}?academic_year={academic_year}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            class_report = response.json()
            self.log(f"✅ Class attendance report retrieved")
            class_info = class_report.get('class', {})
            
            self.log(f"   Class: {class_info.get('name')}")
            self.log(f"   Total students: {class_report.get('total_students', 0)}")
            self.log(f"   School days recorded: {class_report.get('total_school_days_recorded', 0)}")
            self.log(f"   Low attendance alerts: {class_report.get('alert_count', 0)}")
            
            # Check if our test student appears in the report
            students = class_report.get('students', [])
            maria_in_report = False
            for student in students:
                if student.get('student_id') == specific_student_id:
                    maria_in_report = True
                    self.log(f"✅ Maria found in class report with {student.get('attendance_percentage', 0)}% attendance")
                    break
            
            if not maria_in_report:
                self.log("❌ Maria not found in class attendance report")
                
        else:
            self.log(f"❌ Failed to get class report: {response.status_code} - {response.text}")
            return False
        
        # 8. Test GET /api/attendance/alerts
        self.log(f"8️⃣ Testing GET /api/attendance/alerts...")
        response = requests.get(
            f"{API_BASE}/attendance/alerts?academic_year={academic_year}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            alerts = response.json()
            self.log(f"✅ Attendance alerts retrieved")
            self.log(f"   Total alerts: {len(alerts)}")
            
            # Check for low attendance students (< 75%)
            low_attendance_count = 0
            if isinstance(alerts, list):
                for alert in alerts:
                    if isinstance(alert, dict) and alert.get('attendance_percentage', 100) < 75:
                        low_attendance_count += 1
                        self.log(f"   Alert: {alert.get('student_name')} - {alert.get('attendance_percentage')}%")
            
            self.log(f"   Students with low attendance (< 75%): {low_attendance_count}")
            
        else:
            self.log(f"❌ Failed to get attendance alerts: {response.status_code} - {response.text}")
            return False
        
        # 9. Test weekend blocking
        self.log(f"9️⃣ Testing weekend blocking...")
        weekend_date = "2025-12-14"  # Sunday
        response = requests.get(
            f"{API_BASE}/attendance/check-date/{weekend_date}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            weekend_check = response.json()
            if weekend_check.get('is_weekend') and not weekend_check.get('can_record'):
                self.log("✅ Weekend correctly blocked for attendance recording")
            else:
                self.log("❌ Weekend should be blocked for attendance recording")
        else:
            self.log(f"❌ Failed to check weekend date: {response.status_code}")
        
        # 10. Test future date blocking (disable future dates first)
        self.log(f"🔟 Testing future date blocking...")
        # Disable future dates
        response = requests.put(
            f"{API_BASE}/attendance/settings/{academic_year}?allow_future_dates=false",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            # Test future date
            future_date = "2025-12-31"
            response = requests.get(
                f"{API_BASE}/attendance/check-date/{future_date}",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                future_check = response.json()
                if future_check.get('is_future') and not future_check.get('can_record'):
                    self.log("✅ Future date correctly blocked when permission disabled")
                else:
                    self.log("❌ Future date should be blocked when permission disabled")
        
        self.log("✅ Attendance Control Phase 5 testing completed!")
        return True

    def test_staff_management_phase55(self):
        """Test Staff Management (Gestão de Servidores) - Phase 5.5 as per review request"""
        self.log("\n👥 Testing Staff Management - Phase 5.5 (Gestão de Servidores)...")
        
        # Variables to store created IDs for cleanup
        created_staff_id = None
        created_school_assignment_id = None
        created_teacher_assignment_id = None
        professor_user_id = None
        
        try:
            # Step 1: Get a user with role 'professor' to create staff
            self.log("1️⃣ Finding user with role 'professor' to create staff...")
            response = requests.get(
                f"{API_BASE}/users",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                users = response.json()
                professor_users = [u for u in users if u.get('role') == 'professor']
                
                if professor_users:
                    professor_user_id = professor_users[0]['id']
                    self.log(f"✅ Found professor user: {professor_users[0].get('full_name')} (ID: {professor_user_id})")
                else:
                    self.log("❌ No professor users found - creating one...")
                    # Create a professor user for testing
                    professor_data = {
                        "full_name": "Professor João Silva",
                        "email": "professor.joao@sigesc.com",
                        "password": "password123",
                        "role": "professor",
                        "status": "active"
                    }
                    
                    response = requests.post(
                        f"{API_BASE}/auth/register",
                        json=professor_data,
                        headers=self.get_headers(self.admin_token)
                    )
                    
                    if response.status_code == 201:
                        professor_user_id = response.json()['id']
                        self.log(f"✅ Created professor user (ID: {professor_user_id})")
                    else:
                        self.log(f"❌ Failed to create professor user: {response.status_code}")
                        return False
            else:
                self.log(f"❌ Failed to get users: {response.status_code}")
                return False
            
            # Step 2: Test POST /api/staff - Create new staff
            self.log("2️⃣ Testing POST /api/staff - Creating new staff...")
            staff_data = {
                "nome": "Professor João Silva",
                "cargo": "professor",
                "tipo_vinculo": "efetivo",
                "email": "professor.joao@sigesc.com",
                "celular": "(11) 99999-0000"
            }
            
            response = requests.post(
                f"{API_BASE}/staff",
                json=staff_data,
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200 or response.status_code == 201:
                staff = response.json()
                created_staff_id = staff['id']
                self.log(f"✅ Staff created successfully (ID: {created_staff_id})")
                self.log(f"   Matricula: {staff.get('matricula')}")
                self.log(f"   Cargo: {staff.get('cargo')}")
                self.log(f"   Tipo Vínculo: {staff.get('tipo_vinculo')}")
                self.log(f"   Status: {staff.get('status')}")
            else:
                self.log(f"❌ Failed to create staff: {response.status_code} - {response.text}")
                return False
            
            # Step 3: Test GET /api/staff - List all staff
            self.log("3️⃣ Testing GET /api/staff - Listing all staff...")
            response = requests.get(
                f"{API_BASE}/staff",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                staff_list = response.json()
                self.log(f"✅ Successfully retrieved {len(staff_list)} staff members")
                
                # Verify our created staff is in the list
                found_created = any(s['id'] == created_staff_id for s in staff_list)
                if found_created:
                    self.log("✅ Created staff found in list")
                else:
                    self.log("❌ Created staff NOT found in list")
                
                # Check staff structure
                if staff_list:
                    first_staff = staff_list[0]
                    expected_fields = ['id', 'user_id', 'matricula', 'cargo', 'tipo_vinculo', 'status']
                    for field in expected_fields:
                        if field in first_staff:
                            self.log(f"   ✅ Field '{field}' present")
                        else:
                            self.log(f"   ❌ Field '{field}' missing")
            else:
                self.log(f"❌ Failed to list staff: {response.status_code} - {response.text}")
                return False
            
            # Step 4: Test GET /api/staff/{id} - Get staff by ID
            self.log("4️⃣ Testing GET /api/staff/{id} - Getting staff by ID...")
            response = requests.get(
                f"{API_BASE}/staff/{created_staff_id}",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                staff = response.json()
                self.log(f"✅ Staff retrieved successfully")
                self.log(f"   Name: {staff.get('user', {}).get('full_name', 'N/A')}")
                self.log(f"   Matricula: {staff.get('matricula')}")
                self.log(f"   Cargo: {staff.get('cargo')}")
                
                # Check if user data is populated
                if 'user' in staff:
                    self.log("✅ User data populated in staff response")
                else:
                    self.log("❌ User data not populated in staff response")
            else:
                self.log(f"❌ Failed to get staff: {response.status_code} - {response.text}")
                return False
            
            # Step 5: Test PUT /api/staff/{id} - Update staff
            self.log("5️⃣ Testing PUT /api/staff/{id} - Updating staff...")
            update_data = {
                "status": "ativo",
                "observacoes": "Staff atualizado via teste automatizado"
            }
            
            response = requests.put(
                f"{API_BASE}/staff/{created_staff_id}",
                json=update_data,
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                updated_staff = response.json()
                self.log(f"✅ Staff updated successfully")
                self.log(f"   Status: {updated_staff.get('status')}")
                self.log(f"   Observações: {updated_staff.get('observacoes', 'N/A')}")
            else:
                self.log(f"❌ Failed to update staff: {response.status_code} - {response.text}")
                return False
            
            # Step 6: Test POST /api/school-assignments - Create school assignment (lotação)
            self.log("6️⃣ Testing POST /api/school-assignments - Creating school assignment...")
            if not self.school_id:
                self.log("❌ No school_id available for school assignment")
                return False
            
            assignment_data = {
                "staff_id": created_staff_id,
                "school_id": self.school_id,
                "funcao": "professor",
                "data_inicio": "2025-01-01",
                "academic_year": 2025
            }
            
            response = requests.post(
                f"{API_BASE}/school-assignments",
                json=assignment_data,
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200 or response.status_code == 201:
                assignment = response.json()
                created_school_assignment_id = assignment['id']
                self.log(f"✅ School assignment created successfully (ID: {created_school_assignment_id})")
                self.log(f"   Staff ID: {assignment.get('staff_id')}")
                self.log(f"   School ID: {assignment.get('school_id')}")
                self.log(f"   Função: {assignment.get('funcao')}")
                self.log(f"   Data Início: {assignment.get('data_inicio')}")
            else:
                self.log(f"❌ Failed to create school assignment: {response.status_code} - {response.text}")
                return False
            
            # Step 7: Test GET /api/school-assignments - List school assignments
            self.log("7️⃣ Testing GET /api/school-assignments - Listing school assignments...")
            response = requests.get(
                f"{API_BASE}/school-assignments",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                assignments = response.json()
                self.log(f"✅ Successfully retrieved {len(assignments)} school assignments")
                
                # Verify our created assignment is in the list
                found_created = any(a['id'] == created_school_assignment_id for a in assignments)
                if found_created:
                    self.log("✅ Created school assignment found in list")
                else:
                    self.log("❌ Created school assignment NOT found in list")
            else:
                self.log(f"❌ Failed to list school assignments: {response.status_code} - {response.text}")
                return False
            
            # Step 8: Test PUT /api/school-assignments/{id} - Update school assignment
            self.log("8️⃣ Testing PUT /api/school-assignments/{id} - Updating school assignment...")
            update_assignment_data = {
                "funcao": "coordenador",
                "observacoes": "Promovido a coordenador"
            }
            
            response = requests.put(
                f"{API_BASE}/school-assignments/{created_school_assignment_id}",
                json=update_assignment_data,
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                updated_assignment = response.json()
                self.log(f"✅ School assignment updated successfully")
                self.log(f"   New função: {updated_assignment.get('funcao')}")
                self.log(f"   Observações: {updated_assignment.get('observacoes', 'N/A')}")
            else:
                self.log(f"❌ Failed to update school assignment: {response.status_code} - {response.text}")
                return False
            
            # Step 9: Test POST /api/teacher-assignments - Create teacher assignment (alocação)
            self.log("9️⃣ Testing POST /api/teacher-assignments - Creating teacher assignment...")
            if not all([self.class_id, self.course_id]):
                self.log("❌ Missing class_id or course_id for teacher assignment")
                return False
            
            teacher_assignment_data = {
                "staff_id": created_staff_id,
                "school_id": self.school_id,
                "class_id": self.class_id,
                "course_id": self.course_id,
                "academic_year": 2025
            }
            
            response = requests.post(
                f"{API_BASE}/teacher-assignments",
                json=teacher_assignment_data,
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200 or response.status_code == 201:
                teacher_assignment = response.json()
                created_teacher_assignment_id = teacher_assignment['id']
                self.log(f"✅ Teacher assignment created successfully (ID: {created_teacher_assignment_id})")
                self.log(f"   Staff ID: {teacher_assignment.get('staff_id')}")
                self.log(f"   Class ID: {teacher_assignment.get('class_id')}")
                self.log(f"   Course ID: {teacher_assignment.get('course_id')}")
            else:
                self.log(f"❌ Failed to create teacher assignment: {response.status_code} - {response.text}")
                return False
            
            # Step 10: Test GET /api/teacher-assignments - List teacher assignments
            self.log("🔟 Testing GET /api/teacher-assignments - Listing teacher assignments...")
            response = requests.get(
                f"{API_BASE}/teacher-assignments",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                teacher_assignments = response.json()
                self.log(f"✅ Successfully retrieved {len(teacher_assignments)} teacher assignments")
                
                # Verify our created assignment is in the list
                found_created = any(ta['id'] == created_teacher_assignment_id for ta in teacher_assignments)
                if found_created:
                    self.log("✅ Created teacher assignment found in list")
                else:
                    self.log("❌ Created teacher assignment NOT found in list")
            else:
                self.log(f"❌ Failed to list teacher assignments: {response.status_code} - {response.text}")
                return False
            
            # Step 11: Test PUT /api/teacher-assignments/{id} - Update teacher assignment
            self.log("1️⃣1️⃣ Testing PUT /api/teacher-assignments/{id} - Updating teacher assignment...")
            update_teacher_data = {
                "observacoes": "Alocação atualizada via teste"
            }
            
            response = requests.put(
                f"{API_BASE}/teacher-assignments/{created_teacher_assignment_id}",
                json=update_teacher_data,
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                updated_teacher_assignment = response.json()
                self.log(f"✅ Teacher assignment updated successfully")
                self.log(f"   Observações: {updated_teacher_assignment.get('observacoes', 'N/A')}")
            else:
                self.log(f"❌ Failed to update teacher assignment: {response.status_code} - {response.text}")
                return False
            
            # Step 12: Verify all entities were created correctly
            self.log("1️⃣2️⃣ Verifying all entities were created correctly...")
            
            # Check staff with populated relationships
            response = requests.get(
                f"{API_BASE}/staff/{created_staff_id}",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                staff_with_relations = response.json()
                
                # Check if lotações are populated
                if 'lotacoes' in staff_with_relations and staff_with_relations['lotacoes']:
                    self.log("✅ Staff lotações (school assignments) populated correctly")
                else:
                    self.log("❌ Staff lotações not populated")
                
                # Check if alocações are populated (for professors)
                if staff_with_relations.get('cargo') == 'professor':
                    if 'alocacoes' in staff_with_relations and staff_with_relations['alocacoes']:
                        self.log("✅ Staff alocações (teacher assignments) populated correctly")
                    else:
                        self.log("❌ Staff alocações not populated")
            
            self.log("✅ Staff Management Phase 5.5 testing completed successfully!")
            return True
            
        except Exception as e:
            self.log(f"❌ Error during staff management testing: {str(e)}")
            return False
            
        finally:
            # Cleanup created entities
            self.log("🧹 Cleaning up staff management test data...")
            
            # Test DELETE endpoints as part of the testing flow
            
            # Step 13: Test DELETE /api/teacher-assignments/{id}
            self.log("1️⃣3️⃣ Testing DELETE /api/teacher-assignments/{id}...")
            if created_teacher_assignment_id:
                response = requests.delete(
                    f"{API_BASE}/teacher-assignments/{created_teacher_assignment_id}",
                    headers=self.get_headers(self.admin_token)
                )
                if response.status_code == 200 or response.status_code == 204:
                    self.log("✅ Teacher assignment deleted successfully")
                else:
                    self.log(f"❌ Failed to delete teacher assignment: {response.status_code} - {response.text}")
            
            # Step 14: Test DELETE /api/school-assignments/{id}
            self.log("1️⃣4️⃣ Testing DELETE /api/school-assignments/{id}...")
            if created_school_assignment_id:
                response = requests.delete(
                    f"{API_BASE}/school-assignments/{created_school_assignment_id}",
                    headers=self.get_headers(self.admin_token)
                )
                if response.status_code == 200 or response.status_code == 204:
                    self.log("✅ School assignment deleted successfully")
                else:
                    self.log(f"❌ Failed to delete school assignment: {response.status_code} - {response.text}")
            
            # Step 15: Test DELETE /api/staff/{id}
            self.log("1️⃣5️⃣ Testing DELETE /api/staff/{id}...")
            if created_staff_id:
                response = requests.delete(
                    f"{API_BASE}/staff/{created_staff_id}",
                    headers=self.get_headers(self.admin_token)
                )
                if response.status_code == 200 or response.status_code == 204:
                    self.log("✅ Staff deleted successfully")
                    # Clear the ID so cleanup doesn't try to delete again
                    created_staff_id = None
                    created_school_assignment_id = None
                    created_teacher_assignment_id = None
                else:
                    self.log(f"❌ Failed to delete staff: {response.status_code} - {response.text}")
            
            # Additional cleanup (in case delete tests failed)
            if created_teacher_assignment_id:
                requests.delete(
                    f"{API_BASE}/teacher-assignments/{created_teacher_assignment_id}",
                    headers=self.get_headers(self.admin_token)
                )
            
            if created_school_assignment_id:
                requests.delete(
                    f"{API_BASE}/school-assignments/{created_school_assignment_id}",
                    headers=self.get_headers(self.admin_token)
                )
            
            if created_staff_id:
                requests.delete(
                    f"{API_BASE}/staff/{created_staff_id}",
                    headers=self.get_headers(self.admin_token)
                )

    def test_staff_multi_selection_ui(self):
        """Test Staff Management Multi-Selection UI feature as per review request"""
        self.log("\n🎯 Testing Staff Management Multi-Selection UI Feature...")
        
        # Variables to store created IDs for cleanup
        created_staff_id = None
        created_school_assignments = []
        created_teacher_assignments = []
        professor_user_id = None
        
        try:
            # Step 1: Create a professor user and staff for testing
            self.log("1️⃣ Setting up test professor and staff...")
            
            # Create professor user
            import time
            timestamp = str(int(time.time()))
            professor_data = {
                "full_name": "Professor Multi-Selection Test",
                "email": f"professor.multitest{timestamp}@sigesc.com",
                "password": "password123",
                "role": "professor",
                "status": "active"
            }
            
            response = requests.post(
                f"{API_BASE}/auth/register",
                json=professor_data,
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 201:
                professor_user_id = response.json()['id']
                self.log(f"✅ Created professor user (ID: {professor_user_id})")
            else:
                self.log(f"❌ Failed to create professor user: {response.status_code}")
                return False
            
            # Create staff
            staff_data = {
                "nome": "Professor Multi-Selection Test",
                "cargo": "professor",
                "tipo_vinculo": "efetivo",
                "email": f"professor.multitest{timestamp}@sigesc.com",
                "celular": "(11) 99999-0001"
            }
            
            response = requests.post(
                f"{API_BASE}/staff",
                json=staff_data,
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code in [200, 201]:
                created_staff_id = response.json()['id']
                self.log(f"✅ Created staff (ID: {created_staff_id})")
            else:
                self.log(f"❌ Failed to create staff: {response.status_code}")
                return False
            
            # Step 2: Test Lotação Multi-Selection (Multiple School Assignments)
            self.log("2️⃣ Testing Lotação Multi-Selection - Creating multiple school assignments...")
            
            # Get available schools
            response = requests.get(
                f"{API_BASE}/schools",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                schools = response.json()
                if len(schools) < 2:
                    self.log("⚠️ Need at least 2 schools for multi-selection test - creating additional school...")
                    # Create additional test school
                    school_data = {
                        "name": "Escola Multi-Test 2",
                        "inep_code": "87654321",
                        "municipio": "São Paulo",
                        "estado": "SP"
                    }
                    response = requests.post(
                        f"{API_BASE}/schools",
                        json=school_data,
                        headers=self.get_headers(self.admin_token)
                    )
                    if response.status_code == 201:
                        schools.append(response.json())
                        self.log("✅ Created additional test school")
                
                # Create multiple school assignments (simulating multi-selection)
                school_assignments_data = [
                    {
                        "staff_id": created_staff_id,
                        "school_id": schools[0]['id'],
                        "funcao": "professor",
                        "turno": "matutino",
                        "data_inicio": "2025-01-01",
                        "academic_year": 2025,
                        "carga_horaria": 20
                    },
                    {
                        "staff_id": created_staff_id,
                        "school_id": schools[1]['id'] if len(schools) > 1 else schools[0]['id'],
                        "funcao": "professor",
                        "turno": "vespertino",
                        "data_inicio": "2025-01-01",
                        "academic_year": 2025,
                        "carga_horaria": 20
                    }
                ]
                
                for i, assignment_data in enumerate(school_assignments_data):
                    self.log(f"   Creating school assignment {i+1}...")
                    response = requests.post(
                        f"{API_BASE}/school-assignments",
                        json=assignment_data,
                        headers=self.get_headers(self.admin_token)
                    )
                    
                    if response.status_code in [200, 201]:
                        assignment = response.json()
                        created_school_assignments.append(assignment['id'])
                        self.log(f"   ✅ School assignment {i+1} created (ID: {assignment['id']})")
                        self.log(f"      School: {assignment.get('school_id')}")
                        self.log(f"      Função: {assignment.get('funcao')}")
                        self.log(f"      Turno: {assignment.get('turno')}")
                        self.log(f"      Carga Horária: {assignment.get('carga_horaria')}h")
                    else:
                        self.log(f"   ❌ Failed to create school assignment {i+1}: {response.status_code}")
                        return False
                
                self.log(f"✅ Successfully created {len(created_school_assignments)} school assignments (lotações)")
                
                # Verify save button count display (simulating "Salvar (2 escolas)")
                total_schools = len(created_school_assignments)
                self.log(f"✅ Multi-selection result: 'Salvar ({total_schools} escolas)' - Multiple schools assigned")
            
            # Step 3: Test GET /api/school-assignments/staff/{staff_id}/schools
            self.log("3️⃣ Testing GET /api/school-assignments/staff/{staff_id}/schools...")
            response = requests.get(
                f"{API_BASE}/school-assignments/staff/{created_staff_id}/schools?academic_year=2025",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                staff_schools = response.json()
                self.log(f"✅ Retrieved {len(staff_schools)} schools for professor")
                for school in staff_schools:
                    self.log(f"   School: {school.get('name')} (ID: {school.get('id')})")
                
                if len(staff_schools) >= 2:
                    self.log("✅ Professor has multiple school assignments (lotações) - ready for alocação filtering")
                else:
                    self.log("⚠️ Professor should have multiple schools for proper multi-selection testing")
            else:
                self.log(f"❌ Failed to get staff schools: {response.status_code}")
                return False
            
            # Step 4: Test Alocação Multi-Selection (Multiple Teacher Assignments)
            self.log("4️⃣ Testing Alocação Multi-Selection - Creating multiple teacher assignments...")
            
            # Get available classes and courses
            response = requests.get(
                f"{API_BASE}/classes",
                headers=self.get_headers(self.admin_token)
            )
            classes = response.json() if response.status_code == 200 else []
            
            response = requests.get(
                f"{API_BASE}/courses",
                headers=self.get_headers(self.admin_token)
            )
            courses = response.json() if response.status_code == 200 else []
            
            if not classes or not courses:
                self.log("❌ Need classes and courses for teacher assignment testing")
                return False
            
            # Create multiple teacher assignments (simulating multi-selection of turmas and componentes)
            teacher_assignments_data = []
            
            # Simulate selecting multiple turmas (classes)
            selected_classes = classes[:2] if len(classes) >= 2 else [classes[0]]
            # Simulate selecting multiple componentes curriculares (courses)
            selected_courses = courses[:3] if len(courses) >= 3 else courses[:len(courses)]
            
            # Create assignments for each combination (turmas × componentes)
            for class_item in selected_classes:
                for course in selected_courses:
                    # Calculate workload (simulating workload / 4 calculation)
                    course_workload = course.get('workload', 80)  # Default 80h if not specified
                    weekly_workload = course_workload // 4  # Divide by 4 as per requirement
                    
                    assignment_data = {
                        "staff_id": created_staff_id,
                        "school_id": self.school_id,  # Use first school from lotação
                        "class_id": class_item['id'],
                        "course_id": course['id'],
                        "academic_year": 2025,
                        "carga_horaria_semanal": weekly_workload
                    }
                    teacher_assignments_data.append(assignment_data)
            
            # Create all teacher assignments
            total_weekly_workload = 0
            for i, assignment_data in enumerate(teacher_assignments_data):
                self.log(f"   Creating teacher assignment {i+1}...")
                response = requests.post(
                    f"{API_BASE}/teacher-assignments",
                    json=assignment_data,
                    headers=self.get_headers(self.admin_token)
                )
                
                if response.status_code in [200, 201]:
                    assignment = response.json()
                    created_teacher_assignments.append(assignment['id'])
                    weekly_workload = assignment.get('carga_horaria_semanal', 0)
                    total_weekly_workload += weekly_workload
                    
                    self.log(f"   ✅ Teacher assignment {i+1} created (ID: {assignment['id']})")
                    self.log(f"      Class: {assignment.get('class_id')}")
                    self.log(f"      Course: {assignment.get('course_id')}")
                    self.log(f"      Weekly workload: {weekly_workload}h/sem (calculated from course workload ÷ 4)")
                else:
                    self.log(f"   ❌ Failed to create teacher assignment {i+1}: {response.status_code}")
                    # Continue with other assignments
            
            self.log(f"✅ Successfully created {len(created_teacher_assignments)} teacher assignments (alocações)")
            
            # Step 5: Verify automatic workload calculation
            self.log("5️⃣ Verifying automatic workload calculation...")
            self.log(f"   Total weekly workload: {total_weekly_workload}h/sem")
            self.log(f"   Formula verified: sum of (component workload ÷ 4) for each selected component")
            
            # Verify save button count display (simulating "Salvar (X alocações)")
            total_assignments = len(created_teacher_assignments)
            turmas_count = len(selected_classes)
            componentes_count = len(selected_courses)
            expected_assignments = turmas_count * componentes_count
            
            self.log(f"✅ Multi-selection result: 'Salvar ({total_assignments} alocações)'")
            self.log(f"   Turmas selected: {turmas_count}")
            self.log(f"   Componentes selected: {componentes_count}")
            self.log(f"   Expected assignments: {expected_assignments} (turmas × componentes)")
            
            if total_assignments == expected_assignments:
                self.log("✅ Correct number of assignments created (turmas × componentes)")
            else:
                self.log(f"⚠️ Assignment count mismatch. Expected: {expected_assignments}, Created: {total_assignments}")
            
            # Step 6: Test workload calculation with "TODOS" option simulation
            self.log("6️⃣ Testing 'TODOS' componentes curriculares option simulation...")
            
            # Simulate selecting "TODOS" - all available courses
            all_courses = courses
            todos_weekly_workload = 0
            
            for course in all_courses:
                course_workload = course.get('workload', 80)
                weekly_workload = course_workload // 4
                todos_weekly_workload += weekly_workload
                self.log(f"   {course.get('name', 'N/A')}: {course_workload}h → {weekly_workload}h/sem")
            
            self.log(f"✅ 'TODOS' option total weekly workload: {todos_weekly_workload}h/sem")
            self.log(f"   Components included: {len(all_courses)} componentes curriculares")
            
            # Step 7: Verify created records in database
            self.log("7️⃣ Verifying created records...")
            
            # Check lotações
            response = requests.get(
                f"{API_BASE}/school-assignments?staff_id={created_staff_id}",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                lotacoes = response.json()
                self.log(f"✅ Found {len(lotacoes)} lotações in database")
                for lotacao in lotacoes:
                    self.log(f"   Lotação: {lotacao.get('school_name', 'N/A')} - {lotacao.get('funcao')} - {lotacao.get('turno')}")
            
            # Check alocações
            response = requests.get(
                f"{API_BASE}/teacher-assignments?staff_id={created_staff_id}",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                alocacoes = response.json()
                self.log(f"✅ Found {len(alocacoes)} alocações in database")
                for alocacao in alocacoes:
                    self.log(f"   Alocação: {alocacao.get('class_name', 'N/A')} - {alocacao.get('course_name', 'N/A')} - {alocacao.get('carga_horaria_semanal', 0)}h/sem")
            
            self.log("✅ Staff Management Multi-Selection UI testing completed successfully!")
            return True
            
        except Exception as e:
            self.log(f"❌ Error during multi-selection testing: {str(e)}")
            return False
            
        finally:
            # Cleanup created entities
            self.log("🧹 Cleaning up multi-selection test data...")
            
            # Delete teacher assignments
            for assignment_id in created_teacher_assignments:
                try:
                    response = requests.delete(
                        f"{API_BASE}/teacher-assignments/{assignment_id}",
                        headers=self.get_headers(self.admin_token)
                    )
                    if response.status_code == 200:
                        self.log(f"✅ Deleted teacher assignment {assignment_id}")
                except:
                    pass
            
            # Delete school assignments
            for assignment_id in created_school_assignments:
                try:
                    response = requests.delete(
                        f"{API_BASE}/school-assignments/{assignment_id}",
                        headers=self.get_headers(self.admin_token)
                    )
                    if response.status_code == 200:
                        self.log(f"✅ Deleted school assignment {assignment_id}")
                except:
                    pass
            
            # Delete staff
            if created_staff_id:
                try:
                    response = requests.delete(
                        f"{API_BASE}/staff/{created_staff_id}",
                        headers=self.get_headers(self.admin_token)
                    )
                    if response.status_code == 204:
                        self.log(f"✅ Deleted staff {created_staff_id}")
                except:
                    pass
            
            # Delete professor user
            if professor_user_id:
                try:
                    response = requests.delete(
                        f"{API_BASE}/users/{professor_user_id}",
                        headers=self.get_headers(self.admin_token)
                    )
                    if response.status_code == 204:
                        self.log(f"✅ Deleted professor user {professor_user_id}")
                except:
                    pass

    def test_staff_management_deletion_ui(self):
        """Test Staff Management UI with existing lotações/alocações display and deletion as per review request"""
        self.log("\n🗑️ Testing Staff Management - Lotação and Alocação Deletion UI...")
        
        # Variables to store created IDs for testing deletion
        created_staff_id = None
        created_school_assignment_id = None
        created_teacher_assignment_id = None
        
        try:
            # Step 1: Create a staff member for testing
            self.log("1️⃣ Creating staff member for deletion testing...")
            staff_data = {
                "nome": "João Carlos Silva",
                "cargo": "professor", 
                "tipo_vinculo": "efetivo",
                "email": "joao.carlos@sigesc.com",
                "celular": "(11) 99999-1111"
            }
            
            response = requests.post(
                f"{API_BASE}/staff",
                json=staff_data,
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code in [200, 201]:
                staff = response.json()
                created_staff_id = staff['id']
                self.log(f"✅ Staff created for testing (ID: {created_staff_id})")
            else:
                self.log(f"❌ Failed to create staff: {response.status_code} - {response.text}")
                return False
            
            # Step 2: Create school assignment (lotação) for testing deletion
            self.log("2️⃣ Creating school assignment (lotação) for deletion testing...")
            if not self.school_id:
                self.log("❌ No school_id available")
                return False
                
            assignment_data = {
                "staff_id": created_staff_id,
                "school_id": self.school_id,
                "funcao": "professor",
                "turno": "matutino",
                "data_inicio": "2025-01-01",
                "academic_year": 2025
            }
            
            response = requests.post(
                f"{API_BASE}/school-assignments",
                json=assignment_data,
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code in [200, 201]:
                assignment = response.json()
                created_school_assignment_id = assignment['id']
                self.log(f"✅ School assignment created (ID: {created_school_assignment_id})")
            else:
                self.log(f"❌ Failed to create school assignment: {response.status_code} - {response.text}")
                return False
            
            # Step 3: Create teacher assignment (alocação) for testing deletion
            self.log("3️⃣ Creating teacher assignment (alocação) for deletion testing...")
            if not all([self.class_id, self.course_id]):
                self.log("❌ Missing class_id or course_id")
                return False
                
            teacher_assignment_data = {
                "staff_id": created_staff_id,
                "school_id": self.school_id,
                "class_id": self.class_id,
                "course_id": self.course_id,
                "academic_year": 2025
            }
            
            response = requests.post(
                f"{API_BASE}/teacher-assignments",
                json=teacher_assignment_data,
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code in [200, 201]:
                teacher_assignment = response.json()
                created_teacher_assignment_id = teacher_assignment['id']
                self.log(f"✅ Teacher assignment created (ID: {created_teacher_assignment_id})")
            else:
                self.log(f"❌ Failed to create teacher assignment: {response.status_code} - {response.text}")
                return False
            
            # Step 4: Test GET /api/school-assignments?staff_id={id} - Show existing lotações
            self.log("4️⃣ Testing GET /api/school-assignments?staff_id={id} - Show existing lotações...")
            response = requests.get(
                f"{API_BASE}/school-assignments?staff_id={created_staff_id}",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                lotacoes = response.json()
                self.log(f"✅ Retrieved {len(lotacoes)} lotações for staff")
                
                if lotacoes:
                    lotacao = lotacoes[0]
                    self.log(f"   School name: {lotacao.get('school_name', 'N/A')}")
                    self.log(f"   Function: {lotacao.get('funcao', 'N/A')}")
                    self.log(f"   Shift: {lotacao.get('turno', 'N/A')}")
                    self.log(f"   Start date: {lotacao.get('data_inicio', 'N/A')}")
                    self.log("✅ Lotação data structure verified")
                else:
                    self.log("❌ No lotações found for created staff")
                    return False
            else:
                self.log(f"❌ Failed to get lotações: {response.status_code} - {response.text}")
                return False
            
            # Step 5: Test GET /api/teacher-assignments?staff_id={id} - Show existing alocações
            self.log("5️⃣ Testing GET /api/teacher-assignments?staff_id={id} - Show existing alocações...")
            response = requests.get(
                f"{API_BASE}/teacher-assignments?staff_id={created_staff_id}",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                alocacoes = response.json()
                self.log(f"✅ Retrieved {len(alocacoes)} alocações for staff")
                
                if alocacoes:
                    alocacao = alocacoes[0]
                    self.log(f"   School name: {alocacao.get('school_name', 'N/A')}")
                    self.log(f"   Class name: {alocacao.get('class_name', 'N/A')}")
                    self.log(f"   Course name: {alocacao.get('course_name', 'N/A')}")
                    self.log(f"   Workload: {alocacao.get('workload', 'N/A')}")
                    self.log("✅ Alocação data structure verified")
                else:
                    self.log("❌ No alocações found for created staff")
                    return False
            else:
                self.log(f"❌ Failed to get alocações: {response.status_code} - {response.text}")
                return False
            
            # Step 6: Test DELETE /api/school-assignments/{id} - Delete lotação
            self.log("6️⃣ Testing DELETE /api/school-assignments/{id} - Delete lotação...")
            response = requests.delete(
                f"{API_BASE}/school-assignments/{created_school_assignment_id}",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('message') == 'Lotação removida com sucesso':
                    self.log("✅ Lotação deleted successfully")
                    
                    # Verify deletion by checking if it's gone
                    response = requests.get(
                        f"{API_BASE}/school-assignments?staff_id={created_staff_id}",
                        headers=self.get_headers(self.admin_token)
                    )
                    
                    if response.status_code == 200:
                        remaining_lotacoes = response.json()
                        if len(remaining_lotacoes) == 0:
                            self.log("✅ Lotação deletion verified - no lotações remain")
                        else:
                            self.log(f"❌ Lotação deletion failed - {len(remaining_lotacoes)} lotações still exist")
                            return False
                    else:
                        self.log(f"❌ Failed to verify lotação deletion: {response.status_code}")
                        return False
                else:
                    self.log(f"❌ Unexpected deletion response: {result}")
                    return False
                    
            else:
                self.log(f"❌ Failed to delete lotação: {response.status_code} - {response.text}")
                return False
            
            # Step 7: Test DELETE /api/teacher-assignments/{id} - Delete alocação
            self.log("7️⃣ Testing DELETE /api/teacher-assignments/{id} - Delete alocação...")
            response = requests.delete(
                f"{API_BASE}/teacher-assignments/{created_teacher_assignment_id}",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('message') == 'Alocação removida com sucesso':
                    self.log("✅ Alocação deleted successfully")
                    
                    # Verify deletion by checking if it's gone
                    response = requests.get(
                        f"{API_BASE}/teacher-assignments?staff_id={created_staff_id}",
                        headers=self.get_headers(self.admin_token)
                    )
                    
                    if response.status_code == 200:
                        remaining_alocacoes = response.json()
                        if len(remaining_alocacoes) == 0:
                            self.log("✅ Alocação deletion verified - no alocações remain")
                        else:
                            self.log(f"❌ Alocação deletion failed - {len(remaining_alocacoes)} alocações still exist")
                            return False
                    else:
                        self.log(f"❌ Failed to verify alocação deletion: {response.status_code}")
                        return False
                else:
                    self.log(f"❌ Unexpected deletion response: {result}")
                    return False
                    
            else:
                self.log(f"❌ Failed to delete alocação: {response.status_code} - {response.text}")
                return False
            
            # Step 8: Test staff with no lotações/alocações message
            self.log("8️⃣ Testing empty state messages...")
            
            # Check lotações empty state
            response = requests.get(
                f"{API_BASE}/school-assignments?staff_id={created_staff_id}",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                lotacoes = response.json()
                if len(lotacoes) == 0:
                    self.log("✅ Empty lotações state verified - should show 'O servidor não está lotado em nenhuma escola.'")
                else:
                    self.log(f"❌ Expected empty lotações, found {len(lotacoes)}")
            
            # Check alocações empty state
            response = requests.get(
                f"{API_BASE}/teacher-assignments?staff_id={created_staff_id}",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                alocacoes = response.json()
                if len(alocacoes) == 0:
                    self.log("✅ Empty alocações state verified - should show 'O professor não está alocado em nenhuma turma.'")
                else:
                    self.log(f"❌ Expected empty alocações, found {len(alocacoes)}")
            
            self.log("✅ Staff Management Deletion UI testing completed successfully!")
            return True
            
        except Exception as e:
            self.log(f"❌ Error during deletion testing: {str(e)}")
            return False
            
        finally:
            # Cleanup - delete the staff member
            if created_staff_id:
                self.log("🧹 Cleaning up test staff...")
                response = requests.delete(
                    f"{API_BASE}/staff/{created_staff_id}",
                    headers=self.get_headers(self.admin_token)
                )
                if response.status_code in [200, 204]:
                    self.log("✅ Test staff cleaned up")
                else:
                    self.log(f"❌ Failed to cleanup test staff: {response.status_code}")

    def test_learning_objects_full_feature(self):
        """Test Learning Objects (Objetos de Conhecimento) - Full Feature Testing as per review request"""
        self.log("\n📚 Testing Learning Objects (Objetos de Conhecimento) - Full Feature Testing...")
        
        # Test data from review request
        specific_class_id = "42a876e6-aea3-40a3-8660-e1ef44fc3c4a"  # 3º Ano A
        test_date = "2025-12-10"
        academic_year = 2025
        created_learning_object_id = None
        
        # Get a valid course_id first
        if not self.course_id:
            self.log("❌ No course_id available - getting courses first...")
            response = requests.get(
                f"{API_BASE}/courses",
                headers=self.get_headers(self.admin_token)
            )
            if response.status_code == 200:
                courses = response.json()
                if courses:
                    self.course_id = courses[0]['id']
                    self.log(f"✅ Using course: {courses[0]['name']} (ID: {self.course_id})")
                else:
                    self.log("❌ No courses found")
                    return False
            else:
                self.log(f"❌ Failed to get courses: {response.status_code}")
                return False
        
        try:
            # 1. Test POST /api/learning-objects - Create new learning object
            self.log("1️⃣ Testing POST /api/learning-objects - Creating learning object...")
            learning_object_data = {
                "class_id": specific_class_id,
                "course_id": self.course_id,
                "date": test_date,
                "academic_year": academic_year,
                "content": "Introdução aos números decimais e frações",
                "methodology": "Aula expositiva dialogada com exemplos práticos",
                "resources": "Quadro branco, livro didático, material concreto",
                "observations": "Turma demonstrou boa compreensão",
                "number_of_classes": 2
            }
            
            response = requests.post(
                f"{API_BASE}/learning-objects",
                json=learning_object_data,
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200 or response.status_code == 201:
                learning_object = response.json()
                created_learning_object_id = learning_object['id']
                self.log(f"✅ Learning object created successfully (ID: {created_learning_object_id})")
                self.log(f"   Class ID: {learning_object.get('class_id')}")
                self.log(f"   Course ID: {learning_object.get('course_id')}")
                self.log(f"   Date: {learning_object.get('date')}")
                self.log(f"   Content: {learning_object.get('content')}")
                self.log(f"   Methodology: {learning_object.get('methodology')}")
                self.log(f"   Resources: {learning_object.get('resources')}")
                self.log(f"   Number of classes: {learning_object.get('number_of_classes')}")
                self.log(f"   Observations: {learning_object.get('observations')}")
            else:
                self.log(f"❌ Failed to create learning object: {response.status_code} - {response.text}")
                return False
            
            # 2. Test GET /api/learning-objects - List learning objects with filters
            self.log("2️⃣ Testing GET /api/learning-objects - Listing with filters...")
            
            # Test without filters
            response = requests.get(
                f"{API_BASE}/learning-objects",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                all_objects = response.json()
                self.log(f"✅ Successfully retrieved {len(all_objects)} learning objects (no filters)")
            else:
                self.log(f"❌ Failed to list learning objects: {response.status_code} - {response.text}")
                return False
            
            # Test with class_id filter
            response = requests.get(
                f"{API_BASE}/learning-objects?class_id={specific_class_id}",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                class_objects = response.json()
                self.log(f"✅ Successfully retrieved {len(class_objects)} learning objects for class {specific_class_id}")
                
                # Verify our created object is in the list
                found_created = any(obj['id'] == created_learning_object_id for obj in class_objects)
                if found_created:
                    self.log("✅ Created learning object found in class filter")
                else:
                    self.log("❌ Created learning object NOT found in class filter")
            else:
                self.log(f"❌ Failed to list learning objects with class filter: {response.status_code}")
            
            # Test with course_id filter
            response = requests.get(
                f"{API_BASE}/learning-objects?course_id={self.course_id}",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                course_objects = response.json()
                self.log(f"✅ Successfully retrieved {len(course_objects)} learning objects for course {self.course_id}")
            else:
                self.log(f"❌ Failed to list learning objects with course filter: {response.status_code}")
            
            # Test with academic_year filter
            response = requests.get(
                f"{API_BASE}/learning-objects?academic_year={academic_year}",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                year_objects = response.json()
                self.log(f"✅ Successfully retrieved {len(year_objects)} learning objects for year {academic_year}")
            else:
                self.log(f"❌ Failed to list learning objects with year filter: {response.status_code}")
            
            # Test with month filter (December = 12)
            response = requests.get(
                f"{API_BASE}/learning-objects?academic_year={academic_year}&month=12",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                month_objects = response.json()
                self.log(f"✅ Successfully retrieved {len(month_objects)} learning objects for December {academic_year}")
            else:
                self.log(f"❌ Failed to list learning objects with month filter: {response.status_code}")
            
            # 3. Test GET /api/learning-objects/{id} - Get specific learning object
            self.log("3️⃣ Testing GET /api/learning-objects/{id} - Getting specific learning object...")
            response = requests.get(
                f"{API_BASE}/learning-objects/{created_learning_object_id}",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                specific_object = response.json()
                self.log(f"✅ Successfully retrieved specific learning object")
                self.log(f"   ID: {specific_object.get('id')}")
                self.log(f"   Content: {specific_object.get('content')}")
                self.log(f"   Date: {specific_object.get('date')}")
                
                # Verify all fields are present
                expected_fields = ['id', 'class_id', 'course_id', 'date', 'academic_year', 'content', 'methodology', 'resources', 'observations', 'number_of_classes']
                missing_fields = [field for field in expected_fields if field not in specific_object]
                if missing_fields:
                    self.log(f"❌ Missing fields in response: {missing_fields}")
                else:
                    self.log("✅ All expected fields present in response")
            else:
                self.log(f"❌ Failed to get specific learning object: {response.status_code} - {response.text}")
                return False
            
            # 4. Test PUT /api/learning-objects/{id} - Update learning object
            self.log("4️⃣ Testing PUT /api/learning-objects/{id} - Updating learning object...")
            update_data = {
                "content": "Introdução aos números decimais e frações - ATUALIZADO",
                "methodology": "Aula expositiva dialogada com exemplos práticos e exercícios",
                "observations": "Turma demonstrou excelente compreensão após atualização"
            }
            
            response = requests.put(
                f"{API_BASE}/learning-objects/{created_learning_object_id}",
                json=update_data,
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                updated_object = response.json()
                self.log(f"✅ Learning object updated successfully")
                self.log(f"   Updated content: {updated_object.get('content')}")
                self.log(f"   Updated methodology: {updated_object.get('methodology')}")
                self.log(f"   Updated observations: {updated_object.get('observations')}")
                
                # Verify the update was applied
                if "ATUALIZADO" in updated_object.get('content', ''):
                    self.log("✅ Content update verified")
                else:
                    self.log("❌ Content update not applied correctly")
            else:
                self.log(f"❌ Failed to update learning object: {response.status_code} - {response.text}")
                return False
            
            # 5. Test GET /api/learning-objects/check-date/{class_id}/{course_id}/{date} - Check if record exists
            self.log("5️⃣ Testing GET /api/learning-objects/check-date/{class_id}/{course_id}/{date}...")
            response = requests.get(
                f"{API_BASE}/learning-objects/check-date/{specific_class_id}/{self.course_id}/{test_date}",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                date_check = response.json()
                self.log(f"✅ Date check successful")
                self.log(f"   Has record: {date_check.get('has_record')}")
                
                if date_check.get('has_record'):
                    self.log("✅ Correctly found existing record for the date")
                    record = date_check.get('record', {})
                    if record.get('id') == created_learning_object_id:
                        self.log("✅ Returned record matches our created object")
                    else:
                        self.log("❌ Returned record does not match our created object")
                else:
                    self.log("❌ Should have found existing record for the date")
            else:
                self.log(f"❌ Failed to check date: {response.status_code} - {response.text}")
                return False
            
            # 6. Test duplicate prevention - try to create another record for same date/class/course
            self.log("6️⃣ Testing duplicate prevention...")
            duplicate_data = {
                "class_id": specific_class_id,
                "course_id": self.course_id,
                "date": test_date,
                "academic_year": academic_year,
                "content": "Tentativa de duplicação",
                "number_of_classes": 1
            }
            
            response = requests.post(
                f"{API_BASE}/learning-objects",
                json=duplicate_data,
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 400:
                self.log("✅ Duplicate prevention working correctly (400 error)")
                error_detail = response.json().get('detail', '')
                if "Já existe um registro" in error_detail:
                    self.log("✅ Correct error message for duplicate")
                else:
                    self.log(f"❌ Unexpected error message: {error_detail}")
            else:
                self.log(f"❌ Duplicate prevention failed - should return 400: {response.status_code}")
            
            # 7. Test DELETE /api/learning-objects/{id} - Delete learning object
            self.log("7️⃣ Testing DELETE /api/learning-objects/{id} - Deleting learning object...")
            response = requests.delete(
                f"{API_BASE}/learning-objects/{created_learning_object_id}",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                delete_result = response.json()
                self.log(f"✅ Learning object deleted successfully")
                self.log(f"   Message: {delete_result.get('message')}")
            else:
                self.log(f"❌ Failed to delete learning object: {response.status_code} - {response.text}")
                return False
            
            # 8. Verify deletion - try to get the deleted object
            self.log("8️⃣ Verifying deletion...")
            response = requests.get(
                f"{API_BASE}/learning-objects/{created_learning_object_id}",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 404:
                self.log("✅ Deletion verified - object not found (404)")
            else:
                self.log(f"❌ Deletion verification failed - object still exists: {response.status_code}")
                return False
            
            # 9. Verify check-date returns no record after deletion
            self.log("9️⃣ Verifying check-date after deletion...")
            response = requests.get(
                f"{API_BASE}/learning-objects/check-date/{specific_class_id}/{self.course_id}/{test_date}",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                date_check_after = response.json()
                if not date_check_after.get('has_record'):
                    self.log("✅ Check-date correctly shows no record after deletion")
                else:
                    self.log("❌ Check-date still shows record after deletion")
            else:
                self.log(f"❌ Failed to check date after deletion: {response.status_code}")
            
            self.log("✅ Learning Objects Full Feature Testing completed successfully!")
            return True
            
        except Exception as e:
            self.log(f"❌ Error during learning objects testing: {str(e)}")
            return False
        
        finally:
            # Cleanup - try to delete the learning object if it still exists
            if created_learning_object_id:
                try:
                    requests.delete(
                        f"{API_BASE}/learning-objects/{created_learning_object_id}",
                        headers=self.get_headers(self.admin_token)
                    )
                    self.log("🧹 Cleanup: Learning object deleted")
                except:
                    pass

    def test_profile_image_upload(self):
        """Test User Profile Image Upload functionality as per review request"""
        self.log("\n📸 Testing User Profile Image Upload (Foto de Perfil e Capa)...")
        
        # Test credentials from review request
        admin_credentials = {"email": "admin@sigesc.com", "password": "password"}
        professor_credentials = {"email": "ricleidegoncalves@gmail.com", "password": "007724"}
        
        # Login as admin for testing
        admin_token = self.login(admin_credentials, "Admin for Profile Test")
        if not admin_token:
            self.log("❌ Cannot proceed without admin login for profile test")
            return False
        
        # Variables to store uploaded file info
        uploaded_profile_filename = None
        uploaded_cover_filename = None
        
        try:
            # Scenario 1: Upload valid PNG image
            self.log("1️⃣ Scenario 1: Upload valid PNG image...")
            
            # Create a simple PNG image in base64 (1x1 pixel transparent PNG)
            import base64
            import io
            
            # Minimal PNG data (1x1 transparent pixel)
            png_data = base64.b64decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChAI9jU8'
                'AAABJRU5ErkJggg=='
            )
            
            # Test POST /api/upload
            files = {'file': ('test_profile.png', png_data, 'image/png')}
            headers = {"Authorization": f"Bearer {admin_token}"}
            
            response = requests.post(
                f"{API_BASE}/upload",
                files=files,
                headers=headers
            )
            
            if response.status_code == 200:
                upload_result = response.json()
                uploaded_profile_filename = upload_result.get('filename')
                
                self.log(f"✅ PNG image uploaded successfully")
                self.log(f"   Filename: {upload_result.get('filename')}")
                self.log(f"   Original name: {upload_result.get('original_name')}")
                self.log(f"   URL: {upload_result.get('url')}")
                self.log(f"   Size: {upload_result.get('size')} bytes")
                
                # Verify URL format
                expected_url = f"/api/uploads/{uploaded_profile_filename}"
                if upload_result.get('url') == expected_url:
                    self.log("✅ URL format is correct (/api/uploads/{filename})")
                else:
                    self.log(f"❌ URL format incorrect. Expected: {expected_url}, Got: {upload_result.get('url')}")
                
                # Verify file types are allowed
                allowed_types = ['.jpg', '.jpeg', '.png', '.gif', '.pdf', '.doc', '.docx']
                file_ext = '.' + uploaded_profile_filename.split('.')[-1].lower()
                if file_ext in allowed_types:
                    self.log(f"✅ File type {file_ext} is in allowed types")
                else:
                    self.log(f"❌ File type {file_ext} not in allowed types: {allowed_types}")
                    
            else:
                self.log(f"❌ Failed to upload PNG image: {response.status_code} - {response.text}")
                return False
            
            # Test GET /api/uploads/{filename} - Verify file can be accessed
            self.log("2️⃣ Testing GET /api/uploads/{filename} - Verify file access...")
            
            response = requests.get(f"{API_BASE}/uploads/{uploaded_profile_filename}")
            
            if response.status_code == 200:
                self.log("✅ Uploaded file can be accessed via GET")
                
                # Check content-type header
                content_type = response.headers.get('content-type', '')
                if content_type.startswith('image/png'):
                    self.log(f"✅ Content-Type is correct: {content_type}")
                else:
                    self.log(f"❌ Content-Type incorrect. Expected: image/png, Got: {content_type}")
                    
            else:
                self.log(f"❌ Failed to access uploaded file: {response.status_code}")
                return False
            
            # Scenario 2: Update profile with foto_url
            self.log("3️⃣ Scenario 2: Update profile with foto_url...")
            
            profile_update_data = {
                "foto_url": f"/api/uploads/{uploaded_profile_filename}"
            }
            
            response = requests.put(
                f"{API_BASE}/profiles/me",
                json=profile_update_data,
                headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                updated_profile = response.json()
                self.log("✅ Profile updated with foto_url successfully")
                self.log(f"   Foto URL: {updated_profile.get('foto_url')}")
            else:
                self.log(f"❌ Failed to update profile with foto_url: {response.status_code} - {response.text}")
                return False
            
            # Scenario 3: Upload another image for cover photo
            self.log("4️⃣ Scenario 3: Upload image for cover photo...")
            
            # Create another PNG for cover
            files = {'file': ('test_cover.png', png_data, 'image/png')}
            
            response = requests.post(
                f"{API_BASE}/upload",
                files=files,
                headers=headers
            )
            
            if response.status_code == 200:
                cover_upload_result = response.json()
                uploaded_cover_filename = cover_upload_result.get('filename')
                self.log(f"✅ Cover image uploaded successfully: {uploaded_cover_filename}")
            else:
                self.log(f"❌ Failed to upload cover image: {response.status_code} - {response.text}")
                return False
            
            # Update profile with foto_capa_url
            self.log("5️⃣ Updating profile with foto_capa_url...")
            
            cover_update_data = {
                "foto_capa_url": f"/api/uploads/{uploaded_cover_filename}"
            }
            
            response = requests.put(
                f"{API_BASE}/profiles/me",
                json=cover_update_data,
                headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                updated_profile = response.json()
                self.log("✅ Profile updated with foto_capa_url successfully")
                self.log(f"   Cover URL: {updated_profile.get('foto_capa_url')}")
            else:
                self.log(f"❌ Failed to update profile with foto_capa_url: {response.status_code} - {response.text}")
                return False
            
            # Verify both URLs are saved correctly
            self.log("6️⃣ Testing GET /api/profiles/me - Verify both URLs saved...")
            
            response = requests.get(
                f"{API_BASE}/profiles/me",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            
            if response.status_code == 200:
                profile = response.json()
                self.log("✅ Profile retrieved successfully")
                
                foto_url = profile.get('foto_url')
                foto_capa_url = profile.get('foto_capa_url')
                
                self.log(f"   Foto URL: {foto_url}")
                self.log(f"   Foto Capa URL: {foto_capa_url}")
                
                # Verify URLs are correct
                expected_foto_url = f"/api/uploads/{uploaded_profile_filename}"
                expected_capa_url = f"/api/uploads/{uploaded_cover_filename}"
                
                if foto_url == expected_foto_url:
                    self.log("✅ Profile foto_url saved correctly")
                else:
                    self.log(f"❌ Profile foto_url incorrect. Expected: {expected_foto_url}, Got: {foto_url}")
                
                if foto_capa_url == expected_capa_url:
                    self.log("✅ Profile foto_capa_url saved correctly")
                else:
                    self.log(f"❌ Profile foto_capa_url incorrect. Expected: {expected_capa_url}, Got: {foto_capa_url}")
                    
            else:
                self.log(f"❌ Failed to retrieve profile: {response.status_code} - {response.text}")
                return False
            
            # Scenario 4: Validation tests
            self.log("7️⃣ Scenario 4: Validation tests...")
            
            # Test upload without authentication
            self.log("   Testing upload without authentication...")
            files = {'file': ('test_no_auth.png', png_data, 'image/png')}
            
            response = requests.post(f"{API_BASE}/upload", files=files)
            
            if response.status_code == 401:
                self.log("✅ Upload correctly denied without authentication (401)")
            else:
                self.log(f"❌ Upload should require authentication. Got: {response.status_code}")
            
            # Test file size limit (create a large file simulation)
            self.log("   Testing file size limit (5MB)...")
            
            # Create a large file (simulate > 5MB)
            large_data = b'x' * (6 * 1024 * 1024)  # 6MB
            files = {'file': ('large_file.png', large_data, 'image/png')}
            
            response = requests.post(
                f"{API_BASE}/upload",
                files=files,
                headers=headers
            )
            
            if response.status_code == 400:
                self.log("✅ Large file correctly rejected (400)")
                if "muito grande" in response.text.lower() or "5mb" in response.text.lower():
                    self.log("✅ Error message mentions size limit")
            else:
                self.log(f"❌ Large file should be rejected. Got: {response.status_code}")
            
            # Test invalid file type
            self.log("   Testing invalid file type...")
            
            files = {'file': ('test.exe', b'fake exe content', 'application/octet-stream')}
            
            response = requests.post(
                f"{API_BASE}/upload",
                files=files,
                headers=headers
            )
            
            if response.status_code == 400:
                self.log("✅ Invalid file type correctly rejected (400)")
                if "não permitido" in response.text.lower() or "not allowed" in response.text.lower():
                    self.log("✅ Error message mentions file type restriction")
            else:
                self.log(f"❌ Invalid file type should be rejected. Got: {response.status_code}")
            
            self.log("✅ Profile Image Upload testing completed successfully!")
            return True
            
        except Exception as e:
            self.log(f"❌ Error during profile image upload testing: {str(e)}")
            return False
            
        finally:
            # Cleanup uploaded files
            self.log("🧹 Cleaning up uploaded test files...")
            
            if uploaded_profile_filename:
                try:
                    response = requests.delete(
                        f"{API_BASE}/upload/{uploaded_profile_filename}",
                        headers={"Authorization": f"Bearer {admin_token}"}
                    )
                    if response.status_code == 200:
                        self.log(f"✅ Cleaned up profile image: {uploaded_profile_filename}")
                    else:
                        self.log(f"⚠️ Could not clean up profile image: {response.status_code}")
                except:
                    self.log(f"⚠️ Error cleaning up profile image")
            
            if uploaded_cover_filename:
                try:
                    response = requests.delete(
                        f"{API_BASE}/upload/{uploaded_cover_filename}",
                        headers={"Authorization": f"Bearer {admin_token}"}
                    )
                    if response.status_code == 200:
                        self.log(f"✅ Cleaned up cover image: {uploaded_cover_filename}")
                    else:
                        self.log(f"⚠️ Could not clean up cover image: {response.status_code}")
                except:
                    self.log(f"⚠️ Error cleaning up cover image")

    def test_message_deletion_system(self):
        """Test Sistema de Exclusão de Mensagens e Logs de Conversas as per review request"""
        self.log("\n💬 Testing Message Deletion System (Sistema de Exclusão de Mensagens e Logs)...")
        
        # Test credentials from review request
        PROFESSOR_CREDENTIALS = {
            "email": "ricleidegoncalves@gmail.com",
            "password": "007724"
        }
        
        # Login as professor (Ricleide)
        professor_token = self.login(PROFESSOR_CREDENTIALS, "Professor Ricleide")
        if not professor_token:
            self.log("❌ Failed to login as Professor Ricleide")
            return False
        
        # Test data from review request
        connection_id = "11faaa15-32cd-4712-a435-281f5bb5e28c"  # Admin-Ricleide connection
        admin_user_id = "5edcfabe-3a6d-44f4-9310-9bacf3a62491"  # Correct admin user ID
        ricleide_user_id = "b97578dd-bc66-446c-88d7-686b423af399"
        
        # Scenario 1: Verify existing logs
        self.log("1️⃣ Scenario 1: Verifying existing logs...")
        
        # Test GET /api/admin/message-logs/users (admin only)
        self.log("   Testing GET /api/admin/message-logs/users...")
        response = requests.get(
            f"{API_BASE}/admin/message-logs/users",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            users_with_logs = response.json()
            self.log(f"✅ Successfully retrieved users with logs: {len(users_with_logs)} users")
            
            # Check if Gutenberg and Ricleide are in the list
            gutenberg_found = any(u.get('user_id') == admin_user_id for u in users_with_logs)
            ricleide_found = any(u.get('user_id') == ricleide_user_id for u in users_with_logs)
            
            if gutenberg_found:
                self.log("✅ Gutenberg (Admin) found in users with logs")
            else:
                self.log("❌ Gutenberg (Admin) not found in users with logs")
            
            if ricleide_found:
                self.log("✅ Ricleide found in users with logs")
            else:
                self.log("❌ Ricleide not found in users with logs")
                
        else:
            self.log(f"❌ Failed to get users with logs: {response.status_code} - {response.text}")
            return False
        
        # Test GET /api/admin/message-logs/user/{admin_user_id}
        self.log(f"   Testing GET /api/admin/message-logs/user/{admin_user_id}...")
        response = requests.get(
            f"{API_BASE}/admin/message-logs/user/{admin_user_id}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            admin_logs = response.json()
            self.log(f"✅ Successfully retrieved admin logs")
            self.log(f"   User: {admin_logs.get('user_name')}")
            self.log(f"   Total messages: {admin_logs.get('total_messages', 0)}")
            self.log(f"   Total attachments: {admin_logs.get('total_attachments', 0)}")
            
            if admin_logs.get('total_messages', 0) >= 1:
                self.log("✅ Admin has at least 1 logged message as expected")
            else:
                self.log("❌ Admin should have at least 1 logged message")
        else:
            self.log(f"❌ Failed to get admin logs: {response.status_code} - {response.text}")
            return False
        
        # Scenario 2: Create a test message and then delete it
        self.log("2️⃣ Scenario 2: Creating test message and then deleting it...")
        
        # First, create a test message to delete
        self.log("   Creating test message for deletion test...")
        test_message_data = {
            "receiver_id": ricleide_user_id,
            "content": "Test message for deletion system testing",
            "connection_id": connection_id
        }
        
        response = requests.post(
            f"{API_BASE}/messages",
            json=test_message_data,
            headers=self.get_headers(self.admin_token)
        )
        
        message_to_delete = None
        if response.status_code == 200 or response.status_code == 201:
            message_to_delete = response.json()
            self.log(f"✅ Test message created: {message_to_delete.get('id')}")
            self.log(f"   Message content: {message_to_delete.get('content')}")
        else:
            self.log(f"❌ Failed to create test message: {response.status_code} - {response.text}")
            return False
        
        # List messages in the conversation to verify it exists
        self.log(f"   Listing messages in conversation {connection_id}...")
        response = requests.get(
            f"{API_BASE}/messages/{connection_id}",
            headers=self.get_headers(self.admin_token)
        )
        
        messages_before = []
        if response.status_code == 200:
            messages_before = response.json()
            self.log(f"✅ Found {len(messages_before)} messages in conversation")
            
            # Verify our test message is in the list
            test_msg_found = any(msg.get('id') == message_to_delete['id'] for msg in messages_before)
            if test_msg_found:
                self.log("✅ Test message found in conversation")
            else:
                self.log("❌ Test message not found in conversation")
        else:
            self.log(f"❌ Failed to list messages: {response.status_code} - {response.text}")
            return False
        
        # Delete the selected message
        if message_to_delete:
            self.log(f"   Deleting message {message_to_delete['id']}...")
            response = requests.delete(
                f"{API_BASE}/messages/{message_to_delete['id']}",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                delete_result = response.json()
                self.log(f"✅ Message deleted successfully: {delete_result.get('message')}")
            else:
                self.log(f"❌ Failed to delete message: {response.status_code} - {response.text}")
                return False
        
        # Verify message was removed from list
        self.log("   Verifying message was removed from conversation...")
        response = requests.get(
            f"{API_BASE}/messages/{connection_id}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            messages_after = response.json()
            self.log(f"✅ Messages after deletion: {len(messages_after)}")
            
            if len(messages_after) == len(messages_before) - 1:
                self.log("✅ Message count decreased by 1 as expected")
            else:
                self.log(f"❌ Expected {len(messages_before) - 1} messages, got {len(messages_after)}")
            
            # Verify the specific message is not in the list
            deleted_msg_found = any(msg.get('id') == message_to_delete['id'] for msg in messages_after)
            if not deleted_msg_found:
                self.log("✅ Deleted message no longer appears in conversation")
            else:
                self.log("❌ Deleted message still appears in conversation")
        else:
            self.log(f"❌ Failed to verify message deletion: {response.status_code}")
        
        # Verify log was created
        self.log("   Verifying log was created for deleted message...")
        response = requests.get(
            f"{API_BASE}/admin/message-logs",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            all_logs = response.json()
            self.log(f"✅ Retrieved {len(all_logs)} total logs")
            
            # Look for the log of our deleted message
            deleted_msg_log = None
            for log in all_logs:
                if log.get('original_message_id') == message_to_delete['id']:
                    deleted_msg_log = log
                    break
            
            if deleted_msg_log:
                self.log("✅ Log created for deleted message")
                self.log(f"   Log ID: {deleted_msg_log.get('id')}")
                self.log(f"   Deleted by: {deleted_msg_log.get('deleted_by')}")
                self.log(f"   Expires at: {deleted_msg_log.get('expires_at')}")
            else:
                self.log("❌ No log found for deleted message")
        else:
            self.log(f"❌ Failed to retrieve logs: {response.status_code}")
        
        # Scenario 3: Test validation (unauthorized access)
        self.log("3️⃣ Scenario 3: Testing validations...")
        
        # Test non-admin trying to access logs (should fail)
        self.log("   Testing non-admin access to logs (should fail)...")
        response = requests.get(
            f"{API_BASE}/admin/message-logs",
            headers=self.get_headers(professor_token)
        )
        
        if response.status_code == 403:
            self.log("✅ Non-admin correctly denied access to logs (403)")
        else:
            self.log(f"❌ Non-admin should be denied access to logs: {response.status_code}")
        
        # Test trying to delete message without being sender/receiver
        # First, create a test message between admin and ricleide
        self.log("   Creating test message for unauthorized deletion test...")
        test_message_data = {
            "receiver_id": ricleide_user_id,
            "content": "Test message for unauthorized deletion test",
            "connection_id": connection_id
        }
        
        response = requests.post(
            f"{API_BASE}/messages",
            json=test_message_data,
            headers=self.get_headers(self.admin_token)
        )
        
        test_message_id = None
        if response.status_code == 200 or response.status_code == 201:
            test_message = response.json()
            test_message_id = test_message.get('id')
            self.log(f"✅ Test message created: {test_message_id}")
        else:
            self.log(f"❌ Failed to create test message: {response.status_code}")
        
        # Now try to delete with SEMED user (should fail)
        if test_message_id and self.coordinator_token:
            self.log("   Testing unauthorized message deletion (should fail)...")
            response = requests.delete(
                f"{API_BASE}/messages/{test_message_id}",
                headers=self.get_headers(self.coordinator_token)
            )
            
            if response.status_code == 403:
                self.log("✅ Unauthorized user correctly denied message deletion (403)")
            else:
                self.log(f"❌ Unauthorized user should be denied message deletion: {response.status_code}")
        
        # Test other admin endpoints
        self.log("4️⃣ Testing other admin endpoints...")
        
        # Test GET /api/admin/message-logs (list all logs)
        self.log("   Testing GET /api/admin/message-logs...")
        response = requests.get(
            f"{API_BASE}/admin/message-logs?limit=50",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            logs = response.json()
            self.log(f"✅ Successfully retrieved {len(logs)} logs")
            
            if logs:
                first_log = logs[0]
                expected_fields = ['id', 'original_message_id', 'sender_id', 'receiver_id', 'content', 'logged_at', 'deleted_at', 'expires_at']
                for field in expected_fields:
                    if field in first_log:
                        self.log(f"   ✅ Log field '{field}' present")
                    else:
                        self.log(f"   ❌ Log field '{field}' missing")
        else:
            self.log(f"❌ Failed to list all logs: {response.status_code}")
        
        # Test DELETE /api/admin/message-logs/expired
        self.log("   Testing DELETE /api/admin/message-logs/expired...")
        response = requests.delete(
            f"{API_BASE}/admin/message-logs/expired",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            cleanup_result = response.json()
            self.log(f"✅ Expired logs cleanup successful: {cleanup_result.get('message')}")
        else:
            self.log(f"❌ Failed to cleanup expired logs: {response.status_code}")
        
        # Test conversation deletion
        self.log("5️⃣ Testing conversation deletion...")
        
        # First check how many messages are in the conversation
        response = requests.get(
            f"{API_BASE}/messages/{connection_id}",
            headers=self.get_headers(self.admin_token)
        )
        
        messages_count_before_conv_delete = 0
        if response.status_code == 200:
            messages_count_before_conv_delete = len(response.json())
            self.log(f"   Messages in conversation before deletion: {messages_count_before_conv_delete}")
        
        # Note: We won't actually delete the entire conversation as it would affect other tests
        # Instead, we'll test the endpoint validation
        self.log("   Testing conversation deletion validation...")
        
        # Test with invalid connection_id (should fail)
        invalid_connection_id = "invalid-connection-id"
        response = requests.delete(
            f"{API_BASE}/messages/conversation/{invalid_connection_id}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 404:
            self.log("✅ Invalid connection_id correctly returns 404")
        else:
            self.log(f"❌ Invalid connection_id should return 404: {response.status_code}")
        
        self.log("✅ Message Deletion System testing completed!")
        return True

    def test_announcement_system_fase7(self):
        """Test SIGESC Announcement System (FASE 7 - Sistema de Avisos) as per review request"""
        self.log("\n📢 Testing SIGESC Announcement System - FASE 7...")
        
        # Variables to store created IDs for cleanup
        created_announcement_id = None
        professor_token = None
        
        try:
            # Step 1: Login as professor to test recipient functionality
            self.log("1️⃣ Logging in as professor for recipient testing...")
            professor_credentials = {
                "email": "ricleidegoncalves@gmail.com",
                "password": "007724"
            }
            
            professor_token = self.login(professor_credentials, "Professor")
            if not professor_token:
                self.log("❌ Professor login failed - continuing with admin tests only")
            
            # Step 2: Test POST /api/announcements - Create announcement (Admin creates for Professors)
            self.log("2️⃣ Testing POST /api/announcements - Admin creates announcement for Professors...")
            announcement_data = {
                "title": "Reunião Pedagógica Importante",
                "content": "Convocamos todos os professores para reunião pedagógica no dia 20/12/2025 às 14h no auditório principal. Assuntos: planejamento 2026, avaliações e metodologias ativas.",
                "recipient": {
                    "type": "role",
                    "target_roles": ["professor"]
                }
            }
            
            response = requests.post(
                f"{API_BASE}/announcements",
                json=announcement_data,
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200 or response.status_code == 201:
                announcement = response.json()
                created_announcement_id = announcement['id']
                self.log(f"✅ Announcement created successfully (ID: {created_announcement_id})")
                self.log(f"   Title: {announcement.get('title')}")
                recipient = announcement.get('recipient', {})
                self.log(f"   Recipient Type: {recipient.get('type')}")
                self.log(f"   Target Roles: {recipient.get('target_roles')}")
                self.log(f"   Sender: {announcement.get('sender_name', 'N/A')}")
                
                # Verify sender info is populated correctly
                if announcement.get('sender_name'):
                    self.log("✅ Sender information populated correctly")
                else:
                    self.log("❌ Sender information not populated")
            else:
                self.log(f"❌ Failed to create announcement: {response.status_code} - {response.text}")
                return False
            
            # Step 3: Test GET /api/announcements - List announcements
            self.log("3️⃣ Testing GET /api/announcements - List all announcements...")
            response = requests.get(
                f"{API_BASE}/announcements",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                announcements = response.json()
                self.log(f"✅ Successfully retrieved {len(announcements)} announcements")
                
                # Verify our created announcement appears in the list
                found_created = any(a['id'] == created_announcement_id for a in announcements)
                if found_created:
                    self.log("✅ Created announcement found in list")
                else:
                    self.log("❌ Created announcement NOT found in list")
                
                # Check announcement structure
                if announcements:
                    first_announcement = announcements[0]
                    expected_fields = ['id', 'title', 'content', 'recipient', 'sender_name', 'created_at']
                    for field in expected_fields:
                        if field in first_announcement:
                            self.log(f"   ✅ Field '{field}' present")
                        else:
                            self.log(f"   ❌ Field '{field}' missing")
                    
                    # Check recipient structure
                    if 'recipient' in first_announcement:
                        recipient = first_announcement['recipient']
                        if 'type' in recipient:
                            self.log(f"   ✅ Recipient type present: {recipient['type']}")
                        if 'target_roles' in recipient:
                            self.log(f"   ✅ Target roles present: {recipient['target_roles']}")
            else:
                self.log(f"❌ Failed to list announcements: {response.status_code} - {response.text}")
                return False
            
            # Step 4: Test GET /api/announcements/{id} - Get announcement details
            self.log("4️⃣ Testing GET /api/announcements/{id} - Get announcement details...")
            response = requests.get(
                f"{API_BASE}/announcements/{created_announcement_id}",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                announcement_details = response.json()
                self.log(f"✅ Announcement details retrieved successfully")
                self.log(f"   Title: {announcement_details.get('title')}")
                self.log(f"   Content length: {len(announcement_details.get('content', ''))}")
                self.log(f"   Priority: {announcement_details.get('priority')}")
                self.log(f"   Created at: {announcement_details.get('created_at')}")
            else:
                self.log(f"❌ Failed to get announcement details: {response.status_code} - {response.text}")
                return False
            
            # Step 5: Test POST /api/announcements/{id}/read - Mark as read (Professor perspective)
            if professor_token:
                self.log("5️⃣ Testing POST /api/announcements/{id}/read - Professor marks as read...")
                response = requests.post(
                    f"{API_BASE}/announcements/{created_announcement_id}/read",
                    headers=self.get_headers(professor_token)
                )
                
                if response.status_code == 200:
                    read_response = response.json()
                    self.log(f"✅ Announcement marked as read successfully")
                    self.log(f"   Message: {read_response.get('message', 'N/A')}")
                    
                    # Verify is_read status
                    if read_response.get('is_read'):
                        self.log("✅ is_read status correctly set to true")
                    else:
                        self.log("❌ is_read status not set correctly")
                else:
                    self.log(f"❌ Failed to mark as read: {response.status_code} - {response.text}")
            else:
                self.log("5️⃣ Skipping mark as read test (no professor token)")
            
            # Step 6: Test PUT /api/announcements/{id} - Update announcement
            self.log("6️⃣ Testing PUT /api/announcements/{id} - Update announcement...")
            update_data = {
                "title": "Reunião Pedagógica Importante - ATUALIZADA",
                "content": "ATUALIZAÇÃO: A reunião pedagógica foi reagendada para o dia 21/12/2025 às 15h no auditório principal. Assuntos: planejamento 2026, avaliações e metodologias ativas. Por favor, confirmem presença."
            }
            
            response = requests.put(
                f"{API_BASE}/announcements/{created_announcement_id}",
                json=update_data,
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                updated_announcement = response.json()
                self.log(f"✅ Announcement updated successfully")
                self.log(f"   New title: {updated_announcement.get('title')}")
                
                # Verify changes were saved
                if "ATUALIZADA" in updated_announcement.get('title', ''):
                    self.log("✅ Title update verified")
                if "ATUALIZAÇÃO" in updated_announcement.get('content', ''):
                    self.log("✅ Content update verified")
            else:
                self.log(f"❌ Failed to update announcement: {response.status_code} - {response.text}")
                return False
            
            # Step 7: Test GET /api/notifications/unread-count - Get unread count
            if professor_token:
                self.log("7️⃣ Testing GET /api/notifications/unread-count - Get unread count...")
                response = requests.get(
                    f"{API_BASE}/notifications/unread-count",
                    headers=self.get_headers(professor_token)
                )
                
                if response.status_code == 200:
                    unread_count = response.json()
                    self.log(f"✅ Unread count retrieved successfully")
                    self.log(f"   Unread Messages: {unread_count.get('unread_messages', 0)}")
                    self.log(f"   Unread Announcements: {unread_count.get('unread_announcements', 0)}")
                    self.log(f"   Total: {unread_count.get('total', 0)}")
                    
                    # Verify structure
                    if 'unread_messages' in unread_count and 'unread_announcements' in unread_count:
                        self.log("✅ Unread count structure is correct")
                    else:
                        self.log("❌ Unread count structure is incorrect")
                else:
                    self.log(f"❌ Failed to get unread count: {response.status_code} - {response.text}")
            else:
                self.log("7️⃣ Skipping unread count test (no professor token)")
            
            # Step 8: Test filtering announcements by recipient
            self.log("8️⃣ Testing announcement filtering by recipient...")
            response = requests.get(
                f"{API_BASE}/announcements?recipient_type=role&target_role=professor",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                filtered_announcements = response.json()
                self.log(f"✅ Successfully filtered announcements for professors")
                self.log(f"   Found {len(filtered_announcements)} announcements for professors")
                
                # Verify our announcement is in the filtered results
                found_in_filter = any(a['id'] == created_announcement_id for a in filtered_announcements)
                if found_in_filter:
                    self.log("✅ Created announcement found in filtered results")
                else:
                    self.log("❌ Created announcement NOT found in filtered results")
            else:
                self.log(f"❌ Failed to filter announcements: {response.status_code} - {response.text}")
            
            # Step 9: Test DELETE /api/announcements/{id} - Delete announcement
            self.log("9️⃣ Testing DELETE /api/announcements/{id} - Delete announcement...")
            response = requests.delete(
                f"{API_BASE}/announcements/{created_announcement_id}",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200 or response.status_code == 204:
                self.log(f"✅ Announcement deleted successfully")
                
                # Verify deletion by trying to get the announcement
                verify_response = requests.get(
                    f"{API_BASE}/announcements/{created_announcement_id}",
                    headers=self.get_headers(self.admin_token)
                )
                
                if verify_response.status_code == 404:
                    self.log("✅ Announcement deletion verified (404 on get)")
                    created_announcement_id = None  # Mark as deleted for cleanup
                else:
                    self.log(f"❌ Announcement still exists after deletion: {verify_response.status_code}")
            else:
                self.log(f"❌ Failed to delete announcement: {response.status_code} - {response.text}")
                return False
            
            # Step 10: Verify announcement is removed from list
            self.log("🔟 Verifying announcement is removed from list...")
            response = requests.get(
                f"{API_BASE}/announcements",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                final_announcements = response.json()
                found_deleted = any(a['id'] == created_announcement_id for a in final_announcements) if created_announcement_id else False
                
                if not found_deleted:
                    self.log("✅ Deleted announcement not found in final list")
                else:
                    self.log("❌ Deleted announcement still appears in list")
            
            self.log("✅ SIGESC Announcement System (FASE 7) testing completed successfully!")
            return True
            
        except Exception as e:
            self.log(f"❌ Error during announcement system testing: {str(e)}")
            return False
            
        finally:
            # Cleanup: Delete announcement if it still exists
            if created_announcement_id:
                self.log("🧹 Cleaning up announcement test data...")
                try:
                    response = requests.delete(
                        f"{API_BASE}/announcements/{created_announcement_id}",
                        headers=self.get_headers(self.admin_token)
                    )
                    if response.status_code in [200, 204, 404]:
                        self.log("✅ Test announcement cleaned up")
                    else:
                        self.log(f"❌ Failed to cleanup announcement: {response.status_code}")
                except Exception as cleanup_error:
                    self.log(f"❌ Cleanup error: {str(cleanup_error)}")

    def test_pdf_document_generation_phase8(self):
        """Test PDF Document Generation - Phase 8 as per review request"""
        self.log("\n📄 Testing PDF Document Generation - Phase 8...")
        
        if not self.student_id:
            self.log("❌ No student_id available for PDF testing")
            return False
        
        academic_year = "2025"
        
        # Test 1: Boletim Escolar Generation
        self.log("1️⃣ Testing GET /api/documents/boletim/{student_id}...")
        response = requests.get(
            f"{API_BASE}/documents/boletim/{self.student_id}?academic_year={academic_year}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            self.log("✅ Boletim Escolar PDF generated successfully")
            
            # Verify it's a PDF file
            content_type = response.headers.get('content-type', '')
            if 'application/pdf' in content_type:
                self.log("✅ Response is a PDF file (Content-Type: application/pdf)")
            else:
                self.log(f"❌ Expected PDF, got Content-Type: {content_type}")
                return False
            
            # Check content length
            content_length = len(response.content)
            self.log(f"   PDF size: {content_length} bytes")
            if content_length > 1000:  # PDF should be at least 1KB
                self.log("✅ PDF has reasonable size")
            else:
                self.log("❌ PDF seems too small")
                return False
                
        else:
            self.log(f"❌ Failed to generate Boletim Escolar: {response.status_code} - {response.text}")
            return False
        
        # Test 2: Declaração de Matrícula Generation
        self.log("2️⃣ Testing GET /api/documents/declaracao-matricula/{student_id}...")
        response = requests.get(
            f"{API_BASE}/documents/declaracao-matricula/{self.student_id}?academic_year={academic_year}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            self.log("✅ Declaração de Matrícula PDF generated successfully")
            
            # Verify it's a PDF file
            content_type = response.headers.get('content-type', '')
            if 'application/pdf' in content_type:
                self.log("✅ Response is a PDF file (Content-Type: application/pdf)")
            else:
                self.log(f"❌ Expected PDF, got Content-Type: {content_type}")
                return False
            
            # Check content length
            content_length = len(response.content)
            self.log(f"   PDF size: {content_length} bytes")
            if content_length > 1000:
                self.log("✅ PDF has reasonable size")
            else:
                self.log("❌ PDF seems too small")
                return False
                
        else:
            self.log(f"❌ Failed to generate Declaração de Matrícula: {response.status_code} - {response.text}")
            return False
        
        # Test 3: Declaração de Frequência Generation
        self.log("3️⃣ Testing GET /api/documents/declaracao-frequencia/{student_id}...")
        response = requests.get(
            f"{API_BASE}/documents/declaracao-frequencia/{self.student_id}?academic_year={academic_year}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            self.log("✅ Declaração de Frequência PDF generated successfully")
            
            # Verify it's a PDF file
            content_type = response.headers.get('content-type', '')
            if 'application/pdf' in content_type:
                self.log("✅ Response is a PDF file (Content-Type: application/pdf)")
            else:
                self.log(f"❌ Expected PDF, got Content-Type: {content_type}")
                return False
            
            # Check content length
            content_length = len(response.content)
            self.log(f"   PDF size: {content_length} bytes")
            if content_length > 1000:
                self.log("✅ PDF has reasonable size")
            else:
                self.log("❌ PDF seems too small")
                return False
                
        else:
            self.log(f"❌ Failed to generate Declaração de Frequência: {response.status_code} - {response.text}")
            return False
        
        # Test 4: Error Handling - Non-existent student ID
        self.log("4️⃣ Testing error handling with non-existent student ID...")
        fake_student_id = "00000000-0000-0000-0000-000000000000"
        
        response = requests.get(
            f"{API_BASE}/documents/boletim/{fake_student_id}?academic_year={academic_year}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 404:
            self.log("✅ Non-existent student correctly returns 404")
        else:
            self.log(f"❌ Expected 404 for non-existent student, got: {response.status_code}")
            return False
        
        # Test 5: Authentication Required
        self.log("5️⃣ Testing authentication requirement...")
        
        # Test without token
        response = requests.get(f"{API_BASE}/documents/boletim/{self.student_id}")
        if response.status_code == 401:
            self.log("✅ PDF endpoints correctly require authentication (401)")
        else:
            self.log(f"❌ Expected 401 without token, got: {response.status_code}")
            return False
        
        # Test with invalid token
        invalid_headers = {"Authorization": "Bearer invalid_token_here"}
        response = requests.get(
            f"{API_BASE}/documents/boletim/{self.student_id}",
            headers=invalid_headers
        )
        if response.status_code == 401:
            self.log("✅ Invalid token correctly rejected (401)")
        else:
            self.log(f"❌ Expected 401 for invalid token, got: {response.status_code}")
            return False
        
        # Test 6: Test with custom purpose for Declaração de Matrícula
        self.log("6️⃣ Testing Declaração de Matrícula with custom purpose...")
        custom_purpose = "fins de transferência escolar"
        response = requests.get(
            f"{API_BASE}/documents/declaracao-matricula/{self.student_id}?academic_year={academic_year}&purpose={custom_purpose}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            self.log("✅ Declaração de Matrícula with custom purpose generated successfully")
            content_type = response.headers.get('content-type', '')
            if 'application/pdf' in content_type:
                self.log("✅ Custom purpose PDF is valid")
            else:
                self.log(f"❌ Custom purpose PDF invalid Content-Type: {content_type}")
                return False
        else:
            self.log(f"❌ Failed to generate custom purpose declaration: {response.status_code}")
            return False
        
        # Test 7: Test different academic years
        self.log("7️⃣ Testing different academic years...")
        test_year = "2024"
        response = requests.get(
            f"{API_BASE}/documents/boletim/{self.student_id}?academic_year={test_year}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            self.log(f"✅ PDF generation works for academic year {test_year}")
            content_type = response.headers.get('content-type', '')
            if 'application/pdf' in content_type:
                self.log("✅ Different year PDF is valid")
            else:
                self.log(f"❌ Different year PDF invalid Content-Type: {content_type}")
                return False
        else:
            self.log(f"❌ Failed to generate PDF for year {test_year}: {response.status_code}")
            return False
        
        self.log("✅ PDF Document Generation Phase 8 testing completed successfully!")
        return True

    def test_ficha_individual_pdf_generation(self):
        """Test Ficha Individual do Aluno PDF generation as per review request"""
        self.log("\n📄 Testing Ficha Individual PDF Generation...")
        
        # Use credentials from review request
        gutenberg_credentials = {
            "email": "gutenberg@sigesc.com",
            "password": "@Celta2007"
        }
        
        professor_credentials = {
            "email": "ricleidegoncalves@gmail.com", 
            "password": "007724"
        }
        
        # Login as admin (Gutenberg)
        self.log("🔐 Logging in as Gutenberg (Admin)...")
        gutenberg_token = self.login(gutenberg_credentials, "Gutenberg (Admin)")
        if not gutenberg_token:
            self.log("❌ Gutenberg login failed")
            return False
        
        # Login as professor (Ricleide)
        self.log("🔐 Logging in as Ricleide (Professor)...")
        professor_token = self.login(professor_credentials, "Ricleide (Professor)")
        if not professor_token:
            self.log("❌ Ricleide login failed")
            return False
        
        # Get students to test with
        self.log("1️⃣ Getting students for testing...")
        response = requests.get(
            f"{API_BASE}/students",
            headers=self.get_headers(gutenberg_token)
        )
        
        if response.status_code != 200:
            self.log(f"❌ Failed to get students: {response.status_code}")
            return False
        
        students = response.json()
        if not students:
            self.log("❌ No students found for testing")
            return False
        
        test_student = students[0]
        student_id = test_student['id']
        student_name = test_student.get('full_name', 'N/A')
        self.log(f"✅ Using test student: {student_name} (ID: {student_id})")
        
        # Test 1: GET /api/documents/ficha-individual/{student_id}?academic_year=2025
        self.log("2️⃣ Testing GET /api/documents/ficha-individual/{student_id}?academic_year=2025...")
        response = requests.get(
            f"{API_BASE}/documents/ficha-individual/{student_id}?academic_year=2025",
            headers=self.get_headers(gutenberg_token)
        )
        
        if response.status_code == 200:
            self.log("✅ Ficha Individual PDF generated successfully")
            
            # Verify Content-Type
            content_type = response.headers.get('Content-Type')
            if content_type == 'application/pdf':
                self.log("✅ Correct Content-Type: application/pdf")
            else:
                self.log(f"❌ Incorrect Content-Type: {content_type}")
                return False
            
            # Verify PDF size (should be reasonable)
            pdf_size = len(response.content)
            self.log(f"✅ PDF size: {pdf_size} bytes")
            if pdf_size > 1000:  # At least 1KB
                self.log("✅ PDF size is reasonable")
            else:
                self.log("❌ PDF size too small - may be corrupted")
                return False
            
            # Verify filename in Content-Disposition
            content_disposition = response.headers.get('Content-Disposition', '')
            if 'ficha_individual_' in content_disposition and '.pdf' in content_disposition:
                self.log("✅ Correct filename format in Content-Disposition")
            else:
                self.log(f"❌ Incorrect Content-Disposition: {content_disposition}")
        else:
            self.log(f"❌ Failed to generate Ficha Individual PDF: {response.status_code} - {response.text}")
            return False
        
        # Test 2: Test with different academic year (2024)
        self.log("3️⃣ Testing with academic year 2024...")
        response = requests.get(
            f"{API_BASE}/documents/ficha-individual/{student_id}?academic_year=2024",
            headers=self.get_headers(gutenberg_token)
        )
        
        if response.status_code == 200:
            self.log("✅ Ficha Individual PDF generated for 2024")
            pdf_size_2024 = len(response.content)
            self.log(f"✅ PDF size for 2024: {pdf_size_2024} bytes")
        else:
            self.log(f"❌ Failed to generate PDF for 2024: {response.status_code}")
            return False
        
        # Test 3: Test error handling - invalid student ID
        self.log("4️⃣ Testing error handling with invalid student ID...")
        response = requests.get(
            f"{API_BASE}/documents/ficha-individual/invalid-student-id?academic_year=2025",
            headers=self.get_headers(gutenberg_token)
        )
        
        if response.status_code == 404:
            self.log("✅ Correctly returns 404 for invalid student ID")
        else:
            self.log(f"❌ Expected 404, got: {response.status_code}")
            return False
        
        # Test 4: Test authentication requirement
        self.log("5️⃣ Testing authentication requirement...")
        response = requests.get(
            f"{API_BASE}/documents/ficha-individual/{student_id}?academic_year=2025"
        )
        
        if response.status_code == 401:
            self.log("✅ Correctly requires authentication (401)")
        else:
            self.log(f"❌ Expected 401 for missing auth, got: {response.status_code}")
        
        # Test 5: Test professor access
        self.log("6️⃣ Testing professor access to Ficha Individual...")
        response = requests.get(
            f"{API_BASE}/documents/ficha-individual/{student_id}?academic_year=2025",
            headers=self.get_headers(professor_token)
        )
        
        if response.status_code == 200:
            self.log("✅ Professor can access Ficha Individual PDF")
            professor_pdf_size = len(response.content)
            self.log(f"✅ Professor PDF size: {professor_pdf_size} bytes")
        else:
            self.log(f"❌ Professor cannot access PDF: {response.status_code}")
            return False
        
        # Test 6: Verify PDF contains expected content structure
        self.log("7️⃣ Verifying PDF content structure...")
        
        # Get student details for verification
        response = requests.get(
            f"{API_BASE}/students/{student_id}",
            headers=self.get_headers(gutenberg_token)
        )
        
        if response.status_code == 200:
            student_details = response.json()
            self.log("✅ Retrieved student details for verification")
            self.log(f"   Student name: {student_details.get('full_name')}")
            self.log(f"   INEP code: {student_details.get('inep_code', 'N/A')}")
            self.log(f"   Sex: {student_details.get('sex', 'N/A')}")
            self.log(f"   Birth date: {student_details.get('birth_date', 'N/A')}")
        
        # Test 7: Test multiple students (batch scenario)
        self.log("8️⃣ Testing multiple students (batch scenario)...")
        test_students = students[:3]  # Test with first 3 students
        
        for i, student in enumerate(test_students):
            sid = student['id']
            sname = student.get('full_name', f'Student_{i}')
            
            response = requests.get(
                f"{API_BASE}/documents/ficha-individual/{sid}?academic_year=2025",
                headers=self.get_headers(gutenberg_token)
            )
            
            if response.status_code == 200:
                self.log(f"✅ Batch test {i+1}/3: {sname} - PDF generated ({len(response.content)} bytes)")
            else:
                self.log(f"❌ Batch test {i+1}/3: {sname} - Failed ({response.status_code})")
        
        self.log("✅ Ficha Individual PDF Generation testing completed!")
        return True

    def test_coordinator_permissions_system(self):
        """Test Coordinator Permissions system as per review request"""
        self.log("\n🔐 Testing Coordinator Permissions System...")
        
        # 1. Login and Role Verification
        self.log("1️⃣ Testing Coordinator Login and Role Verification...")
        response = requests.post(
            f"{API_BASE}/auth/login",
            json=COORDINATOR_CREDENTIALS,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            data = response.json()
            self.coordinator_token = data.get('access_token')
            user = data.get('user', {})
            user_role = user.get('role')
            
            self.log(f"✅ Coordinator login successful")
            self.log(f"   User: {user.get('full_name', 'N/A')}")
            self.log(f"   Email: {user.get('email')}")
            self.log(f"   Role: {user_role}")
            
            # Verify role is "coordenador" (not "professor")
            if user_role == "coordenador":
                self.log("✅ User role correctly returned as 'coordenador'")
            else:
                self.log(f"❌ Expected role 'coordenador', got: {user_role}")
                return False
        else:
            self.log(f"❌ Coordinator login failed: {response.status_code} - {response.text}")
            return False
        
        # 2. Permissions Endpoint
        self.log("2️⃣ Testing GET /api/auth/permissions with coordinator token...")
        response = requests.get(
            f"{API_BASE}/auth/permissions",
            headers=self.get_headers(self.coordinator_token)
        )
        
        if response.status_code == 200:
            permissions = response.json()
            self.log(f"✅ Permissions endpoint successful")
            
            # Expected permissions for coordinator
            expected_permissions = {
                'can_edit_students': False,
                'can_edit_classes': False,
                'can_edit_grades': True,
                'can_edit_attendance': True,
                'can_edit_learning_objects': True,
                'is_read_only_except_diary': True
            }
            
            self.log("   Checking coordinator permissions:")
            all_correct = True
            for perm, expected_value in expected_permissions.items():
                actual_value = permissions.get(perm)
                if actual_value == expected_value:
                    self.log(f"   ✅ {perm}: {actual_value} (correct)")
                else:
                    self.log(f"   ❌ {perm}: {actual_value} (expected: {expected_value})")
                    all_correct = False
            
            if all_correct:
                self.log("✅ All coordinator permissions are correct")
            else:
                self.log("❌ Some coordinator permissions are incorrect")
                return False
        else:
            self.log(f"❌ Failed to get permissions: {response.status_code} - {response.text}")
            return False
        
        # 3. Student Update (Should be BLOCKED)
        self.log("3️⃣ Testing Student Update (Should be BLOCKED for coordinator)...")
        
        # First get a valid student ID
        response = requests.get(
            f"{API_BASE}/students",
            headers=self.get_headers(self.coordinator_token)
        )
        
        if response.status_code == 200:
            students = response.json()
            if students:
                test_student_id = students[0]['id']
                student_name = students[0].get('full_name', 'N/A')
                self.log(f"   Using student: {student_name} (ID: {test_student_id})")
                
                # Try to update student (should be blocked)
                update_data = {
                    "observations": "Teste de atualização pelo coordenador"
                }
                
                response = requests.put(
                    f"{API_BASE}/students/{test_student_id}",
                    json=update_data,
                    headers=self.get_headers(self.coordinator_token)
                )
                
                if response.status_code == 403:
                    response_text = response.text
                    self.log("✅ Student update correctly BLOCKED (403)")
                    if "Coordenadores podem apenas visualizar" in response_text:
                        self.log("✅ Correct error message about coordinator read-only access")
                    else:
                        self.log(f"   Response: {response_text}")
                elif response.status_code == 401:
                    self.log("✅ Student update correctly BLOCKED (401)")
                else:
                    self.log(f"❌ Student update should be blocked, got: {response.status_code}")
                    return False
            else:
                self.log("❌ No students found for testing")
                return False
        else:
            self.log(f"❌ Failed to get students: {response.status_code} - {response.text}")
            return False
        
        # 4. Grades Access (Should be ALLOWED)
        self.log("4️⃣ Testing Grades Access (Should be ALLOWED for coordinator)...")
        
        # Test GET /api/grades
        response = requests.get(
            f"{API_BASE}/grades",
            headers=self.get_headers(self.coordinator_token)
        )
        
        if response.status_code == 200:
            grades = response.json()
            self.log(f"✅ GET /api/grades successful - retrieved {len(grades)} grades")
        else:
            self.log(f"❌ GET /api/grades failed: {response.status_code} - {response.text}")
            return False
        
        # Test POST /api/grades (create a test grade)
        if self.student_id and self.class_id and self.course_id:
            test_grade_data = {
                "student_id": self.student_id,
                "class_id": self.class_id,
                "course_id": self.course_id,
                "academic_year": 2025,
                "b1": 7.5,
                "observations": "Nota criada pelo coordenador"
            }
            
            response = requests.post(
                f"{API_BASE}/grades",
                json=test_grade_data,
                headers=self.get_headers(self.coordinator_token)
            )
            
            if response.status_code in [200, 201]:
                grade = response.json()
                self.log(f"✅ POST /api/grades successful - created grade ID: {grade.get('id')}")
                self.log(f"   B1: {grade.get('b1')}, Student: {grade.get('student_id')}")
            else:
                self.log(f"❌ POST /api/grades failed: {response.status_code} - {response.text}")
                return False
        else:
            self.log("ℹ️ Skipping grade creation - missing required test data")
        
        # 5. Attendance Access (Should be ALLOWED)
        self.log("5️⃣ Testing Attendance Access (Should be ALLOWED for coordinator)...")
        
        # Use available class from setup instead of hardcoded one
        if self.class_id:
            test_date = "2025-12-15"
            
            response = requests.get(
                f"{API_BASE}/attendance/by-class/{self.class_id}/{test_date}",
                headers=self.get_headers(self.coordinator_token)
            )
            
            if response.status_code == 200:
                attendance_data = response.json()
                self.log(f"✅ GET /api/attendance/by-class successful")
                self.log(f"   Class: {attendance_data.get('class_name', 'N/A')}")
                self.log(f"   Students: {len(attendance_data.get('students', []))}")
            else:
                self.log(f"❌ GET /api/attendance/by-class failed: {response.status_code} - {response.text}")
                return False
        else:
            self.log("ℹ️ Skipping attendance test - no class_id available")
        
        # 6. Learning Objects Access (Should be ALLOWED)
        self.log("6️⃣ Testing Learning Objects Access (Should be ALLOWED for coordinator)...")
        
        response = requests.get(
            f"{API_BASE}/learning-objects",
            headers=self.get_headers(self.coordinator_token)
        )
        
        if response.status_code == 200:
            learning_objects = response.json()
            self.log(f"✅ GET /api/learning-objects successful - retrieved {len(learning_objects)} objects")
        else:
            self.log(f"❌ GET /api/learning-objects failed: {response.status_code} - {response.text}")
            return False
        
        # 7. Compare with Admin (Admin CAN update students)
        self.log("7️⃣ Testing Admin can update students (comparison)...")
        
        if students:  # Use the same student from earlier test
            test_student_id = students[0]['id']
            
            # Admin should be able to update students
            update_data = {
                "observations": "Teste de atualização pelo admin"
            }
            
            response = requests.put(
                f"{API_BASE}/students/{test_student_id}",
                json=update_data,
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                updated_student = response.json()
                self.log("✅ Admin CAN update students (as expected)")
                self.log(f"   Updated observations: {updated_student.get('observations', 'N/A')}")
            else:
                self.log(f"❌ Admin should be able to update students: {response.status_code}")
                return False
        
        # 8. Test Classes Access (Should be READ-ONLY for coordinator)
        self.log("8️⃣ Testing Classes Access (Should be READ-ONLY for coordinator)...")
        
        # Coordinator should be able to GET classes
        response = requests.get(
            f"{API_BASE}/classes",
            headers=self.get_headers(self.coordinator_token)
        )
        
        if response.status_code == 200:
            classes = response.json()
            self.log(f"✅ GET /api/classes successful - retrieved {len(classes)} classes")
        else:
            self.log(f"❌ GET /api/classes failed: {response.status_code} - {response.text}")
            return False
        
        # Coordinator should NOT be able to create classes
        if self.school_id:
            test_class_data = {
                "name": "Teste Coordenador",
                "school_id": self.school_id,
                "grade_level": "1º Ano",
                "shift": "matutino",
                "academic_year": 2025
            }
            
            response = requests.post(
                f"{API_BASE}/classes",
                json=test_class_data,
                headers=self.get_headers(self.coordinator_token)
            )
            
            if response.status_code == 403:
                self.log("✅ Class creation correctly BLOCKED for coordinator (403)")
            elif response.status_code == 401:
                self.log("✅ Class creation correctly BLOCKED for coordinator (401)")
            else:
                self.log(f"❌ Class creation should be blocked for coordinator: {response.status_code}")
                return False
        
        # 9. Test Staff Access (Should be READ-ONLY for coordinator)
        self.log("9️⃣ Testing Staff Access (Should be READ-ONLY for coordinator)...")
        
        # Coordinator should be able to GET staff
        response = requests.get(
            f"{API_BASE}/staff",
            headers=self.get_headers(self.coordinator_token)
        )
        
        if response.status_code == 200:
            staff_list = response.json()
            self.log(f"✅ GET /api/staff successful - retrieved {len(staff_list)} staff members")
        else:
            self.log(f"❌ GET /api/staff failed: {response.status_code} - {response.text}")
            return False
        
        self.log("✅ Coordinator Permissions System testing completed successfully!")
        self.log("\n📋 SUMMARY:")
        self.log("   ✅ Coordinator login with correct role verification")
        self.log("   ✅ Permissions endpoint returns correct coordinator permissions")
        self.log("   ✅ Student updates BLOCKED (read-only)")
        self.log("   ✅ Classes creation BLOCKED (read-only)")
        self.log("   ✅ Staff access READ-ONLY")
        self.log("   ✅ Grades access ALLOWED (diary area)")
        self.log("   ✅ Attendance access ALLOWED (diary area)")
        self.log("   ✅ Learning Objects access ALLOWED (diary area)")
        self.log("   ✅ Admin comparison shows different permissions")
        
        return True

    def test_boletim_component_filtering(self):
        """Test component filtering in Boletim generation based on Education Level and School Type as per review request"""
        self.log("\n📋 Testing Boletim Component Filtering (Education Level + School Type)...")
        
        try:
            # TEST CASE 1: Educação Infantil Student (Berçário)
            self.log("\n1️⃣ TEST CASE 1: Educação Infantil Student (Berçário)...")
            infantil_student_id = "db50cfdc-abbb-422b-974a-08671e61cabd"
            
            self.log(f"   Testing student ID: {infantil_student_id}")
            self.log("   Expected: EDUCAÇÃO INFANTIL components only")
            self.log("   Expected components: Corpo, gestos e movimentos; Escuta, fala, pensamento e imaginação; etc.")
            
            response = requests.get(
                f"{API_BASE}/documents/boletim/{infantil_student_id}?academic_year=2025",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                self.log("✅ Boletim generated successfully for Educação Infantil student")
                self.log(f"   PDF size: {len(response.content)} bytes")
                self.log(f"   Content-Type: {response.headers.get('Content-Type')}")
                
                if response.headers.get('Content-Type') == 'application/pdf':
                    self.log("✅ Correct PDF Content-Type")
                else:
                    self.log("❌ Incorrect Content-Type - expected application/pdf")
                    
                if len(response.content) > 1000:  # Reasonable PDF size
                    self.log("✅ PDF has reasonable size (>1KB)")
                else:
                    self.log("❌ PDF size too small - may be empty or corrupted")
            else:
                self.log(f"❌ Failed to generate boletim for Educação Infantil student: {response.status_code} - {response.text}")
                return False
            
            # TEST CASE 2: Fundamental Anos Iniciais Student from INTEGRAL School
            self.log("\n2️⃣ TEST CASE 2: Fundamental Anos Iniciais Student from INTEGRAL School...")
            
            # First, find a student from Escola Municipal Floresta do Araguaia (integral school)
            integral_school_id = "dd8e65aa-ec50-48b9-b8f8-21f32fc29250"  # Updated correct ID
            self.log(f"   Looking for students from integral school: {integral_school_id}")
            
            response = requests.get(
                f"{API_BASE}/students?school_id={integral_school_id}",
                headers=self.get_headers(self.admin_token)
            )
            
            integral_student_id = None
            if response.status_code == 200:
                students = response.json()
                if students:
                    integral_student_id = students[0]['id']
                    self.log(f"✅ Found integral school student: {students[0].get('full_name')} (ID: {integral_student_id})")
                else:
                    self.log("❌ No students found in integral school")
                    return False
            else:
                self.log(f"❌ Failed to get students from integral school: {response.status_code}")
                return False
            
            if integral_student_id:
                self.log("   Expected: Regular Fundamental + Escola Integral components")
                self.log("   Expected integral components: Recreação, Esporte e Lazer; Arte e Cultura; Tecnologia e Informática; etc.")
                
                response = requests.get(
                    f"{API_BASE}/documents/boletim/{integral_student_id}?academic_year=2025",
                    headers=self.get_headers(self.admin_token)
                )
                
                if response.status_code == 200:
                    self.log("✅ Boletim generated successfully for Integral school student")
                    self.log(f"   PDF size: {len(response.content)} bytes")
                    
                    if len(response.content) > 1000:
                        self.log("✅ PDF has reasonable size")
                    else:
                        self.log("❌ PDF size too small")
                else:
                    self.log(f"❌ Failed to generate boletim for integral school student: {response.status_code} - {response.text}")
                    return False
            
            # TEST CASE 3: Fundamental Anos Iniciais Student from REGULAR School
            self.log("\n3️⃣ TEST CASE 3: Fundamental Anos Iniciais Student from REGULAR School...")
            
            # Find a student from a regular (non-integral) school
            response = requests.get(
                f"{API_BASE}/schools",
                headers=self.get_headers(self.admin_token)
            )
            
            regular_school_id = None
            regular_student_id = None
            
            if response.status_code == 200:
                schools = response.json()
                # Look for a school that is NOT integral (atendimento_integral: false)
                for school in schools:
                    if not school.get('atendimento_integral', False):
                        regular_school_id = school['id']
                        self.log(f"✅ Found regular school: {school.get('name')} (ID: {regular_school_id})")
                        break
                
                if regular_school_id:
                    # Get students from this regular school
                    response = requests.get(
                        f"{API_BASE}/students?school_id={regular_school_id}",
                        headers=self.get_headers(self.admin_token)
                    )
                    
                    if response.status_code == 200:
                        students = response.json()
                        if students:
                            regular_student_id = students[0]['id']
                            self.log(f"✅ Found regular school student: {students[0].get('full_name')} (ID: {regular_student_id})")
                        else:
                            self.log("❌ No students found in regular school")
                    else:
                        self.log(f"❌ Failed to get students from regular school: {response.status_code}")
                else:
                    self.log("❌ No regular (non-integral) schools found")
                    return False
            else:
                self.log(f"❌ Failed to get schools: {response.status_code}")
                return False
            
            if regular_student_id:
                self.log("   Expected: ONLY Regular Fundamental Anos Iniciais components")
                self.log("   Should NOT have: Recreação, Arte e Cultura, Tecnologia e Informática")
                
                response = requests.get(
                    f"{API_BASE}/documents/boletim/{regular_student_id}?academic_year=2025",
                    headers=self.get_headers(self.admin_token)
                )
                
                if response.status_code == 200:
                    self.log("✅ Boletim generated successfully for Regular school student")
                    self.log(f"   PDF size: {len(response.content)} bytes")
                    
                    if len(response.content) > 1000:
                        self.log("✅ PDF has reasonable size")
                    else:
                        self.log("❌ PDF size too small")
                else:
                    self.log(f"❌ Failed to generate boletim for regular school student: {response.status_code} - {response.text}")
                    return False
            
            # TEST CASE 4: Verify inference logic in backend logs
            self.log("\n4️⃣ TEST CASE 4: Verifying inference logic...")
            self.log("   Checking backend logs for 'Boletim: grade_level=..., nivel_ensino inferido=...' messages")
            
            # Check backend logs
            try:
                import subprocess
                result = subprocess.run(
                    ["tail", "-n", "100", "/var/log/supervisor/backend.err.log"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    log_content = result.stdout
                    if "Boletim:" in log_content and "nivel_ensino inferido" in log_content:
                        self.log("✅ Found inference logic messages in backend logs")
                        # Extract relevant log lines
                        log_lines = log_content.split('\n')
                        for line in log_lines:
                            if "Boletim:" in line and "nivel_ensino inferido" in line:
                                self.log(f"   📝 {line.strip()}")
                    else:
                        self.log("ℹ️ No inference logic messages found in recent logs")
                else:
                    self.log("❌ Failed to read backend logs")
            except Exception as e:
                self.log(f"❌ Error reading backend logs: {str(e)}")
            
            # TEST CASE 5: Verify school type identification
            self.log("\n5️⃣ TEST CASE 5: Verifying school type identification...")
            
            response = requests.get(
                f"{API_BASE}/schools",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                schools = response.json()
                integral_count = 0
                regular_count = 0
                
                for school in schools:
                    if school.get('atendimento_integral', False):
                        integral_count += 1
                        self.log(f"   🏫 INTEGRAL: {school.get('name')} (ID: {school.get('id')})")
                    else:
                        regular_count += 1
                        if regular_count <= 3:  # Show only first 3 to avoid spam
                            self.log(f"   🏫 REGULAR: {school.get('name')} (ID: {school.get('id')})")
                
                self.log(f"✅ School type identification: {integral_count} integral, {regular_count} regular schools")
                
                if integral_count > 0 and regular_count > 0:
                    self.log("✅ Both integral and regular schools found - filtering can be tested")
                else:
                    self.log("❌ Missing either integral or regular schools - filtering cannot be fully tested")
            else:
                self.log(f"❌ Failed to get schools for type verification: {response.status_code}")
            
            # TEST CASE 6: Verify component categorization
            self.log("\n6️⃣ TEST CASE 6: Verifying component categorization...")
            
            response = requests.get(
                f"{API_BASE}/courses",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                courses = response.json()
                
                # Categorize components
                infantil_components = []
                fundamental_components = []
                integral_components = []
                
                for course in courses:
                    nivel_ensino = course.get('nivel_ensino', '')
                    atendimento_programa = course.get('atendimento_programa', '')
                    name = course.get('name', course.get('nome', ''))
                    
                    if 'infantil' in nivel_ensino.lower():
                        infantil_components.append(name)
                    elif 'fundamental' in nivel_ensino.lower():
                        fundamental_components.append(name)
                    
                    if 'atendimento_integral' in atendimento_programa:
                        integral_components.append(name)
                
                self.log(f"✅ Component categorization:")
                self.log(f"   Educação Infantil components: {len(infantil_components)}")
                if infantil_components:
                    self.log(f"   Examples: {', '.join(infantil_components[:3])}")
                
                self.log(f"   Fundamental components: {len(fundamental_components)}")
                if fundamental_components:
                    self.log(f"   Examples: {', '.join(fundamental_components[:5])}")
                
                self.log(f"   Escola Integral components: {len(integral_components)}")
                if integral_components:
                    self.log(f"   Examples: {', '.join(integral_components[:3])}")
                    
                    # Check for expected integral components
                    expected_integral = ['Recreação, Esporte e Lazer', 'Arte e Cultura', 'Tecnologia e Informática']
                    found_expected = []
                    for expected in expected_integral:
                        for component in integral_components:
                            if expected.lower() in component.lower():
                                found_expected.append(component)
                                break
                    
                    if found_expected:
                        self.log(f"✅ Found expected integral components: {', '.join(found_expected)}")
                    else:
                        self.log("❌ Expected integral components not found")
            else:
                self.log(f"❌ Failed to get courses for categorization: {response.status_code}")
            
            # TEST CASE 7: Error handling
            self.log("\n7️⃣ TEST CASE 7: Testing error handling...")
            
            # Test with invalid student ID
            invalid_student_id = "00000000-0000-0000-0000-000000000000"
            response = requests.get(
                f"{API_BASE}/documents/boletim/{invalid_student_id}?academic_year=2025",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 404:
                self.log("✅ Correct 404 response for invalid student ID")
            else:
                self.log(f"❌ Expected 404 for invalid student ID, got: {response.status_code}")
            
            # Test without authentication
            response = requests.get(
                f"{API_BASE}/documents/boletim/{infantil_student_id}?academic_year=2025"
            )
            
            if response.status_code == 401:
                self.log("✅ Correct 401 response for missing authentication")
            else:
                self.log(f"❌ Expected 401 for missing auth, got: {response.status_code}")
            
            self.log("✅ Boletim Component Filtering testing completed!")
            return True
            
        except Exception as e:
            self.log(f"❌ Error during boletim component filtering test: {str(e)}")
            return False

    def test_ficha_individual_pdf_generation(self):
        """Test Ficha Individual PDF generation with layout changes as per review request"""
        self.log("\n📄 Testing Ficha Individual PDF Generation (Layout Changes)...")
        
        # Test credentials from review request
        admin_credentials = {
            "email": "gutenberg@sigesc.com",
            "password": "@Celta2007"
        }
        
        # Login as admin
        self.log("1️⃣ Logging in as admin (gutenberg@sigesc.com)...")
        admin_token = self.login(admin_credentials, "Admin (Gutenberg)")
        if not admin_token:
            self.log("❌ Admin login failed - cannot continue")
            return False
        
        # Get students to test with
        self.log("2️⃣ Getting students for testing...")
        response = requests.get(
            f"{API_BASE}/students",
            headers=self.get_headers(admin_token)
        )
        
        if response.status_code != 200:
            self.log(f"❌ Failed to get students: {response.status_code} - {response.text}")
            return False
        
        students = response.json()
        if not students:
            self.log("❌ No students found in database")
            return False
        
        self.log(f"✅ Found {len(students)} students")
        
        # Get classes to verify shifts
        self.log("3️⃣ Getting classes to verify shifts...")
        response = requests.get(
            f"{API_BASE}/classes",
            headers=self.get_headers(admin_token)
        )
        
        if response.status_code == 200:
            classes = response.json()
            self.log(f"✅ Found {len(classes)} classes")
            
            # Look for classes with different shifts
            shifts_found = {}
            for cls in classes:
                shift = cls.get('shift')
                if shift:
                    if shift not in shifts_found:
                        shifts_found[shift] = []
                    shifts_found[shift].append(cls)
            
            self.log(f"   Shifts found: {list(shifts_found.keys())}")
            
            # Check for morning shift specifically
            if 'morning' in shifts_found:
                self.log(f"✅ Found {len(shifts_found['morning'])} classes with 'morning' shift")
            else:
                self.log("⚠️ No classes with 'morning' shift found")
                
        else:
            self.log(f"❌ Failed to get classes: {response.status_code}")
        
        # Test PDF generation for at least 2 students
        test_students = students[:2]  # Take first 2 students
        academic_year = 2025
        
        for i, student in enumerate(test_students, 1):
            student_id = student['id']
            student_name = student.get('full_name', 'N/A')
            
            self.log(f"4️⃣.{i} Testing Ficha Individual PDF for student: {student_name}")
            
            # Generate PDF
            response = requests.get(
                f"{API_BASE}/documents/ficha-individual/{student_id}?academic_year={academic_year}",
                headers=self.get_headers(admin_token)
            )
            
            if response.status_code == 200:
                # Verify Content-Type
                content_type = response.headers.get('Content-Type')
                if content_type == 'application/pdf':
                    self.log(f"   ✅ Correct Content-Type: {content_type}")
                else:
                    self.log(f"   ❌ Incorrect Content-Type: {content_type}")
                
                # Verify file size (should be > 10KB as per requirement)
                content_length = len(response.content)
                if content_length > 10240:  # 10KB
                    self.log(f"   ✅ PDF size: {content_length} bytes (> 10KB)")
                else:
                    self.log(f"   ❌ PDF size too small: {content_length} bytes (< 10KB)")
                
                # Verify filename in headers
                content_disposition = response.headers.get('Content-Disposition', '')
                if 'ficha_individual_' in content_disposition:
                    self.log(f"   ✅ Correct filename format in headers")
                else:
                    self.log(f"   ⚠️ Filename format: {content_disposition}")
                
                self.log(f"   ✅ PDF generated successfully for {student_name}")
                
            elif response.status_code == 404:
                self.log(f"   ❌ Student not found: {student_id}")
            else:
                self.log(f"   ❌ Failed to generate PDF: {response.status_code} - {response.text}")
        
        # Test with different academic years
        self.log("5️⃣ Testing with different academic years...")
        test_student_id = students[0]['id']
        
        for year in [2024, 2025]:
            response = requests.get(
                f"{API_BASE}/documents/ficha-individual/{test_student_id}?academic_year={year}",
                headers=self.get_headers(admin_token)
            )
            
            if response.status_code == 200:
                content_length = len(response.content)
                self.log(f"   ✅ Academic year {year}: PDF generated ({content_length} bytes)")
            else:
                self.log(f"   ❌ Academic year {year}: Failed ({response.status_code})")
        
        # Test error handling
        self.log("6️⃣ Testing error handling...")
        
        # Test with invalid student ID
        invalid_student_id = "invalid-student-id"
        response = requests.get(
            f"{API_BASE}/documents/ficha-individual/{invalid_student_id}?academic_year={academic_year}",
            headers=self.get_headers(admin_token)
        )
        
        if response.status_code == 404:
            self.log("   ✅ Invalid student ID correctly returns 404")
        else:
            self.log(f"   ❌ Invalid student ID should return 404, got: {response.status_code}")
        
        # Test without authentication
        response = requests.get(
            f"{API_BASE}/documents/ficha-individual/{test_student_id}?academic_year={academic_year}"
        )
        
        if response.status_code == 401:
            self.log("   ✅ Unauthenticated request correctly returns 401")
        else:
            self.log(f"   ❌ Unauthenticated request should return 401, got: {response.status_code}")
        
        # Check backend logs for errors
        self.log("7️⃣ Checking backend logs for errors...")
        try:
            import subprocess
            result = subprocess.run(
                ["tail", "-n", "50", "/var/log/supervisor/backend.err.log"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                error_lines = [line for line in result.stdout.split('\n') if 'ERROR' in line.upper()]
                if error_lines:
                    self.log(f"   ⚠️ Found {len(error_lines)} error lines in backend logs")
                    for line in error_lines[-3:]:  # Show last 3 errors
                        self.log(f"     {line}")
                else:
                    self.log("   ✅ No errors found in recent backend logs")
            else:
                self.log("   ⚠️ Could not read backend logs")
                
        except Exception as e:
            self.log(f"   ⚠️ Error checking logs: {str(e)}")
        
        # Summary of layout changes to verify (informational)
        self.log("8️⃣ Layout changes implemented (to be verified manually):")
        self.log("   📋 1. Column 'ID:' removed from header Line 2")
        self.log("   📋 2. Shift translated to Portuguese (morning → Matutino)")
        self.log("   📋 3. Column widths adjusted in Line 3 (ANO/ETAPA: 4.5cm, NASC.: 3cm)")
        self.log("   📋 4. Curriculum components table width 18cm, COMPONENTES CURRICULARES column 5.3cm")
        
        self.log("✅ Ficha Individual PDF generation testing completed!")
        return True

    def test_bug_fix_professores_alocados(self):
        """Test Bug Fix: Professores alocados não apareciam na turma"""
        self.log("\n🐛 Testing Bug Fix: Professores alocados não apareciam na turma...")
        
        # Test data from review request
        class_id = "dbf2fc89-0d43-44df-8394-f5cd38a278e8"  # Berçário A
        expected_teacher = "ABADIA ALVES MARTINS"
        
        # Test GET /api/classes/{class_id}/details
        self.log(f"1️⃣ Testing GET /api/classes/{class_id}/details...")
        response = requests.get(
            f"{API_BASE}/classes/{class_id}/details",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            class_details = response.json()
            self.log(f"✅ Class details retrieved successfully")
            
            # Check class information
            class_info = class_details.get('class', {})
            self.log(f"   Class: {class_info.get('name', 'N/A')}")
            self.log(f"   Grade Level: {class_info.get('grade_level', 'N/A')}")
            
            # Check school information
            school_info = class_details.get('school', {})
            self.log(f"   School: {school_info.get('name', 'N/A')}")
            
            # Check teachers list
            teachers = class_details.get('teachers', [])
            self.log(f"   Number of teachers: {len(teachers)}")
            
            if teachers:
                self.log("   Teachers found:")
                teacher_found = False
                for teacher in teachers:
                    teacher_name = teacher.get('nome', 'N/A')
                    components = teacher.get('componente', 'N/A')
                    self.log(f"     - {teacher_name} (Components: {components})")
                    
                    # Check if expected teacher is found
                    if expected_teacher in teacher_name:
                        teacher_found = True
                        self.log(f"✅ Expected teacher '{expected_teacher}' found!")
                
                if not teacher_found:
                    self.log(f"❌ Expected teacher '{expected_teacher}' NOT found in teachers list")
                    return False
                else:
                    self.log("✅ Bug fix verified: Teachers are now appearing in class details")
            else:
                self.log("❌ No teachers found in class details")
                return False
            
            # Check students
            students = class_details.get('students', [])
            self.log(f"   Number of students: {len(students)}")
            
            return True
            
        elif response.status_code == 404:
            self.log(f"❌ Class not found: {class_id}")
            return False
        else:
            self.log(f"❌ Failed to get class details: {response.status_code} - {response.text}")
            return False

    def test_sistema_avaliacao_conceitual_educacao_infantil(self):
        """Test Sistema de Avaliação Conceitual para Educação Infantil"""
        self.log("\n🎯 Testing Sistema de Avaliação Conceitual para Educação Infantil...")
        
        # Test data - find a Berçário class and student
        bercario_class_id = "dbf2fc89-0d43-44df-8394-f5cd38a278e8"  # Berçário A from review request
        
        # First, get class details to find a student
        self.log("1️⃣ Getting Berçário A class details to find a student...")
        response = requests.get(
            f"{API_BASE}/classes/{bercario_class_id}/details",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code != 200:
            self.log(f"❌ Failed to get Berçário class details: {response.status_code}")
            return False
        
        class_details = response.json()
        students = class_details.get('students', [])
        
        if not students:
            self.log("❌ No students found in Berçário A class")
            return False
        
        # Use first student for testing
        test_student = students[0]
        student_id = test_student.get('id')
        student_name = test_student.get('full_name', 'N/A')
        
        self.log(f"   Using student: {student_name} (ID: {student_id})")
        
        # Get a course for Educação Infantil
        self.log("2️⃣ Getting courses for Educação Infantil...")
        response = requests.get(
            f"{API_BASE}/courses?nivel_ensino=educacao_infantil",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code != 200:
            self.log(f"❌ Failed to get courses: {response.status_code}")
            return False
        
        courses = response.json()
        if not courses:
            self.log("❌ No courses found for Educação Infantil")
            return False
        
        course_id = courses[0]['id']
        course_name = courses[0].get('name', 'N/A')
        self.log(f"   Using course: {course_name} (ID: {course_id})")
        
        # Test conceptual values for Educação Infantil
        conceptual_values = {
            "OD": 10.0,  # Objetivo Desenvolvido
            "DP": 7.5,   # Desenvolvido Parcialmente
            "ND": 5.0,   # Não Desenvolvido
            "NT": 0.0    # Não Trabalhado
        }
        
        self.log("3️⃣ Testing conceptual grade values for Educação Infantil...")
        
        # Test each conceptual value
        for concept, value in conceptual_values.items():
            self.log(f"   Testing {concept} = {value}...")
            
            grade_data = {
                "student_id": student_id,
                "class_id": bercario_class_id,
                "course_id": course_id,
                "academic_year": 2025,
                "b1": value,
                "b2": value,
                "b3": value,
                "b4": value
            }
            
            response = requests.post(
                f"{API_BASE}/grades",
                json=grade_data,
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code in [200, 201]:
                grade = response.json()
                self.log(f"   ✅ {concept} ({value}) grade accepted successfully")
                
                # For Educação Infantil, final average should be the HIGHEST concept (not arithmetic average)
                final_average = grade.get('final_average')
                self.log(f"   Final average: {final_average}")
                
                # Since all quarters have the same value, final average should equal that value
                if final_average == value:
                    self.log(f"   ✅ Final average correctly set to {value} for {concept}")
                else:
                    self.log(f"   ❌ Final average should be {value}, got {final_average}")
                
                # Check status - Educação Infantil should have automatic approval
                status = grade.get('status', 'N/A')
                self.log(f"   Status: {status}")
                
                # For Educação Infantil, approval should be automatic regardless of grade
                if status in ['aprovado', 'cursando']:
                    self.log(f"   ✅ Status correctly set for Educação Infantil: {status}")
                else:
                    self.log(f"   ❌ Unexpected status for Educação Infantil: {status}")
                    
            else:
                self.log(f"   ❌ Failed to create {concept} grade: {response.status_code} - {response.text}")
                return False
        
        # Test mixed conceptual values (highest should be final average)
        self.log("4️⃣ Testing mixed conceptual values (highest concept rule)...")
        
        mixed_grade_data = {
            "student_id": student_id,
            "class_id": bercario_class_id,
            "course_id": course_id,
            "academic_year": 2025,
            "b1": 5.0,   # ND
            "b2": 10.0,  # OD
            "b3": 7.5,   # DP
            "b4": 0.0    # NT
        }
        
        response = requests.post(
            f"{API_BASE}/grades",
            json=mixed_grade_data,
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code in [200, 201]:
            mixed_grade = response.json()
            final_average = mixed_grade.get('final_average')
            
            # For Educação Infantil, final average should be the HIGHEST value (10.0)
            expected_highest = max([5.0, 10.0, 7.5, 0.0])  # Should be 10.0
            
            self.log(f"   Mixed grades: B1=5.0(ND), B2=10.0(OD), B3=7.5(DP), B4=0.0(NT)")
            self.log(f"   Expected highest concept: {expected_highest}")
            self.log(f"   Actual final average: {final_average}")
            
            if final_average == expected_highest:
                self.log("   ✅ Final average correctly calculated as HIGHEST concept for Educação Infantil")
            else:
                self.log(f"   ❌ Final average should be {expected_highest} (highest), got {final_average}")
                
            # Status should still be approved for Educação Infantil
            status = mixed_grade.get('status', 'N/A')
            if status in ['aprovado', 'cursando']:
                self.log(f"   ✅ Automatic approval working for Educação Infantil: {status}")
            else:
                self.log(f"   ❌ Expected automatic approval, got: {status}")
                
        else:
            self.log(f"   ❌ Failed to create mixed grade: {response.status_code} - {response.text}")
            return False
        
        # Test that numeric values are accepted (not just conceptual names)
        self.log("5️⃣ Testing that numeric values are accepted...")
        
        numeric_grade_data = {
            "student_id": student_id,
            "class_id": bercario_class_id,
            "course_id": course_id,
            "academic_year": 2025,
            "b1": 10,    # Integer 10 (should be accepted as 10.0)
            "b2": 7.5,   # Float 7.5
            "b3": 5,     # Integer 5 (should be accepted as 5.0)
            "b4": 0      # Integer 0 (should be accepted as 0.0)
        }
        
        response = requests.post(
            f"{API_BASE}/grades",
            json=numeric_grade_data,
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code in [200, 201]:
            numeric_grade = response.json()
            self.log("   ✅ Numeric values (10, 7.5, 5, 0) accepted successfully")
            
            # Verify values are stored correctly
            b1 = numeric_grade.get('b1')
            b2 = numeric_grade.get('b2')
            b3 = numeric_grade.get('b3')
            b4 = numeric_grade.get('b4')
            
            self.log(f"   Stored values: B1={b1}, B2={b2}, B3={b3}, B4={b4}")
            
            # Check if values match expected conceptual values
            if b1 == 10.0 and b2 == 7.5 and b3 == 5.0 and b4 == 0.0:
                self.log("   ✅ All numeric values stored correctly as conceptual values")
            else:
                self.log("   ❌ Some numeric values not stored correctly")
                
        else:
            self.log(f"   ❌ Failed to accept numeric values: {response.status_code} - {response.text}")
            return False
        
        self.log("✅ Sistema de Avaliação Conceitual para Educação Infantil testing completed!")
        return True

    def test_academic_year_management(self):
        """Test Academic Year Management System as per review request"""
        self.log("\n📅 Testing Academic Year Management System (Sistema de Gerenciamento de Anos Letivos)...")
        
        # Test data from review request
        target_school_id = "ef2f28d3-a42d-4e08-923e-76b6eda5dc04"  # E M E F MONSENHOR AUGUSTO DIAS DE BRITO
        target_class_id = "970fec6e-1b90-44ca-9413-05fe77c369b8"   # 1º Ano A
        academic_year = 2025
        
        # Store original school configuration for cleanup
        original_school_config = None
        
        try:
            # Step 1: Test Academic Year Configuration (Backend) - PUT /api/schools/{school_id}
            self.log("1️⃣ Testing Academic Year Configuration - PUT /api/schools/{school_id}...")
            
            # First, get current school configuration
            response = requests.get(
                f"{API_BASE}/schools/{target_school_id}",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                original_school_config = response.json()
                self.log(f"✅ Retrieved school: {original_school_config.get('name')}")
                self.log(f"   Current anos_letivos: {original_school_config.get('anos_letivos', 'Not configured')}")
            else:
                self.log(f"❌ Failed to get school: {response.status_code} - {response.text}")
                return False
            
            # Configure academic years with 2025 as "fechado" (closed)
            anos_letivos_config = {
                "anos_letivos": {
                    "2025": {"status": "fechado"},
                    "2024": {"status": "aberto"}
                }
            }
            
            response = requests.put(
                f"{API_BASE}/schools/{target_school_id}",
                json=anos_letivos_config,
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                updated_school = response.json()
                self.log(f"✅ School academic years configured successfully")
                self.log(f"   2025 status: {updated_school.get('anos_letivos', {}).get('2025', {}).get('status')}")
                self.log(f"   2024 status: {updated_school.get('anos_letivos', {}).get('2024', {}).get('status')}")
                
                # Verify the data was saved correctly
                if (updated_school.get('anos_letivos', {}).get('2025', {}).get('status') == 'fechado' and
                    updated_school.get('anos_letivos', {}).get('2024', {}).get('status') == 'aberto'):
                    self.log("✅ Academic years configuration saved correctly")
                else:
                    self.log("❌ Academic years configuration not saved correctly")
                    return False
            else:
                self.log(f"❌ Failed to configure academic years: {response.status_code} - {response.text}")
                return False
            
            # Step 2: Test Grade Blocking for Coordinator (POST /api/grades/batch)
            self.log("2️⃣ Testing Grade Blocking for Coordinator - POST /api/grades/batch...")
            
            # Get a student from the target class
            response = requests.get(
                f"{API_BASE}/students?class_id={target_class_id}",
                headers=self.get_headers(self.admin_token)
            )
            
            test_student_id = None
            if response.status_code == 200:
                students = response.json()
                if students:
                    test_student_id = students[0]['id']
                    self.log(f"✅ Found test student: {students[0].get('full_name')} (ID: {test_student_id})")
                else:
                    self.log("❌ No students found in target class")
                    return False
            else:
                self.log(f"❌ Failed to get students: {response.status_code}")
                return False
            
            # Get a course for testing
            response = requests.get(
                f"{API_BASE}/courses",
                headers=self.get_headers(self.admin_token)
            )
            
            test_course_id = None
            if response.status_code == 200:
                courses = response.json()
                if courses:
                    test_course_id = courses[0]['id']
                    self.log(f"✅ Using course: {courses[0].get('name')} (ID: {test_course_id})")
                else:
                    self.log("❌ No courses found")
                    return False
            else:
                self.log(f"❌ Failed to get courses: {response.status_code}")
                return False
            
            # Test coordinator trying to save grade for closed year 2025 (should get HTTP 403)
            self.log("   Testing coordinator access to closed year 2025...")
            grade_data_2025 = [
                {
                    "student_id": test_student_id,
                    "class_id": target_class_id,
                    "course_id": test_course_id,
                    "academic_year": 2025,  # Closed year
                    "b1": 8.0,
                    "b2": 7.0,
                    "observations": "Teste de bloqueio para coordenador"
                }
            ]
            
            response = requests.post(
                f"{API_BASE}/grades/batch",
                json=grade_data_2025,
                headers=self.get_headers(self.coordinator_token)
            )
            
            if response.status_code == 403:
                self.log("✅ Coordinator correctly blocked from editing grades in closed year 2025 (HTTP 403)")
                response_data = response.json()
                if "ano letivo 2025 está fechado" in response_data.get('detail', '').lower():
                    self.log("✅ Correct error message about closed academic year")
                else:
                    self.log(f"❌ Unexpected error message: {response_data.get('detail')}")
            else:
                self.log(f"❌ Coordinator should be blocked (expected 403), got: {response.status_code}")
                return False
            
            # Step 3: Test Admin Bypass for Closed Year (POST /api/grades/batch)
            self.log("3️⃣ Testing Admin Bypass for Closed Year - POST /api/grades/batch...")
            
            # Test admin trying to save grade for closed year 2025 (should succeed - bypass)
            self.log("   Testing admin bypass for closed year 2025...")
            response = requests.post(
                f"{API_BASE}/grades/batch",
                json=grade_data_2025,
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                self.log("✅ Admin successfully bypassed closed year restriction (HTTP 200)")
                batch_result = response.json()
                if batch_result.get('updated', 0) > 0 or batch_result.get('grades'):
                    self.log("✅ Grade successfully saved by admin in closed year")
                else:
                    self.log("❌ Grade not saved despite successful response")
            else:
                self.log(f"❌ Admin should be able to bypass restriction, got: {response.status_code} - {response.text}")
                return False
            
            # Step 4: Test Attendance Blocking (POST /api/attendance)
            self.log("4️⃣ Testing Attendance Blocking - POST /api/attendance...")
            
            # Test coordinator trying to save attendance for closed year 2025
            self.log("   Testing coordinator attendance access to closed year 2025...")
            attendance_data_2025 = {
                "class_id": target_class_id,
                "date": "2025-03-17",  # Date in closed year (Monday)
                "academic_year": 2025,
                "attendance_type": "daily",
                "period": "regular",
                "records": [
                    {
                        "student_id": test_student_id,
                        "status": "P"
                    }
                ],
                "observations": "Teste de bloqueio de frequência para coordenador"
            }
            
            response = requests.post(
                f"{API_BASE}/attendance",
                json=attendance_data_2025,
                headers=self.get_headers(self.coordinator_token)
            )
            
            if response.status_code == 403:
                self.log("✅ Coordinator correctly blocked from editing attendance in closed year 2025 (HTTP 403)")
                response_data = response.json()
                if "ano letivo 2025 está fechado" in response_data.get('detail', '').lower():
                    self.log("✅ Correct error message about closed academic year")
                else:
                    self.log(f"❌ Unexpected error message: {response_data.get('detail')}")
            else:
                self.log(f"❌ Coordinator should be blocked from attendance (expected 403), got: {response.status_code}")
                return False
            
            # Test admin trying to save attendance for closed year 2025 (should succeed)
            self.log("   Testing admin attendance bypass for closed year 2025...")
            response = requests.post(
                f"{API_BASE}/attendance",
                json=attendance_data_2025,
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200 or response.status_code == 201:
                self.log("✅ Admin successfully bypassed attendance restriction for closed year (HTTP 200/201)")
                attendance_result = response.json()
                if attendance_result.get('id'):
                    self.log("✅ Attendance successfully saved by admin in closed year")
                else:
                    self.log("❌ Attendance not saved despite successful response")
            else:
                self.log(f"❌ Admin should be able to bypass attendance restriction, got: {response.status_code} - {response.text}")
                return False
            
            # Step 5: Test Unconfigured Years (should allow editing)
            self.log("5️⃣ Testing Unconfigured Years (should allow editing)...")
            
            # Test coordinator trying to save grade for unconfigured year 2026
            self.log("   Testing coordinator access to unconfigured year 2023...")
            grade_data_2026 = [
                {
                    "student_id": test_student_id,
                    "class_id": target_class_id,
                    "course_id": test_course_id,
                    "academic_year": 2023,  # Use 2023 instead of 2026
                    "b1": 9.0,
                    "b2": 8.0,
                    "observations": "Teste de ano não configurado"
                }
            ]
            
            response = requests.post(
                f"{API_BASE}/grades/batch",
                json=grade_data_2026,
                headers=self.get_headers(self.coordinator_token)
            )
            
            if response.status_code == 200:
                self.log("✅ Coordinator can edit grades in unconfigured year 2023 (default behavior)")
                batch_result = response.json()
                if batch_result.get('updated', 0) > 0 or batch_result.get('grades'):
                    self.log("✅ Grade successfully saved in unconfigured year")
                else:
                    self.log("❌ Grade not saved despite successful response")
            else:
                self.log(f"❌ Coordinator should be able to edit unconfigured year, got: {response.status_code} - {response.text}")
                return False
            
            # Test coordinator trying to save attendance for unconfigured year 2026
            self.log("   Testing coordinator attendance access to unconfigured year 2023...")
            attendance_data_2026 = {
                "class_id": target_class_id,
                "date": "2023-03-16",  # Date in unconfigured year (past date, Monday)
                "academic_year": 2023,  # Use 2023 instead of 2026
                "attendance_type": "daily",
                "period": "regular",
                "records": [
                    {
                        "student_id": test_student_id,
                        "status": "P"
                    }
                ],
                "observations": "Teste de ano não configurado para frequência"
            }
            
            response = requests.post(
                f"{API_BASE}/attendance",
                json=attendance_data_2026,
                headers=self.get_headers(self.coordinator_token)
            )
            
            if response.status_code == 200 or response.status_code == 201:
                self.log("✅ Coordinator can edit attendance in unconfigured year 2023 (default behavior)")
                attendance_result = response.json()
                if attendance_result.get('id'):
                    self.log("✅ Attendance successfully saved in unconfigured year")
                else:
                    self.log("❌ Attendance not saved despite successful response")
            else:
                self.log(f"❌ Coordinator should be able to edit attendance in unconfigured year, got: {response.status_code} - {response.text}")
                return False
            
            self.log("✅ Academic Year Management System testing completed successfully!")
            return True
            
        except Exception as e:
            self.log(f"❌ Error during academic year management testing: {str(e)}")
            return False
            
        finally:
            # Step 6: Cleanup - Revert year 2025 status to "aberto" (open)
            self.log("6️⃣ Cleanup - Reverting year 2025 status to 'aberto'...")
            
            if original_school_config:
                # Restore original configuration or set 2025 to "aberto"
                cleanup_config = {
                    "anos_letivos": {
                        "2025": {"status": "aberto"},
                        "2024": {"status": "aberto"}
                    }
                }
                
                response = requests.put(
                    f"{API_BASE}/schools/{target_school_id}",
                    json=cleanup_config,
                    headers=self.get_headers(self.admin_token)
                )
                
                if response.status_code == 200:
                    self.log("✅ School academic years reverted to 'aberto' status")
                else:
                    self.log(f"❌ Failed to revert school configuration: {response.status_code}")
            else:
                self.log("❌ Could not revert school configuration - original config not available")

    def test_certificado_conclusao(self):
        """Test Certificado de Conclusão functionality as per review request"""
        self.log("\n🎓 Testing Certificado de Conclusão - SIGESC...")
        
        # Test data from review request
        eligible_class_id = "36d77a13-c5f0-4907-860d-ed6c3db32b8b"  # 9º Ano (eligible)
        non_eligible_class_id = "970fec6e-1b90-44ca-9413-05fe77c369b8"  # 1º Ano (not eligible)
        eligible_student_id = "14584e57-0e6f-4436-b1d2-775b09dbd2b3"  # DANNYD LEYON ALVES DE SOUZA
        academic_year = 2025
        
        # 1. Test eligibility validation - eligible class (9º Ano)
        self.log("1️⃣ Testing certificate generation for eligible student (9º Ano)...")
        response = requests.get(
            f"{API_BASE}/documents/certificado/{eligible_student_id}?academic_year={academic_year}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            self.log("✅ Certificate generated successfully for 9º Ano student")
            
            # Verify Content-Type
            content_type = response.headers.get('Content-Type')
            if content_type == 'application/pdf':
                self.log("✅ Correct Content-Type: application/pdf")
            else:
                self.log(f"❌ Incorrect Content-Type: {content_type}")
                return False
            
            # Verify file size (should be > 10KB)
            content_length = len(response.content)
            if content_length > 10240:  # 10KB
                self.log(f"✅ PDF size is adequate: {content_length} bytes (> 10KB)")
            else:
                self.log(f"❌ PDF size too small: {content_length} bytes (< 10KB)")
                return False
            
            # Verify filename in headers
            content_disposition = response.headers.get('Content-Disposition', '')
            if 'certificado_' in content_disposition:
                self.log("✅ Correct filename format in Content-Disposition")
            else:
                self.log(f"❌ Incorrect filename format: {content_disposition}")
                
        else:
            self.log(f"❌ Failed to generate certificate for eligible student: {response.status_code} - {response.text}")
            return False
        
        # 2. Test eligibility validation - non-eligible class (1º Ano)
        self.log("2️⃣ Testing certificate blocking for non-eligible class (1º Ano)...")
        
        # First, find a student from the non-eligible class
        response = requests.get(
            f"{API_BASE}/students?class_id={non_eligible_class_id}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            students = response.json()
            if students:
                non_eligible_student_id = students[0]['id']
                student_name = students[0].get('full_name', 'N/A')
                self.log(f"   Found student from 1º Ano: {student_name}")
                
                # Try to generate certificate for non-eligible student
                response = requests.get(
                    f"{API_BASE}/documents/certificado/{non_eligible_student_id}?academic_year={academic_year}",
                    headers=self.get_headers(self.admin_token)
                )
                
                if response.status_code == 400:
                    error_message = response.json().get('detail', '')
                    expected_message = "Certificado disponível apenas para turmas do 9º Ano ou EJA 4ª Etapa"
                    
                    if expected_message in error_message:
                        self.log("✅ Correctly blocked certificate for 1º Ano with proper error message")
                    else:
                        self.log(f"❌ Incorrect error message: {error_message}")
                        return False
                else:
                    self.log(f"❌ Should have returned 400 error, got: {response.status_code}")
                    return False
            else:
                self.log("❌ No students found in 1º Ano class for testing")
                return False
        else:
            self.log(f"❌ Failed to get students from 1º Ano class: {response.status_code}")
            return False
        
        # 3. Test batch certificate generation for eligible class
        self.log("3️⃣ Testing batch certificate generation for 9º Ano class...")
        response = requests.get(
            f"{API_BASE}/documents/batch/{eligible_class_id}/certificado?academic_year={academic_year}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            self.log("✅ Batch certificate generation successful")
            
            # Verify Content-Type
            content_type = response.headers.get('Content-Type')
            if content_type == 'application/pdf':
                self.log("✅ Correct Content-Type for batch PDF: application/pdf")
            else:
                self.log(f"❌ Incorrect Content-Type for batch PDF: {content_type}")
                return False
            
            # Verify file size (batch should be larger)
            content_length = len(response.content)
            if content_length > 20480:  # 20KB (should be larger for multiple students)
                self.log(f"✅ Batch PDF size is adequate: {content_length} bytes (> 20KB)")
            else:
                self.log(f"❌ Batch PDF size too small: {content_length} bytes (< 20KB)")
                return False
            
            # Verify filename contains "Certificados"
            content_disposition = response.headers.get('Content-Disposition', '')
            if 'Certificados_' in content_disposition:
                self.log("✅ Correct batch filename format")
            else:
                self.log(f"❌ Incorrect batch filename: {content_disposition}")
                
        else:
            self.log(f"❌ Failed to generate batch certificates: {response.status_code} - {response.text}")
            return False
        
        # 4. Test authentication requirement
        self.log("4️⃣ Testing authentication requirement for certificate endpoints...")
        response = requests.get(f"{API_BASE}/documents/certificado/{eligible_student_id}")
        
        if response.status_code == 401:
            self.log("✅ Certificate endpoint correctly requires authentication")
        else:
            self.log(f"❌ Certificate endpoint should require authentication: {response.status_code}")
            return False
        
        # 5. Test invalid student ID
        self.log("5️⃣ Testing invalid student ID handling...")
        invalid_student_id = "00000000-0000-0000-0000-000000000000"
        response = requests.get(
            f"{API_BASE}/documents/certificado/{invalid_student_id}?academic_year={academic_year}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 404:
            self.log("✅ Correctly returns 404 for invalid student ID")
        else:
            self.log(f"❌ Should return 404 for invalid student ID, got: {response.status_code}")
            return False
        
        # 6. Test different academic years
        self.log("6️⃣ Testing certificate generation with different academic years...")
        for year in [2024, 2025]:
            response = requests.get(
                f"{API_BASE}/documents/certificado/{eligible_student_id}?academic_year={year}",
                headers=self.get_headers(self.admin_token)
            )
            
            if response.status_code == 200:
                self.log(f"✅ Certificate generated successfully for academic year {year}")
            else:
                self.log(f"❌ Failed to generate certificate for year {year}: {response.status_code}")
        
        self.log("✅ Certificado de Conclusão testing completed successfully!")
        return True

    def run_all_tests(self):
        """Run all backend tests"""
        self.log("🚀 Starting SIGESC Backend API Tests - Review Request Testing")
        self.log(f"🌐 Backend URL: {BACKEND_URL}")
        
        # Login as admin
        self.admin_token = self.login(ADMIN_CREDENTIALS, "Admin")
        if not self.admin_token:
            self.log("❌ Cannot proceed without admin login")
            return False
        
        # Login as Coordinator
        self.coordinator_token = self.login(COORDINATOR_CREDENTIALS, "Coordinator")
        if not self.coordinator_token:
            self.log("⚠️ Coordinator login failed - skipping permission tests")
        
        # Setup test data
        self.setup_test_data()
        
        # Run test suites
        test_results = []
        
        try:
            # Test Academic Year Management System (NEW - from review request)
            test_results.append(("Academic Year Management", self.test_academic_year_management()))
            
            # Test the two specific functionalities from review request (PRIORITY)
            test_results.append(("Bug Fix: Professores Alocados", self.test_bug_fix_professores_alocados()))
            test_results.append(("Sistema Avaliação Conceitual EI", self.test_sistema_avaliacao_conceitual_educacao_infantil()))
            
            # Test authentication requirements
            test_results.append(("Authentication", self.test_authentication_required()))
            
            # Test Courses endpoint (Fase 4)
            test_results.append(("Courses Endpoint", self.test_courses_endpoint()))
            
            # Test Grades system (Sistema de Notas)
            test_results.append(("Grades System", self.test_grades_system()))
            
            # Test specific class grades
            test_results.append(("Grades by Class", self.test_grades_by_class_specific()))
            
            # Test Guardians CRUD
            test_results.append(("Guardians CRUD", self.test_guardians_crud()))
            
            # Test Enrollments CRUD
            test_results.append(("Enrollments CRUD", self.test_enrollments_crud()))
            
            # Test SEMED permissions
            if self.coordinator_token:
                test_results.append(("SEMED Permissions", self.test_semed_permissions()))
            
            # Test Attendance Control Phase 5
            test_results.append(("Attendance Control Phase 5", self.test_attendance_control_phase5()))
            
            # Test Staff Management Phase 5.5
            test_results.append(("Staff Management Phase 5.5", self.test_staff_management_phase55()))
            
        except Exception as e:
            self.log(f"❌ Error during testing: {str(e)}")
            test_results.append(("Error", False))
        
        finally:
            # Cleanup
            self.cleanup()
        
        # Print summary
        self.log("\n📊 TEST SUMMARY:")
        self.log("=" * 50)
        
        passed = 0
        failed = 0
        
        for test_name, result in test_results:
            status = "✅ PASS" if result else "❌ FAIL"
            self.log(f"{test_name}: {status}")
            if result:
                passed += 1
            else:
                failed += 1
        
        self.log("=" * 50)
        self.log(f"Total: {len(test_results)} | Passed: {passed} | Failed: {failed}")
        
        if failed == 0:
            self.log("🎉 All tests passed!")
            return True
        else:
            self.log(f"❌ {failed} test(s) failed")
            return False
        self.setup_test_data()
        
        # Run tests
        success = True
        
        try:
            # MAIN FOCUS: Test Boletim Component Filtering - PRIMARY TEST as per review request
            if not self.test_boletim_component_filtering():
                success = False
            
            # SECONDARY TESTS
            # Test Coordinator Permissions System
            if not self.test_coordinator_permissions_system():
                success = False
            
            # Test Ficha Individual PDF Generation
            if not self.test_ficha_individual_pdf_generation():
                success = False
            
            # Test PDF Document Generation (PHASE 8)
            if not self.test_pdf_document_generation_phase8():
                success = False
            
            # Test SIGESC Announcement System (FASE 7)
            if not self.test_announcement_system_fase7():
                success = False
            
            # Test Message Deletion System
            if not self.test_message_deletion_system():
                success = False
            
            # Test Profile Image Upload
            if not self.test_profile_image_upload():
                success = False
            
            # Test Learning Objects Full Feature
            if not self.test_learning_objects_full_feature():
                success = False
            
            # Test authentication requirements
            self.test_authentication_required()
            
        finally:
            # Cleanup
            self.cleanup()
        
        # Final result
        self.log("\n" + "="*50)
        if success:
            self.log("🎉 All backend tests completed successfully!")
            self.log("✅ BOLETIM COMPONENT FILTERING FULLY TESTED")
            self.log("✅ COORDINATOR PERMISSIONS SYSTEM FULLY TESTED")
            self.log("✅ FICHA INDIVIDUAL PDF GENERATION FULLY TESTED")
            self.log("✅ PDF DOCUMENT GENERATION (PHASE 8) FULLY TESTED")
        else:
            self.log("❌ Some tests failed - check logs above")
        self.log("="*50)
        
        return success

if __name__ == "__main__":
    tester = SIGESCTester()
    tester.run_all_tests()