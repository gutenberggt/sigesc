"""
MigAuditService — auditoria PERSISTENTE de eventos de integração (SSoT operacional do MIG).

Coleção: `mig_audit_events` (append-only). Cada evento registra tenant, operação, provider,
início/fim, status, volume processado, erros/códigos e o responsável (usuário/processo).
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

    # rastro leve por request HTTP (sem persistir; sem segredos)
    def log_call(self, provider: str, method: str, path: str, status_code: int, extra: dict = None):
        payload = {"provider": provider, "method": method, "path": path, "status": status_code}
        if extra:
            payload.update(extra)
        logger.info("MIG_CALL %s", payload)

    async def record(self, event: dict) -> dict:
        """Persiste um evento operacional. Nunca inclua segredos (api_key/chaves)."""
        doc = {
            "id": str(uuid.uuid4()),
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
            "created_at": _now_iso(),
        }
        if self.db is not None:
            try:
                await self.db[COLLECTION].insert_one(dict(doc))
            except Exception as e:
                logger.warning("MIG audit persist failed: %s", e)
        doc.pop("_id", None)
        return doc

    async def recent(self, provider: str = None, tenant: str = None, limit: int = 50):
        if self.db is None:
            return []
        q = {}
        if provider:
            q["provider"] = provider
        if tenant:
            q["tenant"] = tenant
        return await self.db[COLLECTION].find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)

    async def metrics(self, provider: str = None, tenant: str = None) -> dict:
        """Agrega métricas operacionais a partir dos eventos persistidos (SSoT)."""
        empty = {
            "total_calls": 0, "success": 0, "error": 0, "success_rate": None,
            "avg_latency_ms": None, "volume_processed": 0, "last_execution": None,
            "recent_failures": [],
        }
        if self.db is None:
            return empty
        match = {}
        if provider:
            match["provider"] = provider
        if tenant:
            match["tenant"] = tenant
        pipeline = [
            {"$match": match},
            {"$group": {
                "_id": None,
                "total_calls": {"$sum": 1},
                "success": {"$sum": {"$cond": [{"$eq": ["$status", "success"]}, 1, 0]}},
                "error": {"$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}},
                "avg_latency_ms": {"$avg": "$duration_ms"},
                "volume_processed": {"$sum": {"$ifNull": ["$records_processed", 0]}},
                "last_execution": {"$max": "$finished_at"},
            }},
        ]
        agg = await self.db[COLLECTION].aggregate(pipeline).to_list(1)
        if not agg:
            return empty
        r = agg[0]
        total = r.get("total_calls", 0) or 0
        success = r.get("success", 0) or 0
        failures = await self.db[COLLECTION].find(
            {**match, "status": "error"},
            {"_id": 0, "id": 1, "operation": 1, "finished_at": 1, "http_status": 1,
             "error_code": 1, "error_message": 1}
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
        }
