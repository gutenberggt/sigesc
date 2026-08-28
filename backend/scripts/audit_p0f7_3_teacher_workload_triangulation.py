"""P0-F7.3 — triangulação READ-ONLY da divergência de carga docente.

Consome o relatório privado P0-F7.2 e cruza os três casos de Geografia com
fontes canônicas/operacionais já existentes: teacher_assignments ao vivo,
matriz explícita da turma (class.course_ids), class_schedules, courses,
grades e attendance. A etapa NÃO converte carga anual em carga semanal,
NÃO escolhe 2h ou 3h e NÃO altera o banco.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

PHASE_ID = "P0F7.3-TEACHER-WORKLOAD-TRIANGULATION-READ-ONLY-2026"
P0F72_PHASE = "P0F7.2-TEACHER-ASSIGNMENT-FORENSIC-READ-ONLY-2026"
MANIFEST_VERSION = 1

MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
)


def assert_read_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    executable = "\n".join(
        line for line in source.splitlines()
        if "MUTATOR_TOKENS" not in line and not line.lstrip().startswith('"')
    )
    forbidden = [token for token in MUTATOR_TOKENS if token in executable]
    if forbidden:
        raise RuntimeError(f"READ_ONLY_GUARD_FAILED forbidden={forbidden}")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _canonical_sha256(payload: Any) -> str:
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return payload


def _private_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(rendered)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    os.chmod(path, 0o600)


def _verify_embedded_sha(payload: Mapping[str, Any], field: str, label: str) -> str:
    stored = _norm(payload.get(field))
    if not stored:
        raise ValueError(f"{label}_SHA_MISSING")
    canonical = dict(payload)
    canonical.pop(field, None)
    actual = _canonical_sha256(canonical)
    if actual != stored:
        raise ValueError(f"{label}_SHA_MISMATCH")
    return stored


def validate_p0f72(report: Mapping[str, Any]) -> dict[str, Any]:
    sha = _verify_embedded_sha(report, "manifest_sha256", "P0F7_2")
    if report.get("phase") != P0F72_PHASE:
        raise ValueError("P0F7_2_PHASE_MISMATCH")
    if report.get("mode") != "READ_ONLY_TEACHER_ASSIGNMENT_FORENSIC":
        raise ValueError("P0F7_2_MODE_MISMATCH")
    if report.get("status") != "PASS":
        raise ValueError("P0F7_2_STATUS_NOT_PASS")
    if report.get("group_name") != "Geografia":
        raise ValueError("P0F7_2_GROUP_MISMATCH")

    summary = report.get("summary") or {}
    safety = report.get("safety") or {}
    cases = report.get("cases") or []

    if summary.get("documented_cases") != 3 or len(cases) != 3:
        raise ValueError("P0F7_2_CASE_COUNT_MISMATCH")
    if summary.get("complete_blocker_coverage") is not True:
        raise ValueError("P0F7_2_COVERAGE_INCOMPLETE")
    if safety.get("read_only") is not True:
        raise ValueError("P0F7_2_NOT_READ_ONLY")
    if safety.get("production_writes_executed") is not False:
        raise ValueError("P0F7_2_WRITES_FLAG_INVALID")
    if safety.get("contains_student_data") is not False:
        raise ValueError("P0F7_2_STUDENT_DATA_FLAG_INVALID")
    if safety.get("not_authorization_for_executor") is not True:
        raise ValueError("P0F7_2_EXECUTOR_FLAG_INVALID")

    source_course_id = _norm(report.get("source_course_id"))
    target_course_id = _norm(report.get("target_course_id"))
    if not source_course_id or not target_course_id:
        raise ValueError("P0F7_2_COURSE_PAIR_MISSING")

    seen_numbers: set[int] = set()
    for case in cases:
        number = int(case.get("case_number") or 0)
        if number <= 0 or number in seen_numbers:
            raise ValueError("P0F7_2_CASE_NUMBER_INVALID")
        seen_numbers.add(number)
        if case.get("classification") != "DIVERGENT_ACTIVE_ASSIGNMENT_REQUIRES_REVIEW":
            raise ValueError("P0F7_2_CASE_CLASSIFICATION_INVALID")
        if list(case.get("divergent_fields") or []) != ["carga_horaria_semanal"]:
            raise ValueError("P0F7_2_UNEXPECTED_DIVERGENT_FIELDS")
        for side in ("source_assignment", "target_assignment"):
            assignment = case.get(side) or {}
            if not _norm(assignment.get("id")):
                raise ValueError(f"P0F7_2_{side.upper()}_ID_MISSING")
            if assignment.get("carga_horaria_semanal") is None:
                raise ValueError(f"P0F7_2_{side.upper()}_WORKLOAD_MISSING")

    return {
        "manifest_sha256": sha,
        "source_course_id": source_course_id,
        "target_course_id": target_course_id,
        "cases": cases,
    }


def _signal(source: int | bool, target: int | bool) -> str:
    s = int(source or 0)
    t = int(target or 0)
    if s > 0 and t == 0:
        return "SOURCE_ONLY"
    if t > 0 and s == 0:
        return "TARGET_ONLY"
    if s > 0 and t > 0:
        return "BOTH"
    return "NONE"


def classify_identity_evidence(signals: Mapping[str, str]) -> dict[str, Any]:
    source_only = sorted(k for k, v in signals.items() if v == "SOURCE_ONLY")
    target_only = sorted(k for k, v in signals.items() if v == "TARGET_ONLY")
    both = sorted(k for k, v in signals.items() if v == "BOTH")
    none = sorted(k for k, v in signals.items() if v == "NONE")

    if source_only and target_only:
        classification = "MIXED_IDENTITY_EVIDENCE_REQUIRES_REVIEW"
    elif len(source_only) >= 2 and not target_only:
        classification = "IDENTITY_EVIDENCE_LEANS_SOURCE"
    elif len(target_only) >= 2 and not source_only:
        classification = "IDENTITY_EVIDENCE_LEANS_TARGET"
    elif source_only and not target_only:
        classification = "LIMITED_IDENTITY_EVIDENCE_SOURCE"
    elif target_only and not source_only:
        classification = "LIMITED_IDENTITY_EVIDENCE_TARGET"
    elif both:
        classification = "SHARED_IDENTITY_EVIDENCE_REQUIRES_REVIEW"
    else:
        classification = "NO_EXTERNAL_IDENTITY_EVIDENCE"

    return {
        "classification": classification,
        "source_only_signals": source_only,
        "target_only_signals": target_only,
        "both_signals": both,
        "none_signals": none,
        "automatic_workload_decision": False,
        "workload_resolution": "REQUIRES_SEPARATE_DECISION_OR_STRONGER_CANONICAL_EVIDENCE",
    }


async def _count_attendance_records(db: Any, query: Mapping[str, Any]) -> tuple[int, int]:
    docs = await db.attendance.find(dict(query), {"_id": 0, "records": 1}).to_list(10000)
    return len(docs), sum(len(row.get("records") or []) for row in docs)


async def _fetch_live_assignment(db: Any, assignment_id: str, tenant_id: str) -> dict[str, Any]:
    doc = await db.teacher_assignments.find_one(
        {"id": assignment_id, "mantenedora_id": tenant_id},
        {
            "_id": 0, "id": 1, "staff_id": 1, "class_id": 1, "course_id": 1,
            "academic_year": 1, "school_id": 1, "status": 1,
            "carga_horaria_semanal": 1, "is_substituicao": 1,
            "updated_at": 1,
        },
    )
    return doc or {}


async def collect_report(db: Any, *, p0f72_path: Path) -> dict[str, Any]:
    assert_read_only()
    p0f72 = _load_json(p0f72_path)
    validated = validate_p0f72(p0f72)
    source_course_id = validated["source_course_id"]
    target_course_id = validated["target_course_id"]
    pair_ids = [source_course_id, target_course_id]

    results: list[dict[str, Any]] = []
    drift_count = 0
    identity_classifications: Counter[str] = Counter()

    for raw_case in sorted(validated["cases"], key=lambda row: int(row.get("case_number") or 0)):
        number = int(raw_case["case_number"])
        class_id = _norm((raw_case.get("class") or {}).get("class_id"))
        staff_id = _norm((raw_case.get("teacher") or {}).get("staff_id"))
        school_id = _norm((raw_case.get("school") or {}).get("school_id"))
        year = int((raw_case.get("class") or {}).get("academic_year") or p0f72.get("academic_year") or 0)
        if not class_id or not staff_id or not school_id or year <= 0:
            raise ValueError(f"CASE_{number}_NATURAL_KEY_INCOMPLETE")

        class_doc = await db.classes.find_one(
            {"id": class_id},
            {
                "_id": 0, "id": 1, "name": 1, "school_id": 1, "academic_year": 1,
                "mantenedora_id": 1, "course_ids": 1, "nivel_ensino": 1,
                "education_level": 1, "grade_level": 1,
            },
        ) or {}
        tenant_id = _norm(class_doc.get("mantenedora_id"))
        if not tenant_id:
            raise RuntimeError(f"CASE_{number}_TENANT_MISSING_FAIL_CLOSED")
        if _norm(class_doc.get("school_id")) != school_id:
            raise RuntimeError(f"CASE_{number}_SCHOOL_DRIFT")

        source_expected = raw_case.get("source_assignment") or {}
        target_expected = raw_case.get("target_assignment") or {}
        source_live = await _fetch_live_assignment(db, _norm(source_expected.get("id")), tenant_id)
        target_live = await _fetch_live_assignment(db, _norm(target_expected.get("id")), tenant_id)
        if not source_live or not target_live:
            raise RuntimeError(f"CASE_{number}_ASSIGNMENT_MISSING")

        drift_fields: list[str] = []
        expected_by_side = {"source": source_expected, "target": target_expected}
        live_by_side = {"source": source_live, "target": target_live}
        for side in ("source", "target"):
            expected = expected_by_side[side]
            live = live_by_side[side]
            expected_course = source_course_id if side == "source" else target_course_id
            checks = {
                "id": (_norm(expected.get("id")), _norm(live.get("id"))),
                "course_id": (expected_course, _norm(live.get("course_id"))),
                "staff_id": (staff_id, _norm(live.get("staff_id"))),
                "class_id": (class_id, _norm(live.get("class_id"))),
                "school_id": (school_id, _norm(live.get("school_id"))),
                "academic_year": (year, int(live.get("academic_year") or 0)),
                "status": (_norm(expected.get("status")).casefold(), _norm(live.get("status")).casefold()),
                "carga_horaria_semanal": (
                    expected.get("carga_horaria_semanal"),
                    live.get("carga_horaria_semanal"),
                ),
            }
            for field, (expected_value, live_value) in checks.items():
                if expected_value != live_value:
                    drift_fields.append(f"{side}.{field}")
        if drift_fields:
            drift_count += 1
            raise RuntimeError(f"CASE_{number}_SNAPSHOT_DRIFT:{','.join(sorted(drift_fields))}")

        courses = await db.courses.find(
            {"id": {"$in": pair_ids}, "mantenedora_id": tenant_id},
            {
                "_id": 0, "id": 1, "name": 1, "nivel_ensino": 1, "active": 1,
                "workload": 1, "carga_horaria_por_serie": 1, "created_at": 1,
                "mantenedora_id": 1,
            },
        ).to_list(10)
        course_map = {_norm(row.get("id")): row for row in courses}
        if source_course_id not in course_map or target_course_id not in course_map:
            raise RuntimeError(f"CASE_{number}_COURSE_PAIR_NOT_TENANT_SCOPED")

        matrix_ids = {_norm(value) for value in (class_doc.get("course_ids") or []) if _norm(value)}
        matrix_source = source_course_id in matrix_ids
        matrix_target = target_course_id in matrix_ids

        schedules = await db.class_schedules.find(
            {
                "class_id": class_id,
                "academic_year": year,
                "mantenedora_id": tenant_id,
            },
            {"_id": 0, "id": 1, "schedule_slots": 1},
        ).to_list(20)
        source_slots = 0
        target_slots = 0
        for schedule in schedules:
            for slot in schedule.get("schedule_slots") or []:
                cid = _norm(slot.get("course_id"))
                if cid == source_course_id:
                    source_slots += 1
                elif cid == target_course_id:
                    target_slots += 1

        grades_source = await db.grades.count_documents({
            "class_id": class_id, "academic_year": year,
            "course_id": source_course_id, "mantenedora_id": tenant_id,
        })
        grades_target = await db.grades.count_documents({
            "class_id": class_id, "academic_year": year,
            "course_id": target_course_id, "mantenedora_id": tenant_id,
        })
        attendance_source_docs, attendance_source_records = await _count_attendance_records(
            db,
            {"class_id": class_id, "course_id": source_course_id, "mantenedora_id": tenant_id},
        )
        attendance_target_docs, attendance_target_records = await _count_attendance_records(
            db,
            {"class_id": class_id, "course_id": target_course_id, "mantenedora_id": tenant_id},
        )

        signals = {
            "class_course_ids": _signal(matrix_source, matrix_target),
            "class_schedule_slots": _signal(source_slots, target_slots),
            "grades_documents": _signal(grades_source, grades_target),
            "attendance_documents": _signal(attendance_source_docs, attendance_target_docs),
            "attendance_records_count": _signal(attendance_source_records, attendance_target_records),
        }
        identity_evidence = classify_identity_evidence(signals)
        identity_classifications[identity_evidence["classification"]] += 1

        source_course = course_map[source_course_id]
        target_course = course_map[target_course_id]
        results.append({
            "case_number": number,
            "teacher": raw_case.get("teacher"),
            "class": raw_case.get("class"),
            "school": raw_case.get("school"),
            "snapshot_drift": False,
            "weekly_workload_conflict": {
                "source": source_live.get("carga_horaria_semanal"),
                "target": target_live.get("carga_horaria_semanal"),
            },
            "course_master_evidence": {
                "source": {
                    "course_id": source_course_id,
                    "name": source_course.get("name"),
                    "nivel_ensino": source_course.get("nivel_ensino"),
                    "workload_annual_hours": source_course.get("workload"),
                    "carga_horaria_por_serie": source_course.get("carga_horaria_por_serie"),
                    "active": source_course.get("active"),
                    "created_at": source_course.get("created_at"),
                },
                "target": {
                    "course_id": target_course_id,
                    "name": target_course.get("name"),
                    "nivel_ensino": target_course.get("nivel_ensino"),
                    "workload_annual_hours": target_course.get("workload"),
                    "carga_horaria_por_serie": target_course.get("carga_horaria_por_serie"),
                    "active": target_course.get("active"),
                    "created_at": target_course.get("created_at"),
                },
                "annual_to_weekly_conversion_performed": False,
            },
            "curriculum_matrix_evidence": {
                "source_member": matrix_source,
                "target_member": matrix_target,
                "matrix_size": len(matrix_ids),
            },
            "schedule_evidence": {
                "schedule_documents": len(schedules),
                "source_weekly_slot_count": source_slots,
                "target_weekly_slot_count": target_slots,
                "slot_count_is_not_automatically_treated_as_clock_hours": True,
            },
            "academic_evidence_counts": {
                "grades": {"source_documents": grades_source, "target_documents": grades_target},
                "attendance": {
                    "source_documents": attendance_source_docs,
                    "target_documents": attendance_target_docs,
                    "source_records_count": attendance_source_records,
                    "target_records_count": attendance_target_records,
                },
                "student_identifiers_exposed": False,
                "grade_values_exposed": False,
                "attendance_values_exposed": False,
            },
            "identity_signals": signals,
            "identity_evidence": identity_evidence,
            "automatic_workload_recommendation": False,
            "human_or_policy_decision_required": True,
        })

    report: dict[str, Any] = {
        "phase": PHASE_ID,
        "manifest_version": MANIFEST_VERSION,
        "mode": "READ_ONLY_TEACHER_WORKLOAD_TRIANGULATION",
        "status": "PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "group_name": "Geografia",
        "source_p0f7_2_manifest_sha256": validated["manifest_sha256"],
        "source_course_id": source_course_id,
        "target_course_id": target_course_id,
        "summary": {
            "expected_cases": 3,
            "documented_cases": len(results),
            "snapshot_drift_cases": drift_count,
            "identity_classification_counts": dict(sorted(identity_classifications.items())),
            "automatic_workload_recommendations": 0,
            "human_or_policy_decisions_required": len(results),
            "database_mutation": False,
        },
        "safety": {
            "read_only": True,
            "contains_student_identifiers": False,
            "contains_grade_values": False,
            "contains_attendance_values": False,
            "annual_to_weekly_conversion_performed": False,
            "automatic_recommendation": False,
            "automatic_resolution": False,
            "database_mutation": False,
            "production_writes_executed": False,
            "not_authorization_for_executor": True,
        },
        "cases": results,
    }
    report["manifest_sha256"] = _canonical_sha256(report)
    return report


def compact_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    cases = []
    for row in report.get("cases") or []:
        cases.append({
            "case_number": row.get("case_number"),
            "teacher_name": (row.get("teacher") or {}).get("name"),
            "school_name": (row.get("school") or {}).get("name"),
            "class_name": (row.get("class") or {}).get("name"),
            "weekly_workload_conflict": row.get("weekly_workload_conflict"),
            "course_master_evidence": row.get("course_master_evidence"),
            "curriculum_matrix_evidence": row.get("curriculum_matrix_evidence"),
            "schedule_evidence": row.get("schedule_evidence"),
            "academic_evidence_counts": row.get("academic_evidence_counts"),
            "identity_signals": row.get("identity_signals"),
            "identity_evidence": row.get("identity_evidence"),
            "automatic_workload_recommendation": False,
        })
    return {
        "phase": report.get("phase"),
        "mode": report.get("mode"),
        "status": report.get("status"),
        "group_name": report.get("group_name"),
        "summary": report.get("summary"),
        "cases": cases,
        "manifest_sha256": report.get("manifest_sha256"),
        "student_identifiers_printed": False,
        "grade_values_printed": False,
        "attendance_values_printed": False,
        "automatic_workload_recommendation": False,
        "database_mutation": False,
        "executor_authorized": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="P0-F7.3 teacher workload triangulation read-only"
    )
    parser.add_argument("--forensic", required=True, type=Path)
    parser.add_argument("--json", dest="json_path", required=True, type=Path)
    return parser.parse_args()


async def async_main() -> int:
    assert_read_only()
    args = parse_args()
    mongo_url, db_name = os.getenv("MONGO_URL"), os.getenv("DB_NAME")
    if not mongo_url or not db_name:
        raise RuntimeError("MONGO_URL and DB_NAME are required")
    client = AsyncIOMotorClient(mongo_url)
    try:
        report = await collect_report(client[db_name], p0f72_path=args.forensic)
    finally:
        client.close()
    _private_write_json(args.json_path, report)
    print(json.dumps(compact_summary(report), ensure_ascii=False, indent=2, default=str))
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
