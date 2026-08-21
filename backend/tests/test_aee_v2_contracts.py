"""Fase 1 — contrato canônico e projeção não destrutiva do AEE v2."""

from copy import deepcopy

import pytest

from aee_v2.contracts import AEEPAEE, AEEDossierV2
from aee_v2.legacy_mapper import project_legacy_plan


@pytest.fixture
def legacy_plan():
    return {
        "id": "plano-1",
        "student_id": "student-1",
        "school_id": "school-1",
        "academic_year": 2026,
        "professor_aee_id": "prof-1",
        "professor_aee_nome": "Professora AEE",
        "publico_alvo": "transtorno_espectro_autista",
        "criterio_elegibilidade": "Fundamentação pedagógica construída pela equipe.",
        "turma_origem_id": "class-1",
        "turma_origem_nome": "5º Ano A",
        "escola_origem_nome": "Escola Exemplo",
        "professor_regente_id": "prof-reg-1",
        "professor_regente_nome": "Professor Regente",
        "data_elaboracao": "2026-02-10",
        "periodo_vigencia": "Ano letivo 2026",
        "linha_base_situacao_atual": "Contexto pedagógico inicial.",
        "linha_base_potencialidades": "Interesse por recursos visuais.",
        "linha_base_dificuldades": "Necessita apoio na comunicação e participação.",
        "linha_base_comunicacao": "Utiliza fala e apoio visual.",
        "modalidade": "individual",
        "carga_horaria_semanal": "2 horas",
        "dias_atendimento": ["terca", "quinta"],
        "horario_inicio": "09:00",
        "horario_fim": "10:00",
        "local_atendimento": "Sala de Recursos Multifuncionais",
        "barreiras": [
            {"tipo": "comunicacional", "descricao": "Barreira comunicacional"}
        ],
        "objetivos": [
            {
                "descricao": "Ampliar participação nas atividades",
                "prazo": "medio",
                "status": "em_andamento",
                "indicadores": ["Participa com apoio reduzido"],
            }
        ],
        "recursos_acessibilidade": [
            {
                "tipo": "rotina_visual",
                "descricao": "Rotina visual",
                "disponivel": True,
            }
        ],
        "indicadores_progresso": "Acompanhamento bimestral.",
        "frequencia_revisao": "bimestral",
        "criterios_ajuste": "Revisar estratégias conforme resposta pedagógica.",
        "orientacoes_sala_comum": "Antecipar a rotina e oferecer apoio visual.",
        "combinados_professor_regente": "Reunião mensal.",
        "adequacoes_curriculares": "Acessibilização dos materiais.",
        "adaptacoes_por_componente": "Matemática: apoio visual.",
        "data_inicio": "2026-02-10",
        "data_revisao": "2026-06-30",
        "status": "ativo",
        "template_origin_id": "tpl-1",
        "created_by": "user-1",
        "updated_by": "user-2",
    }


def test_projection_is_non_destructive_and_preserves_legacy_meaning(legacy_plan):
    original = deepcopy(legacy_plan)

    projection = project_legacy_plan(legacy_plan)
    dossier = projection.dossier

    assert legacy_plan == original
    assert dossier.schema_version == 2
    assert dossier.student_id == "student-1"
    assert dossier.school_id == "school-1"
    assert dossier.lifecycle.status == "active"
    assert dossier.provenance.legacy_status == "ativo"
    assert dossier.provenance.legacy_plano_id == "plano-1"

    assert (
        dossier.study_case.fundamentacao_pedagogica_identificacao
        == legacy_plan["criterio_elegibilidade"]
    )
    assert dossier.study_case.potencialidades == legacy_plan["linha_base_potencialidades"]
    assert dossier.study_case.demandas_apoio == legacy_plan["linha_base_dificuldades"]
    assert dossier.paee.objetivos[0].descricao == "Ampliar participação nas atividades"
    assert dossier.pei.articulacao_sala_comum == legacy_plan["orientacoes_sala_comum"]


def test_projection_keeps_missing_support_as_not_assessed(legacy_plan):
    dossier = project_legacy_plan(legacy_plan).dossier

    assert dossier.paee.tecnologia_assistiva.status == "not_assessed"
    assert dossier.paee.comunicacao_aumentativa_alternativa.status == "not_assessed"
    assert dossier.paee.profissional_apoio_escolar.status == "not_assessed"
    assert dossier.paee.tradutor_interprete_libras.status == "not_assessed"
    assert dossier.paee.guia_interprete.status == "not_assessed"


def test_schedule_projects_each_legacy_weekday_without_rewriting_dates(legacy_plan):
    dossier = project_legacy_plan(legacy_plan).dossier

    assert [session.weekday for session in dossier.schedule.sessions] == [
        "terca",
        "quinta",
    ]
    assert all(session.start == "09:00" for session in dossier.schedule.sessions)
    assert all(session.end == "10:00" for session in dossier.schedule.sessions)
    assert all(
        session.effective_from == "2026-02-10"
        for session in dossier.schedule.sessions
    )


def test_mapping_report_surfaces_unknown_nonempty_legacy_fields(legacy_plan):
    legacy_plan["campo_legado_nao_mapeado"] = "preservar e revisar"

    report = project_legacy_plan(legacy_plan).report

    assert "campo_legado_nao_mapeado" in report.unmapped_nonempty_fields


def test_projection_never_treats_missing_information_as_not_needed(legacy_plan):
    legacy_plan["recursos_acessibilidade"] = []

    projection = project_legacy_plan(legacy_plan)
    gap_codes = {gap.code for gap in projection.report.gaps}

    assert "STUDY_CASE_ACCESSIBILITY_STRATEGIES" in gap_codes
    assert "PAEE_MATERIALS_RESOURCES" in gap_codes
    assert "PAEE_TA_AAC_ASSESSMENT" in gap_codes


def test_student_and_family_participation_is_explicit_gap_in_legacy_projection(legacy_plan):
    projection = project_legacy_plan(legacy_plan)
    gap_codes = {gap.code for gap in projection.report.gaps}

    assert "STUDY_CASE_STUDENT_FAMILY_PARTICIPATION" in gap_codes
    assert "PEI_FAMILY_FEEDBACK" in gap_codes


def test_no_health_document_is_required_by_canonical_contract():
    required_fields = set(AEEDossierV2.model_json_schema().get("required", []))

    assert "diagnostico" not in required_fields
    assert "laudo" not in required_fields
    assert "cid" not in required_fields


def test_mutable_defaults_are_isolated_between_documents():
    first = AEEPAEE()
    second = AEEPAEE()

    first.demandas_formacao_educacao_especial_inclusiva.append("Formação 1")

    assert second.demandas_formacao_educacao_especial_inclusiva == []


def test_projection_requires_minimum_identity():
    with pytest.raises(ValueError, match="student_id"):
        project_legacy_plan({"school_id": "s1", "academic_year": 2026})
