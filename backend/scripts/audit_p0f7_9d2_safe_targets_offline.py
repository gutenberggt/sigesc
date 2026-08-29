"""P0-F7.9D2 — resolve remediation targets for confirmed teacher-assignment conflicts.

Offline only. Consumes the sealed P0-F7.9C1 network audit, its bounded reference
snapshot and the already-collected per-school pages. Candidate generation is
restricted to same-name alternative courses, but acceptance is decided only by
``validate_teacher_assignment_curriculum`` — the production write-boundary SSoT.

This phase is proposal-only: it never accesses MongoDB/network/Docker and never
mutates teacher assignments.
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
from utils.curriculum_resolver import _norm_name  # noqa: E402

AUDIT_PHASE = "P0F7.9C1-OFFLINE-NETWORK-CURRICULAR-AUDIT-2026"
REFERENCE_PHASE = "P0F7.9C1-NETWORK-REFERENCE-SNAPSHOT-2026"
REFERENCE_MODE = "READ_ONLY_BOUNDED_NETWORK_REFERENCE"
PAGE_PHASE = "P0F7.9C1-SCHOOL-CURRICULAR-PAGE-2026"
PAGE_MODE = "READ_ONLY_BOUNDED_SCHOOL_PAGE"
OUTPUT_PHASE = "P0F7.9D2-SAFE-TARGET-RESOLUTION-2026"
CONFIRMED_CODES = {
    "TEACHER_ASSIGNMENT_LEVEL_MISMATCH",
    "TEACHER_ASSIGNMENT_SERIES_MISMATCH",
}
INACTIVE_STATUSES = {
    "inactive",
    "inativo",
    "disabled",
    "desativado",
    "deleted",
    "excluido",
    "excluído",
}


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


def _course_available(course: Mapping[str, Any]) -> bool:
    if course.get("active") is False:
        return False
    return _norm(course.get("status")).casefold() not in INACTIVE_STATUSES


def _validate_sources(
    audit: Mapping[str, Any],
    reference: Mapping[str, Any],
    pages: list[Mapping[str, Any]],
) -> tuple[str, int, dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    if audit.get("phase") != AUDIT_PHASE or audit.get("status") != "PASS":
        raise ValueError("P0F7_9C1_AUDIT_INVALID")
    if reference.get("phase") != REFERENCE_PHASE or reference.get("mode") != REFERENCE_MODE:
        raise ValueError("P0F7_9C1_REFERENCE_INVALID")
    if int(reference.get("query_budget") or 0) != 2 or int(reference.get("query_calls") or 0) != 2:
        raise ValueError("P0F7_9C1_REFERENCE_QUERY_BUDGET_INVALID")

    tenant = _norm(audit.get("mantenedora_id"))
    year = int(audit.get("academic_year") or 0)
    if not tenant or year <= 0:
        raise ValueError("P0F7_9C1_AUDIT_CONTEXT_INVALID")
    if _norm(reference.get("mantenedora_id")) != tenant or int(reference.get("academic_year") or 0) != year:
        raise ValueError("P0F7_9C1_REFERENCE_CONTEXT_DRIFT")

    ref_sha = _canonical_sha256(reference)
    if _norm(audit.get("source_reference_sha256")) != ref_sha:
        raise ValueError("P0F7_9C1_AUDIT_REFERENCE_CHAIN_MISMATCH")

    summary = audit.get("summary") or {}
    expected_pages = int(summary.get("school_pages") or 0)
    expected_classes = int(summary.get("classes") or 0)
    expected_assignments = int(summary.get("teacher_assignments") or 0)
    if len(pages) != expected_pages:
        raise ValueError("P0F7_9D2_PAGE_COUNT_DRIFT")

    class_by_id: dict[str, Mapping[str, Any]] = {}
    assignment_by_id: dict[str, Mapping[str, Any]] = {}
    page_schools: set[str] = set()
    for page in pages:
        if page.get("phase") != PAGE_PHASE or page.get("mode") != PAGE_MODE:
            raise ValueError("P0F7_9D2_PAGE_PHASE_OR_MODE_INVALID")
        if int(page.get("query_budget") or 0) != 4 or int(page.get("query_calls") or 0) != 4:
            raise ValueError("P0F7_9D2_PAGE_QUERY_BUDGET_INVALID")
        if _norm(page.get("source_reference_sha256")) != ref_sha:
            raise ValueError("P0F7_9D2_PAGE_REFERENCE_CHAIN_MISMATCH")
        if _norm(page.get("mantenedora_id")) != tenant or int(page.get("academic_year") or 0) != year:
            raise ValueError("P0F7_9D2_PAGE_CONTEXT_DRIFT")
        school_id = _norm(page.get("school_id"))
        if not school_id or school_id in page_schools:
            raise ValueError("P0F7_9D2_PAGE_SCHOOL_INVALID_OR_DUPLICATE")
        page_schools.add(school_id)

        for cls in page.get("classes") or []:
            class_id = _norm((cls or {}).get("id"))
            if not class_id or class_id in class_by_id:
                raise ValueError("P0F7_9D2_CLASS_ID_INVALID_OR_DUPLICATE")
            class_by_id[class_id] = cls
        for assignment in page.get("teacher_assignments") or []:
            assignment_id = _norm((assignment or {}).get("id"))
            if not assignment_id or assignment_id in assignment_by_id:
                raise ValueError("P0F7_9D2_ASSIGNMENT_ID_INVALID_OR_DUPLICATE")
            assignment_by_id[assignment_id] = assignment

    if len(class_by_id) != expected_classes:
        raise ValueError("P0F7_9D2_CLASS_TOTAL_DRIFT")
    if len(assignment_by_id) != expected_assignments:
        raise ValueError("P0F7_9D2_ASSIGNMENT_TOTAL_DRIFT")
    return tenant, year, class_by_id, assignment_by_id


def resolve_targets(
    audit: Mapping[str, Any],
    reference: Mapping[str, Any],
    class_by_id: Mapping[str, Mapping[str, Any]],
    assignment_by_id: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve confirmed findings into proposal-only target classes."""
    tenant = _norm(audit.get("mantenedora_id"))
    year = int(audit.get("academic_year") or 0)
    courses = list(reference.get("courses") or [])
    course_by_id = {_norm(c.get("id")): c for c in courses if _norm(c.get("id"))}
    if len(course_by_id) != len(courses):
        raise ValueError("P0F7_9D2_REFERENCE_COURSE_ID_INVALID_OR_DUPLICATE")

    confirmed = [
        row
        for row in (audit.get("findings") or [])
        if _norm((row or {}).get("integrity_code")) in CONFIRMED_CODES
    ]
    out: list[dict[str, Any]] = []
    for finding in confirmed:
        assignment_id = _norm(finding.get("assignment_id"))
        class_id = _norm(finding.get("class_id"))
        source_course_id = _norm(finding.get("course_id"))
        assignment = assignment_by_id.get(assignment_id)
        cls = class_by_id.get(class_id)
        source_course = course_by_id.get(source_course_id)
        if not assignment:
            raise ValueError(f"P0F7_9D2_ASSIGNMENT_RECORD_MISSING:{assignment_id}")
        if not cls:
            raise ValueError(f"P0F7_9D2_CLASS_RECORD_MISSING:{class_id}")
        if not source_course:
            raise ValueError(f"P0F7_9D2_SOURCE_COURSE_RECORD_MISSING:{source_course_id}")
        if _norm(assignment.get("mantenedora_id")) != tenant:
            raise ValueError("P0F7_9D2_ASSIGNMENT_TENANT_DRIFT")

        source_name_key = _norm_name(_norm(source_course.get("name")))
        candidates = [
            course
            for course in courses
            if _norm(course.get("id")) != source_course_id
            and _norm_name(_norm(course.get("name"))) == source_name_key
            and _norm(course.get("mantenedora_id")) == tenant
            and _course_available(course)
        ]

        accepted: list[dict[str, Any]] = []
        rejected: Counter[str] = Counter()
        for candidate in candidates:
            try:
                verdict = validate_teacher_assignment_curriculum(
                    class_info=cls,
                    course=candidate,
                    school_id=_norm(assignment.get("school_id")),
                    academic_year=year,
                )
                fit = dict(verdict.get("fit") or {})
                accepted.append(
                    {
                        "course_id": candidate.get("id"),
                        "course_name": candidate.get("name"),
                        "course_level": candidate.get("nivel_ensino"),
                        "write_policy": verdict.get("write_policy"),
                        "fit_classification": fit.get("classification"),
                        "fit_rank": fit.get("rank"),
                    }
                )
            except TeacherAssignmentIntegrityError as exc:
                rejected[exc.code] += 1

        accepted.sort(key=lambda row: _norm(row.get("course_id")))
        if len(accepted) == 1:
            resolution = "UNIQUE_SAFE_TARGET"
        elif len(accepted) > 1:
            resolution = "MULTIPLE_SAFE_TARGETS_REVIEW"
        else:
            resolution = "NO_SAFE_TARGET"

        out.append(
            {
                "assignment_id": assignment_id,
                "school_id": finding.get("school_id"),
                "class_id": class_id,
                "class_name": finding.get("class_name"),
                "source_course_id": source_course_id,
                "source_course_name": source_course.get("name"),
                "source_course_level": source_course.get("nivel_ensino"),
                "integrity_code": finding.get("integrity_code"),
                "resolution": resolution,
                "same_name_alternatives_considered": len(candidates),
                "validated_targets": accepted,
                "rejected_candidate_codes": dict(sorted(rejected.items())),
            }
        )

    out.sort(key=lambda row: (_norm(row.get("school_id")), _norm(row.get("assignment_id"))))
    return out


