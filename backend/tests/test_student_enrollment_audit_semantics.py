"""Guards da semântica histórica da Auditoria de Matrículas."""

from pathlib import Path

from routers.student_enrollment_audit_semantics import (
    ACTIONABLE_EMPTY_COND,
    HISTORICAL_PRESERVED_COND,
    HISTORICAL_STATUSES,
    classify_empty_enrollment,
    resolve_semantic_empty_count,
)


def test_relocated_with_previous_number_is_preserved_history():
    assert classify_empty_enrollment({
        "status": "relocated",
        "enrollment_number": "",
        "previous_enrollment_number": "202602386",
    }) == "historical_preserved"


def test_transferred_history_with_previous_is_not_actionable():
    assert classify_empty_enrollment({
        "status": "transferred",
        "enrollment_number": None,
        "previous_enrollment_number": "202600123",
    }) == "historical_preserved"


def test_active_empty_remains_actionable_even_with_previous_snapshot():
    assert classify_empty_enrollment({
        "status": "active",
        "enrollment_number": "",
        "previous_enrollment_number": "202600123",
    }) == "actionable_empty"


def test_historical_without_any_number_remains_actionable():
    assert classify_empty_enrollment({
        "status": "relocated",
        "enrollment_number": "",
        "previous_enrollment_number": "",
    }) == "actionable_empty"


def test_unknown_status_is_fail_closed_actionable():
    assert classify_empty_enrollment({
        "status": "mystery_status",
        "enrollment_number": "",
        "previous_enrollment_number": "202600123",
    }) == "actionable_empty"


def test_numbered_enrollment_is_never_empty():
    assert classify_empty_enrollment({
        "status": "active",
        "enrollment_number": "202600999",
        "previous_enrollment_number": None,
    }) == "numbered"


def test_known_historical_status_contract_contains_relocation():
    assert "relocated" in HISTORICAL_STATUSES
    assert "transferred" in HISTORICAL_STATUSES
    assert "progressed" in HISTORICAL_STATUSES


def test_semantic_partition_hides_only_preserved_history_when_exact():
    effective, ok = resolve_semantic_empty_count(
        raw_empty=1,
        actionable=0,
        preserved=1,
    )
    assert ok is True
    assert effective == 0


def test_semantic_partition_keeps_raw_count_when_partition_does_not_close():
    effective, ok = resolve_semantic_empty_count(
        raw_empty=3,
        actionable=1,
        preserved=1,
    )
    assert ok is False
    assert effective == 3


def test_mongo_conditions_keep_active_empty_out_of_preserved_partition():
    # Guard estrutural: o filtro preservado exige status histórico explícito.
    serialized = repr(HISTORICAL_PRESERVED_COND)
    assert "previous_enrollment_number" in serialized
    assert "status" in serialized
    assert "active" not in HISTORICAL_STATUSES

    actionable_serialized = repr(ACTIONABLE_EMPTY_COND)
    assert "$nor" in actionable_serialized
    assert "previous_enrollment_number" in actionable_serialized


def test_adapter_has_no_mongo_write_primitive_and_never_delegates_legacy_repair():
    source = Path("routers/student_enrollment_audit_semantics.py").read_text(encoding="utf-8")
    forbidden = (
        ".update_one(",
        ".update_many(",
        ".insert_one(",
        ".insert_many(",
        ".delete_one(",
        ".delete_many(",
        ".find_one_and_update(",
        ".replace_one(",
        ".bulk_write(",
    )
    for primitive in forbidden:
        assert primitive not in source

    # A referência existe apenas para remover/substituir a rota e manter metadata
    # via wraps; o corpo do novo POST jamais chama a implementação de repair.
    assert "await current_repair(" not in source
    assert "GOVERNED_RECONCILIATION_REQUIRED" in source
    assert "semantic_partition_ok" in source
