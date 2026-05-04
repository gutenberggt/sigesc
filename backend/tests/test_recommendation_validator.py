"""Testes do firewall de IA (Mai/2026) — `recommendation_validator`.

Cobre:
- Bloqueio por keyword (configurar alerta, sensores, etc.)
- Bloqueio por route_hint (/admin/configuracoes/alertas)
- Capacidade desconhecida = bloquear (postura conservadora)
- Capacidade existente = passar
- Fallback humano quando lista fica vazia
- Log de rejeições não derruba o fluxo
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.recommendation_map import RECOMMENDATION_CAPABILITY_MAP
from core.system_capabilities import SYSTEM_CAPABILITIES, feature_exists
from services.recommendation_validator import (fallback_recommendation,
                                                 reason_for_block,
                                                 validate_recommendations)


# ---------------------- Capacidades ----------------------

def test_alert_config_capability_disabled():
    assert feature_exists("alert_config") is False


def test_unknown_capability_returns_false():
    assert feature_exists("inventei_essa") is False


def test_existing_capabilities():
    assert feature_exists("plano_acao")
    assert feature_exists("permission_matrix")
    assert feature_exists("relatorio_mensal_executivo")


# ---------------------- Bloqueio por keyword ----------------------

def test_block_calibrar_sensores():
    rec = {
        "acao": "Calibrar sensores de alerta para Educação Infantil",
        "justificativa": "CMEI com zero alertas",
    }
    assert reason_for_block(rec) == "alert_config"


def test_block_configurar_alerta():
    rec = {"acao": "Configurar alerta para frequência baixa"}
    assert reason_for_block(rec) == "alert_config"


def test_block_alertas_personalizados():
    rec = {"acao": "Criar alertas personalizados por categoria"}
    assert reason_for_block(rec) == "alert_config"


# ---------------------- Bloqueio por route_hint ----------------------

def test_block_route_inexistente_alertas():
    rec = {
        "acao": "Acessar /admin/configuracoes/alertas e ajustar",
        "justificativa": "ajustar gatilhos",
    }
    assert reason_for_block(rec) == "alert_config"


def test_block_route_ai_settings():
    rec = {"acao": "Vá em /admin/ia para reconfigurar a análise"}
    assert reason_for_block(rec) == "ai_settings_panel"


# ---------------------- Recomendações válidas passam ----------------------

def test_valid_intervencoes():
    rec = {"acao": "Acessar /admin/intervencoes e resolver alertas abertos"}
    assert reason_for_block(rec) is None


def test_valid_visita_tecnica():
    rec = {
        "acao": "Realizar visita técnica em 3 escolas críticas",
        "justificativa": "queda de cobertura",
    }
    assert reason_for_block(rec) is None


# ---------------------- Pipeline completo ----------------------

def test_validate_filters_invalid_keeps_valid():
    recs = [
        {"acao": "Configurar sensores de alerta", "impacto": "alto"},  # ❌
        {"acao": "Realizar visita técnica em CMEIs", "impacto": "medio"},  # ✅
        {"acao": "Acompanhar manualmente com equipe pedagógica", "impacto": "baixo"},  # ✅
    ]
    out = validate_recommendations(recs, context="test")
    assert len(out) == 2
    assert all("sensor" not in (r.get("acao") or "").lower() for r in out)


def test_validate_applies_fallback_when_empty():
    recs = [
        {"acao": "Configurar sensores de alerta", "impacto": "alto"},
        {"acao": "Calibrar regras personalizadas", "impacto": "medio"},
    ]
    out = validate_recommendations(recs, context="test", apply_fallback=True)
    assert len(out) == 1
    assert out[0].get("_fallback") is True


def test_validate_no_fallback_when_disabled():
    recs = [{"acao": "Configurar sensores"}]
    out = validate_recommendations(recs, context="test", apply_fallback=False)
    assert out == []


def test_validate_handles_non_list():
    out = validate_recommendations("not a list", context="test", apply_fallback=True)
    assert len(out) == 1
    assert out[0].get("_fallback") is True


def test_validate_handles_non_dict_items():
    recs = ["string solta", None, {"acao": "Visita técnica nas escolas top3"}]
    out = validate_recommendations(recs, context="test", apply_fallback=False)
    assert len(out) == 1
    assert "Visita" in out[0]["acao"]


def test_fallback_has_required_fields():
    fb = fallback_recommendation()
    assert "acao" in fb
    assert "responsavel" in fb
    assert fb.get("_fallback") is True


# ---------------------- Cenário real do PDF do user ----------------------

def test_real_world_cmei_recommendation_blocked():
    """Reproduz exatamente a recomendação que apareceu no PDF do user."""
    rec = {
        "titulo": "Calibrar sensores de alerta para Educação Infantil",
        "descricao": (
            "Validar em /admin/configuracoes/alertas se os gatilhos estão "
            "ajustados ao perfil da unidade (CMEI). A ausência total de "
            "alertas pode indicar que o sistema não monitora campos de "
            "desenvolvimento ou frequência específicos dessa etapa."
        ),
        "prioridade": 1, "impacto": "medio", "prazo_dias": 14,
        "responsavel": "coordenador",
    }
    assert reason_for_block(rec) == "alert_config"


def test_capability_map_uses_only_real_capabilities():
    """Garante que toda capability listada no mapa existe no registry."""
    for rule in RECOMMENDATION_CAPABILITY_MAP:
        cap = rule["capability"]
        assert cap in SYSTEM_CAPABILITIES, f"capability '{cap}' não está em SYSTEM_CAPABILITIES"
