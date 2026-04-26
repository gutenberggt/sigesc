"""
Regression test — Multi-tenant security bug fix (Feb 2026).

Cenário do bug original:
  1. User era admin/staff de Mantenedora A (mantenedora_id=A no DB e JWT).
  2. Super_admin promove user a gerente de Mantenedora B via designar_gerente.
  3. Backend antes do fix apenas fazia $set: {role, mantenedora_id}, sem:
     - Revogar tokens ativos do user (JWT antigo continuava válido com
       mantenedora_id=A → apply_tenant_filter retornava dados de A)
     - Limpar school_links que pertenciam a escolas de outras mantenedoras
       (continuavam vazando via verify_school_access).

Fix esperado:
  - POST /api/mantenedoras/{mid}/gerente:
    * $set role/mantenedora_id corretos
    * Filtra school_links/school_ids pelas escolas que pertencem à nova
      mantenedora (resposta inclui school_links_removed_cross_tenant)
    * Chama token_blacklist.revoke_all_user_tokens(user_id)
  - Token antigo do user designado retorna 401 ("Token revogado")
  - Após relogin, JWT novo tem mantenedora_id correto e school_ids limpos
  - GET /api/students e GET /api/schools só retornam dados da nova mantenedora
"""
import os
import sys
import uuid
import asyncio
import base64
import json as jsonlib
import pytest
import requests

sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

SUPER_CREDS = {
    "email": "gutenberg@sigesc.com",
    "password": os.getenv("SIGESC_TEST_ADMIN_PASSWORD", "@Celta2007"),
}


def _decode_jwt(token):
    payload_b64 = token.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    return jsonlib.loads(base64.urlsafe_b64decode(payload_b64))


@pytest.fixture(scope="module")
def super_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=SUPER_CREDS, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def two_mantenedoras_and_user():
    """Setup: Floresta (existente) + Pau Darco (cria) + admin user vinculado a Floresta."""
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    from motor.motor_asyncio import AsyncIOMotorClient
    from datetime import datetime, timezone
    from auth_utils import hash_password

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    async def setup():
        flo = await db.mantenedoras.find_one({}, {"_id": 0})
        flo_id = flo["id"]
        pau = await db.mantenedoras.find_one(
            {"name": "TEST_Pau_Darco_for_security_test"}, {"_id": 0}
        )
        if not pau:
            pau_id = str(uuid.uuid4())
            await db.mantenedoras.insert_one(
                {
                    "id": pau_id,
                    "name": "TEST_Pau_Darco_for_security_test",
                    "created_at": datetime.now(timezone.utc),
                }
            )
        else:
            pau_id = pau["id"]
        # Escola na nova mantenedora
        sch = await db.schools.find_one(
            {"name": "TEST_ESCOLA_PAUDARCO", "mantenedora_id": pau_id}, {"_id": 0}
        )
        if not sch:
            pau_sid = str(uuid.uuid4())
            await db.schools.insert_one(
                {
                    "id": pau_sid,
                    "name": "TEST_ESCOLA_PAUDARCO",
                    "mantenedora_id": pau_id,
                    "status": "active",
                    "created_at": datetime.now(timezone.utc),
                }
            )
        else:
            pau_sid = sch["id"]

        flo_school = await db.schools.find_one({"mantenedora_id": flo_id}, {"_id": 0})
        flo_sid = flo_school["id"]

        await db.users.delete_one({"email": "test_designar_gerente@sigesc.com"})
        uid = str(uuid.uuid4())
        await db.users.insert_one(
            {
                "id": uid,
                "email": "test_designar_gerente@sigesc.com",
                "full_name": "TEST USER DESIGNAR",
                "role": "admin",
                "roles": ["admin"],
                "status": "active",
                "mantenedora_id": flo_id,  # nasce vinculado à Floresta
                "school_ids": [flo_sid],
                "school_links": [{"school_id": flo_sid, "role": "admin"}],
                "password_hash": hash_password("test123"),
                "created_at": datetime.now(timezone.utc),
            }
        )
        return {"flo_id": flo_id, "pau_id": pau_id, "user_id": uid, "flo_sid": flo_sid}

    data = asyncio.get_event_loop().run_until_complete(setup())

    yield data

    async def teardown():
        await db.users.delete_one({"id": data["user_id"]})

    asyncio.get_event_loop().run_until_complete(teardown())


def test_old_token_revoked_after_designar_gerente(super_token, two_mantenedoras_and_user):
    """Cenário completo: token antigo deve falhar; token novo deve estar correto."""
    creds = {"email": "test_designar_gerente@sigesc.com", "password": "test123"}

    # Login - JWT carregará mantenedora_id=Floresta
    r = requests.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
    assert r.status_code == 200
    old_token = r.json()["access_token"]
    old_payload = _decode_jwt(old_token)
    assert old_payload["mantenedora_id"] == two_mantenedoras_and_user["flo_id"]

    # Antes da designação, vê dados da Floresta
    r = requests.get(
        f"{BASE_URL}/api/students?page=1&page_size=5",
        headers={"Authorization": f"Bearer {old_token}"},
        timeout=30,
    )
    assert r.status_code == 200
    floresta_total_before = r.json()["total"]

    # Super_admin designa user para Pau Darco
    r = requests.post(
        f"{BASE_URL}/api/mantenedoras/{two_mantenedoras_and_user['pau_id']}/gerente",
        headers={"Authorization": f"Bearer {super_token}"},
        json={"user_id": two_mantenedoras_and_user["user_id"]},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["mantenedora_id"] == two_mantenedoras_and_user["pau_id"]
    # School da Floresta deve ter sido removida
    assert body["school_links_removed_cross_tenant"] >= 1
    assert body["school_links_kept"] == 0

    # Token antigo agora deve ser rejeitado (revogado)
    r = requests.get(
        f"{BASE_URL}/api/students?page=1&page_size=5",
        headers={"Authorization": f"Bearer {old_token}"},
        timeout=30,
    )
    assert r.status_code == 401, f"esperado 401, veio {r.status_code}: {r.text}"
    assert "revogado" in r.text.lower() or "revoked" in r.text.lower()

    # Re-login carrega JWT novo apontando para Pau Darco
    r = requests.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
    assert r.status_code == 200
    new_token = r.json()["access_token"]
    new_payload = _decode_jwt(new_token)
    assert new_payload["mantenedora_id"] == two_mantenedoras_and_user["pau_id"]
    assert new_payload["role"] == "gerente"
    # school_ids da Floresta NÃO devem aparecer
    assert two_mantenedoras_and_user["flo_sid"] not in (new_payload.get("school_ids") or [])

    # Lista de students não deve mais conter dados da Floresta
    r = requests.get(
        f"{BASE_URL}/api/students?page=1&page_size=5",
        headers={"Authorization": f"Bearer {new_token}"},
        timeout=30,
    )
    assert r.status_code == 200
    new_total = r.json()["total"]
    assert new_total < floresta_total_before, (
        f"Vazamento cross-tenant ainda presente: antes={floresta_total_before}, depois={new_total}"
    )

    # Lista de schools deve conter apenas Pau Darco
    r = requests.get(
        f"{BASE_URL}/api/schools",
        headers={"Authorization": f"Bearer {new_token}"},
        timeout=30,
    )
    assert r.status_code == 200
    schools = r.json()
    for s in schools:
        assert s["mantenedora_id"] == two_mantenedoras_and_user["pau_id"], (
            f"Vazou escola de outra mantenedora: {s.get('name')} mant={s.get('mantenedora_id')}"
        )
