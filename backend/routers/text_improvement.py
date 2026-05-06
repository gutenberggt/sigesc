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
_TEACHER_ROLES = ("professor",)
_ALL_ROLES = _ADMIN_ROLES + _TEACHER_ROLES

# Níveis em que o COMPONENTE CURRICULAR aparece na UI (anos finais, médio, EJA).
# Educação Infantil e Anos Iniciais são polivalentes: ocultar o componente.
EDU_LEVELS_WITH_COMPONENT = {
    "fundamental_anos_finais",
    "ensino_medio",
    "eja",
    "eja_fundamental_finais",
    "eja_medio",
}

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

    async def _require_user(request: Request) -> dict:
        """Aceita admin OU professor. Para professor, escopo é restrito ao próprio."""
        user = await AuthMiddleware.get_current_user(request)
        if user.get("role") not in _ALL_ROLES:
            raise HTTPException(403, "Acesso restrito.")
        return user

    async def _require_admin(request: Request) -> dict:
        user = await AuthMiddleware.get_current_user(request)
        if user.get("role") not in _ADMIN_ROLES:
            raise HTTPException(403, "Acesso restrito a administradores")
        return user

    async def _scope_filter_for(user: dict) -> dict:
        """Devolve um dict de filtro mongo a ser unido ao filtro principal.
        - Admin: sem restrição.
        - Professor: limitado a `recorded_by_user_id == user.id` (item criado por ele
          via `learning_objects`). Itens sem essa marca ficam invisíveis ao professor.
        """
        if user.get("role") in _ADMIN_ROLES:
            return {}
        # Professor — escopo restrito.
        return {"recorded_by_user_id": user.get("id")}

    async def _enrich_with_class_course(items: List[dict]) -> List[dict]:
        """Resolve nomes de turma/componente para itens vindos de `learning_objects`.

        - Coleta IDs únicos de class_id/course_id e busca em batch ($in).
        - Anexa `class_name`, `course_name`, `education_level`, `show_course` no contexto.
        - `show_course=True` apenas para níveis em `EDU_LEVELS_WITH_COMPONENT`.
        """
        if not items:
            return items

        lo_items = [i for i in items if i.get("source_collection") == "learning_objects"]
        if not lo_items:
            return items

        # 1) Resolve class_id / course_id no documento de origem se ainda não estiverem
        #    no item enfileirado (compat com items legados).
        missing_lo_ids = [i["source_id"] for i in lo_items if not i.get("class_id") or not i.get("course_id")]
        lo_docs_by_id: dict = {}
        if missing_lo_ids:
            async for d in db.learning_objects.find(
                {"id": {"$in": missing_lo_ids}},
                {"_id": 0, "id": 1, "class_id": 1, "course_id": 1, "recorded_by": 1},
            ):
                lo_docs_by_id[d["id"]] = d

        # 2) Backfill class_id/course_id em itens legados
        for it in lo_items:
            if (not it.get("class_id") or not it.get("course_id")) and it["source_id"] in lo_docs_by_id:
                src = lo_docs_by_id[it["source_id"]]
                it["class_id"] = it.get("class_id") or src.get("class_id")
                it["course_id"] = it.get("course_id") or src.get("course_id")

        # 3) Batch-load classes e courses
        class_ids = {i.get("class_id") for i in lo_items if i.get("class_id")}
        course_ids = {i.get("course_id") for i in lo_items if i.get("course_id")}
        classes_by_id = {}
        courses_by_id = {}
        if class_ids:
            async for c in db.classes.find(
                {"id": {"$in": list(class_ids)}},
                {"_id": 0, "id": 1, "name": 1, "education_level": 1},
            ):
                classes_by_id[c["id"]] = c
        if course_ids:
            async for c in db.courses.find(
                {"id": {"$in": list(course_ids)}},
                {"_id": 0, "id": 1, "name": 1},
            ):
                courses_by_id[c["id"]] = c

        # 4) Anexa ao context
        for it in lo_items:
            ctx = dict(it.get("context") or {})
            cl = classes_by_id.get(it.get("class_id"))
            co = courses_by_id.get(it.get("course_id"))
            if cl:
                ctx["class_name"] = cl.get("name")
                ctx["education_level"] = cl.get("education_level")
            if co:
                ctx["course_name"] = co.get("name")
            ctx["show_course"] = bool(
                cl and (cl.get("education_level") or "") in EDU_LEVELS_WITH_COMPONENT
            )
            it["context"] = ctx

        return items

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
        user = await _require_user(request)
        scope = await _scope_filter_for(user)
        filt: dict = {**scope}
        if status_filter != "all":
            filt["status"] = status_filter
        if collection:
            filt["source_collection"] = collection
        if field:
            filt["source_field"] = field
        cursor = db[QUEUE].find(filt, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
        items = await cursor.to_list(length=limit)
        items = await _enrich_with_class_course(items)
        total = await db[QUEUE].count_documents(filt)
        return {"items": items, "total": total, "skip": skip, "limit": limit,
                "user_scope": "self" if user.get("role") in _TEACHER_ROLES else "all"}

    @router.get("/stats")
    async def stats(request: Request):
        user = await _require_user(request)
        scope = await _scope_filter_for(user)
        match_stage = {"$match": scope} if scope else {"$match": {}}
        pipeline = [
            match_stage,
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

    @router.get("/{item_id}/context")
    async def get_context(item_id: str, request: Request):
        user = await _require_user(request)
        item = await _load_item(item_id)
        # Professor só vê contexto dos próprios items.
        if user.get("role") in _TEACHER_ROLES and item.get("recorded_by_user_id") != user.get("id"):
            raise HTTPException(403, "Item fora do seu escopo")
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

    async def _ensure_owns(item: dict, user: dict) -> None:
        """Garante que o usuário pode modificar o item (admin OU dono)."""
        if user.get("role") in _ADMIN_ROLES:
            return
        if item.get("recorded_by_user_id") != user.get("id"):
            raise HTTPException(403, "Item fora do seu escopo")

    @router.post("/{item_id}/approve")
    async def approve_item(item_id: str, request: Request):
        user = await _require_user(request)
        item = await _load_item(item_id)
        await _ensure_owns(item, user)
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
        user = await _require_user(request)
        item = await _load_item(item_id)
        await _ensure_owns(item, user)
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
        user = await _require_user(request)
        item = await _load_item(item_id)
        await _ensure_owns(item, user)
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
        user = await _require_user(request)
        scope = await _scope_filter_for(user)
        ok = 0; skipped = 0; errors: List[dict] = []
        for item_id in body.ids:
            try:
                item = await db[QUEUE].find_one({"id": item_id, "status": "pending", **scope}, {"_id": 0})
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
