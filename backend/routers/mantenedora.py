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
        """Resolve a mantenedora ativa a partir do header/query/user scope.
        
        Robusto: em caso de usuário legado sem mantenedora_id, usa a primeira
        mantenedora cadastrada como fallback. Nunca levanta 500 — apenas 400/404
        com mensagem clara.
        """
        current_user = await AuthMiddleware.get_current_user(request)
        tenant_id = get_mantenedora_scope(current_user, request)
        current_db = get_db_for_user(current_user)
        doc = None
        try:
            if tenant_id:
                doc = await current_db.mantenedoras.find_one({"id": tenant_id}, {"_id": 0})
                # Fallback: tenant_id inválido ou não encontrado → usa primeira mantenedora
                if not doc:
                    doc = await current_db.mantenedoras.find_one({}, {"_id": 0})
                    if doc:
                        tenant_id = doc.get("id")
            else:
                # Sem tenant_id (super_admin cross-tenant OU user legado sem mantenedora_id)
                doc = await current_db.mantenedoras.find_one({}, {"_id": 0})
                if doc:
                    tenant_id = doc.get("id")
                    # Auto-heal: se o user não é super_admin e não tem mantenedora_id, vincula
                    if (not is_super_admin(current_user)
                            and not current_user.get("mantenedora_id")
                            and current_user.get("id")):
                        try:
                            await current_db.users.update_one(
                                {"id": current_user["id"]},
                                {"$set": {"mantenedora_id": tenant_id}},
                            )
                        except Exception:
                            pass
        except HTTPException:
            raise
        except Exception:
            doc = None
        return current_user, current_db, doc, tenant_id

    @router.get("/mantenedora")
    async def get_mantenedora(request: Request):
        """Busca a Unidade Mantenedora ATIVA (selecionada via TenantSwitcher).
        
        Sem response_model para evitar erros de validação Pydantic em docs legados
        (produção pode ter campos faltantes ou tipos divergentes).
        """
        current_user, current_db, doc, tenant_id = await _resolve_active(request)
        if not doc:
            # Nenhuma mantenedora no banco → cria default automaticamente
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
                "updated_at": None,
            }
            try:
                await current_db.mantenedoras.insert_one(dict(default_mantenedora))
            except Exception:
                pass
            return default_mantenedora
        return doc


    @router.put("/mantenedora")
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


    @router.get("/mantenedora/_diag")
    async def diag_mantenedora(request: Request):
        """Endpoint de diagnóstico: retorna info sem response_model.
        Útil para debugar em produção quando /api/mantenedora falha.
        """
        try:
            current_user = await AuthMiddleware.get_current_user(request)
        except Exception as e:
            return {"auth_ok": False, "error": str(e)}
        try:
            current_db = get_db_for_user(current_user)
            total = await current_db.mantenedoras.count_documents({})
            first = await current_db.mantenedoras.find_one({}, {"_id": 0, "id": 1, "nome": 1})
            return {
                "auth_ok": True,
                "user_email": current_user.get("email"),
                "user_role": current_user.get("role"),
                "user_is_primary": current_user.get("is_primary", False),
                "user_mantenedora_id": current_user.get("mantenedora_id"),
                "mantenedoras_count": total,
                "first_mantenedora": first,
                "is_super_admin": is_super_admin(current_user),
                "scope_tenant_id": get_mantenedora_scope(current_user, request),
            }
        except Exception as e:
            return {"auth_ok": True, "db_error": str(e)}


    @router.post("/mantenedora/_heal")
    async def heal_mantenedora(request: Request):
        """Executa migração self-heal SOB DEMANDA. 
        
        Disponível para qualquer usuário autenticado, MAS:
        - Só promove o user atual a super_admin se AINDA NÃO existir nenhum super_admin
          no sistema (bootstrap-once).
        - Backfill de mantenedora_id em todas as coleções é sempre executado (idempotente).
        
        Retorna relatório do que foi feito.
        """
        try:
            current_user = await AuthMiddleware.get_current_user(request)
        except Exception as e:
            raise HTTPException(status_code=401, detail=str(e))
        
        current_db = get_db_for_user(current_user)
        report = {"user_email": current_user.get("email"), "actions": []}
        
        # 1. Verifica se já existe super_admin
        try:
            existing_super = await current_db.users.find_one(
                {"$or": [{"role": "super_admin"}, {"roles": "super_admin"}]},
                {"_id": 0, "id": 1, "email": 1},
            )
        except Exception as e:
            existing_super = None
            report["actions"].append(f"erro ao verificar super_admin: {e}")
        
        # 2. Se não há super_admin, promove o user ATUAL (self-bootstrap)
        if not existing_super and current_user.get("id"):
            try:
                await current_db.users.update_one(
                    {"id": current_user["id"]},
                    {"$set": {"role": "super_admin", "is_primary": True}},
                )
                report["actions"].append(
                    f"{current_user.get('email')} promovido a super_admin + is_primary=True"
                )
            except Exception as e:
                report["actions"].append(f"erro ao promover user: {e}")
        elif existing_super:
            report["actions"].append(
                f"super_admin já existe ({existing_super.get('email')}); pulando promoção"
            )
        
        # 3. Garante que há pelo menos uma mantenedora
        try:
            total_mant = await current_db.mantenedoras.count_documents({})
        except Exception as e:
            total_mant = 0
            report["actions"].append(f"erro ao contar mantenedoras: {e}")
        
        if total_mant == 0:
            new_mant = {
                "id": str(uuid.uuid4()),
                "nome": "Mantenedora Principal",
                "cnpj": "",
                "codigo_inep": "",
                "natureza_juridica": "Pública Municipal",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                await current_db.mantenedoras.insert_one(dict(new_mant))
                report["actions"].append(f"mantenedora default criada (id={new_mant['id']})")
            except Exception as e:
                report["actions"].append(f"erro ao criar mantenedora default: {e}")
        
        # 4. Pega a primeira mantenedora para backfill
        first_mant = None
        try:
            first_mant = await current_db.mantenedoras.find_one({}, {"_id": 0})
        except Exception as e:
            report["actions"].append(f"erro ao buscar mantenedora: {e}")
        
        if not first_mant:
            report["actions"].append("ABORTADO: nenhuma mantenedora disponível para backfill")
            return report
        
        mant_id = first_mant.get("id")
        report["mantenedora_id"] = mant_id
        report["mantenedora_nome"] = first_mant.get("nome")
        
        # 5. Backfill mantenedora_id em todas as coleções tenant-scoped
        total_healed = 0
        healed_detail = {}
        for coll in ("schools", "staff", "students", "classes", "courses",
                     "enrollments", "grades", "learning_objects", "calendar_events",
                     "calendario_letivo", "school_assignments", "teacher_assignments",
                     "payroll_items", "announcements", "users", "pre_matriculas",
                     "mantenedora_documentos"):
            try:
                res = await current_db[coll].update_many(
                    {"$or": [
                        {"mantenedora_id": {"$exists": False}},
                        {"mantenedora_id": None},
                        {"mantenedora_id": ""},
                    ]},
                    {"$set": {"mantenedora_id": mant_id}},
                )
                if res.modified_count:
                    total_healed += res.modified_count
                    healed_detail[coll] = res.modified_count
            except Exception as e:
                healed_detail[coll] = f"erro: {e}"
        
        report["backfill_total"] = total_healed
        report["backfill_detail"] = healed_detail
        report["actions"].append(f"backfill mantenedora_id: {total_healed} docs migrados")
        
        return report



    return router
