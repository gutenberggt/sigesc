"""Relatório Mensal Executivo (Sprint G3 — Fev/2026).

Produto dentro do produto: Secretário/Gestor recebe TODO MÊS um diagnóstico
forensicamente auditável da rede com:

  1. Resumo executivo (1 tela)
  2. Ranking (Top 5 / Bottom 3 escolas)
  3. Diagnóstico causal
  4. 3 ações obrigatórias com prazo e responsável
  5. Indicador de risco (baixo/médio/alto)

Toda saída é gravada em `ai_analysis_snapshots` (G1.5: hash + HMAC) e
emite código `SIGESC-XXXX-XXXX` (G1.6) com validade de 30 dias para o
link público. Idempotente por (mantenedora_id, year, month) — chamadas
repetidas retornam o mesmo relatório (a menos que `force=True`).

Cron job dia 1º de cada mês 06:00 UTC dispara para cada mantenedora ativa,
gerando relatório do mês ANTERIOR e enviando email-gatilho aos gestores.
"""
from __future__ import annotations

import asyncio
import calendar as _cal
import json
import logging
import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from services import snapshot_service as snap_svc

logger = logging.getLogger(__name__)

_MODEL_PROVIDER = "anthropic"
_MODEL_NAME = "claude-sonnet-4-5-20250929"
_PUBLIC_LINK_VALIDITY_DAYS = 30

_RISK_VALUES = ("baixo", "medio", "alto")

_SYSTEM_PROMPT = """Você é o Consultor Executivo Sênior da Secretaria Municipal de Educação. Recebeu os dados consolidados do mês passado de TODA a rede. Seu papel é entregar um relatório de DECISÃO — não de descrição.

Regras inegociáveis:
- O relatório deve FORÇAR ação. Cada insight vira uma ordem clara, com prazo, com responsável.
- Linguagem direta, política e operacional ao mesmo tempo. Sem eufemismos. Sem "é importante que...".
- Cada afirmação forte é lastreada num número do payload. Sem inventar.
- Se a rede está bem, diga isso e proponha consolidação. Se está mal, diga isso e proponha intervenção.
- Português do Brasil. Sem emojis. Sem markdown. JSON puro.

Devolva EXATAMENTE este JSON (sem ```):

{
  "resumo_executivo": "string (3-5 linhas, o que o gestor PRECISA saber em 1 olhada)",
  "ranking": {
    "top5": [
      {"escola": "Nome", "score": 0-100, "destaque": "frase curta do que está dando certo"}
    ],
    "bottom3": [
      {"escola": "Nome", "score": 0-100, "alerta": "frase curta do problema central"}
    ]
  },
  "diagnostico_causal": "string (1-2 parágrafos: por que a rede está nesse estado, conectando alertas, frequência, cobertura, lançamentos)",
  "acoes_prioritarias": [
    {
      "acao": "Ordem clara, verbo no infinitivo (ex: 'Visitar Escola X para destrancar cobertura curricular')",
      "justificativa": "1 linha lastreada em número do payload",
      "responsavel": "secretario|coordenador|diretor|apoio_pedagogico",
      "prazo_dias": 3|7|14,
      "escolas_alvo": ["nome 1", "nome 2"],
      "impacto": "alto|medio|baixo"
    }
  ],
  "risco": "baixo|medio|alto",
  "evidencias": [
    {"metrica": "nome curto", "valor": "valor literal", "fonte": "rede.<chave> ou escolas[i].<chave>"}
  ]
}

Restrições:
- "acoes_prioritarias" deve ter EXATAMENTE 3 itens. Nem mais, nem menos.
- "evidencias" deve ter 4 a 6 itens.
- "top5" deve ter até 5 itens (pode ter menos se a rede for pequena).
- "bottom3" deve ter até 3 itens (pode ter menos).
- "score" é um número de 0 a 100 calculado pela IA com base em frequência + cobertura + alertas.
- "risco" leva em conta a tendência da rede inteira:
    * "baixo": cobertura média ≥ 85%, alertas ativos < 10% das escolas.
    * "medio": cobertura média 70-84% OU alertas ativos 10-25% das escolas.
    * "alto": cobertura média < 70% OU alertas ativos > 25% das escolas.

LIMITES DE REALIDADE DO SISTEMA (regra inegociável):
NUNCA sugira ações que dependam de funcionalidades que o SIGESC não tem hoje.

Páginas reais que VOCÊ PODE referenciar:
  /admin/intervencoes — gestão de alertas e planos abertos
  /admin/curriculo/cobertura — cobertura curricular
  /admin/ranking-gestores — ranking institucional
  /admin/declaracoes — emissão de declarações
  /admin/relatorios-mensais — esta tela
  /admin/staff — gestão de servidores

NUNCA sugira:
  - "configurar alertas / sensores / regras personalizadas"
  - regras específicas por etapa (Educação Infantil, Fund I/II)
  - integrações externas (Google Calendar, SSO, etc.)

Quando faltar feature técnica, proponha **ação operacional humana** (visita, reunião, capacitação, monitoramento manual com a coordenação).
"""


