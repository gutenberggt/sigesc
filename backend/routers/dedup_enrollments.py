"""
[Saneamento — Sprint 1.0] Endpoints administrativos para tratar o passivo
histórico de matrículas duplicadas detectadas pela auditoria.

REGRA DE DESAMBIGUAÇÃO (combo "i" aprovada pelo usuário):
  Para cada aluno com 2+ matrículas ATIVAS:
    1. Se houver matrícula(s) cujo `school_id` == `students.school_id`:
       → mantém a MAIS RECENTE entre essas (canonical).
    2. Caso contrário (nenhuma bate com escola atual do aluno):
       → mantém a MAIS RECENTE entre TODAS as ativas.
  As demais são marcadas como `status='inactive'` com auditoria:
    - dedup_reason: "auto-dedup-sprint1-matricula-duplicada"
    - dedup_at:     timestamp ISO UTC
    - dedup_kept_id: id da matrícula mantida (para reverter, se necessário)

ENDPOINTS:
  GET  /api/admin/students/duplicate-enrollments              → JSON (default)
  GET  /api/admin/students/duplicate-enrollments?format=csv   → CSV exportável
  POST /api/admin/students/duplicate-enrollments/dedup        → aplica (dry_run=True default)

Acesso: super_admin only. Apenas read na listagem, write apenas no dedup.
"""
import csv
import hashlib
import logging
import os
import uuid
from io import StringIO
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple
from fastapi import APIRouter, HTTPException, Request, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from auth_middleware import AuthMiddleware

logger = logging.getLogger(__name__)


class DedupRequest(BaseModel):
    dry_run: bool = True


