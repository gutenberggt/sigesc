"""Guards do P0 — histórico de Notas do professor no DVD."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PARITY = (ROOT / "routers" / "grades_dvd_parity.py").read_text(encoding="utf-8")
WRITE = (ROOT / "routers" / "grades_historical_backfill_dvd.py").read_text(encoding="utf-8")
CUTOVER = (ROOT / "services" / "grade_cutover_history.py").read_text(encoding="utf-8")
GENERIC = (ROOT / "services" / "dvd_cutover_legacy_provenance.py").read_text(encoding="utf-8")
ROUTERS_INIT = (ROOT / "routers" / "__init__.py").read_text(encoding="utf-8")
GRADE_SCOPE = (ROOT / "services" / "grade_assignment_scope.py").read_text(encoding="utf-8")


def test_paridade_e_escrita_compartilham_ssot_geral_do_cutover():
    assert "from services.grade_cutover_history import" in PARITY
    assert "from services.grade_cutover_history import" in WRITE
    assert "resolve_validated_cutover_legacy_assignment" in CUTOVER
    assert "expected_class_id=context.class_id" in CUTOVER
    assert "expected_component_id=context.course_id" in CUTOVER
    assert "APPROVED_HISTORICAL_CUTOVER_PHASES" in GENERIC
    assert '"38G-B"' in GENERIC
    assert 'provenance.get("apply_state") == "ACTIVATED"' in GENERIC
    assert 'source_legacy_assignment_id' in GENERIC
    assert '"status": "ativo"' in GENERIC
    assert "_legacy_staff_matches_teacher" in GENERIC
    assert "historical_grade_write_evidence" in WRITE


def test_legado_e_visivel_mas_permanece_sem_apropriacao_automatica():
    assert 'dvd_read_only_fields' in PARITY
    assert 'history_source' in PARITY
    assert 'grades_legacy' in PARITY
    assert 'field not in ownership' in PARITY
    assert 'out["grade_ownership"]' in PARITY
    assert 'GRADE_LEGACY_FIELD_REQUIRES_REVIEW' in GRADE_SCOPE
    assert 'GRADE_LEGACY_FIELD_REQUIRES_REVIEW' not in WRITE  # motor canônico continua decidindo


def test_ponte_historica_nao_grava_dados_crus_nem_retrodata_assignment():
    forbidden = (
        '.grades.insert_one(',
        '.grades.update_one(',
        '.grades.update_many(',
        '.grades.delete_one(',
        '.grades.delete_many(',
        '.teacher_class_assignments.update_one(',
        '.teacher_class_assignments.update_many(',
    )
    for token in forbidden:
        assert token not in CUTOVER
        assert token not in WRITE
    assert 'assignment["valid_from"] = evidence[HISTORICAL_WRITE_PERIOD_START_FLAG]' in WRITE
    assert "contexto efêmero" in WRITE


def test_escrita_reutiliza_motor_canonico_de_ownership():
    assert "_build_historical_ownership_adapter" in WRITE
    assert "ownership = await base_apply(" in WRITE
    assert "apply_grade_field_ownership(" not in WRITE
    assert "field_context = _historical_context(context, evidence)" in WRITE


def test_auditoria_de_escrita_historica_e_explicita():
    assert '"historical_grade_write": True' in WRITE
    assert '"historical_fields": sorted(historical_fields)' in WRITE
    assert '"historical_source_legacy_assignment_ids": sorted(source_ids)' in WRITE
    assert "_build_historical_save_adapter" in WRITE


def test_pdf_usa_a_mesma_projecao_historica_da_tela():
    assert '_project_grade_for_assignment(grade, context)' in PARITY
    assert 'dvd_mod._mask_grade_for_assignment = mask_grade_with_legacy_history' in PARITY
    assert 'dvd_mod._dvd_pdf = dvd_pdf_with_legacy_history' in PARITY


def test_instalacao_ocorre_adapter_hardening_paridade_student_scope():
    assert 'from .grades_dvd_parity import install_grades_dvd_parity' in ROUTERS_INIT
    assert 'from .grades_dvd_student_scope import install_grades_dvd_student_scope' in ROUTERS_INIT
    assert 'configured = install_grades_dvd_adapter(' in ROUTERS_INIT
    assert 'configured = install_grades_dvd_hardening(' in ROUTERS_INIT
    assert 'configured = install_grades_dvd_parity(' in ROUTERS_INIT
    assert 'return install_grades_dvd_student_scope(' in ROUTERS_INIT
    assert ROUTERS_INIT.index('install_grades_dvd_adapter(') < ROUTERS_INIT.index('install_grades_dvd_hardening(')
    assert ROUTERS_INIT.index('install_grades_dvd_hardening(') < ROUTERS_INIT.index('install_grades_dvd_parity(')
    assert ROUTERS_INIT.index('install_grades_dvd_parity(') < ROUTERS_INIT.index('install_grades_dvd_student_scope(')
    assert "install_grades_historical_backfill_dvd()" in PARITY


def test_generalizacao_runtime_continua_podendo_patchar_a_prova_de_leitura():
    assert "safe_cutover_legacy_assignment as _safe_cutover_legacy_assignment" in PARITY
    assert "legacy = await _safe_cutover_legacy_assignment" in PARITY


def test_paridade_nao_substitui_rotas_de_escrita():
    assert '@base_router.post' not in PARITY
    assert '@base_router.put' not in PARITY
    assert '@base_router.delete' not in PARITY
    assert '@base_router.post' not in WRITE
    assert '@base_router.put' not in WRITE
    assert '@base_router.delete' not in WRITE
