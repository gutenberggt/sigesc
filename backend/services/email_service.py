"""
Serviço de envio de e-mails transacionais via Resend.
"""
import os
import asyncio
import logging
from typing import Optional

import resend

logger = logging.getLogger(__name__)

_API_KEY = os.environ.get('RESEND_API_KEY')
_SENDER_EMAIL = os.environ.get('RESEND_SENDER_EMAIL')
_SENDER_NAME = os.environ.get('RESEND_SENDER_NAME', 'SIGESC')

if _API_KEY:
    resend.api_key = _API_KEY


def _from_address() -> str:
    if _SENDER_NAME:
        return f"{_SENDER_NAME} <{_SENDER_EMAIL}>"
    return _SENDER_EMAIL or ''


async def send_email(
    to: str,
    subject: str,
    html: str,
    text: Optional[str] = None,
) -> dict:
    """Envia e-mail via Resend de forma não-bloqueante.

    Returns: {"success": bool, "id": str|None, "error": str|None}
    """
    if not _API_KEY or not _SENDER_EMAIL:
        logger.error("Resend não configurado (RESEND_API_KEY/RESEND_SENDER_EMAIL ausentes)")
        return {"success": False, "id": None, "error": "Email service not configured"}

    params = {
        "from": _from_address(),
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if text:
        params["text"] = text

    try:
        result = await asyncio.to_thread(resend.Emails.send, params)
        return {"success": True, "id": result.get("id"), "error": None}
    except Exception as e:
        logger.exception("Falha ao enviar e-mail via Resend")
        return {"success": False, "id": None, "error": str(e)}


def render_email_change_confirmation(
    full_name: str,
    new_email: str,
    confirm_url: str,
    requested_at_human: str,
    ip: str,
    mantenedora_nome: str = "SIGESC",
) -> tuple[str, str]:
    """Renderiza HTML + texto puro do e-mail de confirmação de troca de email.

    Returns: (html, plain_text)
    """
    safe_name = full_name or 'Usuário(a)'
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#111827;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f3f4f6;padding:32px 16px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
        <tr><td style="background:#1d4ed8;padding:24px 32px;color:#ffffff;">
          <div style="font-size:20px;font-weight:700;letter-spacing:0.5px;">SIGESC</div>
          <div style="font-size:13px;opacity:0.9;margin-top:2px;">Sistema Integrado de Gestão Escolar</div>
        </td></tr>
        <tr><td style="padding:32px;">
          <h2 style="margin:0 0 16px 0;font-size:20px;color:#111827;">Olá, {safe_name}.</h2>
          <p style="margin:0 0 16px 0;font-size:15px;line-height:1.55;color:#374151;">
            Recebemos uma solicitação para alterar o e-mail da sua conta no SIGESC para este endereço (<strong>{new_email}</strong>).
          </p>
          <p style="margin:0 0 24px 0;font-size:15px;line-height:1.55;color:#374151;">
            Para confirmar a alteração, clique no botão abaixo. <strong>O link expira em 30 minutos.</strong>
          </p>
          <table cellpadding="0" cellspacing="0" border="0" style="margin:0 0 24px 0;">
            <tr><td style="background:#10b981;border-radius:8px;">
              <a href="{confirm_url}" style="display:inline-block;padding:14px 28px;color:#ffffff;text-decoration:none;font-weight:600;font-size:15px;">
                ✓ Confirmar novo e-mail
              </a>
            </td></tr>
          </table>
          <p style="margin:0 0 8px 0;font-size:13px;color:#6b7280;">Se o botão não funcionar, copie e cole o link no navegador:</p>
          <p style="margin:0 0 24px 0;font-size:13px;word-break:break-all;background:#f9fafb;padding:12px;border-radius:6px;border:1px solid #e5e7eb;color:#374151;">
            {confirm_url}
          </p>
          <h3 style="margin:24px 0 8px 0;font-size:15px;color:#111827;">O que acontece após a confirmação?</h3>
          <ul style="margin:0 0 16px 20px;padding:0;font-size:14px;line-height:1.6;color:#374151;">
            <li>Seu e-mail de acesso passa a ser <strong>{new_email}</strong>.</li>
            <li>Se você é servidor cadastrado, o e-mail no seu cadastro funcional também será atualizado automaticamente.</li>
            <li>Sua senha <strong>não</strong> é alterada.</li>
          </ul>
          <h3 style="margin:24px 0 8px 0;font-size:15px;color:#111827;">Não foi você?</h3>
          <p style="margin:0 0 16px 0;font-size:14px;line-height:1.6;color:#374151;">
            Se você não solicitou esta alteração, <strong>ignore este e-mail</strong> — nenhuma mudança será feita. Recomendamos também alterar a senha da sua conta acessando o SIGESC.
          </p>
        </td></tr>
        <tr><td style="background:#f9fafb;padding:16px 32px;border-top:1px solid #e5e7eb;font-size:12px;color:#6b7280;line-height:1.5;">
          Solicitado em {requested_at_human} · IP {ip}<br/>
          {mantenedora_nome} · Esta é uma mensagem automática. Não responda.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    text = f"""SIGESC — Sistema Integrado de Gestão Escolar

Olá, {safe_name}.

Recebemos uma solicitação para alterar o e-mail da sua conta no SIGESC
para este endereço ({new_email}).

Para confirmar a alteração, acesse o link abaixo (expira em 30 minutos):

{confirm_url}

O que acontece após a confirmação?
- Seu e-mail de acesso passa a ser {new_email}.
- Se você é servidor cadastrado, o e-mail do seu cadastro funcional
  será atualizado automaticamente.
- Sua senha não é alterada.

Não foi você?
Se não solicitou esta alteração, ignore este e-mail — nenhuma mudança
será feita. Recomendamos alterar a senha da sua conta no SIGESC.

---
Solicitado em {requested_at_human} · IP {ip}
{mantenedora_nome} · Mensagem automática. Não responda.
"""
    return html, text
