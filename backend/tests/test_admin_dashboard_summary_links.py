from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = REPO_ROOT / "frontend" / "src" / "pages" / "Dashboard.js"


def _dashboard_source() -> str:
    return DASHBOARD_PATH.read_text(encoding="utf-8")


def _global_admin_cards_block(source: str) -> str:
    start = source.index("case 'super_admin':")
    end = source.index("case 'secretario':", start)
    return source[start:end]


def _secretary_cards_block(source: str) -> str:
    start = source.index("case 'secretario':")
    end = source.index("case 'diretor':", start)
    return source[start:end]


def _general_quick_access_block(source: str) -> str:
    start = source.index(
        "{/* Acesso Rápido geral — para secretário esta é a única faixa-resumo operacional. */}"
    )
    end = source.index(
        "{/* Menu de navegação completo - Admin/Secretário/Diretor/Coordenador/SEMED",
        start,
    )
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


def test_secretary_removes_old_top_statistics_row():
    source = _dashboard_source()
    block = _secretary_cards_block(source)

    assert "return [];" in block
    assert "title: 'Escolas'" not in block
    assert "title: 'Turmas'" not in block
    assert "title: 'Estudantes'" not in block
    assert "title: 'Avisos'" not in block
    assert "{cards.length > 0 && (" in source


def test_secretary_promoted_quick_access_has_exact_requested_resources():
    source = _dashboard_source()
    block = _general_quick_access_block(source)

    expected_testids = [
        "quick-access-schools",
        "quick-access-classes",
        "quick-access-students",
        "quick-access-staff",
        "quick-access-users",
    ]
    for testid in expected_testids:
        assert f'data-testid="{testid}"' in block

    assert "Avisos" not in block


def test_secretary_promoted_cards_show_existing_school_class_student_counts_only():
    source = _dashboard_source()
    block = _general_quick_access_block(source)

    expected_counts = {
        "quick-access-schools-count": "stats.schools.toString()",
        "quick-access-classes-count": "stats.classes.toString()",
        "quick-access-students-count": "stats.students.toString()",
    }
    for testid, expression in expected_counts.items():
        assert f'data-testid="{testid}"' in block
        assert expression in block

    # Conforme decisão de produto, Servidores(as) permanece como estava e
    # Usuários é filtrado no backend, sem introduzir uma nova métrica visual.
    assert 'data-testid="quick-access-staff-count"' not in block
    assert 'data-testid="quick-access-users-count"' not in block
