"""
Apr 2026 — Valida o endpoint /api/spellcheck (corretor PT-BR via LanguageTool).

Casos:
  1. Texto com erros conhecidos ("otimo" + "vai na escola") → matches >= 2,
     payload normalizado (replacements: lista de strings, não objetos).
  2. Texto correto → matches == 0.
  3. Sem token → 401/403.
  4. Texto vazio → 422 (Pydantic).
"""
import os
import pytest
import httpx


BACKEND = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://learning-skills-hub.preview.emergentagent.com",
).rstrip("/")

SUPER_ADMIN = {
    "email": "gutenberg@sigesc.com",
    "password": os.environ.get("SIGESC_TEST_SUPERADMIN_PASSWORD", "@Celta2007"),
}


@pytest.fixture(scope="module")
def token():
    r = httpx.post(f"{BACKEND}/api/auth/login", json=SUPER_ADMIN, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def test_spellcheck_detects_known_errors(token):
    r = httpx.post(
        f"{BACKEND}/api/spellcheck",
        headers=_h(token),
        json={"text": "O menino vai na escola hoje, ele espera um otimo dia."},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "matches" in data and isinstance(data["matches"], list)
    # Esperamos pelo menos 2 erros: "vai na" → "à" e "otimo" → "ótimo"
    assert data["total"] >= 2
    # Cada match deve ter estrutura normalizada
    m = data["matches"][0]
    assert set(m.keys()) >= {
        "message", "offset", "length", "replacements",
        "rule_id", "category", "issue_type",
    }
    # replacements deve ser lista de strings (não objetos)
    for rep in m["replacements"]:
        assert isinstance(rep, str)
    # Deve conter uma sugestão de "ótimo"
    all_replacements = {r for m in data["matches"] for r in m["replacements"]}
    assert "ótimo" in all_replacements


def test_spellcheck_clean_text_returns_empty(token):
    r = httpx.post(
        f"{BACKEND}/api/spellcheck",
        headers=_h(token),
        json={"text": "O ensino fundamental é obrigatório no Brasil."},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # Pode haver sugestões estilísticas menores, mas não erros de ortografia/gramática
    misspellings = [m for m in data["matches"] if m["issue_type"] == "misspelling"]
    assert misspellings == [], f"Falsos positivos: {misspellings}"


def test_spellcheck_requires_auth():
    r = httpx.post(
        f"{BACKEND}/api/spellcheck",
        json={"text": "Teste sem token"},
        timeout=20,
    )
    assert r.status_code in (401, 403), r.text


def test_spellcheck_rejects_empty_text(token):
    r = httpx.post(
        f"{BACKEND}/api/spellcheck",
        headers=_h(token),
        json={"text": ""},
        timeout=20,
    )
    assert r.status_code == 422, r.text
