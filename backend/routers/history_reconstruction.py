"""Ferramenta administrativa: Reconstrução de Histórico Pedagógico.

Reprocessa (idempotente) a consolidação pedagógica para alunos que mudaram de
turma no mesmo ano letivo: copia frequência, notas e conteúdo das turmas de
ORIGEM (matrículas inativas) para a turma ATUAL (matrícula ativa), sem alterar
a origem. Escopo: aluno / turma / escola, opcionalmente por ano letivo.

Endpoints (super_admin):
  POST /admin/history-reconstruction/dry-run
  POST /admin/history-reconstruction/execute
  GET  /admin/history-reconstruction/{protocol}/receipt
"""
from __future__ import annotations

import io
import uuid
import hashlib
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from typing import List, Optional

from auth_middleware import AuthMiddleware
from tenant_scope import is_super_admin
from services.pedagogical_consolidation import consolidate_student_movement
from services.verifiable_docs_service import create_verifiable_document
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from pdf.verification_footer import build_verification_flowables

logger = logging.getLogger(__name__)
MIN_REASON_LEN = 10


class ReconScope(BaseModel):
    scope: str = Field(..., pattern="^(student|class|school)$")
    student_id: Optional[str] = None
    class_id: Optional[str] = None
    school_id: Optional[str] = None
    academic_year: Optional[int] = None


