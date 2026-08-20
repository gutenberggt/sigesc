"""Assessment Policy Multi-Mantenedora v1.

Foundation + Resolver: contratos, lifecycle, contexto e resolução read-only.
Nenhum módulo deste pacote substitui o motor de Notas nesta etapa.
"""

from .canonical import calculate_rule_hash, canonical_rule_json, canonical_rule_payload
from .conflict_checker import (
    AssessmentPolicyConflictChecker,
    policies_conflict_for_resolution,
    scopes_overlap,
)
from .context_builder import build_assessment_policy_context
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
from .resolver import (
    AssessmentPolicyContext,
    AssessmentPolicyResolver,
    ResolvedAssessmentPolicy,
    policy_specificity,
    resolve_policy_from_candidates,
    scope_matches_context,
)
from .series_resolver import (
    EffectiveStudentSeries,
    is_multi_grade_class,
    normalize_series,
    resolve_effective_student_series,
)
from .validator import PolicyValidationIssue, PolicyValidationReport, validate_policy

__all__ = [
    "ASSESSMENT_POLICY_INDEXES",
    "AcademicOutcomeRule",
    "AssessmentMode",
    "AssessmentPolicy",
    "AssessmentPolicyConflictChecker",
    "AssessmentPolicyContext",
    "AssessmentPolicyError",
    "AssessmentPolicyRegistry",
    "AssessmentPolicyRepository",
    "AssessmentPolicyResolver",
    "AssessmentRule",
    "AttendanceBasis",
    "CalculationRule",
    "CalculationStrategy",
    "ConceptScaleEntry",
    "CouncilRule",
    "EffectiveStudentSeries",
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
    "ResolvedAssessmentPolicy",
    "build_assessment_policy_context",
    "calculate_rule_hash",
    "canonical_rule_json",
    "canonical_rule_payload",
    "is_multi_grade_class",
    "normalize_series",
    "policies_conflict_for_resolution",
    "policy_specificity",
    "resolve_effective_student_series",
    "resolve_policy_from_candidates",
    "scope_matches_context",
    "scopes_overlap",
    "validate_policy",
]
