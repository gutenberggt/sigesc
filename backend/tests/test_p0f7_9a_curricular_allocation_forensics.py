from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = ROOT / "backend" / "scripts" / "build_p0f7_9a_curricular_allocation_snapshot_js.py"
ANALYZER_PATH = ROOT / "backend" / "scripts" / "audit_p0f7_9a_curricular_allocation_offline.py"
WRAPPER_PATH = ROOT / "scripts" / "p0f7_9a_investigate_local.ps1"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


builder = _load_module("p0f79a_builder", BUILDER_PATH)
analyzer = _load_module("p0f79a_analyzer", ANALYZER_PATH)


def _seal(payload: dict) -> dict:
    payload = dict(payload)
    payload["manifest_sha256"] = builder._canonical_sha256(payload)
    return payload


def _p0f75() -> dict:
    return _seal({
        "phase": builder.P0F75_PHASE,
        "status": "PASS",
        "group_name": "Geografia",
        "cases": [
            {
                "case_number": 1,
                "class": {"class_id": "class-1", "academic_year": 2026},
                "school": {"school_id": "school-1"},
            },
            {
                "case_number": 2,
                "class": {"class_id": "class-eja", "academic_year": 2026},
                "school": {"school_id": "school-bom-jesus"},
            },
            {
                "case_number": 3,
                "class": {"class_id": "class-3", "academic_year": 2026},
                "school": {"school_id": "school-1"},
            },
        ],
    })


def _snapshot(series: dict) -> dict:
    sha = series["manifest_sha256"]
    return {
        "phase": builder.SNAPSHOT_PHASE,
        "mode": builder.SNAPSHOT_MODE,
        "source_p0f7_5_manifest_sha256": sha,
        "query_budget": 8,
        "query_calls": 8,
        "class": {
            "id": "class-eja",
            "name": "MULTI 3º E 4º ETAPA",
            "school_id": "school-bom-jesus",
            "academic_year": 2026,
            "mantenedora_id": "tenant-1",
            "nivel_ensino": "eja_final",
            "series": ["EJA 3ª ETAPA", "EJA 4ª ETAPA"],
            "course_ids": ["course-lp"],
        },
        "teacher_assignments": [
            {
                "id": "ta-v-bad",
                "staff_id": "staff-v",
                "school_id": "school-bom-jesus",
                "class_id": "class-eja",
                "course_id": "course-ei",
                "academic_year": 2026,
                "status": "ativo",
                "created_at": "2026-02-01T10:00:00Z",
                "mantenedora_id": "tenant-1",
            },
            {
                "id": "ta-v-good",
                "staff_id": "staff-v",
                "school_id": "school-bom-jesus",
                "class_id": "class-eja",
                "course_id": "course-lp",
                "academic_year": 2026,
                "status": "ativo",
                "created_at": "2026-02-01T10:01:00Z",
                "mantenedora_id": "tenant-1",
            },
            {
                "id": "ta-w-bad",
                "staff_id": "staff-w",
                "school_id": "school-bom-jesus",
                "class_id": "class-eja",
                "course_id": "course-ei-2",
                "academic_year": 2026,
                "status": "ativo",
                "created_at": "2026-02-01T10:02:00Z",
                "mantenedora_id": "tenant-1",
            },
        ],
        "courses": [
            {
                "id": "course-ei",
                "name": "O Eu, O Outro e Nós",
                "nivel_ensino": "educacao_infantil",
                "grade_levels": ["Pré I", "Pré II"],
                "mantenedora_id": "tenant-1",
            },
            {
                "id": "course-ei-2",
                "name": "Corpo, Gestos e Movimentos",
                "nivel_ensino": "educacao_infantil",
                "grade_levels": ["Pré I", "Pré II"],
                "mantenedora_id": "tenant-1",
            },
            {
                "id": "course-lp",
                "name": "Língua Portuguesa",
                "nivel_ensino": "eja_final",
                "grade_levels": ["EJA 3ª ETAPA", "EJA 4ª ETAPA"],
                "mantenedora_id": "tenant-1",
            },
        ],
        "staff": [
            {"id": "staff-v", "nome": "Vanúbia Teste", "user_id": "user-v", "mantenedora_id": "tenant-1"},
            {"id": "staff-w", "nome": "Weslane Teste", "user_id": "user-w", "mantenedora_id": "tenant-1"},
        ],
        "teacher_allocations": [
            {"id": "alloc-v", "staff_id": "staff-v", "class_id": "class-eja", "course_id": "course-ei"},
        ],
        "teacher_class_assignments": [
            {"id": "dvd-v", "teacher_id": "user-v", "class_id": "class-eja", "component_id": "course-ei"},
        ],
        "class_schedules": [
            {"id": "sched-1", "class_id": "class-eja", "schedule_slots": [{"course_id": "course-ei"}]},
        ],
        "assignment_audit_logs": [
            {"action": "create", "collection": "teacher_assignments", "document_id": "ta-v-bad"},
        ],
    }


