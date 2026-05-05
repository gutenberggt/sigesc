"""
Router de Autenticação - SIGESC
Endpoints relacionados a login, logout, tokens e perfil de usuário.
"""

from fastapi import APIRouter, HTTPException, status, Request, Response
from datetime import datetime, timezone, timedelta
from typing import Optional
import os
import uuid

from models import (
    LoginRequest, TokenResponse, RefreshTokenRequest,
    UserCreate, UserUpdate, UserResponse, UserInDB, User
)
from auth_utils import (
    hash_password, verify_password, create_access_token,
    create_refresh_token, decode_token, token_blacklist,
    set_auth_cookies, clear_auth_cookies, generate_csrf_token,
    REFRESH_COOKIE_NAME, REFRESH_TOKEN_EXPIRE_DAYS,
)
from auth_middleware import AuthMiddleware

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
    async def login(credentials: LoginRequest, request: Request, response: Response):
        """Autentica usuário, retorna tokens no body E seta cookies HttpOnly."""
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
        
        csrf_token = generate_csrf_token()
        access_token = create_access_token(token_data, csrf=csrf_token)
        refresh_token = create_refresh_token({"sub": user.id})
        set_auth_cookies(
            response,
            access_token=access_token,
            refresh_token=refresh_token,
            csrf_token=csrf_token,
        )
        
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
            csrf_token=csrf_token,
            user=UserResponse(**user_response_data)
        )

    @router.post("/refresh")
    async def refresh_token(request: Request, response: Response, request_data: Optional[RefreshTokenRequest] = None):
        """Renova access + refresh tokens (rotation).

        Lê refresh de (1) cookie HttpOnly `sigesc_refresh`, (2) body legado.
        Ao sucesso: revoga o jti antigo (rotação) e emite novos tokens com novo jti.
        Seta cookies atualizados na resposta.
        """
        try:
            incoming_refresh = request.cookies.get(REFRESH_COOKIE_NAME)
            if not incoming_refresh and request_data is not None:
                incoming_refresh = request_data.refresh_token
            if not incoming_refresh:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token ausente"
                )
            payload = decode_token(incoming_refresh)
            if not payload or payload.get('type') != 'refresh':
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
            
            csrf_token = generate_csrf_token()
            new_access_token = create_access_token(token_data, csrf=csrf_token)
            new_refresh_token = create_refresh_token({"sub": user.id})
            
            # Rotação: revoga o jti antigo para impedir reuso.
            if refresh_jti:
                try:
                    token_exp = payload.get('exp')
                    exp_dt = (
                        datetime.fromtimestamp(token_exp, tz=timezone.utc)
                        if token_exp else
                        datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
                    )
                    await token_blacklist.revoke_token(
                        jti=refresh_jti,
                        user_id=user.id,
                        expires_at=exp_dt,
                        reason='refresh_rotation'
                    )
                except Exception:
                    pass
            
            csrf_token = csrf_token  # já gerado acima e embutido no JWT
            set_auth_cookies(
                response,
                access_token=new_access_token,
                refresh_token=new_refresh_token,
                csrf_token=csrf_token,
            )
            
            user_response_data = user.model_dump(exclude={'password_hash'})
            user_response_data['role'] = effective_role
            user_response_data['school_links'] = effective_school_links
            
            return TokenResponse(
                access_token=new_access_token,
                refresh_token=new_refresh_token,
                csrf_token=csrf_token,
                user=UserResponse(**user_response_data)
            )
        except HTTPException:
            raise
        except Exception:
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
        
        # [Mai/2026] CAPS lock automático removido — preserva capitalização do usuário.
        user_dict = user_data.model_dump(exclude={'password'})
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
    async def logout(request: Request, response: Response):
        """
        Revoga o refresh token atual + todos os access tokens emitidos antes
        do logout (via revoke_all_before) + limpa cookies HttpOnly.
        Em ambiente educacional (multi-device, salas compartilhadas), logout
        invalida todas as sessões do usuário — comportamento mais seguro que
        deixar access_tokens válidos até expirarem naturalmente (15min).
        """
        current_user = await AuthMiddleware.get_current_user(request)
        
        # Lê refresh_token do cookie primeiro, fallback body (retrocompat)
        refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
        if not refresh_token:
            try:
                body = await request.json()
                refresh_token = (body or {}).get('refresh_token')
            except Exception:
                refresh_token = None

        # Revoga refresh_token específico (se existir)
        if refresh_token:
            try:
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
        
        clear_auth_cookies(response)
        
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

    @router.get("/csrf-token")
    async def get_csrf_token(request: Request, response: Response):
        """Emite um novo CSRF token (cookie não-HttpOnly + body).

        Usado pelo frontend no bootstrap antes de rotas de escrita,
        ou quando o cookie CSRF expira mas a sessão ainda é válida
        (ex.: após refresh silencioso do access token).
        """
        current_user = await AuthMiddleware.get_current_user(request)
        from auth_utils import _csrf_cookie_kwargs, CSRF_COOKIE_NAME
        token = generate_csrf_token()
        response.set_cookie(CSRF_COOKIE_NAME, token, **_csrf_cookie_kwargs())
        return {"csrf_token": token, "user_id": current_user['id']}

    @router.post("/change-account")
    async def change_account(request: Request):
        """Altera o email e/ou senha do próprio usuário autenticado.

        Fluxo:
        - Senha sempre exigida (re-autenticação).
        - Mudança de **senha** é aplicada imediatamente.
        - Mudança de **email** dispara confirmação por e-mail (token 30 min).
          O email só é trocado quando o usuário clicar no link.
        - Se ambos forem enviados: senha aplicada na hora; email pendente
          de confirmação.

        Body JSON:
            {"current_password": "...", "new_email": "...", "new_password": "..."}
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

        user_doc = await db.users.find_one({"id": current_user['id']}, {"_id": 0})
        if not user_doc:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")

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

        # ---------- Validação do email novo (se houver) ----------
        email_will_request_confirmation = False
        if new_email and new_email != old_email:
            from pydantic import EmailStr, BaseModel, ValidationError
            class _EmailCheck(BaseModel):
                e: EmailStr
            try:
                _EmailCheck(e=new_email)
            except ValidationError:
                raise HTTPException(status_code=400, detail="Novo email inválido")

            existing = await db.users.find_one(
                {"email": new_email, "id": {"$ne": current_user['id']}},
                {"_id": 0, "id": 1}
            )
            if existing:
                raise HTTPException(status_code=400, detail="Este email já está em uso")

            # Bloqueio: não permite duas solicitações pendentes simultaneamente
            # para o mesmo new_email de outro usuário.
            existing_req = await db.email_change_requests.find_one(
                {"new_email": new_email, "user_id": {"$ne": current_user['id']},
                 "status": "pending"},
                {"_id": 0, "id": 1}
            )
            if existing_req:
                raise HTTPException(
                    status_code=400,
                    detail="Este email já tem uma solicitação pendente de confirmação"
                )
            email_will_request_confirmation = True

        # ---------- Aplica troca de SENHA imediatamente ----------
        password_changed = False
        if new_password:
            if len(new_password) < 6:
                raise HTTPException(
                    status_code=400,
                    detail="Nova senha deve ter pelo menos 6 caracteres"
                )
            await db.users.update_one(
                {"id": current_user['id']},
                {"$set": {"password_hash": hash_password(new_password)}}
            )
            password_changed = True
            try:
                await audit_service.log(
                    action='change_account', collection='users',
                    user=current_user, request=request,
                    document_id=current_user['id'],
                    description="Senha alterada pelo próprio usuário",
                )
            except Exception:
                pass

        # ---------- Cria token e envia e-mail de confirmação ----------
        email_pending = False
        if email_will_request_confirmation:
            from services.email_service import send_email, render_email_change_confirmation
            from datetime import datetime, timezone, timedelta

            # Invalida solicitações pendentes anteriores deste usuário
            await db.email_change_requests.update_many(
                {"user_id": current_user['id'], "status": "pending"},
                {"$set": {"status": "superseded"}}
            )

            token = uuid.uuid4().hex
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(minutes=30)
            ip = (request.client.host if request.client else '-')
            ua = request.headers.get('user-agent', '-')[:200]

            req_doc = {
                "id": str(uuid.uuid4()),
                "user_id": current_user['id'],
                "old_email": old_email,
                "new_email": new_email,
                "token": token,
                "status": "pending",
                "ip": ip,
                "user_agent": ua,
                "created_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
            }
            await db.email_change_requests.insert_one(req_doc)

            # URL que o frontend trata
            frontend_url = os.environ.get(
                'APP_FRONTEND_URL',
                'https://multi-tenant-app-30.preview.emergentagent.com'
            ).rstrip('/')
            confirm_url = f"{frontend_url}/confirm-email-change?token={token}"

            human_dt = now.strftime("%d/%m/%Y %H:%M UTC")
            html, text = render_email_change_confirmation(
                full_name=user_doc.get('full_name') or '',
                new_email=new_email,
                confirm_url=confirm_url,
                requested_at_human=human_dt,
                ip=ip,
            )
            send_result = await send_email(
                to=new_email,
                subject="Confirme a alteração do seu e-mail no SIGESC",
                html=html,
                text=text,
            )
            email_pending = bool(send_result.get('success'))
            try:
                await audit_service.log(
                    action='request_email_change', collection='users',
                    user=current_user, request=request,
                    document_id=current_user['id'],
                    description=(
                        f"Solicitação de troca de email para {new_email} enviada "
                        f"({'sucesso' if email_pending else 'falha no envio'})."
                    ),
                    new_value={'new_email': new_email, 'sent': email_pending,
                               'send_error': send_result.get('error')},
                )
            except Exception:
                pass

            if not email_pending:
                # Reverte registro pendente para evitar lixo
                await db.email_change_requests.update_one(
                    {"id": req_doc['id']},
                    {"$set": {"status": "send_failed",
                              "send_error": send_result.get('error')}}
                )
                send_err = send_result.get('error') or 'erro desconhecido'
                raise HTTPException(
                    status_code=502,
                    detail=f"Falha ao enviar e-mail de confirmação via Resend: {send_err}"
                )

        return {
            "message": "Solicitação processada",
            "password_changed": password_changed,
            "email_pending_confirmation": email_pending,
            "new_email": new_email if email_pending else None,
        }

    @router.post("/confirm-email-change")
    async def confirm_email_change(request: Request):
        """Confirma a troca de email via token enviado por e-mail.

        Body JSON: {"token": "<hex>"}
        """
        try:
            body = await request.json()
        except Exception:
            body = {}
        token = (body or {}).get('token') or ''
        if not token:
            raise HTTPException(status_code=400, detail="Token ausente")

        from datetime import datetime, timezone
        req = await db.email_change_requests.find_one({"token": token}, {"_id": 0})
        if not req:
            raise HTTPException(status_code=404, detail="Token inválido")
        if req.get('status') != 'pending':
            raise HTTPException(
                status_code=400,
                detail=f"Este link já foi usado ou cancelado (status: {req.get('status')})"
            )
        try:
            exp = datetime.fromisoformat(req.get('expires_at'))
        except Exception:
            exp = datetime.now(timezone.utc)
        if datetime.now(timezone.utc) > exp:
            await db.email_change_requests.update_one(
                {"id": req['id']}, {"$set": {"status": "expired"}}
            )
            raise HTTPException(status_code=400, detail="Link expirado")

        new_email = req['new_email']
        old_email = req.get('old_email') or ''
        user_id = req['user_id']

        # Reconfere unicidade no momento da confirmação
        clash = await db.users.find_one(
            {"email": new_email, "id": {"$ne": user_id}},
            {"_id": 0, "id": 1}
        )
        if clash:
            await db.email_change_requests.update_one(
                {"id": req['id']}, {"$set": {"status": "conflict"}}
            )
            raise HTTPException(status_code=400, detail="Este email já está em uso")

        # Aplica
        await db.users.update_one({"id": user_id}, {"$set": {"email": new_email}})

        # Sincroniza staff por email antigo
        staff_synced = False
        if old_email:
            staff = await db.staff.find_one({"email": old_email}, {"_id": 0, "id": 1})
            if staff:
                await db.staff.update_one(
                    {"id": staff['id']}, {"$set": {"email": new_email}}
                )
                staff_synced = True

        await db.email_change_requests.update_one(
            {"id": req['id']},
            {"$set": {"status": "confirmed",
                      "confirmed_at": datetime.now(timezone.utc).isoformat(),
                      "staff_synced": staff_synced}}
        )

        try:
            user_doc = await db.users.find_one({"id": user_id}, {"_id": 0, "id": 1, "email": 1, "role": 1})
            await audit_service.log(
                action='confirm_email_change', collection='users',
                user=user_doc or {'id': user_id, 'email': new_email, 'role': 'unknown'},
                request=request,
                document_id=user_id,
                description=(
                    f"Email confirmado e alterado de {old_email} para {new_email}"
                    + (" (staff sincronizado)" if staff_synced else "")
                ),
                old_value={'email': old_email},
                new_value={'email': new_email, 'staff_synced': staff_synced},
            )
        except Exception:
            pass

        return {
            "message": "Email atualizado com sucesso",
            "new_email": new_email,
            "staff_synced": staff_synced,
        }

    @router.post("/resend-email-change")
    async def resend_email_change(request: Request):
        """Reenvia o e-mail de confirmação (gera novo token de 30min)
        para a solicitação pendente do usuário autenticado."""
        current_user = await AuthMiddleware.get_current_user(request)

        from datetime import datetime, timezone, timedelta
        # Busca a última solicitação pendente OU expirada do usuário
        req = await db.email_change_requests.find_one(
            {"user_id": current_user['id'],
             "status": {"$in": ["pending", "expired", "send_failed"]}},
            {"_id": 0},
            sort=[("created_at", -1)]
        )
        if not req:
            raise HTTPException(
                status_code=404,
                detail="Nenhuma solicitação de troca de email para reenviar"
            )

        new_email = req['new_email']

        # Reconfere unicidade
        clash = await db.users.find_one(
            {"email": new_email, "id": {"$ne": current_user['id']}},
            {"_id": 0, "id": 1}
        )
        if clash:
            await db.email_change_requests.update_one(
                {"id": req['id']}, {"$set": {"status": "conflict"}}
            )
            raise HTTPException(status_code=400, detail="Este email já está em uso")

        # Marca a antiga como superseded e cria nova
        await db.email_change_requests.update_one(
            {"id": req['id']}, {"$set": {"status": "superseded"}}
        )

        token = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=30)
        ip = (request.client.host if request.client else '-')
        ua = request.headers.get('user-agent', '-')[:200]

        new_req = {
            "id": str(uuid.uuid4()),
            "user_id": current_user['id'],
            "old_email": req.get('old_email'),
            "new_email": new_email,
            "token": token,
            "status": "pending",
            "ip": ip,
            "user_agent": ua,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "resent_from": req['id'],
        }
        await db.email_change_requests.insert_one(new_req)

        from services.email_service import send_email, render_email_change_confirmation
        frontend_url = os.environ.get(
            'APP_FRONTEND_URL',
            'https://multi-tenant-app-30.preview.emergentagent.com'
        ).rstrip('/')
        confirm_url = f"{frontend_url}/confirm-email-change?token={token}"

        user_doc = await db.users.find_one({"id": current_user['id']}, {"_id": 0, "full_name": 1})
        html, text = render_email_change_confirmation(
            full_name=(user_doc or {}).get('full_name') or '',
            new_email=new_email,
            confirm_url=confirm_url,
            requested_at_human=now.strftime("%d/%m/%Y %H:%M UTC"),
            ip=ip,
        )
        send_result = await send_email(
            to=new_email,
            subject="Confirme a alteração do seu e-mail no SIGESC",
            html=html,
            text=text,
        )
        if not send_result.get('success'):
            await db.email_change_requests.update_one(
                {"id": new_req['id']},
                {"$set": {"status": "send_failed",
                          "send_error": send_result.get('error')}}
            )
            send_err = send_result.get('error') or 'erro desconhecido'
            raise HTTPException(
                status_code=502,
                detail=f"Falha ao reenviar e-mail via Resend: {send_err}"
            )

        return {"message": "E-mail de confirmação reenviado", "new_email": new_email}

    return router
