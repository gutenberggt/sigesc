"""
Router de Alocação Institucional Temporal — `teacher_class_assignments`.

Rodada 4 (Mai/2026) — Fase 4a: motor temporal do diário.

Princípios arquiteturais (referência: diretriz oficial Mai/2026):
  - Coleção SEPARADA de `class_schedules`. Schedules = grade da turma;
    assignments = responsabilidade institucional de cada slot.
  - Vínculo é TEMPORAL — `valid_from` obrigatório, `valid_until` opcional
    (null = vigente).
  - Multi-slot: cada assignment carrega array `weekly_slots[]` com
    (weekday, aula_numero, start_time, end_time). Suporta aulas
    geminadas, professor compartilhando vários slots, co-docência etc.
  - Soft delete + auditoria via `audit_logs`.
  - `source: manual|import|seed` — rastreabilidade da origem (migração).
  - NÃO bloqueia conflito na criação — fornece endpoint
    `/teacher-class-assignments/conflicts` para inspeção explícita.

Endpoints:
  POST   /teacher-class-assignments
  GET    /teacher-class-assignments               (com filtros)
  GET    /teacher-class-assignments/{id}
  PUT    /teacher-class-assignments/{id}
  DELETE /teacher-class-assignments/{id}          (soft)
  GET    /teacher-class-assignments/conflicts     (detector de choque de horário)
"""
from datetime import datetime, timezone
from typing import List, Optional
import logging
import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from auth_middleware import AuthMiddleware

logger = logging.getLogger(__name__)

WRITE_ROLES = ['admin', 'admin_teste', 'super_admin', 'secretario', 'gerente', 'semed3', 'coordenador']
VIEW_ROLES = WRITE_ROLES + ['professor', 'diretor', 'ass_social_2', 'auxiliar_secretaria']

ALLOWED_SHIFTS = {"morning", "afternoon", "evening", "full", "integral"}
ALLOWED_SOURCES = {"manual", "import", "seed"}


# ============================ MODELS ========================================

class WeeklySlot(BaseModel):
    weekday: int = Field(..., ge=1, le=7, description="1=Seg ... 7=Dom")
    aula_numero: int = Field(..., ge=1, le=12)
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")

    @field_validator("end_time")
    @classmethod
    def _end_after_start(cls, v, info):
        st = info.data.get("start_time")
        if st and v <= st:
            raise ValueError("end_time deve ser maior que start_time")
        return v


class AssignmentCreate(BaseModel):
    teacher_id: str
    class_id: str
    component_id: Optional[str] = None
    shift: Optional[str] = None  # se omitido, valida contra ALLOWED_SHIFTS abaixo
    weekly_slots: List[WeeklySlot] = Field(..., min_length=1, max_length=20)
    valid_from: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    valid_until: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    is_substitute: bool = False
    source: str = "manual"

    @field_validator("shift")
    @classmethod
    def _shift_valid(cls, v):
        if v is not None and v not in ALLOWED_SHIFTS:
            raise ValueError(f"shift deve ser um de {sorted(ALLOWED_SHIFTS)}")
        return v

    @field_validator("source")
    @classmethod
    def _source_valid(cls, v):
        if v not in ALLOWED_SOURCES:
            raise ValueError(f"source deve ser um de {sorted(ALLOWED_SOURCES)}")
        return v

    @field_validator("valid_until")
    @classmethod
    def _until_after_from(cls, v, info):
        if v is None:
            return v
        vf = info.data.get("valid_from")
        if vf and v < vf:
            raise ValueError("valid_until deve ser >= valid_from")
        return v


class AssignmentUpdate(BaseModel):
    component_id: Optional[str] = None
    shift: Optional[str] = None
    weekly_slots: Optional[List[WeeklySlot]] = Field(default=None, min_length=1, max_length=20)
    valid_until: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    is_substitute: Optional[bool] = None


class AssignmentDeleteRequest(BaseModel):
    change_note: str = Field(..., min_length=1, max_length=500)


# ============================ HELPERS =======================================

