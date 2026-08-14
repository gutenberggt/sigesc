import pytest

from mig.cmde.readiness import (
    CMDE_LOT_ENDPOINTS,
    CmdeLotType,
    validate_cmde_batch_readiness,
    validate_cmde_record_readiness,
)
from mig.cmde.student_serializer import (
    CmdeStudentSchoolContext,
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
            "geographic_location": None,
            "differentiated_location": None,
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


def _codes(report):
    return {issue.code for issue in report.issues}


def _fields(report):
    return {issue.field for issue in report.issues if issue.severity == "error"}


def test_ready_record_for_current_student_without_class_profile():
    canonical = _canonical()
    report = validate_cmde_record_readiness(
        canonical,
        lot_type=CmdeLotType.STUDENT_WITHOUT_CLASS_CREATE,
        school=_school(),
    )

    assert report.ready is True
    assert report.blocker_count == 0
    assert report.warning_count == 0
    assert report.endpoint == "/api/v2/estudantes/sem-turma/cadastro/lote"

    # Um registro classificado como pronto também deve passar pelo serializer B.3.
    mapped = map_canonical_student_without_class(canonical, school=_school())
    payload = serialize_student_without_class_batch([mapped])
    assert len(payload["estudantes"]) == 1


@pytest.mark.parametrize(
    ("student_overrides", "enrollment_overrides", "expected_field"),
    [
        ({"full_name": None}, None, "student.full_name"),
        ({"cpf": None}, None, "student.cpf"),
        ({"birth_date": None}, None, "student.birth_date"),
        (None, {"enrollment_number": None}, "enrollment.enrollment_number"),
        (None, {"enrollment_date": None}, "enrollment.enrollment_date"),
        (None, {"academic_year": None}, "enrollment.academic_year"),
    ],
)
def test_missing_minimum_fields_are_explicit_blockers(
    student_overrides,
    enrollment_overrides,
    expected_field,
):
    report = validate_cmde_record_readiness(
        _canonical(
            student_overrides=student_overrides,
            enrollment_overrides=enrollment_overrides,
        ),
        lot_type=CmdeLotType.STUDENT_WITHOUT_CLASS_CREATE,
        school=_school(),
    )

    assert report.ready is False
    assert "missing_required" in _codes(report)
    assert expected_field in _fields(report)


def test_cpf_format_is_validated_without_echoing_the_value():
    canonical = _canonical(student_overrides={"cpf": "123.456.789-00"})
    report = validate_cmde_record_readiness(
        canonical,
        lot_type=CmdeLotType.STUDENT_WITHOUT_CLASS_CREATE,
        school=_school(),
    )

    assert report.ready is False
    assert "student.cpf" in _fields(report)
    assert "123.456.789-00" not in report.model_dump_json()


def test_dates_are_validated_before_serializer_execution():
    report = validate_cmde_record_readiness(
        _canonical(student_overrides={"birth_date": "10-05-2012"}),
        lot_type=CmdeLotType.STUDENT_WITHOUT_CLASS_CREATE,
        school=_school(),
    )

    assert report.ready is False
    assert "student.birth_date" in _fields(report)
    assert "invalid_format" in _codes(report)


def test_school_inep_is_required_and_must_have_eight_digits():
    missing = validate_cmde_record_readiness(
        _canonical(),
        lot_type=CmdeLotType.STUDENT_WITHOUT_CLASS_CREATE,
        school=_school(school_inep_code=None),
    )
    invalid = validate_cmde_record_readiness(
        _canonical(),
        lot_type=CmdeLotType.STUDENT_WITHOUT_CLASS_CREATE,
        school=_school(school_inep_code="school-internal-1"),
    )

    assert missing.ready is False
    assert invalid.ready is False
    assert "school.school_inep_code" in _fields(missing)
    assert "school.school_inep_code" in _fields(invalid)


def test_unstructured_or_missing_address_blocks_territorial_readiness():
    report = validate_cmde_record_readiness(
        _canonical(student_overrides={"address": None}),
        lot_type=CmdeLotType.STUDENT_WITHOUT_CLASS_CREATE,
        school=_school(),
    )

    assert report.ready is False
    assert "student.address" in _fields(report)


@pytest.mark.parametrize(
    ("address_overrides", "expected_field"),
    [
        ({"state_ibge_code": None}, "student.address.state_ibge_code"),
        ({"city_ibge_code": None}, "student.address.city_ibge_code"),
        ({"state_ibge_code": "PA"}, "student.address.state_ibge_code"),
        ({"city_ibge_code": "Floresta"}, "student.address.city_ibge_code"),
        ({"zip_code": "68543-000"}, "student.address.zip_code"),
    ],
)
def test_territorial_codes_and_present_cep_are_validated(
    address_overrides,
    expected_field,
):
    base_address = {
        "zip_code": "68543000",
        "state": "PA",
        "state_ibge_code": "15",
        "city": "Floresta do Araguaia",
        "city_ibge_code": "1502939",
        "neighborhood": "Centro",
        "street": "Rua das Acácias",
        "number": "150",
        "geographic_location": None,
        "differentiated_location": None,
    }
    base_address.update(address_overrides)
    report = validate_cmde_record_readiness(
        _canonical(student_overrides={"address": base_address}),
        lot_type=CmdeLotType.STUDENT_WITHOUT_CLASS_CREATE,
        school=_school(),
    )

    assert report.ready is False
    assert expected_field in _fields(report)


def test_missing_optional_address_text_becomes_warning_not_blocker():
    address = {
        "zip_code": None,
        "state": "PA",
        "state_ibge_code": "15",
        "city": "Floresta do Araguaia",
        "city_ibge_code": "1502939",
        "neighborhood": None,
        "street": None,
        "number": None,
    }
    report = validate_cmde_record_readiness(
        _canonical(student_overrides={"address": address}),
        lot_type=CmdeLotType.STUDENT_WITHOUT_CLASS_CREATE,
        school=_school(),
    )

    assert report.ready is True
    assert report.warning_count == 4
    assert report.blocker_count == 0


@pytest.mark.parametrize(
    ("student_overrides", "enrollment_overrides", "class_record", "expected_field"),
    [
        ({"sex": "feminino"}, None, None, "student.sex"),
        ({"color_race": "parda"}, None, None, "student.color_race"),
        ({"nationality": "Brasileira"}, None, None, "student.nationality"),
        (
            {"comunidade_tradicional": "nao_pertence"},
            None,
            None,
            "student.quilombola",
        ),
        (
            None,
            {"needs_pedagogical_support": False},
            None,
            "enrollment.needs_pedagogical_support",
        ),
        (
            None,
            {"student_series": "6º Ano"},
            {"education_level": "fundamental_anos_finais", "grade_level": "6º Ano"},
            "enrollment.education_level + enrollment.grade_level",
        ),
    ],
)
def test_known_b2_dimensions_without_verified_mapping_block_readiness(
    student_overrides,
    enrollment_overrides,
    class_record,
    expected_field,
):
    report = validate_cmde_record_readiness(
        _canonical(
            student_overrides=student_overrides,
            enrollment_overrides=enrollment_overrides,
            class_record=class_record,
        ),
        lot_type=CmdeLotType.STUDENT_WITHOUT_CLASS_CREATE,
        school=_school(),
    )

    assert report.ready is False
    assert "unverified_mapping" in _codes(report)
    assert expected_field in _fields(report)


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("geographic_location", "urbana"),
        ("differentiated_location", "nao_se_aplica"),
    ],
)
def test_known_address_dimensions_are_not_silently_dropped(field_name, field_value):
    address = {
        "zip_code": "68543000",
        "state": "PA",
        "state_ibge_code": "15",
        "city": "Floresta do Araguaia",
        "city_ibge_code": "1502939",
        "neighborhood": "Centro",
        "street": "Rua das Acácias",
        "number": "150",
        field_name: field_value,
    }
    report = validate_cmde_record_readiness(
        _canonical(student_overrides={"address": address}),
        lot_type=CmdeLotType.STUDENT_WITHOUT_CLASS_CREATE,
        school=_school(),
    )

    assert report.ready is False
    assert f"student.address.{field_name}" in _fields(report)
    assert "unverified_mapping" in _codes(report)


