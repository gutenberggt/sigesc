"""
E2E HTTP test — Fase 3c: Ficha Individual de Dependência (Iter 76).

Valida:
  - GET /api/documents/ficha-individual-dependency/{student_id} retorna PDF
    válido para aluno com dependências ativas.
  - Sem dependências ativas → 400.
  - target_class_id inexistente → 404.
  - Aluno inexistente → 404.
  - Header Content-Type=application/pdf.
"""
from __future__ import annotations

import os
import requests
import pytest

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "https://school-reorganize.preview.emergentagent.com")
    .rstrip("/")
)
EMAIL = "gutenberg@sigesc.com"
PASSWORD = "@Celta2007"
TENANT = "fix_mant_v1"
CLASS_ID = "fix_cl_v1"
STU_HEITOR = "fix_stu_heitor"
STU_ANA = "fix_stu_ana"  # sem dependências
YEAR = 2026


@pytest.fixture(scope="module")
def auth():
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    token = data.get("access_token") or data.get("token")
    csrf = data.get("csrf_token") or ""
    assert token
    s.headers.update({
        "Authorization": f"Bearer {token}",
        "X-CSRF-Token": csrf,
        "X-Mantenedora-Id": TENANT,
        "Content-Type": "application/json",
    })
    # Sanity
    r2 = s.get(f"{BASE_URL}/api/students/{STU_HEITOR}", timeout=15)
    if r2.status_code == 404:
        pytest.skip("Fixture seed_dependency_diary_fixture ausente.")
    return s


def test_ficha_dependency_returns_pdf(auth):
    """Heitor tem 2 dependências ativas em fix_cl_v1. Deve gerar PDF válido."""
    r = auth.get(
        f"{BASE_URL}/api/documents/ficha-individual-dependency/{STU_HEITOR}",
        params={"target_class_id": CLASS_ID, "academic_year": YEAR},
        timeout=60,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    assert r.headers.get("content-type", "").startswith("application/pdf"), \
        f"content-type={r.headers.get('content-type')}"
    body = r.content
    assert body.startswith(b"%PDF-"), "PDF magic header faltando"
    assert len(body) > 1024, f"PDF muito pequeno: {len(body)} bytes"


def test_ficha_dependency_filename_header(auth):
    """Content-Disposition deve trazer 'ficha_dependencia_'."""
    r = auth.get(
        f"{BASE_URL}/api/documents/ficha-individual-dependency/{STU_HEITOR}",
        params={"target_class_id": CLASS_ID, "academic_year": YEAR},
        timeout=60,
    )
    assert r.status_code == 200
    cd = r.headers.get("content-disposition", "")
    assert "ficha_dependencia_" in cd, f"Content-Disposition={cd}"
    assert f"{YEAR}.pdf" in cd, f"Esperava ano no filename, got {cd}"


def test_ficha_dependency_without_active_deps_returns_400(auth):
    """Ana é regular sem deps. Endpoint deve retornar 400."""
    r = auth.get(
        f"{BASE_URL}/api/documents/ficha-individual-dependency/{STU_ANA}",
        params={"target_class_id": CLASS_ID, "academic_year": YEAR},
        timeout=30,
    )
    assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"


def test_ficha_dependency_invalid_class_returns_404(auth):
    """target_class_id inexistente → 404."""
    r = auth.get(
        f"{BASE_URL}/api/documents/ficha-individual-dependency/{STU_HEITOR}",
        params={"target_class_id": "DOES_NOT_EXIST_zz", "academic_year": YEAR},
        timeout=30,
    )
    assert r.status_code == 404


def test_ficha_dependency_invalid_student_returns_404(auth):
    r = auth.get(
        f"{BASE_URL}/api/documents/ficha-individual-dependency/UNKNOWN_STU_xx",
        params={"target_class_id": CLASS_ID, "academic_year": YEAR},
        timeout=30,
    )
    assert r.status_code == 404


def test_ficha_dependency_requires_auth():
    """Sem token → 401/403."""
    r = requests.get(
        f"{BASE_URL}/api/documents/ficha-individual-dependency/{STU_HEITOR}",
        params={"target_class_id": CLASS_ID, "academic_year": YEAR},
        timeout=15,
    )
    assert r.status_code in (401, 403), f"got {r.status_code}"
