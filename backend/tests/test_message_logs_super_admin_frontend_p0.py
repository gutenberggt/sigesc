from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MESSAGE_LOGS = ROOT / "frontend/src/pages/MessageLogs.js"
DASHBOARD = ROOT / "frontend/src/pages/Dashboard.js"
BACKEND = ROOT / "backend/routers/admin_messages.py"


def test_message_logs_page_accepts_super_admin_instead_of_legacy_admin_guard():
    source = MESSAGE_LOGS.read_text(encoding="utf-8")

    assert "user.role !== 'super_admin'" in source
    assert "user.role !== 'admin'" not in source


def test_dashboard_keeps_log_menu_exclusive_to_super_admin():
    source = DASHBOARD.read_text(encoding="utf-8")

    expected = (
        "{ label: 'Log de Conversas', icon: MessageSquare, color: 'red', "
        "route: '/admin/logs', testId: 'nav-logs-button', visible: c => c.isSuperAdmin }"
    )
    assert expected in source


def test_backend_message_logs_remains_super_admin_only():
    source = BACKEND.read_text(encoding="utf-8")

    assert "nav-logs-button', ['super_admin']" in source
