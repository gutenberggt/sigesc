"""F2.2 — saga executável da Retificação de Matrícula/Turma.

A F2.2 orquestra o núcleo de preparação F2.0 e os três primitivos já
endurecidos: Frequência F2.1A, Notas F2.1B e Documentos F2.1C.

O código é publicável sem habilitar mutação real: a execução acadêmica exige
explicitamente ``ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED=true``. O default é
``false`` e rollback permanece disponível para uma execução já aplicada.
"""
from __future__ import annotations

import os
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping

from lib.critical_mutation import acquire_lock, release_lock
from services.enrollment_rectification import (
    RectificationDryRunError,
    build_rectification_dry_run,
)
from services.enrollment_rectification_attendance import (
    LEDGER_COLLECTION as ATTENDANCE_LEDGER_COLLECTION,
    AttendanceRectificationError,
    _digest as attendance_digest,
    apply_attendance_rectification_item,
)
from services.enrollment_rectification_documents import (
    DOCUMENT_ACKNOWLEDGEMENT,
    DOCUMENT_LEDGER_COLLECTION,
    DocumentRectificationError,
    build_rectification_document_inventory,
    check_rectification_rollback_eligibility,
    detect_rectification_origin_residues,
    resolve_rectification_documents,
)
from services.enrollment_rectification_execution import (
    EXECUTION_CONTRACT_VERSION,
    LOCKS_COLLECTION,
    RUNS_COLLECTION,
    RectificationExecutionError,
    _lock_target,
    _prepare_id,
    _reauthenticate,
    _validate_human_gates,
    build_compensating_snapshot,
    validate_state_transition,
    verify_rectification_dry_run_token,
)
from services.enrollment_rectification_grade_contract import grade_academic_fingerprint
from services.enrollment_rectification_grades import (
    LEDGER_COLLECTION as GRADE_LEDGER_COLLECTION,
    GradeRectificationError,
    _cas_filter as grade_cas_filter,
    apply_grade_rectification_item,
)

SAGA_CONTRACT_VERSION = "F2.2"
EXECUTION_FLAG = "ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED"
DOCUMENT_DRY_RUN_BLOCKER = "DOCUMENT_RESOLUTION_REQUIRED_F1_3"
ALLOWED_ACTOR_ROLES = frozenset({"admin", "super_admin", "gerente"})


class RectificationSagaError(Exception):
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def saga_execution_enabled() -> bool:
    """Feature flag operacional; nunca é habilitada implicitamente pelo deploy."""
    return os.environ.get(EXECUTION_FLAG, "false").strip().lower() == "true"


def _roles(actor: Mapping[str, Any]) -> set[str]:
    out = {str(role).strip() for role in (actor.get("roles") or []) if role}
    if actor.get("role"):
        out.add(str(actor.get("role")).strip())
    return out


def _assert_actor(actor: Mapping[str, Any]) -> None:
    if not (_roles(actor) & ALLOWED_ACTOR_ROLES):
        raise RectificationSagaError(
            "RECTIFICATION_SAGA_ACTOR_FORBIDDEN",
            "O perfil não pode operar a saga de retificação.",
            status_code=403,
        )


def _assert_same_operator(run: Mapping[str, Any], actor: Mapping[str, Any]) -> None:
    prepared_by = str((run.get("actor") or {}).get("id") or "")
    current = str(actor.get("id") or "")
    if not prepared_by or prepared_by != current:
        raise RectificationSagaError(
            "RECTIFICATION_SAGA_OPERATOR_MISMATCH",
            "A execução deve ser realizada pelo mesmo operador que fez a reautenticação da preparação.",
            status_code=403,
        )


def _non_document_blockers(blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in blockers if item.get("code") != DOCUMENT_DRY_RUN_BLOCKER]


