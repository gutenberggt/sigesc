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
    async def _resolve_request_tenant(user: dict, request: Request) -> dict:
        """MT-1: resolve tenant operacional ANTES de RBAC/escopo escolar.

        Endpoints de sessão e control plane explicitamente autorizados são
        isentos. Em qualquer rota operacional, ausência/tenant inválido/inativo
        falham fechados.
        """
        from tenant_scope import (
            requires_operational_tenant_context,
            resolve_operational_tenant_context,
        )

        if not requires_operational_tenant_context(user, request):
            return user

        # `audit_service` já recebe o db canônico durante o bootstrap do server.
        # Reutilizar essa referência evita importar server.py de volta (ciclo).
        from audit_service import audit_service
        tenant_db = audit_service.db
        if tenant_db is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    'code': 'TENANT_CONTEXT_UNAVAILABLE',
                    'message': 'Contexto multi-tenant indisponível no momento.',
                },
            )

        ctx = await resolve_operational_tenant_context(tenant_db, user, request)
        enriched = dict(user)
        enriched['active_mantenedora_id'] = ctx.id
        return enriched

    @staticmethod
    async def get_current_user(request: Request) -> dict:
        """Extrai e valida usuário do token JWT.

        Ordem de leitura (G2 — Fev/2026):
          1. Cookie HttpOnly `sigesc_access` (novo padrão seguro).
          2. Header `Authorization: Bearer ...` (retrocompat durante migração).
          3. Query param `?token=...` (necessário p/ window.open em PDFs).

        MT-1: depois da identidade JWT, a mantenedora operacional é resolvida e
        validada antes de qualquer RBAC, salvo endpoints explícitos de sessão ou
        control plane.
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

        user = {
            'id': user_id,
            'role': payload.get('role'),
            'school_ids': payload.get('school_ids', []),
            'email': payload.get('email'),
            'is_sandbox': payload.get('is_sandbox', False),
            'mantenedora_id': payload.get('mantenedora_id'),
        }
        return await AuthMiddleware._resolve_request_tenant(user, request)

    @staticmethod
    def require_roles(allowed_roles: List[str]):
        """Decorator para verificar se o usuário tem um dos papéis permitidos"""
        async def role_checker(request: Request):
            # get_current_user já validou o tenant operacional (MT-1).
            user = await AuthMiddleware.get_current_user(request)

            # super_admin mantém bypass FUNCIONAL, nunca bypass de tenant.
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

        MT-1: o tenant operacional já foi validado por get_current_user antes
        de qualquer decisão da Matriz/RBAC.
        """
        async def permission_checker(request: Request):
            user = await AuthMiddleware.get_current_user(request)
            role = user.get('role')
            # super_admin passa no RBAC funcional; o tenant já foi validado.
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
                # super_admin mantém bypass funcional; tenant já validado.
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

        Papéis globais da mantenedora têm visão total DENTRO do tenant ativo.
        A validação cross-tenant final ocorre em verify_school_access.
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
        """Verifica acesso escolar com tenant obrigatório e fail-closed.

        MT-1:
        - tenant operacional é resolvido antes do escopo escolar;
        - escola inexistente não é autorizada;
        - escola sem mantenedora_id é bloqueada para saneamento governado;
        - tenant divergente é sempre 403, inclusive para super_admin.
        """
        from audit_service import audit_service
        from tenant_scope import resolve_operational_tenant_context

        user = await AuthMiddleware.get_current_user(request)

        if not AuthMiddleware.check_school_access(user, school_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='Acesso negado a esta escola'
            )

        tenant_db = audit_service.db
        if tenant_db is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail='Contexto multi-tenant indisponível'
            )

        ctx = await resolve_operational_tenant_context(tenant_db, user, request)
        school = await tenant_db.schools.find_one(
            {"id": school_id},
            {"_id": 0, "id": 1, "mantenedora_id": 1},
        )
        if not school:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Escola não encontrada'
            )

        school_tenant = school.get('mantenedora_id')
        if not school_tenant:
            log_tenant_event(
                'missing_document_tenant',
                user,
                request,
                extra={'collection': 'schools', 'document_id': school_id},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='Escola sem mantenedora_id; saneamento governado é necessário'
            )

        if str(school_tenant) != str(ctx.id):
            log_tenant_event(
                'cross_tenant_attempt',
                user,
                request,
                requested_mantenedora=str(school_tenant),
                extra={'collection': 'schools', 'document_id': school_id},
            )
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
