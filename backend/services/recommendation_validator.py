"""Camada de governança da IA — Validador de Recomendações (Mai/2026).

Filosofia: a IA gera livremente → este validador intercepta → limpa/ajusta
→ entrega ao usuário SOMENTE recomendações executáveis no SIGESC atual.

Reutilizável em qualquer fluxo que recebe ações sugeridas pela IA:
- Plano de Ação (PMPI-GE)
- Relatório Mensal Executivo (G3)
- Análise Preditiva por escola
- Futuras integrações com IA

Princípios:
1. Bloqueio é semântico (palavras-chave + rotas) — não só URL.
2. Capacidade desconhecida = bloquear (postura conservadora).
3. Toda rejeição é LOGADA para evolução contínua do prompt.
4. Lista nunca volta vazia: aplica fallback operacional humano.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from core.recommendation_map import RECOMMENDATION_CAPABILITY_MAP
from core.system_capabilities import feature_exists

logger = logging.getLogger(__name__)

# Campos textuais comuns onde a IA pode citar a feature/rota inexistente
_TEXT_FIELDS = ("acao", "titulo", "descricao", "justificativa", "metrica_sucesso")

_FALLBACK_RECOMMENDATION = {
    "acao": "Realizar análise manual com a equipe pedagógica",
    "titulo": "Análise manual com equipe",
    "justificativa": (
        "Sem recomendações automáticas executáveis para o contexto atual. "
        "Conduzir reunião de coordenação para definir intervenção humana."
    ),
    "descricao": (
        "Sem recomendações automáticas executáveis para o contexto atual. "
        "Conduzir reunião de coordenação para definir intervenção humana."
    ),
    "responsavel": "coordenador",
    "prazo_dias": 7,
    "impacto": "medio",
    "prioridade": 3,
    "escolas_alvo": [],
    "metrica_sucesso": "Ata da reunião registrada",
    "_fallback": True,
}


def _gather_text(rec: dict) -> str:
    """Concatena os campos textuais relevantes em lower-case para busca."""
    parts = []
    for k in _TEXT_FIELDS:
        v = rec.get(k)
        if isinstance(v, str):
            parts.append(v)
    return " ".join(parts).lower()


def _violates_capability(rec: dict) -> Optional[str]:
    """Retorna o nome da capability bloqueada se a recomendação violar
    o registry, senão None.
    """
    text = _gather_text(rec)
    for rule in RECOMMENDATION_CAPABILITY_MAP:
        # Match por keyword (substring)
        kws = rule.get("keywords") or []
        if any(kw in text for kw in kws):
            cap = rule["capability"]
            if not feature_exists(cap):
                return cap
        # Match por route hint
        routes = rule.get("route_hints") or []
        if any(r in text for r in routes):
            cap = rule["capability"]
            if not feature_exists(cap):
                return cap
    return None


def validate_recommendations(
    recommendations: list[dict],
    *,
    context: str = "default",
    apply_fallback: bool = True,
) -> list[dict]:
    """Filtra recomendações que dependem de capacidades inexistentes.

    Args:
        recommendations: lista de dicts da IA (acao, justificativa, ...)
        context: identificador do fluxo (ex.: "plano_acao", "g3_monthly")
            usado apenas em logs.
        apply_fallback: se True e a lista resultante for vazia, devolve uma
            recomendação operacional humana de fallback.

    Returns:
        Lista de recomendações válidas. Pode ter o fallback como única entrada.
    """
    if not isinstance(recommendations, list):
        logger.warning("[ai-firewall:%s] entrada não é lista: %r", context, type(recommendations))
        return [_FALLBACK_RECOMMENDATION] if apply_fallback else []

    valid: list[dict] = []
    rejected: list[tuple[str, dict]] = []

    for rec in recommendations:
        if not isinstance(rec, dict):
            continue
        cap = _violates_capability(rec)
        if cap is None:
            valid.append(rec)
        else:
            rejected.append((cap, rec))

    if rejected:
        for cap, rec in rejected:
            short = (rec.get("acao") or rec.get("titulo") or "")[:120]
            logger.warning(
                "[ai-firewall:%s] BLOCKED capability=%s acao=%r",
                context, cap, short,
            )

    if not valid and apply_fallback:
        return [dict(_FALLBACK_RECOMMENDATION)]

    return valid


# ---------------------- Helpers públicos para testabilidade ----------------------

def reason_for_block(rec: dict) -> Optional[str]:
    """API pública: retorna o nome da capacidade que bloqueia a rec, ou None."""
    return _violates_capability(rec)


def fallback_recommendation() -> dict:
    """API pública: retorna uma cópia do fallback humano padrão."""
    return dict(_FALLBACK_RECOMMENDATION)