class ExecuteRecon(ReconScope):
    reason: str = Field(..., min_length=MIN_REASON_LEN)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def setup_router(db, audit_service=None):
    router = APIRouter(prefix="/admin/history-reconstruction", tags=["history-reconstruction"])

    async def _require_super_admin(request: Request) -> dict:
        user = await AuthMiddleware.get_current_user(request)
        if not is_super_admin(user):
            raise HTTPException(status_code=403, detail="Apenas Super Administrador pode reconstruir histórico pedagógico.")
        return user

    async def _resolve_students(scope: ReconScope) -> List[str]:
        if scope.scope == "student":
            if not scope.student_id:
                raise HTTPException(400, "student_id obrigatório para escopo 'student'.")
            return [scope.student_id]
        if scope.scope == "class":
            if not scope.class_id:
                raise HTTPException(400, "class_id obrigatório para escopo 'class'.")
            q = {"$or": [{"class_id": scope.class_id}]}
            ids = [e["student_id"] for e in await db.enrollments.find(q, {"_id": 0, "student_id": 1}).to_list(None)]
            return sorted(set(ids))
        if scope.scope == "school":
            if not scope.school_id:
                raise HTTPException(400, "school_id obrigatório para escopo 'school'.")
            ids = [s["id"] for s in await db.students.find({"school_id": scope.school_id}, {"_id": 0, "id": 1}).to_list(None)]
            return sorted(set(ids))
        return []

    async def _plan_for_student(student_id: str, year_filter: Optional[int]):
        """Para cada (ano) com >1 turma, planeja cópia das origens → turma ativa.
        Retorna lista de jobs {student_id, source_class_id, target_class_id, year}."""
        enrolls = await db.enrollments.find({"student_id": student_id}, {"_id": 0}).to_list(None)
        by_year = {}
        for e in enrolls:
            y = e.get("academic_year")
            if year_filter and y != year_filter:
                continue
            by_year.setdefault(y, []).append(e)
        jobs = []
        for y, lst in by_year.items():
            if len(lst) < 2:
                continue
            active = next((e for e in lst if (e.get("status") or "") in ("active", "Ativo")), None)
            if not active:
                # sem matrícula ativa: usa a mais recente como destino
                active = sorted(lst, key=lambda e: e.get("created_at") or "")[-1]
            target = active.get("class_id")
            for e in lst:
                if e.get("class_id") and e.get("class_id") != target:
                    jobs.append({"student_id": student_id, "source_class_id": e["class_id"],
                                 "target_class_id": target, "academic_year": y})
        return jobs

    async def _count_missing(job, dry=True):
        """Conta quanto seria copiado (dry) executando a consolidação idempotente."""
        # dry-run real: roda a consolidação? Não — precisa não alterar. Então conta o gap.
        src, tgt, y, sid = job["source_class_id"], job["target_class_id"], job["academic_year"], job["student_id"]
        missing = {"attendance": 0, "grades": 0, "content_entries": 0}
        # grades
        gsrc = await db.grades.find({"class_id": src, "student_id": sid, "academic_year": y}, {"_id": 0, "course_id": 1}).to_list(500)
        for g in gsrc:
            ex = await db.grades.find_one({"class_id": tgt, "student_id": sid, "course_id": g.get("course_id"), "academic_year": y})
            if not ex:
                missing["grades"] += 1
        # attendance
        asrc = await db.attendance.find({"class_id": src, "academic_year": y, "records.student_id": sid}, {"_id": 0, "date": 1}).to_list(2000)
        for a in asrc:
            ex = await db.attendance.find_one({"class_id": tgt, "date": a["date"], "academic_year": y, "records.student_id": sid})
            if not ex:
                missing["attendance"] += 1
        # content
        csrc = await db.content_entries.find({"class_id": src}, {"_id": 0, "course_id": 1, "date": 1, "deleted": 1}).to_list(3000)
        for c in csrc:
            if c.get("deleted"):
                continue
            ex = await db.content_entries.find_one({"class_id": tgt, "course_id": c.get("course_id"), "date": c.get("date")})
            if not ex:
                missing["content_entries"] += 1
        return missing

    @router.post("/dry-run")
    async def dry_run(payload: ReconScope, request: Request):
        await _require_super_admin(request)
        students = await _resolve_students(payload)
        jobs = []
        for sid in students:
            jobs.extend(await _plan_for_student(sid, payload.academic_year))
        totals = {"attendance": 0, "grades": 0, "content_entries": 0}
        details = []
        for job in jobs:
            miss = await _count_missing(job)
            for k in totals:
                totals[k] += miss[k]
            details.append({**job, "missing": miss})
        return {
            "scope": payload.scope,
            "students_in_scope": len(students),
            "movements_detected": len(jobs),
            "to_consolidate": totals,
            "details": details[:200],
            "note": "Dry run não altera dados. 'to_consolidate' = registros faltantes que seriam copiados.",
        }

    @router.post("/execute")
    async def execute(payload: ExecuteRecon, request: Request):
        user = await _require_super_admin(request)
        students = await _resolve_students(payload)
        jobs = []
        for sid in students:
            jobs.extend(await _plan_for_student(sid, payload.academic_year))

        applied = {"attendance": 0, "grades": 0, "content_entries": 0}
        processed_students = set()
        for job in jobs:
            res = await consolidate_student_movement(
                db, student_id=job["student_id"], source_class_id=job["source_class_id"],
                target_class_id=job["target_class_id"], academic_year=job["academic_year"])
            for k in applied:
                applied[k] += res.get(k, 0)
            processed_students.add(job["student_id"])

        year = datetime.now().year
        seq = await db.history_reconstruction_audit.count_documents({"protocol": {"$regex": f"^RECON-{year}-"}}) + 1
        protocol = f"RECON-{year}-{seq:06d}"
        now = _now_iso()
        ip = request.client.host if request.client else None
        audit_doc = {
            "id": str(uuid.uuid4()), "protocol": protocol,
            "scope": payload.scope, "student_id": payload.student_id, "class_id": payload.class_id,
            "school_id": payload.school_id, "academic_year": payload.academic_year,
            "reason": payload.reason, "executed_by": {"id": user.get("id"), "email": user.get("email")},
            "executed_at": now, "ip": ip,
            "students_processed": len(processed_students), "movements_processed": len(jobs),
            "applied_counts": applied, "status": "executed",
        }
        await db.history_reconstruction_audit.insert_one(audit_doc)
        if audit_service:
            try:
                await audit_service.log(action="update", collection="history_reconstruction_audit",
                                        user=user, request=request, document_id=audit_doc["id"],
                                        school_id=payload.school_id,
                                        description=f"Reconstrução de histórico pedagógico ({protocol}): {len(jobs)} movimentação(ões), {applied}",
                                        extra_data={"protocol": protocol, "applied": applied, "scope": payload.scope})
            except Exception:
                pass
        return {"success": True, "protocol": protocol, "students_processed": len(processed_students),
                "movements_processed": len(jobs), "applied_counts": applied, "executed_at": now}

    @router.get("/{protocol}/receipt")
    async def receipt(protocol: str, request: Request):
        user = await _require_super_admin(request)
        audit = await db.history_reconstruction_audit.find_one({"protocol": protocol}, {"_id": 0})
        if not audit:
            raise HTTPException(404, "Protocolo não encontrado.")
        rec = audit.get("receipt") or {}
        code, token = rec.get("code"), rec.get("token")
        if not (code and token):
            canonical = json.dumps({"protocol": protocol, "scope": audit.get("scope"),
                                    "applied": audit.get("applied_counts"), "at": audit.get("executed_at")},
                                   sort_keys=True, ensure_ascii=False)
            public_hash = hashlib.sha256(canonical.encode()).hexdigest()
            vdoc = await create_verifiable_document(
                db, type="recibo_reconstrucao_historico", public_hash=public_hash, server_signature=None,
                mantenedora_id=None, entity_type="history_reconstruction", entity_id=protocol,
                school_id=audit.get("school_id"), issued_by={"id": user.get("id"), "email": user.get("email")},
                scope_label=f"Reconstrução {protocol}")
            code, token = vdoc["code"], vdoc["verification_token"]
            await db.history_reconstruction_audit.update_one({"protocol": protocol},
                {"$set": {"receipt": {"code": code, "token": token, "created_at": _now_iso()}}})
        pdf = _build_receipt_pdf(audit, code, token)
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f"inline; filename=recibo-{protocol}.pdf"})

    return router


