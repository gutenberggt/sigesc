from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PROFESSOR_DASHBOARD = REPO_ROOT / "frontend/src/pages/ProfessorDashboard.js"
MY_DIARIES = REPO_ROOT / "frontend/src/components/professor/MyDiariesSection.jsx"
ATTENDANCE_BRIDGE = REPO_ROOT / "frontend/src/services/attendanceDvdBridge.js"


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
