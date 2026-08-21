"""Projeção não destrutiva do Plano AEE legado para o Dossiê AEE v2."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contracts import (
    AEEAccessibilityResource,
    AEEDossierV2,
    AEELegacyMappingReport,
    AEELegacyProjection,
    AEELegacyProvenance,
    AEELifecycle,
    AEEMappingGap,
    AEEObjective,
    AEEPAEE,
    AEEPEI,
    AEESchedule,
    AEEScheduleSession,
    AEEStudyCase,
)


LEGACY_STATUS_TO_V2 = {
    "rascunho": "draft",
    "ativo": "active",
    "revisao": "review",
    "encerrado": "closed",
    "cancelado": "cancelled",
}

MAPPED_LEGACY_FIELDS = {
    "id",
    "student_id",
    "school_id",
    "academic_year",
    "professor_aee_id",
    "professor_aee_nome",
    "publico_alvo",
    "criterio_elegibilidade",
    "turma_origem_id",
    "turma_origem_nome",
    "escola_origem_nome",
    "professor_regente_id",
    "professor_regente_nome",
    "data_elaboracao",
    "periodo_vigencia",
    "linha_base_situacao_atual",
    "linha_base_potencialidades",
    "linha_base_dificuldades",
    "linha_base_comunicacao",
    "modalidade",
    "carga_horaria_semanal",
    "dias_atendimento",
    "horario_inicio",
    "horario_fim",
    "local_atendimento",
    "barreiras",
    "objetivos",
    "recursos_acessibilidade",
    "indicadores_progresso",
    "frequencia_revisao",
    "criterios_ajuste",
    "orientacoes_sala_comum",
    "combinados_professor_regente",
    "adequacoes_curriculares",
    "adaptacoes_por_componente",
    "data_inicio",
    "data_revisao",
    "status",
    "template_origin_id",
    "created_by",
    "updated_by",
    "created_at",
    "updated_at",
}

IGNORED_RUNTIME_FIELDS = {
    "_id",
    "student_name",
    "school_name",
    "professor_name",
    "professor_aee_responsavel_nome",
}


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _descriptions(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    result: list[str] = []
    for item in items:
        if isinstance(item, Mapping):
            desc = item.get("descricao")
            if _nonempty(desc):
                result.append(str(desc))
        elif _nonempty(item):
            result.append(str(item))
    return result


def _objectives(items: Any) -> list[AEEObjective]:
    if not isinstance(items, list):
        return []
    result: list[AEEObjective] = []
    for item in items:
        if isinstance(item, Mapping):
            desc = item.get("descricao")
            if not _nonempty(desc):
                continue
            indicadores = item.get("indicadores")
            result.append(
                AEEObjective(
                    descricao=str(desc),
                    prazo=_as_text(item.get("prazo")),
                    status=_as_text(item.get("status")),
                    indicadores=[str(v) for v in indicadores]
                    if isinstance(indicadores, list)
                    else [],
                )
            )
        elif _nonempty(item):
            result.append(AEEObjective(descricao=str(item)))
    return result


def _resources(items: Any) -> list[AEEAccessibilityResource]:
    if not isinstance(items, list):
        return []
    result: list[AEEAccessibilityResource] = []
    for item in items:
        if isinstance(item, Mapping):
            desc = item.get("descricao")
            if not _nonempty(desc):
                continue
            disponivel = item.get("disponivel")
            result.append(
                AEEAccessibilityResource(
                    tipo=_as_text(item.get("tipo")),
                    descricao=str(desc),
                    disponivel=disponivel if isinstance(disponivel, bool) else None,
                )
            )
        elif _nonempty(item):
            result.append(AEEAccessibilityResource(descricao=str(item)))
    return result


def _schedule_sessions(plano: Mapping[str, Any]) -> list[AEEScheduleSession]:
    days = plano.get("dias_atendimento")
    if not isinstance(days, list):
        days = []

    return [
        AEEScheduleSession(
            weekday=str(day),
            start=_as_text(plano.get("horario_inicio")),
            end=_as_text(plano.get("horario_fim")),
            local=_as_text(plano.get("local_atendimento")),
            modalidade=_as_text(plano.get("modalidade")),
            effective_from=_as_text(plano.get("data_inicio")),
        )
        for day in days
        if _nonempty(day)
    ]


def _gap(
    section: str,
    code: str,
    field: str,
    description: str,
    *,
    severity: str = "required",
) -> AEEMappingGap:
    return AEEMappingGap(
        section=section,
        code=code,
        field=field,
        description=description,
        severity=severity,
    )


def evaluate_minimum_gaps(dossier: AEEDossierV2) -> list[AEEMappingGap]:
    """Aponta lacunas para adequação sem invalidar ou apagar o legado.

    A ausência de informação é tratada como ``não avaliada``/lacuna, nunca como
    ``não necessária``.
    """

    gaps: list[AEEMappingGap] = []
    sc = dossier.study_case
    paee = dossier.paee
    pei = dossier.pei

    if not (_nonempty(sc.demanda_inicial_contexto) or sc.barreiras_contexto):
        gaps.append(
            _gap(
                "study_case",
                "STUDY_CASE_INITIAL_DEMANDS_BARRIERS",
                "demanda_inicial_contexto/barreiras_contexto",
                "Registrar demandas individuais iniciais, barreiras e contexto escolar.",
            )
        )

    if not (_nonempty(sc.potencialidades) and _nonempty(sc.demandas_apoio)):
        gaps.append(
            _gap(
                "study_case",
                "STUDY_CASE_POTENTIAL_SUPPORT",
                "potencialidades/demandas_apoio",
                "Completar potencialidades e demandas de apoio identificadas no Estudo de Caso.",
            )
        )

    if not sc.estrategias_recursos_acessibilidade:
        gaps.append(
            _gap(
                "study_case",
                "STUDY_CASE_ACCESSIBILITY_STRATEGIES",
                "estrategias_recursos_acessibilidade",
                "Definir estratégias e recursos de acessibilidade para eliminação de barreiras.",
            )
        )

    if not any(
        _nonempty(value)
        for value in (
            sc.participacao_estudante,
            sc.contribuicoes_estudante,
            sc.contribuicoes_familia,
        )
    ):
        gaps.append(
            _gap(
                "study_case",
                "STUDY_CASE_STUDENT_FAMILY_PARTICIPATION",
                "participacao_estudante/contribuicoes_familia",
                "Registrar o envolvimento do estudante e da família no Estudo de Caso.",
            )
        )

    if not paee.materiais_recursos:
        gaps.append(
            _gap(
                "paee",
                "PAEE_MATERIALS_RESOURCES",
                "materiais_recursos",
                "Definir materiais e recursos para eliminar ou minimizar barreiras.",
            )
        )

    if (
        paee.tecnologia_assistiva.status == "not_assessed"
        or paee.comunicacao_aumentativa_alternativa.status == "not_assessed"
    ):
        gaps.append(
            _gap(
                "paee",
                "PAEE_TA_AAC_ASSESSMENT",
                "tecnologia_assistiva/comunicacao_aumentativa_alternativa",
                "Avaliar necessidade e capacidade de disponibilização de tecnologia assistiva e CAA.",
            )
        )

    support_assessments = (
        paee.profissional_apoio_escolar,
        paee.tradutor_interprete_libras,
        paee.guia_interprete,
    )
    if any(item.status == "not_assessed" for item in support_assessments):
        gaps.append(
            _gap(
                "paee",
                "PAEE_HUMAN_SUPPORT_ASSESSMENT",
                "profissional_apoio_escolar/tradutor_interprete_libras/guia_interprete",
                "Avaliar a necessidade dos apoios humanos previstos para o estudante.",
            )
        )

    if not (
        paee.demandas_formacao_educacao_especial_inclusiva
        or paee.acionamentos_rede_protecao
    ):
        gaps.append(
            _gap(
                "paee",
                "PAEE_TRAINING_NETWORK_ASSESSMENT",
                "demandas_formacao_educacao_especial_inclusiva/acionamentos_rede_protecao",
                "Registrar a avaliação de demandas de formação e de acionamento da rede de proteção.",
            )
        )

    if not (pei.atividades_aee or _nonempty(pei.articulacao_sala_comum)):
        gaps.append(
            _gap(
                "pei",
                "PEI_AEE_ACTIVITIES_ARTICULATION",
                "atividades_aee/articulacao_sala_comum",
                "Registrar atividades do AEE e sua articulação com sala comum e equipe escolar.",
            )
        )

    if not any(
        _nonempty(value)
        for value in (
            pei.acessibilidade_curricular,
            pei.acessibilidade_didatico_pedagogica,
            pei.acessibilidade_avaliativa,
        )
    ):
        gaps.append(
            _gap(
                "pei",
                "PEI_ACCESSIBILITY_MEASURES",
                "acessibilidade_curricular/acessibilidade_didatico_pedagogica/acessibilidade_avaliativa",
                "Registrar medidas de acessibilidade curricular, didático-pedagógica e avaliativa.",
            )
        )

    if not _nonempty(pei.estrategias_acompanhamento_monitoramento):
        gaps.append(
            _gap(
                "pei",
                "PEI_MONITORING",
                "estrategias_acompanhamento_monitoramento",
                "Definir estratégias de acompanhamento e monitoramento do PEI.",
            )
        )

    if not pei.devolutivas_familia:
        gaps.append(
            _gap(
                "pei",
                "PEI_FAMILY_FEEDBACK",
                "devolutivas_familia",
                "Registrar devolutivas às famílias.",
            )
        )

    if not _nonempty(dossier.lifecycle.review_at):
        gaps.append(
            _gap(
                "lifecycle",
                "ANNUAL_REVIEW_DATE",
                "review_at",
                "Programar revisão compatível com a avaliação contínua e a revisão anual.",
                severity="recommended",
            )
        )

    return gaps


def project_legacy_plan(plano: Mapping[str, Any]) -> AEELegacyProjection:
    """Projeta um Plano AEE legado sem alterar o documento original."""

    missing_identity = [
        field
        for field in ("student_id", "school_id", "academic_year")
        if not _nonempty(plano.get(field))
    ]
    if missing_identity:
        raise ValueError(
            "Plano AEE legado sem identidade mínima para projeção v2: "
            + ", ".join(missing_identity)
        )

    legacy_barriers = _descriptions(plano.get("barreiras"))
    resources = _resources(plano.get("recursos_acessibilidade"))
    resource_descriptions = [item.descricao for item in resources]

    legacy_status = _as_text(plano.get("status"))
    lifecycle_status = LEGACY_STATUS_TO_V2.get(legacy_status or "", "draft")

    dossier = AEEDossierV2(
        student_id=str(plano["student_id"]),
        school_id=str(plano["school_id"]),
        academic_year=int(plano["academic_year"]),
        professor_aee_responsavel_id=_as_text(plano.get("professor_aee_id")),
        professor_aee_responsavel_nome=_as_text(plano.get("professor_aee_nome")),
        publico_alvo=_as_text(plano.get("publico_alvo")),
        turma_origem_id=_as_text(plano.get("turma_origem_id")),
        turma_origem_nome=_as_text(plano.get("turma_origem_nome")),
        escola_origem_nome=_as_text(plano.get("escola_origem_nome")),
        professor_regente_id=_as_text(plano.get("professor_regente_id")),
        professor_regente_nome=_as_text(plano.get("professor_regente_nome")),
        study_case=AEEStudyCase(
            state="legacy_projected",
            fundamentacao_pedagogica_identificacao=_as_text(
                plano.get("criterio_elegibilidade")
            ),
            demanda_inicial_contexto=_as_text(plano.get("linha_base_situacao_atual")),
            barreiras_contexto=legacy_barriers,
            potencialidades=_as_text(plano.get("linha_base_potencialidades")),
            demandas_apoio=_as_text(plano.get("linha_base_dificuldades")),
            comunicacao_participacao=_as_text(plano.get("linha_base_comunicacao")),
            estrategias_recursos_acessibilidade=resource_descriptions,
        ),
        paee=AEEPAEE(
            state="legacy_projected",
            barreiras_prioritarias=legacy_barriers,
            objetivos=_objectives(plano.get("objetivos")),
            materiais_recursos=resources,
            indicadores_progresso=_as_text(plano.get("indicadores_progresso")),
            frequencia_revisao=_as_text(plano.get("frequencia_revisao")),
            criterios_ajuste=_as_text(plano.get("criterios_ajuste")),
        ),
        pei=AEEPEI(
            state="legacy_projected",
            articulacao_sala_comum=_as_text(plano.get("orientacoes_sala_comum")),
            combinados_professor_regente=_as_text(
                plano.get("combinados_professor_regente")
            ),
            acessibilidade_curricular=_as_text(plano.get("adequacoes_curriculares")),
            adaptacoes_por_componente=_as_text(
                plano.get("adaptacoes_por_componente")
            ),
            estrategias_acompanhamento_monitoramento=_as_text(
                plano.get("indicadores_progresso")
            ),
        ),
        schedule=AEESchedule(
            carga_horaria_semanal=_as_text(plano.get("carga_horaria_semanal")),
            sessions=_schedule_sessions(plano),
        ),
        lifecycle=AEELifecycle(
            status=lifecycle_status,
            elaborated_at=_as_text(plano.get("data_elaboracao")),
            effective_from=_as_text(plano.get("data_inicio")),
            review_at=_as_text(plano.get("data_revisao")),
            periodo_vigencia_legacy=_as_text(plano.get("periodo_vigencia")),
        ),
        provenance=AEELegacyProvenance(
            legacy_plano_id=_as_text(plano.get("id")),
            legacy_status=legacy_status,
            template_origin_id=_as_text(plano.get("template_origin_id")),
            created_by=_as_text(plano.get("created_by")),
            updated_by=_as_text(plano.get("updated_by")),
            created_at=_as_text(plano.get("created_at")),
            updated_at=_as_text(plano.get("updated_at")),
        ),
    )

    consumed = sorted(field for field in MAPPED_LEGACY_FIELDS if field in plano)
    unmapped = sorted(
        field
        for field, value in plano.items()
        if field not in MAPPED_LEGACY_FIELDS
        and field not in IGNORED_RUNTIME_FIELDS
        and _nonempty(value)
    )

    report = AEELegacyMappingReport(
        legacy_plano_id=_as_text(plano.get("id")),
        consumed_fields=consumed,
        unmapped_nonempty_fields=unmapped,
        gaps=evaluate_minimum_gaps(dossier),
    )
    return AEELegacyProjection(dossier=dossier, report=report)
