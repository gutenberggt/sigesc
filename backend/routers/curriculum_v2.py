"""Currículo v2 — Multi-Camadas (Feb 2026).

Endpoints expostos sob /api/curriculum:
  GET  /api/curriculum/bncc                      — lista canônica nacional
  GET  /api/curriculum/bncc/{id}                 — BNCC skill
  POST /api/curriculum/bncc                      — super_admin
  GET  /api/curriculum/adaptations               — CATÁLOGO p/ SkillPicker
  GET  /api/curriculum/adaptations/{id}          — detalhe (joined BNCC + methods)
  POST /api/curriculum/adaptations               — super_admin/coord
  PUT  /api/curriculum/adaptations/{id}          — super_admin/coord
  DELETE /api/curriculum/adaptations/{id}        — soft delete
  POST /api/curriculum/v2/migrate                — roda migração idempotente
  GET  /api/curriculum/adaptations/availability  — resolve obrigatoriedade
      ?component_id=...&ano=N&bimestre=M → retorna {required: bool, count: N}
  GET  /api/curriculum/coverage                  — métricas por componente/ano/bimestre
"""
from __future__ import annotations

from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel

from auth_middleware import AuthMiddleware
from models import (
    BnccSkill, BnccSkillCreate,
    CurriculumAdaptation, CurriculumAdaptationCreate, CurriculumAdaptationUpdate,
)
from services.curriculum_v2_migration import (
    run_full_migration, BNCC_CODE_RE,
)

router = APIRouter(prefix="/curriculum", tags=["Currículo v2"])


