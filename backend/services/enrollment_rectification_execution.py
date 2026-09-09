"""F2.0 — núcleo seguro de execução da Retificação de Matrícula/Turma.

IMPORTANTE: esta fase NÃO executa mutação acadêmica. Ela fecha as barreiras que
uma futura F2.1 deverá atravessar antes de alterar matrícula, notas ou frequência:

- validação criptográfica do dry-run F1.0;
- proteção TOCTOU por recomputação do ``precondition_hash``;
- reautenticação, justificativa e frase de confirmação;
- lock por tenant+estudante e idempotência da preparação;
- journal PREPARED e snapshot compensável pré-execução;
- state machine explícita para a futura saga.

Não existe função que escreva em ``students``, ``enrollments``, ``attendance``,
``grades``, ``student_history`` ou ``attendance_rectifications`` neste módulo.
A única persistência permitida é de control-plane em
``enrollment_rectification_runs``; locks usam o helper canônico de
``lib.critical_mutation``.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from auth_utils import verify_password
from lib.critical_mutation import acquire_lock, release_lock
from services.enrollment_rectification import (
    CONFIRMATION_PHRASE,
    CONTRACT_VERSION as DRY_RUN_CONTRACT_VERSION,
    OPERATION,
    RectificationDryRunError,
    _canonical_json,
    _dry_run_secret,
    build_rectification_dry_run,
)


EXECUTION_CONTRACT_VERSION = "F2.0"
MIN_JUSTIFICATION_LENGTH = 30
RUNS_COLLECTION = "enrollment_rectification_runs"
LOCKS_COLLECTION = "enrollment_rectification_locks"

# F2.0 é deliberadamente incapaz de executar mutação acadêmica, mesmo se uma
# variável de ambiente for configurada por engano. F2.1 deverá mudar o contrato
# explicitamente e receber revisão própria.
ACADEMIC_MUTATION_IMPLEMENTED = False

RUN_STATES = frozenset(
    {
        "PREPARED",
        "APPLYING",
        "APPLIED",
        "ROLLING_BACK",
        "ROLLED_BACK",
        "FAILED_COMPENSATED",
        "FAILED_MANUAL_RECOVERY",
    }
)
_ALLOWED_TRANSITIONS = {
    "PREPARED": frozenset({"APPLYING"}),
    "APPLYING": frozenset(
        {"APPLIED", "ROLLING_BACK", "FAILED_COMPENSATED", "FAILED_MANUAL_RECOVERY"}
    ),
    "APPLIED": frozenset({"ROLLING_BACK"}),
    "ROLLING_BACK": frozenset({"ROLLED_BACK", "FAILED_MANUAL_RECOVERY"}),
    "ROLLED_BACK": frozenset(),
    "FAILED_COMPENSATED": frozenset(),
    "FAILED_MANUAL_RECOVERY": frozenset(),
}


class RectificationExecutionError(Exception):
    """Erro do contrato F2.0 convertido em HTTP pelo router."""

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


def academic_execution_enabled() -> bool:
    """F2.0 nunca habilita escrita acadêmica, inclusive por configuração."""
    requested = os.environ.get("ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED", "false").lower() == "true"
    return bool(requested and ACADEMIC_MUTATION_IMPLEMENTED)


def _now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    return current if current.tzinfo else current.replace(tzinfo=timezone.utc)


def _b64url_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    try:
        return base64.urlsafe_b64decode((value + padding).encode("ascii"))
    except Exception as exc:  # pragma: no cover - mensagem normalizada abaixo
        raise RectificationExecutionError(
            "RECTIFICATION_DRY_RUN_TOKEN_MALFORMED",
            "O token de dry-run possui codificação inválida.",
            status_code=400,
        ) from exc


def _require_claim(payload: Mapping[str, Any], name: str) -> Any:
    value = payload.get(name)
    if value in (None, ""):
        raise RectificationExecutionError(
            "RECTIFICATION_DRY_RUN_TOKEN_CLAIM_MISSING",
            f"O token de dry-run não contém o claim obrigatório {name}.",
            status_code=400,
            detail={"claim": name},
        )
    return value


def verify_rectification_dry_run_token(
    token: str,
    *,
    tenant_id: str,
    now: datetime | None = None,
    secret: str | None = None,
) -> dict[str, Any]:
    """Valida integralmente o token HMAC stateless produzido pela F1.0."""
    if not token or token.count(".") != 1:
        raise RectificationExecutionError(
            "RECTIFICATION_DRY_RUN_TOKEN_MALFORMED",
            "Token de dry-run inválido.",
            status_code=400,
        )

    encoded_payload, encoded_signature = token.split(".", 1)
    raw = _b64url_decode(encoded_payload)
    supplied_signature = _b64url_decode(encoded_signature)
    expected_signature = hmac.new(_dry_run_secret(secret), raw, hashlib.sha256).digest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise RectificationExecutionError(
            "RECTIFICATION_DRY_RUN_TOKEN_SIGNATURE_INVALID",
            "A assinatura do dry-run é inválida ou o token foi alterado.",
            status_code=400,
        )

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise RectificationExecutionError(
            "RECTIFICATION_DRY_RUN_TOKEN_MALFORMED",
            "O payload do token de dry-run é inválido.",
            status_code=400,
        ) from exc
    if not isinstance(payload, dict):
        raise RectificationExecutionError(
            "RECTIFICATION_DRY_RUN_TOKEN_MALFORMED",
            "O payload do token de dry-run deve ser um objeto.",
            status_code=400,
        )

    required = (
        "v",
        "op",
        "tenant_id",
        "student_id",
        "source_enrollment_id",
        "source_class_id",
        "destination_class_id",
        "academic_year",
        "precondition_hash",
        "iat",
        "exp",
    )
    for claim in required:
        _require_claim(payload, claim)

    if payload["v"] != DRY_RUN_CONTRACT_VERSION:
        raise RectificationExecutionError(
            "RECTIFICATION_DRY_RUN_VERSION_UNSUPPORTED",
            "A versão do dry-run não é aceita pela F2.0.",
            detail={"received": payload["v"], "expected": DRY_RUN_CONTRACT_VERSION},
        )
    if payload["op"] != OPERATION:
        raise RectificationExecutionError(
            "RECTIFICATION_DRY_RUN_OPERATION_MISMATCH",
            "O token não pertence à operação retificacao_enturmacao.",
        )
    if str(payload["tenant_id"]) != str(tenant_id):
        raise RectificationExecutionError(
            "RECTIFICATION_DRY_RUN_TENANT_MISMATCH",
            "O dry-run pertence a outra mantenedora ou contexto operacional.",
            status_code=403,
        )

    try:
        issued_at = int(payload["iat"])
        expires_at = int(payload["exp"])
        int(payload["academic_year"])
    except (TypeError, ValueError) as exc:
        raise RectificationExecutionError(
            "RECTIFICATION_DRY_RUN_TOKEN_CLAIM_INVALID",
            "Claims temporais/ano letivo do dry-run são inválidos.",
            status_code=400,
        ) from exc

    current_ts = int(_now(now).timestamp())
    if expires_at <= current_ts:
        raise RectificationExecutionError(
            "RECTIFICATION_DRY_RUN_TOKEN_EXPIRED",
            "O dry-run expirou. Gere uma nova análise antes de continuar.",
            status_code=409,
        )
    if issued_at > current_ts + 60:
        raise RectificationExecutionError(
            "RECTIFICATION_DRY_RUN_TOKEN_IAT_INVALID",
            "O dry-run possui data de emissão futura incompatível.",
            status_code=400,
        )

    digest = str(payload["precondition_hash"])
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest.lower()):
        raise RectificationExecutionError(
            "RECTIFICATION_DRY_RUN_PRECONDITION_HASH_INVALID",
            "O hash de precondições do dry-run é inválido.",
            status_code=400,
        )
    return dict(payload)


def validate_state_transition(current: str, target: str) -> None:
    if current not in RUN_STATES or target not in RUN_STATES:
        raise RectificationExecutionError(
            "RECTIFICATION_RUN_STATE_INVALID",
            "Estado de saga inválido.",
            detail={"current": current, "target": target},
        )
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise RectificationExecutionError(
            "RECTIFICATION_RUN_TRANSITION_FORBIDDEN",
            "Transição de estado não permitida para a saga de retificação.",
            detail={"current": current, "target": target},
        )


def _validate_human_gates(*, confirmation: str, justification: str) -> str:
    if confirmation != CONFIRMATION_PHRASE:
        raise RectificationExecutionError(
            "RECTIFICATION_CONFIRMATION_MISMATCH",
            "A frase de confirmação não corresponde ao contrato da retificação.",
            status_code=422,
        )
    normalized = (justification or "").strip()
    if len(normalized) < MIN_JUSTIFICATION_LENGTH:
        raise RectificationExecutionError(
            "RECTIFICATION_JUSTIFICATION_TOO_SHORT",
            f"A justificativa deve ter ao menos {MIN_JUSTIFICATION_LENGTH} caracteres.",
            status_code=422,
        )
    return normalized


async def _reauthenticate(db, actor: Mapping[str, Any], password: str) -> None:
    actor_id = actor.get("id")
    if not actor_id or not password:
        raise RectificationExecutionError(
            "RECTIFICATION_REAUTH_REQUIRED",
            "Reautenticação por senha é obrigatória.",
            status_code=401,
        )
    user_doc = await db.users.find_one({"id": actor_id}, {"_id": 0, "password_hash": 1})
    if not user_doc or not verify_password(password, user_doc.get("password_hash", "")):
        raise RectificationExecutionError(
            "RECTIFICATION_REAUTH_FAILED",
            "Senha incorreta. A reautenticação falhou.",
            status_code=401,
        )


def _tenant_query(query: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    scoped = dict(query)
    scoped["mantenedora_id"] = tenant_id
    return scoped


def _sorted_docs(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(docs, key=_canonical_json)


async def _find_docs(db, collection: str, query: dict[str, Any], *, limit: int = 5000) -> list[dict[str, Any]]:
    docs = await db[collection].find(query, {"_id": 0}).to_list(limit)
    return _sorted_docs(docs)


async def build_compensating_snapshot(
    db,
    *,
    claims: Mapping[str, Any],
    tenant_id: str,
) -> dict[str, Any]:
    """Captura somente o universo que uma futura saga poderá alterar.

    É um snapshot de PREPARAÇÃO. F2.1 deverá refazê-lo sob o mesmo lock,
    imediatamente antes da primeira mutação acadêmica.
    """
    student_id = str(claims["student_id"])
    source_class_id = str(claims["source_class_id"])
    destination_class_id = str(claims["destination_class_id"])
    source_enrollment_id = str(claims["source_enrollment_id"])
    academic_year = int(claims["academic_year"])
    year_values = [academic_year, str(academic_year)]

    student = await db.students.find_one(
        _tenant_query({"id": student_id}, tenant_id), {"_id": 0}
    )
    enrollment = await db.enrollments.find_one(
        _tenant_query({"id": source_enrollment_id, "student_id": student_id}, tenant_id),
        {"_id": 0},
    )
    if not student or not enrollment:
        raise RectificationExecutionError(
            "RECTIFICATION_SNAPSHOT_SOURCE_MISSING",
            "A fonte canônica mudou antes do snapshot de preparação.",
        )

    enrollments = await _find_docs(
        db,
        "enrollments",
        _tenant_query(
            {"student_id": student_id, "academic_year": {"$in": year_values}}, tenant_id
        ),
    )
    attendance = await _find_docs(
        db,
        "attendance",
        _tenant_query(
            {
                "class_id": source_class_id,
                "academic_year": {"$in": year_values},
                "records.student_id": student_id,
            },
            tenant_id,
        ),
    )
    grades = await _find_docs(
        db,
        "grades",
        _tenant_query(
            {
                "student_id": student_id,
                "class_id": {"$in": [source_class_id, destination_class_id]},
                "academic_year": {"$in": year_values},
            },
            tenant_id,
        ),
    )
    history = await _find_docs(
        db,
        "student_history",
        _tenant_query(
            {"student_id": student_id, "academic_year": {"$in": year_values}}, tenant_id
        ),
    )
    existing_rectifications = await _find_docs(
        db,
        "attendance_rectifications",
        _tenant_query(
            {"student_id": student_id, "academic_year": {"$in": year_values}}, tenant_id
        ),
    )

    document_ledgers: dict[str, list[dict[str, Any]]] = {}
    for collection in (
        "school_documents_log",
        "verifiable_documents",
        "bulletin_verifications",
        "history_verifications",
        "manual_document_issuances",
    ):
        document_ledgers[collection] = await _find_docs(
            db,
            collection,
            _tenant_query({"student_id": student_id}, tenant_id),
            limit=1000,
        )

    snapshot = {
        "schema_version": EXECUTION_CONTRACT_VERSION,
        "tenant_id": tenant_id,
        "student_id": student_id,
        "academic_year": academic_year,
        "source_enrollment_id": source_enrollment_id,
        "source_class_id": source_class_id,
        "destination_class_id": destination_class_id,
        "student": student,
        "enrollments": enrollments,
        "attendance_source_docs": attendance,
        "grades_source_and_destination": grades,
        "student_history": history,
        "attendance_rectifications_existing": existing_rectifications,
        "document_ledgers": document_ledgers,
        "preserved_student_anchored": ["aee", "bolsa_familia", "atestados"],
    }
    return snapshot


def snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(snapshot).encode("utf-8")).hexdigest()


async def revalidate_rectification_preconditions(
    db,
    *,
    claims: Mapping[str, Any],
    tenant_id: str,
    actor: Mapping[str, Any],
    now: datetime | None = None,
    secret: str | None = None,
) -> dict[str, Any]:
    try:
        current = await build_rectification_dry_run(
            db,
            student_id=str(claims["student_id"]),
            destination_class_id=str(claims["destination_class_id"]),
            tenant_id=tenant_id,
            actor=dict(actor),
            now=_now(now),
            secret=secret,
        )
    except RectificationDryRunError as exc:
        raise RectificationExecutionError(
            "RECTIFICATION_PRECONDITION_CHANGED",
            "A matrícula/turma de origem mudou desde o dry-run. Gere uma nova análise.",
            status_code=exc.status_code,
            detail={
                "source_error_code": exc.code,
                "source_error_message": exc.message,
                "source_error_detail": exc.detail,
            },
        ) from exc

    explicit_contract = {
        "source_enrollment_id": current.get("enrollment", {}).get("id"),
        "source_class_id": current.get("origin_class", {}).get("id"),
        "destination_class_id": current.get("destination_class", {}).get("id"),
        "academic_year": current.get("destination_class", {}).get("academic_year"),
    }
    expected_contract = {
        "source_enrollment_id": claims.get("source_enrollment_id"),
        "source_class_id": claims.get("source_class_id"),
        "destination_class_id": claims.get("destination_class_id"),
        "academic_year": claims.get("academic_year"),
    }
    if _canonical_json(explicit_contract) != _canonical_json(expected_contract):
        raise RectificationExecutionError(
            "RECTIFICATION_PRECONDITION_CHANGED",
            "A matrícula/turma mudou desde o dry-run. Gere uma nova análise.",
            detail={"expected": expected_contract, "current": explicit_contract},
        )

    if current.get("precondition_hash") != claims.get("precondition_hash"):
        raise RectificationExecutionError(
            "RECTIFICATION_PRECONDITION_CHANGED",
            "Notas, frequência, matrícula ou documentos mudaram desde o dry-run.",
            detail={
                "expected_precondition_hash": claims.get("precondition_hash"),
                "current_precondition_hash": current.get("precondition_hash"),
            },
        )
    if not current.get("can_execute_later") or current.get("blockers"):
        raise RectificationExecutionError(
            "RECTIFICATION_BLOCKERS_PRESENT",
            "O estado atual possui bloqueios e não pode ser preparado para execução.",
            detail={"blockers": current.get("blockers") or []},
        )
    return current


def _lock_target(tenant_id: str, student_id: str) -> str:
    return f"enrollment-rectification:{tenant_id}:{student_id}"


def _prepare_id(tenant_id: str, student_id: str, idempotency_key: str) -> str:
    raw = f"{tenant_id}|{student_id}|{idempotency_key}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _prepared_payload(doc: Mapping[str, Any], *, replay: bool) -> dict[str, Any]:
    return {
        "operation": OPERATION,
        "contract_version": EXECUTION_CONTRACT_VERSION,
        "state": doc.get("state"),
        "prepare_id": doc.get("prepare_id"),
        "protocol": doc.get("protocol"),
        "student_id": doc.get("student_id"),
        "source_class_id": doc.get("source_class_id"),
        "destination_class_id": doc.get("destination_class_id"),
        "precondition_hash": doc.get("precondition_hash"),
        "snapshot_digest": doc.get("snapshot_digest"),
        "execution_enabled": False,
        "academic_mutation_performed": False,
        "idempotent_replay": replay,
        "next_gate": "F2.1 academic saga + F3 document gate",
    }


async def prepare_rectification_execution(
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
    """Prepara uma futura saga, sem executar qualquer write acadêmico."""
    claims = verify_rectification_dry_run_token(
        dry_run_token, tenant_id=tenant_id, now=now, secret=secret
    )
    normalized_justification = _validate_human_gates(
        confirmation=confirmation, justification=justification
    )
    await _reauthenticate(db, actor, password)

    key = (idempotency_key or "").strip()
    if len(key) < 8:
        raise RectificationExecutionError(
            "RECTIFICATION_IDEMPOTENCY_KEY_REQUIRED",
            "Idempotency-Key é obrigatório e deve identificar unicamente a tentativa.",
            status_code=422,
        )

    tenant = str(tenant_id)
    student_id = str(claims["student_id"])
    prepare_id = _prepare_id(tenant, student_id, key)

    existing = await db[RUNS_COLLECTION].find_one({"_id": prepare_id}, {"_id": 0})
    if existing:
        if (
            existing.get("actor", {}).get("id") != actor.get("id")
            or existing.get("precondition_hash") != claims.get("precondition_hash")
        ):
            raise RectificationExecutionError(
                "RECTIFICATION_IDEMPOTENCY_KEY_REUSED",
                "A Idempotency-Key já foi usada para outra preparação.",
            )
        return _prepared_payload(existing, replay=True)

    target = _lock_target(tenant, student_id)
    holder = f"{actor.get('id') or actor.get('email') or 'actor'}:{uuid.uuid4().hex[:10]}"
    acquired, lock_doc = await acquire_lock(db, target, holder, LOCKS_COLLECTION)
    if not acquired:
        raise RectificationExecutionError(
            "RECTIFICATION_STUDENT_LOCKED",
            "Já existe uma retificação em preparação para este estudante.",
            status_code=409,
            detail={
                "target": target,
                "expires_at": str((lock_doc or {}).get("expires_at")),
            },
        )

    try:
        # Recheck sob lock para fechar race entre idempotency lookup e preparação.
        existing = await db[RUNS_COLLECTION].find_one({"_id": prepare_id}, {"_id": 0})
        if existing:
            if (
                existing.get("actor", {}).get("id") != actor.get("id")
                or existing.get("precondition_hash") != claims.get("precondition_hash")
            ):
                raise RectificationExecutionError(
                    "RECTIFICATION_IDEMPOTENCY_KEY_REUSED",
                    "A Idempotency-Key já foi usada para outra preparação.",
                )
            return _prepared_payload(existing, replay=True)

        current = await revalidate_rectification_preconditions(
            db,
            claims=claims,
            tenant_id=tenant,
            actor=actor,
            now=now,
            secret=secret,
        )
        snapshot = await build_compensating_snapshot(db, claims=claims, tenant_id=tenant)
        digest = snapshot_digest(snapshot)
        created_at = _now(now).isoformat()
        protocol = f"RETF-PREP-{int(claims['academic_year'])}-{uuid.uuid4().hex[:12].upper()}"
        run_doc = {
            "_id": prepare_id,
            "prepare_id": prepare_id,
            "protocol": protocol,
            "operation": OPERATION,
            "contract_version": EXECUTION_CONTRACT_VERSION,
            "dry_run_version": claims.get("v"),
            "state": "PREPARED",
            "tenant_id": tenant,
            "student_id": student_id,
            "source_enrollment_id": claims.get("source_enrollment_id"),
            "source_class_id": claims.get("source_class_id"),
            "destination_class_id": claims.get("destination_class_id"),
            "academic_year": int(claims["academic_year"]),
            "precondition_hash": claims.get("precondition_hash"),
            "prepared_manifest_hash": current.get("precondition_hash"),
            "dry_run_iat": claims.get("iat"),
            "dry_run_exp": claims.get("exp"),
            "snapshot_digest": digest,
            "pre_execution_snapshot": snapshot,
            "snapshot_is_final_for_mutation": False,
            "actor": {
                "id": actor.get("id"),
                "email": actor.get("email"),
                "role": actor.get("role"),
            },
            "justification": normalized_justification,
            "idempotency_key_hash": hashlib.sha256(key.encode("utf-8")).hexdigest(),
            "academic_mutation_enabled": False,
            "academic_mutation_performed": False,
            "checkpoints": [
                {"name": "TOKEN_VERIFIED", "at": created_at},
                {"name": "REAUTHENTICATED", "at": created_at},
                {"name": "TOCTOU_REVALIDATED", "at": created_at},
                {"name": "PRE_EXECUTION_SNAPSHOT_CAPTURED", "at": created_at},
            ],
            "created_at": created_at,
            "updated_at": created_at,
        }
        await db[RUNS_COLLECTION].insert_one(run_doc)
        return _prepared_payload(run_doc, replay=False)
    finally:
        await release_lock(db, target, holder, LOCKS_COLLECTION)
