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
            'auxiliar_secretaria': 4,
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
        
        if user.role in ['professor', 'secretario', 'coordenador', 'auxiliar_secretaria', 'diretor']:
            effective_role, lotacao_school_links = await get_effective_role_from_lotacoes(user.email, user.role)
            if lotacao_school_links:
                effective_school_links = lotacao_school_links
        
        school_ids = [
            (link['school_id'] if isinstance(link, dict) else link.school_id)
            for link in effective_school_links
            if (link.get('school_id') if isinstance(link, dict) else getattr(link, 'school_id', None))
        ]
        token_data = {
            "sub": user.id,
            "email": user.email,
            "role": effective_role,
            "school_ids": school_ids,
            "mantenedora_id": getattr(user, 'mantenedora_id', None),
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
            
            # Bloqueia refresh se token foi revogado individualmente OU se o usuário
            # tem revoke_all_before posterior ao iat deste refresh_token (ex.: logout).
            refresh_jti = payload.get('jti')
            refresh_iat = payload.get('iat')
            if await token_blacklist.is_token_revoked(
                jti=refresh_jti, user_id=user_id, issued_at=refresh_iat
            ):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token revogado"
                )
            
            user_doc = await db.users.find_one({"id": user_id}, {"_id": 0})
            
            if not user_doc:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Usuário não encontrado"
                )
            
            user = UserInDB(**user_doc)
            
            effective_role = user.role
            effective_school_links = user.school_links or []
            
            if user.role in ['professor', 'secretario', 'coordenador', 'auxiliar_secretaria', 'diretor']:
                effective_role, lotacao_school_links = await get_effective_role_from_lotacoes(user.email, user.role)
                if lotacao_school_links:
                    effective_school_links = lotacao_school_links
            
            school_ids = [
            (link['school_id'] if isinstance(link, dict) else link.school_id)
            for link in effective_school_links
            if (link.get('school_id') if isinstance(link, dict) else getattr(link, 'school_id', None))
        ]
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
    async def register(user_data: UserCreate, request: Request):
        """Registra novo usuário. Multi-tenancy: herda mantenedora do criador autenticado
        ou do header X-Mantenedora-Id. Fallback para a única mantenedora cadastrada.
        Apenas super_admin pode criar outro super_admin."""
        existing_user = await db.users.find_one({"email": user_data.email})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email já cadastrado"
            )
        
        # Regra: papel super_admin só pode ser criado por outro super_admin
        if user_data.role == 'super_admin':
            try:
                creator = await AuthMiddleware.get_current_user(request)
            except HTTPException:
                creator = None
            if not creator or creator.get('role') != 'super_admin':
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Apenas um Super Administrador pode criar outro Super Administrador"
                )
        
        user_dict = format_data_uppercase(user_data.model_dump(exclude={'password'}))
        user_obj = UserInDB(
            **user_dict,
            password_hash=hash_password(user_data.password)
        )
        
        doc = user_obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        
        # Multi-tenancy: deriva mantenedora_id
        tenant_id = None
        # 1) Se há criador autenticado, usa o scope dele
        try:
            from tenant_scope import get_mantenedora_scope
            creator = await AuthMiddleware.get_current_user(request)
            tenant_id = get_mantenedora_scope(creator, request)
            if not tenant_id and creator.get('mantenedora_id'):
                tenant_id = creator['mantenedora_id']
        except HTTPException:
            # Endpoint também usado em onboarding sem auth
            pass
        # 2) Fallback: única mantenedora cadastrada
        if not tenant_id:
            mantenedoras = await db.mantenedoras.find({}, {"_id": 0, "id": 1}).to_list(2)
            if len(mantenedoras) == 1:
                tenant_id = mantenedoras[0]['id']
        if tenant_id:
            doc['mantenedora_id'] = tenant_id
        
        await db.users.insert_one(doc)
        return UserResponse(**user_obj.model_dump(exclude={'password_hash'}))

    @router.post("/logout")
    async def logout(request: Request):
        """
        Revoga o refresh token atual + todos os access tokens emitidos antes
        do logout (via revoke_all_before).
        Em ambiente educacional (multi-device, salas compartilhadas), logout
        invalida todas as sessões do usuário — comportamento mais seguro que
        deixar access_tokens válidos até expirarem naturalmente (15min).
        """
        current_user = await AuthMiddleware.get_current_user(request)
        
        # Revoga refresh_token específico (se enviado)
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
        except Exception:
            pass
        
        # Revoga TODOS os access_tokens emitidos antes deste momento
        # (auth_middleware consulta is_token_revoked com user_id+iat).
        await token_blacklist.revoke_all_user_tokens(
            user_id=current_user['id'],
            reason='user_logout'
        )
        
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

    @router.post("/change-account")
    async def change_account(request: Request):
        """Altera o email e/ou senha do próprio usuário autenticado.

        Body JSON:
            {
                "current_password": "<obrigatório>",
                "new_email": "<opcional>",
                "new_password": "<opcional>"
            }

        Regras:
        - Senha atual sempre exigida (re-autenticação).
        - Pelo menos um dos campos `new_email` / `new_password` deve ser enviado.
        - Novo email não pode estar em uso por outro usuário.
        - **Se o usuário tem registro de servidor (Staff) vinculado pelo email**
          atual, o `email` do servidor é atualizado automaticamente para o novo
          email — garantindo o pareamento `users.email == staff.email`.
        """
        current_user = await AuthMiddleware.get_current_user(request)
        try:
            body = await request.json()
        except Exception:
            body = {}

        current_password = (body or {}).get('current_password') or ''
        new_email = ((body or {}).get('new_email') or '').strip().lower()
        new_password = (body or {}).get('new_password') or ''

        if not current_password:
            raise HTTPException(status_code=400, detail="Senha atual é obrigatória")
        if not new_email and not new_password:
            raise HTTPException(
                status_code=400,
                detail="Informe novo email e/ou nova senha"
            )

        # Carrega usuário com hash
        user_doc = await db.users.find_one({"id": current_user['id']}, {"_id": 0})
        if not user_doc:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")

        # Verifica senha atual
        if not verify_password(current_password, user_doc.get('password_hash', '')):
            await audit_service.log(
                action='change_account_failed',
                collection='users',
                user=current_user,
                request=request,
                document_id=current_user['id'],
                description="Tentativa de alterar conta com senha atual incorreta"
            )
            raise HTTPException(status_code=401, detail="Senha atual incorreta")

        old_email = (user_doc.get('email') or '').lower()
        update_data = {}

        # Validações e montagem do update
        if new_email and new_email != old_email:
            # Validação básica de formato (Pydantic)
            from pydantic import EmailStr, BaseModel, ValidationError
            class _EmailCheck(BaseModel):
                e: EmailStr
            try:
                _EmailCheck(e=new_email)
            except ValidationError:
                raise HTTPException(status_code=400, detail="Novo email inválido")

            # Único
            existing = await db.users.find_one(
                {"email": new_email, "id": {"$ne": current_user['id']}},
                {"_id": 0, "id": 1}
            )
            if existing:
                raise HTTPException(status_code=400, detail="Este email já está em uso")
            update_data['email'] = new_email

        if new_password:
            if len(new_password) < 6:
                raise HTTPException(
                    status_code=400,
                    detail="Nova senha deve ter pelo menos 6 caracteres"
                )
            update_data['password_hash'] = hash_password(new_password)

        if not update_data:
            return {"message": "Nada a alterar"}

        # Atualiza usuário
        await db.users.update_one(
            {"id": current_user['id']},
            {"$set": update_data}
        )

        # Sincroniza email no Staff (servidor) vinculado
        staff_synced = False
        if 'email' in update_data and old_email:
            staff_match = await db.staff.find_one(
                {"email": old_email}, {"_id": 0, "id": 1, "nome": 1}
            )
            if staff_match:
                await db.staff.update_one(
                    {"id": staff_match['id']},
                    {"$set": {"email": update_data['email']}}
                )
                staff_synced = True
                try:
                    await audit_service.log(
                        action='update',
                        collection='staff',
                        user=current_user,
                        request=request,
                        document_id=staff_match['id'],
                        description=(
                            f"Email do servidor sincronizado automaticamente "
                            f"({old_email} → {update_data['email']}) após "
                            f"alteração de conta do usuário."
                        ),
                        old_value={'email': old_email},
                        new_value={'email': update_data['email']},
                    )
                except Exception:
                    pass

        # Auditoria principal
        try:
            await audit_service.log(
                action='change_account',
                collection='users',
                user=current_user,
                request=request,
                document_id=current_user['id'],
                description=(
                    f"Usuário alterou {'email ' if 'email' in update_data else ''}"
                    f"{'e ' if len(update_data) == 2 else ''}"
                    f"{'senha' if 'password_hash' in update_data else ''}".strip()
                    + (" (staff sincronizado)" if staff_synced else "")
                ),
                old_value={'email': old_email},
                new_value={k: ('***' if k == 'password_hash' else v) for k, v in update_data.items()},
            )
        except Exception:
            pass

        return {
            "message": "Conta atualizada com sucesso",
            "email_changed": 'email' in update_data,
            "password_changed": 'password_hash' in update_data,
            "staff_synced": staff_synced,
        }

    return router
