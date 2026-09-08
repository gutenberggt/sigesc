"""Versões Curriculares por escopo operacional.

Evolui o núcleo existente sem remover o contrato anual legado:
- cada nova versão é escopada por ano letivo + componente operacional + série + bimestre;
- o PDF estruturado é preservado como evidência documental e SHA-256;
- publicação supersede somente o MESMO escopo;
- Plano de Ensino é derivado apenas das habilidades DCM obrigatórias resolvidas;
- habilidades complementares/transversais permanecem rastreadas, nunca promovidas a
  obrigatórias por inferência.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
import unicodedata
import uuid
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from auth_middleware import AuthMiddleware
from ftp_upload import delete_from_ftp, upload_to_ftp
from routers.curriculum_core import (
    TeachingPlanItem,
    _ensure_indexes,
    _grade_key,
    _public,
    _tenant_id,
    _validate_plan_items,
    _validate_source_ids,
)
from services.curriculum_structured_pdf import (
    StructuredCurriculumPdfError,
    extract_structured_curriculum_pdf,
)
from tenant_scope import is_super_admin


SCOPED_KIND = "component_grade_bimester"
MANAGE_ROLES = ["super_admin", "coordenador"]


class ScopedVersionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=250)
    source_ids: Optional[list[str]] = None
    notes: Optional[str] = Field(default=None, max_length=5000)


class _ScopedCollectionProxy:
    """Marcador simples para testes/contrato; não envolve Mongo."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _norm(value))
    return " ".join("".join(ch for ch in text if not unicodedata.combining(ch)).lower().split())


def _component_code_from_skill(code: str) -> str:
    match = re.match(r"^EF\d{2}([A-Z]{2})\d{2}$", _norm(code).upper())
    return match.group(1) if match else ""


def _scope_key(academic_year: int, component_id: str, bimestre: int, grade_scope: list[str]) -> str:
    return f"{int(academic_year)}|{_norm(component_id)}|{int(bimestre)}|{_grade_key(grade_scope)}"


async def _require_manage(db, request: Request) -> dict:
    return await AuthMiddleware.require_permission(
        db, "nav-curriculum-button", MANAGE_ROLES
    )(request)


async def _require_read(db, request: Request) -> dict:
    user = await AuthMiddleware.get_current_user(request)
    if is_super_admin(user):
        return user
    role = user.get("role")
    override = await db.permission_overrides.find_one(
        {"item_key": "nav-curriculum-button", "role": role},
        {"_id": 0, "visible": 1},
    )
    if override is not None and not override.get("visible"):
        raise HTTPException(403, "Acesso ao currículo revogado pela Matriz de Permissões.")
    return user


async def _course_for_tenant(db, component_id: str, tenant_id: str) -> dict[str, Any]:
    course = await db.courses.find_one(
        {"id": component_id, "mantenedora_id": tenant_id},
        {"_id": 0, "id": 1, "name": 1, "nivel_ensino": 1, "mantenedora_id": 1},
    )
    if not course:
        raise HTTPException(
            422,
            detail={
                "code": "CURRICULUM_VERSION_COMPONENT_INVALID",
                "message": "Componente curricular inexistente ou fora da mantenedora ativa.",
            },
        )
    return course


