"""
E2E test — PDFs agora retornam `Content-Disposition: attachment` (Iter 76).

Garante que todos os endpoints prioritários de documento entregam o PDF como
download direto, sem páginas/arquivos temporários no servidor.

Endpoints cobertos:
  - /api/documents/boletim/{student_id}
  - /api/documents/ficha-individual/{student_id}
  - /api/documents/ficha-individual-dependency/{student_id}
  - /api/documents/declaracao-matricula/{student_id}
  - /api/documents/declaracao-frequencia/{student_id}
  - /api/documents/declaracao-transferencia/{student_id} (skip se aluno não transferido)
  - /api/documents/historico-escolar/{student_id}

Endpoints que devem CONTINUAR `inline` (não estão na lista de prioridade):
  - /api/documents/certificado/{student_id}
  - /api/documents/batch/{class_id}/{document_type}
  - /api/documents/jobs/{job_id}/download
"""
from __future__ import annotations

import os
import requests
import pytest

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "https://operational-diary.preview.emergentagent.com")
    .rstrip("/")
)
EMAIL = "gutenberg@sigesc.com"
PASSWORD = "@Celta2007"
TENANT = "fix_mant_v1"

# Seed do fixture de dependência: garante aluno com matrícula real
STU_FELIPE = "fix_stu_felipe"   # with_dependency (regular em fix_cl_v1)
STU_HEITOR = "fix_stu_heitor"   # dependency_only
CLASS_V1 = "fix_cl_v1"
YEAR = 2026


@pytest.fixture(scope="module")
def auth():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200
    d = r.json()
    tok = d.get("access_token") or d.get("token")
    csrf = d.get("csrf_token") or ""
    s.headers.update({
        "Authorization": f"Bearer {tok}",
        "X-CSRF-Token": csrf,
        "X-Mantenedora-Id": TENANT,
        "Content-Type": "application/json",
    })
    if s.get(f"{BASE_URL}/api/students/{STU_FELIPE}", timeout=10).status_code == 404:
        pytest.skip("Fixture seed_dependency_diary_fixture ausente.")
    return s


def _assert_attachment_pdf(r, *, expect_disposition: str = "attachment"):
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    ct = r.headers.get("content-type", "")
    assert ct.startswith("application/pdf"), f"content-type={ct}"
    cd = r.headers.get("content-disposition", "")
    assert cd.startswith(expect_disposition + ";"), \
        f"Esperava `{expect_disposition};` no Content-Disposition, got: {cd}"
    body = r.content
    assert body.startswith(b"%PDF-"), "PDF magic bytes faltando"


def test_boletim_returns_attachment(auth):
    r = auth.get(f"{BASE_URL}/api/documents/boletim/{STU_FELIPE}",
                 params={"academic_year": YEAR}, timeout=60)
    _assert_attachment_pdf(r)


def test_ficha_individual_returns_attachment(auth):
    r = auth.get(f"{BASE_URL}/api/documents/ficha-individual/{STU_FELIPE}",
                 params={"academic_year": YEAR}, timeout=60)
    _assert_attachment_pdf(r)


def test_ficha_individual_dependency_returns_attachment(auth):
    r = auth.get(
        f"{BASE_URL}/api/documents/ficha-individual-dependency/{STU_HEITOR}",
        params={"target_class_id": CLASS_V1, "academic_year": YEAR},
        timeout=60,
    )
    _assert_attachment_pdf(r)


def test_declaracao_matricula_returns_attachment(auth):
    r = auth.get(f"{BASE_URL}/api/documents/declaracao-matricula/{STU_FELIPE}",
                 params={"academic_year": YEAR}, timeout=30)
    _assert_attachment_pdf(r)


def test_declaracao_frequencia_returns_attachment(auth):
    r = auth.get(f"{BASE_URL}/api/documents/declaracao-frequencia/{STU_FELIPE}",
                 params={"academic_year": YEAR}, timeout=30)
    _assert_attachment_pdf(r)


def test_declaracao_transferencia_returns_attachment(auth):
    """Pode dar 400 se o aluno não foi transferido — nesse caso, skipa."""
    r = auth.get(f"{BASE_URL}/api/documents/declaracao-transferencia/{STU_FELIPE}",
                 params={"academic_year": YEAR}, timeout=30)
    if r.status_code != 200:
        pytest.skip(
            f"Aluno {STU_FELIPE} não tem transferência ({r.status_code}) — "
            "endpoint não pode ser exercitado neste seed."
        )
    _assert_attachment_pdf(r)


def test_historico_escolar_returns_attachment(auth):
    r = auth.get(f"{BASE_URL}/api/documents/historico-escolar/{STU_FELIPE}",
                 timeout=60)
    # Histórico pode 404 se não houver student_history_records cadastrados
    if r.status_code == 404:
        pytest.skip("Aluno sem histórico cadastrado no seed.")
    _assert_attachment_pdf(r)


# ---------------------------------------------------------------------------
# Endpoints que devem CONTINUAR `inline` (fora do escopo desta refatoração)
# ---------------------------------------------------------------------------

def test_certificado_still_inline_if_exists(auth):
    """Certificado não está na lista — deve continuar inline (se renderizável)."""
    r = auth.get(f"{BASE_URL}/api/documents/certificado/{STU_FELIPE}",
                 params={"academic_year": YEAR}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"Certificado indisponível para {STU_FELIPE} (status={r.status_code}).")
    cd = r.headers.get("content-disposition", "")
    assert cd.startswith("inline;"), f"Certificado deveria continuar inline. got: {cd}"
