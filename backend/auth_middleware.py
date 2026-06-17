from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Optional
from auth_utils import decode_token, token_blacklist, ACCESS_COOKIE_NAME
from tenant_audit import log_tenant_event
import logging

logger = logging.getLogger(__name__)

security = HTTPBearer()

# Áreas onde o Coordenador pode EDITAR (diário: notas, conteúdos, frequência)
COORDINATOR_EDIT_AREAS = ['grades', 'attendance', 'learning_objects', 'conteudo']

# Recursos que o Coordenador pode apenas VISUALIZAR (tudo da sua escola)
COORDINATOR_VIEW_ONLY_AREAS = ['students', 'classes', 'courses', 'enrollments', 'staff', 'school_assignments', 'teacher_assignments']

class AuthMiddleware:
    """Middleware para autenticação e autorização"""
    
    @staticmethod
    async def get_current_user(request: Request) -> dict:
        """Extrai e valida usuário do token JWT.

        Ordem de leitura (G2 — Fev/2026):
          1. Cookie HttpOnly `sigesc_access` (novo padrão seguro).
          2. Header `Authorization: Bearer ...` (retrocompat durante migração).
          3. Query param `?token=...` (necessário p/ window.open em PDFs).
        """
        token = request.cookies.get(ACCESS_COOKIE_NAME)

        if not token:
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]

        if not token:
            query_token = request.query_params.get('token')
            if query_token:
                token = query_token

        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Token de autenticação não fornecido',
                headers={'WWW-Authenticate': 'Bearer'},
            )
        payload = decode_token(token)
        
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Token inválido ou expirado',
                headers={'WWW-Authenticate': 'Bearer'},
            )
        
        if payload.get('type') != 'access':
            log_tenant_event(
                'invalid_token', {'id': payload.get('sub'), 'role': payload.get('role')}, request,
                extra={'token_type': payload.get('type')}
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Tipo de token inválido',
            )
        
        user_id = payload.get('sub')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Token inválido',
            )
        
        # Consulta blacklist: token revogado individualmente (jti) OU dentro
        # da janela de revoke_all (logout). O comparador usa iat (issued at) do
        # access_token. Tokens emitidos antes do fix (sem iat) ignoram o
        # check de revoke_all_before, mas continuam expirando naturalmente.
        issued_at = payload.get('iat')
        token_jti = payload.get('jti')  # access tokens novos podem ter jti no futuro
        if issued_at is not None or token_jti is not None:
            if await token_blacklist.is_token_revoked(
                jti=token_jti, user_id=user_id, issued_at=issued_at
            ):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail='Token revogado',
                    headers={'WWW-Authenticate': 'Bearer'},
                )
        
        return {
            'id': user_id,
            'role': payload.get('role'),
            'school_ids': payload.get('school_ids', []),
            'email': payload.get('email'),
            'is_sandbox': payload.get('is_sandbox', False),
            'mantenedora_id': payload.get('mantenedora_id'),
        }
    
    @staticmethod
    def require_roles(allowed_roles: List[str]):
        """Decorator para verificar se o usuário tem um dos papéis permitidos"""
        async def role_checker(request: Request):
            user = await AuthMiddleware.get_current_user(request)
            
            # super_admin tem acesso total (cross-tenant) — Multi-tenancy Fase 1
            if user['role'] == 'super_admin':
                return user
            
            # admin_teste tem as mesmas permissões que admin
            # apoio_pedagogico tem as mesmas permissões que coordenador
            # gerente é admin escopado à sua mantenedora
            effective_role = user['role']
            if effective_role == 'admin_teste':
                effective_role = 'admin'
            elif effective_role == 'apoio_pedagogico':
                effective_role = 'coordenador'
            elif effective_role == 'gerente':
                effective_role = 'admin'
            
            if effective_role not in allowed_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f'Acesso negado. Papel requerido: {", ".join(allowed_roles)}'
                )
            
            return user
        
        return role_checker
    
    @staticmethod
    def require_permission(db, menu_item_key: str, default_roles: List[str]):
        """Apr 2026: Verificação de permissão sensível à Matriz de Permissões.

        Consulta `db.permission_overrides` para o par (menu_item_key, role) do
        usuário autenticado:
        - Se houver override `visible=True`  → libera acesso (mesmo se papel não está em default_roles).
        - Se houver override `visible=False` → bloqueia (mesmo que papel esteja em default_roles).
        - Se não houver override → cai no `require_roles(default_roles)` tradicional.

        Isso faz da Matriz de Permissões a fonte de verdade tanto para visibilidade
        no menu quanto para acesso na API, sem precisar editar código a cada mudança.
        """
        async def permission_checker(request: Request):
            user = await AuthMiddleware.get_current_user(request)
            role = user.get('role')
            # super_admin SEMPRE passa: evita lock-out acidental via Matriz.
            if role == 'super_admin':
                return user
            try:
                override = await db.permission_overrides.find_one(
                    {"item_key": menu_item_key, "role": role},
                    {"_id": 0, "visible": 1}
                )
            except Exception:
                override = None

            if override is not None:
                if override.get('visible'):
                    return user
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Acesso negado pela Matriz de Permissões ({menu_item_key} × {role})"
                )

            # Fallback: aplica regra padrão do código
            return await AuthMiddleware.require_roles(default_roles)(request)

        return permission_checker

    @staticmethod
    def require_roles_with_coordinator_edit(allowed_roles: List[str], resource_area: str):
        """
        Verifica se o usuário pode EDITAR um recurso específico.
        Coordenadores só podem editar em áreas do diário (notas, frequência, conteúdos).
        Para outras áreas, coordenadores têm acesso somente leitura.
        """
        async def role_checker(request: Request):
            user = await AuthMiddleware.get_current_user(request)
            
            # Se não for coordenador/apoio_pedagogico, verifica normalmente
            if user['role'] not in ('coordenador', 'apoio_pedagogico'):
                # super_admin tem acesso total (cross-tenant)
                if user['role'] == 'super_admin':
                    return user
                # gerente é admin escopado à mantenedora
                effective_role = 'admin' if user['role'] == 'gerente' else user['role']
                if effective_role not in allowed_roles:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f'Acesso negado. Papel requerido: {", ".join(allowed_roles)}'
                    )
                return user
            
            # É coordenador - verifica se pode editar esta área
            if resource_area in COORDINATOR_EDIT_AREAS:
                return user
            
            # Coordenador tentando editar área não permitida
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='Coordenadores podem apenas visualizar este recurso. Edição permitida somente para notas, frequência e conteúdos.'
            )
        
        return role_checker
    
    @staticmethod
    def check_school_access(user: dict, school_id: str) -> bool:
        """Verifica se o usuário tem acesso (LEITURA) à escola.

        Papéis globais da mantenedora têm visão total (alinhado com
        `routers/schools.py::list_schools` e o mapa do frontend `Users.js`).
        Escrita é validada por endpoint (não passa por aqui).
        """
        global_tenant_roles = {
            'super_admin', 'admin', 'admin_teste', 'gerente',
            'semed', 'semed1', 'semed2', 'semed3',
            'ass_social', 'ass_social_2', 'agente_vacinas',
        }
        if user['role'] in global_tenant_roles:
            return True

        # Outros papéis precisam ter a escola vinculada
        return school_id in user['school_ids']
    
    @staticmethod
    async def verify_school_access(request: Request, school_id: str):
        """Verifica acesso à escola e retorna usuário.

        Cross-tenant guard (Feb 2026): para gerente/admin/etc., também valida
        que a escola pertence à mantenedora do usuário (a partir do JWT).
        Super_admin pode atuar cross-tenant ou no tenant ativo via header
        X-Mantenedora-Id (resolvido por get_mantenedora_scope).
        """
        from tenant_scope import is_super_admin, get_mantenedora_scope

        user = await AuthMiddleware.get_current_user(request)

        if not AuthMiddleware.check_school_access(user, school_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='Acesso negado a esta escola'
            )

        # Cross-tenant check: a escola precisa pertencer ao tenant ativo do user.
        # super_admin atuando cross-tenant (sem header) ignora; com header,
        # também é validado pela mesma rota.
        active_tenant = get_mantenedora_scope(user, request)
        if active_tenant is not None:
            # Importação preguiçosa para evitar ciclo no startup
            from server import db as _db  # noqa: WPS433
            school = await _db.schools.find_one(
                {"id": school_id}, {"_id": 0, "mantenedora_id": 1}
            )
            school_tenant = (school or {}).get('mantenedora_id')
            # Se a escola tem mantenedora declarada, força o match.
            # Escolas legadas sem mantenedora_id passam (não é campo obrigatório
            # para coleções ainda não migradas).
            if school_tenant and school_tenant != active_tenant:
                # super_admin acessando seu próprio tenant ativo passa por aqui
                # apenas se o header bater com o tenant da escola.
                if not (is_super_admin(user) and active_tenant is None):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail='Escola pertence a outra mantenedora'
                    )

        return user
    
    @staticmethod
    def is_coordinator_read_only(user: dict, resource_area: str) -> bool:
        """
        Verifica se o coordenador tem acesso somente leitura para um recurso.
        Retorna True se for coordenador tentando editar área de somente leitura.
        """
        if user['role'] != 'coordenador':
            return False
        
        return resource_area not in COORDINATOR_EDIT_AREAS
    
    @staticmethod
    def get_user_permissions(user: dict) -> dict:
        """
        Retorna as permissões do usuário para uso no frontend.
        """
        # Coordenador - apenas visualização (sem edição)
        if user['role'] == 'coordenador':
            return {
                'role': 'coordenador',
                'can_edit_grades': False,
                'can_edit_attendance': False,
                'can_edit_learning_objects': False,
                'can_edit_students': False,
                'can_edit_classes': False,
                'can_edit_staff': False,
                'can_edit_enrollments': False,
                'can_view_all_school_data': True,
                'is_read_only_except_diary': True
            }
        # Auxiliar de Secretaria - mesmas permissões do coordenador (apenas visualização)
        elif user['role'] == 'auxiliar_secretaria':
            return {
                'role': 'auxiliar_secretaria',
                'can_edit_grades': False,
                'can_edit_attendance': False,
                'can_edit_learning_objects': False,
                'can_edit_students': False,
                'can_edit_classes': False,
                'can_edit_staff': False,
                'can_edit_enrollments': False,
                'can_view_all_school_data': True,
                'is_read_only_except_diary': True
            }
        # SEMED 3 e SEMED Níveis 1, 2, 3 - apenas visualização
        elif user['role'] in ['semed', 'semed1', 'semed2', 'semed3']:
            return {
                'role': user['role'],
                'can_edit_grades': False,
                'can_edit_attendance': False,
                'can_edit_learning_objects': False,
                'can_edit_students': False,
                'can_edit_classes': False,
                'can_edit_staff': False,
                'can_edit_enrollments': False,
                'can_view_all_school_data': True,
                'is_read_only_except_diary': True
            }
        elif user['role'] in ['admin', 'admin_teste', 'super_admin', 'gerente']:
            return {
                'role': user['role'],
                'can_edit_grades': True,
                'can_edit_attendance': True,
                'can_edit_learning_objects': True,
                'can_edit_students': True,
                'can_edit_classes': True,
                'can_edit_staff': True,
                'can_edit_enrollments': True,
                'can_view_all_school_data': True,
                'is_read_only_except_diary': False,
                'is_sandbox': user.get('is_sandbox', False)
            }
        elif user['role'] == 'professor':
            return {
                'role': 'professor',
                'can_edit_grades': True,
                'can_edit_attendance': True,
                'can_edit_learning_objects': True,
                'can_edit_students': False,
                'can_edit_classes': False,
                'can_edit_staff': False,
                'can_edit_enrollments': False,
                'can_view_all_school_data': False,
                'is_read_only_except_diary': True
            }
        else:
            # Default para outros roles
            return {
                'role': user['role'],
                'can_edit_grades': user['role'] in ['admin', 'secretario'],
                'can_edit_attendance': user['role'] in ['admin', 'secretario'],
                'can_edit_learning_objects': user['role'] in ['admin', 'secretario'],
                'can_edit_students': user['role'] in ['admin', 'secretario', 'diretor'],
                'can_edit_classes': user['role'] in ['admin', 'secretario', 'diretor'],
                'can_edit_staff': user['role'] in ['admin', 'secretario', 'diretor'],
                'can_edit_enrollments': user['role'] in ['admin', 'secretario', 'diretor'],
                'can_view_all_school_data': True,
                'is_read_only_except_diary': False
            }