def test_builder_is_bounded_read_only_and_avoids_sensitive_collections() -> None:
    js = builder.build_js(_p0f75(), "sigesc")
    assert "QUERY_BUDGET = 8" in js
    assert "P0F79A_SNAPSHOT_JSON=" in js
    assert js.count("result.query_calls += 1") == 8
    for token in (
        ".insertOne(", ".insertMany(", ".updateOne(", ".updateMany(",
        ".deleteOne(", ".deleteMany(", ".replaceOne(", ".bulkWrite(",
    ):
        assert token not in js
    for collection in ("students", "enrollments", "grades", "attendance"):
        assert f"targetDb.{collection}" not in js


def test_analyzer_detects_ei_to_eja_mismatches_and_cross_source_evidence() -> None:
    series = _p0f75()
    report = analyzer.build_report(series, _snapshot(series))
    assert report["status"] == "PASS"
    assert report["investigation_state"] == "FINDINGS_PRESENT"
    assert report["summary"]["active_assignments"] == 3
    assert report["summary"]["active_level_mismatch"] == 2
    assert report["summary"]["active_educacao_infantil_to_eja_final"] == 2
    assert report["summary"]["affected_staff_count"] == 2
    assert report["summary"]["student_records_read"] == 0
    assert report["summary"]["database_mutation"] is False

    by_id = {row["assignment_id"]: row for row in report["all_assignments"]}
    assert by_id["ta-v-bad"]["curricular_classification"] == "LEVEL_MISMATCH"
    assert by_id["ta-v-bad"]["same_binding_in_teacher_allocations"] is True
    assert by_id["ta-v-bad"]["same_binding_in_dvd"] is True
    assert by_id["ta-v-bad"]["course_present_in_class_schedule"] is True
    assert by_id["ta-v-bad"]["assignment_create_audit_event_count"] == 1
    assert by_id["ta-v-good"]["curricular_bucket"] == "COMPATIBLE"


def test_analyzer_fails_closed_on_chain_or_tenant_drift() -> None:
    series = _p0f75()
    snap = _snapshot(series)
    snap["source_p0f7_5_manifest_sha256"] = "wrong"
    try:
        analyzer.build_report(series, snap)
    except ValueError as exc:
        assert "SOURCE_CHAIN_MISMATCH" in str(exc)
    else:
        raise AssertionError("chain drift must fail closed")

    snap = _snapshot(series)
    snap["teacher_assignments"][0]["mantenedora_id"] = "tenant-other"
    try:
        analyzer.build_report(series, snap)
    except ValueError as exc:
        assert "ASSIGNMENT_TENANT_DRIFT" in str(exc)
    else:
        raise AssertionError("tenant drift must fail closed")


def test_offline_analyzer_and_wrapper_have_no_remote_surface() -> None:
    analyzer_source = ANALYZER_PATH.read_text(encoding="utf-8")
    for token in ("motor", "pymongo", "requests", "httpx", "subprocess", "MongoClient"):
        assert token not in analyzer_source

    wrapper = WRAPPER_PATH.read_text(encoding="utf-8")
    for token in ("ssh ", "scp ", "docker exec", "mongosh", "Invoke-WebRequest"):
        assert token not in wrapper
    assert "PRODUCTION_ACCESS=NO" in wrapper
    assert "DATABASE_MUTATION=NO" in wrapper
    assert "STUDENT_DATA_ACCESS=NO" in wrapper
