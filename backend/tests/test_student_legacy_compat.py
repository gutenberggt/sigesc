from pathlib import Path

import pytest
from fastapi import APIRouter, Request
from pydantic import ValidationError

from auth_middleware import AuthMiddleware
from models import Student, StudentUpdate
from routers.student_legacy_compat import (
    build_compatible_student,
    install_student_legacy_compat,
    is_legacy_compat_validation_error,
    normalize_legacy_student_doc,
)


def _route(router, path, method):
    return next(
        route
        for route in router.routes
        if getattr(route, "path", None) == path
        and method in (getattr(route, "methods", set()) or set())
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


@pytest.mark.asyncio
async def test_get_route_fallback_reloads_and_projects_legacy_document(monkeypatch):
    legacy_doc = {
        "id": "student-legacy",
        "full_name": "Estudante Legado",
        "address": "VILA TABULEIRO",
        "city": "FLORESTA DO ARAGUAIA",
        "state": "PA",
        "civil_certificate_type": "NASCIMENTO",
        "comunidade_tradicional": "",
    }

    class FakeStudents:
        def __init__(self):
            self.find_calls = 0

        async def find_one(self, query, projection):
            self.find_calls += 1
            assert query == {"id": "student-legacy"}
            assert projection == {"_id": 0}
            return dict(legacy_doc)

    class FakeDB:
        def __init__(self):
            self.students = FakeStudents()

    async def fake_current_user(request):
        return {"id": "secretary-1", "role": "secretario", "is_sandbox": False}

    monkeypatch.setattr(AuthMiddleware, "get_current_user", fake_current_user)

    router = APIRouter(prefix="/students")

    @router.get("/{student_id}", response_model=Student)
    async def get_student(student_id: str, request: Request):
        assert student_id == "student-legacy"
        # Reproduz o ponto real do endpoint legado que explode ao serializar.
        return Student.model_validate(legacy_doc)

    @router.put("/{student_id}", response_model=Student)
    async def update_student(
        student_id: str,
        student_update: StudentUpdate,
        request: Request,
    ):  # pragma: no cover
        raise NotImplementedError

    @router.post("/{student_id}/cancel-transfer")
    async def cancel_transfer(student_id: str, request: Request):  # pragma: no cover
        raise NotImplementedError

    db = FakeDB()
    install_student_legacy_compat(router, db=db)

    result = await _route(
        router, "/students/{student_id}", "GET"
    ).endpoint("student-legacy", None)

    assert isinstance(result, Student)
    assert result.address.street == "VILA TABULEIRO"
    assert result.address.city == "FLORESTA DO ARAGUAIA"
    assert result.civil_certificate_type == "nascimento"
    assert result.comunidade_tradicional is None
    assert db.students.find_calls == 1


@pytest.mark.asyncio
async def test_nonlegacy_validation_error_is_not_swallowed(monkeypatch):
    class NeverReadStudents:
        async def find_one(self, query, projection):  # pragma: no cover
            raise AssertionError("Fallback não deveria consultar o banco")

    class FakeDB:
        students = NeverReadStudents()

    async def fake_current_user(request):  # pragma: no cover
        raise AssertionError("Auth não deve ser reexecutada para erro não legado")

    monkeypatch.setattr(AuthMiddleware, "get_current_user", fake_current_user)

    router = APIRouter(prefix="/students")

    @router.get("/{student_id}", response_model=Student)
    async def get_student(student_id: str, request: Request):
        return Student.model_validate({
            "id": student_id,
            "full_name": "Erro não legado",
            "sex": "valor-invalido",
        })

    @router.put("/{student_id}", response_model=Student)
    async def update_student(
        student_id: str,
        student_update: StudentUpdate,
        request: Request,
    ):  # pragma: no cover
        raise NotImplementedError

    @router.post("/{student_id}/cancel-transfer")
    async def cancel_transfer(student_id: str, request: Request):  # pragma: no cover
        raise NotImplementedError

    install_student_legacy_compat(router, db=FakeDB())

    with pytest.raises(ValidationError) as caught:
        await _route(
            router, "/students/{student_id}", "GET"
        ).endpoint("student-invalid", None)

    roots = {str(error["loc"][0]) for error in caught.value.errors()}
    assert roots == {"sex"}


def test_compat_adapter_has_no_mongo_write_primitives():
    backend = Path(__file__).resolve().parents[1]
    source = (
        backend / "routers" / "student_legacy_compat.py"
    ).read_text(encoding="utf-8")

    for primitive in (
        ".insert_one(",
        ".insert_many(",
        ".update_one(",
        ".update_many(",
        ".replace_one(",
        ".delete_one(",
        ".delete_many(",
        ".bulk_write(",
        ".find_one_and_update(",
        ".find_one_and_delete(",
        ".find_one_and_replace(",
    ):
        assert primitive not in source
