"""
[Sprint 1.1 — Extração arquitetural] Padrão reutilizável para operações
destrutivas auditáveis em produção (`@critical_mutation`).

ENCAPSULA, em uma única abstração:
  - `Idempotency-Key` (header opcional, TTL configurável — default 24h)
  - Lock distribuído por target (TTL configurável — default 10min)
  - Trilha de auditoria em `<runs_collection>` (run_id, summary, diff,
    actor, environment, execution_fingerprint)
  - Resposta 409 em concorrência detectada
  - Header `X-Idempotent-Replay: true|false` em retries

USO MÍNIMO (dentro de um endpoint FastAPI):

    from lib.critical_mutation import with_critical_mutation

    @router.post("/duplicate-enrollments/dedup")
    async def apply_dedup(request, payload, response):
        user = await AuthMiddleware.require_roles(['super_admin'])(request)

        async def executor():
            # ... fazer o trabalho destrutivo ...
            return {
                "summary": {"affected": 194, "inactivated": 195},
                "diff":    {"duplicates_removed": [...], "kept_records": [...]},
                "payload": {"dry_run": False, "details": [...]},
            }

        return await with_critical_mutation(
            db, target="dedup_enrollments", actor=user,
            request=request, response=response, executor=executor,
            runs_collection="dedup_runs",
            locks_collection="dedup_locks",
            idempotency_collection="dedup_idempotency",
        )

REGRA: o `executor` recebe nada e retorna um dict com 3 chaves:
  - `summary` (dict) — agregados a gravar em `runs.summary`
  - `diff`    (dict) — alterações estruturadas a gravar em `runs.diff`
  - `payload` (dict) — corpo da resposta HTTP final

O wrapper injeta automaticamente `run_id` no `payload` final e grava
`runs.execution_fingerprint`. O `payload` também é gravado em
`<idempotency_collection>.response` quando há `Idempotency-Key`.

DECISÃO DE DESIGN: coleções são parâmetros explícitos (não defaults
mágicos) — cada target tem nomes claros, evita colisão e permite trilhas
históricas separadas (ex.: `dedup_runs` do Sprint 1.0 continua acessível).
"""
from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from fastapi import HTTPException, Request, Response, status
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuração (via env)
# ---------------------------------------------------------------------------
IDEMPOTENCY_TTL_HOURS = int(os.environ.get("CRITICAL_MUTATION_IDEMPOTENCY_TTL_HOURS", "24"))
LOCK_TTL_SECONDS = int(os.environ.get("CRITICAL_MUTATION_LOCK_TTL_SECONDS", "600"))


