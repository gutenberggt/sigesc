"""F2.3D-B — composição da saga F2.2/F2.3 com frequência ordinal.

A F2.1A preserva e retira o student-record da turma de origem. A F2.3D
materializa a mesma sequência, por componente e por posição, nas aulas reais
já existentes do destino. Este módulo mantém o SSoT da saga original e adiciona
somente a composição necessária para que:

- execução nova: APPLIED só retorne ao chamador depois da materialização ordinal;
- replay de uma saga já APPLIED: possa recuperar apenas a frequência ordinal;
- rollback/compensação: retire primeiro os records ordinais do destino antes de
  restaurar a evidência da origem, evitando dupla contagem;
- falha de recuperação de uma saga histórica já APPLIED nunca desfaça a
  matrícula automaticamente.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from services import enrollment_rectification_saga as _saga
from services import enrollment_rectification_saga_runtime as _runtime
from services.enrollment_rectification_attendance import _digest as attendance_digest
from services.enrollment_rectification_attendance_ordinal import (
    ORDINAL_LEDGER_COLLECTION,
    OrdinalAttendanceError,
    apply_ordinal_attendance_from_ledger,
)

RectificationExecutionError = _runtime.RectificationExecutionError
RectificationSagaError = _runtime.RectificationSagaError
prepare_rectification_saga_execution = _runtime.prepare_rectification_saga_execution
saga_execution_enabled = _runtime.saga_execution_enabled

_BASE_COMPENSATE_ACADEMIC = _saga._compensate_academic


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


# A saga F2.2 resolve este helper pelo namespace global em rollback e em
# compensação automática. O binding preserva uma única cadeia compensatória.
if not getattr(_saga, "_f23d_ordinal_compensation_installed", False):
    _saga._compensate_academic = _compensate_academic_with_ordinal
    _saga._f23d_ordinal_compensation_installed = True


rollback_rectification_saga = _runtime.rollback_rectification_saga


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
            "checkpoints": {"name": "ATTENDANCE_ORDINAL_APPLIED", "at": _saga._now(), "summary": dict(summary or {})}
        }
    await db[_saga.RUNS_COLLECTION].update_one(
        {"_id": run_id, "tenant_id": tenant_id}, update
    )


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
    """Executa a saga base e fecha a retificação com a materialização F2.3D."""
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
    if run.get("ordinal_attendance_state") == "APPLIED":
        return {
            **result,
            "attendance_ordinal_state": "APPLIED",
            "attendance_ordinal_summary": run.get("ordinal_attendance_summary") or {},
        }

    try:
        ordinal = await apply_ordinal_attendance_from_ledger(
            db,
            protocol=str(run.get("protocol") or ""),
            tenant_id=str(tenant_id),
            student_id=str(run.get("student_id") or ""),
            source_class_id=str(run.get("source_class_id") or ""),
            target_class_id=str(run.get("destination_class_id") or ""),
            academic_year=int(run.get("academic_year")),
            actor=actor,
            request=request,
            audit_service=audit_service,
        )
        summary = dict(ordinal.get("summary") or {})
        await _mark_ordinal_state(
            db,
            run_id=prepare_id,
            tenant_id=str(tenant_id),
            state="APPLIED",
            summary=summary,
        )
        return {
            **result,
            "attendance_ordinal_state": "APPLIED",
            "attendance_ordinal_summary": summary,
        }
    except Exception as exc:
        code = getattr(exc, "code", "RECTIFICATION_ORDINAL_APPLY_FAILED")
        message = str(exc)

        # Saga histórica já APPLIED: compensamos apenas o que a F2.3D possa ter
        # aplicado parcialmente. A matrícula já aceita nunca é desfeita por uma
        # tentativa de recuperação posterior.
        if was_applied_before:
            compensation_error = None
            try:
                await compensate_ordinal_attendance(db, run=run)
            except Exception as comp_exc:  # estado explicitamente recuperável/manual
                compensation_error = str(comp_exc)
            await _mark_ordinal_state(
                db,
                run_id=prepare_id,
                tenant_id=str(tenant_id),
                state="FAILED_MANUAL_RECOVERY" if compensation_error else "FAILED_RECOVERABLE",
                error_code=code,
                error_message=message,
            )
            raise RectificationSagaError(
                "RECTIFICATION_ORDINAL_RECOVERY_FAILED",
                "A matrícula permaneceu aplicada, mas a recuperação ordinal da frequência não concluiu.",
                detail={
                    "cause_code": code,
                    "ordinal_compensation_failed": bool(compensation_error),
                },
            ) from exc

        # Execução nova: como o chamador ainda não recebeu APPLIED, qualquer
        # falha ordinal deve reverter a saga completa pelo rollback canônico,
        # que já foi composto acima com a compensação ordinal.
        try:
            rolled = await _runtime.rollback_rectification_saga(
                db,
                prepare_id=prepare_id,
                tenant_id=tenant_id,
                actor=actor,
                justification=(
                    "Rollback automático F2.3D porque a materialização ordinal "
                    "da frequência falhou antes da conclusão operacional da retificação."
                ),
                request=request,
                audit_service=audit_service,
            )
            rollback_state = rolled.get("state")
        except Exception as rollback_exc:
            rollback_state = "FAILED_MANUAL_RECOVERY"
            await _mark_ordinal_state(
                db,
                run_id=prepare_id,
                tenant_id=str(tenant_id),
                state="FAILED_MANUAL_RECOVERY",
                error_code=code,
                error_message=f"{message}; rollback={rollback_exc}",
            )
        raise RectificationSagaError(
            "RECTIFICATION_ORDINAL_APPLY_FAILED",
            "A frequência ordinal falhou; a retificação não foi concluída operacionalmente.",
            detail={"cause_code": code, "rollback_state": rollback_state},
        ) from exc


__all__ = [
    "RectificationExecutionError",
    "RectificationSagaError",
    "compensate_ordinal_attendance",
    "execute_rectification_saga",
    "prepare_rectification_saga_execution",
    "rollback_rectification_saga",
    "saga_execution_enabled",
]
