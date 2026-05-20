"""Handler de render para document_type='bulletin' (Boletim Oficial).

Fluxo:
  1. Recebe job dict do render_worker.
  2. Decodifica `source_snapshot_id` no formato `boletim:{student_id}:{year}`.
  3. Monta o bulletin via `utils.bulletin_builder.build_student_bulletin`.
  4. Cria registro em `bulletin_verifications` (token público + dados-resumo
     mínimos LGPD-safe + hash placeholder).
  5. Gera o PDF via `pdf.boletim.generate_boletim_pdf`.
  6. Faz overlay com QR Code apontando para `/verify/boletim/{token}` em todas as páginas.
  7. Persiste o PDF final via `services.document_files.store_pdf`.
  8. Atualiza `bulletin_verifications.pdf_hash_sha256` com o hash REAL do PDF entregue.
  9. Retorna metadados para o render_worker.

Princípio LGPD: o endpoint público de verificação NÃO expõe notas detalhadas;
expõe somente: aluno (nome), escola, ano, status (aprovado/reprovado/em curso),
hash do PDF, data de emissão. Quem tem o PDF físico pode comparar o hash.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

import qrcode
from PyPDF2 import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from services.document_files import store_pdf

logger = logging.getLogger(__name__)


def _parse_source_id(source_snapshot_id: str) -> tuple[str, int]:
    """Decodifica `boletim:{student_id}:{academic_year}`."""
    parts = (source_snapshot_id or "").split(":")
    if len(parts) != 3 or parts[0] != "boletim":
        raise ValueError(
            f"source_snapshot_id inválido para document_type=bulletin: "
            f"esperado 'boletim:STU:YEAR', got '{source_snapshot_id}'"
        )
    try:
        year = int(parts[2])
    except ValueError as e:
        raise ValueError(f"academic_year inválido em source_snapshot_id: {parts[2]}") from e
    return parts[1], year


def _generate_token() -> str:
    """Token público URL-safe de 22 chars (~128 bits de entropia)."""
    return secrets.token_urlsafe(16)


def _build_verify_url(base_url: str, token: str) -> str:
    base = (base_url or "").rstrip("/")
    return f"{base}/verify/boletim/{token}"


def _make_qr_image(data: str) -> BytesIO:
    """Gera PNG do QR Code em memória."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _stamp_qr_overlay(pdf_bytes: bytes, qr_url: str, *, doc_id: str) -> bytes:
    """Adiciona QR Code + texto de verificação no rodapé de TODAS as páginas."""
    reader = PdfReader(BytesIO(pdf_bytes))
    writer = PdfWriter()
    qr_img = _make_qr_image(qr_url)
    from reportlab.lib.utils import ImageReader
    qr_reader = ImageReader(qr_img)

    for page in reader.pages:
        # Overlay com QR no canto inferior direito
        page_box = page.mediabox
        w = float(page_box.width)
        h = float(page_box.height)

        overlay_buf = BytesIO()
        c = canvas.Canvas(overlay_buf, pagesize=(w, h))
        qr_size = 2.4 * cm
        margin = 0.6 * cm
        x_qr = w - qr_size - margin
        y_qr = margin
        c.drawImage(
            qr_reader, x_qr, y_qr, width=qr_size, height=qr_size,
            preserveAspectRatio=True, mask='auto'
        )
        # Texto à esquerda do QR
        c.setFont("Helvetica", 6)
        c.setFillColorRGB(0.25, 0.25, 0.25)
        text_x = x_qr - 0.2 * cm
        c.drawRightString(text_x, y_qr + 1.5 * cm, "Documento verificável online.")
        c.drawRightString(text_x, y_qr + 1.05 * cm, "Leia o QR Code ou acesse:")
        c.drawRightString(text_x, y_qr + 0.60 * cm, qr_url)
        c.drawRightString(text_x, y_qr + 0.15 * cm, f"Cód: {doc_id[:12]}")
        c.save()

        overlay_pdf = PdfReader(BytesIO(overlay_buf.getvalue()))
        page.merge_page(overlay_pdf.pages[0])
        writer.add_page(page)

    out = BytesIO()
    writer.write(out)
    return out.getvalue()


