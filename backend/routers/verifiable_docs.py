"""Router: Verifiable Documents — Portal Público + Admin (G1.6 — Fev/2026).

Endpoints:
  Público (SEM auth, com rate limit):
    GET  /api/public/verify/{code}     — consulta LGPD-safe, 3 estados

  Autenticado:
    GET  /api/documents                — lista (escopo por role)
    GET  /api/documents/{code}         — detalhes (com permissão)
    POST /api/documents/{code}/revoke  — revoga (super_admin/admin/secretario)
    POST /api/documents/ensure-for-snapshot/{snapshot_id}
                                        — gera sob demanda (retroativo)
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Query

from auth_middleware import AuthMiddleware
from services import verifiable_docs_service as vsvc
from services import snapshot_service as snap_svc

logger = logging.getLogger(__name__)


_ADMIN_ROLES = ("super_admin", "admin", "admin_teste", "gerente", "secretario")


def setup_router(db, limiter=None):
    public = APIRouter(prefix="/public", tags=["Portal Público"])
    admin = APIRouter(prefix="/documents", tags=["Documentos Verificáveis"])

    # ------------------ PORTAL PÚBLICO (sem auth) ------------------

    async def _public_verify_impl(code_or_token: str):
        # Aceita verification_token (UUID hex 32 chars) OU code (SIGESC-XXXX-XXXX).
        doc = await vsvc.resolve_either(db, code_or_token)
        resp = vsvc.build_portal_response(doc)
        # Se tem snapshot_id associado e status "valido", revalida o hash de verdade
        if resp.get("status") == "valido" and doc and doc.get("snapshot_id"):
            snap = await db.ai_analysis_snapshots.find_one(
                {"id": doc["snapshot_id"]}, {"_id": 0, "expires_at_dt": 0}
            )
            if not snap:
                # Snapshot removido — invalida o documento
                return {
                    "status": "invalido",
                    "codigo": resp.get("codigo"),
                    "verification_token": resp.get("verification_token"),
                    "mensagem": "Documento não encontrado no repositório.",
                }
            integrity = snap_svc.verify_snapshot_integrity(snap)
            if not integrity["valid"]:
                resp["status"] = "invalido"
                resp["integridade"] = "alterada" if not integrity["hash_valid"] else "confirmada"
                resp["assinatura_valida"] = integrity["signature_valid"]
                resp["mensagem"] = (
                    "A integridade deste documento não pôde ser confirmada — "
                    "ele pode ter sido alterado após a emissão."
                )
        return resp

    if limiter is not None:
        @public.get("/verify/{code}")
        @limiter.limit("20/minute")
        async def public_verify(code: str, request: Request):
            return await _public_verify_impl(code)
    else:
        @public.get("/verify/{code}")
        async def public_verify(code: str, request: Request):
            return await _public_verify_impl(code)

    # ------------------ ADMIN (autenticado) ------------------

    async def _require_admin(request: Request) -> dict:
        user = await AuthMiddleware.get_current_user(request)
        role = user.get("role")
        # diretor também pode listar/gerar sob demanda (mas revogar só admin/secretario)
        if role not in ("super_admin", "admin", "admin_teste", "gerente", "secretario", "diretor"):
            raise HTTPException(403, "Acesso restrito")
        return user

    def _apply_list_scope(user: dict, filt: dict) -> dict:
        scope = snap_svc.get_scope_for_user(user)
        if scope is None:
            raise HTTPException(403, "Sem escopo de acesso")
        if "mantenedora_id" in scope:
            filt["mantenedora_id"] = scope["mantenedora_id"]
        if "entity_ids" in scope:
            ids = scope["entity_ids"]
            if "entity_id" in filt and filt["entity_id"] not in ids:
                raise HTTPException(403, "Fora do seu escopo")
            if "entity_id" not in filt:
                filt["entity_id"] = {"$in": ids}
        return filt

    @admin.get("")
    async def list_documents(
        request: Request,
        type: Optional[str] = None,
        entity_id: Optional[str] = None,
        include_revoked: bool = False,
        limit: int = Query(50, le=200),
    ):
        user = await _require_admin(request)
        filt: dict = {}
        if type:
            filt["type"] = type
        if entity_id:
            filt["entity_id"] = entity_id
        if not include_revoked:
            filt["revoked"] = False
        filt = _apply_list_scope(user, filt)

        cursor = db.verifiable_documents.find(
            filt,
            {"_id": 0, "code": 1, "type": 1, "entity_id": 1, "entity_type": 1,
             "public_hash": 1, "snapshot_id": 1, "created_at": 1,
             "revoked": 1, "revoked_at": 1, "issued_by": 1,
             "public_metadata": 1}
        ).sort("created_at", -1).limit(limit)
        items = await cursor.to_list(length=limit)
        return {"items": items, "total": len(items)}

    @admin.get("/{code}")
    async def get_document(code: str, request: Request):
        user = await _require_admin(request)
        normalized = vsvc.normalize_code(code)
        if not normalized:
            raise HTTPException(400, "Código inválido")
        doc = await db.verifiable_documents.find_one({"code": normalized}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Documento não encontrado")
        scope = snap_svc.get_scope_for_user(user)
        if scope is None:
            raise HTTPException(403, "Sem escopo")
        if "mantenedora_id" in scope and scope["mantenedora_id"] != doc.get("mantenedora_id"):
            raise HTTPException(403, "Fora do seu escopo")
        if "entity_ids" in scope and doc.get("entity_id") not in scope["entity_ids"]:
            raise HTTPException(403, "Fora do seu escopo")
        return doc

    @admin.post("/{code}/revoke")
    async def revoke_document_endpoint(code: str, request: Request):
        user = await _require_admin(request)
        # Apenas admin/super_admin/secretario revogam
        if user.get("role") not in _ADMIN_ROLES:
            raise HTTPException(403, "Apenas admin/secretario pode revogar")
        body = {}
        try:
            body = await request.json()
        except Exception:
            pass
        reason = (body or {}).get("reason") or "Revogação administrativa"
        try:
            r = await vsvc.revoke_document(db, code=code, reason=reason, user=user)
        except KeyError:
            raise HTTPException(404, "Documento não encontrado")
        except ValueError as e:
            raise HTTPException(400, str(e))
        return r

    @admin.post("/ensure-for-snapshot/{snapshot_id}")
    async def ensure_for_snapshot(snapshot_id: str, request: Request):
        """Gera código verificável retroativamente para um snapshot antigo (opção C).

        Uso: quando alguém precisa de PDF auditável + QR de um snapshot pré-G1.6.
        """
        user = await _require_admin(request)
        snap = await db.ai_analysis_snapshots.find_one(
            {"id": snapshot_id}, {"_id": 0, "expires_at_dt": 0}
        )
        if not snap:
            raise HTTPException(404, "Snapshot não encontrado")
        scope = snap_svc.get_scope_for_user(user)
        if scope is None:
            raise HTTPException(403, "Sem escopo")
        if "mantenedora_id" in scope and scope["mantenedora_id"] != snap.get("mantenedora_id"):
            raise HTTPException(403, "Fora do seu escopo")
        if "entity_ids" in scope and snap.get("entity_id") not in scope["entity_ids"]:
            raise HTTPException(403, "Fora do seu escopo")

        # Já existe?
        existing = await db.verifiable_documents.find_one(
            {"snapshot_id": snapshot_id}, {"_id": 0}
        )
        if existing:
            return {"created": False, "document": existing}

        # Escopo label (nome da escola se aplicável)
        scope_label = None
        if snap.get("entity_type") == "escola" and snap.get("entity_id"):
            sch = await db.schools.find_one({"id": snap["entity_id"]}, {"_id": 0, "name": 1})
            if sch:
                scope_label = sch.get("name")

        doc = await vsvc.create_verifiable_document(
            db,
            type=snap.get("analysis_type") or "plano_acao",
            public_hash=snap.get("public_hash") or "",
            server_signature=snap.get("server_signature"),
            mantenedora_id=snap.get("mantenedora_id"),
            entity_type=snap.get("entity_type"),
            entity_id=snap.get("entity_id"),
            snapshot_id=snap.get("id"),
            issued_by=snap.get("created_by") or {},
            scope_label=scope_label,
        )
        return {"created": True, "document": doc}

    # ------------------ Assinaturas e Substituições ------------------

    @admin.post("/{code}/signatures")
    async def add_signature_endpoint(code: str, request: Request):
        """Adiciona uma assinatura institucional ao documento.

        Body: {"role": "diretor", "full_name": "Maria Souza"}
        Apenas super_admin/admin/secretario/diretor.
        """
        user = await _require_admin(request)
        if user.get("role") not in (*_ADMIN_ROLES, "diretor"):
            raise HTTPException(403, "Permissão insuficiente para assinar")
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Body JSON obrigatório com role e full_name")
        role = (body or {}).get("role")
        full_name = (body or {}).get("full_name")
        if not role or not full_name:
            raise HTTPException(400, "Campos obrigatórios: role, full_name")
        try:
            r = await vsvc.add_signature(
                db,
                code_or_token=code,
                role=role,
                full_name=full_name,
                signed_by_user_id=user.get("id"),
            )
        except KeyError:
            raise HTTPException(404, "Documento não encontrado")
        except ValueError as e:
            raise HTTPException(400, str(e))
        return r

    @admin.post("/{code}/supersede")
    async def supersede_endpoint(code: str, request: Request):
        """Marca este documento como SUBSTITUÍDO por um novo.

        Body: {"new_code": "SIGESC-AAAA-BBBB"} ou {"new_token": "..."}
        Substituído ≠ revogado: documento permanece consultável publicamente
        com status `substituido` e referência ao sucessor.
        Apenas super_admin/admin/secretario.
        """
        user = await _require_admin(request)
        if user.get("role") not in _ADMIN_ROLES:
            raise HTTPException(403, "Apenas admin/secretario pode substituir")
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Body JSON obrigatório")
        new_id = (body or {}).get("new_code") or (body or {}).get("new_token")
        if not new_id:
            raise HTTPException(400, "new_code ou new_token obrigatório")
        try:
            r = await vsvc.supersede_document(
                db,
                old_code_or_token=code,
                new_code_or_token=new_id,
                user=user,
            )
        except KeyError as e:
            raise HTTPException(404, str(e))
        except ValueError as e:
            raise HTTPException(400, str(e))
        return r

    return public, admin
