import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "ana_lucia_f2_5b_legacy_aggregate_adjudication_readonly.py"
spec = importlib.util.spec_from_file_location("f25b", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def row(**kwargs):
    base = {
        "id": kwargs.pop("id", "row-1"),
        "class_id": kwargs.pop("class_id", "class-1"),
        "date": kwargs.pop("date", "2026-03-10"),
        "period": kwargs.pop("period", "regular"),
        "aula_numero": kwargs.pop("aula_numero", None),
        "number_of_classes": kwargs.pop("number_of_classes", 1),
    }
    base.update(kwargs)
    return base


def test_legacy_aggregate_is_preservable_without_any_session_collision():
    source = [row()]
    case = mod._adjudicate_legacy_aggregate_case(source[0], source_candidates=source, target_attendance=[])
    assert case["classification"] == "LEGACY_AGGREGATE_KEY_PRESERVABLE_NO_AULA_BACKFILL"
    assert case["aula_numero_inferred"] is None
    assert case["aula_numero_backfill_required"] is False


def test_target_aggregate_same_key_blocks():
    source = [row(id="source")]
    target = [row(id="target")]
    case = mod._adjudicate_legacy_aggregate_case(source[0], source_candidates=source, target_attendance=target)
    assert case["classification"] == "BLOCKED_LEGACY_AGGREGATE_TARGET_COLLISION"


def test_target_session_same_day_blocks_mixed_schema():
    source = [row(id="source")]
    target = [row(id="target", aula_numero=1)]
    case = mod._adjudicate_legacy_aggregate_case(source[0], source_candidates=source, target_attendance=target)
    assert case["classification"] == "BLOCKED_MIXED_TARGET_AGGREGATE_AND_SESSION_ROWS_SAME_DAY"


def test_source_session_same_day_blocks_mixed_schema():
    aggregate = row(id="source-aggregate")
    source = [aggregate, row(id="source-session", aula_numero=1)]
    case = mod._adjudicate_legacy_aggregate_case(aggregate, source_candidates=source, target_attendance=[])
    assert case["classification"] == "BLOCKED_MIXED_SOURCE_AGGREGATE_AND_SESSION_ROWS_SAME_DAY"


def test_duplicate_source_aggregates_block():
    first = row(id="source-1")
    source = [first, row(id="source-2")]
    case = mod._adjudicate_legacy_aggregate_case(first, source_candidates=source, target_attendance=[])
    assert case["classification"] == "BLOCKED_DUPLICATE_LEGACY_AGGREGATE_SOURCE"


def test_missing_date_is_never_inferred_from_timestamps():
    source = [row(date="")]
    case = mod._adjudicate_legacy_aggregate_case(source[0], source_candidates=source, target_attendance=[])
    assert case["classification"] == "UNRESOLVED_MISSING_DATE_NO_TIMESTAMP_INFERENCE"


def test_tenant_adjudication_uses_ana_legacy_context_not_dvd():
    candidates = [{"id": "a", "class_id": "c1", "school_id": "s1", "mantenedora_id": ""}]
    class_by_id = {"c1": {"class": "6º ANO A", "class_id": "c1", "school_id": "s1", "tenant_id": "t1"}}
    result = mod._tenant_adjudication(attendance_candidates=candidates, class_by_id=class_by_id, tenant_id="t1")
    assert result["unresolved_or_contradictory"] == 0
    assert result["decision_counts"] == {
        "DETERMINISTIC_FROM_ANA_LEGACY_ASSIGNMENT_CLASS_SCHOOL_CONTEXT": 1
    }


def test_tenant_school_mismatch_blocks():
    candidates = [{"id": "a", "class_id": "c1", "school_id": "wrong", "mantenedora_id": ""}]
    class_by_id = {"c1": {"class": "6º ANO A", "class_id": "c1", "school_id": "s1", "tenant_id": "t1"}}
    result = mod._tenant_adjudication(attendance_candidates=candidates, class_by_id=class_by_id, tenant_id="t1")
    assert result["unresolved_or_contradictory"] == 1
    assert result["decision_counts"] == {"ROW_SCHOOL_MISMATCH": 1}


def test_natural_key_adjudication_never_authorizes_aula_backfill():
    candidates = [row()]
    class_by_id = {"class-1": {"class": "6º ANO A"}}
    result = mod._natural_key_adjudication(
        attendance_candidates=candidates,
        target_attendance=[],
        class_by_id=class_by_id,
    )
    assert result["legacy_aggregate_preservable_cases"] == 1
    assert result["aula_numero_inference_used"] is False
    assert result["aula_numero_backfill_authorized"] is False
