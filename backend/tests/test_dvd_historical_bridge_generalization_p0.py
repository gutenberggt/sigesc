"""Guards estruturais do P0 — generalização do bridge histórico DVD."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = (ROOT / "routers" / "dvd_historical_bridge_generalization.py").read_text(encoding="utf-8")
ROUTERS_INIT = (ROOT / "routers" / "__init__.py").read_text(encoding="utf-8")
SERVICE = (ROOT / "services" / "dvd_cutover_legacy_provenance.py").read_text(encoding="utf-8")
ATTENDANCE = (ROOT / "routers" / "attendance_tabs_dvd.py").read_text(encoding="utf-8")
GRADES = (ROOT / "routers" / "grades_dvd_parity.py").read_text(encoding="utf-8")


def test_runtime_instala_uma_politica_compartilhada_para_frequencia_e_notas():
    assert "install_dvd_historical_bridge_generalization" in ROUTERS_INIT
    assert "_attendance_tabs_dvd_mod" in ROUTERS_INIT
    assert "_grades_dvd_parity_mod" in ROUTERS_INIT
    assert "attendance_tabs_mod._safe_cutover_legacy_assignment =" in ADAPTER
    assert "grades_parity_mod._safe_cutover_legacy_assignment =" in ADAPTER
    assert "resolve_validated_cutover_legacy_assignment" in ADAPTER


def test_frequencia_preserva_restricao_class_daily_official():
    assert "AttendanceMode.CLASS_DAILY" in ADAPTER
    assert "AttendancePurpose.OFFICIAL" in ADAPTER
    assert "expected_class_id=assignment.get(\"class_id\")" in ADAPTER
    assert "expected_component_id=assignment.get(\"component_id\")" in ADAPTER


def test_notas_ancoram_revalidacao_no_contexto_ja_autorizado():
    assert "expected_class_id=context.class_id" in ADAPTER
    assert "expected_component_id=context.course_id" in ADAPTER
    assert "expected_class_id != assignment_class_id" in SERVICE
    assert "expected_component_id != assignment_component_id" in SERVICE


def test_instalacao_so_retorna_quando_os_dois_modulos_ja_estao_configurados():
    assert "attendance_installed and grades_installed" in ADAPTER
    assert "_dvd_historical_cutover_generalization_installed = True" in ADAPTER


def test_adaptadores_antigos_ficam_como_fallback_conservador_38g_b():
    assert 'provenance.get("apply_phase") != "38G-B"' in ATTENDANCE
    assert 'provenance.get("apply_phase") != "38G-B"' in GRADES
    assert ROUTERS_INIT.index("install_dvd_historical_bridge_generalization(") < ROUTERS_INIT.index("def setup_grades_router(")
    assert ROUTERS_INIT.index("install_dvd_historical_bridge_generalization(") < ROUTERS_INIT.index("def setup_attendance_router(")


def test_generalizacao_nao_contem_escrita_mongo_nem_retrodatacao():
    combined = ADAPTER + "\n" + SERVICE
    forbidden = (
        ".insert_one(",
        ".insert_many(",
        ".update_one(",
        ".update_many(",
        ".replace_one(",
        ".delete_one(",
        ".delete_many(",
        ".bulk_write(",
        ".find_one_and_update(",
        'assignment["valid_from"] =',
    )
    for token in forbidden:
        assert token not in combined


def test_conteudo_nao_entra_no_escopo_deste_p0():
    assert "content_assignment_scope" not in ADAPTER
    assert "content_entries" not in ADAPTER
    assert "learning_objects" not in ADAPTER
