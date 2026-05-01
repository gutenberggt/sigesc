"""
Currículo (BNCC/DCM Floresta do Araguaia) — Sprint A.

Catálogo curricular vivo que indexa Componentes Curriculares, Habilidades
(com código tipo EF01LP02) e Metodologias. Serve a UI de Currículo
(super_admin) e os professores no Registro de Conteúdos.

Endpoints:
  Componentes:
    GET    /api/curriculum/components
    POST   /api/curriculum/components            (super_admin)
    PUT    /api/curriculum/components/{id}       (super_admin)
    DELETE /api/curriculum/components/{id}       (super_admin)

  Habilidades:
    GET    /api/curriculum/skills?componente_id=&ano=&bimestre=&q=&fonte=
    GET    /api/curriculum/skills/{codigo}
    POST   /api/curriculum/skills                (super_admin)
    PUT    /api/curriculum/skills/{id}           (super_admin)
    DELETE /api/curriculum/skills/{id}           (super_admin)

  Metodologias:
    GET    /api/curriculum/methods
    POST   /api/curriculum/methods               (super_admin)
    PUT    /api/curriculum/methods/{id}          (super_admin)
    DELETE /api/curriculum/methods/{id}          (super_admin)

Cobertura curricular (Sprint C) será exposta em /api/curriculum/coverage.
"""
from __future__ import annotations

from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException, Query
from datetime import datetime, timezone

from auth_middleware import AuthMiddleware
from models import (
    CurriculumComponent, CurriculumComponentCreate, CurriculumComponentUpdate,
    CurriculumSkill, CurriculumSkillCreate, CurriculumSkillUpdate,
    CurriculumMethod, CurriculumMethodCreate, CurriculumMethodUpdate,
)

