"""
Router CTUE — Conformidade da Unidade Escolar (SSoT).
Expõe o resultado do CTUEConformityService. Nenhuma regra recalculada aqui.
"""
from fastapi import APIRouter, Request
from typing import Optional

from utils.cache import cache, CACHE_TTL_SCHOOLS
from auth_middleware import AuthMiddleware
from tenant_scope import apply_tenant_filter, get_mantenedora_scope, assert_same_tenant
from services import ctue_conformity_service as ctue

router = APIRouter(prefix="/ctue", tags=["CTUE"])


def setup_router(db, audit_service, sandbox_db=None):
    def get_db_for_user(user: dict):
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db

    @router.get("/profiles")
    async def list_profiles(request: Request):
        await AuthMiddleware.get_current_user(request)
        return {"profiles": ctue.get_profiles()}

    @router.get("/schools/{school_id}/conformity")
    async def school_conformity(school_id: str, request: Request, profile: str = "default"):
        current_user = await AuthMiddleware.verify_school_access(request, school_id)
        current_db = get_db_for_user(current_user)
        school = await current_db.schools.find_one({"id": school_id}, {"_id": 0})
        if not school:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Escola não encontrada")
        assert_same_tenant(school, current_user, request)
        return ctue.evaluate(school, profile=profile)

    @router.get("/conformity-overview")
    async def conformity_overview(request: Request, profile: str = "default"):
        """Lista resumida (mini-cards) de todas as escolas no escopo do usuário."""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)

        wide_roles = ['admin', 'admin_teste', 'super_admin', 'gerente', 'semed', 'semed1',
                      'semed2', 'semed3', 'ass_social', 'ass_social_2', 'agente_vacinas']
        base_filter = {}
        if current_user['role'] not in wide_roles:
            base_filter = {"id": {"$in": current_user.get('school_ids', [])}}
        query = apply_tenant_filter(base_filter, current_user, request)

        schools = await current_db.schools.find(query, {"_id": 0}).to_list(1000)
        overview = [ctue.summarize(s, profile=profile) for s in schools]
        return {"profile": profile, "count": len(overview), "schools": overview}

    @router.get("/network-panel")
    async def network_panel(request: Request, profile: str = "default"):
        """Painel Gerencial da Rede (Centro de Inteligência) — tudo derivado do SSoT.
        Cache transparente invalidado automaticamente quando o CTUE de qualquer escola muda."""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)

        wide_roles = ['admin', 'admin_teste', 'super_admin', 'gerente', 'semed', 'semed1',
                      'semed2', 'semed3', 'ass_social', 'ass_social_2', 'agente_vacinas']
        base_filter = {}
        if current_user['role'] not in wide_roles:
            base_filter = {"id": {"$in": current_user.get('school_ids', [])}}
        query = apply_tenant_filter(base_filter, current_user, request)

        tenant_id = get_mantenedora_scope(current_user, request)
        cache_params = {
            'role': current_user['role'],
            'school_ids': sorted(current_user.get('school_ids', [])),
            'tenant': tenant_id or 'ALL', 'profile': profile,
        }
        cached = cache.get('ctue', cache_params)
        if cached is not None:
            return cached

        schools = await current_db.schools.find(query, {"_id": 0}).to_list(2000)
        panel = ctue.build_network_panel(schools, profile=profile)
        cache.set('ctue', cache_params, panel, CACHE_TTL_SCHOOLS)
        return panel

    return router
