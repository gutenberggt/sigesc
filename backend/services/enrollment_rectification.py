"""F1.0 — dry-run canônico da Retificação de Matrícula/Turma.

Este módulo é deliberadamente READ-ONLY. Ele não cria protocolo persistido, não
altera matrícula, notas, frequência, histórico ou documentos. A saída materializa
o contrato executável aprovado na F0 e produz um token HMAC stateless que poderá
ser revalidado por uma futura fase de execução.

SSoT normativa:
- docs/governance/RETIFICACAO_MATRICULA_TURMA_F0.md
- docs/governance/RETIFICACAO_MATRICULA_TURMA_F0_ADDENDUM_VALIDACAO_FREQUENCIA.md
- docs/governance/RETIFICACAO_MATRICULA_TURMA_F0_ADDENDUM_DOCUMENTOS.md
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from services.enrollment_service import is_special_class
from utils.curriculum_resolver import resolve_curriculum


CONTRACT_VERSION = "F1.0"
OPERATION = "retificacao_enturmacao"
CONFIRMATION_PHRASE = "CONFIRMO A RETIFICAÇÃO DA MATRÍCULA"
DRY_RUN_TTL_MINUTES = 30
GRADE_VALUE_FIELDS = ("b1", "b2", "rec_s1", "b3", "b4", "rec_s2", "recovery")


class RectificationDryRunError(Exception):
    """Erro de domínio convertido em HTTP pelo router."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 409,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}

    def as_detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.detail}


