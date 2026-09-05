from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "backend" / "scripts" / "sibling_class_reconstruction_preflight_readonly.py"
POLICY = ROOT / "backend" / "scripts" / "sibling_class_reconstruction_mirror_policy.py"

ns = {"__name__": "r2_test_module"}
exec(compile(BASE.read_text(encoding="utf-8"), str(BASE), "exec"), ns)
exec(compile(POLICY.read_text(encoding="utf-8"), str(POLICY), "exec"), ns)


def _content(day, *, actor=None, kind="canonical"):
    row = {
        "date": day,
        "content": f"conteudo-{day}",
        "methodology": "m",
        "observations": None,
        "number_of_classes": 1,
    }
    if actor:
        row["teacher_id"] = actor
    return row


def test_mirror_source_does_not_require_target_teacher_authorship():
    result = ns["_source_items_by_month"](
        [_content("2026-02-01", actor="other"), _content("2026-02-08", actor="other")],
        [],
        actor_ids={"target"},
        assignment_ids=set(),
        months=["2026-02"],
    )["2026-02"]
    assert len(result["items"]) == 2
    assert result["foreign_row_count"] == 2
    assert result["canonical_row_count"] == 2
    assert result["legacy_row_count"] == 0
    assert result["blockers"] == []
    assert {item["source_attribution"] for item in result["items"]} == {"OTHER_ACTOR"}


def test_unattributed_legacy_source_is_allowed_as_institutional_mirror():
    result = ns["_source_items_by_month"](
        [],
        [_content("2026-02-01"), _content("2026-02-08")],
        actor_ids={"target"},
        assignment_ids=set(),
        months=["2026-02"],
    )["2026-02"]
    assert len(result["items"]) == 2
    assert result["unattributed_legacy_row_count"] == 2
    assert result["legacy_row_count"] == 2
    assert result["blockers"] == []


def test_multiple_source_rows_same_date_still_fail_closed():
    result = ns["_source_items_by_month"](
        [_content("2026-02-01", actor="a")],
        [_content("2026-02-01", actor="b")],
        actor_ids={"target"},
        assignment_ids=set(),
        months=["2026-02"],
    )["2026-02"]
    assert result["items"] == []
    assert "SOURCE_MULTIPLE_ROWS_SAME_DATE" in result["blockers"]


def test_unique_legacy_binding_resolves_when_no_dvd():
    ns["_R2_LEGACY_ASSIGNMENTS"] = [
        {"id": "legacy-1", "class_id": "class-a", "course_id": "math", "status": "ativo"}
    ]
    result = ns["_assignment_for_date"](
        [],
        class_id="class-a",
        component_id="math",
        teacher_id="teacher",
        target_date="2026-02-10",
    )
    assert result["status"] == "RESOLVED"
    assert result["write_mode"] == "LEGACY_CANONICAL"
    assert result["assignment_fingerprint"]


def test_ambiguous_legacy_binding_fails_closed():
    ns["_R2_LEGACY_ASSIGNMENTS"] = [
        {"id": "legacy-1", "class_id": "class-a", "course_id": "math", "status": "ativo"},
        {"id": "legacy-2", "class_id": "class-a", "course_id": "math", "status": "active"},
    ]
    result = ns["_assignment_for_date"](
        [],
        class_id="class-a",
        component_id="math",
        teacher_id="teacher",
        target_date="2026-02-10",
    )
    assert result["status"] == "AMBIGUOUS_LEGACY_BINDING"
    assert result["write_mode"] is None


def test_month_plan_exposes_write_mode_and_blocks_only_real_mismatch():
    source = {
        "items": [
            {"source_date": "2026-02-01", "source_kind": "content_entries", "source_attribution": "OTHER_ACTOR", "payload_fingerprint": "p1", "number_of_classes": 1},
            {"source_date": "2026-02-08", "source_kind": "content_entries", "source_attribution": "OTHER_ACTOR", "payload_fingerprint": "p2", "number_of_classes": 1},
        ],
        "blockers": [],
        "canonical_row_count": 2,
        "legacy_row_count": 0,
        "foreign_row_count": 2,
        "unattributed_legacy_row_count": 0,
        "target_teacher_row_count": 0,
    }
    attendance = {
        "dates": ["2026-02-03", "2026-02-10"],
        "document_count": 2,
        "actor_conflict_dates": [],
    }
    bindings = {
        "2026-02-03": {"status": "RESOLVED", "assignment_fingerprint": "b1", "historical_backfill": False, "write_mode": "LEGACY_CANONICAL"},
        "2026-02-10": {"status": "RESOLVED", "assignment_fingerprint": "b1", "historical_backfill": False, "write_mode": "LEGACY_CANONICAL"},
    }
    plan = ns["_build_month_plan"](
        month="2026-02",
        source=source,
        target_attendance=attendance,
        occupied_dates=set(),
        assignment_by_date=bindings,
    )
    assert plan["status"] == "READY_TO_APPLY"
    assert plan["target_unresolved_binding_date_count"] == 0
    assert plan["target_write_mode_counts"] == {"LEGACY_CANONICAL": 2}
    assert all(item["target_write_mode"] == "LEGACY_CANONICAL" for item in plan["items"])


def test_policy_contains_no_mongo_write_primitives_or_case_names():
    source = POLICY.read_text(encoding="utf-8")
    for forbidden in (
        "insert_one(", "update_one(", "delete_one(", "bulk_write(",
        "Luiz Gomes", "Jose Pereira Barbosa", "8º ANO", "9º ANO",
    ):
        assert forbidden not in source
