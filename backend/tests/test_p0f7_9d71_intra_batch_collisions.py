from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.analyze_p0f7_9d71_intra_batch_collisions import analyze  # noqa: E402


def _sha(payload):
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _fixtures(*, collide: bool):
    tenant = "tenant-1"
    year = 2026
    entries = []
    assignments = []

    for index in range(1, 24):
        assignment_id = f"a-{index:02d}"
        school_id = "school-1"
        class_id = f"class-{index:02d}"
        source_id = f"source-{index:02d}"
        target_id = f"target-{index:02d}"
        staff_id = f"staff-{index:02d}"

        if collide and index in (21, 22):
            class_id = "class-collision"
            target_id = "target-collision"
            staff_id = "staff-collision"

        entries.append(
            {
                "ordinal": index,
                "assignment_id": assignment_id,
                "school_id": school_id,
                "class_id": class_id,
                "class_name": f"Class {index}",
                "academic_year": year,
                "source": {
                    "course_id": source_id,
                    "course_name": "Geografia" if index in (21, 22) else f"Source {index}",
                    "course_level": "fundamental_anos_finais",
                },
                "target": {
                    "course_id": target_id,
                    "course_name": "Geografia" if index in (21, 22) else f"Target {index}",
                    "course_level": "eja_final",
                    "write_policy": "LEVEL_MATCH_NO_SERIES_SCOPE",
                },
            }
        )
        assignments.append(
            {
                "id": assignment_id,
                "staff_id": staff_id,
                "school_id": school_id,
                "class_id": class_id,
                "course_id": source_id,
                "academic_year": year,
                "status": "ativo",
                "mantenedora_id": tenant,
            }
        )

    plan = {
        "phase": "P0F7.9D4-SEALED-REMEDIATION-PLAN-2026",
        "status": "PASS",
        "mode": "SEALED_PROPOSAL_ONLY_NON_EXECUTABLE",
        "mantenedora_id": tenant,
        "academic_year": year,
        "execution_contract": {"executable": False},
        "entries": entries,
    }
    plan["plan_sha256"] = _sha(plan)

    snapshot = {
        "phase": "P0F7.9D5-LAST-MILE-PREFLIGHT-SNAPSHOT-2026",
        "mode": "READ_ONLY_BOUNDED_LAST_MILE_EXECUTION_PREFLIGHT",
        "mantenedora_id": tenant,
        "academic_year": year,
        "sealed_plan_sha256": plan["plan_sha256"],
        "source_entries": 23,
        "teacher_assignments": assignments,
    }
    return plan, snapshot


def test_clean_batch_opens_gate():
    plan, snapshot = _fixtures(collide=False)
    report = analyze(plan, snapshot)
    assert report["status"] == "PASS"
    assert report["summary"]["safe_noncolliding"] == 23
    assert report["summary"]["blocked_intra_batch"] == 0
    assert report["summary"]["collision_groups"] == 0
    assert report["summary"]["execution_gate_open"] is True


def test_collision_pair_closes_gate_and_partitions_21_plus_2():
    plan, snapshot = _fixtures(collide=True)
    report = analyze(plan, snapshot)
    assert report["status"] == "PASS"
    assert report["summary"]["safe_noncolliding"] == 21
    assert report["summary"]["blocked_intra_batch"] == 2
    assert report["summary"]["collision_groups"] == 1
    assert report["summary"]["execution_gate_open"] is False
    group = report["collision_groups"][0]
    assert group["ordinals"] == [21, 22]
    assert group["assignment_ids"] == ["a-21", "a-22"]
    assert group["required_resolution"] == "HUMAN_ADJUDICATION_BEFORE_ANY_REVISED_WRITE_PLAN"
    assert [row["ordinal"] for row in report["safe_entries"]][-1] == 23


def test_report_does_not_expose_staff_identifier():
    plan, snapshot = _fixtures(collide=True)
    report = analyze(plan, snapshot)
    serialized = json.dumps(report, ensure_ascii=False)
    assert "staff-collision" not in serialized
    assert report["safety"]["staff_ids_exposed_in_report"] is False
