"""
Test HR PDF Report Endpoints (Fase 4)
- Espelho Individual: GET /api/hr/reports/espelho/{item_id}
- Folha por Escola: GET /api/hr/reports/folha-escola/{payroll_id}
- Consolidado da Rede: GET /api/hr/reports/consolidado-rede/{competency_id}
- Auditoria: GET /api/hr/reports/auditoria/{competency_id}
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = "@Celta2007"

# Known test IDs from main agent
KNOWN_COMPETENCY_ID = "4f702c74-46c6-4233-ba50-9e1443b493f2"
KNOWN_PAYROLL_ID = "316d749e-24dc-4b83-8000-56cdc0e00af1"


class TestHRPDFReports:
    """Test HR PDF Report Endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login to get token
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        if login_response.status_code == 200:
            data = login_response.json()
            # Note: API returns 'access_token' not 'token'
            token = data.get('access_token') or data.get('token')
            if token:
                self.session.headers.update({"Authorization": f"Bearer {token}"})
                self.token = token
            else:
                pytest.skip("No token in login response")
        else:
            pytest.skip(f"Login failed: {login_response.status_code}")
    
    # =================== AUTHENTICATION TESTS ===================
    
    def test_consolidado_rede_requires_auth(self):
        """Test that consolidado-rede endpoint requires authentication"""
        # Use a new session without auth
        response = requests.get(f"{BASE_URL}/api/hr/reports/consolidado-rede/{KNOWN_COMPETENCY_ID}")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Consolidado-rede requires authentication (401 without token)")
    
    def test_auditoria_requires_auth(self):
        """Test that auditoria endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/hr/reports/auditoria/{KNOWN_COMPETENCY_ID}")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Auditoria requires authentication (401 without token)")
    
    def test_folha_escola_requires_auth(self):
        """Test that folha-escola endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/hr/reports/folha-escola/{KNOWN_PAYROLL_ID}")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Folha-escola requires authentication (401 without token)")
    
    def test_espelho_requires_auth(self):
        """Test that espelho endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/hr/reports/espelho/nonexistent-id")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Espelho requires authentication (401 without token)")
    
    # =================== CONSOLIDADO DA REDE TESTS ===================
    
    def test_consolidado_rede_returns_pdf(self):
        """Test GET /api/hr/reports/consolidado-rede/{competency_id} returns valid PDF"""
        response = self.session.get(f"{BASE_URL}/api/hr/reports/consolidado-rede/{KNOWN_COMPETENCY_ID}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        assert response.headers.get('Content-Type') == 'application/pdf', \
            f"Expected application/pdf, got {response.headers.get('Content-Type')}"
        
        # Verify PDF signature
        content = response.content
        assert content[:4] == b'%PDF', "Response is not a valid PDF (missing %PDF signature)"
        
        # Check Content-Disposition header
        content_disp = response.headers.get('Content-Disposition', '')
        assert 'consolidado_rede' in content_disp.lower() or 'filename' in content_disp.lower(), \
            f"Content-Disposition should contain filename: {content_disp}"
        
        print(f"PASS: Consolidado-rede returns valid PDF ({len(content)} bytes)")
    
    def test_consolidado_rede_nonexistent_competency(self):
        """Test consolidado-rede with non-existent competency returns 404"""
        response = self.session.get(f"{BASE_URL}/api/hr/reports/consolidado-rede/nonexistent-id-12345")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: Consolidado-rede returns 404 for non-existent competency")
    
    # =================== AUDITORIA TESTS ===================
    
    def test_auditoria_returns_pdf(self):
        """Test GET /api/hr/reports/auditoria/{competency_id} returns valid PDF"""
        response = self.session.get(f"{BASE_URL}/api/hr/reports/auditoria/{KNOWN_COMPETENCY_ID}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        assert response.headers.get('Content-Type') == 'application/pdf', \
            f"Expected application/pdf, got {response.headers.get('Content-Type')}"
        
        # Verify PDF signature
        content = response.content
        assert content[:4] == b'%PDF', "Response is not a valid PDF (missing %PDF signature)"
        
        # Check Content-Disposition header
        content_disp = response.headers.get('Content-Disposition', '')
        assert 'auditoria' in content_disp.lower() or 'filename' in content_disp.lower(), \
            f"Content-Disposition should contain filename: {content_disp}"
        
        print(f"PASS: Auditoria returns valid PDF ({len(content)} bytes)")
    
    def test_auditoria_nonexistent_competency(self):
        """Test auditoria with non-existent competency returns 404"""
        response = self.session.get(f"{BASE_URL}/api/hr/reports/auditoria/nonexistent-id-12345")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: Auditoria returns 404 for non-existent competency")
    
    # =================== FOLHA POR ESCOLA TESTS ===================
    
    def test_folha_escola_returns_pdf(self):
        """Test GET /api/hr/reports/folha-escola/{payroll_id} returns valid PDF"""
        response = self.session.get(f"{BASE_URL}/api/hr/reports/folha-escola/{KNOWN_PAYROLL_ID}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        assert response.headers.get('Content-Type') == 'application/pdf', \
            f"Expected application/pdf, got {response.headers.get('Content-Type')}"
        
        # Verify PDF signature
        content = response.content
        assert content[:4] == b'%PDF', "Response is not a valid PDF (missing %PDF signature)"
        
        # Check Content-Disposition header
        content_disp = response.headers.get('Content-Disposition', '')
        assert 'folha' in content_disp.lower() or 'filename' in content_disp.lower(), \
            f"Content-Disposition should contain filename: {content_disp}"
        
        print(f"PASS: Folha-escola returns valid PDF ({len(content)} bytes)")
    
    def test_folha_escola_nonexistent_payroll(self):
        """Test folha-escola with non-existent payroll returns 404"""
        response = self.session.get(f"{BASE_URL}/api/hr/reports/folha-escola/nonexistent-id-12345")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: Folha-escola returns 404 for non-existent payroll")
    
    # =================== ESPELHO INDIVIDUAL TESTS ===================
    
    def test_espelho_nonexistent_item(self):
        """Test espelho with non-existent item returns 404"""
        response = self.session.get(f"{BASE_URL}/api/hr/reports/espelho/nonexistent-item-id-12345")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: Espelho returns 404 for non-existent item")
    
    def test_espelho_with_valid_item(self):
        """Test espelho with a valid item (if any exists in the payroll)"""
        # First, get the payroll detail to find an item_id
        payroll_response = self.session.get(f"{BASE_URL}/api/hr/school-payrolls/{KNOWN_PAYROLL_ID}")
        
        if payroll_response.status_code != 200:
            pytest.skip(f"Could not fetch payroll detail: {payroll_response.status_code}")
        
        payroll_data = payroll_response.json()
        items = payroll_data.get('items', [])
        
        if not items:
            # Test school has 0 employees, so espelho should return 404 for any item
            print("PASS: Payroll has 0 items (test school has no employees) - espelho 404 test already covers this")
            return
        
        # If there are items, test the first one
        item_id = items[0].get('id')
        response = self.session.get(f"{BASE_URL}/api/hr/reports/espelho/{item_id}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert response.headers.get('Content-Type') == 'application/pdf', \
            f"Expected application/pdf, got {response.headers.get('Content-Type')}"
        
        content = response.content
        assert content[:4] == b'%PDF', "Response is not a valid PDF"
        
        print(f"PASS: Espelho returns valid PDF for item {item_id} ({len(content)} bytes)")
    
    # =================== ROLE-BASED ACCESS TESTS ===================
    
    def test_consolidado_requires_admin_or_semed_role(self):
        """Test that consolidado-rede requires admin/semed roles (admin user should work)"""
        # Admin user is already authenticated, should have access
        response = self.session.get(f"{BASE_URL}/api/hr/reports/consolidado-rede/{KNOWN_COMPETENCY_ID}")
        assert response.status_code == 200, f"Admin should have access, got {response.status_code}"
        print("PASS: Admin user has access to consolidado-rede")
    
    def test_auditoria_requires_admin_or_semed_role(self):
        """Test that auditoria requires admin/semed roles (admin user should work)"""
        response = self.session.get(f"{BASE_URL}/api/hr/reports/auditoria/{KNOWN_COMPETENCY_ID}")
        assert response.status_code == 200, f"Admin should have access, got {response.status_code}"
        print("PASS: Admin user has access to auditoria")
    
    # =================== PDF CONTENT VALIDATION ===================
    
    def test_consolidado_pdf_has_content(self):
        """Test that consolidado PDF has reasonable content size"""
        response = self.session.get(f"{BASE_URL}/api/hr/reports/consolidado-rede/{KNOWN_COMPETENCY_ID}")
        
        assert response.status_code == 200
        content = response.content
        
        # PDF should be at least 1KB (even empty PDFs have headers)
        assert len(content) > 1000, f"PDF seems too small: {len(content)} bytes"
        print(f"PASS: Consolidado PDF has reasonable size ({len(content)} bytes)")
    
    def test_auditoria_pdf_has_content(self):
        """Test that auditoria PDF has reasonable content size"""
        response = self.session.get(f"{BASE_URL}/api/hr/reports/auditoria/{KNOWN_COMPETENCY_ID}")
        
        assert response.status_code == 200
        content = response.content
        
        # PDF should be at least 1KB
        assert len(content) > 1000, f"PDF seems too small: {len(content)} bytes"
        print(f"PASS: Auditoria PDF has reasonable size ({len(content)} bytes)")
    
    def test_folha_escola_pdf_has_content(self):
        """Test that folha-escola PDF has reasonable content size"""
        response = self.session.get(f"{BASE_URL}/api/hr/reports/folha-escola/{KNOWN_PAYROLL_ID}")
        
        assert response.status_code == 200
        content = response.content
        
        # PDF should be at least 1KB
        assert len(content) > 1000, f"PDF seems too small: {len(content)} bytes"
        print(f"PASS: Folha-escola PDF has reasonable size ({len(content)} bytes)")


class TestHRDashboardAndPayrollDetail:
    """Test HR Dashboard and Payroll Detail endpoints to verify PDF buttons context"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        if login_response.status_code == 200:
            data = login_response.json()
            token = data.get('access_token') or data.get('token')
            if token:
                self.session.headers.update({"Authorization": f"Bearer {token}"})
            else:
                pytest.skip("No token in login response")
        else:
            pytest.skip(f"Login failed: {login_response.status_code}")
    
    def test_dashboard_returns_competency_data(self):
        """Test that dashboard returns competency data needed for PDF buttons"""
        response = self.session.get(f"{BASE_URL}/api/hr/dashboard?competency_id={KNOWN_COMPETENCY_ID}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert 'competency' in data, "Dashboard should return competency data"
        assert data['competency'] is not None, "Competency should not be null"
        assert 'id' in data['competency'], "Competency should have id"
        
        print(f"PASS: Dashboard returns competency data (id: {data['competency'].get('id')})")
    
    def test_payroll_detail_returns_items(self):
        """Test that payroll detail returns items for espelho PDF button"""
        response = self.session.get(f"{BASE_URL}/api/hr/school-payrolls/{KNOWN_PAYROLL_ID}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert 'id' in data, "Payroll should have id"
        assert 'items' in data, "Payroll should have items array"
        assert 'school_name' in data, "Payroll should have school_name"
        
        items_count = len(data.get('items', []))
        print(f"PASS: Payroll detail returns data (school: {data.get('school_name')}, items: {items_count})")
    
    def test_competencies_list(self):
        """Test that competencies list endpoint works"""
        response = self.session.get(f"{BASE_URL}/api/hr/competencies")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert isinstance(data, list), "Competencies should be a list"
        
        # Find our known competency
        known_comp = next((c for c in data if c.get('id') == KNOWN_COMPETENCY_ID), None)
        assert known_comp is not None, f"Known competency {KNOWN_COMPETENCY_ID} should be in list"
        
        print(f"PASS: Competencies list works ({len(data)} competencies, known competency found)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
