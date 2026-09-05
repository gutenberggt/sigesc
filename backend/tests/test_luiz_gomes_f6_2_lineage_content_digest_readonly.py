from backend.scripts import luiz_gomes_f6_2_lineage_content_digest_readonly as mod


def test_scope_is_exact():
    assert mod.TARGET_CLASSES == ("8º ANO A", "9º ANO A")
    assert mod.REFERENCE_CLASSES == ("6º ANO A", "6º ANO B", "7º ANO A", "7º ANO B")
    assert mod.START_DATE == "2026-02-01"
    assert mod.END_DATE == "2026-05-01"


def test_payload_digest_is_deterministic_and_plaintext_free():
    row1 = {
        "content": "  Frações   equivalentes ",
        "observations": None,
        "methodology": "Exercícios",
        "resources": ["quadro"],
        "number_of_classes": 1,
    }
    row2 = {
        "content": "Frações equivalentes",
        "observations": None,
        "methodology": "Exercícios",
        "resources": ["quadro"],
        "number_of_classes": 1,
    }
    digest1, length1 = mod._payload_digest(row1)
    digest2, length2 = mod._payload_digest(row2)
    assert digest1 == digest2
    assert length1 == length2
    assert "Frações" not in digest1
    assert len(digest1) == 64


def test_catalog_lineage_reconstructs_name_backwards():
    logs = [{
        "document_id": "c1",
        "timestamp": "2026-05-03T12:00:00+00:00",
        "changes": {"name": {"old": "Matemática", "new": "História"}},
    }]
    inferred, evidence = mod._course_name_at_date("c1", "2026-03-10", "História", logs)
    assert evidence is True
    assert inferred == "Matemática"


def test_catalog_lineage_does_not_invent_history_without_log():
    inferred, evidence = mod._course_name_at_date("c1", "2026-03-10", "História", [])
    assert evidence is False
    assert inferred == "História"


def test_audit_course_transition_is_strict_pair():
    logs = [{
        "document_id": "lo1",
        "changes": {"course_id": {"old": "legacy", "new": "math"}},
    }]
    assert mod._audit_transition_to_math("lo1", "legacy", "math", logs) is True
    assert mod._audit_transition_to_math("lo1", "other", "math", logs) is False


def test_actor_partition_distinguishes_luiz_foreign_and_missing():
    actors = {"u1", "s1"}
    assert mod._actor_category({"recorded_by": "u1"}, actors) == "LUIZ"
    assert mod._actor_category({"recorded_by": "u2"}, actors) == "FOREIGN_ACTOR_PRESENT"
    assert mod._actor_category({}, actors) == "NO_ACTOR_METADATA"


def test_summary_months_are_fixed():
    rows = [
        {"date": "2026-02-10"},
        {"date": "2026-03-10"},
        {"date": "2026-03-10"},
        {"date": "2026-04-10"},
    ]
    result = mod._summary(rows)
    assert result["documents"] == 4
    assert result["distinct_dates"] == 3
    assert result["months"] == {"02": 1, "03": 2, "04": 1}
