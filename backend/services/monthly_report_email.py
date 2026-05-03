"""Email transacional do Relatório Mensal Executivo (Sprint G3).

Filosofia: NÃO é relatório enviado por email. É GATILHO DE AÇÃO.

Linha de assunto e CTA forçam o gestor a clicar e ver O QUE FAZER agora.
"""
from __future__ import annotations

import os
from typing import Optional

_FRONTEND_URL = os.environ.get("APP_FRONTEND_URL", "https://sigesc.app").rstrip("/")

_RISK_LABEL = {
    "alto": ("ALTO", "#DC2626", "#FEE2E2"),
    "medio": ("MÉDIO", "#D97706", "#FEF3C7"),
    "baixo": ("BAIXO", "#059669", "#D1FAE5"),
}

_MES_NOMES = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
}


def render_monthly_report_email(
    *,
    rede_nome: str,
    year: int,
    month: int,
    risco: str,
    n_escolas_alerta: int,
    bottom3: list[dict],
    acoes_top3: list[dict],
    report_url: str,
    verify_url: Optional[str] = None,
    verification_code: Optional[str] = None,
) -> tuple[str, str, str]:
    """Renderiza assunto + HTML + texto puro do email-gatilho.

    Returns: (subject, html, text)
    """
    risco_norm = risco if risco in _RISK_LABEL else "medio"
    risco_label, risco_color, risco_bg = _RISK_LABEL[risco_norm]
    mes_nome = _MES_NOMES.get(month, str(month))

    # ASSUNTO — gatilho real, não passivo
    if risco_norm == "alto" and n_escolas_alerta > 0:
        subject = f"[AÇÃO URGENTE] {n_escolas_alerta} escolas em risco alto — {mes_nome}/{year}"
    elif risco_norm == "alto":
        subject = f"[AÇÃO URGENTE] Risco alto detectado na rede — {mes_nome}/{year}"
    elif risco_norm == "medio":
        subject = f"[Atenção] Diagnóstico {mes_nome}/{year} — pontos de intervenção identificados"
    else:
        subject = f"[OK] Diagnóstico mensal {mes_nome}/{year} — rede estável"

    # Lista de bottom3 / ações para o corpo
    bottom_html = ""
    for b in bottom3[:3]:
        bottom_html += (
            f'<li style="margin:6px 0;"><b>{b.get("escola") or "—"}</b> '
            f'<span style="color:#6b7280;">— {b.get("alerta") or ""}</span></li>'
        )
    if not bottom_html:
        bottom_html = '<li style="color:#6b7280;">Sem escolas em zona crítica.</li>'

    actions_html = ""
    for a in acoes_top3[:3]:
        prazo = a.get("prazo_dias") or 7
        responsavel = (a.get("responsavel") or "secretario").replace("_", " ")
        actions_html += (
            f'<li style="margin:8px 0;line-height:1.5;">'
            f'<b>{a.get("acao") or "—"}</b><br/>'
            f'<span style="font-size:13px;color:#6b7280;">'
            f'Prazo: {prazo} dias · Responsável: {responsavel}'
            f'</span></li>'
        )

    code_block = ""
    if verification_code and verify_url:
        code_block = f"""
        <p style="margin:24px 0 8px 0;font-size:13px;color:#6b7280;">
          Código de verificação institucional (válido por 30 dias):
        </p>
        <div style="background:#F3F4F6;border:1px solid #E5E7EB;border-radius:8px;padding:12px 16px;font-family:monospace;font-size:15px;font-weight:bold;color:#3730A3;letter-spacing:1px;">
          {verification_code}
        </div>
        <p style="margin:8px 0 0 0;font-size:12px;color:#6b7280;">
          <a href="{verify_url}" style="color:#3730A3;">Validar publicamente em {verify_url}</a>
        </p>"""

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#F3F4F6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#111827;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#F3F4F6;padding:32px 16px;">
    <tr><td align="center">
      <table width="640" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff;border-radius:14px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
        <tr><td style="background:#1d4ed8;padding:24px 32px;color:#ffffff;">
          <div style="font-size:13px;opacity:0.9;letter-spacing:1px;text-transform:uppercase;">Relatório Executivo Mensal</div>
          <div style="font-size:22px;font-weight:700;margin-top:6px;">{mes_nome.capitalize()}/{year}</div>
          <div style="font-size:14px;opacity:0.95;margin-top:4px;">{rede_nome}</div>
        </td></tr>

        <tr><td style="padding:28px 32px 8px 32px;">
          <div style="display:inline-block;background:{risco_bg};color:{risco_color};font-weight:700;font-size:13px;padding:6px 14px;border-radius:999px;letter-spacing:0.5px;text-transform:uppercase;">
            Nível de risco · {risco_label}
          </div>
        </td></tr>

        <tr><td style="padding:16px 32px 0 32px;">
          <h2 style="margin:0 0 10px 0;font-size:18px;color:#111827;">Escolas em zona crítica</h2>
          <ul style="margin:0 0 16px 20px;padding:0;font-size:14px;color:#374151;">
            {bottom_html}
          </ul>
        </td></tr>

        <tr><td style="padding:8px 32px 0 32px;">
          <h2 style="margin:0 0 10px 0;font-size:18px;color:#111827;">3 ações prioritárias para esta semana</h2>
          <ol style="margin:0 0 8px 20px;padding:0;font-size:14px;color:#374151;">
            {actions_html}
          </ol>
        </td></tr>

        <tr><td style="padding:24px 32px 8px 32px;">
          <table cellpadding="0" cellspacing="0" border="0">
            <tr><td style="background:#1d4ed8;border-radius:10px;">
              <a href="{report_url}" style="display:inline-block;padding:14px 28px;color:#ffffff;text-decoration:none;font-weight:700;font-size:15px;letter-spacing:0.3px;">
                Abrir diagnóstico completo →
              </a>
            </td></tr>
          </table>
        </td></tr>

        <tr><td style="padding:8px 32px 24px 32px;">
          {code_block}
        </td></tr>

        <tr><td style="background:#F9FAFB;padding:16px 32px;border-top:1px solid #E5E7EB;font-size:12px;color:#6B7280;line-height:1.5;">
          Este relatório foi gerado automaticamente e está assinado digitalmente
          (SHA256 + HMAC). É uma mensagem automática — não responda.
          <br/>
          {rede_nome} · SIGESC · Sistema Integrado de Gestão Escolar
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    text = f"""SIGESC — Relatório Executivo Mensal · {mes_nome}/{year}
{rede_nome}

NÍVEL DE RISCO: {risco_label}

Escolas em zona crítica:
""" + "\n".join(
        f"- {b.get('escola') or '—'} — {b.get('alerta') or ''}"
        for b in bottom3[:3]
    ) + """

3 ações prioritárias para esta semana:
""" + "\n".join(
        f"{i}. {a.get('acao') or '—'} (prazo: {a.get('prazo_dias') or 7} dias · {(a.get('responsavel') or 'secretario').replace('_',' ')})"
        for i, a in enumerate(acoes_top3[:3], 1)
    ) + f"""

Abrir diagnóstico completo: {report_url}
"""
    if verification_code and verify_url:
        text += f"""
Código de verificação institucional (válido por 30 dias): {verification_code}
Validar em: {verify_url}
"""
    text += """
---
Este relatório está assinado digitalmente (SHA256 + HMAC).
SIGESC · Mensagem automática. Não responda."""

    return subject, html, text


def report_url_for(report_id: str) -> str:
    return f"{_FRONTEND_URL}/admin/relatorios-mensais/{report_id}"


def verify_url_for(code: str) -> str:
    return f"{_FRONTEND_URL}/verificar/{code}"
