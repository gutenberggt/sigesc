"""ValidationEngine — validação declarativa de prontidão de registros (agnóstica de provider).

Cada regra: (nome_campo_faltante, predicado). Retorna lista de campos faltantes.
"""
from typing import Callable, List, Tuple, Any, Dict


class ValidationEngine:
    def __init__(self, rules: List[Tuple[str, Callable[[Dict[str, Any]], bool]]]):
        # rules: (missing_label, is_present_predicate)
        self.rules = rules

    def missing_fields(self, record: Dict[str, Any]) -> List[str]:
        return [label for label, is_present in self.rules if not is_present(record)]

    def is_ready(self, record: Dict[str, Any]) -> bool:
        return len(self.missing_fields(record)) == 0