async def _resolve_teacher(db, teacher_id: str) -> Optional[dict]:
    return await db.users.find_one(
        {"id": teacher_id, "role": {"$in": ["professor", "coordenador"]}},
        {"_id": 0, "id": 1, "full_name": 1, "name": 1, "email": 1, "school_id": 1},
    ) or await db.users.find_one(
        {"id": teacher_id}, {"_id": 0, "id": 1, "full_name": 1, "name": 1, "email": 1, "school_id": 1}
    )


async def _resolve_class(db, class_id: str) -> Optional[dict]:
    return await db.classes.find_one(
        {"id": class_id}, {"_id": 0, "id": 1, "name": 1, "school_id": 1}
    )


def _public(doc):
    if doc is None:
        return None
    d = dict(doc)
    d.pop("_id", None)
    return d


def _slots_overlap(a: dict, b: dict) -> bool:
    """Dois slots colidem se mesmo weekday + mesma aula_numero OU
    intervalos de horário se interceptam no mesmo weekday."""
    if a["weekday"] != b["weekday"]:
        return False
    if a["aula_numero"] == b["aula_numero"]:
        return True
    # Sobreposição temporal: max(start) < min(end)
    return max(a["start_time"], b["start_time"]) < min(a["end_time"], b["end_time"])


def _periods_overlap(af: str, au: Optional[str], bf: str, bu: Optional[str]) -> bool:
    """Períodos de validade se sobrepõem? null em valid_until = +infinito."""
    a_end = au or "9999-12-31"
    b_end = bu or "9999-12-31"
    return max(af, bf) <= min(a_end, b_end)


# ============================ ROUTER FACTORY ================================

