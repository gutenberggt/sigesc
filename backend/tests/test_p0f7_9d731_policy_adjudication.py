from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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


def test_current_multieja_case_resolves_to_80_annual_10_monthly_2_weekly(monkeypatch):
    monkeypatch.setattr(mod.d73, "validate_inputs", lambda *args: validated())
    _, policy = mod.validate_policy_inputs({}, {}, {})
    assert policy["multigrade"] is True
    assert policy["multigrade_rule"] == "MAX_ANNUAL_WORKLOAD"
    assert policy["canonical_annual_workload"] == 80
    assert policy["canonical_monthly_workload"] == 10
    assert policy["canonical_weekly_workload"] == 2


def test_template_removes_human_workload_choice_and_records_formula(monkeypatch):
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
    assert "80h anuais / 8 = 10h mensais" in template["workload"]["justification"]
    assert template["workload_resolution"]["human_choice_required"] is False
    assert template["workload_resolution"]["canonical_monthly_workload"] == 10
    assert template["workload_resolution"]["conversion_formula"]["annual_to_monthly"] == "ha / 8 = hm"


def test_html_explains_ha_hm_hs_conversion(monkeypatch):
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
    html = mod.build_html(v, policy)
    assert "CH anual canônica (ha)" in html
    assert "CH mensal canônica (hm)" in html
    assert "CH semanal canônica (hs)" in html
    assert "80 / 8 = 10 hm; 10 / 5 = 2 hs" in html
    assert "80 / 40 = 2 hs" in html


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
    policy = report["curricular_workload_policy"]
    assert policy["canonical_annual_workload"] == 80
    assert policy["canonical_monthly_workload"] == 10
    assert policy["canonical_weekly_workload"] == 2
    assert policy["conversion_formula"]["monthly_to_weekly"] == "hm / 5 = hs"
    assert policy["human_workload_choice_required"] is False
    assert report["summary"]["workload_resolution_source"] == "CURRICULAR_POLICY"
    assert report["report_sha256"] != "old"
