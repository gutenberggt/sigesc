from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]


def _section(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def _production_python_files():
    for path in BACKEND_DIR.rglob("*.py"):
        if "tests" in path.parts:
            continue
        yield path


def test_course_consolidation_is_read_only_during_p0():
    source = (BACKEND_DIR / "routers" / "maintenance.py").read_text(encoding="utf-8")
    section = _section(
        source,
        '@router.post("/maintenance/consolidate-courses")',
        '@router.post("/maintenance/cleanup-cancelled-enrollments")',
    )
    assert "COURSE_CONSOLIDATION_DISABLED_P0" in section
    assert "db.courses.delete_one" not in section
    assert "db.courses.update_one" not in section


def test_teacher_assignment_hard_delete_is_disabled_during_p0():
    source = (BACKEND_DIR / "routers" / "assignments.py").read_text(encoding="utf-8")
    section = source.split('@router.delete("/teacher-assignments/{assignment_id}")', 1)[1]
    assert "TEACHER_ASSIGNMENT_HARD_DELETE_DISABLED_P0" in section
    assert "db.teacher_assignments.delete_one" not in section


def test_course_delete_requires_global_reference_check():
    source = (BACKEND_DIR / "routers" / "courses.py").read_text(encoding="utf-8")
    section = source.split('@router.delete("/{course_id}"', 1)[1]
    assert "get_course_reference_counts" in section
    assert "blocking_course_references" in section
    assert "COURSE_IN_USE_P0" in section


def test_no_other_production_path_hard_deletes_teacher_assignments():
    offenders = []
    for path in _production_python_files():
        source = path.read_text(encoding="utf-8")
        if "db.teacher_assignments.delete_one" in source:
            offenders.append(str(path.relative_to(BACKEND_DIR)))
    assert offenders == []


def test_course_hard_delete_exists_only_in_guarded_course_router():
    offenders = []
    for path in _production_python_files():
        source = path.read_text(encoding="utf-8")
        if "db.courses.delete_one" in source and path != BACKEND_DIR / "routers" / "courses.py":
            offenders.append(str(path.relative_to(BACKEND_DIR)))
    assert offenders == []
