"""Fase 0 — testes de proteção do Diário por Vínculo Docente v1.0.

Não exercitam routers nem banco. Protegem escopo e invariantes antes de qualquer
integração funcional.
"""

import pytest

from services.diary_assignment_contract import (
    AttendancePurpose,
    DiaryProfile,
    MigrationSource,
    MigrationStatus,
    StudentScope,
    are_multigrade_series_in_scope,
    capabilities_for,
    is_class_in_scope,
    is_explicitly_official_attendance,
    is_stage_in_scope,
)


@pytest.mark.parametrize(
    "grade_level",
    ["Berçário I", "Maternal II", "Pré I", "Pré II", "Creche", "Jardim A"],
)
def test_educacao_infantil_in_scope_independentemente_do_rotulo(grade_level):
    assert is_stage_in_scope("educacao_infantil", grade_level)


@pytest.mark.parametrize(
    "grade_level",
    ["1º Ano", "2º Ano", "3º Ano", "4º Ano", "5º Ano", "1 ano", "5° Ano"],
)
def test_anos_iniciais_1_a_5_in_scope(grade_level):
    assert is_stage_in_scope("fundamental_anos_iniciais", grade_level)


@pytest.mark.parametrize("grade_level", ["6º Ano", "7º Ano", "8º Ano", "9º Ano"])
def test_anos_finais_fora_do_escopo(grade_level):
    assert not is_stage_in_scope("fundamental_anos_finais", grade_level)


@pytest.mark.parametrize("education_level", ["eja", "eja_inicial", "eja_anos_iniciais"])
@pytest.mark.parametrize("grade_level", ["1ª Etapa", "2ª Etapa", "EJA 1ª ETAPA", "2 etapa"])
def test_eja_primeira_e_segunda_etapa_in_scope(education_level, grade_level):
    assert is_stage_in_scope(education_level, grade_level)


@pytest.mark.parametrize("grade_level", ["3ª Etapa", "4ª Etapa", "EJA 3ª ETAPA", "quarta etapa"])
def test_eja_terceira_e_quarta_etapa_fora_do_escopo(grade_level):
    assert not is_stage_in_scope("eja", grade_level)


@pytest.mark.parametrize(
    "education_level", ["ensino_medio", "fundamental_anos_finais", "global", None, ""]
)
def test_modalidades_nao_aprovadas_fora_do_escopo(education_level):
    assert not is_stage_in_scope(education_level, "1º Ano")


def test_aee_fora_mesmo_quando_etapa_seria_elegivel():
    assert not is_class_in_scope({
        "education_level": "educacao_infantil",
        "grade_level": "Pré II",
        "atendimento_programa": "aee",
    })
    assert not is_class_in_scope({
        "education_level": "fundamental_anos_iniciais",
        "grade_level": "3º Ano",
        "atendimento_programa": "AEE",
    })


def test_atendimento_integral_nao_exclui_turma_elegivel():
    assert is_class_in_scope({
        "education_level": "fundamental_anos_iniciais",
        "grade_level": "4º Ano",
        "atendimento_programa": "atendimento_integral",
    })


def test_multisseriada_apenas_com_series_elegiveis_pode_entrar_em_bloco():
    assert are_multigrade_series_in_scope(
        "fundamental_anos_iniciais", ["1º Ano", "3º Ano", "5º Ano"]
    )
    assert are_multigrade_series_in_scope("eja", ["1ª Etapa", "2ª Etapa"])


def test_multisseriada_mista_com_etapa_fora_do_escopo_e_bloqueada():
    assert not are_multigrade_series_in_scope(
        "fundamental_anos_iniciais", ["5º Ano", "6º Ano"]
    )
    assert not are_multigrade_series_in_scope("eja", ["2ª Etapa", "3ª Etapa"])


def test_multisseriada_com_serie_vazia_nao_pode_ser_inferida():
    assert not are_multigrade_series_in_scope(
        "fundamental_anos_iniciais", ["1º Ano", None]
    )


def test_perfil_regular_mantem_frequencia_oficial_conteudo_e_notas():
    c = capabilities_for(DiaryProfile.REGULAR)
    assert c.attendance_enabled is True
    assert c.attendance_required is True
    assert c.attendance_purpose is AttendancePurpose.OFFICIAL
    assert c.content_enabled is True
    assert c.grades_enabled is True


def test_perfil_integrador_frequencia_opcional_pdf_only_e_sem_notas():
    c = capabilities_for(DiaryProfile.INTEGRATOR)
    assert c.attendance_enabled is True
    assert c.attendance_required is False
    assert c.attendance_purpose is AttendancePurpose.PDF_ONLY
    assert c.content_enabled is True
    assert c.grades_enabled is False


def test_perfil_compartilhado_mantem_frequencia_oficial_conteudo_e_notas():
    c = capabilities_for(DiaryProfile.SHARED)
    assert c.attendance_enabled is True
    assert c.attendance_required is True
    assert c.attendance_purpose is AttendancePurpose.OFFICIAL
    assert c.content_enabled is True
    assert c.grades_enabled is True


@pytest.mark.parametrize("purpose", [None, "", "pdf_only", "diagnostic", "qualquer_valor"])
def test_regra_positiva_nada_alem_de_official_conta(purpose):
    assert not is_explicitly_official_attendance(purpose)


def test_regra_positiva_official_conta():
    assert is_explicitly_official_attendance("official")


def test_enums_de_migracao_e_escopo_ficam_estaveis():
    assert StudentScope.ALL.value == "all"
    assert StudentScope.GROUP.value == "group"
    assert MigrationStatus.NEEDS_REVIEW.value == "needs_review"
    assert MigrationSource.EXPLICIT_TEACHER_ID.value == "explicit_teacher_id"
    assert MigrationSource.UNRESOLVED.value == "unresolved"
