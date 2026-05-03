"""Gera PDFs auditáveis a partir de snapshots IA (Sprint G1.5).

Duas versões:
  - 'executive': resumo + análise + ações + hash + rodapé de verificação
  - 'auditor': tudo acima + evidências completas + payload_snapshot (anexo)

Usa reportlab (já instalado). Retorna bytes do PDF.
"""
from __future__ import annotations

import io
import json
import os
from datetime import datetime
from typing import Literal

import segno
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Preformatted, Image,
)
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER

FrontendURL = os.environ.get("APP_FRONTEND_URL", "https://sigesc.app").rstrip("/")


def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(
        "SigescTitle", parent=s["Heading1"], fontSize=18, leading=22,
        textColor=colors.HexColor("#3730A3"), spaceAfter=12,
    ))
    s.add(ParagraphStyle(
        "SigescH2", parent=s["Heading2"], fontSize=13, leading=16,
        textColor=colors.HexColor("#1F2937"), spaceBefore=10, spaceAfter=6,
    ))
    s.add(ParagraphStyle(
        "SigescBody", parent=s["BodyText"], fontSize=10, leading=14,
        alignment=TA_JUSTIFY, spaceAfter=6,
    ))
    s.add(ParagraphStyle(
        "SigescMeta", parent=s["BodyText"], fontSize=8, leading=11,
        textColor=colors.HexColor("#6B7280"),
    ))
    s.add(ParagraphStyle(
        "SigescHash", parent=s["BodyText"], fontSize=7, leading=10,
        fontName="Courier", textColor=colors.HexColor("#374151"),
    ))
    return s


