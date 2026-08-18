"""
Router de Conteúdo Pedagógico (Diário) — SIGESC.

Rodada 2 (Mai/2026) — Fase 2: split do domínio "conteúdo" em coleção
própria (`content_entries`), independente de `attendance`.
DVD (Ago/2026) — Fase 2: propriedade pedagógica por `assignment_id`.

Princípios arquiteturais:
  - Legado: 1 entry por (turma, data, componente, aula_numero, professor).
  - DVD: 1 entry por (turma, data, componente, aula_numero, assignment_id).
  - Vínculo SEMÂNTICO — sem `attendance_id`; frequência e conteúdo são independentes.
  - `teacher_id` permanece como snapshot de autoria pedagógica; em DVD é derivado
    do vínculo autorizado, nunca confiado isoladamente ao payload.
  - Optimistic locking (`expected_version`) + soft delete + auditoria canônica.
"""
from datetime import datetime, timezone
from typing import List, Optional
import logging
import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth_middleware import AuthMiddleware
from services.content_assignment_scope import (
    ContentAssignmentScopeError,
    authorize_content_record,
    filter_visible_content_entries,
    resolve_content_assignment_for_create,
)
from services.content_audit import build_content_audit_extra, compute_snapshot_hash
from services.diary_assignment_access import DiaryAction
from utils.academic_year import create_academic_year_validators
from tenant_scope import get_mantenedora_scope, resolve_tenant_id_for_create

logger = logging.getLogger(__name__)

WRITE_ROLES = [
    'professor', 'coordenador', 'admin', 'admin_teste', 'super_admin',
    'secretario', 'gerente', 'auxiliar_secretaria',
]
VIEW_ROLES = WRITE_ROLES + ['diretor', 'ass_social_2', 'semed3']


class ContentEntryCreate(BaseModel):
    class_id: str
    date: str
    course_id: Optional[str] = None
    component_id: Optional[str] = None
    aula_numero: Optional[int] = None
    teacher_id: Optional[str] = None
    assignment_id: Optional[str] = None
    academic_year: Optional[int] = None
    number_of_classes: int = 1
    content: str = Field(..., min_length=1, max_length=20000)
    methodology: Optional[str] = Field(default=None, max_length=5000)
    observations: Optional[str] = Field(default=None, max_length=5000)
    expected_version: Optional[int] = None
    force_overwrite: bool = False
    change_note: Optional[str] = None


class ContentEntryUpdate(BaseModel):
    content: Optional[str] = Field(default=None, min_length=1, max_length=20000)
    methodology: Optional[str] = Field(default=None, max_length=5000)
    observations: Optional[str] = Field(default=None, max_length=5000)
    expected_version: Optional[int] = None
    force_overwrite: bool = False
    change_note: Optional[str] = None


class ContentEntryDeleteRequest(BaseModel):
    change_note: str = Field(..., min_length=1, max_length=500)


class ContentEntryPublishRequest(BaseModel):
    expected_version: Optional[int] = None


class ContentEntryCorrectRequest(BaseModel):
    change_note: str = Field(..., min_length=1, max_length=500)
    expected_version: Optional[int] = None
    content: Optional[str] = Field(default=None, min_length=1, max_length=20000)
    methodology: Optional[str] = Field(default=None, max_length=5000)
    observations: Optional[str] = Field(default=None, max_length=5000)
    number_of_classes: Optional[int] = Field(default=None, ge=1)


async def _resolve_class_info(db, class_id: str) -> Optional[dict]:
    return await db.classes.find_one(
        {"id": class_id}, {"_id": 0, "name": 1, "school_id": 1}
    )


async def _resolve_teacher_name(db, teacher_id: Optional[str]) -> Optional[str]:
    if not teacher_id:
        return None
    u = await db.users.find_one(
        {"id": teacher_id}, {"_id": 0, "full_name": 1, "name": 1}
    )
    if not u:
        return None
    return u.get("full_name") or u.get("name")


