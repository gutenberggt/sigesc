from backend.scripts.audit_p0f7_9d2_safe_targets_offline import resolve_targets


def _base_audit():
    return {
        "mantenedora_id": "tenant-1",
        "academic_year": 2026,
        "findings": [
            {
                "assignment_id": "a1",
                "school_id": "s1",
                "class_id": "c1",
                "class_name": "6º ANO A",
                "course_id": "wrong",
                "course_name": "Geografia",
                "integrity_code": "TEACHER_ASSIGNMENT_LEVEL_MISMATCH",
            }
        ],
    }


def _assignment():
    return {
        "id": "a1",
        "mantenedora_id": "tenant-1",
        "school_id": "s1",
        "class_id": "c1",
        "course_id": "wrong",
        "academic_year": 2026,
        "status": "ativo",
    }


def _class():
    return {
        "id": "c1",
        "mantenedora_id": "tenant-1",
        "school_id": "s1",
        "academic_year": 2026,
        "nivel_ensino": "fundamental_anos_finais",
        "grade_level": "6º ANO",
        "series": ["6º ANO"],
    }


def test_unique_same_name_candidate_must_pass_writer_ssot():
    reference = {
        "courses": [
            {
                "id": "wrong",
                "name": "Geografia",
                "nivel_ensino": "eja_final",
                "grade_levels": [],
                "mantenedora_id": "tenant-1",
            },
            {
                "id": "safe",
                "name": "Geografia",
                "nivel_ensino": "fundamental_anos_finais",
                "grade_levels": ["6º ANO"],
                "mantenedora_id": "tenant-1",
            },
        ]
    }
    result = resolve_targets(
        _base_audit(),
        reference,
        {"c1": _class()},
        {"a1": _assignment()},
    )
    assert len(result) == 1
    assert result[0]["resolution"] == "UNIQUE_SAFE_TARGET"
    assert result[0]["validated_targets"][0]["course_id"] == "safe"


def test_same_name_but_wrong_series_is_not_safe_target():
    reference = {
        "courses": [
            {
                "id": "wrong",
                "name": "Geografia",
                "nivel_ensino": "eja_final",
                "mantenedora_id": "tenant-1",
            },
            {
                "id": "series-wrong",
                "name": "Geografia",
                "nivel_ensino": "fundamental_anos_finais",
                "grade_levels": ["7º ANO", "8º ANO", "9º ANO"],
                "mantenedora_id": "tenant-1",
            },
        ]
    }
    result = resolve_targets(
        _base_audit(),
        reference,
        {"c1": _class()},
        {"a1": _assignment()},
    )
    assert result[0]["resolution"] == "NO_SAFE_TARGET"
    assert result[0]["rejected_candidate_codes"] == {
        "TEACHER_ASSIGNMENT_SERIES_MISMATCH": 1
    }


def test_multiple_valid_candidates_requires_review():
    reference = {
        "courses": [
            {
                "id": "wrong",
                "name": "Geografia",
                "nivel_ensino": "eja_final",
                "mantenedora_id": "tenant-1",
            },
            {
                "id": "safe-1",
                "name": "Geografia",
                "nivel_ensino": "fundamental_anos_finais",
                "grade_levels": ["6º ANO"],
                "mantenedora_id": "tenant-1",
            },
            {
                "id": "safe-2",
                "name": "GEOGRAFIA",
                "nivel_ensino": "fundamental_anos_finais",
                "grade_levels": ["6º Ano", "7º Ano", "8º Ano", "9º Ano"],
                "mantenedora_id": "tenant-1",
            },
        ]
    }
    result = resolve_targets(
        _base_audit(),
        reference,
        {"c1": _class()},
        {"a1": _assignment()},
    )
    assert result[0]["resolution"] == "MULTIPLE_SAFE_TARGETS_REVIEW"
    assert {x["course_id"] for x in result[0]["validated_targets"]} == {
        "safe-1",
        "safe-2",
    }


def test_explicitly_inactive_candidate_is_excluded():
    reference = {
        "courses": [
            {
                "id": "wrong",
                "name": "Geografia",
                "nivel_ensino": "eja_final",
                "mantenedora_id": "tenant-1",
            },
            {
                "id": "inactive",
                "name": "Geografia",
                "nivel_ensino": "fundamental_anos_finais",
                "grade_levels": ["6º ANO"],
                "active": False,
                "mantenedora_id": "tenant-1",
            },
        ]
    }
    result = resolve_targets(
        _base_audit(),
        reference,
        {"c1": _class()},
        {"a1": _assignment()},
    )
    assert result[0]["resolution"] == "NO_SAFE_TARGET"
    assert result[0]["same_name_alternatives_considered"] == 0


def test_nonconfirmed_findings_are_not_resolved():
    audit = _base_audit()
    audit["findings"][0]["integrity_code"] = "TEACHER_ASSIGNMENT_CLASS_LEVEL_REQUIRED"
    reference = {
        "courses": [
            {
                "id": "wrong",
                "name": "Geografia",
                "nivel_ensino": "eja_final",
                "mantenedora_id": "tenant-1",
            }
        ]
    }
    result = resolve_targets(
        audit,
        reference,
        {"c1": _class()},
        {"a1": _assignment()},
    )
    assert result == []
