"""Cópia segura de Objetos de Conhecimento no Diário por Vínculo.

Adiciona uma rota canônica de cópia sobre ``content_entries`` sem reativar
escritas em ``learning_objects``. A origem pode ser conteúdo canônico ou
histórico legado visível no vínculo; o destino precisa ser um assignment
explicitamente autorizado do professor.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel

from auth_middleware import AuthMiddleware
from routers.content_entries import ContentEntryCreate, save_content_canonical
from services.content_assignment_scope import (
    ContentAssignmentScopeError,
    authorize_content_record,
)
from services.content_history_bridge import (
    ContentHistoryBridgeError,
    list_assignment_content_history,
)
from services.diary_assignment_access import DiaryAction
from tenant_scope import get_mantenedora_scope


class ContentCopyDvdRequest(BaseModel):
    target_class_id: str
    target_course_id: str
    target_date: Optional[str] = None
    source_assignment_id: Optional[str] = None
    target_assignment_id: str


def _scope_error(exc: Exception) -> HTTPException:
    code = getattr(exc, "code", "CONTENT_COPY_FORBIDDEN")
    message = getattr(exc, "message", str(exc))
    status = 404 if code in {"ASSIGNMENT_NOT_FOUND", "CLASS_NOT_FOUND"} else 403
    if code in {"ASSIGNMENT_NOT_ACTIVE", "DVD_NOT_ENABLED"}:
        status = 409
    return HTTPException(
        status_code=status,
        detail={"code": code, "message": message},
    )


async def _assert_visible_through_source_assignment(
    db,
    user,
    request,
    *,
    source_id: str,
    source_assignment_id: Optional[str],
    class_id: Optional[str],
    component_id: Optional[str],
) -> None:
    """Prova que uma origem sem assignment próprio é visível pelo vínculo informado."""
    if not source_assignment_id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SOURCE_ASSIGNMENT_REQUIRED",
                "message": "A cópia de conteúdo histórico requer o vínculo docente de origem.",
            },
        )

    try:
        visible = await list_assignment_content_history(
            db,
            user,
            assignment_id=source_assignment_id,
            class_id=class_id,
            component_id=component_id,
            active_mantenedora_id=get_mantenedora_scope(user, request),
        )
    except ContentHistoryBridgeError as exc:
        raise _scope_error(exc) from exc

    if not any(item.get("id") == source_id for item in visible.get("items", [])):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "SOURCE_CONTENT_NOT_VISIBLE",
                "message": "O conteúdo de origem não pertence ao histórico visível deste vínculo.",
            },
        )


async def _resolve_authorized_source(
    db,
    user,
    request,
    source_id: str,
    source_assignment_id: Optional[str],
):
    canonical = await db.content_entries.find_one(
        {"id": source_id, "deleted": False}, {"_id": 0}
    )
    if canonical:
        if canonical.get("assignment_id"):
            try:
                await authorize_content_record(
                    db,
                    user,
                    canonical,
                    action=DiaryAction.VIEW,
                    allow_management_override=False,
                    active_mantenedora_id=get_mantenedora_scope(user, request),
                )
            except ContentAssignmentScopeError as exc:
                raise _scope_error(exc) from exc
        else:
            await _assert_visible_through_source_assignment(
                db,
                user,
                request,
                source_id=source_id,
                source_assignment_id=source_assignment_id,
                class_id=canonical.get("class_id"),
                component_id=canonical.get("component_id") or canonical.get("course_id"),
            )
        return canonical, "content_entries"

    legacy = await db.learning_objects.find_one({"id": source_id}, {"_id": 0})
    if not legacy:
        raise HTTPException(status_code=404, detail="Conteúdo de origem não encontrado")

    await _assert_visible_through_source_assignment(
        db,
        user,
        request,
        source_id=source_id,
        source_assignment_id=source_assignment_id,
        class_id=legacy.get("class_id"),
        component_id=legacy.get("course_id"),
    )
    return legacy, "learning_objects"


def install_content_copy_dvd_adapter(base_router, db, audit_service):
    if getattr(base_router, "_dvd_content_copy_installed", False):
        return base_router

    @base_router.post("/{source_id}/copy-to-class")
    async def copy_content_dvd(
        source_id: str,
        payload: ContentCopyDvdRequest,
        request: Request,
    ):
        user = await AuthMiddleware.require_roles(["professor"])(request)
        source, source_kind = await _resolve_authorized_source(
            db, user, request, source_id, payload.source_assignment_id
        )

        target_date = payload.target_date or str(source.get("date") or "")[:10]
        if not target_date:
            raise HTTPException(status_code=422, detail="Data de destino inválida")

        if (
            payload.target_class_id == source.get("class_id")
            and payload.target_course_id in {source.get("course_id"), source.get("component_id")}
            and target_date == str(source.get("date") or "")[:10]
        ):
            raise HTTPException(
                status_code=409,
                detail="A turma/componente/data de destino é igual ao conteúdo de origem",
            )

        target_class = await db.classes.find_one(
            {"id": payload.target_class_id},
            {"_id": 0, "academic_year": 1, "school_id": 1},
        )
        if not target_class:
            raise HTTPException(status_code=404, detail="Turma de destino não encontrada")

        # Evita que a semântica de copiar se transforme em atualização silenciosa.
        existing_target = await db.content_entries.find_one(
            {
                "class_id": payload.target_class_id,
                "component_id": payload.target_course_id,
                "assignment_id": payload.target_assignment_id,
                "date": target_date,
                "deleted": False,
            },
            {"_id": 0, "id": 1},
        )
        if existing_target:
            raise HTTPException(
                status_code=409,
                detail=f"Já existe conteúdo no destino em {target_date}.",
            )

        create_payload = ContentEntryCreate(
            class_id=payload.target_class_id,
            course_id=payload.target_course_id,
            component_id=payload.target_course_id,
            date=target_date,
            academic_year=(
                target_class.get("academic_year")
                or source.get("academic_year")
                or datetime.now().year
            ),
            number_of_classes=source.get("number_of_classes") or 1,
            content=source.get("content") or "",
            methodology=source.get("methodology"),
            observations=source.get("observations"),
            assignment_id=payload.target_assignment_id,
        )
        created = await save_content_canonical(
            db, user, request, create_payload, audit_service
        )

        now = datetime.now(timezone.utc).isoformat()
        await db.content_entries.update_one(
            {"id": created["id"]},
            {"$set": {
                "copied_from_id": source_id,
                "copied_from_source": source_kind,
                "copied_at": now,
            }},
        )
        updated = await db.content_entries.find_one(
            {"id": created["id"]}, {"_id": 0}
        )

        await audit_service.log(
            action="update",
            collection="content_entries",
            user=user,
            request=request,
            document_id=created["id"],
            description=(
                f"Copiou conteúdo {source_id} para turma {payload.target_class_id}, "
                f"componente {payload.target_course_id}, data {target_date}"
            ),
            old_value=None,
            new_value={
                "copied_from_id": source_id,
                "copied_from_source": source_kind,
                "target_assignment_id": payload.target_assignment_id,
            },
            school_id=target_class.get("school_id"),
        )
        return updated

    base_router._dvd_content_copy_installed = True
    return base_router


def install_content_copy_setup(content_entries_mod):
    """Envolve o setup já harmonizado para instalar a cópia DVD no mesmo router."""
    if getattr(content_entries_mod, "_dvd_content_copy_setup_installed", False):
        return

    original_setup = content_entries_mod.setup_content_entries_router

    def setup_content_entries_router(db, audit_service, sandbox_db=None):
        configured = original_setup(db, audit_service, sandbox_db)
        return install_content_copy_dvd_adapter(configured, db, audit_service)

    content_entries_mod.setup_content_entries_router = setup_content_entries_router
    content_entries_mod._dvd_content_copy_setup_installed = True
