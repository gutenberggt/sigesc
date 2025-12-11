from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Optional
from auth_utils import decode_token
import logging

logger = logging.getLogger(__name__)

security = HTTPBearer()

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
            'email': payload.get('email')
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
