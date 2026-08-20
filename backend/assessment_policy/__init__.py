"""Assessment Policy Multi-Mantenedora v1.

Foundation only: contratos, canonicalização e validação pura.
Nenhum módulo deste pacote é ligado às rotas de notas na Sprint 001.
"""

from .canonical import calculate_rule_hash, canonical_rule_json, canonical_rule_payload
from .models import (
    AcademicOutcomeRule,
    AssessmentMode,
    AssessmentPolicy,
    AssessmentRule,
    AttendanceBasis,
    CalculationRule,
    CalculationStrategy,
    ConceptScaleEntry,
    CouncilRule,
    NormativeSource,
    NumericScale,
    ParentPolicyRef,
    PeriodRule,
    PolicyScope,
    PolicyStatus,
    RecoveryGroup,
    RecoveryRule,
    RecoveryStrategy,
    RecoveryTieBreak,
)
from .validator import PolicyValidationIssue, PolicyValidationReport, validate_policy

__all__ = [
    "AcademicOutcomeRule",
    "AssessmentMode",
    "AssessmentPolicy",
    "AssessmentRule",
    "AttendanceBasis",
    "CalculationRule",
    "CalculationStrategy",
    "ConceptScaleEntry",
    "CouncilRule",
    "NormativeSource",
    "NumericScale",
    "ParentPolicyRef",
    "PeriodRule",
    "PolicyScope",
    "PolicyStatus",
    "PolicyValidationIssue",
    "PolicyValidationReport",
    "RecoveryGroup",
    "RecoveryRule",
    "RecoveryStrategy",
    "RecoveryTieBreak",
    "calculate_rule_hash",
    "canonical_rule_json",
    "canonical_rule_payload",
    "validate_policy",
]
