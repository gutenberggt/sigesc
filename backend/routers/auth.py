"""
Router de Autenticação - SIGESC
Endpoints relacionados a login, logout, tokens e perfil de usuário.
"""

from fastapi import APIRouter, HTTPException, status, Request
from datetime import datetime, timezone, timedelta
import uuid

from models import (
    LoginRequest, TokenResponse, RefreshTokenRequest,
    UserCreate, UserUpdate, UserResponse, UserInDB, User
)
from auth_utils import (
    hash_password, verify_password, create_access_token,
    create_refresh_token, decode_token, token_blacklist
)
from auth_middleware import AuthMiddleware
from text_utils import format_data_uppercase

router = APIRouter(prefix="/auth", tags=["Autenticação"])


def setup_router(db, audit_service):
    """Configura o router com as dependências necessárias"""
    
    async def get_effective_role_from_lotacoes(email: str, base_role: str):
        """Determina o role efetivo baseado nas lotações ativas do usuário"""
        staff = await db.staff.find_one({"email": email}, {"_id": 0, "id": 1})
        if not staff:
            return base_role, []
        
        lotacoes = await db.school_assignments.find({
            "staff_id": staff['id'],
            "status": "ativo",
            "academic_year": datetime.now().year
        }, {"_id": 0}).to_list(100)
        
        if not lotacoes:
            return base_role, []
        
        # Prioridade de funções (maior valor = maior prioridade)
        funcao_priority = {
            'diretor': 5,
            'coordenador': 4,
            'secretario': 3,
            'professor': 2,
            'auxiliar': 1
        }
        
        highest_role = base_role
        highest_priority = funcao_priority.get(base_role, 0)
        school_links = []
        
        for lot in lotacoes:
            funcao = lot.get('funcao', '').lower()
            priority = funcao_priority.get(funcao, 0)
            
            if priority > highest_priority:
                highest_priority = priority
                highest_role = funcao
            
            school_links.append({
                'school_id': lot.get('school_id'),
                'role': funcao
            })
        
        return highest_role, school_links

    @router.post("/login", response_model=TokenResponse)
    async def login(credentials: LoginRequest, request: Request):
        """Autentica usuário e retorna tokens"""
        user_doc = await db.users.find_one({"email": credentials.email}, {"_id": 0})
        
        if not user_doc:
            await audit_service.log(
                action='login',
                collection='users',
                user={'id': 'unknown', 'email': credentials.email, 'role': 'unknown'},
                request=request,
                description=f"Tentativa de login falhada - usuário não encontrado: {credentials.email}"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email ou senha incorretos"
            )
        
        user = UserInDB(**user_doc)
        
        if not verify_password(credentials.password, user.password_hash):
            await audit_service.log(
                action='login',
                collection='users',
                user={'id': user.id, 'email': user.email, 'role': user.role},
                request=request,
                description=f"Tentativa de login falhada - senha incorreta: {credentials.email}"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email ou senha incorretos"
            )
        
        if user.status != 'active':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuário inativo"
            )
        
        effective_role = user.role
        effective_school_links = user.school_links or []
        
        if user.role in ['professor', 'secretario', 'coordenador', 'diretor']:
            effective_role, lotacao_school_links = await get_effective_role_from_lotacoes(user.email, user.role)
            if lotacao_school_links:
                effective_school_links = lotacao_school_links
        
        school_ids = [link.get('school_id') for link in effective_school_links if link.get('school_id')]
        token_data = {
            "sub": user.id,
            "email": user.email,
            "role": effective_role,
            "school_ids": school_ids
        }
        
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token({"sub": user.id})
        
        await audit_service.log(
            action='login',
            collection='users',
            user={'id': user.id, 'email': user.email, 'role': effective_role, 'full_name': user.full_name},
            request=request,
            document_id=user.id,
            description=f"Login realizado: {user.full_name}"
        )
        
        user_response_data = user.model_dump(exclude={'password_hash'})
        user_response_data['role'] = effective_role
        user_response_data['school_links'] = effective_school_links
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserResponse(**user_response_data)
        )

    @router.post("/refresh")
    async def refresh_token(request_data: RefreshTokenRequest):
        """Renova o access token usando o refresh token"""
        try:
            payload = decode_token(request_data.refresh_token)
            if payload.get('type') != 'refresh':
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token inválido"
                )
            
            user_id = payload.get('sub')
            user_doc = await db.users.find_one({"id": user_id}, {"_id": 0})
            
            if not user_doc:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Usuário não encontrado"
                )
            
            user = UserInDB(**user_doc)
            
            effective_role = user.role
            effective_school_links = user.school_links or []
            
            if user.role in ['professor', 'secretario', 'coordenador', 'diretor']:
                effective_role, lotacao_school_links = await get_effective_role_from_lotacoes(user.email, user.role)
                if lotacao_school_links:
                    effective_school_links = lotacao_school_links
            
            school_ids = [link.get('school_id') for link in effective_school_links if link.get('school_id')]
            token_data = {
                "sub": user.id,
                "email": user.email,
                "role": effective_role,
                "school_ids": school_ids
            }
            
            new_access_token = create_access_token(token_data)
            new_refresh_token = create_refresh_token({"sub": user.id})
            
            user_response_data = user.model_dump(exclude={'password_hash'})
            user_response_data['role'] = effective_role
            user_response_data['school_links'] = effective_school_links
            
            return TokenResponse(
                access_token=new_access_token,
                refresh_token=new_refresh_token,
                user=UserResponse(**user_response_data)
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido ou expirado"
            )

    @router.get("/me", response_model=UserResponse)
    async def get_current_user_profile(request: Request):
        """Retorna o perfil do usuário autenticado"""
        current_user = await AuthMiddleware.get_current_user(request)
        
        user_doc = await db.users.find_one({"id": current_user['id']}, {"_id": 0})
        if not user_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuário não encontrado"
            )
        
        return UserResponse(**user_doc)

    @router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
    async def register(user_data: UserCreate):
        """Registra novo usuário"""
        existing_user = await db.users.find_one({"email": user_data.email})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email já cadastrado"
            )
        
        user_dict = format_data_uppercase(user_data.model_dump(exclude={'password'}))
        user_obj = UserInDB(
            **user_dict,
            password_hash=hash_password(user_data.password)
        )
        
        doc = user_obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        
        await db.users.insert_one(doc)
        return UserResponse(**user_obj.model_dump(exclude={'password_hash'}))

    @router.post("/logout")
    async def logout(request: Request):
        """Revoga o refresh token atual do usuário."""
        current_user = await AuthMiddleware.get_current_user(request)
        
        try:
            body = await request.json()
            refresh_token = body.get('refresh_token')
            
            if refresh_token:
                payload = decode_token(refresh_token)
                if payload and payload.get('jti'):
                    token_exp = payload.get('exp')
                    exp_datetime = datetime.fromtimestamp(token_exp, tz=timezone.utc) if token_exp else datetime.now(timezone.utc) + timedelta(days=7)
                    
                    await token_blacklist.revoke_token(
                        jti=payload.get('jti'),
                        user_id=current_user['id'],
                        expires_at=exp_datetime,
                        reason='user_logout'
                    )
        except:
            pass
        
        await audit_service.log(
            action='logout',
            collection='users',
            user=current_user,
            request=request,
            document_id=current_user['id'],
            description=f"Logout realizado"
        )
        
        return {"message": "Logout realizado com sucesso"}

    @router.post("/logout-all")
    async def logout_all_sessions(request: Request):
        """Revoga TODOS os refresh tokens do usuário."""
        current_user = await AuthMiddleware.get_current_user(request)
        
        await token_blacklist.revoke_all_user_tokens(
            user_id=current_user['id'],
            reason='user_logout_all'
        )
        
        await audit_service.log(
            action='logout_all',
            collection='users',
            user=current_user,
            request=request,
            document_id=current_user['id'],
            description=f"Logout de todas as sessões realizado"
        )
        
        return {"message": "Todas as sessões foram encerradas. Faça login novamente."}

    @router.get("/permissions")
    async def get_user_permissions(request: Request):
        """Retorna as permissões do usuário autenticado baseado no seu role"""
        current_user = await AuthMiddleware.get_current_user(request)
        
        permissions = AuthMiddleware.get_user_permissions(current_user)
        permissions['school_ids'] = current_user.get('school_ids', [])
        
        return permissions

    return router
