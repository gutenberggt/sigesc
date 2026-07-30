"""
MigAuditService — auditoria PERSISTENTE de eventos de integração (SSoT operacional do MIG).

Coleção: `mig_audit_events` (append-only). Cada evento registra tenant, operação, provider,
início/fim, status, volume processado, tentativas, erros/códigos, correlation_id e o responsável.
`log_call` (síncrono) permanece para o rastro leve por requisição HTTP; `record` (assíncrono)
persiste o evento operacional.
"""
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger("mig.audit")

COLLECTION = "mig_audit_events"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


class MigAuditService:
    def __init__(self, db=None):
        self.db = db

    def log_call(self, provider: str, method: str, path: str, status_code: int,
                 correlation_id: str = None):
        logger.info("MIG_CALL %s", {"provider": provider, "method": method, "path": path,
                                    "status": status_code, "correlation_id": correlation_id})

    async def record(self, event: dict) -> dict:
        """Persiste um evento operacional. Nunca inclua segredos (api_key/chaves)."""
        doc = {
            "id": str(uuid.uuid4()),
            "correlation_id": event.get("correlation_id"),
            "provider": event.get("provider", "generic"),
            "tenant": event.get("tenant"),
            "operation": event.get("operation"),
            "actor": event.get("actor"),
            "status": event.get("status"),                    # success | error
            "started_at": event.get("started_at"),
            "finished_at": event.get("finished_at") or _now_iso(),
            "duration_ms": event.get("duration_ms"),
            "records_processed": event.get("records_processed", 0),
            "attempts": event.get("attempts", 1),
            "http_status": event.get("http_status"),
            "error_code": event.get("error_code"),
            "error_message": event.get("error_message"),
            # Feature flags / metadados
            "environment": event.get("environment"),
            "feature": event.get("feature"),
            "previous_value": event.get("previous_value"),
            "new_value": event.get("new_value"),
            # Simulação (Sprint 002.a) — cenário executado + flag de origem simulada
            "scenario": event.get("scenario"),
            "simulated": event.get("simulated", False),
            # Preparação futura CMDE (Sprint 002) — default 0/None
            "records_sent": event.get("records_sent", 0),
            "records_accepted": event.get("records_accepted", 0),
            "records_rejected": event.get("records_rejected", 0),
            "rejection_reasons": event.get("rejection_reasons"),
            "created_at": _now_iso(),
        }
        if self.db is not None:
            try:
                await self.db[COLLECTION].insert_one(dict(doc))
            except Exception as e:
                logger.warning("MIG audit persist failed: %s", e)
        doc.pop("_id", None)
        return doc

    def _build_filter(self, provider=None, tenant=None, status=None, operation=None,
                      date_from=None, date_to=None):
        q = {}
        if provider:
            q["provider"] = provider
        if tenant:
            q["tenant"] = tenant
        if status:
            q["status"] = status
        if operation:
            q["operation"] = operation
        if date_from or date_to:
            rng = {}
            if date_from:
                rng["$gte"] = date_from
            if date_to:
                rng["$lte"] = date_to
            q["created_at"] = rng
        return q

    async def recent(self, provider=None, tenant=None, limit=50):
        if self.db is None:
            return []
        q = self._build_filter(provider=provider, tenant=tenant)
        return await self.db[COLLECTION].find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)

    async def query_events(self, provider=None, tenant=None, status=None, operation=None,
                           date_from=None, date_to=None, page=1, page_size=50):
        if self.db is None:
            return {"events": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 0}
        q = self._build_filter(provider, tenant, status, operation, date_from, date_to)
        page = max(1, int(page))
        page_size = min(max(1, int(page_size)), 200)
        total = await self.db[COLLECTION].count_documents(q)
        events = await self.db[COLLECTION].find(q, {"_id": 0}).sort("created_at", -1) \
            .skip((page - 1) * page_size).limit(page_size).to_list(page_size)
        return {
            "events": events, "total": total, "page": page, "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        }

    async def metrics(self, provider=None, tenant=None) -> dict:
        empty = {
            "total_calls": 0, "success": 0, "error": 0, "success_rate": None,
            "avg_latency_ms": None, "volume_processed": 0, "last_execution": None,
            "recent_failures": [],
            # Preparação futura CMDE (Sprint 002)
            "students_sent": 0, "students_accepted": 0, "students_rejected": 0,
            "processing_rate": None,
        }
        if self.db is None:
            return empty
        match = self._build_filter(provider=provider, tenant=tenant)
        pipeline = [
            {"$match": match},
            {"$group": {
                "_id": None,
                "total_calls": {"$sum": 1},
                "success": {"$sum": {"$cond": [{"$eq": ["$status", "success"]}, 1, 0]}},
                "error": {"$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}},
                "avg_latency_ms": {"$avg": "$duration_ms"},
                "volume_processed": {"$sum": {"$ifNull": ["$records_processed", 0]}},
                "students_sent": {"$sum": {"$ifNull": ["$records_sent", 0]}},
                "students_accepted": {"$sum": {"$ifNull": ["$records_accepted", 0]}},
                "students_rejected": {"$sum": {"$ifNull": ["$records_rejected", 0]}},
                "last_execution": {"$max": "$finished_at"},
            }},
        ]
        agg = await self.db[COLLECTION].aggregate(pipeline).to_list(1)
        if not agg:
            return empty
        r = agg[0]
        total = r.get("total_calls", 0) or 0
        success = r.get("success", 0) or 0
        sent = r.get("students_sent", 0) or 0
        accepted = r.get("students_accepted", 0) or 0
        failures = await self.db[COLLECTION].find(
            {**match, "status": "error"},
            {"_id": 0, "id": 1, "correlation_id": 1, "operation": 1, "finished_at": 1,
             "http_status": 1, "error_code": 1, "error_message": 1}
        ).sort("created_at", -1).to_list(10)
        return {
            "total_calls": total,
            "success": success,
            "error": r.get("error", 0) or 0,
            "success_rate": round(success / total * 100, 1) if total else None,
            "avg_latency_ms": round(r["avg_latency_ms"], 1) if r.get("avg_latency_ms") is not None else None,
            "volume_processed": r.get("volume_processed", 0) or 0,
            "last_execution": r.get("last_execution"),
            "recent_failures": failures,
            "students_sent": sent,
            "students_accepted": accepted,
            "students_rejected": r.get("students_rejected", 0) or 0,
            "processing_rate": round(accepted / sent * 100, 1) if sent else None,
        }
