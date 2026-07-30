"""
CTUEConformityService — Fonte Única (SSoT) de cálculo de conformidade do CTUE.

TODA a lógica de completude, conformidade, estados, maturidade e frescor de
atualização da Unidade Escolar vive AQUI. Painel do CTUE, índice inteligente,
mini-cards da listagem, dashboard da rede, BI, dossiê/PDF e API consomem o
MESMO resultado. Nenhuma regra de negócio é duplicada no frontend.

Regras são CONFIGURÁVEIS (config/ctue_rulesets.json). Avaliação por condições
estruturadas (sem eval de código arbitrário). Perfis de avaliação (MP/FNDE/TCM/…)
alteram apenas os pesos das seções; o motor é único.
"""
import json
import os
from datetime import datetime, timezone

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "ctue_rulesets.json")

# Estados (4) — SSoT dos rótulos/ícones
STATE_CONFORME = "conforme"        # 🟢
STATE_ATENCAO = "atencao"          # 🟡
STATE_CRITICO = "critico"          # 🟠
STATE_NAO_CONFORME = "nao_conforme"  # 🔴
STATE_NAO_AVALIADO = "nao_avaliado"  # 🔘 (Fase D)


def _load_ruleset():
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


_RULESET = _load_ruleset()


def get_profiles():
    """Lista de perfis disponíveis (chave + rótulo)."""
    profiles = _RULESET.get("profiles", {})
    return [{"key": k, "label": v.get("label", k)} for k, v in profiles.items()]


def _is_filled(value, tipo):
    if value is None:
        return False
    if tipo == "str":
        return str(value).strip() != ""
    if tipo in ("int", "float", "number"):
        try:
            return float(value) > 0
        except (TypeError, ValueError):
            return False
    if tipo == "bool":
        return value is not None
    return value not in (None, "", [])


def _eval_condition(school, cond):
    field = cond.get("field")
    op = cond.get("op")
    val = school.get(field)
    target = cond.get("value")
    if op == "filled":
        return _is_filled(val, "str" if isinstance(val, str) else "int" if isinstance(val, (int, float)) else "bool")
    if op == "truthy":
        return bool(val) is True
    if op == "falsy":
        return not bool(val)
    if op in ("gt", "gte", "lt", "lte", "eq", "ne"):
        try:
            v = float(val) if val is not None else 0.0
            t = float(target)
        except (TypeError, ValueError):
            return False
        return {
            "gt": v > t, "gte": v >= t, "lt": v < t,
            "lte": v <= t, "eq": v == t, "ne": v != t,
        }[op]
    if op == "in":
        return val in (target or [])
    if op == "not_in":
        if val is None:
            return True
        return str(val).strip().lower() not in [str(x).strip().lower() for x in (target or [])]
    return False


def _eval_regra(school, regra):
    conds = regra.get("condicoes", [])
    if not conds:
        return True
    modo = regra.get("modo", "all")
    results = [_eval_condition(school, c) for c in conds]
    return any(results) if modo == "any" else all(results)


def _state_from_pct(pct, thresholds):
    if pct >= thresholds.get("conforme", 85):
        return STATE_CONFORME
    if pct >= thresholds.get("atencao", 65):
        return STATE_ATENCAO
    if pct >= thresholds.get("critico", 40):
        return STATE_CRITICO
    return STATE_NAO_CONFORME


