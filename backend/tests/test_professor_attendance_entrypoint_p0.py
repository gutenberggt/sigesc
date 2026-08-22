from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[2]
PROFESSOR_DASHBOARD = REPO_ROOT / "frontend/src/pages/ProfessorDashboard.js"
MY_DIARIES = REPO_ROOT / "frontend/src/components/professor/MyDiariesSection.jsx"
ATTENDANCE_BRIDGE = REPO_ROOT / "frontend/src/services/attendanceDvdBridge.js"
ATTENDANCE_LAUNCH = REPO_ROOT / "frontend/src/components/attendance/LancamentoTab.jsx"
ATTENDANCE_RECORDS = REPO_ROOT / "frontend/src/components/attendance/RegistrosTab.jsx"
BROWSER_LOCAL_DATE = REPO_ROOT / "frontend/src/utils/browserLocalDate.js"
CLIENT_TIME_CONTEXT = REPO_ROOT / "frontend/src/utils/clientTimeContext.js"
FRONTEND_INDEX = REPO_ROOT / "frontend/src/index.js"
BACKEND_SERVER = REPO_ROOT / "backend/server.py"
AUDIT_SERVICE = REPO_ROOT / "backend/audit_service.py"
AUDIT_LOGS_ROUTER = REPO_ROOT / "backend/routers/audit_logs.py"
RENDER_WORKER = REPO_ROOT / "backend/services/render_worker.py"
BULLETIN_ROUTER = REPO_ROOT / "backend/routers/bulletin_pdf.py"
HISTORY_ROUTER = REPO_ROOT / "backend/routers/history_pdf.py"
DIARY_SNAPSHOTS_ROUTER = REPO_ROOT / "backend/routers/diary_snapshots.py"
RENDER_JOBS_ROUTER = REPO_ROOT / "backend/routers/render_jobs.py"
BULLETIN_RENDERER = REPO_ROOT / "backend/services/bulletin_renderer.py"
HISTORY_RENDERER = REPO_ROOT / "backend/services/history_renderer.py"
PDF_DIR = REPO_ROOT / "backend/pdf"
HR_PDF_GENERATOR = REPO_ROOT / "backend/hr_pdf_generator.py"


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


def test_global_browser_time_context_is_installed_and_backend_accepts_it():
    index = _read(FRONTEND_INDEX)
    helper = _read(CLIENT_TIME_CONTEXT)
    server = _read(BACKEND_SERVER)

    assert 'import { installClientTimeContext } from "@/utils/clientTimeContext";' in index
    assert "installClientTimeContext();" in index
    assert "Intl.DateTimeFormat().resolvedOptions().timeZone" in helper
    assert "String(-date.getTimezoneOffset())" in helper
    assert "axios.interceptors.request.use" in helper
    assert "window.fetch =" in helper

    assert "from utils.client_time import ClientTimeContextMiddleware" in server
    assert "app.add_middleware(ClientTimeContextMiddleware)" in server
    for header in (
        "X-SIGESC-Timezone",
        "X-SIGESC-UTC-Offset-Minutes",
        "X-SIGESC-Local-Date",
    ):
        assert header in helper
        assert header in server


def test_audit_keeps_utc_canonical_and_local_snapshot():
    source = _read(AUDIT_SERVICE)
    pdf_source = _read(AUDIT_LOGS_ROUTER)

    assert "now_utc = datetime.now(timezone.utc)" in source
    assert "'timestamp': now_utc.isoformat()" in source
    assert "'timestamp_utc': time_ctx['timestamp_utc']" in source
    assert "'timestamp_local': time_ctx['timestamp_local']" in source
    assert "'timezone': time_ctx['timezone']" in source
    assert "'utc_offset_minutes': time_ctx['utc_offset_minutes']" in source
    assert "local_day_bounds_utc(" in source
    assert "filters['end_date'] + 'T23:59:59'" not in source

    # PDF de auditoria prefere o snapshot civil imutável do evento.
    assert "lg.get('timestamp_local') or lg.get('timestamp')" in pdf_source
    assert "local_now()" in pdf_source


def test_async_document_render_preserves_originating_time_context():
    for path in (
        BULLETIN_ROUTER,
        HISTORY_ROUTER,
        DIARY_SNAPSHOTS_ROUTER,
        RENDER_JOBS_ROUTER,
    ):
        source = _read(path)
        if "document_render_jobs.insert_one" in source:
            assert "current_time_context" in source
            assert '"time_context": current_time_context()' in source

    worker = _read(RENDER_WORKER)
    assert "from utils.client_time import use_time_context" in worker
    assert 'job.get("time_context")' in worker
    assert "with use_time_context(" in worker

    for path in (BULLETIN_RENDERER, HISTORY_RENDERER):
        source = _read(path)
        assert "created_at_local" in source
        assert "timezone" in source
        assert "utc_offset_minutes" in source


def test_document_generators_do_not_use_naive_container_clock_for_civil_time():
    patterns = (
        re.compile(r"(?<![\w.])datetime\.now\(\)"),
        re.compile(r"(?<![\w.])date\.today\(\)"),
    )
    paths = list(PDF_DIR.glob("*.py")) + [HR_PDF_GENERATOR]
    violations = []
    for path in paths:
        source = _read(path)
        for pattern in patterns:
            if pattern.search(source):
                violations.append(str(path.relative_to(REPO_ROOT)))
    assert not violations, f"relógio civil ingênuo do container em: {violations}"


def test_frontend_civil_date_is_never_derived_from_utc_iso_day():
    pattern = re.compile(
        r"toISOString\(\)\s*\.\s*(?:split\(\s*['\"]T['\"]\s*\)\s*\[\s*0\s*\]"
        r"|slice\(\s*0\s*,\s*10\s*\)|substring\(\s*0\s*,\s*10\s*\))"
    )
    violations = []
    for path in (REPO_ROOT / "frontend/src").rglob("*"):
        if path.suffix not in {".js", ".jsx", ".ts", ".tsx"}:
            continue
        source = _read(path)
        if pattern.search(source):
            violations.append(str(path.relative_to(REPO_ROOT)))
    assert not violations, f"data civil derivada de ISO UTC em: {violations}"