async def _build_bulletin_pdf(db, *, student_id: str, academic_year: int) -> tuple[bytes, dict]:
    """Gera o PDF do boletim com as MESMAS regras do endpoint síncrono.

    Retorna (pdf_bytes, summary) onde summary contém dados-resumo para
    o verification record (LGPD-safe).
    """
    student = await db.students.find_one({"id": student_id}, {"_id": 0})
    if not student:
        raise ValueError(f"Aluno não encontrado: {student_id}")

    class_id = student.get("class_id")
    school_id = student.get("school_id")
    class_info = await db.classes.find_one({"id": class_id}, {"_id": 0}) if class_id else None
    if not class_info:
        raise ValueError(f"Turma do aluno não encontrada (class_id={class_id})")

    school = await db.schools.find_one({"id": school_id}, {"_id": 0}) or {
        "name": "Escola Municipal", "city": "Município"
    }

    actual_year = academic_year or class_info.get("academic_year") or datetime.now().year

    # Courses
    course_ids = class_info.get("course_ids") or []
    courses = []
    if course_ids:
        courses = await db.courses.find({"id": {"$in": course_ids}}, {"_id": 0}).to_list(200)
        courses.sort(key=lambda c: c.get("name", ""))

    # Grades
    grades = await db.grades.find(
        {"student_id": student_id, "academic_year": actual_year}, {"_id": 0}
    ).to_list(500)

    # Enrollment (simplificado — só registration_number)
    enrollment = {
        "registration_number": student.get("enrollment_number", "N/A"),
        "student_series": class_info.get("grade_level"),
    }

    # Mantenedora
    mantenedora = await db.mantenedoras.find_one({}, {"_id": 0}) or {}

    # Calendário letivo
    calendario_letivo = await db.calendario_letivo.find_one(
        {"ano_letivo": actual_year, "school_id": None}, {"_id": 0}
    )

    # Frequência consolidada por componente
    attendance_data = {}
    if course_ids:
        atts = await db.attendance.find(
            {
                "class_id": class_id,
                "course_id": {"$in": course_ids},
                "records.student_id": student_id,
            },
            {"_id": 0}
        ).to_list(None)
        for att in atts:
            cid = att.get("course_id")
            absences = 0
            for sr in att.get("records") or []:
                if sr.get("student_id") == student_id and (sr.get("status") or "").upper() in ("F", "A", "ABSENT"):
                    absences += 1
            if cid:
                prev = attendance_data.get(cid) or {"absences": 0}
                prev["absences"] = (prev.get("absences") or 0) + absences
                attendance_data[cid] = prev

    # PDF (reusa gerador oficial existente)
    from pdf.boletim import generate_boletim_pdf
    buf = generate_boletim_pdf(
        student=student,
        school=school,
        enrollment=enrollment,
        class_info=class_info,
        grades=grades,
        courses=courses,
        academic_year=str(actual_year),
        mantenedora=mantenedora,
        calendario_letivo=calendario_letivo,
        attendance_data=attendance_data,
    )
    buf.seek(0)
    pdf_bytes = buf.read()

    summary = {
        "student_id": student_id,
        "student_name": student.get("full_name"),
        "school_id": school_id,
        "school_name": school.get("name"),
        "class_id": class_id,
        "class_name": class_info.get("name"),
        "grade_level": class_info.get("grade_level"),
        "academic_year": actual_year,
        "mantenedora_id": mantenedora.get("id"),
    }
    return pdf_bytes, summary


async def render_bulletin_handler(job: dict, *, db, public_base_url: str) -> dict:
    """Handler registrado para document_type='bulletin'."""
    source_snapshot_id = job.get("source_snapshot_id") or ""
    student_id, academic_year = _parse_source_id(source_snapshot_id)

    # 1) PDF base + resumo
    pdf_bytes, summary = await _build_bulletin_pdf(
        db, student_id=student_id, academic_year=academic_year
    )

    # 2) Cria pre-registro de verificação (token + token_hash idx)
    token = _generate_token()
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    verification_id = str(uuid.uuid4())
    verify_url = _build_verify_url(public_base_url, token)
    now = datetime.now(timezone.utc).isoformat()

    verification_doc = {
        "id": verification_id,
        "token_hash": token_hash,  # NUNCA armazenamos o token em claro
        "document_type": "bulletin",
        "job_id": job.get("id"),
        **summary,
        "verify_url": verify_url,
        "pdf_hash_sha256": None,  # preenchido após overlay
        "created_at": now,
        "revoked_at": None,
        "revoked_by": None,
        "issued_by_user_id": job.get("requested_by_user_id"),
    }
    await db.bulletin_verifications.insert_one(verification_doc)

    # 3) Overlay com QR
    final_pdf = _stamp_qr_overlay(pdf_bytes, verify_url, doc_id=verification_id)

    # 4) Hash do PDF final
    pdf_hash = hashlib.sha256(final_pdf).hexdigest()

    # 5) Persiste o arquivo
    safe_name = (summary.get("student_name") or "aluno").replace(" ", "_")
    filename = f"boletim_oficial_{safe_name}_{academic_year}.pdf"
    stored = await store_pdf(
        db,
        pdf_bytes=final_pdf,
        filename=filename,
        document_type="bulletin",
        mantenedora_id=summary.get("mantenedora_id"),
        school_id=summary.get("school_id"),
        student_id=student_id,
    )

    # 6) Atualiza verification com hash REAL do PDF entregue
    await db.bulletin_verifications.update_one(
        {"id": verification_id},
        {"$set": {"pdf_hash_sha256": pdf_hash, "file_id": stored["file_id"]}}
    )

    logger.info(
        "[bulletin_renderer] job=%s student=%s year=%s file_id=%s sha=%s",
        job.get("id"), student_id, academic_year, stored["file_id"], pdf_hash[:12]
    )

    return {
        "generated_file_id": stored["file_id"],
        "generated_file_size_bytes": stored["size_bytes"],
        "pdf_hash_sha256": pdf_hash,
        "verification_id": verification_id,
        "verify_url": verify_url,
    }
