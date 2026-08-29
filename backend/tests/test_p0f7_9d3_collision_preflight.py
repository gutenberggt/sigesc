from backend.scripts.audit_p0f7_9d3_collision_preflight_offline import build_report
from backend.scripts.build_p0f7_9d3_collision_snapshot_js import build_js


def _d2():
    return {
        "phase": "P0F7.9D2-SAFE-TARGET-RESOLUTION-2026",
        "status": "PASS",
        "mantenedora_id": "tenant-1",
        "academic_year": 2026,
        "summary": {"unique_safe_target": 1, "proposal_only": True},
        "resolutions": [
            {
                "assignment_id": "a1",
                "school_id": "s1",
                "class_id": "c1",
                "class_name": "6º ANO A",
                "source_course_id": "wrong",
                "source_course_name": "Geografia",
                "source_course_level": "eja_final",
                "resolution": "UNIQUE_SAFE_TARGET",
                "validated_targets": [
                    {
                        "course_id": "safe",
                        "course_name": "Geografia",
                        "course_level": "fundamental_anos_finais",
                        "write_policy": "EXPLICIT_SERIES_FULL_MATCH",
                    }
                ],
            }
        ],
    }


def _snapshot(records):
    d2 = _d2()
    import hashlib, json

    raw = json.dumps(d2, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return {
        "phase": "P0F7.9D3-COLLISION-PREFLIGHT-SNAPSHOT-2026",
        "mode": "READ_ONLY_BOUNDED_TARGET_COLLISION_PREFLIGHT",
        "mantenedora_id": "tenant-1",
        "academic_year": 2026,
        "source_p0f7_9d2_report_sha256": hashlib.sha256(raw).hexdigest(),
        "query_budget": 2,
        "query_calls": 2,
        "source_proposals": 1,
        "counts": {"matching_assignments": len(records)},
        "teacher_assignments": records,
    }


def _source():
    return {
        "id": "a1",
        "staff_id": "p1",
        "school_id": "s1",
        "class_id": "c1",
        "course_id": "wrong",
        "academic_year": 2026,
        "status": "ativo",
        "mantenedora_id": "tenant-1",
    }


def test_builder_is_bounded_and_structural_only():
    js = build_js(_d2(), "sigesc")
    assert "countDocuments" in js
    assert "MAX_MATCHING_ASSIGNMENTS = 200" in js
    assert "staff_id:1" in js
    assert "full_name" not in js
    assert "nome:1" not in js
    assert "updateOne" not in js
    assert "updateMany" not in js
    assert "deleteOne" not in js


def test_clear_when_no_active_target_collision():
    report = build_report(_d2(), _snapshot([_source()]))
    assert report["summary"]["clear_for_remediation_planning"] == 1
    assert report["results"][0]["preflight"] == "CLEAR_FOR_REMEDIATION_PLANNING"


def test_active_target_collision_blocks_planning():
    collision = {
        "id": "a2",
        "staff_id": "p1",
        "school_id": "s1",
        "class_id": "c1",
        "course_id": "safe",
        "academic_year": 2026,
        "status": "ativo",
        "mantenedora_id": "tenant-1",
    }
    report = build_report(_d2(), _snapshot([_source(), collision]))
    assert report["summary"]["active_target_already_exists"] == 1
    assert report["results"][0]["preflight"] == "ACTIVE_TARGET_ALREADY_EXISTS"
    assert report["results"][0]["active_collision_assignment_ids"] == ["a2"]


def test_inactive_target_does_not_block_but_is_recorded():
    collision = {
        "id": "a2",
        "staff_id": "p1",
        "school_id": "s1",
        "class_id": "c1",
        "course_id": "safe",
        "academic_year": 2026,
        "status": "inativo",
        "mantenedora_id": "tenant-1",
    }
    report = build_report(_d2(), _snapshot([_source(), collision]))
    assert report["results"][0]["preflight"] == "CLEAR_FOR_REMEDIATION_PLANNING"
    assert report["results"][0]["inactive_collision_assignment_ids"] == ["a2"]


def test_source_course_drift_requires_review():
    source = _source()
    source["course_id"] = "changed"
    report = build_report(_d2(), _snapshot([source]))
    assert report["summary"]["source_drift_review_required"] == 1
    assert "SOURCE_COURSE_ID_DRIFT" in report["results"][0]["reasons"]
