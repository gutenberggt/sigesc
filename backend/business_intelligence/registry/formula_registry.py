"""FormulaRegistry — implementação em memória do registro de definições.

Objetivo: ser o ponto ÚNICO onde toda fórmula/indicador "nasce" (Registry First).
Responsabilidade: guardar/servir IndicatorDefinition com suporte a versionamento
e ativação/desativação. NÃO calcula nada. NÃO conhece indicadores concretos.

Uso previsto:
    registry = FormulaRegistry()
    registry.register(minha_definicao)          # em sprints futuras
    definicao = registry.get("IND-FREQ")         # versão ACTIVE

Open/Closed: novos indicadores entram por `register` — o Motor não muda.
Extensibilidade: uma futura implementação `MongoFormulaRegistry(IRegistry)` pode
substituir esta sem alterar o Engine (bastando trocar no container/DI).
"""
from __future__ import annotations
from typing import Optional

from ..interfaces.ports import IRegistry
from ..contracts.definitions import IndicatorDefinition
from ..models.enums import IndicatorStatus
from .errors import (
    IndicatorNotFoundError, DuplicateDefinitionError, NoActiveVersionError,
)


class FormulaRegistry(IRegistry):
    """Registro em memória (base). Thread-safety/persistência: sprints futuras."""

    def __init__(self) -> None:
        # code -> { version -> IndicatorDefinition }
        self._defs: dict[str, dict[int, IndicatorDefinition]] = {}

    def register(self, definition: IndicatorDefinition) -> None:
        versions = self._defs.setdefault(definition.code, {})
        if definition.version in versions:
            raise DuplicateDefinitionError(
                f"{definition.code}@{definition.version} já registrado"
            )
        versions[definition.version] = definition

    def get(self, code: str, version: Optional[int] = None) -> IndicatorDefinition:
        versions = self._defs.get(code)
        if not versions:
            raise IndicatorNotFoundError(f"Indicador '{code}' não encontrado")
        if version is not None:
            if version not in versions:
                raise IndicatorNotFoundError(f"{code}@{version} não encontrado")
            return versions[version]
        # versão ACTIVE de maior número
        actives = [
            d for d in versions.values() if d.status == IndicatorStatus.ACTIVE
        ]
        if not actives:
            raise NoActiveVersionError(f"Sem versão ACTIVE para '{code}'")
        return max(actives, key=lambda d: d.version)

    def list(self, *, category: Optional[str] = None, active_only: bool = True) -> list:
        out: list[IndicatorDefinition] = []
        for versions in self._defs.values():
            for d in versions.values():
                if active_only and d.status != IndicatorStatus.ACTIVE:
                    continue
                if category and d.category.value != category:
                    continue
                out.append(d)
        return out

    def versions(self, code: str) -> list:
        versions = self._defs.get(code, {})
        return sorted(versions.keys())

    def exists(self, code: str, version: Optional[int] = None) -> bool:
        versions = self._defs.get(code)
        if not versions:
            return False
        return True if version is None else (version in versions)
