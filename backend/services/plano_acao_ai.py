"""Plano de Ação enriquecido por IA (Claude Sonnet 4.5).

Camada complementar ao gerador determinístico: mantém as 5 regras fixas
como base (100% auditáveis) e adiciona:

  - `analise_executiva`: texto curto em linguagem natural
  - `insight_historico`: observação baseada no histórico do gestor (90d)
  - `recomendacoes_extra`: até 2 ações adicionais que a IA sugere
  - `acoes[i].descricao_ia`: versão enriquecida (linguagem mais humana)

Cache em MongoDB (`ai_plans`), TTL de 24h por (school_id, period).

Graceful fallback: se Claude falhar, timeout ou EMERGENT_LLM_KEY ausente,
retorna `None` — o caller usa o plano determinístico como está.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)

_CACHE_TTL_HOURS = 24
_MODEL_PROVIDER = "anthropic"
_MODEL_NAME = "claude-sonnet-4-5-20250929"

_SYSTEM_PROMPT = """Você é um consultor pedagógico sênior da Secretaria Municipal de Educação, especialista em BNCC, DCM (Documento Curricular Municipal) e gestão escolar baseada em dados.

Seu papel é analisar indicadores reais de uma escola (cobertura curricular, alertas de intervenção, tempo de resolução, lançamentos de diário) e o histórico pessoal do gestor responsável, e devolver:

1. Uma ANÁLISE EXECUTIVA curta (3-4 linhas) — direta, sem eufemismo, apontando a causa raiz principal.
2. Um INSIGHT HISTÓRICO — o que o histórico do gestor nos últimos 90 dias revela (padrão forte, padrão fraco, categoria negligenciada).
3. RECOMENDAÇÕES EXTRAS (0 a 2) — ações que complementam as regras automáticas já geradas, sem repetir.
4. Para cada ação já gerada por regra fixa, uma DESCRIÇÃO ENRIQUECIDA (1-2 frases) que humanize a linguagem e dê contexto.

