"""Contratos canônicos do Dossiê AEE v2.

Fase 1: especificação aditiva e não destrutiva.
Nenhum modelo deste módulo substitui, nesta fase, os documentos legados persistidos
em ``planos_aee``. O objetivo é estabelecer um contrato estável para projeção,
validação gradual e futura persistência versionada do Estudo de Caso, PAEE e PEI.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


SectionState = Literal["legacy_projected", "in_progress", "complete", "not_applicable"]
LifecycleStatus = Literal["draft", "active", "review", "closed", "cancelled"]
AssessmentStatus = Literal[
    "not_assessed",
    "not_needed",
    "needed",
    "provided",
    "unavailable",
]


class AEEV2BaseModel(BaseModel):
    """Base compatível com evolução aditiva do contrato."""

    model_config = ConfigDict(extra="ignore", validate_assignment=True)


class AEEAccessibilityResource(AEEV2BaseModel):
    tipo: Optional[str] = None
    descricao: str
    disponivel: Optional[bool] = None


class AEEObjective(AEEV2BaseModel):
    descricao: str
    prazo: Optional[str] = None
    status: Optional[str] = None
    indicadores: list[str] = Field(default_factory=list)


class AEESupportAssessment(AEEV2BaseModel):
    """Avaliação pedagógica de necessidade/organização de apoio.

    ``not_assessed`` é deliberadamente diferente de ``not_needed`` para impedir
    que ausência de informação legada seja interpretada como dispensa do apoio.
    """

    status: AssessmentStatus = "not_assessed"
    justificativa: Optional[str] = None
    capacidade_disponibilizacao: Optional[str] = None
    observacoes: Optional[str] = None


class AEEScheduleSession(AEEV2BaseModel):
    weekday: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    local: Optional[str] = None
    modalidade: Optional[str] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None


class AEEStudyCase(AEEV2BaseModel):
    """Estudo de Caso — etapa inicial que fundamenta PAEE e PEI."""

    state: SectionState = "in_progress"
    fundamentacao_pedagogica_identificacao: Optional[str] = None
    demanda_inicial_contexto: Optional[str] = None
    barreiras_contexto: list[str] = Field(default_factory=list)
    potencialidades: Optional[str] = None
    demandas_apoio: Optional[str] = None
    comunicacao_participacao: Optional[str] = None
    estrategias_recursos_acessibilidade: list[str] = Field(default_factory=list)

    # Participação deve poder ser registrada sem presumir que já ocorreu.
    participacao_estudante: Optional[str] = None
    contribuicoes_estudante: Optional[str] = None
    contribuicoes_familia: Optional[str] = None

    # Diálogo intersetorial somente quando necessário.
    articulacao_rede_protecao: list[str] = Field(default_factory=list)


class AEEPAEE(AEEV2BaseModel):
    """Plano de Atendimento Educacional Especializado."""

    state: SectionState = "in_progress"
    barreiras_prioritarias: list[str] = Field(default_factory=list)
    objetivos: list[AEEObjective] = Field(default_factory=list)
    materiais_recursos: list[AEEAccessibilityResource] = Field(default_factory=list)

    tecnologia_assistiva: AEESupportAssessment = Field(default_factory=AEESupportAssessment)
    comunicacao_aumentativa_alternativa: AEESupportAssessment = Field(
        default_factory=AEESupportAssessment
    )
    profissional_apoio_escolar: AEESupportAssessment = Field(
        default_factory=AEESupportAssessment
    )
    tradutor_interprete_libras: AEESupportAssessment = Field(
        default_factory=AEESupportAssessment
    )
    guia_interprete: AEESupportAssessment = Field(default_factory=AEESupportAssessment)

    demandas_formacao_educacao_especial_inclusiva: list[str] = Field(default_factory=list)
    acionamentos_rede_protecao: list[str] = Field(default_factory=list)

    indicadores_progresso: Optional[str] = None
    frequencia_revisao: Optional[str] = None
    criterios_ajuste: Optional[str] = None


class AEEPEI(AEEV2BaseModel):
    """Plano Educacional Individualizado / acessibilização curricular."""

    state: SectionState = "in_progress"

    atividades_aee: list[str] = Field(default_factory=list)
    articulacao_sala_comum: Optional[str] = None
    combinados_professor_regente: Optional[str] = None

    acessibilidade_curricular: Optional[str] = None
    acessibilidade_didatico_pedagogica: Optional[str] = None
    acessibilidade_avaliativa: Optional[str] = None
    adaptacoes_por_componente: Optional[str] = None

    estrategias_acompanhamento_monitoramento: Optional[str] = None
    devolutivas_familia: list[str] = Field(default_factory=list)


class AEESchedule(AEEV2BaseModel):
    carga_horaria_semanal: Optional[str] = None
    sessions: list[AEEScheduleSession] = Field(default_factory=list)


class AEELifecycle(AEEV2BaseModel):
    status: LifecycleStatus = "draft"
    version: int = 2
    elaborated_at: Optional[str] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    review_at: Optional[str] = None
    periodo_vigencia_legacy: Optional[str] = None


class AEELegacyProvenance(AEEV2BaseModel):
    migrated_from_legacy_aee: bool = True
    projection_mode: Literal["legacy_projection", "native_v2"] = "legacy_projection"
    legacy_plano_id: Optional[str] = None
    legacy_status: Optional[str] = None
    template_origin_id: Optional[str] = None

    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AEEDossierV2(AEEV2BaseModel):
    """Documento canônico unificado do AEE v2.

    O contrato unifica a navegação e o ciclo de vida, mas mantém Estudo de Caso,
    PAEE e PEI como seções semanticamente distintas.
    """

    schema_version: Literal[2] = 2

    student_id: str
    school_id: str
    academic_year: int

    professor_aee_responsavel_id: Optional[str] = None
    professor_aee_responsavel_nome: Optional[str] = None

    publico_alvo: Optional[str] = None

    turma_origem_id: Optional[str] = None
    turma_origem_nome: Optional[str] = None
    escola_origem_nome: Optional[str] = None
    professor_regente_id: Optional[str] = None
    professor_regente_nome: Optional[str] = None

    study_case: AEEStudyCase = Field(default_factory=AEEStudyCase)
    paee: AEEPAEE = Field(default_factory=AEEPAEE)
    pei: AEEPEI = Field(default_factory=AEEPEI)
    schedule: AEESchedule = Field(default_factory=AEESchedule)
    lifecycle: AEELifecycle = Field(default_factory=AEELifecycle)
    provenance: AEELegacyProvenance = Field(default_factory=AEELegacyProvenance)


class AEEMappingGap(AEEV2BaseModel):
    section: Literal["study_case", "paee", "pei", "schedule", "lifecycle", "legacy"]
    code: str
    field: str
    description: str
    severity: Literal["required", "recommended", "audit"] = "required"


class AEELegacyMappingReport(AEEV2BaseModel):
    legacy_plano_id: Optional[str] = None
    consumed_fields: list[str] = Field(default_factory=list)
    unmapped_nonempty_fields: list[str] = Field(default_factory=list)
    gaps: list[AEEMappingGap] = Field(default_factory=list)


class AEELegacyProjection(AEEV2BaseModel):
    dossier: AEEDossierV2
    report: AEELegacyMappingReport
