from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHOOLS_ROUTER = REPO_ROOT / "backend" / "routers" / "schools.py"
DIARIO_AEE = REPO_ROOT / "frontend" / "src" / "pages" / "DiarioAEE.js"


def test_professor_without_school_ids_uses_active_teacher_assignments_for_school_scope():
    source = SCHOOLS_ROUTER.read_text(encoding="utf-8")

    assert "effective_school_ids = sorted(current_user.get('school_ids') or [])" in source
    assert "current_user['role'] == 'professor' and not effective_school_ids" in source
    assert '"staff_id": staff[\'id\']' in source
    assert '"status": "ativo"' in source
    assert '"academic_year": datetime.now().year' in source
    assert 'current_db.teacher_assignments.find(' in source
    assert 'current_db.classes.find(' in source
    assert "effective_school_ids = sorted({" in source


def test_resolved_school_scope_is_used_in_cache_and_query():
    source = SCHOOLS_ROUTER.read_text(encoding="utf-8")

    assert "'school_ids': effective_school_ids" in source
    assert 'base_filter = {"id": {"$in": effective_school_ids}}' in source


def test_diario_aee_keeps_existing_aee_filter_and_consumes_schools_endpoint():
    source = DIARIO_AEE.read_text(encoding="utf-8")

    assert '`${API_URL}/api/schools`' in source
    assert 'allSchools.filter(s => s.aee)' in source