def _eval_section(school, section):
    """Retorna dict com completude, conformidade, status, regras e pendências."""
    # ---- Completude (preenchimento) ----
    campos = section.get("campos", [])
    fill_fields = [c for c in campos if c.get("requer_preenchimento")]
    total_peso = sum(c.get("peso", 1) for c in fill_fields)
    filled_peso = 0
    pendencias = []
    for c in fill_fields:
        if _is_filled(school.get(c["campo"]), c.get("tipo", "str")):
            filled_peso += c.get("peso", 1)
        else:
            pendencias.append(c["campo"])
    completude = round((filled_peso / total_peso) * 100) if total_peso > 0 else 100
    itens_total = len(fill_fields)
    itens_preenchidos = itens_total - len(pendencias)

    # ---- Conformidade (regras) ----
    regras = section.get("regras_conformidade", [])
    regra_results = []
    if regras:
        peso_total = sum(r.get("peso", 1) for r in regras)
        peso_ok = 0
        for r in regras:
            atende = _eval_regra(school, r)
            if atende:
                peso_ok += r.get("peso", 1)
            regra_results.append({"id": r["id"], "label": r.get("label", r["id"]), "atende": atende})
        conformidade = round((peso_ok / peso_total) * 100) if peso_total > 0 else 100
    else:
        # Sem regras → conformidade = completude (estar cadastrado é o "atender")
        conformidade = completude

    status = _state_from_pct(conformidade, section.get("section_thresholds", {}))
    return {
        "completude": completude,
        "conformidade": conformidade,
        "status": status,
        "itens_total": itens_total,
        "itens_preenchidos": itens_preenchidos,
        "regras": regra_results,
        "pendencias": pendencias,
    }