def _public(entry: dict) -> dict:
    if entry is None:
        return None
    e = dict(entry)
    e.pop("_id", None)
    return e


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _assignment_error_to_http(exc: ContentAssignmentScopeError):
    not_found = {"ASSIGNMENT_NOT_FOUND", "CLASS_NOT_FOUND"}
    conflicts = {
        "DVD_CONTENT_ASSIGNMENT_REQUIRED",
        "DVD_CONTENT_ASSIGNMENT_AMBIGUOUS",
        "ASSIGNMENT_NOT_ACTIVE",
        "DVD_NOT_ENABLED",
    }
    status = 404 if exc.code in not_found else 409 if exc.code in conflicts else 403
    raise HTTPException(
        status_code=status,
        detail={"code": exc.code, "message": exc.message},
    ) from exc


async def _authorize_dvd_record(
    db,
    current_user,
    request,
    entry,
    *,
    action=DiaryAction.VIEW,
    allow_management_override=False,
):
    if not entry.get("assignment_id"):
        return None
    try:
        return await authorize_content_record(
            db,
            current_user,
            entry,
            action=action,
            allow_management_override=allow_management_override,
            active_mantenedora_id=get_mantenedora_scope(current_user, request),
        )
    except ContentAssignmentScopeError as exc:
        _assignment_error_to_http(exc)


async def _resolve_bimestre_for_date(db, academic_year: int, target_date: str) -> Optional[int]:
    calendario = await db.calendario_letivo.find_one({"ano_letivo": academic_year}, {"_id": 0})
    if not calendario:
        return None
    for i in range(1, 5):
        inicio = calendario.get(f"bimestre_{i}_inicio")
        fim = calendario.get(f"bimestre_{i}_fim")
        if inicio and fim and inicio <= target_date <= fim:
            return i
    return None


