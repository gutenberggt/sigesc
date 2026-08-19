from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_PARITY = REPO_ROOT / "backend/routers/attendance_tabs_dvd.py"
BACKEND_EXT = REPO_ROOT / "backend/routers/attendance_ext_dvd.py"
ROUTERS_INIT = REPO_ROOT / "backend/routers/__init__.py"
BRIDGE = REPO_ROOT / "frontend/src/services/attendanceDvdBridge.js"
INFO_TAB = REPO_ROOT / "frontend/src/components/attendance/InformacoesTab.jsx"
ALERTS_TAB = REPO_ROOT / "frontend/src/components/attendance/AlertasTab.jsx"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_cutover_history_is_read_only_and_not_reassigned():
    source = _read(BACKEND_PARITY)

    assert '"assignment_id": None' in source
    assert 'item["read_only"] = True' in source
    assert 'item["history_source"] = "attendance_legacy"' in source
    assert 'provenance.get("apply_phase") != "38G-B"' in source
    assert 'provenance.get("apply_state") != "ACTIVATED"' in source
    assert 'source_legacy_assignment_id' in source

    # A ponte histórica é de leitura; nunca promove legado para assignment_id.
    assert 'update_many(' not in source
    assert 'insert_many(' not in source
    assert '"$set": {"assignment_id"' not in source


def test_regular_same_teacher_reuses_owner_without_transferring_ownership():
    source = _read(BACKEND_PARITY)

    assert 'CLASS_DAILY_ALREADY_OWNED' in source
    assert 'existing.get("teacher_id")' in source
    assert 'context.assignment.get("teacher_id")' in source
    assert 'raw["assignment_id"] = owner_assignment_id' in source
    assert '"diary_settings.profile": "regular"' in source


def test_student_information_is_assignment_scoped_and_roster_authorized():
    source = _read(BACKEND_PARITY)

    assert '/attendance/class-students-info/{class_id}' in source
    assert 'assignment_id: Optional[str] = None' in source
    assert 'resolve_attendance_assignment(' in source
    assert 'build_attendance_roster(' in source
    assert 'DVD_ASSIGNMENT_REQUIRED' in source
    assert 'Você não tem acesso a esta turma' in source


def test_alerts_are_assignment_aware_and_reuse_canonical_dvd_report():
    source = _read(BACKEND_EXT)

    assert '/attendance/alerts' in source
    assert 'assignment_id: Optional[str] = None' in source
    assert 'from routers.attendance_dvd import _dvd_report' in source
    assert 'report.get("documentary_only")' in source
    assert 'percentage >= 75' in source


def test_frontend_bridge_carries_assignment_to_all_attendance_tabs():
    source = _read(BRIDGE)

    for path in (
        '/attendance/by-class/',
        '/attendance/report/class/',
        '/attendance/attendance-summary/',
        '/attendance/dates-with-records',
        '/attendance/bimestre-summary',
        '/attendance/class-students-info/',
        '/attendance/alerts',
    ):
        assert path in source
    assert "appendQuery(url, 'assignment_id', assignmentId)" in source


def test_information_tab_locks_school_and_class_in_dvd_mode():
    source = _read(INFO_TAB)

    assert 'attendanceAPI.getClassStudentsInfo(dvdDiary.class_id, academicYear)' in source
    assert 'Informações restritas ao seu vínculo docente' in source
    assert 'value={dvdDiary?.school_id || \'\'} disabled' in source
    assert 'value={dvdDiary?.class_id || \'\'} disabled' in source


def test_regular_dvd_alerts_are_enabled_but_documentary_remains_non_official():
    source = _read(ALERTS_TAB)

    assert 'Alertas do seu Diário por Vínculo' in source
    assert 'Registro documental não gera alertas de frequência' in source
    assert 'disabled={dvdMode}' in source
    assert 'fica indisponível neste contexto' not in source


def test_parity_adapter_is_installed_after_phase4_adapter():
    source = _read(ROUTERS_INIT)

    phase4 = source.index('configured = install_attendance_dvd_adapter')
    parity = source.index('return install_attendance_tabs_dvd_adapter')
    assert phase4 < parity
    assert '_attendance_tabs_dvd_mod.dvd_mod = _attendance_dvd_mod' in source
