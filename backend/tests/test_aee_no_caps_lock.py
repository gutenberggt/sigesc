"""
Testa o lock de normalização do AEE.

Garantia: nenhuma das coleções AEE pode ser tocada pelo middleware de
normalização (`utils/text_normalize.py`). O texto deve voltar EXATAMENTE
como entrou, mesmo que esteja em CAPS narrativo.
"""
import pytest

from utils.text_normalize import (
    NORMALIZATION_BLOCKLIST,
    INPUT_WHITELIST,
    normalize_input_fields,
)


CAPS_INPUT = "O ALUNO APRESENTA DIFICULDADES DE ATENÇÃO E NECESSITA DE ACOMPANHAMENTO INDIVIDUALIZADO DURANTE AS ATIVIDADES PEDAGÓGICAS."
LOWER_INPUT = "o aluno apresenta dificuldades de atenção"


def test_blocklist_inclui_aee_essencial():
    """Garante explicitamente que as coleções AEE estão protegidas."""
    for coll in ("aee_plans", "aee_attendances", "aee_attendance_records", "aee_templates"):
        assert coll in NORMALIZATION_BLOCKLIST


def test_aee_nunca_normaliza_caps():
    """CAPS narrativo em AEE permanece literalmente igual."""
    payload = {"observacoes": CAPS_INPUT, "objetivo_geral": CAPS_INPUT}
    out = normalize_input_fields(payload, "aee_plans")
    assert out["observacoes"] == CAPS_INPUT, "AEE não pode normalizar CAPS"
    assert out["objetivo_geral"] == CAPS_INPUT


def test_aee_preserva_minusculas():
    payload = {"descricao": LOWER_INPUT}
    out = normalize_input_fields(payload, "aee_attendance_records")
    assert out["descricao"] == LOWER_INPUT


def test_aee_nao_esta_em_whitelist():
    """Defense-in-depth: nem mesmo se alguém adicionar AEE ao INPUT_WHITELIST,
    a função aplica normalização (o blocklist tem prioridade)."""
    for coll in ("aee_plans", "aee_attendances", "aee_attendance_records"):
        assert coll not in INPUT_WHITELIST


def test_outras_collections_continuam_funcionando():
    """Sanity: a normalização AINDA funciona para coleções permitidas."""
    payload = {"observations": CAPS_INPUT}
    out = normalize_input_fields(payload, "students")
    # Deve mudar (CAPS → sentence case) — exatamente o oposto do AEE.
    assert out["observations"] != CAPS_INPUT


def test_template_aee_seed_nao_em_caps():
    """Templates institucionais devem estar em sentence case (não CAPS)."""
    from seeds.aee_templates_seed import TEMPLATES_INSTITUCIONAIS
    import re
    caps_pattern = re.compile(r"[A-ZÁÊÃÇÕ]{15,}")
    for tpl in TEMPLATES_INSTITUCIONAIS:
        for field in (
            "descricao", "modalidade", "local", "objetivo_geral",
            "objetivos_especificos", "metodologia", "recursos_didaticos",
            "metodos_avaliacao", "estrategias_intervencao",
            "habilidades_priorizadas",
        ):
            v = tpl.get(field) or ""
            if isinstance(v, list):
                v = " ".join(str(x) for x in v)
            assert not caps_pattern.search(str(v)), (
                f"Template '{tpl.get('nome_template')}' campo '{field}' "
                f"contém trecho em CAPS: {str(v)[:120]}"
            )