def _normalize_created_at(value) -> datetime:
    """Normaliza `created_at` (datetime ou string) para datetime tz-aware (UTC).

    Datas tz-naive vindas de registros antigos em produção são convertidas para UTC.
    Strings ISO são parseadas; valores ausentes/inválidos retornam datetime.min UTC.
    Indispensável para evitar `TypeError: can't compare offset-naive and offset-aware datetimes`
    ao usar `max(..., key=...)` sobre matrículas mistas.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)
    return datetime.min.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# [Sprint 1.0 — governança] Trilha de auditoria de runs do dedup.
# Coleção `dedup_runs` registra cada execução (dry_run ou apply) com:
#   run_id, mode, target, summary, diff, actor, environment, timestamps.
# Indispensável antes do apply oficial — log estruturado, consultável.
# ---------------------------------------------------------------------------
_DEDUP_RUNS_COLLECTION = "dedup_runs"
_DEDUP_INDEXES_ENSURED = False


async def _ensure_dedup_runs_indexes(db) -> None:
    """Cria índices idempotentes em `dedup_runs` na primeira escrita.

    Índices:
      - created_at desc (consulta histórica recente)
      - mode (filtrar dry_run vs apply)
      - actor (filtrar por executor)
      - run_id único (evita gravação dupla acidental)
    """
    global _DEDUP_INDEXES_ENSURED
    if _DEDUP_INDEXES_ENSURED:
        return
    try:
        coll = db[_DEDUP_RUNS_COLLECTION]
        await coll.create_index("run_id", unique=True)
        await coll.create_index([("created_at", -1)])
        await coll.create_index("mode")
        await coll.create_index("actor.user_id")
        _DEDUP_INDEXES_ENSURED = True
    except Exception as e:
        logger.warning(f"[dedup_runs] falha ao criar índices (segue sem): {e}")


async def _record_dedup_run(
    db,
    *,
    mode: str,
    target: str,
    summary: Dict[str, Any],
    diff: Dict[str, Any],
    actor: Dict[str, Any],
    started_at: datetime,
    finished_at: datetime,
    duration_ms: int,
) -> str:
    """Persiste um documento em `dedup_runs` e retorna o `run_id` gerado."""
    await _ensure_dedup_runs_indexes(db)
    run_id = str(uuid.uuid4())
    doc = {
        "run_id": run_id,
        "created_at": finished_at.isoformat(),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_ms": duration_ms,
        "mode": mode,  # "dry_run" | "apply"
        "target": target,  # "dedup_enrollments"
        "summary": summary,
        "diff": diff,
        "actor": actor,
        "environment": os.environ.get("ENVIRONMENT", "unknown"),
        # [Sprint 1.1] Telemetria de agrupamento futuro — hash determinístico
        # por (target, mode, dia UTC). Não é idempotência; permite agregar runs
        # do mesmo "batch operacional" para relatórios.
        "execution_fingerprint": _execution_fingerprint(target, mode, finished_at),
    }
    try:
        await db[_DEDUP_RUNS_COLLECTION].insert_one(doc)
        logger.info(
            f"[dedup_runs] gravado run_id={run_id} mode={mode} "
            f"actor={actor.get('email')} duration_ms={duration_ms}"
        )
    except Exception as e:
        # Não derruba a operação principal — apenas loga.
        logger.error(f"[dedup_runs] falha ao gravar run_id={run_id}: {e}")
    return run_id


# ---------------------------------------------------------------------------
# [Sprint 1.1 — Hardening] Idempotency + Distributed Lock + Fingerprint
#
# Objetivo: transformar POST /dedup em operação determinística e re-executável
# com segurança. Elimina dependência de "boa vontade operacional".
#
# Camadas:
#   1. Idempotency-Key (header opcional, backward compatible) → cache 24h
#   2. Lock por target → serializa execuções concorrentes, TTL 10min
#   3. Execution fingerprint → telemetria de agrupamento (não idempotência)
# ---------------------------------------------------------------------------
_DEDUP_IDEMPOTENCY_COLLECTION = "dedup_idempotency"
_DEDUP_LOCKS_COLLECTION = "dedup_locks"

IDEMPOTENCY_TTL_HOURS = int(os.environ.get("DEDUP_IDEMPOTENCY_TTL_HOURS", "24"))
LOCK_TTL_SECONDS = int(os.environ.get("DEDUP_LOCK_TTL_SECONDS", "600"))  # 10min

_IDEMPOTENCY_INDEXES_ENSURED = False
_LOCK_INDEXES_ENSURED = False


def _execution_fingerprint(target: str, mode: str, when: datetime) -> str:
    """Hash determinístico para agrupar runs do mesmo dia/target/mode.

    Útil pra relatórios tipo "quantos applys em dedup_enrollments hoje".
    NÃO substitui idempotency_key (que protege contra retry específico).
    """
    bucket = when.astimezone(timezone.utc).strftime("%Y-%m-%d")
    raw = f"{target}|{mode}|{bucket}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


async def _ensure_idempotency_indexes(db) -> None:
    """Índice composto único (key, target) + TTL no created_at."""
    global _IDEMPOTENCY_INDEXES_ENSURED
    if _IDEMPOTENCY_INDEXES_ENSURED:
        return
    try:
        coll = db[_DEDUP_IDEMPOTENCY_COLLECTION]
        await coll.create_index(
            [("key", 1), ("target", 1)], unique=True, name="uniq_key_target"
        )
        # TTL: expira automaticamente após N horas
        await coll.create_index(
            "created_at",
            expireAfterSeconds=IDEMPOTENCY_TTL_HOURS * 3600,
            name="ttl_created_at",
        )
        _IDEMPOTENCY_INDEXES_ENSURED = True
    except Exception as e:
        logger.warning(f"[dedup_idempotency] falha ao criar índices: {e}")


async def _ensure_lock_indexes(db) -> None:
    """`_id` (= target) já é único por design. TTL em expires_at limpa stale."""
    global _LOCK_INDEXES_ENSURED
    if _LOCK_INDEXES_ENSURED:
        return
    try:
        coll = db[_DEDUP_LOCKS_COLLECTION]
        # MongoDB TTL: documento é removido quando expires_at < now
        await coll.create_index(
            "expires_at", expireAfterSeconds=0, name="ttl_expires_at"
        )
        _LOCK_INDEXES_ENSURED = True
    except Exception as e:
        logger.warning(f"[dedup_locks] falha ao criar índices: {e}")


async def _idempotent_lookup(
    db, key: str, target: str
) -> Optional[Dict[str, Any]]:
    """Retorna a resposta cacheada se existir (cache hit), senão None."""
    await _ensure_idempotency_indexes(db)
    doc = await db[_DEDUP_IDEMPOTENCY_COLLECTION].find_one(
        {"key": key, "target": target}, {"_id": 0, "response": 1, "run_id": 1}
    )
    return doc


async def _idempotent_save(
    db, key: str, target: str, run_id: str, response: Dict[str, Any]
) -> None:
    """Persiste o resultado para retry future com a mesma key."""
    await _ensure_idempotency_indexes(db)
    try:
        await db[_DEDUP_IDEMPOTENCY_COLLECTION].insert_one({
            "key": key,
            "target": target,
            "run_id": run_id,
            "response": response,
            "created_at": datetime.now(timezone.utc),
        })
    except DuplicateKeyError:
        # Race: outra request com mesma key gravou primeiro. Ignora.
        logger.info(
            f"[dedup_idempotency] race detectada em key={key} target={target} — "
            f"resposta da request concorrente prevalece"
        )
    except Exception as e:
        logger.error(f"[dedup_idempotency] falha ao salvar key={key}: {e}")


async def _acquire_lock(
    db, target: str, holder: str, ttl_seconds: int = LOCK_TTL_SECONDS
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Tenta adquirir lock por target. Atomic via MongoDB.

    Retorna (acquired, existing_lock_doc).
      - acquired=True  → caller deve executar e chamar _release_lock
      - acquired=False → existing_lock_doc traz holder + expires_at p/ resposta 409
    """
    await _ensure_lock_indexes(db)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=ttl_seconds)
    new_doc = {
        "_id": target,
        "holder": holder,
        "acquired_at": now,
        "expires_at": expires_at,
    }
    coll = db[_DEDUP_LOCKS_COLLECTION]

    # Caso 1: doc existente mas EXPIRADO (TTL ainda não rodou) → assume o lock
    result = await coll.replace_one(
        {"_id": target, "expires_at": {"$lte": now}}, new_doc
    )
    if getattr(result, "modified_count", 0) == 1:
        logger.info(
            f"[dedup_lock] assumi lock expirado de target={target} para holder={holder}"
        )
        return True, new_doc

    # Caso 2: doc não existe → insere atomicamente
    try:
        await coll.insert_one(new_doc)
        return True, new_doc
    except DuplicateKeyError:
        existing = await coll.find_one({"_id": target})
        return False, existing


