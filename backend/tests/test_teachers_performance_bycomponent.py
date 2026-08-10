"""
Bug fix: GET /api/analytics/teachers/performance — medição POR COMPONENTE.

Valida:
  - 200 + shape dos campos (diario_real_pct, diario_pct, sla_*, score, turmas)
  - INVARIANTE: diario_real_pct >= diario_pct para TODO professor
  - ANTI-INFLAÇÃO: nenhum professor com 100.0 em ambas as colunas
  - PDF (content-type application/pdf)
  - filtros school_id / limit
  - ano sem dados (2019) -> 200 com data vazia
  - regressão dos demais endpoints do router analytics
"""
import os

import pytest
import requests
from dotenv import dotenv_values

_env = dotenv_values("/app/frontend/.env")
_base = os.environ.get("REACT_APP_BACKEND_URL") or _env.get("REACT_APP_BACKEND_URL")
if not _base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = _base.rstrip("/")

ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = "@Celta2007"
YEAR = 2026

PERF = f"{BASE_URL}/api/analytics/teachers/performance"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=60,
    )
    if r.status_code != 200:
        pytest.fail(f"Login falhou: {r.status_code} {r.text[:300]}")
    token = r.json().get("access_token")
    if not token:
        pytest.fail(f"Login sem access_token: {r.text[:300]}")
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def perf_data(client):
    r = client.get(PERF, params={"academic_year": YEAR, "limit": 100}, timeout=180)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:500]}"
    body = r.json()
    assert isinstance(body, dict) and "data" in body
    assert isinstance(body["data"], list)
    return body["data"]


# ---------- shape ----------
class TestShape:
    def test_status_and_fields(self, perf_data):
        assert len(perf_data) > 0, "seed sem professores — não é possível validar invariantes"
        required = [
            "teacher_id", "teacher_name", "diario_real_pct", "diario_pct",
            "sla_freq", "sla_conteudo", "sla_notas", "media_notas", "score", "turmas",
        ]
        for t in perf_data:
            missing = [k for k in required if k not in t]
            assert not missing, f"campos ausentes {missing} em {t}"
            for k in ("diario_real_pct", "diario_pct", "sla_freq", "sla_conteudo",
                      "sla_notas", "score"):
                assert isinstance(t[k], (int, float)), f"{k} não numérico: {t[k]!r}"
                assert 0 <= t[k] <= 100, f"{k}={t[k]} fora de 0-100 ({t['teacher_name']})"
            assert isinstance(t["turmas"], int) and t["turmas"] >= 0

    def test_no_mongo_id_leak(self, perf_data):
        for t in perf_data:
            assert "_id" not in t


# ---------- invariante crítica ----------
class TestInvariants:
    def test_diario_real_ge_diario_pct(self, perf_data):
        violations = [
            (t["teacher_name"], t["diario_real_pct"], t["diario_pct"])
            for t in perf_data if t["diario_real_pct"] < t["diario_pct"]
        ]
        assert not violations, f"INVARIANTE violada (real < 60%): {violations}"

    def test_no_double_100_inflation(self, perf_data):
        inflated = [
            {
                "teacher": t["teacher_name"],
                "sla_freq": t["sla_freq"],
                "sla_conteudo": t["sla_conteudo"],
                "sla_notas": t["sla_notas"],
            }
            for t in perf_data
            if t["diario_real_pct"] == 100.0 and t["diario_pct"] == 100.0
        ]
        assert not inflated, f"ANTI-INFLAÇÃO: professores cravados em 100/100: {inflated}"

    def test_sla_components_consistent_with_diario_pct(self, perf_data):
        """diario_pct deve ser a média ponderada 4/3/3 dos SLAs."""
        for t in perf_data:
            expected = min(round((t["sla_freq"] * 4 + t["sla_conteudo"] * 3
                                  + t["sla_notas"] * 3) / 10, 1), 100)
            assert abs(t["diario_pct"] - expected) <= 0.2, (
                f"{t['teacher_name']}: diario_pct={t['diario_pct']} != esperado {expected}")

    def test_sorted_by_score_desc(self, perf_data):
        scores = [t["score"] for t in perf_data]
        assert scores == sorted(scores, reverse=True)


# ---------- filtros ----------
class TestFilters:
    def test_limit(self, client):
        r = client.get(PERF, params={"academic_year": YEAR, "limit": 5}, timeout=180)
        assert r.status_code == 200, r.text[:300]
        assert len(r.json()["data"]) <= 5

    def test_school_id_filter(self, client, perf_data):
        r = client.get(f"{BASE_URL}/api/schools", timeout=60)
        assert r.status_code == 200, r.text[:300]
        payload = r.json()
        schools = payload if isinstance(payload, list) else payload.get("data", [])
        if not schools:
            pytest.skip("nenhuma escola disponível")
        sid = schools[0].get("id")
        r2 = client.get(PERF, params={"academic_year": YEAR, "school_id": sid, "limit": 100},
                        timeout=180)
        assert r2.status_code == 200, f"{r2.status_code}: {r2.text[:500]}"
        filtered = r2.json()["data"]
        assert len(filtered) <= len(perf_data)
        # invariante também no recorte filtrado
        for t in filtered:
            assert t["diario_real_pct"] >= t["diario_pct"], t

    def test_invalid_school_id_returns_empty(self, client):
        r = client.get(PERF, params={"academic_year": YEAR, "school_id": "TEST_nope"}, timeout=120)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["data"] == []


# ---------- regressão ano sem dados ----------
class TestEmptyYear:
    @pytest.mark.parametrize("year", [2019, 1999])
    def test_year_without_data(self, client, year):
        r = client.get(PERF, params={"academic_year": year}, timeout=120)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:500]}"
        assert r.json()["data"] == []


# ---------- PDF ----------
class TestPdf:
    def test_pdf_ok(self, client):
        r = client.get(f"{PERF}/pdf", params={"academic_year": YEAR}, timeout=240)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:500]}"
        assert "application/pdf" in r.headers.get("content-type", ""), r.headers
        assert r.content[:4] == b"%PDF", r.content[:40]
        assert len(r.content) > 1000

    def test_pdf_empty_year(self, client):
        r = client.get(f"{PERF}/pdf", params={"academic_year": 2019}, timeout=180)
        assert r.status_code in (200, 404), f"{r.status_code}: {r.text[:400]}"


# ---------- regressão geral do router analytics ----------
class TestAnalyticsRegression:
    @pytest.mark.parametrize("path,params", [
        ("/api/analytics/overview", {"academic_year": YEAR}),
        ("/api/analytics/enrollments/trend", {}),
        ("/api/analytics/attendance/monthly", {"academic_year": YEAR}),
        ("/api/analytics/grades/by-subject", {"academic_year": YEAR}),
        ("/api/analytics/grades/by-period", {"academic_year": YEAR}),
        ("/api/analytics/schools/ranking", {"academic_year": YEAR}),
        ("/api/analytics/students/performance", {"academic_year": YEAR, "limit": 10}),
        ("/api/analytics/distribution/grades", {"academic_year": YEAR}),
    ])
    def test_endpoint_200(self, client, path, params):
        r = client.get(f"{BASE_URL}{path}", params=params, timeout=240)
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:400]}"


# ---------- auth ----------
class TestAuth:
    def test_requires_auth(self):
        r = requests.get(PERF, params={"academic_year": YEAR}, timeout=60)
        assert r.status_code in (401, 403), f"{r.status_code}: {r.text[:200]}"
