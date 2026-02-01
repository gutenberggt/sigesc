"""
Router de Usuários - SIGESC
Endpoints para gestão de usuários do sistema (Admin only).
"""

from fastapi import APIRouter, HTTPException, status, Request
from typing import List
from passlib.context import CryptContext

from models import UserResponse, UserUpdate
from auth_middleware import AuthMiddleware

router = APIRouter(prefix="/users", tags=["Usuários"])

# Contexto para hash de senha
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def setup_router(db, audit_service, sandbox_db=None):
    """Configura o router com as dependências necessárias"""
    
    def get_db_for_user(user: dict):
        """Retorna o banco correto baseado no usuário"""
        if sandbox_db and (user.get('is_sandbox') or user.get('role') == 'admin_teste'):
            return sandbox_db
        return db

    @router.get("", response_model=List[UserResponse])
    async def list_users(request: Request, skip: int = 0, limit: int = 1000):
        """Lista usuários (apenas admin e semed)"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'semed'])(request)
        current_db = get_db_for_user(current_user)
        
        users = await current_db.users.find({}, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
        
        # Remove password_hash de todos
        for user in users:
            user.pop('password_hash', None)
        
        return users

    @router.get("/{user_id}", response_model=UserResponse)
    async def get_user(user_id: str, request: Request):
        """Busca usuário por ID"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario', 'diretor', 'semed'])(request)
        current_db = get_db_for_user(current_user)
        
        user_doc = await current_db.users.find_one({"id": user_id}, {"_id": 0})
        
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
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        # Busca usuário
        user_doc = await current_db.users.find_one({"id": user_id}, {"_id": 0})
        if not user_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuário não encontrado"
            )
        
        # Prepara atualização
        update_data = user_update.model_dump(exclude_unset=True)
        
        # Se a senha foi fornecida, faz o hash
        if 'password' in update_data and update_data['password']:
            update_data['password_hash'] = pwd_context.hash(update_data['password'])
            del update_data['password']  # Remove o campo password, só salva password_hash
        elif 'password' in update_data:
            del update_data['password']  # Remove se estiver vazio
        
        if update_data:
            await current_db.users.update_one(
                {"id": user_id},
                {"$set": update_data}
            )
        
        # Retorna usuário atualizado
        updated_user = await current_db.users.find_one({"id": user_id}, {"_id": 0})
        updated_user.pop('password_hash', None)
        
        return UserResponse(**updated_user)

    @router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_user(user_id: str, request: Request):
        """Deleta usuário definitivamente do sistema"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste'])(request)
        current_db = get_db_for_user(current_user)
        
        # Verificar se o usuário existe
        user = await current_db.users.find_one({"id": user_id})
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
        result = await current_db.users.delete_one({"id": user_id})
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro ao excluir usuário"
            )
        
        return None

    return router
