"""MigAuditService — registro estruturado de chamadas a provedores (sem expor segredos).

Fundação: log estruturado. Persistência em coleção dedicada fica para a sprint de infra.
"""
import logging

logger = logging.getLogger("mig.audit")


class MigAuditService:
    def log_call(self, provider: str, method: str, path: str, status_code: int, extra: dict = None):
        payload = {"provider": provider, "method": method, "path": path, "status": status_code}
        if extra:
            # Nunca logar segredos (api_key, chaves). Chamador é responsável por não passá-los.
            payload.update(extra)
        logger.info("MIG_CALL %s", payload)
