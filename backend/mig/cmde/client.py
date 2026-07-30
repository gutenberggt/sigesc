"""
CmdeClient — cliente HTTP ÚNICO do CMDE. Compõe BaseGovClient com autenticação Bearer e
resolução de ambiente. NÃO contém regra de negócio (apenas endpoints do provedor).
"""
from mig.core.http_client import BaseGovClient
from mig.core.feature_flags import FeatureFlags


class CmdeClient:
    def __init__(self, environment: str, api_key: str):
        base_url = FeatureFlags.resolve_cmde_base_url(environment)
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self._http = BaseGovClient(base_url=base_url, default_headers=headers,
                                   timeout=30.0, provider="cmde")

    async def elegibilidade_por_documento(self, documento: str) -> dict:
        clean = documento.replace(".", "").replace("-", "").strip()
        return await self._http.get(f"/elegibilidades/{clean}")

    async def elegibilidade_por_inep(self, inep: str) -> dict:
        return await self._http.get(f"/elegibilidades/inep/{inep}")

    async def elegibilidades_paginadas(self, page: int, page_size: int) -> dict:
        return await self._http.get("/elegibilidades", params={"page": page, "size": page_size})
