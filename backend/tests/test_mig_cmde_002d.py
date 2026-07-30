"""
Sprint 002.d — Testes do FrequencyWorker.

Cobre: bootstrap (ensure_indexes + validação), múltiplos workers concorrentes, timeout, retry,
rejeição definitiva, recuperação após interrupção (lease expirado), integração com o Simulador,
reconciliação via SendReceipt e auditoria de todos os caminhos.
"""
import sys, os, asyncio

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
from mig.cmde.worker import FrequencyWorker
from mig.cmde.queue import (MongoFrequencyQueue, SUCCESS, FAILED, RETRYING, DEAD_LETTER,
                            PROCESSING, PENDING)
from mig.cmde.frequency_repository import QUEUE, RECEIPTS, BATCHES
from mig.cmde.frequency_simulator import (CmdeFrequencySimulator, SimulatorConfig,
                                          SCENARIO_ACCEPT, SCENARIO_REJECT, SCENARIO_TIMEOUT,
                                          SCENARIO_ERROR_503)
from mig.core.audit import MigAuditService
from mig.core.monitoring import MigMonitoring
from mig.core.retry import RetryPolicy

TAG = "wtest"
T = "w_tenant"
AUD = "mig_audit_events"


def _item(i, batch="wbatch", tenant=T, cid="CMDE-WORKER-0"):
    return {"id": f"{TAG}_{i}", "tenant": tenant, "batch_id": batch,
            "correlation_id": cid, "idempotency_key": f"{TAG}:{i}", "student_id": f"s{i}",
            "school_inep": "1517", "competencia": "2020-05", "status": PENDING, "attempts": 0,
            "created_at": "2020-05-01T00:00:00+00:00", "test_tag": TAG,
            "payload_snapshot": {"student_id": f"s{i}", "cpf": "111", "school_inep": "1517",
                                 "competencia": "2020-05", "dias_letivos": 20, "faltas_validas": 1,
                                 "frequencia_percentual": 95.0, "full_name": f"Aluno {i}"}}


async def _clean(db):
    await db[QUEUE].delete_many({"test_tag": TAG})
    await db[RECEIPTS].delete_many({"tenant": T})
    await db[BATCHES].delete_many({"id": {"$regex": "^wbatch"}})
    await db[AUD].delete_many({"correlation_id": {"$regex": "^CMDE-WORKER"}})


def _mk_queue(db):
    return MongoFrequencyQueue(db, max_attempts=5, base_backoff_seconds=0)