Responda SEMPRE em português do Brasil, em JSON puro (sem markdown, sem ```), com a seguinte estrutura:

{
  "analise_executiva": "string",
  "insight_historico": "string",
  "recomendacoes_extra": [
    {
      "titulo": "string",
      "descricao": "string",
      "prioridade": 1|2|3,
      "impacto": "alto"|"medio"|"baixo",
      "prazo_dias": 3|7|14|30,
      "responsavel": "diretor"|"coordenador"|"apoio_pedagogico",
      "metrica_sucesso": "string"
    }
  ],
  "acoes_enriquecidas": {
    "<ordem_da_acao>": "descrição enriquecida"
  }
}

Regras:
- Nunca minta ou maquiê dados — baseie-se apenas no que foi passado.
- Se os indicadores forem bons, diga isso em vez de inventar problemas.
- Use o tom de um coordenador experiente conversando com o gestor, não de relatório formal.
- Recomendações extras devem ser executáveis em 1 clique (cite a página: /admin/intervencoes, /admin/curriculo/cobertura, /admin/ranking-gestores).
- Sem emojis.
"""


def _normalize_period(period: str) -> str:
    return period if period in ("7d", "30d", "60d", "90d", "all") else "30d"


def _cache_key(mantenedora_id: Optional[str], school_id: str, period: str) -> str:
    raw = f"{mantenedora_id or '_'}|{school_id}|{period}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _parse_json(text: str) -> Optional[dict]:
    """Tenta extrair um JSON mesmo se o modelo embrulhar em markdown."""
    if not text:
        return None
    txt = text.strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```(?:json)?\s*", "", txt)
        txt = re.sub(r"\s*```$", "", txt)
    try:
        return json.loads(txt)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", txt)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


async def _gestor_history(db, school_id: str) -> dict:
    """Agrega métricas do gestor responsável pela escola nos últimos 90 dias."""
    coord = await db.users.find_one(
        {"status": "active", "role": {"$in": ["coordenador", "diretor"]},
         "school_links.school_id": school_id},
        {"_id": 0, "id": 1, "full_name": 1, "role": 1},
    )
    since = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    alerts = await db.intervention_alerts.find(
        {"school_id": school_id, "first_detected_at": {"$gte": since}},
        {"_id": 0, "escalation_level": 1, "first_detected_at": 1,
         "resolved_at": 1, "componente_codigo": 1, "status": 1},
    ).to_list(length=2000)

    received = len(alerts)
    resolved = [a for a in alerts if a.get("resolved_at")]
    active = [a for a in alerts if not a.get("resolved_at")]

    # Tempo médio próprio
    durations = []
    for a in resolved:
        try:
            d1 = datetime.fromisoformat(a["first_detected_at"])
            d2 = datetime.fromisoformat(a["resolved_at"])
            if d1.tzinfo is None:
                d1 = d1.replace(tzinfo=timezone.utc)
            if d2.tzinfo is None:
                d2 = d2.replace(tzinfo=timezone.utc)
            durations.append((d2 - d1).total_seconds() / 86400.0)
        except Exception:
            continue
    avg_days = round(sum(durations) / len(durations), 1) if durations else None

    # Categoria mais negligenciada (ativos por componente)
    from collections import Counter
    counter = Counter(a.get("componente_codigo") or "?" for a in active)
    neglected = counter.most_common(1)
    neglected_comp = neglected[0][0] if neglected else None
    neglected_count = neglected[0][1] if neglected else 0

    return {
        "nome": (coord or {}).get("full_name") or "Não definido",
        "role": (coord or {}).get("role") or "—",
        "received_90d": received,
        "resolved_90d": len(resolved),
        "active_90d": len(active),
        "resolution_rate_90d": round(len(resolved) / received, 3) if received else None,
        "avg_resolution_days_90d": avg_days,
        "most_neglected_component": neglected_comp,
        "most_neglected_active_count": neglected_count,
    }


async def _call_claude(payload: dict, timeout_s: int = 45) -> Optional[dict]:
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        logger.warning("[plano_acao_ai] EMERGENT_LLM_KEY ausente — skipando IA")
        return None

    session_id = f"plano-acao-{payload.get('school_id', 'x')}-{int(datetime.now().timestamp())}"
    chat = (
        LlmChat(api_key=api_key, session_id=session_id, system_message=_SYSTEM_PROMPT)
        .with_model(_MODEL_PROVIDER, _MODEL_NAME)
    )
    user_msg = UserMessage(text=(
        "Dados operacionais da escola e histórico do gestor (90 dias). "
        "Gere a análise no JSON especificado:\n\n" + json.dumps(payload, ensure_ascii=False, indent=2)
    ))
    try:
        response = await asyncio.wait_for(chat.send_message(user_msg), timeout=timeout_s)
    except asyncio.TimeoutError:
        logger.warning("[plano_acao_ai] timeout chamando Claude")
        return None
    except Exception as e:
        logger.warning("[plano_acao_ai] erro Claude: %s", e)
        return None

    parsed = _parse_json(response or "")
    if not parsed:
        logger.warning("[plano_acao_ai] resposta não-JSON: %s", (response or "")[:200])
        return None
    return parsed


def _validate_ai_response(data: dict) -> dict:
    """Sanitiza a resposta (tipos, limites) para não confiar cegamente."""
    safe: dict[str, Any] = {
        "analise_executiva": str(data.get("analise_executiva") or "").strip()[:600],
        "insight_historico": str(data.get("insight_historico") or "").strip()[:400],
        "recomendacoes_extra": [],
        "acoes_enriquecidas": {},
    }
    extras = data.get("recomendacoes_extra") or []
    if isinstance(extras, list):
        for r in extras[:2]:
            if not isinstance(r, dict):
                continue
            safe["recomendacoes_extra"].append({
                "titulo": str(r.get("titulo") or "")[:150],
                "descricao": str(r.get("descricao") or "")[:500],
                "prioridade": int(r.get("prioridade") or 3) if str(r.get("prioridade") or "").isdigit() else 3,
                "impacto": r.get("impacto") if r.get("impacto") in ("alto", "medio", "baixo") else "medio",
                "prazo_dias": int(r.get("prazo_dias") or 14) if str(r.get("prazo_dias") or "").isdigit() else 14,
                "responsavel": r.get("responsavel") if r.get("responsavel") in ("diretor", "coordenador", "apoio_pedagogico") else "coordenador",
                "metrica_sucesso": str(r.get("metrica_sucesso") or "")[:200],
            })
    enr = data.get("acoes_enriquecidas") or {}
    if isinstance(enr, dict):
        for k, v in enr.items():
            try:
                safe["acoes_enriquecidas"][str(int(k))] = str(v)[:500]
            except Exception:
                continue
    return safe


async def enrich_plan_with_ai(
    db,
    *,
    mantenedora_id: Optional[str],
    school_id: str,
    school_name: str,
    period: str,
    contexto: dict,
    acoes: list[dict],
    force: bool = False,
) -> Optional[dict]:
    """Gera (ou usa cache de) enriquecimento IA para um plano de ação.

    Returns None em caso de falha / IA indisponível — caller deve tratar.
    """
    period = _normalize_period(period)
    key = _cache_key(mantenedora_id, school_id, period)

    # 1. Cache lookup (a menos que force=True)
    now = datetime.now(timezone.utc)
    if not force:
        cached = await db.ai_plans.find_one({"key": key}, {"_id": 0})
        if cached:
            try:
                ts = datetime.fromisoformat(cached.get("generated_at"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age_h = (now - ts).total_seconds() / 3600.0
                if age_h < _CACHE_TTL_HOURS:
                    cached["from_cache"] = True
                    cached["cache_age_hours"] = round(age_h, 1)
                    return cached
            except Exception:
                pass

    # 2. Compor payload
    gestor = await _gestor_history(db, school_id)
    payload = {
        "school_id": school_id,
        "school_name": school_name,
        "period": period,
        "contexto_atual": contexto,
        "acoes_deterministicas": [
            {
                "ordem": a.get("ordem"),
                "categoria": a.get("categoria"),
                "titulo": a.get("titulo"),
                "prioridade": a.get("prioridade"),
                "prazo_dias": a.get("prazo_dias"),
            }
            for a in (acoes or [])
        ],
        "gestor": gestor,
    }

    # 3. Chamar Claude
    raw = await _call_claude(payload)
    if not raw:
        return None
    safe = _validate_ai_response(raw)

    # 4. Persistir cache
    doc = {
        "key": key,
        "mantenedora_id": mantenedora_id,
        "school_id": school_id,
        "period": period,
        "gestor": gestor,
        "ai": safe,
        "generated_at": now.isoformat(),
        "model": f"{_MODEL_PROVIDER}/{_MODEL_NAME}",
    }
    await db.ai_plans.update_one({"key": key}, {"$set": doc}, upsert=True)
    doc.pop("_id", None)
    doc["from_cache"] = False
    return doc