def build_report(
    audit: Mapping[str, Any],
    reference: Mapping[str, Any],
    pages: list[Mapping[str, Any]],
) -> dict[str, Any]:
    tenant, year, class_by_id, assignment_by_id = _validate_sources(audit, reference, pages)
    resolutions = resolve_targets(audit, reference, class_by_id, assignment_by_id)
    counts = Counter(row["resolution"] for row in resolutions)
    source_confirmed = sum(
        1
        for row in (audit.get("findings") or [])
        if _norm((row or {}).get("integrity_code")) in CONFIRMED_CODES
    )
    if len(resolutions) != source_confirmed:
        raise ValueError("P0F7_9D2_CONFIRMED_COVERAGE_DRIFT")

    report: dict[str, Any] = {
        "phase": OUTPUT_PHASE,
        "status": "PASS",
        "mantenedora_id": tenant,
        "academic_year": year,
        "source_audit_sha256": _canonical_sha256(audit),
        "source_reference_sha256": _canonical_sha256(reference),
        "summary": {
            "confirmed_conflicts": len(resolutions),
            "unique_safe_target": counts["UNIQUE_SAFE_TARGET"],
            "multiple_safe_targets_review": counts["MULTIPLE_SAFE_TARGETS_REVIEW"],
            "no_safe_target": counts["NO_SAFE_TARGET"],
            "proposal_only": True,
        },
        "resolutions": resolutions,
        "safety": {
            "production_access": False,
            "database_access": False,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
            "student_records_read": 0,
            "teacher_identity_fields_used": 0,
        },
    }
    report["report_sha256"] = _canonical_sha256(report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve P0-F7.9D2 safe remediation targets offline")
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--pages-dir", required=True, type=Path)
    parser.add_argument("--json", dest="output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    page_paths = sorted(args.pages_dir.glob("school-*.json"))
    if not page_paths:
        raise ValueError("P0F7_9D2_NO_SCHOOL_PAGES_FOUND")
    report = build_report(
        _load(args.audit),
        _load(args.reference),
        [_load(path) for path in page_paths],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print("P0F7_9D2_SAFE_TARGET_RESOLUTION=PASS")
    print(f"REPORT={args.output}")
    print("PRODUCTION_ACCESS=NO")
    print("DATABASE_MUTATION=NO")
    print("REMEDIATION_EXECUTED=NO")


if __name__ == "__main__":
    main()
