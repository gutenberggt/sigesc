"""Iter 108 — PME Anos Finais (analytics + external indicators + RBAC)."""
import os
import jwt as pyjwt
import pytest
import requests

def _read_frontend_env():
    path = "/app/frontend/.env"
    try:
        for line in open(path):
            if line.startswith("REACT_APP_BACKEND_URL"):
                return line.split("=", 1)[1].strip()
    except Exception:
        return None
    return None


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _read_frontend_env() or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not set"
API = f"{BASE_URL}/api"

SUPER_ADMIN = ("gutenberg@sigesc.com", "@Celta2007")
PROFESSOR = ("professor.teste@sigesc.com", "professor123")


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


def _csrf(token):
    # JWT claim 'csrf' — used for PUT/POST endpoints with X-CSRF-Token header
    payload = pyjwt.decode(token, options={"verify_signature": False})
    return payload.get("csrf")


@pytest.fixture(scope="module")
def admin_token():
    return _login(*SUPER_ADMIN)


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "X-CSRF-Token": _csrf(admin_token) or ""}


@pytest.fixture(scope="module")
def professor_token():
    try:
        return _login(*PROFESSOR)
    except AssertionError:
        pytest.skip("professor.teste login failed in this env")


# -------- Analytics --------
class TestAnalytics:
    def test_analytics_2026_super_admin(self, admin_headers):
        r = requests.get(f"{API}/pme/anos-finais/analytics?academic_year=2026", headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for k in ["academic_year", "escolas", "matriculas", "multisseriadas", "deficiencia",
                  "cor_raca", "rendimento", "distorcao_idade_serie", "evasao",
                  "socioeconomico", "docentes"]:
            assert k in d, f"missing key {k}"
        assert d["academic_year"] == 2026
        assert d["matriculas"]["total"] >= 1
        assert d["escolas"]["total"] >= 1
        # rendimento sub-structure
        for sub in ["geral", "por_serie", "por_zona", "por_cor_raca"]:
            assert sub in d["rendimento"]

    def test_analytics_2024_empty_ok(self, admin_headers):
        # 2024/2025 may be empty — must NOT error
        r = requests.get(f"{API}/pme/anos-finais/analytics?academic_year=2024", headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.json().get("academic_year") == 2024

    def test_analytics_zona_filter(self, admin_headers):
        r = requests.get(f"{API}/pme/anos-finais/analytics?academic_year=2026&zona=urbana",
                         headers=admin_headers, timeout=60)
        assert r.status_code == 200
        d = r.json()
        assert d["filters"]["zona"] == "urbana"

    def test_analytics_default_year(self, admin_headers):
        # no academic_year -> uses current
        r = requests.get(f"{API}/pme/anos-finais/analytics", headers=admin_headers, timeout=60)
        assert r.status_code == 200

    # ---- Regressão BUG iter109: cor_raca deve refletir color_race (não tudo 'nao_declarado') ----
    def test_analytics_cor_raca_uses_color_race_field(self, admin_headers):
        """BUG: PME lia 'cor_raca' (vazio). Fix: agora lê 'color_race' (fallback cor_raca).
        Com seed Maria=branca, Ana=parda, Joao=preta, esperamos múltiplas chaves preenchidas
        e NÃO tudo concentrado em 'nao_declarado' / 'nao_informada'."""
        r = requests.get(f"{API}/pme/anos-finais/analytics?academic_year=2026",
                         headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        cor = d.get("cor_raca") or {}
        assert isinstance(cor, dict) and cor, f"cor_raca vazio: {cor}"
        total = sum(int(v) for v in cor.values() if isinstance(v, (int, float)))
        nao_decl = int(cor.get("nao_declarado", 0)) + int(cor.get("nao_informada", 0))
        # Deve existir pelo menos uma chave real (branca/parda/preta/amarela/indigena)
        keys_reais = {"branca", "parda", "preta", "amarela", "indigena"} & set(cor.keys())
        assert keys_reais, f"esperava cor/raça real declarada, veio: {cor}"
        # Não pode ser TUDO 'não declarado'
        assert nao_decl < total, f"cor_raca está tudo como não declarado: {cor}"
        # Conferir as 3 chaves semeadas (branca/parda/preta)
        for k in ("branca", "parda", "preta"):
            assert int(cor.get(k, 0)) >= 1, f"esperava ao menos 1 em '{k}', veio {cor}"

    def test_pme_cor_raca_matches_students_race_counts(self, admin_headers):
        """Consistência entre PME (color_race) e GET /students race_counts (também color_race)."""
        # PME analytics
        rp = requests.get(f"{API}/pme/anos-finais/analytics?academic_year=2026",
                          headers=admin_headers, timeout=60)
        assert rp.status_code == 200
        pme_cor = rp.json().get("cor_raca") or {}
        # Students endpoint (race_counts)
        rs = requests.get(f"{API}/students?limit=1", headers=admin_headers, timeout=30)
        assert rs.status_code == 200, rs.text[:200]
        body = rs.json()
        rc = (body.get("race_counts") or body.get("raceCounts") or {})
        # Para as chaves semeadas, race_counts deve refletir pelo menos os mesmos alunos
        for k in ("branca", "parda", "preta"):
            assert int(rc.get(k, 0)) >= int(pme_cor.get(k, 0)), \
                f"inconsistência em '{k}': pme={pme_cor.get(k)} students={rc.get(k)}"

    def test_rendimento_por_cor_raca_keys(self, admin_headers):
        """rendimento.por_cor_raca deve usar chaves reais de color_race (ao menos 1 não-'nao_declarado')."""
        r = requests.get(f"{API}/pme/anos-finais/analytics?academic_year=2026",
                         headers=admin_headers, timeout=60)
        assert r.status_code == 200
        rend = r.json().get("rendimento", {}).get("por_cor_raca", {})
        assert isinstance(rend, dict)
        if rend:
            keys = set(rend.keys())
            keys_reais = {"branca", "parda", "preta", "amarela", "indigena"} & keys
            assert keys_reais, f"rend.por_cor_raca sem chave real: {keys}"


# -------- External Indicators --------
class TestExternalIndicators:
    def test_get_external_2026(self, admin_headers):
        r = requests.get(f"{API}/pme/anos-finais/external-indicators?academic_year=2026",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        # Either has data or {exists: False}
        assert d.get("academic_year") == 2026 or "academic_year" not in d
        # Per problem statement, IDEB 4.2 / meta 5.0 already saved for 2026
        if d.get("ideb_atual") is not None:
            assert isinstance(d.get("ideb_atual"), (int, float))

    def test_put_external_creates_2025_and_persists(self, admin_headers):
        payload = {
            "academic_year": 2025,
            "ideb_atual": 3.9,
            "ideb_meta": 4.7,
            "pop_11_14_pct": 91.0,
            "evolucao": [{"year": 2021, "ideb": 3.5, "lp": 240, "mat": 232}],
            "bncc_descritores": [{"descritor": "TEST_D12", "nivel_defasagem_pct": 35}],
        }
        r = requests.put(f"{API}/pme/anos-finais/external-indicators",
                         json=payload, headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data.get("success") is True
        assert data.get("academic_year") == 2025

        # GET back & verify persistence
        g = requests.get(f"{API}/pme/anos-finais/external-indicators?academic_year=2025",
                         headers=admin_headers, timeout=30)
        assert g.status_code == 200
        gd = g.json()
        assert gd.get("ideb_atual") == 3.9
        assert gd.get("ideb_meta") == 4.7
        assert gd.get("pop_11_14_pct") == 91.0
        assert isinstance(gd.get("evolucao"), list) and len(gd["evolucao"]) >= 1
        assert isinstance(gd.get("bncc_descritores"), list) and len(gd["bncc_descritores"]) >= 1

    def test_put_without_csrf_rejected(self, admin_token):
        # only Bearer, no X-CSRF-Token => should fail
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = requests.put(f"{API}/pme/anos-finais/external-indicators",
                         json={"academic_year": 2025, "ideb_atual": 1.0},
                         headers=headers, timeout=30)
        assert r.status_code in (400, 401, 403), f"expected CSRF rejection, got {r.status_code} {r.text[:200]}"


# -------- RBAC --------
class TestRBAC:
    def test_professor_analytics_403(self, professor_token):
        headers = {"Authorization": f"Bearer {professor_token}"}
        r = requests.get(f"{API}/pme/anos-finais/analytics?academic_year=2026", headers=headers, timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text[:200]}"

    def test_professor_external_get_403(self, professor_token):
        headers = {"Authorization": f"Bearer {professor_token}"}
        r = requests.get(f"{API}/pme/anos-finais/external-indicators?academic_year=2026",
                         headers=headers, timeout=30)
        assert r.status_code == 403

    def test_professor_external_put_blocked(self, professor_token):
        headers = {
            "Authorization": f"Bearer {professor_token}",
            "X-CSRF-Token": _csrf(professor_token) or "",
        }
        r = requests.put(f"{API}/pme/anos-finais/external-indicators",
                         json={"academic_year": 2025, "ideb_atual": 9.9},
                         headers=headers, timeout=30)
        assert r.status_code in (401, 403)

    def test_no_auth_returns_401(self):
        r = requests.get(f"{API}/pme/anos-finais/analytics?academic_year=2026", timeout=30)
        assert r.status_code in (401, 403)
