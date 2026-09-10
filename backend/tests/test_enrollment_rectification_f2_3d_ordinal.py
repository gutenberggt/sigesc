from services.enrollment_rectification_attendance_ordinal import build_ordinal_pairs


def _src(date, aula, status, sid):
    return {
        "source_date": date,
        "source_aula_numero": aula,
        "source_attendance_id": sid,
        "attendance_status": status,
    }


def _dst(date, aula, did):
    return {"date": date, "aula_numero": aula, "id": did}


def test_ordinal_preserves_status_sequence_while_ignoring_date_correspondence():
    source = [
        _src("2026-02-10", 1, "P", "s1"),
        _src("2026-02-12", 1, "P", "s2"),
        _src("2026-02-19", 1, "F", "s3"),
        _src("2026-02-24", 1, "J", "s4"),
    ]
    destination = [
        _dst("2026-03-03", 1, "d1"),
        _dst("2026-03-03", 2, "d2"),
        _dst("2026-03-05", 1, "d3"),
        _dst("2026-03-10", 1, "d4"),
    ]

    result = build_ordinal_pairs(source, destination)

    assert [p["source"]["attendance_status"] for p in result["pairs"]] == ["P", "P", "F", "J"]
    assert [p["destination"]["id"] for p in result["pairs"]] == ["d1", "d2", "d3", "d4"]
    assert result["applied_count"] == 4
    assert result["ignored_excess_count"] == 0


def test_source_excess_is_ignored_not_blocked():
    source = [
        _src("2026-02-10", 1, "P", "s1"),
        _src("2026-02-10", 2, "P", "s2"),
        _src("2026-02-11", 1, "P", "s3"),
        _src("2026-02-11", 2, "P", "s4"),
        _src("2026-02-12", 1, "F", "s5"),
        _src("2026-02-12", 2, "F", "s6"),
    ]
    destination = [
        _dst("2026-03-03", 1, "d1"),
        _dst("2026-03-03", 2, "d2"),
        _dst("2026-03-04", 1, "d3"),
        _dst("2026-03-04", 2, "d4"),
    ]

    result = build_ordinal_pairs(source, destination)

    assert [p["source"]["attendance_status"] for p in result["pairs"]] == ["P", "P", "P", "P"]
    assert result["source_count"] == 6
    assert result["destination_slot_count"] == 4
    assert result["applied_count"] == 4
    assert result["ignored_excess_count"] == 2
    assert result["unused_destination_slot_count"] == 0


def test_destination_excess_stays_unused():
    source = [_src("2026-02-10", 1, "P", "s1"), _src("2026-02-11", 1, "F", "s2")]
    destination = [
        _dst("2026-03-01", 1, "d1"),
        _dst("2026-03-02", 1, "d2"),
        _dst("2026-03-03", 1, "d3"),
    ]

    result = build_ordinal_pairs(source, destination)

    assert result["applied_count"] == 2
    assert result["ignored_excess_count"] == 0
    assert result["unused_destination_slot_count"] == 1
