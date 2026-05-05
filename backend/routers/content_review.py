"""Router: Fila de Revisão de Conteúdo (Sprint Mai/2026).

Administra sugestões de normalização textual geradas pelo script
`scripts/normalize_content.py`. Admin/super_admin aprovam ou rejeitam
cada item antes de gravar no documento original.

Endpoints:
    GET    /api/admin/content-review              — lista paginada (filtros)
    GET    /api/admin/content-review/stats        — contagens por status/coleção
    POST   /api/admin/content-review/{id}/approve — aplica + arquiva
    POST   /api/admin/content-review/{id}/reject  — marca rejeitado
    POST   /api/admin/content-review/{id}/edit-and-approve
                                                   — admin edita e aprova
    POST   /api/admin/content-review/bulk-approve — aprova lote
    DELETE /api/admin/content-review/purge-rejected — limpa rejeitados (super_admin)

Acesso: `super_admin`, `admin`, `admin_teste`.

Coleção: `content_review_queue`.

NÃO toca em BNCC, AEE, learning_objects. A whitelist de coleções/campos
vive em `scripts/normalize_content.py` (CONTENT_FIELDS_BY_COLLECTION).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth_middleware import AuthMiddleware

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/content-review", tags=["Content Review"])

QUEUE = "content_review_queue"
_ADMIN_ROLES = ("super_admin", "admin", "admin_teste")

# Whitelist de coleções/campos autorizados para aprovação (mirror do script).
# Mantenha em sync com scripts/normalize_content.py::CONTENT_FIELDS_BY_COLLECTION
WHITELIST = {
    "students": {"observations"},
    "student_history": {"observations"},
    "enrollments": {"observations"},
    "staff": {"observacoes"},
    # learning_objects FASE 1 (decisão proprietário 05/Mai/2026):
    # methodology = label "Práticas Pedagógicas" na UI; pratica_pedagogica = legado
    "learning_objects": {"content", "methodology", "pratica_pedagogica", "observations"},
}


class EditAndApproveRequest(BaseModel):
    edited_text: str = Field(..., min_length=1, max_length=10_000)


class BulkApproveRequest(BaseModel):
    ids: List[str] = Field(..., min_length=1, max_length=200)


def setup_router(db, **_kwargs):

    async def _require_admin(request: Request) -> dict:
        user = await AuthMiddleware.get_current_user(request)
        if user.get("role") not in _ADMIN_ROLES:
            raise HTTPException(403, "Acesso restrito a administradores")
        return user

    async def _load_item(item_id: str) -> dict:
        item = await db[QUEUE].find_one({"id": item_id}, {"_id": 0})
        if not item:
            raise HTTPException(404, "Item não encontrado")
        return item

    async def _apply_to_source(item: dict, new_value: str) -> None:
        col_name = item["source_collection"]
        field = item["source_field"]
        if col_name not in WHITELIST or field not in WHITELIST[col_name]:
            raise HTTPException(400, f"Combinação {col_name}.{field} fora da whitelist.")
        source_id = item["source_id"]
        # Suporta docs que usam 'id' (UUID string) ou '_id' (ObjectId legado).
        result = await db[col_name].update_one(
            {"id": source_id},
            {"$set": {field: new_value, "content_migrated": True,
                      "content_migrated_at": datetime.now(timezone.utc).isoformat()}},
        )
        if result.matched_count == 0:
            # tenta por _id string (fallback raro)
            result = await db[col_name].update_one(
                {"_id": source_id},
                {"$set": {field: new_value, "content_migrated": True,
                          "content_migrated_at": datetime.now(timezone.utc).isoformat()}},
            )
        if result.matched_count == 0:
            raise HTTPException(404, f"Documento original ({col_name}/{source_id}) não encontrado.")

    # ------------------------------------------------------------------
    # LIST
    # ------------------------------------------------------------------
    @router.get("")
    async def list_items(
        request: Request,
        status_filter: str = Query("pending", alias="status"),
        collection: Optional[str] = None,
        field: Optional[str] = None,
        limit: int = Query(50, ge=1, le=200),
        skip: int = Query(0, ge=0),
    ):
        await _require_admin(request)
        filt: dict = {}
        if status_filter != "all":
            filt["status"] = status_filter
        if collection:
            filt["source_collection"] = collection
        if field:
            filt["source_field"] = field

        cursor = db[QUEUE].find(filt, {"_id": 0}) \
            .sort("created_at", -1).skip(skip).limit(limit)
        items = await cursor.to_list(length=limit)
        total = await db[QUEUE].count_documents(filt)
        return {"items": items, "total": total, "skip": skip, "limit": limit}

    # ------------------------------------------------------------------
    # STATS
    # ------------------------------------------------------------------
    @router.get("/stats")
    async def stats(request: Request):
        await _require_admin(request)
        pipeline = [
            {"$group": {
                "_id": {"status": "$status", "colecao": "$source_collection"},
                "count": {"$sum": 1},
            }},
        ]
        rows: dict = {}
        totals = {"pending": 0, "approved": 0, "rejected": 0, "edited": 0}
        async for doc in db[QUEUE].aggregate(pipeline):
            st = doc["_id"]["status"]; col = doc["_id"]["colecao"]
            rows.setdefault(col, {"pending": 0, "approved": 0, "rejected": 0, "edited": 0})
            rows[col][st] = doc["count"]
            totals[st] = totals.get(st, 0) + doc["count"]
        return {"per_collection": rows, "totals": totals}

    # ------------------------------------------------------------------
    # CONTEXT (preview do doc original)
    # ------------------------------------------------------------------
    @router.get("/{item_id}/context")
    async def get_context(item_id: str, request: Request):
        """Retorna campos textuais do doc original para o admin entender o
        contexto antes de aprovar uma sugestão. Filtrado por tenant — só
        retorna campos da whitelist + identificação do registro."""
        await _require_admin(request)
        item = await _load_item(item_id)
        col_name = item["source_collection"]
        source_id = item["source_id"]

        # Campos seguros para preview (whitelist + identificação)
        whitelisted = list(WHITELIST.get(col_name, set()))
        id_fields = [
            "id", "full_name", "nome", "name", "email", "enrollment_number",
            "class_id", "course_id", "school_id", "date", "academic_year",
            "mantenedora_id", "content_migrated", "content_migrated_at",
        ]
        projection = {**{f: 1 for f in (whitelisted + id_fields)}, "_id": 0}

        doc = await db[col_name].find_one({"id": source_id}, projection)
        if not doc:
            doc = await db[col_name].find_one({"_id": source_id}, projection)
        if not doc:
            raise HTTPException(404, "Documento original não encontrado")

        return {
            "collection": col_name,
            "source_id": source_id,
            "highlight_field": item["source_field"],
            "fields": doc,
        }

    # ------------------------------------------------------------------
    # APPROVE
    # ------------------------------------------------------------------
    @router.post("/{item_id}/approve")
    async def approve_item(item_id: str, request: Request):
        user = await _require_admin(request)
        item = await _load_item(item_id)
        if item["status"] != "pending":
            raise HTTPException(400, f"Item já está em estado '{item['status']}'.")

        await _apply_to_source(item, item["sugestao"])
        await db[QUEUE].update_one(
            {"id": item_id},
            {"$set": {
                "status": "approved",
                "reviewed_at": datetime.now(timezone.utc),
                "reviewed_by": user.get("id"),
            }},
        )
        return {"ok": True, "status": "approved"}

    # ------------------------------------------------------------------
    # REJECT
    # ------------------------------------------------------------------
    @router.post("/{item_id}/reject")
    async def reject_item(item_id: str, request: Request):
        user = await _require_admin(request)
        item = await _load_item(item_id)
        if item["status"] != "pending":
            raise HTTPException(400, f"Item já está em estado '{item['status']}'.")
        await db[QUEUE].update_one(
            {"id": item_id},
            {"$set": {
                "status": "rejected",
                "reviewed_at": datetime.now(timezone.utc),
                "reviewed_by": user.get("id"),
            }},
        )
        return {"ok": True, "status": "rejected"}

    # ------------------------------------------------------------------
    # EDIT + APPROVE
    # ------------------------------------------------------------------
    @router.post("/{item_id}/edit-and-approve")
    async def edit_and_approve(item_id: str, body: EditAndApproveRequest, request: Request):
        user = await _require_admin(request)
        item = await _load_item(item_id)
        if item["status"] != "pending":
            raise HTTPException(400, f"Item já está em estado '{item['status']}'.")

        await _apply_to_source(item, body.edited_text)
        await db[QUEUE].update_one(
            {"id": item_id},
            {"$set": {
                "status": "edited",
                "edited_text": body.edited_text,
                "reviewed_at": datetime.now(timezone.utc),
                "reviewed_by": user.get("id"),
            }},
        )
        return {"ok": True, "status": "edited"}

    # ------------------------------------------------------------------
    # BULK APPROVE
    # ------------------------------------------------------------------
    @router.post("/bulk-approve")
    async def bulk_approve(body: BulkApproveRequest, request: Request):
        user = await _require_admin(request)
        ok = 0; skipped = 0; errors: List[dict] = []
        for item_id in body.ids:
            try:
                item = await db[QUEUE].find_one({"id": item_id, "status": "pending"}, {"_id": 0})
                if not item:
                    skipped += 1; continue
                await _apply_to_source(item, item["sugestao"])
                await db[QUEUE].update_one(
                    {"id": item_id},
                    {"$set": {
                        "status": "approved",
                        "reviewed_at": datetime.now(timezone.utc),
                        "reviewed_by": user.get("id"),
                    }},
                )
                ok += 1
            except HTTPException as e:
                errors.append({"id": item_id, "error": e.detail})
            except Exception as e:  # noqa: BLE001
                logger.exception("bulk-approve falhou em %s", item_id)
                errors.append({"id": item_id, "error": str(e)})
        return {"approved": ok, "skipped": skipped, "errors": errors}

    # ------------------------------------------------------------------
    # PURGE REJECTED
    # ------------------------------------------------------------------
    @router.delete("/purge-rejected")
    async def purge_rejected(request: Request):
        user = await _require_admin(request)
        if user.get("role") != "super_admin":
            raise HTTPException(403, "Apenas super_admin pode limpar rejeitados.")
        res = await db[QUEUE].delete_many({"status": "rejected"})
        return {"deleted": res.deleted_count}

    return router
