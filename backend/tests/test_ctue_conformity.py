"""Sprint A1 CTUE — testes dos endpoints SSoT de conformidade.

Cobre:
  1. GET /api/ctue/profiles → 7 perfis.
  2. GET /api/ctue/conformity-overview → contrato dos mini-cards.
  3. GET /api/ctue/schools/{id}/conformity → contrato completo + seções Fase D nao_avaliado.
  4. Troca de perfil altera as métricas da MESMA escola.
  5. PUT /api/schools/{id} (segurança) → conformidade da seção sobe + atualizacao = hoje.
  6. Autenticação obrigatória / 404 para escola inexistente.
"""
import os
import time

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BACKEND = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else None
if not BACKEND:
    from dotenv import dotenv_values
    BACKEND = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")

ADMIN = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}
EXPECTED_PROFILES = {"default", "mp", "fnde", "tcm", "infraestrutura", "seguranca", "educacao_integral"}
FASE_D = {"obras", "documentacao", "observacoes_tecnicas"}


@pytest.fixture(scope="module")
def auth():
    time.sleep(1.0)
    r = httpx.post(f"{BACKEND}/api/auth/login", json=ADMIN, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login falhou {r.status_code}: {r.text[:300]}")
    data = r.json()
    tk = data.get("access_token") or data.get("token")
    assert tk, f"sem token na resposta: {data}"
    return {"token": tk, "csrf": data.get("csrf_token") or ""}


@pytest.fixture(scope="module")
def h(auth):
    return {"Authorization": f"Bearer {auth['token']}"}


@pytest.fixture(scope="module")
def hw(auth):
    """Headers para escrita (com CSRF)."""
    return {"Authorization": f"Bearer {auth['token']}", "X-CSRF-Token": auth["csrf"]}


@pytest.fixture(scope="module")
def overview(h):
    r = httpx.get(f"{BACKEND}/api/ctue/conformity-overview", params={"profile": "default"}, headers=h, timeout=60)
    assert r.status_code == 200, r.text[:400]
    return r.json()


# ---------- 1. Perfis ----------
class TestProfiles:
    def test_profiles_list(self, h):
        r = httpx.get(f"{BACKEND}/api/ctue/profiles", headers=h, timeout=30)
        assert r.status_code == 200, r.text[:300]
        profiles = r.json()["profiles"]
        keys = {p["key"] for p in profiles}
        assert keys == EXPECTED_PROFILES, keys
        assert all(isinstance(p["label"], str) and p["label"] for p in profiles)

    def test_profiles_requires_auth(self):
        r = httpx.get(f"{BACKEND}/api/ctue/profiles", timeout=30)
        assert r.status_code in (401, 403), r.status_code


# ---------- 2. Overview (mini-cards) ----------
class TestOverview:
    def test_contract(self, overview):
        assert overview["profile"] == "default"
        assert overview["count"] == len(overview["schools"])
        assert overview["count"] > 0, "nenhuma escola no escopo do admin"
        for s in overview["schools"]:
            for f in ("school_id", "name", "situacao", "completude", "conformidade",
                      "status", "maturidade", "atualizacao"):
                assert f in s, f"campo {f} ausente em {s.get('name')}"
            assert "gestor" in s
            assert isinstance(s["completude"], int) and 0 <= s["completude"] <= 100
            assert isinstance(s["conformidade"], int) and 0 <= s["conformidade"] <= 100
            assert s["status"] in {"conforme", "atencao", "critico", "nao_conforme"}
            assert 1 <= s["maturidade"]["nivel"] <= 5
            assert s["maturidade"]["nome"]
            assert "label" in s["atualizacao"] and "freshness" in s["atualizacao"]
            assert s["atualizacao"]["freshness"] in {"recent", "ok", "stale", "never"}

    def test_no_mongo_objectid_leak(self, overview):
        assert '"_id":' not in str(overview) and "'_id'" not in str(overview)

    def test_profile_changes_overview_numbers(self, h, overview):
        r = httpx.get(f"{BACKEND}/api/ctue/conformity-overview", params={"profile": "seguranca"},
                      headers=h, timeout=60)
        assert r.status_code == 200
        seg = r.json()
        assert seg["profile"] == "seguranca"
        base = {s["school_id"]: s["conformidade"] for s in overview["schools"]}
        diff = [sid for sid, v in base.items()
                if any(x["school_id"] == sid and x["conformidade"] != v for x in seg["schools"])]
        assert diff, "perfil 'seguranca' não alterou a conformidade de nenhuma escola"


# ---------- 3. Conformidade por escola ----------
class TestSchoolConformity:
    def test_full_contract(self, h, overview):
        sid = overview["schools"][0]["school_id"]
        r = httpx.get(f"{BACKEND}/api/ctue/schools/{sid}/conformity", params={"profile": "mp"},
                      headers=h, timeout=30)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["school_id"] == sid
        assert d["profile"] == "mp"
        for f in ("completude_geral", "conformidade_geral", "selo_geral", "maturidade",
                  "atualizacao", "sections", "ruleset_id", "versao", "evaluated_at"):
            assert f in d, f
        assert d["selo_geral"] in {"conforme", "atencao", "critico", "nao_conforme"}
        assert len(d["sections"]) == 14, len(d["sections"])
        for sec in d["sections"]:
            for f in ("key", "label", "status", "completude", "conformidade",
                      "itens_total", "itens_preenchidos", "regras", "pendencias"):
                assert f in sec, f"{sec['key']} sem {f}"

    def test_fase_d_sections_nao_avaliado(self, h, overview):
        sid = overview["schools"][0]["school_id"]
        d = httpx.get(f"{BACKEND}/api/ctue/schools/{sid}/conformity", headers=h, timeout=30).json()
        found = {s["key"]: s for s in d["sections"] if s["key"] in FASE_D}
        assert set(found) == FASE_D, found.keys()
        for k, s in found.items():
            assert s["status"] == "nao_avaliado", (k, s["status"])
            assert s["avaliada"] is False, k
            assert s["completude"] is None and s["conformidade"] is None, k

    def test_fase_d_does_not_reduce_conformity(self, h, overview):
        """Média ponderada deve usar só seções avaliadas."""
        sid = overview["schools"][0]["school_id"]
        d = httpx.get(f"{BACKEND}/api/ctue/schools/{sid}/conformity", headers=h, timeout=30).json()
        active = [s for s in d["sections"] if s.get("avaliada") and s.get("peso", 0) > 0]
        wt = sum(s["peso"] for s in active)
        expected = round(sum(s["peso"] * s["conformidade"] for s in active) / wt)
        assert d["conformidade_geral"] == expected, (d["conformidade_geral"], expected)
        expected_c = round(sum(s["peso"] * s["completude"] for s in active) / wt)
        assert d["completude_geral"] == expected_c

    @pytest.mark.parametrize("profile", sorted(EXPECTED_PROFILES))
    def test_all_profiles_work(self, h, overview, profile):
        sid = overview["schools"][0]["school_id"]
        r = httpx.get(f"{BACKEND}/api/ctue/schools/{sid}/conformity",
                      params={"profile": profile}, headers=h, timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["profile"] == profile

    def test_profile_changes_same_school(self, h, overview):
        sid = overview["schools"][0]["school_id"]
        vals = {}
        for p in ("default", "mp", "seguranca"):
            d = httpx.get(f"{BACKEND}/api/ctue/schools/{sid}/conformity",
                          params={"profile": p}, headers=h, timeout=30).json()
            vals[p] = (d["completude_geral"], d["conformidade_geral"])
        assert len(set(vals.values())) > 1, f"perfis não alteraram métricas: {vals}"

    def test_school_not_found(self, h):
        r = httpx.get(f"{BACKEND}/api/ctue/schools/inexistente-xyz/conformity", headers=h, timeout=30)
        assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"

    def test_requires_auth(self, overview):
        sid = overview["schools"][0]["school_id"]
        r = httpx.get(f"{BACKEND}/api/ctue/schools/{sid}/conformity", timeout=30)
        assert r.status_code in (401, 403)


# ---------- 5. E2E: editar escola → conformidade sobe + atualizacao hoje ----------
class TestEditRaisesConformity:
    def test_seguranca_fields_raise_conformity_and_refresh(self, h, hw, overview):
        sid = overview["schools"][0]["school_id"]
        before = httpx.get(f"{BACKEND}/api/ctue/schools/{sid}/conformity",
                           params={"profile": "seguranca"}, headers=h, timeout=30).json()
        sec_before = next(s for s in before["sections"] if s["key"] == "seguranca")

        school = httpx.get(f"{BACKEND}/api/schools/{sid}", headers=h, timeout=30)
        assert school.status_code == 200, school.text[:300]
        original = school.json()

        payload = dict(original)
        for k in ("_id", "id", "created_at", "updated_at"):
            payload.pop(k, None)
        payload.update({
            "qtd_extintores": 8,
            "brigada_incendio": True,
            "plano_evacuacao": True,
            "saidas_emergencia": 2,
            "qtd_cameras": 4,
        })
        put = httpx.put(f"{BACKEND}/api/schools/{sid}", json=payload, headers=hw, timeout=60)
        assert put.status_code == 200, f"PUT falhou {put.status_code}: {put.text[:400]}"

        after = httpx.get(f"{BACKEND}/api/ctue/schools/{sid}/conformity",
                          params={"profile": "seguranca"}, headers=h, timeout=30).json()
        sec_after = next(s for s in after["sections"] if s["key"] == "seguranca")

        assert sec_after["conformidade"] >= sec_before["conformidade"], (sec_before, sec_after)
        assert sec_after["conformidade"] > 0
        assert sec_after["completude"] >= sec_before["completude"]
        assert after["atualizacao"]["label"] == "Atualizado hoje", after["atualizacao"]
        assert after["atualizacao"]["freshness"] == "recent"

        # o overview (mini-card) reflete o mesmo SSoT
        ov = httpx.get(f"{BACKEND}/api/ctue/conformity-overview", params={"profile": "seguranca"},
                       headers=h, timeout=60).json()
        card = next(s for s in ov["schools"] if s["school_id"] == sid)
        assert card["conformidade"] == after["conformidade_geral"]
        assert card["completude"] == after["completude_geral"]
        assert card["atualizacao"]["label"] == "Atualizado hoje"

    def test_schools_crud_regression(self, h, hw, overview):
        """CRUD de escolas não deve regredir com o CTUE (create → get → put → delete)."""
        ref = httpx.get(f"{BACKEND}/api/schools/{overview['schools'][0]['school_id']}",
                        headers=h, timeout=30).json()
        mant = ref.get("mantenedora_id")
        assert mant, "escola de referência sem mantenedora_id"
        hwm = dict(hw); hwm["X-Mantenedora-Id"] = mant
        payload = {"name": "TEST_CTUE_CRUD", "status": "active", "tipo_unidade": "sede",
                   "zona_localizacao": "urbana", "mantenedora_id": mant}
        c = httpx.post(f"{BACKEND}/api/schools", json=payload, headers=hwm, timeout=60)
        assert c.status_code in (200, 201), f"CREATE falhou {c.status_code}: {c.text[:300]}"
        sid = c.json()["id"]
        try:
            g = httpx.get(f"{BACKEND}/api/schools/{sid}", headers=h, timeout=30)
            assert g.status_code == 200
            assert g.json()["name"] == "TEST_CTUE_CRUD"
            assert g.json().get("updated_at") or g.json().get("created_at")

            up = dict(g.json())
            for k in ("_id", "id", "created_at", "updated_at"):
                up.pop(k, None)
            up["gestor_principal"] = "TEST_CRUD Gestor"
            p = httpx.put(f"{BACKEND}/api/schools/{sid}", json=up, headers=hwm, timeout=60)
            assert p.status_code == 200, p.text[:300]
            g2 = httpx.get(f"{BACKEND}/api/schools/{sid}", headers=h, timeout=30).json()
            assert g2["gestor_principal"] == "TEST_CRUD Gestor"
            assert g2.get("updated_at"), "updated_at não gravado no update"

            conf = httpx.get(f"{BACKEND}/api/ctue/schools/{sid}/conformity", headers=h, timeout=30)
            assert conf.status_code == 200
            assert conf.json()["atualizacao"]["label"] == "Atualizado hoje"
        finally:
            d = httpx.delete(f"{BACKEND}/api/schools/{sid}", headers=hwm, timeout=60)
            assert d.status_code in (200, 204), f"DELETE falhou {d.status_code}: {d.text[:300]}"
            assert httpx.get(f"{BACKEND}/api/schools/{sid}", headers=h, timeout=30).status_code == 404

    def test_gestor_principal_persists_and_appears_in_overview(self, h, hw, overview):
        sid = overview["schools"][0]["school_id"]
        original = httpx.get(f"{BACKEND}/api/schools/{sid}", headers=h, timeout=30).json()
        payload = dict(original)
        for k in ("_id", "id", "created_at", "updated_at"):
            payload.pop(k, None)
        payload["gestor_principal"] = "TEST_Gestor QA"
        put = httpx.put(f"{BACKEND}/api/schools/{sid}", json=payload, headers=hw, timeout=60)
        assert put.status_code == 200, put.text[:300]

        ov = httpx.get(f"{BACKEND}/api/ctue/conformity-overview", headers=h, timeout=60).json()
        card = next(s for s in ov["schools"] if s["school_id"] == sid)
        assert card["gestor"] == "TEST_Gestor QA", card
