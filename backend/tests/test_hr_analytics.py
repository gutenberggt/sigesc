"""
Test HR Dashboard Analytics Endpoint (Fase 5 - Indicadores Visuais)
Tests the GET /api/hr/dashboard/analytics endpoint for admin/semed users.
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = "@Celta2007"
KNOWN_COMPETENCY_ID = "4f702c74-46c6-4233-ba50-9e1443b493f2"


class TestHRAnalyticsEndpoint:
    """Tests for GET /api/hr/dashboard/analytics endpoint"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token")
        pytest.skip(f"Authentication failed: {response.status_code}")
    
    @pytest.fixture(scope="class")
    def auth_headers(self, admin_token):
        """Headers with auth token"""
        return {
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json"
        }
    
    # =================== AUTH TESTS ===================
    
    def test_analytics_requires_auth(self):
        """Analytics endpoint returns 401 without token"""
        response = requests.get(
            f"{BASE_URL}/api/hr/dashboard/analytics?competency_id={KNOWN_COMPETENCY_ID}"
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Analytics endpoint requires authentication (401 without token)")
    
    def test_analytics_requires_competency_id(self, auth_headers):
        """Analytics endpoint requires competency_id parameter"""
        response = requests.get(
            f"{BASE_URL}/api/hr/dashboard/analytics",
            headers=auth_headers
        )
        # Should return 422 (validation error) without required param
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print("PASS: Analytics endpoint requires competency_id parameter")
    
    def test_analytics_invalid_competency_returns_404(self, auth_headers):
        """Analytics endpoint returns 404 for non-existent competency"""
        response = requests.get(
            f"{BASE_URL}/api/hr/dashboard/analytics?competency_id=invalid-uuid-12345",
            headers=auth_headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: Analytics endpoint returns 404 for invalid competency")
    
    # =================== DATA STRUCTURE TESTS ===================
    
    def test_analytics_returns_correct_structure(self, auth_headers):
        """Analytics endpoint returns correct data structure"""
        response = requests.get(
            f"{BASE_URL}/api/hr/dashboard/analytics?competency_id={KNOWN_COMPETENCY_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        
        # Check top-level keys
        assert "status_distribution" in data, "Missing status_distribution"
        assert "schools_ranking" in data, "Missing schools_ranking"
        assert "network_summary" in data, "Missing network_summary"
        assert "conformity" in data, "Missing conformity"
        
        print("PASS: Analytics endpoint returns correct top-level structure")
    
    def test_analytics_status_distribution_structure(self, auth_headers):
        """status_distribution is a dict with status keys and count values"""
        response = requests.get(
            f"{BASE_URL}/api/hr/dashboard/analytics?competency_id={KNOWN_COMPETENCY_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        status_dist = data.get("status_distribution", {})
        
        # Should be a dict
        assert isinstance(status_dist, dict), "status_distribution should be a dict"
        
        # All values should be integers (counts)
        for status, count in status_dist.items():
            assert isinstance(count, int), f"Count for {status} should be int, got {type(count)}"
            assert count >= 0, f"Count for {status} should be >= 0"
        
        print(f"PASS: status_distribution structure valid - {len(status_dist)} statuses found")
    
    def test_analytics_schools_ranking_structure(self, auth_headers):
        """schools_ranking is a list of school data objects"""
        response = requests.get(
            f"{BASE_URL}/api/hr/dashboard/analytics?competency_id={KNOWN_COMPETENCY_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        schools = data.get("schools_ranking", [])
        
        # Should be a list
        assert isinstance(schools, list), "schools_ranking should be a list"
        
        # If there are schools, check structure
        if schools:
            school = schools[0]
            expected_keys = ["name", "full_name", "employees", "absences", "expected", "worked", "complementary"]
            for key in expected_keys:
                assert key in school, f"Missing key '{key}' in school data"
        
        print(f"PASS: schools_ranking structure valid - {len(schools)} schools found")
    
    def test_analytics_network_summary_structure(self, auth_headers):
        """network_summary contains hour totals"""
        response = requests.get(
            f"{BASE_URL}/api/hr/dashboard/analytics?competency_id={KNOWN_COMPETENCY_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        summary = data.get("network_summary", {})
        
        # Check required keys
        expected_keys = ["expected", "worked", "complementary", "absences", "medical", "leave"]
        for key in expected_keys:
            assert key in summary, f"Missing key '{key}' in network_summary"
            assert isinstance(summary[key], (int, float)), f"{key} should be numeric"
        
        print(f"PASS: network_summary structure valid - expected={summary['expected']}, worked={summary['worked']}")
    
    def test_analytics_conformity_structure(self, auth_headers):
        """conformity contains percentage and count data"""
        response = requests.get(
            f"{BASE_URL}/api/hr/dashboard/analytics?competency_id={KNOWN_COMPETENCY_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        conformity = data.get("conformity", {})
        
        # Check required keys
        expected_keys = [
            "employees_ok_pct", "payrolls_sent_pct",
            "ok_employees", "total_employees",
            "sent_payrolls", "total_payrolls"
        ]
        for key in expected_keys:
            assert key in conformity, f"Missing key '{key}' in conformity"
        
        # Percentages should be 0-100 range
        assert 0 <= conformity["employees_ok_pct"] <= 100, "employees_ok_pct should be 0-100"
        assert 0 <= conformity["payrolls_sent_pct"] <= 100, "payrolls_sent_pct should be 0-100"
        
        # Counts should be non-negative
        assert conformity["ok_employees"] >= 0, "ok_employees should be >= 0"
        assert conformity["total_employees"] >= 0, "total_employees should be >= 0"
        assert conformity["sent_payrolls"] >= 0, "sent_payrolls should be >= 0"
        assert conformity["total_payrolls"] >= 0, "total_payrolls should be >= 0"
        
        print(f"PASS: conformity structure valid - employees_ok={conformity['employees_ok_pct']}%, payrolls_sent={conformity['payrolls_sent_pct']}%")
    
    # =================== DATA CONSISTENCY TESTS ===================
    
    def test_analytics_conformity_counts_consistent(self, auth_headers):
        """ok_employees <= total_employees and sent_payrolls <= total_payrolls"""
        response = requests.get(
            f"{BASE_URL}/api/hr/dashboard/analytics?competency_id={KNOWN_COMPETENCY_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        conformity = data.get("conformity", {})
        
        assert conformity["ok_employees"] <= conformity["total_employees"], \
            "ok_employees should be <= total_employees"
        assert conformity["sent_payrolls"] <= conformity["total_payrolls"], \
            "sent_payrolls should be <= total_payrolls"
        
        print("PASS: Conformity counts are consistent")
    
    def test_analytics_schools_ranking_sorted_by_absences(self, auth_headers):
        """schools_ranking should be sorted by absences descending"""
        response = requests.get(
            f"{BASE_URL}/api/hr/dashboard/analytics?competency_id={KNOWN_COMPETENCY_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        schools = data.get("schools_ranking", [])
        
        if len(schools) > 1:
            absences = [s.get("absences", 0) for s in schools]
            assert absences == sorted(absences, reverse=True), \
                "schools_ranking should be sorted by absences descending"
        
        print(f"PASS: schools_ranking sorted correctly ({len(schools)} schools)")
    
    def test_analytics_schools_ranking_max_15(self, auth_headers):
        """schools_ranking should have max 15 entries"""
        response = requests.get(
            f"{BASE_URL}/api/hr/dashboard/analytics?competency_id={KNOWN_COMPETENCY_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        schools = data.get("schools_ranking", [])
        
        assert len(schools) <= 15, f"schools_ranking should have max 15 entries, got {len(schools)}"
        
        print(f"PASS: schools_ranking has {len(schools)} entries (max 15)")


class TestHRAnalyticsIntegration:
    """Integration tests comparing analytics with dashboard data"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token")
        pytest.skip(f"Authentication failed: {response.status_code}")
    
    @pytest.fixture(scope="class")
    def auth_headers(self, admin_token):
        """Headers with auth token"""
        return {
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json"
        }
    
    def test_analytics_total_payrolls_matches_dashboard(self, auth_headers):
        """Analytics total_payrolls should match dashboard total_schools"""
        # Get dashboard data
        dashboard_resp = requests.get(
            f"{BASE_URL}/api/hr/dashboard?competency_id={KNOWN_COMPETENCY_ID}",
            headers=auth_headers
        )
        assert dashboard_resp.status_code == 200
        dashboard = dashboard_resp.json()
        
        # Get analytics data
        analytics_resp = requests.get(
            f"{BASE_URL}/api/hr/dashboard/analytics?competency_id={KNOWN_COMPETENCY_ID}",
            headers=auth_headers
        )
        assert analytics_resp.status_code == 200
        analytics = analytics_resp.json()
        
        dashboard_schools = dashboard.get("summary", {}).get("total_schools", 0)
        analytics_payrolls = analytics.get("conformity", {}).get("total_payrolls", 0)
        
        assert dashboard_schools == analytics_payrolls, \
            f"Dashboard total_schools ({dashboard_schools}) should match analytics total_payrolls ({analytics_payrolls})"
        
        print(f"PASS: Dashboard total_schools ({dashboard_schools}) matches analytics total_payrolls")
    
    def test_analytics_status_distribution_sums_to_total(self, auth_headers):
        """Sum of status_distribution should equal total_payrolls"""
        response = requests.get(
            f"{BASE_URL}/api/hr/dashboard/analytics?competency_id={KNOWN_COMPETENCY_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        status_dist = data.get("status_distribution", {})
        total_payrolls = data.get("conformity", {}).get("total_payrolls", 0)
        
        status_sum = sum(status_dist.values())
        assert status_sum == total_payrolls, \
            f"Sum of status_distribution ({status_sum}) should equal total_payrolls ({total_payrolls})"
        
        print(f"PASS: status_distribution sum ({status_sum}) equals total_payrolls")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
