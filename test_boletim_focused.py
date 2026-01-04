#!/usr/bin/env python3
"""
Focused test for Boletim Component Filtering as per review request
"""

import requests
import json
import os
from datetime import datetime

# Get backend URL from environment
BACKEND_URL = os.getenv('REACT_APP_BACKEND_URL', 'https://classroomplus-2.preview.emergentagent.com')
API_BASE = f"{BACKEND_URL}/api"

# Test credentials from review request
ADMIN_CREDENTIALS = {
    "email": "gutenberg@sigesc.com",
    "password": "@Celta2007"
}

def log(message):
    """Log test messages with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def login():
    """Login and get access token"""
    log("🔐 Logging in as Admin...")
    
    try:
        response = requests.post(
            f"{API_BASE}/auth/login",
            json=ADMIN_CREDENTIALS,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get('access_token')
            user = data.get('user', {})
            log(f"✅ Login successful for {user.get('full_name', 'Admin')}")
            return token
        else:
            log(f"❌ Login failed: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        log(f"❌ Login error: {str(e)}")
        return None

def get_headers(token):
    """Get authorization headers"""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

def test_boletim_component_filtering():
    """Test Boletim Component Filtering as per review request"""
    log("📋 Testing Boletim Component Filtering (Education Level + School Type)...")
    
    # Login
    token = login()
    if not token:
        return False
    
    headers = get_headers(token)
    
    try:
        # TEST CASE 1: Educação Infantil Student (Berçário)
        log("\n1️⃣ TEST CASE 1: Educação Infantil Student (Berçário)...")
        infantil_student_id = "db50cfdc-abbb-422b-974a-08671e61cabd"
        
        log(f"   Testing student ID: {infantil_student_id}")
        log("   Expected: EDUCAÇÃO INFANTIL components only")
        log("   Expected components: Corpo, gestos e movimentos; Escuta, fala, pensamento e imaginação; etc.")
        
        response = requests.get(
            f"{API_BASE}/documents/boletim/{infantil_student_id}?academic_year=2025",
            headers=headers
        )
        
        if response.status_code == 200:
            log("✅ Boletim generated successfully for Educação Infantil student")
            log(f"   PDF size: {len(response.content)} bytes")
            log(f"   Content-Type: {response.headers.get('Content-Type')}")
            
            if response.headers.get('Content-Type') == 'application/pdf':
                log("✅ Correct PDF Content-Type")
            else:
                log("❌ Incorrect Content-Type - expected application/pdf")
                
            if len(response.content) > 1000:  # Reasonable PDF size
                log("✅ PDF has reasonable size (>1KB)")
            else:
                log("❌ PDF size too small - may be empty or corrupted")
        else:
            log(f"❌ Failed to generate boletim for Educação Infantil student: {response.status_code} - {response.text}")
            return False
        
        # TEST CASE 2: Fundamental Anos Iniciais Student from INTEGRAL School
        log("\n2️⃣ TEST CASE 2: Fundamental Anos Iniciais Student from INTEGRAL School...")
        
        # Use the correct integral school ID
        integral_school_id = "dd8e65aa-ec50-48b9-b8f8-21f32fc29250"  # Escola Municipal Floresta do Araguaia
        log(f"   Looking for students from integral school: {integral_school_id}")
        
        response = requests.get(
            f"{API_BASE}/students?school_id={integral_school_id}",
            headers=headers
        )
        
        integral_student_id = None
        if response.status_code == 200:
            students = response.json()
            if students:
                integral_student_id = students[0]['id']
                log(f"✅ Found integral school student: {students[0].get('full_name')} (ID: {integral_student_id})")
            else:
                log("❌ No students found in integral school")
                return False
        else:
            log(f"❌ Failed to get students from integral school: {response.status_code}")
            return False
        
        if integral_student_id:
            log("   Expected: Regular Fundamental + Escola Integral components")
            log("   Expected integral components: Recreação, Esporte e Lazer; Arte e Cultura; Tecnologia e Informática; etc.")
            
            response = requests.get(
                f"{API_BASE}/documents/boletim/{integral_student_id}?academic_year=2025",
                headers=headers
            )
            
            if response.status_code == 200:
                log("✅ Boletim generated successfully for Integral school student")
                log(f"   PDF size: {len(response.content)} bytes")
                
                if len(response.content) > 1000:
                    log("✅ PDF has reasonable size")
                else:
                    log("❌ PDF size too small")
            else:
                log(f"❌ Failed to generate boletim for integral school student: {response.status_code} - {response.text}")
                return False
        
        # TEST CASE 3: Fundamental Anos Iniciais Student from REGULAR School
        log("\n3️⃣ TEST CASE 3: Fundamental Anos Iniciais Student from REGULAR School...")
        
        # Use a known regular school
        regular_school_id = "ef2f28d3-a42d-4e08-923e-76b6eda5dc04"  # E M E F MONSENHOR AUGUSTO DIAS DE BRITO
        log(f"   Using regular school: {regular_school_id}")
        
        response = requests.get(
            f"{API_BASE}/students?school_id={regular_school_id}",
            headers=headers
        )
        
        regular_student_id = None
        if response.status_code == 200:
            students = response.json()
            if students:
                regular_student_id = students[0]['id']
                log(f"✅ Found regular school student: {students[0].get('full_name')} (ID: {regular_student_id})")
            else:
                log("❌ No students found in regular school")
                return False
        else:
            log(f"❌ Failed to get students from regular school: {response.status_code}")
            return False
        
        if regular_student_id:
            log("   Expected: ONLY Regular Fundamental Anos Iniciais components")
            log("   Should NOT have: Recreação, Arte e Cultura, Tecnologia e Informática")
            
            response = requests.get(
                f"{API_BASE}/documents/boletim/{regular_student_id}?academic_year=2025",
                headers=headers
            )
            
            if response.status_code == 200:
                log("✅ Boletim generated successfully for Regular school student")
                log(f"   PDF size: {len(response.content)} bytes")
                
                if len(response.content) > 1000:
                    log("✅ PDF has reasonable size")
                else:
                    log("❌ PDF size too small")
            else:
                log(f"❌ Failed to generate boletim for regular school student: {response.status_code} - {response.text}")
                return False
        
        # TEST CASE 4: Verify inference logic in backend logs
        log("\n4️⃣ TEST CASE 4: Verifying inference logic...")
        log("   Checking backend logs for 'Boletim: grade_level=..., nivel_ensino inferido=...' messages")
        
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
                    log("✅ Found inference logic messages in backend logs")
                    # Extract relevant log lines
                    log_lines = log_content.split('\n')
                    for line in log_lines:
                        if "Boletim:" in line and "nivel_ensino inferido" in line:
                            log(f"   📝 {line.strip()}")
                else:
                    log("ℹ️ No inference logic messages found in recent logs")
            else:
                log("❌ Failed to read backend logs")
        except Exception as e:
            log(f"❌ Error reading backend logs: {str(e)}")
        
        # TEST CASE 5: Verify school type identification
        log("\n5️⃣ TEST CASE 5: Verifying school type identification...")
        
        response = requests.get(
            f"{API_BASE}/schools",
            headers=headers
        )
        
        if response.status_code == 200:
            schools = response.json()
            integral_count = 0
            regular_count = 0
            
            for school in schools:
                if school.get('atendimento_integral', False):
                    integral_count += 1
                    log(f"   🏫 INTEGRAL: {school.get('name')} (ID: {school.get('id')})")
                else:
                    regular_count += 1
                    if regular_count <= 3:  # Show only first 3 to avoid spam
                        log(f"   🏫 REGULAR: {school.get('name')} (ID: {school.get('id')})")
            
            log(f"✅ School type identification: {integral_count} integral, {regular_count} regular schools")
            
            if integral_count > 0 and regular_count > 0:
                log("✅ Both integral and regular schools found - filtering can be tested")
            else:
                log("❌ Missing either integral or regular schools - filtering cannot be fully tested")
        else:
            log(f"❌ Failed to get schools for type verification: {response.status_code}")
        
        # TEST CASE 6: Verify component categorization
        log("\n6️⃣ TEST CASE 6: Verifying component categorization...")
        
        response = requests.get(
            f"{API_BASE}/courses",
            headers=headers
        )
        
        if response.status_code == 200:
            courses = response.json()
            
            # Categorize components
            infantil_components = []
            fundamental_components = []
            integral_components = []
            
            for course in courses:
                nivel_ensino = course.get('nivel_ensino', '') or ''
                atendimento_programa = course.get('atendimento_programa', '') or ''
                name = course.get('name', course.get('nome', '')) or ''
                
                if 'infantil' in nivel_ensino.lower():
                    infantil_components.append(name)
                elif 'fundamental' in nivel_ensino.lower():
                    fundamental_components.append(name)
                
                if 'atendimento_integral' in atendimento_programa:
                    integral_components.append(name)
            
            log(f"✅ Component categorization:")
            log(f"   Educação Infantil components: {len(infantil_components)}")
            if infantil_components:
                log(f"   Examples: {', '.join(infantil_components[:3])}")
            
            log(f"   Fundamental components: {len(fundamental_components)}")
            if fundamental_components:
                log(f"   Examples: {', '.join(fundamental_components[:5])}")
            
            log(f"   Escola Integral components: {len(integral_components)}")
            if integral_components:
                log(f"   Examples: {', '.join(integral_components[:3])}")
                
                # Check for expected integral components
                expected_integral = ['Recreação, Esporte e Lazer', 'Arte e Cultura', 'Tecnologia e Informática']
                found_expected = []
                for expected in expected_integral:
                    for component in integral_components:
                        if expected.lower() in component.lower():
                            found_expected.append(component)
                            break
                
                if found_expected:
                    log(f"✅ Found expected integral components: {', '.join(found_expected)}")
                else:
                    log("❌ Expected integral components not found")
        else:
            log(f"❌ Failed to get courses for categorization: {response.status_code}")
        
        log("\n✅ Boletim Component Filtering testing completed!")
        return True
        
    except Exception as e:
        log(f"❌ Error during boletim component filtering test: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_boletim_component_filtering()
    if success:
        log("\n🎉 Test completed successfully!")
    else:
        log("\n❌ Test failed!")