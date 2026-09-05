from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "backend" / "scripts" / "sibling_class_reconstruction_preflight_readonly.py"
MIRROR = ROOT / "backend" / "scripts" / "sibling_class_reconstruction_mirror_policy.py"
GLOBAL = ROOT / "backend" / "scripts" / "sibling_class_reconstruction_global_ordinal_policy.py"
ORPHAN = ROOT / "backend" / "scripts" / "sibling_class_reconstruction_orphan_adjudication.py"
STRUCTURAL = ROOT / "backend" / "scripts" / "sibling_class_reconstruction_orphan_structural_discrimination.py"
SESSION = ROOT / "backend" / "scripts" / "sibling_class_reconstruction_session_ordinal_policy.py"

ns = {"__name__": "r2d_test_module"}
for path in (BASE, MIRROR, GLOBAL, ORPHAN, STRUCTURAL, SESSION):
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), ns)


def _source_item(day, classes=2, fingerprint="fp"):
    return {
        "source_date": day,
        "source_kind": "learning_objects",
        "source_attribution": "OTHER_ACTOR",
        "payload_fingerprint": fingerprint,
        "number_of_classes": classes,
    }


def _session(day, aula=None, period=None, classes=1):
    return {
        "date": day,
        "period": period,
        "aula_numero": aula,
        "number_of_classes": classes,
        "recorded_by": "actor",
        "created_by": "actor",
        "updated_by": "actor",
        "teacher_id": "teacher",
        "staff_id": "staff",
        "assignment_id": "assignment",
    }


def test_expand_source_slots_preserves_capacity_and_order():
    slots, invalid = ns["_expand_source_slots"]([
        _source_item("2026-02-01", 2, "a"),
        _source_item("2026-02-02", 1, "b"),
    ])
    assert invalid == []
    assert [(x["source_record_ordinal"], x["source_slot"]) for x in slots] == [
        (1, 1), (1, 2), (2, 1)
    ]
    assert slots[0]["payload_fingerprint"] == "a"
    assert slots[2]["payload_fingerprint"] == "b"


def test_expand_source_slots_rejects_invalid_capacity():
    slots, invalid = ns["_expand_source_slots"]([
        _source_item("2026-02-01", 0, "a"),
        _source_item("2026-02-02", 11, "b"),
    ])
    # zero chega pelo fallback legado como 1; acima do limite é inválido.
    assert len(slots) == 1
    assert len(invalid) == 1
    assert invalid[0]["source_ordinal"] == 2


def test_target_sessions_accept_two_distinct_aula_numero_same_day():
    indexed = ns["_index_target_sessions"]([
        _session("2026-04-30", aula="1"),
        _session("2026-04-30", aula="2"),
    ])
    assert indexed["collision_days"] == []
    assert indexed["partial_metadata_days"] == []
    assert [x["aula_numero"] for x in indexed["sessions"]] == ["1", "2"]


def test_target_sessions_fail_closed_on_indistinguishable_same_day():
    indexed = ns["_index_target_sessions"]([
        _session("2026-04-30"),
        _session("2026-04-30"),
    ])
    assert indexed["collision_days"] == ["2026-04-30"]


def test_target_sessions_fail_closed_on_partial_metadata_pattern():
    indexed = ns["_index_target_sessions"]([
        _session("2026-04-30", aula="1"),
        _session("2026-04-30", period="tarde"),
    ])
    assert indexed["partial_metadata_days"] == ["2026-04-30"]


def test_session_pair_plan_ready_when_slots_equal_sessions():
    source = {
        "items": [_source_item("2026-04-29", 2, "payload")],
        "blockers": [],
        "monthly_counts": {"2026-04": 1},
    }
    target = ns["_index_target_sessions"]([
        _session("2026-04-30", aula="1"),
        _session("2026-04-30", aula="2"),
    ])
    binding = {
        "2026-04-30": {
            "status": "RESOLVED",
            "assignment_fingerprint": "assignfp",
            "write_mode": "LEGACY_CANONICAL",
            "historical_backfill": False,
        }
    }
    plan = ns["_session_pair_plan"](
        source=source,
        target=target,
        occupied_dates=set(),
        assignment_by_date=binding,
        structural_classification="ORPHAN_TWO_DISTINCT_SESSIONS_SUPPORTED",
    )
    assert plan["status"] == "READY_TO_APPLY"
    assert plan["source_record_total"] == 1
    assert plan["source_slot_total"] == 2
    assert plan["target_session_total"] == 2
    assert plan["paired_session_count"] == 2
    assert plan["blockers"] == []


def test_session_pair_plan_blocks_count_mismatch_without_repetition():
    source = {
        "items": [_source_item("2026-04-29", 2, "payload")],
        "blockers": [],
        "monthly_counts": {"2026-04": 1},
    }
    target = ns["_index_target_sessions"]([
        _session("2026-04-30", aula="1"),
        _session("2026-04-30", aula="2"),
        _session("2026-05-01", aula="1"),
    ])
    binding = {
        "2026-04-30": {
            "status": "RESOLVED",
            "assignment_fingerprint": "a",
            "write_mode": "LEGACY_CANONICAL",
            "historical_backfill": False,
        },
        "2026-05-01": {
            "status": "RESOLVED",
            "assignment_fingerprint": "b",
            "write_mode": "LEGACY_CANONICAL",
            "historical_backfill": False,
        },
    }
    plan = ns["_session_pair_plan"](
        source=source,
        target=target,
        occupied_dates=set(),
        assignment_by_date=binding,
        structural_classification="ORPHAN_TWO_DISTINCT_SESSIONS_SUPPORTED",
    )
    assert plan["status"] == "BLOCKED_REVIEW_REQUIRED"
    assert "SESSION_GLOBAL_COUNT_MISMATCH" in plan["blockers"]
    assert plan["paired_session_count"] == 2
    assert plan["unpaired_target_session_count"] == 1


def test_attendance_number_of_classes_is_diagnostic_not_expansion():
    indexed = ns["_index_target_sessions"]([
        _session("2026-04-30", aula="1", classes=2),
        _session("2026-04-30", aula="2", classes=2),
    ])
    assert len(indexed["sessions"]) == 2
    assert indexed["attendance_number_of_classes_sum_diagnostic"] == 4
