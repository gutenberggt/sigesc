"""
Router de Dependência de Estudos — SIGESC

Implementação Fase 1 (Fev/2026). Ver /app/docs/STUDENT_DEPENDENCY.md.

Princípios arquiteturais:
- Entidade própria (NÃO matrícula simplificada).
- Mutuamente exclusivo via Student.dependency_mode (enum).
- Limite de componentes lendo da mantenedora.
- Duplicidade impedida: (student_id, course_id, origin_academic_year, status=active).
- Auditoria completa (create / update / status change).
- Imutabilidade de existência: vínculo criado NUNCA é apagado fisicamente pela aplicação.
- DELETE HTTP preservado por compatibilidade e convertido em cancelamento lógico auditável.
- Tenant scope obrigatório.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request, status

from models import StudentDependency, StudentDependencyCreate, StudentDependencyUpdate

logger = logging.getLogger(__name__)

# Papéis com poder de gerenciar (criar/editar/cancelar)
DEPENDENCY_MANAGE_ROLES = {
    "super_admin", "admin", "admin_teste", "gerente", "secretario", "diretor",
}
# Papéis que podem visualizar
DEPENDENCY_VIEW_ROLES = DEPENDENCY_MANAGE_ROLES | {"coordenador", "apoio_pedagogico", "professor", "semed", "semed1", "semed2", "semed3"}
TERMINAL_DEPENDENCY_STATUSES = {"completed", "failed", "cancelled"}


def setup_student_dependencies_router(db, auth_middleware, audit_service=None, apply_tenant_filter=None):
    """Configura o router de dependências de estudos.

    apply_tenant_filter: função(filter_dict, current_user, request) → injeta scope.
    """
    router = APIRouter(prefix="/student-dependencies", tags=["Dependência de Estudos"])

    # ------------------------------------------------------------------
    async def _require_role(request: Request, allowed: set) -> dict:
        user = await auth_middleware.get_current_user(request)
        role = user.get("role")
        if role not in allowed:
            raise HTTPException(403, detail="Sem permissão para esta operação.")
        return user

    async def _scoped(filter_dict: dict, user: dict, request: Request) -> dict:
        if apply_tenant_filter is not None:
            return apply_tenant_filter(filter_dict, user, request)
        # Fallback minimalista
        if user.get("mantenedora_id"):
            filter_dict["mantenedora_id"] = user["mantenedora_id"]
        return filter_dict

    async def _get_mantenedora_config(
        mantenedora_id: Optional[str], request: Optional[Request] = None
    ) -> dict:
        """Resolve a config da mantenedora — delega para `tenant_scope`.

        Mantemos a assinatura por compatibilidade; a resolução de fato vive
        em `resolve_active_mantenedora` (fonte única do projeto).
        """
        from tenant_scope import resolve_active_mantenedora
        user = None
        if request is not None:
            try:
                user = await auth_middleware.get_current_user(request)
            except Exception:
                user = None
        # Se não há user (chamada interna), monta um stub mínimo com a mant_id
        if user is None:
            user = {"mantenedora_id": mantenedora_id}
        doc = await resolve_active_mantenedora(db, user, request, fallback_to_first=True)
        return doc or {}

    async def _validate_dependency_limit(
        student_id: str,
        mantenedora_id: Optional[str],
        request: Optional[Request] = None,
    ) -> None:
        """Valida estado acadêmico, modalidade e limite de componentes."""
        student = await db.students.find_one(
            {"id": student_id},
            {"_id": 0, "id": 1, "dependency_mode": 1, "status": 1},
        )
        if not student:
            raise HTTPException(404, detail="Estudante não encontrado.")

        # Hardening Set/2026: não cria vínculo acadêmico para estudante fora do
        # estado ativo. Campo ausente é tratado como active apenas por
        # compatibilidade com documentos legados anteriores à normalização.
        student_status = student.get("status") or "active"
        if str(student_status).lower() not in {"active", "ativo"}:
            raise HTTPException(
                409,
                detail={
                    "code": "DEPENDENCY_REQUIRES_ACTIVE_STUDENT",
                    "message": "Dependência de Estudos só pode ser vinculada a estudante ativo.",
                    "student_status": student_status,
                },
            )

        mode = student.get("dependency_mode") or "none"
        if mode == "none":
            raise HTTPException(
                400,
                detail="Estudante não possui modalidade de dependência configurada. Defina 'Com dependência' ou 'Apenas dependência' no cadastro do estudante antes de vincular componentes."
            )
        config = await _get_mantenedora_config(mantenedora_id, request)
        if mode == "with_dependency":
            if not config.get("aprovacao_com_dependencia"):
                raise HTTPException(400, detail="Mantenedora não permite aprovação com dependência.")
            limit = config.get("max_componentes_dependencia") or 0
        else:  # dependency_only
            if not config.get("cursar_apenas_dependencia"):
                raise HTTPException(400, detail="Mantenedora não permite cursar apenas dependência.")
            limit = config.get("qtd_componentes_apenas_dependencia") or 0
        if not limit or limit <= 0:
            raise HTTPException(
                400,
                detail="Mantenedora não definiu o limite de componentes em dependência."
            )
        active_count = await db.student_dependencies.count_documents({
            "student_id": student_id,
            "status": "active",
        })
        if active_count >= limit:
            raise HTTPException(
                400,
                detail=f"O aluno excede o limite de componentes em dependência permitido pela mantenedora ({limit})."
            )

    async def _check_duplicate(student_id: str, course_id: str, origin_year: int) -> None:
        """Impede duplicidade: mesmo aluno × componente × ano de origem ativo."""
        existing = await db.student_dependencies.find_one({
            "student_id": student_id,
            "course_id": course_id,
            "origin_academic_year": origin_year,
            "status": "active",
        })
        if existing:
            raise HTTPException(
                400,
                detail=f"Já existe dependência ativa deste componente para o ano de origem {origin_year}."
            )

    async def _audit(action: str, dep_id: str, user: dict, request: Request, before: Optional[dict] = None, after: Optional[dict] = None):
        if audit_service is None:
            return
        try:
            await audit_service.log(
                action=action, collection="student_dependencies",
                user=user, request=request,
                document_id=dep_id,
                old_value=before, new_value=after,
                description=f"Dependência {dep_id} {action}",
            )
        except Exception as e:
            # AuditService permanece best-effort, mas a entidade acadêmica não é
            # mais removida fisicamente. Uma falha aqui não pode causar perda do vínculo.
            logger.warning("[student_dependencies] audit log falhou: %s", e)

    async def _ensure_completion_snapshot(
        dependency_doc: dict,
        *,
        new_status: str,
        status_reason: Optional[str],
        user_id: Optional[str],
        completion_academic_year: Optional[int] = None,
    ) -> None:
        """Garante snapshot idempotente para todo estado terminal.

        A transição pode já ter sido persistida quando o snapshot falha. Nesse
        caso o vínculo continua existindo, a API retorna erro visível e uma
        repetição da operação tenta o snapshot novamente. Nunca há perda do SSoT.
        """
        if new_status not in TERMINAL_DEPENDENCY_STATUSES:
            return
        try:
            from routers.dependency_completions import create_completion_snapshot_on_transition
            await create_completion_snapshot_on_transition(
                db,
                dependency_doc=dependency_doc,
                new_status=new_status,
                status_reason=status_reason,
                issued_by_user_id=user_id or "system",
                completion_academic_year=completion_academic_year
                    or datetime.now(timezone.utc).year,
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception(
                "[student_dependencies] vínculo preservado, mas snapshot terminal falhou dep=%s",
                dependency_doc.get("id"),
            )
            raise HTTPException(
                500,
                detail={
                    "code": "DEPENDENCY_PRESERVED_SNAPSHOT_PENDING",
                    "message": "O vínculo foi preservado, mas o snapshot documental não pôde ser concluído. Reexecute a operação; nenhuma exclusão física ocorreu.",
                },
            ) from exc

    # ==================================================================
    # CREATE
    # ==================================================================
    @router.post("", response_model=dict)
    async def create_dependency(request: Request, payload: StudentDependencyCreate):
        user = await _require_role(request, DEPENDENCY_MANAGE_ROLES)
        mantenedora_id = user.get("mantenedora_id")

        # Validações
        await _validate_dependency_limit(payload.student_id, mantenedora_id, request)
        await _check_duplicate(payload.student_id, payload.course_id, payload.origin_academic_year)

        # Constrói registro
        dep = StudentDependency(
            **payload.model_dump(),
            mantenedora_id=mantenedora_id,
            created_by=user.get("id"),
        )
        doc = dep.model_dump()
        doc["created_at"] = doc["created_at"].isoformat()
        await db.student_dependencies.insert_one(doc)

        await _audit("create", dep.id, user, request, after=doc)
        logger.info("[student_dependencies] criada %s para aluno %s", dep.id, payload.student_id)

        return {"message": "Dependência vinculada com sucesso.", "id": dep.id}

    # ==================================================================
    # LIST por aluno
    # ==================================================================
    @router.get("/student/{student_id}", response_model=List[dict])
    async def list_by_student(request: Request, student_id: str):
        user = await _require_role(request, DEPENDENCY_VIEW_ROLES)
        flt = await _scoped({"student_id": student_id}, user, request)
        deps = await db.student_dependencies.find(flt, {"_id": 0}).sort("created_at", -1).to_list(100)

        # Enriquece com nomes de turma/componente para exibição
        class_ids = list({d.get("class_id") for d in deps if d.get("class_id")})
        course_ids = list({d.get("course_id") for d in deps if d.get("course_id")})
        classes_map: dict = {}
        courses_map: dict = {}
        if class_ids:
            classes = await db.classes.find(
                {"id": {"$in": class_ids}}, {"_id": 0, "id": 1, "name": 1, "series": 1}
            ).to_list(len(class_ids))
            classes_map = {c["id"]: c for c in classes}
        if course_ids:
            courses = await db.courses.find(
                {"id": {"$in": course_ids}}, {"_id": 0, "id": 1, "name": 1, "carga_horaria": 1}
            ).to_list(len(course_ids))
            courses_map = {c["id"]: c for c in courses}

        for d in deps:
            cls = classes_map.get(d.get("class_id"), {})
            crs = courses_map.get(d.get("course_id"), {})
            d["class_name"] = cls.get("name", "")
            d["class_series"] = cls.get("series", "")
            d["course_name"] = crs.get("name", "")
            d["course_carga_horaria"] = crs.get("carga_horaria")
        return deps

    # ==================================================================
    # LIST por turma (para diário)
    # ==================================================================
    @router.get("/class/{class_id}/course/{course_id}", response_model=List[dict])
    async def list_by_class_course(request: Request, class_id: str, course_id: str):
        """Lista alunos em dependência ativa nesta turma+componente."""
        user = await _require_role(request, DEPENDENCY_VIEW_ROLES)
        flt = await _scoped({
            "class_id": class_id, "course_id": course_id, "status": "active"
        }, user, request)
        return await db.student_dependencies.find(flt, {"_id": 0}).to_list(200)

    # ==================================================================
    # UPDATE
    # ==================================================================
    @router.put("/{dep_id}", response_model=dict)
    async def update_dependency(request: Request, dep_id: str, payload: StudentDependencyUpdate):
        user = await _require_role(request, DEPENDENCY_MANAGE_ROLES)
        flt = await _scoped({"id": dep_id}, user, request)
        existing = await db.student_dependencies.find_one(flt, {"_id": 0})
        if not existing:
            raise HTTPException(404, detail="Dependência não encontrada.")

        update_data = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
        if not update_data:
            return {"message": "Nada para atualizar."}

        new_status = update_data.get("status")
        effective_reason = update_data.get("status_reason") or existing.get("status_reason")
        if new_status == "cancelled" and (not effective_reason or not str(effective_reason).strip()):
            raise HTTPException(
                422,
                detail={
                    "code": "CANCELLATION_REASON_REQUIRED",
                    "message": "Cancelamento exige status_reason não vazio.",
                },
            )

        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        update_data["updated_by"] = user.get("id")
        await db.student_dependencies.update_one(flt, {"$set": update_data})

        # Todo estado terminal deve possuir snapshot. A chamada é idempotente e
        # também roda em repetição do mesmo estado para reparar falha anterior.
        snapshot_error = None
        if new_status in TERMINAL_DEPENDENCY_STATUSES:
            try:
                merged = {**existing, **update_data}
                await _ensure_completion_snapshot(
                    merged,
                    new_status=new_status,
                    status_reason=effective_reason,
                    user_id=user.get("id"),
                    completion_academic_year=update_data.get("completed_in_academic_year")
                        or existing.get("completed_in_academic_year"),
                )
            except HTTPException as exc:
                snapshot_error = exc

        await _audit("update", dep_id, user, request, before=existing, after=update_data)
        if snapshot_error is not None:
            raise snapshot_error
        return {"message": "Dependência atualizada com sucesso."}

    # ==================================================================
    # DELETE HTTP = CANCELAMENTO LÓGICO (NUNCA physical delete)
    # ==================================================================
    @router.delete("/{dep_id}", response_model=dict)
    async def delete_dependency(request: Request, dep_id: str):
        """Compatibilidade HTTP: preserva para sempre a entidade acadêmica.

        O verbo DELETE deixa de significar remoção física. Para vínculo ativo,
        realiza transição idempotente para `cancelled`, registra motivo/ator/data
        e exige snapshot documental. Estados terminais são preservados e apenas
        têm o snapshot idempotente confirmado.
        """
        user = await _require_role(request, DEPENDENCY_MANAGE_ROLES)
        flt = await _scoped({"id": dep_id}, user, request)
        existing = await db.student_dependencies.find_one(flt, {"_id": 0})
        if not existing:
            raise HTTPException(404, detail="Dependência não encontrada.")

        current_status = existing.get("status") or "active"
        if current_status in TERMINAL_DEPENDENCY_STATUSES:
            # Repetição segura: confirma/repara snapshot sem alterar o vínculo.
            await _ensure_completion_snapshot(
                existing,
                new_status=current_status,
                status_reason=existing.get("status_reason"),
                user_id=user.get("id"),
                completion_academic_year=existing.get("completed_in_academic_year"),
            )
            return {
                "message": "Dependência preservada em estado terminal; nenhuma exclusão física foi realizada.",
                "status": current_status,
                "physically_deleted": False,
            }

        now = datetime.now(timezone.utc).isoformat()
        actor = user.get("email") or user.get("id") or "usuário"
        reason = f"[logical-delete] cancelada via DELETE por {actor}"
        transition = {
            "status": "cancelled",
            "status_reason": reason,
            "updated_at": now,
            "updated_by": user.get("id"),
        }
        transition_filter = {**flt, "status": current_status}
        result = await db.student_dependencies.update_one(
            transition_filter,
            {"$set": transition},
        )
        modified = getattr(result, "modified_count", 1)
        if modified == 0:
            # Concorrência: recarrega e nunca tenta remover fisicamente.
            latest = await db.student_dependencies.find_one(flt, {"_id": 0})
            if not latest:
                raise HTTPException(
                    409,
                    detail={
                        "code": "DEPENDENCY_INTEGRITY_CONCURRENT_DISAPPEARANCE",
                        "message": "O vínculo deixou de estar disponível durante a operação. Nenhuma exclusão foi executada por esta rota.",
                    },
                )
            existing = latest
            current_status = latest.get("status") or current_status
            if current_status not in TERMINAL_DEPENDENCY_STATUSES:
                raise HTTPException(409, detail="Dependência foi alterada concorrentemente; recarregue e tente novamente.")
            transition = {}

        merged = {**existing, **transition}
        snapshot_error = None
        try:
            await _ensure_completion_snapshot(
                merged,
                new_status=merged.get("status") or "cancelled",
                status_reason=merged.get("status_reason"),
                user_id=user.get("id"),
                completion_academic_year=merged.get("completed_in_academic_year"),
            )
        except HTTPException as exc:
            snapshot_error = exc

        await _audit(
            "update",
            dep_id,
            user,
            request,
            before=existing,
            after=transition or {"status": current_status, "logical_delete_retry": True},
        )
        logger.info(
            "[student_dependencies] cancelamento lógico %s por %s; physical_delete=false",
            dep_id,
            user.get("email"),
        )
        if snapshot_error is not None:
            raise snapshot_error
        return {
            "message": "Dependência cancelada e preservada no histórico.",
            "status": merged.get("status"),
            "physically_deleted": False,
        }

    # ==================================================================
    # SUMMARY (card resumido na tela do aluno)
    # ==================================================================
    @router.get("/student/{student_id}/summary", response_model=dict)
    async def student_summary(request: Request, student_id: str):
        """Resumo: contagem de ativas, concluídas, falhadas + limite e modo."""
        user = await _require_role(request, DEPENDENCY_VIEW_ROLES)
        student = await db.students.find_one(
            {"id": student_id},
            {"_id": 0, "id": 1, "dependency_mode": 1},
        )
        if not student:
            raise HTTPException(404, detail="Estudante não encontrado.")
        mode = student.get("dependency_mode") or "none"
        config = await _get_mantenedora_config(user.get("mantenedora_id"), request)
        limit = None
        if mode == "with_dependency":
            limit = config.get("max_componentes_dependencia")
        elif mode == "dependency_only":
            limit = config.get("qtd_componentes_apenas_dependencia")
        flt = await _scoped({"student_id": student_id}, user, request)
        all_deps = await db.student_dependencies.find(flt, {"_id": 0, "status": 1}).to_list(200)
        return {
            "dependency_mode": mode,
            "limit": limit,
            "active": sum(1 for d in all_deps if d.get("status") == "active"),
            "completed": sum(1 for d in all_deps if d.get("status") == "completed"),
            "failed": sum(1 for d in all_deps if d.get("status") == "failed"),
            "cancelled": sum(1 for d in all_deps if d.get("status") == "cancelled"),
            "total": len(all_deps),
        }

    return router
