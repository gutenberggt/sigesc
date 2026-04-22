"""
Router de Usuários - SIGESC
Endpoints para gestão de usuários do sistema (Admin only).
"""

from fastapi import APIRouter, HTTPException, status, Request
from typing import List
from passlib.context import CryptContext

from models import UserResponse, UserUpdate
from auth_middleware import AuthMiddleware
from text_utils import format_data_uppercase
from tenant_scope import apply_tenant_filter, assert_same_tenant

router = APIRouter(prefix="/users", tags=["Usuários"])

# Contexto para hash de senha
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def setup_router(db, audit_service, sandbox_db=None):
    """Configura o router com as dependências necessárias"""
    
    def get_db_for_user(user: dict):
        """Retorna o banco correto baseado no usuário"""
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db

    @router.get("")
    async def list_users(request: Request, skip: int = 0, limit: int = 1000):
        """Lista usuários (admin, secretario e semed) — filtrado por mantenedora ativa.
        Super_admin é usuário nato de toda mantenedora: aparece em qualquer tenant selecionado.
        """
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario', 'semed', 'semed3'])(request)
        current_db = get_db_for_user(current_user)
        
        # Multi-tenancy: filtra por mantenedora ativa (mas super_admin é cross-tenant nato)
        from tenant_scope import get_mantenedora_scope
        tenant_id = get_mantenedora_scope(current_user, request)
        if tenant_id:
            # Tenant específico: inclui os usuários da mantenedora + qualquer super_admin (nato)
            filter_query = {'$or': [
                {'mantenedora_id': tenant_id},
                {'role': 'super_admin'}
            ]}
        else:
            # Cross-tenant (super_admin sem seleção): todos os usuários
            filter_query = {}
        
        users = await current_db.users.find(filter_query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
        
        # Remove password_hash de todos
        for user in users:
            user.pop('password_hash', None)
        
        return users

    @router.get("/{user_id}")
    async def get_user(user_id: str, request: Request):
        """Busca usuário por ID"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario', 'diretor', 'semed', 'semed3'])(request)
        current_db = get_db_for_user(current_user)
        
        user_doc = await current_db.users.find_one({"id": user_id}, {"_id": 0})
        
        if not user_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuário não encontrado"
            )
        
        # Multi-tenancy: super_admin é usuário nato de toda mantenedora
        if user_doc.get('role') != 'super_admin':
            assert_same_tenant(user_doc, current_user, request)
        
        user_doc.pop('password_hash', None)
        return user_doc

    @router.put("/{user_id}")
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
        
        # Multi-tenancy: super_admin é usuário nato (acessível de qualquer tenant)
        if user_doc.get('role') != 'super_admin':
            assert_same_tenant(user_doc, current_user, request)
        
        # Prepara atualização
        update_data = user_update.model_dump(exclude_unset=True)
        
        # Se a senha foi fornecida, faz o hash
        if 'password' in update_data and update_data['password']:
            update_data['password_hash'] = pwd_context.hash(update_data['password'])
            del update_data['password']
        elif 'password' in update_data:
            del update_data['password']
        
        # Converte dados para maiúsculas
        update_data = format_data_uppercase(update_data)
        
        if update_data:
            await current_db.users.update_one(
                {"id": user_id},
                {"$set": update_data}
            )
        
        # Retorna usuário atualizado
        updated_user = await current_db.users.find_one({"id": user_id}, {"_id": 0})
        updated_user.pop('password_hash', None)
        
        return updated_user

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
        
        # Multi-tenancy: super_admin é nato de toda mantenedora
        if user.get('role') != 'super_admin':
            assert_same_tenant(user, current_user, request)
        
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

    @router.post("/switch-role")
    async def switch_active_role(request: Request):
        """
        Alterna o papel ativo do usuário logado.
        O novo papel deve estar na lista de papéis (roles) do usuário.
        """
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        body = await request.json()
        new_role = body.get('role')
        
        if not new_role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="O campo 'role' é obrigatório"
            )
        
        # Busca o usuário no banco
        user_doc = await current_db.users.find_one({"id": current_user['id']}, {"_id": 0})
        if not user_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuário não encontrado"
            )
        
        # Verifica se o papel está na lista de papéis do usuário
        user_roles = user_doc.get('roles', [])
        # Se roles estiver vazio, usa o role principal como único papel disponível
        if not user_roles:
            user_roles = [user_doc.get('role')]
        
        if new_role not in user_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Você não possui o papel '{new_role}'. Papéis disponíveis: {user_roles}"
            )
        
        # Atualiza o papel ativo
        await current_db.users.update_one(
            {"id": current_user['id']},
            {"$set": {"role": new_role}}
        )
        
        return {
            "message": f"Papel alterado para '{new_role}' com sucesso",
            "new_role": new_role,
            "available_roles": user_roles
        }

    return router
