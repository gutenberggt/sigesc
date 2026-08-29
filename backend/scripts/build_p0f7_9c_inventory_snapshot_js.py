"""Build the P0-F7.9C bounded network inventory collector.

Runs locally. Reads only the already-copied P0-F7.9A snapshot to derive the
mantenedora and academic year, then emits a small read-only mongosh collector.
The production collector performs counts only; it never reads students,
enrollments, grades or attendance and never mutates MongoDB.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

SOURCE_PHASE = "P0F7.9A-CURRICULAR-ALLOCATION-FORENSIC-SNAPSHOT-2026"
SOURCE_MODE = "READ_ONLY_BOUNDED_MONGOSH_CLASS_FORENSICS"
INVENTORY_PHASE = "P0F7.9C-NETWORK-CURRICULAR-INVENTORY-2026"
INVENTORY_MODE = "READ_ONLY_COUNTS_ONLY_TENANT_SCOPED"
QUERY_BUDGET = 6


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


def _source_context(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    if snapshot.get("phase") != SOURCE_PHASE or snapshot.get("mode") != SOURCE_MODE:
        raise ValueError("P0F7_9A_SOURCE_PHASE_OR_MODE_INVALID")
    if snapshot.get("query_budget") != 8 or snapshot.get("query_calls") != 8:
        raise ValueError("P0F7_9A_SOURCE_QUERY_BUDGET_INVALID")

    cls = snapshot.get("class") or {}
    tenant = _norm(cls.get("mantenedora_id"))
    year = int(cls.get("academic_year") or 0)
    if not tenant:
        raise ValueError("P0F7_9A_SOURCE_TENANT_MISSING_FAIL_CLOSED")
    if year <= 0:
        raise ValueError("P0F7_9A_SOURCE_ACADEMIC_YEAR_INVALID")

    return {
        "mantenedora_id": tenant,
        "academic_year": year,
        "source_p0f7_9a_snapshot_sha256": _canonical_sha256(snapshot),
    }


def build_js(snapshot: Mapping[str, Any], db_name: str) -> str:
    if not db_name or not all(ch.isalnum() or ch in "_.-" for ch in db_name):
        raise ValueError("DB_NAME_INVALID")

    ctx = _source_context(snapshot)
    request = json.dumps(ctx, ensure_ascii=False, separators=(",", ":"))
    database = json.dumps(db_name, ensure_ascii=False)
    phase = json.dumps(INVENTORY_PHASE)
    mode = json.dumps(INVENTORY_MODE)

    return f'''const PHASE = {phase};
const MODE = {mode};
const QUERY_BUDGET = {QUERY_BUDGET};
const req = {request};
const targetDb = db.getSiblingDB({database});
const tenant = String(req.mantenedora_id || "");
const year = Number(req.academic_year || 0);
if (!tenant) throw new Error("TENANT_MISSING_FAIL_CLOSED");
if (!year) throw new Error("ACADEMIC_YEAR_INVALID");
const yearFilter = {{$in:[year,String(year)]}};
const result = {{
  phase: PHASE,
  mode: MODE,
  generated_at_utc: new Date().toISOString(),
  mantenedora_id: tenant,
  academic_year: year,
  source_p0f7_9a_snapshot_sha256: req.source_p0f7_9a_snapshot_sha256,
  query_budget: QUERY_BUDGET,
  query_calls: 0,
  counts: {{}}
}};

result.counts.schools = targetDb.schools.countDocuments({{mantenedora_id:tenant}});
result.query_calls += 1;
result.counts.classes = targetDb.classes.countDocuments({{mantenedora_id:tenant,academic_year:yearFilter}});
result.query_calls += 1;
result.counts.classes_without_explicit_level = targetDb.classes.countDocuments({{
  mantenedora_id:tenant,
  academic_year:yearFilter,
  $and:[
    {{$or:[{{nivel_ensino:{{$exists:false}}}},{{nivel_ensino:null}},{{nivel_ensino:""}}]}},
    {{$or:[{{education_level:{{$exists:false}}}},{{education_level:null}},{{education_level:""}}]}}
  ]
}});
result.query_calls += 1;
result.counts.teacher_assignments = targetDb.teacher_assignments.countDocuments({{mantenedora_id:tenant,academic_year:yearFilter}});
result.query_calls += 1;
result.counts.active_teacher_assignments = targetDb.teacher_assignments.countDocuments({{
  mantenedora_id:tenant,
  academic_year:yearFilter,
  status:{{$in:["ativo","active"]}}
}});
result.query_calls += 1;
result.counts.courses = targetDb.courses.countDocuments({{mantenedora_id:tenant}});
result.query_calls += 1;

if (result.query_calls !== QUERY_BUDGET) {{
  throw new Error(`QUERY_BUDGET_MISMATCH_${{result.query_calls}}_${{QUERY_BUDGET}}`);
}}
print("P0F79C_INVENTORY_JSON=" + JSON.stringify(result));
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build P0-F7.9C tenant-scoped counts-only inventory collector")
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--db", required=True)
    parser.add_argument("--js", dest="js_path", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    js = build_js(_load(args.snapshot), args.db)
    args.js_path.parent.mkdir(parents=True, exist_ok=True)
    args.js_path.write_text(js, encoding="utf-8")
    print(f"P0F7_9C_INVENTORY_COLLECTOR_BUILT=YES path={args.js_path}")
    print(f"P0F7_9C_QUERY_BUDGET={QUERY_BUDGET}")
    print("PRODUCTION_WRITES=0")
    print("SENSITIVE_ACADEMIC_COLLECTIONS_READ=0")


if __name__ == "__main__":
    main()
