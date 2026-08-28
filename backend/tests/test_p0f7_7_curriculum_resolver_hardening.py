from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESOLVER = ROOT / "backend" / "utils" / "curriculum_resolver.py"

spec = importlib.util.spec_from_file_location("curriculum_resolver_p0f77", RESOLVER)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def _candidate(
    course_id: str,
    *,
    rank: int,
    evidence: int,
    active: bool = True,
    created_at: str = "2026-01-01T00:00:00Z",
) -> dict:
    return {
        "course_id": course_id,
        "curricular_rank": rank,
        "evidence_score": evidence,
        "active": active,
        "created_at": created_at,
    }


def test_series_tokens_normalize_regular_and_eja() -> None:
    assert mod._series_tokens(["8º", "9º ANO"]) == {"ano:8", "ano:9"}
    assert mod._series_tokens("EJA 3ª ETAPA") == {"eja:3"}
    assert mod._series_tokens({"6º ANO": 120, "7º ANO": 120}) == {
        "ano:6",
        "ano:7",
    }


def test_case_1_source_is_strong_and_target_requires_review() -> None:
    class_series = {"ano:8", "ano:9"}
    source = mod._curricular_fit(
        {
            "nivel_ensino": "fundamental_anos_finais",
            "grade_levels": ["7º", "8º", "9º"],
            "carga_horaria_por_serie": {},
        },
        class_level="fundamental_anos_finais",
        class_series=class_series,
    )
    target = mod._curricular_fit(
        {
            "nivel_ensino": "fundamental_anos_finais",
            "grade_levels": ["6º"],
            "carga_horaria_por_serie": {
                "6º ANO": 120,
                "7º ANO": 120,
                "8º ANO": 120,
                "9º ANO": 120,
            },
        },
        class_level="fundamental_anos_finais",
        class_series=class_series,
    )

    assert source["rank"] == 3
    assert source["classification"] == "EXPLICIT_SERIES_FULL_MATCH"
    assert target["rank"] == 2
    assert target["classification"] == "SERIES_SCOPE_CONFLICT_REQUIRES_REVIEW"


def test_case_1_curricular_strength_overrules_operational_evidence() -> None:
    source = _candidate("source", rank=3, evidence=0)
    target = _candidate("target", rank=2, evidence=50)

    winner, reason = mod._pick_winner([target, source])

    assert winner["course_id"] == "source"
    assert reason == "stronger_curricular_compatibility"


def test_case_2_level_mismatch_is_incompatible() -> None:
    class_series = {"eja:3", "eja:4"}
    source = mod._curricular_fit(
        {
            "nivel_ensino": "fundamental_anos_finais",
            "grade_levels": ["7º", "8º", "9º"],
        },
        class_level="eja_final",
        class_series=class_series,
    )
    target = mod._curricular_fit(
        {
            "nivel_ensino": "fundamental_anos_finais",
            "grade_levels": ["6º"],
        },
        class_level="eja_final",
        class_series=class_series,
    )
    compatible_level_only = mod._curricular_fit(
        {
            "nivel_ensino": "eja_final",
            "grade_levels": [],
            "carga_horaria_por_serie": {},
        },
        class_level="eja_final",
        class_series=class_series,
    )

    assert source["classification"] == "LEVEL_MISMATCH"
    assert target["classification"] == "LEVEL_MISMATCH"
    assert source["rank"] == target["rank"] == 1
    assert compatible_level_only["classification"] == "LEVEL_MATCH_NO_SERIES_SCOPE"
    assert compatible_level_only["rank"] == 2


def test_compatible_level_only_beats_mismatched_evidence_if_already_candidate() -> None:
    mismatched = _candidate("old-evidence", rank=1, evidence=100)
    compatible = _candidate("eja-compatible", rank=2, evidence=0)

    winner, reason = mod._pick_winner([mismatched, compatible])

    assert winner["course_id"] == "eja-compatible"
    assert reason == "stronger_curricular_compatibility"


def test_case_3_remains_review_and_uses_historical_evidence_within_same_rank() -> None:
    class_series = {"ano:6", "ano:7"}
    source_fit = mod._curricular_fit(
        {
            "nivel_ensino": "fundamental_anos_finais",
            "grade_levels": ["7º", "8º", "9º"],
            "carga_horaria_por_serie": {},
        },
        class_level="fundamental_anos_finais",
        class_series=class_series,
    )
    target_fit = mod._curricular_fit(
        {
            "nivel_ensino": "fundamental_anos_finais",
            "grade_levels": ["6º"],
            "carga_horaria_por_serie": {
                "6º ANO": 120,
                "7º ANO": 120,
            },
        },
        class_level="fundamental_anos_finais",
        class_series=class_series,
    )

    assert source_fit["rank"] == 2
    assert source_fit["classification"] == (
        "PARTIAL_EXPLICIT_SERIES_MATCH_REQUIRES_REVIEW"
    )
    assert target_fit["rank"] == 2
    assert target_fit["classification"] == "SERIES_SCOPE_CONFLICT_REQUIRES_REVIEW"

    source = _candidate("source", rank=source_fit["rank"], evidence=0)
    target = _candidate("target", rank=target_fit["rank"], evidence=8)
    winner, reason = mod._pick_winner([source, target])

    assert winner["course_id"] == "target"
    assert reason == "higher_evidence"


def test_historical_tiebreak_order_is_preserved_inside_same_curricular_rank() -> None:
    older = _candidate(
        "b-course",
        rank=3,
        evidence=0,
        created_at="2026-01-01T00:00:00Z",
    )
    newer = _candidate(
        "a-course",
        rank=3,
        evidence=0,
        created_at="2026-02-01T00:00:00Z",
    )

    winner, reason = mod._pick_winner([older, newer])

    assert winner["course_id"] == "a-course"
    assert reason == "recency_tiebreak"


def test_level_match_without_series_scope_is_review_not_strong() -> None:
    fit = mod._curricular_fit(
        {"nivel_ensino": "fundamental_anos_finais"},
        class_level="fundamental_anos_finais",
        class_series={"ano:8"},
    )
    assert fit["rank"] == 2
    assert fit["classification"] == "LEVEL_MATCH_NO_SERIES_SCOPE"
