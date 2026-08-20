"""Testes da Sprint 007 — configuração assistida."""

from datetime import date

from assessment_policy.assisted_config import (
    ASSISTED_MAPPING_INVALID,
    ASSISTED_STATUS_NOT_EDITABLE,
    AssistedPolicyConfiguration,
    LegacyFieldMappingConfig,
    preview_assisted_configuration,
)
from assessment_policy.models import (
    AcademicOutcomeRule,
    AssessmentMode,
    AssessmentPolicy,
    AssessmentRule,
    AttendanceBasis,
    CalculationRule,
    CalculationStrategy,
    ConceptScaleEntry,
    NormativeSource,
    PeriodRule,
    PolicyScope,
    PolicyStatus,
    RecoveryGroup,
    RecoveryRule,
    RecoveryTieBreak,
)


def _conceptual_policy(*, status=PolicyStatus.DRAFT, normative=True):
    return AssessmentPolicy(
        id="policy-1-2-2026",
        policy_key="EF_1_2_CONCEITUAL_2026",
        version=1,
        mantenedora_id="tenant-a",
        name="1º e 2º Ano — Conceitual — 2026",
        status=status,
        academic_year=2026,
        effective_from=date(2026, 1, 1),
        effective_until=date(2026, 12, 31),
        scope=PolicyScope(series=["1º Ano", "2º Ano"]),
        assessment=AssessmentRule(
            mode=AssessmentMode.CONCEPTUAL,
            conceptual_scale=[
                ConceptScaleEntry(code="C", label="Consolidado", numeric_value=10.0),
                ConceptScaleEntry(code="ED", label="Em Desenvolvimento", numeric_value=7.5),
                ConceptScaleEntry(code="ND", label="Não Desenvolvido", numeric_value=5.0),
            ],
            periods=[
                PeriodRule(code="b1", label="1º Bimestre", weight=2),
                PeriodRule(code="b2", label="2º Bimestre", weight=3),
                PeriodRule(code="b3", label="3º Bimestre", weight=2),
                PeriodRule(code="b4", label="4º Bimestre", weight=3),
            ],
            calculation=CalculationRule(strategy=CalculationStrategy.WEIGHTED_AVERAGE),
        ),
        recovery=RecoveryRule(enabled=False),
        academic_outcome=AcademicOutcomeRule(
            minimum_component_average=5.0,
            minimum_attendance_percentage=75.0,
            attendance_basis=AttendanceBasis.GLOBAL,
        ),
        normative_sources=(
            [
                NormativeSource(
                    type="documento_semed",
                    title="Documento oficial SEMED — política avaliativa 2026",
                    reference="Fonte institucional a ser anexada/identificada no cadastro.",
                )
            ]
            if normative
            else []
        ),
    )


def _mapping():
    return LegacyFieldMappingConfig(
        period_field_map={"b1": "b1", "b2": "b2", "b3": "b3", "b4": "b4"},
        recovery_field_map={},
    )


def test_complete_conceptual_configuration_is_ready_for_pilot():
    preview = preview_assisted_configuration(
        AssistedPolicyConfiguration(policy=_conceptual_policy(), legacy_mapping=_mapping())
    )

    assert preview.can_save_draft is True
    assert preview.can_validate is True
    assert preview.can_dry_run is True
    assert preview.mapping_hash.startswith("sha256:")
    assert preview.calculated_rule_hash.startswith("sha256:")
    assert not [item for item in preview.issues if item.severity == "error"]


def test_valid_policy_can_validate_without_legacy_mapping_but_cannot_run_pilot():
    preview = preview_assisted_configuration(
        AssistedPolicyConfiguration(
            policy=_conceptual_policy(),
            legacy_mapping=LegacyFieldMappingConfig(),
        )
    )

    assert preview.can_save_draft is True
    assert preview.can_validate is True
    assert preview.can_dry_run is False
    assert preview.mapping_hash is None
    assert any(item.code == ASSISTED_MAPPING_INVALID for item in preview.issues)


def test_missing_normative_source_blocks_validation_and_pilot_but_not_draft_save():
    preview = preview_assisted_configuration(
        AssistedPolicyConfiguration(
            policy=_conceptual_policy(normative=False),
            legacy_mapping=_mapping(),
        )
    )

    assert preview.can_save_draft is True
    assert preview.can_validate is False
    assert preview.can_dry_run is False
    assert any(
        item.code == "ASSESSMENT_POLICY_NORMATIVE_SOURCE_REQUIRED"
        for item in preview.issues
    )


def test_attendance_threshold_without_basis_blocks_pilot():
    policy = _conceptual_policy()
    policy = policy.model_copy(
        update={
            "academic_outcome": policy.academic_outcome.model_copy(
                update={"attendance_basis": None}
            )
        }
    )
    preview = preview_assisted_configuration(
        AssistedPolicyConfiguration(policy=policy, legacy_mapping=_mapping())
    )

    assert preview.can_validate is False
    assert preview.can_dry_run is False
    assert any(
        item.code == "ASSESSMENT_POLICY_ATTENDANCE_CONTRACT_INCOMPLETE"
        for item in preview.issues
    )


def test_recovery_requires_explicit_improvement_decision_and_mapping():
    policy = _conceptual_policy().model_copy(
        update={
            "recovery": RecoveryRule(
                enabled=True,
                groups=[
                    RecoveryGroup(
                        code="recuperacao",
                        label="Recuperação",
                        input_code="rec",
                        period_codes=["b1", "b2", "b3", "b4"],
                        tie_break=RecoveryTieBreak.HIGHEST_WEIGHT,
                        only_if_improves=None,
                    )
                ],
            )
        }
    )
    preview = preview_assisted_configuration(
        AssistedPolicyConfiguration(policy=policy, legacy_mapping=_mapping())
    )

    assert preview.can_validate is False
    assert preview.can_dry_run is False
    assert any(
        item.code == "ASSESSMENT_POLICY_RECOVERY_IMPROVEMENT_RULE_REQUIRED"
        for item in preview.issues
    )
    assert any(item.code == ASSISTED_MAPPING_INVALID for item in preview.issues)


def test_published_policy_is_never_editable_in_assisted_config():
    policy = _conceptual_policy(status=PolicyStatus.PUBLISHED)
    # O teste de status deve ocorrer mesmo que a integridade/hash também gere erro.
    preview = preview_assisted_configuration(
        AssistedPolicyConfiguration(policy=policy, legacy_mapping=_mapping())
    )

    assert preview.can_save_draft is False
    assert preview.can_validate is False
    assert preview.can_dry_run is False
    assert any(item.code == ASSISTED_STATUS_NOT_EDITABLE for item in preview.issues)