async def _resolve_mandatory_skills(
    db,
    *,
    tenant_id: str,
    grade: int,
    bimestre: int,
    mandatory_skills: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    codes = list(dict.fromkeys(_norm(item.get("code")).upper() for item in mandatory_skills if _norm(item.get("code"))))
    if not codes:
        return []
    bncc_docs = await db.bncc_skills.find(
        {"codigo_bncc": {"$in": codes}, "ativo": True},
        {"_id": 0, "id": 1, "codigo_bncc": 1, "descricao_bncc": 1},
    ).to_list(length=len(codes))
    bncc_by_code = {doc["codigo_bncc"].upper(): doc for doc in bncc_docs}

    component_codes = {_component_code_from_skill(code) for code in codes}
    component_codes.discard("")
    curriculum_components = await db.curriculum_components.find(
        {"codigo": {"$in": sorted(component_codes)}, "ativo": True},
        {"_id": 0, "id": 1, "codigo": 1, "fonte": 1},
    ).to_list(length=100)
    curriculum_component_ids = [doc["id"] for doc in curriculum_components]

    bncc_ids = [doc["id"] for doc in bncc_docs]
    adaptations = []
    if bncc_ids and curriculum_component_ids:
        adaptations = await db.curriculum_adaptations.find(
            {
                "ativo": True,
                "component_id": {"$in": curriculum_component_ids},
                "bncc_skill_id": {"$in": bncc_ids},
                "ano": {"$in": [grade, 0, None]},
                "$and": [
                    {"$or": [
                        {"bimestre": bimestre},
                        {"bimestre": None},
                        {"bimestre": {"$exists": False}},
                    ]},
                    {"$or": [
                        {"mantenedora_id": tenant_id},
                        {"mantenedora_id": None},
                    ]},
                ],
            },
            {"_id": 0},
        ).to_list(length=1000)

    by_bncc_id: dict[str, list[dict[str, Any]]] = {}
    for adaptation in adaptations:
        by_bncc_id.setdefault(_norm(adaptation.get("bncc_skill_id")), []).append(adaptation)

    result: list[dict[str, Any]] = []
    for item in mandatory_skills:
        code = _norm(item.get("code")).upper()
        bncc = bncc_by_code.get(code)
        candidates = by_bncc_id.get(_norm((bncc or {}).get("id")), [])
        candidates.sort(
            key=lambda a: (
                0 if a.get("mantenedora_id") == tenant_id else 1,
                0 if a.get("bimestre") == bimestre else 1,
                0 if int(a.get("ano") or 0) == grade else 1,
                _norm(a.get("fonte")),
                _norm(a.get("id")),
            )
        )
        chosen = candidates[0] if candidates else None
        result.append({
            "code": code,
            "resolved": bool(chosen),
            "adaptation_id": (chosen or {}).get("id"),
            "catalog_description": (chosen or {}).get("descricao_local") or (bncc or {}).get("descricao_bncc"),
            "document_focus": item.get("focus"),
            "knowledge_objects": list(item.get("knowledge_objects") or []),
            "evidence": item.get("evidence"),
            "origin": item.get("origin"),
            "source_page": item.get("source_page"),
        })
    return result


async def _next_revision(db, tenant_id: str, scope_key: str) -> int:
    latest = await db.curriculum_versions.find_one(
        {"mantenedora_id": tenant_id, "scope_key": scope_key},
        {"_id": 0, "revision": 1},
        sort=[("revision", -1)],
    )
    return int((latest or {}).get("revision") or 0) + 1


def _version_public(doc: dict[str, Any]) -> dict[str, Any]:
    result = _public(doc) or {}
    payload = result.get("structured_payload") or {}
    resolution = result.get("skill_resolution") or []
    result["summary"] = {
        "mandatory_skills": len(payload.get("mandatory_skills") or []),
        "mandatory_resolved": sum(1 for item in resolution if item.get("resolved")),
        "mandatory_unresolved": sum(1 for item in resolution if not item.get("resolved")),
        "complementary_skills": len(payload.get("complementary_skills") or []),
        "transversal_skills": len(payload.get("transversal_skills") or []),
        "knowledge_object_groups": len(payload.get("knowledge_object_groups") or []),
    }
    return result


def build_scoped_curriculum_router(db) -> APIRouter:
    router = APIRouter(prefix="/scoped-versions", tags=["Currículo - Versões por Escopo"])

    @router.get("")
    async def list_scoped_versions(
        request: Request,
        academic_year: Optional[int] = Query(default=None, ge=2000, le=2200),
        component_id: Optional[str] = None,
        bimestre: Optional[int] = Query(default=None, ge=1, le=4),
        status_filter: Optional[str] = Query(default=None, alias="status"),
    ):
        user = await _require_read(db, request)
        tenant_id = _tenant_id(user, request)
        query: dict[str, Any] = {"mantenedora_id": tenant_id, "scope_kind": SCOPED_KIND}
        if academic_year is not None:
            query["academic_year"] = academic_year
        if component_id:
            query["component_id"] = component_id
        if bimestre is not None:
            query["bimestre"] = bimestre
        if status_filter:
            query["status"] = status_filter
        docs = await db.curriculum_versions.find(query, {"_id": 0}).sort(
            [("academic_year", -1), ("component_name", 1), ("grade_key", 1), ("bimestre", 1), ("revision", -1)]
        ).to_list(length=2000)
        return {"items": [_version_public(doc) for doc in docs], "total": len(docs)}

    @router.get("/{version_id}")
    async def get_scoped_version(version_id: str, request: Request):
        user = await _require_read(db, request)
        tenant_id = _tenant_id(user, request)
        doc = await db.curriculum_versions.find_one(
            {"id": version_id, "mantenedora_id": tenant_id, "scope_kind": SCOPED_KIND},
            {"_id": 0},
        )
        if not doc:
            raise HTTPException(404, "Versão curricular por escopo não encontrada.")
        return _version_public(doc)

    @router.post("/upload", status_code=201)
    async def upload_scoped_version(
        request: Request,
        file: UploadFile = File(...),
        academic_year: int = Form(...),
        component_id: str = Form(...),
        bimestre: int = Form(...),
        grade: int = Form(...),
        source_ids: str = Form(..., description="IDs de fontes oficiais separados por vírgula"),
        name: Optional[str] = Form(default=None),
        notes: Optional[str] = Form(default=None),
    ):
        user = await _require_manage(db, request)
        tenant_id = _tenant_id(user, request)
        await _ensure_indexes(db)
        if academic_year < 2000 or academic_year > 2200 or bimestre not in (1, 2, 3, 4) or grade < 1 or grade > 13:
            raise HTTPException(422, "Ano letivo, série ou bimestre inválido.")
        course = await _course_for_tenant(db, component_id, tenant_id)
        source_id_list = [item.strip() for item in source_ids.split(",") if item.strip()]
        source_id_list = await _validate_source_ids(db, source_id_list, tenant_id)

        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "A Versão Curricular deve ser enviada em PDF.")
        content = await file.read()
        if len(content) > 30 * 1024 * 1024:
            raise HTTPException(413, "PDF maior que 30 MB.")
        sha256 = hashlib.sha256(content).hexdigest()
        try:
            structured = extract_structured_curriculum_pdf(content)
        except StructuredCurriculumPdfError as exc:
            raise HTTPException(422, detail={"code": exc.code, "message": exc.message}) from exc

        if structured["grade"] != grade or structured["bimestre"] != bimestre:
            raise HTTPException(
                422,
                detail={
                    "code": "CURRICULUM_VERSION_SCOPE_MISMATCH",
                    "message": "Ano/série ou bimestre informado não corresponde ao documento.",
                    "document_grade": structured["grade"],
                    "document_bimestre": structured["bimestre"],
                },
            )
        if _fold(structured.get("component_name")) != _fold(course.get("name")):
            raise HTTPException(
                422,
                detail={
                    "code": "CURRICULUM_VERSION_COMPONENT_MISMATCH",
                    "message": "O componente selecionado não corresponde ao componente identificado no PDF.",
                    "document_component": structured.get("component_name"),
                    "selected_component": course.get("name"),
                },
            )

        # Evidência documental deve sobreviver a deploys: sem FTP persistente, fail-closed.
        uploaded, document_url, uploaded_filename = upload_to_ftp(content, file.filename, "document")
        if not uploaded:
            raise HTTPException(
                503,
                detail={
                    "code": "CURRICULUM_VERSION_DOCUMENT_STORAGE_FAILED",
                    "message": "Não foi possível preservar o PDF no armazenamento documental persistente.",
                },
            )

        scope_key = _scope_key(academic_year, component_id, bimestre, [str(grade)])
        revision = await _next_revision(db, tenant_id, scope_key)
        resolution = await _resolve_mandatory_skills(
            db,
            tenant_id=tenant_id,
            grade=grade,
            bimestre=bimestre,
            mandatory_skills=structured["mandatory_skills"],
        )
        now = _now()
        doc = {
            "id": str(uuid.uuid4()),
            "name": name or f"{course.get('name')} — {grade}º ano — {bimestre}º bimestre — {academic_year}",
            "academic_year": academic_year,
            "source_ids": source_id_list,
            "valid_from": None,
            "notes": notes,
            "mantenedora_id": tenant_id,
            "revision": revision,
            "status": "draft",
            "published_at": None,
            "published_by": None,
            "superseded_at": None,
            "scope_kind": SCOPED_KIND,
            "scope_key": scope_key,
            "component_id": component_id,
            "component_name": course.get("name"),
            "education_stage": structured.get("education_stage"),
            "grade_scope": [str(grade)],
            "grade_key": _grade_key([str(grade)]),
            "bimestre": bimestre,
            "document_filename": file.filename,
            "document_storage_filename": uploaded_filename,
            "document_url": document_url,
            "document_sha256": sha256,
            "document_contract": structured.get("contract"),
            "structured_payload": structured,
            "skill_resolution": resolution,
            "created_by": user.get("id"),
            "created_at": now,
            "updated_by": user.get("id"),
            "updated_at": now,
        }
        try:
            await db.curriculum_versions.insert_one(doc)
        except Exception:
            delete_from_ftp(document_url)
            raise
        return _version_public(doc)

    @router.put("/{version_id}")
    async def update_scoped_version(version_id: str, payload: ScopedVersionUpdate, request: Request):
        user = await _require_manage(db, request)
        tenant_id = _tenant_id(user, request)
        current = await db.curriculum_versions.find_one(
            {"id": version_id, "mantenedora_id": tenant_id, "scope_kind": SCOPED_KIND}, {"_id": 0}
        )
        if not current:
            raise HTTPException(404, "Versão curricular por escopo não encontrada.")
        if current.get("status") != "draft":
            raise HTTPException(409, detail={"code": "CURRICULUM_VERSION_IMMUTABLE"})
        update = payload.model_dump(exclude_unset=True)
        if "source_ids" in update and update["source_ids"] is not None:
            update["source_ids"] = await _validate_source_ids(db, update["source_ids"], tenant_id)
        if not update:
            raise HTTPException(400, "Nada para atualizar.")
        update.update({"updated_by": user.get("id"), "updated_at": _now()})
        await db.curriculum_versions.update_one({"id": version_id}, {"$set": update})
        return _version_public(await db.curriculum_versions.find_one({"id": version_id}, {"_id": 0}))

    @router.post("/{version_id}/refresh-skill-resolution")
    async def refresh_skill_resolution(version_id: str, request: Request):
        user = await _require_manage(db, request)
        tenant_id = _tenant_id(user, request)
        current = await db.curriculum_versions.find_one(
            {"id": version_id, "mantenedora_id": tenant_id, "scope_kind": SCOPED_KIND}, {"_id": 0}
        )
        if not current:
            raise HTTPException(404, "Versão curricular por escopo não encontrada.")
        payload = current.get("structured_payload") or {}
        resolution = await _resolve_mandatory_skills(
            db,
            tenant_id=tenant_id,
            grade=int((current.get("grade_scope") or [0])[0]),
            bimestre=int(current.get("bimestre") or 0),
            mandatory_skills=list(payload.get("mandatory_skills") or []),
        )
        await db.curriculum_versions.update_one(
            {"id": version_id},
            {"$set": {"skill_resolution": resolution, "updated_by": user.get("id"), "updated_at": _now()}},
        )
        current["skill_resolution"] = resolution
        return _version_public(current)

    @router.post("/{version_id}/publish")
    async def publish_scoped_version(version_id: str, request: Request):
        user = await _require_manage(db, request)
        tenant_id = _tenant_id(user, request)
        current = await db.curriculum_versions.find_one(
            {"id": version_id, "mantenedora_id": tenant_id, "scope_kind": SCOPED_KIND}, {"_id": 0}
        )
        if not current:
            raise HTTPException(404, "Versão curricular por escopo não encontrada.")
        if current.get("status") == "published":
            return _version_public(current)
        if current.get("status") != "draft":
            raise HTTPException(409, "Somente versão em rascunho pode ser publicada.")
        await _validate_source_ids(db, current.get("source_ids") or [], tenant_id)
        unresolved = [item.get("code") for item in (current.get("skill_resolution") or []) if not item.get("resolved")]
        if unresolved:
            raise HTTPException(
                409,
                detail={
                    "code": "CURRICULUM_VERSION_SKILLS_UNRESOLVED",
                    "message": "Há habilidades obrigatórias ainda não resolvidas no catálogo curricular.",
                    "codes": unresolved,
                },
            )
        now = _now()
        previous = await db.curriculum_versions.find(
            {
                "mantenedora_id": tenant_id,
                "scope_kind": SCOPED_KIND,
                "scope_key": current["scope_key"],
                "status": "published",
                "id": {"$ne": version_id},
            },
            {"_id": 0, "id": 1},
        ).to_list(length=100)
        previous_ids = [doc["id"] for doc in previous]
        if previous_ids:
            await db.curriculum_versions.update_many(
                {"id": {"$in": previous_ids}},
                {"$set": {"status": "superseded", "superseded_at": now, "updated_at": now}},
            )
            await db.teaching_plans.update_many(
                {"mantenedora_id": tenant_id, "curriculum_version_id": {"$in": previous_ids}, "status": "published"},
                {"$set": {"status": "superseded", "updated_at": now}},
            )
        await db.curriculum_versions.update_one(
            {"id": version_id},
            {"$set": {
                "status": "published",
                "published_at": now,
                "published_by": user.get("id"),
                "updated_by": user.get("id"),
                "updated_at": now,
            }},
        )
        current.update({"status": "published", "published_at": now, "published_by": user.get("id")})
        return _version_public(current)

    @router.post("/{version_id}/create-teaching-plan", status_code=201)
    async def create_teaching_plan_from_version(version_id: str, request: Request):
        user = await _require_manage(db, request)
        tenant_id = _tenant_id(user, request)
        version = await db.curriculum_versions.find_one(
            {"id": version_id, "mantenedora_id": tenant_id, "scope_kind": SCOPED_KIND}, {"_id": 0}
        )
        if not version:
            raise HTTPException(404, "Versão curricular por escopo não encontrada.")
        if version.get("status") != "published":
            raise HTTPException(
                409,
                detail={"code": "CURRICULUM_VERSION_NOT_PUBLISHED", "message": "Publique a versão antes de criar o Plano de Ensino."},
            )
        unresolved = [item for item in (version.get("skill_resolution") or []) if not item.get("resolved")]
        if unresolved:
            raise HTTPException(409, detail={"code": "CURRICULUM_VERSION_SKILLS_UNRESOLVED"})

        existing = await db.teaching_plans.find_one(
            {
                "mantenedora_id": tenant_id,
                "curriculum_version_id": version_id,
                "academic_year": version["academic_year"],
                "component_id": version["component_id"],
                "bimestre": version["bimestre"],
                "grade_key": version["grade_key"],
            },
            {"_id": 0},
            sort=[("revision", -1)],
        )
        if existing:
            return _public(existing)

        payload = version.get("structured_payload") or {}
        resolution_by_code = {item.get("code"): item for item in (version.get("skill_resolution") or [])}
        items: list[TeachingPlanItem] = []
        for sequence, skill in enumerate(payload.get("mandatory_skills") or [], start=1):
            code = _norm(skill.get("code")).upper()
            resolved = resolution_by_code.get(code) or {}
            knowledge_objects = [
                {
                    "label": label,
                    "source_page": skill.get("source_page"),
                    "source_text": label,
                }
                for label in (skill.get("knowledge_objects") or [])
                if _norm(label)
            ]
            items.append(TeachingPlanItem(
                adaptation_id=resolved["adaptation_id"],
                skill_code_snapshot=code,
                skill_description_snapshot=resolved.get("catalog_description") or skill.get("focus"),
                learning_objective=skill.get("focus"),
                knowledge_objects=knowledge_objects,
                pedagogical_practices=[],
                source_refs=[
                    f"curriculum_version:{version_id}",
                    f"document_sha256:{version.get('document_sha256')}",
                    *([f"page:{skill.get('source_page')}"] if skill.get("source_page") else []),
                ],
                sequence=sequence,
            ))
        await _validate_plan_items(db, items, tenant_id)
        now = _now()
        doc = {
            "id": str(uuid.uuid4()),
            "curriculum_version_id": version_id,
            "academic_year": version["academic_year"],
            "component_id": version["component_id"],
            "bimestre": version["bimestre"],
            "grade_scope": list(version.get("grade_scope") or []),
            "grade_key": version["grade_key"],
            "education_stage": version.get("education_stage"),
            "title": f"Plano de Ensino Bimestral — {version.get('component_name')} — {version.get('grade_scope', [''])[0]}º ano — {version.get('bimestre')}º bimestre",
            "items": [item.model_dump() for item in items],
            "notes": "Gerado a partir da Versão Curricular Estruturada. Habilidades complementares e integração transversal permanecem registradas na versão e não foram promovidas automaticamente a itens obrigatórios do plano.",
            "mantenedora_id": tenant_id,
            "status": "draft",
            "revision": 1,
            "published_at": None,
            "published_by": None,
            "created_by": user.get("id"),
            "created_at": now,
            "updated_by": user.get("id"),
            "updated_at": now,
            "origin": "scoped_curriculum_version",
        }
        await db.teaching_plans.insert_one(doc)
        return _public(doc)

    return router
