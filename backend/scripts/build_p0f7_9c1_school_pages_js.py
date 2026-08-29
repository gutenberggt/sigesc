"""Build P0-F7.9C1 per-school bounded mongosh collectors.

Runs locally from the sealed P0-F7.9C0 report plus the small reference snapshot.
Each emitted collector performs four tenant/year/school-scoped read-only queries:
counts classes and assignments, then fetches only the minimal class and assignment
fields required by the offline curricular audit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

REPORT_PHASE = "P0F7.9C-INVENTORY-OFFLINE-VALIDATION-2026"
REFERENCE_PHASE = "P0F7.9C1-NETWORK-REFERENCE-SNAPSHOT-2026"
REFERENCE_MODE = "READ_ONLY_BOUNDED_NETWORK_REFERENCE"
PAGE_PHASE = "P0F7.9C1-SCHOOL-CURRICULAR-PAGE-2026"
PAGE_MODE = "READ_ONLY_BOUNDED_SCHOOL_PAGE"
QUERY_BUDGET = 4
MAX_CLASSES_PER_SCHOOL = 100
MAX_ASSIGNMENTS_PER_SCHOOL = 600


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
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return payload


def _validate(report: Mapping[str, Any], reference: Mapping[str, Any]) -> dict[str, Any]:
    if report.get("phase") != REPORT_PHASE or report.get("status") != "PASS":
        raise ValueError("P0F7_9C0_REPORT_INVALID")
    if report.get("collection_strategy") != "PAGED_BY_SCHOOL_SNAPSHOT":
        raise ValueError("P0F7_9C0_STRATEGY_NOT_PAGED")
    if reference.get("phase") != REFERENCE_PHASE or reference.get("mode") != REFERENCE_MODE:
        raise ValueError("P0F7_9C1_REFERENCE_INVALID")
    if int(reference.get("query_budget") or 0) != 2 or int(reference.get("query_calls") or 0) != 2:
        raise ValueError("P0F7_9C1_REFERENCE_QUERY_BUDGET_INVALID")
    if _norm(reference.get("source_p0f7_9c0_report_sha256")) != _canonical_sha256(report):
        raise ValueError("P0F7_9C1_REFERENCE_CHAIN_MISMATCH")
    tenant = _norm(report.get("mantenedora_id"))
    year = int(report.get("academic_year") or 0)
    if _norm(reference.get("mantenedora_id")) != tenant or int(reference.get("academic_year") or 0) != year:
        raise ValueError("P0F7_9C1_REFERENCE_CONTEXT_DRIFT")
    schools = reference.get("schools") or []
    if not schools:
        raise ValueError("P0F7_9C1_REFERENCE_SCHOOLS_EMPTY")
    seen: set[str] = set()
    normalized: list[dict[str, str]] = []
    for row in schools:
        school_id = _norm((row or {}).get("id"))
        if not school_id or school_id in seen:
            raise ValueError("P0F7_9C1_SCHOOL_ID_INVALID_OR_DUPLICATE")
        if _norm((row or {}).get("mantenedora_id")) != tenant:
            raise ValueError("P0F7_9C1_SCHOOL_TENANT_DRIFT")
        seen.add(school_id)
        normalized.append({"id": school_id, "name": _norm((row or {}).get("name"))})
    return {
        "tenant": tenant,
        "year": year,
        "schools": normalized,
        "reference_sha256": _canonical_sha256(reference),
        "report_sha256": _canonical_sha256(report),
    }


def _safe_filename(school_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in school_id)


def _page_js(ctx: Mapping[str, Any], school: Mapping[str, str], db_name: str) -> str:
    req = {
        "mantenedora_id": ctx["tenant"],
        "academic_year": ctx["year"],
        "school_id": school["id"],
        "school_name": school["name"],
        "source_reference_sha256": ctx["reference_sha256"],
        "source_p0f7_9c0_report_sha256": ctx["report_sha256"],
    }
    request = json.dumps(req, ensure_ascii=False, separators=(",", ":"))
    database = json.dumps(db_name, ensure_ascii=False)
    return f'''const PHASE = {json.dumps(PAGE_PHASE)};
const MODE = {json.dumps(PAGE_MODE)};
const QUERY_BUDGET = {QUERY_BUDGET};
const MAX_CLASSES = {MAX_CLASSES_PER_SCHOOL};
const MAX_ASSIGNMENTS = {MAX_ASSIGNMENTS_PER_SCHOOL};
const req = {request};
const targetDb = db.getSiblingDB({database});
const tenant = String(req.mantenedora_id || "");
const schoolId = String(req.school_id || "");
const year = Number(req.academic_year || 0);
if (!tenant || !schoolId || !year) throw new Error("PAGE_CONTEXT_INVALID");
const yearFilter = {{$in:[year,String(year)]}};
const result = {{
  phase: PHASE,
  mode: MODE,
  generated_at_utc: new Date().toISOString(),
  mantenedora_id: tenant,
  academic_year: year,
  school_id: schoolId,
  school_name: req.school_name,
  source_reference_sha256: req.source_reference_sha256,
  source_p0f7_9c0_report_sha256: req.source_p0f7_9c0_report_sha256,
  query_budget: QUERY_BUDGET,
  query_calls: 0,
  counts: {{}},
  classes: [],
  teacher_assignments: []
}};

const classFilter = {{mantenedora_id:tenant,school_id:schoolId,academic_year:yearFilter}};
const assignmentFilter = {{mantenedora_id:tenant,school_id:schoolId,academic_year:yearFilter}};
result.counts.classes = targetDb.classes.countDocuments(classFilter);
result.query_calls += 1;
result.counts.teacher_assignments = targetDb.teacher_assignments.countDocuments(assignmentFilter);
result.query_calls += 1;
if (result.counts.classes > MAX_CLASSES) throw new Error("SCHOOL_CLASS_BOUND_REACHED");
if (result.counts.teacher_assignments > MAX_ASSIGNMENTS) throw new Error("SCHOOL_ASSIGNMENT_BOUND_REACHED");

result.classes = targetDb.classes.find(
  classFilter,
  {{
    _id:0,id:1,name:1,school_id:1,academic_year:1,mantenedora_id:1,
    nivel_ensino:1,education_level:1,grade_level:1,series:1,course_ids:1
  }}
).sort({{id:1}}).limit(MAX_CLASSES + 1).toArray();
result.query_calls += 1;
if (result.classes.length !== Number(result.counts.classes)) throw new Error("SCHOOL_CLASS_FETCH_COUNT_DRIFT");

result.teacher_assignments = targetDb.teacher_assignments.find(
  assignmentFilter,
  {{
    _id:0,id:1,school_id:1,class_id:1,course_id:1,academic_year:1,status:1,
    created_at:1,updated_at:1,is_substituicao:1,mantenedora_id:1
  }}
).sort({{id:1}}).limit(MAX_ASSIGNMENTS + 1).toArray();
result.query_calls += 1;
if (result.teacher_assignments.length !== Number(result.counts.teacher_assignments)) throw new Error("SCHOOL_ASSIGNMENT_FETCH_COUNT_DRIFT");

if (result.query_calls !== QUERY_BUDGET) throw new Error("QUERY_BUDGET_MISMATCH");
print("P0F79C1_SCHOOL_PAGE_JSON=" + JSON.stringify(result));
'''


def build_pages(report: Mapping[str, Any], reference: Mapping[str, Any], db_name: str, out_dir: Path) -> int:
    if not db_name or not all(ch.isalnum() or ch in "_.-" for ch in db_name):
        raise ValueError("DB_NAME_INVALID")
    ctx = _validate(report, reference)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("school-*.js"):
        old.unlink()
    for school in ctx["schools"]:
        path = out_dir / f"school-{_safe_filename(school['id'])}.js"
        path.write_text(_page_js(ctx, school, db_name), encoding="utf-8")
    return len(ctx["schools"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build P0-F7.9C1 per-school collectors")
    parser.add_argument("--inventory-report", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--db", required=True)
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    count = build_pages(_load(args.inventory_report), _load(args.reference), args.db, args.out_dir)
    print(f"P0F7_9C1_SCHOOL_COLLECTORS_BUILT={count}")
    print(f"P0F7_9C1_SCHOOL_QUERY_BUDGET_EACH={QUERY_BUDGET}")
    print(f"P0F7_9C1_MAX_CLASSES_PER_SCHOOL={MAX_CLASSES_PER_SCHOOL}")
    print(f"P0F7_9C1_MAX_ASSIGNMENTS_PER_SCHOOL={MAX_ASSIGNMENTS_PER_SCHOOL}")
    print("PRODUCTION_WRITES=0")
    print("SENSITIVE_ACADEMIC_COLLECTIONS_READ=0")


if __name__ == "__main__":
    main()
