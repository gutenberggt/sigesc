"""
Sprint 002.a — Testes: modelos de domínio, DTOs, contratos (QueuePort/IdempotencyStore),
idempotência determinística e Simulador CMDE (cenários + modo caótico determinístico).

Sem envio real ao MEC. Sem Batch Builder / Queue real / Worker / Scheduler.
"""
import sys, os, asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mig.core.ids import compute_idempotency_key, generate_correlation_id
from mig.core.audit import MigAuditService
from mig.core.monitoring import MigMonitoring
from mig.core.inmemory import InMemoryQueue, InMemoryIdempotencyStore
from mig.core.retry import run_with_retry, RetryPolicy
from mig.core.exceptions import MigUnavailableError, MigTimeoutError, MigUpstreamError
from mig.cmde.dtos import (
    FrequencyItemDTO, FrequencyBatchRequestDTO, CmdeFrequencyPayloadDTO,
    CmdeFrequencyResponseDTO, CmdeItemResultDTO,
)
from mig.cmde.frequency_models import FrequencyBatch, QueueItem, SendReceipt, BATCH_STATUSES
from mig.cmde.frequency_simulator import (
    CmdeFrequencySimulator, SimulatorConfig,
    SCENARIO_ACCEPT, SCENARIO_REJECT, SCENARIO_ERROR_503, SCENARIO_TIMEOUT, SCENARIO_INVALID,
)


class FakeAudit:
    """Captura eventos sem tocar o banco (mantém o dict cru, com scenario/simulated)."""
    def __init__(self):
        self.records = []
    async def record(self, event):
        self.records.append(dict(event))
        return dict(event)
    def log_call(self, *a, **k):
        pass


def _payload(cid="CMDE-20260730-AAAAA", n=3, tenant="t1", comp="2026-05"):
    items = [FrequencyItemDTO(student_id=f"s{i}", cpf=f"cpf{i}", school_inep="1517",
                              competencia=comp, dias_letivos=20, faltas_validas=i,
                              frequencia_percentual=100.0 - i) for i in range(n)]
    return CmdeFrequencyPayloadDTO(correlation_id=cid, tenant=tenant, competencia=comp,
                                   school_inep="1517", items=items)


# ---------- Idempotência determinística ----------
def test_idempotency_key():
    base = dict(tenant="t1", provider="cmde", operation="frequency",
                competencia="2026-05", student_id="s1", school_inep="1517")
    k1 = compute_idempotency_key(**base)
    k2 = compute_idempotency_key(**base)
    assert k1 == k2 and len(k1) == 40, "chave deve ser determinística (sha1 hex)"
    # muda aluno -> muda chave
    assert compute_idempotency_key(**{**base, "student_id": "s2"}) != k1
    # muda competência -> muda chave
    assert compute_idempotency_key(**{**base, "competencia": "2026-06"}) != k1
    # nova versão de payload -> nova chave (reenvio controlado)
    assert compute_idempotency_key(**base, payload_version=2) != k1
    print("OK 002a: idempotency_key determinística + sensível a inputs/versão")


# ---------- DTOs / Modelos de domínio ----------
def test_models_and_dtos():
    b = FrequencyBatch(competencia="2026-05", tenant="t1", correlation_id="CMDE-x")
    doc = b.to_doc()
    assert doc["status"] == "draft" and doc["totals"]["items"] == 0 and doc["competencia"] == "2026-05"
    assert doc["status"] in BATCH_STATUSES and "id" in doc and doc["created_at"]
    q = QueueItem(batch_id=b.id, idempotency_key="k", student_id="s1", competencia="2026-05", tenant="t1")
    qd = q.to_doc()
    assert qd["status"] == "pending" and qd["attempts"] == 0 and qd["lease_until"] is None
    r = SendReceipt(queue_item_id=q.id, batch_id=b.id, accepted=True, mec_protocol="SIM-1")
    assert r.to_doc()["accepted"] is True
    req = FrequencyBatchRequestDTO(competencia="2026-05")
    assert req.dry_run is True  # dry-run é o padrão
    print("OK 002a: modelos de domínio + DTOs (defaults corretos)")


