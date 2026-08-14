import pytest
from pydantic import ValidationError

from mig.cmde.student_serializer import (
    CMDE_STUDENT_WITHOUT_CLASS_CREATE_ENDPOINT,
    CmdeStudentSchoolContext,
    CmdeStudentSerializationError,
    map_canonical_student_without_class,
    serialize_student_without_class_batch,
)
from mig.core.canonical_student import build_canonical_student_enrollment


def _canonical(
    *,
    student_overrides=None,
    enrollment_overrides=None,
    class_record=None,
):
    student = {
        "id": "student-internal-1",
        "mantenedora_id": "tenant-1",
        "full_name": "João da Conceição",
        "birth_date": "2012-05-10",
        "cpf": "12345678900",
        "email": "joao@example.com",
        "phone": "94999998888",
        # Dimensões codificadas permanecem ausentes no caso-base para que o
        # serializer possa demonstrar o subconjunto atualmente confirmado.
        "sex": None,
        "color_race": None,
        "nationality": None,
        "comunidade_tradicional": None,
        "address": {
            "zip_code": "68543000",
            "state": "PA",
            "state_ibge_code": "15",
            "city": "Floresta do Araguaia",
            "city_ibge_code": "1502939",
            "neighborhood": "Centro",
            "street": "Rua das Acácias",
            "number": "150",
        },
    }
    student.update(student_overrides or {})

    enrollment = {
        "id": "enrollment-internal-1",
        "student_id": "student-internal-1",
        "school_id": "school-internal-1",
        "class_id": None,
        "enrollment_number": "MAT-2026-001",
        "enrollment_date": "05/02/2026",
        "academic_year": 2026,
        "status": "active",
        "needs_pedagogical_support": None,
        "sgp_enrollment_id": None,
    }
    enrollment.update(enrollment_overrides or {})

    return build_canonical_student_enrollment(
        student=student,
        enrollment=enrollment,
        class_record=class_record,
    )


def _school(**overrides):
    data = {
        "school_inep_code": "15029390",
        "school_name": "Escola Municipal João Goulart",
    }
    data.update(overrides)
    return CmdeStudentSchoolContext(**data)


def test_target_endpoint_is_explicit_and_provider_specific():
    assert (
        CMDE_STUDENT_WITHOUT_CLASS_CREATE_ENDPOINT
        == "/api/v2/estudantes/sem-turma/cadastro/lote"
    )


def test_maps_confirmed_structural_fields_without_internal_ids_or_defaults():
    record = map_canonical_student_without_class(_canonical(), school=_school())
    payload = serialize_student_without_class_batch([record])

    assert payload == {
        "estudantes": [
            {
                "co_entidade": "15029390",
                "co_matricula_rede": "MAT-2026-001",
                "data_inicio_matricula": "05/02/2026",
                "estudante_bairro_res": "Centro",
                "estudante_cep_res": "68543000",
                "estudante_co_municipio_res": 1502939,
                "estudante_co_uf_res": 15,
                "estudante_cpf": "12345678900",
                "estudante_dt_nascimento": "10/05/2012",
                "estudante_email": "joao@example.com",
                "estudante_logradouro_res": "Rua das Acácias",
                "estudante_nome": "João da Conceição",
                "estudante_nu_endereco_res": "150",
                "estudante_telefone": "94999998888",
                "no_entidade": "Escola Municipal João Goulart",
                "nu_ano_matricula": 2026,
            }
        ]
    }
    dumped = str(payload)
    assert "student-internal-1" not in dumped
    assert "enrollment-internal-1" not in dumped
    assert "school-internal-1" not in dumped
    assert "tenant-1" not in dumped


def test_utf8_is_preserved_without_destructive_normalization():
    record = map_canonical_student_without_class(_canonical(), school=_school())
    payload = serialize_student_without_class_batch([record])

    assert payload["estudantes"][0]["estudante_nome"] == "João da Conceição"
    assert payload["estudantes"][0]["estudante_logradouro_res"] == "Rua das Acácias"