def _norm_month(year: int, month: int) -> tuple[int, int]:
    if not (1 <= month <= 12) or year < 2020 or year > 2100:
        raise ValueError(f"Período inválido: {year}/{month}")
    return year, month


def _month_range(year: int, month: int) -> tuple[datetime, datetime]:
    """Retorna [início, fim) do mês em UTC."""
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    last_day = _cal.monthrange(year, month)[1]
    end = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)
    return start, end


def _previous_month(today: Optional[datetime] = None) -> tuple[int, int]:
    today = today or datetime.now(timezone.utc)
    first_of_this_month = today.replace(day=1)
    last_of_prev = first_of_this_month - timedelta(days=1)
    return last_of_prev.year, last_of_prev.month


async def _aggregate_month(db, mantenedora_id: Optional[str], year: int, month: int) -> dict:
    """Coleta dados consolidados do mês para a mantenedora.

    Retorna payload determinístico que vai ao Claude e fica congelado no snapshot.
    Estrutura:
      {
        "rede": {nome, total_escolas, total_alunos, alertas_ativos, ...},
        "escolas": [{id, nome, frequencia_pct, cobertura_pct, alertas_no_mes, ...}],
        "componentes_negligenciados": [{codigo, total_alertas}]
      }
    """
    start, end = _month_range(year, month)
    start_iso, end_iso = start.isoformat(), end.isoformat()

    # Mantenedora info
    mant = None
    if mantenedora_id:
        mant = await db.mantenedoras.find_one({"id": mantenedora_id}, {"_id": 0, "nome": 1, "id": 1})

    school_filter: dict = {"status": {"$ne": "inactive"}}
    if mantenedora_id:
        school_filter["mantenedora_id"] = mantenedora_id
    schools = await db.schools.find(
        school_filter, {"_id": 0, "id": 1, "name": 1}
    ).to_list(length=2000)
    school_ids = [s["id"] for s in schools]

    # Total alunos (snapshot atual)
    student_filter: dict = {"status": "active"}
    if mantenedora_id:
        student_filter["mantenedora_id"] = mantenedora_id
    total_alunos = await db.students.count_documents(student_filter)

    # Alertas do mês
    alert_filter: dict = {"first_detected_at": {"$gte": start_iso, "$lte": end_iso}}
    if school_ids:
        alert_filter["school_id"] = {"$in": school_ids}
    alerts_month = await db.intervention_alerts.find(
        alert_filter,
        {"_id": 0, "school_id": 1, "componente_codigo": 1, "escalation_level": 1,
         "status": 1, "resolved_at": 1, "first_detected_at": 1},
    ).to_list(length=20000)

    # Alertas ativos no fim do mês (não resolvidos OU resolvidos depois do fim do mês)
    alert_active_filter: dict = {
        "first_detected_at": {"$lte": end_iso},
        "$or": [
            {"resolved_at": None},
            {"resolved_at": {"$gt": end_iso}},
            {"resolved_at": {"$exists": False}},
        ],
    }
    if school_ids:
        alert_active_filter["school_id"] = {"$in": school_ids}
    alerts_active = await db.intervention_alerts.find(
        alert_active_filter,
        {"_id": 0, "school_id": 1, "componente_codigo": 1, "escalation_level": 1},
    ).to_list(length=20000)

    # Frequência média do mês por escola — agregação simples por classe → escola
    # Estrutura attendance: {class_id, date, present, total} — agregamos taxa de presença.
    att_pipeline = [
        {"$match": {"date": {"$gte": start_iso[:10], "$lte": end_iso[:10]}}},
    ]
    if school_ids:
        att_pipeline.append({"$lookup": {
            "from": "classes",
            "localField": "class_id",
            "foreignField": "id",
            "as": "_class",
        }})
        att_pipeline.append({"$unwind": {"path": "$_class", "preserveNullAndEmptyArrays": True}})
        att_pipeline.append({"$match": {"_class.school_id": {"$in": school_ids}}})
        att_pipeline.append({"$addFields": {"school_id": "$_class.school_id"}})
    att_pipeline.append({"$group": {
        "_id": "$school_id",
        "presentes": {"$sum": {"$ifNull": ["$present", 0]}},
        "total": {"$sum": {"$ifNull": ["$total", 0]}},
    }})
    att_rows = await db.attendance.aggregate(att_pipeline).to_list(length=2000)
    freq_por_escola: dict[str, float] = {}
    for r in att_rows:
        sid = r["_id"]
        tot = r.get("total") or 0
        if not sid or not tot:
            continue
        freq_por_escola[sid] = round(100.0 * (r.get("presentes") or 0) / tot, 1)

    # Cobertura curricular: lê de curriculum_coverage_stats (se existir) — fallback 0
    cobertura_por_escola: dict[str, float] = {}
    try:
        cov_filter: dict = {}
        if school_ids:
            cov_filter["school_id"] = {"$in": school_ids}
        cov_rows = await db.curriculum_coverage_stats.find(
            cov_filter, {"_id": 0, "school_id": 1, "coverage_pct": 1}
        ).to_list(length=2000)
        for r in cov_rows:
            cobertura_por_escola[r["school_id"]] = float(r.get("coverage_pct") or 0)
    except Exception:
        pass

    # Aulas lançadas no mês por escola (learning_objects)
    lo_pipeline = []
    if school_ids:
        lo_pipeline.append({"$match": {
            "date": {"$gte": start_iso[:10], "$lte": end_iso[:10]},
        }})
        lo_pipeline.append({"$lookup": {
            "from": "classes",
            "localField": "class_id",
            "foreignField": "id",
            "as": "_class",
        }})
        lo_pipeline.append({"$unwind": {"path": "$_class", "preserveNullAndEmptyArrays": True}})
        lo_pipeline.append({"$match": {"_class.school_id": {"$in": school_ids}}})
        lo_pipeline.append({"$group": {"_id": "$_class.school_id", "n": {"$sum": 1}}})
        try:
            lo_rows = await db.learning_objects.aggregate(lo_pipeline).to_list(length=2000)
            aulas_por_escola = {r["_id"]: int(r.get("n") or 0) for r in lo_rows if r.get("_id")}
        except Exception:
            aulas_por_escola = {}
    else:
        aulas_por_escola = {}

    # Compilar lista de escolas
    alerts_month_by_school: Counter = Counter(a.get("school_id") for a in alerts_month if a.get("school_id"))
    alerts_active_by_school: Counter = Counter(a.get("school_id") for a in alerts_active if a.get("school_id"))
    componentes_negligenciados = Counter(
        a.get("componente_codigo") or "?" for a in alerts_active
    ).most_common(5)

    escolas_payload = []
    for s in schools:
        sid = s["id"]
        freq = freq_por_escola.get(sid)
        cob = cobertura_por_escola.get(sid)
        am = int(alerts_month_by_school.get(sid, 0))
        aa = int(alerts_active_by_school.get(sid, 0))
        aulas = int(aulas_por_escola.get(sid, 0))
        escolas_payload.append({
            "id": sid,
            "nome": s.get("name") or "Escola",
            "frequencia_mes_pct": freq,
            "cobertura_curricular_pct": cob,
            "alertas_no_mes": am,
            "alertas_ativos_fim_mes": aa,
            "aulas_lancadas_mes": aulas,
        })

    # Cobertura média da rede (só conta escolas com dado)
    cob_values = [e["cobertura_curricular_pct"] for e in escolas_payload
                  if e["cobertura_curricular_pct"] is not None]
    freq_values = [e["frequencia_mes_pct"] for e in escolas_payload
                   if e["frequencia_mes_pct"] is not None]
    cob_media = round(sum(cob_values) / len(cob_values), 1) if cob_values else None
    freq_media = round(sum(freq_values) / len(freq_values), 1) if freq_values else None

    # Pct de escolas com alertas ativos
    n_total = len(escolas_payload)
    n_com_alertas = sum(1 for e in escolas_payload if e["alertas_ativos_fim_mes"] > 0)
    pct_com_alertas = round(100.0 * n_com_alertas / n_total, 1) if n_total else 0.0

    return {
        "rede": {
            "mantenedora_id": mantenedora_id,
            "mantenedora_nome": (mant or {}).get("nome") if mant else "Rede",
            "ano": year,
            "mes": month,
            "mes_label": f"{month:02d}/{year}",
            "total_escolas": n_total,
            "total_alunos": total_alunos,
            "frequencia_media_pct": freq_media,
            "cobertura_curricular_media_pct": cob_media,
            "alertas_no_mes_total": len(alerts_month),
            "alertas_ativos_fim_mes_total": len(alerts_active),
            "escolas_com_alertas_ativos": n_com_alertas,
            "pct_escolas_com_alertas": pct_com_alertas,
        },
        "escolas": escolas_payload,
        "componentes_negligenciados": [
            {"codigo": c, "alertas_ativos": n} for c, n in componentes_negligenciados
        ],
    }


