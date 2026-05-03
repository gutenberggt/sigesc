"""Feb 2026 — Sprint F: Multi-Tenant Toolkit (audit + branding + onboard)."""
import os
import asyncio
import httpx
import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

BACKEND = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://learning-skills-hub.preview.emergentagent.com",
).rstrip("/")
SUPER_ADMIN = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}


@pytest.fixture(scope="module")
def token():
    r = httpx.post(f"{BACKEND}/api/auth/login", json=SUPER_ADMIN, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def test_branding_public_no_auth():
    """Endpoint de branding deve responder sem token (login screen consome)."""
    r = httpx.get(f"{BACKEND}/api/tenant/branding/public", timeout=10)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "name" in d
    assert "primary_color" in d
    assert d["primary_color"].startswith("#")


def test_audit_returns_collections(token):
    r = httpx.get(f"{BACKEND}/api/tenant/audit?sample_size=1", headers=_h(token), timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "rows" in d
    assert any(r["collection"] == "schools" for r in d["rows"])
    assert any(r["collection"] == "classes" for r in d["rows"])


def test_audit_protected(token):
    """Sem token → 401."""
    r = httpx.get(f"{BACKEND}/api/tenant/audit", timeout=10)
    assert r.status_code in (401, 403)


def test_backfill_dry_run(token):
    """Dry run não escreve."""
    r = httpx.post(
        f"{BACKEND}/api/tenant/audit/backfill?dry_run=true",
        headers=_h(token), timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["dry_run"] is True
    assert "results" in d


def test_onboard_creates_full_tenant(token):
    payload = {
        "nome": f"Pytest Mantenedora F{int(asyncio.get_event_loop().time())}",
        "admin_email": f"pytest_admin_{int(asyncio.get_event_loop().time())}@test.com",
        "admin_nome": "Admin Teste",
        "estado": "PA", "municipio": "Teste",
        "primary_color": "#ff0000",
        "escola_inicial_nome": "Escola Inicial Pytest",
    }
    r = httpx.post(f"{BACKEND}/api/tenant/onboard", headers=_h(token), json=payload, timeout=20)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["ok"] is True
    assert d["mantenedora_id"]
    assert d["admin_user_id"]
    assert d["school_id"]
    assert d["admin_temp_password"] == "Mudar@2026"

    # Cleanup
    async def cleanup():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        await db.mantenedoras.delete_one({"id": d["mantenedora_id"]})
        await db.users.delete_one({"id": d["admin_user_id"]})
        await db.schools.delete_one({"id": d["school_id"]})

    asyncio.run(cleanup())


def test_onboard_rejects_duplicate_email(token):
    """Não pode criar duas mantenedoras com o mesmo admin_email."""
    payload = {
        "nome": "DupTest", "admin_email": "gutenberg@sigesc.com",  # já existe
        "admin_nome": "X",
    }
    r = httpx.post(f"{BACKEND}/api/tenant/onboard", headers=_h(token), json=payload, timeout=15)
    assert r.status_code == 409, r.text
