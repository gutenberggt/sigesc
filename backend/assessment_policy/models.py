"""Contratos puros da Assessment Policy Multi-Mantenedora v1.

Este módulo NÃO acessa MongoDB, HTTP, autenticação ou qualquer motor legado.
Ele define apenas a estrutura versionada da política avaliativa.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PolicyStatus(str, Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"
    RETIRED = "retired"


class AssessmentMode(str, Enum):
    NUMERIC = "numeric"
    CONCEPTUAL = "conceptual"
    DESCRIPTIVE = "descriptive"
    SKILL_BASED = "skill_based"


class CalculationStrategy(str, Enum):
    SIMPLE_AVERAGE = "simple_average"
    WEIGHTED_AVERAGE = "weighted_average"


class PartialDivisorStrategy(str, Enum):
    SUM_AVAILABLE_WEIGHTS = "sum_available_weights"
    SUM_ALL_WEIGHTS = "sum_all_weights"


class FinalDivisorStrategy(str, Enum):
    SUM_ALL_WEIGHTS = "sum_all_weights"


class RoundingMode(str, Enum):
    HALF_UP = "half_up"


class RecoveryStrategy(str, Enum):
    REPLACE_LOWEST = "replace_lowest"


class RecoveryTieBreak(str, Enum):
    HIGHEST_WEIGHT = "highest_weight"
    EARLIEST_PERIOD = "earliest_period"
    LATEST_PERIOD = "latest_period"


class AttendanceBasis(str, Enum):
    GLOBAL = "global"
    COMPONENT = "component"
    STAGE = "stage"


class ComponentOutcomeStrategy(str, Enum):
    """Estratégia de rendimento por componentes suportada pela Outcome v1."""

    ALL_REQUIRED_COMPONENTS = "all_required_components"


class DependencyMode(str, Enum):
    """Modos acadêmicos já existentes no domínio StudentDependency."""

    WITH_DEPENDENCY = "with_dependency"
    DEPENDENCY_ONLY = "dependency_only"


class PolicyScope(BaseModel):
    """Dimensões de aplicabilidade.

    `None` significa "sem restrição nesta dimensão". Lista vazia é rejeitada
    para evitar políticas que parecem publicadas, mas nunca podem resolver.
    """

    model_config = ConfigDict(extra="forbid")

    school_ids: Optional[List[str]] = None
    class_ids: Optional[List[str]] = None
    series: Optional[List[str]] = None
    component_ids: Optional[List[str]] = None
    education_stages: Optional[List[str]] = None
    modalities: Optional[List[str]] = None

    @field_validator(
        "school_ids",
        "class_ids",
        "series",
        "component_ids",
        "education_stages",
        "modalities",
    )
    @classmethod
    def validate_scope_list(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        if not value:
            raise ValueError("use None para representar ausência de restrição; lista vazia é inválida")
        cleaned = [str(item).strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("itens de escopo não podem ser vazios")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("itens de escopo não podem ser duplicados")
        return cleaned


class ConceptScaleEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=120)
    numeric_value: float

    @field_validator("code", "label")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("valor textual obrigatório")
        return value


class NumericScale(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum: float
    maximum: float
    decimal_places: int = Field(default=1, ge=0, le=4)

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.maximum <= self.minimum:
            raise ValueError("maximum deve ser maior que minimum")
        return self


class PeriodRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=120)
    weight: float = Field(gt=0)
    required_for_final: bool = True

    @field_validator("code", "label")
    @classmethod
    def strip_period_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("valor textual obrigatório")
        return value


class CalculationRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: CalculationStrategy
    partial_divisor: PartialDivisorStrategy = PartialDivisorStrategy.SUM_AVAILABLE_WEIGHTS
    final_divisor: FinalDivisorStrategy = FinalDivisorStrategy.SUM_ALL_WEIGHTS
    rounding_mode: RoundingMode = RoundingMode.HALF_UP
    decimal_places: int = Field(default=2, ge=0, le=4)


class AssessmentRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: AssessmentMode
    conceptual_scale: Optional[List[ConceptScaleEntry]] = None
    numeric_scale: Optional[NumericScale] = None
    periods: List[PeriodRule] = Field(default_factory=list)
    calculation: Optional[CalculationRule] = None

    @model_validator(mode="after")
    def validate_mode_contract(self):
        if self.mode == AssessmentMode.CONCEPTUAL:
            if not self.conceptual_scale:
                raise ValueError("modo conceptual exige conceptual_scale")
            if not self.periods:
                raise ValueError("modo conceptual exige periods")
            if self.calculation is None:
                raise ValueError("modo conceptual exige calculation")
        elif self.mode == AssessmentMode.NUMERIC:
            if self.numeric_scale is None:
                raise ValueError("modo numeric exige numeric_scale")
            if not self.periods:
                raise ValueError("modo numeric exige periods")
            if self.calculation is None:
                raise ValueError("modo numeric exige calculation")
        return self


class RecoveryGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=120)
    input_code: str = Field(min_length=1, max_length=32)
    period_codes: List[str] = Field(min_length=1)
    strategy: RecoveryStrategy = RecoveryStrategy.REPLACE_LOWEST
    tie_break: RecoveryTieBreak = RecoveryTieBreak.HIGHEST_WEIGHT
    only_if_improves: Optional[bool] = None

    @field_validator("code", "label", "input_code")
    @classmethod
    def strip_recovery_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("valor textual obrigatório")
        return value

    @field_validator("period_codes")
    @classmethod
    def validate_period_codes(cls, value: List[str]) -> List[str]:
        cleaned = [str(item).strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("period_codes não pode conter item vazio")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("period_codes não pode conter duplicidade")
        return cleaned


class RecoveryRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    groups: List[RecoveryGroup] = Field(default_factory=list)


class CouncilRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    can_override_academic_result: bool = False
    requires_reason: bool = True
    requires_audit_event: bool = True


class DependencyOutcomeRange(BaseModel):
    """Faixa explícita de componentes não atingidos para um modo de dependência."""

    model_config = ConfigDict(extra="forbid")

    mode: DependencyMode
    min_failed_components: int = Field(ge=1)
    max_failed_components: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_range(self):
        if (
            self.max_failed_components is not None
            and self.max_failed_components < self.min_failed_components
        ):
            raise ValueError("max_failed_components não pode ser menor que min_failed_components")
        return self


class DependencyRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    outcomes: List[DependencyOutcomeRange] = Field(default_factory=list)


class AcademicOutcomeRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum_component_average: Optional[float] = None
    # Compatibilidade temporária com o schema Foundation. Na Outcome v1,
    # `False` não recebe semântica implícita e é rejeitado pelo validator.
    require_all_components: bool = True
    component_strategy: ComponentOutcomeStrategy = (
        ComponentOutcomeStrategy.ALL_REQUIRED_COMPONENTS
    )
    minimum_attendance_percentage: Optional[float] = Field(default=None, ge=0, le=100)
    attendance_basis: Optional[AttendanceBasis] = None
    dependency: DependencyRule = Field(default_factory=DependencyRule)
    council: CouncilRule = Field(default_factory=CouncilRule)


class NormativeSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    reference: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("type", "title")
    @classmethod
    def strip_normative_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("valor textual obrigatório")
        return value


class ParentPolicyRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_id: str
    version: int = Field(ge=1)
    rule_hash: str


class AssessmentPolicy(BaseModel):
    """Versão persistível da política avaliativa.

    Uma versão `published` deve ser tratada como imutável pelo Registry.
    `revision` é controle de concorrência otimista e não integra o hash da regra.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    policy_key: str = Field(min_length=1, max_length=120)
    version: int = Field(ge=1)
    mantenedora_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=255)
    status: PolicyStatus = PolicyStatus.DRAFT
    revision: int = Field(default=1, ge=1)

    academic_year: int = Field(ge=1900, le=2200)
    effective_from: date
    effective_until: date

    scope: PolicyScope = Field(default_factory=PolicyScope)
    assessment: AssessmentRule
    recovery: RecoveryRule = Field(default_factory=RecoveryRule)
    academic_outcome: AcademicOutcomeRule = Field(default_factory=AcademicOutcomeRule)
    normative_sources: List[NormativeSource] = Field(default_factory=list)
    parent_policy: Optional[ParentPolicyRef] = None

    rule_hash: Optional[str] = None

    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    validated_by: Optional[str] = None
    validated_at: Optional[datetime] = None
    published_by: Optional[str] = None
    published_at: Optional[datetime] = None

    @field_validator("policy_key", "mantenedora_id", "name")
    @classmethod
    def strip_policy_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("valor textual obrigatório")
        return value

    @model_validator(mode="after")
    def validate_effective_period(self):
        if self.effective_until < self.effective_from:
            raise ValueError("effective_until não pode ser anterior a effective_from")
        if not (self.effective_from.year <= self.academic_year <= self.effective_until.year):
            raise ValueError("academic_year deve estar contido no intervalo de vigência")
        return self
