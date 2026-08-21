"""Fundação canônica do AEE v2.

Fase 1: contratos e projeção não destrutiva do legado.
"""

from .contracts import AEEDossierV2, AEELegacyProjection
from .legacy_mapper import evaluate_minimum_gaps, project_legacy_plan

__all__ = [
    "AEEDossierV2",
    "AEELegacyProjection",
    "evaluate_minimum_gaps",
    "project_legacy_plan",
]
