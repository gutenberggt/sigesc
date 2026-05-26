"""
[Saneamento — Sprint 1.0+1.1] Endpoints administrativos para tratar o passivo
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
  GET  /api/admin/students/dedup-runs                         → histórico
  GET  /api/admin/students/dedup-runs/{run_id}                → detalhe

Acesso: super_admin only.

[Sprint 1.1 — Hardening v2]
Toda a infraestrutura de idempotency/lock/audit foi extraída para
`/app/backend/lib/critical_mutation.py` como padrão reutilizável. Este
arquivo agora é APENAS a lógica de negócio do dedup (regra de canonical
+ inativação) + os 3 endpoints.
"""
import csv
import logging
from datetime import datetime, timezone
from io import StringIO
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth_middleware import AuthMiddleware
from lib.critical_mutation import (
    acquire_lock,
    execution_fingerprint,
    idempotent_lookup,
    idempotent_save,
    normalize_created_at,
    record_run,
    release_lock,
    with_critical_mutation,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Nomes das coleções (legacy do Sprint 1.0 — dados de prod já vivem aqui)
# ---------------------------------------------------------------------------
DEDUP_TARGET = "dedup_enrollments"
DEDUP_RUNS_COLLECTION = "dedup_runs"
DEDUP_LOCKS_COLLECTION = "dedup_locks"
DEDUP_IDEMPOTENCY_COLLECTION = "dedup_idempotency"
DEDUP_REASON = "auto-dedup-sprint1-matricula-duplicada"


class DedupRequest(BaseModel):
    dry_run: bool = True


# ---------------------------------------------------------------------------
# Re-exports para backward-compat de tests/módulos antigos.
# (Sprint 1.0/1.1 expunha esses helpers diretamente daqui.)
# ---------------------------------------------------------------------------
def _normalize_created_at(value):
    return normalize_created_at(value)


def _execution_fingerprint(target: str, mode: str, when: datetime) -> str:
    return execution_fingerprint(target, mode, when)


async def _acquire_lock(db, target: str, holder: str, ttl_seconds: int = 600):
    return await acquire_lock(
        db, target, holder, DEDUP_LOCKS_COLLECTION, ttl_seconds=ttl_seconds
    )


async def _release_lock(db, target: str, holder: str) -> None:
    await release_lock(db, target, holder, DEDUP_LOCKS_COLLECTION)


async def _idempotent_lookup(db, key: str, target: str):
    return await idempotent_lookup(db, key, target, DEDUP_IDEMPOTENCY_COLLECTION)


async def _idempotent_save(db, key: str, target: str, run_id: str, response: dict):
    await idempotent_save(
        db, key, target, run_id, response, DEDUP_IDEMPOTENCY_COLLECTION
    )


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
    return await record_run(
        db,
        runs_collection=DEDUP_RUNS_COLLECTION,
        mode=mode,
        target=target,
        summary=summary,
        diff=diff,
        actor=actor,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
    )


# ---------------------------------------------------------------------------
# Núcleo do dedup: detecção + regra de canonical
# ---------------------------------------------------------------------------
async def _find_duplicate_enrollments(db) -> List[Dict[str, Any]]:
    """Identifica todos os casos de aluno com 2+ matrículas ATIVAS."""
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

    def _ts(e):
        return normalize_created_at(e.get("created_at"))

    out = []
    for group in dup_groups:
        sid = group["_id"]
        student = students.get(sid, {})
        student_school_id = student.get("school_id")

        enrolls = await db.enrollments.find(
            {"student_id": sid, "status": "active"},
            {"_id": 0, "id": 1, "school_id": 1, "class_id": 1, "created_at": 1},
        ).to_list(None)

        preferenciais = [
            e for e in enrolls
            if e.get("school_id") == student_school_id and student_school_id
        ]
        canonical = (
            max(preferenciais, key=_ts) if preferenciais
            else (max(enrolls, key=_ts) if enrolls else None)
        )
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


async def _execute_dedup_work(db, payload: DedupRequest) -> Dict[str, Any]:
    """Núcleo de inativação. Retorna `{mode, summary, diff, payload}` no
    contrato esperado por `with_critical_mutation`. NÃO grava auditoria
    — quem grava é o wrapper.
    """
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
                    "dedup_reason": DEDUP_REASON,
                    "dedup_at": now_iso,
                    "dedup_kept_id": case["canonical_enrollment_id"],
                }},
            )
            inactivated += result.modified_count

    return {
        "mode": "dry_run" if payload.dry_run else "apply",
        "summary": {
            "affected_students": affected_students,
            "would_inactivate": would_inactivate,
            "inactivated": inactivated,
        },
        "diff": {
            "duplicates_removed": duplicates_removed,
            "kept_records": kept_records,
        },
        "payload": {
            "dry_run": payload.dry_run,
            "affected_students": affected_students,
            "would_inactivate": would_inactivate,
            "inactivated": inactivated,
            "details": details,
        },
    }


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
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
        cases = await _find_duplicate_enrollments(db)
        finished = datetime.now(timezone.utc)
        duration_ms = int((finished - started).total_seconds() * 1000)
        logger.info(f"[dedup] list done {duration_ms}ms — {len(cases)} alunos")

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
        request: Request, payload: DedupRequest, response: Response
    ):
        """Aplica o dedup. dry_run=True (default) só simula.

        [Sprint 1.1] Operação envelopada por `with_critical_mutation`:
          - `Idempotency-Key` (header opcional, TTL 24h)
          - Lock por target (TTL 10min, 409 em concorrência)
          - Trilha em `dedup_runs` com `execution_fingerprint`
          - `X-Idempotent-Replay` header em retries
        """
        current_user = await AuthMiddleware.require_roles(['super_admin'])(request)

        async def executor():
            return await _execute_dedup_work(db, payload)

        return await with_critical_mutation(
            db,
            target=DEDUP_TARGET,
            actor=current_user,
            request=request,
            response=response,
            executor=executor,
            runs_collection=DEDUP_RUNS_COLLECTION,
            locks_collection=DEDUP_LOCKS_COLLECTION,
            idempotency_collection=DEDUP_IDEMPOTENCY_COLLECTION,
        )

    @router.get("/dedup-runs")
    async def list_dedup_runs(
        request: Request,
        mode: Optional[str] = Query(None, pattern="^(dry_run|apply)$"),
        target: Optional[str] = Query(None),
        limit: int = Query(50, ge=1, le=500),
        skip: int = Query(0, ge=0),
    ):
        """Histórico de execuções gravadas em `dedup_runs`."""
        await AuthMiddleware.require_roles(['super_admin'])(request)

        q: Dict[str, Any] = {}
        if mode:
            q["mode"] = mode
        if target:
            q["target"] = target

        cursor = (
            db[DEDUP_RUNS_COLLECTION]
            .find(q, {"_id": 0})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        items = await cursor.to_list(limit)
        total = await db[DEDUP_RUNS_COLLECTION].count_documents(q)
        return {"total": total, "skip": skip, "limit": limit, "items": items}

    @router.get("/dedup-runs/{run_id}")
    async def get_dedup_run(run_id: str, request: Request):
        """Retorna um run específico (com `diff` completo)."""
        await AuthMiddleware.require_roles(['super_admin'])(request)
        doc = await db[DEDUP_RUNS_COLLECTION].find_one(
            {"run_id": run_id}, {"_id": 0}
        )
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"dedup_run não encontrado: {run_id}",
            )
        return doc

    return router
