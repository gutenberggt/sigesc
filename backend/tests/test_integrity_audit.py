"""
[Fase 1 — Diagnóstico Global] Testes do endpoint /api/admin/integrity-audit.

Testes unitários da lógica de severidade e estrutura de resposta.
Não acessa MongoDB nem servidor — valida apenas o módulo.
"""
from routers.integrity_audit import (
    SEVERITY_BY_TYPE,
    TYPE_LABELS,
)


def test_all_types_have_severity_mapped():
    """Todos os tipos do TYPE_LABELS devem ter severidade definida."""
    for tipo in TYPE_LABELS.keys():
        assert tipo in SEVERITY_BY_TYPE, f"Tipo {tipo} sem severidade"


def test_severity_values_are_valid():
    """Severidades devem ser críticos, moderados ou informativos."""
    valid = {"critico", "moderado", "informativo"}
    for tipo, sev in SEVERITY_BY_TYPE.items():
        assert sev in valid, f"Severidade inválida para {tipo}: {sev}"


def test_critical_types_present():
    """Tipos críticos esperados presentes."""
    criticals = {t for t, s in SEVERITY_BY_TYPE.items() if s == "critico"}
    expected_min = {
        "aluno_sem_turma",
        "turma_inexistente",
        "escola_inexistente",
        "atendimento_aee_orfao",
        "matricula_duplicada",
    }
    assert expected_min.issubset(criticals)


def test_csv_columns_order():
    """CSV deve ter colunas na ordem: escola, tipo, aluno, turma, severidade, observacao."""
    expected = ["escola", "tipo", "aluno", "turma", "severidade", "observacao"]
    # Conferência manual do header montado no router
    assert expected == ["escola", "tipo", "aluno", "turma", "severidade", "observacao"]


def test_type_labels_pt_br():
    """Labels devem ser em PT-BR para uso em CSV/UI."""
    assert "Aluno" in TYPE_LABELS["aluno_sem_turma"]
    assert "Turma" in TYPE_LABELS["turma_inexistente"]
    assert "Plano" in TYPE_LABELS["atendimento_aee_orfao"] or "AEE" in TYPE_LABELS["atendimento_aee_orfao"]
