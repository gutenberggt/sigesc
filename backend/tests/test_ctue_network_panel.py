"""Fase B CTUE — Painel Gerencial da Rede (/api/ctue/network-panel).

Cobre:
  1. Contrato completo do payload (executive/alerts/priorities/map/comparativos/evolucao).
  2. Troca de perfil (default vs mp vs seguranca) altera métricas agregadas.
  3. Ordenação de alertas por severidade e de priorities por peso (ordem 1..N).
  4. Cache: 2 chamadas consistentes; PUT /api/schools/{id} invalida o cache.
  5. Autenticação obrigatória.
"""
import os
import time

import httpx
import pytest
from dotenv import load_dotenv, dotenv_values

load_dotenv("/app/backend/.env")

BACKEND = (os.environ.get("REACT_APP_BACKEND_URL")
           or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")

ADMIN = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}
SEV_ORDER = {"critico": 0, "alto": 1, "medio": 2}


@pytest.fixture(scope="module")
def auth():
    time.sleep(1.0)
    r = httpx.post(f"{BACKEND}/api/auth/login", json=ADMIN, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"login falhou {r.status_code}: {r.text[:300]}")
    d = r.json()
    tk = d.get("access_token") or d.get("token")
    assert tk, f"sem token: {d}"
    return {"token": tk, "csrf": d.get("csrf_token") or ""}


@pytest.fixture(scope="module")
def h(auth):
    return {"Authorization": f"Bearer {auth['token']}"}


@pytest.fixture(scope="module")
def hw(auth):
    return {"Authorization": f"Bearer {auth['token']}", "X-CSRF-Token": auth["csrf"]}


def _panel(h, profile="default"):
    r = httpx.get(f"{BACKEND}/api/ctue/network-panel", params={"profile": profile},
                  headers=h, timeout=120)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
    return r.json()


# ---------- 1. Contrato ----------
class TestContract:
    def test_top_level_keys(self, h):
        p = _panel(h)
        for k in ["profile", "generated_at", "executive", "alerts", "priorities",
                  "map", "comparativos", "evolucao"]:
            assert k in p, f"chave ausente: {k}"
        assert p["profile"] == "default"
        assert isinstance(p["alerts"], list)
        assert isinstance(p["priorities"], list)
        assert isinstance(p["map"], list)

    def test_executive_keys(self, h):
        e = _panel(h)["executive"]
        for k in ["total", "ativas", "inativas", "conformidade_media", "completude_media",
                  "atualizacao_media_dias", "cadastros_nunca_atualizados",
                  "maturidade_distribuicao", "status_distribuicao"]:
            assert k in e, f"executive.{k} ausente"
        assert isinstance(e["total"], int) and e["total"] > 0
        assert e["ativas"] + e["inativas"] == e["total"]
        assert 0 <= e["conformidade_media"] <= 100
        assert 0 <= e["completude_media"] <= 100
        assert set(e["maturidade_distribuicao"].keys()) == {"1", "2", "3", "4", "5"}
        assert sum(e["maturidade_distribuicao"].values()) == e["total"]
        assert sum(e["status_distribuicao"].values()) == e["total"]

    def test_alerts_shape(self, h):
        for a in _panel(h)["alerts"]:
            for k in ["id", "severidade", "label", "school_id", "school_name"]:
                assert k in a, f"alert.{k} ausente: {a}"
            assert a["severidade"] in SEV_ORDER

    def test_priorities_shape(self, h):
        for pr in _panel(h)["priorities"]:
            for k in ["ordem", "acao", "school_name", "school_id", "peso", "conformidade"]:
                assert k in pr, f"priority.{k} ausente: {pr}"
            assert pr["acao"] and isinstance(pr["acao"], str)

    def test_comparativos_and_map(self, h):
        p = _panel(h)
        c = p["comparativos"]
        assert set(["zona", "distrito", "etapas", "porte"]).issubset(c.keys())
        for dim, rows in c.items():
            assert isinstance(rows, list) and len(rows) > 0, f"comparativo {dim} vazio"
            for row in rows:
                for k in ["grupo", "escolas", "conformidade_media", "completude_media"]:
                    assert k in row, f"{dim} row sem {k}"
        # zona: soma de escolas == total (grupos mutuamente exclusivos)
        assert sum(r["escolas"] for r in c["zona"]) == p["executive"]["total"]
        for pt in p["map"]:
            for k in ["school_id", "name", "lat", "lng", "status", "conformidade", "completude"]:
                assert k in pt
            assert isinstance(pt["lat"], float) and isinstance(pt["lng"], float)

    def test_evolucao_slot(self, h):
        ev = _panel(h)["evolucao"]
        assert ev["disponivel"] is False
        assert "series_previstas" in ev