router = APIRouter(prefix="/curriculum", tags=["Currículo"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def setup_router(db):

    async def _require_super(request: Request):
        return await AuthMiddleware.require_permission(
            db, 'nav-curriculum-button', ['super_admin']
        )(request)

    async def _require_auth(request: Request):
        return await AuthMiddleware.get_current_user(request)

    # =================== COMPONENTES ===================

    @router.get("/components")
    async def list_components(
        request: Request,
        etapa: Optional[str] = None,
        fonte: Optional[str] = None,
        ativo: Optional[bool] = True,
    ):
        await _require_auth(request)
        q = {}
        if etapa:
            q['etapa'] = etapa
        if fonte:
            q['fonte'] = fonte
        if ativo is not None:
            q['ativo'] = ativo
        cursor = db.curriculum_components.find(q, {'_id': 0}).sort([('ordem', 1), ('nome', 1)])
        return await cursor.to_list(length=500)

    @router.post("/components", status_code=201)
    async def create_component(payload: CurriculumComponentCreate, request: Request):
        await _require_super(request)
        # Unicidade por (codigo, etapa, fonte)
        exists = await db.curriculum_components.find_one(
            {"codigo": payload.codigo, "etapa": payload.etapa, "fonte": payload.fonte},
            {"_id": 0, "id": 1}
        )
        if exists:
            raise HTTPException(409, "Componente já existe (codigo+etapa+fonte).")
        comp = CurriculumComponent(**payload.model_dump())
        await db.curriculum_components.insert_one(comp.model_dump())
        return comp.model_dump()

    @router.put("/components/{component_id}")
    async def update_component(component_id: str, payload: CurriculumComponentUpdate, request: Request):
        await _require_super(request)
        update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
        if not update:
            raise HTTPException(400, "Nada para atualizar.")
        update['updated_at'] = _now()
        r = await db.curriculum_components.update_one({"id": component_id}, {"$set": update})
        if r.matched_count == 0:
            raise HTTPException(404, "Componente não encontrado.")
        # Se mudou o código, repropaga em skills
        if 'codigo' in update:
            await db.curriculum_skills.update_many(
                {"componente_id": component_id},
                {"$set": {"componente_codigo": update['codigo'], "updated_at": _now()}}
            )
        return {"ok": True}

    @router.delete("/components/{component_id}")
    async def delete_component(component_id: str, request: Request):
        await _require_super(request)
        # Se há skills vinculadas, apenas inativa.
        n_skills = await db.curriculum_skills.count_documents({"componente_id": component_id, "ativo": True})
        if n_skills > 0:
            await db.curriculum_components.update_one(
                {"id": component_id},
                {"$set": {"ativo": False, "updated_at": _now()}}
            )
            return {"ok": True, "soft_deleted": True, "skills_vinculadas": n_skills}
        r = await db.curriculum_components.delete_one({"id": component_id})
        if r.deleted_count == 0:
            raise HTTPException(404, "Componente não encontrado.")
        return {"ok": True, "deleted": True}

    # =================== HABILIDADES ===================

    @router.get("/skills")
    async def list_skills(
        request: Request,
        componente_id: Optional[str] = None,
        ano: Optional[int] = None,
        bimestre: Optional[int] = None,
        fonte: Optional[str] = None,
        etapa: Optional[str] = None,
        q: Optional[str] = Query(None, description="Busca por código ou descrição"),
        ativo: Optional[bool] = True,
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ):
        await _require_auth(request)
        filt: dict = {}
        if componente_id:
            filt['componente_id'] = componente_id
        if ano is not None:
            filt['ano'] = ano
        bimestre_clauses = None
        if bimestre is not None:
            # Inclui também habilidades sem bimestre (transversais ao ano), para
            # não esconder seeds genéricos como BNCC_COMPUTACAO.
            bimestre_clauses = [
                {'bimestre': bimestre},
                {'bimestre': None},
                {'bimestre': {'$exists': False}},
            ]
        if fonte:
            filt['fonte'] = fonte
        if ativo is not None:
            filt['ativo'] = ativo
        q_clauses = None
        if q:
            import re
            pattern = re.escape(q)
            q_clauses = [
                {'codigo': {'$regex': f'^{pattern}', '$options': 'i'}},
                {'descricao': {'$regex': pattern, '$options': 'i'}},
            ]

        # Combina cláusulas $or sem conflito
        and_clauses = []
        if bimestre_clauses:
            and_clauses.append({'$or': bimestre_clauses})
        if q_clauses:
            and_clauses.append({'$or': q_clauses})
        if len(and_clauses) == 1:
            filt.update(and_clauses[0])
        elif len(and_clauses) >= 2:
            filt['$and'] = and_clauses

        # Filtro derivado: etapa via componente
        if etapa and 'componente_id' not in filt:
            comp_ids = [
                c['id'] async for c in
                db.curriculum_components.find({"etapa": etapa, "ativo": True}, {"_id": 0, "id": 1})
            ]
            if comp_ids:
                filt['componente_id'] = {"$in": comp_ids}
            else:
                return {"items": [], "total": 0}

        total = await db.curriculum_skills.count_documents(filt)
        cursor = (
            db.curriculum_skills.find(filt, {"_id": 0})
            .sort([("componente_codigo", 1), ("ano", 1), ("bimestre", 1), ("codigo", 1)])
            .skip(offset).limit(limit)
        )
        items = await cursor.to_list(length=limit)
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    @router.get("/skills/{codigo}")
    async def get_skill(codigo: str, request: Request):
        await _require_auth(request)
        skill = await db.curriculum_skills.find_one({"codigo": codigo}, {"_id": 0})
        if not skill:
            raise HTTPException(404, f"Habilidade '{codigo}' não encontrada.")
        # Junta componente
        comp = await db.curriculum_components.find_one(
            {"id": skill['componente_id']}, {"_id": 0}
        )
        # Junta métodos recomendados
        methods = []
        if skill.get('metodos_recomendados'):
            cursor = db.curriculum_methods.find(
                {"id": {"$in": skill['metodos_recomendados']}}, {"_id": 0}
            )
            methods = await cursor.to_list(length=50)
        return {**skill, "componente": comp, "metodos": methods}

    @router.post("/skills", status_code=201)
    async def create_skill(payload: CurriculumSkillCreate, request: Request):
        await _require_super(request)
        comp = await db.curriculum_components.find_one(
            {"id": payload.componente_id}, {"_id": 0, "codigo": 1}
        )
        if not comp:
            raise HTTPException(400, "Componente não encontrado.")
        exists = await db.curriculum_skills.find_one({"codigo": payload.codigo}, {"_id": 0, "id": 1})
        if exists:
            raise HTTPException(409, f"Habilidade '{payload.codigo}' já existe.")
        skill = CurriculumSkill(
            **payload.model_dump(),
            componente_codigo=comp.get('codigo'),
        )
        await db.curriculum_skills.insert_one(skill.model_dump())
        return skill.model_dump()

    @router.put("/skills/{skill_id}")
    async def update_skill(skill_id: str, payload: CurriculumSkillUpdate, request: Request):
        await _require_super(request)
        update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
        if 'componente_id' in update:
            comp = await db.curriculum_components.find_one(
                {"id": update['componente_id']}, {"_id": 0, "codigo": 1}
            )
            if not comp:
                raise HTTPException(400, "Componente alvo não encontrado.")
            update['componente_codigo'] = comp.get('codigo')
        update['updated_at'] = _now()
        r = await db.curriculum_skills.update_one({"id": skill_id}, {"$set": update})
        if r.matched_count == 0:
            raise HTTPException(404, "Habilidade não encontrada.")
        return {"ok": True}

    @router.delete("/skills/{skill_id}")
    async def delete_skill(skill_id: str, request: Request):
        await _require_super(request)
        r = await db.curriculum_skills.delete_one({"id": skill_id})
        if r.deleted_count == 0:
            raise HTTPException(404, "Habilidade não encontrada.")
        return {"ok": True}

    # =================== METODOLOGIAS ===================

    @router.get("/methods")
    async def list_methods(request: Request, ativo: Optional[bool] = True):
        await _require_auth(request)
        q = {}
        if ativo is not None:
            q['ativo'] = ativo
        cursor = db.curriculum_methods.find(q, {"_id": 0}).sort([("nome", 1)])
        return await cursor.to_list(length=500)

    @router.post("/methods", status_code=201)
    async def create_method(payload: CurriculumMethodCreate, request: Request):
        await _require_super(request)
        m = CurriculumMethod(**payload.model_dump())
        await db.curriculum_methods.insert_one(m.model_dump())
        return m.model_dump()

    @router.put("/methods/{method_id}")
    async def update_method(method_id: str, payload: CurriculumMethodUpdate, request: Request):
        await _require_super(request)
        update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
        if not update:
            raise HTTPException(400, "Nada para atualizar.")
        update['updated_at'] = _now()
        r = await db.curriculum_methods.update_one({"id": method_id}, {"$set": update})
        if r.matched_count == 0:
            raise HTTPException(404, "Metodologia não encontrada.")
        return {"ok": True}

    @router.delete("/methods/{method_id}")
    async def delete_method(method_id: str, request: Request):
        await _require_super(request)
        r = await db.curriculum_methods.delete_one({"id": method_id})
        if r.deleted_count == 0:
            raise HTTPException(404, "Metodologia não encontrada.")
        return {"ok": True}

    # =================== STATS (atalho para Dashboard de Cobertura na Sprint C) ===================

    @router.get("/stats")
    async def get_stats(request: Request):
        await _require_auth(request)
        return {
            "components": await db.curriculum_components.count_documents({"ativo": True}),
            "skills": await db.curriculum_skills.count_documents({"ativo": True}),
            "methods": await db.curriculum_methods.count_documents({"ativo": True}),
            "by_fonte": {
                fonte: await db.curriculum_skills.count_documents({"fonte": fonte, "ativo": True})
                for fonte in ["BNCC", "BNCC_COMPUTACAO", "DCM_FA", "MUNICIPAL"]
            },
        }

    return router
