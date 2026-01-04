"""
Router de Usuários - SIGESC
Endpoints para gestão de usuários do sistema (Admin only).
"""

from fastapi import APIRouter, HTTPException, status, Request
from typing import List

from models import UserResponse, UserUpdate
from auth_middleware import AuthMiddleware

router = APIRouter(prefix="/users", tags=["Usuários"])


def setup_router(db, audit_service):
    """Configura o router com as dependências necessárias"""

    @router.get("", response_model=List[UserResponse])
    async def list_users(request: Request, skip: int = 0, limit: int = 1000):
        """Lista usuários (apenas admin e semed)"""
        current_user = await AuthMiddleware.require_roles(['admin', 'semed'])(request)
        
        users = await db.users.find({}, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
        
        # Remove password_hash de todos
        for user in users:
            user.pop('password_hash', None)
        
        return users

    @router.get("/{user_id}", response_model=UserResponse)
    async def get_user(user_id: str, request: Request):
        """Busca usuário por ID"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'semed'])(request)
        
        user_doc = await db.users.find_one({"id": user_id}, {"_id": 0})
        
        if not user_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuário não encontrado"
            )
        
        user_doc.pop('password_hash', None)
        return UserResponse(**user_doc)

    @router.put("/{user_id}", response_model=UserResponse)
    async def update_user(user_id: str, user_update: UserUpdate, request: Request):
        """Atualiza usuário"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
        
        # Busca usuário
        user_doc = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not user_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuário não encontrado"
            )
        
        # Prepara atualização
        update_data = user_update.model_dump(exclude_unset=True)
        
        if update_data:
            await db.users.update_one(
                {"id": user_id},
                {"$set": update_data}
            )
        
        # Retorna usuário atualizado
        updated_user = await db.users.find_one({"id": user_id}, {"_id": 0})
        updated_user.pop('password_hash', None)
        
        return UserResponse(**updated_user)

    @router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_user(user_id: str, request: Request):
        """Deleta usuário definitivamente do sistema"""
        current_user = await AuthMiddleware.require_roles(['admin'])(request)
        
        # Verificar se o usuário existe
        user = await db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuário não encontrado"
            )
        
        # Não permitir excluir o próprio usuário
        if user_id == current_user['id']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não é possível excluir seu próprio usuário"
            )
        
        # Excluir definitivamente o usuário
        result = await db.users.delete_one({"id": user_id})
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro ao excluir usuário"
            )
        
        return None

    return router
