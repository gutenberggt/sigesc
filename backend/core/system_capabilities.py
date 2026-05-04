"""Registry de capacidades reais do sistema SIGESC (Mai/2026).

Fonte da verdade do que o produto FAZ hoje. A camada de governança da IA
(`recommendation_validator`) consulta este registry para bloquear sugestões
fictícias, garantindo que toda recomendação retornada ao usuário seja
EXECUTÁVEL no estado atual do sistema.

Convenções:
- chave: identificador estável e curto da capacidade
- valor: True quando a feature existe no produto, False quando ainda não

Quando uma feature for entregue (ex.: G3 já em produção), basta flipar
a flag aqui — não precisa caçar lugares em código que dependiam dela.
"""
from __future__ import annotations

SYSTEM_CAPABILITIES: dict[str, bool] = {
    # Cadastros e gestão de pessoas
    "user_management": True,
    "staff_management": True,        # Gestão de Servidores
    "school_assignments": True,      # Lotações
    "student_edit": True,
    "responsavel_edit": True,

    # Operação pedagógica
    "grade_edit": True,
    "attendance_edit": True,
    "curriculum_coverage": True,
    "learning_objects": True,
    "diary_launch": True,            # Lançamento de diário/aulas

    # Governança institucional
    "plano_acao": True,
    "intervention_alerts": True,
    "permission_matrix": True,
    "snapshots_audit": True,         # G1.5
    "verifiable_docs": True,         # G1.6
    "school_documents": True,        # G1.7 — Declarações
    "relatorio_mensal_executivo": True,  # G3

    # Comunicação
    "messaging": True,
    "email_resend": True,

    # NÃO IMPLEMENTADO (IA não deve sugerir)
    "alert_config": False,           # /admin/configuracoes/alertas — não existe
    "alert_rules_per_etapa": False,  # Regras por Educação Infantil/Fund I/II
    "ai_settings_panel": False,      # Configurações de IA por usuário
    "branding_per_school": False,    # Branding individual por escola (G4 não pronto)
    "calendar_integration": False,   # Google Calendar etc.
    "sso_external": False,           # SSO terceiro
    "exports_lgpd_per_mantenedora": False,  # Backlog
    "csv_invite_via_resend": False,  # Backlog
}


def feature_exists(capability: str) -> bool:
    """Retorna True se a capacidade está implementada no SIGESC.

    Conservador: capacidades desconhecidas retornam False (a IA NÃO deve
    sugerir o que não está mapeado aqui).
    """
    return SYSTEM_CAPABILITIES.get(capability, False)
