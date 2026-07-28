"""Fase C CTUE — Dossiê Institucional (PDF).

Cobre:
  1. GET /api/ctue/schools/{id}/dossie → 200, Content-Type application/pdf, assinatura %PDF.
  2. Seções obrigatórias presentes no texto extraído (pdfplumber).
  3. Troca de perfil (default vs mp) altera percentuais no quadro-resumo.
  4. Auth obrigatória (401 sem token) + 404 escola inexistente + escopo de tenant.
  5. Ausência de QR/assinatura/histórico e uso de 'Não informado'.
"""
import io
import os
import re
import time

import httpx
import pytest
from dotenv import dotenv_values, load_dotenv

load_dotenv("/app/backend/.env")

BACKEND = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else \
    dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")

ADMIN = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}


@pytest.fixture(scope="module")
def h():
    time.sleep(1.0)
    r = httpx.post(f"{BACKEND}/api/auth/login", json=ADMIN, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login falhou {r.status_code}: {r.text[:300]}")
    tk = r.json().get("access_token") or r.json().get("token")
    assert tk, "sem token"
    return {"Authorization": f"Bearer {tk}"}


@pytest.fixture(scope="module")
def school_id(h):
    r = httpx.get(f"{BACKEND}/api/ctue/conformity-overview", params={"profile": "default"}, headers=h, timeout=60)
    assert r.status_code == 200, r.text[:300]
    schools = r.json()["schools"]
    assert schools, "nenhuma escola no escopo"
    return schools[0]["school_id"]


def _get_pdf(h, sid, profile="default"):
    r = httpx.get(f"{BACKEND}/api/ctue/schools/{sid}/dossie", params={"profile": profile}, headers=h, timeout=120)
    return r


def _text(pdf_bytes):
    import pdfplumber
    out = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for p in pdf.pages:
            out.append(p.extract_text() or "")
    return "\n".join(out), len(out)


# ---------- 1. Contrato HTTP ----------
def test_dossie_default_returns_valid_pdf(h, school_id):
    r = _get_pdf(h, school_id, "default")
    assert r.status_code == 200, r.text[:400]
    assert "application/pdf" in r.headers.get("content-type", "")
    assert r.content[:4] == b"%PDF", f"não é PDF: {r.content[:20]!r}"
    assert len(r.content) > 5000
    cd = r.headers.get("content-disposition", "")
    assert "dossie_institucional" in cd and cd.endswith('.pdf"'), cd


def test_dossie_profile_mp_returns_valid_pdf(h, school_id):
    r = _get_pdf(h, school_id, "mp")
    assert r.status_code == 200, r.text[:400]
    assert "application/pdf" in r.headers.get("content-type", "")
    assert r.content[:4] == b"%PDF"


# ---------- 2. Seções obrigatórias ----------
def test_dossie_contains_all_required_sections(h, school_id):
    r = _get_pdf(h, school_id, "default")
    assert r.status_code == 200
    text, pages = _text(r.content)
    assert pages >= 1
    required = [
        "DOSSIÊ INSTITUCIONAL",
        "Identificação da Unidade",
        "Dados Administrativos e Gestão",
        "Quadro-resumo de Conformidade e Completude",
        "Infraestrutura Física e Ambientes",
        "Acessibilidade",
        "Segurança",
        "Água, Saneamento e Energia",
        "Equipamentos",
        "Resumo Institucional",
        "Conformidade Geral",
        "Completude Geral",
        "Última Atualização",
        "Nível de Maturidade",
    ]
    missing = [s for s in required if s not in text]
    assert not missing, f"seções ausentes: {missing}"


def test_dossie_has_gestor_and_summary_table_headers(h, school_id):
    r = _get_pdf(h, school_id, "default")
    text, _ = _text(r.content)
    for k in ["Gestor(a) Principal", "Código INEP", "Seção", "Conformidade", "Completude", "Itens", "Situação"]:
        assert k in text, f"campo/coluna ausente: {k}"


def test_dossie_no_out_of_scope_content(h, school_id):
    """Sem QR Code, assinatura digital, histórico ou anexos."""
    r = _get_pdf(h, school_id, "default")
    text, _ = _text(r.content)
    low = text.lower()
    for forbidden in ["qr code", "qrcode", "assinatura", "assinado", "histórico de alterações", "anexo"]:
        assert forbidden not in low, f"conteúdo fora de escopo encontrado: {forbidden}"


def test_dossie_uses_nao_informado_for_missing_values(h, school_id):
    r = _get_pdf(h, school_id, "default")
    text, _ = _text(r.content)
    # Deve haver ao menos um 'Não informado' (dados incompletos na base) e nenhuma célula 'None'
    assert "Não informado" in text
    assert not re.search(r"\bNone\b", text), "valor 'None' cru vazando no PDF"


# ---------- 3. Perfil altera o conteúdo (vem do CTUEConformityService) ----------
def test_profile_changes_conformity_numbers(h, school_id):
    api_def = httpx.get(f"{BACKEND}/api/ctue/schools/{school_id}/conformity",
                        params={"profile": "default"}, headers=h, timeout=60).json()
    api_mp = httpx.get(f"{BACKEND}/api/ctue/schools/{school_id}/conformity",
                       params={"profile": "mp"}, headers=h, timeout=60).json()

    t_def, _ = _text(_get_pdf(h, school_id, "default").content)
    t_mp, _ = _text(_get_pdf(h, school_id, "mp").content)

    # o PDF reflete exatamente o valor do serviço (SSoT)
    assert f"{api_def['conformidade_geral']}%" in t_def
    assert f"{api_mp['conformidade_geral']}%" in t_mp
    # perfil impresso no resumo
    assert "default" in t_def
    assert "mp" in t_mp
    if api_def["conformidade_geral"] != api_mp["conformidade_geral"]:
        assert t_def != t_mp, "PDFs idênticos apesar de conformidade diferente"
    else:
        pytest.skip(f"perfis produzem a mesma conformidade geral ({api_def['conformidade_geral']}%) nesta escola")


def test_pdf_section_rows_match_service(h, school_id):
    api = httpx.get(f"{BACKEND}/api/ctue/schools/{school_id}/conformity",
                    params={"profile": "default"}, headers=h, timeout=60).json()
    text, _ = _text(_get_pdf(h, school_id, "default").content)
    for s in api["sections"]:
        assert s["label"] in text, f"seção do SSoT ausente no PDF: {s['label']}"
    mat = api.get("maturidade", {})
    assert f"Nível {mat.get('nivel')}" in text


# ---------- 4. Auth / escopo ----------
def test_dossie_requires_auth(school_id):
    r = httpx.get(f"{BACKEND}/api/ctue/schools/{school_id}/dossie", timeout=30)
    assert r.status_code in (401, 403), f"esperado 401/403, obtido {r.status_code}"


def test_dossie_invalid_token(school_id):
    r = httpx.get(f"{BACKEND}/api/ctue/schools/{school_id}/dossie",
                  headers={"Authorization": "Bearer invalido.xyz"}, timeout=30)
    assert r.status_code in (401, 403)


def test_dossie_school_not_found(h):
    r = httpx.get(f"{BACKEND}/api/ctue/schools/nao-existe-000/dossie", headers=h, timeout=30)
    assert r.status_code in (403, 404), f"obtido {r.status_code}: {r.text[:200]}"


def test_dossie_invalid_profile_does_not_500(h, school_id):
    r = _get_pdf(h, school_id, "perfil_inexistente")
    assert r.status_code in (200, 400, 422), f"obtido {r.status_code}: {r.text[:200]}"