async def _release_lock(db, target: str, holder: str) -> None:
    """Libera o lock APENAS se ainda for nosso (CAS por holder)."""
    try:
        await db[_DEDUP_LOCKS_COLLECTION].delete_one(
            {"_id": target, "holder": holder}
        )
    except Exception as e:
        # Não bloqueia o caller — TTL vai limpar eventualmente.
        logger.warning(f"[dedup_lock] release falhou target={target}: {e}")


async def _find_duplicate_enrollments(db) -> List[Dict[str, Any]]:
    """
    Identifica todos os casos de aluno com 2+ matrículas ATIVAS.

    Retorna lista de dicts:
      {
        "student_id": str,
        "student_name": str,
        "student_school_id": str | None,
        "student_school_name": str | None,
        "enrollments": [
            {
                "id": str,
                "school_id": str,
                "school_name": str,
                "class_id": str,
                "class_name": str,
                "created_at": str | None,
                "is_canonical": bool,
            }, ...
        ],
        "canonical_enrollment_id": str | None,
      }
    """
    # 1) Identifica student_ids com 2+ matrículas ativas
    duplicates_cursor = db.enrollments.aggregate([
        {"$match": {"status": "active"}},
        {"$group": {"_id": "$student_id", "n": {"$sum": 1},
                    "enrollment_ids": {"$push": "$id"}}},
        {"$match": {"n": {"$gt": 1}}},
    ])
    dup_groups = await duplicates_cursor.to_list(None)
    if not dup_groups:
        return []

    student_ids = [g["_id"] for g in dup_groups]

    # 2) Carrega students + schools + classes em batch
    students = {
        s["id"]: s async for s in db.students.find(
            {"id": {"$in": student_ids}},
            {"_id": 0, "id": 1, "full_name": 1, "school_id": 1},
        )
    }
    schools_cache: Dict[str, str] = {}
    classes_cache: Dict[str, str] = {}

    async def _school_name(sid):
        if not sid:
            return None
        if sid not in schools_cache:
            doc = await db.schools.find_one({"id": sid}, {"_id": 0, "name": 1})
            schools_cache[sid] = doc.get("name") if doc else None
        return schools_cache[sid]

    async def _class_name(cid):
        if not cid:
            return None
        if cid not in classes_cache:
            doc = await db.classes.find_one({"id": cid}, {"_id": 0, "name": 1})
            classes_cache[cid] = doc.get("name") if doc else None
        return classes_cache[cid]

    # 3) Para cada grupo, monta lista detalhada de matrículas e identifica canonical
    out = []
    for group in dup_groups:
        sid = group["_id"]
        student = students.get(sid, {})
        student_school_id = student.get("school_id")

        # Carrega TODAS as matrículas ativas desse aluno
        enrolls = await db.enrollments.find(
            {"student_id": sid, "status": "active"},
            {"_id": 0, "id": 1, "school_id": 1, "class_id": 1, "created_at": 1},
        ).to_list(None)

        # Regra (i) combo:
        # → preferência por matrícula cujo school_id bate com students.school_id
        # → entre as preferenciais, escolhe a mais recente (created_at)
        # → fallback: mais recente de todas
        def _ts(e):
            return _normalize_created_at(e.get("created_at"))

        preferenciais = [e for e in enrolls if e.get("school_id") == student_school_id and student_school_id]
        if preferenciais:
            canonical = max(preferenciais, key=_ts)
        else:
            canonical = max(enrolls, key=_ts) if enrolls else None
        canonical_id = canonical.get("id") if canonical else None

        enrolls_detail = []
        for e in enrolls:
            enrolls_detail.append({
                "id": e.get("id"),
                "school_id": e.get("school_id"),
                "school_name": await _school_name(e.get("school_id")),
                "class_id": e.get("class_id"),
                "class_name": await _class_name(e.get("class_id")),
                "created_at": e.get("created_at").isoformat() if isinstance(e.get("created_at"), datetime) else e.get("created_at"),
                "is_canonical": e.get("id") == canonical_id,
            })

        out.append({
            "student_id": sid,
            "student_name": student.get("full_name"),
            "student_school_id": student_school_id,
            "student_school_name": await _school_name(student_school_id),
            "enrollments": enrolls_detail,
            "canonical_enrollment_id": canonical_id,
        })

    return out


