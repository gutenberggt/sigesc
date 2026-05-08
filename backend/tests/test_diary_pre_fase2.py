"""
Tests para utilitários pré-Fase 2 do Diário com Dependência.

Cobre:
- Constantes congeladas (label, limite, divisor) imutabilidade.
- Validador de plano `assert_uses_index` (IXSCAN ok / COLLSCAN falha).
- `validate_dependency_label` aceita oficial e rejeita variantes.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.diary_constants import (
    DEPENDENCY_DISPLAY_LABEL,
    FORBIDDEN_DEPENDENCY_LABELS,
    MAX_DEPENDENCY_STUDENTS_PER_DIARY,
    DIARY_DIVIDER_ITEM,
    DIARY_CONTRACT_VERSION,
    validate_dependency_label,
)
from utils.query_validation import (
    assert_uses_index,
    QueryNotUsingIndexError,
)


class TestDiaryConstants:
    def test_label_oficial_eh_dependencia(self):
        assert DEPENDENCY_DISPLAY_LABEL == "Dependência"

    def test_label_oficial_nao_esta_na_lista_proibida(self):
        assert DEPENDENCY_DISPLAY_LABEL not in FORBIDDEN_DEPENDENCY_LABELS

    def test_variantes_proibidas_cobrem_casos_comuns(self):
        for v in ("DP", "Dep.", "Dependente", "(Dep.)"):
            assert v in FORBIDDEN_DEPENDENCY_LABELS

    def test_limite_defensivo_e_30(self):
        # Mudança aqui requer atualizar o contrato (item 18).
        assert MAX_DEPENDENCY_STUDENTS_PER_DIARY == 30

    def test_divider_item_tem_flag_e_label(self):
        assert DIARY_DIVIDER_ITEM["is_divider"] is True
        assert DIARY_DIVIDER_ITEM["label"] == "Dependência de Estudos"
        assert DIARY_DIVIDER_ITEM["student_id"].startswith("__divider")

    def test_contract_version_v1(self):
        assert DIARY_CONTRACT_VERSION == 1

    def test_validate_dependency_label_aceita_oficial(self):
        validate_dependency_label("Dependência")  # não levanta

    def test_validate_dependency_label_rejeita_variantes(self):
        for v in ("DP", "Dep.", "Dependente"):
            with pytest.raises(ValueError, match="proibida"):
                validate_dependency_label(v)

    def test_validate_dependency_label_rejeita_qualquer_outro(self):
        with pytest.raises(ValueError, match="não oficial"):
            validate_dependency_label("Reforço")


class TestAssertUsesIndex:
    def _plan(self, stages_chain, index_name=None):
        """Constrói explain output simulado.

        stages_chain: lista de stages do mais externo ao mais interno.
        Ex.: ["FETCH", "IXSCAN"]
        """
        stage = None
        for s in reversed(stages_chain):
            new = {"stage": s}
            if stage:
                new["inputStage"] = stage
            if s == "IXSCAN" and index_name:
                new["indexName"] = index_name
            stage = new
        return {"queryPlanner": {"winningPlan": stage}}

    def test_ixscan_passa(self):
        plan = self._plan(["FETCH", "IXSCAN"])
        assert_uses_index(plan, description="test")  # não levanta

    def test_collscan_levanta(self):
        plan = self._plan(["COLLSCAN"])
        with pytest.raises(QueryNotUsingIndexError, match="COLLSCAN"):
            assert_uses_index(plan, description="test")

    def test_sem_ixscan_levanta(self):
        plan = self._plan(["FETCH"])  # sem IXSCAN
        with pytest.raises(QueryNotUsingIndexError, match="não usa IXSCAN"):
            assert_uses_index(plan, description="test")

    def test_index_name_diferente_levanta(self):
        plan = self._plan(["FETCH", "IXSCAN"], index_name="ix_other")
        with pytest.raises(QueryNotUsingIndexError, match="diferente do esperado"):
            assert_uses_index(plan, expected_index_name="ix_expected", description="test")

    def test_index_name_igual_passa(self):
        plan = self._plan(["FETCH", "IXSCAN"], index_name="ix_dep_tenant_class_course_status")
        assert_uses_index(
            plan, expected_index_name="ix_dep_tenant_class_course_status", description="test"
        )
