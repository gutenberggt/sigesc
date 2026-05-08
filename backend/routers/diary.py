"""
Router do Diário Escolar (Fase 2 — Dependência de Estudos).

Endpoint canônico que devolve a lista UNIFICADA de items
(regulares + dependências) conforme `/app/docs/DIARY_API_CONTRACT.md` v1.

Princípios:
- Backend é a única fonte da verdade pedagógica.
- Frontend renderiza o que vem; nunca infere.
- Tenant scope obrigatório; verificação de acesso a turma/componente.
- Telemetria via `record_diary_load` (registrado dentro do `load_diary_items`).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from auth_middleware import AuthMiddleware
from tenant_scope import apply_tenant_filter, get_mantenedora_scope
from utils.diary_loader import load_diary_items

logger = logging.getLogger(__name__)


# Roles que podem ler o diário (cf. STUDENT_DEPENDENCY view roles + professor)
ROLES_DIARY_VIEW = {
    "super_admin", "admin", "admin_teste", "gerente", "secretario", "diretor",
    "coordenador", "apoio_pedagogico", "professor",
    "semed", "semed1", "semed2", "semed3",
}


def setup_diary_router(db):
    router = APIRouter(prefix="/diary", tags=["Diário Escolar"])

    @router.get("/class/{class_id}/course/{course_id}")
    async def get_diary_class_course(
        request: Request,
        class_id: str,
        course_id: str,
        academic_year: int,
    ):
        """Retorna lista unificada de items do diário (contrato v1).

        Resposta:
            {
              "contract_version": 1,
              "class_id": str,
              "course_id": str,
              "academic_year": int,
              "items": [<item>],
              "meta": {
                  "regular_count": int,
                  "dependency_count": int,
                  "has_dependencies": bool,
                  "dependency_ratio_pct": float,
                  "total": int,
                  "load_duration_ms": float,
              },
              "warnings": [...]   # opcional
            }
        """
        current_user = await AuthMiddleware.get_current_user(request)
        role = current_user.get("role")
        if role not in ROLES_DIARY_VIEW:
            raise HTTPException(status_code=403, detail="Sem permissão para acessar diários.")

        # Verifica existência da turma + tenant scope (defesa em camadas)
        class_filter = apply_tenant_filter({"id": class_id}, current_user, request)
        turma = await db.classes.find_one(class_filter, {"_id": 0})
        if not turma:
            raise HTTPException(status_code=404, detail="Turma não encontrada.")

        course_filter = apply_tenant_filter({"id": course_id}, current_user, request)
        course = await db.courses.find_one(course_filter, {"_id": 0, "id": 1})
        if not course:
            raise HTTPException(status_code=404, detail="Componente não encontrado.")

        tenant_id = (
            get_mantenedora_scope(current_user, request)
            or turma.get("mantenedora_id")
        )

        try:
            payload = await load_diary_items(
                db=db,
                class_id=class_id,
                course_id=course_id,
                academic_year=academic_year,
                tenant_id=tenant_id,
            )
        except Exception as e:
            logger.exception("[diary] erro ao carregar items class=%s course=%s", class_id, course_id)
            raise HTTPException(status_code=500, detail=f"Erro ao carregar diário: {e}") from e

        return payload

    return router
