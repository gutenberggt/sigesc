"""F2.1B — primitivo compensável de Notas para retificação de enturmação.

Internal-only: nenhum router importa este módulo nesta fase. A função processa
um item do manifesto revalidado sob o lock da futura saga. O gate global de
execução acadêmica continua fechado em enrollment_rectification_execution.py.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping

from services.enrollment_rectification_grade_contract import (
    GRADE_VALUE_FIELDS,
    grade_academic_fingerprint,
    migratable_grade_fields,
)

LEDGER_COLLECTION = "grade_rectifications"
LEDGER_INDEX_NAME = "uq_grade_rectification_protocol_source_grade"
ALLOWED_ACTOR_ROLES = frozenset({"admin", "super_admin", "gerente"})


class GradeRectificationError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 409, detail: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}

    def as_detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.detail}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _year_values(year: int) -> list[Any]:
    return [year, str(year)]


def _identity_query(*, tenant_id: str, student_id: str, class_id: str, course_id: str, academic_year: int) -> dict[str, Any]:
    return {
        "mantenedora_id": tenant_id,
        "student_id": student_id,
        "class_id": class_id,
        "course_id": course_id,
        "academic_year": {"$in": _year_values(academic_year)},
    }


def _cas_filter(doc: Mapping[str, Any]) -> dict[str, Any]:
    """CAS pelo subconjunto acadêmico que compõe o fingerprint F2.1B.

    Documentos legados podem não possuir fisicamente `grade_ownership` ou
    `rectified_fields`. O fingerprint normaliza ausência para mapa vazio; o CAS
    preserva essa semântica sem exigir que o campo legado exista.
    """
    query: dict[str, Any] = {
        "id": doc.get("id"),
        "mantenedora_id": doc.get("mantenedora_id"),
        "student_id": doc.get("student_id"),
        "class_id": doc.get("class_id"),
        "course_id": doc.get("course_id"),
        "academic_year": doc.get("academic_year"),
        "dependency_id": doc.get("dependency_id"),
    }
    if "grade_ownership" in doc:
        query["grade_ownership"] = doc.get("grade_ownership") or {}
    else:
        query["grade_ownership"] = {"$exists": False}
    if "rectified_fields" in doc:
        query["rectified_fields"] = doc.get("rectified_fields") or {}
    else:
        query["rectified_fields"] = {"$exists": False}
    for field in GRADE_VALUE_FIELDS:
        query[field] = doc.get(field)
    return query


def _ledger_key(*, tenant_id: str, protocol: str, source_grade_id: str) -> dict[str, str]:
    return {
        "mantenedora_id": tenant_id,
        "protocol": protocol,
        "source_grade_id": source_grade_id,
    }


async def ensure_grade_rectification_indexes(db) -> None:
    await db[LEDGER_COLLECTION].create_index(
        [("mantenedora_id", 1), ("protocol", 1), ("source_grade_id", 1)],
        unique=True,
        name=LEDGER_INDEX_NAME,
    )


async def _mark_failed(db, key: Mapping[str, Any], *, code: str, message: str, state: str = "FAILED_RECOVERABLE") -> None:
    await db[LEDGER_COLLECTION].update_one(
        dict(key),
        {"$set": {"state": state, "failure_code": code, "failure_message": message, "failed_at": _now()}},
    )


def _require_manifest_contract(item: Mapping[str, Any]) -> tuple[str, str, list[str]]:
    source_grade_id = str(item.get("source_grade_id") or item.get("grade_id") or "")
    source_fp = str(item.get("source_grade_fingerprint") or "")
    target_course_id = str(item.get("target_course_id") or "")
    fields = list(item.get("migratable_fields") or [])
    if not source_grade_id or len(source_fp) != 64 or not target_course_id:
        raise GradeRectificationError(
            "RECTIFICATION_GRADE_MANIFEST_UNHARDENED",
            "O item de notas não possui o contrato F2.1B completo. Gere novo dry-run.",
            status_code=422,
        )
    if not fields or any(field not in GRADE_VALUE_FIELDS for field in fields):
        raise GradeRectificationError(
            "RECTIFICATION_GRADE_FIELDS_INVALID",
            "O manifesto não contém campos avaliativos migráveis válidos.",
            status_code=422,
        )
    return source_grade_id, target_course_id, fields


async def apply_grade_rectification_item(
    db,
    *,
    manifest_item: Mapping[str, Any],
    protocol: str,
    tenant_id: str,
    student_id: str,
    source_class_id: str,
    target_enrollment_id: str,
    target_class_id: str,
    academic_year: int,
    actor: Mapping[str, Any],
    request=None,
    audit_service=None,
) -> dict[str, Any]:
    """Aplica exatamente um item de nota, sem exposição HTTP.

    O chamador futuro deverá possuir o lock da saga. Esta função continua
    defensiva contra mudanças concorrentes de `grades` realizadas por rotas
    normais entre dry-run e aplicação.
    """
    if actor.get("role") not in ALLOWED_ACTOR_ROLES:
        raise GradeRectificationError(
            "RECTIFICATION_GRADE_ACTOR_FORBIDDEN",
            "O perfil não pode executar o primitivo interno de retificação de notas.",
            status_code=403,
        )
    if not all((protocol, tenant_id, student_id, source_class_id, target_enrollment_id, target_class_id)):
        raise GradeRectificationError(
            "RECTIFICATION_GRADE_INPUT_INVALID",
            "Protocolo, tenant, estudante, matrícula e turmas são obrigatórios.",
            status_code=422,
        )

    source_grade_id, target_course_id, fields_to_apply = _require_manifest_contract(manifest_item)
    await ensure_grade_rectification_indexes(db)
    key = _ledger_key(tenant_id=tenant_id, protocol=protocol, source_grade_id=source_grade_id)
    prior = await db[LEDGER_COLLECTION].find_one(key, {"_id": 0})
    if prior and prior.get("state") == "APPLIED":
        return {**prior, "idempotent_replay": True}
    if prior and prior.get("state") in {"DESTINATION_APPLIED", "FAILED_RECOVERABLE"}:
        raise GradeRectificationError(
            "RECTIFICATION_GRADE_RECOVERY_REQUIRED",
            "A etapa anterior iniciou mutação e exige recuperação explícita antes de novo retry.",
            detail={"state": prior.get("state")},
        )

    source = await db.grades.find_one({"id": source_grade_id}, {"_id": 0})
    if not source:
        raise GradeRectificationError("RECTIFICATION_GRADE_SOURCE_NOT_FOUND", "Nota de origem não encontrada.", status_code=404)
    if str(source.get("mantenedora_id") or "") != str(tenant_id):
        raise GradeRectificationError("RECTIFICATION_GRADE_TENANT_MISMATCH", "A nota de origem não pertence ao tenant operacional.", status_code=403)
    for field, expected, current in (
        ("student_id", student_id, source.get("student_id")),
        ("class_id", source_class_id, source.get("class_id")),
        ("academic_year", str(academic_year), str(source.get("academic_year"))),
        ("course_id", str(manifest_item.get("source_course_id") or ""), str(source.get("course_id") or "")),
    ):
        if str(expected) != str(current):
            raise GradeRectificationError(
                "RECTIFICATION_GRADE_SOURCE_IDENTITY_CHANGED",
                "A identidade acadêmica da nota de origem divergiu do dry-run.",
                detail={"field": field, "expected": expected, "current": current},
            )
    if source.get("dependency_id"):
        raise GradeRectificationError(
            "RECTIFICATION_GRADE_DEPENDENCY_REVIEW_REQUIRED",
            "Nota vinculada a Dependência de Estudos exige revisão manual na V1.",
        )
    if grade_academic_fingerprint(source) != manifest_item.get("source_grade_fingerprint"):
        raise GradeRectificationError(
            "RECTIFICATION_GRADE_SOURCE_FINGERPRINT_CHANGED",
            "A nota de origem mudou depois do dry-run.",
        )
    current_fields = migratable_grade_fields(source)
    if current_fields != fields_to_apply:
        raise GradeRectificationError(
            "RECTIFICATION_GRADE_SOURCE_FIELDS_CHANGED",
            "Os campos avaliativos migráveis mudaram depois do dry-run.",
            detail={"expected": fields_to_apply, "current": current_fields},
        )

    dest_query = _identity_query(
        tenant_id=tenant_id,
        student_id=student_id,
        class_id=target_class_id,
        course_id=target_course_id,
        academic_year=academic_year,
    )
    destination_docs = await db.grades.find(dest_query, {"_id": 0}).to_list(3)
    if len(destination_docs) > 1:
        raise GradeRectificationError(
            "RECTIFICATION_GRADE_DESTINATION_CARDINALITY_INVALID",
            "Há múltiplos documentos de nota para a mesma identidade no destino.",
            detail={"count": len(destination_docs)},
        )
    destination = destination_docs[0] if destination_docs else None
    expected_absent = bool(manifest_item.get("destination_expected_absent"))
    expected_dest_id = manifest_item.get("destination_grade_id")
    expected_dest_fp = manifest_item.get("destination_grade_fingerprint")
    if expected_absent:
        if destination is not None:
            raise GradeRectificationError(
                "RECTIFICATION_GRADE_DESTINATION_FINGERPRINT_CHANGED",
                "Surgiu nota no destino depois do dry-run.",
            )
    else:
        if destination is None or str(destination.get("id")) != str(expected_dest_id):
            raise GradeRectificationError(
                "RECTIFICATION_GRADE_DESTINATION_FINGERPRINT_CHANGED",
                "A identidade da nota de destino mudou depois do dry-run.",
            )
        if grade_academic_fingerprint(destination) != expected_dest_fp:
            raise GradeRectificationError(
                "RECTIFICATION_GRADE_DESTINATION_FINGERPRINT_CHANGED",
                "A nota de destino mudou depois do dry-run.",
            )

    destination_ownership = dict((destination or {}).get("grade_ownership") or {})
    destination_rectified = dict((destination or {}).get("rectified_fields") or {})
    overlaps = [field for field in fields_to_apply if destination and destination.get(field) not in (None, "", [], {})]
    metadata_conflicts = [
        field for field in fields_to_apply
        if destination_ownership.get(field) or destination_rectified.get(field)
    ]
    if overlaps:
        raise GradeRectificationError(
            "RECTIFICATION_GRADE_DESTINATION_VALUE_PRESENT",
            "Há valor não-nulo no destino para campo que seria retificado.",
            detail={"fields": overlaps},
        )
    if metadata_conflicts:
        raise GradeRectificationError(
            "RECTIFICATION_GRADE_DESTINATION_FIELD_METADATA_PRESENT",
            "Há metadado de autoria/retificação no destino para campo que seria retificado.",
            detail={"fields": metadata_conflicts},
        )

    source_snapshot = deepcopy(source)
    destination_before = deepcopy(destination) if destination else None
    created_at = _now()
    pending = {
        "id": str(uuid.uuid4()),
        **key,
        "target_enrollment_id": target_enrollment_id,
        "student_id": student_id,
        "source_class_id": source_class_id,
        "target_class_id": target_class_id,
        "academic_year": academic_year,
        "source_course_id": source.get("course_id"),
        "target_course_id": target_course_id,
        "source_grade_fingerprint": manifest_item.get("source_grade_fingerprint"),
        "destination_fingerprint_before": expected_dest_fp,
        "fields_applied": fields_to_apply,
        "source_grade_snapshot": source_snapshot,
        "destination_before": destination_before,
        "state": "PENDING",
        "created_at": created_at,
        "created_by": actor.get("id"),
        "actor_role": actor.get("role"),
    }
    await db[LEDGER_COLLECTION].update_one(key, {"$setOnInsert": pending}, upsert=True)
    ledger = await db[LEDGER_COLLECTION].find_one(key, {"_id": 0})
    if ledger and ledger.get("state") == "APPLIED":
        return {**ledger, "idempotent_replay": True}

    now = _now()
    source_ownership = source.get("grade_ownership") or {}
    new_ownership = dict(destination_ownership)
    new_rectified = dict(destination_rectified)
    values_set: dict[str, Any] = {}
    for field in fields_to_apply:
        values_set[field] = source.get(field)
        if field in source_ownership:
            new_ownership[field] = deepcopy(source_ownership[field])
        else:
            new_ownership.pop(field, None)
        new_rectified[field] = {
            "protocol": protocol,
            "source_grade_id": source_grade_id,
            "source_class_id": source_class_id,
            "source_course_id": source.get("course_id"),
            "target_course_id": target_course_id,
            "source_value_hash": _digest(source.get(field)),
            "source_grade_fingerprint": manifest_item.get("source_grade_fingerprint"),
            "rectified_at": now,
            "rectified_by": actor.get("id"),
        }

    destination_id: str
    try:
        if destination:
            destination_id = str(destination["id"])
            set_data = {
                **values_set,
                "grade_ownership": new_ownership,
                "rectified_fields": new_rectified,
                "updated_at": now,
                "updated_by": actor.get("id"),
                "last_updated_by": actor.get("id"),
            }
            result = await db.grades.update_one(_cas_filter(destination), {"$set": set_data})
            if result.matched_count != 1:
                await _mark_failed(db, key, code="RECTIFICATION_GRADE_DESTINATION_CAS_CONFLICT", message="CAS do destino falhou.")
                raise GradeRectificationError(
                    "RECTIFICATION_GRADE_DESTINATION_CAS_CONFLICT",
                    "A nota de destino mudou durante a retificação; recuperação explícita é necessária.",
                )
        else:
            # Recheck imediatamente antes do insert; eventual corrida residual é
            # detectada pela cardinalidade pós-insert e nunca é conciliada best-effort.
            if await db.grades.count_documents(dest_query):
                await _mark_failed(db, key, code="RECTIFICATION_GRADE_DESTINATION_CAS_CONFLICT", message="Destino surgiu antes do insert.")
                raise GradeRectificationError(
                    "RECTIFICATION_GRADE_DESTINATION_CAS_CONFLICT",
                    "Surgiu nota no destino durante a retificação.",
                )
            destination_id = str(uuid.uuid4())
            new_grade = {
                "id": destination_id,
                "mantenedora_id": tenant_id,
                "student_id": student_id,
                "class_id": target_class_id,
                "course_id": target_course_id,
                "academic_year": source.get("academic_year"),
                "dependency_id": None,
                "b1": None, "b2": None, "b3": None, "b4": None,
                "rec_s1": None, "rec_s2": None, "recovery": None,
                "observations": None,
                "final_average": None,
                "status": "cursando",
                "grade_ownership": new_ownership,
                "rectified_fields": new_rectified,
                "created_at": now,
                "created_by": actor.get("id"),
                "updated_at": now,
                "updated_by": actor.get("id"),
                "last_updated_by": actor.get("id"),
            }
            new_grade.update(values_set)
            await db.grades.insert_one(new_grade)
            if await db.grades.count_documents(dest_query) != 1:
                await _mark_failed(db, key, code="RECTIFICATION_GRADE_DESTINATION_CARDINALITY_RACE", message="Concorrência criou cardinalidade inválida no destino.")
                raise GradeRectificationError(
                    "RECTIFICATION_GRADE_DESTINATION_CARDINALITY_RACE",
                    "Concorrência tornou o destino ambíguo; recuperação explícita é necessária.",
                )

        # Reutiliza a fórmula canônica existente; não duplica cálculo na F2.1B.
        from routers.grades import calculate_and_update_grade
        calculated = await calculate_and_update_grade(db, destination_id)
        if not calculated:
            await _mark_failed(db, key, code="RECTIFICATION_GRADE_DESTINATION_RECALC_FAILED", message="Destino não pôde ser recalculado.")
            raise GradeRectificationError(
                "RECTIFICATION_GRADE_DESTINATION_RECALC_FAILED",
                "A nota de destino não pôde ser recalculada.",
            )
    except GradeRectificationError:
        raise
    except Exception as exc:
        await _mark_failed(db, key, code="RECTIFICATION_GRADE_DESTINATION_APPLY_FAILED", message=str(exc))
        raise GradeRectificationError(
            "RECTIFICATION_GRADE_DESTINATION_APPLY_FAILED",
            "Falha ao materializar a nota de destino; recuperação explícita é necessária.",
        ) from exc

    destination_after = await db.grades.find_one({"id": destination_id}, {"_id": 0})
    if not destination_after:
        await _mark_failed(db, key, code="RECTIFICATION_GRADE_DESTINATION_POSTCONDITION_FAILED", message="Destino ausente após aplicação.")
        raise GradeRectificationError("RECTIFICATION_GRADE_DESTINATION_POSTCONDITION_FAILED", "Destino ausente após aplicação.")
    for field in fields_to_apply:
        if destination_after.get(field) != source.get(field):
            await _mark_failed(db, key, code="RECTIFICATION_GRADE_DESTINATION_POSTCONDITION_FAILED", message=f"Campo {field} divergiu.")
            raise GradeRectificationError("RECTIFICATION_GRADE_DESTINATION_POSTCONDITION_FAILED", "Valor retificado divergiu no destino.")
        if (destination_after.get("grade_ownership") or {}).get(field) != source_ownership.get(field):
            await _mark_failed(db, key, code="RECTIFICATION_GRADE_OWNERSHIP_POSTCONDITION_FAILED", message=f"Ownership {field} divergiu.")
            raise GradeRectificationError("RECTIFICATION_GRADE_OWNERSHIP_POSTCONDITION_FAILED", "A proveniência docente não foi preservada.")
        if not (destination_after.get("rectified_fields") or {}).get(field):
            await _mark_failed(db, key, code="RECTIFICATION_GRADE_RECTIFIED_FIELDS_MISSING", message=f"rectified_fields.{field} ausente.")
            raise GradeRectificationError("RECTIFICATION_GRADE_RECTIFIED_FIELDS_MISSING", "Metadado granular de retificação ausente.")

    await db[LEDGER_COLLECTION].update_one(
        key,
        {"$set": {
            "state": "DESTINATION_APPLIED",
            "destination_grade_id": destination_id,
            "destination_fingerprint_after": grade_academic_fingerprint(destination_after),
            "destination_applied_at": _now(),
        }},
    )

    # Segunda revalidação da origem imediatamente antes da retirada.
    source_before_delete = await db.grades.find_one({"id": source_grade_id}, {"_id": 0})
    if not source_before_delete or grade_academic_fingerprint(source_before_delete) != manifest_item.get("source_grade_fingerprint"):
        await _mark_failed(db, key, code="RECTIFICATION_GRADE_SOURCE_CAS_CONFLICT", message="Origem mudou antes da retirada.")
        raise GradeRectificationError(
            "RECTIFICATION_GRADE_SOURCE_CAS_CONFLICT",
            "A nota de origem mudou após materializar o destino; recuperação explícita é necessária.",
        )
    deletion = await db.grades.delete_one(_cas_filter(source_before_delete))
    if deletion.deleted_count != 1:
        await _mark_failed(db, key, code="RECTIFICATION_GRADE_SOURCE_CAS_CONFLICT", message="CAS de retirada da origem falhou.")
        raise GradeRectificationError(
            "RECTIFICATION_GRADE_SOURCE_CAS_CONFLICT",
            "Falha concorrente ao retirar a nota da turma errada; recuperação explícita é necessária.",
        )
    if await db.grades.find_one({"id": source_grade_id}, {"_id": 0}):
        await _mark_failed(db, key, code="RECTIFICATION_GRADE_SOURCE_POSTCONDITION_FAILED", message="Origem permaneceu ativa.")
        raise GradeRectificationError("RECTIFICATION_GRADE_SOURCE_POSTCONDITION_FAILED", "A nota de origem permaneceu ativa.")

    applied_at = _now()
    await db[LEDGER_COLLECTION].update_one(
        key,
        {"$set": {
            "state": "APPLIED",
            "applied_at": applied_at,
            "source_removed": True,
            "destination_grade_id": destination_id,
            "destination_after": destination_after,
        }, "$unset": {"failure_code": "", "failure_message": "", "failed_at": ""}},
    )
    final = await db[LEDGER_COLLECTION].find_one(key, {"_id": 0})

    if audit_service is not None:
        await audit_service.log(
            action="rectify_grade_item",
            collection="grades",
            user=dict(actor),
            request=request,
            document_id=destination_id,
            description=f"Retificou nota da turma de origem para o destino — protocolo {protocol}",
            academic_year=academic_year,
            extra_data={
                "protocol": protocol,
                "student_id": student_id,
                "source_grade_id": source_grade_id,
                "destination_grade_id": destination_id,
                "fields": fields_to_apply,
                "source_class_id": source_class_id,
                "target_class_id": target_class_id,
            },
        )
    return {**final, "idempotent_replay": False}
