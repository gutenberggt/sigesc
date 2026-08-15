"""
Tests for the Boletim Virtual do Aluno (Student Portal) feature.
Covers:
- Student login (/api/auth/login) with role='aluno'
- /api/student/me endpoint
- /api/student/me/report-card endpoint (data shape, conceito logic, alerts, auth roles)
"""
from __future__ import annotations

import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend .env if not set at process env
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except Exception:
        pass


STUDENT_EMAIL = "aluno@sigesc.com"
STUDENT_PASSWORD = os.getenv("SIGESC_TEST_STUDENT_PASSWORD", "aluno123")
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = os.getenv("SIGESC_TEST_ADMIN_PASSWORD", "@Celta2007")


# -------- Fixtures --------
@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(api_client, email, password):
    r = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=20,
    )
    return r


@pytest.fixture(scope="module")
def student_token(api_client):
    r = _login(api_client, STUDENT_EMAIL, STUDENT_PASSWORD)
    assert r.status_code == 200, f"Login aluno falhou: {r.status_code} {r.text}"
    data = r.json()
    assert "access_token" in data, f"Resposta sem access_token: {data}"
    return data["access_token"], data.get("user", {})


@pytest.fixture(scope="module")
def admin_token(api_client):
    r = _login(api_client, ADMIN_EMAIL, ADMIN_PASSWORD)
    if r.status_code != 200:
        pytest.skip(f"admin login falhou: {r.status_code}")
    return r.json()["access_token"]


# -------- Auth / login --------
class TestStudentAuth:
    def test_login_student_returns_role_aluno(self, api_client):
        r = _login(api_client, STUDENT_EMAIL, STUDENT_PASSWORD)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "access_token" in data
        user = data.get("user", {})
        assert user.get("role") == "aluno", f"role esperado 'aluno', obtido {user.get('role')}"


# -------- /api/student/me --------
class TestStudentMe:
    def test_student_me_returns_student_data(self, api_client, student_token):
        token, _ = student_token
        r = api_client.get(
            f"{BASE_URL}/api/student/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "id" in data
        # aluno deve ter algum nome
        assert data.get("full_name") or data.get("name")

    def test_student_me_no_token_is_401(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/student/me", timeout=20)
        assert r.status_code in (401, 403), f"esperado 401/403, got {r.status_code}"


# -------- /api/student/me/report-card --------
REQUIRED_TOP_LEVEL_KEYS = {
    "aluno", "escola", "turma", "academic_year",
    "media_aprovacao", "frequencia_minima",
    "higher_grade", "usa_conceito",
    "componentes", "media_geral", "frequencia",
    "situacao_final", "alerts", "computed_at",
}


class TestReportCard:
    def test_report_card_ok_and_shape(self, api_client, student_token):
        token, _ = student_token
        r = api_client.get(
            f"{BASE_URL}/api/student/me/report-card",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        missing = REQUIRED_TOP_LEVEL_KEYS - set(data.keys())
        assert not missing, f"faltando chaves no response: {missing}"

        # aluno / escola campos básicos
        assert data["aluno"].get("nome")
        assert "nome" in data["escola"]

        # frequencia sub-obj
        freq = data["frequencia"]
        for k in ("dias_letivos_ate_hoje", "dias_letivos_previstos", "total_faltas"):
            assert k in freq, f"frequencia.{k} ausente"

        # tipos
        assert isinstance(data["componentes"], list)
        assert isinstance(data["alerts"], list)
        assert isinstance(data["usa_conceito"], bool)
        assert isinstance(data["higher_grade"], bool)

    def test_report_card_conceito_fields_when_usa_conceito(self, api_client, student_token):
        token, _ = student_token
        r = api_client.get(
            f"{BASE_URL}/api/student/me/report-card",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        if not data.get("usa_conceito"):
            pytest.skip("Aluno seed não está em turma por CONCEITO; pular verificação específica")

        assert data["media_geral"] is None, "media_geral deve ser None quando usa_conceito=True"

        componentes = data["componentes"]
        assert isinstance(componentes, list)
        if not componentes:
            pytest.skip("sem componentes na turma seed (fallback vazio) — aceitável")
        for comp in componentes:
            assert comp.get("usa_conceito") is True
            assert comp.get("rec_b1") is None
            assert comp.get("rec_b2") is None
            assert comp.get("rec_b3") is None
            assert comp.get("rec_b4") is None
            assert comp.get("rec_final") is None
            assert comp.get("media") is None
            assert comp.get("media_final") is None
            assert comp.get("situacao") in ("cursando", "aprovado", None)

    def test_report_card_situacao_final_valid(self, api_client, student_token):
        token, _ = student_token
        r = api_client.get(
            f"{BASE_URL}/api/student/me/report-card",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        assert r.status_code == 200
        assert r.json()["situacao_final"] in ("aprovado", "reprovado", "cursando")

    def test_report_card_alerts_coherence(self, api_client, student_token):
        """Se vier alerta 'excesso_faltas' → severity=high; 'parabens_presenca' → success."""
        token, _ = student_token
        r = api_client.get(
            f"{BASE_URL}/api/student/me/report-card",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        for a in data.get("alerts", []):
            assert a.get("type") in ("excesso_faltas", "parabens_presenca")
            if a["type"] == "excesso_faltas":
                assert a["severity"] == "high"
            if a["type"] == "parabens_presenca":
                assert a["severity"] == "success"
            assert a.get("message")

    def test_report_card_forbidden_for_non_aluno(self, api_client, admin_token):
        r = api_client.get(
            f"{BASE_URL}/api/student/me/report-card",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        )
        assert r.status_code == 403, f"esperado 403, got {r.status_code}: {r.text[:200]}"

    def test_report_card_no_token_returns_401(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/student/me/report-card", timeout=20)
        assert r.status_code in (401, 403), f"esperado 401/403, got {r.status_code}"
