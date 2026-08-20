"""Detecção de conflitos de publicação alinhada ao Policy Resolver."""

from __future__ import annotations

from typing import Optional, Protocol, Sequence

from .models import AssessmentPolicy, PolicyScope, PolicyStatus
from .resolver import policy_specificity
from .series_resolver import normalize_series


class ConflictPolicyRepository(Protocol):
    async def list_by_tenant(
        self,
        mantenedora_id: str,
        *,
        academic_year: Optional[int] = None,
        statuses: Optional[Sequence[PolicyStatus]] = None,
    ) -> Sequence[AssessmentPolicy]: ...


def _exact_overlap(left: Optional[Sequence[str]], right: Optional[Sequence[str]]) -> bool:
    if left is None or right is None:
        return True
    return bool({str(item).strip() for item in left} & {str(item).strip() for item in right})


def _text_overlap(left: Optional[Sequence[str]], right: Optional[Sequence[str]]) -> bool:
    if left is None or right is None:
        return True
    left_set = {normalize_series(item) for item in left if normalize_series(item)}
    right_set = {normalize_series(item) for item in right if normalize_series(item)}
    return bool(left_set & right_set)


def scopes_overlap(left: PolicyScope, right: PolicyScope) -> bool:
    """True quando existe ao menos um contexto capaz de satisfazer ambos."""
    return all(
        (
            _exact_overlap(left.school_ids, right.school_ids),
            _exact_overlap(left.class_ids, right.class_ids),
            _text_overlap(left.series, right.series),
            _exact_overlap(left.component_ids, right.component_ids),
            _text_overlap(left.education_stages, right.education_stages),
            _text_overlap(left.modalities, right.modalities),
        )
    )


def effective_periods_overlap(left: AssessmentPolicy, right: AssessmentPolicy) -> bool:
    if int(left.academic_year) != int(right.academic_year):
        return False
    return max(left.effective_from, right.effective_from) <= min(
        left.effective_until,
        right.effective_until,
    )


def policies_conflict_for_resolution(
    candidate: AssessmentPolicy,
    published: AssessmentPolicy,
) -> bool:
    """Conflito existe somente se a sobreposição puder gerar empate real.

    Overrides com especificidade diferente são permitidos: o Resolver possui
    precedência determinística. Igual especificidade + escopo/vigência
    sobrepostos seria ambíguo e deve ser barrado antes da publicação.
    """
    if candidate.mantenedora_id != published.mantenedora_id:
        return False
    if candidate.id == published.id:
        return False
    if published.status != PolicyStatus.PUBLISHED:
        return False
    if not effective_periods_overlap(candidate, published):
        return False
    if not scopes_overlap(candidate.scope, published.scope):
        return False
    return policy_specificity(candidate.scope) == policy_specificity(published.scope)


class AssessmentPolicyConflictChecker:
    """Checker real que libera o Registry para publicação segura."""

    def __init__(self, repository: ConflictPolicyRepository):
        self.repository = repository

    async def find_publish_conflicts(self, policy: AssessmentPolicy) -> Sequence[str]:
        published = await self.repository.list_by_tenant(
            policy.mantenedora_id,
            academic_year=policy.academic_year,
            statuses=[PolicyStatus.PUBLISHED],
        )
        conflicts = [
            item.id
            for item in published
            if policies_conflict_for_resolution(policy, item)
        ]
        return tuple(sorted(set(conflicts)))