def _tenant_query(query: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    scoped = dict(query)
    scoped["mantenedora_id"] = tenant_id
    return scoped


def _year(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _norm(value: Any) -> str:
    if value is None:
        return ""
    text = "".join(
        char
        for char in unicodedata.normalize("NFKD", str(value))
        if not unicodedata.combining(char)
    )
    return " ".join(text.casefold().strip().split())


def _stable_doc(doc: dict[str, Any] | None, fields: Iterable[str]) -> dict[str, Any]:
    doc = doc or {}
    return {field: doc.get(field) for field in fields}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _dry_run_secret(explicit: str | None = None) -> bytes:
    secret = explicit or os.environ.get("ENROLLMENT_RECTIFICATION_DRY_RUN_SECRET") or os.environ.get(
        "SNAPSHOT_HMAC_SECRET"
    )
    if not secret or len(secret) < 32:
        raise RectificationDryRunError(
            "RECTIFICATION_DRY_RUN_SECRET_UNAVAILABLE",
            "O segredo de assinatura do dry-run não está configurado com segurança.",
            status_code=503,
        )
    return secret.encode("utf-8")


def _sign_token(payload: dict[str, Any], *, secret: str | None = None) -> str:
    raw = _canonical_json(payload).encode("utf-8")
    signature = hmac.new(_dry_run_secret(secret), raw, hashlib.sha256).digest()
    return f"{_b64url(raw)}.{_b64url(signature)}"


def _issue(blockers: list[dict[str, Any]], code: str, message: str, **detail: Any) -> None:
    blockers.append({"code": code, "message": message, "detail": detail or None})


def _warn(warnings: list[dict[str, Any]], code: str, message: str, **detail: Any) -> None:
    warnings.append({"code": code, "message": message, "detail": detail or None})


async def _find_regular_active_enrollments(
    db,
    *,
    student_id: str,
    tenant_id: str,
    academic_year: int,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    enrollments = await db.enrollments.find(
        _tenant_query(
            {
                "student_id": student_id,
                "academic_year": {"$in": [academic_year, str(academic_year)]},
                "status": "active",
            },
            tenant_id,
        ),
        {"_id": 0},
    ).to_list(100)
    result: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for enrollment in enrollments:
        class_id = enrollment.get("class_id")
        if not class_id:
            continue
        class_doc = await db.classes.find_one(
            _tenant_query({"id": class_id}, tenant_id), {"_id": 0}
        )
        if not class_doc:
            raise RectificationDryRunError(
                "ACTIVE_ENROLLMENT_CLASS_MISSING",
                "Existe matrícula ativa apontando para turma inexistente ou fora do tenant.",
                detail={"enrollment_id": enrollment.get("id"), "class_id": class_id},
            )
        if not is_special_class(class_doc):
            result.append((enrollment, class_doc))
    return result


async def _load_courses(db, ids: set[str], tenant_id: str) -> dict[str, dict[str, Any]]:
    if not ids:
        return {}
    docs = await db.courses.find(
        _tenant_query({"id": {"$in": sorted(ids)}}, tenant_id), {"_id": 0}
    ).to_list(500)
    return {doc.get("id"): doc for doc in docs if doc.get("id")}


async def _destination_curriculum(
    db,
    *,
    student_id: str,
    destination_class: dict[str, Any],
    academic_year: int,
    tenant_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    resolution = await resolve_curriculum(
        db,
        student_id=student_id,
        class_id=destination_class["id"],
        academic_year=academic_year,
        class_info=destination_class,
        student_info={
            "id": student_id,
            "student_series": destination_class.get("grade_level"),
            "class_id": destination_class["id"],
        },
        atendimento_programa_filter=destination_class.get("atendimento_programa"),
    )
    resolved = resolution.get("components") or []
    ids = {item.get("course_id") for item in resolved if item.get("course_id")}
    course_map = await _load_courses(db, {str(x) for x in ids if x}, tenant_id)
    components = []
    for item in resolved:
        course_id = item.get("course_id")
        doc = course_map.get(course_id) or {}
        components.append(
            {
                "course_id": course_id,
                "name": doc.get("name"),
                "code": doc.get("code"),
                "source": item.get("source"),
                "evidence_score": item.get("evidence_score", 0),
            }
        )
    return components, resolution.get("warnings") or []


def _build_course_map(
    source_courses: dict[str, dict[str, Any]],
    destination_components: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    blockers: list[dict[str, Any]] = []
    destination_by_id = {
        item.get("course_id"): item for item in destination_components if item.get("course_id")
    }
    by_code: dict[str, list[dict[str, Any]]] = {}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for item in destination_components:
        code = _norm(item.get("code"))
        name = _norm(item.get("name"))
        if code:
            by_code.setdefault(code, []).append(item)
        if name:
            by_name.setdefault(name, []).append(item)

    mapped: list[dict[str, Any]] = []
    for source_id, source in sorted(source_courses.items()):
        candidates: list[dict[str, Any]] = []
        method = None
        if source_id in destination_by_id:
            candidates = [destination_by_id[source_id]]
            method = "same_course_id"
        else:
            code = _norm(source.get("code"))
            if code and len(by_code.get(code, [])) == 1:
                candidates = by_code[code]
                method = "unique_code"
            elif code and len(by_code.get(code, [])) > 1:
                candidates = by_code[code]
                method = "ambiguous_code"
            else:
                name = _norm(source.get("name"))
                if name:
                    candidates = by_name.get(name, [])
                    if len(candidates) == 1:
                        method = "unique_normalized_name"
                    elif len(candidates) > 1:
                        method = "ambiguous_normalized_name"

        if len(candidates) != 1:
            code = "COURSE_MAPPING_AMBIGUOUS" if len(candidates) > 1 else "COURSE_MAPPING_MISSING"
            _issue(
                blockers,
                code,
                "O componente da origem não possui correspondência curricular 1:1 no destino.",
                source_course_id=source_id,
                source_name=source.get("name"),
                source_code=source.get("code"),
                candidate_course_ids=[c.get("course_id") for c in candidates],
                method=method,
            )
            mapped.append(
                {
                    "source_course_id": source_id,
                    "source_name": source.get("name"),
                    "source_code": source.get("code"),
                    "target_course_id": None,
                    "target_name": None,
                    "method": method or "none",
                    "ok": False,
                }
            )
            continue

        target = candidates[0]
        mapped.append(
            {
                "source_course_id": source_id,
                "source_name": source.get("name"),
                "source_code": source.get("code"),
                "target_course_id": target.get("course_id"),
                "target_name": target.get("name"),
                "method": method,
                "ok": True,
            }
        )
    return mapped, blockers


def _target_for(course_map: list[dict[str, Any]], source_course_id: str | None) -> str | None:
    if not source_course_id:
        return None
    for item in course_map:
        if item.get("source_course_id") == source_course_id and item.get("ok"):
            return item.get("target_course_id")
    return None


def _nonempty(value: Any) -> bool:
    return value not in (None, "", [], {})


async def _grade_manifest(
    db,
    *,
    student_id: str,
    source_class_id: str,
    destination_class_id: str,
    academic_year: int,
    tenant_id: str,
    course_map: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    blockers: list[dict[str, Any]] = []
    source_grades = await db.grades.find(
        _tenant_query(
            {
                "student_id": student_id,
                "class_id": source_class_id,
                "academic_year": {"$in": [academic_year, str(academic_year)]},
            },
            tenant_id,
        ),
        {"_id": 0},
    ).to_list(500)
    manifest = []
    for grade in source_grades:
        source_course_id = grade.get("course_id")
        target_course_id = _target_for(course_map, source_course_id)
        target_grade = None
        overlaps: list[str] = []
        if target_course_id:
            target_grade = await db.grades.find_one(
                _tenant_query(
                    {
                        "student_id": student_id,
                        "class_id": destination_class_id,
                        "course_id": target_course_id,
                        "academic_year": {"$in": [academic_year, str(academic_year)]},
                    },
                    tenant_id,
                ),
                {"_id": 0},
            )
            if target_grade:
                for field in GRADE_VALUE_FIELDS:
                    if _nonempty(grade.get(field)) and _nonempty(target_grade.get(field)):
                        overlaps.append(field)
        if overlaps:
            _issue(
                blockers,
                "GRADE_DESTINATION_VALUE_PRESENT",
                "Já existem valores de nota no destino nos mesmos campos da evidência de origem.",
                source_grade_id=grade.get("id"),
                target_grade_id=(target_grade or {}).get("id"),
                target_course_id=target_course_id,
                fields=overlaps,
            )
        if grade.get("dependency_id"):
            _issue(
                blockers,
                "GRADE_DEPENDENCY_REVIEW_REQUIRED",
                "Nota da origem possui dependency_id e exige revisão manual na V1.",
                grade_id=grade.get("id"),
                dependency_id=grade.get("dependency_id"),
            )
        manifest.append(
            {
                "grade_id": grade.get("id"),
                "source_course_id": source_course_id,
                "target_course_id": target_course_id,
                "source_values": {field: grade.get(field) for field in GRADE_VALUE_FIELDS},
                "grade_ownership_present": bool(grade.get("grade_ownership")),
                "destination_grade_id": (target_grade or {}).get("id"),
                "overlapping_fields": overlaps,
            }
        )
    return manifest, blockers


async def _attendance_manifest(
    db,
    *,
    student_id: str,
    source_class_id: str,
    destination_class_id: str,
    academic_year: int,
    tenant_id: str,
    course_map: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    blockers: list[dict[str, Any]] = []
    source_docs = await db.attendance.find(
        _tenant_query(
            {
                "class_id": source_class_id,
                "academic_year": {"$in": [academic_year, str(academic_year)]},
                "records.student_id": student_id,
            },
            tenant_id,
        ),
        {"_id": 0},
    ).to_list(None)
    manifest: list[dict[str, Any]] = []
    for doc in source_docs:
        source_course_id = doc.get("course_id")
        target_course_id = _target_for(course_map, source_course_id)
        student_records = [
            record for record in (doc.get("records") or []) if record.get("student_id") == student_id
        ]
        for record in student_records:
            overlap_query: dict[str, Any] = {
                "class_id": destination_class_id,
                "academic_year": {"$in": [academic_year, str(academic_year)]},
                "date": doc.get("date"),
                "records.student_id": student_id,
            }
            if target_course_id:
                overlap_query["course_id"] = target_course_id
            elif source_course_id:
                overlap_query["course_id"] = "__UNMAPPED_COURSE__"
            else:
                overlap_query["$or"] = [
                    {"course_id": None}, {"course_id": ""}, {"course_id": {"$exists": False}}
                ]
            overlap_count = await db.attendance.count_documents(
                _tenant_query(overlap_query, tenant_id)
            )
            if overlap_count:
                _issue(
                    blockers,
                    "ATTENDANCE_OVERLAP_DESTINATION",
                    "Já existe frequência ordinária do estudante no destino para a mesma data/componente.",
                    source_attendance_id=doc.get("id"),
                    source_date=doc.get("date"),
                    target_course_id=target_course_id,
                    destination_matches=overlap_count,
                )
            if record.get("dependency_id") or doc.get("dependency_id"):
                _issue(
                    blockers,
                    "ATTENDANCE_DEPENDENCY_REVIEW_REQUIRED",
                    "Frequência relacionada a dependência exige revisão manual na V1.",
                    source_attendance_id=doc.get("id"),
                )
            manifest.append(
                {
                    "source_attendance_id": doc.get("id"),
                    "source_date": doc.get("date"),
                    "source_course_id": source_course_id,
                    "target_course_id": target_course_id,
                    "source_aula_numero": doc.get("aula_numero"),
                    "source_assignment_id": doc.get("assignment_id"),
                    "status": record.get("status"),
                    "justification": record.get("justification") or record.get("justificativa"),
                    "validated": bool(doc.get("validated_by") or doc.get("validated_at")),
                    "version": doc.get("version"),
                    "destination_overlap_count": overlap_count,
                    "target_storage": "attendance_rectifications (F1.2; não criado nesta fase)",
                }
            )
    return manifest, blockers


async def _document_manifest(
    db,
    *,
    student_id: str,
    source_class_id: str,
    academic_year: int,
    tenant_id: str,
) -> dict[str, Any]:
    year_values = [academic_year, str(academic_year)]
    tracked_counts = {
        "school_documents_log": await db.school_documents_log.count_documents(
            _tenant_query(
                {
                    "student_id": student_id,
                    "$or": [
                        {"class_id": source_class_id},
                        {"academic_year": {"$in": year_values}},
                    ],
                },
                tenant_id,
            )
        ),
        "bulletin_verifications": await db.bulletin_verifications.count_documents(
            _tenant_query(
                {
                    "student_id": student_id,
                    "$or": [
                        {"class_id": source_class_id},
                        {"academic_year": {"$in": year_values}},
                    ],
                },
                tenant_id,
            )
        ),
        "history_verifications": await db.history_verifications.count_documents(
            _tenant_query({"student_id": student_id}, tenant_id)
        ),
        "manual_document_issuances": await db.manual_document_issuances.count_documents(
            _tenant_query(
                {
                    "student_id": student_id,
                    "$or": [
                        {"class_id": source_class_id},
                        {"academic_year": {"$in": year_values}},
                    ],
                },
                tenant_id,
            )
        ),
        "diary_snapshots": await db.diary_snapshots.count_documents(
            _tenant_query(
                {
                    "class_id": source_class_id,
                    "academic_year": {"$in": year_values},
                },
                tenant_id,
            )
        ),
        "promotion_books": await db.promotion_books.count_documents(
            _tenant_query(
                {
                    "class_id": source_class_id,
                    "academic_year": {"$in": year_values},
                },
                tenant_id,
            )
        ),
        "document_render_jobs": await db.document_render_jobs.count_documents(
            _tenant_query(
                {"source_snapshot_id": {"$regex": student_id}},
                tenant_id,
            )
        ),
        "verifiable_documents": await db.verifiable_documents.count_documents(
            _tenant_query(
                {
                    "$or": [
                        {"entity_id": student_id},
                        {"public_metadata.student_id": student_id},
                    ]
                },
                tenant_id,
            )
        ),
    }
    return {
        "coverage_complete": False,
        "tracked_counts": tracked_counts,
        "tracked_total": sum(tracked_counts.values()),
        "coverage_gap": {
            "code": "SYNC_PDF_LEDGER_GAP",
            "message": (
                "Boletim, Ficha Individual e declarações síncronas ainda podem ser emitidos "
                "por caminhos oficiais sem ledger persistente; ausência nos contadores não "
                "prova ausência histórica de emissão."
            ),
            "gate": "F3",
        },
    }


async def build_rectification_dry_run(
    db,
    *,
    student_id: str,
    destination_class_id: str,
    tenant_id: str,
    actor: dict[str, Any] | None = None,
    secret: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Executa o dry-run F1.0 sem qualquer escrita no banco."""
    if not student_id or not destination_class_id or not tenant_id:
        raise RectificationDryRunError(
            "INVALID_DRY_RUN_INPUT",
            "student_id, destination_class_id e tenant_id são obrigatórios.",
            status_code=422,
        )

    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    student = await db.students.find_one(
        _tenant_query({"id": student_id}, tenant_id), {"_id": 0}
    )
    if not student:
        raise RectificationDryRunError(
            "STUDENT_NOT_FOUND",
            "Estudante não encontrado no tenant operacional.",
            status_code=404,
        )

    destination_class = await db.classes.find_one(
        _tenant_query({"id": destination_class_id}, tenant_id), {"_id": 0}
    )
    if not destination_class:
        raise RectificationDryRunError(
            "DESTINATION_CLASS_NOT_FOUND",
            "Turma de destino não encontrada no tenant operacional.",
            status_code=404,
        )
    destination_year = _year(destination_class.get("academic_year"))
    if destination_year is None:
        raise RectificationDryRunError(
            "DESTINATION_ACADEMIC_YEAR_INVALID",
            "A turma de destino não possui ano letivo válido.",
        )

    regular = await _find_regular_active_enrollments(
        db,
        student_id=student_id,
        tenant_id=tenant_id,
        academic_year=destination_year,
    )
    if len(regular) != 1:
        raise RectificationDryRunError(
            "PRIMARY_ENROLLMENT_CARDINALITY_INVALID",
            "A retificação exige exatamente uma matrícula regular ativa no ano da turma destino.",
            detail={"regular_active_count": len(regular), "academic_year": destination_year},
        )
    enrollment, source_class = regular[0]
    source_class_id = source_class.get("id")

    if source_class_id == destination_class_id:
        _issue(blockers, "SAME_CLASS", "Origem e destino são a mesma turma.")
    if is_special_class(source_class):
        _issue(blockers, "SOURCE_SPECIAL_CLASS", "A turma de origem é programa especial e está fora da V1.")
    if is_special_class(destination_class):
        _issue(blockers, "DESTINATION_SPECIAL_CLASS", "A turma de destino é programa especial e está fora da V1.")

    source_school = source_class.get("school_id") or enrollment.get("school_id")
    destination_school = destination_class.get("school_id")
    if not source_school or source_school != destination_school:
        _issue(
            blockers,
            "DIFFERENT_SCHOOL",
            "A V1 permite retificação apenas dentro da mesma escola.",
            source_school_id=source_school,
            destination_school_id=destination_school,
        )
    source_year = _year(enrollment.get("academic_year")) or _year(source_class.get("academic_year"))
    if source_year != destination_year:
        _issue(
            blockers,
            "DIFFERENT_ACADEMIC_YEAR",
            "Origem e destino devem pertencer ao mesmo ano letivo.",
            source_year=source_year,
            destination_year=destination_year,
        )

    if enrollment.get("mantenedora_id") != tenant_id or source_class.get("mantenedora_id") != tenant_id:
        _issue(blockers, "TENANT_MISMATCH_SOURCE", "A origem não pertence integralmente ao tenant operacional.")
    if destination_class.get("mantenedora_id") != tenant_id:
        _issue(blockers, "TENANT_MISMATCH_DESTINATION", "O destino não pertence ao tenant operacional.")

    destination_components, curriculum_warnings = await _destination_curriculum(
        db,
        student_id=student_id,
        destination_class=destination_class,
        academic_year=destination_year,
        tenant_id=tenant_id,
    )
    for item in curriculum_warnings:
        _warn(
            warnings,
            "DESTINATION_CURRICULUM_WARNING",
            "O resolver curricular do destino reportou uma advertência.",
            resolver_warning=item,
        )

    source_grades_for_courses = await db.grades.find(
        _tenant_query(
            {
                "student_id": student_id,
                "class_id": source_class_id,
                "academic_year": {"$in": [destination_year, str(destination_year)]},
            },
            tenant_id,
        ),
        {"_id": 0, "course_id": 1},
    ).to_list(500)
    source_attendance_for_courses = await db.attendance.find(
        _tenant_query(
            {
                "class_id": source_class_id,
                "academic_year": {"$in": [destination_year, str(destination_year)]},
                "records.student_id": student_id,
            },
            tenant_id,
        ),
        {"_id": 0, "course_id": 1},
    ).to_list(None)
    source_course_ids = {
        str(item.get("course_id"))
        for item in [*source_grades_for_courses, *source_attendance_for_courses]
        if item.get("course_id")
    }
    source_courses = await _load_courses(db, source_course_ids, tenant_id)
    missing_source_course_docs = sorted(source_course_ids - set(source_courses))
    for course_id in missing_source_course_docs:
        _issue(
            blockers,
            "SOURCE_COURSE_NOT_FOUND",
            "Há evidência acadêmica vinculada a componente inexistente ou fora do tenant.",
            source_course_id=course_id,
        )

    course_map, course_blockers = _build_course_map(source_courses, destination_components)
    blockers.extend(course_blockers)

    grades_manifest, grade_blockers = await _grade_manifest(
        db,
        student_id=student_id,
        source_class_id=source_class_id,
        destination_class_id=destination_class_id,
        academic_year=destination_year,
        tenant_id=tenant_id,
        course_map=course_map,
    )
    blockers.extend(grade_blockers)

    attendance_manifest, attendance_blockers = await _attendance_manifest(
        db,
        student_id=student_id,
        source_class_id=source_class_id,
        destination_class_id=destination_class_id,
        academic_year=destination_year,
        tenant_id=tenant_id,
        course_map=course_map,
    )
    blockers.extend(attendance_blockers)

    dependencies = await db.student_dependencies.find(
        _tenant_query(
            {
                "student_id": student_id,
                "$or": [
                    {"class_id": source_class_id},
                    {"target_class_id": source_class_id},
                    {"target_class_id": destination_class_id},
                ],
            },
            tenant_id,
        ),
        {"_id": 0, "id": 1, "class_id": 1, "target_class_id": 1, "course_id": 1, "status": 1},
    ).to_list(200)
    if dependencies:
        _issue(
            blockers,
            "STUDENT_DEPENDENCY_REVIEW_REQUIRED",
            "Existem dependências acadêmicas relacionadas às turmas envolvidas.",
            dependency_ids=[item.get("id") for item in dependencies],
        )

    events = await db.academic_events.find(
        _tenant_query(
            {
                "student_id": student_id,
                "$or": [
                    {"origin_class_id": {"$in": [source_class_id, destination_class_id]}},
                    {"destination_class_id": {"$in": [source_class_id, destination_class_id]}},
                ],
            },
            tenant_id,
        ),
        {"_id": 0, "id": 1, "event_type": 1, "origin_class_id": 1, "destination_class_id": 1, "effective_date": 1},
    ).to_list(200)
    if events:
        _issue(
            blockers,
            "ACADEMIC_EVENT_REVIEW_REQUIRED",
            "Há movimentação acadêmica temporal relacionada às turmas envolvidas.",
            event_ids=[item.get("id") for item in events],
        )

    legacy_class_students = await db.class_students.count_documents(
        _tenant_query({"student_id": student_id, "class_id": source_class_id}, tenant_id)
    )
    if legacy_class_students:
        _warn(
            warnings,
            "LEGACY_CLASS_STUDENTS_RESIDUE",
            "Existe resíduo legado class_students na turma de origem; não haverá nova escrita nessa estrutura.",
            count=legacy_class_students,
        )

    history_count = await db.student_history.count_documents(
        _tenant_query(
            {
                "student_id": student_id,
                "$or": [
                    {"class_id": source_class_id},
                    {"old_class_id": source_class_id},
                    {"new_class_id": source_class_id},
                ],
            },
            tenant_id,
        )
    )
    if history_count:
        _warn(
            warnings,
            "STUDENT_HISTORY_REVIEW_REQUIRED_F1_3",
            "Há trilha histórica ligada à origem que precisará ser classificada na F1.3.",
            count=history_count,
        )

    documents = await _document_manifest(
        db,
        student_id=student_id,
        source_class_id=source_class_id,
        academic_year=destination_year,
        tenant_id=tenant_id,
    )
    _warn(warnings, **{
        "code": documents["coverage_gap"]["code"],
        "message": documents["coverage_gap"]["message"],
        "gate": documents["coverage_gap"]["gate"],
    })
    if documents["tracked_total"]:
        _issue(
            blockers,
            "DOCUMENT_RESOLUTION_REQUIRED_F1_3",
            "Foram encontrados artefatos documentais rastreáveis que exigirão resolução antes de uma execução final.",
            tracked_counts=documents["tracked_counts"],
        )

    preserved_counts = {
        "medical_certificates": await db.medical_certificates.count_documents(
            _tenant_query({"student_id": student_id}, tenant_id)
        ),
        "bolsa_familia_tracking": await db.bolsa_familia_tracking.count_documents(
            _tenant_query({"student_id": student_id}, tenant_id)
        ),
        "planos_aee": await db.planos_aee.count_documents(
            _tenant_query({"student_id": student_id}, tenant_id)
        ),
        "atendimentos_aee": await db.atendimentos_aee.count_documents(
            _tenant_query({"student_id": student_id}, tenant_id)
        ),
    }

    counts = {
        "regular_active_enrollments": len(regular),
        "source_grades": len(grades_manifest),
        "source_attendance_student_records": len(attendance_manifest),
        "student_dependencies": len(dependencies),
        "academic_events": len(events),
        "student_history_origin": history_count,
        "class_students_legacy": legacy_class_students,
        **{f"documents.{k}": v for k, v in documents["tracked_counts"].items()},
    }

    precondition_material = {
        "tenant_id": tenant_id,
        "student": _stable_doc(student, ("id", "mantenedora_id", "school_id", "class_id", "status")),
        "enrollment": _stable_doc(
            enrollment,
            (
                "id",
                "student_id",
                "mantenedora_id",
                "school_id",
                "class_id",
                "academic_year",
                "student_series",
                "status",
                "enrollment_number",
                "enrollment_date",
            ),
        ),
        "source_class": _stable_doc(
            source_class,
            ("id", "mantenedora_id", "school_id", "academic_year", "grade_level", "atendimento_programa"),
        ),
        "destination_class": _stable_doc(
            destination_class,
            ("id", "mantenedora_id", "school_id", "academic_year", "grade_level", "atendimento_programa", "course_ids"),
        ),
        "course_map": course_map,
        "grades": grades_manifest,
        "attendance": attendance_manifest,
        "dependencies": dependencies,
        "events": events,
        "document_counts": documents["tracked_counts"],
    }
    precondition_hash = _sha256(precondition_material)
    issued_at = now or datetime.now(timezone.utc)
    if issued_at.tzinfo is None:
        issued_at = issued_at.replace(tzinfo=timezone.utc)
    expires_at = issued_at + timedelta(minutes=DRY_RUN_TTL_MINUTES)
    token_payload = {
        "v": CONTRACT_VERSION,
        "op": OPERATION,
        "tenant_id": tenant_id,
        "student_id": student_id,
        "source_enrollment_id": enrollment.get("id"),
        "source_class_id": source_class_id,
        "destination_class_id": destination_class_id,
        "academic_year": destination_year,
        "precondition_hash": precondition_hash,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    dry_run_token = _sign_token(token_payload, secret=secret)

    return {
        "contract_version": CONTRACT_VERSION,
        "operation": OPERATION,
        "execution_enabled": False,
        "can_execute_later": len(blockers) == 0,
        "dry_run_token": dry_run_token,
        "dry_run_expires_at": expires_at.isoformat(),
        "precondition_hash": precondition_hash,
        "student": {"id": student.get("id"), "full_name": student.get("full_name")},
        "enrollment": _stable_doc(
            enrollment,
            (
                "id",
                "enrollment_number",
                "enrollment_date",
                "academic_year",
                "student_series",
                "school_id",
                "class_id",
                "status",
            ),
        ),
        "origin_class": _stable_doc(
            source_class,
            ("id", "name", "grade_level", "school_id", "academic_year", "atendimento_programa"),
        ),
        "destination_class": _stable_doc(
            destination_class,
            ("id", "name", "grade_level", "school_id", "academic_year", "atendimento_programa"),
        ),
        "counts": counts,
        "destination_curriculum": destination_components,
        "course_map": course_map,
        "grades_manifest": grades_manifest,
        "attendance_manifest": attendance_manifest,
        "dependencies": dependencies,
        "academic_events": events,
        "documents": documents,
        "preservations": {
            "content_entries": "preserve",
            "aee": "preserve",
            "bolsa_familia_tracking": "preserve",
            "medical_certificates": "preserve",
            "current_counts": preserved_counts,
        },
        "blockers": blockers,
        "warnings": warnings,
        "expected_postconditions": [
            "uma única matrícula regular ativa no ano apontando ao destino",
            "zero attendance.records[] do estudante na turma origem",
            "zero grades ativos do estudante na turma origem",
            "frequência histórica preservada sem fabricar sessão no destino",
            "documentos antigos nunca reescritos silenciosamente",
        ],
        "confirmation_phrase": CONFIRMATION_PHRASE,
        "operator": {"id": (actor or {}).get("id"), "email": (actor or {}).get("email")},
    }
