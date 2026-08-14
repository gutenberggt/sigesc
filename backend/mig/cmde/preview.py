"""Dry-run/Preview operacional de Student + Enrollment para CMDEB.

Fase B.6 da interoperabilidade Student + Enrollment.

Esta camada reúne B.1–B.5 para responder, sem qualquer efeito colateral:
- quais matrículas selecionadas estão prontas;
- quais estão bloqueadas e por quê;
- quais IDs externos SGP já estão vinculados na SSoT MIG;
- qual registro de payload seria produzido para cada item pronto;
- qual payload de lote seria produzido SOMENTE se toda a página estiver pronta.

Invariantes:
- somente leituras no MongoDB;
- não chama provider/HTTP;
- não cria fila, lote, idempotency key ou audit event;
- não grava/atualiza Student, Enrollment ou mig_sgp_external_ids;
- coleção B.5 é a única fonte dos IDs externos no preview;
- um lote parcial nunca é apresentado como payload pronto para envio;
- identidade já conciliada no SGP não é candidata a lote de cadastro novo.
"""
from __future__ import annotations

from collections import Counter
from math import ceil
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from mig.cmde.external_ids import SgpExternalIdPair, SgpExternalIdStore
from mig.cmde.readiness import (
    CMDE_LOT_ENDPOINTS,
    CMDE_READINESS_VERSION,
    CmdeLotType,
    CmdeReadinessIssue,
    CmdeRecordReadinessReport,
    validate_cmde_record_readiness,
)
from mig.cmde.student_serializer import (
    CMDE_STUDENT_SERIALIZER_VERSION,
    CmdeStudentSchoolContext,
    CmdeStudentSerializationError,
    map_canonical_student_without_class,
    serialize_student_without_class_batch,
)
from mig.core.canonical_student import (
    CANONICAL_CONTRACT_VERSION,
    CanonicalStudentEnrollmentDTO,
    build_canonical_student_enrollment,
)
from mig.core.exceptions import MigConfigError, MigForbiddenError


CMDE_OPERATIONAL_PREVIEW_VERSION = "cmdeb-v2.preview.2026-08-14"
_ACTIVE_ENROLLMENT_STATUSES = ("active", "Ativo")
_CREATE_LOT_TYPES = frozenset(
    {
        CmdeLotType.STUDENT_WITHOUT_CLASS_CREATE.value,
        CmdeLotType.STUDENT_WITH_CLASS_CREATE.value,
    }
)


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CmdeStudentPreviewRequestDTO(BaseModel):
    """Seleção read-only para o preview.

    ``dry_run=False`` é estruturalmente inválido: este endpoint não possui modo de
    envio. Paginação limita exposição de PII e evita respostas gigantes.
    """

    model_config = ConfigDict(extra="forbid")

    dry_run: Literal[True] = True
    lot_type: str = CmdeLotType.STUDENT_WITHOUT_CLASS_CREATE.value
    tenant_id: Optional[str] = None
    school_id: Optional[str] = None
    class_id: Optional[str] = None
    student_id: Optional[str] = None
    enrollment_id: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=100, ge=1, le=200)


class CmdePreviewExternalIds(_FrozenModel):
    source: Literal["mig_sgp_external_ids"] = "mig_sgp_external_ids"
    student_external_id: Optional[str] = None
    enrollment_external_id: Optional[str] = None


class CmdeOperationalPreviewRecord(_FrozenModel):
    student_id: Optional[str] = None
    enrollment_id: Optional[str] = None
    school_id: Optional[str] = None
    class_id: Optional[str] = None
    external_ids: CmdePreviewExternalIds
    ready: bool
    blocker_count: int
    warning_count: int
    issues: tuple[CmdeReadinessIssue, ...]
    readiness: Optional[CmdeRecordReadinessReport] = None
    candidate_payload_record: Optional[dict[str, Any]] = None


class CmdeOperationalPreviewReport(_FrozenModel):
    mode: Literal["dry_run"] = "dry_run"
    preview_version: str = CMDE_OPERATIONAL_PREVIEW_VERSION
    canonical_contract_version: str = CANONICAL_CONTRACT_VERSION
    readiness_version: str = CMDE_READINESS_VERSION
    serializer_version: str = CMDE_STUDENT_SERIALIZER_VERSION
    lot_type: str
    endpoint: Optional[str] = None
    tenant_id: str
    page: int
    page_size: int
    total_matching: int
    total_pages: int
    page_records: int
    ready_records: int
    blocked_records: int
    warning_records: int
    blocker_counts: dict[str, int]
    warning_counts: dict[str, int]
    page_ready: bool
    page_payload: Optional[dict[str, Any]] = None
    payload_scope: Literal["current_page"] = "current_page"
    provider_called: Literal[False] = False
    write_attempted: Literal[False] = False
    queue_touched: Literal[False] = False
    records: tuple[CmdeOperationalPreviewRecord, ...]


