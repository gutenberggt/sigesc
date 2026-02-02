#!/usr/bin/env python3
"""
SIGESC WebSocket Messaging System Test Suite
Tests WebSocket connections, message sending, and real-time notifications
"""

import requests
import json
import asyncio
import websockets
import ssl
import os
from datetime import datetime
import time

# Get backend URL from environment
BACKEND_URL = os.getenv('REACT_APP_BACKEND_URL', 'https://studentsys-update.preview.emergentagent.com')
API_BASE = f"{BACKEND_URL}/api"
WS_BASE = BACKEND_URL.replace('https://', 'wss://').replace('http://', 'ws://')

# Test credentials from review request
ADMIN_CREDENTIALS = {
    "email": "admin@sigesc.com",
    "password": "password"
}

PROFESSOR_CREDENTIALS = {
    "email": "ricleidegoncalves@gmail.com", 
    "password": "007724"
}

class WebSocketTester:
    def __init__(self):
        self.admin_token = None
        self.professor_token = None
        self.admin_user_id = None
        self.professor_user_id = None
        self.connection_id = None
        self.test_message_id = None
        
    def log(self, message):
        """Log test messages with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
        
    def login(self, credentials, role_name):
        """Login and get access token and user info"""
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
                user_id = user.get('id')
                self.log(f"✅ Login successful for {user.get('full_name', role_name)} (ID: {user_id})")
                return token, user_id
            else:
                self.log(f"❌ Login failed: {response.status_code} - {response.text}")
                return None, None
                
        except Exception as e:
            self.log(f"❌ Login error: {str(e)}")
            return None, None
    
    def get_headers(self, token):
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    
    async def test_websocket_connection(self, token, user_name):
        """Test WebSocket connection with ping/pong"""
        self.log(f"🔌 Testing WebSocket connection for {user_name}...")
        
        ws_url = f"{WS_BASE}/api/ws/{token}"
        self.log(f"   Connecting to: {ws_url}")
        
        try:
            # Create SSL context that doesn't verify certificates (for testing)
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            async with websockets.connect(ws_url, ssl=ssl_context) as websocket:
                self.log(f"✅ WebSocket connected successfully for {user_name}")
                
                # Test ping/pong
                self.log("📡 Sending ping...")
                await websocket.send("ping")
                
                # Wait for pong response
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    if response == "pong":
                        self.log("✅ Received pong response - WebSocket communication working")
                        return True
                    else:
                        self.log(f"❌ Expected 'pong', received: {response}")
                        return False
                except asyncio.TimeoutError:
                    self.log("❌ Timeout waiting for pong response")
                    return False
                    
        except Exception as e:
            self.log(f"❌ WebSocket connection failed: {str(e)}")
            return False
    
    def get_connections(self, token):
        """Get user connections to find receiver"""
        self.log("👥 Getting user connections...")
        
        try:
            response = requests.get(
                f"{API_BASE}/connections",
                headers=self.get_headers(token)
            )
            
            if response.status_code == 200:
                connections = response.json()
                self.log(f"✅ Found {len(connections)} connections")
                
                for conn in connections:
                    self.log(f"   Connection ID: {conn.get('id')}")
                    self.log(f"   User 1: {conn.get('user1_name')} (ID: {conn.get('user1_id')})")
                    self.log(f"   User 2: {conn.get('user2_name')} (ID: {conn.get('user2_id')})")
                    self.log(f"   Status: {conn.get('status')}")
                
                return connections
            else:
                self.log(f"❌ Failed to get connections: {response.status_code} - {response.text}")
                return []
                
        except Exception as e:
            self.log(f"❌ Error getting connections: {str(e)}")
            return []
    
    def find_ricleide_user_id(self, connections, admin_user_id):
        """Find Ricleide's user_id from connections"""
        self.log("🔍 Finding Ricleide's user_id from connections...")
        
        for conn in connections:
            # The connections API returns the connected user info directly
            user_id = conn.get('user_id')
            full_name = conn.get('full_name')
            connection_id = conn.get('id')
            
            # Check if this is Ricleide (not the admin)
            if user_id != admin_user_id and 'RICLEIDE' in full_name.upper():
                self.log(f"✅ Found Ricleide: {full_name} (ID: {user_id})")
                return user_id, connection_id
        
        self.log("❌ Ricleide not found in connections")
        return None, None
    
    def send_message(self, token, receiver_id, content):
        """Send message via POST /api/messages"""
        self.log(f"📤 Sending message to user {receiver_id}...")
        
        message_data = {
            "receiver_id": receiver_id,
            "content": content,
            "message_type": "text"
        }
        
        try:
            response = requests.post(
                f"{API_BASE}/messages",
                json=message_data,
                headers=self.get_headers(token)
            )
            
            if response.status_code == 200 or response.status_code == 201:
                message = response.json()
                message_id = message.get('id')
                self.log(f"✅ Message sent successfully (ID: {message_id})")
                self.log(f"   Content: {message.get('content')}")
                self.log(f"   Timestamp: {message.get('created_at')}")
                return message_id
            else:
                self.log(f"❌ Failed to send message: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            self.log(f"❌ Error sending message: {str(e)}")
            return None
    
    async def listen_for_websocket_notifications(self, token, user_name, duration=10):
        """Listen for WebSocket notifications for a specified duration"""
        self.log(f"👂 Listening for WebSocket notifications for {user_name} ({duration}s)...")
        
        ws_url = f"{WS_BASE}/api/ws/{token}"
        notifications_received = []
        
        try:
            # Create SSL context that doesn't verify certificates (for testing)
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            async with websockets.connect(ws_url, ssl=ssl_context) as websocket:
                self.log(f"✅ WebSocket listener connected for {user_name}")
                
                # Listen for messages for the specified duration
                end_time = time.time() + duration
                
                while time.time() < end_time:
                    try:
                        # Wait for message with timeout
                        remaining_time = end_time - time.time()
                        if remaining_time <= 0:
                            break
                            
                        message = await asyncio.wait_for(websocket.recv(), timeout=min(remaining_time, 2.0))
                        
                        # Skip ping/pong messages
                        if message in ["ping", "pong"]:
                            continue
                        
                        try:
                            # Try to parse as JSON
                            notification = json.loads(message)
                            notifications_received.append(notification)
                            
                            self.log(f"📨 Received notification:")
                            self.log(f"   Type: {notification.get('type')}")
                            self.log(f"   Message: {notification.get('message', {}).get('content', 'N/A')}")
                            self.log(f"   From: {notification.get('message', {}).get('sender_name', 'N/A')}")
                            self.log(f"   Timestamp: {notification.get('message', {}).get('created_at', 'N/A')}")
                            
                        except json.JSONDecodeError:
                            self.log(f"📨 Received non-JSON message: {message}")
                            notifications_received.append({"raw_message": message})
                            
                    except asyncio.TimeoutError:
                        # Continue listening
                        continue
                
                self.log(f"✅ Finished listening. Received {len(notifications_received)} notifications")
                return notifications_received
                
        except Exception as e:
            self.log(f"❌ Error listening for notifications: {str(e)}")
            return notifications_received
    
    async def test_real_time_messaging(self):
        """Test complete real-time messaging flow"""
        self.log("🚀 Testing complete real-time messaging flow...")
        
        # Step 1: Start listening for notifications as Ricleide
        self.log("1️⃣ Starting WebSocket listener for Ricleide...")
        
        # Create a task to listen for notifications
        listen_task = asyncio.create_task(
            self.listen_for_websocket_notifications(self.professor_token, "Ricleide", 15)
        )
        
        # Wait a moment for the listener to connect
        await asyncio.sleep(2)
        
        # Step 2: Send message from Admin to Ricleide
        self.log("2️⃣ Sending message from Admin to Ricleide...")
        test_content = f"Test message from Admin at {datetime.now().strftime('%H:%M:%S')}"
        message_id = self.send_message(self.admin_token, self.professor_user_id, test_content)
        
        if not message_id:
            self.log("❌ Failed to send test message")
            listen_task.cancel()
            return False
        
        self.test_message_id = message_id
        
        # Step 3: Wait for notifications
        self.log("3️⃣ Waiting for WebSocket notification...")
        await asyncio.sleep(3)
        
        # Step 4: Get the notifications received
        notifications = await listen_task
        
        # Step 5: Verify notification was received
        self.log("4️⃣ Verifying WebSocket notification...")
        
        new_message_notifications = [
            n for n in notifications 
            if n.get('type') == 'new_message'
        ]
        
        if new_message_notifications:
            self.log(f"✅ Received {len(new_message_notifications)} 'new_message' notifications")
            
            # Check if our test message was in the notifications
            for notification in new_message_notifications:
                message = notification.get('message', {})
                if message.get('id') == message_id:
                    self.log("✅ Test message found in WebSocket notification!")
                    self.log(f"   Message ID: {message.get('id')}")
                    self.log(f"   Content: {message.get('content')}")
                    self.log(f"   Sender: {message.get('sender_name')}")
                    return True
            
            self.log("❌ Test message not found in notifications")
            return False
        else:
            self.log("❌ No 'new_message' notifications received")
            return False
    
    async def run_all_tests(self):
        """Run all WebSocket messaging tests"""
        self.log("🎯 Starting SIGESC WebSocket Messaging System Tests")
        self.log("=" * 60)
        
        # Step 1: Login as Admin
        self.log("\n📋 STEP 1: Login as Admin")
        self.admin_token, self.admin_user_id = self.login(ADMIN_CREDENTIALS, "Admin")
        if not self.admin_token:
            self.log("❌ Admin login failed - cannot continue")
            return False
        
        # Step 2: Login as Professor (Ricleide)
        self.log("\n📋 STEP 2: Login as Professor (Ricleide)")
        self.professor_token, self.professor_user_id = self.login(PROFESSOR_CREDENTIALS, "Ricleide")
        if not self.professor_token:
            self.log("❌ Professor login failed - cannot continue")
            return False
        
        # Step 3: Test WebSocket Connection for Admin
        self.log("\n📋 STEP 3: Test WebSocket Connection for Admin")
        admin_ws_success = await self.test_websocket_connection(self.admin_token, "Admin")
        if not admin_ws_success:
            self.log("❌ Admin WebSocket connection failed")
            return False
        
        # Step 4: Test WebSocket Connection for Ricleide
        self.log("\n📋 STEP 4: Test WebSocket Connection for Ricleide")
        professor_ws_success = await self.test_websocket_connection(self.professor_token, "Ricleide")
        if not professor_ws_success:
            self.log("❌ Ricleide WebSocket connection failed")
            return False
        
        # Step 5: Get Connections
        self.log("\n📋 STEP 5: Get Connections")
        connections = self.get_connections(self.admin_token)
        if not connections:
            self.log("❌ No connections found")
            return False
        
        # Step 6: Find Ricleide's user_id
        self.log("\n📋 STEP 6: Find Ricleide's user_id")
        ricleide_id, connection_id = self.find_ricleide_user_id(connections, self.admin_user_id)
        if not ricleide_id:
            self.log("❌ Could not find Ricleide in connections")
            return False
        
        self.connection_id = connection_id
        
        # Verify we have the correct Ricleide user_id
        if ricleide_id != self.professor_user_id:
            self.log(f"⚠️ Warning: Connection shows Ricleide ID as {ricleide_id}, but login shows {self.professor_user_id}")
            # Use the ID from connections as it's the established relationship
            self.professor_user_id = ricleide_id
        
        # Step 7: Test Message Sending
        self.log("\n📋 STEP 7: Test Message Sending")
        test_content = f"Test message from Admin to Ricleide at {datetime.now().strftime('%H:%M:%S')}"
        message_id = self.send_message(self.admin_token, self.professor_user_id, test_content)
        if not message_id:
            self.log("❌ Message sending failed")
            return False
        
        # Step 8: Test Real-time Messaging
        self.log("\n📋 STEP 8: Test Real-time WebSocket Messaging")
        realtime_success = await self.test_real_time_messaging()
        if not realtime_success:
            self.log("❌ Real-time messaging test failed")
            return False
        
        # Step 9: Verify Message was Sent Successfully
        self.log("\n📋 STEP 9: Verify Message in Conversation")
        if self.connection_id:
            try:
                response = requests.get(
                    f"{API_BASE}/messages/{self.connection_id}",
                    headers=self.get_headers(self.admin_token)
                )
                
                if response.status_code == 200:
                    messages = response.json()
                    self.log(f"✅ Retrieved {len(messages)} messages in conversation")
                    
                    # Find our test message
                    test_message_found = False
                    for msg in messages:
                        if msg.get('id') == self.test_message_id:
                            test_message_found = True
                            self.log(f"✅ Test message found in conversation:")
                            self.log(f"   ID: {msg.get('id')}")
                            self.log(f"   Content: {msg.get('content')}")
                            self.log(f"   Sender: {msg.get('sender_name')}")
                            break
                    
                    if not test_message_found:
                        self.log("❌ Test message not found in conversation")
                        return False
                else:
                    self.log(f"❌ Failed to get conversation messages: {response.status_code}")
                    return False
                    
            except Exception as e:
                self.log(f"❌ Error verifying message: {str(e)}")
                return False
        
        self.log("\n🎉 ALL WEBSOCKET MESSAGING TESTS PASSED!")
        self.log("=" * 60)
        return True

async def main():
    """Main test function"""
    tester = WebSocketTester()
    success = await tester.run_all_tests()
    
    if success:
        print("\n✅ SIGESC WebSocket Messaging System - ALL TESTS PASSED")
        exit(0)
    else:
        print("\n❌ SIGESC WebSocket Messaging System - SOME TESTS FAILED")
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())