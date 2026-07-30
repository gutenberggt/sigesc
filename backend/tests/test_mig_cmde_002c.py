"""
Sprint 002.c — Testes do MongoFrequencyQueue (fila durável).

Concorrência e recuperação: reserva simultânea, expiração de lease + requeue, múltiplos tenants,
grande volume, backpressure, máquina de estados (RETRYING/DEAD_LETTER), renovação de lease, métricas.
"""
import sys, os, asyncio, uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_env():
    from pathlib import Path
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_env()

from motor.motor_asyncio import AsyncIOMotorClient
from mig.cmde.queue import (MongoFrequencyQueue, PENDING, RESERVED, PROCESSING, RETRYING,
                            SUCCESS, FAILED, DEAD_LETTER)
from mig.cmde.frequency_repository import QUEUE

TAG = "qtest"
TA, TB = "q_tenant_A", "q_tenant_B"


def _item(tenant, i):
    return {"id": f"{TAG}_{tenant}_{i}", "tenant": tenant, "batch_id": f"{TAG}_batch",
            "idempotency_key": f"{TAG}:{tenant}:{i}", "student_id": f"s{i}",
            "competencia": "2020-05", "test_tag": TAG}


async def _clean(db):
    await db[QUEUE].delete_many({"test_tag": TAG})