def test_disability_flag_is_fail_closed_until_official_mapping_exists():
    canonical = _canonical()
    canonical = canonical.model_copy(
        update={
            "student": canonical.student.model_copy(
                update={"student_with_disability": True}
            )
        }
    )
    report = validate_cmde_record_readiness(
        canonical,
        lot_type=CmdeLotType.STUDENT_WITHOUT_CLASS_CREATE,
        school=_school(),
    )

    assert report.ready is False
    assert "student.student_with_disability" in _fields(report)


def test_external_sgp_ids_are_not_required_for_initial_create():
    canonical = _canonical(
        student_overrides={"sgp_student_id": None},
        enrollment_overrides={"sgp_enrollment_id": None},
    )
    report = validate_cmde_record_readiness(
        canonical,
        lot_type=CmdeLotType.STUDENT_WITHOUT_CLASS_CREATE,
        school=_school(),
    )

    assert report.ready is True
    assert "student.sgp_student_id" not in _fields(report)
    assert "enrollment.sgp_enrollment_id" not in _fields(report)


def test_known_but_not_implemented_lot_type_fails_closed():
    report = validate_cmde_record_readiness(
        _canonical(),
        lot_type=CmdeLotType.ENROLLMENT_MOVEMENT,
        school=_school(),
    )

    assert report.ready is False
    assert report.endpoint == "/api/v2/matriculas/movimentacao/lote"
    assert _codes(report) == {"unsupported_lot_type"}


