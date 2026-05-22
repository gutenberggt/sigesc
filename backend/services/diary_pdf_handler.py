"""
Handler de render para `document_type='diary_period'` (Fase 5 — Mai/2026).

PRINCÍPIO ABSOLUTO: este handler lê APENAS o snapshot congelado.
NUNCA volta ao banco vivo (`attendance`, `content_entries`).

Fluxo:
  1. Recebe `job` do render_worker — `source_snapshot_id == diary_snapshots.id`.
  2. Carrega o snapshot completo.
  3. Renderiza PDF a partir do `payload` congelado.
  4. Calcula SHA-256 do PDF gerado.
  5. Persiste em `document_files`.
  6. Anexa entrada em `diary_snapshots.renders[]` (diretriz 6 — array, não singular).
  7. Retorna metadados para o render_worker registrar no job.
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime
from io import BytesIO
from typing import Optional

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    Image as RLImage,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER

from services.document_files import store_pdf
from services.diary_snapshot_service import append_render, TEMPLATE_VERSION, RENDER_ENGINE_VERSION

logger = logging.getLogger(__name__)

# URL pública do verificador. Default = REACT_APP_BACKEND_URL.
# O QR aponta para a PÁGINA frontend `/verify/diary/{token}`,
# que internamente consulta `/api/verify/diary/{token}`.
PUBLIC_VERIFY_BASE = (
    os.environ.get("PUBLIC_VERIFY_BASE")
    or os.environ.get("REACT_APP_BACKEND_URL", "")
).rstrip("/")


# Mapeamento human-readable dos status (diretriz 6 — semantic_rules_version=1)
STATUS_LABEL_PT = {
    "not_expected": "Sem aula",
    "empty": "Pendente",
    "partial": "Parcial",
    "complete": "Completo",
    "corrected": "Corrigido",
    "validated": "Validado",
    "inconsistent": "Inconsistente",
}

STATUS_COLOR_HEX = {
    "not_expected": "#9CA3AF",
    "empty": "#D97706",
    "partial": "#CA8A04",
    "complete": "#10B981",
    "corrected": "#3B82F6",
    "validated": "#047857",
    "inconsistent": "#DC2626",
}


def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(
        "DiaryTitle", parent=s["Heading1"], fontSize=16, leading=20,
        textColor=colors.HexColor("#0F172A"), spaceAfter=8, alignment=TA_LEFT,
    ))
    s.add(ParagraphStyle(
        "DiaryH2", parent=s["Heading2"], fontSize=12, leading=14,
        textColor=colors.HexColor("#1E40AF"), spaceBefore=8, spaceAfter=4,
    ))
    s.add(ParagraphStyle(
        "DiaryBody", parent=s["BodyText"], fontSize=9, leading=12, spaceAfter=2,
    ))
    s.add(ParagraphStyle(
        "DiaryMeta", parent=s["BodyText"], fontSize=7, leading=9,
        textColor=colors.HexColor("#6B7280"),
    ))
    s.add(ParagraphStyle(
        "DiaryHashFooter", parent=s["BodyText"], fontSize=6, leading=8,
        textColor=colors.HexColor("#6B7280"), fontName="Courier",
    ))
    s.add(ParagraphStyle(
        "DiaryCenter", parent=s["BodyText"], fontSize=8, leading=10, alignment=TA_CENTER,
    ))
    return s


def _fmt_date_br(iso: str) -> str:
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
        return d.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return iso or "—"


def _build_qr_image(token: str) -> Optional[bytes]:
    """Gera PNG do QR apontando para a página pública de verificação.

    Retorna None se o token não existir (snapshot ainda não publicado).
    """
    if not token:
        return None
    url = f"{PUBLIC_VERIFY_BASE}/verify/diary/{token}"
    qr = qrcode.QRCode(
        version=None,                          # auto
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4, border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _build_pdf_from_snapshot(snap: dict) -> bytes:
    """Renderiza o PDF do diário a partir do payload congelado."""
    styles = _styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=2.0 * cm,
        title=f"Diário Escolar — {snap.get('class_id','')}",
    )
    story: list = []

    branding = snap.get("branding") or {}
    klass = (snap.get("payload") or {}).get("class") or {}
    period = snap.get("period") or {}
    payload = snap.get("payload") or {}
    summary = payload.get("summary") or {}
    days = payload.get("days") or []
    authors = payload.get("authors_registry") or []
    orphan = payload.get("orphan_evidence") or {}

    # -------- Cabeçalho institucional --------
    header_lines = []
    if branding.get("mantenedora_name"):
        header_lines.append(branding["mantenedora_name"])
    if branding.get("document_footer"):
        header_lines.append(branding["document_footer"])
    if branding.get("school_name"):
        header_lines.append(f"<b>{branding['school_name']}</b>")
    for ln in header_lines:
        story.append(Paragraph(ln, styles["DiaryBody"]))
    story.append(Spacer(1, 0.3 * cm))

    # -------- Título --------
    story.append(Paragraph("Diário Escolar — Documento Institucional", styles["DiaryTitle"]))
    story.append(Paragraph(
        f"Turma: <b>{klass.get('name','—')}</b> &nbsp;·&nbsp; "
        f"Período: <b>{_fmt_date_br(period.get('from',''))} a {_fmt_date_br(period.get('to',''))}</b> "
        f"({period.get('type','custom')})",
        styles["DiaryBody"],
    ))
    story.append(Paragraph(
        f"Ano letivo: {klass.get('academic_year','—')} &nbsp;·&nbsp; "
        f"Nível: {klass.get('education_level','—')} &nbsp;·&nbsp; "
        f"Turno: {klass.get('shift','—')}",
        styles["DiaryMeta"],
    ))
    story.append(Spacer(1, 0.3 * cm))

    # -------- Resumo --------
    dsc = summary.get("day_status_counts") or {}
    story.append(Paragraph("Resumo do Período", styles["DiaryH2"]))
    resumo = [
        ["Métrica", "Quantidade"],
        ["Slots esperados pela grade", str(summary.get("expected_slots", 0))],
        ["Dias completos", str(dsc.get("complete", 0) + dsc.get("corrected", 0))],
        ["Dias parciais", str(dsc.get("partial", 0))],
        ["Dias pendentes", str(dsc.get("empty", 0))],
        ["Dias inconsistentes", str(dsc.get("inconsistent", 0))],
        ["Frequência registrada", str(summary.get("attendance_completed", 0))],
        ["Frequência validada", str(summary.get("attendance_validated", 0))],
        ["Conteúdo publicado", str(summary.get("content_published", 0))],
        ["Conteúdo corrigido", str(summary.get("content_corrected", 0))],
    ]
    t = Table(resumo, colWidths=[10 * cm, 5 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E40AF")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D1D5DB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.4 * cm))

    # -------- Dias com lançamentos --------
    story.append(Paragraph("Registros Diários", styles["DiaryH2"]))
    significant_days = [d for d in days if d.get("status") != "not_expected"]
    if not significant_days:
        story.append(Paragraph("<i>Nenhum dia com aula esperada neste período.</i>", styles["DiaryBody"]))
    else:
        for d in significant_days:
            status = d.get("status", "empty")
            color_hex = STATUS_COLOR_HEX.get(status, "#6B7280")
            story.append(Paragraph(
                f"<font color='{color_hex}'>■</font> "
                f"<b>{_fmt_date_br(d.get('date',''))}</b> — "
                f"<font color='{color_hex}'><b>{STATUS_LABEL_PT.get(status, status)}</b></font> "
                f"&nbsp;·&nbsp; {d.get('expected_slots', 0)} aula(s) esperada(s)"
                + ("  &nbsp;·&nbsp; <b>EVIDÊNCIA ÓRFÃ</b>" if d.get("has_orphan_evidence") else ""),
                styles["DiaryBody"],
            ))
            entries = d.get("entries") or []
            if entries:
                rows = [["Aula", "Professor", "Componente", "Frequência", "Conteúdo"]]
                for e in entries:
                    rows.append([
                        str(e.get("aula_numero", "—")),
                        (e.get("teacher_name") or "—")[:30],
                        (e.get("component_name") or "—")[:24],
                        e.get("attendance_status", "—"),
                        e.get("content_status", "—"),
                    ])
                inner = Table(rows, colWidths=[1.0 * cm, 5.5 * cm, 4.5 * cm, 3.0 * cm, 3.0 * cm])
                inner.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.2, colors.HexColor("#D1D5DB")),
                    ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ]))
                story.append(inner)
            story.append(Spacer(1, 0.15 * cm))

    # -------- Evidência órfã --------
    orph_att = orphan.get("attendance_dates") or []
    orph_con = orphan.get("content_dates") or []
    if orph_att or orph_con:
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph("Registros fora do horário esperado", styles["DiaryH2"]))
        story.append(Paragraph(
            "Lançamentos detectados em datas SEM expectativa pela grade letiva.",
            styles["DiaryBody"],
        ))
        if orph_att:
            story.append(Paragraph(
                f"<b>Frequência:</b> {', '.join(_fmt_date_br(d) for d in orph_att)}",
                styles["DiaryMeta"],
            ))
        if orph_con:
            story.append(Paragraph(
                f"<b>Conteúdo:</b> {', '.join(_fmt_date_br(d) for d in orph_con)}",
                styles["DiaryMeta"],
            ))

    # -------- Autores e responsabilidade institucional --------
    story.append(PageBreak())
    story.append(Paragraph("Responsabilidade Institucional", styles["DiaryH2"]))
    story.append(Paragraph(
        "Cada pessoa abaixo contribuiu institucionalmente para a construção "
        "deste diário no período registrado. Os tipos de contribuição estão "
        "explicitados — multi-autoria preservada (Fev/2026, §multi-autoria).",
        styles["DiaryBody"],
    ))
    if authors:
        rows = [["Nome", "Papel", "Contribuições"]]
        for a in authors:
            rows.append([
                a.get("full_name", "—")[:40],
                a.get("role", "—") or "—",
                ", ".join(a.get("contribution_types") or [])[:50],
            ])
        t = Table(rows, colWidths=[6 * cm, 3 * cm, 8 * cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E40AF")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.2, colors.HexColor("#D1D5DB")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("<i>Nenhum autor identificado neste período.</i>", styles["DiaryBody"]))

    # -------- Assinaturas institucionais (com tipo de maturidade) --------
    sigs = [s for s in (snap.get("signatures") or []) if s.get("status", "active") == "active"]
    if sigs:
        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph("Assinaturas Institucionais", styles["DiaryH2"]))
        story.append(Paragraph(
            "Cada assinatura abaixo está vinculada criptograficamente ao "
            "hash do documento. Tipos: <b>manual</b> = assinatura física "
            "esperada; <b>image</b> = imagem cadastrada no SIGESC; "
            "<b>icp_brasil</b> = certificado qualificado ICP-Brasil.",
            styles["DiaryMeta"],
        ))
        story.append(Spacer(1, 0.2 * cm))
        for s in sigs:
            sig_type = s.get("signature_type", "manual")
            block = []
            if sig_type == "manual":
                # Linha física para assinatura à caneta
                block.append(Paragraph("_" * 60, styles["DiaryBody"]))
                block.append(Paragraph(
                    f"<b>{s.get('full_name', '—')}</b>", styles["DiaryBody"]))
                block.append(Paragraph(
                    f"{s.get('role', '—')} &nbsp;·&nbsp; "
                    f"Data esperada: {(s.get('signed_at') or '')[:10]}",
                    styles["DiaryMeta"]))
                block.append(Paragraph(
                    "<i>Assinatura física esperada.</i>", styles["DiaryMeta"]))
            elif sig_type == "image":
                block.append(Paragraph(
                    f"<b>{s.get('full_name', '—')}</b> — {s.get('role', '—')}",
                    styles["DiaryBody"]))
                block.append(Paragraph(
                    f"Assinado eletronicamente em {(s.get('signed_at') or '—')[:19]} "
                    f"com imagem institucional (file: {s.get('image_file_id', '—')}).",
                    styles["DiaryMeta"]))
                block.append(Paragraph(
                    "<i>Documento assinado eletronicamente com imagem "
                    "institucional cadastrada no SIGESC. "
                    "Não equivale à assinatura digital qualificada ICP-Brasil.</i>",
                    styles["DiaryMeta"]))
            elif sig_type == "icp_brasil":
                ci = s.get("certificate_info") or {}
                block.append(Paragraph(
                    f"<b>{s.get('full_name', '—')}</b> — {s.get('role', '—')}",
                    styles["DiaryBody"]))
                block.append(Paragraph(
                    f"Assinatura digital qualificada ICP-Brasil "
                    f"em {(s.get('signed_at') or '—')[:19]}.",
                    styles["DiaryMeta"]))
                block.append(Paragraph(
                    f"Cert: {ci.get('subject', '—')} · "
                    f"Emissor: {ci.get('issuer', '—')} · "
                    f"Válido até: {ci.get('valid_until', '—')}",
                    styles["DiaryMeta"]))
            # Hash vinculado (todas as maturidades)
            block.append(Paragraph(
                f"Vínculo ao hash documental: {(s.get('signed_document_hash') or '—')[:32]}…",
                styles["DiaryHashFooter"]))
            for b in block:
                story.append(b)
            story.append(Spacer(1, 0.3 * cm))
    else:
        # Mesmo sem assinaturas cadastradas: sai linha física como fallback.
        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph("Assinatura Institucional", styles["DiaryH2"]))
        story.append(Paragraph("_" * 60, styles["DiaryBody"]))
        story.append(Paragraph(
            "Responsável institucional &nbsp;·&nbsp; Data: ___/___/______",
            styles["DiaryMeta"],
        ))

    # -------- QR público de verificação (Fase 5b — Mai/2026) --------
    # Apenas em snapshots published com token. Embute na ÚLTIMA página
    # ao lado das assinaturas (decisão 5b do owner).
    token = snap.get("verification_token")
    qr_png = _build_qr_image(token)
    if qr_png:
        story.append(Spacer(1, 0.4 * cm))
        qr_url = f"{PUBLIC_VERIFY_BASE}/verify/diary/{token}"
        qr_table = Table(
            [[
                RLImage(BytesIO(qr_png), width=3.0 * cm, height=3.0 * cm),
                Paragraph(
                    "<b>Verificação institucional pública</b><br/>"
                    "Escaneie o QR ao lado com a câmera do celular para "
                    "validar a autenticidade deste documento. A verificação "
                    "confirma: código, escola, turma, período, hash, "
                    "estado e assinaturas — sem expor dados pessoais.<br/>"
                    f"<font size='6' color='#6B7280'>{qr_url}</font>",
                    styles["DiaryMeta"],
                ),
            ]],
            colWidths=[3.5 * cm, 13 * cm],
        )
        qr_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(qr_table)

    # -------- Rodapé com hash institucional --------
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(
        f"Código: {snap.get('code','—')}  ·  "
        f"Schema v{snap.get('schema_version')} / Semantic v{snap.get('semantic_rules_version')} / "
        f"Template {snap.get('template_version')} / Engine v{snap.get('render_engine_version')}",
        styles["DiaryMeta"],
    ))
    story.append(Paragraph(
        f"Emitido em {snap.get('issued_at','—')}  ·  "
        f"Hash documental: {(snap.get('payload_hash_sha256') or '—')[:64]}",
        styles["DiaryHashFooter"],
    ))

    doc.build(story)
    return buf.getvalue()


async def render_diary_handler(job: dict, *, db, public_base_url: str = "") -> dict:
    """Handler registrado para document_type='diary_period'.

    Esperado: `source_snapshot_id` = `diary_snapshots.id` (UUID direto).
    """
    snapshot_id = job.get("source_snapshot_id") or ""
    snap = await db.diary_snapshots.find_one({"id": snapshot_id}, {"_id": 0})
    if not snap:
        raise ValueError(f"SNAPSHOT_NOT_FOUND: {snapshot_id}")
    if snap.get("status") not in ("published", "superseded"):
        # Permite re-render de superseded (auditoria), mas nunca draft.
        if snap.get("status") == "draft":
            raise ValueError("SNAPSHOT_NOT_PUBLISHED: publique antes de renderizar")
        raise ValueError(f"SNAPSHOT_NOT_RENDERABLE: status={snap.get('status')}")

    # Renderiza PDF a partir do payload congelado (NUNCA banco vivo).
    pdf_bytes = _build_pdf_from_snapshot(snap)
    pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()

    klass_name = (((snap.get("payload") or {}).get("class") or {}).get("name") or "turma").replace(" ", "_")
    period = snap.get("period") or {}
    filename = f"diario_{klass_name}_{period.get('from','')}_a_{period.get('to','')}.pdf"

    stored = await store_pdf(
        db,
        pdf_bytes=pdf_bytes,
        filename=filename,
        document_type="diary_period",
        mantenedora_id=snap.get("mantenedora_id"),
        school_id=snap.get("school_id"),
        student_id=None,
    )

    # Anexa em renders[] (diretriz 6 — array, não singular)
    await append_render(
        db,
        snapshot_id=snapshot_id,
        render_id=job.get("id") or stored["file_id"],
        template_version=TEMPLATE_VERSION,
        render_engine_version=RENDER_ENGINE_VERSION,
        generated_file_id=stored["file_id"],
        checksum_sha256=pdf_hash,
        generated_by_user_id=job.get("requested_by_user_id"),
    )

    logger.info(
        "[diary_renderer] job=%s snapshot=%s file=%s sha=%s",
        job.get("id"), snapshot_id, stored["file_id"], pdf_hash[:12]
    )

    return {
        "generated_file_id": stored["file_id"],
        "generated_file_size_bytes": stored["size_bytes"],
        "pdf_hash_sha256": pdf_hash,
    }
