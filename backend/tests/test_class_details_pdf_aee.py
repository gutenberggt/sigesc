"""
Tests for the PDF "Detalhes da Turma" - AEE grade level behavior.
GET /api/classes/{class_id}/details/pdf should:
 - For AEE class (atendimento_programa='AEE') -> "Série/Etapa" line shows "-" (not grade_level)
 - For non-AEE class -> "Série/Etapa" shows the real grade_level
"""
from __future__ import annotations

import os
import subprocess
import tempfile

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = "@Celta2007"
MANTENEDORA_ID = "a991c1ac-56b1-46a8-b122-effedbe19b21"

CLASS_ID_AEE = "73844918-60b1-4c62-b6cb-a21a35cc49c1"
CLASS_ID_NON_AEE = "3da4e569-6522-432c-9b42-1e344a2f0c69"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _download_pdf_text(token, class_id):
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Mantenedora-Id": MANTENEDORA_ID,
    }
    r = requests.get(
        f"{BASE_URL}/api/classes/{class_id}/details/pdf",
        headers=headers,
        timeout=45,
    )
    assert r.status_code == 200, f"PDF download failed {r.status_code}: {r.text[:300]}"
    assert r.headers.get("content-type", "").startswith("application/pdf"), f"Unexpected CT: {r.headers.get('content-type')}"

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(r.content)
        path = tmp.name

    out = subprocess.run(
        ["pdftotext", "-layout", path, "-"], capture_output=True, text=True, timeout=30
    )
    os.unlink(path)
    assert out.returncode == 0, f"pdftotext failed: {out.stderr}"
    return out.stdout


class TestClassDetailsPDFAEE:
    def test_aee_class_shows_dash_in_serie_etapa(self, admin_token):
        """For AEE class, the 'Série/Etapa' field must render '-' (not the grade_level)."""
        text = _download_pdf_text(admin_token, CLASS_ID_AEE)
        assert "Série/Etapa" in text or "Serie/Etapa" in text, "Campo 'Série/Etapa' ausente no PDF AEE"

        # Find the line containing Série/Etapa and check the value is '-'
        found_line = None
        for line in text.splitlines():
            if "Série/Etapa" in line or "Serie/Etapa" in line:
                found_line = line
                break
        assert found_line is not None
        # Extract content after label
        idx = found_line.find("Etapa:")
        after_label = found_line[idx + len("Etapa:"):].strip()
        # For AEE, the value after "Série/Etapa:" should be "-" (possibly padded with spaces)
        # Take only the first token since line can contain other columns
        first_token = after_label.split()[0] if after_label.split() else ""
        assert first_token == "-", (
            f"Esperado '-' após 'Série/Etapa:' para turma AEE, obtido '{first_token}'. "
            f"Linha completa: {found_line!r}"
        )

    def test_non_aee_class_shows_grade_level(self, admin_token):
        """For non-AEE class (6º ANO A), 'Série/Etapa' must render the real grade_level (not '-')."""
        text = _download_pdf_text(admin_token, CLASS_ID_NON_AEE)
        found_line = None
        for line in text.splitlines():
            if "Série/Etapa" in line or "Serie/Etapa" in line:
                found_line = line
                break
        assert found_line is not None, "Campo 'Série/Etapa' ausente no PDF não-AEE"
        idx = found_line.find("Etapa:")
        after_label = found_line[idx + len("Etapa:"):].strip()
        first_token = after_label.split()[0] if after_label.split() else ""
        assert first_token != "-", (
            f"Para turma não-AEE o grade_level deve aparecer — obtido '-'. Linha: {found_line!r}"
        )
        # Additionally, should contain some reasonable grade_level text.
        # Most common: contains '6' or 'ANO'
        assert any(k in after_label.upper() for k in ("ANO", "6", "SÉRIE", "SERIE", "ETAPA", "6º", "6°")), (
            f"grade_level inesperado: '{after_label}'"
        )