def setup_router(db):

    async def _require_any_auth(request: Request):
        return await AuthMiddleware.require_permission(
            db, 'nav-curriculum-button', None
        )(request)

    async def _require_super(request: Request):
        return await AuthMiddleware.require_permission(
            db, 'nav-curriculum-button', ['super_admin']
        )(request)

    # =================== BNCC (canônico nacional) ===================

    @router.get("/bncc")
    async def list_bncc(
        request: Request,
        etapa: Optional[str] = None,
        ano: Optional[int] = None,
        componente_codigo: Optional[str] = None,
        q: Optional[str] = Query(None, description="Busca por código ou descrição"),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ):
        await _require_any_auth(request)
        filt: dict = {"ativo": True}
        if etapa:
            filt['etapa'] = etapa
        if ano is not None:
            filt['ano'] = ano
        if componente_codigo:
            filt['componente_codigo'] = componente_codigo
        if q:
            import re
            pattern = re.escape(q)
            filt['$or'] = [
                {'codigo_bncc': {'$regex': f'^{pattern}', '$options': 'i'}},
                {'descricao_bncc': {'$regex': pattern, '$options': 'i'}},
            ]
        total = await db.bncc_skills.count_documents(filt)
        cursor = (
            db.bncc_skills.find(filt, {"_id": 0})
            .sort([("componente_codigo", 1), ("ano", 1), ("codigo_bncc", 1)])
            .skip(offset).limit(limit)
        )
        items = await cursor.to_list(length=limit)
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    @router.get("/bncc/{bncc_id}")
    async def get_bncc(bncc_id: str, request: Request):
        await _require_any_auth(request)
        skill = await db.bncc_skills.find_one({"id": bncc_id}, {"_id": 0})
        if not skill:
            raise HTTPException(404, "BNCC skill não encontrada")
        return skill

    @router.post("/bncc", status_code=201, response_model=BnccSkill)
    async def create_bncc(payload: BnccSkillCreate, request: Request):
        await _require_super(request)
        exists = await db.bncc_skills.find_one({"codigo_bncc": payload.codigo_bncc}, {"_id": 0, "id": 1})
        if exists:
            raise HTTPException(409, f"Código BNCC '{payload.codigo_bncc}' já existe.")
        doc = BnccSkill(**payload.model_dump())
        await db.bncc_skills.insert_one(doc.model_dump())
        return doc

    # =================== ADAPTATIONS (catálogo para UI) ===================

    @router.get("/adaptations")
    async def list_adaptations(
        request: Request,
        component_id: Optional[str] = None,
        componente_codigo: Optional[str] = None,
        ano: Optional[int] = None,
        bimestre: Optional[int] = None,
        etapa: Optional[str] = None,
        mantenedora_id: Optional[str] = None,
        q: Optional[str] = Query(None, description="Busca por código ou descrição"),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ):
        """Retorna o catálogo para o SkillPicker. Faz $lookup com bncc_skills
        e curriculum_components para devolver tudo em 1 chamada.
        """
        user = await _require_any_auth(request)

        filt: dict = {"ativo": True}
        # Escopo por mantenedora: adaptations sem mantenedora (nacionais) são
        # universais; com mantenedora são escopadas.
        if mantenedora_id is not None:
            filt["$or"] = [
                {"mantenedora_id": mantenedora_id},
                {"mantenedora_id": None},
            ]
        else:
            # Se usuário tem mantenedora_id, prioriza as da mantenedora + nacionais.
            user_mant = user.get('mantenedora_id')
            if user_mant:
                filt["$or"] = [
                    {"mantenedora_id": user_mant},
                    {"mantenedora_id": None},
                ]
        if component_id:
            filt["component_id"] = component_id
        if ano is not None:
            filt["ano"] = ano
        if bimestre is not None:
            # Inclusivo: bimestre matching OR null (transversais)
            bim_clauses = [
                {"bimestre": bimestre},
                {"bimestre": None},
                {"bimestre": {"$exists": False}},
            ]
            filt.setdefault("$and", []).append({"$or": bim_clauses})

        # Resolver componente_codigo → lista de component_ids
        if componente_codigo and not component_id:
            comp_ids = [
                c['id'] async for c in db.curriculum_components.find(
                    {"codigo": componente_codigo.upper(), "ativo": True},
                    {"_id": 0, "id": 1},
                )
            ]
            if comp_ids:
                filt["component_id"] = {"$in": comp_ids}
            else:
                return {"items": [], "total": 0, "limit": limit, "offset": offset}

        # Para query textual, precisa procurar em codigo_local + descricao_local
        # e também em bncc_skill. Vamos pegar BNCC ids que batem e expandir.
        if q:
            import re
            pat = re.escape(q)
            bncc_ids_match = [
                b['id'] async for b in db.bncc_skills.find(
                    {"$or": [
                        {"codigo_bncc": {"$regex": f"^{pat}", "$options": "i"}},
                        {"descricao_bncc": {"$regex": pat, "$options": "i"}},
                    ]},
                    {"_id": 0, "id": 1},
                ).limit(200)
            ]
            q_clauses = [
                {"codigo_local": {"$regex": f"^{pat}", "$options": "i"}},
                {"descricao_local": {"$regex": pat, "$options": "i"}},
            ]
            if bncc_ids_match:
                q_clauses.append({"bncc_skill_id": {"$in": bncc_ids_match}})
            filt.setdefault("$and", []).append({"$or": q_clauses})

        total = await db.curriculum_adaptations.count_documents(filt)
        cursor = (
            db.curriculum_adaptations.find(filt, {"_id": 0})
            .sort([("ano", 1), ("bimestre", 1), ("ordem_sequencia", 1)])
            .skip(offset).limit(limit)
        )
        adapts = await cursor.to_list(length=limit)

        # Resolve BNCC + componente num único lookup batch
        bncc_ids = {a['bncc_skill_id'] for a in adapts if a.get('bncc_skill_id')}
        comp_ids = {a['component_id'] for a in adapts if a.get('component_id')}
        bncc_map: dict = {}
        if bncc_ids:
            async for b in db.bncc_skills.find({"id": {"$in": list(bncc_ids)}}, {"_id": 0}):
                bncc_map[b['id']] = b
        comp_map: dict = {}
        if comp_ids:
            async for c in db.curriculum_components.find({"id": {"$in": list(comp_ids)}}, {"_id": 0}):
                comp_map[c['id']] = c

        # Flatten shape for UI
        items = []
        for a in adapts:
            bncc = bncc_map.get(a.get('bncc_skill_id')) if a.get('bncc_skill_id') else None
            comp = comp_map.get(a.get('component_id'))
            items.append({
                "adaptation_id": a["id"],
                "codigo": (bncc and bncc.get("codigo_bncc")) or a.get("codigo_local"),
                "codigo_bncc": bncc and bncc.get("codigo_bncc"),
                "codigo_local": a.get("codigo_local"),
                "descricao": a.get("descricao_local") or (bncc and bncc.get("descricao_bncc")) or "",
                "descricao_bncc": bncc and bncc.get("descricao_bncc"),
                "eixo": a.get("eixo_local") or (bncc and bncc.get("eixo")),
                "objeto_conhecimento": a.get("objeto_conhecimento"),
                "ano": a.get("ano"),
                "bimestre": a.get("bimestre"),
                "ordem_sequencia": a.get("ordem_sequencia", 0),
                "fonte": a.get("fonte"),
                "componente_codigo": comp and comp.get("codigo"),
                "componente_nome": comp and comp.get("nome"),
                "component_id": a.get("component_id"),
                "mantenedora_id": a.get("mantenedora_id"),
                "has_bncc": bool(bncc),
            })

        return {"items": items, "total": total, "limit": limit, "offset": offset}

    @router.get("/adaptations/availability")
    async def adaptations_availability(
        request: Request,
        component_id: Optional[str] = None,
        componente_codigo: Optional[str] = None,
        ano: Optional[int] = Query(None),
        bimestre: Optional[int] = None,
    ):
        """Para o frontend decidir se `adaptation_id` é obrigatório:
        retorna `{required: bool, count: int}`. Regra: se houver ao menos 1
        adaptation para o slot, o campo é obrigatório.
        """
        user = await _require_any_auth(request)
        filt: dict = {"ativo": True}
        user_mant = user.get('mantenedora_id')
        if user_mant:
            filt["$or"] = [{"mantenedora_id": user_mant}, {"mantenedora_id": None}]
        if component_id:
            filt["component_id"] = component_id
        elif componente_codigo:
            comp_ids = [
                c['id'] async for c in db.curriculum_components.find(
                    {"codigo": componente_codigo.upper(), "ativo": True},
                    {"_id": 0, "id": 1},
                )
            ]
            if not comp_ids:
                return {"required": False, "count": 0, "reason": "no_component_match"}
            filt["component_id"] = {"$in": comp_ids}
        if ano is not None:
            filt["ano"] = ano
        if bimestre is not None:
            filt.setdefault("$and", []).append({"$or": [
                {"bimestre": bimestre}, {"bimestre": None}, {"bimestre": {"$exists": False}},
            ]})
        count = await db.curriculum_adaptations.count_documents(filt)
        return {"required": count > 0, "count": count}

    @router.get("/adaptations/{adapt_id}")
    async def get_adaptation(adapt_id: str, request: Request):
        await _require_any_auth(request)
        a = await db.curriculum_adaptations.find_one({"id": adapt_id}, {"_id": 0})
        if not a:
            raise HTTPException(404, "Adaptation não encontrada")
        bncc = None
        if a.get('bncc_skill_id'):
            bncc = await db.bncc_skills.find_one({"id": a['bncc_skill_id']}, {"_id": 0})
        comp = await db.curriculum_components.find_one({"id": a['component_id']}, {"_id": 0})
        methods = await db.curriculum_adaptation_methods.find(
            {"adaptation_id": adapt_id, "ativo": True}, {"_id": 0}
        ).to_list(length=100)
        return {
            "adaptation": a,
            "bncc": bncc,
            "componente": comp,
            "metodologias": methods,
        }

    @router.post("/adaptations", status_code=201)
    async def create_adaptation(payload: CurriculumAdaptationCreate, request: Request):
        user = await _require_super(request)
        # Valida que componente existe
        comp = await db.curriculum_components.find_one({"id": payload.component_id}, {"_id": 0, "id": 1})
        if not comp:
            raise HTTPException(400, "component_id inexistente")
        if payload.bncc_skill_id:
            bncc = await db.bncc_skills.find_one({"id": payload.bncc_skill_id}, {"_id": 0, "id": 1})
            if not bncc:
                raise HTTPException(400, "bncc_skill_id inexistente")
        # mantenedora_id default = usuário atual
        data = payload.model_dump()
        if not data.get('mantenedora_id'):
            data['mantenedora_id'] = user.get('mantenedora_id')
        doc = CurriculumAdaptation(**data)
        try:
            await db.curriculum_adaptations.insert_one(doc.model_dump())
        except Exception as e:
            raise HTTPException(409, f"Conflito de unicidade: {e}")
        return doc.model_dump()

    @router.put("/adaptations/{adapt_id}")
    async def update_adaptation(adapt_id: str, payload: CurriculumAdaptationUpdate, request: Request):
        await _require_super(request)
        update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
        if not update:
            raise HTTPException(400, "Nada para atualizar")
        from datetime import datetime, timezone
        update['updated_at'] = datetime.now(timezone.utc).isoformat()
        r = await db.curriculum_adaptations.update_one({"id": adapt_id}, {"$set": update})
        if r.matched_count == 0:
            raise HTTPException(404, "Adaptation não encontrada")
        return {"ok": True, "updated": list(update.keys())}

    @router.delete("/adaptations/{adapt_id}")
    async def delete_adaptation(adapt_id: str, request: Request):
        await _require_super(request)
        # Checa se alguma learning_object a referencia
        in_use = await db.learning_objects.count_documents({"adaptation_ids": adapt_id})
        if in_use > 0:
            # Soft delete
            r = await db.curriculum_adaptations.update_one(
                {"id": adapt_id}, {"$set": {"ativo": False}}
            )
            if r.matched_count == 0:
                raise HTTPException(404, "Adaptation não encontrada")
            return {"ok": True, "soft_deleted": True, "in_use_by": in_use}
        r = await db.curriculum_adaptations.delete_one({"id": adapt_id})
        if r.deleted_count == 0:
            raise HTTPException(404, "Adaptation não encontrada")
        return {"ok": True, "deleted": True}

    # =================== MIGRATION ===================

    @router.post("/v2/migrate")
    async def migrate_v2(request: Request):
        """Roda migração idempotente completa. Seguro para re-execução."""
        await _require_super(request)
        result = await run_full_migration(db)
        return {"ok": True, **result}

    # =================== COVERAGE (Sprint C) ===================

    @router.get("/coverage")
    async def curriculum_coverage(
        request: Request,
        class_id: Optional[str] = None,
        academic_year: Optional[int] = None,
        component_id: Optional[str] = None,
    ):
        """Cobertura curricular: % de adaptations cobertas pelas aulas registradas.

        Retorna totais por (componente, ano, bimestre) + lista de pendências.
        """
        user = await _require_any_auth(request)
        user_mant = user.get('mantenedora_id')
        # 1. Base de adaptações (denominador)
        filt_a: dict = {"ativo": True}
        if user_mant:
            filt_a["$or"] = [{"mantenedora_id": user_mant}, {"mantenedora_id": None}]
        if component_id:
            filt_a["component_id"] = component_id
        all_adaptations = await db.curriculum_adaptations.find(filt_a, {"_id": 0}).to_list(length=5000)

        # 2. IDs usados em learning_objects (numerador)
        filt_lo: dict = {}
        if class_id:
            filt_lo["class_id"] = class_id
        if academic_year is not None:
            filt_lo["academic_year"] = academic_year
        used_ids: set = set()
        cursor = db.learning_objects.find(
            filt_lo, {"_id": 0, "adaptation_ids": 1}
        )
        async for lo in cursor:
            for aid in (lo.get("adaptation_ids") or []):
                used_ids.add(aid)

        # 3. Agrega por (componente, ano, bimestre)
        from collections import defaultdict
        comp_map: dict = {}
        async for c in db.curriculum_components.find({}, {"_id": 0, "id": 1, "codigo": 1, "nome": 1}):
            comp_map[c['id']] = c
        buckets: dict = defaultdict(lambda: {"total": 0, "covered": 0, "pending": []})
        for a in all_adaptations:
            comp = comp_map.get(a['component_id']) or {}
            key = (comp.get('codigo') or a['component_id'], a.get('ano'), a.get('bimestre'))
            b = buckets[key]
            b["total"] += 1
            if a['id'] in used_ids:
                b["covered"] += 1
            else:
                b["pending"].append({
                    "adaptation_id": a['id'],
                    "codigo": a.get('codigo_local'),
                    "bncc_skill_id": a.get('bncc_skill_id'),
                })

        rows = []
        for (codigo, ano, bimestre), b in sorted(buckets.items()):
            rows.append({
                "componente_codigo": codigo,
                "ano": ano,
                "bimestre": bimestre,
                "total": b["total"],
                "covered": b["covered"],
                "pct": round((b["covered"] / b["total"] * 100) if b["total"] else 0, 1),
                "pending": b["pending"][:20],
                "pending_count": len(b["pending"]),
            })
        totals = {
            "total": sum(r["total"] for r in rows),
            "covered": sum(r["covered"] for r in rows),
        }
        totals["pct"] = round((totals["covered"] / totals["total"] * 100) if totals["total"] else 0, 1)
        return {"totals": totals, "rows": rows}

    return router
