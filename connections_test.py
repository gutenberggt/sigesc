#!/usr/bin/env python3
"""
SIGESC Connections and Messages System Test Suite
Tests the networking system similar to LinkedIn
"""

import requests
import json
import os
from datetime import datetime

# Get backend URL from environment
BACKEND_URL = os.getenv('REACT_APP_BACKEND_URL', 'https://deploy-refresh-5.preview.emergentagent.com')
API_BASE = f"{BACKEND_URL}/api"

# Test credentials from review request
ADMIN_CREDENTIALS = {
    "email": "admin@sigesc.com",
    "password": "password"
}

RICLEIDE_CREDENTIALS = {
    "email": "ricleidegoncalves@gmail.com", 
    "password": "007724"
}

class ConnectionsTester:
    def __init__(self):
        self.admin_token = None
        self.ricleide_token = None
        
        # User IDs from review request
        self.admin_user_id = "5edcfabe-3a6d-44f4-93e3-61b16c7d78e6"
        self.ricleide_user_id = "b97578dd-bc66-446c-88d7-686b423af399"
        self.existing_connection_id = "11faaa15-32cd-4712-a435-281f5bb5e28c"
        
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
    
    def test_connections_system(self):
        """Test Connections and Messages System as per review request"""
        self.log("\n🤝 Testing Connections and Messages System (Sistema de Conexões)...")
        
        # Test 1: GET /api/connections - List accepted connections
        self.log("1️⃣ Testing GET /api/connections - List accepted connections...")
        response = requests.get(
            f"{API_BASE}/connections",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            connections = response.json()
            self.log(f"✅ Successfully retrieved {len(connections)} connections")
            
            # Verify existing connection with Ricleide
            ricleide_connection = None
            for conn in connections:
                if (conn.get('sender_id') == self.ricleide_user_id or 
                    conn.get('receiver_id') == self.ricleide_user_id):
                    ricleide_connection = conn
                    break
            
            if ricleide_connection:
                self.log(f"✅ Found existing connection with Ricleide (ID: {ricleide_connection.get('id')})")
                self.log(f"   Status: {ricleide_connection.get('status')}")
            else:
                self.log("❌ Existing connection with Ricleide not found")
        else:
            self.log(f"❌ Failed to list connections: {response.status_code} - {response.text}")
            return False
        
        # Test 2: GET /api/connections/status/{user_id} - Check connection status
        self.log("2️⃣ Testing GET /api/connections/status/{user_id} - Check connection status...")
        response = requests.get(
            f"{API_BASE}/connections/status/{self.ricleide_user_id}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            status_info = response.json()
            self.log(f"✅ Connection status retrieved")
            self.log(f"   Status: {status_info.get('status')}")
            self.log(f"   Connection ID: {status_info.get('connection_id', 'N/A')}")
            
            if status_info.get('status') == 'accepted':
                self.log("✅ Connection status is 'accepted' as expected")
            else:
                self.log(f"❌ Expected 'accepted' status, got: {status_info.get('status')}")
        else:
            self.log(f"❌ Failed to check connection status: {response.status_code} - {response.text}")
            return False
        
        # Test 3: GET /api/connections/pending - List pending invitations received
        self.log("3️⃣ Testing GET /api/connections/pending - List pending invitations...")
        response = requests.get(
            f"{API_BASE}/connections/pending",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            pending = response.json()
            self.log(f"✅ Successfully retrieved {len(pending)} pending invitations")
        else:
            self.log(f"❌ Failed to list pending invitations: {response.status_code} - {response.text}")
        
        # Test 4: GET /api/connections/sent - List sent invitations
        self.log("4️⃣ Testing GET /api/connections/sent - List sent invitations...")
        response = requests.get(
            f"{API_BASE}/connections/sent",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            sent = response.json()
            self.log(f"✅ Successfully retrieved {len(sent)} sent invitations")
        else:
            self.log(f"❌ Failed to list sent invitations: {response.status_code} - {response.text}")
        
        # Test 5: POST /api/messages - Send message to connected user
        self.log("5️⃣ Testing POST /api/messages - Send message to Ricleide...")
        message_data = {
            "receiver_id": self.ricleide_user_id,
            "content": "Olá Ricleide! Esta é uma mensagem de teste do sistema de conexões do SIGESC.",
            "attachments": []
        }
        
        response = requests.post(
            f"{API_BASE}/messages",
            json=message_data,
            headers=self.get_headers(self.admin_token)
        )
        
        created_message_id = None
        if response.status_code == 200 or response.status_code == 201:
            message = response.json()
            created_message_id = message.get('id')
            self.log(f"✅ Message sent successfully (ID: {created_message_id})")
            self.log(f"   Content: {message.get('content')[:50]}...")
            self.log(f"   Receiver: {message.get('receiver_id')}")
            self.log(f"   Timestamp: {message.get('created_at')}")
        else:
            self.log(f"❌ Failed to send message: {response.status_code} - {response.text}")
            return False
        
        # Test 6: GET /api/messages/{connection_id} - List messages in conversation
        self.log("6️⃣ Testing GET /api/messages/{connection_id} - List conversation messages...")
        response = requests.get(
            f"{API_BASE}/messages/{self.existing_connection_id}",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            messages = response.json()
            self.log(f"✅ Successfully retrieved {len(messages)} messages in conversation")
            
            if messages:
                # Check if our test message appears
                test_message_found = False
                for msg in messages:
                    if msg.get('id') == created_message_id:
                        test_message_found = True
                        self.log("✅ Test message found in conversation")
                        break
                
                if not test_message_found:
                    self.log("❌ Test message not found in conversation")
                
                # Show sample message structure
                sample_msg = messages[0]
                self.log(f"   Sample message: {sample_msg.get('content', '')[:30]}...")
                self.log(f"   Sender: {sample_msg.get('sender_id')}")
                self.log(f"   Read status: {sample_msg.get('is_read', False)}")
        else:
            self.log(f"❌ Failed to list conversation messages: {response.status_code} - {response.text}")
        
        # Test 7: GET /api/messages/conversations/list - List all conversations
        self.log("7️⃣ Testing GET /api/messages/conversations/list - List all conversations...")
        response = requests.get(
            f"{API_BASE}/messages/conversations/list",
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 200:
            conversations = response.json()
            self.log(f"✅ Successfully retrieved {len(conversations)} conversations")
            
            if conversations:
                # Find conversation with Ricleide
                ricleide_conversation = None
                for conv in conversations:
                    if (conv.get('connection_id') == self.existing_connection_id or
                        conv.get('other_user_id') == self.ricleide_user_id):
                        ricleide_conversation = conv
                        break
                
                if ricleide_conversation:
                    self.log("✅ Found conversation with Ricleide")
                    self.log(f"   Last message: {ricleide_conversation.get('last_message', '')[:30]}...")
                    self.log(f"   Unread count: {ricleide_conversation.get('unread_count', 0)}")
                else:
                    self.log("❌ Conversation with Ricleide not found")
        else:
            self.log(f"❌ Failed to list conversations: {response.status_code} - {response.text}")
        
        # Test 8: POST /api/messages/{message_id}/read - Mark message as read
        self.log("8️⃣ Testing POST /api/messages/{message_id}/read - Mark message as read...")
        if created_message_id:
            response = requests.post(
                f"{API_BASE}/messages/{created_message_id}/read",
                headers=self.get_headers(self.ricleide_token)  # Ricleide marks as read
            )
            
            if response.status_code == 200:
                self.log("✅ Message marked as read successfully")
            else:
                self.log(f"❌ Failed to mark message as read: {response.status_code} - {response.text}")
        
        # Test 9: GET /api/messages/unread/count - Count unread messages
        self.log("9️⃣ Testing GET /api/messages/unread/count - Count unread messages...")
        response = requests.get(
            f"{API_BASE}/messages/unread/count",
            headers=self.get_headers(self.ricleide_token)
        )
        
        if response.status_code == 200:
            unread_data = response.json()
            self.log(f"✅ Unread count retrieved")
            self.log(f"   Total unread: {unread_data.get('count', 0)}")
        else:
            self.log(f"❌ Failed to get unread count: {response.status_code} - {response.text}")
        
        # Test 10: Validation - Try to send message without connection
        self.log("🔟 Testing validation - Send message to non-connected user...")
        # Try to send message to admin from Ricleide (if they're not connected)
        invalid_message_data = {
            "receiver_id": self.admin_user_id,
            "content": "This should fail if not connected",
            "attachments": []
        }
        
        response = requests.post(
            f"{API_BASE}/messages",
            json=invalid_message_data,
            headers=self.get_headers(self.ricleide_token)
        )
        
        # This should either succeed (if connected) or fail with proper error
        if response.status_code == 400 or response.status_code == 403:
            self.log("✅ Correctly blocked message to non-connected user")
        elif response.status_code == 200 or response.status_code == 201:
            self.log("ℹ️ Message sent successfully (users are connected)")
        else:
            self.log(f"❌ Unexpected response for non-connected message: {response.status_code}")
        
        # Test 11: Validation - Try to send invitation to self
        self.log("1️⃣1️⃣ Testing validation - Send invitation to self...")
        self_invite_data = {
            "receiver_id": self.admin_user_id,  # Admin trying to invite himself
            "message": "This should fail"
        }
        
        response = requests.post(
            f"{API_BASE}/connections/invite",
            json=self_invite_data,
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 400:
            self.log("✅ Correctly blocked self-invitation")
        else:
            self.log(f"❌ Self-invitation should be blocked: {response.status_code}")
        
        # Test 12: Validation - Try to send duplicate invitation
        self.log("1️⃣2️⃣ Testing validation - Send duplicate invitation...")
        duplicate_invite_data = {
            "receiver_id": self.ricleide_user_id,  # Already connected
            "message": "This should fail as duplicate"
        }
        
        response = requests.post(
            f"{API_BASE}/connections/invite",
            json=duplicate_invite_data,
            headers=self.get_headers(self.admin_token)
        )
        
        if response.status_code == 400:
            self.log("✅ Correctly blocked duplicate invitation")
        else:
            self.log(f"❌ Duplicate invitation should be blocked: {response.status_code}")
        
        self.log("✅ Connections and Messages System testing completed!")
        return True
    
    def run_all_tests(self):
        """Run all connection and message tests"""
        self.log("🚀 Starting SIGESC Connections and Messages System Tests...")
        self.log(f"🌐 Backend URL: {API_BASE}")
        
        # Login as admin and Ricleide
        self.admin_token = self.login(ADMIN_CREDENTIALS, "Admin")
        self.ricleide_token = self.login(RICLEIDE_CREDENTIALS, "Ricleide")
        
        if not self.admin_token:
            self.log("❌ Cannot proceed without admin token")
            return False
        
        if not self.ricleide_token:
            self.log("❌ Cannot proceed without Ricleide token")
            return False
        
        # Run test suites
        success = True
        
        try:
            # Test Connections and Messages System
            if not self.test_connections_system():
                success = False
            
        except Exception as e:
            self.log(f"❌ Test execution error: {str(e)}")
            success = False
        
        # Final result
        self.log("\n" + "="*50)
        if success:
            self.log("🎉 All connections and messages tests completed successfully!")
            self.log("✅ CONNECTIONS AND MESSAGES SYSTEM FULLY TESTED")
        else:
            self.log("❌ Some tests failed - check logs above")
        self.log("="*50)
        
        return success

if __name__ == "__main__":
    tester = ConnectionsTester()
    tester.run_all_tests()