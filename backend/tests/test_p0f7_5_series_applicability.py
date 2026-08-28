import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_p0f7_5_series_applicability.py"
spec = importlib.util.spec_from_file_location("p0f75", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)
analyze_course_series = mod.analyze_course_series


def test_explicit_full_match():
    r = analyze_course_series(
        {"grade_levels": ["7º ANO", "8º ANO", "9º ANO"], "carga_horaria_por_serie": None},
        ["8º ANO", "9º ANO"],
        level_compatibility="EXACT_LEVEL_MATCH",
    )
    assert r["classification"] == "EXPLICIT_SERIES_FULL_MATCH"


def test_matrix_full_but_explicit_scope_conflict():
    r = analyze_course_series(
        {
            "grade_levels": ["6º ANO"],
            "carga_horaria_por_serie": {
                "6º Ano": 120,
                "7º Ano": 120,
                "8º Ano": 120,
                "9º Ano": 120,
            },
        },
        ["8º ANO", "9º ANO"],
        level_compatibility="EXACT_LEVEL_MATCH",
    )
    assert r["classification"] == "MATRIX_FULL_BUT_EXPLICIT_SCOPE_CONFLICT_REQUIRES_REVIEW"


def test_partial_series_match():
    r = analyze_course_series(
        {"grade_levels": ["7º ANO", "8º ANO", "9º ANO"], "carga_horaria_por_serie": None},
        ["6º ANO", "7º ANO"],
        level_compatibility="EXACT_LEVEL_MATCH",
    )
    assert r["classification"] == "PARTIAL_SERIES_MATCH_REQUIRES_REVIEW"


def test_eja_exact_level_without_series_scope():
    r = analyze_course_series(
        {"grade_levels": [], "carga_horaria_por_serie": None},
        ["EJA 3ª ETAPA", "EJA 4ª ETAPA"],
        level_compatibility="EXACT_LEVEL_MATCH",
    )
    assert r["classification"] == "LEVEL_ONLY_NO_SERIES_SCOPE"


def test_level_mismatch_precedes_series():
    r = analyze_course_series(
        {"grade_levels": ["7º ANO"], "carga_horaria_por_serie": None},
        ["EJA 3ª ETAPA", "EJA 4ª ETAPA"],
        level_compatibility="LEVEL_MISMATCH",
    )
    assert r["classification"] == "LEVEL_MISMATCH_PRECEDES_SERIES"


def test_no_automatic_decision_flags():
    r = analyze_course_series(
        {"grade_levels": [], "carga_horaria_por_serie": {"8º Ano": 120}},
        ["8º ANO"],
        level_compatibility="EXACT_LEVEL_MATCH",
    )
    assert r["automatic_course_decision"] is False
    assert r["automatic_workload_decision"] is False
