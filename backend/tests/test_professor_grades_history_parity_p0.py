"""Guards do P0 — histórico de Notas do professor no DVD.

Os testes são estruturais para rodar no gate puro do Diário por Vínculo sem
Mongo real. A validação de produção permanece read-only e mede os dados reais.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PARITY = (ROOT / "routers" / "grades_dvd_parity.py").read_text(encoding="utf-8")
ROUTERS_INIT = (ROOT / "routers" / "__init__.py").read_text(encoding="utf-8")
GRADE_SCOPE = (ROOT / "services" / "grade_assignment_scope.py").read_text(encoding="utf-8")


def test_paridade_revalida_exatamente_o_cutover_38g_b():
    assert 'source_legacy_assignment_id' in PARITY
    assert 'provenance.get("apply_phase") != "38G-B"' in PARITY
    assert 'provenance.get("apply_state") != "ACTIVATED"' in PARITY
    assert '"course_id": context.course_id' in PARITY
    assert '"status": "ativo"' in PARITY
    assert '_legacy_staff_matches_teacher' in PARITY


def test_legado_e_visivel_mas_permanece_sem_autoria():
    assert 'dvd_read_only_fields' in PARITY
    assert 'history_source' in PARITY
    assert 'grades_legacy' in PARITY
    assert 'field not in ownership' in PARITY
    assert 'out["grade_ownership"]' in PARITY
    # O motor de escrita original continua proibindo apropriação automática.
    assert 'GRADE_LEGACY_FIELD_REQUIRES_REVIEW' in GRADE_SCOPE


def test_paridade_nao_escreve_em_grades_nem_em_ownership():
    forbidden = (
        '.grades.insert_one(',
        '.grades.update_one(',
        '.grades.update_many(',
        '.grades.delete_one(',
        '.grades.delete_many(',
        'apply_grade_field_ownership(',
    )
    for token in forbidden:
        assert token not in PARITY


def test_pdf_usa_a_mesma_projecao_historica_da_tela():
    assert '_project_grade_for_assignment(grade, context)' in PARITY
    assert 'dvd_mod._mask_grade_for_assignment = mask_grade_with_legacy_history' in PARITY
    assert 'dvd_mod._dvd_pdf = dvd_pdf_with_legacy_history' in PARITY


def test_instalacao_ocorre_depois_do_adapter_e_do_hardening_fase5():
    assert 'from .grades_dvd_parity import install_grades_dvd_parity' in ROUTERS_INIT
    assert 'configured = install_grades_dvd_adapter(' in ROUTERS_INIT
    assert 'configured = install_grades_dvd_hardening(' in ROUTERS_INIT
    assert 'return install_grades_dvd_parity(' in ROUTERS_INIT
    assert ROUTERS_INIT.index('install_grades_dvd_adapter(') < ROUTERS_INIT.index('install_grades_dvd_hardening(')
    assert ROUTERS_INIT.index('install_grades_dvd_hardening(') < ROUTERS_INIT.index('install_grades_dvd_parity(')


def test_adaptador_p0_nao_substitui_rotas_de_escrita():
    assert '_save_one_dvd_grade' not in PARITY
    assert '@base_router.post' not in PARITY
    assert '@base_router.put' not in PARITY
    assert '@base_router.delete' not in PARITY
