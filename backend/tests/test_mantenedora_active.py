"""
Iteration 57 — Validação do refactor /api/mantenedora (singular) para a coleção `mantenedoras` (plural)
e suporte a tenant scope (X-Mantenedora-Id) com fallback super_admin cross-tenant.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = "@Celta2007"
ORIGINAL_TENANT = "a991c1ac-56b1-46a8-b122-effedbe19b21"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.text}"
    data = r.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def headers_t1(admin_token):
    return {"Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
            "X-Mantenedora-Id": ORIGINAL_TENANT}


@pytest.fixture(scope="module")
def secondary_tenant(headers):
    payload = {"nome": "TEST_MT_ITER57_TENANT", "cnpj": "11.111.111/0001-11",
               "municipio": "Test City", "estado": "PA"}
    r = requests.post(f"{BASE_URL}/api/mantenedoras", json=payload, headers=headers, timeout=30)
    assert r.status_code in (200, 201), f"Could not create tenant: {r.status_code} {r.text}"
    tid = r.json().get("id")
    assert tid
    yield tid
    try:
        requests.delete(f"{BASE_URL}/api/mantenedoras/{tid}", headers=headers, timeout=30)
    except Exception:
        pass


@pytest.fixture(scope="module")
def headers_t2(admin_token, secondary_tenant):
    return {"Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
            "X-Mantenedora-Id": secondary_tenant}


# ---------- GET /api/mantenedora ----------

class TestGetMantenedoraActive:
    def test_no_header_returns_first_mantenedora(self, headers):
        """super_admin sem header → fallback retorna a primeira mantenedora da coleção."""
        r = requests.get(f"{BASE_URL}/api/mantenedora", headers=headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "id" in data
        assert "nome" in data

    def test_header_t1_returns_t1_mantenedora(self, headers_t1):
        """X-Mantenedora-Id=t1 → retorna especificamente a mantenedora T1."""
        r = requests.get(f"{BASE_URL}/api/mantenedora", headers=headers_t1, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("id") == ORIGINAL_TENANT, f"Expected {ORIGINAL_TENANT}, got {data.get('id')}"

    def test_header_t2_returns_t2_mantenedora(self, headers_t2, secondary_tenant):
        """X-Mantenedora-Id=t2 → retorna a mantenedora T2 distinta."""
        r = requests.get(f"{BASE_URL}/api/mantenedora", headers=headers_t2, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("id") == secondary_tenant
        assert data.get("nome") == "TEST_MT_ITER57_TENANT"


# ---------- PUT /api/mantenedora ----------

class TestPutMantenedoraActive:
    def test_super_admin_can_put_t1(self, headers_t1):
        """super_admin com header t1 atualiza a mantenedora T1 (não 403)."""
        update_payload = {"telefone": "11888887777"}
        r = requests.put(f"{BASE_URL}/api/mantenedora", json=update_payload,
                         headers=headers_t1, timeout=30)
        assert r.status_code == 200, f"PUT failed: {r.status_code} {r.text}"
        data = r.json()
        assert data.get("id") == ORIGINAL_TENANT
        assert data.get("telefone") == "11888887777"

        # Verify persistence with GET
        g = requests.get(f"{BASE_URL}/api/mantenedora", headers=headers_t1, timeout=30)
        assert g.status_code == 200
        assert g.json().get("telefone") == "11888887777"

    def test_super_admin_can_put_t2(self, headers_t2, secondary_tenant):
        """PUT na mantenedora T2 atualiza a coleção plural correta."""
        update_payload = {"municipio": "Updated City T2"}
        r = requests.put(f"{BASE_URL}/api/mantenedora", json=update_payload,
                         headers=headers_t2, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("id") == secondary_tenant
        assert data.get("municipio") == "Updated City T2"

    def test_put_writes_to_mantenedoras_plural_collection(self, headers_t2, secondary_tenant):
        """Confirma que PUT escreveu na coleção `mantenedoras` (plural) — usa MongoDB direto."""
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient

        async def _check():
            c = AsyncIOMotorClient(os.environ.get('MONGO_URL'))
            db = c[os.environ.get('DB_NAME')]
            return await db.mantenedoras.find_one({'id': secondary_tenant})

        try:
            doc = asyncio.run(_check())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            doc = loop.run_until_complete(_check())
        assert doc is not None, "Mantenedora not found in `mantenedoras` plural collection"
        assert doc.get("municipio") == "Updated City T2"


# ---------- Phase 2 regression — the iteration_56 endpoints still pass ----------

class TestRegressionPhase2:
    def test_me_returns_super_admin(self, headers):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=headers, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("role") == "super_admin"
        assert d.get("mantenedora_id") == ORIGINAL_TENANT

    def test_t1_schools_still_visible(self, headers_t1):
        r = requests.get(f"{BASE_URL}/api/schools", headers=headers_t1, timeout=30)
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        names = [s.get("name") or s.get("nome") for s in items]
        assert any("MULTISSERIADA" in (n or "").upper() for n in names)

    def test_classes_count_t1(self, headers_t1):
        r = requests.get(f"{BASE_URL}/api/classes", headers=headers_t1, timeout=30)
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        assert len(items) >= 6

    def test_mantenedoras_list_visible(self, headers):
        """Listagem de mantenedoras (plural) continua acessível para super_admin."""
        r = requests.get(f"{BASE_URL}/api/mantenedoras", headers=headers, timeout=30)
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        ids = [m.get("id") for m in items]
        assert ORIGINAL_TENANT in ids