def _parse_json(text: str) -> Optional[dict]:
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


def _sanitize_evidencias(raw: Any, max_items: int = 8) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out = []
    for e in raw[:max_items]:
        if not isinstance(e, dict):
            continue
        out.append({
            "metrica": str(e.get("metrica") or "")[:80],
            "valor": str(e.get("valor") if e.get("valor") is not None else "")[:100],
            "fonte": str(e.get("fonte") or "")[:120],
        })
    return [e for e in out if e["metrica"] and e["valor"]]


def _validate_report(data: dict) -> dict:
    """Sanitiza estritamente — não confia na IA."""
    safe: dict[str, Any] = {
        "resumo_executivo": str(data.get("resumo_executivo") or "").strip()[:1500],
        "ranking": {"top5": [], "bottom3": []},
        "diagnostico_causal": str(data.get("diagnostico_causal") or "").strip()[:2000],
        "acoes_prioritarias": [],
        "risco": data.get("risco") if data.get("risco") in _RISK_VALUES else "medio",
        "evidencias": _sanitize_evidencias(data.get("evidencias"), max_items=8),
    }
    rk = data.get("ranking") or {}
    for src_key, dst_key, msg_key, max_n in (
        ("top5", "top5", "destaque", 5), ("bottom3", "bottom3", "alerta", 3)
    ):
        items = rk.get(src_key) or []
        if not isinstance(items, list):
            continue
        for it in items[:max_n]:
            if not isinstance(it, dict):
                continue
            try:
                score = int(it.get("score"))
                score = max(0, min(100, score))
            except Exception:
                score = 0
            safe["ranking"][dst_key].append({
                "escola": str(it.get("escola") or "")[:200],
                "score": score,
                msg_key: str(it.get(msg_key) or "")[:300],
            })

    extras = data.get("acoes_prioritarias") or []
    pre_validation: list = []
    if isinstance(extras, list):
        for r in extras[:3]:
            if not isinstance(r, dict):
                continue
            try:
                prazo = int(r.get("prazo_dias") or 7)
            except Exception:
                prazo = 7
            if prazo not in (3, 7, 14, 30):
                prazo = 7
            escolas_alvo = r.get("escolas_alvo") or []
            if isinstance(escolas_alvo, list):
                escolas_alvo = [str(x)[:200] for x in escolas_alvo[:10] if x]
            else:
                escolas_alvo = []
            pre_validation.append({
                "acao": str(r.get("acao") or "")[:300],
                "justificativa": str(r.get("justificativa") or "")[:400],
                "responsavel": r.get("responsavel") if r.get("responsavel") in
                    ("secretario", "coordenador", "diretor", "apoio_pedagogico") else "secretario",
                "prazo_dias": prazo,
                "escolas_alvo": escolas_alvo,
                "impacto": r.get("impacto") if r.get("impacto") in ("alto", "medio", "baixo") else "medio",
            })

    # Camada de governança: bloqueia recs que dependem de capacidades inexistentes.
    # Aplica fallback porque o G3 EXIGE 3 ações — lista vazia não é estado válido.
    from services.recommendation_validator import validate_recommendations
    safe["acoes_prioritarias"] = validate_recommendations(
        pre_validation,
        context="g3_monthly",
        apply_fallback=True,
    )
    return safe


