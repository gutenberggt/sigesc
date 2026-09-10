"""F2.3D-B — composição da saga F2.2/F2.3 com frequência ordinal.

A F2.1A preserva e retira o student-record da turma de origem. A F2.3D
materializa a mesma sequência, por componente e por posição, nas aulas reais
já existentes do destino.

Composição:
- execução nova: a materialização ordinal ocorre no checkpoint
  ``ATTENDANCE_APPLIED``, ainda dentro do lock crítico da saga F2.2;
- qualquer falha nesse checkpoint entra na compensação automática da própria
  saga antes do estado final ``APPLIED``;
- rollback/compensação remove primeiro os records ordinais do destino e só
  depois restaura a evidência da origem;
- replay de uma saga histórica já ``APPLIED`` usa lock próprio e recupera
  apenas a frequência ordinal, sem repetir matrícula/notas nem desfazer a
  matrícula caso a recuperação seja recusada;
- request/audit_service do chamador são transportados por ContextVar até o
  checkpoint interno, preservando desvalidação institucional auditada.
"""
from __future__ import annotations

from contextvars import ContextVar
from copy import deepcopy
from typing import Any, Mapping

from services import enrollment_rectification_saga as _saga
from services import enrollment_rectification_saga_runtime as _runtime
from services.enrollment_rectification_attendance import _digest as attendance_digest
from services.enrollment_rectification_attendance_ordinal import (
    ORDINAL_LEDGER_COLLECTION,
    apply_ordinal_attendance_from_ledger,
    build_ordinal_attendance_plan,
)

RectificationExecutionError = _runtime.RectificationExecutionError
RectificationSagaError = _runtime.RectificationSagaError
prepare_rectification_saga_execution = _runtime.prepare_rectification_saga_execution
saga_execution_enabled = _runtime.saga_execution_enabled

_BASE_COMPENSATE_ACADEMIC = _saga._compensate_academic
_BASE_CHECKPOINT = _saga._checkpoint
_CTX_ACTOR: ContextVar[Mapping[str, Any] | None] = ContextVar("f23d_actor", default=None)
_CTX_REQUEST: ContextVar[Any] = ContextVar("f23d_request", default=None)
_CTX_AUDIT: ContextVar[Any] = ContextVar("f23d_audit", default=None)


def _version_filter(doc: Mapping[str, Any]) -> dict[str, Any]:
    if "version" in doc:
        return {"version": doc.get("version")}
    return {"version": {"$exists": False}}


async def compensate_ordinal_attendance(db, *, run: Mapping[str, Any]) -> dict[str, Any]:
    """Remove materializações F2.3D com CAS antes da compensação da F2.2."""
    tenant_id = str(run.get("tenant_id") or "")
    protocol = str(run.get("protocol") or "")
    student_id = str(run.get("student_id") or "")
    actor_id = str((run.get("actor") or {}).get("id") or "")
    ledgers = await db[ORDINAL_LEDGER_COLLECTION].find(
        {
            "mantenedora_id": tenant_id,
            "protocol": protocol,
            "student_id": student_id,
            "state": "APPLIED",
        },
        {"_id": 0},
    ).sort([("applied_at", -1), ("ordinal", -1)]).to_list(10000)

    compensated = 0
    revalidation_pending = 0
    for ledger in ledgers:
        target_id = str(ledger.get("target_attendance_id") or "")
        current = await db.attendance.find_one(
            {"id": target_id, "mantenedora_id": tenant_id}, {"_id": 0}
        )
        before = deepcopy(ledger.get("target_document_before") or {})
        if not current or not before:
            raise RectificationSagaError(
                "RECTIFICATION_ORDINAL_COMPENSATION_SNAPSHOT_MISSING",
                "A frequência ordinal não possui estado suficiente para compensação segura.",
                detail={"target_attendance_id": target_id},
            )
        expected_after = str(ledger.get("target_document_hash_after") or "")
        if expected_after and attendance_digest(current) != expected_after:
            raise RectificationSagaError(
                "RECTIFICATION_ORDINAL_COMPENSATION_CAS_CONFLICT",
                "A frequência de destino mudou depois da migração ordinal.",
                detail={"target_attendance_id": target_id},
            )

        restored = before
        restored["version"] = int(current.get("version") or 1) + 1
        restored["updated_at"] = _saga._now()
        restored["updated_by"] = actor_id
        if ledger.get("requires_revalidation"):
            revalidation_pending += 1
            for field in ("validated_by", "validated_by_name", "validated_by_role", "validated_at"):
                restored.pop(field, None)
            restored["rectification_revalidation_pending"] = True
            restored["rectification_revalidation_protocol"] = protocol

        replaced = await db.attendance.replace_one(
            {
                "id": target_id,
                "mantenedora_id": tenant_id,
                **_version_filter(current),
            },
            restored,
        )
        if replaced.modified_count != 1:
            raise RectificationSagaError(
                "RECTIFICATION_ORDINAL_COMPENSATION_RESTORE_CONFLICT",
                "Não foi possível retirar a frequência ordinal com CAS.",
                detail={"target_attendance_id": target_id},
            )
        await db[ORDINAL_LEDGER_COLLECTION].update_one(
            {
                "mantenedora_id": tenant_id,
                "protocol": protocol,
                "target_attendance_id": target_id,
                "student_id": student_id,
            },
            {"$set": {"state": "COMPENSATED", "compensated_at": _saga._now()}},
        )
        compensated += 1

    return {
        "ordinal_attendance_compensated": compensated,
        "ordinal_revalidation_pending": revalidation_pending,
    }