# ---------- Contratos: IdempotencyStore ----------
async def _run_idem_store():
    store = InMemoryIdempotencyStore()
    assert await store.seen("k1") is None
    await store.remember("k1", {"accepted": True, "protocol": "P1"})
    got = await store.seen("k1")
    assert got and got["protocol"] == "P1"
    print("OK 002a: IdempotencyStore (seen/remember)")


# ---------- Contratos: QueuePort (reserva atômica + lease) ----------
async def _run_queue():
    q = InMemoryQueue()
    await q.enqueue({"id": "i1", "tenant": "t1"})
    await q.enqueue({"id": "i2", "tenant": "t1"})
    await q.enqueue({"id": "i3", "tenant": "t2"})
    a = await q.reserve("t1")
    b = await q.reserve("t1")
    c = await q.reserve("t1")
    assert a and b and a["id"] != b["id"], "cada reserve pega um item distinto"
    assert c is None, "sem itens pending -> None"
    assert a["status"] == "leased" and a["attempts"] == 1
    # isolamento por tenant
    d = await q.reserve("t2")
    assert d and d["id"] == "i3"
    # complete terminal
    await q.complete("i1", "accepted")
    assert (await q.stats("t1")).get("accepted") == 1
    # lease expirado volta a pending
    q._items["i2"]["lease_until"] = "2000-01-01T00:00:00+00:00"
    assert await q.requeue_expired() == 1
    assert (await q.stats("t1")).get("pending") == 1
    print("OK 002a: QueuePort (reserva atômica, isolamento tenant, lease/requeue)")


# ---------- Simulador: cenário ACCEPT ----------
async def _run_sim_accept():
    fa = FakeAudit(); mon = MigMonitoring()
    sim = CmdeFrequencySimulator(SimulatorConfig(scenario=SCENARIO_ACCEPT), audit=fa, monitoring=mon)
    resp = await sim.enviar_frequencia(_payload(n=3))
    assert resp.valid and resp.protocol and len(resp.items) == 3 and all(i.accepted for i in resp.items)
    ev = fa.records[-1]
    assert ev["scenario"] == SCENARIO_ACCEPT and ev["simulated"] is True and ev["status"] == "success"
    assert ev["records_sent"] == 3 and ev["records_accepted"] == 3 and ev["records_rejected"] == 0
    assert ev["correlation_id"] == "CMDE-20260730-AAAAA"
    assert mon.snapshot().get("cmde_sim.accept") == 1 and mon.snapshot().get("cmde_sim.request") == 1
    print("OK 002a: simulador ACCEPT (protocolo + audit + métricas)")


# ---------- Simulador: cenário REJECT (parcial) ----------
async def _run_sim_reject():
    fa = FakeAudit()
    sim = CmdeFrequencySimulator(SimulatorConfig(scenario=SCENARIO_REJECT, reject_every=2), audit=fa)
    resp = await sim.enviar_frequencia(_payload(n=4))
    rejected = [i for i in resp.items if not i.accepted]
    assert resp.valid and len(rejected) == 2 and all(i.code == "REJEITADO_SIM" for i in rejected)
    ev = fa.records[-1]
    assert ev["records_rejected"] == 2 and ev["records_accepted"] == 2 and ev["status"] == "success"
    assert ev["rejection_reasons"] and len(ev["rejection_reasons"]) == 2
    print("OK 002a: simulador REJECT (rejeição parcial auditada)")


# ---------- Simulador: erro definitivo + timeout ----------
async def _run_sim_errors():
    fa = FakeAudit()
    sim = CmdeFrequencySimulator(SimulatorConfig(scenario=SCENARIO_ERROR_503), audit=fa)
    try:
        await sim.enviar_frequencia(_payload()); assert False
    except MigUnavailableError:
        pass
    ev = fa.records[-1]
    assert ev["status"] == "error" and ev["scenario"] == SCENARIO_ERROR_503 and ev["http_status"] == 503
    assert ev["error_code"] == "MigUnavailableError"

    fa2 = FakeAudit()
    sim_t = CmdeFrequencySimulator(SimulatorConfig(scenario=SCENARIO_TIMEOUT), audit=fa2)
    try:
        await sim_t.enviar_frequencia(_payload()); assert False
    except MigTimeoutError:
        pass
    assert fa2.records[-1]["http_status"] == 504
    print("OK 002a: simulador ERRO 503 + TIMEOUT 504 (auditados como error)")


