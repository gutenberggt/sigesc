"""
Router de Responsáveis - SIGESC
Endpoints para gestão de responsáveis dos alunos.
"""

from fastapi import APIRouter, HTTPException, status, Request
from typing import List

from models import Guardian, GuardianCreate, GuardianUpdate
from auth_middleware import AuthMiddleware
from utils.guardian_links import normalize_guardian_student_links

router = APIRouter(prefix="/guardians", tags=["Responsáveis"])


def setup_router(db, audit_service):
    """Configura o router com as dependências necessárias"""

    async def ensure_primary_guardian_available(primary_student_ids, guardian_id=None):
        """Impede dois responsáveis principais para o mesmo estudante."""
        for student_id in primary_student_ids:
            query = {"primary_student_ids": student_id}
            if guardian_id:
                query["id"] = {"$ne": guardian_id}
            existing = await db.guardians.find_one(
                query, {"_id": 0, "id": 1, "full_name": 1}
            )
            if existing:
                student = await db.students.find_one(
                    {"id": student_id}, {"_id": 0, "full_name": 1}
                )
                student_name = student.get("full_name") if student else student_id
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"O estudante {student_name} já possui responsável legal principal: "
                        f"{existing.get('full_name', 'responsável já cadastrado')}. "
                        "Revise o vínculo anterior antes de definir outro responsável principal."
                    ),
                )

    @router.post("", response_model=Guardian, status_code=status.HTTP_201_CREATED)
    async def create_guardian(guardian_data: GuardianCreate, request: Request):
        """Cria novo responsável"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)

        # [Mai/2026] CAPS lock automático removido — preserva capitalização do usuário.
        guardian_dict = guardian_data.model_dump()
        try:
            linked, primary = normalize_guardian_student_links(
                guardian_dict.get("student_ids"),
                guardian_dict.get("primary_student_ids"),
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

        guardian_dict["student_ids"] = linked
        guardian_dict["primary_student_ids"] = primary
        await ensure_primary_guardian_available(primary)

        guardian_obj = Guardian(**guardian_dict)
        doc = guardian_obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()

        await db.guardians.insert_one(doc)

        return guardian_obj

    @router.get("", response_model=List[Guardian])
    async def list_guardians(request: Request, skip: int = 0, limit: int = 100):
        """Lista responsáveis"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'semed', 'semed1', 'semed2', 'semed3'])(request)

        guardians = await db.guardians.find({}, {"_id": 0}).skip(skip).limit(limit).to_list(limit)

        return guardians

    @router.get("/{guardian_id}", response_model=Guardian)
    async def get_guardian(guardian_id: str, request: Request):
        """Busca responsável por ID"""
        current_user = await AuthMiddleware.get_current_user(request)

        guardian_doc = await db.guardians.find_one({"id": guardian_id}, {"_id": 0})

        if not guardian_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Responsável não encontrado"
            )

        return Guardian(**guardian_doc)

    @router.put("/{guardian_id}", response_model=Guardian)
    async def update_guardian(guardian_id: str, guardian_update: GuardianUpdate, request: Request):
        """Atualiza responsável"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)

        existing_guardian = await db.guardians.find_one({"id": guardian_id}, {"_id": 0})
        if not existing_guardian:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Responsável não encontrado"
            )

        update_data = guardian_update.model_dump(exclude_unset=True)
        # [Mai/2026] CAPS lock automático removido — preserva capitalização do usuário.

        if 'full_name' in update_data and not str(update_data.get('full_name') or '').strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="O nome do responsável não pode ficar vazio."
            )

        if 'student_ids' in update_data or 'primary_student_ids' in update_data:
            try:
                linked, primary = normalize_guardian_student_links(
                    update_data.get("student_ids", existing_guardian.get("student_ids", [])),
                    update_data.get(
                        "primary_student_ids",
                        existing_guardian.get("primary_student_ids", []),
                    ),
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=str(exc),
                ) from exc

            update_data["student_ids"] = linked
            update_data["primary_student_ids"] = primary
            await ensure_primary_guardian_available(primary, guardian_id=guardian_id)

        if update_data:
            await db.guardians.update_one(
                {"id": guardian_id},
                {"$set": update_data}
            )

        updated_guardian = await db.guardians.find_one({"id": guardian_id}, {"_id": 0})
        return Guardian(**updated_guardian)

    @router.delete("/{guardian_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_guardian(guardian_id: str, request: Request):
        """Deleta responsável"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)

        result = await db.guardians.delete_one({"id": guardian_id})

        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Responsável não encontrado"
            )

        return None

    return router
