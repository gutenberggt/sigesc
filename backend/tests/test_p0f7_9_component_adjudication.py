from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend" / "scripts" / "audit_p0f7_9_component_adjudication_runner.py"
CORE = ROOT / "backend" / "scripts" / "audit_p0f7_9_component_adjudication.py"
POWERSHELL = ROOT / "scripts" / "p0f7_9_adjudicate_local.ps1"

spec = importlib.util.spec_from_file_location("p0f79", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def _seal(payload: dict) -> dict:
    payload = dict(payload)
    payload["manifest_sha256"] = mod._canonical_sha256(payload)
    return payload


def _p0f75() -> dict:
    cases = []
    for number in (1, 2, 3):
        cases.append({
            "case_number": number,
            "identity_evidence_from_p0f7_3": {
                "classification": "IDENTITY_EVIDENCE_LEANS_TARGET"
            },
        })
    return _seal({
        "phase": mod.P0F75_PHASE,
        "status": "PASS",
        "cases": cases,
    })


def _case(
    number: int,
    policy: str,
    source_rank: int,
    target_rank: int,
    *,
    preference=None,
    adjudication=True,
    alternatives=None,
) -> dict:
    return {
        "case_number": number,
        "teacher_name": "Professor Teste",
        "school_name": "Escola Teste",
        "class_name": f"Turma {number}",
        "class_level": "eja_final" if number == 2 else "fundamental_anos_finais",
        "class_series": ["eja:3", "eja:4"] if number == 2 else ["ano:6", "ano:7"],
        "snapshot_drift": False,
        "source": {
            "course_id": f"source-{number}",
            "curricular_rank": source_rank,
            "curricular_classification": "LEVEL_MISMATCH" if source_rank == 1 else "SOURCE_CLASS",
        },
        "target": {
            "course_id": f"target-{number}",
            "curricular_rank": target_rank,
            "curricular_classification": "LEVEL_MISMATCH" if target_rank == 1 else "TARGET_CLASS",
        },
        "alternative_exact_level_candidates": alternatives or [],
        "pair_policy": {
            "state": policy,
            "curricular_preference": preference,
            "component_adjudication_required": adjudication,
            "automatic_database_action": False,
        },
        "automatic_course_mutation": False,
        "automatic_workload_decision": False,
        "executor_authorized": False,
    }


def _p0f782(p0f75: dict) -> dict:
    cases = [
        _case(
            1,
            mod.CASE1_POLICY,
            3,
            2,
            preference="source",
            adjudication=False,
        ),
        _case(
            2,
            mod.CASE2_POLICY,
            1,
            1,
            alternatives=[{
                "course_id": "eja-candidate",
                "curricular_rank": 2,
                "curricular_classification": "LEVEL_MATCH_NO_SERIES_SCOPE",
                "automatically_injected_into_resolver": False,
            }],
        ),
        _case(3, mod.CASE3_POLICY, 2, 2),
    ]
    return _seal({
        "phase": mod.P0F782_PHASE,
        "status": "PASS",
        "source_p0f7_5_manifest_sha256": p0f75["manifest_sha256"],
        "summary": {
            "documented_cases": 3,
            "snapshot_drift_cases": 0,
            "automatic_course_mutations": 0,
            "automatic_workload_decisions": 0,
            "database_mutation": False,
        },
        "cases": cases,
        "database_mutation": False,
        "executor_authorized": False,
    })


def _validated():
    p75 = _p0f75()
    p782 = _p0f782(p75)
    return mod.validate_inputs(p75, p782), p75, p782


def _decisions(validated: dict) -> dict:
    contract = mod.decision_contract(validated)
    return {
        "phase": mod.PHASE_ID,
        "source_p0f7_8_2_manifest_sha256": validated["p0f7_8_2_sha"],
        "responsible": "Responsável Institucional",
        "authority_confirmed": True,
        "decisions": [
            {
                "case_number": 2,
                "decision": mod.DECISION_SELECT_ALTERNATIVE,
                "selected_course_id": contract["case_2"]["allowed_course_ids"][0],
                "justification": "Componente compatível com o nível EJA Final.",
            },
            {
                "case_number": 3,
                "decision": mod.DECISION_SELECT_TARGET,
                "selected_course_id": contract["case_3"]["target_course_id"],
                "justification": "Decisão institucional baseada no conjunto de evidências.",
            },
        ],
        "workload_decision_performed": False,
        "executor_authorized": False,
    }


def test_offline_ast_guard_passes_and_wrapper_is_local_only() -> None:
    mod.assert_offline_only()
    runner_source = SCRIPT.read_text(encoding="utf-8")
    wrapper_source = POWERSHELL.read_text(encoding="utf-8")
    assert "MongoClient(" not in runner_source
    assert "AsyncIOMotorClient" not in runner_source
    for token in ("ssh.exe", "scp.exe", "docker exec", "mongosh", "Invoke-WebRequest"):
        assert token not in wrapper_source
    assert "PRODUCTION_ACCESS=NO" in wrapper_source


def test_input_chain_and_three_policy_states_are_required() -> None:
    validated, _, _ = _validated()
    assert sorted(validated["cases782"]) == [1, 2, 3]
    assert validated["cases782"][1]["pair_policy"]["state"] == mod.CASE1_POLICY
    assert validated["cases782"][2]["pair_policy"]["state"] == mod.CASE2_POLICY
    assert validated["cases782"][3]["pair_policy"]["state"] == mod.CASE3_POLICY


def test_case1_is_locked_technical_source_outcome_without_executor() -> None:
    validated, _, _ = _validated()
    contract = mod.decision_contract(validated)
    assert contract["case_1"]["locked_outcome"] == "TECHNICAL_SOURCE_PREFERENCE"
    assert contract["case_1"]["selected_course_id"] == "source-1"
    assert contract["case_1"]["human_decision_required"] is False
    assert contract["executor_authorized"] is False
    assert contract["workload_decision_allowed"] is False


def test_case2_cannot_select_incompatible_source_or_target() -> None:
    validated, _, _ = _validated()
    decisions = _decisions(validated)
    decisions["decisions"][0]["decision"] = mod.DECISION_SELECT_SOURCE
    decisions["decisions"][0]["selected_course_id"] = "source-2"
    with pytest.raises(ValueError, match="CASE_2_DECISION_NOT_ALLOWED"):
        mod.validate_human_decisions(validated, decisions)


def test_case3_selection_must_match_declared_side() -> None:
    validated, _, _ = _validated()
    decisions = _decisions(validated)
    decisions["decisions"][1]["decision"] = mod.DECISION_SELECT_SOURCE
    decisions["decisions"][1]["selected_course_id"] = "target-3"
    with pytest.raises(ValueError, match="CASE_3_SELECTED_COURSE_MISMATCH"):
        mod.validate_human_decisions(validated, decisions)


def test_workload_decision_is_explicitly_forbidden() -> None:
    validated, _, _ = _validated()
    decisions = _decisions(validated)
    decisions["workload_decision_performed"] = True
    with pytest.raises(ValueError, match="WORKLOAD_DECISION_FORBIDDEN"):
        mod.validate_human_decisions(validated, decisions)


def test_sealed_manifest_has_no_database_or_executor_authorization() -> None:
    validated, _, _ = _validated()
    manifest = mod.seal_manifest(validated, _decisions(validated))
    assert manifest["status"] == "PASS"
    assert manifest["summary"]["technical_component_outcomes"] == 1
    assert manifest["summary"]["human_component_decisions"] == 2
    assert manifest["summary"]["workload_decisions"] == 0
    assert manifest["safety"]["database_access"] is False
    assert manifest["safety"]["database_mutation"] is False
    assert manifest["safety"]["executor_authorized"] is False
    assert manifest["safety"]["not_authorization_for_executor"] is True
    stored = manifest["manifest_sha256"]
    canonical = dict(manifest)
    canonical.pop("manifest_sha256")
    assert stored == mod._canonical_sha256(canonical)


def test_html_is_offline_and_has_only_cases_2_and_3_as_human_choices() -> None:
    validated, _, _ = _validated()
    page = mod.build_html(validated)
    assert "connect-src 'none'" in page
    assert "Caso 1" in page and "Não há adjudicação humana" in page
    assert 'id="decision-2"' in page
    assert 'id="decision-3"' in page
    assert 'id="decision-1"' not in page
    assert "2h × 3h" in page
    assert "executor_authorized:false" in page