def _format_iso(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M:%S UTC")
    except Exception:
        return iso_str


def _evidence_table(items, styles):
    if not items:
        return Paragraph(
            '<font color="#9CA3AF">Sem evidências estruturadas.</font>',
            styles["SigescMeta"],
        )
    data = [["Métrica", "Valor", "Fonte (campo no payload)"]]
    for e in items:
        data.append([
            Paragraph(str(e.get("metrica") or "—"), styles["SigescBody"]),
            Paragraph(str(e.get("valor") or "—"), styles["SigescBody"]),
            Paragraph(
                f'<font name="Courier" size="8">{e.get("fonte") or "—"}</font>',
                styles["SigescBody"],
            ),
        ])
    t = Table(data, colWidths=[5 * cm, 4 * cm, 7 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2FF")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#3730A3")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _action_block(action, styles):
    lines = [
        Paragraph(
            f"<b>#{action.get('ordem')} · Prioridade {action.get('prioridade')} "
            f"· Impacto {action.get('impacto')}</b> — {action.get('titulo') or ''}",
            styles["SigescBody"],
        )
    ]
    desc = action.get("descricao_ia") or action.get("descricao") or ""
    if desc:
        lines.append(Paragraph(desc, styles["SigescBody"]))
    if action.get("metrica_sucesso"):
        lines.append(Paragraph(
            f"<i>Métrica de sucesso:</i> {action['metrica_sucesso']}",
            styles["SigescMeta"],
        ))
    return lines


def _qr_png_bytes(url: str, size_cm: float = 3.0) -> io.BytesIO:
    """Gera QR code PNG a partir de uma URL. Retorna BytesIO pronto p/ reportlab."""
    qr = segno.make(url, error="H")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=8, border=2)
    buf.seek(0)
    return buf


def _integrity_block(doc, styles):
    code = doc.get("verification_code") or ""
    verify_url_public = (
        f"{FrontendURL}/verificar/{code}" if code
        else f"{FrontendURL}/api/snapshots/{doc['id']}/verify"
    )

    # QR Code (se tiver código público)
    qr_image = None
    if code:
        try:
            qr_png = _qr_png_bytes(verify_url_public)
            qr_image = Image(qr_png, width=3 * cm, height=3 * cm)
        except Exception:
            qr_image = None

    header_bits = [
        Paragraph("<b>Selo de integridade</b>", styles["SigescH2"]),
        Paragraph(
            "Este documento pode ser validado publicamente sem login. "
            "Escaneie o QR Code ou digite o código no portal oficial.",
            styles["SigescMeta"],
        ),
        Spacer(1, 4),
    ]

    if code:
        # Bloco destacado com código + QR lado a lado
        verify_box = Table(
            [[
                [
                    Paragraph("<b>Código de verificação</b>", styles["SigescMeta"]),
                    Paragraph(
                        f'<font name="Courier-Bold" size="14" color="#3730A3">{code}</font>',
                        styles["SigescMeta"],
                    ),
                    Spacer(1, 6),
                    Paragraph("<b>Portal:</b>", styles["SigescMeta"]),
                    Paragraph(
                        f'<font name="Courier" size="9">{FrontendURL}/verificar</font>',
                        styles["SigescMeta"],
                    ),
                    Spacer(1, 4),
                    Paragraph(
                        "Digite o código acima ou escaneie o QR Code ao lado "
                        "para confirmar a autenticidade e integridade deste documento.",
                        styles["SigescMeta"],
                    ),
                ],
                qr_image or Paragraph("—", styles["SigescMeta"]),
            ]],
            colWidths=[10 * cm, 3.5 * cm],
        )
        verify_box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF2FF")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#6366F1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        header_bits.append(verify_box)
        header_bits.append(Spacer(1, 8))

    detail_bits = [
        Paragraph(f"<b>ID do snapshot:</b> {doc.get('id')}", styles["SigescMeta"]),
        Paragraph(f"<b>Emitido em:</b> {_format_iso(doc.get('created_at') or '')}", styles["SigescMeta"]),
        Paragraph(f"<b>Modelo:</b> {doc.get('model') or '—'}", styles["SigescMeta"]),
        Paragraph(f"<b>Versão:</b> {doc.get('version')}", styles["SigescMeta"]),
        Paragraph(f"<b>Criado por:</b> {(doc.get('created_by') or {}).get('email') or '—'} "
                  f"({(doc.get('created_by') or {}).get('role') or '—'})",
                  styles["SigescMeta"]),
        Spacer(1, 4),
        Paragraph("<b>Hash público (SHA256):</b>", styles["SigescMeta"]),
        Preformatted(doc.get("public_hash") or "—", styles["SigescHash"]),
        Paragraph("<b>Assinatura do servidor (HMAC-SHA256):</b>", styles["SigescMeta"]),
        Preformatted(doc.get("server_signature") or "não disponível", styles["SigescHash"]),
    ]
    return header_bits + detail_bits


def build_pdf(doc: dict, *, mode: Literal["executive", "auditor"] = "executive") -> bytes:
    """Gera PDF auditável de um snapshot.

    Mode 'executive': público-alvo gestor (resumo + ações + selo).
    Mode 'auditor': inclui evidências completas + payload_snapshot cru em anexo.
    """
    styles = _styles()
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title=f"SIGESC Snapshot {doc.get('id', '')[:8]}",
    )

    ai = doc.get("ai_output") or {}
    payload = doc.get("payload_snapshot") or {}

    entity_label = {
        "escola": "Escola",
        "rede": "Rede",
        "secretaria": "Secretaria",
    }.get(doc.get("entity_type"), doc.get("entity_type") or "—")
    title_analysis = {
        "plano_acao": "Plano de Ação Automático",
        "relatorio_mensal": "Relatório Executivo Mensal",
    }.get(doc.get("analysis_type"), doc.get("analysis_type") or "Análise")

    story = []
    # Cabeçalho
    story.append(Paragraph(f"SIGESC · {title_analysis}", styles["SigescTitle"]))
    story.append(Paragraph(
        f"<b>{entity_label}:</b> {payload.get('school_name') or doc.get('entity_id')}"
        f" · <b>Período:</b> {payload.get('period') or '—'}"
        f" · <b>Modo:</b> {'EXECUTIVO' if mode == 'executive' else 'AUDITOR'}",
        styles["SigescMeta"],
    ))
    story.append(Spacer(1, 10))

    # Resumo executivo
    story.append(Paragraph("1. Análise executiva", styles["SigescH2"]))
    if ai.get("analise_executiva"):
        story.append(Paragraph(ai["analise_executiva"], styles["SigescBody"]))
    else:
        story.append(Paragraph(
            "<i>Análise executiva indisponível neste snapshot.</i>",
            styles["SigescMeta"],
        ))

    # Evidências analise
    story.append(Paragraph("Evidências — análise executiva", styles["SigescH2"]))
    story.append(_evidence_table(ai.get("analise_evidencias") or [], styles))
    story.append(Spacer(1, 8))

    # Insight histórico
    story.append(Paragraph("2. Histórico do gestor (90 dias)", styles["SigescH2"]))
    if ai.get("insight_historico"):
        story.append(Paragraph(ai["insight_historico"], styles["SigescBody"]))
    story.append(_evidence_table(ai.get("insight_evidencias") or [], styles))
    story.append(Spacer(1, 8))

    # Ações determinísticas + enriquecidas
    story.append(Paragraph("3. Ações recomendadas", styles["SigescH2"]))
    # Reconstitui 'acoes' a partir de payload_snapshot.acoes se existir
    acoes = payload.get("acoes") or []
    if acoes:
        for a in acoes:
            for b in _action_block(a, styles):
                story.append(b)
            story.append(Spacer(1, 3))
    else:
        story.append(Paragraph(
            "<i>Nenhuma ação determinística registrada.</i>",
            styles["SigescMeta"],
        ))

    # Recomendações extras IA
    extras = ai.get("recomendacoes_extra") or []
    if extras:
        story.append(Paragraph("4. Recomendações extras (IA)", styles["SigescH2"]))
        for i, r in enumerate(extras, 1):
            story.append(Paragraph(
                f"<b>{i}.</b> <b>{r.get('titulo') or ''}</b> · "
                f"Prioridade {r.get('prioridade')} · Impacto {r.get('impacto')} "
                f"· {r.get('prazo_dias')} dias · Responsável: {r.get('responsavel')}",
                styles["SigescBody"],
            ))
            if r.get("descricao"):
                story.append(Paragraph(r["descricao"], styles["SigescBody"]))
            if r.get("metrica_sucesso"):
                story.append(Paragraph(
                    f"<i>Métrica de sucesso:</i> {r['metrica_sucesso']}",
                    styles["SigescMeta"],
                ))
            # evidências (apenas modo auditor mostra tabela; executivo mostra inline)
            if mode == "auditor":
                story.append(_evidence_table(r.get("baseado_em") or [], styles))
            elif r.get("baseado_em"):
                ev = " · ".join(
                    f"{e.get('metrica')}: {e.get('valor')}"
                    for e in r["baseado_em"]
                )
                story.append(Paragraph(
                    f'<font color="#6366F1">Baseado em: {ev}</font>',
                    styles["SigescMeta"],
                ))
            story.append(Spacer(1, 3))

    story.append(Spacer(1, 16))
    # Selo de integridade
    for b in _integrity_block(doc, styles):
        story.append(b)

    # Anexo técnico (modo auditor)
    if mode == "auditor":
        story.append(PageBreak())
        story.append(Paragraph("Anexo A · Payload técnico (dados congelados)", styles["SigescTitle"]))
        story.append(Paragraph(
            "Abaixo estão os dados operacionais exatamente como existiam no "
            "momento da análise. Qualquer reprodução do hash público deve "
            "usar este payload como entrada.",
            styles["SigescMeta"],
        ))
        story.append(Spacer(1, 6))
        story.append(Preformatted(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)[:12000],
            styles["SigescHash"],
        ))

    pdf.build(story)
    return buf.getvalue()