async def _call_claude(payload: dict, timeout_s: int = 60) -> Optional[dict]:
    from services.llm_client import chat_with_claude, llm_provider

    if llm_provider() == "none":
        logger.warning("[monthly_report] sem LLM key (ANTHROPIC ou EMERGENT) — skipando IA")
        return None
    sid = f"monthly-report-{payload['rede'].get('mantenedora_id', 'x')}-{payload['rede']['ano']}-{payload['rede']['mes']}"
    user_text = (
        "Dados consolidados do mês da rede municipal. Gere o relatório no JSON especificado:\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    response = await chat_with_claude(
        system_prompt=_SYSTEM_PROMPT,
        user_text=user_text,
        session_id=sid,
        model=_MODEL_NAME,
        timeout_s=timeout_s,
    )
    if not response:
        return None
    parsed = _parse_json(response)
    if not parsed:
        logger.warning("[monthly_report] resposta não-JSON: %s", response[:200])
        return None
    return parsed


def _stub_report(payload: dict) -> dict:
    """Fallback determinístico quando IA está indisponível.

    Garante que o relatório SEMPRE pode ser gerado — sem IA o conteúdo é
    objetivo e baseado puramente nos números agregados. Mantém auditabilidade.
    """
    rede = payload["rede"]
    escolas = list(payload.get("escolas") or [])

    def score_escola(e: dict) -> int:
        freq = e.get("frequencia_mes_pct") or 0
        cob = e.get("cobertura_curricular_pct") or 0
        alertas = e.get("alertas_ativos_fim_mes") or 0
        # score 0-100: 50% freq + 40% cobertura - 2 por alerta
        s = 0.5 * freq + 0.4 * cob - 2 * alertas
        return max(0, min(100, int(round(s))))

    ranked = sorted(escolas, key=score_escola, reverse=True)
    top5 = [{
        "escola": e["nome"],
        "score": score_escola(e),
        "destaque": f"Frequência {e.get('frequencia_mes_pct') or 0}% e cobertura {e.get('cobertura_curricular_pct') or 0}%.",
    } for e in ranked[:5]]
    bottom3 = [{
        "escola": e["nome"],
        "score": score_escola(e),
        "alerta": f"{e.get('alertas_ativos_fim_mes') or 0} alertas ativos no fim do mês; cobertura {e.get('cobertura_curricular_pct') or 0}%.",
    } for e in ranked[-3:][::-1]] if ranked else []

    pct = rede.get("pct_escolas_com_alertas") or 0
    cob = rede.get("cobertura_curricular_media_pct") or 0
    if pct > 25 or (cob and cob < 70):
        risco = "alto"
    elif pct > 10 or (cob and cob < 85):
        risco = "medio"
    else:
        risco = "baixo"

    resumo = (
        f"Rede {rede.get('mantenedora_nome') or '—'} em {rede['mes_label']}: "
        f"{rede.get('total_escolas') or 0} escolas, "
        f"frequência média {rede.get('frequencia_media_pct') or 0}%, "
        f"cobertura {rede.get('cobertura_curricular_media_pct') or 0}%, "
        f"{rede.get('escolas_com_alertas_ativos') or 0} escolas com alertas ativos "
        f"({pct}% da rede). Nível de risco: {risco}."
    )

    diagnostico = (
        "Análise determinística — IA externa indisponível neste ciclo. "
        "Os números acima refletem o agregado real do mês: priorize "
        "verificação manual das escolas listadas em bottom3 e "
        "validação do plano de ação de cada uma."
    )

    acoes = []
    if bottom3:
        acoes.append({
            "acao": f"Realizar visita técnica nas {len(bottom3)} escolas com pior desempenho",
            "justificativa": f"{bottom3[0]['escola']} e outras estão na faixa crítica.",
            "responsavel": "secretario",
            "prazo_dias": 7,
            "escolas_alvo": [e["escola"] for e in bottom3],
            "impacto": "alto",
        })
    comps = payload.get("componentes_negligenciados") or []
    if comps:
        acoes.append({
            "acao": f"Revisar plano pedagógico do componente '{comps[0]['codigo']}'",
            "justificativa": f"{comps[0]['alertas_ativos']} alertas ativos concentrados.",
            "responsavel": "coordenador",
            "prazo_dias": 14,
            "escolas_alvo": [],
            "impacto": "medio",
        })
    if rede.get("alertas_ativos_fim_mes_total"):
        acoes.append({
            "acao": "Revisar e despachar alertas ativos pendentes da rede",
            "justificativa": f"{rede['alertas_ativos_fim_mes_total']} alertas em aberto no fim do mês.",
            "responsavel": "coordenador",
            "prazo_dias": 3,
            "escolas_alvo": [],
            "impacto": "alto",
        })
    while len(acoes) < 3:
        acoes.append({
            "acao": "Consolidar boas práticas das escolas top",
            "justificativa": "Manter o que está funcionando.",
            "responsavel": "secretario",
            "prazo_dias": 14,
            "escolas_alvo": [e["escola"] for e in top5[:3]],
            "impacto": "medio",
        })

    evidencias = [
        {"metrica": "Total de escolas", "valor": str(rede.get("total_escolas")), "fonte": "rede.total_escolas"},
        {"metrica": "Frequência média", "valor": f"{rede.get('frequencia_media_pct') or 0}%", "fonte": "rede.frequencia_media_pct"},
        {"metrica": "Cobertura média", "valor": f"{rede.get('cobertura_curricular_media_pct') or 0}%", "fonte": "rede.cobertura_curricular_media_pct"},
        {"metrica": "Alertas ativos no fim", "valor": str(rede.get("alertas_ativos_fim_mes_total")), "fonte": "rede.alertas_ativos_fim_mes_total"},
        {"metrica": "% escolas com alertas", "valor": f"{pct}%", "fonte": "rede.pct_escolas_com_alertas"},
    ]
    return {
        "resumo_executivo": resumo,
        "ranking": {"top5": top5, "bottom3": bottom3},
        "diagnostico_causal": diagnostico,
        "acoes_prioritarias": acoes[:3],
        "risco": risco,
        "evidencias": evidencias,
    }