async def save_content_canonical(db, current_user, request, entry: "ContentEntryCreate", audit_service):
    """Motor canônico ÚNICO de escrita de conteúdo pedagógico.

    O caminho legado é preservado quando não existe DVD ativo para o contexto.
    Em DVD, `assignment_id` é a propriedade pedagógica e `teacher_id` é derivado
    do vínculo autorizado. O adapter legado e o frontend atual podem omitir
    assignment apenas quando houver um único vínculo DVD inequívoco do professor.
    """
    validators = create_academic_year_validators(db)
    user_role = current_user.get("role", "")

    class_info = await db.classes.find_one(
        {"id": entry.class_id}, {"_id": 0, "name": 1, "school_id": 1, "academic_year": 1}
    )
    if not class_info:
        raise HTTPException(status_code=404, detail="Turma não encontrada")

    academic_year = entry.academic_year or class_info.get("academic_year") or datetime.now().year
    school_id = class_info.get("school_id")
    component_id = entry.component_id or entry.course_id

    try:
        resolution = await resolve_content_assignment_for_create(
            db,
            current_user,
            class_id=entry.class_id,
            component_id=component_id,
            on_date=entry.date,
            assignment_id=entry.assignment_id,
            provided_teacher_id=entry.teacher_id,
            allow_management_override=bool(entry.assignment_id),
            active_mantenedora_id=get_mantenedora_scope(current_user, request),
        )
    except ContentAssignmentScopeError as exc:
        _assignment_error_to_http(exc)

    teacher_id = resolution.teacher_id
    teacher_unknown = teacher_id is None
    teacher_name = (
        resolution.teacher_name
        or await _resolve_teacher_name(db, teacher_id)
        or current_user.get("name")
    )

    if user_role != "admin":
        await validators["verify_academic_year_open_or_raise"](school_id, academic_year)
    if user_role not in ["admin", "admin_teste", "super_admin", "gerente", "secretario"]:
        bimestre = await _resolve_bimestre_for_date(db, academic_year, entry.date)
        if bimestre:
            await validators["verify_bimestre_edit_deadline_or_raise"](academic_year, bimestre, user_role)

    now = datetime.now(timezone.utc)
    if resolution.dvd_enabled:
        nk = {
            "class_id": entry.class_id,
            "component_id": component_id,
            "assignment_id": resolution.assignment_id,
            "date": entry.date,
            "aula_numero": entry.aula_numero,
            "deleted": False,
        }
    else:
        nk = {
            "class_id": entry.class_id,
            "component_id": component_id,
            "teacher_id": teacher_id,
            "assignment_id": {"$exists": False},
            "date": entry.date,
            "aula_numero": entry.aula_numero,
            "deleted": False,
        }
    existing = await db.content_entries.find_one(nk)

    if existing:
        if existing.get("status") != "draft":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "REQUIRES_CORRECT_FLOW",
                    "message": (
                        "Já existe conteúdo publicado para esta turma/componente/aula/data. "
                        "Use POST /content-entries/{id}/correct com change_note."
                    ),
                    "current_status": existing.get("status"),
                    "content_entry_id": existing.get("id"),
                },
            )

        current_version = existing.get("version") or 1
        ev = entry.expected_version
        change_kind = "content_updated"
        if ev is not None and ev != current_version:
            if not entry.force_overwrite:
                last_uid = existing.get("updated_by") or existing.get("created_by")
                last_modifier = None
                if last_uid:
                    u = await db.users.find_one(
                        {"id": last_uid}, {"_id": 0, "name": 1, "full_name": 1, "email": 1, "role": 1}
                    )
                    if u:
                        last_modifier = {
                            "id": last_uid,
                            "name": u.get("full_name") or u.get("name"),
                            "email": u.get("email"),
                            "role": u.get("role"),
                        }
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "CONTENT_VERSION_CONFLICT",
                        "message": (
                            "Conteúdo foi alterado por outro usuário desde que você carregou. "
                            "Recarregue OU reenvie com force_overwrite=true e change_note='motivo'."
                        ),
                        "expected_version": ev,
                        "current_version": current_version,
                        "last_modified_by": last_modifier,
                        "last_modified_at": _iso(existing.get("updated_at")),
                        "content_entry_id": existing.get("id"),
                    },
                )
            if not (entry.change_note and entry.change_note.strip()):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "OVERWRITE_REQUIRES_NOTE",
                        "message": "Sobrescrita após conflito requer change_note (motivo) obrigatório.",
                    },
                )
            change_kind = "content_overwrite"

        new_version = current_version + 1
        previous_content = existing.get("content")
        set_fields = {
            "content": entry.content,
            "methodology": entry.methodology,
            "observations": entry.observations,
            "number_of_classes": entry.number_of_classes,
            "academic_year": academic_year,
            "updated_by": current_user["id"],
            "updated_at": now,
            "version": new_version,
        }
        await db.content_entries.update_one({"id": existing["id"]}, {"$set": set_fields})
        updated = await db.content_entries.find_one({"id": existing["id"]}, {"_id": 0})

        extra = build_content_audit_extra(
            entry=updated, change_kind=change_kind,
            expected_version=ev, final_version=new_version,
            previous_content=previous_content, new_content=entry.content,
            change_note=entry.change_note if change_kind == "content_overwrite" else None,
            class_info=class_info,
        )
        await audit_service.log(
            action="update", collection="content_entries",
            user=current_user, request=request, document_id=existing["id"],
            description=(
                f"{'Sobrescreveu' if change_kind == 'content_overwrite' else 'Atualizou'} "
                f"conteúdo da turma {class_info.get('name', 'N/A')} em {entry.date}"
            ),
            old_value={"content": previous_content, "version": current_version},
            new_value={"content": entry.content, "version": new_version},
            school_id=school_id,
            extra_data=extra,
        )
        return _public(updated)

    mantenedora_id = await resolve_tenant_id_for_create(
        db, current_user, request, class_id=entry.class_id
    )
    doc = {
        "id": str(uuid.uuid4()),
        "mantenedora_id": mantenedora_id,
        "academic_year": academic_year,
        "class_id": entry.class_id,
        "course_id": entry.course_id,
        "component_id": component_id,
        "aula_numero": entry.aula_numero,
        "date": entry.date,
        "teacher_id": teacher_id,
        "teacher_name": teacher_name,
        "teacher_unknown": teacher_unknown,
        "number_of_classes": entry.number_of_classes,
        "content": entry.content,
        "methodology": entry.methodology,
        "observations": entry.observations,
        "status": "draft",
        "version": 1,
        "deleted": False,
        "created_by": current_user["id"],
        "created_at": now,
        "updated_by": current_user["id"],
        "updated_at": now,
        "published_at": None,
        "published_by": None,
        "corrected_from_version": None,
        "school_id": school_id,
    }
    if resolution.dvd_enabled:
        doc["assignment_id"] = resolution.assignment_id
        doc["assignment_profile_at_record"] = resolution.access_context.settings.profile.value
        doc["assignment_schema_version_at_record"] = resolution.access_context.settings.schema_version

    try:
        await db.content_entries.insert_one(doc)
    except Exception as ex:  # noqa: BLE001
        if "duplicate key" in str(ex).lower():
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CONTENT_ENTRY_DUPLICATE",
                    "message": "Já existe entry para esta turma/data/componente/aula/vínculo pedagógico.",
                },
            )
        raise

    extra = build_content_audit_extra(
        entry=doc, change_kind="content_created",
        expected_version=None, final_version=1,
        previous_content=None, new_content=entry.content,
        class_info=class_info,
    )
    await audit_service.log(
        action="create", collection="content_entries",
        user=current_user, request=request, document_id=doc["id"],
        description=(
            f"Criou conteúdo da turma {class_info.get('name', 'N/A')} "
            f"em {entry.date} (aula {entry.aula_numero or '-'})"
        ),
        school_id=school_id,
        extra_data=extra,
    )
    return _public(await db.content_entries.find_one({"id": doc["id"]}, {"_id": 0}))


