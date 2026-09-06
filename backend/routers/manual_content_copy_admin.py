"""R2.0g.1 — Assistente administrativo de cópia manual mapeada de conteúdo.

Serviço EXCLUSIVO do ``super_admin``. O operador escolhe explicitamente a data
alvo de cada conteúdo; o backend nunca infere automaticamente uma correspondência.

Fluxo: opções/leitura -> mapeamento humano -> preflight determinístico -> apply
canônico. Nenhuma escrita em ``learning_objects``. O apply reutiliza
``save_content_canonical`` e falha fechado em autoria/vínculo ambíguos.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Query, Request
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from auth_middleware import AuthMiddleware
from routers.content_entries import ContentEntryCreate, save_content_canonical
from tenant_scope import resolve_operational_tenant_context


COPY_TYPE = "MANUAL_MAPPED_CONTENT_COPY"
BATCH_COLLECTION = "manual_content_copy_batches"


class ManualCopyMapping(BaseModel):
    source_id: str
    target_date: Optional[str] = None


class ManualCopyPlanRequest(BaseModel):
    request_id: str = Field(..., min_length=8, max_length=100)
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    source_class_id: str
    source_component_id: str
    target_class_id: str
    target_component_id: str
    mappings: list[ManualCopyMapping]


class ManualCopyApplyRequest(ManualCopyPlanRequest):
    manifest_hash: str = Field(..., pattern=r"^[0-9a-f]{64}$")


def _canonical_hash(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _month_bounds(month: str) -> tuple[str, str, int]:
    try:
        start = datetime.strptime(month + "-01", "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Mês inválido") from exc
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), start.year


async def _require_super_admin(request: Request) -> dict:
    user = await AuthMiddleware.require_roles(["super_admin"])(request)
    # Defesa adicional: não aceitar papel equivalente, override ou role composto.
    if user.get("role") != "super_admin":
        raise HTTPException(
            status_code=403,
            detail="Serviço exclusivo do Super Administrador",
        )
    return user


async def _class_in_tenant(db, tenant_id: str, class_id: str) -> dict:
    doc = await db.classes.find_one(
        {"id": class_id, "mantenedora_id": tenant_id},
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(
            status_code=404,
            detail="Turma não encontrada na mantenedora ativa",
        )
    return doc


async def _school_in_tenant(
    db,
    tenant_id: str,
    school_id: Optional[str],
) -> Optional[dict]:
    if not school_id:
        return None
    doc = await db.schools.find_one(
        {"id": school_id, "mantenedora_id": tenant_id},
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(
            status_code=404,
            detail="Escola não encontrada na mantenedora ativa",
        )
    return doc


def _component_match_query(component_id: str) -> dict:
    return {
        "$or": [
            {"component_id": component_id},
            {"course_id": component_id},
        ]
    }


async def _component_exists(db, tenant_id: str, component_id: str) -> dict:
    doc = await db.courses.find_one(
        {
            "id": component_id,
            "$or": [
                {"mantenedora_id": tenant_id},
                {"mantenedora_id": {"$exists": False}},
            ],
        },
        {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1},
    )
    if not doc:
        raise HTTPException(
            status_code=404,
            detail="Componente curricular não encontrado",
        )
    if doc.get("mantenedora_id") and str(doc.get("mantenedora_id")) != str(tenant_id):
        raise HTTPException(
            status_code=403,
            detail="Componente pertence a outra mantenedora",
        )
    return doc


async def _options(db, *, tenant_id: str) -> dict:
    """Opções do assistente sempre limitadas à mantenedora operacional ativa."""
    schools = await db.schools.find(
        {"mantenedora_id": tenant_id},
        {"_id": 0, "id": 1, "name": 1, "nome": 1},
    ).to_list(2000)
    classes = await db.classes.find(
        {"mantenedora_id": tenant_id},
        {
            "_id": 0,
            "id": 1,
            "name": 1,
            "school_id": 1,
            "academic_year": 1,
        },
    ).to_list(5000)
    courses = await db.courses.find(
        {
            "$or": [
                {"mantenedora_id": tenant_id},
                {"mantenedora_id": {"$exists": False}},
            ]
        },
        {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1},
    ).to_list(5000)

    school_items = sorted(
        [
            {"id": row.get("id"), "name": row.get("name") or row.get("nome") or ""}
            for row in schools
            if row.get("id")
        ],
        key=lambda row: row["name"].casefold(),
    )
    class_items = sorted(
        [
            {
                "id": row.get("id"),
                "name": row.get("name") or "",
                "school_id": row.get("school_id"),
                "academic_year": row.get("academic_year"),
            }
            for row in classes
            if row.get("id") and row.get("school_id")
        ],
        key=lambda row: (str(row["school_id"]), row["name"].casefold()),
    )
    course_items = sorted(
        [
            {"id": row.get("id"), "name": row.get("name") or ""}
            for row in courses
            if row.get("id")
            and (
                not row.get("mantenedora_id")
                or str(row.get("mantenedora_id")) == str(tenant_id)
            )
        ],
        key=lambda row: row["name"].casefold(),
    )
    return {
        "schools": school_items,
        "classes": class_items,
        "courses": course_items,
    }


def _payload_fingerprint(row: dict, source_kind: str) -> str:
    return _canonical_hash(
        {
            "source_kind": source_kind,
            "id": row.get("id"),
            "class_id": row.get("class_id"),
            "component_id": row.get("component_id") or row.get("course_id"),
            "date": str(row.get("date") or "")[:10],
            "number_of_classes": int(row.get("number_of_classes") or 1),
            "content": row.get("content") or "",
            "methodology": row.get("methodology"),
            "observations": row.get("observations"),
        }
    )


async def _source_rows(
    db,
    *,
    tenant_id: str,
    class_id: str,
    component_id: str,
    month: str,
) -> list[dict]:
    start, end, _year = _month_bounds(month)
    class_doc = await _class_in_tenant(db, tenant_id, class_id)
    await _school_in_tenant(db, tenant_id, class_doc.get("school_id"))
    await _component_exists(db, tenant_id, component_id)

    canonical = await db.content_entries.find(
        {
            "class_id": class_id,
            "date": {"$gte": start, "$lt": end},
            "deleted": False,
            **_component_match_query(component_id),
        },
        {"_id": 0},
    ).to_list(1000)
    legacy = await db.learning_objects.find(
        {
            "class_id": class_id,
            "course_id": component_id,
            "date": {"$gte": start, "$lt": end},
        },
        {"_id": 0},
    ).to_list(1000)

    rows: list[dict] = []
    tagged = [(row, "content_entries") for row in canonical] + [
        (row, "learning_objects") for row in legacy
    ]
    for row, kind in tagged:
        source_id = row.get("id")
        if not source_id:
            continue
        if row.get("mantenedora_id") and str(row.get("mantenedora_id")) != str(tenant_id):
            continue
        day = str(row.get("date") or "")[:10]
        content = str(row.get("content") or "")
        if not day or not content.strip():
            continue
        rows.append(
            {
                "id": source_id,
                "date": day,
                "number_of_classes": int(row.get("number_of_classes") or 1),
                "content": content,
                "methodology": row.get("methodology"),
                "observations": row.get("observations"),
                "source_kind": kind,
                "fingerprint": _payload_fingerprint(row, kind),
            }
        )
    rows.sort(key=lambda item: (item["date"], item["id"]))
    return rows


async def _canonical_user_for_actor(db, actor_id: str) -> Optional[dict]:
    if not actor_id:
        return None
    return await db.users.find_one(
        {"$or": [{"id": actor_id}, {"staff_id": actor_id}]},
        {"_id": 0, "id": 1, "full_name": 1, "name": 1, "staff_id": 1},
    )


async def _dvd_binding(
    db,
    *,
    class_id: str,
    component_id: str,
    target_date: str,
) -> Optional[dict]:
    rows = await db.teacher_class_assignments.find(
        {
            "class_id": class_id,
            "deleted": False,
            "diary_settings.enabled": True,
            "$or": [
                {"component_id": component_id},
                {"component_id": None},
            ],
        },
        {
            "_id": 0,
            "id": 1,
            "teacher_id": 1,
            "teacher_name": 1,
            "component_id": 1,
            "valid_from": 1,
            "valid_until": 1,
        },
    ).to_list(500)

    active = [
        row
        for row in rows
        if str(row.get("valid_from") or "0000-00-00") <= target_date
        and (
            not row.get("valid_until")
            or target_date <= str(row.get("valid_until"))
        )
    ]
    exact_active = [row for row in active if row.get("component_id") == component_id]
    candidates = exact_active or [row for row in active if row.get("component_id") is None]
    if len(candidates) == 1 and candidates[0].get("teacher_id"):
        row = candidates[0]
        return {
            "status": "RESOLVED",
            "mode": "DVD_ASSIGNMENT",
            "assignment_id": row.get("id"),
            "teacher_id": row.get("teacher_id"),
            "teacher_name": row.get("teacher_name"),
            "historical_backfill": False,
        }
    if len(candidates) > 1:
        return {"status": "AMBIGUOUS", "reason": "MULTIPLE_DVD_ASSIGNMENTS"}

    historical = [
        row
        for row in rows
        if row.get("valid_from") and target_date < str(row.get("valid_from"))
    ]
    exact_historical = [
        row for row in historical if row.get("component_id") == component_id
    ]
    candidates = exact_historical or [
        row for row in historical if row.get("component_id") is None
    ]
    if len(candidates) == 1 and candidates[0].get("teacher_id"):
        row = candidates[0]
        return {
            "status": "RESOLVED",
            "mode": "DVD_HISTORICAL_BACKFILL",
            "assignment_id": row.get("id"),
            "teacher_id": row.get("teacher_id"),
            "teacher_name": row.get("teacher_name"),
            "historical_backfill": True,
        }
    if len(candidates) > 1:
        return {
            "status": "AMBIGUOUS",
            "reason": "MULTIPLE_HISTORICAL_DVD_ASSIGNMENTS",
        }
    return None


async def _legacy_binding(
    db,
    *,
    class_doc: dict,
    component_id: str,
) -> Optional[dict]:
    academic_year = class_doc.get("academic_year")
    query = {
        "class_id": class_doc.get("id"),
        "course_id": component_id,
        "status": "ativo",
    }
    if academic_year is not None:
        query["academic_year"] = {
            "$in": [academic_year, str(academic_year)]
        }
    rows = await db.teacher_assignments.find(
        query,
        {"_id": 0, "staff_id": 1, "teacher_id": 1},
    ).to_list(100)
    actor_ids = sorted(
        {
            str(row.get("teacher_id") or row.get("staff_id"))
            for row in rows
            if row.get("teacher_id") or row.get("staff_id")
        }
    )
    if len(actor_ids) > 1:
        return {"status": "AMBIGUOUS", "reason": "MULTIPLE_LEGACY_TEACHERS"}
    if not actor_ids:
        return None

    user = await _canonical_user_for_actor(db, actor_ids[0])
    if not user or not user.get("id"):
        return {
            "status": "UNRESOLVED",
            "reason": "LEGACY_TEACHER_USER_ID_UNRESOLVED",
        }
    return {
        "status": "RESOLVED",
        "mode": "LEGACY_CANONICAL",
        "assignment_id": None,
        "teacher_id": user.get("id"),
        "teacher_name": user.get("full_name") or user.get("name"),
        "historical_backfill": False,
    }


async def _attendance_teacher_binding(
    db,
    *,
    class_id: str,
    component_id: str,
    target_date: str,
) -> Optional[dict]:
    rows = await db.attendance.find(
        {
            "class_id": class_id,
            "course_id": component_id,
            "date": target_date,
        },
        {"_id": 0, "teacher_id": 1, "staff_id": 1},
    ).to_list(100)
    actor_ids = sorted(
        {
            str(row.get("teacher_id") or row.get("staff_id"))
            for row in rows
            if row.get("teacher_id") or row.get("staff_id")
        }
    )
    if len(actor_ids) > 1:
        return {
            "status": "AMBIGUOUS",
            "reason": "MULTIPLE_ATTENDANCE_TEACHERS",
        }
    if not actor_ids:
        return None

    user = await _canonical_user_for_actor(db, actor_ids[0])
    if not user or not user.get("id"):
        return {
            "status": "UNRESOLVED",
            "reason": "ATTENDANCE_TEACHER_USER_ID_UNRESOLVED",
        }
    return {
        "status": "RESOLVED",
        "mode": "ATTENDANCE_TEACHER_SNAPSHOT",
        "assignment_id": None,
        "teacher_id": user.get("id"),
        "teacher_name": user.get("full_name") or user.get("name"),
        "historical_backfill": False,
    }


async def _resolve_target_binding(
    db,
    *,
    class_doc: dict,
    component_id: str,
    target_date: str,
) -> dict:
    dvd = await _dvd_binding(
        db,
        class_id=class_doc["id"],
        component_id=component_id,
        target_date=target_date,
    )
    if dvd:
        return dvd
    legacy = await _legacy_binding(
        db,
        class_doc=class_doc,
        component_id=component_id,
    )
    if legacy:
        return legacy
    attendance = await _attendance_teacher_binding(
        db,
        class_id=class_doc["id"],
        component_id=component_id,
        target_date=target_date,
    )
    if attendance:
        return attendance
    return {
        "status": "UNRESOLVED",
        "reason": "TARGET_TEACHER_NOT_RESOLVED",
    }


async def _occupied_dates(
    db,
    *,
    class_id: str,
    component_id: str,
    start: str,
    end: str,
) -> set[str]:
    canonical = await db.content_entries.find(
        {
            "class_id": class_id,
            "date": {"$gte": start, "$lt": end},
            "deleted": False,
            **_component_match_query(component_id),
        },
        {"_id": 0, "date": 1},
    ).to_list(1000)
    legacy = await db.learning_objects.find(
        {
            "class_id": class_id,
            "course_id": component_id,
            "date": {"$gte": start, "$lt": end},
        },
        {"_id": 0, "date": 1},
    ).to_list(1000)
    return {
        str(row.get("date") or "")[:10]
        for row in canonical + legacy
        if row.get("date")
    }


async def _destination_dates(
    db,
    *,
    tenant_id: str,
    class_id: str,
    component_id: str,
    month: str,
) -> list[dict]:
    start, end, _year = _month_bounds(month)
    class_doc = await _class_in_tenant(db, tenant_id, class_id)
    await _school_in_tenant(db, tenant_id, class_doc.get("school_id"))
    await _component_exists(db, tenant_id, component_id)

    attendance = await db.attendance.find(
        {
            "class_id": class_id,
            "course_id": component_id,
            "date": {"$gte": start, "$lt": end},
        },
        {"_id": 0, "date": 1, "number_of_classes": 1},
    ).to_list(3000)
    by_day: dict[str, list[dict]] = defaultdict(list)
    for row in attendance:
        day = str(row.get("date") or "")[:10]
        if start <= day < end:
            by_day[day].append(row)

    occupied = await _occupied_dates(
        db,
        class_id=class_id,
        component_id=component_id,
        start=start,
        end=end,
    )
    result = []
    for day, rows in sorted(by_day.items()):
        binding = await _resolve_target_binding(
            db,
            class_doc=class_doc,
            component_id=component_id,
            target_date=day,
        )
        unavailable_reason = None
        if day in occupied:
            unavailable_reason = "TARGET_ALREADY_HAS_CONTENT"
        elif binding.get("status") != "RESOLVED":
            unavailable_reason = (
                binding.get("reason") or "TARGET_BINDING_UNRESOLVED"
            )
        result.append(
            {
                "date": day,
                "session_count": len(rows),
                "declared_load": sum(
                    int(row.get("number_of_classes") or 1) for row in rows
                ),
                "available": unavailable_reason is None,
                "unavailable_reason": unavailable_reason,
                "binding_mode": (
                    binding.get("mode")
                    if binding.get("status") == "RESOLVED"
                    else None
                ),
                "teacher_name": (
                    binding.get("teacher_name")
                    if binding.get("status") == "RESOLVED"
                    else None
                ),
            }
        )
    return result


async def _build_plan(
    db,
    *,
    tenant_id: str,
    payload: ManualCopyPlanRequest,
) -> dict:
    source_class = await _class_in_tenant(
        db,
        tenant_id,
        payload.source_class_id,
    )
    target_class = await _class_in_tenant(
        db,
        tenant_id,
        payload.target_class_id,
    )
    await _school_in_tenant(db, tenant_id, source_class.get("school_id"))
    await _school_in_tenant(db, tenant_id, target_class.get("school_id"))
    await _component_exists(db, tenant_id, payload.source_component_id)
    await _component_exists(db, tenant_id, payload.target_component_id)

    source_rows = await _source_rows(
        db,
        tenant_id=tenant_id,
        class_id=payload.source_class_id,
        component_id=payload.source_component_id,
        month=payload.month,
    )
    source_by_id = {row["id"]: row for row in source_rows}
    destinations = await _destination_dates(
        db,
        tenant_id=tenant_id,
        class_id=payload.target_class_id,
        component_id=payload.target_component_id,
        month=payload.month,
    )
    destination_by_day = {row["date"]: row for row in destinations}

    selected = [mapping for mapping in payload.mappings if mapping.target_date]
    target_days = [mapping.target_date for mapping in selected]
    errors: list[dict] = []
    if len(target_days) != len(set(target_days)):
        errors.append(
            {
                "code": "DUPLICATE_TARGET_DATE",
                "message": "Uma data de destino foi selecionada mais de uma vez.",
            }
        )

    items = []
    for mapping in selected:
        source = source_by_id.get(mapping.source_id)
        target = destination_by_day.get(mapping.target_date or "")
        if not source:
            errors.append(
                {
                    "code": "SOURCE_NOT_FOUND_OR_CHANGED",
                    "source_id": mapping.source_id,
                }
            )
            continue
        if not target:
            errors.append(
                {
                    "code": "TARGET_DATE_NOT_ELIGIBLE",
                    "target_date": mapping.target_date,
                }
            )
            continue
        if not target.get("available"):
            errors.append(
                {
                    "code": target.get("unavailable_reason")
                    or "TARGET_NOT_AVAILABLE",
                    "target_date": mapping.target_date,
                }
            )
            continue
        binding = await _resolve_target_binding(
            db,
            class_doc=target_class,
            component_id=payload.target_component_id,
            target_date=mapping.target_date or "",
        )
        if binding.get("status") != "RESOLVED":
            errors.append(
                {
                    "code": binding.get("reason")
                    or "TARGET_BINDING_UNRESOLVED",
                    "target_date": mapping.target_date,
                }
            )
            continue
        items.append(
            {
                "source_id": source["id"],
                "source_date": source["date"],
                "source_kind": source["source_kind"],
                "source_fingerprint": source["fingerprint"],
                "target_date": mapping.target_date,
                "target_binding_mode": binding.get("mode"),
                "target_assignment_id": binding.get("assignment_id"),
                "target_teacher_id": binding.get("teacher_id"),
                "target_teacher_name": binding.get("teacher_name"),
                "historical_backfill": bool(
                    binding.get("historical_backfill")
                ),
            }
        )

    skipped = len(payload.mappings) - len(selected)
    manifest_core = {
        "schema": "MANUAL_MAPPED_CONTENT_COPY_V1",
        "copy_type": COPY_TYPE,
        "request_id": payload.request_id,
        "tenant_id": tenant_id,
        "month": payload.month,
        "source_class_id": payload.source_class_id,
        "source_component_id": payload.source_component_id,
        "target_class_id": payload.target_class_id,
        "target_component_id": payload.target_component_id,
        "items": items,
        "skipped_without_target": skipped,
        "errors": errors,
    }
    return {
        **manifest_core,
        "valid": not errors and bool(items),
        "selected_count": len(items),
        "manifest_hash": _canonical_hash(manifest_core),
    }


async def _load_source_full(
    db,
    *,
    source_id: str,
    tenant_id: str,
    expected_class_id: str,
    expected_component_id: str,
) -> tuple[dict, str]:
    canonical = await db.content_entries.find_one(
        {"id": source_id, "deleted": False},
        {"_id": 0},
    )
    if canonical:
        row, kind = canonical, "content_entries"
    else:
        legacy = await db.learning_objects.find_one(
            {"id": source_id},
            {"_id": 0},
        )
        if not legacy:
            raise HTTPException(
                status_code=409,
                detail="Conteúdo de origem não existe mais",
            )
        row, kind = legacy, "learning_objects"

    if row.get("class_id") != expected_class_id:
        raise HTTPException(
            status_code=409,
            detail="Conteúdo de origem mudou de turma",
        )
    row_component = row.get("component_id") or row.get("course_id")
    if row_component != expected_component_id:
        raise HTTPException(
            status_code=409,
            detail="Conteúdo de origem mudou de componente",
        )
    if row.get("mantenedora_id") and str(row.get("mantenedora_id")) != str(tenant_id):
        raise HTTPException(
            status_code=403,
            detail="Conteúdo de origem pertence a outra mantenedora",
        )
    return row, kind


async def _rollback_created(
    db,
    audit_service,
    user,
    request,
    created_ids: list[str],
    batch_id: str,
) -> None:
    """Rollback compensatório somente dos IDs criados neste apply em memória."""
    now = datetime.now(timezone.utc)
    for entry_id in created_ids:
        # A lista ``created_ids`` não vem do cliente: ela só recebe IDs retornados
        # por save_content_canonical nesta execução. Assim conseguimos reverter
        # inclusive se a atualização de provenance falhar antes de gravar batch_id.
        row = await db.content_entries.find_one(
            {
                "id": entry_id,
                "created_by": user.get("id"),
                "deleted": False,
            },
            {"_id": 0},
        )
        if not row:
            continue
        await db.content_entries.update_one(
            {"id": entry_id, "deleted": False},
            {
                "$set": {
                    "manual_copy_batch_id": batch_id,
                    "deleted": True,
                    "deleted_at": now,
                    "deleted_by": user.get("id"),
                    "manual_copy_rolled_back": True,
                }
            },
        )
        try:
            await audit_service.log(
                action="delete",
                collection="content_entries",
                user=user,
                request=request,
                document_id=entry_id,
                description=(
                    f"Rollback do lote de cópia manual mapeada {batch_id}"
                ),
                old_value={"manual_copy_batch_id": batch_id, "deleted": False},
                new_value={"manual_copy_batch_id": batch_id, "deleted": True},
                school_id=row.get("school_id"),
            )
        except Exception:  # noqa: BLE001
            # A falha de auditoria não pode interromper a limpeza dos demais IDs.
            continue


def _batch_key(tenant_id: str, request_id: str) -> str:
    return _canonical_hash(
        {"tenant_id": tenant_id, "request_id": request_id}
    )


def install_manual_content_copy_setup(content_entries_mod):
    """Instala o R2.0g no router canônico de conteúdo sem tocar em server.py."""
    if getattr(
        content_entries_mod,
        "_manual_content_copy_setup_installed",
        False,
    ):
        return

    original_setup = content_entries_mod.setup_content_entries_router

    def setup_content_entries_router(db, audit_service, sandbox_db=None):
        base_router = original_setup(db, audit_service, sandbox_db)
        if getattr(
            base_router,
            "_manual_content_copy_admin_installed",
            False,
        ):
            return base_router

        @base_router.get("/admin/manual-copy/options")
        async def manual_copy_options(request: Request):
            user = await _require_super_admin(request)
            tenant = await resolve_operational_tenant_context(
                db,
                user,
                request,
            )
            return await _options(db, tenant_id=tenant.id)

        @base_router.get("/admin/manual-copy/source")
        async def manual_copy_source(
            request: Request,
            class_id: str = Query(...),
            component_id: str = Query(...),
            month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
        ):
            user = await _require_super_admin(request)
            tenant = await resolve_operational_tenant_context(
                db,
                user,
                request,
            )
            items = await _source_rows(
                db,
                tenant_id=tenant.id,
                class_id=class_id,
                component_id=component_id,
                month=month,
            )
            return {"month": month, "items": items, "count": len(items)}

        @base_router.get("/admin/manual-copy/destinations")
        async def manual_copy_destinations(
            request: Request,
            class_id: str = Query(...),
            component_id: str = Query(...),
            month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
        ):
            user = await _require_super_admin(request)
            tenant = await resolve_operational_tenant_context(
                db,
                user,
                request,
            )
            items = await _destination_dates(
                db,
                tenant_id=tenant.id,
                class_id=class_id,
                component_id=component_id,
                month=month,
            )
            return {"month": month, "items": items, "count": len(items)}

        @base_router.post("/admin/manual-copy/preflight")
        async def manual_copy_preflight(
            payload: ManualCopyPlanRequest,
            request: Request,
        ):
            user = await _require_super_admin(request)
            tenant = await resolve_operational_tenant_context(
                db,
                user,
                request,
            )
            return await _build_plan(
                db,
                tenant_id=tenant.id,
                payload=payload,
            )

        @base_router.post("/admin/manual-copy/apply")
        async def manual_copy_apply(
            payload: ManualCopyApplyRequest,
            request: Request,
        ):
            user = await _require_super_admin(request)
            tenant = await resolve_operational_tenant_context(
                db,
                user,
                request,
            )

            key = _batch_key(tenant.id, payload.request_id)
            existing_batch = await db[BATCH_COLLECTION].find_one(
                {"_id": key},
                {"_id": 0},
            )
            if existing_batch and existing_batch.get("status") == "COMPLETED":
                return existing_batch.get("result") or {}
            if existing_batch:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "MANUAL_COPY_REQUEST_ALREADY_USED",
                        "message": (
                            "Este identificador de lote já foi usado. "
                            "Recarregue a tela antes de tentar novamente."
                        ),
                    },
                )

            plan_payload = ManualCopyPlanRequest(
                **payload.model_dump(exclude={"manifest_hash"})
            )
            plan = await _build_plan(
                db,
                tenant_id=tenant.id,
                payload=plan_payload,
            )
            if not plan.get("valid"):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "MANUAL_COPY_PREFLIGHT_FAILED",
                        "errors": plan.get("errors"),
                    },
                )
            if plan.get("manifest_hash") != payload.manifest_hash:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "MANUAL_COPY_MANIFEST_CHANGED",
                        "message": (
                            "O estado mudou após o preflight; "
                            "revise o mapa antes de copiar."
                        ),
                    },
                )

            batch_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            try:
                await db[BATCH_COLLECTION].insert_one(
                    {
                        "_id": key,
                        "batch_id": batch_id,
                        "request_id": payload.request_id,
                        "mantenedora_id": tenant.id,
                        "manifest_hash": payload.manifest_hash,
                        "status": "RUNNING",
                        "started_at": now,
                        "started_by": user.get("id"),
                        "copy_type": COPY_TYPE,
                    }
                )
            except DuplicateKeyError as exc:
                current = await db[BATCH_COLLECTION].find_one(
                    {"_id": key},
                    {"_id": 0},
                )
                if current and current.get("status") == "COMPLETED":
                    return current.get("result") or {}
                raise HTTPException(
                    status_code=409,
                    detail="Este lote já está em execução ou já foi usado",
                ) from exc

            created_ids: list[str] = []
            try:
                target_class = await _class_in_tenant(
                    db,
                    tenant.id,
                    payload.target_class_id,
                )
                for item in plan["items"]:
                    source, source_kind = await _load_source_full(
                        db,
                        source_id=item["source_id"],
                        tenant_id=tenant.id,
                        expected_class_id=payload.source_class_id,
                        expected_component_id=payload.source_component_id,
                    )
                    current_fp = _payload_fingerprint(source, source_kind)
                    if current_fp != item["source_fingerprint"]:
                        raise HTTPException(
                            status_code=409,
                            detail="Conteúdo de origem mudou durante o lote",
                        )

                    # expected_version=0 transforma qualquer rascunho concorrente
                    # que surgir entre preflight/apply em conflito 409. O writer
                    # canônico não poderá convertê-lo em update silencioso.
                    create = ContentEntryCreate(
                        class_id=payload.target_class_id,
                        course_id=payload.target_component_id,
                        component_id=payload.target_component_id,
                        date=item["target_date"],
                        teacher_id=(
                            item.get("target_teacher_id")
                            if not item.get("target_assignment_id")
                            else None
                        ),
                        assignment_id=item.get("target_assignment_id"),
                        academic_year=target_class.get("academic_year"),
                        number_of_classes=int(
                            source.get("number_of_classes") or 1
                        ),
                        content=source.get("content") or "",
                        methodology=source.get("methodology"),
                        observations=source.get("observations"),
                        expected_version=0,
                    )
                    created = await save_content_canonical(
                        db,
                        user,
                        request,
                        create,
                        audit_service,
                    )
                    created_ids.append(created["id"])
                    provenance = {
                        "manual_copy_batch_id": batch_id,
                        "manual_copy_request_id": payload.request_id,
                        "manual_copy_manifest_hash": payload.manifest_hash,
                        "manual_copy_type": COPY_TYPE,
                        "manual_copy_administrative_reconstruction": True,
                        "manual_copy_source_id": item["source_id"],
                        "manual_copy_source_kind": source_kind,
                        "manual_copy_source_class_id": payload.source_class_id,
                        "manual_copy_source_component_id": payload.source_component_id,
                        "manual_copy_source_date": item["source_date"],
                        "manual_copy_source_fingerprint": item[
                            "source_fingerprint"
                        ],
                        "manual_copy_target_class_id": payload.target_class_id,
                        "manual_copy_target_component_id": payload.target_component_id,
                        "manual_copy_target_date": item["target_date"],
                        "manual_copy_target_binding_mode": item[
                            "target_binding_mode"
                        ],
                        "manual_copy_authorized_by": user.get("id"),
                        "manual_copy_at": datetime.now(timezone.utc),
                    }
                    updated = await db.content_entries.update_one(
                        {"id": created["id"], "deleted": False},
                        {"$set": provenance},
                    )
                    if updated.modified_count != 1:
                        raise HTTPException(
                            status_code=500,
                            detail="Falha ao persistir a proveniência do lote",
                        )

                result = {
                    "status": "COMPLETED",
                    "message": "Cópia concluída",
                    "batch_id": batch_id,
                    "manifest_hash": payload.manifest_hash,
                    "copied_count": len(created_ids),
                    "skipped_without_target": plan.get(
                        "skipped_without_target",
                        0,
                    ),
                }
                await db[BATCH_COLLECTION].update_one(
                    {"_id": key, "batch_id": batch_id},
                    {
                        "$set": {
                            "status": "COMPLETED",
                            "completed_at": datetime.now(timezone.utc),
                            "result": result,
                        }
                    },
                )
                await audit_service.log(
                    action="create",
                    collection=BATCH_COLLECTION,
                    user=user,
                    request=request,
                    document_id=batch_id,
                    description=(
                        "Concluiu lote de cópia manual mapeada com "
                        f"{len(created_ids)} registros"
                    ),
                    new_value={
                        "batch_id": batch_id,
                        "manifest_hash": payload.manifest_hash,
                        "copied_count": len(created_ids),
                    },
                    school_id=target_class.get("school_id"),
                )
                return result
            except Exception as exc:
                await _rollback_created(
                    db,
                    audit_service,
                    user,
                    request,
                    created_ids,
                    batch_id,
                )
                await db[BATCH_COLLECTION].update_one(
                    {"_id": key, "batch_id": batch_id},
                    {
                        "$set": {
                            "status": "FAILED_ROLLED_BACK",
                            "failed_at": datetime.now(timezone.utc),
                            "rolled_back_count": len(created_ids),
                            "error_type": type(exc).__name__,
                        }
                    },
                )
                raise

        base_router._manual_content_copy_admin_installed = True
        return base_router

    content_entries_mod.setup_content_entries_router = setup_content_entries_router
    content_entries_mod._manual_content_copy_setup_installed = True
