"""
Endpoint de upload de assinatura institucional (Fase 5c — Mai/2026).

Owner aprovou (defaults 4b + 3a + restrições):
  - Roles autorizados: diretor, secretario, gerente, admin, super_admin
  - Cada usuário só altera A PRÓPRIA assinatura
  - Armazena via `services/document_files.py` (GridFS-like)
  - Limite: 512KB, PNG/JPG/WEBP, 600x200, MIME validado, re-encode obrigatório.
"""
from __future__ import annotations

import base64
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from auth_middleware import AuthMiddleware
from services.document_files import (
    store_signature_image,
    fetch_signature_image,
    SIGNATURE_MAX_BYTES,
    ALLOWED_SIGNATURE_MIMES,
)

SIGNATURE_ROLES = ["diretor", "secretario", "gerente",
                   "admin", "admin_teste", "super_admin"]


class SignatureUploadRequest(BaseModel):
    # base64-encoded para suportar upload via JSON sem multipart complexo.
    data_base64: str = Field(..., min_length=10, max_length=int(SIGNATURE_MAX_BYTES * 1.4))
    mime_type: str = Field(..., pattern="^image/(png|jpeg|webp)$")


def setup_user_signature_router(db, audit_service):
    router = APIRouter(prefix="/users/me/signature-image", tags=["Assinatura Institucional"])

    @router.put("")
    async def upload_my_signature(payload: SignatureUploadRequest, request: Request):
        current_user = await AuthMiddleware.require_roles(SIGNATURE_ROLES)(request)
        try:
            raw = base64.b64decode(payload.data_base64, validate=True)
        except Exception:
            raise HTTPException(status_code=422, detail={
                "code": "INVALID_BASE64", "message": "data_base64 inválido.",
            })
        if len(raw) > SIGNATURE_MAX_BYTES:
            raise HTTPException(status_code=422, detail={
                "code": "FILE_TOO_LARGE",
                "message": f"Limite: {SIGNATURE_MAX_BYTES // 1024}KB.",
            })
        if payload.mime_type not in ALLOWED_SIGNATURE_MIMES:
            raise HTTPException(status_code=422, detail={
                "code": "MIME_NOT_ALLOWED",
                "message": f"Permitidos: {sorted(ALLOWED_SIGNATURE_MIMES)}.",
            })

        try:
            info = await store_signature_image(
                db, raw_bytes=raw, declared_mime=payload.mime_type,
                user_id=current_user["id"],
                mantenedora_id=current_user.get("mantenedora_id"),
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail={
                "code": str(e).split(":")[0], "message": str(e),
            })

        # Substitui o ponteiro do usuário. NÃO deleta a anterior — histórico
        # implícito em document_files via auditoria.
        previous_id = (await db.users.find_one(
            {"id": current_user["id"]}, {"_id": 0, "signature_image_file_id": 1},
        ) or {}).get("signature_image_file_id")
        await db.users.update_one(
            {"id": current_user["id"]},
            {"$set": {
                "signature_image_file_id": info["file_id"],
                "signature_image_updated_at": __import__("datetime").datetime.utcnow().isoformat(),
            }},
        )
        await audit_service.log(
            action='update_signature_image',
            collection='users',
            user=current_user, request=request, document_id=current_user["id"],
            description="Atualizou imagem da própria assinatura institucional.",
            extra_data={
                "entity_type": "signature_image",
                "previous_file_id": previous_id,
                "new_file_id": info["file_id"],
                "size_bytes": info["size_bytes"],
                "dimensions": f"{info['width']}x{info['height']}",
            },
        )
        return {
            "file_id": info["file_id"],
            "size_bytes": info["size_bytes"],
            "sha256": info["sha256"],
            "width": info["width"],
            "height": info["height"],
            "mime_type": info["mime_type"],
        }

    @router.get("")
    async def get_my_signature(request: Request):
        current_user = await AuthMiddleware.require_roles(SIGNATURE_ROLES)(request)
        u = await db.users.find_one(
            {"id": current_user["id"]},
            {"_id": 0, "signature_image_file_id": 1, "signature_image_updated_at": 1},
        ) or {}
        fid = u.get("signature_image_file_id")
        if not fid:
            return {"file_id": None}
        img = await fetch_signature_image(db, fid)
        if not img:
            return {"file_id": None}
        return {
            "file_id": fid,
            "mime_type": img["mime_type"],
            "size_bytes": img["size_bytes"],
            "width": img["width"],
            "height": img["height"],
            "updated_at": u.get("signature_image_updated_at"),
            "data_base64": base64.b64encode(img["bytes"]).decode("ascii"),
        }

    return router


def setup_signature_image_render_router(db):
    """Rota interna que retorna a IMAGEM raw (com auth) — usada para preview.

    Pública (sem auth) não — assinaturas são dado sensível.
    """
    router = APIRouter(prefix="/signature-images", tags=["Assinatura Institucional"])

    @router.get("/{file_id}")
    async def render_signature(file_id: str, request: Request):
        await AuthMiddleware.require_roles(
            SIGNATURE_ROLES + ["coordenador", "apoio_pedagogico", "professor"]
        )(request)
        img = await fetch_signature_image(db, file_id)
        if not img:
            raise HTTPException(status_code=404)
        return Response(content=img["bytes"], media_type=img["mime_type"])

    return router
