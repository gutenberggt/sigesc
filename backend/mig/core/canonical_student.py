"""Contrato canônico Student + Enrollment para a camada de interoperabilidade MIG.

Este módulo é deliberadamente agnóstico de provider. Ele projeta os registros internos
do SIGESC em uma representação estável antes de qualquer tradução para CMDE/SGP.

Invariantes da Fase B.1:
- não contém códigos/enums específicos do CMDE;
- não inventa defaults para dados desconhecidos;
- preserva ``None`` como não informado;
- não interpreta endereço legado não estruturado;
- não converte comunidade tradicional em raça/cor;
- não deriva deficiência a partir de ``has_disability``/transtornos;
- mantém IDs internos e externos em campos distintos.
"""
from __future__ import annotations

from typing import Any, Literal, Mapping, Optional

from pydantic import BaseModel, ConfigDict


CANONICAL_CONTRACT_VERSION = "student-enrollment.v1"

_CANONICAL_RACE_VALUES = {
    "branca",
    "preta",
    "parda",
    "amarela",
    "indigena",
    "nao_declarada",
}
_CANONICAL_SEX_VALUES = {
    "masculino",
    "feminino",
    "prefere_nao_informar",
}
_TRADITIONAL_COMMUNITY_VALUES = {
    "nao_pertence",
    "quilombola",
    "cigano",
    "ribeirinho",
    "extrativista",
}