async def run():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    await _clean(db)

    # ensure_indexes idempotente
    q = MongoFrequencyQueue(db, max_attempts=3, base_backoff_seconds=0)
    await q.ensure_indexes(); await q.ensure_indexes()
    print("OK 002c: ensure_indexes idempotente")

    # --- enqueue idempotente ---
    it = _item(TA, 0)
    await q.enqueue(it); await q.enqueue(it)
    assert await db[QUEUE].count_documents({"idempotency_key": it["idempotency_key"]}) == 1
    print("OK 002c: enqueue idempotente (idempotency_key unique)")

    # --- reserva simultânea (atômica): 20 itens, 40 reserves concorrentes ---
    await _clean(db)
    for i in range(20):
        await q.enqueue(_item(TA, i))
    results = await asyncio.gather(*[q.reserve(TA, lease_seconds=60) for _ in range(40)])
    reserved = [r for r in results if r]
    ids = [r["id"] for r in reserved]
    assert len(reserved) == 20, ("todos os 20 reservados uma única vez", len(reserved))
    assert len(set(ids)) == 20, "nenhum item reservado em duplicidade"
    assert all(r["status"] == RESERVED and r["attempts"] == 1 for r in reserved)
    assert all(r.get("first_reserved_at") for r in reserved)
    print("OK 002c: reserva simultânea atômica (20 itens, sem duplicidade)")

    # --- expiração de lease + requeue automático ---
    await db[QUEUE].update_many({"tenant": TA, "status": RESERVED},
                                {"$set": {"lease_until": "2000-01-01T00:00:00+00:00"}})
    n = await q.requeue_expired()
    assert n == 20, ("todos expirados voltam a PENDING", n)
    assert await db[QUEUE].count_documents({"tenant": TA, "status": PENDING}) == 20
    print("OK 002c: expiração de lease → requeue automático (PENDING)")

    # --- renovação de lease impede requeue ---
    r = await q.reserve(TA)
    assert await q.renew_lease(r["id"], lease_seconds=120) is True
    doc = await db[QUEUE].find_one({"id": r["id"]}, {"_id": 0})
    from datetime import datetime, timezone
    assert doc["lease_until"] > datetime.now(timezone.utc).isoformat(), "lease renovado para o futuro"
    assert await q.requeue_expired() == 0, "lease válido não é requeued"
    print("OK 002c: renovação de lease (não é requeued)")

    # --- múltiplos tenants (isolamento) ---
    await _clean(db)
    for i in range(3):
        await q.enqueue(_item(TA, i))
    for i in range(2):
        await q.enqueue(_item(TB, i))
    ra = [await q.reserve(TA) for _ in range(5)]
    assert len([x for x in ra if x]) == 3 and all(x["tenant"] == TA for x in ra if x)
    rb = await q.reserve(TB)
    assert rb and rb["tenant"] == TB
    print("OK 002c: isolamento multi-tenant na reserva")

    # --- backpressure por tenant ---
    await _clean(db)
    qb = MongoFrequencyQueue(db, backpressure_per_tenant=2, base_backoff_seconds=0)
    for i in range(5):
        await qb.enqueue(_item(TA, i))
    r1 = await qb.reserve(TA); r2 = await qb.reserve(TA); r3 = await qb.reserve(TA)
    assert r1 and r2 and r3 is None, "3ª reserva bloqueada por backpressure (2 in-flight)"
    await qb.succeed(r1["id"])                       # libera capacidade
    r4 = await qb.reserve(TA)
    assert r4 is not None, "após concluir 1, nova reserva é permitida"
    print("OK 002c: backpressure por tenant (limite de in-flight)")

    # --- máquina de estados: RETRYING → DEAD_LETTER após max_attempts ---
    await _clean(db)
    qd = MongoFrequencyQueue(db, max_attempts=3, base_backoff_seconds=0)
    await qd.enqueue(_item(TA, 99))
    seq = []
    for _ in range(4):
        it2 = await qd.reserve(TA)
        if it2 is None:
            seq.append("NONE"); break
        await qd.start_processing(it2["id"])
        st = await qd.fail(it2["id"], error="temporario", recoverable=True)
        seq.append(st)
    # reserve1->fail(attempts1)->RETRYING; r2->RETRYING; r3(attempts3>=3)->DEAD_LETTER; r4->NONE
    assert seq == [RETRYING, RETRYING, DEAD_LETTER, "NONE"], seq
    assert await db[QUEUE].count_documents({"tenant": TA, "status": DEAD_LETTER}) == 1
    print("OK 002c: RETRYING x2 → DEAD_LETTER (max_attempts) → não mais reservável")

    # --- falha não recuperável → FAILED direto ---
    await _clean(db)
    await qd.enqueue(_item(TA, 5))
    x = await qd.reserve(TA)
    st = await qd.fail(x["id"], error="401", recoverable=False)
    assert st == FAILED
    print("OK 002c: falha não recuperável → FAILED (terminal)")

    # --- grande volume: 500 itens drenados até SUCCESS ---
    await _clean(db)
    docs = [_item(TA, i) for i in range(500)]
    await db[QUEUE].insert_many([{**d, "status": PENDING, "attempts": 0,
                                  "created_at": "2020-05-01T00:00:00+00:00"} for d in docs])
    drained = 0
    while True:
        it3 = await q.reserve(TA, lease_seconds=120)
        if it3 is None:
            break
        await q.succeed(it3["id"]); drained += 1
    assert drained == 500, drained
    assert await db[QUEUE].count_documents({"tenant": TA, "status": SUCCESS}) == 500
    print("OK 002c: grande volume (500 itens drenados → SUCCESS)")

    # --- métricas da fila ---
    await _clean(db)
    await db[QUEUE].insert_many([
        {**_item(TA, 1), "status": PENDING, "attempts": 0, "created_at": "2020-05-01T00:00:00+00:00"},
        {**_item(TA, 2), "status": PENDING, "attempts": 0, "created_at": "2020-05-01T00:00:00+00:00"},
        {**_item(TA, 3), "status": PROCESSING, "attempts": 1, "created_at": "2020-05-01T00:00:00+00:00",
         "first_reserved_at": "2020-05-01T00:00:01+00:00"},
        {**_item(TA, 4), "status": RETRYING, "attempts": 2, "created_at": "2020-05-01T00:00:00+00:00"},
        {**_item(TA, 5), "status": DEAD_LETTER, "attempts": 3, "created_at": "2020-05-01T00:00:00+00:00"},
        {**_item(TA, 6), "status": SUCCESS, "attempts": 1, "created_at": "2020-05-01T00:00:00+00:00",
         "first_reserved_at": "2020-05-01T00:00:02+00:00"},
    ])
    m = await q.queue_metrics(TA)
    assert m["pendentes"] == 2 and m["processando"] == 1 and m["retries"] == 1, m
    assert m["dead_letters"] == 1 and m["success"] == 1, m
    assert m["tempo_medio_fila_ms"] is not None, m
    print("OK 002c: métricas da fila (pendentes/processando/retries/dead_letters/tempo médio)")

    await _clean(db)
    print("\nSPRINT 002.c — TODOS OS TESTES PASSARAM ✅")


if __name__ == "__main__":
    asyncio.run(run())
