"""
FrequencyWorker — consumidor da fila de envio de frequência CMDE (Sprint 002.d).

Consome EXCLUSIVAMENTE a fila (MongoFrequencyQueue) + a porta de envio (CmdeFrequencyPort),
usando o RetryManager, Audit, Metrics e Correlation ID existentes. O provider PADRÃO é o
Simulador CMDE (nenhuma chamada real ao MEC). NÃO contém Scheduler.

Todos os caminhos de processamento são auditados (operation = FREQUENCY_ITEM_<estado>) e
reconciliados via SendReceipt + totais/estado do lote.
"""
import hashlib
import json
import time
from datetime import datetime, timezone

from mig.cmde.queue import (MongoFrequencyQueue, SUCCESS, FAILED, RETRYING, DEAD_LETTER)
from mig.cmde.frequency_simulator import CmdeFrequencySimulator, SimulatorConfig
from mig.cmde.frequency_repository import FrequencyRepository
from mig.cmde.frequency_models import SendReceipt
from mig.cmde.dtos import CmdeFrequencyPayloadDTO, FrequencyItemDTO
from mig.core.audit import MigAuditService
from mig.core.monitoring import MigMonitoring
from mig.core.retry import run_with_retry, CMDE_DEFAULT
from mig.core.ids import generate_correlation_id
from mig.core.exceptions import MigError

PROVIDER = "cmde"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


