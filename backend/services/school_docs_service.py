"""Orquestrador de emissão de declarações escolares (G1.7 — Fev/2026).

Fluxo:
  1. Busca dados do aluno + escola + turma
  2. Cria SNAPSHOT imutável (payload congelado: quem emitiu, o quê, pra quem, pra quê)
  3. Cria verifiable_document com validade custom por tipo
  4. Registra log em school_documents_log (auditoria, IP, user)
  5. Retorna bytes do PDF pronto para download

LGPD:
  - No snapshot: dados mínimos do aluno (nome, nascimento, escola, turma, ano)
  - No PDF: mesmos dados mínimos + finalidade
  - No portal público: ZERO dados do aluno, apenas tipo/data/emissor/escopo
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Literal

from fastapi import HTTPException

from services import snapshot_service as snap_svc
from services import verifiable_docs_service as vsvc
from services.school_doc_templates import (
    build_school_document_pdf, DOC_TITLES,
)

logger = logging.getLogger(__name__)

DocType = Literal["matricula", "frequencia", "escolaridade"]

# Validade default por tipo (opção 5d do usuário)
DEFAULT_VALIDITY_DAYS = {
    "matricula": 90,
    "frequencia": 30,
    "escolaridade": 180,
}

ALLOWED_TYPES = tuple(DEFAULT_VALIDITY_DAYS.keys())


async def _load_student(db, student_id: str) -> dict:
    student = await db.students.find_one({"id": student_id}, {"_id": 0})
    if not student:
        raise HTTPException(404, "Aluno não encontrado")
    return student


async def _load_school(db, school_id: Optional[str]) -> dict:
    if not school_id:
        return {}
    school = await db.schools.find_one({"id": school_id}, {"_id": 0})
    return school or {}


async def _load_class(db, class_id: Optional[str]) -> dict:
    if not class_id:
        return {}
    cls = await db.classes.find_one({"id": class_id}, {"_id": 0})
    return cls or {}


async def _load_tenant_branding(db, mantenedora_id: Optional[str]) -> dict:
    """Lê branding da mantenedora (município/secretaria)."""
    if not mantenedora_id:
        return {}
    doc = await db.tenant_branding.find_one(
        {"mantenedora_id": mantenedora_id}, {"_id": 0}
    )
    if not doc:
        # fallback: nome da mantenedora se houver
        m = await db.mantenedoras.find_one(
            {"id": mantenedora_id}, {"_id": 0, "name": 1, "city": 1, "state": 1}
        )
        return m or {}
    return doc


def _lgpd_safe_student_payload(student: dict) -> dict:
    """Extrai APENAS campos permitidos pelo escopo LGPD do MVP.

    Sem CPF, RG, endereço, telefone, responsáveis, dados de raça/cor etc.
    """
    return {
        "id": student.get("id"),
        "full_name": student.get("full_name"),
        "birth_date": student.get("birth_date"),
        "enrollment_number": student.get("enrollment_number"),
    }


async def build_context(
    db,
    *,
    student: dict,
    school: dict,
    cls: dict,
    branding: dict,
    doc_type: DocType,
    purpose: str,
    user: dict,
    extra: Optional[dict] = None,
) -> dict:
    """Monta o dict de contexto usado tanto pelo PDF quanto pelo payload_snapshot.

    Dados mínimos — LGPD compliant (opção 4a).
    """
    extra = extra or {}
    # Fallback: se mantenedora não tiver branding, usa defaults genéricos
    secretariat = (
        branding.get("secretariat_name")
        or branding.get("secretaria_nome")
        or branding.get("name")
        or "Secretaria Municipal de Educação"
    )
    city = branding.get("city") or branding.get("municipio") or ""
    state = branding.get("state") or branding.get("uf") or ""

    ctx = {
        "doc_type": doc_type,
        "doc_title": DOC_TITLES.get(doc_type, "DECLARAÇÃO"),
        "purpose": purpose or "",
        # Aluno (LGPD-mínimo)
        "student_id": student.get("id"),
        "student_name": student.get("full_name"),
        "student_birth_date": student.get("birth_date"),
        "enrollment_number": student.get("enrollment_number"),
        # Escola / turma
        "school_id": school.get("id"),
        "school_name": school.get("name"),
        "class_id": cls.get("id"),
        "class_name": cls.get("name"),
        "grade_level": cls.get("grade_level"),
        "academic_year": cls.get("academic_year") or datetime.now().year,
        "shift": cls.get("shift") or "",
        # Institucional
        "secretariat_name": secretariat,
        "city": city,
        "state": state,
        # Assinatura
        "issuer_name": user.get("full_name") or user.get("email") or "Secretaria",
        "issuer_role": {
            "secretario": "Secretário(a) Escolar",
            "auxiliar_secretaria": "Auxiliar de Secretaria",
            "admin": "Administrador(a)",
            "admin_teste": "Administrador(a)",
            "super_admin": "Administrador(a) do Sistema",
            "diretor": "Diretor(a) Escolar",
        }.get(user.get("role"), "Responsável pela Emissão"),
        # Emissão
        "issued_at": datetime.now(timezone.utc).isoformat(),
    }
    # Campos específicos
    if doc_type == "frequencia":
        ctx["frequencia_pct"] = extra.get("frequencia_pct")
        ctx["bimestre"] = extra.get("bimestre")
    if doc_type == "escolaridade":
        ctx["serie_concluida"] = extra.get("serie_concluida")
    return ctx


async def issue_school_document(
    db,
    *,
    student_id: str,
    doc_type: DocType,
    purpose: str,
    user: dict,
    class_id: Optional[str] = None,
    ip: Optional[str] = None,
    validity_days: Optional[int] = None,
    extra: Optional[dict] = None,
) -> dict:
    """Emite uma declaração escolar verificável.

    Retorna: {code, pdf_bytes, valid_until, snapshot_id, public_hash}
    """
    if doc_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Tipo inválido. Use: {ALLOWED_TYPES}")

    # 1. Carrega dados
    student = await _load_student(db, student_id)
    # Escola do aluno (pode ser sobrescrita por class_id informado)
    school_id = student.get("school_id")
    cls = {}
    if class_id:
        cls = await _load_class(db, class_id)
    else:
        # Pega turma atual do aluno (mais recente) se não informado
        cls_doc = await db.class_students.find_one(
            {"student_id": student_id, "active": {"$ne": False}},
            {"_id": 0, "class_id": 1},
            sort=[("enrolled_at", -1)],
        )
        if cls_doc:
            cls = await _load_class(db, cls_doc.get("class_id"))
    # Usa school da turma se disponível
    if cls.get("school_id"):
        school_id = cls["school_id"]
    school = await _load_school(db, school_id)

    mantenedora_id = user.get("mantenedora_id")
    branding = await _load_tenant_branding(db, mantenedora_id)

    # 2. Monta contexto
    ctx = await build_context(
        db,
        student=student, school=school, cls=cls, branding=branding,
        doc_type=doc_type, purpose=purpose, user=user, extra=extra,
    )

    # 3. Snapshot imutável (LGPD-safe payload)
    validity = int(validity_days) if validity_days else DEFAULT_VALIDITY_DAYS[doc_type]
    valid_until = datetime.now(timezone.utc) + timedelta(days=validity)
    snapshot_payload = {
        "doc_type": doc_type,
        "purpose": purpose,
        "student": _lgpd_safe_student_payload(student),
        "school": {"id": school.get("id"), "name": school.get("name")},
        "class": {
            "id": cls.get("id"), "name": cls.get("name"),
            "grade_level": cls.get("grade_level"),
            "academic_year": cls.get("academic_year"),
            "shift": cls.get("shift"),
        },
        "municipality": {"city": ctx.get("city"), "state": ctx.get("state")},
        "validity_days": validity,
        "extra": extra or {},
    }
    snapshot_output = {
        "doc_title": ctx["doc_title"],
        "issued_at": ctx["issued_at"],
        "issuer_email": user.get("email"),
        "issuer_role": user.get("role"),
        "valid_until": valid_until.isoformat(),
    }

    snap = await snap_svc.create_snapshot(
        db,
        mantenedora_id=mantenedora_id,
        entity_type="estudante",
        entity_id=student_id,
        analysis_type=doc_type,  # "matricula" | "frequencia" | "escolaridade"
        payload_snapshot=snapshot_payload,
        ai_output=snapshot_output,  # não é IA; é output oficial
        model="sigesc/emissao-direta",
        user=user,
    )

    # 4. Override expires_at em verifiable_documents conforme validade do tipo.
    # (create_snapshot já criou um verifiable_document com TTL padrão; reescrevemos
    # expires_at para respeitar a validade OFICIAL do documento escolar)
    if snap.get("verification_code"):
        await db.verifiable_documents.update_one(
            {"code": snap["verification_code"]},
            {"$set": {
                "expires_at": valid_until.isoformat(),
                "public_metadata.valido_ate": valid_until.date().isoformat(),
            }}
        )

    # 5. Gera PDF com código + QR + validade
    ctx["code"] = snap.get("verification_code")
    ctx["valid_until"] = valid_until.isoformat()
    ctx["snapshot_id"] = snap["id"]
    pdf_bytes = build_school_document_pdf(doc_type, ctx)

    # 6. Log de emissão (auditoria)
    await db.school_documents_log.insert_one({
        "id": str(uuid.uuid4()),
        "student_id": student_id,
        "student_name": student.get("full_name"),
        "school_id": school.get("id"),
        "class_id": cls.get("id"),
        "doc_type": doc_type,
        "purpose": purpose,
        "code": snap.get("verification_code"),
        "snapshot_id": snap["id"],
        "emitted_by": {
            "user_id": user.get("id"),
            "email": user.get("email"),
            "role": user.get("role"),
        },
        "emitted_at": datetime.now(timezone.utc).isoformat(),
        "ip": ip,
        "valid_until": valid_until.isoformat(),
        "mantenedora_id": mantenedora_id,
    })

    return {
        "code": snap.get("verification_code"),
        "snapshot_id": snap["id"],
        "public_hash": snap["public_hash"],
        "valid_until": valid_until.isoformat(),
        "pdf_bytes": pdf_bytes,
        "doc_type": doc_type,
    }
