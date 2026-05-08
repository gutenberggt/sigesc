"""
Constantes congeladas do Diário com Dependência.

[Fev/2026] Ver /app/docs/DIARY_API_CONTRACT.md (contract_version: 1).

Estes valores são CONGELADOS. Mudança requer bump de contract_version.
"""
from __future__ import annotations

# ============================================================================
# 1. Nomenclatura visual — string única, sem variantes.
# Proibido: "DP", "Depend.", "Dependente", "Aluno dependência", "(Dep.)".
# ============================================================================
DEPENDENCY_DISPLAY_LABEL = "Dependência"

# Variantes proibidas (validação automática em testes/lint).
FORBIDDEN_DEPENDENCY_LABELS = {
    "DP", "Dep.", "Depend.", "Dependente", "Aluno dependência",
    "(Dep.)", "(DP)", "Em DP", "EM DP",
}


# ============================================================================
# 2. Limite defensivo de alunos em dependência por carregamento de diário.
# Acima disso → log crítico + flag administrativa, mas SEM quebrar o diário.
# Alvo: situação anômala (erro operacional de seed/import).
# ============================================================================
MAX_DEPENDENCY_STUDENTS_PER_DIARY = 30


# ============================================================================
# 3. Marcador de divisor visual (item especial entre regulares e deps).
# Frontend renderiza como linha horizontal + título "Dependência de Estudos".
# ============================================================================
DIARY_DIVIDER_ITEM = {
    "is_divider": True,
    "label": "Dependência de Estudos",
    "student_id": "__divider_dependency__",
}


# ============================================================================
# 4. Versão do contrato (espelha DIARY_API_CONTRACT.md).
# ============================================================================
DIARY_CONTRACT_VERSION = 1


# ============================================================================
# 5. SLA de performance (do contrato — usado em alertas/observabilidade).
# ============================================================================
DIARY_SLA_P95_MS = 200
DIARY_SLA_P99_MS = 500
DIARY_SLA_PAYLOAD_KB = 50


# ============================================================================
# Helpers de validação (usados em testes e seeds).
# ============================================================================
def validate_dependency_label(label: str) -> None:
    """Levanta ValueError se o label não é o oficial.

    Use em testes de PRs que adicionam UI/PDF/ficha referenciando dependência.
    """
    if label != DEPENDENCY_DISPLAY_LABEL:
        if label in FORBIDDEN_DEPENDENCY_LABELS:
            raise ValueError(
                f"Variante proibida '{label}'. Use '{DEPENDENCY_DISPLAY_LABEL}' (constante única)."
            )
        raise ValueError(
            f"Label não oficial: '{label}'. Esperado: '{DEPENDENCY_DISPLAY_LABEL}'."
        )
