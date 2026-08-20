"""
Router de Usuários - SIGESC
Endpoints para gestão de usuários do sistema (Admin only).
"""

from fastapi import APIRouter, HTTPException, status, Request, Response
from typing import List
from passlib.context import CryptContext

from models import UserResponse, UserUpdate
from auth_middleware import AuthMiddleware
from auth_utils import (
    create_access_token,
    create_refresh_token,
    generate_csrf_token,
    set_auth_cookies,
)
from role_context import (
    SCHOOL_SCOPED_ROLES,
    get_authorized_roles,
    resolve_role_context,
)
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
    async def list_users(request: Request, skip: int = 0, limit: int = 0):
        """Lista usuários (admin, secretario e semed) — filtrado por mantenedora ativa.
        Super_admin é usuário nato de toda mantenedora: aparece em qualquer tenant selecionado.

        Paginação opcional:
          - skip>0 e/ou limit>0 → aplica paginação.
          - limit=0 (default) → retorna TODOS os usuários do escopo, sem teto.
        """
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario', 'semed', 'semed3'])(request)
        current_db = get_db_for_user(current_user)
        
        # Multi-tenancy: filtra por mantenedora ativa (FAIL-CLOSED).
        from tenant_scope import get_mantenedora_scope, is_super_admin, INVALID_TENANT_SENTINEL
        from tenant_audit import log_tenant_event
        tenant_id = get_mantenedora_scope(current_user, request)
        if is_super_admin(current_user):
            # super_admin: cross-tenant nato (sem seleção) ou tenant escolhido.
            filter_query = {} if tenant_id is None else {'$or': [
                {'mantenedora_id': tenant_id}, {'role': 'super_admin'}
            ]}
        elif not tenant_id:
            # Não-super_admin sem tenant → NENHUM dado (nunca todos).
            log_tenant_event('missing_tenant', current_user, request)
            filter_query = {'mantenedora_id': INVALID_TENANT_SENTINEL}
        else:
            filter_query = {'$or': [
                {'mantenedora_id': tenant_id}, {'role': 'super_admin'}
            ]}
        
        cursor = current_db.users.find(filter_query, {"_id": 0})
        if skip:
            cursor = cursor.skip(skip)
        if limit and limit > 0:
            cursor = cursor.limit(limit)
        users = await cursor.to_list(length=None)
        
        # Remove password_hash de todos
        for user in users:
            user.pop('password_hash', None)
        
        return users

    @router.get("/count")
    async def count_users(request: Request):
        """Retorna o total real de usuários (não limitado ao paginado) da mantenedora ativa.
        Usado pelo card 'Usuários' do Dashboard para evitar travar em 1000.
        """
        current_user = await AuthMiddleware.require_roles(
            ['admin', 'admin_teste', 'secretario', 'semed', 'semed3']
        )(request)
        current_db = get_db_for_user(current_user)

        from tenant_scope import get_mantenedora_scope, is_super_admin, INVALID_TENANT_SENTINEL
        from tenant_audit import log_tenant_event
        tenant_id = get_mantenedora_scope(current_user, request)
        if is_super_admin(current_user):
            filter_query = {} if tenant_id is None else {'$or': [{'mantenedora_id': tenant_id}, {'role': 'super_admin'}]}
        elif not tenant_id:
            log_tenant_event('missing_tenant', current_user, request)
            filter_query = {'mantenedora_id': INVALID_TENANT_SENTINEL}
        else:
            filter_query = {'$or': [{'mantenedora_id': tenant_id}, {'role': 'super_admin'}]}

        total = await current_db.users.count_documents(filter_query)
        total_active = await current_db.users.count_documents({**filter_query, 'status': 'active'})
        return {"total": total, "total_active": total_active}

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
        
        # Regra: promoção para super_admin só por super_admin
        update_raw = user_update.model_dump(exclude_unset=True)
        if update_raw.get('role') == 'super_admin' and current_user.get('role') != 'super_admin':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Apenas um Super Administrador pode atribuir o papel de Super Administrador"
            )
        # Bloqueio: não permitir rebaixar o super_admin primário
        if user_doc.get('is_primary') and update_raw.get('role') and update_raw['role'] != 'super_admin':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="O Super Administrador primário não pode ter seu papel alterado"
            )
        
        # Prepara atualização
        update_data = user_update.model_dump(exclude_unset=True)
        
        # Se a senha foi fornecida, faz o hash
        if 'password' in update_data and update_data['password']:
            update_data['password_hash'] = pwd_context.hash(update_data['password'])
            del update_data['password']
        elif 'password' in update_data:
            del update_data['password']
        
        # [Mai/2026] CAPS lock automático removido — preserva capitalização do usuário.
        
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
        
        # Super Administrador PRIMÁRIO (is_primary) nunca pode ser excluído
        if user.get('is_primary'):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="O Super Administrador primário do sistema não pode ser excluído"
            )
        
        # Apenas outro super_admin pode excluir um super_admin
        if user.get('role') == 'super_admin' and current_user.get('role') != 'super_admin':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Apenas um Super Administrador pode excluir outro Super Administrador"
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
    async def switch_active_role(request: Request, response: Response):
        """Troca somente o papel ativo da sessão; não altera `users.role`."""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)

        body = await request.json()
        new_role = body.get('role')
        if not new_role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="O campo 'role' é obrigatório"
            )

        user_doc = await current_db.users.find_one(
            {"id": current_user['id']},
            {"_id": 0}
        )
        if not user_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuário não encontrado"
            )
        if user_doc.get('status') != 'active':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuário inativo"
            )

        available_roles = get_authorized_roles(user_doc)
        if new_role not in available_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Você não possui o papel '{new_role}'. "
                    f"Papéis disponíveis: {available_roles}"
                )
            )

        role_context = await resolve_role_context(
            current_db,
            user_doc,
            new_role,
        )
        if (
            new_role in SCHOOL_SCOPED_ROLES
            and role_context['source'] == 'lotacoes'
            and not role_context['has_role_assignment']
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Não há lotação ativa em {new_role} para o ano letivo atual"
                )
            )

        token_data = {
            "sub": user_doc['id'],
            "email": user_doc.get('email'),
            "role": new_role,
            "school_ids": role_context['school_ids'],
            "mantenedora_id": user_doc.get('mantenedora_id'),
        }
        csrf_token = generate_csrf_token()
        access_token = create_access_token(token_data, csrf=csrf_token)
        refresh_token = create_refresh_token({
            "sub": user_doc['id'],
            "active_role": new_role,
        })
        set_auth_cookies(
            response,
            access_token=access_token,
            refresh_token=refresh_token,
            csrf_token=csrf_token,
        )

        user_response = dict(user_doc)
        user_response.pop('password_hash', None)
        user_response['role'] = new_role
        user_response['school_links'] = role_context['school_links']

        try:
            await audit_service.log(
                action='switch_role',
                collection='users',
                user={**current_user, 'full_name': user_doc.get('full_name')},
                request=request,
                document_id=user_doc['id'],
                description=(
                    f"Papel ativo da sessão alterado de "
                    f"{current_user.get('role')} para {new_role}"
                ),
                old_value={'active_role': current_user.get('role')},
                new_value={'active_role': new_role},
            )
        except Exception:
            pass

        return {
            "message": f"Papel ativo alterado para '{new_role}' com sucesso",
            "new_role": new_role,
            "available_roles": available_roles,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "csrf_token": csrf_token,
            "token_type": "bearer",
            "user": UserResponse(**user_response).model_dump(),
        }

    return router
