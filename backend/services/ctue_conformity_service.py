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