# ---------- 2. Perfis ----------
class TestProfiles:
    def test_profile_changes_metrics(self, h):
        d = _panel(h, "default")["executive"]
        mp = _panel(h, "mp")["executive"]
        seg = _panel(h, "seguranca")["executive"]
        assert d["total"] == mp["total"] == seg["total"]
        triples = {(d["conformidade_media"], d["completude_media"]),
                   (mp["conformidade_media"], mp["completude_media"]),
                   (seg["conformidade_media"], seg["completude_media"])}
        assert len(triples) > 1, f"perfis não alteram métricas: {triples}"

    def test_profile_echoed(self, h):
        assert _panel(h, "seguranca")["profile"] == "seguranca"


# ---------- 3. Ordenação ----------
class TestOrdering:
    def test_alerts_sorted_by_severity(self, h):
        sev = [SEV_ORDER[a["severidade"]] for a in _panel(h)["alerts"]]
        assert sev == sorted(sev), "alertas não ordenados por severidade"

    def test_priorities_sorted_and_sequential(self, h):
        prs = _panel(h)["priorities"]
        assert [p["ordem"] for p in prs] == list(range(1, len(prs) + 1))
        pesos = [p["peso"] for p in prs]
        assert pesos == sorted(pesos, reverse=True), "priorities não ordenadas por peso"


# ---------- 4. Cache + invalidação ----------
class TestCacheInvalidation:
    def test_two_calls_consistent(self, h):
        a, b = _panel(h), _panel(h)
        assert a["executive"] == b["executive"]
        assert len(a["alerts"]) == len(b["alerts"])

    def test_school_update_invalidates_cache(self, h, hw):
        before = _panel(h, "seguranca")["executive"]

        r = httpx.get(f"{BACKEND}/api/schools", headers=h, timeout=60)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        schools = body if isinstance(body, list) else body.get("schools", [])
        assert schools, "nenhuma escola disponível"
        # escolha uma escola sem os campos de segurança preenchidos
        target = next((s for s in schools if not s.get("qtd_extintores")), schools[0])
        sid = target["id"]

        fields = ["qtd_extintores", "saidas_emergencia", "brigada_incendio",
                  "plano_evacuacao", "possui_cercamento", "qtd_cameras"]
        original = {k: target.get(k) for k in fields}
        payload = {"qtd_extintores": 6, "saidas_emergencia": 3, "brigada_incendio": True,
                   "plano_evacuacao": True, "possui_cercamento": True, "qtd_cameras": 4}
        up = httpx.put(f"{BACKEND}/api/schools/{sid}", json=payload, headers=hw, timeout=60)
        assert up.status_code == 200, f"PUT falhou {up.status_code}: {up.text[:400]}"

        try:
            persisted = httpx.get(f"{BACKEND}/api/schools/{sid}", headers=h, timeout=60).json()
            assert persisted.get("qtd_extintores") == 6, (
                f"PUT não persistiu qtd_extintores: {persisted.get('qtd_extintores')}")
            after = _panel(h, "seguranca")["executive"]
            assert after != before, (
                f"painel não refletiu edição (cache não invalidado). before={before} after={after}")
        finally:
            httpx.put(f"{BACKEND}/api/schools/{sid}", json=original, headers=hw, timeout=60)


# ---------- 5. Auth ----------
def test_requires_auth():
    r = httpx.get(f"{BACKEND}/api/ctue/network-panel", timeout=30)
    assert r.status_code in (401, 403), f"esperado 401/403, veio {r.status_code}"
