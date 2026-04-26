"""
Router para gestão de Mantenedoras (multi-tenant).

⚠️  LEIA /app/backend/tenant_scope.py ANTES DE ADICIONAR ENDPOINTS AQUI  ⚠️

Endpoints:
  - GET    /mantenedoras              → lista (super_admin vê tudo; outros veem apenas a própria)
  - GET    /mantenedoras/{id}         → detalhe
  - POST   /mantenedoras              → cria (super_admin only)
  - PUT    /mantenedoras/{id}         → atualiza (super_admin ou gerente da própria)
  - DELETE /mantenedoras/{id}         → exclui (super_admin only) — só se vazia
  - POST   /mantenedoras/{id}/gerente → designa gerente (super_admin only)
  - GET    /mantenedoras/me           → a mantenedora do usuário logado
"""
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
import uuid
from models import Mantenedora, MantenedoraBase, MantenedoraUpdate
from auth_middleware import AuthMiddleware
from tenant_scope import is_super_admin, get_user_mantenedora_id


def create_mantenedoras_router(db):
    router = APIRouter(prefix="/api", tags=["Mantenedoras"])

    @router.get("/mantenedoras")
    async def list_mantenedoras(request: Request):
        user = await AuthMiddleware.get_current_user(request)
        if is_super_admin(user):
            docs = await db.mantenedoras.find({}, {"_id": 0}).sort("name", 1).to_list(500)
        else:
            mid = get_user_mantenedora_id(user)
            if not mid:
                return []
            docs = await db.mantenedoras.find({"id": mid}, {"_id": 0}).to_list(1)
        return docs

    @router.get("/mantenedoras/me")
    async def my_mantenedora(request: Request):
        user = await AuthMiddleware.get_current_user(request)
        mid = get_user_mantenedora_id(user)
        if not mid:
            return None
        return await db.mantenedoras.find_one({"id": mid}, {"_id": 0})

    @router.get("/mantenedoras/{mid}")
    async def get_mantenedora(mid: str, request: Request):
        user = await AuthMiddleware.get_current_user(request)
        if not is_super_admin(user) and get_user_mantenedora_id(user) != mid:
            raise HTTPException(status_code=403, detail="Acesso restrito")
        doc = await db.mantenedoras.find_one({"id": mid}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Mantenedora não encontrada")
        return doc

    @router.post("/mantenedoras")
    async def create_mantenedora(data: MantenedoraBase, request: Request):
        user = await AuthMiddleware.get_current_user(request)
        if not is_super_admin(user):
            raise HTTPException(status_code=403, detail="Apenas super_admin pode criar mantenedoras")
        nova = Mantenedora(**data.model_dump())
        await db.mantenedoras.insert_one(nova.model_dump())
        return await db.mantenedoras.find_one({"id": nova.id}, {"_id": 0})

    @router.put("/mantenedoras/{mid}")
    async def update_mantenedora(mid: str, data: MantenedoraUpdate, request: Request):
        user = await AuthMiddleware.get_current_user(request)
        can = is_super_admin(user) or (user.get('role') == 'gerente' and get_user_mantenedora_id(user) == mid)
        if not can:
            raise HTTPException(status_code=403, detail="Sem permissão para alterar esta mantenedora")
        existing = await db.mantenedoras.find_one({"id": mid})
        if not existing:
            raise HTTPException(status_code=404, detail="Mantenedora não encontrada")
        update = {k: v for k, v in data.model_dump().items() if v is not None}
        update['updated_at'] = datetime.now(timezone.utc)
        await db.mantenedoras.update_one({"id": mid}, {"$set": update})
        return await db.mantenedoras.find_one({"id": mid}, {"_id": 0})

    @router.delete("/mantenedoras/{mid}")
    async def delete_mantenedora(mid: str, request: Request):
        user = await AuthMiddleware.get_current_user(request)
        if not is_super_admin(user):
            raise HTTPException(status_code=403, detail="Apenas super_admin pode excluir")
        # Só permitir exclusão se não houver escolas vinculadas
        schools_count = await db.schools.count_documents({"mantenedora_id": mid})
        if schools_count > 0:
            raise HTTPException(status_code=400, detail=f"Não é possível excluir: existem {schools_count} escolas vinculadas")
        await db.mantenedoras.delete_one({"id": mid})
        return {"success": True}

    @router.post("/mantenedoras/{mid}/gerente")
    async def designar_gerente(mid: str, request: Request):
        """Designa um usuário como gerente desta mantenedora.
        Body JSON esperado: {"user_id": "..."}.
        Apenas super_admin pode designar.

        Side effects (segurança multi-tenant):
          1. role/mantenedora_id atualizados.
          2. school_links/school_ids são filtrados para conter apenas escolas
             que pertencem à nova mantenedora (evita vazamento cross-tenant
             quando o user já era admin/staff de outra mantenedora).
          3. Todas as sessões ativas do usuário são revogadas — força novo
             login para que o próximo JWT contenha mantenedora_id correto.
             Sem isso, tokens emitidos antes da designação continuariam
             trazendo mantenedora_id antigo no payload, fazendo
             apply_tenant_filter retornar dados da mantenedora errada.
        """
        from auth_utils import token_blacklist
        user = await AuthMiddleware.get_current_user(request)
        if not is_super_admin(user):
            raise HTTPException(status_code=403, detail="Apenas super_admin pode designar gerente")
        body = await request.json()
        user_id = body.get('user_id')
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id é obrigatório")
        target = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not target:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        mantenedora = await db.mantenedoras.find_one({"id": mid})
        if not mantenedora:
            raise HTTPException(status_code=404, detail="Mantenedora não encontrada")

        # Coleta todas as escolas atualmente vinculadas ao user
        old_school_ids = set(target.get('school_ids') or [])
        for link in (target.get('school_links') or []):
            sid = link.get('school_id') if isinstance(link, dict) else None
            if sid:
                old_school_ids.add(sid)

        # Filtra para manter apenas escolas que pertencem à nova mantenedora
        kept_ids = set()
        if old_school_ids:
            schools_in_new = await db.schools.find(
                {"id": {"$in": list(old_school_ids)}, "mantenedora_id": mid},
                {"_id": 0, "id": 1}
            ).to_list(None)
            kept_ids = {s['id'] for s in schools_in_new}

        new_school_links = [
            link for link in (target.get('school_links') or [])
            if isinstance(link, dict) and link.get('school_id') in kept_ids
        ]
        new_school_ids = [s for s in (target.get('school_ids') or []) if s in kept_ids]

        await db.users.update_one(
            {"id": user_id},
            {"$set": {
                "role": "gerente",
                "mantenedora_id": mid,
                "school_links": new_school_links,
                "school_ids": new_school_ids,
            }}
        )

        # Revoga todas as sessões ativas do user → força relogin com novo JWT
        await token_blacklist.revoke_all_user_tokens(
            user_id=user_id,
            reason=f'designar_gerente_to_mantenedora_{mid}'
        )

        # Audit log
        try:
            from services.audit_service import audit_service
            await audit_service.log(
                action='designar_gerente',
                collection='users',
                user=user,
                request=request,
                document_id=user_id,
                description=(
                    f"Designou {target.get('full_name')} ({target.get('email')}) como "
                    f"gerente de '{mantenedora.get('name', mid)}'. "
                    f"School_links removidos (cross-tenant): {len(old_school_ids) - len(kept_ids)}. "
                    f"Tokens antigos revogados."
                ),
                old_value={
                    'role': target.get('role'),
                    'mantenedora_id': target.get('mantenedora_id'),
                    'school_links_count': len(target.get('school_links') or []),
                },
                new_value={
                    'role': 'gerente',
                    'mantenedora_id': mid,
                    'school_links_count': len(new_school_links),
                },
            )
        except Exception:
            pass

        return {
            "success": True,
            "user_id": user_id,
            "mantenedora_id": mid,
            "school_links_kept": len(new_school_links),
            "school_links_removed_cross_tenant": len(old_school_ids) - len(kept_ids),
        }

    return router