async def run():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    await _clean(db)

    # --- Bootstrap ---
    w = FrequencyWorker(db, queue=_mk_queue(db))
    assert await w.bootstrap() is True
    print("OK 002d: bootstrap (ensure_indexes + validação de infraestrutura)")

    # --- Integração com Simulador (accept) + recibo + auditoria ---
    await _clean(db)
    await db[QUEUE].insert_one(_item(1))
    aud = MigAuditService(db); mon = MigMonitoring()
    sim = CmdeFrequencySimulator(SimulatorConfig(scenario=SCENARIO_ACCEPT), audit=aud, monitoring=mon)
    w = FrequencyWorker(db, port=sim, queue=_mk_queue(db), audit=aud, monitoring=mon)
    st = await w.process_one(T)
    assert st == SUCCESS
    doc = await db[QUEUE].find_one({"id": f"{TAG}_1"}, {"_id": 0})
    assert doc["status"] == SUCCESS
    rec = await db[RECEIPTS].find_one({"queue_item_id": f"{TAG}_1"}, {"_id": 0})
    assert rec and rec["accepted"] is True and rec["mec_protocol"] and rec["raw_response_hash"]
    ev = await db[AUD].find_one({"operation": "FREQUENCY_ITEM_SUCCESS", "correlation_id": "CMDE-WORKER-0"}, {"_id": 0})
    assert ev and ev["records_accepted"] == 1 and ev["actor"] == "worker"
    print("OK 002d: SUCCESS via Simulador (recibo + protocolo + auditoria)")

    # --- Múltiplos workers concorrentes (sem duplo processamento) ---
    await _clean(db)
    await db[QUEUE].insert_many([_item(i) for i in range(30)])
    sim = CmdeFrequencySimulator(SimulatorConfig(scenario=SCENARIO_ACCEPT), audit=aud, monitoring=mon)
    workers = [FrequencyWorker(db, port=sim, queue=_mk_queue(db), audit=aud, monitoring=mon)
               for _ in range(4)]
    summaries = await asyncio.gather(*[wk.run(T) for wk in workers])
    total_processed = sum(s["processed"] for s in summaries)
    assert total_processed == 30, total_processed
    assert await db[QUEUE].count_documents({"test_tag": TAG, "status": SUCCESS}) == 30
    # 1 recibo por item (sem duplicidade)
    assert await db[RECEIPTS].count_documents({"tenant": T}) == 30
    print("OK 002d: múltiplos workers concorrentes (30 itens, sem duplo processamento)")

    # --- Retry: 503 x2 depois aceita (RetryManager, 1 process_one → SUCCESS) ---
    await _clean(db)
    await db[QUEUE].insert_one(_item(2, cid="CMDE-WORKER-RETRY"))
    sim_r = CmdeFrequencySimulator(SimulatorConfig(scenario=SCENARIO_ERROR_503, transient_failures=2),
                                   audit=aud, monitoring=mon)
    w = FrequencyWorker(db, port=sim_r, queue=_mk_queue(db), audit=aud, monitoring=mon,
                        retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.01))
    st = await w.process_one(T)
    assert st == SUCCESS, st
    ev = await db[AUD].find_one({"operation": "FREQUENCY_ITEM_SUCCESS", "correlation_id": "CMDE-WORKER-RETRY"}, {"_id": 0})
    assert ev and ev["attempts"] == 3, ev
    print("OK 002d: retry recuperável (503,503,200 → SUCCESS em 3 tentativas)")

    # --- Timeout: sempre falha → após retries → RETRYING (durável) ---
    await _clean(db)
    await db[QUEUE].insert_one(_item(3, cid="CMDE-WORKER-TIMEOUT"))
    sim_t = CmdeFrequencySimulator(SimulatorConfig(scenario=SCENARIO_TIMEOUT), audit=aud, monitoring=mon)
    w = FrequencyWorker(db, port=sim_t, queue=_mk_queue(db), audit=aud, monitoring=mon,
                        retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0.01))
    st = await w.process_one(T)
    assert st == RETRYING, st
    doc = await db[QUEUE].find_one({"id": f"{TAG}_3"}, {"_id": 0})
    assert doc["status"] == RETRYING and doc["last_error"]
    rec = await db[RECEIPTS].find_one({"queue_item_id": f"{TAG}_3"}, {"_id": 0})
    assert rec and rec["accepted"] is False and rec["http_status"] == 504
    ev = await db[AUD].find_one({"operation": "FREQUENCY_ITEM_RETRYING"}, {"_id": 0})
    assert ev and ev["status"] == "error"
    print("OK 002d: timeout → RETRYING durável (recibo + auditoria)")

    # --- Rejeição definitiva → FAILED ---
    await _clean(db)
    await db[QUEUE].insert_one(_item(4, cid="CMDE-WORKER-REJECT"))
    sim_j = CmdeFrequencySimulator(SimulatorConfig(scenario=SCENARIO_REJECT), audit=aud, monitoring=mon)
    w = FrequencyWorker(db, port=sim_j, queue=_mk_queue(db), audit=aud, monitoring=mon)
    st = await w.process_one(T)
    assert st == FAILED, st
    rec = await db[RECEIPTS].find_one({"queue_item_id": f"{TAG}_4"}, {"_id": 0})
    assert rec and rec["accepted"] is False and rec["rejection_code"] == "REJEITADO_SIM"
    ev = await db[AUD].find_one({"operation": "FREQUENCY_ITEM_FAILED"}, {"_id": 0})
    assert ev and ev["records_rejected"] == 1
    print("OK 002d: rejeição definitiva → FAILED (não recuperável)")

    # --- Recuperação após interrupção (lease expirado) ---
    await _clean(db)
    it = _item(5, cid="CMDE-WORKER-CRASH")
    it["status"] = PROCESSING
    it["lease_until"] = "2000-01-01T00:00:00+00:00"   # worker "morreu" com lease vencido
    await db[QUEUE].insert_one(it)
    sim = CmdeFrequencySimulator(SimulatorConfig(scenario=SCENARIO_ACCEPT), audit=aud, monitoring=mon)
    w = FrequencyWorker(db, port=sim, queue=_mk_queue(db), audit=aud, monitoring=mon)
    summary = await w.run(T)   # requeue_first=True recupera o item preso
    assert summary["success"] == 1, summary
    doc = await db[QUEUE].find_one({"id": f"{TAG}_5"}, {"_id": 0})
    assert doc["status"] == SUCCESS
    print("OK 002d: recuperação após interrupção (lease expirado → requeue → SUCCESS)")

    # --- Reconciliação de lote (partial) ---
    await _clean(db)
    await db[QUEUE].insert_one(_item(6, batch="wbatch_mix", cid="CMDE-WORKER-MIX"))   # accept
    await db[QUEUE].insert_one(_item(7, batch="wbatch_mix", cid="CMDE-WORKER-MIX"))   # reject
    await db[BATCHES].insert_one({"id": "wbatch_mix", "status": "ready", "tenant": T,
                                  "competencia": "2020-05"})
    # worker 1: accept para s6; worker 2: reject para s7 → usar dois simuladores
    w_ok = FrequencyWorker(db, port=CmdeFrequencySimulator(SimulatorConfig(scenario=SCENARIO_ACCEPT), audit=aud, monitoring=mon),
                           queue=_mk_queue(db), audit=aud, monitoring=mon)
    w_rej = FrequencyWorker(db, port=CmdeFrequencySimulator(SimulatorConfig(scenario=SCENARIO_REJECT), audit=aud, monitoring=mon),
                            queue=_mk_queue(db), audit=aud, monitoring=mon)
    await w_ok.process_one(T)   # pega o primeiro pending (s6) → SUCCESS
    await w_rej.process_one(T)  # pega o próximo (s7) → FAILED
    batch = await db[BATCHES].find_one({"id": "wbatch_mix"}, {"_id": 0})
    assert batch["status"] == "partial", batch
    assert batch["totals"]["accepted"] == 1 and batch["totals"]["rejected"] == 1, batch
    print("OK 002d: reconciliação de lote (partial: 1 accepted + 1 rejected)")

    await _clean(db)
    print("\nSPRINT 002.d — TODOS OS TESTES PASSARAM ✅")


if __name__ == "__main__":
    asyncio.run(run())
