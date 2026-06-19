"""
Router de Transferência Institucional de Turmas (Re-homing — Opção A).

Move turmas inteiras de uma escola (em encerramento) para outra escola da
MESMA mantenedora, alterando apenas `school_id` e PRESERVANDO o `class_id`
em toda a árvore pedagógica (motor canônico, idempotente).

Segurança (super_admin only):
  - Re-autenticação por senha (verify_password) imediatamente antes de executar.
  - Justificativa obrigatória.
  - Frase de confirmação textual obrigatória.
  - Dry Run obrigatório (gera token) + idempotência por `dry_run_token`.

Fase 1 = Backend (dry-run, execute, auditoria, school_history, academic_events).
Rollback (Fase 2) é tratado separadamente.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import List, Optional
from bson import ObjectId

from auth_middleware import AuthMiddleware
from auth_utils import verify_password
from tenant_scope import is_super_admin

logger = logging.getLogger(__name__)

# Motor canônico — coleções denormalizadas que carregam `school_id`.
# Âncora por turma (class_id estável).
CLASS_ANCHORED = [
    "students", "enrollments", "attendance", "grades", "content_entries",
    "student_dependencies", "teacher_class_assignments",
]
# Âncora por aluno (student_id estável) — AEE e Bolsa Família.
STUDENT_ANCHORED = [
    "planos_aee", "atendimentos_aee", "evolucoes_aee", "articulacoes_aee",
    "bolsa_familia_tracking",
]

CONFIRMATION_PHRASE = "CONFIRMO A TRANSFERÊNCIA INSTITUCIONAL"
DRY_RUN_TTL_HOURS = 24
MIN_REASON_LEN = 10


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DryRunRequest(BaseModel):
    origin_school_id: str
    destination_school_id: str
    class_ids: List[str] = Field(..., min_length=1)
    pre_matricula_action: str = "transfer"  # transfer | keep | close


class ExecuteRequest(BaseModel):
    dry_run_token: str
    password: str
    reason: str = Field(..., min_length=MIN_REASON_LEN)
    confirmation_text: str


def setup_router(db, audit_service=None):
    router = APIRouter(prefix="/admin/school-transfer", tags=["Transferência Institucional"])

    async def _require_super_admin(request: Request) -> dict:
        user = await AuthMiddleware.get_current_user(request)
        if not is_super_admin(user):
            raise HTTPException(status_code=403, detail="Apenas Super Administrador pode executar transferência institucional.")
        return user

    async def _collect_student_ids(class_ids: List[str]) -> List[str]:
        # Apenas alunos cuja turma de origem (home class) está sendo movida.
        # AEE/Bolsa Família/dependências por aluno só seguem quem realmente
        # muda de escola — não alunos com mera matrícula avulsa na turma.
        ids = set()
        async for s in db.students.find({"class_id": {"$in": class_ids}}, {"_id": 0, "id": 1}):
            if s.get("id"):
                ids.add(s["id"])
        return list(ids)

    async def _build_validations(origin, destination, class_ids, classes_docs) -> List[dict]:
        v: List[dict] = []

        def add(code, label, ok, blocking, detail=None):
            v.append({"code": code, "label": label, "ok": bool(ok), "blocking": bool(blocking), "detail": detail})

        add("ORIGIN_EXISTS", "Escola de origem existe", origin is not None, True)
        add("DESTINATION_EXISTS", "Escola de destino existe", destination is not None, True)

        if origin and destination:
            add("SAME_MANTENEDORA", "Origem e destino na mesma mantenedora",
                origin.get("mantenedora_id") and origin.get("mantenedora_id") == destination.get("mantenedora_id"),
                True,
                detail={"origin": origin.get("mantenedora_id"), "destination": destination.get("mantenedora_id")})
            add("DESTINATION_ACTIVE", "Escola de destino ativa",
                destination.get("status") == "active", True,
                detail={"status": destination.get("status")})
            add("NOT_SAME_SCHOOL", "Origem e destino são escolas diferentes",
                origin.get("id") != destination.get("id"), True)

        found_ids = {c["id"] for c in classes_docs}
        missing = [cid for cid in class_ids if cid not in found_ids]
        add("CLASSES_BELONG_TO_ORIGIN", "Todas as turmas pertencem à origem",
            len(missing) == 0, True,
            detail={"missing_or_wrong_school": missing})

        in_progress = [c["id"] for c in classes_docs if c.get("transfer_in_progress")]
        add("NO_TRANSFER_IN_PROGRESS", "Nenhuma turma em outra transferência em andamento",
            len(in_progress) == 0, True, detail={"locked": in_progress})

        # Calendário do destino aberto para os anos letivos das turmas (bloqueante)
        years = sorted({c.get("academic_year") for c in classes_docs if c.get("academic_year")})
        missing_cal = []
        for y in years:
            cal = await db.calendario_letivo.find_one(
                {"ano_letivo": y, "school_id": {"$in": [destination.get("id") if destination else None, None]}},
                {"_id": 0, "id": 1},
            )
            if not cal:
                missing_cal.append(y)
        add("DESTINATION_CALENDAR_OPEN", "Calendário letivo do destino configurado",
            len(missing_cal) == 0, True, detail={"missing_years": missing_cal})

        # Compatibilidade de etapa (não-bloqueante: dados de oferta podem estar vazios em legado)
        niveis = (destination or {}).get("niveis_ensino_oferecidos") or []
        incompatible = []
        if niveis:
            niveis_set = {str(n).lower() for n in niveis}
            for c in classes_docs:
                lvl = str(c.get("education_level") or "").lower()
                if lvl and lvl not in niveis_set:
                    incompatible.append({"class_id": c["id"], "education_level": c.get("education_level")})
        add("STAGE_COMPATIBILITY", "Compatibilidade de etapa/oferta no destino",
            len(incompatible) == 0, False, detail={"incompatible": incompatible})

        return v

    async def _counts(class_ids: List[str], student_ids: List[str]) -> dict:
        counts = {"classes": len(class_ids)}
        for coll in CLASS_ANCHORED:
            counts[coll] = await db[coll].count_documents({"class_id": {"$in": class_ids}})
        for coll in STUDENT_ANCHORED:
            counts[coll] = await db[coll].count_documents({"student_id": {"$in": student_ids}}) if student_ids else 0
        return counts

    async def _teacher_pendencies(class_ids: List[str], classes_docs) -> List[dict]:
        teacher_ids = set()
        for c in classes_docs:
            for tid in (c.get("teacher_ids") or []):
                teacher_ids.add(tid)
        async for a in db.teacher_class_assignments.find(
            {"class_id": {"$in": class_ids}}, {"_id": 0, "staff_id": 1, "teacher_id": 1}
        ):
            tid = a.get("staff_id") or a.get("teacher_id")
            if tid:
                teacher_ids.add(tid)
        return [{"staff_id": t} for t in teacher_ids]

    # ----------------------------------------------------------------- DRY RUN
    @router.post("/dry-run")
    async def dry_run(payload: DryRunRequest, request: Request):
        user = await _require_super_admin(request)

        origin = await db.schools.find_one({"id": payload.origin_school_id}, {"_id": 0})
        destination = await db.schools.find_one({"id": payload.destination_school_id}, {"_id": 0})

        classes_docs = await db.classes.find(
            {"id": {"$in": payload.class_ids}, "school_id": payload.origin_school_id}, {"_id": 0}
        ).to_list(None)

        validations = await _build_validations(origin, destination, payload.class_ids, classes_docs)
        student_ids = await _collect_student_ids(payload.class_ids)
        counts = await _counts(payload.class_ids, student_ids)
        counts["students_distinct"] = len(student_ids)
        pendencies = await _teacher_pendencies(payload.class_ids, classes_docs)

        blocking_failures = [v for v in validations if v["blocking"] and not v["ok"]]
        warnings = [v for v in validations if not v["blocking"] and not v["ok"]]

        token = str(uuid.uuid4())
        now = _now_iso()
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=DRY_RUN_TTL_HOURS)).isoformat()

        audit_doc = {
            "id": str(uuid.uuid4()),
            "dry_run_token": token,
            "protocol": None,
            "status": "dry_run",
            "mantenedora_id": (origin or {}).get("mantenedora_id"),
            "origin_school_id": payload.origin_school_id,
            "destination_school_id": payload.destination_school_id,
            "class_ids": payload.class_ids,
            "pre_matricula_action": payload.pre_matricula_action,
            "counts": counts,
            "validations": validations,
            "teacher_pendencies": pendencies,
            "can_execute": len(blocking_failures) == 0,
            "operator": {"id": user.get("id"), "email": user.get("email")},
            "created_at": now,
            "expires_at": expires_at,
        }
        await db.school_transfer_audit.insert_one(audit_doc)
        audit_doc.pop("_id", None)

        return {
            "dry_run_token": token,
            "can_execute": len(blocking_failures) == 0,
            "blocking_failures": blocking_failures,
            "warnings": warnings,
            "validations": validations,
            "counts": counts,
            "teacher_pendencies": pendencies,
            "origin": {"id": (origin or {}).get("id"), "name": (origin or {}).get("name")} if origin else None,
            "destination": {"id": (destination or {}).get("id"), "name": (destination or {}).get("name")} if destination else None,
            "confirmation_phrase": CONFIRMATION_PHRASE,
            "expires_at": expires_at,
        }

    # ----------------------------------------------------------------- EXECUTE
    @router.post("/execute")
    async def execute(payload: ExecuteRequest, request: Request):
        user = await _require_super_admin(request)

        # 1) Frase de confirmação textual
        if (payload.confirmation_text or "").strip() != CONFIRMATION_PHRASE:
            raise HTTPException(status_code=400, detail=f"Frase de confirmação incorreta. Digite exatamente: {CONFIRMATION_PHRASE}")

        # 2) Re-autenticação por senha (nunca logada/armazenada)
        user_doc = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 1})
        if not user_doc or not verify_password(payload.password, user_doc.get("password_hash", "")):
            if audit_service:
                try:
                    await audit_service.log(
                        action="update", collection="school_transfer_audit", user=user, request=request,
                        description="Re-autenticação falhou na transferência institucional",
                    )
                except Exception:
                    pass
            raise HTTPException(status_code=401, detail="Senha incorreta. Re-autenticação falhou.")

        # 3) Idempotência: já executado com este token?
        existing = await db.school_transfer_audit.find_one(
            {"dry_run_token": payload.dry_run_token, "status": "executed"}, {"_id": 0}
        )
        if existing:
            return {"already_executed": True, "protocol": existing.get("protocol"), "audit": existing}

        # 4) Carrega o dry-run
        dry = await db.school_transfer_audit.find_one(
            {"dry_run_token": payload.dry_run_token, "status": "dry_run"}, {"_id": 0}
        )
        if not dry:
            raise HTTPException(status_code=404, detail="Dry Run não encontrado ou já consumido. Refaça a simulação.")
        try:
            if datetime.now(timezone.utc) > datetime.fromisoformat(dry["expires_at"]):
                await db.school_transfer_audit.update_one(
                    {"id": dry["id"]}, {"$set": {"status": "expired"}}
                )
                raise HTTPException(status_code=410, detail="Dry Run expirado. Refaça a simulação.")
        except HTTPException:
            raise
        except Exception:
            pass

        origin_id = dry["origin_school_id"]
        dest_id = dry["destination_school_id"]
        class_ids = dry["class_ids"]

        origin = await db.schools.find_one({"id": origin_id}, {"_id": 0})
        destination = await db.schools.find_one({"id": dest_id}, {"_id": 0})
        classes_docs = await db.classes.find(
            {"id": {"$in": class_ids}, "school_id": origin_id}, {"_id": 0}
        ).to_list(None)

        # 5) Re-valida bloqueantes
        validations = await _build_validations(origin, destination, class_ids, classes_docs)
        blocking_failures = [v for v in validations if v["blocking"] and not v["ok"]]
        if blocking_failures:
            raise HTTPException(status_code=409, detail={"code": "BLOCKING_VALIDATIONS", "failures": blocking_failures})

        student_ids = await _collect_student_ids(class_ids)
        now = _now_iso()
        tenant = (origin or {}).get("mantenedora_id")

        # 6) Snapshot pré-transferência (para rollback futuro — Fase 2).
        # Usa o `_id` do Mongo como chave universal (algumas coleções, ex.
        # bolsa_familia_tracking, não possuem campo `id`).
        snapshot = []
        for c in classes_docs:
            snapshot.append({"collection": "classes", "key": "id", "doc_key": c["id"],
                             "old_school_id": c.get("school_id"),
                             "old_school_history": c.get("school_history")})
        for coll in CLASS_ANCHORED:
            async for d in db[coll].find({"class_id": {"$in": class_ids}}, {"_id": 1, "school_id": 1}):
                snapshot.append({"collection": coll, "key": "_id", "doc_key": str(d["_id"]),
                                 "old_school_id": d.get("school_id")})
        if student_ids:
            for coll in STUDENT_ANCHORED:
                async for d in db[coll].find({"student_id": {"$in": student_ids}}, {"_id": 1, "school_id": 1}):
                    snapshot.append({"collection": coll, "key": "_id", "doc_key": str(d["_id"]),
                                     "old_school_id": d.get("school_id")})

        # 7) Lock
        await db.classes.update_many({"id": {"$in": class_ids}}, {"$set": {"transfer_in_progress": True}})

        modified = {}
        try:
            # 8) Re-homing por turma (classes + school_history)
            for c in classes_docs:
                history = c.get("school_history") or []
                if not history:
                    history = [{"school_id": origin_id, "start_date": c.get("created_at"), "end_date": now}]
                elif history[-1].get("end_date") is None:
                    history[-1]["end_date"] = now
                history.append({"school_id": dest_id, "start_date": now, "end_date": None})
                await db.classes.update_one(
                    {"id": c["id"]},
                    {"$set": {"school_id": dest_id, "school_history": history},
                     "$unset": {"transfer_in_progress": ""}},
                )
            modified["classes"] = len(classes_docs)

            # 9) Coleções âncora-turma
            for coll in CLASS_ANCHORED:
                res = await db[coll].update_many({"class_id": {"$in": class_ids}}, {"$set": {"school_id": dest_id}})
                modified[coll] = res.modified_count

            # 10) Coleções âncora-aluno
            if student_ids:
                for coll in STUDENT_ANCHORED:
                    res = await db[coll].update_many({"student_id": {"$in": student_ids}}, {"$set": {"school_id": dest_id}})
                    modified[coll] = res.modified_count

            # 11) academic_events institucional por turma (append-only)
            for c in classes_docs:
                await db.academic_events.insert_one({
                    "id": str(uuid.uuid4()),
                    "event_type": "transferencia_institucional",
                    "effective_date": now[:10],
                    "student_id": None,
                    "origin_class_id": c["id"],
                    "destination_class_id": c["id"],
                    "origin_school_id": origin_id,
                    "destination_school_id": dest_id,
                    "mantenedora_id": tenant,
                    "academic_year": c.get("academic_year"),
                    "rationale": payload.reason,
                    "approval_required": False,
                    "approval_status": "approved",
                    "approved_by_user_id": user.get("id"),
                    "approved_at": now,
                    "created_by_user_id": user.get("id"),
                    "created_at": now,
                    "protocol": None,  # preenchido abaixo
                    "supersedes_event_id": None,
                    "superseded_by_event_id": None,
                    "audit_trail": [{"action": "created_via_institutional_transfer",
                                     "by_user_id": user.get("id"), "at": now}],
                })
        except Exception as exc:
            # Falha parcial: libera lock e marca como failed (idempotente — reexecução completa)
            await db.classes.update_many({"id": {"$in": class_ids}}, {"$unset": {"transfer_in_progress": ""}})
            await db.school_transfer_audit.update_one(
                {"id": dry["id"]}, {"$set": {"status": "failed", "error": str(exc), "failed_at": now}}
            )
            logger.exception("[school-transfer] falha na execução")
            raise HTTPException(status_code=500, detail=f"Falha na transferência: {exc}")

        # 12) Protocolo
        year = datetime.now().year
        seq = await db.school_transfer_audit.count_documents(
            {"protocol": {"$regex": f"^TRANSF-{year}-"}}
        ) + 1
        protocol = f"TRANSF-{year}-{seq:06d}"
        await db.academic_events.update_many(
            {"origin_school_id": origin_id, "destination_school_id": dest_id,
             "event_type": "transferencia_institucional", "protocol": None},
            {"$set": {"protocol": protocol}},
        )

        # 13) Encerra a escola origem se TODAS as turmas saíram
        origin_closed = False
        remaining = await db.classes.count_documents({"school_id": origin_id})
        if remaining == 0:
            await db.schools.update_one({"id": origin_id}, {"$set": {"status": "encerrada", "encerrada_em": now}})
            origin_closed = True

        # 14) Persiste auditoria
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent", "")[:200]
        audit_update = {
            "status": "executed",
            "protocol": protocol,
            "idempotency_key": payload.dry_run_token,
            "reason": payload.reason,
            "executed_by": {"id": user.get("id"), "email": user.get("email")},
            "executed_at": now,
            "ip": ip,
            "user_agent": ua,
            "modified_counts": modified,
            "student_ids": student_ids,
            "origin_closed": origin_closed,
            "snapshot": snapshot,
        }
        await db.school_transfer_audit.update_one({"id": dry["id"]}, {"$set": audit_update})

        if audit_service:
            try:
                await audit_service.log(
                    action="update", collection="school_transfer_audit", user=user, request=request,
                    document_id=dry["id"], school_id=dest_id,
                    description=f"Transferência institucional executada ({protocol}): {len(class_ids)} turma(s) {origin_id} → {dest_id}",
                    extra_data={"protocol": protocol, "class_ids": class_ids,
                                "modified_counts": modified, "origin_closed": origin_closed,
                                "reason": payload.reason},
                )
            except Exception:
                pass

        return {
            "success": True,
            "protocol": protocol,
            "origin_closed": origin_closed,
            "modified_counts": modified,
            "students_moved": len(student_ids),
            "executed_at": now,
        }

    # ----------------------------------------------------------------- LIST
    @router.get("")
    async def list_transfers(request: Request, status: Optional[str] = None, limit: int = 50):
        await _require_super_admin(request)
        flt = {}
        if status:
            flt["status"] = status
        items = await db.school_transfer_audit.find(
            flt, {"_id": 0, "snapshot": 0}
        ).sort("created_at", -1).limit(min(limit, 200)).to_list(None)
        return {"items": items, "total": len(items)}

    # ----------------------------------------------------------------- DETAIL
    @router.get("/{protocol}")
    async def get_transfer(protocol: str, request: Request):
        await _require_super_admin(request)
        doc = await db.school_transfer_audit.find_one({"protocol": protocol}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Protocolo não encontrado.")
        return doc

    return router
