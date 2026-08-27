from fastapi import APIRouter, Request
from pydantic import ValidationError

from models import Student, StudentUpdate
from routers.student_legacy_compat import (
    build_compatible_student,
    install_student_legacy_compat,
    is_legacy_compat_validation_error,
    normalize_legacy_student_doc,
)


def test_legacy_address_is_reassembled_without_mutating_source():
    source = {
        "id": "student-1",
        "full_name": "Estudante Legado",
        "address": "  FAZENDA SANTO ANTONIO  ",
        "address_number": "S/N",
        "address_complement": "ZONA RURAL",
        "neighborhood": "BOM JESUS II",
        "city": "FLORESTA DO ARAGUAIA",
        "state": "PARÁ",
        "zip_code": "",
        "civil_certificate_type": "NASCIMENTO",
        "comunidade_tradicional": "",
    }

    normalized = normalize_legacy_student_doc(source)

    assert source["address"] == "  FAZENDA SANTO ANTONIO  "
    assert source["civil_certificate_type"] == "NASCIMENTO"
    assert source["comunidade_tradicional"] == ""

    assert normalized["address"] == {
        "zip_code": "",
        "state": "PARÁ",
        "state_ibge_code": None,
        "city": "FLORESTA DO ARAGUAIA",
        "city_ibge_code": None,
        "neighborhood": "BOM JESUS II",
        "street": "FAZENDA SANTO ANTONIO",
        "number": "S/N",
        "complement": "ZONA RURAL",
        "geographic_location": None,
        "differentiated_location": None,
    }
    assert normalized["civil_certificate_type"] == "nascimento"
    assert normalized["comunidade_tradicional"] is None

    student = Student.model_validate(normalized)
    assert student.address.street == "FAZENDA SANTO ANTONIO"
    assert student.address.number == "S/N"
    assert student.address.complement == "ZONA RURAL"
    assert student.address.city == "FLORESTA DO ARAGUAIA"
    assert student.address.state == "PARÁ"


def test_blank_legacy_address_preserves_flat_city_and_state():
    student = build_compatible_student({
        "id": "student-2",
        "full_name": "Estudante Sem Logradouro",
        "address": "",
        "city": "FLORESTA DO ARAGUAIA",
        "state": "PA",
    })

    assert student.address is not None
    assert student.address.street is None
    assert student.address.city == "FLORESTA DO ARAGUAIA"
    assert student.address.state == "PA"


def test_structured_address_is_not_reinterpreted():
    source = {
        "id": "student-3",
        "full_name": "Estudante Atual",
        "address": {
            "street": "Rua 1º de Maio",
            "number": "2084",
            "city": "Floresta do Araguaia",
            "state": "PA",
        },
        "civil_certificate_type": "nascimento",
        "comunidade_tradicional": "nao_pertence",
    }

    normalized = normalize_legacy_student_doc(source)

    assert normalized["address"] == source["address"]
    assert normalized["civil_certificate_type"] == "nascimento"
    assert normalized["comunidade_tradicional"] == "nao_pertence"
    Student.model_validate(normalized)


def test_only_audited_legacy_validation_errors_are_eligible_for_fallback():
    try:
        Student.model_validate({
            "id": "student-4",
            "full_name": "Legado",
            "address": "VILA TABULEIRO",
            "civil_certificate_type": "NASCIMENTO",
            "comunidade_tradicional": "",
        })
    except ValidationError as exc:
        assert is_legacy_compat_validation_error(exc) is True
    else:
        raise AssertionError("Documento legado deveria falhar antes da projeção")

    try:
        Student.model_validate({
            "id": "student-5",
            "full_name": "Erro Não Legado",
            "sex": "valor-invalido",
        })
    except ValidationError as exc:
        assert is_legacy_compat_validation_error(exc) is False
    else:
        raise AssertionError("Valor inválido de sex deveria falhar")


def test_unsupported_literal_is_not_silently_reinterpreted():
    normalized = normalize_legacy_student_doc({
        "id": "student-6",
        "full_name": "Valor Não Mapeado",
        "address": {},
        "civil_certificate_type": "OUTRO",
        "comunidade_tradicional": "comunidade_desconhecida",
    })

    assert normalized["civil_certificate_type"] == "OUTRO"
    assert normalized["comunidade_tradicional"] == "comunidade_desconhecida"

    try:
        Student.model_validate(normalized)
    except ValidationError as exc:
        roots = {str(error["loc"][0]) for error in exc.errors()}
        assert roots == {"civil_certificate_type", "comunidade_tradicional"}
    else:
        raise AssertionError("Valores não mapeados não podem ser aceitos silenciosamente")


def test_installer_wraps_expected_routes_and_is_idempotent():
    router = APIRouter(prefix="/students")

    @router.get("/{student_id}", response_model=Student)
    async def get_student(student_id: str, request: Request):  # pragma: no cover
        raise NotImplementedError

    @router.put("/{student_id}", response_model=Student)
    async def update_student(  # pragma: no cover
        student_id: str,
        student_update: StudentUpdate,
        request: Request,
    ):
        raise NotImplementedError

    @router.post("/{student_id}/cancel-transfer")
    async def cancel_transfer(student_id: str, request: Request):  # pragma: no cover
        raise NotImplementedError

    installed = install_student_legacy_compat(router, db=object())
    assert installed is router
    assert getattr(router, "_student_legacy_compat_installed") is True

    expected = {
        ("/students/{student_id}", "GET"),
        ("/students/{student_id}", "PUT"),
        ("/students/{student_id}/cancel-transfer", "POST"),
    }
    actual = {
        (route.path, method)
        for route in router.routes
        for method in (getattr(route, "methods", set()) or set())
        if (route.path, method) in expected
    }
    assert actual == expected

    assert install_student_legacy_compat(router, db=object()) is router
