from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Optional
from auth_utils import decode_token
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
        """Extrai e valida usuário do token JWT"""
        auth_header = request.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Token de autenticação não fornecido',
                headers={'WWW-Authenticate': 'Bearer'},
            )
        
        token = auth_header.split(' ')[1]
        payload = decode_token(token)
        
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Token inválido ou expirado',
                headers={'WWW-Authenticate': 'Bearer'},
            )
        
        if payload.get('type') != 'access':
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
        
        return {
            'id': user_id,
            'role': payload.get('role'),
            'school_ids': payload.get('school_ids', []),
            'email': payload.get('email'),
            'is_sandbox': payload.get('is_sandbox', False)
        }
    
    @staticmethod
    def require_roles(allowed_roles: List[str]):
        """Decorator para verificar se o usuário tem um dos papéis permitidos"""
        async def role_checker(request: Request):
            user = await AuthMiddleware.get_current_user(request)
            
            if user['role'] not in allowed_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f'Acesso negado. Papel requerido: {", ".join(allowed_roles)}'
                )
            
            return user
        
        return role_checker
    
    @staticmethod
    def require_roles_with_coordinator_edit(allowed_roles: List[str], resource_area: str):
        """
        Verifica se o usuário pode EDITAR um recurso específico.
        Coordenadores só podem editar em áreas do diário (notas, frequência, conteúdos).
        Para outras áreas, coordenadores têm acesso somente leitura.
        """
        async def role_checker(request: Request):
            user = await AuthMiddleware.get_current_user(request)
            
            # Se não for coordenador, verifica normalmente
            if user['role'] != 'coordenador':
                if user['role'] not in allowed_roles:
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
        """Verifica se o usuário tem acesso à escola"""
        # Admin e SEMED têm acesso a todas as escolas
        if user['role'] in ['admin', 'semed']:
            return True
        
        # Outros papéis precisam ter a escola vinculada
        return school_id in user['school_ids']
    
    @staticmethod
    async def verify_school_access(request: Request, school_id: str):
        """Verifica acesso à escola e retorna usuário"""
        user = await AuthMiddleware.get_current_user(request)
        
        if not AuthMiddleware.check_school_access(user, school_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='Acesso negado a esta escola'
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
        if user['role'] == 'coordenador':
            return {
                'role': 'coordenador',
                'can_edit_grades': True,
                'can_edit_attendance': True,
                'can_edit_learning_objects': True,
                'can_edit_students': False,
                'can_edit_classes': False,
                'can_edit_staff': False,
                'can_edit_enrollments': False,
                'can_view_all_school_data': True,
                'is_read_only_except_diary': True
            }
        elif user['role'] == 'admin':
            return {
                'role': 'admin',
                'can_edit_grades': True,
                'can_edit_attendance': True,
                'can_edit_learning_objects': True,
                'can_edit_students': True,
                'can_edit_classes': True,
                'can_edit_staff': True,
                'can_edit_enrollments': True,
                'can_view_all_school_data': True,
                'is_read_only_except_diary': False
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