# ---------------------------------------------------------------------------
# Utilitários compartilhados
# ---------------------------------------------------------------------------
def normalize_created_at(value: Any) -> datetime:
    """Normaliza um `created_at` (datetime ou string ISO) para tz-aware UTC.

    Indispensável quando uma coleção mistura registros antigos (tz-naive)
    e novos (tz-aware) — evita `TypeError: can't compare offset-naive
    and offset-aware datetimes` em comparações com `max(..., key=...)`.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)
    return datetime.min.replace(tzinfo=timezone.utc)


def execution_fingerprint(target: str, mode: str, when: datetime) -> str:
    """Hash determinístico `sha256(target + mode + UTC_day)[:16]`.

    Telemetria de agrupamento: permite agregar runs do mesmo "batch
    operacional" para relatórios (não substitui idempotency_key).
    """
    bucket = when.astimezone(timezone.utc).strftime("%Y-%m-%d")
    raw = f"{target}|{mode}|{bucket}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Estado de índices (lazy, idempotente)
# ---------------------------------------------------------------------------
_indexes_ensured: Dict[str, set] = {"runs": set(), "locks": set(), "idemp": set()}


async def ensure_runs_indexes(db, runs_collection: str) -> None:
    if runs_collection in _indexes_ensured["runs"]:
        return
    try:
        c = db[runs_collection]
        await c.create_index("run_id", unique=True)
        await c.create_index([("created_at", -1)])
        await c.create_index("mode")
        await c.create_index("target")
        await c.create_index("actor.user_id")
        await c.create_index("execution_fingerprint")
        _indexes_ensured["runs"].add(runs_collection)
    except Exception as e:
        logger.warning(f"[{runs_collection}] falha índices: {e}")


async def ensure_locks_indexes(db, locks_collection: str) -> None:
    if locks_collection in _indexes_ensured["locks"]:
        return
    try:
        # MongoDB TTL: doc é removido quando expires_at < now
        await db[locks_collection].create_index("expires_at", expireAfterSeconds=0)
        _indexes_ensured["locks"].add(locks_collection)
    except Exception as e:
        logger.warning(f"[{locks_collection}] falha índices: {e}")


async def ensure_idempotency_indexes(db, idempotency_collection: str) -> None:
    if idempotency_collection in _indexes_ensured["idemp"]:
        return
    try:
        c = db[idempotency_collection]
        await c.create_index(
            [("key", 1), ("target", 1)], unique=True, name="uniq_key_target"
        )
        await c.create_index(
            "created_at",
            expireAfterSeconds=IDEMPOTENCY_TTL_HOURS * 3600,
            name="ttl_created_at",
        )
        _indexes_ensured["idemp"].add(idempotency_collection)
    except Exception as e:
        logger.warning(f"[{idempotency_collection}] falha índices: {e}")


# ---------------------------------------------------------------------------
# Lock distribuído por target
# ---------------------------------------------------------------------------
async def acquire_lock(
    db,
    target: str,
    holder: str,
    locks_collection: str,
    ttl_seconds: int = LOCK_TTL_SECONDS,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Aquisição atômica.

    Retorna `(acquired, existing_lock_doc)`.
      - acquired=True   → caller DEVE chamar `release_lock(...)` ao final
      - acquired=False  → existing_lock_doc traz `{holder, expires_at}`
    """
    await ensure_locks_indexes(db, locks_collection)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=ttl_seconds)
    new_doc = {
        "_id": target,
        "holder": holder,
        "acquired_at": now,
        "expires_at": expires_at,
    }
    coll = db[locks_collection]

    # Caso 1: lock existente JÁ expirado (TTL ainda não rodou) → assume
    result = await coll.replace_one(
        {"_id": target, "expires_at": {"$lte": now}}, new_doc
    )
    if getattr(result, "modified_count", 0) == 1:
        logger.info(f"[lock:{target}] assumi lock expirado para holder={holder}")
        return True, new_doc

    # Caso 2: doc não existe → insere atomicamente
    try:
        await coll.insert_one(new_doc)
        return True, new_doc
    except DuplicateKeyError:
        existing = await coll.find_one({"_id": target})
        return False, existing


async def release_lock(db, target: str, holder: str, locks_collection: str) -> None:
    """CAS por holder: NÃO derruba lock de terceiros."""
    try:
        await db[locks_collection].delete_one({"_id": target, "holder": holder})
    except Exception as e:
        logger.warning(f"[lock:{target}] release falhou (TTL limpa eventualmente): {e}")


# ---------------------------------------------------------------------------
# Idempotency cache
# ---------------------------------------------------------------------------
async def idempotent_lookup(
    db, key: str, target: str, idempotency_collection: str
) -> Optional[Dict[str, Any]]:
    await ensure_idempotency_indexes(db, idempotency_collection)
    return await db[idempotency_collection].find_one(
        {"key": key, "target": target}, {"_id": 0, "response": 1, "run_id": 1}
    )


async def idempotent_save(
    db,
    key: str,
    target: str,
    run_id: str,
    response_payload: Dict[str, Any],
    idempotency_collection: str,
) -> None:
    await ensure_idempotency_indexes(db, idempotency_collection)
    try:
        await db[idempotency_collection].insert_one({
            "key": key,
            "target": target,
            "run_id": run_id,
            "response": response_payload,
            "created_at": datetime.now(timezone.utc),
        })
    except DuplicateKeyError:
        logger.info(
            f"[idemp:{target}] race em key={key} — concorrente prevaleceu"
        )
    except Exception as e:
        logger.error(f"[idemp:{target}] falha save key={key}: {e}")


