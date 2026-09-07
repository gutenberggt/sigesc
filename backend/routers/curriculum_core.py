"""Núcleo Curricular Canônico — F2/F3.

Camada aditiva entre as fontes curriculares oficiais e o registro docente:
``curriculum_sources`` → ``curriculum_versions`` → ``teaching_plans``.

Não migra histórico e nunca escreve em ``learning_objects``. Durante a transição,
``curriculum_adaptations`` permanece como catálogo de habilidades referenciáveis
pelos itens do Plano de Ensino Bimestral.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
from typing import Any, Literal, Optional
import uuid

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator

from auth_middleware import AuthMiddleware
from tenant_scope import (
    INVALID_TENANT_SENTINEL,
    assert_same_tenant,
    get_mantenedora_scope,
    is_super_admin,
)


READ_PERMISSION_KEY = "nav-curriculum-button"
MANAGE_PERMISSION_KEY = "nav-curriculum-button"
MANAGE_DEFAULT_ROLES = ["super_admin", "coordenador"]


class CurriculumSourceCreate(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    source_type: Literal[
        "BNCC", "BNCC_COMPUTACAO", "DCM", "REFERENCIAL_MUNICIPAL", "OUTRO_OFICIAL"
    ]
    scope: Literal["tenant", "national"] = "tenant"
    description: Optional[str] = Field(default=None, max_length=4000)
    document_url: Optional[str] = Field(default=None, max_length=2000)
    document_sha256: Optional[str] = Field(default=None, max_length=128)
    academic_year: Optional[int] = Field(default=None, ge=2000, le=2200)
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CurriculumSourceUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=300)
    description: Optional[str] = Field(default=None, max_length=4000)
    document_url: Optional[str] = Field(default=None, max_length=2000)
    document_sha256: Optional[str] = Field(default=None, max_length=128)
    academic_year: Optional[int] = Field(default=None, ge=2000, le=2200)
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    active: Optional[bool] = None


class CurriculumVersionCreate(BaseModel):
    name: str = Field(min_length=3, max_length=250)
    academic_year: int = Field(ge=2000, le=2200)
    source_ids: list[str] = Field(min_length=1)
    valid_from: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=5000)


class CurriculumVersionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=250)
    source_ids: Optional[list[str]] = None
    valid_from: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=5000)


class NamedCurricularElement(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    label: str = Field(min_length=1, max_length=1000)
    source_page: Optional[int] = Field(default=None, ge=1)
    source_text: Optional[str] = Field(default=None, max_length=4000)


class TeachingPlanItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    adaptation_id: str
    skill_code_snapshot: Optional[str] = Field(default=None, max_length=120)
    skill_description_snapshot: Optional[str] = Field(default=None, max_length=5000)
    learning_objective: Optional[str] = Field(default=None, max_length=5000)
    knowledge_objects: list[NamedCurricularElement] = Field(default_factory=list)
    pedagogical_practices: list[NamedCurricularElement] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    sequence: int = Field(default=0, ge=0)


class TeachingPlanCreate(BaseModel):
    curriculum_version_id: str
    academic_year: int = Field(ge=2000, le=2200)
    component_id: str
    bimestre: int = Field(ge=1, le=4)
    grade_scope: list[str] = Field(min_length=1)
    education_stage: Optional[str] = Field(default=None, max_length=100)
    title: str = Field(min_length=3, max_length=300)
    items: list[TeachingPlanItem] = Field(default_factory=list)
    notes: Optional[str] = Field(default=None, max_length=5000)

    @field_validator("grade_scope")
    @classmethod
    def normalize_grade_scope(cls, value: list[str]) -> list[str]:
        result = [str(item).strip() for item in value if str(item).strip()]
        if not result:
            raise ValueError("grade_scope não pode ser vazio")
        return list(dict.fromkeys(result))


class TeachingPlanUpdate(BaseModel):
    education_stage: Optional[str] = Field(default=None, max_length=100)
    title: Optional[str] = Field(default=None, min_length=3, max_length=300)
    items: Optional[list[TeachingPlanItem]] = None
    notes: Optional[str] = Field(default=None, max_length=5000)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _public(doc: Optional[dict]) -> Optional[dict]:
    if doc is None:
        return None
    result = dict(doc)
    result.pop("_id", None)
    return result


def _grade_key(values: list[str]) -> str:
    return "|".join(sorted({str(v).strip() for v in values if str(v).strip()}))


async def _require_read(db, request: Request) -> dict:
    """Qualquer autenticado, salvo revogação explícita na Matriz."""
    user = await AuthMiddleware.get_current_user(request)
    if is_super_admin(user):
        return user
    role = user.get("role")
    try:
        override = await db.permission_overrides.find_one(
            {"item_key": READ_PERMISSION_KEY, "role": role}, {"_id": 0, "visible": 1}
        )
    except Exception:
        override = None
    if override is not None and not override.get("visible"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Acesso negado pela Matriz de Permissões ({READ_PERMISSION_KEY} × {role})",
        )
    return user


async def _require_manage(db, request: Request) -> dict:
    return await AuthMiddleware.require_permission(
        db, MANAGE_PERMISSION_KEY, MANAGE_DEFAULT_ROLES
    )(request)


def _tenant_id(user: dict, request: Request) -> str:
    tenant_id = get_mantenedora_scope(user, request)
    if not tenant_id or tenant_id == INVALID_TENANT_SENTINEL:
        raise HTTPException(
            409,
            detail={
                "code": "CURRICULUM_TENANT_REQUIRED",
                "message": "Selecione uma mantenedora para operar o currículo.",
            },
        )
    return tenant_id


async def _ensure_indexes(db) -> None:
    """Índices aditivos e idempotentes; não reescrevem histórico."""
    await db.curriculum_sources.create_index(
        [("mantenedora_id", 1), ("source_type", 1), ("title", 1)],
        name="ix_curriculum_sources_tenant_type_title",
    )
    await db.curriculum_versions.create_index(
        [("mantenedora_id", 1), ("academic_year", 1), ("status", 1)],
        name="ix_curriculum_versions_tenant_year_status",
    )
    await db.teaching_plans.create_index(
        [
            ("mantenedora_id", 1), ("curriculum_version_id", 1),
            ("academic_year", 1), ("component_id", 1),
            ("bimestre", 1), ("grade_key", 1),
        ],
        unique=True,
        name="uq_teaching_plan_scope",
    )
    await db.teaching_plans.create_index(
        [("mantenedora_id", 1), ("academic_year", 1), ("status", 1)],
        name="ix_teaching_plans_tenant_year_status",
    )


async def _validate_source_ids(db, source_ids: list[str], tenant_id: str) -> list[str]:
    requested = list(dict.fromkeys(source_ids))
    if not requested:
        raise HTTPException(422, "Informe pelo menos uma fonte curricular.")
    docs = await db.curriculum_sources.find(
        {
            "id": {"$in": requested}, "active": True,
            "$or": [
                {"mantenedora_id": tenant_id},
                {"scope": "national", "mantenedora_id": None},
            ],
        },
        {"_id": 0, "id": 1},
    ).to_list(length=len(requested))
    found = {doc["id"] for doc in docs}
    missing = [source_id for source_id in requested if source_id not in found]
    if missing:
        raise HTTPException(
            422,
            detail={
                "code": "CURRICULUM_SOURCE_SCOPE_INVALID",
                "message": "Fonte inexistente, inativa ou fora da mantenedora ativa.",
                "source_ids": missing[:20],
            },
        )
    return requested


async def _validate_plan_items(db, items: list[TeachingPlanItem], tenant_id: str) -> None:
    adaptation_ids = list(dict.fromkeys(item.adaptation_id for item in items))
    if not adaptation_ids:
        return
    docs = await db.curriculum_adaptations.find(
        {
            "id": {"$in": adaptation_ids}, "ativo": True,
            "$or": [{"mantenedora_id": tenant_id}, {"mantenedora_id": None}],
        },
        {"_id": 0, "id": 1},
    ).to_list(length=len(adaptation_ids))
    found = {doc["id"] for doc in docs}
    missing = [adaptation_id for adaptation_id in adaptation_ids if adaptation_id not in found]
    if missing:
        raise HTTPException(
            422,
            detail={
                "code": "TEACHING_PLAN_SKILL_INVALID",
                "message": "Habilidade inexistente, inativa ou fora da mantenedora ativa.",
                "adaptation_ids": missing[:20],
            },
        )


async def _resolve_bimestre(db, tenant_id: str, academic_year: int, target_date: str) -> Optional[int]:
    cal = await db.calendario_letivo.find_one(
        {
            "ano_letivo": academic_year,
            "$or": [
                {"mantenedora_id": tenant_id},
                {"mantenedora_id": None},
                {"mantenedora_id": {"$exists": False}},
            ],
        },
        {"_id": 0},
    )
    if not cal:
        return None
    ymd = str(target_date)[:10]
    for bimestre in range(1, 5):
        start = str(cal.get(f"bimestre_{bimestre}_inicio") or "")[:10]
        end = str(cal.get(f"bimestre_{bimestre}_fim") or "")[:10]
        if start and end and start <= ymd <= end:
            return bimestre
    return None


def build_curriculum_core_router(db) -> APIRouter:
    router = APIRouter(tags=["Núcleo Curricular Canônico"])

    @router.get("/sources")
    async def list_sources(request: Request, active_only: bool = True):
        user = await _require_read(db, request)
        tenant_id = _tenant_id(user, request)
        query: dict[str, Any] = {
            "$or": [
                {"mantenedora_id": tenant_id},
                {"scope": "national", "mantenedora_id": None},
            ]
        }
        if active_only:
            query["active"] = True
        items = await db.curriculum_sources.find(query, {"_id": 0}).sort(
            [("scope", 1), ("source_type", 1), ("title", 1)]
        ).to_list(length=1000)
        return {"items": items, "total": len(items)}

    @router.post("/sources", status_code=201)
    async def create_source(payload: CurriculumSourceCreate, request: Request):
        user = await _require_manage(db, request)
        tenant_id = _tenant_id(user, request)
        await _ensure_indexes(db)
        if payload.scope == "national" and not is_super_admin(user):
            raise HTTPException(403, "Somente Super Administrador pode registrar fonte nacional.")
        now = _now()
        doc = {
            "id": str(uuid.uuid4()), **payload.model_dump(),
            "mantenedora_id": None if payload.scope == "national" else tenant_id,
            "active": True,
            "created_by": user.get("id"), "created_at": now,
            "updated_by": user.get("id"), "updated_at": now,
        }
        await db.curriculum_sources.insert_one(doc)
        return _public(doc)

    @router.put("/sources/{source_id}")
    async def update_source(source_id: str, payload: CurriculumSourceUpdate, request: Request):
        user = await _require_manage(db, request)
        _tenant_id(user, request)
        current = await db.curriculum_sources.find_one({"id": source_id}, {"_id": 0})
        if not current:
            raise HTTPException(404, "Fonte curricular não encontrada")
        if current.get("scope") == "national":
            if not is_super_admin(user):
                raise HTTPException(403, "Fonte nacional é administrada pelo Super Administrador.")
        else:
            assert_same_tenant(current, user, request)
        update = payload.model_dump(exclude_unset=True)
        if not update:
            raise HTTPException(400, "Nada para atualizar")
        update.update({"updated_by": user.get("id"), "updated_at": _now()})
        await db.curriculum_sources.update_one({"id": source_id}, {"$set": update})
        return _public(await db.curriculum_sources.find_one({"id": source_id}, {"_id": 0}))

    @router.get("/versions")
    async def list_versions(
        request: Request,
        academic_year: Optional[int] = Query(default=None, ge=2000, le=2200),
        status_filter: Optional[str] = Query(default=None, alias="status"),
    ):
        user = await _require_read(db, request)
        tenant_id = _tenant_id(user, request)
        query: dict[str, Any] = {"mantenedora_id": tenant_id}
        if academic_year is not None:
            query["academic_year"] = academic_year
        if status_filter:
            query["status"] = status_filter
        items = await db.curriculum_versions.find(query, {"_id": 0}).sort(
            [("academic_year", -1), ("revision", -1)]
        ).to_list(length=500)
        return {"items": items, "total": len(items)}

    @router.post("/versions", status_code=201)
    async def create_version(payload: CurriculumVersionCreate, request: Request):
        user = await _require_manage(db, request)
        tenant_id = _tenant_id(user, request)
        await _ensure_indexes(db)
        source_ids = await _validate_source_ids(db, payload.source_ids, tenant_id)
        latest = await db.curriculum_versions.find_one(
            {"mantenedora_id": tenant_id, "academic_year": payload.academic_year},
            {"_id": 0, "revision": 1}, sort=[("revision", -1)],
        )
        revision = int((latest or {}).get("revision") or 0) + 1
        now = _now()
        doc = {
            "id": str(uuid.uuid4()), **payload.model_dump(), "source_ids": source_ids,
            "mantenedora_id": tenant_id, "revision": revision, "status": "draft",
            "published_at": None, "published_by": None, "superseded_at": None,
            "created_by": user.get("id"), "created_at": now,
            "updated_by": user.get("id"), "updated_at": now,
        }
        await db.curriculum_versions.insert_one(doc)
        return _public(doc)

    @router.put("/versions/{version_id}")
    async def update_version(version_id: str, payload: CurriculumVersionUpdate, request: Request):
        user = await _require_manage(db, request)
        tenant_id = _tenant_id(user, request)
        current = await db.curriculum_versions.find_one(
            {"id": version_id, "mantenedora_id": tenant_id}, {"_id": 0}
        )
        if not current:
            raise HTTPException(404, "Versão curricular não encontrada")
        if current.get("status") != "draft":
            raise HTTPException(409, detail={"code": "CURRICULUM_VERSION_IMMUTABLE"})
        update = payload.model_dump(exclude_unset=True)
        if "source_ids" in update:
            update["source_ids"] = await _validate_source_ids(db, update["source_ids"], tenant_id)
        if not update:
            raise HTTPException(400, "Nada para atualizar")
        update.update({"updated_by": user.get("id"), "updated_at": _now()})
        await db.curriculum_versions.update_one({"id": version_id}, {"$set": update})
        return _public(await db.curriculum_versions.find_one({"id": version_id}, {"_id": 0}))

    @router.post("/versions/{version_id}/publish")
    async def publish_version(version_id: str, request: Request):
        user = await _require_manage(db, request)
        tenant_id = _tenant_id(user, request)
        current = await db.curriculum_versions.find_one(
            {"id": version_id, "mantenedora_id": tenant_id}, {"_id": 0}
        )
        if not current:
            raise HTTPException(404, "Versão curricular não encontrada")
        if current.get("status") == "published":
            return current
        if current.get("status") != "draft":
            raise HTTPException(409, "Somente versão em rascunho pode ser publicada.")
        await _validate_source_ids(db, current.get("source_ids") or [], tenant_id)
        now = _now()
        await db.curriculum_versions.update_many(
            {
                "mantenedora_id": tenant_id, "academic_year": current["academic_year"],
                "status": "published", "id": {"$ne": version_id},
            },
            {"$set": {"status": "superseded", "superseded_at": now, "updated_at": now}},
        )
        await db.curriculum_versions.update_one(
            {"id": version_id},
            {"$set": {
                "status": "published", "published_at": now, "published_by": user.get("id"),
                "updated_by": user.get("id"), "updated_at": now,
            }},
        )
        return _public(await db.curriculum_versions.find_one({"id": version_id}, {"_id": 0}))

    # Deve preceder a rota dinâmica /teaching-plans/{plan_id}.
    @router.get("/teaching-plans/context")
    async def teaching_plan_context(
        request: Request, class_id: str, component_id: str,
        date: Optional[str] = None,
        academic_year: Optional[int] = Query(default=None, ge=2000, le=2200),
        bimestre: Optional[int] = Query(default=None, ge=1, le=4),
    ):
        user = await _require_read(db, request)
        tenant_id = _tenant_id(user, request)
        class_doc = await db.classes.find_one({"id": class_id}, {"_id": 0})
        if not class_doc:
            raise HTTPException(404, "Turma não encontrada")
        assert_same_tenant(class_doc, user, request)
        year = int(academic_year or class_doc.get("academic_year") or datetime.now().year)
        resolved_bimestre = bimestre or (
            await _resolve_bimestre(db, tenant_id, year, date) if date else None
        )
        if resolved_bimestre is None:
            raise HTTPException(
                422,
                detail={
                    "code": "TEACHING_PLAN_BIMESTER_REQUIRED",
                    "message": "Não foi possível determinar o bimestre; informe-o explicitamente.",
                },
            )
        grade = str(
            class_doc.get("grade_level") or class_doc.get("series") or class_doc.get("serie") or ""
        ).strip()
        query: dict[str, Any] = {
            "mantenedora_id": tenant_id, "academic_year": year,
            "component_id": component_id, "bimestre": resolved_bimestre,
            "status": "published",
        }
        if grade:
            query["grade_scope"] = grade
        plan = await db.teaching_plans.find_one(query, {"_id": 0}, sort=[("revision", -1)])
        if not plan:
            return {
                "status": "missing", "plan": None, "academic_year": year,
                "bimestre": resolved_bimestre, "grade": grade or None,
                "component_id": component_id,
                "message": "Não há Plano de Ensino Bimestral publicado para este contexto.",
            }
        return {
            "status": "published", "plan": plan, "academic_year": year,
            "bimestre": resolved_bimestre, "grade": grade or None,
            "component_id": component_id,
        }

    @router.get("/teaching-plans")
    async def list_teaching_plans(
        request: Request,
        academic_year: Optional[int] = Query(default=None, ge=2000, le=2200),
        component_id: Optional[str] = None,
        bimestre: Optional[int] = Query(default=None, ge=1, le=4),
        status_filter: Optional[str] = Query(default=None, alias="status"),
    ):
        user = await _require_read(db, request)
        tenant_id = _tenant_id(user, request)
        query: dict[str, Any] = {"mantenedora_id": tenant_id}
        if academic_year is not None:
            query["academic_year"] = academic_year
        if component_id:
            query["component_id"] = component_id
        if bimestre is not None:
            query["bimestre"] = bimestre
        if status_filter:
            query["status"] = status_filter
        items = await db.teaching_plans.find(query, {"_id": 0}).sort(
            [("academic_year", -1), ("component_id", 1), ("bimestre", 1), ("grade_key", 1)]
        ).to_list(length=2000)
        return {"items": items, "total": len(items)}

    @router.post("/teaching-plans", status_code=201)
    async def create_teaching_plan(payload: TeachingPlanCreate, request: Request):
        user = await _require_manage(db, request)
        tenant_id = _tenant_id(user, request)
        await _ensure_indexes(db)
        version = await db.curriculum_versions.find_one(
            {
                "id": payload.curriculum_version_id, "mantenedora_id": tenant_id,
                "academic_year": payload.academic_year,
            },
            {"_id": 0},
        )
        if not version:
            raise HTTPException(422, "Versão curricular inexistente ou fora do escopo.")
        await _validate_plan_items(db, payload.items, tenant_id)
        now = _now()
        doc = {
            "id": str(uuid.uuid4()), **payload.model_dump(),
            "grade_key": _grade_key(payload.grade_scope), "mantenedora_id": tenant_id,
            "status": "draft", "revision": 1, "published_at": None, "published_by": None,
            "created_by": user.get("id"), "created_at": now,
            "updated_by": user.get("id"), "updated_at": now,
        }
        try:
            await db.teaching_plans.insert_one(doc)
        except Exception as exc:
            if "duplicate key" in str(exc).lower():
                raise HTTPException(
                    409,
                    detail={
                        "code": "TEACHING_PLAN_SCOPE_EXISTS",
                        "message": "Já existe plano para esta versão/ano/componente/bimestre/faixa.",
                    },
                ) from exc
            raise
        return _public(doc)

    @router.get("/teaching-plans/{plan_id}")
    async def get_teaching_plan(plan_id: str, request: Request):
        user = await _require_read(db, request)
        tenant_id = _tenant_id(user, request)
        plan = await db.teaching_plans.find_one(
            {"id": plan_id, "mantenedora_id": tenant_id}, {"_id": 0}
        )
        if not plan:
            raise HTTPException(404, "Plano de Ensino não encontrado")
        return plan

    @router.put("/teaching-plans/{plan_id}")
    async def update_teaching_plan(plan_id: str, payload: TeachingPlanUpdate, request: Request):
        user = await _require_manage(db, request)
        tenant_id = _tenant_id(user, request)
        current = await db.teaching_plans.find_one(
            {"id": plan_id, "mantenedora_id": tenant_id}, {"_id": 0}
        )
        if not current:
            raise HTTPException(404, "Plano de Ensino não encontrado")
        if current.get("status") != "draft":
            raise HTTPException(409, detail={"code": "TEACHING_PLAN_IMMUTABLE"})
        update = payload.model_dump(exclude_unset=True)
        if "items" in update and update["items"] is not None:
            items = [TeachingPlanItem.model_validate(item) for item in update["items"]]
            await _validate_plan_items(db, items, tenant_id)
            update["items"] = [item.model_dump() for item in items]
        if not update:
            raise HTTPException(400, "Nada para atualizar")
        update.update({
            "revision": int(current.get("revision") or 1) + 1,
            "updated_by": user.get("id"), "updated_at": _now(),
        })
        await db.teaching_plans.update_one({"id": plan_id}, {"$set": update})
        return _public(await db.teaching_plans.find_one({"id": plan_id}, {"_id": 0}))

    @router.post("/teaching-plans/{plan_id}/publish")
    async def publish_teaching_plan(plan_id: str, request: Request):
        user = await _require_manage(db, request)
        tenant_id = _tenant_id(user, request)
        plan = await db.teaching_plans.find_one(
            {"id": plan_id, "mantenedora_id": tenant_id}, {"_id": 0}
        )
        if not plan:
            raise HTTPException(404, "Plano de Ensino não encontrado")
        if plan.get("status") == "published":
            return plan
        if plan.get("status") != "draft":
            raise HTTPException(409, "Somente plano em rascunho pode ser publicado.")
        if not plan.get("items"):
            raise HTTPException(422, "Plano vazio não pode ser publicado.")
        version = await db.curriculum_versions.find_one(
            {
                "id": plan.get("curriculum_version_id"), "mantenedora_id": tenant_id,
                "status": "published",
            },
            {"_id": 0},
        )
        if not version:
            raise HTTPException(
                409,
                detail={
                    "code": "CURRICULUM_VERSION_NOT_PUBLISHED",
                    "message": "Publique a versão curricular antes do Plano de Ensino.",
                },
            )
        items = [TeachingPlanItem.model_validate(item) for item in plan.get("items") or []]
        await _validate_plan_items(db, items, tenant_id)
        now = _now()
        await db.teaching_plans.update_many(
            {
                "mantenedora_id": tenant_id,
                "curriculum_version_id": plan["curriculum_version_id"],
                "academic_year": plan["academic_year"], "component_id": plan["component_id"],
                "bimestre": plan["bimestre"], "grade_key": plan["grade_key"],
                "status": "published", "id": {"$ne": plan_id},
            },
            {"$set": {"status": "superseded", "updated_at": now}},
        )
        await db.teaching_plans.update_one(
            {"id": plan_id},
            {"$set": {
                "status": "published", "published_at": now, "published_by": user.get("id"),
                "updated_by": user.get("id"), "updated_at": now,
            }},
        )
        return _public(await db.teaching_plans.find_one({"id": plan_id}, {"_id": 0}))

    return router


def install_curriculum_core_setup(curriculum_v2_mod: Any) -> None:
    """Anexa F2/F3 ao router v2 sem alterar ``server.py``."""
    if getattr(curriculum_v2_mod, "_canonical_curriculum_core_installed", False):
        return
    original_setup = curriculum_v2_mod.setup_router

    @wraps(original_setup)
    def setup_router(db):
        configured = original_setup(db)
        if not getattr(configured, "_canonical_curriculum_core_routes", False):
            configured.include_router(build_curriculum_core_router(db))
            configured._canonical_curriculum_core_routes = True
        return configured

    curriculum_v2_mod.setup_router = setup_router
    curriculum_v2_mod._canonical_curriculum_core_installed = True
