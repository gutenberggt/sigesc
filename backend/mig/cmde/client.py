"""
CmdeClient — cliente HTTP ÚNICO do CMDE. Compõe BaseGovClient com autenticação Bearer,
resolução de ambiente e política de retentativa. NÃO contém regra de negócio.
"""
from mig.core.http_client import BaseGovClient
from mig.core.feature_flags import FeatureFlags
from mig.core.retry import CMDE_DEFAULT, NO_RETRY


class CmdeClient:
    def __init__(self, environment: str, api_key: str, audit=None, monitoring=None,
                 retry_enabled: bool = True, correlation_id: str = None):
        base_url = FeatureFlags.resolve_cmde_base_url(environment)
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self._http = BaseGovClient(base_url=base_url, default_headers=headers, timeout=30.0,
                                   provider="cmde", audit=audit, monitoring=monitoring,
                                   retry_policy=CMDE_DEFAULT if retry_enabled else NO_RETRY,
                                   correlation_id=correlation_id)

    @property
    def last_attempts(self) -> int:
        return self._http.last_attempts

    async def elegibilidade_por_documento(self, documento: str) -> dict:
        clean = documento.replace(".", "").replace("-", "").strip()
        return await self._http.get(f"/elegibilidades/{clean}")

    async def elegibilidade_por_inep(self, inep: str) -> dict:
        return await self._http.get(f"/elegibilidades/inep/{inep}")

    async def elegibilidades_paginadas(self, page: int, page_size: int) -> dict:
        return await self._http.get("/elegibilidades", params={"page": page, "size": page_size})
