"""
CmdeService — orquestrador dos casos de uso da Integração MEC Gestão Presente (CMDE).

GovProvider do CMDE. Não faz HTTP direto (usa CmdeClient) e não conhece transporte.
Sprint 001: cada operação de integração é auditada de forma persistente (MigAuditService),
respeita feature flags dinâmicas e usa retentativa. Métricas são derivadas do audit (SSoT).
"""
import time
from datetime import datetime, timezone
from typing import Optional

from mig.providers.base import GovProvider
from mig.core.exceptions import MigConfigError, MigForbiddenError, MigError
from mig.core.audit import MigAuditService
from mig.core.monitoring import MigMonitoring
from mig.core.feature_flags import FeatureFlagService
from mig.core.ids import generate_correlation_id
from mig.cmde.config_repo import CmdeConfigRepository
from mig.cmde.client import CmdeClient
from mig.cmde.mapper import CmdeMapper
from mig.cmde.dtos import MecConfigUpdateDTO, FrequencyBatchRequestDTO
from mig.cmde.batch_builder import FrequencyBatchBuilder

_ACTIVE_STATUSES = ["active", "Ativo"]
PROVIDER = "cmde"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


class CmdeService(GovProvider):
    name = "cmde"

    def __init__(self, db):
        self.db = db
        self.config_repo = CmdeConfigRepository(db)
        self.audit = MigAuditService(db)
        self.monitoring = MigMonitoring()
        self.flags = FeatureFlagService(db)
        self.batch_builder = FrequencyBatchBuilder(db)

    # ---- Configuração ----
    async def get_config(self) -> dict:
        return await self.config_repo.get_public_config()

    async def update_config(self, body: dict, context: dict = None) -> dict:
        allowed = set(MecConfigUpdateDTO.model_fields.keys())
        update_data = {k: v for k, v in (body or {}).items() if k in allowed}
        status = await self.config_repo.update_config(update_data)
        ctx = context or {}
        await self.audit.record({
            "provider": PROVIDER, "operation": "config_update", "tenant": ctx.get("tenant"),
            "actor": ctx.get("actor"), "status": "success", "started_at": _now_iso(),
            "finished_at": _now_iso(), "duration_ms": 0, "records_processed": 0,
        })
        return {"message": "Configuração atualizada com sucesso", "status": status}

    # ---- Status ----
    async def sync_status(self) -> dict:
        config = await self.config_repo.get_raw()
        total_active = await self.db.students.count_documents({"status": {"$in": _ACTIVE_STATUSES}})
        with_cpf = await self.db.students.count_documents({"status": {"$in": _ACTIVE_STATUSES}, "cpf": {"$ne": ""}})
        with_nis = await self.db.students.count_documents({"status": {"$in": _ACTIVE_STATUSES}, "nis": {"$ne": ""}})
        total_schools = await self.db.schools.count_documents({})
        with_inep = await self.db.schools.count_documents({"inep_code": {"$ne": ""}})
        return {
            "status": (config or {}).get("status", "not_configured"),
            "environment": (config or {}).get("environment", "homologacao"),
            "last_sync": (config or {}).get("last_sync"),
            "details": {
                "students_total": total_active, "students_with_cpf": with_cpf,
                "students_with_nis": with_nis, "schools_total": total_schools,
                "schools_with_inep": with_inep,
            },
        }

    # ---- Mapeamento de alunos ----
    async def students_mapping(self, school_id: Optional[str] = None) -> dict:
        query = {"status": {"$in": _ACTIVE_STATUSES}}
        if school_id:
            query["school_id"] = school_id
        students = await self.db.students.find(
            query,
            {"_id": 0, "id": 1, "full_name": 1, "cpf": 1, "nis": 1, "inep_code": 1,
             "school_id": 1, "class_id": 1, "birth_date": 1}
        ).sort("full_name", 1).to_list(10000)
        school_ids = list(set(s.get("school_id") for s in students if s.get("school_id")))
        schools = await self.db.schools.find(
            {"id": {"$in": school_ids}}, {"_id": 0, "id": 1, "name": 1, "inep_code": 1}
        ).to_list(1000)
        school_map = {s["id"]: s for s in schools}
        result = [CmdeMapper.build_mapping_row(s, school_map.get(s.get("school_id"), {})) for s in students]
        total = len(result)
        ready = sum(1 for r in result if r["ready"])
        return {"students": result, "total": total, "ready_count": ready, "not_ready_count": total - ready}

    # ---- Consulta de elegibilidades (única saída HTTP; auditada + retry + flag) ----
    async def query(self, search: Optional[str] = None, inep: Optional[str] = None,
                    page: int = 1, page_size: int = 50, context: dict = None) -> dict:
        ctx = context or {}
        tenant = ctx.get("tenant")
        started = _now_iso()
        t0 = time.perf_counter()

        config = await self.config_repo.get_raw()
        if not config or not config.get("api_key"):
            raise MigConfigError("Integração MEC não configurada. Configure a chave de API primeiro.")

        environment = config.get("environment", "homologacao")
        if not await self.flags.is_enabled("cmde.elegibilidades", tenant, environment):
            raise MigForbiddenError("Recurso de elegibilidades desabilitado por feature flag para este contexto.")

        correlation_id = generate_correlation_id("CMDE")
        retry_enabled = await self.flags.is_enabled("cmde.retry", tenant, environment)
        client = CmdeClient(environment=environment, api_key=config.get("api_key"),
                            audit=self.audit, monitoring=self.monitoring,
                            retry_enabled=retry_enabled, correlation_id=correlation_id)

        try:
            if search:
                data = await client.elegibilidade_por_documento(search)
            elif inep:
                data = await client.elegibilidade_por_inep(inep)
            else:
                data = await client.elegibilidades_paginadas(page, page_size)
        except MigError as e:
            await self.audit.record({
                "provider": PROVIDER, "operation": "elegibilidades", "tenant": tenant,
                "actor": ctx.get("actor"), "status": "error", "started_at": started,
                "finished_at": _now_iso(), "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
                "records_processed": 0, "attempts": client.last_attempts,
                "http_status": e.status_code, "error_code": type(e).__name__, "error_message": e.message,
                "correlation_id": correlation_id, "environment": environment,
            })
            raise

        await self.config_repo.touch_last_sync("elegibilidades")
        records = len(data) if isinstance(data, list) else (
            len(data.get("data", [])) if isinstance(data, dict) and isinstance(data.get("data"), list) else 1)
        await self.audit.record({
            "provider": PROVIDER, "operation": "elegibilidades", "tenant": tenant,
            "actor": ctx.get("actor"), "status": "success", "started_at": started,
            "finished_at": _now_iso(), "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
            "records_processed": records, "attempts": client.last_attempts, "http_status": 200,
            "correlation_id": correlation_id, "environment": environment,
        })
        return data

    # ---- Camada operacional (Sprint 001) ----
    async def metrics(self, context: dict = None) -> dict:
        ctx = context or {}
        data = await self.audit.metrics(provider=PROVIDER, tenant=ctx.get("tenant"))
        data["runtime_counters"] = self.monitoring.snapshot()
        return data

    async def audit_events(self, context: dict = None, page: int = 1, page_size: int = 50,
                           status: str = None, operation: str = None,
                           date_from: str = None, date_to: str = None) -> dict:
        ctx = context or {}
        return await self.audit.query_events(
            provider=PROVIDER, tenant=ctx.get("tenant"), status=status, operation=operation,
            date_from=date_from, date_to=date_to, page=page, page_size=page_size)

    async def feature_flags(self, context: dict = None) -> dict:
        ctx = context or {}
        config = await self.config_repo.get_raw() or {}
        env = config.get("environment", "homologacao")
        return {"environment": env, "tenant": ctx.get("tenant"),
                "flags": await self.flags.effective(ctx.get("tenant"), env)}

    async def build_frequency_batch(self, request: FrequencyBatchRequestDTO,
                                     context: dict = None) -> dict:
        """Sprint 002.b — constrói lote de frequência a partir do SSoT (read-only)."""
        return await self.batch_builder.build(request, context or {})

    async def set_feature_flag(self, flag: str, enabled: bool, context: dict = None,
                               environment: str = None) -> dict:
        ctx = context or {}
        tenant = ctx.get("tenant")
        env = environment or (await self.config_repo.get_raw() or {}).get("environment", "homologacao")
        previous = await self.flags.is_enabled(flag, tenant, env)
        result = await self.flags.set_flag(flag, enabled, tenant=tenant, environment=env,
                                           actor=ctx.get("actor"))
        # Auditoria da mudança de capacidade (P0 Sprint 001.1)
        await self.audit.record({
            "provider": PROVIDER, "operation": "FEATURE_FLAG_UPDATED", "tenant": tenant,
            "actor": ctx.get("actor"), "status": "success", "started_at": _now_iso(),
            "finished_at": _now_iso(), "duration_ms": 0, "environment": env, "feature": flag,
            "previous_value": bool(previous), "new_value": bool(enabled),
            "correlation_id": generate_correlation_id("FLAG"),
        })
        return result
