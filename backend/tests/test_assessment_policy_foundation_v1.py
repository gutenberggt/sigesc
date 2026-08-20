"""Testes puros da Foundation da Assessment Policy Multi-Mantenedora v1.

Não usa MongoDB e não altera o motor atual de notas.
"""

from datetime import date

import pytest
from pydantic import ValidationError

from assessment_policy import (
    AcademicOutcomeRule,
    AssessmentMode,
    AssessmentPolicy,
    AssessmentRule,
    AttendanceBasis,
    CalculationRule,
    CalculationStrategy,
    ConceptScaleEntry,
    NormativeSource,
    NumericScale,
    PeriodRule,
    PolicyScope,
    RecoveryGroup,
    RecoveryRule,
    calculate_rule_hash,
    validate_policy,
)


def _periods():
    return [
        PeriodRule(code="b1", label="1º Bimestre", weight=2),
        PeriodRule(code="b2", label="2º Bimestre", weight=3),
        PeriodRule(code="b3", label="3º Bimestre", weight=2),
        PeriodRule(code="b4", label="4º Bimestre", weight=3),
    ]


def _floresta_conceptual_policy(**updates):
    policy = AssessmentPolicy(
        id="policy-floresta-1-2-2026-v1",
        policy_key="EF_1_2_CONCEITUAL",
        version=1,
        mantenedora_id="tenant-floresta",
        name="EF — 1º e 2º Ano — 2026",
        academic_year=2026,
        effective_from=date(2026, 1, 1),
        effective_until=date(2026, 12, 31),
        scope=PolicyScope(
            series=["1º Ano", "2º Ano"],
            education_stages=["ensino_fundamental"],
        ),
        assessment=AssessmentRule(
            mode=AssessmentMode.CONCEPTUAL,
            conceptual_scale=[
                ConceptScaleEntry(code="C", label="Consolidado", numeric_value=10.0),
                ConceptScaleEntry(code="ED", label="Em Desenvolvimento", numeric_value=7.5),
                ConceptScaleEntry(code="ND", label="Não Desenvolvido", numeric_value=5.0),
            ],
            periods=_periods(),
            calculation=CalculationRule(
                strategy=CalculationStrategy.WEIGHTED_AVERAGE,
            ),
        ),
        recovery=RecoveryRule(
            enabled=True,
            groups=[
                RecoveryGroup(
                    code="r1",
                    label="Recuperação 1",
                    input_code="rec_s1",
                    period_codes=["b1", "b2"],
                    only_if_improves=True,
                ),
                RecoveryGroup(
                    code="r2",
                    label="Recuperação 2",
                    input_code="rec_s2",
                    period_codes=["b3", "b4"],
                    only_if_improves=True,
                ),
            ],
        ),
        academic_outcome=AcademicOutcomeRule(
            minimum_component_average=5.0,
            minimum_attendance_percentage=75.0,
            attendance_basis=AttendanceBasis.GLOBAL,
        ),
        normative_sources=[
            NormativeSource(
                type="internal_policy",
                title="Política avaliativa formal da mantenedora",
            )
        ],
    )
    return policy.model_copy(update=updates)


def test_floresta_policy_contract_is_valid_for_publish():
    report = validate_policy(_floresta_conceptual_policy(), for_publish=True)

    assert report.valid is True
    assert report.issues == []
    assert report.calculated_rule_hash.startswith("sha256:")


def test_hash_is_deterministic_and_ignores_administrative_metadata():
    original = _floresta_conceptual_policy()
    renamed = original.model_copy(
        update={
            "name": "Outro nome administrativo",
            "created_by": "user-2",
            "normative_sources": [
                NormativeSource(type="regulation", title="Referência administrativa atualizada")
            ],
        }
    )

    assert calculate_rule_hash(original) == calculate_rule_hash(renamed)


def test_hash_changes_when_effective_rule_changes():
    original = _floresta_conceptual_policy()
    changed_assessment = original.assessment.model_copy(
        update={
            "periods": [
                PeriodRule(code="b1", label="1º Bimestre", weight=1),
                PeriodRule(code="b2", label="2º Bimestre", weight=1),
                PeriodRule(code="b3", label="3º Bimestre", weight=1),
                PeriodRule(code="b4", label="4º Bimestre", weight=1),
            ]
        }
    )
    changed = original.model_copy(update={"assessment": changed_assessment})

    assert calculate_rule_hash(original) != calculate_rule_hash(changed)


def test_publish_requires_recovery_improvement_rule_to_be_explicit():
    policy = _floresta_conceptual_policy()
    groups = list(policy.recovery.groups)
    groups[0] = groups[0].model_copy(update={"only_if_improves": None})
    policy = policy.model_copy(
        update={"recovery": policy.recovery.model_copy(update={"groups": groups})}
    )

    report = validate_policy(policy, for_publish=True)

    assert report.valid is False
    assert any(
        issue.code == "ASSESSMENT_POLICY_RECOVERY_IMPROVEMENT_RULE_REQUIRED"
        for issue in report.issues
    )


def test_recovery_cannot_reference_unknown_period():
    policy = _floresta_conceptual_policy()
    groups = list(policy.recovery.groups)
    groups[0] = groups[0].model_copy(update={"period_codes": ["b1", "b9"]})
    policy = policy.model_copy(
        update={"recovery": policy.recovery.model_copy(update={"groups": groups})}
    )

    report = validate_policy(policy)

    assert report.valid is False
    assert any(
        issue.code == "ASSESSMENT_POLICY_RECOVERY_UNKNOWN_PERIOD"
        for issue in report.issues
    )


def test_attendance_percentage_and_basis_are_atomic_contract():
    policy = _floresta_conceptual_policy(
        academic_outcome=AcademicOutcomeRule(
            minimum_component_average=5.0,
            minimum_attendance_percentage=75.0,
            attendance_basis=None,
        )
    )

    report = validate_policy(policy)

    assert report.valid is False
    assert any(
        issue.code == "ASSESSMENT_POLICY_ATTENDANCE_CONTRACT_INCOMPLETE"
        for issue in report.issues
    )


def test_publish_requires_normative_source():
    policy = _floresta_conceptual_policy(normative_sources=[])

    report = validate_policy(policy, for_publish=True)

    assert report.valid is False
    assert any(
        issue.code == "ASSESSMENT_POLICY_NORMATIVE_SOURCE_REQUIRED"
        for issue in report.issues
    )


def test_numeric_policy_does_not_depend_on_conceptual_scale():
    policy = _floresta_conceptual_policy()
    numeric_assessment = AssessmentRule(
        mode=AssessmentMode.NUMERIC,
        numeric_scale=NumericScale(minimum=0, maximum=10, decimal_places=1),
        periods=_periods(),
        calculation=CalculationRule(strategy=CalculationStrategy.WEIGHTED_AVERAGE),
    )
    policy = policy.model_copy(
        update={
            "policy_key": "EF_3_NUMERIC",
            "name": "EF — 3º Ano — 2026",
            "scope": PolicyScope(series=["3º Ano"]),
            "assessment": numeric_assessment,
        }
    )

    report = validate_policy(policy, for_publish=True)

    assert report.valid is True


def test_scope_rejects_empty_list_because_none_means_unrestricted():
    with pytest.raises(ValidationError):
        PolicyScope(series=[])
