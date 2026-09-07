"""F4 — cutover do formulário de Conteúdos para ``content_entries``.

A UI histórica continua chamando ``/learning-objects``. Esta camada adapta esse
contrato para o writer canônico sem reativar novas escritas em
``learning_objects``. O legado permanece somente como histórico/fallback.

Além do conteúdo textual, a F4 persiste a relação estruturada com o Plano de
Ensino Bimestral quando houver um plano publicado para o contexto. A ausência
de plano não bloqueia o professor nesta fase: ela é registrada explicitamente
no snapshot de vínculo para permitir rollout incremental e auditoria posterior.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from fastapi import HTTPException, Request

from routers.content_entries import (
    ContentEntryCreate,
    _resolve_bimestre_for_date,
    save_content_canonical,
)
from services.content_assignment_scope import (
    ContentAssignmentScopeError,
    authorize_content_record,
    filter_visible_content_entries,
)
from services.content_audit import build_content_audit_extra
from services.diary_assignment_access import DiaryAction
from services.professor_content_projection import (
    ProfessorContentProjectionError,
    _active_entitled_course_ids,
    list_professor_content_projection,
)
from tenant_scope import assert_same_tenant, get_mantenedora_scope
from utils.academic_year import create_academic_year_validators


FORM_WRITER_ORIGIN = "learning_objects_form_f4"


def _dump(value: Any, *, exclude_none: bool = False) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=exclude_none)
    if hasattr(value, "dict"):
        return value.dict(exclude_none=exclude_none)
    return dict(vars(value))


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _public_canonical(record: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(record)
    item.pop("_id", None)
    component_id = item.get("component_id") or item.get("course_id")
    item["component_id"] = component_id
    item["course_id"] = component_id
    item["recorded_by"] = item.get("teacher_id")
    item["source"] = "content_entries"
    item["legacy"] = False
    item["read_only"] = False
    return item


def _semantic_key(record: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        _norm(record.get("class_id")),
        _norm(record.get("component_id") or record.get("course_id")),
        _norm(record.get("date"))[:10],
        _norm(record.get("aula_numero")),
    )


def _dedupe_elements(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for raw in items:
        item = dict(raw or {})
        key = (_norm(item.get("id")), _norm(item.get("label")))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


async def _curriculum_binding(
    db,
    current_user: Mapping[str, Any],
    request: Request,
    *,
    class_id: str,
    component_id: str,
    date: str,
    academic_year: int,
    adaptation_ids: list[str],
) -> dict[str, Any]:
    """Gera snapshot aditivo do Plano de Ensino aplicável à escrita docente."""
    tenant_id = get_mantenedora_scope(current_user, request)
    class_doc = await db.classes.find_one({"id": class_id}, {"_id": 0})
    if not class_doc:
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    assert_same_tenant(class_doc, current_user, request)

    bimestre = await _resolve_bimestre_for_date(db, academic_year, date)
    grade = _norm(
        class_doc.get("grade_level") or class_doc.get("series") or class_doc.get("serie")
    )
    if not bimestre:
        return {
            "status": "bimester_unresolved",
            "academic_year": academic_year,
            "bimestre": None,
            "grade": grade or None,
            "component_id": component_id,
            "teaching_plan_id": None,
            "curriculum_version_id": None,
            "teaching_plan_item_ids": [],
            "selected_adaptation_ids": list(dict.fromkeys(adaptation_ids)),
            "knowledge_objects": [],
            "pedagogical_practices": [],
            "source_refs": [],
        }

    query: dict[str, Any] = {
        "mantenedora_id": tenant_id,
        "academic_year": academic_year,
        "component_id": component_id,
        "bimestre": bimestre,
        "status": "published",
    }
    if grade:
        query["grade_scope"] = grade
    plan = await db.teaching_plans.find_one(query, {"_id": 0}, sort=[("revision", -1)])
    selected = list(dict.fromkeys(_norm(item) for item in adaptation_ids if _norm(item)))
    if not plan:
        return {
            "status": "missing_plan",
            "academic_year": academic_year,
            "bimestre": bimestre,
            "grade": grade or None,
            "component_id": component_id,
            "teaching_plan_id": None,
            "curriculum_version_id": None,
            "teaching_plan_item_ids": [],
            "selected_adaptation_ids": selected,
            "knowledge_objects": [],
            "pedagogical_practices": [],
            "source_refs": [],
        }

    plan_items = list(plan.get("items") or [])
    matched = [item for item in plan_items if _norm(item.get("adaptation_id")) in selected]
    matched_adaptations = {_norm(item.get("adaptation_id")) for item in matched}
    unmatched = [item for item in selected if item not in matched_adaptations]
    if not selected:
        status = "published_plan_unlinked"
    elif unmatched:
        status = "partial"
    else:
        status = "bound"

    knowledge = _dedupe_elements(
        [element for item in matched for element in (item.get("knowledge_objects") or [])]
    )
    practices = _dedupe_elements(
        [element for item in matched for element in (item.get("pedagogical_practices") or [])]
    )
    source_refs = list(dict.fromkeys(
        _norm(ref)
        for item in matched
        for ref in (item.get("source_refs") or [])
        if _norm(ref)
    ))
    return {
        "status": status,
        "academic_year": academic_year,
        "bimestre": bimestre,
        "grade": grade or None,
        "component_id": component_id,
        "teaching_plan_id": plan.get("id"),
        "teaching_plan_revision": plan.get("revision"),
        "curriculum_version_id": plan.get("curriculum_version_id"),
        "teaching_plan_item_ids": [item.get("id") for item in matched if item.get("id")],
        "selected_adaptation_ids": selected,
        "unmatched_adaptation_ids": unmatched,
        "knowledge_objects": knowledge,
        "pedagogical_practices": practices,
        "source_refs": source_refs,
        "snapshotted_at": datetime.now(timezone.utc).isoformat(),
    }


async def _persist_form_metadata(
    db,
    audit_service,
    current_user: Mapping[str, Any],
    request: Request,
    *,
    record: Mapping[str, Any],
    resources: Optional[str],
    skill_codigos: list[str],
    adaptation_ids: list[str],
) -> dict[str, Any]:
    component_id = _norm(record.get("component_id") or record.get("course_id"))
    binding = await _curriculum_binding(
        db,
        current_user,
        request,
        class_id=_norm(record.get("class_id")),
        component_id=component_id,
        date=_norm(record.get("date"))[:10],
        academic_year=int(record.get("academic_year") or datetime.now().year),
        adaptation_ids=adaptation_ids,
    )
    curriculum_links = {
        "adaptation_ids": list(dict.fromkeys(adaptation_ids)),
        "teaching_plan_item_ids": list(binding.get("teaching_plan_item_ids") or []),
        "knowledge_objects": list(binding.get("knowledge_objects") or []),
        "pedagogical_practices": list(binding.get("pedagogical_practices") or []),
        "source_refs": list(binding.get("source_refs") or []),
    }
    metadata = {
        "resources": resources,
        "skill_codigos": list(dict.fromkeys(skill_codigos)),
        "adaptation_ids": list(dict.fromkeys(adaptation_ids)),
        "curriculum_binding": binding,
        "curriculum_links": curriculum_links,
        "writer_origin": FORM_WRITER_ORIGIN,
    }
    result = await db.content_entries.update_one({"id": record["id"]}, {"$set": metadata})
    if getattr(result, "matched_count", 1) == 0:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CANONICAL_CONTENT_METADATA_LOST",
                "message": "O conteúdo canônico desapareceu durante a vinculação curricular.",
            },
        )
    updated = await db.content_entries.find_one({"id": record["id"]}, {"_id": 0})
    if audit_service is not None:
        await audit_service.log(
            action="update",
            collection="content_entries",
            user=current_user,
            request=request,
            document_id=record["id"],
            description="Vinculou conteúdo docente ao contexto curricular canônico (F4)",
            old_value=None,
            new_value={
                "writer_origin": FORM_WRITER_ORIGIN,
                "curriculum_binding": binding,
                "adaptation_ids": metadata["adaptation_ids"],
            },
            school_id=record.get("school_id"),
        )
    return _public_canonical(updated or {**dict(record), **metadata})


async def create_from_learning_object_form(
    db,
    audit_service,
    current_user: Mapping[str, Any],
    request: Request,
    data: Any,
) -> dict[str, Any]:
    raw = _dump(data)
    component_id = _norm(raw.get("course_id") or raw.get("component_id"))
    if not component_id:
        raise HTTPException(status_code=422, detail="Componente curricular é obrigatório")
    payload = ContentEntryCreate(
        class_id=raw["class_id"],
        course_id=component_id,
        component_id=component_id,
        date=raw["date"],
        academic_year=raw.get("academic_year"),
        number_of_classes=raw.get("number_of_classes") or 1,
        content=raw.get("content") or "",
        methodology=raw.get("methodology"),
        observations=raw.get("observations"),
        assignment_id=raw.get("assignment_id"),
    )
    created = await save_content_canonical(db, current_user, request, payload, audit_service)
    return await _persist_form_metadata(
        db,
        audit_service,
        current_user,
        request,
        record=created,
        resources=raw.get("resources"),
        skill_codigos=list(raw.get("skill_codigos") or []),
        adaptation_ids=list(raw.get("adaptation_ids") or []),
    )


async def update_from_learning_object_form(
    db,
    audit_service,
    current_user: Mapping[str, Any],
    request: Request,
    entry_id: str,
    data: Any,
) -> dict[str, Any]:
    existing = await db.content_entries.find_one({"id": entry_id, "deleted": False}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Conteúdo canônico não encontrado")
    raw = _dump(data, exclude_none=True)
    current_component = _norm(existing.get("component_id") or existing.get("course_id"))
    requested_component = _norm(raw.get("course_id") or raw.get("component_id"))
    if requested_component and requested_component != current_component:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CANONICAL_COMPONENT_MOVE_REQUIRES_COPY",
                "message": "Para mudar o componente, copie o lançamento para o componente correto e exclua o anterior.",
            },
        )

    payload = ContentEntryCreate(
        class_id=existing["class_id"],
        course_id=current_component,
        component_id=current_component,
        date=existing["date"],
        aula_numero=existing.get("aula_numero"),
        teacher_id=existing.get("teacher_id"),
        assignment_id=existing.get("assignment_id"),
        academic_year=existing.get("academic_year"),
        number_of_classes=raw.get("number_of_classes", existing.get("number_of_classes") or 1),
        content=raw.get("content", existing.get("content") or ""),
        methodology=raw.get("methodology", existing.get("methodology")),
        observations=raw.get("observations", existing.get("observations")),
        expected_version=existing.get("version") or 1,
    )
    updated = await save_content_canonical(db, current_user, request, payload, audit_service)
    return await _persist_form_metadata(
        db,
        audit_service,
        current_user,
        request,
        record=updated,
        resources=raw.get("resources", existing.get("resources")),
        skill_codigos=list(raw.get("skill_codigos", existing.get("skill_codigos") or [])),
        adaptation_ids=list(raw.get("adaptation_ids", existing.get("adaptation_ids") or [])),
    )


async def delete_from_learning_object_form(
    db,
    audit_service,
    current_user: Mapping[str, Any],
    request: Request,
    entry_id: str,
) -> dict[str, Any]:
    existing = await db.content_entries.find_one({"id": entry_id, "deleted": False}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Conteúdo canônico não encontrado")
    assert_same_tenant(existing, current_user, request)
    if existing.get("assignment_id"):
        try:
            await authorize_content_record(
                db,
                current_user,
                existing,
                action=DiaryAction.CONTENT,
                allow_management_override=True,
                active_mantenedora_id=get_mantenedora_scope(current_user, request),
            )
        except ContentAssignmentScopeError as exc:
            raise HTTPException(
                status_code=403,
                detail={"code": exc.code, "message": exc.message},
            ) from exc
    elif current_user.get("role") == "professor" and existing.get("teacher_id") != current_user.get("id"):
        raise HTTPException(status_code=403, detail="Este conteúdo pertence a outro professor.")

    class_doc = await db.classes.find_one(
        {"id": existing.get("class_id")}, {"_id": 0, "school_id": 1, "academic_year": 1}
    )
    academic_year = int(existing.get("academic_year") or (class_doc or {}).get("academic_year") or datetime.now().year)
    role = current_user.get("role", "")
    validators = create_academic_year_validators(db)
    if role != "admin" and class_doc:
        await validators["verify_academic_year_open_or_raise"](class_doc.get("school_id"), academic_year)
    if role not in ["admin", "admin_teste", "super_admin", "gerente", "secretario"]:
        bimestre = await _resolve_bimestre_for_date(db, academic_year, existing.get("date"))
        if bimestre:
            await validators["verify_bimestre_edit_deadline_or_raise"](academic_year, bimestre, role)

    now = datetime.now(timezone.utc)
    new_version = int(existing.get("version") or 1) + 1
    await db.content_entries.update_one(
        {"id": entry_id, "deleted": False},
        {"$set": {
            "deleted": True,
            "deleted_at": now,
            "deleted_by": current_user.get("id"),
            "updated_at": now,
            "updated_by": current_user.get("id"),
            "version": new_version,
        }},
    )
    if audit_service is not None:
        extra = build_content_audit_extra(
            entry=existing,
            change_kind="content_deleted",
            expected_version=None,
            final_version=new_version,
            previous_content=existing.get("content"),
            new_content=None,
            change_note="Exclusão pelo formulário docente compatível F4",
            class_info=class_doc,
        )
        await audit_service.log(
            action="delete",
            collection="content_entries",
            user=current_user,
            request=request,
            document_id=entry_id,
            description="Excluiu conteúdo docente canônico pelo formulário compatível (F4)",
            old_value={"deleted": False, "version": existing.get("version") or 1},
            new_value={"deleted": True, "version": new_version},
            school_id=existing.get("school_id") or (class_doc or {}).get("school_id"),
            extra_data=extra,
        )
    return {"message": "Registro excluído com sucesso", "id": entry_id, "source": "content_entries"}


async def list_learning_objects_cutover(
    db,
    current_user: Mapping[str, Any],
    request: Request,
    *,
    legacy_items: list[dict[str, Any]],
    class_id: Optional[str],
    course_id: Optional[str],
    date: Optional[str],
    academic_year: Optional[int],
    month: Optional[int],
) -> list[dict[str, Any]]:
    """Projeta legado + canônico mantendo a forma plana esperada pela UI."""
    year = int(academic_year or datetime.now().year)
    tenant_id = get_mantenedora_scope(current_user, request)

    if current_user.get("role") == "professor" and class_id:
        try:
            base_items = await list_professor_content_projection(
                db,
                current_user,
                class_id=class_id,
                academic_year=year,
                month=month,
                date=date,
                active_mantenedora_id=tenant_id,
            )
        except ProfessorContentProjectionError as exc:
            raise HTTPException(
                status_code=403 if exc.code != "CLASS_NOT_FOUND_IN_TENANT" else 404,
                detail={"code": exc.code, "message": exc.message},
            ) from exc
        entitled = await _active_entitled_course_ids(
            db,
            current_user,
            class_id=class_id,
            academic_year=year,
            mantenedora_id=tenant_id,
        )
        if course_id and course_id not in entitled:
            return []
        if course_id:
            base_items = [
                item for item in base_items
                if _norm(item.get("course_id") or item.get("component_id")) == course_id
            ]
    else:
        base_items = [dict(item) for item in legacy_items]
        entitled = set()

    q: dict[str, Any] = {"deleted": False}
    if tenant_id:
        q["mantenedora_id"] = tenant_id
    if class_id:
        q["class_id"] = class_id
    if course_id:
        q["component_id"] = course_id
    if date:
        q["date"] = _norm(date)[:10]
    elif month:
        start = f"{year}-{int(month):02d}-01"
        end = f"{year + 1}-01-01" if int(month) == 12 else f"{year}-{int(month) + 1:02d}-01"
        q["date"] = {"$gte": start, "$lt": end}
    q["academic_year"] = year

    candidates = await db.content_entries.find(q, {"_id": 0}).to_list(5000)
    if current_user.get("role") == "professor":
        candidates = [
            item for item in candidates
            if _norm(item.get("component_id") or item.get("course_id")) in entitled
            and (item.get("assignment_id") or item.get("teacher_id") == current_user.get("id"))
        ]
    canonical_visible = await filter_visible_content_entries(
        db,
        current_user,
        candidates,
        active_mantenedora_id=tenant_id,
    )
    canonical = [_public_canonical(item) for item in canonical_visible]

    canonical_keys = {_semantic_key(item) for item in canonical}
    merged = [item for item in base_items if _semantic_key(item) not in canonical_keys]
    merged.extend(canonical)

    class_names: dict[str, str] = {}
    course_names: dict[str, str] = {}
    class_ids = sorted({_norm(item.get("class_id")) for item in merged if _norm(item.get("class_id"))})
    course_ids = sorted({
        _norm(item.get("course_id") or item.get("component_id"))
        for item in merged if _norm(item.get("course_id") or item.get("component_id"))
    })
    if class_ids:
        rows = await db.classes.find({"id": {"$in": class_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(len(class_ids))
        class_names = {_norm(row.get("id")): str(row.get("name") or "") for row in rows}
    if course_ids:
        rows = await db.courses.find({"id": {"$in": course_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(len(course_ids))
        course_names = {_norm(row.get("id")): str(row.get("name") or "") for row in rows}
    for item in merged:
        cid = _norm(item.get("class_id"))
        coid = _norm(item.get("course_id") or item.get("component_id"))
        item["class_name"] = item.get("class_name") or class_names.get(cid, "")
        item["course_name"] = item.get("course_name") or course_names.get(coid, "")

    merged.sort(key=lambda item: (_norm(item.get("date")), -int(item.get("aula_numero") or 0)), reverse=True)
    return merged


async def get_canonical_learning_object(
    db,
    current_user: Mapping[str, Any],
    request: Request,
    entry_id: str,
) -> Optional[dict[str, Any]]:
    record = await db.content_entries.find_one({"id": entry_id, "deleted": False}, {"_id": 0})
    if not record:
        return None
    assert_same_tenant(record, current_user, request)
    if record.get("assignment_id"):
        try:
            await authorize_content_record(
                db,
                current_user,
                record,
                action=DiaryAction.VIEW,
                allow_management_override=True,
                active_mantenedora_id=get_mantenedora_scope(current_user, request),
            )
        except ContentAssignmentScopeError as exc:
            raise HTTPException(
                status_code=403,
                detail={"code": exc.code, "message": exc.message},
            ) from exc
    elif current_user.get("role") == "professor" and record.get("teacher_id") != current_user.get("id"):
        raise HTTPException(status_code=403, detail="Este conteúdo pertence a outro professor.")
    return _public_canonical(record)
