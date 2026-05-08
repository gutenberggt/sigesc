"""
Enums centralizados de Dependência de Estudos.

[Fev/2026] P1b — exigência operacional do owner.

Antes desta consolidação, strings de status/type estavam soltas em:
- models.py (Literal inline)
- student_dependencies.py (sets locais)
- diary_loader.py / dependency_validator.py
- frontend (string literals)

Risco eliminado:
- Maiusculização inconsistente (`ACTIVE`, `Active`, `active`, `ativo`).
- Variantes de tipo (`with-dependency`, `withDependency`, `with_dependency`).
- Filtros divergentes em relatórios.
- Índices Mongo perdendo eficiência por valor não normalizado.

Princípio: **toda string de status/type passa por aqui antes de gravar/comparar.**
"""
from __future__ import annotations

from typing import Literal

# ---------------------------------------------------------------------------
# CONGELADO — não acrescentar/remover sem bumpar contract_version do Diário.
# ---------------------------------------------------------------------------
DEPENDENCY_STATUS_VALUES: tuple[str, ...] = (
    "active",
    "completed",
    "failed",
    "cancelled",
)
DependencyStatus = Literal["active", "completed", "failed", "cancelled"]

DEPENDENCY_TYPE_VALUES: tuple[str, ...] = (
    "none",            # aluno sem dependência (default students)
    "with_dependency",
    "dependency_only",
)
DependencyType = Literal["none", "with_dependency", "dependency_only"]


# ---------------------------------------------------------------------------
# Mapas de normalização — aceita variações históricas e converte para o canônico.
# ---------------------------------------------------------------------------
_STATUS_ALIASES: dict[str, str] = {
    # status
    "active": "active",
    "ativo": "active",
    "ativa": "active",
    "completed": "completed",
    "concluida": "completed",
    "concluído": "completed",
    "concluida": "completed",
    "concluido": "completed",
    "finalizado": "completed",
    "failed": "failed",
    "reprovado": "failed",
    "reprovada": "failed",
    "falhou": "failed",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "cancelada": "cancelled",
    "cancelado": "cancelled",
}

_TYPE_ALIASES: dict[str, str] = {
    "none": "none",
    "nenhum": "none",
    "nenhuma": "none",
    "without": "none",
    "with_dependency": "with_dependency",
    "with-dependency": "with_dependency",
    "withdependency": "with_dependency",
    "com_dependencia": "with_dependency",
    "com-dependencia": "with_dependency",
    "comdependencia": "with_dependency",
    "dependency_only": "dependency_only",
    "dependency-only": "dependency_only",
    "dependencyonly": "dependency_only",
    "apenas_dependencia": "dependency_only",
    "apenas-dependencia": "dependency_only",
    "apenasdependencia": "dependency_only",
}


# ---------------------------------------------------------------------------
def normalize_dependency_status(value: object) -> DependencyStatus | None:
    """Converte qualquer variação para um valor canônico de DEPENDENCY_STATUS.

    - Retorna `None` se `value` é vazio/None.
    - Retorna o valor canônico se reconhece.
    - **Levanta `ValueError`** se a string não tem mapeamento — falha rápida e ruidosa.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Status de dependência deve ser str, recebeu {type(value).__name__}")
    if not value.strip():
        return None
    key = value.strip().lower()
    mapped = _STATUS_ALIASES.get(key)
    if mapped is None:
        raise ValueError(
            f"Status de dependência desconhecido: '{value}'. "
            f"Esperado um de {DEPENDENCY_STATUS_VALUES}."
        )
    return mapped  # type: ignore[return-value]


def normalize_dependency_type(value: object) -> DependencyType | None:
    """Idem para DEPENDENCY_TYPE."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Tipo de dependência deve ser str, recebeu {type(value).__name__}")
    if not value.strip():
        return None
    key = value.strip().lower()
    mapped = _TYPE_ALIASES.get(key)
    if mapped is None:
        raise ValueError(
            f"Tipo de dependência desconhecido: '{value}'. "
            f"Esperado um de {DEPENDENCY_TYPE_VALUES}."
        )
    return mapped  # type: ignore[return-value]


def validate_dependency_status(value: object) -> DependencyStatus:
    """Como `normalize_dependency_status` mas exige valor não-vazio e canônico."""
    norm = normalize_dependency_status(value)
    if norm is None:
        raise ValueError("Status de dependência obrigatório.")
    return norm


def validate_dependency_type(value: object) -> DependencyType:
    """Como `normalize_dependency_type` mas exige valor não-vazio e canônico."""
    norm = normalize_dependency_type(value)
    if norm is None:
        raise ValueError("Tipo de dependência obrigatório.")
    return norm


# ---------------------------------------------------------------------------
# Helpers semânticos para uso em filtros e checks.
# ---------------------------------------------------------------------------
def is_active_status(value: object) -> bool:
    """True somente para o status canônico 'active' (ignora None/erro)."""
    try:
        return normalize_dependency_status(value) == "active"
    except ValueError:
        return False
