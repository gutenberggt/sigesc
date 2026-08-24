"""Orquestrador de emissão de declarações escolares (G1.7 — Fev/2026).

Fluxo:
  1. Busca dados do aluno + matrícula canônica + escola + turma
  2. Cria SNAPSHOT imutável (payload congelado: quem emitiu, o quê, pra quem, pra quê)
  3. Cria verifiable_document com validade custom por tipo
  4. Registra log em school_documents_log (auditoria, IP, user)
  5. Retorna bytes do PDF pronto para download

Desde Ago/2026, ``enrollments`` é a fonte primária do vínculo aluno↔turma.
``students.class_id`` existe apenas como fallback temporário de leitura para o
passivo legado e emite WARNING. ``class_students`` não participa mais deste fluxo.

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
from services.enrollment_service import find_primary_active_enrollment
from services.school_doc_templates import (
    build_school_document_pdf,
    DOC_TITLES,
)

logger = logging.getLogger(__name__)

DocType = Literal["matricula", "frequencia", "escolaridade"]

DEFAULT_VALIDITY_DAYS = {
    "matricula": 90,
    "frequencia": 30,
    "escolaridade": 180,
}

ALLOWED_TYPES = tuple(DEFAULT_VALIDITY_DAYS.keys())


async def _load_student(db, student_id: str) -> dict:
    student = await db.students.find_one({"id": student_id}, {"_id": 0})
    if not student:
        raise HTTPException(404, "Estudante não encontrado")
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
        m = await db.mantenedoras.find_one(
            {"id": mantenedora_id}, {"_id": 0, "name": 1, "city": 1, "state": 1}
        )
        return m or {}
    return doc


def _lgpd_safe_student_payload(student: dict) -> dict:
    """Extrai APENAS campos permitidos pelo escopo LGPD do MVP."""
    return {
        "id": student.get("id"),
        "full_name": student.get("full_name"),
        "birth_date": student.get("birth_date"),
        "enrollment_number": student.get("enrollment_number"),
    }


async def _resolve_school_class_enrollment(
    db,
    *,
    student: dict,
    class_id: Optional[str],
    doc_type: DocType,
) -> tuple[dict, dict, Optional[dict], str]:
    """Resolve turma/escola priorizando exclusivamente ``enrollments``.

    ``students.class_id`` é mantido como fallback de compatibilidade até a Fase 2
    de reconciliação do passivo. O fallback é observável por log e pelo snapshot.
    """
    student_id = student.get("id")
    enrollment = None
    source = "enrollments"

    if class_id:
        cls = await _load_class(db, class_id)
        if not cls:
            raise HTTPException(404, "Turma informada não encontrada")

        # Declarações de matrícula/frequência precisam comprovar vínculo ativo
        # com a turma explicitamente solicitada.
        if doc_type in {"matricula", "frequencia"}:
            enrollment = await db.enrollments.find_one(
                {
                    "student_id": student_id,
                    "class_id": class_id,
                    "status": "active",
                },
                {"_id": 0},
            )
            if not enrollment:
                raise HTTPException(
                    409,
                    "O estudante não possui matrícula ativa na turma informada.",
                )
    else:
        enrollment = await find_primary_active_enrollment(db, student_id)
        if enrollment:
            cls = await _load_class(db, enrollment.get("class_id"))
        else:
            cls = {}
            legacy_class_id = student.get("class_id")
            if legacy_class_id:
                source = "students.class_id_legacy_fallback"
                logger.warning(
                    "[ENROLLMENT_LEGACY_FALLBACK] student_id=%s sem matrícula regular ativa; "
                    "usando students.class_id=%s temporariamente",
                    student_id,
                    legacy_class_id,
                )
                cls = await _load_class(db, legacy_class_id)

    if doc_type in {"matricula", "frequencia"} and not cls:
        raise HTTPException(
            409,
            "O estudante não possui matrícula regular ativa suficiente para emitir este documento.",
        )

    school_id = (
        (enrollment or {}).get("school_id")
        or cls.get("school_id")
        or student.get("school_id")
    )
    school = await _load_school(db, school_id)
    return school, cls, enrollment, source


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
    """Monta o dict de contexto usado tanto pelo PDF quanto pelo payload_snapshot."""
    extra = extra or {}
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
        "student_id": student.get("id"),
        "student_name": student.get("full_name"),
        "student_birth_date": student.get("birth_date"),
        "enrollment_number": student.get("enrollment_number"),
        "school_id": school.get("id"),
        "school_name": school.get("name"),
        "class_id": cls.get("id"),
        "class_name": cls.get("name"),
        "grade_level": cls.get("grade_level"),
        "academic_year": cls.get("academic_year") or datetime.now().year,
        "shift": cls.get("shift") or "",
        "secretariat_name": secretariat,
        "city": city,
        "state": state,
        "issuer_name": user.get("full_name") or user.get("email") or "Secretaria",
        "issuer_role": {
            "secretario": "Secretário(a) Escolar",
            "auxiliar_secretaria": "Auxiliar de Secretaria",
            "admin": "Administrador(a)",
            "admin_teste": "Administrador(a)",
            "super_admin": "Administrador(a) do Sistema",
            "diretor": "Diretor(a) Escolar",
        }.get(user.get("role"), "Responsável pela Emissão"),
        "issued_at": datetime.now(timezone.utc).isoformat(),
    }
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
    """Emite uma declaração escolar verificável."""
    if doc_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Tipo inválido. Use: {ALLOWED_TYPES}")

    student = await _load_student(db, student_id)
    school, cls, enrollment, enrollment_source = await _resolve_school_class_enrollment(
        db,
        student=student,
        class_id=class_id,
        doc_type=doc_type,
    )

    # Quando a matrícula canônica possui número, ela prevalece sobre o espelho
    # em students para o documento e para o snapshot.
    effective_student = dict(student)
    if enrollment and enrollment.get("enrollment_number"):
        effective_student["enrollment_number"] = enrollment["enrollment_number"]

    mantenedora_id = (
        (enrollment or {}).get("mantenedora_id")
        or school.get("mantenedora_id")
        or user.get("mantenedora_id")
    )
    branding = await _load_tenant_branding(db, mantenedora_id)

    ctx = await build_context(
        db,
        student=effective_student,
        school=school,
        cls=cls,
        branding=branding,
        doc_type=doc_type,
        purpose=purpose,
        user=user,
        extra=extra,
    )

    validity = int(validity_days) if validity_days else DEFAULT_VALIDITY_DAYS[doc_type]
    valid_until = datetime.now(timezone.utc) + timedelta(days=validity)
    snapshot_payload = {
        "doc_type": doc_type,
        "purpose": purpose,
        "student": _lgpd_safe_student_payload(effective_student),
        "school": {"id": school.get("id"), "name": school.get("name")},
        "class": {
            "id": cls.get("id"),
            "name": cls.get("name"),
            "grade_level": cls.get("grade_level"),
            "academic_year": cls.get("academic_year"),
            "shift": cls.get("shift"),
        },
        "enrollment": {
            "id": (enrollment or {}).get("id"),
            "source": enrollment_source,
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
        analysis_type=doc_type,
        payload_snapshot=snapshot_payload,
        ai_output=snapshot_output,
        model="sigesc/emissao-direta",
        user=user,
    )

    if snap.get("verification_code"):
        await db.verifiable_documents.update_one(
            {"code": snap["verification_code"]},
            {"$set": {
                "expires_at": valid_until.isoformat(),
                "public_metadata.valido_ate": valid_until.date().isoformat(),
            }},
        )

    ctx["code"] = snap.get("verification_code")
    ctx["valid_until"] = valid_until.isoformat()
    ctx["snapshot_id"] = snap["id"]
    pdf_bytes = build_school_document_pdf(doc_type, ctx)

    await db.school_documents_log.insert_one({
        "id": str(uuid.uuid4()),
        "student_id": student_id,
        "student_name": student.get("full_name"),
        "school_id": school.get("id"),
        "class_id": cls.get("id"),
        "enrollment_id": (enrollment or {}).get("id"),
        "enrollment_source": enrollment_source,
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
