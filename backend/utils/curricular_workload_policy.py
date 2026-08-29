"""Canonical curricular workload policy for selected curriculum components.

P0-F7.9D7.3.1 — single source of truth for annual/weekly workload of
Geografia, História and Ciências across Fundamental/EJA levels.

Rules supplied institutionally on 2026-08-29:
- applicability is determined by component + education level + series/year;
- for multigrade classes, the greatest annual workload among represented
  series prevails;
- canonical annual workloads are 80h or 120h, represented in
  ``teacher_assignments.carga_horaria_semanal`` as 2h or 3h respectively.

This module is pure: no DB, network, FastAPI or write side effects.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from utils.curriculum_resolver import _norm_name, _norm_scalar, _series_tokens

POLICY_PHASE = "P0-F7.9D7.3.1"
POLICY_VERSION = "2026-08-29"
POLICY_SOURCE = "MATRIZ_CURRICULAR_INSTITUCIONAL_2026_08_29"

ANNUAL_TO_WEEKLY = {
    80: 2,
    120: 3,
}

# Keys use curriculum_resolver normalization.
_RULES: dict[str, dict[str, Any]] = {
    "geografia": {
        "fundamental_anos_iniciais": {"default": 80},
        "fundamental_anos_finais": {"series": {6: 120, 7: 80, 8: 80, 9: 80}},
        "eja": {"default": 80},
        "eja_final": {"default": 80},
    },
    "historia": {
        "fundamental_anos_iniciais": {"default": 80},
        "fundamental_anos_finais": {"series": {6: 80, 7: 80, 8: 120, 9: 80}},
        "eja": {"default": 80},
        "eja_final": {"default": 80},
    },
    "ciencias": {
        "fundamental_anos_iniciais": {"default": 80},
        "fundamental_anos_finais": {"series": {6: 80, 7: 120, 8: 80, 9: 120}},
        "eja": {"default": 80},
        "eja_final": {"default": 120},
    },
}

_LEVEL_ALIASES = {
    "fundamental_anos_iniciais": "fundamental_anos_iniciais",
    "fundamental anos iniciais": "fundamental_anos_iniciais",
    "fundamental - anos iniciais": "fundamental_anos_iniciais",
    "ensino fundamental anos iniciais": "fundamental_anos_iniciais",
    "fundamental_anos_finais": "fundamental_anos_finais",
    "fundamental anos finais": "fundamental_anos_finais",
    "fundamental - anos finais": "fundamental_anos_finais",
    "ensino fundamental anos finais": "fundamental_anos_finais",
    "eja": "eja",
    "eja_anos_iniciais": "eja",
    "eja anos iniciais": "eja",
    "eja - anos iniciais": "eja",
    "eja_final": "eja_final",
    "eja_anos_finais": "eja_final",
    "eja anos finais": "eja_final",
    "eja - anos finais": "eja_final",
}


@dataclass(frozen=True)
class CurricularWorkloadPolicyError(ValueError):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


def _component_key(name: Any) -> str:
    return _norm_name(str(name or ""))


def _level_key(level: Any) -> str:
    normalized = _norm_scalar(level)
    return _LEVEL_ALIASES.get(normalized, normalized)


def _series_numbers(value: Any) -> list[int]:
    numbers: set[int] = set()
    for token in _series_tokens(value):
        try:
            numbers.add(int(token.split(":", 1)[1]))
        except (IndexError, TypeError, ValueError):
            continue
    return sorted(numbers)


def resolve_curricular_workload(
    *,
    component_name: Any,
    class_level: Any,
    class_series: Any,
) -> dict[str, Any]:
    """Resolve canonical annual and weekly workload for the institutional matrix.

    Components outside the policy are returned as ``applies=False`` so callers
    can preserve existing behavior. Components covered by the policy fail
    closed when level/series is insufficient to resolve a variable rule.
    """
    component = _component_key(component_name)
    rules_by_level = _RULES.get(component)
    if not rules_by_level:
        return {
            "applies": False,
            "phase": POLICY_PHASE,
            "version": POLICY_VERSION,
            "source": POLICY_SOURCE,
            "component": component,
        }

    level = _level_key(class_level)
    rule = rules_by_level.get(level)
    if not rule:
        raise CurricularWorkloadPolicyError(
            "CURRICULAR_WORKLOAD_LEVEL_UNSUPPORTED",
            f"Nível de ensino sem regra de carga horária para {component_name!s}.",
        )

    series_numbers = _series_numbers(class_series)
    per_series = rule.get("series") or {}
    multigrade = len(series_numbers) > 1

    if per_series:
        if not series_numbers:
            raise CurricularWorkloadPolicyError(
                "CURRICULAR_WORKLOAD_SERIES_REQUIRED",
                "A série/ano da turma é obrigatória para resolver esta carga horária.",
            )
        missing = [number for number in series_numbers if number not in per_series]
        if missing:
            raise CurricularWorkloadPolicyError(
                "CURRICULAR_WORKLOAD_SERIES_UNSUPPORTED",
                f"Série(s) sem regra de carga horária: {missing}.",
            )
        per_series_values = {number: int(per_series[number]) for number in series_numbers}
    else:
        annual_default = rule.get("default")
        if annual_default not in ANNUAL_TO_WEEKLY:
            raise CurricularWorkloadPolicyError(
                "CURRICULAR_WORKLOAD_DEFAULT_INVALID",
                "Carga horária anual canônica ausente ou inválida.",
            )
        if series_numbers:
            per_series_values = {number: int(annual_default) for number in series_numbers}
        else:
            per_series_values = {0: int(annual_default)}

    annual = max(per_series_values.values())
    weekly = ANNUAL_TO_WEEKLY.get(annual)
    if weekly is None:
        raise CurricularWorkloadPolicyError(
            "CURRICULAR_WORKLOAD_WEEKLY_MAPPING_MISSING",
            f"Carga anual {annual}h não possui representação semanal canônica.",
        )

    return {
        "applies": True,
        "phase": POLICY_PHASE,
        "version": POLICY_VERSION,
        "source": POLICY_SOURCE,
        "component": component,
        "class_level": level,
        "series": series_numbers,
        "per_series_annual_workload": per_series_values,
        "multigrade": multigrade,
        "multigrade_rule": "MAX_ANNUAL_WORKLOAD" if multigrade else "SINGLE_SERIES_OR_LEVEL_RULE",
        "canonical_annual_workload": annual,
        "canonical_weekly_workload": weekly,
    }
