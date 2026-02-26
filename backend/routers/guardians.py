"""
Router de Responsáveis - SIGESC
Endpoints para gestão de responsáveis dos alunos.
"""

from fastapi import APIRouter, HTTPException, status, Request
from typing import List

from models import Guardian, GuardianCreate, GuardianUpdate
from auth_middleware import AuthMiddleware
from text_utils import format_data_uppercase

router = APIRouter(prefix="/guardians", tags=["Responsáveis"])


def setup_router(db, audit_service):
    """Configura o router com as dependências necessárias"""

    @router.post("", response_model=Guardian, status_code=status.HTTP_201_CREATED)
    async def create_guardian(guardian_data: GuardianCreate, request: Request):
        """Cria novo responsável"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
        
        guardian_dict = format_data_uppercase(guardian_data.model_dump())
        guardian_obj = Guardian(**guardian_dict)
        doc = guardian_obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        
        await db.guardians.insert_one(doc)
        
        return guardian_obj

    @router.get("", response_model=List[Guardian])
    async def list_guardians(request: Request, skip: int = 0, limit: int = 100):
        """Lista responsáveis"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'semed', 'semed3'])(request)
        
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
        
        update_data = guardian_update.model_dump(exclude_unset=True)
        update_data = format_data_uppercase(update_data)
        
        if update_data:
            result = await db.guardians.update_one(
                {"id": guardian_id},
                {"$set": update_data}
            )
            
            if result.matched_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Responsável não encontrado"
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
