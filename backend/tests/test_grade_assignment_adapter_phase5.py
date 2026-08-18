"""Guards estruturais da Fase 5.

Não importam o FastAPI completo: inspecionam a fonte para manter invariantes de
arquitetura que complementam os testes puros de ``grade_assignment_scope``.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = (ROOT / "routers" / "grades_dvd.py").read_text(encoding="utf-8")
ROUTERS_INIT = (ROOT / "routers" / "__init__.py").read_text(encoding="utf-8")


def test_fase5_reutiliza_router_e_nao_cria_grades_v2():
    assert "GradesV2" not in ADAPTER
    assert 'base_router.get("/by-class/{class_id}/{course_id}")' in ADAPTER
    assert 'base_router.post("/batch")' in ADAPTER
    assert 'base_router.get("/pdf/{class_id}/{course_id}")' in ADAPTER


def test_fase5_instala_adapter_no_setup_grades_existente():
    assert "_setup_grades_router" in ROUTERS_INIT
    assert "install_grades_dvd_adapter" in ROUTERS_INIT
    assert "setup_grades_router(" in ROUTERS_INIT


def test_fase5_sync_offline_nao_pode_gravar_grades_cru():
    assert "def _install_sync_adapter" in ADAPTER
    assert "sync_mod.process_sync_operation = dvd_process" in ADAPTER
    assert "_save_one_dvd_grade(" in ADAPTER
    assert 'if op.collection != "grades"' in ADAPTER


def test_fase5_sync_pull_mascara_notas_de_outros_professores():
    assert "sync_mod.fetch_collection_data_paginated = dvd_fetch" in ADAPTER
    assert "_mask_grade_for_teacher" in ADAPTER
    assert 'if collection != "grades" or user.get("role") != "professor"' in ADAPTER


def test_fase5_periodos_usam_calendario_letivo_institucional():
    assert "current_db.calendario_letivo.find_one" in ADAPTER
    assert '"ano_letivo": academic_year' in ADAPTER
    assert '"school_id": school_id' in ADAPTER
    assert '"school_id": None' in ADAPTER


def test_fase5_pdf_e_leitura_preservam_privacidade_por_assignment():
    assert "owned_fields_for_assignment" in ADAPTER
    assert "foreign_value" in ADAPTER
    assert 'out["grade_ownership"]' in ADAPTER
    assert '"final_average": None if foreign_value' in ADAPTER
    assert "generate_grades_report_pdf" in ADAPTER