def test_none_fields_are_omitted_instead_of_becoming_empty_or_zero():
    canonical = _canonical(
        student_overrides={
            "email": None,
            "phone": None,
            "address": None,
        },
        enrollment_overrides={"enrollment_number": None},
    )
    record = map_canonical_student_without_class(canonical, school=None)
    item = serialize_student_without_class_batch([record])["estudantes"][0]

    assert "estudante_email" not in item
    assert "estudante_telefone" not in item
    assert "estudante_cep_res" not in item
    assert "estudante_co_uf_res" not in item
    assert "estudante_co_municipio_res" not in item
    assert "co_matricula_rede" not in item
    assert "co_entidade" not in item
    assert "no_entidade" not in item


def test_blocked_sex_code_stops_serialization_instead_of_guessing():
    canonical = _canonical(student_overrides={"sex": "feminino"})

    with pytest.raises(CmdeStudentSerializationError, match="sexo do estudante"):
        map_canonical_student_without_class(canonical, school=_school())


def test_blocked_race_color_stops_serialization_instead_of_guessing():
    canonical = _canonical(student_overrides={"color_race": "parda"})

    with pytest.raises(CmdeStudentSerializationError, match="raça/cor"):
        map_canonical_student_without_class(canonical, school=_school())


def test_blocked_nationality_stops_serialization_instead_of_using_examples():
    canonical = _canonical(student_overrides={"nationality": "Brasileira"})

    with pytest.raises(CmdeStudentSerializationError, match="nacionalidade"):
        map_canonical_student_without_class(canonical, school=_school())


def test_blocked_quilombola_false_is_not_coerced_to_numeric_default():
    canonical = _canonical(
        student_overrides={"comunidade_tradicional": "nao_pertence"}
    )

    with pytest.raises(CmdeStudentSerializationError, match="indicador quilombola"):
        map_canonical_student_without_class(canonical, school=_school())


def test_blocked_pedagogical_support_stops_serialization():
    canonical = _canonical(
        enrollment_overrides={"needs_pedagogical_support": False}
    )

    with pytest.raises(CmdeStudentSerializationError, match="apoio pedagógico"):
        map_canonical_student_without_class(canonical, school=_school())


def test_blocked_education_stage_stops_serialization_when_stage_is_known():
    canonical = _canonical(
        enrollment_overrides={"student_series": "6º Ano"},
        class_record={
            "education_level": "fundamental_anos_finais",
            "grade_level": "6º Ano",
        },
    )

    with pytest.raises(CmdeStudentSerializationError, match="etapa de ensino"):
        map_canonical_student_without_class(canonical, school=_school())


def test_disability_flag_never_leaks_to_payload_without_official_mapping():
    canonical = _canonical()
    canonical = canonical.model_copy(
        update={
            "student": canonical.student.model_copy(
                update={"student_with_disability": True}
            )
        }
    )

    with pytest.raises(CmdeStudentSerializationError, match="deficiência|disability"):
        map_canonical_student_without_class(canonical, school=_school())


def test_invalid_ibge_codes_fail_instead_of_being_inferred_from_text():
    canonical = _canonical(
        student_overrides={
            "address": {
                "state": "PA",
                "state_ibge_code": "PA",
                "city": "Floresta do Araguaia",
                "city_ibge_code": "Floresta do Araguaia",
            }
        }
    )

    with pytest.raises(CmdeStudentSerializationError, match="código IBGE"):
        map_canonical_student_without_class(canonical, school=_school())


def test_invalid_school_inep_fails_instead_of_using_internal_school_id():
    with pytest.raises(CmdeStudentSerializationError, match="código INEP"):
        map_canonical_student_without_class(
            _canonical(),
            school=_school(school_inep_code="school-internal-1"),
        )


def test_only_unambiguous_date_formats_are_accepted():
    canonical = _canonical(student_overrides={"birth_date": "10-05-2012"})

    with pytest.raises(CmdeStudentSerializationError, match="data fora"):
        map_canonical_student_without_class(canonical, school=_school())


def test_empty_batch_is_rejected_by_contract():
    with pytest.raises(ValidationError):
        serialize_student_without_class_batch([])


def test_external_sgp_ids_are_not_sent_in_create_without_class_payload():
    canonical = _canonical(
        student_overrides={"sgp_student_id": "99999"},
        enrollment_overrides={"sgp_enrollment_id": "88888"},
    )
    record = map_canonical_student_without_class(canonical, school=_school())
    payload = serialize_student_without_class_batch([record])
    dumped = str(payload)

    assert "99999" not in dumped
    assert "88888" not in dumped
    assert "id_sgp_estudante" not in dumped
    assert "id_sgp_matricula" not in dumped
