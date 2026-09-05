import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "luiz_gomes_f6_1_component_adjudication_readonly.py"
spec = importlib.util.spec_from_file_location("luiz_gomes_f6_1", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def _base(candidate_rows, *, legacy=None, dvd=None, attendance=None):
    return mod.adjudicate_class(
        class_name="8º ANO A",
        class_id="class-8a",
        current_math_course_id="math-current",
        learning_rows=candidate_rows,
        math_attendance_rows=attendance or [],
        legacy_history=legacy or [],
        dvd_history=dvd or [],
        course_by_id={
            "math-current": {"id": "math-current", "name": "Matemática"},
            "other-a": {"id": "other-a", "name": "Componente A"},
            "other-b": {"id": "other-b", "name": "Componente B"},
        },
    )


def test_projections_exclude_forbidden_fields():
    assert not mod.FORBIDDEN_FIELDS.intersection(mod.LEARNING_PROJECTION)
    assert not mod.FORBIDDEN_FIELDS.intersection(mod.ATTENDANCE_PROJECTION)


def test_unique_legacy_assignment_candidate_is_classified():
    rows = [
        {"class_id": "class-8a", "course_id": "other-a", "date": "2026-02-10"},
        {"class_id": "class-8a", "course_id": "other-b", "date": "2026-02-11"},
    ]
    legacy = [
        {"id": "legacy-1", "class_id": "class-8a", "course_id": "other-a", "status": "inativo"}
    ]
    result = _base(rows, legacy=legacy)
    assert "UNIQUE_OTHER_COMPONENT_WITH_LUIZ_ASSIGNMENT_HISTORY" in result["classification"]
    assert "LEGACY_TEACHER_ASSIGNMENT_TO_OTHER_COMPONENT_CONFIRMED" in result["classification"]


def test_dvd_candidate_is_classified():
    rows = [{"class_id": "class-8a", "course_id": "other-a", "date": "2026-03-10"}]
    dvd = [
        {
            "id": "dvd-1",
            "class_id": "class-8a",
            "component_id": "other-a",
            "valid_from": "2026-02-01",
            "valid_until": "2026-04-30",
        }
    ]
    result = _base(rows, dvd=dvd)
    assert "DVD_ASSIGNMENT_TO_OTHER_COMPONENT_CONFIRMED" in result["classification"]


def test_date_overlap_candidate_is_ranked_without_claiming_authorship():
    rows = [
        {"class_id": "class-8a", "course_id": "other-a", "date": "2026-02-10"},
        {"class_id": "class-8a", "course_id": "other-a", "date": "2026-02-17"},
        {"class_id": "class-8a", "course_id": "other-b", "date": "2026-02-12"},
    ]
    attendance = [
        {"class_id": "class-8a", "course_id": "math-current", "date": "2026-02-10"},
        {"class_id": "class-8a", "course_id": "math-current", "date": "2026-02-17"},
    ]
    result = _base(rows, attendance=attendance)
    assert "UNIQUE_MAX_DATE_OVERLAP_CANDIDATE" in result["classification"]
    assert "NO_DIRECT_LUIZ_ASSIGNMENT_HISTORY_ON_CANDIDATES" in result["classification"]
    assert result["candidates"][0]["catalog_name"] == "Componente A"
    assert result["candidates"][0]["date_overlap_with_math_attendance"] == 2


def test_month_counts_are_preserved_per_candidate():
    rows = [
        {"class_id": "class-8a", "course_id": "other-a", "date": "2026-02-10"},
        {"class_id": "class-8a", "course_id": "other-a", "date": "2026-03-10"},
        {"class_id": "class-8a", "course_id": "other-a", "date": "2026-04-10"},
    ]
    result = _base(rows)
    assert result["candidates"][0]["content"]["months"] == {"02": 1, "03": 1, "04": 1}


def test_current_math_rows_are_not_candidates():
    rows = [{"class_id": "class-8a", "course_id": "math-current", "date": "2026-02-10"}]
    result = _base(rows)
    assert result["candidate_count"] == 0
    assert result["classification"] == ["NO_OTHER_COMPONENT_CONTENT_IN_PERIOD"]


def test_fingerprint_does_not_expose_raw_id():
    raw = "internal-course-id"
    assert mod._fp(raw) != raw
    assert len(mod._fp(raw)) == 12
