from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend" / "scripts" / "audit_p0f7_6_curriculum_resolver_policy_conflict.py"
RESOLVER = ROOT / "backend" / "utils" / "curriculum_resolver.py"

spec = importlib.util.spec_from_file_location("p0f76", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def _case(
    number: int,
    *,
    class_name: str,
    class_level: str,
    class_series: list[str],
    source_classification: str,
    target_classification: str,
    alternate: dict | None = None,
) -> dict:
    candidates = [
        {
            "course": {
                "course_id": "target-course",
                "nivel_ensino": "fundamental_anos_finais",
                "workload": 120,
            },
            "is_source": False,
            "is_target": True,
            "series_applicability": {"classification": target_classification},
        },
        {
            "course": {
                "course_id": "source-course",
                "nivel_ensino": "fundamental_anos_finais",
                "workload": 80,
            },
            "is_source": True,
            "is_target": False,
            "series_applicability": {"classification": source_classification},
        },
    ]
    if alternate:
        candidates.append(
            {
                "course": alternate,
                "is_source": False,
                "is_target": False,
                "series_applicability": {
                    "classification": alternate["series_classification"]
                },
            }
        )

    return {
        "case_number": number,
        "teacher": {"name": "Aciolino Alves Carneiro"},
        "school": {"name": "E M E I E F Bom Jesus"},
        "class": {
            "name": class_name,
            "explicit_level_used": class_level,
        },
        "class_series": class_series,
        "source_series_applicability": {"classification": source_classification},
        "target_series_applicability": {"classification": target_classification},
        "exact_level_same_name_candidates": candidates,
        "identity_evidence_from_p0f7_3": {
            "classification": "IDENTITY_EVIDENCE_LEANS_TARGET"
        },
    }


def _report() -> dict:
    payload = {
        "phase": mod.P0F75_PHASE,
        "manifest_version": 1,
        "mode": "READ_ONLY_SERIES_APPLICABILITY",
        "status": "PASS",
        "group_name": "Geografia",
        "summary": {
            "expected_cases": 3,
            "documented_cases": 3,
            "automatic_course_decisions": 0,
            "automatic_workload_decisions": 0,
            "human_or_policy_decisions_required": 3,
            "database_access": False,
            "database_mutation": False,
        },
        "safety": {
            "read_only": True,
            "database_access": False,
            "database_mutation": False,
            "production_writes_executed": False,
            "not_authorization_for_executor": True,
        },
        "cases": [
            _case(
                1,
                class_name="MULTI 8º E 9º",
                class_level="fundamental_anos_finais",
                class_series=["8º ANO", "9º ANO"],
                source_classification="EXPLICIT_SERIES_FULL_MATCH",
                target_classification="MATRIX_FULL_BUT_EXPLICIT_SCOPE_CONFLICT_REQUIRES_REVIEW",
            ),
            _case(
                2,
                class_name="MULTI 3º E 4º ETAPA",
                class_level="eja_final",
                class_series=["EJA 3ª ETAPA", "EJA 4ª ETAPA"],
                source_classification="LEVEL_MISMATCH_PRECEDES_SERIES",
                target_classification="LEVEL_MISMATCH_PRECEDES_SERIES",
                alternate={
                    "course_id": "eja-course",
                    "nivel_ensino": "eja_final",
                    "workload": 80,
                    "series_classification": "LEVEL_ONLY_NO_SERIES_SCOPE",
                },
            ),
            _case(
                3,
                class_name="MULTI 6º E 7º",
                class_level="fundamental_anos_finais",
                class_series=["6º ANO", "7º ANO"],
                source_classification="PARTIAL_SERIES_MATCH_REQUIRES_REVIEW",
                target_classification="MATRIX_FULL_BUT_EXPLICIT_SCOPE_CONFLICT_REQUIRES_REVIEW",
            ),
        ],
    }
    payload["manifest_sha256"] = mod._canonical_sha256(payload)
    return payload


def test_read_only_guard_passes() -> None:
    mod.assert_read_only()


def test_current_resolver_reports_policy_gap_closed_by_hardening() -> None:
    policy = mod.inspect_resolver_policy(RESOLVER)
    assert policy["expected_precedence_confirmed"] is True
    assert policy["winner_uses_operational_signals"] is True
    assert policy["winner_curricular_gates"]["curricular_rank"] is True
    assert policy["loaded_curricular_fields"]["nivel_ensino"] is True
    assert policy["loaded_curricular_fields"]["grade_levels"] is True
    assert policy["loaded_curricular_fields"]["carga_horaria_por_serie"] is True
    assert policy["derived_curricular_rank_gate"] is True
    assert policy["winner_has_level_or_series_gate"] is True
    assert policy["policy_gap_candidate"] is False


def test_three_cases_are_classified_without_automatic_decision() -> None:
    cases = [mod.classify_case(case) for case in _report()["cases"]]

    assert cases[0]["conflict_codes"] == [
        "EVIDENCE_LEANS_TARGET_BUT_SOURCE_HAS_STRONGER_SERIES_SCOPE"
    ]
    assert cases[1]["conflict_codes"] == [
        "EVIDENCE_LEANS_TARGET_BUT_TARGET_CURRICULARLY_INCOMPATIBLE",
        "SOURCE_AND_TARGET_INCOMPATIBLE_ALTERNATE_LEVEL_CANDIDATE_EXISTS",
    ]
    assert cases[2]["conflict_codes"] == [
        "EVIDENCE_LEANS_TARGET_WITH_UNRESOLVED_TARGET_SERIES_SCOPE"
    ]

    assert all(case["automatic_course_decision"] is False for case in cases)
    assert all(case["automatic_workload_decision"] is False for case in cases)


def test_collect_report_is_offline_and_reports_hardening_closed(tmp_path: Path) -> None:
    source = tmp_path / "p0f7_5.json"
    source.write_text(json.dumps(_report(), ensure_ascii=False), encoding="utf-8")

    report = mod.collect_report(source, RESOLVER)

    assert report["status"] == "PASS"
    assert report["summary"]["meaningful_policy_conflicts"] == 4
    assert report["summary"]["resolver_policy_gap_candidate"] is False
    assert report["summary"]["requires_resolver_hardening_before_executor"] is False
    assert report["summary"]["automatic_course_decisions"] == 0
    assert report["summary"]["automatic_workload_decisions"] == 0
    assert report["summary"]["database_access"] is False
    assert report["safety"]["offline"] is True
    assert report["safety"]["not_authorization_for_executor"] is True


def test_invalid_p0f75_sha_fails_closed() -> None:
    report = _report()
    report["manifest_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="P0F7_5_SHA_MISMATCH"):
        mod.validate_p0f75(report)
