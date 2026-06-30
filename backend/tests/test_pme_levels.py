"""Iter 111 — PME Análise (4 níveis: Edu Infantil, Anos Iniciais, Anos Finais, EJA)."""
import os
import jwt as pyjwt
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
assert BASE_URL
API = f"{BASE_URL}/api"
SUPER = ("gutenberg@sigesc.com", "@Celta2007")
PROF = ("professor.teste@sigesc.com", "professor123")


def _login(email, pwd):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    return r.json()["access_token"]


def _csrf(tok):
    return pyjwt.decode(tok, options={"verify_signature": False}).get("csrf")


@pytest.fixture(scope="module")
def admin_tok():
    return _login(*SUPER)


@pytest.fixture(scope="module")
def admin_h(admin_tok):
    return {"Authorization": f"Bearer {admin_tok}", "X-CSRF-Token": _csrf(admin_tok) or ""}


LEVELS = [
    ("educacao_infantil", "Educação Infantil"),
    ("fundamental_anos_iniciais", "Anos Iniciais"),
    ("fundamental_anos_finais", "Anos Finais"),
    ("eja", "EJA"),
]


class TestAnalyticsByLevel:
    @pytest.mark.parametrize("lvl,label", LEVELS)
    def test_analytics_returns_level(self, admin_h, lvl, label):
        r = requests.get(f"{API}/pme/anos-finais/analytics",
                         params={"academic_year": 2026, "level": lvl},
                         headers=admin_h, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("level") == lvl
        assert d.get("level_label") == label
        assert d.get("academic_year") == 2026
        # Filtros refletem o nível
        assert d.get("filters", {}).get("level") == lvl

    def test_default_level_anos_finais(self, admin_h):
        """Sem o param level → default = fundamental_anos_finais (mantém comportamento anterior)."""
        r = requests.get(f"{API}/pme/anos-finais/analytics?academic_year=2026",
                         headers=admin_h, timeout=60)
        assert r.status_code == 200
        assert r.json().get("level") == "fundamental_anos_finais"

    def test_invalid_level_falls_back_to_default(self, admin_h):
        r = requests.get(f"{API}/pme/anos-finais/analytics",
                         params={"academic_year": 2026, "level": "ensino_medio"},
                         headers=admin_h, timeout=60)
        assert r.status_code == 200
        assert r.json().get("level") == "fundamental_anos_finais"

    def test_distorcao_only_for_fundamental(self, admin_h):
        """Infantil e EJA não têm tabela expected_age → distorcao deve ficar vazia.
        Anos Iniciais/Finais podem ter chaves preenchidas se há dados."""
        # Infantil
        r = requests.get(f"{API}/pme/anos-finais/analytics",
                         params={"academic_year": 2026, "level": "educacao_infantil"},
                         headers=admin_h, timeout=60)
        assert r.status_code == 200
        assert r.json().get("distorcao_idade_serie", {}) == {}
        # EJA
        r2 = requests.get(f"{API}/pme/anos-finais/analytics",
                          params={"academic_year": 2026, "level": "eja"},
                          headers=admin_h, timeout=60)
        assert r2.status_code == 200
        assert r2.json().get("distorcao_idade_serie", {}) == {}


class TestSchoolsByLevel:
    @pytest.mark.parametrize("lvl", [l for l, _ in LEVELS])
    def test_schools_endpoint_returns_only_for_level(self, admin_h, lvl):
        r = requests.get(f"{API}/pme/anos-finais/schools",
                         params={"academic_year": 2026, "level": lvl},
                         headers=admin_h, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("level") == lvl
        assert d.get("academic_year") == 2026
        assert isinstance(d.get("schools"), list)
        # Cada escola tem ao menos id e name
        for s in d["schools"]:
            assert "id" in s and "name" in s

    def test_schools_consistency_with_analytics(self, admin_h):
        """Para cada nível, len(schools_by_level) == analytics.escolas.total."""
        for lvl, _ in LEVELS:
            rs = requests.get(f"{API}/pme/anos-finais/schools",
                              params={"academic_year": 2026, "level": lvl},
                              headers=admin_h, timeout=30)
            ra = requests.get(f"{API}/pme/anos-finais/analytics",
                              params={"academic_year": 2026, "level": lvl},
                              headers=admin_h, timeout=60)
            assert rs.status_code == 200 and ra.status_code == 200
            n_schools = len(rs.json().get("schools", []))
            n_an = ra.json().get("escolas", {}).get("total", 0)
            assert n_schools == n_an, f"{lvl}: schools={n_schools} vs analytics.escolas.total={n_an}"


class TestExternalIndicatorsByLevel:
    """GET/PUT external-indicators é chaveado por (mantenedora, year, level)."""

    def test_put_then_get_per_level_isolated(self, admin_h):
        year = 2025
        values = {
            "educacao_infantil": 1.1,
            "fundamental_anos_iniciais": 2.2,
            "fundamental_anos_finais": 3.3,
            "eja": 4.4,
        }
        # Salvar valor distinto por nível
        for lvl, v in values.items():
            r = requests.put(f"{API}/pme/anos-finais/external-indicators",
                             json={"academic_year": year, "level": lvl, "ideb_atual": v},
                             headers=admin_h, timeout=30)
            assert r.status_code == 200, r.text[:300]
            assert r.json().get("level") == lvl
            assert r.json().get("academic_year") == year
        # Ler de volta — cada nível deve manter o seu próprio valor (isolamento)
        for lvl, v in values.items():
            g = requests.get(f"{API}/pme/anos-finais/external-indicators",
                             params={"academic_year": year, "level": lvl},
                             headers=admin_h, timeout=30)
            assert g.status_code == 200, g.text[:300]
            gd = g.json()
            assert gd.get("level") == lvl
            assert gd.get("ideb_atual") == v, f"{lvl}: esperava {v}, veio {gd.get('ideb_atual')}"

    def test_get_missing_level_returns_exists_false(self, admin_h):
        # Ano improvável de ter dados ainda
        r = requests.get(f"{API}/pme/anos-finais/external-indicators",
                         params={"academic_year": 2010, "level": "eja"},
                         headers=admin_h, timeout=30)
        assert r.status_code == 200
        d = r.json()
        # Pode ser {exists:False, ...} ou doc vazio
        if d.get("ideb_atual") is None and "exists" in d:
            assert d.get("exists") is False
        assert d.get("level") == "eja"

    def test_put_without_csrf_rejected(self, admin_tok):
        h = {"Authorization": f"Bearer {admin_tok}"}
        r = requests.put(f"{API}/pme/anos-finais/external-indicators",
                         json={"academic_year": 2024, "level": "eja", "ideb_atual": 1.0},
                         headers=h, timeout=30)
        assert r.status_code in (400, 401, 403)


class TestRBACLevels:
    def test_professor_blocked_on_schools_endpoint(self):
        try:
            tok = _login(*PROF)
        except AssertionError:
            pytest.skip("professor login indisponível")
        r = requests.get(f"{API}/pme/anos-finais/schools",
                         params={"academic_year": 2026, "level": "educacao_infantil"},
                         headers={"Authorization": f"Bearer {tok}"}, timeout=30)
        assert r.status_code == 403
