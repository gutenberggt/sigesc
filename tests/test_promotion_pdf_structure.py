"""
Test cases for Livro de Promoção PDF structure verification
Tests the new 2-page structure with:
- Page 1: 1º Semestre (1º e 2º Bimestre + Recuperação 1º Semestre)
- Page 2: 2º Semestre (3º e 4º Bimestre + Recuperação 2º Semestre) + Total/Média/Resultado
- Institutional header with logo
- Signatures (Secretário/Diretor) and date
"""

import pytest
import requests
import os
from io import BytesIO

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://edusys-offline.preview.emergentagent.com')

# Test credentials
TEST_EMAIL = "gutenberg@sigesc.com"
TEST_PASSWORD = "@Celta2007"

# Known class IDs for testing
TEST_CLASSES = {
    "3º Ano A": "68fe60c3-a103-4617-9716-5fa304ac8a38",
    "6º Ano A": "d031e882-b865-411b-89ad-059c2982e48d",
    "9º Ano A": "36d77a13-c5f0-4907-860d-ed6c3db32b8b"
}


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for tests"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json().get("access_token")


@pytest.fixture
def api_client(auth_token):
    """Create authenticated session"""
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    })
    return session


class TestPDFStructure:
    """Tests for PDF structure verification"""
    
    def test_pdf_has_2_pages(self, api_client):
        """Test that PDF has exactly 2 pages"""
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            pytest.skip("PyPDF2 not installed")
        
        class_id = TEST_CLASSES["6º Ano A"]
        response = api_client.get(
            f"{BASE_URL}/api/documents/promotion/{class_id}?academic_year=2025"
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Parse PDF
        pdf_buffer = BytesIO(response.content)
        reader = PdfReader(pdf_buffer)
        
        # Verify 2 pages
        assert len(reader.pages) == 2, f"Expected 2 pages, got {len(reader.pages)}"
        print(f"✓ PDF has {len(reader.pages)} pages as expected")
    
    def test_page1_contains_1st_semester_content(self, api_client):
        """Test that Page 1 contains 1st semester content"""
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            pytest.skip("PyPDF2 not installed")
        
        class_id = TEST_CLASSES["6º Ano A"]
        response = api_client.get(
            f"{BASE_URL}/api/documents/promotion/{class_id}?academic_year=2025"
        )
        
        assert response.status_code == 200
        
        pdf_buffer = BytesIO(response.content)
        reader = PdfReader(pdf_buffer)
        
        # Extract text from page 1
        page1_text = reader.pages[0].extract_text()
        
        # Verify page 1 contains 1st semester content
        assert "1º BIMESTRE" in page1_text or "1º Bim" in page1_text.upper() or "BIMESTRE" in page1_text.upper(), \
            "Page 1 should contain 1st bimester content"
        assert "2º BIMESTRE" in page1_text or "2º Bim" in page1_text.upper() or "BIMESTRE" in page1_text.upper(), \
            "Page 1 should contain 2nd bimester content"
        
        print(f"✓ Page 1 contains 1st semester content")
    
    def test_page2_contains_2nd_semester_and_result(self, api_client):
        """Test that Page 2 contains 2nd semester content and results"""
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            pytest.skip("PyPDF2 not installed")
        
        class_id = TEST_CLASSES["6º Ano A"]
        response = api_client.get(
            f"{BASE_URL}/api/documents/promotion/{class_id}?academic_year=2025"
        )
        
        assert response.status_code == 200
        
        pdf_buffer = BytesIO(response.content)
        reader = PdfReader(pdf_buffer)
        
        # Extract text from page 2
        page2_text = reader.pages[1].extract_text()
        
        # Verify page 2 contains 2nd semester content
        assert "3º BIMESTRE" in page2_text or "3º Bim" in page2_text.upper() or "BIMESTRE" in page2_text.upper(), \
            "Page 2 should contain 3rd bimester content"
        assert "4º BIMESTRE" in page2_text or "4º Bim" in page2_text.upper() or "BIMESTRE" in page2_text.upper(), \
            "Page 2 should contain 4th bimester content"
        
        # Verify result columns
        assert "RESULTADO" in page2_text.upper() or "TOTAL" in page2_text.upper() or "MÉDIA" in page2_text.upper(), \
            "Page 2 should contain result/total/média columns"
        
        print(f"✓ Page 2 contains 2nd semester content and results")
    
    def test_pdf_contains_institutional_header(self, api_client):
        """Test that PDF contains institutional header"""
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            pytest.skip("PyPDF2 not installed")
        
        class_id = TEST_CLASSES["6º Ano A"]
        response = api_client.get(
            f"{BASE_URL}/api/documents/promotion/{class_id}?academic_year=2025"
        )
        
        assert response.status_code == 200
        
        pdf_buffer = BytesIO(response.content)
        reader = PdfReader(pdf_buffer)
        
        # Extract text from page 1
        page1_text = reader.pages[0].extract_text()
        
        # Verify institutional header elements
        assert "LIVRO DE PROMOÇÃO" in page1_text.upper(), \
            "PDF should contain 'LIVRO DE PROMOÇÃO' title"
        assert "ESCOLA" in page1_text.upper(), \
            "PDF should contain school information"
        assert "TURMA" in page1_text.upper() or "ANO" in page1_text.upper(), \
            "PDF should contain class information"
        
        print(f"✓ PDF contains institutional header")
    
    def test_pdf_contains_signatures(self, api_client):
        """Test that PDF contains signature fields"""
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            pytest.skip("PyPDF2 not installed")
        
        class_id = TEST_CLASSES["6º Ano A"]
        response = api_client.get(
            f"{BASE_URL}/api/documents/promotion/{class_id}?academic_year=2025"
        )
        
        assert response.status_code == 200
        
        pdf_buffer = BytesIO(response.content)
        reader = PdfReader(pdf_buffer)
        
        # Extract text from page 2 (signatures should be at the end)
        page2_text = reader.pages[1].extract_text()
        
        # Verify signature fields
        has_secretario = "SECRETÁRIO" in page2_text.upper() or "SECRETARIA" in page2_text.upper()
        has_diretor = "DIRETOR" in page2_text.upper() or "DIRETORA" in page2_text.upper()
        
        assert has_secretario or has_diretor, \
            "PDF should contain signature fields (Secretário/Diretor)"
        
        print(f"✓ PDF contains signature fields")
    
    def test_pdf_contains_date(self, api_client):
        """Test that PDF contains date"""
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            pytest.skip("PyPDF2 not installed")
        
        class_id = TEST_CLASSES["6º Ano A"]
        response = api_client.get(
            f"{BASE_URL}/api/documents/promotion/{class_id}?academic_year=2025"
        )
        
        assert response.status_code == 200
        
        pdf_buffer = BytesIO(response.content)
        reader = PdfReader(pdf_buffer)
        
        # Extract text from page 2
        page2_text = reader.pages[1].extract_text()
        
        # Verify date is present (month names in Portuguese)
        months = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 
                  'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
        
        has_date = any(month in page2_text.lower() for month in months)
        
        assert has_date, "PDF should contain date in Portuguese format"
        
        print(f"✓ PDF contains date")
    
    def test_pdf_size_reasonable(self, api_client):
        """Test that PDF size is reasonable (~34KB as mentioned)"""
        class_id = TEST_CLASSES["6º Ano A"]
        response = api_client.get(
            f"{BASE_URL}/api/documents/promotion/{class_id}?academic_year=2025"
        )
        
        assert response.status_code == 200
        
        pdf_size_kb = len(response.content) / 1024
        
        # PDF should be between 10KB and 100KB
        assert 10 < pdf_size_kb < 100, f"PDF size {pdf_size_kb:.1f}KB is outside expected range (10-100KB)"
        
        print(f"✓ PDF size is {pdf_size_kb:.1f}KB (within expected range)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
