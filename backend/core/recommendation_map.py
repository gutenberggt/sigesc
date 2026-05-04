"""Mapa palavras-chave → capacidade do sistema (Mai/2026).

Cada regra associa um conjunto de termos comumente usados pela IA quando
sugere uma ação a uma capacidade do `system_capabilities`. Se a capacidade
não existe, a recomendação é descartada pelo validator.

Convenções:
- `keywords`: lista de strings em minúsculas, comparadas via substring contra
  `acao + justificativa` da recomendação (já em minúsculas)
- `capability`: chave de `SYSTEM_CAPABILITIES`
- `route_hints`: opcional, lista de paths (ex.: `/admin/foo`) que se aparecerem
  acionam a regra mesmo sem keyword textual

A ordem dos itens importa: a primeira regra que casar bloqueia.
"""
from __future__ import annotations

RECOMMENDATION_CAPABILITY_MAP: list[dict] = [
    # Configuração de alertas personalizados — não existe
    {
        "keywords": [
            "configurar alerta", "configuração de alerta", "configuracao de alerta",
            "configurar sensor", "configurar sensores",
            "sensores de alerta", "ajustar gatilho", "calibrar sensor",
            "alertas personalizados", "regra de alerta", "regras de alerta",
            "regras personalizadas", "parametrizar alerta",
        ],
        "route_hints": [
            "/admin/configuracoes/alertas",
            "/admin/alertas/configuracoes",
            "/admin/configuracoes-alertas",
        ],
        "capability": "alert_config",
    },
    # Regras específicas por etapa (Infantil, Fund I/II)
    {
        "keywords": [
            "regras específicas para educação infantil",
            "regras específicas para cmei",
            "calibrar para cmei",
            "monitorar campos de desenvolvimento",
            "monitorar desenvolvimento infantil",
        ],
        "capability": "alert_rules_per_etapa",
    },
    # Painel de configurações de IA
    {
        "keywords": [
            "configurações de ia", "configurar a ia", "ajustar a ia",
            "preferências de ia", "ajustar prompt",
        ],
        "route_hints": ["/admin/ia", "/admin/ai-settings", "/admin/configuracoes/ia"],
        "capability": "ai_settings_panel",
    },
    # Branding por escola
    {
        "keywords": [
            "branding por escola", "logotipo por escola", "tema individual da escola",
            "personalizar visual da escola",
        ],
        "capability": "branding_per_school",
    },
    # SSO / OAuth externo
    {
        "keywords": ["sso", "single sign-on", "login externo", "oauth corporativo"],
        "capability": "sso_external",
    },
    # Integração calendário
    {
        "keywords": [
            "integrar com google calendar", "sincronizar agenda", "calendário externo",
        ],
        "capability": "calendar_integration",
    },
    # Export LGPD por mantenedora
    {
        "keywords": [
            "export lgpd por mantenedora", "exportar dados da mantenedora", "portabilidade lgpd",
        ],
        "capability": "exports_lgpd_per_mantenedora",
    },
    # CSV → convite Resend
    {
        "keywords": [
            "convite automático por csv", "convidar via csv", "envio de convite por csv",
        ],
        "capability": "csv_invite_via_resend",
    },
]