def setup_content_entries_router(db, audit_service, sandbox_db=None):
    router = APIRouter(prefix="/content-entries", tags=["Diário - Conteúdo"])

    @router.post("")
    async def create_content_entry(entry: ContentEntryCreate, request: Request):
        current_user = await AuthMiddleware.require_roles(WRITE_ROLES)(request)
        return await save_content_canonical(db, current_user, request, entry, audit_service)

    @router.get("")
    async def list_content_entries(
        request: Request,
        class_id: Optional[str] = Query(None),
        date: Optional[str] = Query(None),
        teacher_id: Optional[str] = Query(None),
        component_id: Optional[str] = Query(None),
        assignment_id: Optional[str] = Query(None),
        include_deleted: bool = Query(False),
    ):
        current_user = await AuthMiddleware.require_roles(VIEW_ROLES)(request)
        q: dict = {}
        if not include_deleted:
            q["deleted"] = False
        if class_id:
            q["class_id"] = class_id
        if date:
            q["date"] = date
        if teacher_id:
            q["teacher_id"] = teacher_id
        if component_id:
            q["component_id"] = component_id
        if assignment_id:
            q["assignment_id"] = assignment_id
        cursor = db.content_entries.find(q, {"_id": 0}).sort([("date", -1), ("aula_numero", 1)])
        items = await cursor.to_list(2000)
        visible = await filter_visible_content_entries(
            db,
            current_user,
            items,
            active_mantenedora_id=get_mantenedora_scope(current_user, request),
        )
        return {"items": visible, "total": len(visible)}

    @router.get("/{entry_id}")
    async def get_content_entry(entry_id: str, request: Request):
        current_user = await AuthMiddleware.require_roles(VIEW_ROLES)(request)
        e = await db.content_entries.find_one({"id": entry_id}, {"_id": 0})
        if not e:
            raise HTTPException(status_code=404, detail="Conteúdo não encontrado")
        await _authorize_dvd_record(db, current_user, request, e, action=DiaryAction.VIEW)
        return e

    @router.put("/{entry_id}")
    async def update_content_entry(entry_id: str, patch: ContentEntryUpdate, request: Request):
        current_user = await AuthMiddleware.require_roles(WRITE_ROLES)(request)
        existing = await db.content_entries.find_one({"id": entry_id, "deleted": False}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Conteúdo não encontrado")
        await _authorize_dvd_record(
            db, current_user, request, existing,
            action=DiaryAction.CONTENT, allow_management_override=True,
        )

        if existing.get("status") != "draft":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "REQUIRES_CORRECT_FLOW",
                    "message": (
                        "Conteúdo já publicado. Para alterá-lo use "
                        "POST /content-entries/{id}/correct com change_note obrigatório."
                    ),
                    "current_status": existing.get("status"),
                    "content_entry_id": entry_id,
                },
            )

        current_version = existing.get("version") or 1
        ev = patch.expected_version
        change_kind = "content_updated"
        if ev is not None and ev != current_version:
            if not patch.force_overwrite:
                last_uid = existing.get("updated_by") or existing.get("created_by")
                last_modifier = None
                if last_uid:
                    u = await db.users.find_one(
                        {"id": last_uid}, {"_id": 0, "name": 1, "full_name": 1, "email": 1, "role": 1}
                    )
                    if u:
                        last_modifier = {
                            "id": last_uid,
                            "name": u.get("full_name") or u.get("name"),
                            "email": u.get("email"),
                            "role": u.get("role"),
                        }
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "CONTENT_VERSION_CONFLICT",
                        "message": (
                            "Conteúdo foi alterado por outro usuário desde que você carregou. "
                            "Recarregue OU reenvie com force_overwrite=true e change_note='motivo'."
                        ),
                        "expected_version": ev,
                        "current_version": current_version,
                        "last_modified_by": last_modifier,
                        "last_modified_at": _iso(existing.get("updated_at")),
                        "content_entry_id": entry_id,
                    },
                )
            if not (patch.change_note and patch.change_note.strip()):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "OVERWRITE_REQUIRES_NOTE",
                        "message": "Sobrescrita após conflito requer change_note (motivo) obrigatório.",
                    },
                )
            change_kind = "content_overwrite"

        new_version = current_version + 1
        set_fields = {
            "updated_by": current_user["id"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "version": new_version,
        }
        previous_content = existing.get("content")
        new_content = previous_content
        if patch.content is not None:
            set_fields["content"] = patch.content
            new_content = patch.content
        if patch.methodology is not None:
            set_fields["methodology"] = patch.methodology
        if patch.observations is not None:
            set_fields["observations"] = patch.observations

        await db.content_entries.update_one({"id": entry_id}, {"$set": set_fields})
        updated = await db.content_entries.find_one({"id": entry_id}, {"_id": 0})

        class_info = await _resolve_class_info(db, existing["class_id"])
        extra = build_content_audit_extra(
            entry=updated, change_kind=change_kind,
            expected_version=ev, final_version=new_version,
            previous_content=previous_content,
            new_content=new_content,
            change_note=patch.change_note if change_kind == "content_overwrite" else None,
            class_info=class_info,
        )
        await audit_service.log(
            action="update", collection="content_entries",
            user=current_user, request=request, document_id=entry_id,
            description=(
                f"{'Sobrescreveu' if change_kind == 'content_overwrite' else 'Atualizou'} "
                f"conteúdo da turma {class_info.get('name', 'N/A') if class_info else '-'} em {existing.get('date')}"
            ),
            old_value={"content": previous_content, "version": current_version},
            new_value={"content": new_content, "version": new_version},
            school_id=existing.get("school_id"),
            extra_data=extra,
        )
        return updated

    @router.post("/{entry_id}/publish")
    async def publish_content_entry(
        entry_id: str, request: Request, payload: ContentEntryPublishRequest
    ):
        current_user = await AuthMiddleware.require_roles(WRITE_ROLES)(request)
        existing = await db.content_entries.find_one({"id": entry_id, "deleted": False}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Conteúdo não encontrado")
        await _authorize_dvd_record(
            db, current_user, request, existing,
            action=DiaryAction.CONTENT, allow_management_override=True,
        )
        if existing.get("status") != "draft":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "PUBLISH_REQUIRES_DRAFT",
                    "message": f"Só é possível publicar conteúdo em draft. Status atual: {existing.get('status')}",
                    "current_status": existing.get("status"),
                },
            )
        if not (existing.get("content") or "").strip():
            raise HTTPException(
                status_code=422,
                detail={"code": "EMPTY_CONTENT", "message": "Conteúdo vazio não pode ser publicado."},
            )
        current_version = existing.get("version") or 1
        if payload.expected_version is not None and payload.expected_version != current_version:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CONTENT_VERSION_CONFLICT",
                    "message": "Versão diferente da esperada — recarregue.",
                    "expected_version": payload.expected_version,
                    "current_version": current_version,
                },
            )

        snapshot_hash = compute_snapshot_hash(existing)
        new_version = current_version + 1
        now = datetime.now(timezone.utc).isoformat()
        await db.content_entries.update_one(
            {"id": entry_id},
            {"$set": {
                "status": "published",
                "published_at": now,
                "published_by": current_user["id"],
                "published_snapshot_hash": snapshot_hash,
                "published_version": new_version,
                "version": new_version,
                "updated_at": now,
                "updated_by": current_user["id"],
            }},
        )
        updated = await db.content_entries.find_one({"id": entry_id}, {"_id": 0})

        class_info = await _resolve_class_info(db, existing["class_id"])
        extra = build_content_audit_extra(
            entry=updated, change_kind="content_published",
            expected_version=payload.expected_version, final_version=new_version,
            previous_content=None, new_content=None,
            class_info=class_info,
        )
        extra["published_snapshot_hash"] = snapshot_hash
        await audit_service.log(
            action="update", collection="content_entries",
            user=current_user, request=request, document_id=entry_id,
            description=(
                f"Publicou conteúdo da turma {class_info.get('name', 'N/A') if class_info else '-'} "
                f"em {existing.get('date')} (hash {snapshot_hash[:8]}...)"
            ),
            old_value={"status": "draft", "version": current_version},
            new_value={"status": "published", "version": new_version, "snapshot_hash": snapshot_hash},
            school_id=existing.get("school_id"),
            extra_data=extra,
        )
        return updated

    @router.post("/{entry_id}/correct")
    async def correct_content_entry(
        entry_id: str, request: Request, payload: ContentEntryCorrectRequest
    ):
        current_user = await AuthMiddleware.require_roles(WRITE_ROLES)(request)
        existing = await db.content_entries.find_one({"id": entry_id, "deleted": False}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Conteúdo não encontrado")
        await _authorize_dvd_record(
            db, current_user, request, existing,
            action=DiaryAction.CONTENT, allow_management_override=True,
        )

        if existing.get("status") not in ("published", "corrected"):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CORRECT_REQUIRES_PUBLISHED",
                    "message": (
                        "Correção só é permitida em conteúdo publicado ou já corrigido. "
                        "Em draft, use PUT normal."
                    ),
                    "current_status": existing.get("status"),
                },
            )

        if (
            payload.content is None
            and payload.methodology is None
            and payload.observations is None
            and payload.number_of_classes is None
        ):
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "EMPTY_CORRECTION",
                    "message": (
                        "Informe pelo menos um campo a corrigir "
                        "(content, methodology, observations ou number_of_classes)."
                    ),
                },
            )

        current_version = existing.get("version") or 1
        if payload.expected_version is not None and payload.expected_version != current_version:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CONTENT_VERSION_CONFLICT",
                    "message": "Versão diferente — recarregue antes de corrigir.",
                    "expected_version": payload.expected_version,
                    "current_version": current_version,
                },
            )

        new_version = current_version + 1
        previous_content = existing.get("content")
        new_content = previous_content
        set_fields = {
            "status": "corrected",
            "corrected_from_version": current_version,
            "version": new_version,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": current_user["id"],
        }
        if payload.content is not None:
            set_fields["content"] = payload.content
            new_content = payload.content
        if payload.methodology is not None:
            set_fields["methodology"] = payload.methodology
        if payload.observations is not None:
            set_fields["observations"] = payload.observations
        if payload.number_of_classes is not None:
            set_fields["number_of_classes"] = payload.number_of_classes

        await db.content_entries.update_one({"id": entry_id}, {"$set": set_fields})
        updated = await db.content_entries.find_one({"id": entry_id}, {"_id": 0})

        class_info = await _resolve_class_info(db, existing["class_id"])
        extra = build_content_audit_extra(
            entry=updated, change_kind="content_corrected",
            expected_version=payload.expected_version, final_version=new_version,
            previous_content=previous_content, new_content=new_content,
            change_note=payload.change_note,
            class_info=class_info,
        )
        extra["corrected_from_version"] = current_version
        await audit_service.log(
            action="update", collection="content_entries",
            user=current_user, request=request, document_id=entry_id,
            description=(
                f"Corrigiu conteúdo (v{current_version} → v{new_version}) da turma "
                f"{class_info.get('name', 'N/A') if class_info else '-'} em {existing.get('date')}: "
                f"{payload.change_note[:80]}"
            ),
            old_value={"content": previous_content, "version": current_version, "status": existing.get("status")},
            new_value={"content": new_content, "version": new_version, "status": "corrected"},
            school_id=existing.get("school_id"),
            extra_data=extra,
        )
        return updated

    @router.delete("/{entry_id}")
    async def soft_delete_content_entry(
        entry_id: str, request: Request, payload: ContentEntryDeleteRequest
    ):
        current_user = await AuthMiddleware.require_roles(WRITE_ROLES)(request)
        existing = await db.content_entries.find_one({"id": entry_id, "deleted": False}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Conteúdo não encontrado ou já excluído")
        await _authorize_dvd_record(
            db, current_user, request, existing,
            action=DiaryAction.CONTENT, allow_management_override=True,
        )

        now = datetime.now(timezone.utc).isoformat()
        new_version = (existing.get("version") or 1) + 1
        await db.content_entries.update_one(
            {"id": entry_id},
            {"$set": {
                "deleted": True,
                "deleted_at": now,
                "deleted_by": current_user["id"],
                "delete_note": payload.change_note[:500],
                "version": new_version,
                "updated_at": now,
                "updated_by": current_user["id"],
            }},
        )

        class_info = await _resolve_class_info(db, existing["class_id"])
        extra = build_content_audit_extra(
            entry=existing, change_kind="content_deleted",
            expected_version=None, final_version=new_version,
            previous_content=existing.get("content"),
            new_content=None,
            change_note=payload.change_note,
            class_info=class_info,
        )
        await audit_service.log(
            action="delete", collection="content_entries",
            user=current_user, request=request, document_id=entry_id,
            description=(
                f"Excluiu (soft) conteúdo da turma "
                f"{class_info.get('name', 'N/A') if class_info else '-'} em {existing.get('date')}: "
                f"{payload.change_note[:80]}"
            ),
            old_value={"content": existing.get("content"), "deleted": False},
            new_value={"content": existing.get("content"), "deleted": True},
            school_id=existing.get("school_id"),
            extra_data=extra,
        )
        return {"ok": True, "id": entry_id, "deleted": True, "version": new_version}

    return router
