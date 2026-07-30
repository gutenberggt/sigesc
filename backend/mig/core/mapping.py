"""MappingEngine (base) — utilidades de tradução campo↔campo SIGESC ↔ provider.

Fundação: helper simples de projeção. Mappers específicos (ex.: CmdeMapper) o utilizam.
"""
from typing import Dict, Any, List, Tuple


class MappingEngine:
    @staticmethod
    def project(record: Dict[str, Any], field_map: List[Tuple[str, str]]) -> Dict[str, Any]:
        """field_map: lista de (campo_origem, campo_destino)."""
        return {dst: record.get(src) for src, dst in field_map}
