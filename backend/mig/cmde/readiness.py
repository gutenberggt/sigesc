"""Validador de prontidão CMDEB por tipo de lote.

Fase B.4 da interoperabilidade Student + Enrollment.

O validador é deliberadamente anterior ao preview/envio. Ele não consulta banco,
não faz HTTP e não cria fila. Seu papel é dizer, de forma determinística, se um
registro canônico possui dados suficientes e semanticamente convertíveis para um
tipo de lote CMDE conhecido.

Princípios:
- fail-closed para tipos de lote ainda não implementados;
- erros por campo, sem expor valores pessoais no diagnóstico;
- ``None`` continua sendo ausência, nunca default;
- códigos IBGE são validados somente quando já persistidos, nunca inferidos;
- dimensões B.2 presentes, mas ainda sem legenda oficial, bloqueiam prontidão;
- o serializer B.3 é usado como guarda final, não como substituto do diagnóstico.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Iterable, Literal, Optional

from pydantic import BaseModel, ConfigDict

from mig.cmde.code_tables import CmdeCodeMappingError, convert_cmde_code
from mig.cmde.student_serializer import (
    CMDE_STUDENT_SERIALIZER_VERSION,
    CMDE_STUDENT_WITHOUT_CLASS_CREATE_ENDPOINT,
    CmdeStudentSchoolContext,
    CmdeStudentSerializationError,
    map_canonical_student_without_class,
)
from mig.core.canonical_student import (
    CANONICAL_CONTRACT_VERSION,
    CanonicalStudentEnrollmentDTO,
)


CMDE_READINESS_VERSION = "cmdeb-v2.readiness.2026-08-14"
CMDE_OFFICIAL_DOC_VERSION = "2.0.0"


class CmdeLotType(str, Enum):
    """Tipos Student/Enrollment publicados no contrato CMDEB v2 atual."""

    STUDENT_WITHOUT_CLASS_CREATE = "student_without_class_create"
    STUDENT_WITH_CLASS_CREATE = "student_with_class_create"
    STUDENT_EDIT = "student_edit"
    ENROLLMENT_CLASS_ASSIGNMENT = "enrollment_class_assignment"
    ENROLLMENT_CLASS_ASSIGNMENT_EDIT = "enrollment_class_assignment_edit"
    ENROLLMENT_EDIT = "enrollment_edit"
    ENROLLMENT_MOVEMENT = "enrollment_movement"
    ENROLLMENT_CONFIRM_COMPLETION = "enrollment_confirm_completion"


CMDE_LOT_ENDPOINTS = MappingProxyType(
    {
        CmdeLotType.STUDENT_WITHOUT_CLASS_CREATE.value: (
            CMDE_STUDENT_WITHOUT_CLASS_CREATE_ENDPOINT
        ),
        CmdeLotType.STUDENT_WITH_CLASS_CREATE.value: (
            "/api/v2/estudantes/com-turma/cadastro/lote"
        ),
        CmdeLotType.STUDENT_EDIT.value: "/api/v2/estudantes/edicao/lote",
        CmdeLotType.ENROLLMENT_CLASS_ASSIGNMENT.value: (
            "/api/v2/matriculas/enturmacao/lote"
        ),
        CmdeLotType.ENROLLMENT_CLASS_ASSIGNMENT_EDIT.value: (
            "/api/v2/matriculas/enturmacao/edicao/lote"
        ),
        CmdeLotType.ENROLLMENT_EDIT.value: "/api/v2/matriculas/edicao/lote",
        CmdeLotType.ENROLLMENT_MOVEMENT.value: (
            "/api/v2/matriculas/movimentacao/lote"
        ),
        CmdeLotType.ENROLLMENT_CONFIRM_COMPLETION.value: (
            "/api/v2/matriculas/confirmar-conclusao/lote"
        ),
    }
)

IMPLEMENTED_READINESS_LOT_TYPES = frozenset(
    {CmdeLotType.STUDENT_WITHOUT_CLASS_CREATE.value}
)


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CmdeReadinessIssue(_FrozenModel):
    code: str
    field: str
    severity: Literal["error", "warning"]
    message: str


class CmdeRecordReadinessReport(_FrozenModel):
    lot_type: str
    endpoint: Optional[str] = None
    readiness_version: str = CMDE_READINESS_VERSION
    canonical_contract_version: str = CANONICAL_CONTRACT_VERSION
    serializer_version: str = CMDE_STUDENT_SERIALIZER_VERSION
    student_id: str
    enrollment_id: str
    ready: bool
    blocker_count: int
    warning_count: int
    issues: tuple[CmdeReadinessIssue, ...]


class CmdeBatchReadinessReport(_FrozenModel):
    lot_type: str
    endpoint: Optional[str] = None
    readiness_version: str = CMDE_READINESS_VERSION
    ready: bool
    total_records: int
    ready_records: int
    blocked_records: int
    batch_issues: tuple[CmdeReadinessIssue, ...]
    records: tuple[CmdeRecordReadinessReport, ...]


def _lot_type_value(lot_type: CmdeLotType | str) -> str:
    if isinstance(lot_type, CmdeLotType):
        return lot_type.value
    return str(lot_type).strip()


def _text(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _issue(
    *,
    code: str,
    field: str,
    message: str,
    severity: Literal["error", "warning"] = "error",
) -> CmdeReadinessIssue:
    return CmdeReadinessIssue(
        code=code,
        field=field,
        severity=severity,
        message=message,
    )


def _has_error(issues: Iterable[CmdeReadinessIssue]) -> bool:
    return any(issue.severity == "error" for issue in issues)


def _is_digits(value: Any, digits: int) -> bool:
    text = _text(value)
    return bool(text and text.isdigit() and len(text) == digits)


def _valid_date(value: Any) -> bool:
    text = _text(value)
    if text is None:
        return False
    for source_format in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            datetime.strptime(text, source_format)
            return True
        except ValueError:
            continue
    return False


def _education_stage_value(canonical: CanonicalStudentEnrollmentDTO) -> Optional[str]:
    enrollment = canonical.enrollment
    level = _text(enrollment.education_level)
    grade = _text(enrollment.grade_level)
    if level is None and grade is None:
        return None
    return " | ".join(part for part in (level, grade) if part is not None)


def _append_mapping_issue(
    issues: list[CmdeReadinessIssue],
    *,
    table_name: str,
    field: str,
    value: Any,
) -> None:
    if value is None:
        return
    try:
        convert_cmde_code(table_name, value)
    except CmdeCodeMappingError:
        issues.append(
            _issue(
                code="unverified_mapping",
                field=field,
                message=(
                    "valor informado, mas a conversão CMDE correspondente ainda "
                    "não possui equivalência oficial habilitada"
                ),
            )
        )


def _validate_student_without_class_create(
    canonical: CanonicalStudentEnrollmentDTO,
    *,
    school: Optional[CmdeStudentSchoolContext],
) -> list[CmdeReadinessIssue]:
    student = canonical.student
    enrollment = canonical.enrollment
    address = student.address
    issues: list[CmdeReadinessIssue] = []

    # Perfil mínimo operacional do MIG para não produzir um cadastro sem
    # identidade, vínculo escolar ou territorialidade inequívoca.
    if _text(student.full_name) is None:
        issues.append(
            _issue(
                code="missing_required",
                field="student.full_name",
                message="nome completo é necessário para o lote de cadastro",
            )
        )

    if _text(student.cpf) is None:
        issues.append(
            _issue(
                code="missing_required",
                field="student.cpf",
                message="CPF é necessário para o lote de cadastro",
            )
        )
    elif not _is_digits(student.cpf, 11):
        issues.append(
            _issue(
                code="invalid_format",
                field="student.cpf",
                message="CPF deve conter exatamente 11 dígitos",
            )
        )

    if _text(student.birth_date) is None:
        issues.append(
            _issue(
                code="missing_required",
                field="student.birth_date",
                message="data de nascimento é necessária para o lote de cadastro",
            )
        )
    elif not _valid_date(student.birth_date):
        issues.append(
            _issue(
                code="invalid_format",
                field="student.birth_date",
                message="data deve usar DD/MM/AAAA ou AAAA-MM-DD",
            )
        )

    if _text(enrollment.enrollment_number) is None:
        issues.append(
            _issue(
                code="missing_required",
                field="enrollment.enrollment_number",
                message="matrícula da rede é necessária para o lote de cadastro",
            )
        )

    if _text(enrollment.enrollment_date) is None:
        issues.append(
            _issue(
                code="missing_required",
                field="enrollment.enrollment_date",
                message="data de início da matrícula é necessária para o lote de cadastro",
            )
        )
    elif not _valid_date(enrollment.enrollment_date):
        issues.append(
            _issue(
                code="invalid_format",
                field="enrollment.enrollment_date",
                message="data deve usar DD/MM/AAAA ou AAAA-MM-DD",
            )
        )

    if enrollment.academic_year is None:
        issues.append(
            _issue(
                code="missing_required",
                field="enrollment.academic_year",
                message="ano da matrícula é necessário para o lote de cadastro",
            )
        )
    elif not 1900 <= enrollment.academic_year <= 2100:
        issues.append(
            _issue(
                code="invalid_format",
                field="enrollment.academic_year",
                message="ano da matrícula está fora do intervalo operacional aceito",
            )
        )

    school_context = school or CmdeStudentSchoolContext()
    if _text(school_context.school_inep_code) is None:
        issues.append(
            _issue(
                code="missing_required",
                field="school.school_inep_code",
                message="código INEP da escola é necessário para rotear o cadastro",
            )
        )
    elif not _is_digits(school_context.school_inep_code, 8):
        issues.append(
            _issue(
                code="invalid_format",
                field="school.school_inep_code",
                message="código INEP deve conter exatamente 8 dígitos",
            )
        )

    if _text(school_context.school_name) is None:
        issues.append(
            _issue(
                code="recommended_missing",
                field="school.school_name",
                severity="warning",
                message="nome da escola não está disponível para enriquecer o payload",
            )
        )

    if address is None:
        issues.append(
            _issue(
                code="missing_required",
                field="student.address",
                message=(
                    "endereço estruturado é necessário para certificar os códigos "
                    "territoriais sem inferência por texto legado"
                ),
            )
        )
    else:
        if _text(address.state_ibge_code) is None:
            issues.append(
                _issue(
                    code="missing_required",
                    field="student.address.state_ibge_code",
                    message="código IBGE da UF é necessário para prontidão territorial",
                )
            )
        elif not _is_digits(address.state_ibge_code, 2):
            issues.append(
                _issue(
                    code="invalid_format",
                    field="student.address.state_ibge_code",
                    message="código IBGE da UF deve conter exatamente 2 dígitos",
                )
            )

        if _text(address.city_ibge_code) is None:
            issues.append(
                _issue(
                    code="missing_required",
                    field="student.address.city_ibge_code",
                    message=(
                        "código IBGE do município é necessário para prontidão territorial"
                    ),
                )
            )
        elif not _is_digits(address.city_ibge_code, 7):
            issues.append(
                _issue(
                    code="invalid_format",
                    field="student.address.city_ibge_code",
                    message="código IBGE do município deve conter exatamente 7 dígitos",
                )
            )

        if _text(address.zip_code) is None:
            issues.append(
                _issue(
                    code="recommended_missing",
                    field="student.address.zip_code",
                    severity="warning",
                    message="CEP não está disponível para enriquecer o payload",
                )
            )
        elif not _is_digits(address.zip_code, 8):
            issues.append(
                _issue(
                    code="invalid_format",
                    field="student.address.zip_code",
                    message="CEP informado deve conter exatamente 8 dígitos",
                )
            )

        for field_name, value, label in (
            ("student.address.neighborhood", address.neighborhood, "bairro"),
            ("student.address.street", address.street, "logradouro"),
            ("student.address.number", address.number, "número do endereço"),
        ):
            if _text(value) is None:
                issues.append(
                    _issue(
                        code="recommended_missing",
                        field=field_name,
                        severity="warning",
                        message=f"{label} não está disponível para enriquecer o payload",
                    )
                )

        # Essas dimensões já existem na B.2. Se o SIGESC conhece o valor, ele
        # não pode simplesmente desaparecer até a tabela oficial ser habilitada.
        _append_mapping_issue(
            issues,
            table_name="geographic_location",
            field="student.address.geographic_location",
            value=address.geographic_location,
        )
        _append_mapping_issue(
            issues,
            table_name="differentiated_location",
            field="student.address.differentiated_location",
            value=address.differentiated_location,
        )

    _append_mapping_issue(
        issues,
        table_name="sex",
        field="student.sex",
        value=student.sex,
    )
    _append_mapping_issue(
        issues,
        table_name="race_color",
        field="student.color_race",
        value=student.color_race,
    )
    _append_mapping_issue(
        issues,
        table_name="nationality",
        field="student.nationality",
        value=student.nationality,
    )
    _append_mapping_issue(
        issues,
        table_name="quilombola",
        field="student.quilombola",
        value=student.quilombola,
    )
    _append_mapping_issue(
        issues,
        table_name="pedagogical_support",
        field="enrollment.needs_pedagogical_support",
        value=enrollment.needs_pedagogical_support,
    )
    _append_mapping_issue(
        issues,
        table_name="education_stage",
        field="enrollment.education_level + enrollment.grade_level",
        value=_education_stage_value(canonical),
    )

    if student.student_with_disability is not None:
        issues.append(
            _issue(
                code="unverified_mapping",
                field="student.student_with_disability",
                message="conversão oficial de deficiência ainda não está habilitada",
            )
        )

    # Guarda de integração com a B.3. Só roda quando os diagnósticos anteriores
    # não encontraram bloqueadores; assim evita mensagens duplicadas e garante
    # que qualquer restrição residual do serializer também feche o gate.
    if not _has_error(issues):
        try:
            map_canonical_student_without_class(canonical, school=school_context)
        except CmdeStudentSerializationError:
            issues.append(
                _issue(
                    code="serialization_blocked",
                    field="payload",
                    message=(
                        "o serializer CMDE bloqueou o registro; revisar o contrato "
                        "canônico e as tabelas de conversão"
                    ),
                )
            )

    return issues


def validate_cmde_record_readiness(
    canonical: CanonicalStudentEnrollmentDTO,
    *,
    lot_type: CmdeLotType | str,
    school: Optional[CmdeStudentSchoolContext] = None,
) -> CmdeRecordReadinessReport:
    """Valida um registro sem produzir payload nem executar efeitos colaterais."""
    lot_type_value = _lot_type_value(lot_type)
    endpoint = CMDE_LOT_ENDPOINTS.get(lot_type_value)

    if lot_type_value not in CMDE_LOT_ENDPOINTS:
        issues = [
            _issue(
                code="unknown_lot_type",
                field="lot_type",
                message="tipo de lote não existe no catálogo CMDEB registrado na B.4",
            )
        ]
    elif lot_type_value not in IMPLEMENTED_READINESS_LOT_TYPES:
        issues = [
            _issue(
                code="unsupported_lot_type",
                field="lot_type",
                message=(
                    "endpoint CMDE conhecido, mas o perfil de prontidão deste tipo "
                    "de lote ainda não foi implementado"
                ),
            )
        ]
    else:
        issues = _validate_student_without_class_create(canonical, school=school)

    blockers = sum(issue.severity == "error" for issue in issues)
    warnings = sum(issue.severity == "warning" for issue in issues)
    return CmdeRecordReadinessReport(
        lot_type=lot_type_value,
        endpoint=endpoint,
        student_id=canonical.student.student_id,
        enrollment_id=canonical.enrollment.enrollment_id,
        ready=blockers == 0,
        blocker_count=blockers,
        warning_count=warnings,
        issues=tuple(issues),
    )


def validate_cmde_batch_readiness(
    items: Iterable[
        tuple[CanonicalStudentEnrollmentDTO, Optional[CmdeStudentSchoolContext]]
    ],
    *,
    lot_type: CmdeLotType | str,
) -> CmdeBatchReadinessReport:
    """Agrega prontidão por registro para uso futuro no preview B.6."""
    lot_type_value = _lot_type_value(lot_type)
    pairs = tuple(items)
    batch_issues: list[CmdeReadinessIssue] = []

    if not pairs:
        batch_issues.append(
            _issue(
                code="empty_batch",
                field="batch",
                message="lote vazio não pode ser considerado pronto",
            )
        )

    reports = tuple(
        validate_cmde_record_readiness(
            canonical,
            lot_type=lot_type_value,
            school=school,
        )
        for canonical, school in pairs
    )
    ready_records = sum(report.ready for report in reports)
    blocked_records = len(reports) - ready_records
    ready = bool(reports) and blocked_records == 0 and not _has_error(batch_issues)

    return CmdeBatchReadinessReport(
        lot_type=lot_type_value,
        endpoint=CMDE_LOT_ENDPOINTS.get(lot_type_value),
        ready=ready,
        total_records=len(reports),
        ready_records=ready_records,
        blocked_records=blocked_records,
        batch_issues=tuple(batch_issues),
        records=reports,
    )