async def _compensate_academic_with_ordinal(db, *, run: Mapping[str, Any]) -> dict[str, Any]:
    ordinal = await compensate_ordinal_attendance(db, run=run)
    base = await _BASE_COMPENSATE_ACADEMIC(db, run=run)
    return {**base, **ordinal}


async def _mark_ordinal_state(
    db,
    *,
    run_id: str,
    tenant_id: str,
    state: str,
    summary: Mapping[str, Any] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "ordinal_attendance_state": state,
        "ordinal_attendance_updated_at": _saga._now(),
    }
    if summary is not None:
        payload["ordinal_attendance_summary"] = dict(summary)
    if error_code:
        payload["ordinal_attendance_error_code"] = error_code
    if error_message:
        payload["ordinal_attendance_error_message"] = error_message
    update: dict[str, Any] = {"$set": payload}
    if state == "APPLIED":
        update["$unset"] = {
            "ordinal_attendance_error_code": "",
            "ordinal_attendance_error_message": "",
        }
        update["$push"] = {
            "checkpoints": {
                "name": "ATTENDANCE_ORDINAL_APPLIED",
                "at": _saga._now(),
                "summary": dict(summary or {}),
            }
        }
    await db[_saga.RUNS_COLLECTION].update_one(
        {"_id": run_id, "tenant_id": tenant_id}, update
    )


async def _apply_ordinal_for_run(
    db,
    *,
    run: Mapping[str, Any],
    actor: Mapping[str, Any],
    request=None,
    audit_service=None,
) -> dict[str, Any]:
    protocol = str(run.get("protocol") or "")
    tenant_id = str(run.get("tenant_id") or "")
    student_id = str(run.get("student_id") or "")
    target_class_id = str(run.get("destination_class_id") or "")
    academic_year = int(run.get("academic_year"))

    # Preflight imediatamente antes da escrita. Além dos blockers ordinários,
    # garante que nenhuma desvalidação institucional comece sem audit_service.
    preview = await build_ordinal_attendance_plan(
        db,
        protocol=protocol,
        tenant_id=tenant_id,
        student_id=student_id,
        target_class_id=target_class_id,
        academic_year=academic_year,
    )
    if preview.get("blockers"):
        raise RectificationSagaError(
            "RECTIFICATION_ORDINAL_PLAN_BLOCKED",
            "A migração ordinal possui bloqueios no destino.",
            detail={"blockers": preview.get("blockers")},
        )
    validated_slots = [
        pair.get("destination") or {}
        for component in (preview.get("components") or [])
        for pair in (component.get("pairs") or [])
        if (pair.get("destination") or {}).get("validated_by")
        or (pair.get("destination") or {}).get("validated_at")
    ]
    if validated_slots and audit_service is None:
        raise RectificationSagaError(
            "RECTIFICATION_ORDINAL_AUDIT_CONTEXT_REQUIRED",
            "Há frequência validada no destino e o contexto de auditoria não está disponível.",
            detail={"validated_slots": len(validated_slots)},
        )

    ordinal = await apply_ordinal_attendance_from_ledger(
        db,
        protocol=protocol,
        tenant_id=tenant_id,
        student_id=student_id,
        source_class_id=str(run.get("source_class_id") or ""),
        target_class_id=target_class_id,
        academic_year=academic_year,
        actor=actor,
        request=request,
        audit_service=audit_service,
    )
    summary = dict(ordinal.get("summary") or {})
    await _mark_ordinal_state(
        db,
        run_id=str(run.get("prepare_id") or run.get("_id") or ""),
        tenant_id=tenant_id,
        state="APPLIED",
        summary=summary,
    )
    return summary


