from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PROFESSOR_DASHBOARD = REPO_ROOT / "frontend/src/pages/ProfessorDashboard.js"
MY_DIARIES = REPO_ROOT / "frontend/src/components/professor/MyDiariesSection.jsx"
ATTENDANCE_BRIDGE = REPO_ROOT / "frontend/src/services/attendanceDvdBridge.js"
ATTENDANCE_LAUNCH = REPO_ROOT / "frontend/src/components/attendance/LancamentoTab.jsx"
ATTENDANCE_RECORDS = REPO_ROOT / "frontend/src/components/attendance/RegistrosTab.jsx"
BROWSER_LOCAL_DATE = REPO_ROOT / "frontend/src/utils/browserLocalDate.js"
LEARNING_OBJECTS = REPO_ROOT / "frontend/src/pages/LearningObjects.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_quick_access_frequency_does_not_open_naked_legacy_route():
    source = _read(PROFESSOR_DASHBOARD)

    assert "const openFromMyDiaries = () =>" in source
    assert "document.querySelector('[data-testid=\"meus-diarios-section\"]')" in source
    assert 'data-testid="menu-frequencia"' in source
    assert "onClick={openFromMyDiaries}" in source
    assert "onClick={() => navigate('/professor/frequencia')}" not in source


def test_diary_frequency_action_carries_assignment_id():
    source = _read(MY_DIARIES)

    assert "assignmentId: diary.assignment_id" in source
    assert "buildDiaryActionUrl('/professor/frequencia', actionContext)" in source


def test_attendance_bridge_rewrites_reads_when_assignment_id_is_present():
    source = _read(ATTENDANCE_BRIDGE)

    assert "params.get('assignment_id')" in source
    assert "'/attendance/by-class/'" in source
    assert "appendQuery(url, 'assignment_id', assignmentId)" in source


def test_attendance_today_is_browser_local_and_not_utc_calendar_day():
    helper = _read(BROWSER_LOCAL_DATE)
    launch = _read(ATTENDANCE_LAUNCH)
    records = _read(ATTENDANCE_RECORDS)

    # Contrato permanente: data civil vem do relógio/fuso do dispositivo.
    assert "date.getFullYear()" in helper
    assert "date.getMonth() + 1" in helper
    assert "date.getDate()" in helper
    assert "browserLocalTodayISO" in helper

    # A aba de lançamento corrige o default UTC legado antes da pintura e o
    # botão Hoje sempre recalcula pelo fuso do navegador/computador.
    assert "normalizeLegacyUtcTodayDefault(selectedDate)" in launch
    assert "setSelectedDate(browserLocalTodayISO())" in launch
    assert "new Date().toISOString().split('T')[0]" not in launch

    # O calendário anual destaca Hoje pela mesma regra civil local.
    assert "const todayISO = browserLocalTodayISO();" in records
    assert "const isToday = dateStr === todayISO;" in records
    assert "new Date().toISOString().split('T')[0]" not in records



def test_learning_objects_today_and_calendar_dates_use_browser_local_day():
    source = _read(LEARNING_OBJECTS)

    assert "browserLocalDateISO" in source
    assert "browserLocalTodayISO" in source
    assert "const isToday = dateStr === browserLocalTodayISO();" in source
    assert "sabLetivos.add(browserLocalDateISO(d));" in source
    assert "blocked.add(browserLocalDateISO(d));" in source
    assert "new Date().toISOString().split('T')[0]" not in source