def test_unknown_lot_type_fails_closed_without_guessing_endpoint():
    report = validate_cmde_record_readiness(
        _canonical(),
        lot_type="future_unknown_batch",
        school=_school(),
    )

    assert report.ready is False
    assert report.endpoint is None
    assert _codes(report) == {"unknown_lot_type"}


def test_batch_report_counts_ready_and_blocked_records():
    ready = _canonical()
    blocked = _canonical(student_overrides={"cpf": None})
    batch = validate_cmde_batch_readiness(
        [(ready, _school()), (blocked, _school())],
        lot_type=CmdeLotType.STUDENT_WITHOUT_CLASS_CREATE,
    )

    assert batch.ready is False
    assert batch.total_records == 2
    assert batch.ready_records == 1
    assert batch.blocked_records == 1
    assert len(batch.records) == 2


def test_empty_batch_is_never_ready():
    batch = validate_cmde_batch_readiness(
        [],
        lot_type=CmdeLotType.STUDENT_WITHOUT_CLASS_CREATE,
    )

    assert batch.ready is False
    assert batch.total_records == 0
    assert {issue.code for issue in batch.batch_issues} == {"empty_batch"}


def test_diagnostic_does_not_expose_student_name_or_cpf():
    canonical = _canonical(student_overrides={"sex": "feminino"})
    report = validate_cmde_record_readiness(
        canonical,
        lot_type=CmdeLotType.STUDENT_WITHOUT_CLASS_CREATE,
        school=_school(),
    )
    dumped = report.model_dump_json()

    assert canonical.student.full_name not in dumped
    assert canonical.student.cpf not in dumped


def test_registered_lot_catalog_contains_current_student_and_enrollment_endpoints():
    assert CMDE_LOT_ENDPOINTS[CmdeLotType.STUDENT_WITHOUT_CLASS_CREATE.value].endswith(
        "/estudantes/sem-turma/cadastro/lote"
    )
    assert CMDE_LOT_ENDPOINTS[CmdeLotType.STUDENT_WITH_CLASS_CREATE.value].endswith(
        "/estudantes/com-turma/cadastro/lote"
    )
    assert CMDE_LOT_ENDPOINTS[CmdeLotType.ENROLLMENT_CLASS_ASSIGNMENT.value].endswith(
        "/matriculas/enturmacao/lote"
    )
    assert CMDE_LOT_ENDPOINTS[CmdeLotType.ENROLLMENT_MOVEMENT.value].endswith(
        "/matriculas/movimentacao/lote"
    )
