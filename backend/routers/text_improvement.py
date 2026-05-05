"""Router: Higienização Textual — Fase 1 (Formatação) — Mai/2026.

Espelha `content_review.py` mas opera sobre `text_improvement_queue`.
Acesso: super_admin, admin, admin_teste.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth_middleware import AuthMiddleware

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/text-improvement", tags=["Text Improvement"])

QUEUE = "text_improvement_queue"
_ADMIN_ROLES = ("super_admin", "admin", "admin_teste")

# Whitelist de coleções/campos. Mantenha em sync com `scripts/text_improvement.py`.
WHITELIST = {
    "students": {"observations"},
    "student_history": {"observations"},
    "enrollments": {"observations"},
    "staff": {"observacoes"},
    "learning_objects": {"content", "methodology", "pratica_pedagogica", "observations"},
}


class EditAndApproveRequest(BaseModel):
    edited_text: str = Field(..., min_length=1, max_length=10_000)


class BulkApproveRequest(BaseModel):
    ids: List[str] = Field(..., min_length=1, max_length=200)


class BulkApproveByRuleRequest(BaseModel):
    rule: str = Field(..., min_length=1, max_length=64)
    confirm: bool = Field(default=False)


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
        result = await db[col_name].update_one(
            {"id": source_id},
            {"$set": {field: new_value, "text_improved": True,
                      "text_improved_at": datetime.now(timezone.utc).isoformat()}},
        )
        if result.matched_count == 0:
            result = await db[col_name].update_one(
                {"_id": source_id},
                {"$set": {field: new_value, "text_improved": True,
                          "text_improved_at": datetime.now(timezone.utc).isoformat()}},
            )
        if result.matched_count == 0:
            raise HTTPException(404, f"Documento original ({col_name}/{source_id}) não encontrado.")

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
        cursor = db[QUEUE].find(filt, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
        items = await cursor.to_list(length=limit)
        total = await db[QUEUE].count_documents(filt)
        return {"items": items, "total": total, "skip": skip, "limit": limit}

    @router.get("/stats")
    async def stats(request: Request):
        await _require_admin(request)
        pipeline = [{
            "$group": {
                "_id": {"status": "$status", "colecao": "$source_collection"},
                "count": {"$sum": 1},
            },
        }]
        rows: dict = {}
        totals = {"pending": 0, "approved": 0, "rejected": 0, "edited": 0}
        async for doc in db[QUEUE].aggregate(pipeline):
            st = doc["_id"]["status"]; col = doc["_id"]["colecao"]
            rows.setdefault(col, {"pending": 0, "approved": 0, "rejected": 0, "edited": 0})
            rows[col][st] = doc["count"]
            totals[st] = totals.get(st, 0) + doc["count"]
        return {"per_collection": rows, "totals": totals}

    @router.get("/{item_id}/context")
    async def get_context(item_id: str, request: Request):
        await _require_admin(request)
        item = await _load_item(item_id)
        col_name = item["source_collection"]
        source_id = item["source_id"]
        whitelisted = list(WHITELIST.get(col_name, set()))
        id_fields = ["id", "full_name", "nome", "name", "email", "enrollment_number",
                     "class_id", "course_id", "school_id", "date", "academic_year",
                     "mantenedora_id", "text_improved", "text_improved_at"]
        projection = {**{f: 1 for f in (whitelisted + id_fields)}, "_id": 0}
        doc = await db[col_name].find_one({"id": source_id}, projection)
        if not doc:
            doc = await db[col_name].find_one({"_id": source_id}, projection)
        if not doc:
            raise HTTPException(404, "Documento original não encontrado")
        return {"collection": col_name, "source_id": source_id,
                "highlight_field": item["source_field"], "fields": doc}

    @router.post("/{item_id}/approve")
    async def approve_item(item_id: str, request: Request):
        user = await _require_admin(request)
        item = await _load_item(item_id)
        if item["status"] != "pending":
            raise HTTPException(400, f"Item já está em estado '{item['status']}'.")
        await _apply_to_source(item, item["sugestao"])
        await db[QUEUE].update_one({"id": item_id}, {"$set": {
            "status": "approved",
            "reviewed_at": datetime.now(timezone.utc),
            "reviewed_by": user.get("id"),
        }})
        return {"ok": True, "status": "approved"}

    @router.post("/{item_id}/reject")
    async def reject_item(item_id: str, request: Request):
        user = await _require_admin(request)
        item = await _load_item(item_id)
        if item["status"] != "pending":
            raise HTTPException(400, f"Item já está em estado '{item['status']}'.")
        await db[QUEUE].update_one({"id": item_id}, {"$set": {
            "status": "rejected",
            "reviewed_at": datetime.now(timezone.utc),
            "reviewed_by": user.get("id"),
        }})
        return {"ok": True, "status": "rejected"}

    @router.post("/{item_id}/edit-and-approve")
    async def edit_and_approve(item_id: str, body: EditAndApproveRequest, request: Request):
        user = await _require_admin(request)
        item = await _load_item(item_id)
        if item["status"] != "pending":
            raise HTTPException(400, f"Item já está em estado '{item['status']}'.")
        await _apply_to_source(item, body.edited_text)
        await db[QUEUE].update_one({"id": item_id}, {"$set": {
            "status": "edited",
            "edited_text": body.edited_text,
            "reviewed_at": datetime.now(timezone.utc),
            "reviewed_by": user.get("id"),
        }})
        return {"ok": True, "status": "edited"}

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
                await db[QUEUE].update_one({"id": item_id}, {"$set": {
                    "status": "approved",
                    "reviewed_at": datetime.now(timezone.utc),
                    "reviewed_by": user.get("id"),
                }})
                ok += 1
            except HTTPException as e:
                errors.append({"id": item_id, "error": e.detail})
            except Exception as e:  # noqa: BLE001
                logger.exception("bulk-approve falhou em %s", item_id)
                errors.append({"id": item_id, "error": str(e)})
        return {"approved": ok, "skipped": skipped, "errors": errors}

    # ------------------------------------------------------------------
    # RULES SUMMARY (apenas itens com regra ÚNICA)
    # ------------------------------------------------------------------
    @router.get("/rules-summary")
    async def rules_summary(request: Request):
        """Retorna contagem de itens pendentes agrupados por regra,
        considerando APENAS itens em que aquela é a ÚNICA regra aplicada
        (mais seguro para aprovação em massa)."""
        await _require_admin(request)
        pipeline = [
            {"$match": {
                "status": "pending",
                "$expr": {"$eq": [{"$size": "$applied_rules"}, 1]},
            }},
            {"$group": {
                "_id": {"$arrayElemAt": ["$applied_rules", 0]},
                "count": {"$sum": 1},
            }},
            {"$sort": {"count": -1}},
        ]
        rows = []
        async for doc in db[QUEUE].aggregate(pipeline):
            rows.append({"rule": doc["_id"], "count": doc["count"]})
        return {"single_rule_groups": rows}

    # ------------------------------------------------------------------
    # BULK APPROVE BY RULE (filtro: itens onde applied_rules == [rule])
    # ------------------------------------------------------------------
    @router.post("/bulk-approve-by-rule")
    async def bulk_approve_by_rule(body: BulkApproveByRuleRequest, request: Request):
        """Aprova em massa TODOS os itens pendentes onde a regra `body.rule`
        é a ÚNICA aplicada. Limite de segurança: 500 itens por chamada."""
        user = await _require_admin(request)
        if not body.confirm:
            raise HTTPException(400, "Confirmação requerida (confirm=true).")

        filt = {
            "status": "pending",
            "applied_rules": [body.rule],  # match exato da lista
        }
        items = await db[QUEUE].find(filt, {"_id": 0}).limit(500).to_list(500)

        ok = 0; errors: List[dict] = []
        for item in items:
            try:
                await _apply_to_source(item, item["sugestao"])
                await db[QUEUE].update_one({"id": item["id"]}, {"$set": {
                    "status": "approved",
                    "reviewed_at": datetime.now(timezone.utc),
                    "reviewed_by": user.get("id"),
                }})
                ok += 1
            except HTTPException as e:
                errors.append({"id": item["id"], "error": e.detail})
            except Exception as e:  # noqa: BLE001
                logger.exception("bulk-approve-by-rule falhou em %s", item["id"])
                errors.append({"id": item["id"], "error": str(e)})

        return {"approved": ok, "matched": len(items), "errors": errors,
                "rule": body.rule}

    return router