async def ensure_indexes(db) -> None:
    try:
        await db.monthly_reports.create_index(
            [("mantenedora_id", 1), ("year", 1), ("month", 1)],
            unique=True,
            name="monthly_report_unique_period",
        )
        await db.monthly_reports.create_index([("created_at", -1)])
    except Exception as e:
        logger.warning("[monthly_report] falha ao criar índices: %s", e)


async def list_monthly_reports(db, *, mantenedora_id: Optional[str], limit: int = 24) -> list[dict]:
    filt: dict = {}
    if mantenedora_id:
        filt["mantenedora_id"] = mantenedora_id
    cursor = db.monthly_reports.find(
        filt,
        {
            "_id": 0, "id": 1, "mantenedora_id": 1, "year": 1, "month": 1,
            "month_label": 1, "snapshot_id": 1, "verification_code": 1,
            "risco": 1, "created_at": 1, "model": 1, "email_sent_at": 1,
            "from_cache": 1, "rede_summary": 1,
        },
    ).sort([("year", -1), ("month", -1)]).limit(limit)
    return await cursor.to_list(length=limit)


async def get_monthly_report(db, *, report_id: str) -> Optional[dict]:
    return await db.monthly_reports.find_one({"id": report_id}, {"_id": 0})


async def find_existing_report(
    db, *, mantenedora_id: Optional[str], year: int, month: int
) -> Optional[dict]:
    return await db.monthly_reports.find_one(
        {"mantenedora_id": mantenedora_id, "year": year, "month": month},
        {"_id": 0},
    )


