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
import logging
from io import StringIO
from datetime import datetime, timezone
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Request, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth_middleware import AuthMiddleware

logger = logging.getLogger(__name__)


class DedupRequest(BaseModel):
    dry_run: bool = True


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
            ts = e.get("created_at")
            if isinstance(ts, datetime):
                return ts
            if isinstance(ts, str):
                try:
                    return datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    return datetime.min.replace(tzinfo=timezone.utc)
            return datetime.min.replace(tzinfo=timezone.utc)

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
    async def apply_dedup(request: Request, payload: DedupRequest):
        """Aplica o dedup. dry_run=True (default) só simula.

        Marca as matrículas NÃO canônicas como `status='inactive'` adicionando:
          - dedup_reason: "auto-dedup-sprint1-matricula-duplicada"
          - dedup_at: ISO UTC
          - dedup_kept_id: id da matrícula mantida
        """
        await AuthMiddleware.require_roles(['super_admin'])(request)

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

        for case in cases:
            non_canonical_ids = [
                e["id"] for e in case["enrollments"] if not e["is_canonical"]
            ]
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

        return {
            "dry_run": payload.dry_run,
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "duration_ms": duration_ms,
            "affected_students": affected_students,
            "would_inactivate": would_inactivate,
            "inactivated": inactivated,
            "details": details,
        }

    return router
