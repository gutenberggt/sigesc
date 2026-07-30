"""
BaseGovClient — cliente HTTP base, ÚNICA porta de saída HTTP para provedores governamentais.

Responsabilidade: transporte (timeout, headers, logging estruturado, tradução de erros para
exceções tipadas, retentativa via RetryPolicy). NÃO contém regra de negócio.
"""
import logging
import httpx

from mig.core.exceptions import (
    MigAuthError, MigForbiddenError, MigUpstreamError,
    MigUnavailableError, MigTimeoutError,
)
from mig.core.monitoring import MigMonitoring
from mig.core.audit import MigAuditService
from mig.core.retry import RetryPolicy, NO_RETRY, run_with_retry

logger = logging.getLogger("mig.http")


class BaseGovClient:
    def __init__(self, base_url: str, default_headers: dict = None, timeout: float = 30.0,
                 monitoring: MigMonitoring = None, audit: MigAuditService = None,
                 provider: str = "generic", retry_policy: RetryPolicy = None):
        self.base_url = (base_url or "").rstrip("/")
        self.default_headers = default_headers or {}
        self.timeout = timeout
        self.monitoring = monitoring or MigMonitoring()
        self.audit = audit or MigAuditService()
        self.provider = provider
        self.retry_policy = retry_policy or NO_RETRY
        self.last_attempts = 0

    async def _single_request(self, method: str, url: str, params, json, merged) -> dict:
        self.monitoring.incr(f"{self.provider}.request")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.request(method, url, params=params, json=json, headers=merged)
        except httpx.TimeoutException as e:
            self.monitoring.incr(f"{self.provider}.timeout")
            raise MigTimeoutError("Tempo limite ao consultar a API do MEC. Tente novamente.") from e
        except httpx.ConnectError as e:
            self.monitoring.incr(f"{self.provider}.connect_error")
            raise MigUnavailableError("Não foi possível conectar à API do MEC. Verifique a configuração de rede.") from e

        self.audit.log_call(self.provider, method, url, resp.status_code)
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

    async def request(self, method: str, path: str, *, params: dict = None,
                      json: dict = None, headers: dict = None) -> dict:
        url = f"{self.base_url}{path}" if path.startswith("/") else f"{self.base_url}/{path}"
        merged = {**self.default_headers, **(headers or {})}

        def _on_attempt(attempt, exc, recoverable):
            self.monitoring.incr(f"{self.provider}.retry" if recoverable else f"{self.provider}.fatal")

        result = await run_with_retry(
            lambda: self._single_request(method, url, params, json, merged),
            self.retry_policy, on_attempt=_on_attempt,
        )
        self.last_attempts = result.attempts
        return result.value

    async def get(self, path: str, **kwargs) -> dict:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs) -> dict:
        return await self.request("POST", path, **kwargs)
