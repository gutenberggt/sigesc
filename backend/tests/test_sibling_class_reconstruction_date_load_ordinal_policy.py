from pathlib import Path


def _load_policy():
    ns = {"__name__": "r2f_test_module"}
    code = Path(
        "backend/scripts/sibling_class_reconstruction_date_load_ordinal_policy.py"
    ).read_text(encoding="utf-8")
    exec(compile(code, "r2f-policy.py", "exec"), ns)
    return ns


def _source(ordinal, day, load):
    return {
        "source_ordinal": ordinal,
        "source_date": day,
        "source_month": day[:7],
        "source_declared_load": load,
        "source_kind": "learning_objects",
        "source_attribution": "OTHER_ACTOR",
        "payload_fingerprint": f"source-{ordinal}",
    }


def _target(ordinal, day, load):
    return {
        "target_ordinal": ordinal,
        "target_date": day,
        "target_month": day[:7],
        "target_document_count": load,
        "target_declared_load": load,
        "target_load_consistent": True,
        "target_load_fingerprint": f"target-{ordinal}",
        "session_key_hashes": [f"session-{ordinal}-{i}" for i in range(load)],
    }


def _bindings(targets):
    return {
        item["target_date"]: {
            "status": "RESOLVED",
            "assignment_fingerprint": f"binding-{item['target_ordinal']}",
            "write_mode": "LEGACY_CANONICAL",
            "historical_backfill": False,
        }
        for item in targets
    }


def test_monotonic_load_pairing_preserves_order_and_skips_incompatible_targets():
    ns = _load_policy()
    source = [
        _source(1, "2026-02-03", 2),
        _source(2, "2026-02-10", 1),
        _source(3, "2026-02-17", 2),
    ]
    target = [
        _target(1, "2026-02-04", 1),
        _target(2, "2026-02-05", 2),
        _target(3, "2026-02-11", 1),
        _target(4, "2026-02-18", 2),
    ]
    pairs = ns["_max_monotonic_load_pairs"](source, target)
    assert pairs == [(0, 1), (1, 2), (2, 3)]


def test_ready_requires_complete_count_and_load_coverage():
    ns = _load_policy()
    source = [
        _source(1, "2026-02-03", 2),
        _source(2, "2026-02-10", 1),
    ]
    target = [
        _target(1, "2026-02-04", 2),
        _target(2, "2026-02-11", 1),
    ]
    plan = ns["_date_load_plan"](
        source_units=source,
        source_blockers=[],
        source_multiple_days=[],
        target={"collision_days": [], "partial_metadata_days": []},
        target_days=target,
        target_invalid_load_days=[],
        occupied_dates=set(),
        assignment_by_date=_bindings(target),
        calibration_hash=ns["EXPECTED_R2E_CALIBRATION_HASH"],
        calibration_classification=ns["EXPECTED_R2E_CLASSIFICATION"],
    )
    assert plan["status"] == "READY_TO_APPLY"
    assert plan["blockers"] == []
    assert plan["monotonic_load_compatible_pair_count"] == 2
    assert plan["unpaired_source_content_count"] == 0
    assert plan["unpaired_target_date_count"] == 0


def test_count_and_total_load_gap_remain_fail_closed():
    ns = _load_policy()
    source = [
        _source(1, "2026-02-03", 2),
        _source(2, "2026-02-10", 2),
    ]
    target = [
        _target(1, "2026-02-04", 1),
        _target(2, "2026-02-11", 2),
        _target(3, "2026-02-18", 1),
    ]
    plan = ns["_date_load_plan"](
        source_units=source,
        source_blockers=[],
        source_multiple_days=[],
        target={"collision_days": [], "partial_metadata_days": []},
        target_days=target,
        target_invalid_load_days=[],
        occupied_dates=set(),
        assignment_by_date=_bindings(target),
        calibration_hash=ns["EXPECTED_R2E_CALIBRATION_HASH"],
        calibration_classification=ns["EXPECTED_R2E_CLASSIFICATION"],
    )
    assert plan["status"] == "BLOCKED_REVIEW_REQUIRED"
    assert "DATE_GLOBAL_COUNT_MISMATCH" in plan["blockers"]
    assert "DAILY_LOAD_SEQUENCE_MISMATCH" in plan["blockers"]
    assert plan["monotonic_load_compatible_pair_count"] == 1
    assert plan["unpaired_source_content_count"] == 1
    assert plan["unpaired_target_date_count"] == 2


def test_calibration_drift_blocks_even_when_pairs_fit():
    ns = _load_policy()
    source = [_source(1, "2026-02-03", 2)]
    target = [_target(1, "2026-02-04", 2)]
    plan = ns["_date_load_plan"](
        source_units=source,
        source_blockers=[],
        source_multiple_days=[],
        target={"collision_days": [], "partial_metadata_days": []},
        target_days=target,
        target_invalid_load_days=[],
        occupied_dates=set(),
        assignment_by_date=_bindings(target),
        calibration_hash="0" * 64,
        calibration_classification=ns["EXPECTED_R2E_CLASSIFICATION"],
    )
    assert plan["status"] == "BLOCKED_REVIEW_REQUIRED"
    assert "R2E_CALIBRATION_HASH_CHANGED" in plan["blockers"]
    assert plan["monotonic_load_compatible_pair_count"] == 0


def test_target_daily_load_requires_document_count_equal_declared_sum():
    ns = _load_policy()
    ns["_safe_positive_int"] = lambda value, maximum: int(value)
    target_index = {
        "sessions": [
            {
                "target_date": "2026-04-30",
                "number_of_classes_diagnostic": 1,
                "session_key_hash": "a",
            },
            {
                "target_date": "2026-04-30",
                "number_of_classes_diagnostic": 2,
                "session_key_hash": "b",
            },
        ]
    }
    days, invalid = ns["_target_date_loads"](target_index)
    assert invalid == ["2026-04-30"]
    assert days[0]["target_document_count"] == 2
    assert days[0]["target_declared_load"] == 3
    assert days[0]["target_load_consistent"] is False
