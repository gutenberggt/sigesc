from pathlib import Path


def _load_policy():
    ns = {"__name__": "r2e_test_module"}
    code = Path(
        "backend/scripts/sibling_class_reconstruction_source_semantic_calibration.py"
    ).read_text(encoding="utf-8")
    exec(compile(code, "r2e-policy.py", "exec"), ns)
    return ns


def _profile(
    date,
    *,
    content_count,
    attendance_count,
    content_load,
    attendance_load,
    content_all_one=False,
    attendance_all_one=False,
):
    return {
        "date": date,
        "month": date[:7],
        "content_count": content_count,
        "attendance_document_count": attendance_count,
        "content_declared_load_sum": content_load,
        "attendance_declared_load_sum": attendance_load,
        "content_all_declared_one": content_all_one,
        "attendance_all_declared_one": attendance_all_one,
        "single_content_date": content_count == 1,
        "content_count_equals_attendance_documents": content_count == attendance_count,
        "declared_load_equal": content_load == attendance_load,
        "single_content_load_equals_attendance_documents": (
            content_count == 1 and content_load == attendance_count
        ),
        "single_content_load_equals_attendance_load": (
            content_count == 1 and content_load == attendance_load
        ),
    }


def test_one_content_per_date_covering_two_unit_sessions():
    ns = _load_policy()
    profiles = [
        _profile(
            "2026-02-03",
            content_count=1,
            attendance_count=2,
            content_load=2,
            attendance_load=2,
            attendance_all_one=True,
        ),
        _profile(
            "2026-02-10",
            content_count=1,
            attendance_count=2,
            content_load=2,
            attendance_load=2,
            attendance_all_one=True,
        ),
    ]
    result = ns["_classify_source_semantics"](profiles)
    assert result["classification"] == (
        "ONE_CONTENT_PER_DATE_COVERS_SESSION_DOCUMENTS_SUPPORTED"
    )
    assert result["blockers"] == []


def test_one_content_per_date_covering_bundled_attendance_load():
    ns = _load_policy()
    profiles = [
        _profile(
            "2026-03-05",
            content_count=1,
            attendance_count=1,
            content_load=2,
            attendance_load=2,
        ),
        _profile(
            "2026-03-12",
            content_count=1,
            attendance_count=1,
            content_load=2,
            attendance_load=2,
        ),
    ]
    result = ns["_classify_source_semantics"](profiles)
    assert result["classification"] == (
        "ONE_CONTENT_PER_DATE_COVERS_DECLARED_LOAD_SUPPORTED"
    )


def test_one_content_per_session_is_supported_when_both_are_unitary():
    ns = _load_policy()
    profiles = [
        _profile(
            "2026-04-07",
            content_count=2,
            attendance_count=2,
            content_load=2,
            attendance_load=2,
            content_all_one=True,
            attendance_all_one=True,
        ),
        _profile(
            "2026-04-14",
            content_count=2,
            attendance_count=2,
            content_load=2,
            attendance_load=2,
            content_all_one=True,
            attendance_all_one=True,
        ),
    ]
    result = ns["_classify_source_semantics"](profiles)
    assert result["classification"] == "ONE_CONTENT_PER_SESSION_SUPPORTED"
    assert result["multiple_content_dates"] == ["2026-04-07", "2026-04-14"]


def test_gap_forces_fail_closed():
    ns = _load_policy()
    profiles = [
        _profile(
            "2026-02-03",
            content_count=1,
            attendance_count=2,
            content_load=2,
            attendance_load=2,
            attendance_all_one=True,
        ),
        _profile(
            "2026-02-10",
            content_count=1,
            attendance_count=0,
            content_load=2,
            attendance_load=0,
        ),
    ]
    result = ns["_classify_source_semantics"](profiles)
    assert result["classification"] == "INSUFFICIENT_OR_CONFLICTING_EVIDENCE"
    assert "SOURCE_CONTENT_DATE_WITHOUT_ATTENDANCE" in result["blockers"]


def test_mixed_patterns_are_not_collapsed_into_one_rule():
    ns = _load_policy()
    profiles = [
        _profile(
            "2026-03-05",
            content_count=1,
            attendance_count=2,
            content_load=2,
            attendance_load=2,
            attendance_all_one=True,
        ),
        _profile(
            "2026-03-12",
            content_count=1,
            attendance_count=1,
            content_load=1,
            attendance_load=2,
        ),
    ]
    result = ns["_classify_source_semantics"](profiles)
    assert result["classification"] == "MIXED_HISTORICAL_GRANULARITY"
