"""F2.3 — binding runtime compatível da saga F2.2.

A F2.2 foi construída sobre helpers do núcleo F2.0 cujas assinaturas atuais
não coincidem integralmente com as chamadas históricas da saga. Este módulo
faz a composição explícita entre os dois contratos sem alterar a semântica
acadêmica da F2.2:

- valida os gates humanos pelo núcleo F2.0;
- valida a Idempotency-Key antes de persistir PREPARED;
- reautentica com a assinatura canônica atual;
- deriva prepare_id por tenant + estudante + Idempotency-Key;
- adapta o snapshot F2.0 para a forma esperada pela saga, acrescentando seu
  digest calculado, sem alterar o conteúdo acadêmico capturado;
- mantém execute/rollback no SSoT da F2.2.

A feature flag continua fail-closed e não é modificada por este módulo.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Mapping

from services import enrollment_rectification_saga as _saga
from services.enrollment_rectification_execution import (
    RectificationExecutionError,
    _prepare_id as _core_prepare_id,
    _reauthenticate as _core_reauthenticate,
    _validate_human_gates as _core_validate_human_gates,
    build_compensating_snapshot as _core_build_compensating_snapshot,
    snapshot_digest as _core_snapshot_digest,
)


RectificationSagaError = _saga.RectificationSagaError
saga_execution_enabled = _saga.saga_execution_enabled
execute_rectification_saga = _saga.execute_rectification_saga
rollback_rectification_saga = _saga.rollback_rectification_saga


async def build_compensating_snapshot(
    db,
    *,
    claims: Mapping[str, Any],
    tenant_id: str,
    current_dry_run: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Adapta o snapshot canônico F2.0 ao contrato consumido pela F2.2.

    ``current_dry_run`` é aceito apenas por compatibilidade de chamada. O
    snapshot permanece calculado exclusivamente pelo helper canônico F2.0.
    """
    del current_dry_run
    snapshot = await _core_build_compensating_snapshot(
        db,
        claims=claims,
        tenant_id=str(tenant_id),
    )
    adapted = dict(snapshot)
    adapted["snapshot_digest"] = _core_snapshot_digest(snapshot)
    return adapted


# A função execute_rectification_saga() vive no módulo F2.2 e resolve o nome
# ``build_compensating_snapshot`` pelo namespace global daquele módulo. Fazemos
# o binding uma única vez no import para que a execução use o adaptador acima,
# sem duplicar a regra acadêmica da saga.
_saga.build_compensating_snapshot = build_compensating_snapshot


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
    """Prepara a saga F2.2 usando as assinaturas canônicas atuais do F2.0."""
    _saga._assert_actor(actor)

    claims = _saga.verify_rectification_dry_run_token(
        dry_run_token,
        tenant_id=str(tenant_id),
        now=now,
        secret=secret,
    )
    normalized_justification = _core_validate_human_gates(
        confirmation=confirmation,
        justification=justification,
    )
    await _core_reauthenticate(db, actor, password)

    key = (idempotency_key or "").strip()
    if len(key) < 8:
        raise RectificationSagaError(
            "RECTIFICATION_IDEMPOTENCY_KEY_REQUIRED",
            "Idempotency-Key é obrigatório e deve identificar unicamente a tentativa.",
            status_code=422,
        )

    tenant = str(tenant_id)
    student_id = str(claims.get("student_id") or "")
    prepare_id = _core_prepare_id(tenant, student_id, key)

    async def _existing_run():
        return await db[_saga.RUNS_COLLECTION].find_one(
            {"_id": prepare_id, "tenant_id": tenant},
            {"_id": 0},
        )

    existing = await _existing_run()
    if existing:
        if (
            str((existing.get("actor") or {}).get("id") or "")
            != str(actor.get("id") or "")
            or existing.get("precondition_hash") != claims.get("precondition_hash")
        ):
            raise RectificationSagaError(
                "RECTIFICATION_IDEMPOTENCY_CONFLICT",
                "A mesma Idempotency-Key já foi usada por outro operador ou snapshot.",
            )
        return _saga._prepared_response(existing, replay=True)

    holder = f"rectification-f23-prepare:{prepare_id}"
    target = _saga._lock_target(tenant, student_id)
    acquired, lock_info = await _saga.acquire_lock(
        db,
        target,
        holder,
        _saga.LOCKS_COLLECTION,
    )
    if not acquired:
        raise RectificationSagaError(
            "RECTIFICATION_STUDENT_LOCKED",
            "Outra operação crítica está em andamento para este estudante.",
            detail={"lock": lock_info},
        )

    try:
        # Recheck sob lock para fechar a janela entre lookup e persistência.
        existing = await _existing_run()
        if existing:
            if (
                str((existing.get("actor") or {}).get("id") or "")
                != str(actor.get("id") or "")
                or existing.get("precondition_hash") != claims.get("precondition_hash")
            ):
                raise RectificationSagaError(
                    "RECTIFICATION_IDEMPOTENCY_CONFLICT",
                    "A Idempotency-Key tornou-se conflitante durante a preparação.",
                )
            return _saga._prepared_response(existing, replay=True)

        current, inventory = await _saga._current_saga_plan(
            db,
            claims=claims,
            tenant_id=tenant,
            actor=actor,
            secret=secret,
        )
        snapshot = await build_compensating_snapshot(
            db,
            claims=claims,
            tenant_id=tenant,
            current_dry_run=current,
        )

        protocol = str(uuid.uuid4())
        created = _saga._now()
        run_doc = {
            "_id": prepare_id,
            "prepare_id": prepare_id,
            "protocol": protocol,
            "contract_version": _saga.SAGA_CONTRACT_VERSION,
            "base_execution_contract": _saga.EXECUTION_CONTRACT_VERSION,
            "tenant_id": tenant,
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
            "actor": {
                "id": actor.get("id"),
                "email": actor.get("email"),
                "role": actor.get("role"),
            },
            "justification": normalized_justification,
            "idempotency_key": key,
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
        await db[_saga.RUNS_COLLECTION].insert_one(run_doc)
        return _saga._prepared_response(run_doc, replay=False)
    finally:
        await _saga.release_lock(
            db,
            target,
            holder,
            _saga.LOCKS_COLLECTION,
        )


__all__ = [
    "RectificationExecutionError",
    "RectificationSagaError",
    "build_compensating_snapshot",
    "execute_rectification_saga",
    "prepare_rectification_saga_execution",
    "rollback_rectification_saga",
    "saga_execution_enabled",
]
