"""
Importador de PDF curricular (BNCC / DCM) — May 2026.

Pipeline: super_admin envia PDF → extract → fila de revisão → commit seletivo.

Endpoints (todos super_admin via Matriz `nav-curriculum-button`):
  POST   /api/curriculum/import/upload                        (multipart, ?only=LP,MA)
  GET    /api/curriculum/import/batches?status=
  GET    /api/curriculum/import/batches/{batch_id}
  PUT    /api/curriculum/import/batches/{batch_id}/items/{idx}
  POST   /api/curriculum/import/batches/{batch_id}/bulk-status
  POST   /api/curriculum/import/batches/{batch_id}/commit
  DELETE /api/curriculum/import/batches/{batch_id}            (cancela)
"""
from __future__ import annotations

import os
import tempfile
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Request, UploadFile, File, HTTPException, Query
from pydantic import BaseModel

from auth_middleware import AuthMiddleware
from models import (
    CurriculumImportBatch, CurriculumImportItem, CurriculumImportItemUpdate,
)
from services.curriculum_extractor import extract_skills_from_pdf, COMPONENT_MAP

router = APIRouter(prefix="/curriculum/import", tags=["Currículo - Importação"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BulkStatusPayload(BaseModel):
    indices: List[int]
    status: str


def setup_router(db):

    async def _require_super(request: Request):
        return await AuthMiddleware.require_permission(
            db, 'nav-curriculum-button', ['super_admin']
        )(request)

    # =================== UPLOAD + EXTRACT ===================

    @router.post("/upload", status_code=201)
    async def upload_pdf(
        request: Request,
        file: UploadFile = File(...),
        only: Optional[str] = Query(None, description="Componentes (CSV) — ex.: 'LP' ou 'LP,MA'"),
        fonte: str = Query('DCM_FA', description="DCM_FA | BNCC | MUNICIPAL"),
    ):
        user = await _require_super(request)

        if not file.filename or not file.filename.lower().endswith('.pdf'):
            raise HTTPException(400, "Apenas arquivos .pdf são aceitos.")

        # Salva temporariamente
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        try:
            content = await file.read()
            if len(content) > 30 * 1024 * 1024:
                raise HTTPException(413, "PDF maior que 30 MB. Divida em partes menores.")
            tmp.write(content)
            tmp.flush()
            tmp.close()

            only_list = [c.strip().upper() for c in only.split(',')] if only else None
            try:
                items_raw = extract_skills_from_pdf(tmp.name, only_components=only_list, fonte=fonte)
            except Exception as e:
                raise HTTPException(500, f"Falha ao extrair PDF: {e}")
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

        # Marca itens duplicados (já existem em curriculum_skills)
        codigos = [i['codigo'] for i in items_raw]
        existing = set()
        if codigos:
            cursor = db.curriculum_skills.find(
                {"codigo": {"$in": codigos}}, {"_id": 0, "codigo": 1}
            )
            async for doc in cursor:
                existing.add(doc['codigo'])

        items: List[CurriculumImportItem] = []
        for idx, raw in enumerate(items_raw):
            status = 'duplicate' if raw['codigo'] in existing else 'pending'
            items.append(CurriculumImportItem(
                idx=idx,
                codigo=raw['codigo'],
                descricao=raw['descricao'],
                ano=raw.get('ano'),
                ano_range=raw.get('ano_range'),
                bimestre=raw.get('bimestre'),
                componente_codigo=raw.get('componente_codigo'),
                componente_nome=raw.get('componente_nome'),
                etapa=raw.get('etapa'),
                page=raw.get('page'),
                fonte=raw.get('fonte', fonte),
                status=status,
            ))

        batch = CurriculumImportBatch(
            filename=file.filename,
            only_components=only_list or [],
            fonte=fonte,
            items=items,
            total_items=len(items),
            status='pending_review',
            created_by=user.get('id'),
            created_by_name=user.get('full_name') or user.get('email'),
        )
        await db.curriculum_import_batches.insert_one(batch.model_dump())

        return {
            "batch_id": batch.id,
            "total_items": len(items),
            "duplicates": sum(1 for i in items if i.status == 'duplicate'),
            "by_componente": {
                c: sum(1 for i in items if i.componente_codigo == c)
                for c in {i.componente_codigo for i in items if i.componente_codigo}
            },
        }

    # =================== LIST + GET ===================

    @router.get("/batches")
    async def list_batches(request: Request, status: Optional[str] = None, limit: int = 50):
        await _require_super(request)
        q = {}
        if status:
            q['status'] = status
        cursor = (
            db.curriculum_import_batches
            .find(q, {"_id": 0, "items": 0})  # exclui items pesados
            .sort([("created_at", -1)])
            .limit(limit)
        )
        return await cursor.to_list(length=limit)

    @router.get("/batches/{batch_id}")
    async def get_batch(batch_id: str, request: Request):
        await _require_super(request)
        batch = await db.curriculum_import_batches.find_one({"id": batch_id}, {"_id": 0})
        if not batch:
            raise HTTPException(404, "Batch não encontrado.")
        return batch

    # =================== EDIT ITEMS ===================

    @router.put("/batches/{batch_id}/items/{idx}")
    async def update_item(batch_id: str, idx: int, payload: CurriculumImportItemUpdate, request: Request):
        await _require_super(request)
        update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
        if not update:
            raise HTTPException(400, "Nada para atualizar.")
        # Constrói operadores positionais $.fieldname para items[idx]
        set_ops = {f"items.$[elem].{k}": v for k, v in update.items()}
        r = await db.curriculum_import_batches.update_one(
            {"id": batch_id},
            {"$set": set_ops},
            array_filters=[{"elem.idx": idx}],
        )
        if r.matched_count == 0:
            raise HTTPException(404, "Batch não encontrado.")
        return {"ok": True, "updated": list(update.keys())}

    @router.post("/batches/{batch_id}/bulk-status")
    async def bulk_status(batch_id: str, payload: BulkStatusPayload, request: Request):
        await _require_super(request)
        if payload.status not in ('pending', 'approved', 'rejected', 'edited'):
            raise HTTPException(400, "Status inválido para bulk.")
        r = await db.curriculum_import_batches.update_one(
            {"id": batch_id},
            {"$set": {"items.$[elem].status": payload.status}},
            array_filters=[{"elem.idx": {"$in": payload.indices}}],
        )
        if r.matched_count == 0:
            raise HTTPException(404, "Batch não encontrado.")
        return {"ok": True, "affected": len(payload.indices)}

    # =================== COMMIT ===================

    @router.post("/batches/{batch_id}/commit")
    async def commit_batch(batch_id: str, request: Request):
        """Persiste os items aprovados como CurriculumSkill (criando componente se necessário)."""
        user = await _require_super(request)
        batch = await db.curriculum_import_batches.find_one({"id": batch_id}, {"_id": 0})
        if not batch:
            raise HTTPException(404, "Batch não encontrado.")
        if batch['status'] in ('committed', 'cancelled'):
            raise HTTPException(400, f"Batch já está '{batch['status']}'.")

        approved = [i for i in batch['items'] if i.get('status') == 'approved']
        if not approved:
            raise HTTPException(400, "Nenhum item aprovado para importar.")

        # Cache de components (componente_codigo, etapa, fonte) → component_id
        comp_cache: dict = {}
        skills_inserted = 0
        skills_skipped_dup = 0
        components_created = 0

        for item in approved:
            comp_codigo = (item.get('componente_codigo') or 'XX').upper()
            etapa = item.get('etapa') or 'anos_iniciais'
            fonte = item.get('fonte') or batch.get('fonte', 'DCM_FA')
            cache_key = (comp_codigo, etapa, fonte)

            if cache_key not in comp_cache:
                # Tenta achar componente existente
                comp = await db.curriculum_components.find_one(
                    {"codigo": comp_codigo, "etapa": etapa, "fonte": fonte},
                    {"_id": 0}
                )
                if not comp:
                    # Cria
                    nome = item.get('componente_nome') or COMPONENT_MAP.get(
                        comp_codigo, (comp_codigo, etapa)
                    )[0]
                    new_comp = {
                        "id": f"comp_{comp_codigo.lower()}_{etapa}_{fonte.lower()}",
                        "codigo": comp_codigo,
                        "nome": nome,
                        "eixo_estruturante": None,
                        "etapa": etapa,
                        "fonte": fonte,
                        "descricao": f"Importado via batch {batch['id']}.",
                        "ordem": 50,
                        "ativo": True,
                        "created_at": _now(),
                        "updated_at": None,
                    }
                    await db.curriculum_components.insert_one(new_comp)
                    components_created += 1
                    comp_cache[cache_key] = new_comp['id']
                else:
                    comp_cache[cache_key] = comp['id']

            # Verifica novamente duplicidade no momento do commit
            exists = await db.curriculum_skills.find_one(
                {"codigo": item['codigo']}, {"_id": 0, "id": 1}
            )
            if exists:
                skills_skipped_dup += 1
                # Marca item como duplicate
                await db.curriculum_import_batches.update_one(
                    {"id": batch_id},
                    {"$set": {"items.$[elem].status": "duplicate"}},
                    array_filters=[{"elem.idx": item['idx']}],
                )
                continue

            skill_doc = {
                "id": f"skill_imp_{batch_id[:8]}_{item['idx']}",
                "codigo": item['codigo'],
                "descricao": item['descricao'],
                "componente_id": comp_cache[cache_key],
                "componente_codigo": comp_codigo,
                "ano": item.get('ano'),
                "bimestre": item.get('bimestre'),
                "objeto_conhecimento": None,
                "unidade_tematica": None,
                "fonte": fonte,
                "metodos_recomendados": [],
                "ativo": True,
                "created_at": _now(),
                "updated_at": None,
            }
            await db.curriculum_skills.insert_one(skill_doc)
            skills_inserted += 1
            await db.curriculum_import_batches.update_one(
                {"id": batch_id},
                {"$set": {"items.$[elem].status": "imported"}},
                array_filters=[{"elem.idx": item['idx']}],
            )

        # Atualiza status do batch
        remaining_pending = await db.curriculum_import_batches.count_documents({
            "id": batch_id,
            "items.status": {"$in": ["pending", "approved", "edited"]},
        })
        new_status = 'committed' if remaining_pending == 0 else 'partially_committed'

        summary = {
            "approved_at_commit": len(approved),
            "skills_inserted": skills_inserted,
            "skills_skipped_duplicate": skills_skipped_dup,
            "components_created": components_created,
            "committed_by": user.get('email'),
        }
        await db.curriculum_import_batches.update_one(
            {"id": batch_id},
            {"$set": {
                "status": new_status,
                "committed_at": _now(),
                "summary": summary,
            }}
        )

        return {
            "batch_id": batch_id,
            "status": new_status,
            **summary,
        }

    @router.delete("/batches/{batch_id}")
    async def cancel_batch(batch_id: str, request: Request):
        await _require_super(request)
        # Hard delete se ainda nada foi importado, senão marca cancelled
        batch = await db.curriculum_import_batches.find_one({"id": batch_id}, {"_id": 0, "summary": 1})
        if not batch:
            raise HTTPException(404, "Batch não encontrado.")
        if batch.get('summary'):
            await db.curriculum_import_batches.update_one(
                {"id": batch_id},
                {"$set": {"status": "cancelled", "updated_at": _now()}}
            )
            return {"ok": True, "soft_cancelled": True}
        await db.curriculum_import_batches.delete_one({"id": batch_id})
        return {"ok": True, "deleted": True}

    return router
