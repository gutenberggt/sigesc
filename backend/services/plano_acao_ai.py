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

**EXPLAINABILITY OBRIGATÓRIA (regra inegociável)**: cada afirmação forte DEVE ser lastreada em evidências numéricas extraídas do payload. Para cada campo principal, inclua um array paralelo de evidências com os dados que embasaram a inferência. Nunca afirme algo que não possa ser confirmado por um número no payload.

Responda SEMPRE em português do Brasil, em JSON puro (sem markdown, sem ```), com a seguinte estrutura:

{
  "analise_executiva": "string",
  "analise_evidencias": [
    {"metrica": "nome curto", "valor": "valor literal", "fonte": "contexto_atual.<chave>"}
  ],
  "insight_historico": "string",
  "insight_evidencias": [
    {"metrica": "nome curto", "valor": "valor literal", "fonte": "gestor.<chave>"}
  ],
  "recomendacoes_extra": [
    {
      "titulo": "string",
      "descricao": "string",
      "prioridade": 1|2|3,
      "impacto": "alto"|"medio"|"baixo",
      "prazo_dias": 3|7|14|30,
      "responsavel": "diretor"|"coordenador"|"apoio_pedagogico",
      "metrica_sucesso": "string",
      "baseado_em": [
        {"metrica": "nome curto", "valor": "valor literal", "fonte": "contexto_atual.<chave> ou gestor.<chave>"}
      ]
    }
  ],
  "acoes_enriquecidas": {
    "<ordem_da_acao>": "descrição enriquecida"
  }
}

Regras absolutas:
- Cada `analise_evidencias` DEVE ter 2 a 4 itens. Cada `insight_evidencias` DEVE ter 1 a 3 itens. Cada recomendação extra DEVE ter `baseado_em` com pelo menos 1 item.
- "fonte" é o caminho literal no payload (ex.: "contexto_atual.coverage_pct", "gestor.avg_resolution_days_90d").
- "valor" deve ser a representação literal do número/string (ex.: "0%", "66", "null", "CO").
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
    from services.llm_client import chat_with_claude, llm_provider, DEFAULT_MODEL

    if llm_provider() == "none":
        logger.warning("[plano_acao_ai] sem LLM key (ANTHROPIC ou EMERGENT) — skipando IA")
        return None

    session_id = f"plano-acao-{payload.get('school_id', 'x')}-{int(datetime.now().timestamp())}"
    user_text = (
        "Dados operacionais da escola e histórico do gestor (90 dias). "
        "Gere a análise no JSON especificado:\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    response = await chat_with_claude(
        system_prompt=_SYSTEM_PROMPT,
        user_text=user_text,
        session_id=session_id,
        model=_MODEL_NAME if _MODEL_NAME else DEFAULT_MODEL,
        timeout_s=timeout_s,
    )
    if not response:
        return None
    parsed = _parse_json(response)
    if not parsed:
        logger.warning("[plano_acao_ai] resposta não-JSON: %s", response[:200])
        return None
    return parsed


def _sanitize_evidencias(raw: Any, max_items: int = 5) -> list:
    """Valida/limita array de evidências (metrica/valor/fonte)."""
    if not isinstance(raw, list):
        return []
    out = []
    for e in raw[:max_items]:
        if not isinstance(e, dict):
            continue
        out.append({
            "metrica": str(e.get("metrica") or "")[:60],
            "valor": str(e.get("valor") if e.get("valor") is not None else "")[:80],
            "fonte": str(e.get("fonte") or "")[:80],
        })
    return [e for e in out if e["metrica"] and e["valor"]]


def _validate_ai_response(data: dict) -> dict:
    """Sanitiza a resposta (tipos, limites) para não confiar cegamente."""
    safe: dict[str, Any] = {
        "analise_executiva": str(data.get("analise_executiva") or "").strip()[:600],
        "analise_evidencias": _sanitize_evidencias(data.get("analise_evidencias"), max_items=4),
        "insight_historico": str(data.get("insight_historico") or "").strip()[:400],
        "insight_evidencias": _sanitize_evidencias(data.get("insight_evidencias"), max_items=3),
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
                "baseado_em": _sanitize_evidencias(r.get("baseado_em"), max_items=3),
            })
    enr = data.get("acoes_enriquecidas") or {}
    if isinstance(enr, dict):
        for k, v in enr.items():
            try:
                safe["acoes_enriquecidas"][str(int(k))] = str(v)[:500]
            except Exception:
                continue
    return safe


async def invalidate_ai_plans_for_school(db, *, school_id: str) -> int:
    """Invalida cache de planos IA de uma escola.

    Chamado quando há mudança operacional relevante (novo alerta, resolução,
    criação de learning_object). Garante que a próxima chamada ao plano-acao
    com ai=true regere a análise com os dados frescos, sem esperar 24h.

    Retorna o número de documentos removidos.
    """
    if not school_id:
        return 0
    try:
        r = await db.ai_plans.delete_many({"school_id": school_id})
        if r.deleted_count > 0:
            logger.info(
                "[plano_acao_ai] cache invalidado p/ school=%s (%d docs)",
                school_id, r.deleted_count,
            )
        return r.deleted_count
    except Exception as e:
        logger.warning("[plano_acao_ai] falha na invalidação: %s", e)
        return 0


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
    user: Optional[dict] = None,
) -> Optional[dict]:
    """Gera (ou usa cache de) enriquecimento IA para um plano de ação.

    Returns None em caso de falha / IA indisponível — caller deve tratar.
    Quando o user é fornecido, cria snapshot imutável (Sprint G1.5).
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

    # 3.5 G1.5: snapshot imutável (payload congelado + hash + HMAC)
    snapshot_id = None
    public_hash = None
    server_signature = None
    if user is not None:
        try:
            from services.snapshot_service import create_snapshot
            # Payload congelado: inclui ações determinísticas para reprodutibilidade
            frozen_payload = {**payload, "acoes": acoes}
            snap = await create_snapshot(
                db,
                mantenedora_id=mantenedora_id,
                entity_type="escola",
                entity_id=school_id,
                analysis_type="plano_acao",
                payload_snapshot=frozen_payload,
                ai_output=safe,
                model=f"{_MODEL_PROVIDER}/{_MODEL_NAME}",
                user=user,
            )
            snapshot_id = snap["id"]
            public_hash = snap["public_hash"]
            server_signature = snap["server_signature"]
        except Exception as e:
            logger.warning("[plano_acao_ai] falha ao criar snapshot: %s", e)

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
        "snapshot_id": snapshot_id,
        "public_hash": public_hash,
        "server_signature": server_signature,
    }
    await db.ai_plans.update_one({"key": key}, {"$set": doc}, upsert=True)
    doc.pop("_id", None)
    doc["from_cache"] = False
    return doc
