"""
Router de Conteúdo Pedagógico (Diário) — SIGESC.

Rodada 2 (Mai/2026) — Fase 2: split do domínio "conteúdo" em coleção
própria (`content_entries`), independente de `attendance`.

Princípios arquiteturais (referência: diretriz oficial Mai/2026):
  - 1 entry por (turma, data, componente, aula_numero, professor).
  - Vínculo SEMÂNTICO — sem `attendance_id`. Frequência e conteúdo
    podem existir independentemente; consolidação acontece via JOIN
    semântico em relatórios e PDFs.
  - Multi-autoria desde o nascimento — `teacher_id` é parte da chave.
  - Optimistic locking (mesmo padrão da Fase 1 — `expected_version`).
  - Soft delete (`deleted=true`) para preservar histórico.
  - Toda escrita registra em `audit_logs` (canônico) com texto anterior.
  - Status nasce como `draft`; transições (`published`, `corrected`)
    serão tratadas na Rodada 3.

Endpoints:
  POST   /content-entries           cria um entry
  GET    /content-entries           lista por class_id+date (e opcionais)
  GET    /content-entries/{id}      detalhe
  PUT    /content-entries/{id}      atualiza (com expected_version)
  DELETE /content-entries/{id}      soft delete
"""
from datetime import datetime, timezone
from typing import List, Optional
import logging
import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth_middleware import AuthMiddleware
from services.content_audit import build_content_audit_extra, compute_snapshot_hash

logger = logging.getLogger(__name__)

# Roles que podem CRIAR/EDITAR conteúdo. Coordenação/secretaria também
# para correções autorizadas (registradas no audit log).
WRITE_ROLES = [
    'professor', 'coordenador', 'admin', 'admin_teste', 'super_admin',
    'secretario', 'gerente', 'auxiliar_secretaria',
]
VIEW_ROLES = WRITE_ROLES + ['diretor', 'ass_social_2', 'semed3']


# ============================ MODELS ========================================

class ContentEntryCreate(BaseModel):
    class_id: str
    date: str  # ISO YYYY-MM-DD
    course_id: Optional[str] = None
    component_id: Optional[str] = None
    aula_numero: Optional[int] = None
    teacher_id: Optional[str] = None  # default: usuário logado
    content: str = Field(..., min_length=1, max_length=20000)
    methodology: Optional[str] = Field(default=None, max_length=5000)
    observations: Optional[str] = Field(default=None, max_length=5000)


class ContentEntryUpdate(BaseModel):
    content: Optional[str] = Field(default=None, min_length=1, max_length=20000)
    methodology: Optional[str] = Field(default=None, max_length=5000)
    observations: Optional[str] = Field(default=None, max_length=5000)
    # Optimistic locking (mesmo padrão da Fase 1).
    expected_version: Optional[int] = None
    force_overwrite: bool = False
    change_note: Optional[str] = None


class ContentEntryDeleteRequest(BaseModel):
    # Razão obrigatória para soft-delete — preserva governance.
    change_note: str = Field(..., min_length=1, max_length=500)


class ContentEntryPublishRequest(BaseModel):
    # Optimistic locking opcional: garante que estamos publicando a
    # versão que o frontend viu.
    expected_version: Optional[int] = None


class ContentEntryCorrectRequest(BaseModel):
    # change_note OBRIGATÓRIO — auditoria institucional.
    change_note: str = Field(..., min_length=1, max_length=500)
    expected_version: Optional[int] = None
    # Campos a corrigir (qualquer combinação). Pelo menos um deve vir.
    content: Optional[str] = Field(default=None, min_length=1, max_length=20000)
    methodology: Optional[str] = Field(default=None, max_length=5000)
    observations: Optional[str] = Field(default=None, max_length=5000)


# ============================ HELPERS =======================================

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
    """Remove campos internos do payload de retorno (sem _id)."""
    if entry is None:
        return None
    e = dict(entry)
    e.pop("_id", None)
    return e


# ============================ ROUTER FACTORY ================================

