"""
FrequencyScheduler — acionamento periódico do FrequencyWorker (Sprint 002.e).

Responsabilidade ÚNICA: orquestrar a execução do Worker. NÃO conhece regra de negócio, Queue,
RetryManager, Provider nem comunicação com o MEC — apenas dispara o Worker (via runner injetável)
respeitando feature flag, janela operacional e lock por tenant, auditando cada disparo.

- OFF por padrão em produção (flag `cmde.frequency.scheduler_enabled` = False no default).
- Ativação SOMENTE por feature flag, habilitável por tenant.
- Janela operacional configurável por tenant.
- Lock por tenant (compare-and-set atômico) impede execuções simultâneas.
- Provider ativo permanece o Simulador CMDE (via FrequencyWorker padrão) — nenhuma chamada real ao MEC.
"""
import uuid
from datetime import datetime, timezone, timedelta

from mig.core.feature_flags import FeatureFlagService
from mig.core.audit import MigAuditService
from mig.core.monitoring import MigMonitoring
from mig.core.ids import generate_correlation_id

COLLECTION = "mig_cmde_scheduler"
FLAG = "cmde.frequency.scheduler_enabled"


def _now():
    return datetime.now(timezone.utc)


def _iso(dt=None):
    return (dt or _now()).isoformat()


class FrequencyScheduler:
    def __init__(self, db, worker_runner=None, flags=None, audit=None, monitoring=None,
                 interval_seconds: int = 300, lock_ttl_seconds: int = 120):
        self.db = db
        self.col = db[COLLECTION]
        self._worker_runner = worker_runner          # injetável (testes); default = FrequencyWorker
        self.flags = flags or FeatureFlagService(db)
        self.audit = audit or MigAuditService(db)
        self.monitoring = monitoring or MigMonitoring()
        self.interval_seconds = interval_seconds
        self.lock_ttl = lock_ttl_seconds

    async def _run_worker(self, tenant, max_items):
        if self._worker_runner is not None:
            return await self._worker_runner(tenant, max_items)
        from mig.cmde.worker import FrequencyWorker
        return await FrequencyWorker(self.db).run(tenant, max_items=max_items)

    # ---- Config por tenant ----
    async def get_config(self, tenant, environment=None) -> dict:
        doc = await self.col.find_one({"tenant": tenant, "environment": environment}, {"_id": 0})
        return doc or {"tenant": tenant, "environment": environment}

    async def set_config(self, tenant, environment=None, window_start=None, window_end=None,
                         interval_seconds=None, max_items=None) -> dict:
        set_doc = {"updated_at": _iso()}
        for k, v in [("window_start", window_start), ("window_end", window_end),
                     ("interval_seconds", interval_seconds), ("max_items", max_items)]:
            if v is not None:
                set_doc[k] = v
        await self.col.update_one({"tenant": tenant, "environment": environment},
                                  {"$set": set_doc,
                                   "$setOnInsert": {"tenant": tenant, "environment": environment}},
                                  upsert=True)
        return await self.get_config(tenant, environment)

    def _within_window(self, cfg, now) -> bool:
        ws, we = cfg.get("window_start"), cfg.get("window_end")
        if ws is None or we is None:
            return True
        h = now.hour
        return (ws <= h < we) if ws <= we else (h >= ws or h < we)

    # ---- Lock (compare-and-set atômico) ----
    async def _acquire_lock(self, tenant, environment, now):
        await self.col.update_one({"tenant": tenant, "environment": environment},
                                  {"$setOnInsert": {"tenant": tenant, "environment": environment}},
                                  upsert=True)
        now_iso = now.isoformat()
        owner = str(uuid.uuid4())
        res = await self.col.update_one(
            {"tenant": tenant, "environment": environment,
             "$or": [{"lock_until": None}, {"lock_until": {"$exists": False}},
                     {"lock_until": {"$lt": now_iso}}]},
            {"$set": {"lock_until": _iso(now + timedelta(seconds=self.lock_ttl)),
                      "lock_owner": owner, "updated_at": now_iso}})
        return owner if res.modified_count == 1 else None

    async def _release_lock(self, tenant, environment, owner):
        await self.col.update_one({"tenant": tenant, "environment": environment, "lock_owner": owner},
                                  {"$set": {"lock_until": None, "updated_at": _iso()}})

    # ---- Tick (um ciclo) ----
    async def tick(self, tenant, environment=None, max_items=None, now=None, manual=False) -> dict:
        now = now or _now()
        if not manual and not await self.flags.is_enabled(FLAG, tenant, environment):
            return {"status": "disabled", "tenant": tenant, "flag": FLAG}
        cfg = await self.get_config(tenant, environment)
        if not manual and not self._within_window(cfg, now):
            return {"status": "outside_window", "tenant": tenant,
                    "window": [cfg.get("window_start"), cfg.get("window_end")]}
        owner = await self._acquire_lock(tenant, environment, now)
        if not owner:
            return {"status": "locked", "tenant": tenant}
        correlation_id = generate_correlation_id("SCHED")
        try:
            self.monitoring.incr("scheduler.tick")
            summary = await self._run_worker(tenant, max_items or cfg.get("max_items"))
            interval = cfg.get("interval_seconds") or self.interval_seconds
            next_run = _iso(now + timedelta(seconds=interval))
            await self.col.update_one(
                {"tenant": tenant, "environment": environment},
                {"$set": {"last_run": now.isoformat(), "next_run": next_run,
                          "last_result": summary, "last_status": "ran",
                          "last_correlation_id": correlation_id, "updated_at": now.isoformat()}})
            await self.audit.record({
                "provider": "cmde", "operation": "SCHEDULER_TICK", "tenant": tenant,
                "actor": "scheduler(manual)" if manual else "scheduler", "status": "success",
                "started_at": now.isoformat(), "finished_at": _iso(), "duration_ms": 0,
                "environment": environment, "correlation_id": correlation_id,
                "records_processed": summary.get("processed", 0),
                "records_accepted": summary.get("success", 0),
                "records_rejected": summary.get("failed", 0) + summary.get("dead_letter", 0)})
            return {"status": "ran", "tenant": tenant, "summary": summary,
                    "next_run": next_run, "correlation_id": correlation_id}
        finally:
            await self._release_lock(tenant, environment, owner)

    # ---- Visão de status (Dashboard) ----
    async def status_view(self, tenant, environment=None) -> dict:
        enabled = await self.flags.is_enabled(FLAG, tenant, environment)
        cfg = await self.get_config(tenant, environment)
        return {
            "status": "ON" if enabled else "OFF", "enabled": enabled, "flag": FLAG,
            "tenant": tenant, "environment": environment,
            "last_run": cfg.get("last_run"), "next_run": cfg.get("next_run"),
            "last_result": cfg.get("last_result"), "last_status": cfg.get("last_status"),
            "window": [cfg.get("window_start"), cfg.get("window_end")],
            "interval_seconds": cfg.get("interval_seconds") or self.interval_seconds,
            "provider": "simulator",
        }