class FrequencyWorker:
    def __init__(self, db, port=None, queue=None, audit=None, monitoring=None,
                 lease_seconds: int = 60, retry_policy=None):
        self.db = db
        self.audit = audit or MigAuditService(db)
        self.monitoring = monitoring or MigMonitoring()
        # Provider PADRÃO: Simulador CMDE (nenhuma chamada real ao MEC)
        self.port = port or CmdeFrequencySimulator(
            SimulatorConfig(), audit=self.audit, monitoring=self.monitoring)
        self.queue = queue or MongoFrequencyQueue(db)
        self.repo = FrequencyRepository(db)
        self.lease_seconds = lease_seconds
        self.retry_policy = retry_policy or CMDE_DEFAULT

    # ---- Bootstrap: índices + validação de infraestrutura ----
    async def bootstrap(self) -> bool:
        await self.queue.ensure_indexes()
        try:
            await self.queue.col.estimated_document_count()
        except Exception as e:
            raise MigError(f"Fila de envio indisponível: {e}", status_code=503)
        idx = await self.queue.col.index_information()
        required = {"uq_idem", "reserve_idx", "lease_idx"}
        missing = required - set(idx.keys())
        if missing:
            raise MigError(f"Infraestrutura da fila inválida — índices ausentes: {sorted(missing)}",
                           status_code=500)
        return True

    # ---- Processamento de um item ----
    async def process_one(self, tenant: str):
        item = await self.queue.reserve(tenant, self.lease_seconds)
        if not item:
            return None
        self.monitoring.incr("worker.reserved")
        await self.queue.start_processing(item["id"])
        cid = item.get("correlation_id") or generate_correlation_id("CMDE")
        payload = CmdeFrequencyPayloadDTO(
            correlation_id=cid, tenant=item.get("tenant"), competencia=item.get("competencia"),
            school_inep=item.get("school_inep", ""),
            items=[FrequencyItemDTO(**(item.get("payload_snapshot") or {}))])
        started = _now_iso(); t0 = time.perf_counter()

        # ---- Transporte (Simulador por padrão) com RetryManager ----
        try:
            result = await run_with_retry(lambda: self.port.enviar_frequencia(payload),
                                          self.retry_policy)
            resp, attempts = result.value, result.attempts
        except MigError as e:
            state = await self.queue.fail(item["id"], error=e.message, recoverable=True)
            await self._receipt(item, cid, http_status=e.status_code, accepted=False,
                                code=type(e).__name__, reason=e.message, raw=None)
            await self._audit(item, cid, state, "error", started, t0,
                              attempts=self.retry_policy.max_attempts, http_status=e.status_code,
                              error_code=type(e).__name__, error_message=e.message,
                              sent=1, accepted=0, rejected=0)
            self.monitoring.incr("worker.transport_error")
            await self._reconcile_batch(item.get("batch_id"))
            return state

        # ---- Resposta fora do contrato ----
        if not resp.valid:
            state = await self.queue.fail(item["id"], error="INVALID_RESPONSE", recoverable=True)
            await self._receipt(item, cid, http_status=resp.http_status, accepted=False,
                                code="INVALID_RESPONSE", reason="Resposta fora do contrato esperado.",
                                raw=resp)
            await self._audit(item, cid, state, "error", started, t0, attempts=attempts,
                              http_status=resp.http_status, error_code="INVALID_RESPONSE",
                              error_message="Resposta fora do contrato esperado.",
                              sent=1, accepted=0, rejected=0)
            self.monitoring.incr("worker.invalid")
            await self._reconcile_batch(item.get("batch_id"))
            return state

        # ---- Reconciliação por item ----
        matched = next((r for r in resp.items if r.ref == item["student_id"]), None)
        if matched and matched.accepted:
            await self.queue.succeed(item["id"])
            await self._receipt(item, cid, http_status=resp.http_status, accepted=True,
                                code=None, reason=None, raw=resp, protocol=resp.protocol)
            await self._audit(item, cid, SUCCESS, "success", started, t0, attempts=attempts,
                              http_status=resp.http_status, sent=1, accepted=1, rejected=0)
            self.monitoring.incr("worker.success")
            state = SUCCESS
        else:
            code = matched.code if matched else "NO_RESULT"
            reason = matched.reason if matched else "Item não retornado pelo CMDE."
            state = await self.queue.fail(item["id"], error=reason, recoverable=False)  # rejeição definitiva
            await self._receipt(item, cid, http_status=resp.http_status, accepted=False,
                                code=code, reason=reason, raw=resp, protocol=resp.protocol)
            await self._audit(item, cid, state, "error", started, t0, attempts=attempts,
                              http_status=resp.http_status, error_code=code, error_message=reason,
                              sent=1, accepted=0, rejected=1)
            self.monitoring.incr("worker.rejected")
        await self._reconcile_batch(item.get("batch_id"))
        return state

    # ---- Loop de drenagem (sem Scheduler) ----
    async def run(self, tenant: str, max_items: int = None, requeue_first: bool = True) -> dict:
        if requeue_first:
            await self.queue.requeue_expired()
        summary = {"processed": 0, "success": 0, "failed": 0, "retrying": 0, "dead_letter": 0}
        key = {SUCCESS: "success", FAILED: "failed", RETRYING: "retrying", DEAD_LETTER: "dead_letter"}
        while True:
            if max_items and summary["processed"] >= max_items:
                break
            state = await self.process_one(tenant)
            if state is None:
                break
            summary["processed"] += 1
            if key.get(state):
                summary[key[state]] += 1
        return summary

    # ---- Recibo + reconciliação de lote ----
    async def _receipt(self, item, cid, http_status, accepted, code, reason, raw, protocol=None):
        raw_hash = None
        if raw is not None:
            raw_hash = hashlib.sha1(
                json.dumps(raw.model_dump(), sort_keys=True, default=str).encode()).hexdigest()
        rec = SendReceipt(queue_item_id=item["id"], batch_id=item.get("batch_id"),
                          correlation_id=cid, tenant=item.get("tenant"), mec_protocol=protocol,
                          http_status=http_status, accepted=accepted, rejection_code=code,
                          rejection_reason=reason, raw_response_hash=raw_hash)
        await self.repo.save_receipt(rec)

    async def _reconcile_batch(self, batch_id):
        if not batch_id:
            return
        counts = await self.repo.batch_item_counts(batch_id)
        total = sum(counts.values())
        accepted = counts.get(SUCCESS, 0)
        rejected = counts.get(FAILED, 0) + counts.get(DEAD_LETTER, 0)
        terminal = accepted + rejected
        if total and terminal == total:
            status = "completed" if rejected == 0 else ("failed" if accepted == 0 else "partial")
        else:
            status = "processing"
        await self.repo.update_batch(batch_id, status=status,
                                     totals={"items": total, "sent": terminal,
                                             "accepted": accepted, "rejected": rejected})

    # ---- Auditoria (todos os caminhos) ----
    async def _audit(self, item, cid, outcome, status, started, t0, attempts, http_status=None,
                     error_code=None, error_message=None, sent=0, accepted=0, rejected=0):
        await self.audit.record({
            "provider": PROVIDER, "operation": f"FREQUENCY_ITEM_{outcome}", "tenant": item.get("tenant"),
            "actor": "worker", "status": status, "started_at": started, "finished_at": _now_iso(),
            "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
            "environment": None, "correlation_id": cid, "attempts": attempts,
            "records_processed": sent, "records_sent": sent, "records_accepted": accepted,
            "records_rejected": rejected, "http_status": http_status,
            "error_code": error_code, "error_message": error_message,
        })
