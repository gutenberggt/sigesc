"""
FeatureFlags — resolução de ambiente e flags dinâmicas do MIG (por tenant/ambiente).

- `resolve_cmde_base_url` (estático): ambiente → URL base do CMDE.
- `FeatureFlagService` (dinâmico): flags persistidas em `db.mig_feature_flags` com resolução
  hierárquica: override por (tenant, environment) > por (tenant) > por (environment) > global > default.
  Habilita ativação gradual, testes controlados e novos recursos do MIG sem deploy.
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger("mig.flags")

CMDE_ENVIRONMENTS = {
    "homologacao": "https://api-cmde.hmg.gestaopresente.mec.gov.br/v1",
    "producao": "https://api-cmde.gestaopresente.mec.gov.br/v1",
}

# Flags padrão (comportamento neutro: tudo habilitado — preserva o funcionamento atual)
DEFAULT_FLAGS = {
    "cmde.enabled": True,
    "cmde.elegibilidades": True,
    "cmde.retry": True,
}

COLLECTION = "mig_feature_flags"


class FeatureFlags:
    @staticmethod
    def resolve_cmde_base_url(environment: str) -> str:
        return CMDE_ENVIRONMENTS.get(environment or "homologacao",
                                     CMDE_ENVIRONMENTS["homologacao"])


class FeatureFlagService:
    def __init__(self, db=None):
        self.db = db

    async def _overrides(self, flag: str):
        if self.db is None:
            return []
        return await self.db[COLLECTION].find({"flag": flag}, {"_id": 0}).to_list(200)

    async def is_enabled(self, flag: str, tenant: str = None, environment: str = None) -> bool:
        default = DEFAULT_FLAGS.get(flag, False)
        overrides = await self._overrides(flag)
        if not overrides:
            return default
        # resolução hierárquica: mais específico vence
        def match(o, want_tenant, want_env):
            return o.get("tenant") == want_tenant and o.get("environment") == want_env
        for wt, we in [(tenant, environment), (tenant, None), (None, environment), (None, None)]:
            for o in overrides:
                if match(o, wt, we):
                    return bool(o.get("enabled"))
        return default

    async def effective(self, tenant: str = None, environment: str = None) -> dict:
        result = {}
        for flag in DEFAULT_FLAGS:
            result[flag] = await self.is_enabled(flag, tenant, environment)
        return result

    async def set_flag(self, flag: str, enabled: bool, tenant: str = None,
                       environment: str = None, actor: str = None) -> dict:
        if self.db is None:
            return {}
        key = {"flag": flag, "tenant": tenant, "environment": environment}
        doc = {**key, "enabled": bool(enabled), "actor": actor,
               "updated_at": datetime.now(timezone.utc).isoformat()}
        await self.db[COLLECTION].update_one(key, {"$set": doc}, upsert=True)
        return doc
