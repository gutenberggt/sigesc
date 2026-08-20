"""Assessment Policy Multi-Mantenedora v1.

Foundation only: contratos, canonicalização, validação, repository e lifecycle.
Nenhum módulo deste pacote é ligado às rotas de notas na Sprint 001.
"""

from .canonical import calculate_rule_hash, canonical_rule_json, canonical_rule_payload
from .exceptions import AssessmentPolicyError
from .indexes import ASSESSMENT_POLICY_INDEXES, IndexSpec
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
from .registry import AssessmentPolicyRegistry, PolicyConflictChecker, PolicyRepository
from .repository import AssessmentPolicyRepository
from .validator import PolicyValidationIssue, PolicyValidationReport, validate_policy

__all__ = [
    "ASSESSMENT_POLICY_INDEXES",
    "AcademicOutcomeRule",
    "AssessmentMode",
    "AssessmentPolicy",
    "AssessmentPolicyError",
    "AssessmentPolicyRegistry",
    "AssessmentPolicyRepository",
    "AssessmentRule",
    "AttendanceBasis",
    "CalculationRule",
    "CalculationStrategy",
    "ConceptScaleEntry",
    "CouncilRule",
    "IndexSpec",
    "NormativeSource",
    "NumericScale",
    "ParentPolicyRef",
    "PeriodRule",
    "PolicyConflictChecker",
    "PolicyRepository",
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