def setup_content_entries_router(db, audit_service, sandbox_db=None):
    router = APIRouter(prefix="/content-entries", tags=["Diário - Conteúdo"])

    # ---------------- CREATE ----------------
    @router.post("")
    async def create_content_entry(entry: ContentEntryCreate, request: Request):
        current_user = await AuthMiddleware.require_roles(WRITE_ROLES)(request)
        teacher_id = entry.teacher_id or current_user["id"]
        teacher_name = await _resolve_teacher_name(db, teacher_id) or current_user.get("name")
        class_info = await _resolve_class_info(db, entry.class_id)
        if not class_info:
            raise HTTPException(status_code=404, detail="Turma não encontrada")

        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "id": str(uuid.uuid4()),
            "class_id": entry.class_id,
            "course_id": entry.course_id,
            "component_id": entry.component_id,
            "aula_numero": entry.aula_numero,
            "date": entry.date,
            "teacher_id": teacher_id,
            "teacher_name": teacher_name,
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
            "school_id": class_info.get("school_id"),
        }
        try:
            await db.content_entries.insert_one(doc)
        except Exception as ex:  # noqa: BLE001
            # Provável violação do UNIQUE composto
            if "duplicate key" in str(ex).lower():
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "CONTENT_ENTRY_DUPLICATE",
                        "message": "Já existe entry para esta turma/data/componente/aula/professor.",
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
            school_id=class_info.get("school_id"),
            extra_data=extra,
        )
        return _public(await db.content_entries.find_one({"id": doc["id"]}, {"_id": 0}))

    # ---------------- LIST ----------------
    @router.get("")
    async def list_content_entries(
        request: Request,
        class_id: Optional[str] = Query(None),
        date: Optional[str] = Query(None),
        teacher_id: Optional[str] = Query(None),
        component_id: Optional[str] = Query(None),
        include_deleted: bool = Query(False),
    ):
        await AuthMiddleware.require_roles(VIEW_ROLES)(request)
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
        cursor = db.content_entries.find(q, {"_id": 0}).sort([("date", -1), ("aula_numero", 1)])
        items = await cursor.to_list(2000)
        return {"items": items, "total": len(items)}

    # ---------------- GET BY ID ----------------
    @router.get("/{entry_id}")
    async def get_content_entry(entry_id: str, request: Request):
        await AuthMiddleware.require_roles(VIEW_ROLES)(request)
        e = await db.content_entries.find_one({"id": entry_id}, {"_id": 0})
        if not e:
            raise HTTPException(status_code=404, detail="Conteúdo não encontrado")
        return e

    # ---------------- UPDATE ----------------
    @router.put("/{entry_id}")
    async def update_content_entry(entry_id: str, patch: ContentEntryUpdate, request: Request):
        current_user = await AuthMiddleware.require_roles(WRITE_ROLES)(request)
        existing = await db.content_entries.find_one({"id": entry_id, "deleted": False}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Conteúdo não encontrado")

        # Rodada 3: PUT só em draft. Para published/corrected, exige /correct.
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

        # ============= OPTIMISTIC LOCKING (mesmo padrão Fase 1) =============
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
                        "last_modified_at": existing.get("updated_at"),
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
        # =====================================================================

        # Monta update
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

    # ---------------- PUBLISH (Rodada 3) ----------------
    @router.post("/{entry_id}/publish")
    async def publish_content_entry(
        entry_id: str, request: Request, payload: ContentEntryPublishRequest
    ):
        """Transita draft → published. Computa snapshot_hash imutável."""
        current_user = await AuthMiddleware.require_roles(WRITE_ROLES)(request)
        existing = await db.content_entries.find_one({"id": entry_id, "deleted": False}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Conteúdo não encontrado")
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
            previous_content=None, new_content=None,  # Sem mudança de texto no publish
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

    # ---------------- CORRECT (Rodada 3) ----------------
    @router.post("/{entry_id}/correct")
    async def correct_content_entry(
        entry_id: str, request: Request, payload: ContentEntryCorrectRequest
    ):
        """Correção institucional de conteúdo já publicado.

        Permitida apenas em published ou corrected. Preserva
        `corrected_from_version` apontando para a versão imediatamente
        anterior — permite reconstruir a timeline completa.
        """
        current_user = await AuthMiddleware.require_roles(WRITE_ROLES)(request)
        existing = await db.content_entries.find_one({"id": entry_id, "deleted": False}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Conteúdo não encontrado")

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

        # Pelo menos um campo de conteúdo deve vir
        if payload.content is None and payload.methodology is None and payload.observations is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "EMPTY_CORRECTION",
                    "message": "Informe pelo menos um campo a corrigir (content, methodology ou observations).",
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

    # ---------------- SOFT DELETE ----------------
    @router.delete("/{entry_id}")
    async def soft_delete_content_entry(
        entry_id: str, request: Request, payload: ContentEntryDeleteRequest
    ):
        current_user = await AuthMiddleware.require_roles(WRITE_ROLES)(request)
        existing = await db.content_entries.find_one({"id": entry_id, "deleted": False}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Conteúdo não encontrado ou já excluído")

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
