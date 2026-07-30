"""
BaseGovClient — cliente HTTP base, ÚNICA porta de saída HTTP para provedores governamentais.

Responsabilidade: transporte (timeout, headers, logging estruturado, tradução de erros
para exceções tipadas do MIG). NÃO contém regra de negócio.
"""
import logging
import httpx

from mig.core.exceptions import (
    MigAuthError, MigForbiddenError, MigUpstreamError,
    MigUnavailableError, MigTimeoutError,
)
from mig.core.monitoring import MigMonitoring
from mig.core.audit import MigAuditService

logger = logging.getLogger("mig.http")


class BaseGovClient:
    def __init__(self, base_url: str, default_headers: dict = None, timeout: float = 30.0,
                 monitoring: MigMonitoring = None, audit: MigAuditService = None,
                 provider: str = "generic"):
        self.base_url = (base_url or "").rstrip("/")
        self.default_headers = default_headers or {}
        self.timeout = timeout
        self.monitoring = monitoring or MigMonitoring()
        self.audit = audit or MigAuditService()
        self.provider = provider

    async def request(self, method: str, path: str, *, params: dict = None,
                      json: dict = None, headers: dict = None) -> dict:
        url = f"{self.base_url}{path}" if path.startswith("/") else f"{self.base_url}/{path}"
        merged = {**self.default_headers, **(headers or {})}
        self.monitoring.incr(f"{self.provider}.request")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.request(method, url, params=params, json=json, headers=merged)
        except httpx.TimeoutException as e:
            self.monitoring.incr(f"{self.provider}.timeout")
            logger.warning("MIG upstream timeout provider=%s method=%s path=%s", self.provider, method, path)
            raise MigTimeoutError("Tempo limite ao consultar a API do MEC. Tente novamente.") from e
        except httpx.ConnectError as e:
            self.monitoring.incr(f"{self.provider}.connect_error")
            logger.warning("MIG upstream connect error provider=%s path=%s", self.provider, path)
            raise MigUnavailableError("Não foi possível conectar à API do MEC. Verifique a configuração de rede.") from e

        self.audit.log_call(self.provider, method, path, resp.status_code)
        if resp.status_code == 200:
            self.monitoring.incr(f"{self.provider}.ok")
            try:
                return resp.json()
            except Exception:
                return {"raw": resp.text}
        self.monitoring.incr(f"{self.provider}.http_{resp.status_code}")
        if resp.status_code == 401:
            raise MigAuthError("Chave de API inválida ou expirada. Verifique a configuração.")
        if resp.status_code == 403:
            raise MigForbiddenError("Acesso negado pela API do MEC. Verifique se o IP do servidor está autorizado.")
        raise MigUpstreamError(f"Erro na API do MEC (HTTP {resp.status_code}): {resp.text[:200]}",
                               status_code=resp.status_code)

    async def get(self, path: str, **kwargs) -> dict:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs) -> dict:
        return await self.request("POST", path, **kwargs)
