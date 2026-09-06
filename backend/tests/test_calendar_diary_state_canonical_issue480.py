from routers.calendar_diary_state_canonical import (
    merge_content_sources,
    reconcile_strict_payload,
)


def _entry(aula, component="english-final", teacher="current-teacher"):
    return {
        "component_id": component,
        "component_name": "Língua Inglesa",
        "aula_numero": aula,
        "teacher_id": teacher,
        "attendance_status": "missing",
        "content_status": "missing",
    }


def _payload(entries):
    return {
        "class_id": "class-1",
        "matching_mode": "strict",
        "days": [{
            "date": "2026-03-12",
            "status": "partial",
            "entries": entries,
            "expected_slots": len(entries),
            "has_orphan_evidence": False,
        }],
        "summary": {},
    }


def _attendance(id_, aula, *, component="english-final", teacher="historical", classes=1):
    return {
        "id": id_,
        "date": "2026-03-12",
        "course_id": component,
        "aula_numero": aula,
        "number_of_classes": classes,
        "created_by": teacher,
        "records": [{"student_id": "s1", "status": "P"}],
    }


def _content(id_, *, component="english-final", aula=None, teacher="historical"):
    return {
        "id": id_,
        "date": "2026-03-12",
        "component_id": component,
        "aula_numero": aula,
        "teacher_id": teacher,
        "status": "published",
        "version": 1,
        "deleted": False,
    }


def test_two_lessons_require_two_component_sessions_and_one_content_can_cover_both():
    payload = _payload([_entry(1), _entry(2)])
    result = reconcile_strict_payload(
        payload,
        [_attendance("a1", 1), _attendance("a2", 2)],
        [_content("c1", aula=1)],
    )
    entries = result["days"][0]["entries"]
    assert [entry["attendance_status"] for entry in entries] == ["completed", "completed"]
    assert [entry["content_status"] for entry in entries] == ["published", "published"]
    assert result["days"][0]["status"] == "complete"
    assert result["summary"]["attendance_completed"] == 2
    assert result["summary"]["content_published"] == 2


def test_wrong_component_same_slot_does_not_prove_frequency():
    result = reconcile_strict_payload(
        _payload([_entry(1)]),
        [_attendance("wrong", 1, component="literature")],
        [],
    )
    entry = result["days"][0]["entries"][0]
    assert entry["attendance_status"] == "missing"
    assert result["days"][0]["status"] == "inconsistent"


def test_historical_author_does_not_hide_content_or_frequency():
    result = reconcile_strict_payload(
        _payload([_entry(1, teacher="current")]),
        [_attendance("a1", 1, teacher="old-author")],
        [_content("c1", teacher="another-author")],
    )
    entry = result["days"][0]["entries"][0]
    assert entry["attendance_status"] == "completed"
    assert entry["content_status"] == "published"


def test_shadowed_aggregate_does_not_turn_complete_day_inconsistent():
    payload = _payload([_entry(1), _entry(2)])
    result = reconcile_strict_payload(
        payload,
        [
            _attendance("agg", None, classes=2),
            _attendance("a1", 1),
            _attendance("a2", 2),
        ],
        [_content("c1")],
    )
    assert result["days"][0]["status"] == "complete"
    assert result["summary"]["orphan_attendance_dates"] == []


def test_isolated_aggregate_on_two_slot_day_does_not_fan_out():
    result = reconcile_strict_payload(
        _payload([_entry(1), _entry(2)]),
        [_attendance("agg", None, classes=2)],
        [_content("c1")],
    )
    entries = result["days"][0]["entries"]
    assert [entry["attendance_status"] for entry in entries] == ["missing", "missing"]
    assert result["days"][0]["status"] == "inconsistent"


def test_canonical_content_wins_only_same_date_component_and_legacy_other_component_remains():
    canonical = [_content("canonical", component="english-final")]
    legacy_same = _content("legacy-same", component="english-final")
    legacy_other = _content("legacy-other", component="literature")
    merged = merge_content_sources(canonical, [legacy_same, legacy_other])
    assert {item["id"] for item in merged} == {"canonical", "legacy-other"}


def test_flexible_stage_is_not_modified_by_issue_480_reconciler():
    payload = _payload([_entry(1)])
    payload["matching_mode"] = "flexible"
    original = payload.copy()
    assert reconcile_strict_payload(payload, [], []) is payload
    assert payload == original
