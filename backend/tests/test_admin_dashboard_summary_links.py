from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = REPO_ROOT / "frontend" / "src" / "pages" / "Dashboard.js"


def _dashboard_source() -> str:
    return DASHBOARD_PATH.read_text(encoding="utf-8")


def _global_admin_cards_block(source: str) -> str:
    start = source.index("case 'super_admin':")
    end = source.index("case 'secretario':", start)
    return source[start:end]


def test_global_admin_summary_cards_are_clickable_and_keep_their_counts():
    source = _dashboard_source()
    block = _global_admin_cards_block(source)

    expected_routes = {
        "Escolas": "/admin/schools",
        "Turmas": "/admin/classes",
        "Estudantes": "/admin/students",
        "Servidores(as)": "/admin/staff",
        "Usuários": "/admin/users",
    }

    for title, route in expected_routes.items():
        assert f"title: '{title}'" in block
        assert f"route: '{route}'" in block

    assert "stats.schools.toString()" in block
    assert "stats.classes.toString()" in block
    assert "stats.students.toString()" in block
    assert "stats.staff.toString()" in block
    assert "stats.users.toString()" in block


def test_global_admin_does_not_render_duplicate_quick_access_row():
    source = _dashboard_source()

    assert (
        "!isDirectorCoordinatorDashboard && !isAdmin && "
        "(isAdminOrSecretary || isSchoolStaff || isSemed)"
    ) in source


def test_summary_card_navigation_keeps_keyboard_accessibility():
    source = _dashboard_source()

    assert "const isClickable = Boolean(card.route);" in source
    assert "if (event.key === 'Enter' || event.key === ' ')" in source
    assert "role={isClickable ? 'button' : undefined}" in source
    assert "tabIndex={isClickable ? 0 : undefined}" in source
    assert "aria-label={isClickable ? `Abrir ${card.title}` : undefined}" in source
