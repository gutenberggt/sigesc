"""
Testes da padronização de SITUAÇÃO para turmas conceituais (Ed. Infantil + 1º/2º ano).

Regra (aplicada em todo o sistema):
- Durante o ano (nem todas as B1-B4 lançadas): "Em andamento"
- Ao encerrar (todas as B1-B4 lançadas):
    - Educação Infantil -> "Concluiu a etapa"
    - 1º e 2º ano       -> "Promovido(a)"
- Status especiais (transferido/desistente/falecido) sempre prevalecem.
- Turmas avaliadas (3º ao 9º, EJA) NÃO usam esses rótulos.
"""

from grade_calculator import (
    determinar_resultado_documento,
    STATUS_EM_ANDAMENTO,
    STATUS_CONCLUIU_ETAPA,
    STATUS_PROMOVIDO,
)

REGRAS = {"media_aprovacao": 5.0, "frequencia_minima": 75.0}


def _comp(has_all_bims, media=10, has_any_grade=None):
    if has_any_grade is None:
        has_any_grade = has_all_bims
    return {"nome": "Comp", "media": media, "atendimento_programa": "",
            "has_all_bims": has_all_bims, "has_b4": has_all_bims,
            "has_any_grade": has_any_grade}


def test_infantil_em_andamento():
    r = determinar_resultado_documento("active", "Pré II", "educacao_infantil",
                                       None, [_comp(False)], REGRAS)
    assert r["resultado"] == STATUS_EM_ANDAMENTO


def test_infantil_concluiu_etapa():
    r = determinar_resultado_documento("active", "Pré II", "educacao_infantil",
                                       None, [_comp(True)], REGRAS)
    assert r["resultado"] == STATUS_CONCLUIU_ETAPA


def test_primeiro_ano_em_andamento():
    r = determinar_resultado_documento("active", "1º Ano", "fundamental_anos_iniciais",
                                       None, [_comp(False)], REGRAS)
    assert r["resultado"] == STATUS_EM_ANDAMENTO


def test_primeiro_ano_promovido():
    r = determinar_resultado_documento("active", "1º Ano", "fundamental_anos_iniciais",
                                       None, [_comp(True)], REGRAS)
    assert r["resultado"] == STATUS_PROMOVIDO


def test_segundo_ano_promovido():
    r = determinar_resultado_documento("active", "2º Ano", "fundamental_anos_iniciais",
                                       None, [_comp(True)], REGRAS)
    assert r["resultado"] == STATUS_PROMOVIDO


def test_status_especial_prevalece_em_conceitual():
    r = determinar_resultado_documento("transferido", "1º Ano", "fundamental_anos_iniciais",
                                       None, [_comp(True)], REGRAS)
    assert r["resultado"] == "TRANSFERIDO(A)"


def test_turma_avaliada_nao_usa_rotulos_conceituais():
    # 5º ano (avaliado) após 4º bimestre -> APROVADO (não 'Promovido(a)')
    comp = {"nome": "Mat", "media": 7.0, "atendimento_programa": "",
            "has_all_bims": True, "has_b4": True}
    r = determinar_resultado_documento("active", "5º Ano", "fundamental_anos_iniciais",
                                       "2000-01-01", [comp], REGRAS)
    assert r["resultado"] == "APROVADO"
    assert r["resultado"] not in (STATUS_EM_ANDAMENTO, STATUS_CONCLUIU_ETAPA, STATUS_PROMOVIDO)


def test_conceitual_ignora_componente_sem_nota():
    # 1 componente completo (4 bims) + 1 componente nunca avaliado -> Promovido(a)
    cheio = _comp(True)
    vazio = {"nome": "Vazio", "media": None, "atendimento_programa": "",
             "has_all_bims": False, "has_b4": False, "has_any_grade": False}
    r = determinar_resultado_documento("active", "1º Ano", "fundamental_anos_iniciais",
                                       None, [cheio, vazio], REGRAS)
    assert r["resultado"] == STATUS_PROMOVIDO


def test_conceitual_componente_parcial_fica_em_andamento():
    # 1 componente completo + 1 componente PARCIAL (tem nota mas faltam bims) -> Em andamento
    cheio = _comp(True)
    parcial = {"nome": "Parcial", "media": 10, "atendimento_programa": "",
               "has_all_bims": False, "has_b4": False, "has_any_grade": True}
    r = determinar_resultado_documento("active", "Pré II", "educacao_infantil",
                                       None, [cheio, parcial], REGRAS)
    assert r["resultado"] == STATUS_EM_ANDAMENTO
