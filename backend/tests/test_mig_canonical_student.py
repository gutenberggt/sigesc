import pytest

from mig.core.canonical_student import (
    CANONICAL_CONTRACT_VERSION,
    build_canonical_student_enrollment,
)


def _student(**overrides):
    data = {
        "id": "student-internal-1",
        "mantenedora_id": "tenant-1",
        "full_name": "Maria da Silva",
        "social_name": "Maria",
        "birth_date": "10/02/2010",
        "cpf": "12345678901",
        "rg": "1234567",
        "email": "maria@example.com",
        "phone": "94999999999",
        "nis": "12345678900",
        "sex": "feminino",
        "color_race": "parda",
        "nationality": "Brasileira",
        "birth_state": "PA",
        "birth_city": "Floresta do Araguaia",
        "comunidade_tradicional": "nao_pertence",
        "address": {
            "zip_code": "68543000",
            "state": "PA",
            "state_ibge_code": "15",
            "city": "Floresta do Araguaia",
            "city_ibge_code": "1502939",
            "neighborhood": "Centro",
            "street": "Rua A",
            "number": "10",
            "complement": "Casa",
            "geographic_location": "urbana",
            "differentiated_location": "nao_se_aplica",
        },
    }
    data.update(overrides)
    return data


def _enrollment(**overrides):
    data = {
        "id": "enrollment-internal-1",
        "student_id": "student-internal-1",
        "school_id": "school-1",
        "class_id": "class-1",
        "enrollment_number": "2026-0001",
        "enrollment_date": "01/02/2026",
        "enrollment_end_date": None,
        "high_school_eja_completion_date": None,
        "academic_year": 2026,
        "status": "active",
        "student_series": "6º Ano",
        "needs_pedagogical_support": None,
        "sgp_enrollment_id": None,
    }
    data.update(overrides)
    return data


def _class_record(**overrides):
    data = {
        "id": "class-1",
        "education_level": "fundamental_anos_finais",
        "grade_level": "6º Ano",
    }
    data.update(overrides)
    return data


def test_builds_stable_provider_agnostic_contract_for_complete_records():
    result = build_canonical_student_enrollment(
        student=_student(),
        enrollment=_enrollment(),
        class_record=_class_record(),
    )

    assert result.contract_version == CANONICAL_CONTRACT_VERSION
    assert result.student.student_id == "student-internal-1"
    assert result.student.tenant_id == "tenant-1"
    assert result.student.full_name == "Maria da Silva"
    assert result.student.color_race == "parda"
    assert result.student.quilombola is False
    assert result.student.address.state_ibge_code == "15"
    assert result.student.address.city_ibge_code == "1502939"
    assert result.enrollment.enrollment_id == "enrollment-internal-1"
    assert result.enrollment.academic_year == 2026
    assert result.enrollment.education_level == "fundamental_anos_finais"
    assert result.enrollment.grade_level == "6º Ano"


def test_unknown_values_remain_none_and_no_fictitious_defaults_are_created():
    student = _student(
        full_name="   ",
        nationality=None,
        sex=None,
        color_race=None,
        comunidade_tradicional=None,
        address="Rua antiga em texto livre",
        has_disability=True,
        disabilities=["tdah"],
    )
    enrollment = _enrollment(
        enrollment_number="",
        needs_pedagogical_support=None,
        sgp_enrollment_id=None,
    )

    result = build_canonical_student_enrollment(
        student=student,
        enrollment=enrollment,
        class_record=None,
    )

    assert result.student.full_name is None
    assert result.student.nationality is None
    assert result.student.sex is None
    assert result.student.color_race is None
    assert result.student.traditional_community is None
    assert result.student.quilombola is None
    assert result.student.address is None
    assert result.student.student_with_disability is None
    assert result.enrollment.enrollment_number is None
    assert result.enrollment.needs_pedagogical_support is None
    assert result.enrollment.education_level is None


def test_traditional_community_is_not_reinterpreted_as_race_color():
    result = build_canonical_student_enrollment(
        student=_student(
            color_race="quilombola",
            comunidade_tradicional="quilombola",
        ),
        enrollment=_enrollment(),
    )

    assert result.student.color_race is None
    assert result.student.traditional_community == "quilombola"
    assert result.student.quilombola is True


def test_has_disability_and_tdah_never_create_official_disability_flag_in_b1():
    result = build_canonical_student_enrollment(
        student=_student(
            has_disability=True,
            disabilities=["tdah", "dislexia"],
        ),
        enrollment=_enrollment(),
    )

    assert result.student.student_with_disability is None


def test_ibge_codes_are_never_inferred_from_state_or_city_text():
    result = build_canonical_student_enrollment(
        student=_student(
            address={
                "state": "PA",
                "city": "Floresta do Araguaia",
                "state_ibge_code": None,
                "city_ibge_code": None,
            }
        ),
        enrollment=_enrollment(),
    )

    assert result.student.address.state == "PA"
    assert result.student.address.city == "Floresta do Araguaia"
    assert result.student.address.state_ibge_code is None
    assert result.student.address.city_ibge_code is None


def test_internal_and_external_ids_remain_separate():
    result = build_canonical_student_enrollment(
        student=_student(sgp_student_id="sgp-student-99"),
        enrollment=_enrollment(sgp_enrollment_id="sgp-enrollment-88"),
    )

    assert result.student.student_id == "student-internal-1"
    assert result.student.sgp_student_id == "sgp-student-99"
    assert result.enrollment.enrollment_id == "enrollment-internal-1"
    assert result.enrollment.sgp_enrollment_id == "sgp-enrollment-88"


def test_effective_grade_prefers_enrollment_student_series_then_class_grade():
    with_student_series = build_canonical_student_enrollment(
        student=_student(),
        enrollment=_enrollment(student_series="7º Ano"),
        class_record=_class_record(grade_level="6º Ano"),
    )
    without_student_series = build_canonical_student_enrollment(
        student=_student(),
        enrollment=_enrollment(student_series=None),
        class_record=_class_record(grade_level="6º Ano"),
    )

    assert with_student_series.enrollment.grade_level == "7º Ano"
    assert without_student_series.enrollment.grade_level == "6º Ano"


def test_rejects_cross_student_enrollment_mismatch():
    with pytest.raises(ValueError, match="enrollment.student_id diverge"):
        build_canonical_student_enrollment(
            student=_student(),
            enrollment=_enrollment(student_id="other-student"),
        )
