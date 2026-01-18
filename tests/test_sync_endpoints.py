"""
Test suite for SIGESC Sync Endpoints (Fase 4 - Offline Synchronization)
Tests the following endpoints:
- GET /api/sync/status - Returns sync status and collection counts
- POST /api/sync/pull - Downloads data from server to local cache
- POST /api/sync/push - Sends pending operations from client to server
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "gutenberg@sigesc.com"
TEST_PASSWORD = "@Celta2007"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for tests"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Authentication failed - skipping sync tests")


@pytest.fixture
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture
def authenticated_client(api_client, auth_token):
    """Session with auth header"""
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_client


class TestSyncStatusEndpoint:
    """Tests for GET /api/sync/status"""
    
    def test_sync_status_requires_authentication(self, api_client):
        """Test that /api/sync/status returns 401 without token"""
        response = api_client.get(f"{BASE_URL}/api/sync/status")
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
    
    def test_sync_status_returns_collection_counts(self, authenticated_client):
        """Test that /api/sync/status returns collection counts"""
        response = authenticated_client.get(f"{BASE_URL}/api/sync/status")
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify response structure
        assert "serverTime" in data
        assert "collections" in data
        assert "user" in data
        
        # Verify collections structure
        collections = data["collections"]
        assert "grades" in collections
        assert "attendance" in collections
        assert "students" in collections
        assert "classes" in collections
        assert "courses" in collections
        
        # Verify counts are integers
        for key, value in collections.items():
            assert isinstance(value, int)
            assert value >= 0
        
        # Verify user data
        user = data["user"]
        assert "id" in user
        assert "role" in user


class TestSyncPullEndpoint:
    """Tests for POST /api/sync/pull"""
    
    def test_sync_pull_requires_authentication(self, api_client):
        """Test that /api/sync/pull returns 401 without token"""
        response = api_client.post(
            f"{BASE_URL}/api/sync/pull",
            json={"collections": ["classes"]}
        )
        assert response.status_code == 401
    
    def test_sync_pull_returns_data_for_collections(self, authenticated_client):
        """Test that /api/sync/pull returns data for requested collections"""
        response = authenticated_client.post(
            f"{BASE_URL}/api/sync/pull",
            json={"collections": ["classes", "schools", "courses"]}
        )
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify response structure
        assert "data" in data
        assert "syncedAt" in data
        assert "counts" in data
        
        # Verify requested collections are in response
        assert "classes" in data["data"]
        assert "schools" in data["data"]
        assert "courses" in data["data"]
        
        # Verify counts match data length
        for collection, records in data["data"].items():
            assert isinstance(records, list)
            assert data["counts"][collection] == len(records)
    
    def test_sync_pull_with_class_filter(self, authenticated_client):
        """Test that /api/sync/pull filters by classId"""
        # First get a valid class ID
        status_response = authenticated_client.get(f"{BASE_URL}/api/sync/status")
        assert status_response.status_code == 200
        
        # Pull classes to get a valid class_id
        pull_response = authenticated_client.post(
            f"{BASE_URL}/api/sync/pull",
            json={"collections": ["classes"]}
        )
        assert pull_response.status_code == 200
        
        classes = pull_response.json()["data"]["classes"]
        if classes:
            class_id = classes[0]["id"]
            
            # Now test pull with classId filter
            filtered_response = authenticated_client.post(
                f"{BASE_URL}/api/sync/pull",
                json={
                    "collections": ["grades", "attendance"],
                    "classId": class_id
                }
            )
            assert filtered_response.status_code == 200
            
            data = filtered_response.json()
            assert "grades" in data["data"]
            assert "attendance" in data["data"]
    
    def test_sync_pull_with_academic_year_filter(self, authenticated_client):
        """Test that /api/sync/pull filters by academicYear"""
        response = authenticated_client.post(
            f"{BASE_URL}/api/sync/pull",
            json={
                "collections": ["classes"],
                "academicYear": "2025"
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "classes" in data["data"]
    
    def test_sync_pull_unknown_collection_returns_empty(self, authenticated_client):
        """Test that /api/sync/pull returns empty for unknown collections"""
        response = authenticated_client.post(
            f"{BASE_URL}/api/sync/pull",
            json={"collections": ["unknown_collection"]}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "unknown_collection" in data["data"]
        assert data["data"]["unknown_collection"] == []
        assert data["counts"]["unknown_collection"] == 0


class TestSyncPushEndpoint:
    """Tests for POST /api/sync/push"""
    
    def test_sync_push_requires_authentication(self, api_client):
        """Test that /api/sync/push returns 401 without token"""
        response = api_client.post(
            f"{BASE_URL}/api/sync/push",
            json={"operations": []}
        )
        assert response.status_code == 401
    
    def test_sync_push_empty_operations(self, authenticated_client):
        """Test that /api/sync/push handles empty operations"""
        response = authenticated_client.post(
            f"{BASE_URL}/api/sync/push",
            json={"operations": []}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["processed"] == 0
        assert data["succeeded"] == 0
        assert data["failed"] == 0
        assert data["results"] == []
    
    def test_sync_push_create_operation(self, authenticated_client):
        """Test that /api/sync/push creates new records"""
        temp_id = f"temp_test_{uuid.uuid4().hex[:8]}"
        
        response = authenticated_client.post(
            f"{BASE_URL}/api/sync/push",
            json={
                "operations": [
                    {
                        "collection": "grades",
                        "operation": "create",
                        "recordId": temp_id,
                        "data": {
                            "student_id": f"test-student-{uuid.uuid4().hex[:8]}",
                            "class_id": "970fec6e-1b90-44ca-9413-05fe77c369b8",
                            "course_id": "test-course",
                            "academic_year": 2025,
                            "b1": 8.5
                        },
                        "timestamp": "2025-01-18T00:00:00Z"
                    }
                ]
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["processed"] == 1
        assert data["succeeded"] == 1
        assert data["failed"] == 0
        
        # Verify result structure
        result = data["results"][0]
        assert result["recordId"] == temp_id
        assert result["success"] == True
        assert result["serverId"] is not None
        assert result["error"] is None
        
        # Cleanup: delete the created record
        server_id = result["serverId"]
        cleanup_response = authenticated_client.post(
            f"{BASE_URL}/api/sync/push",
            json={
                "operations": [
                    {
                        "collection": "grades",
                        "operation": "delete",
                        "recordId": server_id,
                        "timestamp": "2025-01-18T00:01:00Z"
                    }
                ]
            }
        )
        assert cleanup_response.status_code == 200
    
    def test_sync_push_update_operation(self, authenticated_client):
        """Test that /api/sync/push updates existing records"""
        # First create a record
        temp_id = f"temp_test_{uuid.uuid4().hex[:8]}"
        
        create_response = authenticated_client.post(
            f"{BASE_URL}/api/sync/push",
            json={
                "operations": [
                    {
                        "collection": "grades",
                        "operation": "create",
                        "recordId": temp_id,
                        "data": {
                            "student_id": f"test-student-{uuid.uuid4().hex[:8]}",
                            "class_id": "970fec6e-1b90-44ca-9413-05fe77c369b8",
                            "course_id": "test-course",
                            "academic_year": 2025,
                            "b1": 7.0
                        },
                        "timestamp": "2025-01-18T00:00:00Z"
                    }
                ]
            }
        )
        assert create_response.status_code == 200
        server_id = create_response.json()["results"][0]["serverId"]
        
        # Now update the record
        update_response = authenticated_client.post(
            f"{BASE_URL}/api/sync/push",
            json={
                "operations": [
                    {
                        "collection": "grades",
                        "operation": "update",
                        "recordId": server_id,
                        "data": {
                            "b2": 8.5,
                            "b3": 9.0
                        },
                        "timestamp": "2025-01-18T00:01:00Z"
                    }
                ]
            }
        )
        assert update_response.status_code == 200
        
        data = update_response.json()
        assert data["processed"] == 1
        assert data["succeeded"] == 1
        assert data["failed"] == 0
        
        result = data["results"][0]
        assert result["success"] == True
        assert result["serverId"] == server_id
        
        # Cleanup
        authenticated_client.post(
            f"{BASE_URL}/api/sync/push",
            json={
                "operations": [
                    {
                        "collection": "grades",
                        "operation": "delete",
                        "recordId": server_id,
                        "timestamp": "2025-01-18T00:02:00Z"
                    }
                ]
            }
        )
    
    def test_sync_push_delete_operation(self, authenticated_client):
        """Test that /api/sync/push deletes records"""
        # First create a record
        temp_id = f"temp_test_{uuid.uuid4().hex[:8]}"
        
        create_response = authenticated_client.post(
            f"{BASE_URL}/api/sync/push",
            json={
                "operations": [
                    {
                        "collection": "grades",
                        "operation": "create",
                        "recordId": temp_id,
                        "data": {
                            "student_id": f"test-student-{uuid.uuid4().hex[:8]}",
                            "class_id": "970fec6e-1b90-44ca-9413-05fe77c369b8",
                            "course_id": "test-course",
                            "academic_year": 2025,
                            "b1": 6.0
                        },
                        "timestamp": "2025-01-18T00:00:00Z"
                    }
                ]
            }
        )
        assert create_response.status_code == 200
        server_id = create_response.json()["results"][0]["serverId"]
        
        # Now delete the record
        delete_response = authenticated_client.post(
            f"{BASE_URL}/api/sync/push",
            json={
                "operations": [
                    {
                        "collection": "grades",
                        "operation": "delete",
                        "recordId": server_id,
                        "timestamp": "2025-01-18T00:01:00Z"
                    }
                ]
            }
        )
        assert delete_response.status_code == 200
        
        data = delete_response.json()
        assert data["processed"] == 1
        assert data["succeeded"] == 1
        assert data["failed"] == 0
        
        result = data["results"][0]
        assert result["success"] == True
    
    def test_sync_push_unknown_collection_fails(self, authenticated_client):
        """Test that /api/sync/push fails gracefully for unknown collections"""
        response = authenticated_client.post(
            f"{BASE_URL}/api/sync/push",
            json={
                "operations": [
                    {
                        "collection": "unknown_collection",
                        "operation": "create",
                        "recordId": "test-unknown",
                        "data": {"test": "data"},
                        "timestamp": "2025-01-18T00:00:00Z"
                    }
                ]
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["processed"] == 1
        assert data["succeeded"] == 0
        assert data["failed"] == 1
        
        result = data["results"][0]
        assert result["success"] == False
        assert "Coleção desconhecida" in result["error"]
    
    def test_sync_push_unknown_operation_fails(self, authenticated_client):
        """Test that /api/sync/push fails gracefully for unknown operations"""
        response = authenticated_client.post(
            f"{BASE_URL}/api/sync/push",
            json={
                "operations": [
                    {
                        "collection": "grades",
                        "operation": "unknown_op",
                        "recordId": "test-unknown-op",
                        "data": {"test": "data"},
                        "timestamp": "2025-01-18T00:00:00Z"
                    }
                ]
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["processed"] == 1
        assert data["succeeded"] == 0
        assert data["failed"] == 1
        
        result = data["results"][0]
        assert result["success"] == False
        assert "Operação desconhecida" in result["error"]
    
    def test_sync_push_update_nonexistent_record_fails(self, authenticated_client):
        """Test that /api/sync/push update fails for non-existent records"""
        response = authenticated_client.post(
            f"{BASE_URL}/api/sync/push",
            json={
                "operations": [
                    {
                        "collection": "grades",
                        "operation": "update",
                        "recordId": "non-existent-record-id",
                        "data": {"b1": 10},
                        "timestamp": "2025-01-18T00:00:00Z"
                    }
                ]
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["processed"] == 1
        assert data["succeeded"] == 0
        assert data["failed"] == 1
        
        result = data["results"][0]
        assert result["success"] == False
        assert "não encontrado" in result["error"]
    
    def test_sync_push_multiple_operations(self, authenticated_client):
        """Test that /api/sync/push handles multiple operations"""
        temp_id_1 = f"temp_test_{uuid.uuid4().hex[:8]}"
        temp_id_2 = f"temp_test_{uuid.uuid4().hex[:8]}"
        
        response = authenticated_client.post(
            f"{BASE_URL}/api/sync/push",
            json={
                "operations": [
                    {
                        "collection": "grades",
                        "operation": "create",
                        "recordId": temp_id_1,
                        "data": {
                            "student_id": f"test-student-{uuid.uuid4().hex[:8]}",
                            "class_id": "970fec6e-1b90-44ca-9413-05fe77c369b8",
                            "course_id": "test-course",
                            "academic_year": 2025,
                            "b1": 7.5
                        },
                        "timestamp": "2025-01-18T00:00:00Z"
                    },
                    {
                        "collection": "grades",
                        "operation": "create",
                        "recordId": temp_id_2,
                        "data": {
                            "student_id": f"test-student-{uuid.uuid4().hex[:8]}",
                            "class_id": "970fec6e-1b90-44ca-9413-05fe77c369b8",
                            "course_id": "test-course-2",
                            "academic_year": 2025,
                            "b1": 8.0
                        },
                        "timestamp": "2025-01-18T00:00:01Z"
                    }
                ]
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["processed"] == 2
        assert data["succeeded"] == 2
        assert data["failed"] == 0
        assert len(data["results"]) == 2
        
        # Cleanup
        for result in data["results"]:
            authenticated_client.post(
                f"{BASE_URL}/api/sync/push",
                json={
                    "operations": [
                        {
                            "collection": "grades",
                            "operation": "delete",
                            "recordId": result["serverId"],
                            "timestamp": "2025-01-18T00:02:00Z"
                        }
                    ]
                }
            )


class TestSyncAttendanceOperations:
    """Tests for sync operations on attendance collection"""
    
    def test_sync_push_create_attendance(self, authenticated_client):
        """Test creating attendance record via sync push"""
        temp_id = f"temp_attendance_{uuid.uuid4().hex[:8]}"
        
        response = authenticated_client.post(
            f"{BASE_URL}/api/sync/push",
            json={
                "operations": [
                    {
                        "collection": "attendance",
                        "operation": "create",
                        "recordId": temp_id,
                        "data": {
                            "class_id": "970fec6e-1b90-44ca-9413-05fe77c369b8",
                            "date": "2025-01-18",
                            "academic_year": 2025,
                            "records": [
                                {"student_id": "test-student-1", "status": "present"},
                                {"student_id": "test-student-2", "status": "absent"}
                            ]
                        },
                        "timestamp": "2025-01-18T00:00:00Z"
                    }
                ]
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["processed"] == 1
        assert data["succeeded"] == 1
        
        # Cleanup
        server_id = data["results"][0]["serverId"]
        authenticated_client.post(
            f"{BASE_URL}/api/sync/push",
            json={
                "operations": [
                    {
                        "collection": "attendance",
                        "operation": "delete",
                        "recordId": server_id,
                        "timestamp": "2025-01-18T00:01:00Z"
                    }
                ]
            }
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
