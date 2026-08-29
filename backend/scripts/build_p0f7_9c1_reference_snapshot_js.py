"""Build P0-F7.9C1 bounded network reference snapshot collector.

Runs locally and consumes only the sealed P0-F7.9C0 inventory report. The
emitted mongosh collector is read-only and fetches only the small network
reference sets required for per-school pagination: schools and courses.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

SOURCE_PHASE = "P0F7.9C-INVENTORY-OFFLINE-VALIDATION-2026"
SOURCE_STRATEGY = "PAGED_BY_SCHOOL_SNAPSHOT"
REFERENCE_PHASE = "P0F7.9C1-NETWORK-REFERENCE-SNAPSHOT-2026"
REFERENCE_MODE = "READ_ONLY_BOUNDED_NETWORK_REFERENCE"
QUERY_BUDGET = 2
MAX_SCHOOLS = 50
MAX_COURSES = 150


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


def _context(report: Mapping[str, Any]) -> dict[str, Any]:
    if report.get("phase") != SOURCE_PHASE or report.get("status") != "PASS":
        raise ValueError("P0F7_9C0_REPORT_INVALID")
    if report.get("collection_strategy") != SOURCE_STRATEGY:
        raise ValueError("P0F7_9C0_STRATEGY_NOT_PAGED")
    tenant = _norm(report.get("mantenedora_id"))
    year = int(report.get("academic_year") or 0)
    counts = report.get("counts") or {}
    schools = int(counts.get("schools") or 0)
    courses = int(counts.get("courses") or 0)
    if not tenant or year <= 0:
        raise ValueError("P0F7_9C0_CONTEXT_INVALID")
    if schools <= 0 or schools > MAX_SCHOOLS:
        raise ValueError("P0F7_9C1_SCHOOL_BOUND_INVALID")
    if courses < 0 or courses > MAX_COURSES:
        raise ValueError("P0F7_9C1_COURSE_BOUND_INVALID")
    return {
        "mantenedora_id": tenant,
        "academic_year": year,
        "expected_schools": schools,
        "expected_courses": courses,
        "source_p0f7_9c0_report_sha256": _canonical_sha256(report),
    }


def build_js(report: Mapping[str, Any], db_name: str) -> str:
    if not db_name or not all(ch.isalnum() or ch in "_.-" for ch in db_name):
        raise ValueError("DB_NAME_INVALID")
    ctx = _context(report)
    request = json.dumps(ctx, ensure_ascii=False, separators=(",", ":"))
    database = json.dumps(db_name, ensure_ascii=False)
    return f'''const PHASE = {json.dumps(REFERENCE_PHASE)};
const MODE = {json.dumps(REFERENCE_MODE)};
const QUERY_BUDGET = {QUERY_BUDGET};
const MAX_SCHOOLS = {MAX_SCHOOLS};
const MAX_COURSES = {MAX_COURSES};
const req = {request};
const targetDb = db.getSiblingDB({database});
const tenant = String(req.mantenedora_id || "");
if (!tenant) throw new Error("TENANT_MISSING_FAIL_CLOSED");
const result = {{
  phase: PHASE,
  mode: MODE,
  generated_at_utc: new Date().toISOString(),
  mantenedora_id: tenant,
  academic_year: Number(req.academic_year),
  source_p0f7_9c0_report_sha256: req.source_p0f7_9c0_report_sha256,
  query_budget: QUERY_BUDGET,
  query_calls: 0,
  schools: [],
  courses: []
}};

result.schools = targetDb.schools.find(
  {{mantenedora_id:tenant}},
  {{_id:0,id:1,name:1,mantenedora_id:1}}
).sort({{id:1}}).limit(MAX_SCHOOLS + 1).toArray();
result.query_calls += 1;
if (result.schools.length > MAX_SCHOOLS) throw new Error("SCHOOL_BOUND_REACHED");
if (result.schools.length !== Number(req.expected_schools)) throw new Error("SCHOOL_COUNT_DRIFT");

result.courses = targetDb.courses.find(
  {{mantenedora_id:tenant}},
  {{
    _id:0,id:1,name:1,nivel_ensino:1,grade_levels:1,carga_horaria_por_serie:1,
    atendimento_programa:1,active:1,status:1,mantenedora_id:1
  }}
).sort({{id:1}}).limit(MAX_COURSES + 1).toArray();
result.query_calls += 1;
if (result.courses.length > MAX_COURSES) throw new Error("COURSE_BOUND_REACHED");
if (result.courses.length !== Number(req.expected_courses)) throw new Error("COURSE_COUNT_DRIFT");

if (result.query_calls !== QUERY_BUDGET) throw new Error("QUERY_BUDGET_MISMATCH");
print("P0F79C1_REFERENCE_JSON=" + JSON.stringify(result));
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build P0-F7.9C1 network reference collector")
    parser.add_argument("--inventory-report", required=True, type=Path)
    parser.add_argument("--db", required=True)
    parser.add_argument("--js", dest="js_path", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    js = build_js(_load(args.inventory_report), args.db)
    args.js_path.parent.mkdir(parents=True, exist_ok=True)
    args.js_path.write_text(js, encoding="utf-8")
    print(f"P0F7_9C1_REFERENCE_COLLECTOR_BUILT=YES path={args.js_path}")
    print(f"P0F7_9C1_REFERENCE_QUERY_BUDGET={QUERY_BUDGET}")
    print("PRODUCTION_WRITES=0")
    print("SENSITIVE_ACADEMIC_COLLECTIONS_READ=0")


if __name__ == "__main__":
    main()
