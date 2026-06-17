"""
Regressão CRÍTICA — Isolamento Multi-Tenant (P0).

Cenário (definido pela arquitetura):
  Mantenedora A + Gerente A + Escola A
  Mantenedora B + Gerente B + Escola B

  1) Login A → Refresh → Listar escolas → SOMENTE escolas da A
  2) Login B → Refresh → Listar escolas → SOMENTE escolas da B
  3) Token SEM mantenedora_id (gerente) → 0 resultados (FAIL-CLOSED), nunca todas.

Cobre a causa raiz (refresh perdia `mantenedora_id`) e o fail-closed do
`apply_tenant_filter`.
"""
import os
import uuid
import asyncio

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

import auth_utils
from auth_utils import hash_password, create_access_token, decode_token

API = "http://localhost:8001"
PWD = "Tenant@2026"


async def _seed(db):
    # template de usuário válido (copia o schema de um usuário ativo existente)
    template = await db.users.find_one({"status": "active"}, {"_id": 0})
    assert template, "Nenhum usuário ativo de template encontrado"

    tag = uuid.uuid4().hex[:8]
    mant_a = f"TENANT_TEST_A_{tag}"
    mant_b = f"TENANT_TEST_B_{tag}"
    await db.mantenedoras.insert_one({"id": mant_a, "nome": f"Mantenedora A {tag}"})
    await db.mantenedoras.insert_one({"id": mant_b, "nome": f"Mantenedora B {tag}"})

    school_a = f"SCHOOL_A_{tag}"
    school_b = f"SCHOOL_B_{tag}"
    await db.schools.insert_one({"id": school_a, "name": f"Escola A {tag}", "mantenedora_id": mant_a, "inep_code": "", "status": "active"})
    await db.schools.insert_one({"id": school_b, "name": f"Escola B {tag}", "mantenedora_id": mant_b, "inep_code": "", "status": "active"})

    def _mk_user(email, mant):
        u = dict(template)
        u.update({
            "id": str(uuid.uuid4()),
            "email": email,
            "full_name": f"Gerente {email}",
            "role": "gerente",
            "roles": ["gerente"],
            "status": "active",
            "mantenedora_id": mant,
            "school_links": [],
            "password_hash": hash_password(PWD),
        })
        u.pop("_id", None)
        return u

    email_a = f"gerente.a.{tag}@tenant-test.com"
    email_b = f"gerente.b.{tag}@tenant-test.com"
    ua = _mk_user(email_a, mant_a)
    ub = _mk_user(email_b, mant_b)
    await db.users.insert_one(ua)
    await db.users.insert_one(ub)

    return {
        "tag": tag, "mant_a": mant_a, "mant_b": mant_b,
        "school_a": school_a, "school_b": school_b,
        "email_a": email_a, "email_b": email_b,
        "user_a": ua, "user_b": ub,
    }


async def _cleanup(db, ctx):
    await db.mantenedoras.delete_many({"id": {"$in": [ctx["mant_a"], ctx["mant_b"]]}})
    await db.schools.delete_many({"id": {"$in": [ctx["school_a"], ctx["school_b"]]}})
    await db.users.delete_many({"email": {"$in": [ctx["email_a"], ctx["email_b"]]}})


async def _login_refresh_list(c, email):
    r = await c.post("/api/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 200, f"login {email}: {r.text}"
    rt = r.json()["refresh_token"]
    rr = await c.post("/api/auth/refresh", json={"refresh_token": rt})
    assert rr.status_code == 200, f"refresh {email}: {rr.text}"
    nat = rr.json()["access_token"]
    # confirma claim preservado
    claim = decode_token(nat).get("mantenedora_id")
    schools = await c.get("/api/schools?include_student_count=false", headers={"Authorization": f"Bearer {nat}"})
    assert schools.status_code == 200, schools.text
    ids = [s["id"] for s in schools.json()]
    return claim, ids


async def _run():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    ctx = await _seed(db)
    try:
        async with httpx.AsyncClient(base_url=API, timeout=40) as c:
            # 1) Gerente A
            claim_a, ids_a = await _login_refresh_list(c, ctx["email_a"])
            # 2) Gerente B
            claim_b, ids_b = await _login_refresh_list(c, ctx["email_b"])

            # 3) Token SEM mantenedora_id (simula o bug antigo) para o gerente A
            bad_token = create_access_token({
                "sub": ctx["user_a"]["id"], "email": ctx["email_a"],
                "role": "gerente", "school_ids": [],
                # mantenedora_id AUSENTE de propósito
            })
            r_bad = await c.get("/api/schools?include_student_count=false", headers={"Authorization": f"Bearer {bad_token}"})
            assert r_bad.status_code == 200, r_bad.text
            ids_bad = [s["id"] for s in r_bad.json()]
        return ctx, claim_a, ids_a, claim_b, ids_b, ids_bad
    finally:
        await _cleanup(db, ctx)


def test_multi_tenant_isolation_after_refresh():
    ctx, claim_a, ids_a, claim_b, ids_b, ids_bad = asyncio.run(_run())

    # Claims preservados no refresh
    assert claim_a == ctx["mant_a"], f"refresh A perdeu mantenedora_id: {claim_a}"
    assert claim_b == ctx["mant_b"], f"refresh B perdeu mantenedora_id: {claim_b}"

    # Gerente A vê SOMENTE escola da A
    assert ctx["school_a"] in ids_a, "Gerente A não vê a própria escola"
    assert ctx["school_b"] not in ids_a, "VAZAMENTO: Gerente A vê escola da B!"

    # Gerente B vê SOMENTE escola da B
    assert ctx["school_b"] in ids_b, "Gerente B não vê a própria escola"
    assert ctx["school_a"] not in ids_b, "VAZAMENTO: Gerente B vê escola da A!"

    # Token sem mantenedora_id → FAIL-CLOSED (0 resultados), nunca cross-tenant
    assert ids_bad == [], f"FAIL-CLOSED quebrado: token sem tenant retornou {len(ids_bad)} escolas"
    assert ctx["school_b"] not in ids_bad and ctx["school_a"] not in ids_bad

    print(f"✓ Isolamento multi-tenant OK | A={claim_a} B={claim_b} | fail-closed=0 escolas")


if __name__ == "__main__":
    test_multi_tenant_isolation_after_refresh()
    print("OK")
