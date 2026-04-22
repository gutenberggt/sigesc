"""
Router para Mantenedora (Unidade ativa).
Lê/escreve na coleção multi-tenant `mantenedoras`, usando o scope do usuário
(X-Mantenedora-Id do super_admin, ou mantenedora_id do próprio usuário).
"""

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
import uuid

from models import *
from auth_middleware import AuthMiddleware
from tenant_scope import get_mantenedora_scope, is_super_admin


router = APIRouter(tags=["Mantenedora"])


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências."""
    
    # Helper para obter DB correto (produção ou sandbox)
    def get_db_for_user(user: dict):
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db

    async def _resolve_active(request: Request):
        """Resolve a mantenedora ativa a partir do header/query/user scope."""
        current_user = await AuthMiddleware.get_current_user(request)
        tenant_id = get_mantenedora_scope(current_user, request)
        current_db = get_db_for_user(current_user)
        doc = None
        if tenant_id:
            doc = await current_db.mantenedoras.find_one({"id": tenant_id}, {"_id": 0})
        elif is_super_admin(current_user):
            # super_admin cross-tenant: pega a primeira (ou cria uma se não houver nenhuma)
            doc = await current_db.mantenedoras.find_one({}, {"_id": 0})
        else:
            raise HTTPException(status_code=400, detail="Usuário sem mantenedora vinculada")
        return current_user, current_db, doc, tenant_id

    @router.get("/mantenedora", response_model=Mantenedora)
    async def get_mantenedora(request: Request):
        """Busca a Unidade Mantenedora ATIVA (selecionada via TenantSwitcher)."""
        current_user, current_db, doc, tenant_id = await _resolve_active(request)
        if not doc:
            # super_admin sem tenant e sem mantenedora alguma cadastrada → cria default
            if is_super_admin(current_user) and not tenant_id:
                default_mantenedora = {
                    "id": str(uuid.uuid4()),
                    "nome": "Nova Mantenedora",
                    "cnpj": "",
                    "codigo_inep": "",
                    "natureza_juridica": "Pública Municipal",
                    "cep": "",
                    "logradouro": "",
                    "numero": "",
                    "complemento": "",
                    "bairro": "",
                    "municipio": "",
                    "estado": "PA",
                    "telefone": "",
                    "celular": "",
                    "email": "",
                    "site": "",
                    "responsavel_nome": "",
                    "responsavel_cargo": "Prefeito(a)",
                    "responsavel_cpf": "",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": None
                }
                await current_db.mantenedoras.insert_one(default_mantenedora)
                return default_mantenedora
            # Header apontando para tenant inexistente, ou usuário sem tenant
            raise HTTPException(status_code=404, detail="Mantenedora não encontrada")
        return doc


    @router.put("/mantenedora", response_model=Mantenedora)
    async def update_mantenedora(
        mantenedora_update: MantenedoraUpdate,
        request: Request
    ):
        """Atualiza a Unidade Mantenedora ATIVA"""
        current_user = await AuthMiddleware.get_current_user(request)

        # Verificar permissão (apenas admin, super_admin, gerente e semed podem editar)
        if current_user.get('role') not in ['admin', 'admin_teste', 'super_admin', 'gerente', 'semed']:
            raise HTTPException(status_code=403, detail="Sem permissão para editar a mantenedora")

        _, current_db, doc, tenant_id = await _resolve_active(request)
        if not doc:
            raise HTTPException(status_code=404, detail="Mantenedora não encontrada")

        # Atualizar campos
        update_data = mantenedora_update.model_dump(exclude_unset=True)
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        await current_db.mantenedoras.update_one(
            {"id": doc["id"]},
            {"$set": update_data}
        )

        # Retornar atualizado
        updated = await current_db.mantenedoras.find_one({"id": doc["id"]}, {"_id": 0})
        return updated



    return router
