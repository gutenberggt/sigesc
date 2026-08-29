"""P0-F7.9C1 offline network curricular audit.

Consumes only the sealed P0-F7.9C0 report, the bounded reference snapshot and
one bounded page per school. No database/network/Docker access is performed.
Curricular classification reuses the write-boundary SSoT from
services.teacher_assignment_integrity; this module does not reimplement the
curricular compatibility policy.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from services.teacher_assignment_integrity import (  # noqa: E402
    TeacherAssignmentIntegrityError,
    validate_teacher_assignment_curriculum,
)

REPORT_PHASE = "P0F7.9C-INVENTORY-OFFLINE-VALIDATION-2026"
REFERENCE_PHASE = "P0F7.9C1-NETWORK-REFERENCE-SNAPSHOT-2026"
REFERENCE_MODE = "READ_ONLY_BOUNDED_NETWORK_REFERENCE"
PAGE_PHASE = "P0F7.9C1-SCHOOL-CURRICULAR-PAGE-2026"
PAGE_MODE = "READ_ONLY_BOUNDED_SCHOOL_PAGE"
OUTPUT_PHASE = "P0F7.9C1-OFFLINE-NETWORK-CURRICULAR-AUDIT-2026"
ACTIVE_STATUS = {"active", "ativo"}


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _canonical_sha256(payload: Any) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON_ROOT_MUST_BE_OBJECT:{path}")
    return payload


def _is_active(row: Mapping[str, Any]) -> bool:
    return _norm(row.get("status")).casefold() in ACTIVE_STATUS


def _explicit_level(cls: Mapping[str, Any]) -> str:
    return _norm(cls.get("nivel_ensino") or cls.get("education_level"))


def classify_assignment(
    assignment: Mapping[str, Any],
    class_by_id: Mapping[str, Mapping[str, Any]],
    course_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[str, dict[str, Any]]:
    """Classify one historical binding through the current writer SSoT."""
    class_id = _norm(assignment.get("class_id"))
    course_id = _norm(assignment.get("course_id"))
    cls = class_by_id.get(class_id)
    course = course_by_id.get(course_id)
    if not cls:
        return "AUDIT_CLASS_RECORD_MISSING", {}
    if not course:
        return "AUDIT_COURSE_RECORD_MISSING", {}
    try:
        result = validate_teacher_assignment_curriculum(
            class_info=cls,
            course=course,
            school_id=_norm(assignment.get("school_id")),
            academic_year=int(assignment.get("academic_year") or 0),
        )
        return "COMPATIBLE", dict(result)
    except TeacherAssignmentIntegrityError as exc:
        return exc.code, dict(exc.fit or {})


def _validate_reference(report: Mapping[str, Any], reference: Mapping[str, Any]) -> tuple[str, int]:
    if report.get("phase") != REPORT_PHASE or report.get("status") != "PASS":
        raise ValueError("P0F7_9C0_REPORT_INVALID")
    if report.get("collection_strategy") != "PAGED_BY_SCHOOL_SNAPSHOT":
        raise ValueError("P0F7_9C0_STRATEGY_NOT_PAGED")
    if reference.get("phase") != REFERENCE_PHASE or reference.get("mode") != REFERENCE_MODE:
        raise ValueError("P0F7_9C1_REFERENCE_INVALID")
    if int(reference.get("query_budget") or 0) != 2 or int(reference.get("query_calls") or 0) != 2:
        raise ValueError("P0F7_9C1_REFERENCE_QUERY_BUDGET_INVALID")
    if _norm(reference.get("source_p0f7_9c0_report_sha256")) != _canonical_sha256(report):
        raise ValueError("P0F7_9C1_REFERENCE_SOURCE_CHAIN_MISMATCH")
    tenant = _norm(report.get("mantenedora_id"))
    year = int(report.get("academic_year") or 0)
    if _norm(reference.get("mantenedora_id")) != tenant or int(reference.get("academic_year") or 0) != year:
        raise ValueError("P0F7_9C1_REFERENCE_CONTEXT_DRIFT")
    expected = report.get("counts") or {}
    if len(reference.get("schools") or []) != int(expected.get("schools") or -1):
        raise ValueError("P0F7_9C1_REFERENCE_SCHOOL_COUNT_DRIFT")
    if len(reference.get("courses") or []) != int(expected.get("courses") or -1):
        raise ValueError("P0F7_9C1_REFERENCE_COURSE_COUNT_DRIFT")
    return tenant, year


def build_report(report: Mapping[str, Any], reference: Mapping[str, Any], pages: list[Mapping[str, Any]]) -> dict[str, Any]:
    tenant, year = _validate_reference(report, reference)
    ref_sha = _canonical_sha256(reference)
    report_sha = _canonical_sha256(report)
    schools = reference.get("schools") or []
    courses = reference.get("courses") or []
    school_by_id = {_norm(row.get("id")): row for row in schools if _norm(row.get("id"))}
    if len(school_by_id) != len(schools):
        raise ValueError("P0F7_9C1_REFERENCE_SCHOOL_ID_DUPLICATE")
    course_by_id = {_norm(row.get("id")): row for row in courses if _norm(row.get("id"))}
    if len(course_by_id) != len(courses):
        raise ValueError("P0F7_9C1_REFERENCE_COURSE_ID_DUPLICATE")
    for row in schools + courses:
        if _norm(row.get("mantenedora_id")) != tenant:
            raise ValueError("P0F7_9C1_REFERENCE_TENANT_DRIFT")

    page_by_school: dict[str, Mapping[str, Any]] = {}
    total_classes = 0
    total_assignments = 0
    active_assignments = 0
    all_classes: dict[str, Mapping[str, Any]] = {}
    assignments: list[Mapping[str, Any]] = []
    assignment_ids: set[str] = set()

    for page in pages:
        if page.get("phase") != PAGE_PHASE or page.get("mode") != PAGE_MODE:
            raise ValueError("P0F7_9C1_PAGE_PHASE_OR_MODE_INVALID")
        if int(page.get("query_budget") or 0) != 4 or int(page.get("query_calls") or 0) != 4:
            raise ValueError("P0F7_9C1_PAGE_QUERY_BUDGET_INVALID")
        if _norm(page.get("source_reference_sha256")) != ref_sha:
            raise ValueError("P0F7_9C1_PAGE_REFERENCE_CHAIN_MISMATCH")
        if _norm(page.get("source_p0f7_9c0_report_sha256")) != report_sha:
            raise ValueError("P0F7_9C1_PAGE_REPORT_CHAIN_MISMATCH")
        if _norm(page.get("mantenedora_id")) != tenant or int(page.get("academic_year") or 0) != year:
            raise ValueError("P0F7_9C1_PAGE_CONTEXT_DRIFT")
        school_id = _norm(page.get("school_id"))
        if school_id not in school_by_id or school_id in page_by_school:
            raise ValueError("P0F7_9C1_PAGE_SCHOOL_UNKNOWN_OR_DUPLICATE")
        page_by_school[school_id] = page
        cls_rows = list(page.get("classes") or [])
        asg_rows = list(page.get("teacher_assignments") or [])
        counts = page.get("counts") or {}
        if len(cls_rows) != int(counts.get("classes") or 0):
            raise ValueError("P0F7_9C1_PAGE_CLASS_COUNT_DRIFT")
        if len(asg_rows) != int(counts.get("teacher_assignments") or 0):
            raise ValueError("P0F7_9C1_PAGE_ASSIGNMENT_COUNT_DRIFT")
        total_classes += len(cls_rows)
        total_assignments += len(asg_rows)
        for cls in cls_rows:
            class_id = _norm(cls.get("id"))
            if not class_id or class_id in all_classes:
                raise ValueError("P0F7_9C1_CLASS_ID_INVALID_OR_DUPLICATE")
            if _norm(cls.get("mantenedora_id")) != tenant or _norm(cls.get("school_id")) != school_id:
                raise ValueError("P0F7_9C1_CLASS_SCOPE_DRIFT")
            if int(cls.get("academic_year") or 0) != year:
                raise ValueError("P0F7_9C1_CLASS_YEAR_DRIFT")
            all_classes[class_id] = cls
        for assignment in asg_rows:
            assignment_id = _norm(assignment.get("id"))
            if not assignment_id or assignment_id in assignment_ids:
                raise ValueError("P0F7_9C1_ASSIGNMENT_ID_INVALID_OR_DUPLICATE")
            assignment_ids.add(assignment_id)
            if _norm(assignment.get("mantenedora_id")) != tenant or _norm(assignment.get("school_id")) != school_id:
                raise ValueError("P0F7_9C1_ASSIGNMENT_SCOPE_DRIFT")
            if int(assignment.get("academic_year") or 0) != year:
                raise ValueError("P0F7_9C1_ASSIGNMENT_YEAR_DRIFT")
            if _is_active(assignment):
                active_assignments += 1
            assignments.append(assignment)

    if set(page_by_school) != set(school_by_id):
        missing = sorted(set(school_by_id) - set(page_by_school))
        raise ValueError(f"P0F7_9C1_SCHOOL_PAGE_COVERAGE_INCOMPLETE:{','.join(missing)}")

    expected = report.get("counts") or {}
    if total_classes != int(expected.get("classes") or -1):
        raise ValueError("P0F7_9C1_NETWORK_CLASS_TOTAL_DRIFT")
    if total_assignments != int(expected.get("teacher_assignments") or -1):
        raise ValueError("P0F7_9C1_NETWORK_ASSIGNMENT_TOTAL_DRIFT")
    if active_assignments != int(expected.get("active_teacher_assignments") or -1):
        raise ValueError("P0F7_9C1_NETWORK_ACTIVE_ASSIGNMENT_TOTAL_DRIFT")

    classes_without_level = sum(1 for cls in all_classes.values() if not _explicit_level(cls))
    if classes_without_level != int(expected.get("classes_without_explicit_level") or -1):
        raise ValueError("P0F7_9C1_CLASSES_WITHOUT_LEVEL_TOTAL_DRIFT")

    code_counts: Counter[str] = Counter()
    active_code_counts: Counter[str] = Counter()
    school_counters: dict[str, Counter[str]] = {school_id: Counter() for school_id in school_by_id}
    findings: list[dict[str, Any]] = []
    ei_to_eja = 0

    for assignment in assignments:
        code, fit = classify_assignment(assignment, all_classes, course_by_id)
        active = _is_active(assignment)
        code_counts[code] += 1
        if active:
            active_code_counts[code] += 1
        school_id = _norm(assignment.get("school_id"))
        school_counters[school_id]["TOTAL"] += 1
        school_counters[school_id][code] += 1
        if code == "COMPATIBLE":
            continue
        cls = all_classes.get(_norm(assignment.get("class_id"))) or {}
        course = course_by_id.get(_norm(assignment.get("course_id"))) or {}
        class_level = _explicit_level(cls)
        course_level = _norm(course.get("nivel_ensino"))
        if (
            code == "TEACHER_ASSIGNMENT_LEVEL_MISMATCH"
            and class_level.casefold() == "eja_final"
            and course_level.casefold() == "educacao_infantil"
            and active
        ):
            ei_to_eja += 1
        findings.append({
            "assignment_id": assignment.get("id"),
            "school_id": school_id,
            "class_id": assignment.get("class_id"),
            "class_name": cls.get("name"),
            "course_id": assignment.get("course_id"),
            "course_name": course.get("name"),
            "class_level": class_level or None,
            "course_level": course_level or None,
            "status": assignment.get("status"),
            "is_active": active,
            "integrity_code": code,
            "fit_classification": fit.get("classification") if fit else None,
            "fit_rank": fit.get("rank") if fit else None,
        })

    by_school = []
    for school_id in sorted(school_by_id):
        counter = school_counters[school_id]
        noncompatible = counter["TOTAL"] - counter["COMPATIBLE"]
        by_school.append({
            "school_id": school_id,
            "school_name": school_by_id[school_id].get("name"),
            "assignments": counter["TOTAL"],
            "compatible": counter["COMPATIBLE"],
            "noncompatible_or_blocked": noncompatible,
            "codes": {k: v for k, v in sorted(counter.items()) if k != "TOTAL" and v},
        })

    output: dict[str, Any] = {
        "phase": OUTPUT_PHASE,
        "status": "PASS",
        "mantenedora_id": tenant,
        "academic_year": year,
        "source_p0f7_9c0_report_sha256": report_sha,
        "source_reference_sha256": ref_sha,
        "summary": {
            "schools": len(school_by_id),
            "school_pages": len(page_by_school),
            "classes": total_classes,
            "classes_without_explicit_level": classes_without_level,
            "teacher_assignments": total_assignments,
            "active_teacher_assignments": active_assignments,
            "courses": len(course_by_id),
            "compatible_assignments": code_counts["COMPATIBLE"],
            "noncompatible_or_blocked_assignments": total_assignments - code_counts["COMPATIBLE"],
            "active_noncompatible_or_blocked_assignments": active_assignments - active_code_counts["COMPATIBLE"],
            "active_educacao_infantil_to_eja_final": ei_to_eja,
            "integrity_codes": dict(sorted(code_counts.items())),
            "active_integrity_codes": dict(sorted(active_code_counts.items())),
        },
        "by_school": by_school,
        "findings": findings,
        "safety": {
            "database_access_by_offline_analyzer": False,
            "database_mutation": False,
            "production_writes": False,
            "student_records_read": 0,
            "enrollment_records_read": 0,
            "grade_records_read": 0,
            "attendance_records_read": 0,
            "teacher_identity_fields_collected": 0,
            "remediation_executed": False,
        },
    }
    output["report_sha256"] = _canonical_sha256(output)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit P0-F7.9C1 school pages offline")
    parser.add_argument("--inventory-report", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--pages-dir", required=True, type=Path)
    parser.add_argument("--json", dest="output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    page_paths = sorted(args.pages_dir.glob("school-*.json"))
    if not page_paths:
        raise ValueError("P0F7_9C1_NO_SCHOOL_PAGES_FOUND")
    report = build_report(
        _load(args.inventory_report),
        _load(args.reference),
        [_load(path) for path in page_paths],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print("P0F7_9C1_NETWORK_AUDIT=PASS")
    print(f"REPORT={args.output}")
    print("PRODUCTION_ACCESS=NO")
    print("DATABASE_MUTATION=NO")
    print("REMEDIATION_EXECUTED=NO")


if __name__ == "__main__":
    main()
