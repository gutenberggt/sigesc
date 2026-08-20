"""Policy Resolver determinístico da Assessment Policy v1.

O algoritmo de seleção é puro e não conhece FastAPI, autenticação ou o motor de
Notas. Um adapter/repository fornece somente políticas publicadas candidatas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional, Protocol, Sequence

from .canonical import calculate_rule_hash
from .exceptions import (
    AssessmentPolicyError,
    POLICY_AMBIGUOUS,
    POLICY_INTEGRITY_ERROR,
    POLICY_REQUIRED,
)
from .models import AssessmentPolicy, PolicyScope, PolicyStatus
from .series_resolver import normalize_series


@dataclass(frozen=True)
class AssessmentPolicyContext:
    mantenedora_id: str
    school_id: str
    class_id: str
    student_id: str
    academic_year: int
    reference_date: date
    student_series: str
    component_id: Optional[str] = None
    education_stage: Optional[str] = None
    modality: Optional[str] = None


@dataclass(frozen=True)
class ResolvedAssessmentPolicy:
    policy: AssessmentPolicy
    specificity: tuple[int, int]
    matched_dimensions: tuple[str, ...]


class ResolverPolicyRepository(Protocol):
    async def list_published_candidates(
        self,
        mantenedora_id: str,
        *,
        academic_year: int,
        reference_date: date,
    ) -> Sequence[AssessmentPolicy]: ...


def _exact_member(value: Optional[str], allowed: Optional[Sequence[str]]) -> bool:
    if allowed is None:
        return True
    if value is None:
        return False
    target = str(value).strip()
    return any(str(item).strip() == target for item in allowed)


def _text_member(value: Optional[str], allowed: Optional[Sequence[str]]) -> bool:
    if allowed is None:
        return True
    normalized = normalize_series(value)
    if not normalized:
        return False
    return any(normalize_series(item) == normalized for item in allowed)


def scope_matches_context(scope: PolicyScope, context: AssessmentPolicyContext) -> bool:
    return all(
        (
            _exact_member(context.school_id, scope.school_ids),
            _exact_member(context.class_id, scope.class_ids),
            _text_member(context.student_series, scope.series),
            _exact_member(context.component_id, scope.component_ids),
            _text_member(context.education_stage, scope.education_stages),
            _text_member(context.modality, scope.modalities),
        )
    )


def policy_specificity(scope: PolicyScope) -> tuple[int, int]:
    """Retorna `(tier_administrativo, restrições_contextuais)`.

    O tamanho da lista nunca desempata. O que importa é a dimensão ter sido
    explicitamente restringida, evitando que sobreposições sejam arbitradas por
    uma heurística opaca.
    """

    has_class = scope.class_ids is not None
    has_school = scope.school_ids is not None
    has_component = scope.component_ids is not None
    contextual_count = sum(
        dimension is not None
        for dimension in (
            scope.series,
            scope.education_stages,
            scope.modalities,
        )
    )

    if has_class and has_component:
        tier = 7
    elif has_class:
        tier = 6
    elif has_school and has_component:
        tier = 5
    elif has_school:
        tier = 4
    elif has_component:
        tier = 3
    elif contextual_count:
        tier = 2
    else:
        tier = 1

    return tier, contextual_count


def matched_dimensions(scope: PolicyScope) -> tuple[str, ...]:
    names = (
        "school_ids",
        "class_ids",
        "series",
        "component_ids",
        "education_stages",
        "modalities",
    )
    return tuple(name for name in names if getattr(scope, name) is not None)


def _published_candidate_is_effective(
    policy: AssessmentPolicy,
    context: AssessmentPolicyContext,
) -> bool:
    if policy.mantenedora_id != context.mantenedora_id:
        return False
    if policy.status != PolicyStatus.PUBLISHED:
        return False
    if int(policy.academic_year) != int(context.academic_year):
        return False
    if not (policy.effective_from <= context.reference_date <= policy.effective_until):
        return False
    return scope_matches_context(policy.scope, context)


def _assert_policy_integrity(policy: AssessmentPolicy) -> None:
    calculated = calculate_rule_hash(policy)
    if not policy.rule_hash or policy.rule_hash != calculated:
        raise AssessmentPolicyError(
            POLICY_INTEGRITY_ERROR,
            "A política publicada possui hash ausente ou divergente.",
            details={
                "policy_id": policy.id,
                "policy_key": policy.policy_key,
                "version": policy.version,
                "stored_rule_hash": policy.rule_hash,
                "calculated_rule_hash": calculated,
            },
        )


def resolve_policy_from_candidates(
    context: AssessmentPolicyContext,
    candidates: Iterable[AssessmentPolicy],
) -> ResolvedAssessmentPolicy:
    """Seleciona exatamente uma política efetiva ou falha fechado."""

    applicable: list[tuple[tuple[int, int], AssessmentPolicy]] = []
    for policy in candidates:
        if not _published_candidate_is_effective(policy, context):
            continue
        _assert_policy_integrity(policy)
        applicable.append((policy_specificity(policy.scope), policy))

    if not applicable:
        raise AssessmentPolicyError(
            POLICY_REQUIRED,
            "Nenhuma política avaliativa publicada é aplicável ao contexto informado.",
            details={
                "mantenedora_id": context.mantenedora_id,
                "school_id": context.school_id,
                "class_id": context.class_id,
                "student_id": context.student_id,
                "component_id": context.component_id,
                "academic_year": context.academic_year,
                "reference_date": context.reference_date.isoformat(),
                "student_series": context.student_series,
            },
        )

    best_score = max(score for score, _ in applicable)
    winners = [policy for score, policy in applicable if score == best_score]
    if len(winners) != 1:
        raise AssessmentPolicyError(
            POLICY_AMBIGUOUS,
            "Mais de uma política igualmente específica resolve o mesmo contexto.",
            details={
                "specificity": list(best_score),
                "policy_ids": sorted(policy.id for policy in winners),
            },
        )

    winner = winners[0]
    return ResolvedAssessmentPolicy(
        policy=winner,
        specificity=best_score,
        matched_dimensions=matched_dimensions(winner.scope),
    )


class AssessmentPolicyResolver:
    """Orquestrador read-only sobre o algoritmo puro de resolução."""

    def __init__(self, repository: ResolverPolicyRepository):
        self.repository = repository

    async def resolve(self, context: AssessmentPolicyContext) -> ResolvedAssessmentPolicy:
        candidates = await self.repository.list_published_candidates(
            context.mantenedora_id,
            academic_year=context.academic_year,
            reference_date=context.reference_date,
        )
        return resolve_policy_from_candidates(context, candidates)
