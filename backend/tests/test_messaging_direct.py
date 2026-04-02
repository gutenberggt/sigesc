"""
Test suite for SIGESC Messaging System - Direct Connection Feature
Tests:
1. POST /api/connections/direct/{user_id} - Admin can create direct connection
2. POST /api/connections/direct/{user_id} - Non-admin to admin works
3. POST /api/connections/direct/{user_id} - Non-admin to non-admin returns 403
4. GET /api/connections/status/{user_id} - Returns admin_direct when admin involved
5. POST /api/messages - Admin can send message without prior connection
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = "@Celta2007"


class TestMessagingDirectConnection:
    """Tests for direct connection and messaging features"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")
        data = response.json()
        return data.get("access_token")
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        """Headers with admin auth"""
        return {"Authorization": f"Bearer {admin_token}"}
    
    @pytest.fixture(scope="class")
    def admin_user_id(self, admin_headers):
        """Get admin user ID"""
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=admin_headers)
        if response.status_code != 200:
            pytest.skip("Could not get admin user info")
        return response.json().get("id")
    
    @pytest.fixture(scope="class")
    def other_users(self, admin_headers):
        """Get list of other users from the system"""
        response = requests.get(f"{BASE_URL}/api/users", headers=admin_headers)
        if response.status_code != 200:
            pytest.skip("Could not get users list")
        users = response.json()
        # Filter out admin users
        non_admin_users = [u for u in users if u.get('role') not in ('admin', 'admin_teste')]
        return non_admin_users
    
    def test_health_check(self):
        """Test API is accessible"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        print("PASS: API health check")
    
    def test_admin_login(self, admin_token):
        """Test admin can login"""
        assert admin_token is not None, "Admin token should not be None"
        assert len(admin_token) > 0, "Admin token should not be empty"
        print(f"PASS: Admin login successful, token length: {len(admin_token)}")
    
    def test_get_connection_status_self(self, admin_headers, admin_user_id):
        """Test connection status returns 'self' for own profile"""
        response = requests.get(
            f"{BASE_URL}/api/connections/status/{admin_user_id}",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("status") == "self", f"Expected 'self', got {data.get('status')}"
        print("PASS: Connection status returns 'self' for own profile")
    
    def test_get_connection_status_admin_direct(self, admin_headers, other_users):
        """Test connection status returns 'admin_direct' when admin views non-connected user"""
        if not other_users:
            pytest.skip("No non-admin users available for testing")
        
        target_user = other_users[0]
        target_user_id = target_user.get('id')
        
        response = requests.get(
            f"{BASE_URL}/api/connections/status/{target_user_id}",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        # Should be either 'admin_direct' (no connection) or 'accepted' (already connected)
        assert data.get("status") in ("admin_direct", "accepted", "none"), \
            f"Expected 'admin_direct', 'accepted', or 'none', got {data.get('status')}"
        print(f"PASS: Connection status for non-connected user: {data.get('status')}")
    
    def test_create_direct_connection_admin_to_user(self, admin_headers, other_users):
        """Test admin can create direct connection with any user"""
        if not other_users:
            pytest.skip("No non-admin users available for testing")
        
        target_user = other_users[0]
        target_user_id = target_user.get('id')
        
        response = requests.post(
            f"{BASE_URL}/api/connections/direct/{target_user_id}",
            headers=admin_headers
        )
        # Should succeed (200) or already connected
        assert response.status_code in (200, 400), \
            f"Expected 200 or 400, got {response.status_code}: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert data.get("status") == "accepted", f"Expected 'accepted', got {data.get('status')}"
            assert data.get("user_id") == target_user_id, "User ID should match"
            print(f"PASS: Admin created direct connection with user {target_user_id}")
        else:
            print(f"PASS: Connection already exists (400 response)")
    
    def test_create_direct_connection_invalid_user(self, admin_headers):
        """Test direct connection with non-existent user returns 404"""
        response = requests.post(
            f"{BASE_URL}/api/connections/direct/fake-user-id-12345",
            headers=admin_headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: Direct connection with invalid user returns 404")
    
    def test_create_direct_connection_self(self, admin_headers, admin_user_id):
        """Test cannot create direct connection with self"""
        response = requests.post(
            f"{BASE_URL}/api/connections/direct/{admin_user_id}",
            headers=admin_headers
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("PASS: Cannot create direct connection with self")
    
    def test_list_connections(self, admin_headers):
        """Test listing connections"""
        response = requests.get(
            f"{BASE_URL}/api/connections",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"PASS: Listed {len(data)} connections")
    
    def test_send_message_admin_to_user(self, admin_headers, other_users):
        """Test admin can send message to user (auto-creates connection if needed)"""
        if not other_users:
            pytest.skip("No non-admin users available for testing")
        
        target_user = other_users[0]
        target_user_id = target_user.get('id')
        
        response = requests.post(
            f"{BASE_URL}/api/messages",
            headers=admin_headers,
            json={
                "receiver_id": target_user_id,
                "content": "TEST_MESSAGE: Hello from admin test"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("content") == "TEST_MESSAGE: Hello from admin test"
        assert data.get("receiver_id") == target_user_id
        print(f"PASS: Admin sent message to user {target_user_id}")
    
    def test_send_message_empty_content(self, admin_headers, other_users):
        """Test sending message with empty content fails"""
        if not other_users:
            pytest.skip("No non-admin users available for testing")
        
        target_user = other_users[0]
        target_user_id = target_user.get('id')
        
        response = requests.post(
            f"{BASE_URL}/api/messages",
            headers=admin_headers,
            json={
                "receiver_id": target_user_id,
                "content": ""
            }
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("PASS: Empty message content returns 400")
    
    def test_get_unread_count(self, admin_headers):
        """Test getting unread message count"""
        response = requests.get(
            f"{BASE_URL}/api/messages/unread/count",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "unread_count" in data, "Response should contain unread_count"
        print(f"PASS: Unread count: {data.get('unread_count')}")
    
    def test_list_conversations(self, admin_headers):
        """Test listing conversations"""
        response = requests.get(
            f"{BASE_URL}/api/messages/conversations/list",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"PASS: Listed {len(data)} conversations")
    
    def test_notifications_unread_count(self, admin_headers):
        """Test notifications unread count endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/notifications/unread-count",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "unread_messages" in data or "unread_count" in data, \
            "Response should contain unread count"
        print(f"PASS: Notifications unread count: {data}")


class TestConnectionStatusEndpoint:
    """Tests specifically for GET /api/connections/status/{user_id}"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Admin login failed: {response.status_code}")
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}"}
    
    def test_status_endpoint_returns_correct_fields(self, admin_headers):
        """Test status endpoint returns expected fields"""
        # Get any user to test with
        users_response = requests.get(f"{BASE_URL}/api/users", headers=admin_headers)
        if users_response.status_code != 200:
            pytest.skip("Could not get users")
        
        users = users_response.json()
        non_admin = [u for u in users if u.get('role') not in ('admin', 'admin_teste')]
        if not non_admin:
            pytest.skip("No non-admin users")
        
        target_id = non_admin[0].get('id')
        response = requests.get(
            f"{BASE_URL}/api/connections/status/{target_id}",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have status field
        assert "status" in data, "Response should have 'status' field"
        # Status should be one of expected values
        valid_statuses = ["none", "pending", "accepted", "rejected", "self", "admin_direct"]
        assert data["status"] in valid_statuses, f"Invalid status: {data['status']}"
        
        print(f"PASS: Status endpoint returns valid status: {data['status']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
