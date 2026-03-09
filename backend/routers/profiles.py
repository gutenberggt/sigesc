"""
Router para Perfis.
Extraído automaticamente de server.py.
"""

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
import uuid
import re

from models import *
from auth_middleware import AuthMiddleware


router = APIRouter(tags=["Perfis"])


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências."""
    
    # Helper para obter DB correto (produção ou sandbox)
    def get_db_for_user(user: dict):
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db



    @router.get("/profiles/me")
    async def get_my_profile(request: Request):
        """Retorna o perfil do usuário logado"""
        current_user = await AuthMiddleware.get_current_user(request)

        # Busca dados completos do usuário no banco
        user_data = await db.users.find_one({"id": current_user['id']}, {"_id": 0, "password_hash": 0})

        profile = await db.user_profiles.find_one({"user_id": current_user['id']}, {"_id": 0})

        if not profile:
            # Criar perfil automaticamente se não existir
            profile = {
                "id": str(uuid.uuid4()),
                "user_id": current_user['id'],
                "headline": None,
                "sobre": None,
                "localizacao": None,
                "telefone": None,
                "website": None,
                "linkedin_url": None,
                "foto_capa_url": None,
                "foto_url": user_data.get('avatar_url') if user_data else None,
                "is_public": True,
                "experiencias": [],
                "formacoes": [],
                "competencias": [],
                "certificacoes": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": None
            }
            await db.user_profiles.insert_one(profile)
            profile.pop('_id', None)

        # Adicionar dados do usuário
        profile['user'] = {
            'id': current_user['id'],
            'full_name': user_data.get('full_name', '') if user_data else '',
            'email': user_data.get('email', '') if user_data else current_user.get('email', ''),
            'role': user_data.get('role', '') if user_data else current_user.get('role', '')
        }

        return profile


    @router.get("/profiles/search")
    async def search_public_profiles(q: str = "", request: Request = None):
        """Busca perfis públicos pelo nome do usuário (mínimo 3 caracteres)"""
        # Validar mínimo de 3 caracteres
        if len(q) < 3:
            return []

        # Buscar usuários cujo nome começa com a query (case insensitive)
        import re
        regex_pattern = f"^{re.escape(q)}"

        users = await db.users.find(
            {"full_name": {"$regex": regex_pattern, "$options": "i"}},
            {"_id": 0, "password_hash": 0}
        ).to_list(20)

        results = []
        for user in users:
            # Verificar se o perfil é público
            profile = await db.user_profiles.find_one({"user_id": user['id']}, {"_id": 0})

            # Se não tem perfil, considera como público (padrão)
            is_public = True
            if profile:
                is_public = profile.get('is_public', True)

            if is_public:
                results.append({
                    "user_id": user['id'],
                    "full_name": user.get('full_name', ''),
                    "email": user.get('email', ''),
                    "role": user.get('role', ''),
                    "headline": profile.get('headline') if profile else None,
                    "foto_url": profile.get('foto_url') if profile else user.get('avatar_url')
                })

        return results


    @router.get("/profiles/{user_id}")
    async def get_profile_by_user_id(user_id: str, request: Request):
        """Retorna o perfil de um usuário específico"""
        current_user = None
        try:
            current_user = await AuthMiddleware.get_current_user(request)
        except:
            pass

        profile = await db.user_profiles.find_one({"user_id": user_id}, {"_id": 0})

        if not profile:
            # Buscar usuário para criar perfil
            user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
            if not user:
                raise HTTPException(status_code=404, detail="Usuário não encontrado")

            # Criar perfil automaticamente
            profile = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "headline": None,
                "sobre": None,
                "localizacao": None,
                "telefone": None,
                "website": None,
                "linkedin_url": None,
                "foto_capa_url": None,
                "foto_url": user.get('avatar_url'),
                "is_public": True,
                "experiencias": [],
                "formacoes": [],
                "competencias": [],
                "certificacoes": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": None
            }
            await db.user_profiles.insert_one(profile)
            profile.pop('_id', None)
        else:
            # Verificar visibilidade
            is_owner = current_user and current_user['id'] == user_id
            is_admin = current_user and current_user.get('role') == 'admin'

            if not profile.get('is_public', True) and not is_owner and not is_admin:
                raise HTTPException(status_code=403, detail="Este perfil é privado")

        # Buscar dados do usuário
        user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
        if user:
            profile['user'] = {
                'id': user['id'],
                'full_name': user.get('full_name', ''),
                'email': user.get('email', ''),
                'role': user.get('role', '')
            }

        return profile


    @router.put("/profiles/me")
    async def update_my_profile(profile_data: UserProfileUpdate, request: Request):
        """Atualiza o perfil do usuário logado"""
        current_user = await AuthMiddleware.get_current_user(request)

        # Verificar se perfil existe
        profile = await db.user_profiles.find_one({"user_id": current_user['id']})

        update_data = profile_data.model_dump(exclude_unset=True)
        update_data['updated_at'] = datetime.now(timezone.utc).isoformat()

        if not profile:
            # Criar perfil se não existir
            new_profile = {
                "id": str(uuid.uuid4()),
                "user_id": current_user['id'],
                "headline": None,
                "sobre": None,
                "localizacao": None,
                "telefone": None,
                "website": None,
                "linkedin_url": None,
                "foto_capa_url": None,
                "foto_url": current_user.get('avatar_url'),
                "is_public": True,
                "experiencias": [],
                "formacoes": [],
                "competencias": [],
                "certificacoes": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
                **update_data
            }
            await db.user_profiles.insert_one(new_profile)
            new_profile.pop('_id', None)
            return new_profile

        await db.user_profiles.update_one(
            {"user_id": current_user['id']},
            {"$set": update_data}
        )

        updated_profile = await db.user_profiles.find_one({"user_id": current_user['id']}, {"_id": 0})
        return updated_profile


    @router.put("/profiles/{user_id}")
    async def update_profile_by_admin(user_id: str, profile_data: UserProfileUpdate, request: Request):
        """Admin pode atualizar perfil de qualquer usuário"""
        current_user = await AuthMiddleware.require_roles(['admin'])(request)

        # Verificar se perfil existe
        profile = await db.user_profiles.find_one({"user_id": user_id})

        update_data = profile_data.model_dump(exclude_unset=True)
        update_data['updated_at'] = datetime.now(timezone.utc).isoformat()

        if not profile:
            # Verificar se usuário existe
            user = await db.users.find_one({"id": user_id})
            if not user:
                raise HTTPException(status_code=404, detail="Usuário não encontrado")

            # Criar perfil
            new_profile = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "headline": None,
                "sobre": None,
                "localizacao": None,
                "telefone": None,
                "website": None,
                "linkedin_url": None,
                "foto_capa_url": None,
                "foto_url": user.get('avatar_url'),
                "is_public": True,
                "experiencias": [],
                "formacoes": [],
                "competencias": [],
                "certificacoes": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
                **update_data
            }
            await db.user_profiles.insert_one(new_profile)
            new_profile.pop('_id', None)
            return new_profile

        await db.user_profiles.update_one(
            {"user_id": user_id},
            {"$set": update_data}
        )

        updated_profile = await db.user_profiles.find_one({"user_id": user_id}, {"_id": 0})
        return updated_profile



    return router
