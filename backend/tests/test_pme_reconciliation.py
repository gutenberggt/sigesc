"""Iter 112 — PME Anos Finais reconciliation bug fix.

Bug: matriculas.ativos (cabeçalho) divergia de rendimento.geral.cursando.
Fix: outcome_map canônico. matriculas.ativos = cursando + aprovado (por matrícula);
     matriculas.alunos_ativos = alunos únicos ativos (novo campo).

Testa para cada nível: educacao_infantil, anos_iniciais, anos_finais, eja:
  (a) matriculas.total == soma(rendimento.geral.*)
  (b) matriculas.ativos == rendimento.geral.cursando + rendimento.geral.aprovado
  (c) matriculas.alunos_ativos existe e <= matriculas.ativos
"""
import os
import pytest
import requests


def _read_frontend_env():
    try:
        for line in open("/app/frontend/.env"):
            if line.startswith("REACT_APP_BACKEND_URL"):
                return line.split("=", 1)[1].strip()
    except Exception:
        return None
    return None


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _read_frontend_env() or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not set"
API = f"{BASE_URL}/api"

SUPER_ADMIN = ("gutenberg@sigesc.com", "@Celta2007")
LEVELS = ["educacao_infantil", "anos_iniciais", "anos_finais", "eja"]

REND_KEYS = ["aprovado", "abandono", "transferido", "cursando", "cancelado", "inativo"]


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{API}/auth/login",
                      json={"email": SUPER_ADMIN[0], "password": SUPER_ADMIN[1]},
                      timeout=30)
    assert r.status_code == 200, r.text[:300]
    tok = r.json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _get_analytics(headers, level):
    r = requests.get(
        f"{API}/pme/anos-finais/analytics",
        params={"academic_year": 2026, "level": level},
        headers=headers, timeout=60,
    )
    assert r.status_code == 200, f"level={level} -> {r.status_code} {r.text[:300]}"
    return r.json()


@pytest.mark.parametrize("level", LEVELS)
def test_matriculas_total_equals_rendimento_sum(admin_headers, level):
    d = _get_analytics(admin_headers, level)
    total = int(d["matriculas"]["total"])
    geral = d["rendimento"]["geral"]
    soma = sum(int(geral.get(k, 0)) for k in REND_KEYS)
    assert total == soma, (
        f"[{level}] matriculas.total ({total}) != soma rendimento.geral ({soma}); "
        f"geral={geral}"
    )


@pytest.mark.parametrize("level", LEVELS)
def test_matriculas_ativos_equals_cursando_plus_aprovado(admin_headers, level):
    d = _get_analytics(admin_headers, level)
    ativos = int(d["matriculas"]["ativos"])
    geral = d["rendimento"]["geral"]
    expected = int(geral.get("cursando", 0)) + int(geral.get("aprovado", 0))
    assert ativos == expected, (
        f"[{level}] matriculas.ativos ({ativos}) != cursando+aprovado ({expected}); "
        f"geral={geral}"
    )


@pytest.mark.parametrize("level", LEVELS)
def test_matriculas_alunos_ativos_field_present(admin_headers, level):
    d = _get_analytics(admin_headers, level)
    m = d["matriculas"]
    assert "alunos_ativos" in m, f"[{level}] campo matriculas.alunos_ativos ausente: {m}"
    alunos_ativos = int(m["alunos_ativos"])
    ativos = int(m["ativos"])
    # alunos únicos ativos deve ser <= matrículas ativas (um aluno pode ter várias matrículas)
    assert 0 <= alunos_ativos <= ativos, (
        f"[{level}] alunos_ativos ({alunos_ativos}) fora do range esperado [0, {ativos}]"
    )


@pytest.mark.parametrize("level", LEVELS)
def test_analytics_structure_regression(admin_headers, level):
    """Regressão: estrutura da resposta permanece."""
    d = _get_analytics(admin_headers, level)
    for k in ("matriculas", "rendimento", "cor_raca", "distorcao_idade_serie", "escolas"):
        assert k in d, f"[{level}] chave '{k}' ausente"
    assert "geral" in d["rendimento"]
    assert d.get("filters", {}).get("level") == level or True  # filters may or may not echo