def _optional_text(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _required_text(value: Any, field_name: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise ValueError(f"{field_name} é obrigatório no contrato canônico")
    return text


def _optional_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def _optional_bool(value: Any) -> Optional[bool]:
    return value if isinstance(value, bool) else None


def _canonical_race(value: Any) -> Optional[str]:
    text = _optional_text(value)
    if text is None:
        return None
    normalized = text.lower()
    return normalized if normalized in _CANONICAL_RACE_VALUES else None


def _canonical_sex(value: Any) -> Optional[str]:
    text = _optional_text(value)
    if text is None:
        return None
    normalized = text.lower()
    return normalized if normalized in _CANONICAL_SEX_VALUES else None


def _canonical_traditional_community(value: Any) -> Optional[str]:
    text = _optional_text(value)
    if text is None:
        return None
    normalized = text.lower()
    return normalized if normalized in _TRADITIONAL_COMMUNITY_VALUES else None


def _derive_quilombola(community: Optional[str]) -> Optional[bool]:
    if community is None:
        return None
    return community == "quilombola"


class _CanonicalBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CanonicalStudentAddressDTO(_CanonicalBaseModel):
    zip_code: Optional[str] = None
    state: Optional[str] = None
    state_ibge_code: Optional[str] = None
    city: Optional[str] = None
    city_ibge_code: Optional[str] = None
    neighborhood: Optional[str] = None
    street: Optional[str] = None
    number: Optional[str] = None
    complement: Optional[str] = None
    geographic_location: Optional[str] = None
    differentiated_location: Optional[str] = None


class CanonicalStudentDTO(_CanonicalBaseModel):
    student_id: str
    tenant_id: Optional[str] = None
    sgp_student_id: Optional[str] = None

    full_name: Optional[str] = None
    social_name: Optional[str] = None
    birth_date: Optional[str] = None
    cpf: Optional[str] = None
    rg: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    nis: Optional[str] = None

    sex: Optional[str] = None
    color_race: Optional[str] = None
    nationality: Optional[str] = None
    birth_state: Optional[str] = None
    birth_city: Optional[str] = None

    traditional_community: Optional[str] = None
    quilombola: Optional[bool] = None

    # Intencionalmente não derivado na B.1. A tabela oficial de condições/deficiências
    # pertence às fases de conversão/mapper e deve ser confirmada antes de uso.
    student_with_disability: Optional[bool] = None

    address: Optional[CanonicalStudentAddressDTO] = None


class CanonicalEnrollmentDTO(_CanonicalBaseModel):
    enrollment_id: str
    sgp_enrollment_id: Optional[str] = None
    student_id: str
    school_id: Optional[str] = None
    class_id: Optional[str] = None

    enrollment_number: Optional[str] = None
    enrollment_date: Optional[str] = None
    enrollment_end_date: Optional[str] = None
    high_school_eja_completion_date: Optional[str] = None
    academic_year: Optional[int] = None
    status: Optional[str] = None

    education_level: Optional[str] = None
    student_series: Optional[str] = None
    grade_level: Optional[str] = None
    needs_pedagogical_support: Optional[bool] = None


class CanonicalStudentEnrollmentDTO(_CanonicalBaseModel):
    contract_version: Literal["student-enrollment.v1"] = CANONICAL_CONTRACT_VERSION
    student: CanonicalStudentDTO
    enrollment: CanonicalEnrollmentDTO


def _build_address(address: Any) -> Optional[CanonicalStudentAddressDTO]:
    """Projeta apenas o novo endereço estruturado; legado string/list/null não é interpretado."""
    if not isinstance(address, Mapping):
        return None
    return CanonicalStudentAddressDTO(
        zip_code=_optional_text(address.get("zip_code")),
        state=_optional_text(address.get("state")),
        state_ibge_code=_optional_text(address.get("state_ibge_code")),
        city=_optional_text(address.get("city")),
        city_ibge_code=_optional_text(address.get("city_ibge_code")),
        neighborhood=_optional_text(address.get("neighborhood")),
        street=_optional_text(address.get("street")),
        number=_optional_text(address.get("number")),
        complement=_optional_text(address.get("complement")),
        geographic_location=_optional_text(address.get("geographic_location")),
        differentiated_location=_optional_text(address.get("differentiated_location")),
    )


def build_canonical_student_enrollment(
    *,
    student: Mapping[str, Any],
    enrollment: Mapping[str, Any],
    class_record: Optional[Mapping[str, Any]] = None,
    tenant_id: Optional[str] = None,
) -> CanonicalStudentEnrollmentDTO:
    """Projeta Student + Enrollment SIGESC sem qualquer tradução específica de provider."""
    student_id = _required_text(student.get("id"), "student.id")
    enrollment_id = _required_text(enrollment.get("id"), "enrollment.id")
    enrollment_student_id = _required_text(enrollment.get("student_id"), "enrollment.student_id")

    if enrollment_student_id != student_id:
        raise ValueError("enrollment.student_id diverge de student.id")

    class_data: Mapping[str, Any] = class_record or {}
    community = _canonical_traditional_community(student.get("comunidade_tradicional"))
    student_series = _optional_text(enrollment.get("student_series"))
    grade_level = student_series or _optional_text(class_data.get("grade_level"))

    canonical_student = CanonicalStudentDTO(
        student_id=student_id,
        tenant_id=_optional_text(tenant_id) or _optional_text(student.get("mantenedora_id")),
        # Campo ainda não persistido no modelo Student na B.1; se existir futuramente,
        # será transportado sem substituir o ID interno.
        sgp_student_id=_optional_text(student.get("sgp_student_id")),
        full_name=_optional_text(student.get("full_name")),
        social_name=_optional_text(student.get("social_name")),
        birth_date=_optional_text(student.get("birth_date")),
        cpf=_optional_text(student.get("cpf")),
        rg=_optional_text(student.get("rg")),
        email=_optional_text(student.get("email")),
        phone=_optional_text(student.get("phone")),
        nis=_optional_text(student.get("nis")),
        sex=_canonical_sex(student.get("sex")),
        color_race=_canonical_race(student.get("color_race")),
        nationality=_optional_text(student.get("nationality")),
        birth_state=_optional_text(student.get("birth_state")),
        birth_city=_optional_text(student.get("birth_city")),
        traditional_community=community,
        quilombola=_derive_quilombola(community),
        student_with_disability=None,
        address=_build_address(student.get("address")),
    )

    canonical_enrollment = CanonicalEnrollmentDTO(
        enrollment_id=enrollment_id,
        sgp_enrollment_id=_optional_text(enrollment.get("sgp_enrollment_id")),
        student_id=enrollment_student_id,
        school_id=_optional_text(enrollment.get("school_id")),
        class_id=_optional_text(enrollment.get("class_id")),
        enrollment_number=_optional_text(enrollment.get("enrollment_number")),
        enrollment_date=_optional_text(enrollment.get("enrollment_date")),
        enrollment_end_date=_optional_text(enrollment.get("enrollment_end_date")),
        high_school_eja_completion_date=_optional_text(
            enrollment.get("high_school_eja_completion_date")
        ),
        academic_year=_optional_int(enrollment.get("academic_year")),
        status=_optional_text(enrollment.get("status")),
        education_level=_optional_text(class_data.get("education_level")),
        student_series=student_series,
        grade_level=grade_level,
        needs_pedagogical_support=_optional_bool(
            enrollment.get("needs_pedagogical_support")
        ),
    )

    return CanonicalStudentEnrollmentDTO(
        student=canonical_student,
        enrollment=canonical_enrollment,
    )