# ---------------------------------------------------------------------------
# Persistência do `run` (envelope completo)
# ---------------------------------------------------------------------------
async def record_run(
    db,
    *,
    runs_collection: str,
    mode: str,
    target: str,
    summary: Dict[str, Any],
    diff: Dict[str, Any],
    actor: Dict[str, Any],
    started_at: datetime,
    finished_at: datetime,
    duration_ms: int,
) -> str:
    """Persiste o run e retorna o `run_id` gerado.

    Falhas no insert são apenas logadas — auditoria nunca derruba a
    operação principal.
    """
    await ensure_runs_indexes(db, runs_collection)
    run_id = str(uuid.uuid4())
    doc = {
        "run_id": run_id,
        "created_at": finished_at.isoformat(),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_ms": duration_ms,
        "mode": mode,
        "target": target,
        "summary": summary,
        "diff": diff,
        "actor": actor,
        "environment": os.environ.get("ENVIRONMENT", "unknown"),
        "execution_fingerprint": execution_fingerprint(target, mode, finished_at),
    }
    try:
        await db[runs_collection].insert_one(doc)
        logger.info(
            f"[{runs_collection}] gravado run_id={run_id} mode={mode} "
            f"actor={actor.get('email')} duration_ms={duration_ms}"
        )
    except Exception as e:
        logger.error(f"[{runs_collection}] falha ao gravar run_id={run_id}: {e}")
    return run_id


# ---------------------------------------------------------------------------
# Orquestrador: with_critical_mutation
# ---------------------------------------------------------------------------
ExecutorResult = Dict[str, Any]  # {"summary": {...}, "diff": {...}, "payload": {...}, "mode": "dry_run|apply"}


async def with_critical_mutation(
    db,
    *,
    target: str,
    actor: Dict[str, Any],
    request: Request,
    response: Response,
    executor: Callable[[], Awaitable[ExecutorResult]],
    runs_collection: str,
    locks_collection: str,
    idempotency_collection: str,
) -> Dict[str, Any]:
    """Envelopa idempotency + lock + audit em torno do `executor`.

    Parâmetros:
      - `executor`: corrotina sem args que retorna
        `{"mode": "...", "summary": {...}, "diff": {...}, "payload": {...}}`
      - `runs_collection`, `locks_collection`, `idempotency_collection`:
        nomes explícitos das 3 coleções (sem defaults — clareza > magia).

    Retorna o `payload` (com `run_id`, `started_at`, `finished_at`,
    `duration_ms` injetados automaticamente).

    Lança:
      - `HTTPException(409)` se concorrente detectado
    """
    idempotency_key = request.headers.get("Idempotency-Key")

    # [1] Idempotency cache lookup
    if idempotency_key:
        cached = await idempotent_lookup(
            db, idempotency_key, target, idempotency_collection
        )
        if cached and cached.get("response"):
            response.headers["X-Idempotent-Replay"] = "true"
            logger.info(
                f"[critical_mutation:{target}] idempotent replay "
                f"key={idempotency_key} run_id={cached.get('run_id')}"
            )
            return cached["response"]

    # [2] Adquire lock por target
    holder = f"{actor.get('email','?')}:{uuid.uuid4().hex[:8]}"
    acquired, existing = await acquire_lock(
        db, target, holder, locks_collection
    )
    if not acquired:
        existing_holder = (existing or {}).get("holder", "desconhecido")
        existing_expires = (existing or {}).get("expires_at")
        expires_iso = (
            existing_expires.isoformat()
            if isinstance(existing_expires, datetime)
            else str(existing_expires)
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Operação já em andamento para este target",
                "target": target,
                "lock_holder": existing_holder,
                "expires_at": expires_iso,
            },
        )

    # [3] Execução protegida — try/finally garante release
    started = datetime.now(timezone.utc)
    try:
        result = await executor()
    finally:
        await release_lock(db, target, holder, locks_collection)
    finished = datetime.now(timezone.utc)
    duration_ms = int((finished - started).total_seconds() * 1000)

    # Contrato do executor
    mode = result.get("mode") or "apply"
    summary = result.get("summary") or {}
    diff = result.get("diff") or {}
    payload = dict(result.get("payload") or {})

    # [4] Grava run em auditoria
    run_id = await record_run(
        db,
        runs_collection=runs_collection,
        mode=mode,
        target=target,
        summary=summary,
        diff=diff,
        actor={
            "user_id": actor.get("id"),
            "email": actor.get("email"),
            "role": actor.get("role"),
        },
        started_at=started,
        finished_at=finished,
        duration_ms=duration_ms,
    )

    # [5] Enriquece payload final
    payload.setdefault("run_id", run_id)
    payload.setdefault("started_at", started.isoformat())
    payload.setdefault("finished_at", finished.isoformat())
    payload.setdefault("duration_ms", duration_ms)

    # [6] Salva idempotency response (se key foi enviada)
    if idempotency_key:
        await idempotent_save(
            db, idempotency_key, target, run_id, payload, idempotency_collection
        )
        response.headers["X-Idempotent-Replay"] = "false"

    return payload