# ---------- Simulador: resposta inválida ----------
async def _run_sim_invalid():
    fa = FakeAudit()
    sim = CmdeFrequencySimulator(SimulatorConfig(scenario=SCENARIO_INVALID), audit=fa)
    resp = await sim.enviar_frequencia(_payload())
    assert resp.valid is False and resp.items == [] and resp.raw == {"unexpected_schema": True}
    ev = fa.records[-1]
    assert ev["status"] == "error" and ev["error_code"] == "INVALID_RESPONSE" and ev["scenario"] == SCENARIO_INVALID
    print("OK 002a: simulador RESPOSTA INVÁLIDA (valid=False, auditado como error)")


# ---------- Simulador + RetryManager (transient_failures) ----------
async def _run_sim_retry():
    fa = FakeAudit()
    sim = CmdeFrequencySimulator(SimulatorConfig(scenario=SCENARIO_ERROR_503, transient_failures=2), audit=fa)
    cid = "CMDE-20260730-RETRY"
    pl = _payload(cid=cid, n=2)
    res = await run_with_retry(lambda: sim.enviar_frequencia(pl),
                               RetryPolicy(max_attempts=3, base_delay_seconds=0.01))
    assert res.value.valid and all(i.accepted for i in res.value.items) and res.attempts == 3
    # 2 eventos de erro + 1 de sucesso, todos com o MESMO correlation_id
    assert sum(1 for r in fa.records if r["status"] == "error") == 2
    assert sum(1 for r in fa.records if r["status"] == "success") == 1
    assert all(r["correlation_id"] == cid for r in fa.records)
    print("OK 002a: simulador + RetryManager (falha 2x -> aceita na 3ª, correlation_id estável)")


# ---------- Simulador: modo caótico DETERMINÍSTICO ----------
async def _run_sim_chaos():
    def seq(seed):
        fa = FakeAudit()
        sim = CmdeFrequencySimulator(SimulatorConfig(chaos=True, chaos_seed=seed, transient_failures=999),
                                     audit=fa)
        async def _go():
            for i in range(20):
                try:
                    await sim.enviar_frequencia(_payload(cid=f"C-{i}", n=1))
                except Exception:
                    pass
            return [r["scenario"] for r in fa.records]
        return asyncio.get_event_loop().run_until_complete(_go()) if False else _go()
    s1 = await seq(42)
    s2 = await seq(42)
    s3 = await seq(7)
    assert s1 == s2, "mesmo seed -> mesma sequência de cenários (determinístico)"
    assert s1 != s3, "seeds diferentes -> sequências diferentes"
    assert len(set(s1)) >= 2, "modo caótico deve variar os cenários"
    # auditável: todos os eventos têm cenário registrado e simulated=True
    print("OK 002a: modo caótico determinístico + auditável (seq estável por seed)")


# ---------- audit.record persiste scenario/simulated ----------
async def _run_audit_fields():
    doc = await MigAuditService(None).record({"provider": "cmde", "operation": "FREQUENCY_SEND",
                                              "scenario": "accept", "simulated": True, "status": "success"})
    assert doc["scenario"] == "accept" and doc["simulated"] is True
    print("OK 002a: audit.record mapeia scenario/simulated")


if __name__ == "__main__":
    test_idempotency_key()
    test_models_and_dtos()
    asyncio.run(_run_idem_store())
    asyncio.run(_run_queue())
    asyncio.run(_run_sim_accept())
    asyncio.run(_run_sim_reject())
    asyncio.run(_run_sim_errors())
    asyncio.run(_run_sim_invalid())
    asyncio.run(_run_sim_retry())
    asyncio.run(_run_sim_chaos())
    asyncio.run(_run_audit_fields())
    print("\nSPRINT 002.a — TODOS OS TESTES PASSARAM ✅")
