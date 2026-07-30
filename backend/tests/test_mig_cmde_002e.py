"""
Sprint 002.e — Testes do FrequencyScheduler.

Cobre: ativação/desativação por Feature Flag, múltiplos tenants, lock, janela operacional,
integração com o Worker, auditoria dos disparos, atualização de métricas, garantia de nenhuma
chamada real ao MEC (provider = Simulador) e dead letters + reprocessamento idempotente.
"""
import sys, os, asyncio
from datetime import datetime, timezone

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
from mig.cmde.scheduler import FrequencyScheduler, FLAG, COLLECTION
from mig.cmde.worker import FrequencyWorker
from mig.cmde.queue import MongoFrequencyQueue, SUCCESS, DEAD_LETTER, PENDING
from mig.cmde.frequency_repository import QUEUE, RECEIPTS
from mig.cmde.frequency_simulator import CmdeFrequencySimulator, SimulatorConfig, SCENARIO_ACCEPT
from mig.core.feature_flags import FeatureFlagService
from mig.core.audit import MigAuditService
from mig.core.monitoring import MigMonitoring

TA, TB = "sched_A", "sched_B"
AUD = "mig_audit_events"


async def _clean(db):
    for t in (TA, TB):
        await db[COLLECTION].delete_many({"tenant": t})
        await db["mig_feature_flags"].delete_many({"tenant": t})
        await db[QUEUE].delete_many({"tenant": t})
    await db[AUD].delete_many({"operation": "SCHEDULER_TICK", "tenant": {"$in": [TA, TB]}})


