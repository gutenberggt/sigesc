"""
[Fase 2 — Fev/2026] Endpoints da migração definitiva da Grade Horária
`class_schedules` (legacy) → `teacher_class_assignments` (modelo novo).

Envelopado por `with_critical_mutation` (lock + idempotência + auditoria).
Toda a lógica vive em `services.grade_legacy_migration_service`.

ENDPOINTS (role: super_admin):
  GET  /api/admin/grade/legacy-migration/preview
  POST /api/admin/grade/legacy-migration/apply
  GET  /api/admin/grade/legacy-migration/runs[/{run_id}]
  POST /api/admin/grade/legacy-migration/runs/{run_id}/rollback
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel

from auth_middleware import AuthMiddleware
from lib.critical_mutation import with_critical_mutation
from services.grade_legacy_migration_service import (
    UnexpectedDeterministicDuplicate,
    build_migration_diagnostic,
    execute_migration,
    execute_rollback,
)

logger = logging.getLogger(__name__)

TARGET = "grade_legacy_migration"
RUNS_COLLECTION = "grade_legacy_migration_runs"
LOCKS_COLLECTION = "grade_legacy_migration_locks"
IDEMPOTENCY_COLLECTION = "grade_legacy_migration_idempotency"


class MigrationApplyRequest(BaseModel):
    dry_run: bool = True
    academic_year: Optional[int] = None
    school_id: Optional[str] = None
    class_id: Optional[str] = None

    def scope(self) -> Dict[str, Any]:
        return {
            "academic_year": self.academic_year,
            "school_id": self.school_id,
            "class_id": self.class_id,
        }


def setup_grade_legacy_migration_router(db):
    router = APIRouter(prefix="/admin/grade", tags=["GradeLegacyMigration"])

    @router.get("/legacy-migration/preview")
    async def preview(
        request: Request,
        academic_year: Optional[int] = Query(None),
        school_id: Optional[str] = Query(None),
        class_id: Optional[str] = Query(None),
    ):
        """Plano de migração READ-ONLY. Retorna turmas afetadas, assignments
        a criar, breakdown por escola, turmas ignoradas (já têm modelo novo)
        e amostra de 5 documentos sintetizados. Não altera nada."""
        await AuthMiddleware.require_roles(['super_admin'])(request)
        scope = {"academic_year": academic_year, "school_id": school_id, "class_id": class_id}
        diag = await build_migration_diagnostic(db, scope)
        diag.pop("_candidates", None)
        diag.pop("_affected_class_ids", None)
        diag["generated_at"] = datetime.now(timezone.utc).isoformat()
        return diag

    @router.post("/legacy-migration/apply")
    async def apply(
        request: Request, payload: MigrationApplyRequest, response: Response
    ):
        """Aplica a migração. dry_run=True (default) só simula.

        Rollout faseado: passe `school_id` (e opcionalmente `class_id`) para
        migrar 1 escola piloto antes da rede toda.

        FALHA (422) se detectar duplicidade determinística inesperada.
        """
        current_user = await AuthMiddleware.require_roles(['super_admin'])(request)

        async def executor(run_id: str):
            return await execute_migration(db, payload.scope(), payload.dry_run, run_id)

        try:
            return await with_critical_mutation(
                db,
                target=TARGET,
                actor=current_user,
                request=request,
                response=response,
                executor=executor,
                runs_collection=RUNS_COLLECTION,
                locks_collection=LOCKS_COLLECTION,
                idempotency_collection=IDEMPOTENCY_COLLECTION,
            )
        except UnexpectedDeterministicDuplicate as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "UNEXPECTED_DETERMINISTIC_DUPLICATE", "message": str(e)},
            )

    @router.get("/legacy-migration/runs")
    async def list_runs(
        request: Request,
        mode: Optional[str] = Query(None, pattern="^(dry_run|apply|rollback)$"),
        limit: int = Query(50, ge=1, le=500),
        skip: int = Query(0, ge=0),
    ):
        await AuthMiddleware.require_roles(['super_admin'])(request)
        q: Dict[str, Any] = {}
        if mode:
            q["mode"] = mode
        cursor = (
            db[RUNS_COLLECTION].find(q, {"_id": 0})
            .sort("created_at", -1).skip(skip).limit(limit)
        )
        items = await cursor.to_list(limit)
        total = await db[RUNS_COLLECTION].count_documents(q)
        return {"total": total, "skip": skip, "limit": limit, "items": items}

    @router.get("/legacy-migration/runs/{run_id}")
    async def get_run(run_id: str, request: Request):
        await AuthMiddleware.require_roles(['super_admin'])(request)
        doc = await db[RUNS_COLLECTION].find_one({"run_id": run_id}, {"_id": 0})
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"run não encontrado: {run_id}",
            )
        return doc

    @router.post("/legacy-migration/runs/{run_id}/rollback")
    async def rollback_run(run_id: str, request: Request, response: Response):
        """Reverte um apply apagando APENAS os docs criados por ele (CAS
        rigoroso). Cria novo run mode='rollback' com relatório final."""
        current_user = await AuthMiddleware.require_roles(['super_admin'])(request)

        original = await db[RUNS_COLLECTION].find_one({"run_id": run_id}, {"_id": 0})
        if not original:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"run não encontrado: {run_id}",
            )
        if original.get("mode") != "apply":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Só é possível reverter runs com mode='apply' (esse é '{original.get('mode')}')",
            )
        already = (original.get("diff") or {}).get("rollback", {}).get("reversed_by_run_id")
        if already:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": "Run já foi revertido", "reversed_by_run_id": already},
            )

        async def executor(rollback_run_id: str):
            return await execute_rollback(db, original, rollback_run_id, RUNS_COLLECTION)

        return await with_critical_mutation(
            db,
            target=TARGET,
            actor=current_user,
            request=request,
            response=response,
            executor=executor,
            runs_collection=RUNS_COLLECTION,
            locks_collection=LOCKS_COLLECTION,
            idempotency_collection=IDEMPOTENCY_COLLECTION,
        )

    return router