async def _checkpoint_with_ordinal(
    db,
    *,
    run_id: str,
    tenant_id: str,
    name: str,
    detail: dict[str, Any] | None = None,
) -> None:
    """Fecha frequência ordinal dentro do mesmo lock da execução F2.2."""
    if name == "ATTENDANCE_APPLIED":
        run = await db[_saga.RUNS_COLLECTION].find_one(
            {"_id": run_id, "tenant_id": tenant_id}, {"_id": 0}
        )
        if not run:
            raise RectificationSagaError(
                "RECTIFICATION_RUN_NOT_FOUND",
                "Saga não encontrada durante o checkpoint ordinal.",
                status_code=404,
            )
        if run.get("ordinal_attendance_state") != "APPLIED":
            actor = dict(_CTX_ACTOR.get() or run.get("actor") or {})
            actor["active_mantenedora_id"] = tenant_id
            actor["mantenedora_id"] = tenant_id
            summary = await _apply_ordinal_for_run(
                db,
                run=run,
                actor=actor,
                request=_CTX_REQUEST.get(),
                audit_service=_CTX_AUDIT.get(),
            )
            detail = {**(detail or {}), "ordinal_summary": summary}
    await _BASE_CHECKPOINT(
        db,
        run_id=run_id,
        tenant_id=tenant_id,
        name=name,
        detail=detail,
    )


# A F2.2 resolve estes helpers pelo namespace global. A composição ocorre uma
# única vez por processo e mantém toda falha nova dentro da cadeia compensável.
if not getattr(_saga, "_f23d_ordinal_compensation_installed", False):
    _saga._compensate_academic = _compensate_academic_with_ordinal
    _saga._f23d_ordinal_compensation_installed = True
if not getattr(_saga, "_f23d_ordinal_checkpoint_installed", False):
    _saga._checkpoint = _checkpoint_with_ordinal
    _saga._f23d_ordinal_checkpoint_installed = True


rollback_rectification_saga = _runtime.rollback_rectification_saga


