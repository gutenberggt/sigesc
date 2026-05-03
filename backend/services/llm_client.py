"""LLM client unificado SIGESC (Mai/2026).

Estratégia híbrida:
- ANTHROPIC_API_KEY definido → SDK oficial `anthropic` (deploy externo, ex: Coolify)
- Senão, EMERGENT_LLM_KEY → `emergentintegrations` (preview/deploy Emergent)
- Nenhum dos dois → retorna None (callers usam fallback determinístico)

Apenas Claude (modelo padrão: claude-sonnet-4-5-20250929). Não suporta
streaming nem multimodal — apenas texto único system+user → texto.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
DEFAULT_MAX_TOKENS = 4096


def _has_anthropic_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _has_emergent_key() -> bool:
    return bool(os.environ.get("EMERGENT_LLM_KEY"))


def llm_provider() -> str:
    """Retorna o nome do provider que será usado, para logging/diagnóstico."""
    if _has_anthropic_key():
        return "anthropic_direct"
    if _has_emergent_key():
        return "emergent_universal"
    return "none"


async def chat_with_claude(
    *,
    system_prompt: str,
    user_text: str,
    session_id: str,
    model: str = DEFAULT_MODEL,
    timeout_s: int = 60,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> Optional[str]:
    """Envia uma mensagem síncrona ao Claude e retorna texto puro.

    Retorna None se nenhuma key está configurada ou se a chamada falhou
    (timeout, erro de API). Callers devem implementar fallback.
    """
    if _has_anthropic_key():
        return await _call_anthropic_direct(
            system_prompt=system_prompt,
            user_text=user_text,
            model=model,
            timeout_s=timeout_s,
            max_tokens=max_tokens,
        )
    if _has_emergent_key():
        return await _call_emergent(
            system_prompt=system_prompt,
            user_text=user_text,
            session_id=session_id,
            model=model,
            timeout_s=timeout_s,
        )
    logger.warning("[llm] Nenhuma key configurada (ANTHROPIC_API_KEY ou EMERGENT_LLM_KEY)")
    return None


async def _call_anthropic_direct(
    *, system_prompt: str, user_text: str, model: str, timeout_s: int, max_tokens: int,
) -> Optional[str]:
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        logger.error("[llm] biblioteca 'anthropic' não instalada — impossível usar ANTHROPIC_API_KEY")
        return None

    api_key = os.environ["ANTHROPIC_API_KEY"]
    client = AsyncAnthropic(api_key=api_key, timeout=float(timeout_s))
    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_text}],
            ),
            timeout=timeout_s + 5,
        )
        # response.content é uma lista de blocos; pega o texto do primeiro
        if response.content and hasattr(response.content[0], "text"):
            return response.content[0].text
        return None
    except asyncio.TimeoutError:
        logger.warning("[llm] timeout direct anthropic")
        return None
    except Exception as e:
        logger.warning("[llm] erro direct anthropic: %s", e)
        return None


async def _call_emergent(
    *, system_prompt: str, user_text: str, session_id: str, model: str, timeout_s: int,
) -> Optional[str]:
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except ImportError:
        logger.error("[llm] emergentintegrations indisponível")
        return None

    api_key = os.environ["EMERGENT_LLM_KEY"]
    chat = (
        LlmChat(api_key=api_key, session_id=session_id, system_message=system_prompt)
        .with_model("anthropic", model)
    )
    msg = UserMessage(text=user_text)
    try:
        return await asyncio.wait_for(chat.send_message(msg), timeout=timeout_s)
    except asyncio.TimeoutError:
        logger.warning("[llm] timeout emergent")
        return None
    except Exception as e:
        logger.warning("[llm] erro emergent: %s", e)
        return None
