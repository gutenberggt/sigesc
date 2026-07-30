"""
GovProvider — interface que futuros órgãos (CMDE e outros) implementam.

Habilita o SIGESC a suportar múltiplas integrações governamentais reutilizando o core.
CMDE é a primeira implementação (mig/cmde/service.py).
"""
from abc import ABC, abstractmethod
from typing import Any, Dict


class GovProvider(ABC):
    name: str = "generic"

    @abstractmethod
    async def get_config(self) -> Dict[str, Any]: ...

    @abstractmethod
    async def update_config(self, data: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    async def sync_status(self) -> Dict[str, Any]: ...

    @abstractmethod
    async def query(self, **kwargs) -> Dict[str, Any]: ...