def setup_teacher_class_assignments_router(db, audit_service, sandbox_db=None):
    router = APIRouter(prefix="/teacher-class-assignments", tags=["Alocação Institucional"])

    # ---------------- CREATE ----------------
    @router.post("")
    async def create_assignment(payload: AssignmentCreate, request: Request):
        current_user = await AuthMiddleware.require_roles(WRITE_ROLES)(request)
        teacher = await _resolve_teacher(db, payload.teacher_id)
        if not teacher:
            raise HTTPException(status_code=404, detail="Professor não encontrado")
        klass = await _resolve_class(db, payload.class_id)
        if not klass:
            raise HTTPException(status_code=404, detail="Turma não encontrada")

        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "id": str(uuid.uuid4()),
            "teacher_id": payload.teacher_id,
            "teacher_name": teacher.get("full_name") or teacher.get("name"),
            "class_id": payload.class_id,
            "class_name": klass.get("name"),
            "school_id": klass.get("school_id"),
            "component_id": payload.component_id,
            "shift": payload.shift,
            "weekly_slots": [s.model_dump() for s in payload.weekly_slots],
            "valid_from": payload.valid_from,
            "valid_until": payload.valid_until,
            "is_substitute": payload.is_substitute,
            "source": payload.source,
            "deleted": False,
            "created_at": now,
            "created_by": current_user["id"],
            "updated_at": now,
            "updated_by": current_user["id"],
        }
        await db.teacher_class_assignments.insert_one(doc)
        await audit_service.log(
            action="create", collection="teacher_class_assignments",
            user=current_user, request=request, document_id=doc["id"],
            description=(
                f"Alocou {doc['teacher_name']} em {doc['class_name']} "
                f"(comp={payload.component_id}, valido_de {payload.valid_from})"
            ),
            school_id=doc["school_id"],
            extra_data={
                "entity_type": "teacher_class_assignment",
                "teacher_id": payload.teacher_id,
                "class_id": payload.class_id,
                "component_id": payload.component_id,
                "weekly_slots_count": len(payload.weekly_slots),
                "valid_from": payload.valid_from,
                "valid_until": payload.valid_until,
                "is_substitute": payload.is_substitute,
                "source": payload.source,
                "change_kind": "assignment_created",
            },
        )
        return _public(doc)

    # ---------------- LIST ----------------
    @router.get("")
    async def list_assignments(
        request: Request,
        class_id: Optional[str] = Query(None),
        teacher_id: Optional[str] = Query(None),
        component_id: Optional[str] = Query(None),
        school_id: Optional[str] = Query(None),
        active_on: Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
        include_deleted: bool = Query(False),
        is_substitute: Optional[bool] = Query(None),
    ):
        await AuthMiddleware.require_roles(VIEW_ROLES)(request)
        q: dict = {}
        if not include_deleted:
            q["deleted"] = False
        if class_id:
            q["class_id"] = class_id
        if teacher_id:
            q["teacher_id"] = teacher_id
        if component_id:
            q["component_id"] = component_id
        if school_id:
            q["school_id"] = school_id
        if is_substitute is not None:
            q["is_substitute"] = is_substitute
        if active_on:
            q["valid_from"] = {"$lte": active_on}
            q["$or"] = [{"valid_until": None}, {"valid_until": {"$gte": active_on}}]
        cursor = db.teacher_class_assignments.find(q, {"_id": 0}).sort([("class_id", 1), ("valid_from", 1)])
        items = await cursor.to_list(5000)
        return {"items": items, "total": len(items)}

    # ---------------- CONFLICTS (detector de choque) ----------------
    @router.get("/conflicts")
    async def list_conflicts(
        request: Request,
        teacher_id: str = Query(...),
        on_date: Optional[str] = Query(None),
    ):
        """Retorna pares de assignments do MESMO professor que sobrepõem em
        período temporal E têm slots conflitantes (mesmo weekday/aula
        ou janelas de horário se interceptam).

        Não filtra por turma de propósito — detectar choque institucional
        é justamente cruzar turmas distintas. Filtro `on_date` restringe
        ao período vigente naquela data."""
        await AuthMiddleware.require_roles(VIEW_ROLES)(request)
        q = {"teacher_id": teacher_id, "deleted": False}
        if on_date:
            q["valid_from"] = {"$lte": on_date}
            q["$or"] = [{"valid_until": None}, {"valid_until": {"$gte": on_date}}]
        items = await db.teacher_class_assignments.find(q, {"_id": 0}).to_list(2000)

        conflicts = []
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                if not _periods_overlap(
                    a["valid_from"], a.get("valid_until"),
                    b["valid_from"], b.get("valid_until"),
                ):
                    continue
                for sa in a.get("weekly_slots", []):
                    for sb in b.get("weekly_slots", []):
                        if _slots_overlap(sa, sb):
                            conflicts.append({
                                "assignment_a_id": a["id"],
                                "assignment_b_id": b["id"],
                                "class_a": a.get("class_name"),
                                "class_b": b.get("class_name"),
                                "weekday": sa["weekday"],
                                "slot_a": {"aula": sa["aula_numero"], "start": sa["start_time"], "end": sa["end_time"]},
                                "slot_b": {"aula": sb["aula_numero"], "start": sb["start_time"], "end": sb["end_time"]},
                                "conflict_kind": ("same_aula" if sa["aula_numero"] == sb["aula_numero"]
                                                  else "time_overlap"),
                            })
        return {"teacher_id": teacher_id, "on_date": on_date, "conflicts": conflicts, "total": len(conflicts)}

    # ---------------- INTEGRITY REPORT (Fase 6 — Mai/2026) ----------------
    @router.get("/integrity-report")
    async def integrity_report(
        request: Request,
        school_id: Optional[str] = Query(None),
        class_id: Optional[str] = Query(None),
        reference_date: Optional[str] = Query(None, description="YYYY-MM-DD; default: hoje"),
        academic_year: Optional[int] = Query(None),
    ):
        """Relatório de integridade da grade horária.

        Sem grade correta, completude/pendências/PDFs ficam falsos. Este
        endpoint detecta 8 classes de problemas (gap temporal, overlap,
        expired_no_successor, orphan_teacher, double_booking, classes
        sem assignment, validade invertida, slots duplicados).

        Roles autorizados: WRITE_ROLES (admins, coordenação, direção,
        secretaria, SEMED).
        """
        await AuthMiddleware.require_roles(WRITE_ROLES)(request)
        from services.grade_integrity_service import compute_integrity_report
        return await compute_integrity_report(
            db,
            school_id=school_id,
            class_id=class_id,
            reference_date=reference_date,
            academic_year=academic_year,
        )

    # ---------------- GET BY ID ----------------
    @router.get("/{assignment_id}")
    async def get_assignment(assignment_id: str, request: Request):
        await AuthMiddleware.require_roles(VIEW_ROLES)(request)
        doc = await db.teacher_class_assignments.find_one({"id": assignment_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Alocação não encontrada")
        return doc

    # ---------------- UPDATE ----------------
    @router.put("/{assignment_id}")
    async def update_assignment(assignment_id: str, patch: AssignmentUpdate, request: Request):
        current_user = await AuthMiddleware.require_roles(WRITE_ROLES)(request)
        existing = await db.teacher_class_assignments.find_one(
            {"id": assignment_id, "deleted": False}, {"_id": 0}
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Alocação não encontrada")

        set_fields: dict = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": current_user["id"],
        }
        if patch.component_id is not None:
            set_fields["component_id"] = patch.component_id
        if patch.shift is not None:
            set_fields["shift"] = patch.shift
        if patch.weekly_slots is not None:
            set_fields["weekly_slots"] = [s.model_dump() for s in patch.weekly_slots]
        if patch.valid_until is not None:
            if patch.valid_until < existing["valid_from"]:
                raise HTTPException(
                    status_code=422,
                    detail={"code": "INVALID_PERIOD", "message": "valid_until deve ser >= valid_from."},
                )
            set_fields["valid_until"] = patch.valid_until
        if patch.is_substitute is not None:
            set_fields["is_substitute"] = patch.is_substitute

        await db.teacher_class_assignments.update_one({"id": assignment_id}, {"$set": set_fields})
        updated = await db.teacher_class_assignments.find_one({"id": assignment_id}, {"_id": 0})
        await audit_service.log(
            action="update", collection="teacher_class_assignments",
            user=current_user, request=request, document_id=assignment_id,
            description=f"Atualizou alocação {assignment_id}",
            school_id=existing.get("school_id"),
            old_value={k: existing.get(k) for k in set_fields if k != "updated_at" and k != "updated_by"},
            new_value={k: set_fields[k] for k in set_fields if k != "updated_at" and k != "updated_by"},
            extra_data={
                "entity_type": "teacher_class_assignment",
                "change_kind": "assignment_updated",
                "teacher_id": existing["teacher_id"],
                "class_id": existing["class_id"],
            },
        )
        return updated

    # ---------------- SOFT DELETE ----------------
    @router.delete("/{assignment_id}")
    async def soft_delete_assignment(
        assignment_id: str, request: Request, payload: AssignmentDeleteRequest
    ):
        current_user = await AuthMiddleware.require_roles(WRITE_ROLES)(request)
        existing = await db.teacher_class_assignments.find_one(
            {"id": assignment_id, "deleted": False}, {"_id": 0}
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Alocação não encontrada ou já excluída")

        now = datetime.now(timezone.utc).isoformat()
        await db.teacher_class_assignments.update_one(
            {"id": assignment_id},
            {"$set": {
                "deleted": True,
                "deleted_at": now,
                "deleted_by": current_user["id"],
                "delete_note": payload.change_note[:500],
                "updated_at": now,
                "updated_by": current_user["id"],
            }},
        )
        await audit_service.log(
            action="delete", collection="teacher_class_assignments",
            user=current_user, request=request, document_id=assignment_id,
            description=f"Excluiu alocação {assignment_id}: {payload.change_note[:80]}",
            school_id=existing.get("school_id"),
            extra_data={
                "entity_type": "teacher_class_assignment",
                "change_kind": "assignment_deleted",
                "teacher_id": existing["teacher_id"],
                "class_id": existing["class_id"],
                "change_note": payload.change_note[:500],
            },
        )
        return {"ok": True, "id": assignment_id, "deleted": True}

    return router
