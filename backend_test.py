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
BACKEND_URL = os.getenv('REACT_APP_BACKEND_URL', 'https://eduflow-77.preview.emergentagent.com')
API_BASE = f"{BACKEND_URL}/api"

# Test credentials
ADMIN_CREDENTIALS = {
    "email": "admin@sigesc.com",
    "password": "password"
}

SEMED_CREDENTIALS = {
    "email": "semed@sigesc.com", 
    "password": "password"
}

class SIGESCTester:
    def __init__(self):
        self.admin_token = None
        self.semed_token = None
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
            headers=self.get_headers(self.semed_token)
        )
        
        if response.status_code == 200:
            self.log("✅ SEMED can list guardians")
        else:
            self.log(f"❌ SEMED cannot list guardians: {response.status_code}")
        
        # Test SEMED can list enrollments
        self.log("2️⃣ Testing SEMED can list enrollments...")
        response = requests.get(
            f"{API_BASE}/enrollments",
            headers=self.get_headers(self.semed_token)
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
            headers=self.get_headers(self.semed_token)
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
            headers=self.get_headers(self.semed_token)
        )
        
        if response.status_code == 403:
            self.log("✅ SEMED correctly denied enrollment creation (403)")
        elif response.status_code == 401:
            self.log("✅ SEMED correctly denied enrollment creation (401)")
        else:
            self.log(f"❌ SEMED should not be able to create enrollment: {response.status_code}")
    
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
    
    def run_all_tests(self):
        """Run all backend tests"""
        self.log("🚀 Starting SIGESC Backend API Tests")
        self.log(f"🌐 Backend URL: {BACKEND_URL}")
        
        # Login as admin
        self.admin_token = self.login(ADMIN_CREDENTIALS, "Admin")
        if not self.admin_token:
            self.log("❌ Cannot proceed without admin login")
            return False
        
        # Login as SEMED
        self.semed_token = self.login(SEMED_CREDENTIALS, "SEMED")
        if not self.semed_token:
            self.log("⚠️ SEMED login failed - skipping permission tests")
        
        # Setup test data
        self.setup_test_data()
        
        # Run tests
        success = True
        
        try:
            # Test authentication requirements
            self.test_authentication_required()
            
            # Test Grades System (main focus of this review)
            if not self.test_grades_system():
                success = False
            
            # Test Guardians CRUD
            if not self.test_guardians_crud():
                success = False
            
            # Test Enrollments CRUD
            if not self.test_enrollments_crud():
                success = False
            
            # Test SEMED permissions
            if self.semed_token:
                self.test_semed_permissions()
            
        finally:
            # Cleanup
            self.cleanup()
        
        # Final result
        self.log("\n" + "="*50)
        if success:
            self.log("🎉 All backend tests completed successfully!")
        else:
            self.log("❌ Some tests failed - check logs above")
        self.log("="*50)
        
        return success

if __name__ == "__main__":
    tester = SIGESCTester()
    tester.run_all_tests()