"""CTUE — Sprint de conclusão: seções informativas (Obras, Documentação, Observações Técnicas).

Cobre:
  1. PUT /api/schools/{id} aceita e persiste obras[], documentos[], observacoes_tecnicas[].
  2. GET /api/schools e GET /api/schools/{id} retornam os arrays.
  3. Dossiê (PDF) contém seções 9/10/11 com os registros + linha 'Documentos pendentes:'.
  4. Conformidade (conformidade_geral/completude_geral/maturidade) INALTERADA pelas 3 seções.
  5. Label 'Localização & Georreferenciamento' vem do backend.
  6. Cleanup: restaura os arrays originais da escola.
"""
import io
import os
import time

import httpx
import pytest
from dotenv import dotenv_values, load_dotenv

load_dotenv("/app/backend/.env")

BACKEND = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else \
    dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")

ADMIN = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}

OBRA = {
    "tipo": "Reforma",
    "situacao": "Em execução",
    "data_inicio": "2026-02-10",
    "previsao_conclusao": "2026-08-30",
    "descricao": "TEST_reforma do bloco de salas",
    "observacoes": "TEST_obs obra",
}
DOC = {
    "categoria": "AVCB (Corpo de Bombeiros)",
    "filename": "TEST_avcb.pdf",
    "url": "/api/uploads/TEST_avcb.pdf",
    "data_documento": "2026-01-15",
    "observacoes": "TEST_obs doc",
}
OBS = {
    "tipo": "Relatório de Vistoria",
    "data": "2026-03-01",
    "responsavel": "TEST_Engenheiro Responsavel",
    "texto": "TEST_vistoria tecnica realizada sem pendencias estruturais",
}


