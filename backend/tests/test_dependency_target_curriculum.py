import pytest
from fastapi import HTTPException

from utils.dependency_validator import validate_dependency_target_values


def _class(**overrides):
    doc = {
        "id": "class-67",
        "school_id": "school-sao-bras",
        "is_multi_grade": True,
        "series": ["6º ANO", "7º ANO"],
        "grade_level": "6º E 7º ANO",
    }
    doc.update(overrides)
    return doc


def _course(**overrides):
    doc = {"id": "course-lp", "grade_levels": ["6º Ano"]}
    doc.update(overrides)
    return doc


def test_accepts_equivalent_series_spelling_for_multigrade_target():
    result = validate_dependency_target_values(
        class_doc=_class(),
        course_doc=_course(),
        effective_course_ids=["course-lp", "course-mat"],
        school_id="school-sao-bras",
        course_id="course-lp",
        target_series="6º ANO",
    )
    assert result["target_series"] == "6º ANO"


def test_accepts_component_scope_that_contains_selected_series():
    result = validate_dependency_target_values(
        class_doc=_class(),
        course_doc=_course(grade_levels=["6º/7º/9º Ano"]),
        effective_course_ids=["course-lp"],
        school_id="school-sao-bras",
        course_id="course-lp",
        target_series="6° ano",
    )
    assert result["course_id"] == "course-lp"


def test_rejects_component_from_other_series():
    with pytest.raises(HTTPException) as exc:
        validate_dependency_target_values(
            class_doc=_class(),
            course_doc=_course(grade_levels=["7º ANO"]),
            effective_course_ids=["course-lp"],
            school_id="school-sao-bras",
            course_id="course-lp",
            target_series="6º ANO",
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "DEPENDENCY_TARGET_COURSE_SERIES_MISMATCH"


def test_rejects_course_not_offered_by_destination_class():
    with pytest.raises(HTTPException) as exc:
        validate_dependency_target_values(
            class_doc=_class(),
            course_doc=_course(),
            effective_course_ids=["course-mat"],
            school_id="school-sao-bras",
            course_id="course-lp",
            target_series="6º ANO",
        )
    assert exc.value.detail["code"] == "DEPENDENCY_TARGET_COURSE_NOT_IN_CLASS"


def test_requires_series_for_real_multigrade_class():
    with pytest.raises(HTTPException) as exc:
        validate_dependency_target_values(
            class_doc=_class(),
            course_doc=_course(),
            effective_course_ids=["course-lp"],
            school_id="school-sao-bras",
            course_id="course-lp",
            target_series=None,
        )
    assert exc.value.detail["code"] == "DEPENDENCY_TARGET_SERIES_REQUIRED"


def test_course_without_grade_levels_applies_to_selected_series():
    result = validate_dependency_target_values(
        class_doc=_class(),
        course_doc=_course(grade_levels=[]),
        effective_course_ids=["course-lp"],
        school_id="school-sao-bras",
        course_id="course-lp",
        target_series="6º ANO",
    )
    assert result["class_id"] == "class-67"