async def generate_monthly_report(
    db,
    *,
    mantenedora_id: Optional[str],
    year: int,
    month: int,
    user: dict,
    force: bool = False,
) -> dict:
    """Idempotente. Retorna o relatório (cached ou novo) com snapshot+verification_code.

    - Se já existe e force=False → retorna existente com from_cache=True.
    - Se force=True → revoga código antigo e gera novo snapshot.
    """
    year, month = _norm_month(year, month)

    # Cache lookup
    existing = await find_existing_report(db, mantenedora_id=mantenedora_id, year=year, month=month)
    if existing and not force:
        existing["from_cache"] = True
        return existing

    payload = await _aggregate_month(db, mantenedora_id, year, month)
    if payload["rede"]["total_escolas"] == 0:
        raise ValueError("Rede vazia — não há escolas ativas para gerar o relatório")

    ai_output = await _call_claude(payload) or _stub_report(payload)
    safe = _validate_report(ai_output)

    # Cria snapshot imutável (G1.5) — gera automaticamente verification_code (G1.6)
    snap = await snap_svc.create_snapshot(
        db,
        mantenedora_id=mantenedora_id,
        entity_type="rede",
        entity_id=mantenedora_id or "_",
        analysis_type="relatorio_mensal",
        payload_snapshot=payload,
        ai_output=safe,
        model=f"{_MODEL_PROVIDER}/{_MODEL_NAME}",
        user=user,
    )
    code = snap.get("verification_code")

    # Aplica validade de 30 dias ao link público (G3 spec)
    if code:
        try:
            expires_at = (datetime.now(timezone.utc) + timedelta(days=_PUBLIC_LINK_VALIDITY_DAYS)).isoformat()
            await db.verifiable_documents.update_one(
                {"code": code},
                {"$set": {"expires_at": expires_at}},
            )
        except Exception as e:
            logger.warning("[monthly_report] falha ao setar expires_at: %s", e)

    # Persistência idempotente em monthly_reports
    rede_summary = {
        "mantenedora_nome": payload["rede"].get("mantenedora_nome"),
        "total_escolas": payload["rede"].get("total_escolas"),
        "total_alunos": payload["rede"].get("total_alunos"),
        "frequencia_media_pct": payload["rede"].get("frequencia_media_pct"),
        "cobertura_curricular_media_pct": payload["rede"].get("cobertura_curricular_media_pct"),
        "escolas_com_alertas_ativos": payload["rede"].get("escolas_com_alertas_ativos"),
        "pct_escolas_com_alertas": payload["rede"].get("pct_escolas_com_alertas"),
    }
    now_iso = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": snap["id"],   # mesmo id do snapshot — evita duplicação
        "snapshot_id": snap["id"],
        "verification_code": code,
        "mantenedora_id": mantenedora_id,
        "year": year,
        "month": month,
        "month_label": f"{month:02d}/{year}",
        "model": f"{_MODEL_PROVIDER}/{_MODEL_NAME}",
        "ai": safe,
        "rede_summary": rede_summary,
        "risco": safe.get("risco"),
        "created_at": now_iso,
        "created_by": {
            "user_id": user.get("id"),
            "email": user.get("email"),
            "role": user.get("role"),
        },
        "email_sent_at": None,
        "email_recipients": [],
        "from_cache": False,
    }
    await db.monthly_reports.update_one(
        {"mantenedora_id": mantenedora_id, "year": year, "month": month},
        {"$set": doc},
        upsert=True,
    )
    return doc


async def mark_email_sent(
    db, *, report_id: str, recipients: list[str]
) -> None:
    await db.monthly_reports.update_one(
        {"id": report_id},
        {"$set": {
            "email_sent_at": datetime.now(timezone.utc).isoformat(),
            "email_recipients": recipients,
        }},
    )