def _build_receipt_pdf(audit: dict, code: str, token: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2 * cm, bottomMargin=1.5 * cm,
                            leftMargin=2 * cm, rightMargin=2 * cm, title=f"Recibo {audit.get('protocol')}")
    styles = getSampleStyleSheet()
    h = ParagraphStyle("H", parent=styles["Title"], fontSize=16, textColor=colors.HexColor("#1E3A8A"))
    label = ParagraphStyle("l", parent=styles["Normal"], fontSize=9.5, textColor=colors.HexColor("#374151"), leading=13)
    ac = audit.get("applied_counts") or {}
    story = [Paragraph("Recibo de Reconstrução de Histórico Pedagógico", h),
             Paragraph("SIGESC — Sistema Integrado de Gestão Escolar", label), Spacer(1, 0.6 * cm)]
    rows = [
        ("Protocolo", audit.get("protocol")),
        ("Escopo", audit.get("scope")),
        ("Ano letivo", str(audit.get("academic_year") or "Todos")),
        ("Alunos processados", str(audit.get("students_processed"))),
        ("Movimentações processadas", str(audit.get("movements_processed"))),
        ("Frequência consolidada", str(ac.get("attendance", 0))),
        ("Notas consolidadas", str(ac.get("grades", 0))),
        ("Conteúdos consolidados", str(ac.get("content_entries", 0))),
        ("Operador", (audit.get("executed_by") or {}).get("email")),
        ("Data/hora", audit.get("executed_at")),
        ("Justificativa", audit.get("reason")),
    ]
    t = Table([[Paragraph(f"<b>{k}</b>", label), Paragraph(str(v), label)] for k, v in rows], colWidths=[6 * cm, 10.5 * cm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E5E7EB")),
                           ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3F4F6")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
    story.append(t)
    story.append(Spacer(1, 0.8 * cm))
    story.extend(build_verification_flowables(code, None, label="Verificação de Autenticidade do Recibo", verification_token=token))
    doc.build(story)
    return buf.getvalue()
