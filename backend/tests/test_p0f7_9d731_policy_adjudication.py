from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "adjudicate_p0f7_9d731_curricular_policy.py"
spec = importlib.util.spec_from_file_location("p0f7_9d731", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def validated():
    return {
        "d72_sha256": "abc",
        "class": {
            "class_level": "eja_final",
            "series": ["EJA 3ª ETAPA", "EJA 4ª ETAPA"],
        },
        "shared_target": {"course_name": "Geografia", "course_id": "geo-eja-final"},
        "workload_options": [2, 3],
        "pair_rows": [
            {"ordinal": 21, "assignment_id": "a1", "weekly_workload": 2, "source_course_name": "Geografia", "status": "ativo"},
            {"ordinal": 22, "assignment_id": "a2", "weekly_workload": 3, "source_course_name": "Geografia", "status": "ativo"},
        ],
    }


def test_offline_guard_passes():
    mod.assert_offline_only()


def test_current_multieja_case_resolves_to_80_annual_and_2_weekly(monkeypatch):
    monkeypatch.setattr(mod.d73, "validate_inputs", lambda *args: validated())
    _, policy = mod.validate_policy_inputs({}, {}, {})
    assert policy["multigrade"] is True
    assert policy["multigrade_rule"] == "MAX_ANNUAL_WORKLOAD"
    assert policy["canonical_annual_workload"] == 80
    assert policy["canonical_weekly_workload"] == 2


def test_template_removes_human_workload_choice(monkeypatch):
    v = validated()
    monkeypatch.setattr(mod.d73, "validate_inputs", lambda *args: v)
    monkeypatch.setattr(mod.d73, "build_decision_template", lambda value: {
        "phase": "decision",
        "survivor": {"decision": mod.d73.SURVIVOR_DEFER, "assignment_id": None, "justification": ""},
        "workload": {"decision": mod.d73.WORKLOAD_DEFER, "value": None, "justification": ""},
        "production_write_authorized": False,
        "executor_authorized": False,
    })
    _, policy = mod.validate_policy_inputs({}, {}, {})
    template = mod.build_decision_template(v, policy)
    assert template["workload"]["decision"] == mod.d73.WORKLOAD_SELECT
    assert template["workload"]["value"] == 2
    assert template["workload_resolution"]["human_choice_required"] is False


def test_tampered_workload_is_rejected_before_base_seal(monkeypatch):
    monkeypatch.setattr(mod.d73, "validate_inputs", lambda *args: validated())
    decision = {"workload": {"decision": mod.d73.WORKLOAD_SELECT, "value": 3}}
    with pytest.raises(ValueError, match="WORKLOAD_POLICY_TAMPERED"):
        mod.seal({}, {}, {}, decision)


def test_policy_metadata_is_added_to_base_seal(monkeypatch):
    monkeypatch.setattr(mod.d73, "validate_inputs", lambda *args: validated())
    monkeypatch.setattr(mod.d73, "seal", lambda *args: {
        "phase": "base",
        "summary": {"revised_plan_ready": True},
        "report_sha256": "old",
    })
    decision = {"workload": {"decision": mod.d73.WORKLOAD_SELECT, "value": 2}}
    report = mod.seal({}, {}, {}, decision)
    assert report["curricular_workload_policy"]["canonical_annual_workload"] == 80
    assert report["curricular_workload_policy"]["canonical_weekly_workload"] == 2
    assert report["curricular_workload_policy"]["human_workload_choice_required"] is False
    assert report["summary"]["workload_resolution_source"] == "CURRICULAR_POLICY"
    assert report["report_sha256"] != "old"
