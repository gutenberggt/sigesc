from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "backend" / "scripts" / "sibling_class_reconstruction_preflight_readonly.py"
MIRROR = ROOT / "backend" / "scripts" / "sibling_class_reconstruction_mirror_policy.py"
GLOBAL = ROOT / "backend" / "scripts" / "sibling_class_reconstruction_global_ordinal_policy.py"

ns = {"__name__": "r2_global_test_module"}
for path in (BASE, MIRROR, GLOBAL):
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), ns)


def _src(day: str, fp: str, *, classes: int = 1):
    return {
        "source_date": day,
        "source_kind": "learning_objects",
        "source_attribution": "OTHER_ACTOR",
        "payload_fingerprint": fp,
        "number_of_classes": classes,
    }


def _binding():
    return {
        "status": "RESOLVED",
        "assignment_fingerprint": "binding-fp",
        "historical_backfill": False,
        "write_mode": "LEGACY_CANONICAL",
    }


def _source(items):
    return {
        "items": items,
        "blockers": [],
        "monthly_counts": {},
        "canonical_total": 0,
        "legacy_total": len(items),
        "attribution_counts": {"OTHER_ACTOR": len(items)},
    }


def _target(dates):
    return {
        "dates": dates,
        "conflict_dates": [],
        "monthly_counts": {},
        "document_count": len(dates),
        "foreign_document_count": 0,
    }


def test_global_strategy_reuses_case_contract():
    case = {
        "schema": "SIBLING_CLASS_RECONSTRUCTION_CASE_V1",
        "case_id": "case-global",
        "teacher_name": "Professor",
        "school_name": "Escola",
        "component_name": "Matemática",
        "academic_year": 2026,
        "start_date": "2026-02-01",
        "end_date": "2026-05-01",
        "strategy": "GLOBAL_ORDINAL_CONTINUOUS_PERIOD",
        "pairs": [{"source_class": "B", "target_class": "A"}],
    }
    ns["_validate_case"](case)


def test_global_pairing_crosses_month_boundary_without_reset():
    source = _source([
        _src("2026-02-27", "p1"),
        _src("2026-03-02", "p2"),
        _src("2026-03-09", "p3"),
    ])
    target_dates = ["2026-02-27", "2026-03-05", "2026-04-01"]
    bindings = {day: _binding() for day in target_dates}
    plan = ns["_global_pair_plan"](
        source=source,
        target=_target(target_dates),
        occupied_dates=set(),
        assignment_by_date=bindings,
    )
    assert plan["status"] == "READY_TO_APPLY"
    assert plan["paired_count"] == 3
    assert [item["global_ordinal"] for item in plan["items"]] == [1, 2, 3]
    assert plan["items"][2]["source_date"] == "2026-03-09"
    assert plan["items"][2]["target_date"] == "2026-04-01"
    assert plan["calendar_cross_month_pair_count"] == 1


def test_global_total_mismatch_is_diagnostic_and_fail_closed():
    source = _source([
        _src("2026-02-01", "p1"),
        _src("2026-02-08", "p2"),
        _src("2026-03-01", "p3"),
    ])
    target_dates = ["2026-02-02", "2026-02-09", "2026-03-02", "2026-04-01"]
    bindings = {day: _binding() for day in target_dates}
    plan = ns["_global_pair_plan"](
        source=source,
        target=_target(target_dates),
        occupied_dates=set(),
        assignment_by_date=bindings,
    )
    assert plan["status"] == "BLOCKED_REVIEW_REQUIRED"
    assert "GLOBAL_COUNT_MISMATCH" in plan["blockers"]
    assert plan["paired_count"] == 3
    assert plan["unpaired_source_count"] == 0
    assert plan["unpaired_target_count"] == 1
    assert plan["unpaired_target_dates"][0]["target_date"] == "2026-04-01"


def test_number_of_classes_is_diagnostic_only_and_does_not_expand_source():
    source = _source([
        _src("2026-02-01", "p1", classes=2),
        _src("2026-02-08", "p2", classes=1),
    ])
    target_dates = ["2026-02-02", "2026-02-09", "2026-02-16"]
    bindings = {day: _binding() for day in target_dates}
    plan = ns["_global_pair_plan"](
        source=source,
        target=_target(target_dates),
        occupied_dates=set(),
        assignment_by_date=bindings,
    )
    assert plan["source_total"] == 2
    assert plan["source_number_of_classes_total"] == 3
    assert plan["paired_count"] == 2
    assert plan["unpaired_target_count"] == 1
    assert plan["status"] == "BLOCKED_REVIEW_REQUIRED"


def test_hard_conflict_prevents_even_diagnostic_pair_items():
    source = _source([_src("2026-02-01", "p1")])
    target_dates = ["2026-02-02"]
    bindings = {day: _binding() for day in target_dates}
    plan = ns["_global_pair_plan"](
        source=source,
        target=_target(target_dates),
        occupied_dates={"2026-02-02"},
        assignment_by_date=bindings,
    )
    assert plan["status"] == "BLOCKED_REVIEW_REQUIRED"
    assert "TARGET_DATE_ALREADY_HAS_CONTENT" in plan["blockers"]
    assert plan["paired_count"] == 0
    assert plan["items"] == []


def test_global_policy_contains_no_write_primitives_or_case_names():
    source = GLOBAL.read_text(encoding="utf-8")
    for forbidden in (
        "insert_one(",
        "update_one(",
        "delete_one(",
        "bulk_write(",
        "Luiz Gomes",
        "Jose Pereira Barbosa",
        "8º ANO",
        "9º ANO",
    ):
        assert forbidden not in source
