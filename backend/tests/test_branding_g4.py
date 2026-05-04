"""Sprint G4 — PUT /api/tenant/branding (Live Preview backend).

Cobre:
- 401 sem token
- 400 cor hex inválida
- 200 hex válido com X-Mantenedora-Id (super_admin override)
- GET /api/mantenedoras retorna lista (super_admin)
- Persistência via GET /api/mantenedoras/{id}
"""
import os
import time
import asyncio
import httpx
import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")

BACKEND = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
SUPER_ADMIN = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}


@pytest.fixture(scope="module")
def session():
    """Login → retorna (token, csrf, sample_tenant_id)."""
    r = httpx.post(f"{BACKEND}/api/auth/login", json=SUPER_ADMIN, timeout=20)
    r.raise_for_status()
    body = r.json()
    token = body["access_token"]
    csrf = body.get("csrf_token") or ""
    return {"token": token, "csrf": csrf}


@pytest.fixture(scope="module")
def target_tenant(session):
    """Cria um tenant descartável p/ não poluir produção."""
    on = httpx.post(
        f"{BACKEND}/api/tenant/onboard",
        headers={"Authorization": f"Bearer {session['token']}",
                 "X-CSRF-Token": session["csrf"]},
        json={
            "nome": f"G4 Test Branding {int(time.time())}",
            "admin_email": f"g4_branding_{int(time.time())}@test.com",
            "admin_nome": "G4 Test",
        },
        timeout=20,
    )
    assert on.status_code == 201, on.text
    mid = on.json()["mantenedora_id"]
    aid = on.json()["admin_user_id"]
    yield mid
    # cleanup
    async def cleanup():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        await db.mantenedoras.delete_one({"id": mid})
        await db.users.delete_one({"id": aid})
    asyncio.run(cleanup())


def _h(session, mantenedora_id=None):
    h = {
        "Authorization": f"Bearer {session['token']}",
        "X-CSRF-Token": session["csrf"],
    }
    if mantenedora_id:
        h["X-Mantenedora-Id"] = mantenedora_id
    return h


def test_branding_requires_auth():
    r = httpx.put(
        f"{BACKEND}/api/tenant/branding",
        json={"primary_color": "#ff0000"}, timeout=10,
    )
    assert r.status_code in (401, 403), r.text


def test_branding_rejects_invalid_hex(session, target_tenant):
    r = httpx.put(
        f"{BACKEND}/api/tenant/branding",
        headers=_h(session, target_tenant),
        json={"primary_color": "red"},
        timeout=15,
    )
    assert r.status_code == 400, r.text
    assert "primary_color" in (r.json().get("detail") or "")


def test_branding_rejects_invalid_secondary_hex(session, target_tenant):
    r = httpx.put(
        f"{BACKEND}/api/tenant/branding",
        headers=_h(session, target_tenant),
        json={"secondary_color": "#zzzzzz"},
        timeout=15,
    )
    assert r.status_code == 400, r.text


def test_branding_updates_with_valid_payload(session, target_tenant):
    payload = {
        "name": "G4 Updated Name",
        "slogan": "Educação que transforma",
        "logo_url": "https://example.com/logo.png",
        "primary_color": "#dc2626",
        "secondary_color": "#0ea5e9",
    }
    r = httpx.put(
        f"{BACKEND}/api/tenant/branding",
        headers=_h(session, target_tenant),
        json=payload, timeout=15,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["primary_color"] == "#dc2626"
    assert d["secondary_color"] == "#0ea5e9"
    assert d["name"] == "G4 Updated Name"
    assert d["slogan"] == "Educação que transforma"
    assert d["logo_url"] == "https://example.com/logo.png"
    assert d["id"] == target_tenant


def test_branding_persistence_via_mantenedora_get(session, target_tenant):
    """Read-after-write via /api/mantenedoras/{id}."""
    r = httpx.get(
        f"{BACKEND}/api/mantenedoras/{target_tenant}",
        headers=_h(session), timeout=10,
    )
    assert r.status_code == 200, r.text
    m = r.json()
    assert m.get("cor_primaria") == "#dc2626"
    assert m.get("cor_secundaria") == "#0ea5e9"
    assert m.get("nome") == "G4 Updated Name"


def test_mantenedoras_list_super_admin(session):
    r = httpx.get(
        f"{BACKEND}/api/mantenedoras",
        headers=_h(session), timeout=10,
    )
    assert r.status_code == 200, r.text
    items = r.json()
    assert isinstance(items, list)
    assert len(items) >= 1
    assert "id" in items[0]
    assert "nome" in items[0]


def test_branding_empty_payload_rejected(session, target_tenant):
    r = httpx.put(
        f"{BACKEND}/api/tenant/branding",
        headers=_h(session, target_tenant),
        json={}, timeout=10,
    )
    assert r.status_code == 400, r.text


def test_branding_invalid_tenant_returns_404(session):
    r = httpx.put(
        f"{BACKEND}/api/tenant/branding",
        headers=_h(session, "non-existent-tenant-id-xyz"),
        json={"primary_color": "#123456"},
        timeout=10,
    )
    assert r.status_code == 404, r.text
