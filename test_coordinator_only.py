#!/usr/bin/env python3
"""
Test only the Coordinator Permissions system
"""

import requests
import json
import os
from datetime import datetime

# Get backend URL from environment
BACKEND_URL = os.getenv('REACT_APP_BACKEND_URL', 'https://sigesc-school-2.preview.emergentagent.com')
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

def log(message):
    """Log test messages with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def get_headers(token):
    """Get authorization headers"""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

def login(credentials, role_name):
    """Login and get access token"""
    log(f"🔐 Logging in as {role_name}...")
    
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
            log(f"✅ Login successful for {user.get('full_name', role_name)}")
            return token
        else:
            log(f"❌ Login failed: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        log(f"❌ Login error: {str(e)}")
        return None

def test_coordinator_permissions():
    """Test Coordinator Permissions system as per review request"""
    log("\n🔐 Testing Coordinator Permissions System...")
    
    # Login as admin first
    admin_token = login(ADMIN_CREDENTIALS, "Admin")
    if not admin_token:
        log("❌ Cannot proceed without admin login")
        return False
    
    # 1. Login and Role Verification
    log("1️⃣ Testing Coordinator Login and Role Verification...")
    response = requests.post(
        f"{API_BASE}/auth/login",
        json=COORDINATOR_CREDENTIALS,
        headers={"Content-Type": "application/json"}
    )
    
    if response.status_code == 200:
        data = response.json()
        coordinator_token = data.get('access_token')
        user = data.get('user', {})
        user_role = user.get('role')
        
        log(f"✅ Coordinator login successful")
        log(f"   User: {user.get('full_name', 'N/A')}")
        log(f"   Email: {user.get('email')}")
        log(f"   Role: {user_role}")
        
        # Verify role is "coordenador" (not "professor")
        if user_role == "coordenador":
            log("✅ User role correctly returned as 'coordenador'")
        else:
            log(f"❌ Expected role 'coordenador', got: {user_role}")
            return False
    else:
        log(f"❌ Coordinator login failed: {response.status_code} - {response.text}")
        return False
    
    # 2. Permissions Endpoint
    log("2️⃣ Testing GET /api/auth/permissions with coordinator token...")
    response = requests.get(
        f"{API_BASE}/auth/permissions",
        headers=get_headers(coordinator_token)
    )
    
    if response.status_code == 200:
        permissions = response.json()
        log(f"✅ Permissions endpoint successful")
        
        # Expected permissions for coordinator
        expected_permissions = {
            'can_edit_students': False,
            'can_edit_classes': False,
            'can_edit_grades': True,
            'can_edit_attendance': True,
            'can_edit_learning_objects': True,
            'is_read_only_except_diary': True
        }
        
        log("   Checking coordinator permissions:")
        all_correct = True
        for perm, expected_value in expected_permissions.items():
            actual_value = permissions.get(perm)
            if actual_value == expected_value:
                log(f"   ✅ {perm}: {actual_value} (correct)")
            else:
                log(f"   ❌ {perm}: {actual_value} (expected: {expected_value})")
                all_correct = False
        
        if all_correct:
            log("✅ All coordinator permissions are correct")
        else:
            log("❌ Some coordinator permissions are incorrect")
            return False
    else:
        log(f"❌ Failed to get permissions: {response.status_code} - {response.text}")
        return False
    
    # 3. Student Update (Should be BLOCKED)
    log("3️⃣ Testing Student Update (Should be BLOCKED for coordinator)...")
    
    # First get a valid student ID
    response = requests.get(
        f"{API_BASE}/students",
        headers=get_headers(coordinator_token)
    )
    
    if response.status_code == 200:
        students = response.json()
        if students:
            test_student_id = students[0]['id']
            student_name = students[0].get('full_name', 'N/A')
            log(f"   Using student: {student_name} (ID: {test_student_id})")
            
            # Try to update student (should be blocked)
            update_data = {
                "observations": "Teste de atualização pelo coordenador"
            }
            
            response = requests.put(
                f"{API_BASE}/students/{test_student_id}",
                json=update_data,
                headers=get_headers(coordinator_token)
            )
            
            if response.status_code == 403:
                response_text = response.text
                log("✅ Student update correctly BLOCKED (403)")
                if "Coordenadores podem apenas visualizar" in response_text:
                    log("✅ Correct error message about coordinator read-only access")
                else:
                    log(f"   Response: {response_text}")
            elif response.status_code == 401:
                log("✅ Student update correctly BLOCKED (401)")
            else:
                log(f"❌ Student update should be blocked, got: {response.status_code}")
                return False
        else:
            log("❌ No students found for testing")
            return False
    else:
        log(f"❌ Failed to get students: {response.status_code} - {response.text}")
        return False
    
    # 4. Grades Access (Should be ALLOWED)
    log("4️⃣ Testing Grades Access (Should be ALLOWED for coordinator)...")
    
    # Test GET /api/grades
    response = requests.get(
        f"{API_BASE}/grades",
        headers=get_headers(coordinator_token)
    )
    
    if response.status_code == 200:
        grades = response.json()
        log(f"✅ GET /api/grades successful - retrieved {len(grades)} grades")
    else:
        log(f"❌ GET /api/grades failed: {response.status_code} - {response.text}")
        return False
    
    # 5. Learning Objects Access (Should be ALLOWED)
    log("5️⃣ Testing Learning Objects Access (Should be ALLOWED for coordinator)...")
    
    response = requests.get(
        f"{API_BASE}/learning-objects",
        headers=get_headers(coordinator_token)
    )
    
    if response.status_code == 200:
        learning_objects = response.json()
        log(f"✅ GET /api/learning-objects successful - retrieved {len(learning_objects)} objects")
    else:
        log(f"❌ GET /api/learning-objects failed: {response.status_code} - {response.text}")
        return False
    
    # 6. Compare with Admin (Admin CAN update students)
    log("6️⃣ Testing Admin can update students (comparison)...")
    
    if students:  # Use the same student from earlier test
        test_student_id = students[0]['id']
        
        # Admin should be able to update students
        update_data = {
            "observations": "Teste de atualização pelo admin"
        }
        
        response = requests.put(
            f"{API_BASE}/students/{test_student_id}",
            json=update_data,
            headers=get_headers(admin_token)
        )
        
        if response.status_code == 200:
            updated_student = response.json()
            log("✅ Admin CAN update students (as expected)")
            log(f"   Updated observations: {updated_student.get('observations', 'N/A')}")
        else:
            log(f"❌ Admin should be able to update students: {response.status_code}")
            return False
    
    log("✅ Coordinator Permissions System testing completed successfully!")
    log("\n📋 SUMMARY:")
    log("   ✅ Coordinator login with correct role verification")
    log("   ✅ Permissions endpoint returns correct coordinator permissions")
    log("   ✅ Student updates BLOCKED (read-only)")
    log("   ✅ Grades access ALLOWED (diary area)")
    log("   ✅ Learning Objects access ALLOWED (diary area)")
    log("   ✅ Admin comparison shows different permissions")
    
    return True

if __name__ == "__main__":
    log("🚀 Starting Coordinator Permissions Test")
    log(f"🌐 Backend URL: {BACKEND_URL}")
    
    success = test_coordinator_permissions()
    
    if success:
        log("\n🎉 ALL COORDINATOR PERMISSIONS TESTS PASSED!")
    else:
        log("\n❌ SOME COORDINATOR PERMISSIONS TESTS FAILED!")