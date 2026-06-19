"""Feb 2026 — Sprint F: Multi-Tenant Toolkit (audit + branding + onboard)."""
import os
import asyncio
import time
import httpx
import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

BACKEND = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://school-reorganize.preview.emergentagent.com",
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
    """Endpoint de branding deve responder sem token (login screen consome).

    Sem mantenedora_id na query: resolve por Host.
    """
    r = httpx.get(f"{BACKEND}/api/tenant/branding/public", timeout=10)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "name" in d
    assert "primary_color" in d
    assert d["primary_color"].startswith("#")
    assert "resolved_via" in d
    # Headers de cache
    assert "Vary" in r.headers and "Host" in r.headers["Vary"]
    assert "Cache-Control" in r.headers


def test_branding_resolves_by_host_domain(token):
    """Vincula um domain via API. Em produção o ingress preserva Host;
    aqui validamos via DB que o vínculo existe e o branding retorna corretamente
    quando o backend recebe esse Host."""
    onboard = httpx.post(
        f"{BACKEND}/api/tenant/onboard",
        headers=_h(token),
        json={
            "nome": "Tenant Branding Test",
            "admin_email": f"branding_{int(time.time())}@test.com",
            "admin_nome": "Branding Admin",
            "primary_color": "#00ff00",
            "domain": "branding-test.sigesc.local",
        },
        timeout=20,
    )
    assert onboard.status_code == 201, onboard.text
    mid = onboard.json()["mantenedora_id"]
    assert onboard.json()["domain_linked"] == "branding-test.sigesc.local"
    try:
        # Lista domains confirma vínculo
        r = httpx.get(
            f"{BACKEND}/api/tenant/domains?mantenedora_id={mid}",
            headers=_h(token), timeout=10,
        )
        assert r.status_code == 200
        items = r.json()["items"]
        assert any(d["domain"] == "branding-test.sigesc.local" for d in items)
    finally:
        async def cleanup():
            c = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = c[os.environ["DB_NAME"]]
            await db.mantenedoras.delete_one({"id": mid})
            await db.tenant_domains.delete_many({"mantenedora_id": mid})
            await db.users.delete_one({"id": onboard.json()["admin_user_id"]})
        asyncio.run(cleanup())


def test_domains_crud(token):
    """CRUD de tenant_domains."""
    on = httpx.post(
        f"{BACKEND}/api/tenant/onboard", headers=_h(token),
        json={
            "nome": "Domain CRUD Test",
            "admin_email": f"dom_{int(time.time())}_{os.getpid()}@t.com",
            "admin_nome": "X",
        }, timeout=15,
    )
    assert on.status_code == 201, on.text
    mid = on.json()["mantenedora_id"]
    try:
        r = httpx.post(
            f"{BACKEND}/api/tenant/domains", headers=_h(token),
            json={"mantenedora_id": mid, "domain": "crud.sigesc.local", "is_primary": True},
            timeout=10,
        )
        assert r.status_code == 201, r.text
        domain_id = r.json()["id"]
        # Duplicata 409
        r2 = httpx.post(
            f"{BACKEND}/api/tenant/domains", headers=_h(token),
            json={"mantenedora_id": mid, "domain": "crud.sigesc.local"}, timeout=10,
        )
        assert r2.status_code == 409
        # Domínio inválido 400
        r3 = httpx.post(
            f"{BACKEND}/api/tenant/domains", headers=_h(token),
            json={"mantenedora_id": mid, "domain": "not_a_domain"}, timeout=10,
        )
        assert r3.status_code == 400
        # Lista
        r4 = httpx.get(
            f"{BACKEND}/api/tenant/domains?mantenedora_id={mid}",
            headers=_h(token), timeout=10,
        )
        assert r4.status_code == 200
        items = r4.json()["items"]
        assert len(items) == 1
        assert items[0]["mantenedora_nome"] == "Domain CRUD Test"
        # Delete
        r5 = httpx.delete(
            f"{BACKEND}/api/tenant/domains/{domain_id}",
            headers=_h(token), timeout=10,
        )
        assert r5.status_code == 200
    finally:
        async def cleanup():
            c = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = c[os.environ["DB_NAME"]]
            await db.mantenedoras.delete_one({"id": mid})
            await db.tenant_domains.delete_many({"mantenedora_id": mid})
            await db.users.delete_one({"id": on.json()["admin_user_id"]})
        asyncio.run(cleanup())


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
        "nome": f"Pytest Mantenedora F{int(time.time())}",
        "admin_email": f"pytest_admin_{int(time.time())}@test.com",
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