@pytest.fixture(scope="module")
def h():
    time.sleep(1.0)
    r = httpx.post(f"{BACKEND}/api/auth/login", json=ADMIN, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login falhou {r.status_code}: {r.text[:300]}")
    body = r.json()
    tk = body.get("access_token") or body.get("token")
    assert tk, "sem token"
    hdr = {"Authorization": f"Bearer {tk}"}
    if body.get("csrf_token"):
        hdr["X-CSRF-Token"] = body["csrf_token"]
    return hdr


@pytest.fixture(scope="module")
def school(h):
    r = httpx.get(f"{BACKEND}/api/schools", headers=h, params={"limit": 5}, timeout=60)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    items = data if isinstance(data, list) else data.get("schools") or data.get("items")
    assert items, f"nenhuma escola: {str(data)[:300]}"
    return items[0]


@pytest.fixture(scope="module", autouse=True)
def restore(h, school):
    """Restaura os 3 arrays ao estado original no fim do módulo."""
    original = {
        "obras": school.get("obras") or [],
        "documentos": school.get("documentos") or [],
        "observacoes_tecnicas": school.get("observacoes_tecnicas") or [],
    }
    yield
    httpx.put(f"{BACKEND}/api/schools/{school['id']}", headers=h, json=original, timeout=60)


def _conformity(h, sid):
    r = httpx.get(f"{BACKEND}/api/ctue/schools/{sid}/conformity", headers=h, timeout=60)
    assert r.status_code == 200, r.text[:300]
    return r.json()


def _pdf_text(h, sid):
    import pdfplumber
    r = httpx.get(f"{BACKEND}/api/ctue/schools/{sid}/dossie", headers=h, timeout=120)
    assert r.status_code == 200, r.text[:300]
    assert r.content[:4] == b"%PDF"
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


class TestSecoesInformativas:
    """PUT/GET dos 3 arrays + dossiê + conformidade inalterada."""

    def test_01_baseline_conformity(self, h, school, request):
        c = _conformity(h, school["id"])
        request.config.cache.set("ctue_baseline", {
            "conformidade_geral": c.get("conformidade_geral"),
            "completude_geral": c.get("completude_geral"),
            "maturidade": c.get("maturidade") or c.get("nivel_maturidade"),
        })
        assert c.get("conformidade_geral") is not None

    def test_02_put_persiste_arrays(self, h, school):
        sid = school["id"]
        payload = {"obras": [OBRA], "documentos": [DOC], "observacoes_tecnicas": [OBS]}
        r = httpx.put(f"{BACKEND}/api/schools/{sid}", headers=h, json=payload, timeout=60)
        assert r.status_code == 200, f"PUT falhou {r.status_code}: {r.text[:400]}"
        body = r.json()
        assert len(body.get("obras") or []) == 1
        assert body["obras"][0]["tipo"] == "Reforma"
        assert body["documentos"][0]["categoria"] == DOC["categoria"]
        assert body["observacoes_tecnicas"][0]["responsavel"] == OBS["responsavel"]

        # GET individual confirma persistência
        g = httpx.get(f"{BACKEND}/api/schools/{sid}", headers=h, timeout=60)
        assert g.status_code == 200
        d = g.json()
        assert d["obras"][0]["descricao"] == OBRA["descricao"]
        assert d["documentos"][0]["filename"] == DOC["filename"]
        assert d["observacoes_tecnicas"][0]["texto"] == OBS["texto"]
        assert "_id" not in d

    def test_03_list_schools_retorna_arrays(self, h, school):
        r = httpx.get(f"{BACKEND}/api/schools", headers=h, params={"limit": 100}, timeout=60)
        assert r.status_code == 200
        data = r.json()
        items = data if isinstance(data, list) else data.get("schools") or data.get("items")
        target = next((s for s in items if s["id"] == school["id"]), None)
        assert target is not None
        assert len(target.get("obras") or []) == 1, f"obras não retornadas em GET /schools: {target.get('obras')}"
        assert len(target.get("documentos") or []) == 1
        assert len(target.get("observacoes_tecnicas") or []) == 1

    def test_04_conformidade_inalterada(self, h, school, request):
        base = request.config.cache.get("ctue_baseline", None)
        assert base, "baseline ausente"
        c = _conformity(h, school["id"])
        assert c["conformidade_geral"] == base["conformidade_geral"], "conformidade_geral mudou!"
        assert c["completude_geral"] == base["completude_geral"], "completude_geral mudou!"
        assert (c.get("maturidade") or c.get("nivel_maturidade")) == base["maturidade"], "maturidade mudou!"

    def test_05_secoes_permanecem_nao_avaliadas(self, h, school):
        c = _conformity(h, school["id"])
        secs = c.get("secoes") or c.get("sections") or []
        by_key = {s.get("key") or s.get("secao"): s for s in secs}
        for key in ("obras", "documentacao", "observacoes_tecnicas"):
            assert key in by_key, f"seção {key} ausente: {list(by_key)}"
            st = by_key[key].get("status") or by_key[key].get("situacao")
            assert st == "nao_avaliado", f"{key} status={st} (esperado nao_avaliado)"

    def test_06_label_localizacao_georreferenciamento(self, h, school):
        c = _conformity(h, school["id"])
        secs = c.get("secoes") or c.get("sections") or []
        loc = next((s for s in secs if (s.get("key") or s.get("secao")) == "localizacao"), None)
        assert loc is not None, "seção localizacao ausente"
        assert loc.get("label") == "Localização & Georreferenciamento", loc.get("label")

    def test_07_dossie_secoes_9_10_11(self, h, school):
        txt = _pdf_text(h, school["id"])
        assert "9. Obras e Intervenções" in txt
        assert "10. Documentação" in txt
        assert "11. Observações Técnicas" in txt
        # registros cadastrados aparecem
        assert "Reforma" in txt
        assert "AVCB" in txt
        assert "Relatório de Vistoria" in txt or "Relatorio de Vistoria" in txt
        assert "Documentos pendentes:" in txt
        assert "TEST_Engenheiro Responsavel" in txt or "TEST_vistoria" in txt.replace("\n", "")

    def test_08_remocao_persiste(self, h, school):
        sid = school["id"]
        r = httpx.put(f"{BACKEND}/api/schools/{sid}", headers=h,
                      json={"obras": [], "documentos": [], "observacoes_tecnicas": []}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        g = httpx.get(f"{BACKEND}/api/schools/{sid}", headers=h, timeout=60).json()
        assert (g.get("obras") or []) == []
        assert (g.get("documentos") or []) == []
        assert (g.get("observacoes_tecnicas") or []) == []

    def test_09_put_sem_token_401(self, school):
        r = httpx.put(f"{BACKEND}/api/schools/{school['id']}", json={"obras": []}, timeout=30)
        assert r.status_code in (401, 403), r.status_code
