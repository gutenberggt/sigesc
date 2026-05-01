"""
Corretor ortográfico/gramatical PT-BR via LanguageTool.

Proxy simples que recebe o texto do frontend e repassa para a API pública
do LanguageTool (https://api.languagetool.org/v2/check). A API pública é
gratuita com limite de 20 req/min por IP e 20.000 caracteres por chamada —
suficiente para uso escolar. Caso a prefeitura extrapole, basta subir um
container LanguageTool e apontar a env LANGUAGETOOL_URL para o novo endpoint.

Request body:
    {"text": str, "language": "pt-BR"}  # language é opcional (default pt-BR)

Response body (payload simplificado):
    {
      "matches": [
        {
          "message": str,
          "offset": int,
          "length": int,
          "replacements": [str, ...],   # aplainado: só os valores
          "rule_id": str,
          "category": str,
          "issue_type": str             # "misspelling" | "grammar" | "style" | ...
        }, ...
      ],
      "total": int,
      "language": "pt-BR"
    }
"""
from __future__ import annotations

import os
import logging
import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from auth_middleware import AuthMiddleware

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Corretor Ortográfico"])

LANGUAGETOOL_URL = os.environ.get(
    "LANGUAGETOOL_URL", "https://api.languagetool.org/v2/check"
)
MAX_TEXT_LENGTH = 20_000  # limite da API pública


class SpellCheckRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH)
    language: str = Field(default="pt-BR")


def setup_router(db=None, **kwargs):

    @router.post("/spellcheck")
    async def spellcheck(payload: SpellCheckRequest, request: Request):
        """Corrige ortografia e gramática PT-BR. Requer autenticação."""
        # Qualquer usuário autenticado pode usar o corretor.
        await AuthMiddleware.get_current_user(request)

        # Whitelist: apenas pt-BR e pt-PT (foco do sistema é PT-BR).
        lang = payload.language if payload.language in ("pt-BR", "pt-PT") else "pt-BR"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    LANGUAGETOOL_URL,
                    data={
                        "text": payload.text,
                        "language": lang,
                        # Desabilita regras pedantes que geram ruído em textos escolares.
                        "disabledRules": "WHITESPACE_RULE,UPPERCASE_SENTENCE_START",
                    },
                    headers={"User-Agent": "SIGESC-Spellchecker/1.0"},
                )
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=504,
                detail="Corretor demorou para responder. Tente novamente em instantes.",
            )
        except Exception as e:
            logger.error(f"Falha ao chamar LanguageTool: {e}")
            raise HTTPException(status_code=502, detail="Serviço de correção indisponível.")

        if resp.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail="Limite de requisições atingido. Aguarde alguns segundos.",
            )
        if resp.status_code >= 400:
            logger.error(f"LanguageTool {resp.status_code}: {resp.text[:200]}")
            raise HTTPException(status_code=502, detail="Serviço de correção retornou erro.")

        raw = resp.json()
        matches = []
        for m in raw.get("matches", []):
            rule = m.get("rule") or {}
            matches.append({
                "message": m.get("message", ""),
                "short_message": m.get("shortMessage", ""),
                "offset": m.get("offset", 0),
                "length": m.get("length", 0),
                "replacements": [r.get("value", "") for r in m.get("replacements", [])][:8],
                "rule_id": rule.get("id", ""),
                "category": (rule.get("category") or {}).get("name", ""),
                "issue_type": (rule.get("issueType") or "other"),
                "context": (m.get("context") or {}).get("text", ""),
            })

        return {
            "matches": matches,
            "total": len(matches),
            "language": lang,
        }

    return router