def _text(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _projection_issue(message: str) -> CmdeReadinessIssue:
    return CmdeReadinessIssue(
        code="canonical_projection_failed",
        field="canonical",
        severity="error",
        message=message,
    )


def _serialization_issue() -> CmdeReadinessIssue:
    return CmdeReadinessIssue(
        code="preview_serialization_failed",
        field="payload",
        severity="error",
        message=(
            "o registro passou pelo gate de prontidão, mas o serializer recusou "
            "a geração do candidato de payload"
        ),
    )


def _external_identity_issue() -> CmdeReadinessIssue:
    return CmdeReadinessIssue(
        code="external_identity_already_exists",
        field="external_ids",
        severity="error",
        message=(
            "há identidade SGP já conciliada pela B.5; lote de cadastro novo não "
            "é aplicável a este registro"
        ),
    )


def _resolve_tenant(request: CmdeStudentPreviewRequestDTO, context: dict[str, Any]) -> str:
    context_tenant = _text((context or {}).get("tenant"))
    requested_tenant = _text(request.tenant_id)

    if context_tenant and requested_tenant and context_tenant != requested_tenant:
        raise MigForbiddenError(
            "tenant_id do preview diverge do escopo de mantenedora autenticado"
        )

    tenant = context_tenant or requested_tenant
    if tenant is None:
        raise MigConfigError(
            "tenant_id é obrigatório para preview cross-tenant; selecione uma mantenedora"
        )
    return tenant


def _hydrate_external_ids(
    canonical: CanonicalStudentEnrollmentDTO,
    pair: SgpExternalIdPair,
) -> CanonicalStudentEnrollmentDTO:
    """Substitui slots externos pelo vínculo B.5, inclusive por ``None``.

    Isso impede que ``Enrollment.sgp_enrollment_id`` legado se torne uma segunda
    fonte de verdade no preview.
    """
    student = canonical.student.model_copy(
        update={"sgp_student_id": pair.student_external_id}
    )
    enrollment = canonical.enrollment.model_copy(
        update={"sgp_enrollment_id": pair.enrollment_external_id}
    )
    return canonical.model_copy(update={"student": student, "enrollment": enrollment})


def _matches_projection_failure(
    *,
    enrollment: dict[str, Any],
    message: str,
) -> CmdeOperationalPreviewRecord:
    issue = _projection_issue(message)
    return CmdeOperationalPreviewRecord(
        student_id=_text(enrollment.get("student_id")),
        enrollment_id=_text(enrollment.get("id")),
        school_id=_text(enrollment.get("school_id")),
        class_id=_text(enrollment.get("class_id")),
        external_ids=CmdePreviewExternalIds(),
        ready=False,
        blocker_count=1,
        warning_count=0,
        issues=(issue,),
    )


def _count_issues(
    records: list[CmdeOperationalPreviewRecord],
    *,
    severity: Literal["error", "warning"],
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for record in records:
        counts.update(
            issue.code for issue in record.issues if issue.severity == severity
        )
    return dict(sorted(counts.items()))


class CmdeOperationalPreviewService:
    """Orquestrador read-only do preview B.6."""

    def __init__(self, db):
        self.db = db
        self.external_ids = SgpExternalIdStore(db)

    async def build(
        self,
        request: CmdeStudentPreviewRequestDTO,
        context: Optional[dict[str, Any]] = None,
    ) -> CmdeOperationalPreviewReport:
        tenant_id = _resolve_tenant(request, context or {})
        lot_type = request.lot_type.strip()

        query: dict[str, Any] = {
            "mantenedora_id": tenant_id,
            "status": {"$in": list(_ACTIVE_ENROLLMENT_STATUSES)},
        }
        for key, value in (
            ("school_id", request.school_id),
            ("class_id", request.class_id),
            ("student_id", request.student_id),
            ("id", request.enrollment_id),
        ):
            normalized = _text(value)
            if normalized is not None:
                query[key] = normalized

        enrollment_collection = self.db["enrollments"]
        total_matching = await enrollment_collection.count_documents(query)
        skip = (request.page - 1) * request.page_size
        enrollments = await (
            enrollment_collection.find(query, {"_id": 0})
            .sort("id", 1)
            .skip(skip)
            .limit(request.page_size)
            .to_list(request.page_size)
        )

        student_ids = sorted(
            {
                student_id
                for enrollment in enrollments
                if (student_id := _text(enrollment.get("student_id"))) is not None
            }
        )
        school_ids = sorted(
            {
                school_id
                for enrollment in enrollments
                if (school_id := _text(enrollment.get("school_id"))) is not None
            }
        )
        class_ids = sorted(
            {
                class_id
                for enrollment in enrollments
                if (class_id := _text(enrollment.get("class_id"))) is not None
            }
        )

        students = (
            await self.db["students"]
            .find(
                {"mantenedora_id": tenant_id, "id": {"$in": student_ids}},
                {"_id": 0},
            )
            .to_list(len(student_ids))
            if student_ids
            else []
        )
        schools = (
            await self.db["schools"]
            .find(
                {"mantenedora_id": tenant_id, "id": {"$in": school_ids}},
                {"_id": 0},
            )
            .to_list(len(school_ids))
            if school_ids
            else []
        )
        classes = (
            await self.db["classes"]
            .find(
                {"mantenedora_id": tenant_id, "id": {"$in": class_ids}},
                {"_id": 0},
            )
            .to_list(len(class_ids))
            if class_ids
            else []
        )

        student_map = {item.get("id"): item for item in students if item.get("id")}
        school_map = {item.get("id"): item for item in schools if item.get("id")}
        class_map = {item.get("id"): item for item in classes if item.get("id")}

        records: list[CmdeOperationalPreviewRecord] = []
        page_mapped_records = []

        for enrollment in enrollments:
            student_id = _text(enrollment.get("student_id"))
            enrollment_id = _text(enrollment.get("id"))
            if student_id is None or enrollment_id is None:
                records.append(
                    _matches_projection_failure(
                        enrollment=enrollment,
                        message="matrícula sem identificadores internos mínimos",
                    )
                )
                continue

            student = student_map.get(student_id)
            if student is None:
                records.append(
                    _matches_projection_failure(
                        enrollment=enrollment,
                        message="Student referenciado pela matrícula não foi encontrado no tenant",
                    )
                )
                continue

            class_record = class_map.get(_text(enrollment.get("class_id")))
            school_record = school_map.get(_text(enrollment.get("school_id"))) or {}
            school_context = CmdeStudentSchoolContext(
                school_inep_code=_text(school_record.get("inep_code")),
                school_name=_text(school_record.get("name")),
            )

            try:
                canonical = build_canonical_student_enrollment(
                    student=student,
                    enrollment=enrollment,
                    class_record=class_record,
                    tenant_id=tenant_id,
                )
            except (TypeError, ValueError):
                records.append(
                    _matches_projection_failure(
                        enrollment=enrollment,
                        message="Student + Enrollment não puderam formar o contrato canônico B.1",
                    )
                )
                continue

            pair = await self.external_ids.resolve_pair(
                tenant_id=tenant_id,
                student_internal_id=student_id,
                enrollment_internal_id=enrollment_id,
            )
            canonical = _hydrate_external_ids(canonical, pair)

            readiness = validate_cmde_record_readiness(
                canonical,
                lot_type=lot_type,
                school=school_context,
            )
            issues = list(readiness.issues)
            candidate_payload_record: Optional[dict[str, Any]] = None
            mapped_record = None
            ready = readiness.ready

            # Guarda operacional B.5: create não deve sugerir recadastro de uma
            # identidade já conhecida no SGP. Fluxos de edição/matrícula futuros
            # usarão esses IDs quando seus lot_types forem implementados.
            if lot_type in _CREATE_LOT_TYPES and (
                pair.student_external_id is not None
                or pair.enrollment_external_id is not None
            ):
                issues.append(_external_identity_issue())
                ready = False

            if ready:
                try:
                    mapped_record = map_canonical_student_without_class(
                        canonical,
                        school=school_context,
                    )
                    candidate_payload_record = mapped_record.model_dump(
                        mode="json",
                        exclude_none=True,
                    )
                except CmdeStudentSerializationError:
                    issues.append(_serialization_issue())
                    ready = False

            blockers = sum(issue.severity == "error" for issue in issues)
            warnings = sum(issue.severity == "warning" for issue in issues)
            records.append(
                CmdeOperationalPreviewRecord(
                    student_id=student_id,
                    enrollment_id=enrollment_id,
                    school_id=_text(enrollment.get("school_id")),
                    class_id=_text(enrollment.get("class_id")),
                    external_ids=CmdePreviewExternalIds(
                        student_external_id=pair.student_external_id,
                        enrollment_external_id=pair.enrollment_external_id,
                    ),
                    ready=ready,
                    blocker_count=blockers,
                    warning_count=warnings,
                    issues=tuple(issues),
                    readiness=readiness,
                    candidate_payload_record=candidate_payload_record,
                )
            )
            if ready and mapped_record is not None:
                page_mapped_records.append(mapped_record)

        ready_records = sum(record.ready for record in records)
        blocked_records = len(records) - ready_records
        warning_records = sum(record.warning_count > 0 for record in records)
        page_ready = bool(records) and blocked_records == 0

        # Fail-closed: em página mista, não montamos um lote parcial silencioso.
        page_payload = (
            serialize_student_without_class_batch(page_mapped_records)
            if page_ready
            else None
        )

        return CmdeOperationalPreviewReport(
            lot_type=lot_type,
            endpoint=CMDE_LOT_ENDPOINTS.get(lot_type),
            tenant_id=tenant_id,
            page=request.page,
            page_size=request.page_size,
            total_matching=total_matching,
            total_pages=ceil(total_matching / request.page_size) if total_matching else 0,
            page_records=len(records),
            ready_records=ready_records,
            blocked_records=blocked_records,
            warning_records=warning_records,
            blocker_counts=_count_issues(records, severity="error"),
            warning_counts=_count_issues(records, severity="warning"),
            page_ready=page_ready,
            page_payload=page_payload,
            records=tuple(records),
        )