async def _execute_composed(
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
    before = await db[_saga.RUNS_COLLECTION].find_one(
        {"_id": prepare_id, "tenant_id": tenant_id}, {"_id": 0}
    )
    was_applied_before = bool(before and before.get("state") == "APPLIED")

    result = await _runtime.execute_rectification_saga(
        db,
        prepare_id=prepare_id,
        tenant_id=tenant_id,
        actor=actor,
        document_acknowledgement=document_acknowledgement,
        request=request,
        audit_service=audit_service,
        secret=secret,
    )
    if result.get("state") != "APPLIED":
        return result

    run = await db[_saga.RUNS_COLLECTION].find_one(
        {"_id": prepare_id, "tenant_id": tenant_id}, {"_id": 0}
    )
    if not run:
        raise RectificationSagaError(
            "RECTIFICATION_RUN_NOT_FOUND",
            "A saga aplicada não foi localizada para concluir a frequência ordinal.",
            status_code=404,
        )

    # Execução nova: o hook ATTENDANCE_APPLIED já rodou dentro do lock da F2.2.
    if not was_applied_before:
        if run.get("ordinal_attendance_state") != "APPLIED":
            raise RectificationSagaError(
                "RECTIFICATION_ORDINAL_POSTCONDITION_MISSING",
                "A saga terminou APPLIED sem comprovar a materialização ordinal.",
            )
        return {
            **result,
            "attendance_ordinal_state": "APPLIED",
            "attendance_ordinal_summary": run.get("ordinal_attendance_summary") or {},
        }

    # Replay histórico: o núcleo F2.2 devolveu idempotent replay antes de obter
    # lock; adquirimos um lock dedicado somente para a recuperação F2.3D.
    if run.get("ordinal_attendance_state") == "APPLIED":
        return {
            **result,
            "attendance_ordinal_state": "APPLIED",
            "attendance_ordinal_summary": run.get("ordinal_attendance_summary") or {},
        }

    holder = f"rectification-f23d-recovery:{prepare_id}:{actor.get('id')}"
    target = _saga._lock_target(str(tenant_id), str(run.get("student_id") or ""))
    acquired, lock_info = await _saga.acquire_lock(
        db, target, holder, _saga.LOCKS_COLLECTION
    )
    if not acquired:
        raise RectificationSagaError(
            "RECTIFICATION_STUDENT_LOCKED",
            "Estudante está sob outra mutação crítica durante a recuperação ordinal.",
            detail={"lock": lock_info},
        )
    try:
        run = await db[_saga.RUNS_COLLECTION].find_one(
            {"_id": prepare_id, "tenant_id": tenant_id}, {"_id": 0}
        )
        if not run or run.get("state") != "APPLIED":
            raise RectificationSagaError(
                "RECTIFICATION_ORDINAL_RECOVERY_STATE_CHANGED",
                "O estado da saga histórica mudou antes da recuperação ordinal.",
            )
        if run.get("ordinal_attendance_state") == "APPLIED":
            return {
                **result,
                "attendance_ordinal_state": "APPLIED",
                "attendance_ordinal_summary": run.get("ordinal_attendance_summary") or {},
            }
        try:
            summary = await _apply_ordinal_for_run(
                db,
                run=run,
                actor=actor,
                request=request,
                audit_service=audit_service,
            )
            return {
                **result,
                "attendance_ordinal_state": "APPLIED",
                "attendance_ordinal_summary": summary,
            }
        except Exception as exc:
            code = getattr(exc, "code", "RECTIFICATION_ORDINAL_RECOVERY_FAILED")
            compensation_error = None
            try:
                await compensate_ordinal_attendance(db, run=run)
            except Exception as comp_exc:
                compensation_error = str(comp_exc)
            await _mark_ordinal_state(
                db,
                run_id=prepare_id,
                tenant_id=str(tenant_id),
                state="FAILED_MANUAL_RECOVERY" if compensation_error else "FAILED_RECOVERABLE",
                error_code=code,
                error_message=str(exc),
            )
            raise RectificationSagaError(
                "RECTIFICATION_ORDINAL_RECOVERY_FAILED",
                "A matrícula permaneceu aplicada, mas a recuperação ordinal da frequência não concluiu.",
                detail={
                    "cause_code": code,
                    "ordinal_compensation_failed": bool(compensation_error),
                },
            ) from exc
    finally:
        await _saga.release_lock(db, target, holder, _saga.LOCKS_COLLECTION)


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
    """Executa com contexto auditável disponível ao checkpoint F2.3D."""
    actor_token = _CTX_ACTOR.set(dict(actor))
    request_token = _CTX_REQUEST.set(request)
    audit_token = _CTX_AUDIT.set(audit_service)
    try:
        return await _execute_composed(
            db,
            prepare_id=prepare_id,
            tenant_id=tenant_id,
            actor=actor,
            document_acknowledgement=document_acknowledgement,
            request=request,
            audit_service=audit_service,
            secret=secret,
        )
    finally:
        _CTX_AUDIT.reset(audit_token)
        _CTX_REQUEST.reset(request_token)
        _CTX_ACTOR.reset(actor_token)


__all__ = [
    "RectificationExecutionError",
    "RectificationSagaError",
    "compensate_ordinal_attendance",
    "execute_rectification_saga",
    "prepare_rectification_saga_execution",
    "rollback_rectification_saga",
    "saga_execution_enabled",
]