async def run():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    await _clean(db)
    flags = FeatureFlagService(db)
    audit = MigAuditService(db)
    mon = MigMonitoring()

    # runner FAKE (prova que o Scheduler só orquestra; nenhuma chamada real ao MEC)
    calls = []
    async def fake_runner(tenant, max_items):
        calls.append((tenant, max_items))
        await asyncio.sleep(0)
        return {"processed": 3, "success": 3, "failed": 0, "retrying": 0, "dead_letter": 0}

    sched = FrequencyScheduler(db, worker_runner=fake_runner, flags=flags, audit=audit,
                               monitoring=mon, interval_seconds=300)

    # --- 1. Flag OFF (default) → disabled, runner NÃO chamado ---
    r = await sched.tick(TA, environment=None)
    assert r["status"] == "disabled" and len(calls) == 0, r
    print("OK 002e: flag OFF por padrão → disabled (runner não chamado)")

    # --- 2. Habilita por flag (tenant A) → ran + auditoria + métrica ---
    await flags.set_flag(FLAG, True, tenant=TA, environment=None, actor="tester")
    r = await sched.tick(TA, environment=None)
    assert r["status"] == "ran" and r["summary"]["success"] == 3, r
    assert calls[-1][0] == TA
    ev = await db[AUD].find_one({"operation": "SCHEDULER_TICK", "tenant": TA}, {"_id": 0})
    assert ev and ev["records_accepted"] == 3 and ev["actor"] == "scheduler"
    assert mon.snapshot().get("scheduler.tick") == 1
    cfg = await sched.get_config(TA)
    assert cfg["last_run"] and cfg["next_run"] and cfg["last_status"] == "ran"
    print("OK 002e: flag ON → dispara Worker + auditoria + métrica + last/next run")

    # --- 3. Multi-tenant: B continua OFF ---
    r_b = await sched.tick(TB, environment=None)
    assert r_b["status"] == "disabled", r_b
    assert all(c[0] == TA for c in calls), "runner nunca chamado para B"
    print("OK 002e: multi-tenant (B desabilitado não dispara)")

    # --- 4. Lock: dois ticks concorrentes → 1 ran, 1 locked ---
    slow_calls = []
    async def slow_runner(tenant, max_items):
        slow_calls.append(tenant)
        await asyncio.sleep(0.3)
        return {"processed": 1, "success": 1, "failed": 0, "retrying": 0, "dead_letter": 0}
    sched_lock = FrequencyScheduler(db, worker_runner=slow_runner, flags=flags, audit=audit,
                                    monitoring=MigMonitoring())
    res = await asyncio.gather(sched_lock.tick(TA), sched_lock.tick(TA))
    statuses = sorted(x["status"] for x in res)
    assert statuses == ["locked", "ran"], statuses
    assert len(slow_calls) == 1, "apenas um Worker executou sob lock"
    print("OK 002e: lock por tenant (execuções simultâneas → 1 ran, 1 locked)")

    # --- 5. Janela operacional: fora da janela → outside_window (manual ignora) ---
    now = datetime.now(timezone.utc)
    closed_start = (now.hour + 2) % 24
    closed_end = (now.hour + 3) % 24
    await sched.set_config(TA, window_start=closed_start, window_end=closed_end)
    r = await sched.tick(TA, now=now)
    assert r["status"] == "outside_window", r
    r_manual = await sched.tick(TA, now=now, manual=True)
    assert r_manual["status"] == "ran", "disparo manual ignora a janela"
    await sched.set_config(TA, window_start=0, window_end=24)   # reabre
    print("OK 002e: janela operacional (fora=skip; manual ignora)")

    # --- 6. Integração REAL com Worker + Simulador (nenhuma chamada ao MEC) ---
    await db[QUEUE].delete_many({"tenant": TA})
    for i in range(5):
        await db[QUEUE].insert_one({
            "id": f"sch_{i}", "tenant": TA, "batch_id": "schbatch", "correlation_id": "CMDE-SCHED",
            "idempotency_key": f"sched:{i}", "student_id": f"s{i}", "school_inep": "1517",
            "competencia": "2020-05", "status": PENDING, "attempts": 0,
            "created_at": "2020-05-01T00:00:00+00:00",
            "payload_snapshot": {"student_id": f"s{i}", "cpf": "1", "school_inep": "1517",
                                 "competencia": "2020-05", "dias_letivos": 20, "faltas_validas": 1,
                                 "frequencia_percentual": 95.0}})
    sim = CmdeFrequencySimulator(SimulatorConfig(scenario=SCENARIO_ACCEPT), audit=audit, monitoring=mon)
    real_worker = FrequencyWorker(db, port=sim, queue=MongoFrequencyQueue(db, base_backoff_seconds=0),
                                  audit=audit, monitoring=mon)
    assert isinstance(real_worker.port, CmdeFrequencySimulator), "provider ativo é o Simulador"
    sched_real = FrequencyScheduler(db, worker_runner=lambda t, m: real_worker.run(t, max_items=m),
                                    flags=flags, audit=audit, monitoring=mon)
    r = await sched_real.tick(TA, manual=True)
    assert r["summary"]["success"] == 5, r
    assert await db[QUEUE].count_documents({"tenant": TA, "status": SUCCESS}) == 5
    # protocolo simulado (SIM-...) confirma que não houve chamada real
    rec = await db[RECEIPTS].find_one({"queue_item_id": "sch_0"}, {"_id": 0})
    assert rec and rec["mec_protocol"].startswith("SIM-"), rec
    await db[RECEIPTS].delete_many({"tenant": TA})
    print("OK 002e: integração real com Worker+Simulador (5 SUCCESS, protocolo SIM-, sem MEC)")

    # --- 7. Dead letters + reprocessamento idempotente ---
    await db[QUEUE].delete_many({"tenant": TA})
    await db[QUEUE].insert_one({
        "id": "dl_1", "tenant": TA, "batch_id": "b", "correlation_id": "CMDE-DL",
        "idempotency_key": "dl:1", "student_id": "s1", "competencia": "2020-05",
        "status": DEAD_LETTER, "attempts": 5, "last_error": "timeout",
        "created_at": "2020-05-01T00:00:00+00:00", "updated_at": "2020-05-02T00:00:00+00:00"})
    q = MongoFrequencyQueue(db)
    ok = await q.reprocess("dl_1")
    assert ok is True
    doc = await db[QUEUE].find_one({"id": "dl_1"}, {"_id": 0})
    assert doc["status"] == PENDING and doc["attempts"] == 0 and doc["idempotency_key"] == "dl:1"
    # idempotência: item não foi duplicado
    assert await db[QUEUE].count_documents({"idempotency_key": "dl:1"}) == 1
    print("OK 002e: dead letter reprocessado → PENDING (idempotência preservada)")

    await _clean(db)
    print("\nSPRINT 002.e — TODOS OS TESTES PASSARAM ✅")


if __name__ == "__main__":
    asyncio.run(run())
