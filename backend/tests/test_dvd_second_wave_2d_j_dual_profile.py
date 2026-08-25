import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import prepare_dvd_second_wave_2d_j as base
from scripts import prepare_dvd_second_wave_2d_j_dual_profile_persistent as subject


def _dvd(
    row_id: str,
    *,
    component_id: str,
    profile: str = "regular",
    scope: str = "all",
    teacher_id: str = "teacher",
    class_id: str = "class",
):
    return {
        "id": row_id,
        "teacher_id": teacher_id,
        "class_id": class_id,
        "component_id": component_id,
        "valid_from": "2026-08-18",
        "valid_until": None,
        "is_substitute": False,
        "deleted": False,
        "diary_settings": {
            "enabled": True,
            "schema_version": 1,
            "profile": profile,
            "student_scope": scope,
        },
    }


def test_dual_source_profile_accepts_one_same_component_plus_two_siblings():
    component = base.APPROVED_TARGETS["1f08bfe3-b486-4266-81bc-2f03fe72a3a4"]["component_id"]
    peers = [_dvd("peer-1", component_id=component, profile="regular")]
    siblings = [
        _dvd("sib-1", component_id="other-1", profile="regular"),
        _dvd("sib-2", component_id="other-2", profile="regular"),
    ]

    evidence = subject.resolve_dual_source_profile(component, peers, siblings)
    assert evidence["profile"] == "regular"
    assert evidence["student_scope"] == "all"
    assert evidence["peer_count"] == 1
    assert evidence["sibling_count"] == 2
    assert evidence["evidence_model"] == subject.DUAL_PROFILE_EVIDENCE


def test_dual_source_profile_rejects_single_source_only():
    component = base.APPROVED_TARGETS["1f08bfe3-b486-4266-81bc-2f03fe72a3a4"]["component_id"]
    peers = [_dvd("peer-1", component_id=component)]

    with pytest.raises(subject.DualProfilePreflightError, match="TEACHER_CLASS_SIBLING_EVIDENCE_INSUFFICIENT"):
        subject.resolve_dual_source_profile(component, peers, [])

    with pytest.raises(subject.DualProfilePreflightError, match="SAME_COMPONENT_EVIDENCE_INSUFFICIENT"):
        subject.resolve_dual_source_profile(
            component,
            [],
            [
                _dvd("sib-1", component_id="other-1"),
                _dvd("sib-2", component_id="other-2"),
            ],
        )


def test_dual_source_profile_disagreement_is_fail_closed():
    component = base.APPROVED_TARGETS["7d62a0df-c601-4288-b4ef-18093d3c37cf"]["component_id"]
    peers = [_dvd("peer-1", component_id=component, profile="regular")]
    siblings = [
        _dvd("sib-1", component_id="other-1", profile="integrator"),
        _dvd("sib-2", component_id="other-2", profile="integrator"),
    ]

    with pytest.raises(subject.DualProfilePreflightError, match="DUAL_PROFILE_DISAGREEMENT"):
        subject.resolve_dual_source_profile(component, peers, siblings)


def test_each_source_must_be_unanimous_and_scope_all():
    component = base.APPROVED_TARGETS["7d62a0df-c601-4288-b4ef-18093d3c37cf"]["component_id"]

    with pytest.raises(subject.DualProfilePreflightError, match="SAME_COMPONENT_STUDENT_SCOPE_AMBIGUOUS"):
        subject.resolve_dual_source_profile(
            component,
            [_dvd("peer-1", component_id=component, scope="group")],
            [
                _dvd("sib-1", component_id="other-1"),
                _dvd("sib-2", component_id="other-2"),
            ],
        )

    with pytest.raises(subject.DualProfilePreflightError, match="TEACHER_CLASS_SIBLING_PROFILE_AMBIGUOUS"):
        subject.resolve_dual_source_profile(
            component,
            [_dvd("peer-1", component_id=component)],
            [
                _dvd("sib-1", component_id="other-1", profile="regular"),
                _dvd("sib-2", component_id="other-2", profile="integrator"),
            ],
        )


def test_manifest_provenance_records_both_profile_sources():
    legacy_id = "1f08bfe3-b486-4266-81bc-2f03fe72a3a4"
    validated = {
        "manifest": [
            {
                "id": "proposed",
                "cutover_provenance": {
                    "source_legacy_assignment_id": legacy_id,
                    "evidence": "old",
                    "peer_profile_count": 1,
                },
            }
        ],
        "peer_evidence": {
            legacy_id: {
                "profile": "regular",
                "peer_count": 1,
                "sibling_count": 7,
            }
        },
        "manifest_sha256": "old",
    }

    subject._enrich_manifest_profile_provenance(validated)
    provenance = validated["manifest"][0]["cutover_provenance"]
    assert provenance["evidence"] == subject.REQUIRED_EVIDENCE
    assert provenance["profile_evidence"] == subject.DUAL_PROFILE_EVIDENCE
    assert provenance["same_component_peer_count"] == 1
    assert provenance["sibling_profile_count"] == 7
    assert validated["manifest_sha256"] != "old"


def test_script_is_read_only_and_direct_entrypoint_imports_without_pythonpath():
    subject.assert_script_read_only()
    script = Path("scripts/prepare_dvd_second_wave_2d_j_dual_profile_persistent.py")
    source = script.read_text(encoding="utf-8")
    assert "--apply" not in source
    assert "--rollback" not in source

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "ModuleNotFoundError" not in proc.stderr
    assert "--backup-dir" in proc.stdout
