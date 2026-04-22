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
        """
        user = await AuthMiddleware.get_current_user(request)
        if not is_super_admin(user):
            raise HTTPException(status_code=403, detail="Apenas super_admin pode designar gerente")
        body = await request.json()
        user_id = body.get('user_id')
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id é obrigatório")
        target = await db.users.find_one({"id": user_id})
        if not target:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        mantenedora = await db.mantenedoras.find_one({"id": mid})
        if not mantenedora:
            raise HTTPException(status_code=404, detail="Mantenedora não encontrada")
        await db.users.update_one(
            {"id": user_id},
            {"$set": {"role": "gerente", "mantenedora_id": mid}}
        )
        return {"success": True, "user_id": user_id, "mantenedora_id": mid}

    return router
