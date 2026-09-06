from services.diary_canonical_evidence_policy import (
    build_content_day_index,
    expected_slot_counts,
    select_content_for_slot,
    select_strict_attendance,
)


def _entry(*, date="2026-03-12", component="english-final", aula=1, teacher="teacher-a"):
    return {
        "date": date,
        "component_id": component,
        "aula_numero": aula,
        "teacher_id": teacher,
    }


def _attendance(id_, *, date="2026-03-12", course="english-final", aula=1, creator="teacher-a", version=1):
    return {
        "id": id_,
        "date": date,
        "course_id": course,
        "aula_numero": aula,
        "created_by": creator,
        "version": version,
    }


def _content(id_, *, date="2026-03-12", component="english-final", aula=None, teacher="teacher-a", version=1, deleted=False):
    return {
        "id": id_,
        "date": date,
        "component_id": component,
        "aula_numero": aula,
        "teacher_id": teacher,
        "version": version,
        "deleted": deleted,
    }


def test_two_expected_lessons_require_two_distinct_attendance_documents():
    entries = [_entry(aula=1), _entry(aula=2)]
    counts = expected_slot_counts(entries)
    rows = [_attendance("a1", aula=1), _attendance("a2", aula=2)]
    used = set()

    first = select_strict_attendance(
        entries[0], rows,
        expected_slot_count_for_component_day=counts[("2026-03-12", "english-final")],
        used_ids=used,
    )
    assert first["id"] == "a1"
    used.add(first["id"])

    second = select_strict_attendance(
        entries[1], rows,
        expected_slot_count_for_component_day=counts[("2026-03-12", "english-final")],
        used_ids=used,
    )
    assert second["id"] == "a2"


def test_legacy_aggregate_never_fans_out_to_two_strict_slots():
    entries = [_entry(aula=1), _entry(aula=2)]
    aggregate = _attendance("agg", aula=None)
    counts = expected_slot_counts(entries)

    for entry in entries:
        assert select_strict_attendance(
            entry,
            [aggregate],
            expected_slot_count_for_component_day=counts[("2026-03-12", "english-final")],
        ) is None


def test_single_expected_slot_can_preserve_one_legacy_aggregate_without_inventing_aula():
    entry = _entry(aula=3)
    aggregate = _attendance("agg", aula=None)
    picked = select_strict_attendance(
        entry,
        [aggregate],
        expected_slot_count_for_component_day=1,
    )
    assert picked["id"] == "agg"
    assert picked["aula_numero"] is None


def test_attendance_matching_ignores_author_but_requires_component_and_slot():
    entry = _entry(aula=2, teacher="teacher-current")
    rows = [
        _attendance("wrong-component", course="eja-english", aula=2, creator="teacher-current"),
        _attendance("right", course="english-final", aula=2, creator="teacher-historical"),
    ]
    picked = select_strict_attendance(
        entry,
        rows,
        expected_slot_count_for_component_day=2,
    )
    assert picked["id"] == "right"


def test_one_content_entry_can_cover_two_lessons_same_component_day_regardless_of_author():
    content = _content("c1", aula=1, teacher="historical-teacher")
    for aula in (1, 2):
        picked = select_content_for_slot(
            _entry(aula=aula, teacher="current-teacher"),
            [content],
        )
        assert picked["id"] == "c1"


def test_multiple_slot_contents_do_not_cross_fill_an_unmatched_third_slot():
    rows = [_content("c1", aula=1), _content("c2", aula=2)]
    assert select_content_for_slot(_entry(aula=3), rows) is None


def test_day_level_content_without_aula_covers_all_slots_and_latest_version_wins():
    rows = [
        _content("old", aula=None, version=1),
        _content("new", aula=None, version=4, teacher="another-author"),
    ]
    assert select_content_for_slot(_entry(aula=1), rows)["id"] == "new"
    assert select_content_for_slot(_entry(aula=2), rows)["id"] == "new"


def test_deleted_content_is_not_visible_evidence():
    rows = [_content("deleted", deleted=True)]
    assert build_content_day_index(rows) == {}
    assert select_content_for_slot(_entry(), rows) is None


def test_expected_slot_counts_are_partitioned_by_date_and_component():
    entries = [
        _entry(aula=1),
        _entry(aula=2),
        _entry(component="literature", aula=3),
        _entry(date="2026-03-13", aula=1),
    ]
    assert expected_slot_counts(entries) == {
        ("2026-03-12", "english-final"): 2,
        ("2026-03-12", "literature"): 1,
        ("2026-03-13", "english-final"): 1,
    }