async def _execute_dedup(
    db,
    payload: "DedupRequest",
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    """Núcleo da execução do dedup. Extraído do endpoint para permitir
    envelopamento por idempotency + lock no Sprint 1.1.

    Comportamento idêntico ao Sprint 1.0:
      - varre duplicatas
      - se `payload.dry_run=False`, inativa as não-canônicas
      - grava `dedup_runs` (SEMPRE, dry_run ou apply)
      - retorna o payload completo
    """
    started = datetime.now(timezone.utc)
    logger.info(
        f"[dedup-enrollments] apply start dry_run={payload.dry_run} "
        f"at {started.isoformat()}"
    )
    cases = await _find_duplicate_enrollments(db)
    now_iso = datetime.now(timezone.utc).isoformat()

    would_inactivate = 0
    inactivated = 0
    affected_students = 0
    details = []
    duplicates_removed: List[Dict[str, Any]] = []
    kept_records: List[Dict[str, Any]] = []

    for case in cases:
        non_canonical = [e for e in case["enrollments"] if not e["is_canonical"]]
        canonical = next(
            (e for e in case["enrollments"] if e["is_canonical"]), None
        )
        non_canonical_ids = [e["id"] for e in non_canonical]
        if not non_canonical_ids:
            continue
        would_inactivate += len(non_canonical_ids)
        affected_students += 1
        details.append({
            "student_id": case["student_id"],
            "student_name": case["student_name"],
            "kept": case["canonical_enrollment_id"],
            "inactivated": non_canonical_ids,
        })
        if canonical:
            kept_records.append({
                "enrollment_id": canonical.get("id"),
                "student_id": case["student_id"],
                "school_id": canonical.get("school_id"),
                "class_id": canonical.get("class_id"),
            })
        for e in non_canonical:
            duplicates_removed.append({
                "enrollment_id": e.get("id"),
                "student_id": case["student_id"],
                "school_id": e.get("school_id"),
                "class_id": e.get("class_id"),
                "kept_id": case["canonical_enrollment_id"],
            })

        if not payload.dry_run:
            result = await db.enrollments.update_many(
                {"id": {"$in": non_canonical_ids}},
                {"$set": {
                    "status": "inactive",
                    "dedup_reason": "auto-dedup-sprint1-matricula-duplicada",
                    "dedup_at": now_iso,
                    "dedup_kept_id": case["canonical_enrollment_id"],
                }},
            )
            inactivated += result.modified_count

    finished = datetime.now(timezone.utc)
    duration_ms = int((finished - started).total_seconds() * 1000)
    logger.info(
        f"[dedup-enrollments] apply done in {duration_ms}ms — "
        f"dry_run={payload.dry_run} would_inactivate={would_inactivate} "
        f"inactivated={inactivated}"
    )

    run_id = await _record_dedup_run(
        db,
        mode="dry_run" if payload.dry_run else "apply",
        target="dedup_enrollments",
        summary={
            "affected_students": affected_students,
            "would_inactivate": would_inactivate,
            "inactivated": inactivated,
        },
        diff={
            "duplicates_removed": duplicates_removed,
            "kept_records": kept_records,
        },
        actor={
            "user_id": current_user.get("id"),
            "email": current_user.get("email"),
            "role": current_user.get("role"),
        },
        started_at=started,
        finished_at=finished,
        duration_ms=duration_ms,
    )

    return {
        "run_id": run_id,
        "dry_run": payload.dry_run,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_ms": duration_ms,
        "affected_students": affected_students,
        "would_inactivate": would_inactivate,
        "inactivated": inactivated,
        "details": details,
    }


def setup_dedup_router(db):
    router = APIRouter(prefix="/admin/students", tags=["DedupEnrollments"])

    @router.get("/duplicate-enrollments")
    async def list_duplicates(
        request: Request,
        format: str = Query("json", pattern="^(json|csv)$"),
    ):
        """Lista os casos de matrícula duplicada. JSON ou CSV."""
        await AuthMiddleware.require_roles(['super_admin'])(request)

        started = datetime.now(timezone.utc)
        logger.info(f"[dedup-enrollments] list start at {started.isoformat()}")
        cases = await _find_duplicate_enrollments(db)
        finished = datetime.now(timezone.utc)
        duration_ms = int((finished - started).total_seconds() * 1000)
        logger.info(f"[dedup-enrollments] list done in {duration_ms}ms — {len(cases)} alunos")

        if format == "csv":
            buf = StringIO()
            w = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
            w.writerow([
                "aluno", "escola_atual_aluno",
                "matricula_id", "matricula_escola", "matricula_turma",
                "matricula_created_at", "manter",
            ])
            for case in cases:
                for e in case["enrollments"]:
                    w.writerow([
                        case.get("student_name") or "",
                        case.get("student_school_name") or "",
                        e.get("id") or "",
                        e.get("school_name") or e.get("school_id") or "",
                        e.get("class_name") or e.get("class_id") or "",
                        e.get("created_at") or "",
                        "SIM" if e.get("is_canonical") else "NAO",
                    ])
            buf.seek(0)
            stamp = finished.strftime("%Y%m%d_%H%M%S")
            return StreamingResponse(
                iter([buf.getvalue()]),
                media_type="text/csv; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="duplicate-enrollments_{stamp}.csv"',
                },
            )

        return {
            "generated_at": finished.isoformat(),
            "duration_ms": duration_ms,
            "total_students_affected": len(cases),
            "total_enrollments_to_inactivate": sum(
                len([e for e in c["enrollments"] if not e["is_canonical"]]) for c in cases
            ),
            "items": cases,
        }

    @router.post("/duplicate-enrollments/dedup")
    async def apply_dedup(
        request: Request,
        payload: DedupRequest,
        response: Response,
    ):
        """Aplica o dedup. dry_run=True (default) só simula.

        Marca as matrículas NÃO canônicas como `status='inactive'` adicionando:
          - dedup_reason: "auto-dedup-sprint1-matricula-duplicada"
          - dedup_at: ISO UTC
          - dedup_kept_id: id da matrícula mantida

        Toda execução (dry_run ou apply) é gravada em `dedup_runs` para
        trilha de auditoria (run_id, summary, diff, actor, environment).

        [Sprint 1.1 — Hardening]
          - Header `Idempotency-Key` (opcional): chamadas com a MESMA key
            retornam o resultado cacheado em até {IDEMPOTENCY_TTL_HOURS}h,
            sem re-executar. Resposta cacheada carrega `X-Idempotent-Replay: true`.
          - Lock por target: execuções concorrentes recebem 409 com info do holder.
          - Sem `Idempotency-Key` → comportamento legacy preservado.
        """
        current_user = await AuthMiddleware.require_roles(['super_admin'])(request)
        target = "dedup_enrollments"
        idempotency_key = request.headers.get("Idempotency-Key")

        # [1] Idempotency cache lookup (se key presente)
        if idempotency_key:
            cached = await _idempotent_lookup(db, idempotency_key, target)
            if cached and cached.get("response"):
                response.headers["X-Idempotent-Replay"] = "true"
                logger.info(
                    f"[dedup] idempotent replay key={idempotency_key} "
                    f"run_id={cached.get('run_id')}"
                )
                return cached["response"]

        # [2] Adquire lock por target
        holder = f"{current_user.get('email','?')}:{uuid.uuid4().hex[:8]}"
        acquired, existing_lock = await _acquire_lock(db, target, holder)
        if not acquired:
            existing_holder = (existing_lock or {}).get("holder", "desconhecido")
            existing_expires = (existing_lock or {}).get("expires_at")
            expires_iso = (
                existing_expires.isoformat()
                if isinstance(existing_expires, datetime)
                else str(existing_expires)
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Operação dedup já em andamento para este target",
                    "target": target,
                    "lock_holder": existing_holder,
                    "expires_at": expires_iso,
                },
            )

        # [3] Execução protegida — try/finally garante release
        try:
            result_payload = await _execute_dedup(db, payload, current_user)
        finally:
            await _release_lock(db, target, holder)

        # [4] Persiste idempotency response (se key foi enviada)
        if idempotency_key:
            await _idempotent_save(
                db, idempotency_key, target,
                result_payload.get("run_id", ""), result_payload,
            )
            response.headers["X-Idempotent-Replay"] = "false"

        return result_payload

    @router.get("/dedup-runs")
    async def list_dedup_runs(
        request: Request,
        mode: Optional[str] = Query(None, pattern="^(dry_run|apply)$"),
        target: Optional[str] = Query(None),
        limit: int = Query(50, ge=1, le=500),
        skip: int = Query(0, ge=0),
    ):
        """Histórico de execuções do dedup gravadas em `dedup_runs`.

        Por default lista os 50 mais recentes (`created_at` desc). Filtros
        opcionais: `mode` (dry_run|apply), `target` (ex: dedup_enrollments).
        Acesso: super_admin only.
        """
        await AuthMiddleware.require_roles(['super_admin'])(request)

        q: Dict[str, Any] = {}
        if mode:
            q["mode"] = mode
        if target:
            q["target"] = target

        cursor = (
            db[_DEDUP_RUNS_COLLECTION]
            .find(q, {"_id": 0})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        items = await cursor.to_list(limit)
        total = await db[_DEDUP_RUNS_COLLECTION].count_documents(q)
        return {"total": total, "skip": skip, "limit": limit, "items": items}

    @router.get("/dedup-runs/{run_id}")
    async def get_dedup_run(run_id: str, request: Request):
        """Retorna um run específico (com `diff` completo)."""
        await AuthMiddleware.require_roles(['super_admin'])(request)
        doc = await db[_DEDUP_RUNS_COLLECTION].find_one(
            {"run_id": run_id}, {"_id": 0}
        )
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"dedup_run não encontrado: {run_id}",
            )
        return doc

    return router