async def _current_saga_plan(
    db,
    *,
    claims: Mapping[str, Any],
    tenant_id: str,
    actor: Mapping[str, Any],
    secret: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Revalida F1 e converte apenas o antigo blocker documental resolvível."""
    try:
        current = await build_rectification_dry_run(
            db,
            student_id=str(claims.get("student_id") or ""),
            destination_class_id=str(claims.get("destination_class_id") or ""),
            tenant_id=tenant_id,
            actor=dict(actor),
            secret=secret,
        )
    except RectificationDryRunError as exc:
        raise RectificationSagaError(
            "RECTIFICATION_PRECONDITION_CHANGED",
            "As pré-condições acadêmicas mudaram depois do dry-run.",
            detail={"source_error_code": exc.code, "source_error": exc.as_detail()},
        ) from exc

    expected_identity = {
        "student_id": claims.get("student_id"),
        "source_enrollment_id": claims.get("source_enrollment_id"),
        "source_class_id": claims.get("source_class_id"),
        "destination_class_id": claims.get("destination_class_id"),
        "academic_year": claims.get("academic_year"),
    }
    current_identity = {
        "student_id": (current.get("student") or {}).get("id"),
        "source_enrollment_id": (current.get("enrollment") or {}).get("id"),
        "source_class_id": (current.get("origin_class") or {}).get("id"),
        "destination_class_id": (current.get("destination_class") or {}).get("id"),
        "academic_year": (current.get("enrollment") or {}).get("academic_year"),
    }
    if any(str(expected_identity[k]) != str(current_identity[k]) for k in expected_identity):
        raise RectificationSagaError(
            "RECTIFICATION_PRECONDITION_IDENTITY_CHANGED",
            "A identidade acadêmica da retificação mudou depois do dry-run.",
            detail={"expected": expected_identity, "current": current_identity},
        )
    if current.get("precondition_hash") != claims.get("precondition_hash"):
        raise RectificationSagaError(
            "RECTIFICATION_PRECONDITION_CHANGED",
            "As evidências acadêmicas mudaram depois do dry-run.",
            detail={
                "expected_precondition_hash": claims.get("precondition_hash"),
                "current_precondition_hash": current.get("precondition_hash"),
            },
        )

    non_document = _non_document_blockers(list(current.get("blockers") or []))
    inventory = await build_rectification_document_inventory(
        db,
        student_id=str(claims.get("student_id")),
        source_class_id=str(claims.get("source_class_id")),
        academic_year=int(claims.get("academic_year")),
        tenant_id=tenant_id,
    )
    if non_document:
        raise RectificationSagaError(
            "RECTIFICATION_BLOCKERS_PRESENT",
            "O dry-run possui bloqueios acadêmicos não resolvíveis pela saga.",
            detail={"blockers": non_document},
        )
    if inventory.get("blockers"):
        raise RectificationSagaError(
            "RECTIFICATION_DOCUMENT_BLOCKERS_PRESENT",
            "O eixo documental possui artefatos que exigem tratamento institucional anterior à saga.",
            detail={"blockers": inventory.get("blockers")},
        )
    return current, inventory


def _prepared_response(run: Mapping[str, Any], *, replay: bool) -> dict[str, Any]:
    return {
        "contract_version": SAGA_CONTRACT_VERSION,
        "prepare_id": run.get("_id") or run.get("prepare_id"),
        "protocol": run.get("protocol"),
        "state": run.get("state"),
        "execution_enabled": saga_execution_enabled(),
        "academic_mutation_performed": bool(run.get("academic_mutation_performed")),
        "snapshot_digest": run.get("snapshot_digest"),
        "document_inventory_digest": run.get("document_inventory_digest"),
        "idempotent_replay": replay,
        "next_gate": "F2.2 /execute + feature flag + reconhecimento documental explícito",
    }


async def prepare_rectification_saga_execution(
    db,
    *,
    dry_run_token: str,
    tenant_id: str,
    actor: Mapping[str, Any],
    password: str,
    confirmation: str,
    justification: str,
    idempotency_key: str,
    now: datetime | None = None,
    secret: str | None = None,
) -> dict[str, Any]:
    """Prepara a F2.2 sem write acadêmico, inclusive quando F2.1C é resolvível."""
    _assert_actor(actor)
    _validate_human_gates(
        confirmation=confirmation,
        justification=justification,
        idempotency_key=idempotency_key,
    )
    claims = verify_rectification_dry_run_token(
        dry_run_token,
        tenant_id=tenant_id,
        now=now,
        secret=secret,
    )
    await _reauthenticate(db, tenant_id=tenant_id, actor=dict(actor), password=password)

    prepare_id = _prepare_id(tenant_id=tenant_id, actor_id=str(actor.get("id") or ""), idempotency_key=idempotency_key)
    existing = await db[RUNS_COLLECTION].find_one({"_id": prepare_id, "tenant_id": tenant_id}, {"_id": 0})
    if existing:
        if existing.get("precondition_hash") != claims.get("precondition_hash"):
            raise RectificationSagaError(
                "RECTIFICATION_IDEMPOTENCY_CONFLICT",
                "A mesma Idempotency-Key já foi usada para outro snapshot.",
            )
        return _prepared_response(existing, replay=True)

    holder = f"rectification-f22-prepare:{prepare_id}"
    target = _lock_target(tenant_id, str(claims.get("student_id")))
    acquired, lock_info = await acquire_lock(db, target, holder, LOCKS_COLLECTION)
    if not acquired:
        raise RectificationSagaError(
            "RECTIFICATION_STUDENT_LOCKED",
            "Outra operação crítica está em andamento para este estudante.",
            detail={"lock": lock_info},
        )
    try:
        current, inventory = await _current_saga_plan(
            db,
            claims=claims,
            tenant_id=tenant_id,
            actor=actor,
            secret=secret,
        )
        snapshot = await build_compensating_snapshot(
            db,
            claims=claims,
            tenant_id=tenant_id,
            current_dry_run=current,
        )
        protocol = str(uuid.uuid4())
        created = _now()
        run_doc = {
            "_id": prepare_id,
            "prepare_id": prepare_id,
            "protocol": protocol,
            "contract_version": SAGA_CONTRACT_VERSION,
            "base_execution_contract": EXECUTION_CONTRACT_VERSION,
            "tenant_id": tenant_id,
            "student_id": claims.get("student_id"),
            "source_enrollment_id": claims.get("source_enrollment_id"),
            "source_class_id": claims.get("source_class_id"),
            "destination_class_id": claims.get("destination_class_id"),
            "academic_year": claims.get("academic_year"),
            "precondition_hash": claims.get("precondition_hash"),
            "snapshot_digest": snapshot.get("snapshot_digest"),
            "pre_execution_snapshot": snapshot,
            "snapshot_is_final_for_mutation": False,
            "document_inventory_digest": inventory.get("inventory_digest"),
            "actor": {"id": actor.get("id"), "email": actor.get("email"), "role": actor.get("role")},
            "justification": justification.strip(),
            "idempotency_key": idempotency_key.strip(),
            "state": "PREPARED",
            "academic_mutation_enabled": False,
            "academic_mutation_performed": False,
            "created_at": created,
            "updated_at": created,
            "checkpoints": [
                {"name": "DRY_RUN_TOKEN_VERIFIED", "at": created},
                {"name": "PRECONDITION_HASH_REVALIDATED", "at": created},
                {"name": "HUMAN_REAUTHENTICATED", "at": created},
                {"name": "DOCUMENT_GATE_RESOLVABLE", "at": created},
                {"name": "COMPENSATING_SNAPSHOT_CAPTURED", "at": created},
            ],
        }
        await db[RUNS_COLLECTION].insert_one(run_doc)
        return _prepared_response(run_doc, replay=False)
    finally:
        await release_lock(db, target, holder, LOCKS_COLLECTION)


async def _transition_run(db, *, run_id: str, tenant_id: str, current: str, new: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    validate_state_transition(current, new)
    payload = {"state": new, "updated_at": _now(), **(extra or {})}
    result = await db[RUNS_COLLECTION].update_one(
        {"_id": run_id, "tenant_id": tenant_id, "state": current},
        {"$set": payload},
    )
    if result.modified_count != 1:
        raise RectificationSagaError(
            "RECTIFICATION_RUN_CAS_CONFLICT",
            "O estado da saga mudou concorrentemente.",
            detail={"expected_state": current, "target_state": new},
        )
    return await db[RUNS_COLLECTION].find_one({"_id": run_id, "tenant_id": tenant_id}, {"_id": 0})


async def _checkpoint(db, *, run_id: str, tenant_id: str, name: str, detail: dict[str, Any] | None = None) -> None:
    await db[RUNS_COLLECTION].update_one(
        {"_id": run_id, "tenant_id": tenant_id},
        {
            "$push": {"checkpoints": {"name": name, "at": _now(), **(detail or {})}},
            "$set": {"updated_at": _now()},
        },
    )


async def _apply_enrollment_projection(
    db,
    *,
    run: Mapping[str, Any],
    plan: Mapping[str, Any],
    actor: Mapping[str, Any],
) -> None:
    tenant_id = str(run.get("tenant_id"))
    enrollment_id = str(run.get("source_enrollment_id"))
    student_id = str(run.get("student_id"))
    source_class_id = str(run.get("source_class_id"))
    destination_class_id = str(run.get("destination_class_id"))
    year = run.get("academic_year")

    enrollment = await db.enrollments.find_one(
        {
            "id": enrollment_id,
            "student_id": student_id,
            "mantenedora_id": tenant_id,
            "class_id": source_class_id,
            "status": "active",
            "academic_year": {"$in": [year, str(year)]},
        },
        {"_id": 0},
    )
    if not enrollment:
        raise RectificationSagaError(
            "RECTIFICATION_ENROLLMENT_CAS_PRECONDITION_FAILED",
            "A matrícula de origem não está mais no estado preparado.",
        )
    destination = await db.classes.find_one(
        {"id": destination_class_id, "mantenedora_id": tenant_id}, {"_id": 0}
    )
    if not destination:
        raise RectificationSagaError("RECTIFICATION_DESTINATION_CLASS_NOT_FOUND", "Turma de destino não encontrada.")

    now = _now()
    enrollment_set: dict[str, Any] = {
        "class_id": destination_class_id,
        "updated_at": now,
        "updated_by": actor.get("id"),
        "rectification_protocol": run.get("protocol"),
    }
    if destination.get("grade_level"):
        enrollment_set["student_series"] = destination.get("grade_level")
    result = await db.enrollments.update_one(
        {
            "id": enrollment_id,
            "student_id": student_id,
            "mantenedora_id": tenant_id,
            "class_id": source_class_id,
            "status": "active",
            "academic_year": enrollment.get("academic_year"),
        },
        {"$set": enrollment_set},
    )
    if result.modified_count != 1:
        raise RectificationSagaError(
            "RECTIFICATION_ENROLLMENT_CAS_CONFLICT",
            "A matrícula mudou durante a aplicação da saga.",
        )

    student = await db.students.find_one(
        {"id": student_id, "mantenedora_id": tenant_id, "class_id": source_class_id}, {"_id": 0}
    )
    if not student:
        raise RectificationSagaError(
            "RECTIFICATION_STUDENT_PROJECTION_CAS_PRECONDITION_FAILED",
            "A projeção atual do estudante divergiu do snapshot preparado.",
        )
    result = await db.students.update_one(
        {"id": student_id, "mantenedora_id": tenant_id, "class_id": source_class_id},
        {"$set": {
            "class_id": destination_class_id,
            "updated_at": now,
            "updated_by": actor.get("id"),
            "rectification_protocol": run.get("protocol"),
        }},
    )
    if result.modified_count != 1:
        raise RectificationSagaError(
            "RECTIFICATION_STUDENT_PROJECTION_CAS_CONFLICT",
            "A projeção do estudante mudou durante a aplicação da saga.",
        )


async def _compensate_grades(db, *, run: Mapping[str, Any]) -> None:
    tenant_id = str(run.get("tenant_id"))
    protocol = str(run.get("protocol"))
    ledgers = await db[GRADE_LEDGER_COLLECTION].find(
        {"mantenedora_id": tenant_id, "protocol": protocol}, {"_id": 0}
    ).to_list(5000)
    for ledger in reversed(ledgers):
        state = ledger.get("state")
        if state in {"PENDING", "COMPENSATED"}:
            continue
        if state not in {"APPLIED", "DESTINATION_APPLIED"}:
            raise RectificationSagaError(
                "RECTIFICATION_GRADE_COMPENSATION_UNSAFE",
                "O ledger de notas não permite provar compensação segura.",
                detail={"source_grade_id": ledger.get("source_grade_id"), "state": state},
            )
        destination_id = ledger.get("destination_grade_id")
        current_destination = None
        if destination_id:
            current_destination = await db.grades.find_one(
                {"id": destination_id, "mantenedora_id": tenant_id}, {"_id": 0}
            )
        expected_after = ledger.get("destination_fingerprint_after")
        before = ledger.get("destination_before")
        if current_destination:
            if expected_after and grade_academic_fingerprint(current_destination) != expected_after:
                raise RectificationSagaError(
                    "RECTIFICATION_GRADE_COMPENSATION_CAS_CONFLICT",
                    "A nota de destino mudou depois da saga; compensação automática foi recusada.",
                    detail={"destination_grade_id": destination_id},
                )
            if before is None:
                deleted = await db.grades.delete_one(grade_cas_filter(current_destination))
                if deleted.deleted_count != 1:
                    raise RectificationSagaError(
                        "RECTIFICATION_GRADE_COMPENSATION_DELETE_CONFLICT",
                        "Não foi possível retirar com CAS a nota criada pela saga.",
                    )
            else:
                replaced = await db.grades.replace_one(grade_cas_filter(current_destination), deepcopy(before))
                if replaced.modified_count != 1:
                    raise RectificationSagaError(
                        "RECTIFICATION_GRADE_COMPENSATION_RESTORE_CONFLICT",
                        "Não foi possível restaurar com CAS a nota pré-existente do destino.",
                    )
        elif before is not None:
            raise RectificationSagaError(
                "RECTIFICATION_GRADE_COMPENSATION_DESTINATION_MISSING",
                "A nota de destino que deveria ser restaurada desapareceu.",
            )

        source_snapshot = deepcopy(ledger.get("source_grade_snapshot") or {})
        source_id = source_snapshot.get("id")
        if source_id:
            current_source = await db.grades.find_one({"id": source_id, "mantenedora_id": tenant_id}, {"_id": 0})
            if current_source:
                if grade_academic_fingerprint(current_source) != grade_academic_fingerprint(source_snapshot):
                    raise RectificationSagaError(
                        "RECTIFICATION_GRADE_COMPENSATION_SOURCE_CONFLICT",
                        "A nota de origem reapareceu com conteúdo diferente.",
                    )
            else:
                await db.grades.insert_one(source_snapshot)
        await db[GRADE_LEDGER_COLLECTION].update_one(
            {"mantenedora_id": tenant_id, "protocol": protocol, "source_grade_id": ledger.get("source_grade_id")},
            {"$set": {"state": "COMPENSATED", "compensated_at": _now()}},
        )


async def _compensate_attendance(db, *, run: Mapping[str, Any]) -> bool:
    """Restaura o student-record; validação antiga nunca é recriada automaticamente."""
    tenant_id = str(run.get("tenant_id"))
    protocol = str(run.get("protocol"))
    snapshot = run.get("final_pre_execution_snapshot") or run.get("pre_execution_snapshot") or {}
    originals = {str(item.get("id")): item for item in (snapshot.get("attendance_documents") or []) if item.get("id")}
    revalidation_pending = False
    ledgers = await db[ATTENDANCE_LEDGER_COLLECTION].find(
        {"mantenedora_id": tenant_id, "protocol": protocol}, {"_id": 0}
    ).to_list(10000)
    for ledger in reversed(ledgers):
        state = ledger.get("state")
        if state in {"PENDING", "COMPENSATED"}:
            continue
        if state != "APPLIED":
            raise RectificationSagaError(
                "RECTIFICATION_ATTENDANCE_COMPENSATION_UNSAFE",
                "O ledger de frequência não permite provar compensação segura.",
                detail={"source_attendance_id": ledger.get("source_attendance_id"), "state": state},
            )
        attendance_id = str(ledger.get("source_attendance_id"))
        current = await db.attendance.find_one(
            {"id": attendance_id, "mantenedora_id": tenant_id}, {"_id": 0}
        )
        original = deepcopy(originals.get(attendance_id) or {})
        if not current or not original:
            raise RectificationSagaError(
                "RECTIFICATION_ATTENDANCE_COMPENSATION_SNAPSHOT_MISSING",
                "Frequência ou snapshot original indisponível para compensação segura.",
            )
        if ledger.get("source_document_hash_after") and attendance_digest(current) != ledger.get("source_document_hash_after"):
            raise RectificationSagaError(
                "RECTIFICATION_ATTENDANCE_COMPENSATION_CAS_CONFLICT",
                "A frequência mudou depois da saga; compensação automática foi recusada.",
            )
        current_version = current.get("version") or 0
        restored = original
        restored["version"] = current_version + 1
        restored["updated_at"] = _now()
        restored["updated_by"] = (run.get("actor") or {}).get("id")
        if ledger.get("requires_revalidation"):
            revalidation_pending = True
            for field in ("validated_by", "validated_by_name", "validated_by_role", "validated_at"):
                restored.pop(field, None)
            restored["rectification_revalidation_pending"] = True
            restored["rectification_revalidation_protocol"] = protocol
        replaced = await db.attendance.replace_one(
            {"id": attendance_id, "mantenedora_id": tenant_id, "version": current.get("version")},
            restored,
        )
        if replaced.modified_count != 1:
            raise RectificationSagaError(
                "RECTIFICATION_ATTENDANCE_COMPENSATION_RESTORE_CONFLICT",
                "Não foi possível restaurar a frequência com CAS.",
            )
        await db[ATTENDANCE_LEDGER_COLLECTION].update_one(
            {
                "mantenedora_id": tenant_id,
                "protocol": protocol,
                "source_attendance_id": attendance_id,
                "student_id": run.get("student_id"),
            },
            {"$set": {
                "state": "COMPENSATED",
                "compensated_at": _now(),
                "revalidation_pending": bool(ledger.get("requires_revalidation")),
            }},
        )
    return revalidation_pending


async def _restore_enrollment_projection(db, *, run: Mapping[str, Any]) -> None:
    tenant_id = str(run.get("tenant_id"))
    source_class_id = str(run.get("source_class_id"))
    destination_class_id = str(run.get("destination_class_id"))
    enrollment_id = str(run.get("source_enrollment_id"))
    student_id = str(run.get("student_id"))
    snapshot = run.get("final_pre_execution_snapshot") or run.get("pre_execution_snapshot") or {}

    original_enrollment = next(
        (deepcopy(item) for item in (snapshot.get("enrollments") or []) if str(item.get("id")) == enrollment_id),
        None,
    )
    original_student = deepcopy(snapshot.get("student") or {})
    if not original_enrollment or not original_student:
        raise RectificationSagaError(
            "RECTIFICATION_ENROLLMENT_COMPENSATION_SNAPSHOT_MISSING",
            "Snapshot de matrícula/estudante não está disponível para compensação.",
        )

    current_enrollment = await db.enrollments.find_one(
        {"id": enrollment_id, "mantenedora_id": tenant_id}, {"_id": 0}
    )
    if not current_enrollment:
        raise RectificationSagaError("RECTIFICATION_ENROLLMENT_COMPENSATION_MISSING", "Matrícula desapareceu durante a saga.")
    if str(current_enrollment.get("class_id")) == source_class_id:
        pass
    elif str(current_enrollment.get("class_id")) == destination_class_id:
        replaced = await db.enrollments.replace_one(
            {"id": enrollment_id, "mantenedora_id": tenant_id, "class_id": destination_class_id},
            original_enrollment,
        )
        if replaced.modified_count != 1:
            raise RectificationSagaError("RECTIFICATION_ENROLLMENT_COMPENSATION_CAS_CONFLICT", "CAS de restauração da matrícula falhou.")
    else:
        raise RectificationSagaError(
            "RECTIFICATION_ENROLLMENT_COMPENSATION_CLASS_CONFLICT",
            "A matrícula foi movida para uma terceira turma; compensação automática foi recusada.",
        )

    current_student = await db.students.find_one(
        {"id": student_id, "mantenedora_id": tenant_id}, {"_id": 0}
    )
    if not current_student:
        raise RectificationSagaError("RECTIFICATION_STUDENT_COMPENSATION_MISSING", "Estudante desapareceu durante a saga.")
    if str(current_student.get("class_id")) == source_class_id:
        return
    if str(current_student.get("class_id")) != destination_class_id:
        raise RectificationSagaError(
            "RECTIFICATION_STUDENT_COMPENSATION_CLASS_CONFLICT",
            "A projeção do estudante aponta para uma terceira turma.",
        )
    replaced = await db.students.replace_one(
        {"id": student_id, "mantenedora_id": tenant_id, "class_id": destination_class_id},
        original_student,
    )
    if replaced.modified_count != 1:
        raise RectificationSagaError("RECTIFICATION_STUDENT_COMPENSATION_CAS_CONFLICT", "CAS de restauração do estudante falhou.")


async def _compensate_academic(db, *, run: Mapping[str, Any]) -> dict[str, Any]:
    tenant_id = str(run.get("tenant_id"))
    protocol = str(run.get("protocol"))
    irrevocable = await db[DOCUMENT_LEDGER_COLLECTION].count_documents(
        {"mantenedora_id": tenant_id, "protocol": protocol, "state": "APPLIED"}
    )
    if irrevocable:
        raise RectificationSagaError(
            "RECTIFICATION_COMPENSATION_DOCUMENT_IRREVERSIBLE",
            "Há documento revogado pela saga; compensação automática integral não é possível.",
            detail={"document_revocations": irrevocable},
        )
    await _compensate_grades(db, run=run)
    revalidation_pending = await _compensate_attendance(db, run=run)
    await _restore_enrollment_projection(db, run=run)
    return {"attendance_revalidation_pending": revalidation_pending}


async def _verify_source_restored(db, *, run: Mapping[str, Any]) -> None:
    tenant_id = str(run.get("tenant_id"))
    source = str(run.get("source_class_id"))
    enrollment = await db.enrollments.find_one(
        {"id": run.get("source_enrollment_id"), "mantenedora_id": tenant_id}, {"_id": 0}
    )
    student = await db.students.find_one(
        {"id": run.get("student_id"), "mantenedora_id": tenant_id}, {"_id": 0}
    )
    if not enrollment or str(enrollment.get("class_id")) != source:
        raise RectificationSagaError("RECTIFICATION_ROLLBACK_ENROLLMENT_POSTCONDITION_FAILED", "Matrícula não retornou à origem.")
    if not student or str(student.get("class_id")) != source:
        raise RectificationSagaError("RECTIFICATION_ROLLBACK_STUDENT_POSTCONDITION_FAILED", "Projeção do estudante não retornou à origem.")


async def execute_rectification_saga(
    db,
    *,
    prepare_id: str,
    tenant_id: str,
    actor: Mapping[str, Any],
    document_acknowledgement: str,
    request=None,
    audit_service=None,
    secret: str | None = None,
) -> dict[str, Any]:
    """Executa PREPARED → APPLYING → APPLIED sob lock tenant+estudante."""
    _assert_actor(actor)
    if not saga_execution_enabled():
        raise RectificationSagaError(
            "RECTIFICATION_EXECUTION_DISABLED",
            "A saga está instalada, mas a execução acadêmica permanece desabilitada por configuração.",
            status_code=503,
        )
    if document_acknowledgement != DOCUMENT_ACKNOWLEDGEMENT:
        raise RectificationSagaError(
            "DOCUMENT_UNTRACKED_ACKNOWLEDGEMENT_REQUIRED",
            "O reconhecimento documental explícito é obrigatório para executar a saga.",
            status_code=422,
        )
    run = await db[RUNS_COLLECTION].find_one({"_id": prepare_id, "tenant_id": tenant_id}, {"_id": 0})
    if not run:
        raise RectificationSagaError("RECTIFICATION_RUN_NOT_FOUND", "Preparação não encontrada no tenant operacional.", status_code=404)
    _assert_same_operator(run, actor)
    if run.get("state") == "APPLIED":
        return {"prepare_id": prepare_id, "protocol": run.get("protocol"), "state": "APPLIED", "idempotent_replay": True}
    if run.get("state") != "PREPARED":
        raise RectificationSagaError(
            "RECTIFICATION_RUN_NOT_PREPARED",
            "Somente uma preparação PREPARED pode iniciar execução.",
            detail={"state": run.get("state")},
        )

    holder = f"rectification-f22-execute:{prepare_id}:{actor.get('id')}"
    target = _lock_target(tenant_id, str(run.get("student_id")))
    acquired, lock_info = await acquire_lock(db, target, holder, LOCKS_COLLECTION)
    if not acquired:
        raise RectificationSagaError("RECTIFICATION_STUDENT_LOCKED", "Estudante está sob outra mutação crítica.", detail={"lock": lock_info})
    applying = False
    try:
        run = await db[RUNS_COLLECTION].find_one({"_id": prepare_id, "tenant_id": tenant_id}, {"_id": 0})
        if run.get("state") == "APPLIED":
            return {"prepare_id": prepare_id, "protocol": run.get("protocol"), "state": "APPLIED", "idempotent_replay": True}
        if run.get("state") != "PREPARED":
            raise RectificationSagaError("RECTIFICATION_RUN_STATE_CHANGED", "O estado da preparação mudou antes do lock.", detail={"state": run.get("state")})

        claims = {
            "student_id": run.get("student_id"),
            "source_enrollment_id": run.get("source_enrollment_id"),
            "source_class_id": run.get("source_class_id"),
            "destination_class_id": run.get("destination_class_id"),
            "academic_year": run.get("academic_year"),
            "precondition_hash": run.get("precondition_hash"),
        }
        plan, inventory = await _current_saga_plan(db, claims=claims, tenant_id=tenant_id, actor=actor, secret=secret)
        if run.get("document_inventory_digest") and run.get("document_inventory_digest") != inventory.get("inventory_digest"):
            raise RectificationSagaError(
                "RECTIFICATION_DOCUMENT_PRECONDITION_CHANGED",
                "O inventário documental mudou depois da preparação.",
                detail={"expected": run.get("document_inventory_digest"), "current": inventory.get("inventory_digest")},
            )

        final_snapshot = await build_compensating_snapshot(
            db,
            claims=claims,
            tenant_id=tenant_id,
            current_dry_run=plan,
        )
        await db[RUNS_COLLECTION].update_one(
            {"_id": prepare_id, "tenant_id": tenant_id, "state": "PREPARED"},
            {"$set": {
                "final_pre_execution_snapshot": final_snapshot,
                "final_snapshot_digest": final_snapshot.get("snapshot_digest"),
                "snapshot_is_final_for_mutation": True,
                "execution_plan": {
                    "grades_manifest": plan.get("grades_manifest") or [],
                    "attendance_manifest": plan.get("attendance_manifest") or [],
                    "document_inventory_digest": inventory.get("inventory_digest"),
                },
                "updated_at": _now(),
            }},
        )
        run = await _transition_run(
            db,
            run_id=prepare_id,
            tenant_id=tenant_id,
            current="PREPARED",
            new="APPLYING",
            extra={"execution_started_at": _now(), "execution_actor": {"id": actor.get("id"), "role": actor.get("role")}},
        )
        applying = True

        await _apply_enrollment_projection(db, run=run, plan=plan, actor=actor)
        await _checkpoint(db, run_id=prepare_id, tenant_id=tenant_id, name="ENROLLMENT_PROJECTION_APPLIED")

        attendance_results = []
        for item in plan.get("attendance_manifest") or []:
            attendance_results.append(
                await apply_attendance_rectification_item(
                    db,
                    manifest_item=item,
                    protocol=str(run.get("protocol")),
                    tenant_id=tenant_id,
                    student_id=str(run.get("student_id")),
                    source_class_id=str(run.get("source_class_id")),
                    target_enrollment_id=str(run.get("source_enrollment_id")),
                    target_class_id=str(run.get("destination_class_id")),
                    academic_year=int(run.get("academic_year")),
                    actor=actor,
                    request=request,
                    audit_service=audit_service,
                )
            )
        await _checkpoint(
            db,
            run_id=prepare_id,
            tenant_id=tenant_id,
            name="ATTENDANCE_APPLIED",
            detail={"items": len(attendance_results)},
        )

        grade_results = []
        for item in plan.get("grades_manifest") or []:
            if not item.get("migratable_fields"):
                continue
            grade_results.append(
                await apply_grade_rectification_item(
                    db,
                    manifest_item=item,
                    protocol=str(run.get("protocol")),
                    tenant_id=tenant_id,
                    student_id=str(run.get("student_id")),
                    source_class_id=str(run.get("source_class_id")),
                    target_enrollment_id=str(run.get("source_enrollment_id")),
                    target_class_id=str(run.get("destination_class_id")),
                    academic_year=int(run.get("academic_year")),
                    actor=actor,
                    request=request,
                    audit_service=audit_service,
                )
            )
        await _checkpoint(
            db,
            run_id=prepare_id,
            tenant_id=tenant_id,
            name="GRADES_APPLIED",
            detail={"items": len(grade_results)},
        )

        residues = await detect_rectification_origin_residues(
            db,
            student_id=str(run.get("student_id")),
            source_enrollment_id=str(run.get("source_enrollment_id")),
            source_class_id=str(run.get("source_class_id")),
            academic_year=int(run.get("academic_year")),
            tenant_id=tenant_id,
        )
        if not residues.get("ok"):
            raise RectificationSagaError(
                "RECTIFICATION_ORIGIN_RESIDUES_PRESENT",
                "A pós-condição falhou: ainda há resíduos acadêmicos na turma de origem.",
                detail={"residues": residues.get("residues")},
            )
        await _checkpoint(db, run_id=prepare_id, tenant_id=tenant_id, name="ORIGIN_ZERO_POSTCONDITION")

        document_result = await resolve_rectification_documents(
            db,
            protocol=str(run.get("protocol")),
            student_id=str(run.get("student_id")),
            source_class_id=str(run.get("source_class_id")),
            academic_year=int(run.get("academic_year")),
            tenant_id=tenant_id,
            actor=actor,
            acknowledgement=document_acknowledgement,
        )
        await _checkpoint(
            db,
            run_id=prepare_id,
            tenant_id=tenant_id,
            name="DOCUMENTS_RESOLVED",
            detail={"revoked_count": document_result.get("revoked_count", 0)},
        )

        run = await _transition_run(
            db,
            run_id=prepare_id,
            tenant_id=tenant_id,
            current="APPLYING",
            new="APPLIED",
            extra={
                "executed_at": _now(),
                "academic_mutation_enabled": True,
                "academic_mutation_performed": True,
                "origin_residues": residues.get("residues"),
                "attendance_items_applied": len(attendance_results),
                "grade_items_applied": len(grade_results),
                "documents_revoked": document_result.get("revoked_count", 0),
            },
        )
        if audit_service is not None:
            await audit_service.log(
                action="update",
                collection="enrollments",
                user=dict(actor),
                request=request,
                document_id=str(run.get("source_enrollment_id")),
                description=f"Retificação de Matrícula/Turma aplicada — protocolo {run.get('protocol')}",
                academic_year=run.get("academic_year"),
                extra_data={
                    "prepare_id": prepare_id,
                    "protocol": run.get("protocol"),
                    "source_class_id": run.get("source_class_id"),
                    "destination_class_id": run.get("destination_class_id"),
                },
            )
        return {
            "contract_version": SAGA_CONTRACT_VERSION,
            "prepare_id": prepare_id,
            "protocol": run.get("protocol"),
            "state": "APPLIED",
            "idempotent_replay": False,
            "origin_residues": residues.get("residues"),
            "attendance_items_applied": len(attendance_results),
            "grade_items_applied": len(grade_results),
            "documents_revoked": document_result.get("revoked_count", 0),
        }
    except Exception as exc:
        if applying:
            latest = await db[RUNS_COLLECTION].find_one({"_id": prepare_id, "tenant_id": tenant_id}, {"_id": 0})
            try:
                compensation = await _compensate_academic(db, run=latest)
                await _transition_run(
                    db,
                    run_id=prepare_id,
                    tenant_id=tenant_id,
                    current="APPLYING",
                    new="FAILED_COMPENSATED",
                    extra={
                        "failure_code": getattr(exc, "code", "RECTIFICATION_SAGA_APPLY_FAILED"),
                        "failure_message": str(exc),
                        "compensated_at": _now(),
                        **compensation,
                    },
                )
                state = "FAILED_COMPENSATED"
            except Exception as compensation_exc:
                await db[RUNS_COLLECTION].update_one(
                    {"_id": prepare_id, "tenant_id": tenant_id},
                    {"$set": {
                        "state": "FAILED_MANUAL_RECOVERY",
                        "updated_at": _now(),
                        "failure_code": getattr(exc, "code", "RECTIFICATION_SAGA_APPLY_FAILED"),
                        "failure_message": str(exc),
                        "compensation_failure": str(compensation_exc),
                    }},
                )
                state = "FAILED_MANUAL_RECOVERY"
            raise RectificationSagaError(
                "RECTIFICATION_SAGA_APPLY_FAILED",
                "A saga não concluiu; o estado de recuperação foi registrado.",
                detail={
                    "run_state": state,
                    "cause_code": getattr(exc, "code", None),
                    "cause": str(exc),
                },
            ) from exc
        if isinstance(exc, RectificationSagaError):
            raise
        raise RectificationSagaError(
            "RECTIFICATION_SAGA_PREMUTATION_FAILED",
            "A execução foi recusada antes de iniciar mutação acadêmica.",
            detail={"cause_code": getattr(exc, "code", None), "cause": str(exc)},
        ) from exc
    finally:
        await release_lock(db, target, holder, LOCKS_COLLECTION)


async def rollback_rectification_saga(
    db,
    *,
    prepare_id: str,
    tenant_id: str,
    actor: Mapping[str, Any],
    justification: str,
    request=None,
    audit_service=None,
) -> dict[str, Any]:
    """Reverte somente APPLIED documentalmente elegível; independe da feature flag."""
    _assert_actor(actor)
    if len((justification or "").strip()) < 30:
        raise RectificationSagaError(
            "RECTIFICATION_ROLLBACK_JUSTIFICATION_TOO_SHORT",
            "A justificativa de rollback deve ter pelo menos 30 caracteres.",
            status_code=422,
        )
    run = await db[RUNS_COLLECTION].find_one({"_id": prepare_id, "tenant_id": tenant_id}, {"_id": 0})
    if not run:
        raise RectificationSagaError("RECTIFICATION_RUN_NOT_FOUND", "Saga não encontrada no tenant operacional.", status_code=404)
    if run.get("state") == "ROLLED_BACK":
        return {"prepare_id": prepare_id, "protocol": run.get("protocol"), "state": "ROLLED_BACK", "idempotent_replay": True}
    if run.get("state") != "APPLIED":
        raise RectificationSagaError(
            "RECTIFICATION_ROLLBACK_STATE_INVALID",
            "Somente uma saga APPLIED pode ser revertida automaticamente.",
            detail={"state": run.get("state")},
        )

    holder = f"rectification-f22-rollback:{prepare_id}:{actor.get('id')}"
    target = _lock_target(tenant_id, str(run.get("student_id")))
    acquired, lock_info = await acquire_lock(db, target, holder, LOCKS_COLLECTION)
    if not acquired:
        raise RectificationSagaError("RECTIFICATION_STUDENT_LOCKED", "Estudante está sob outra mutação crítica.", detail={"lock": lock_info})
    rolling = False
    try:
        run = await db[RUNS_COLLECTION].find_one({"_id": prepare_id, "tenant_id": tenant_id}, {"_id": 0})
        if run.get("state") == "ROLLED_BACK":
            return {"prepare_id": prepare_id, "protocol": run.get("protocol"), "state": "ROLLED_BACK", "idempotent_replay": True}
        if run.get("state") != "APPLIED":
            raise RectificationSagaError("RECTIFICATION_ROLLBACK_STATE_CHANGED", "O estado da saga mudou antes do rollback.")

        eligibility = await check_rectification_rollback_eligibility(
            db,
            protocol=str(run.get("protocol")),
            student_id=str(run.get("student_id")),
            source_class_id=str(run.get("source_class_id")),
            academic_year=int(run.get("academic_year")),
            tenant_id=tenant_id,
            executed_at=str(run.get("executed_at") or ""),
        )
        if not eligibility.get("eligible"):
            raise RectificationSagaError(
                "RECTIFICATION_ROLLBACK_BLOCKED",
                "Rollback automático bloqueado pelo eixo documental.",
                detail={"blockers": eligibility.get("blockers")},
            )
        run = await _transition_run(
            db,
            run_id=prepare_id,
            tenant_id=tenant_id,
            current="APPLIED",
            new="ROLLING_BACK",
            extra={
                "rollback_started_at": _now(),
                "rollback_actor": {"id": actor.get("id"), "role": actor.get("role")},
                "rollback_justification": justification.strip(),
            },
        )
        rolling = True
        compensation = await _compensate_academic(db, run=run)
        await _verify_source_restored(db, run=run)
        run = await _transition_run(
            db,
            run_id=prepare_id,
            tenant_id=tenant_id,
            current="ROLLING_BACK",
            new="ROLLED_BACK",
            extra={"rolled_back_at": _now(), **compensation},
        )
        if audit_service is not None:
            await audit_service.log(
                action="update",
                collection="enrollments",
                user=dict(actor),
                request=request,
                document_id=str(run.get("source_enrollment_id")),
                description=f"Rollback da Retificação de Matrícula/Turma — protocolo {run.get('protocol')}",
                academic_year=run.get("academic_year"),
                extra_data={"prepare_id": prepare_id, "protocol": run.get("protocol")},
            )
        return {
            "contract_version": SAGA_CONTRACT_VERSION,
            "prepare_id": prepare_id,
            "protocol": run.get("protocol"),
            "state": "ROLLED_BACK",
            "idempotent_replay": False,
            **compensation,
        }
    except Exception as exc:
        if rolling:
            await db[RUNS_COLLECTION].update_one(
                {"_id": prepare_id, "tenant_id": tenant_id},
                {"$set": {
                    "state": "FAILED_MANUAL_RECOVERY",
                    "updated_at": _now(),
                    "rollback_failure_code": getattr(exc, "code", "RECTIFICATION_ROLLBACK_FAILED"),
                    "rollback_failure_message": str(exc),
                }},
            )
            raise RectificationSagaError(
                "RECTIFICATION_ROLLBACK_FAILED_MANUAL_RECOVERY",
                "O rollback iniciou, mas não pôde ser concluído com segurança; recuperação manual é obrigatória.",
                detail={"cause_code": getattr(exc, "code", None), "cause": str(exc)},
            ) from exc
        if isinstance(exc, RectificationSagaError):
            raise
        if isinstance(exc, (RectificationExecutionError, AttendanceRectificationError, GradeRectificationError, DocumentRectificationError)):
            raise RectificationSagaError(
                "RECTIFICATION_ROLLBACK_PREMUTATION_FAILED",
                "Rollback recusado antes de mutação.",
                detail={"cause_code": getattr(exc, "code", None), "cause": str(exc)},
            ) from exc
        raise
    finally:
        await release_lock(db, target, holder, LOCKS_COLLECTION)
