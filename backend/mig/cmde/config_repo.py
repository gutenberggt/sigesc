"""
CmdeConfigRepository — acesso exclusivo à coleção db.mec_integration.

Isola persistência da regra de negócio. Nunca expõe segredos (chave privada / campos PGP).
DECISÃO Sprint 000 (aprovada, opção b): PGP não é persistido; qualquer campo pgp_* legado é
descartado na leitura para não vazar.
"""
from datetime import datetime, timezone

# Campos públicos de config (sem PGP — decisão Sprint 000)
DEFAULT_CONFIG = {
    "environment": "homologacao",
    "api_key": "",
    "server_ip": "",
    "responsible_name": "",
    "responsible_email": "",
    "responsible_cpf": "",
    "responsible_phone": "",
    "responsible_role": "",
    "status": "not_configured",
    "last_sync": None,
}

# Campos que NUNCA devem ser retornados ao cliente
_SENSITIVE_OR_LEGACY = ["pgp_private_key", "pgp_public_key", "_has_private_key"]


class CmdeConfigRepository:
    def __init__(self, db):
        self.db = db

    async def get_raw(self):
        return await self.db.mec_integration.find_one({}, {"_id": 0})

    async def get_public_config(self):
        config = await self.get_raw()
        if not config:
            return dict(DEFAULT_CONFIG)
        for k in _SENSITIVE_OR_LEGACY:
            config.pop(k, None)
        config.pop("updated_at", None)
        config.pop("last_sync_type", None)
        return config

    async def update_config(self, update_data: dict) -> str:
        update_data = dict(update_data)
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        existing = await self.get_raw() or {}
        has_key = bool(update_data.get("api_key") or existing.get("api_key"))
        update_data["status"] = "configured" if has_key else "pending"
        await self.db.mec_integration.update_one({}, {"$set": update_data}, upsert=True)
        return update_data["status"]

    async def touch_last_sync(self, sync_type: str):
        await self.db.mec_integration.update_one(
            {}, {"$set": {"last_sync": datetime.now(timezone.utc).isoformat(),
                          "last_sync_type": sync_type}}
        )
