"""Recibo oficial (PDF) da Transferência Institucional — com QR verificável.

Gera um documento A4 com os campos mínimos exigidos (protocolo, origem,
destino, turmas, alunos, operador, justificativa, data/hora) e um rodapé de
verificação pública (código humano + QR apontando para `/v/{token}`).
"""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from pdf.verification_footer import build_verification_flowables


def _fmt_dt(iso) -> str:
    if not iso:
        return "—"
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", ""))
        return d.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(iso)[:16]


def build_transfer_receipt_pdf(*, audit: dict, origin: dict | None, destination: dict | None,
                               code: str, token: str) -> bytes:
    buf = io.BytesIO()
    protocol = audit.get("protocol") or "—"
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=2 * cm, bottomMargin=1.5 * cm,
        leftMargin=2 * cm, rightMargin=2 * cm, title=f"Recibo {protocol}",
    )
    styles = getSampleStyleSheet()
    h = ParagraphStyle("H", parent=styles["Title"], fontSize=16, textColor=colors.HexColor("#1E3A8A"))
    sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#6B7280"))
    label = ParagraphStyle("l", parent=styles["Normal"], fontSize=9.5, textColor=colors.HexColor("#374151"), leading=13)

    is_rollback = audit.get("status") == "rolled_back"
    story = []
    story.append(Paragraph(
        "Recibo de Reversão de Transferência Institucional" if is_rollback
        else "Recibo de Transferência Institucional", h))
    story.append(Paragraph("SIGESC — Sistema Integrado de Gestão Escolar", sub))
    story.append(Spacer(1, 0.6 * cm))

    counts = audit.get("counts") or {}
    status_label = {"executed": "Executada", "rolled_back": "Revertida"}.get(audit.get("status"), audit.get("status") or "—")
    rows = [
        ("Protocolo", protocol),
        ("Status", status_label),
        ("Escola de origem", (origin or {}).get("name") or audit.get("origin_school_id")),
        ("Escola de destino", (destination or {}).get("name") or audit.get("destination_school_id")),
        ("Turmas transferidas", str(counts.get("classes", len(audit.get("class_ids") or [])))),
        ("Alunos afetados", str(counts.get("students_distinct", counts.get("students", "—")))),
        ("Matrículas", str(counts.get("enrollments", "—"))),
        ("Operador", (audit.get("executed_by") or {}).get("email") or "—"),
        ("Data/hora da execução", _fmt_dt(audit.get("executed_at"))),
        ("Justificativa", audit.get("reason") or "—"),
    ]
    if is_rollback:
        rb = audit.get("rollback") or {}
        rows += [
            ("Protocolo de reversão", rb.get("protocol") or "—"),
            ("Revertido por", (rb.get("rolled_back_by") or {}).get("email") or "—"),
            ("Data/hora da reversão", _fmt_dt(rb.get("rolled_back_at"))),
            ("Justificativa da reversão", rb.get("reason") or "—"),
            ("Escola origem reaberta", "Sim" if rb.get("origin_reopened") else "Não"),
        ]

    data = [[Paragraph(f"<b>{k}</b>", label), Paragraph(str(v), label)] for k, v in rows]
    t = Table(data, colWidths=[5.5 * cm, 11 * cm])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E5E7EB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3F4F6")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.8 * cm))
    story.extend(build_verification_flowables(
        code, None, label="Verificação de Autenticidade do Recibo", verification_token=token))

    doc.build(story)
    return buf.getvalue()