def _freshness(updated_at):
    """Indicador de Atualização a partir de updated_at (ISO str ou datetime)."""
    if not updated_at:
        return {"last_update": None, "days_since": None, "label": "Nunca atualizado", "freshness": "never"}
    try:
        if isinstance(updated_at, str):
            dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        else:
            dt = updated_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return {"last_update": None, "days_since": None, "label": "Nunca atualizado", "freshness": "never"}
    now = datetime.now(timezone.utc)
    days = (now - dt).days
    if days <= 0:
        label, fresh = "Atualizado hoje", "recent"
    elif days == 1:
        label, fresh = "Atualizado ontem", "recent"
    elif days < 30:
        label, fresh = f"Atualizado há {days} dias", "ok"
    elif days < 365:
        meses = max(1, days // 30)
        label, fresh = f"Atualizado há {meses} {'mês' if meses == 1 else 'meses'}", "stale"
    else:
        anos = days // 365
        label, fresh = f"Atualizado há {anos} {'ano' if anos == 1 else 'anos'}", "stale"
    return {"last_update": dt.isoformat(), "days_since": days, "label": label, "freshness": fresh}


def _maturity(completude_geral, conformidade_geral, section_map, freshness, ruleset):
    """Nível de maturidade 1..5 (prontuário institucional)."""
    infra_keys = ruleset.get("maturity", {}).get("infra_sections", [])
    infra_ok = all(
        section_map.get(k, {}).get("status") == STATE_CONFORME
        for k in infra_keys if k in section_map
    ) if infra_keys else False
    recent = freshness.get("freshness") in ("recent", "ok")

    if conformidade_geral >= 95 and completude_geral >= 95 and recent:
        return {"nivel": 5, "nome": "Excelência operacional"}
    if conformidade_geral >= 85:
        return {"nivel": 4, "nome": "Conformidade institucional"}
    if completude_geral >= 80 and infra_ok:
        return {"nivel": 3, "nome": "Infraestrutura validada"}
    if completude_geral >= 80:
        return {"nivel": 2, "nome": "Cadastro completo"}
    return {"nivel": 1, "nome": "Cadastro inicial"}


def evaluate(school, profile="default", ruleset=None):
    """
    Avalia uma escola (dict) e retorna o ConformityResult — o CONTRATO ÚNICO
    consumido por todos os canais. `profile` seleciona os pesos das seções.
    """
    rs = ruleset or _RULESET
    profiles = rs.get("profiles", {})
    prof = profiles.get(profile) or profiles.get("default", {})
    weights = prof.get("section_weights", {})

    sections_out = []
    section_map = {}
    active_weight_total = 0
    conf_weighted = 0
    comp_weighted = 0

    for section in rs.get("sections", []):
        key = section["key"]
        fase_d = section.get("inativa_ate_fase") == "D"
        peso = weights.get(key, 0)

        if fase_d:
            sec = {
                "key": key, "label": section["label"], "peso": peso,
                "status": STATE_NAO_AVALIADO, "avaliada": False,
                "completude": None, "conformidade": None,
                "itens_total": 0, "itens_preenchidos": 0,
                "regras": [], "pendencias": [],
                "nota": "Ainda não avaliado nesta versão",
            }
            sections_out.append(sec)
            section_map[key] = sec
            continue

        evaln = _eval_section(school, section)
        sec = {
            "key": key, "label": section["label"], "peso": peso,
            "avaliada": True, **evaln,
        }
        sections_out.append(sec)
        section_map[key] = sec

        if peso > 0:
            active_weight_total += peso
            conf_weighted += peso * evaln["conformidade"]
            comp_weighted += peso * evaln["completude"]

    conformidade_geral = round(conf_weighted / active_weight_total) if active_weight_total > 0 else 0
    completude_geral = round(comp_weighted / active_weight_total) if active_weight_total > 0 else 0

    gt = rs.get("status_global_thresholds", {})
    selo_geral = _state_from_pct(conformidade_geral, gt)

    fresh = _freshness(school.get("updated_at"))
    maturity = _maturity(completude_geral, conformidade_geral, section_map, fresh, rs)

    return {
        "school_id": school.get("id"),
        "ruleset_id": rs.get("ruleset_id"),
        "versao": rs.get("versao"),
        "profile": profile,
        "completude_geral": completude_geral,
        "conformidade_geral": conformidade_geral,
        "selo_geral": selo_geral,
        "maturidade": maturity,
        "atualizacao": fresh,
        "sections": sections_out,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def summarize(school, profile="default"):
    """Versão enxuta para mini-cards da listagem (SSoT — mesmo cálculo)."""
    r = evaluate(school, profile=profile)
    return {
        "school_id": r["school_id"],
        "name": school.get("name"),
        "gestor": school.get("gestor_principal"),
        "situacao": school.get("status", "active"),
        "completude": r["completude_geral"],
        "conformidade": r["conformidade_geral"],
        "status": r["selo_geral"],
        "maturidade": r["maturidade"],
        "atualizacao": r["atualizacao"],
    }


def _eval_alert(alert, result):
    op = alert.get("op")
    if "section" in alert:
        sec = next((s for s in result["sections"] if s["key"] == alert["section"]), None)
        if not sec or sec.get("avaliada") is False:
            return False
        if op == "status_in":
            return sec.get("status") in (alert.get("value") or [])
        return False
    metric = alert.get("metric")
    if metric == "days_since":
        days = result["atualizacao"].get("days_since")
        if op == "gt_or_never":
            return days is None or days > alert.get("value", 999999)
        return False
    val = result.get(metric)
    if val is None:
        return False
    target = alert.get("value")
    return {"lt": val < target, "lte": val <= target, "gt": val > target,
            "gte": val >= target, "eq": val == target}.get(op, False)


def build_network_panel(schools, profile="default", ruleset=None):
    """
    Centro de Inteligência da Rede — deriva TUDO de evaluate() (SSoT).
    Executiva + Alertas + Fila de Prioridades + Mapa + Comparativos + slot de Evolução.
    """
    rs = ruleset or _RULESET
    alert_defs = rs.get("alerts", [])
    sev_weights = rs.get("severity_weights", {})
    action_defs = rs.get("priority_actions", {})
    porte_buckets = rs.get("porte_buckets", [])

    results = [(s, evaluate(s, profile=profile, ruleset=rs)) for s in schools]
    total = len(results)
    ativas = sum(1 for s, _ in results if s.get("status") == "active")

    # ---- Visão Executiva ----
    avaliadas = [r for _, r in results]
    conf_media = round(sum(r["conformidade_geral"] for r in avaliadas) / total) if total else 0
    comp_media = round(sum(r["completude_geral"] for r in avaliadas) / total) if total else 0
    dias_list = [r["atualizacao"]["days_since"] for r in avaliadas if r["atualizacao"].get("days_since") is not None]
    atualizacao_media_dias = round(sum(dias_list) / len(dias_list)) if dias_list else None
    nunca = sum(1 for r in avaliadas if r["atualizacao"].get("freshness") == "never")
    maturidade_dist = {str(n): 0 for n in range(1, 6)}
    for r in avaliadas:
        maturidade_dist[str(r["maturidade"]["nivel"])] += 1
    maturidade_media = round(sum(r["maturidade"]["nivel"] for r in avaliadas) / total) if total else 1
    status_dist = {}
    for r in avaliadas:
        status_dist[r["selo_geral"]] = status_dist.get(r["selo_geral"], 0) + 1

    executive = {
        "total": total, "ativas": ativas, "inativas": total - ativas,
        "conformidade_media": conf_media, "completude_media": comp_media,
        "atualizacao_media_dias": atualizacao_media_dias,
        "cadastros_nunca_atualizados": nunca,
        "maturidade_distribuicao": maturidade_dist,
        "maturidade_media": maturidade_media,
        "status_distribuicao": status_dist,
    }

    # ---- Alertas + Fila de Prioridades ----
    alerts_out = []
    priorities = []
    for school, r in results:
        nome = school.get("name", "Escola")
        crit_score = 0
        hits = []
        for a in alert_defs:
            if _eval_alert(a, r):
                sev = a.get("severidade", "medio")
                crit_score += sev_weights.get(sev, 10)
                hits.append(a)
                alerts_out.append({
                    "id": a["id"], "severidade": sev, "label": a["label"],
                    "school_id": r["school_id"], "school_name": nome,
                })
        # ações sugeridas (regras, sem IA)
        acts = []
        fresh = r["atualizacao"].get("freshness")
        if fresh == "never" and "never" in action_defs:
            acts.append(("never", action_defs["never"]))
        elif fresh == "stale" and "stale" in action_defs:
            acts.append(("stale", action_defs["stale"]))
        for key in ["seguranca", "acessibilidade", "agua_saneamento_energia", "conservacao"]:
            sec = next((s for s in r["sections"] if s["key"] == key), None)
            if sec and sec.get("avaliada") and sec.get("status") in ("nao_conforme", "critico") and key in action_defs:
                acts.append((key, action_defs[key]))
        if r["completude_geral"] < 30 and "completude" in action_defs:
            acts.append(("completude", action_defs["completude"]))
        for motivo, adef in acts:
            priorities.append({
                "school_id": r["school_id"], "school_name": nome,
                "motivo": motivo,
                "acao": adef["template"].replace("{escola}", nome),
                "peso": adef.get("peso", 50) + crit_score,
                "conformidade": r["conformidade_geral"],
            })

    sev_order = {"critico": 0, "alto": 1, "medio": 2}
    alerts_out.sort(key=lambda x: sev_order.get(x["severidade"], 9))
    priorities.sort(key=lambda x: x["peso"], reverse=True)
    for i, p in enumerate(priorities):
        p["ordem"] = i + 1

    # ---- Mapa da Rede ----
    map_points = []
    for school, r in results:
        lat, lng = school.get("latitude"), school.get("longitude")
        try:
            latf, lngf = float(lat), float(lng)
        except (TypeError, ValueError):
            continue
        map_points.append({
            "school_id": r["school_id"], "name": school.get("name"),
            "gestor": school.get("gestor_principal"),
            "lat": latf, "lng": lngf, "status": r["selo_geral"],
            "conformidade": r["conformidade_geral"], "completude": r["completude_geral"],
            "atualizacao": r["atualizacao"]["label"],
        })

    # ---- Comparativos ----
    def _porte_label(school):
        cap = school.get("capacidade_total_alunos") or 0
        try:
            cap = int(cap)
        except (TypeError, ValueError):
            cap = 0
        if cap <= 0:
            return "Não informado"
        for b in porte_buckets:
            if b.get("max") is None or cap <= b["max"]:
                return b["label"]
        return "Não informado"

    def _group(getter):
        buckets = {}
        for school, r in results:
            key = getter(school) or "Não informado"
            keys = key if isinstance(key, list) else [key]
            for k in (keys or ["Não informado"]):
                k = k or "Não informado"
                buckets.setdefault(k, []).append(r)
        out = []
        for k, rs_list in buckets.items():
            n = len(rs_list)
            out.append({
                "grupo": k, "escolas": n,
                "conformidade_media": round(sum(x["conformidade_geral"] for x in rs_list) / n),
                "completude_media": round(sum(x["completude_geral"] for x in rs_list) / n),
            })
        out.sort(key=lambda x: x["escolas"], reverse=True)
        return out

    zona_label = lambda s: ("Urbana" if s.get("zona_localizacao") == "urbana" else "Rural" if s.get("zona_localizacao") == "rural" else "Não informado")
    def _etapas(s):
        m = {"educacao_infantil": "Educação Infantil", "fundamental_anos_iniciais": "Fund. Anos Iniciais",
             "fundamental_anos_finais": "Fund. Anos Finais", "ensino_medio": "Ensino Médio", "eja": "EJA"}
        et = [v for k, v in m.items() if s.get(k)]
        return et or ["Não informado"]

    comparativos = {
        "zona": _group(zona_label),
        "distrito": _group(lambda s: s.get("distrito")),
        "etapas": _group(_etapas),
        "porte": _group(_porte_label),
    }

    return {
        "profile": profile,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "executive": executive,
        "alerts": alerts_out,
        "priorities": priorities,
        "map": map_points,
        "comparativos": comparativos,
        "evolucao": {
            "disponivel": False,
            "nota": "Arquitetura preparada. Histórico será alimentado por snapshots do ConformityResult (ruleset_id+versao+timestamp) em coleção append-only ctue_history (Sprint futura).",
            "series_previstas": ["conformidade", "completude", "atualizacao", "maturidade"],
        },
    }


# ---- Indicadores de infraestrutura (campos-fonte já usados pelo ruleset) ----
_INFRA_INDICADORES = [
    ("Acessibilidade (rampas)", lambda s: bool(s.get("possui_rampas"))),
    ("Banheiros acessíveis", lambda s: (s.get("banheiros_acessiveis") or 0) > 0 or bool(s.get("banheiros_adaptados"))),
    ("Abastecimento de água", lambda s: bool(str(s.get("abastecimento_agua") or "").strip())),
    ("Energia elétrica", lambda s: bool(str(s.get("energia_eletrica") or "").strip())),
    ("Esgotamento sanitário", lambda s: bool(str(s.get("saneamento") or "").strip())),
    ("Internet", lambda s: bool(s.get("possui_internet"))),
    ("Biblioteca", lambda s: bool(s.get("possui_biblioteca"))),
    ("Laboratório (ciências/informática)", lambda s: bool(s.get("possui_lab_ciencias") or s.get("possui_lab_informatica"))),
    ("Quadra esportiva", lambda s: bool(s.get("possui_quadra") or s.get("possui_quadra_esportiva"))),
    ("Cozinha", lambda s: bool(s.get("possui_cozinha"))),
    ("Extintores de incêndio", lambda s: (s.get("qtd_extintores") or s.get("extintores") or 0) > 0),
]

_MOTIVO_LABEL = {
    "never": "Realizar o cadastro técnico (CTUE) das unidades ainda não cadastradas",
    "stale": "Atualizar o CTUE das unidades desatualizadas",
    "seguranca": "Regularizar a Segurança (extintores, brigada e plano de evacuação)",
    "acessibilidade": "Regularizar a Acessibilidade (rampas, banheiros e sinalização)",
    "agua_saneamento_energia": "Validar Água, Saneamento e Energia",
    "conservacao": "Revisar a Conservação e necessidade de reforma",
    "completude": "Completar o cadastro das unidades com dados ausentes",
}


def _has_doc_categoria(school, categorias):
    presentes = {(d.get("categoria") or "").strip() for d in (school.get("documentos") or [])}
    return any(c in presentes for c in categorias)


def build_network_dossie(schools, profile="default", ruleset=None):
    """
    Dados consolidados para o Dossiê Institucional da Rede (PDF).
    CONSOME exclusivamente o SSoT: build_network_panel() + evaluate() por escola.
    Não cria novos indicadores de conformidade — apenas consolida/ordena o que já existe.
    """
    rs = ruleset or _RULESET
    # Panorama Geral (item 3) considera TODA a rede (total/ativas/inativas + médias).
    panel_all = build_network_panel(schools, profile=profile, ruleset=rs)
    # A partir do item 4 (Distribuição, Ranking, Prioridades, Infra, Obras, Doc, Diagnóstico,
    # Plano) considera-se APENAS escolas ativas.
    ativas = [s for s in schools if s.get("status") == "active"]
    panel = build_network_panel(ativas, profile=profile, ruleset=rs)
    results = [(s, evaluate(s, profile=profile, ruleset=rs)) for s in ativas]
    total = len(results) or 1

    # 5. Ranking de Conformidade (ordenado por conformidade desc — usa ConformityResult)
    ranking = []
    for s, r in results:
        ranking.append({
            "name": s.get("name") or "—",
            "conformidade": r["conformidade_geral"],
            "completude": r["completude_geral"],
            "atualizacao": r["atualizacao"]["label"],
            "maturidade_nivel": r["maturidade"]["nivel"],
            "maturidade_nome": r["maturidade"]["nome"],
            "status": r["selo_geral"],
            "situacao": "Ativa" if s.get("status") == "active" else "Inativa",
        })
    ranking.sort(key=lambda x: (x["conformidade"], x["completude"]), reverse=True)

    # 7. Infraestrutura da Rede (consolidação de campos-fonte existentes)
    infraestrutura = []
    for label, pred in _INFRA_INDICADORES:
        com = sum(1 for s, _ in results if pred(s))
        sem = len(results) - com
        infraestrutura.append({
            "indicador": label, "com": com, "sem": sem,
            "pct_com": round(com / total * 100),
        })

    # 8. Obras e Intervenções (consolidação das listas obras[])
    obras_por_situacao, obras_por_tipo = {}, {}
    total_obras = 0
    escolas_com_obras = 0
    for s, _ in results:
        lista = s.get("obras") or []
        if lista:
            escolas_com_obras += 1
        for o in lista:
            total_obras += 1
            sit = (o.get("situacao") or "Não informado").strip() or "Não informado"
            tp = (o.get("tipo") or "Não informado").strip() or "Não informado"
            obras_por_situacao[sit] = obras_por_situacao.get(sit, 0) + 1
            obras_por_tipo[tp] = obras_por_tipo.get(tp, 0) + 1
    obras = {
        "total_intervencoes": total_obras,
        "escolas_com_obras": escolas_com_obras,
        "por_situacao": sorted([{"grupo": k, "qtd": v} for k, v in obras_por_situacao.items()], key=lambda x: x["qtd"], reverse=True),
        "por_tipo": sorted([{"grupo": k, "qtd": v} for k, v in obras_por_tipo.items()], key=lambda x: x["qtd"], reverse=True),
    }

    # 9. Documentação (booleans de Situação Documental + categorias do repositório)
    doc_defs = [
        ("Planta / Projeto arquitetônico", lambda s: _has_doc_categoria(s, ["Planta Baixa", "Projeto Arquitetônico", "Memorial Descritivo"])),
        ("Alvará de Funcionamento", lambda s: bool(s.get("alvara_funcionamento")) or _has_doc_categoria(s, ["Alvará de Funcionamento"])),
        ("Licença Sanitária", lambda s: bool(s.get("licenca_sanitaria")) or _has_doc_categoria(s, ["Licença Sanitária"])),
        ("AVCB (Corpo de Bombeiros)", lambda s: bool(s.get("avcb_bombeiros")) or _has_doc_categoria(s, ["AVCB (Corpo de Bombeiros)"])),
        ("Habite-se", lambda s: bool(s.get("habite_se")) or _has_doc_categoria(s, ["Habite-se"])),
        ("Certificado de Potabilidade da Água", lambda s: bool(s.get("certificado_potabilidade")) or _has_doc_categoria(s, ["Certificado de Potabilidade da Água"])),
    ]
    documentacao = []
    for label, pred in doc_defs:
        com = sum(1 for s, _ in results if pred(s))
        documentacao.append({
            "documento": label, "com": com, "sem": len(results) - com,
            "pct_com": round(com / total * 100),
        })

    # 10. Diagnóstico Executivo (texto determinístico a partir dos indicadores)
    ex = panel["executive"]
    pontos_fortes, fragilidades, areas_prioritarias = [], [], []
    if ex["conformidade_media"] >= 65:
        pontos_fortes.append(f"Conformidade média da rede em {ex['conformidade_media']}%.")
    else:
        fragilidades.append(f"Conformidade média da rede em {ex['conformidade_media']}%, abaixo do patamar adequado.")
    if ex["completude_media"] >= 65:
        pontos_fortes.append(f"Completude cadastral média em {ex['completude_media']}%.")
    else:
        fragilidades.append(f"Completude cadastral média em {ex['completude_media']}%, indicando cadastros incompletos.")
    if ex.get("cadastros_nunca_atualizados"):
        fragilidades.append(f"{ex['cadastros_nunca_atualizados']} unidade(s) nunca tiveram o CTUE atualizado.")
    for ind in infraestrutura:
        if ind["pct_com"] >= 85:
            pontos_fortes.append(f"{ind['indicador']}: presente em {ind['pct_com']}% das unidades.")
        elif ind["pct_com"] < 50:
            fragilidades.append(f"{ind['indicador']}: presente em apenas {ind['pct_com']}% das unidades.")
    # Áreas prioritárias = agregação da Fila de Prioridades (SSoT), por motivo
    motivo_count = {}
    for p in panel["priorities"]:
        motivo_count[p["motivo"]] = motivo_count.get(p["motivo"], 0) + 1
    for motivo, qtd in sorted(motivo_count.items(), key=lambda x: x[1], reverse=True):
        areas_prioritarias.append(f"{_MOTIVO_LABEL.get(motivo, motivo)} ({qtd} unidade(s)).")
    diagnostico = {
        "pontos_fortes": pontos_fortes or ["Sem pontos fortes destacados nesta fotografia."],
        "fragilidades": fragilidades or ["Nenhuma fragilidade crítica identificada."],
        "areas_prioritarias": areas_prioritarias or ["Sem áreas prioritárias no momento."],
    }

    # 11. Plano de Ação Sugerido (consolida a Fila de Prioridades — sem nova lógica)
    plano_grupos = {}
    for p in panel["priorities"]:
        g = plano_grupos.setdefault(p["motivo"], {"escolas": set(), "peso": 0})
        g["escolas"].add(p["school_name"])
        g["peso"] += p.get("peso", 0)
    plano_acao = []
    for motivo, g in plano_grupos.items():
        exemplos = sorted(g["escolas"])
        plano_acao.append({
            "recomendacao": _MOTIVO_LABEL.get(motivo, motivo),
            "escolas": len(g["escolas"]),
            "exemplos": exemplos[:4],
            "peso": g["peso"],
        })
    plano_acao.sort(key=lambda x: x["peso"], reverse=True)

    return {
        "profile": profile,
        "profile_label": next((p["label"] for p in get_profiles() if p["key"] == profile), profile),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "executive": panel_all["executive"],
        "ranking": ranking,
        "priorities": panel["priorities"],
        "comparativos": panel["comparativos"],
        "infraestrutura": infraestrutura,
        "obras": obras,
        "documentacao": documentacao,
        "diagnostico": diagnostico,
        "plano_acao": plano_acao,
    }
