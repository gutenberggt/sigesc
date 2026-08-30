"""P0-F7.9D7.7 — build the read-only post-execution verifier.

The verifier consumes the exact D7.5 manifest, reuses the reviewed D7.6.3
manifest contract, and emits a mongosh program that performs only bounded
reads. It verifies the final state of all 23 authorized teacher-assignment
operations plus active-tuple uniqueness and the adjudicated duplicate pair.

This module performs no network or database access itself.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any, Mapping

D763_BUILDER_PATH = Path(__file__).with_name(
    "build_p0f7_9d763_authorized_revised_executor_js.py"
)
_spec = importlib.util.spec_from_file_location("p0f7_9d763_builder", D763_BUILDER_PATH)
if not _spec or not _spec.loader:
    raise RuntimeError("P0F7_9D77_D763_BUILDER_IMPORT_FAILED")
d763 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(d763)

EXPECTED_MANIFEST_SHA256 = d763.d761.d76.EXPECTED_MANIFEST_SHA256
EXPECTED_REVISED_PLAN_SHA256 = d763.d761.d76.EXPECTED_REVISED_PLAN_SHA256
EXPECTED_D74_REPORT_SHA256 = d763.d761.d76.EXPECTED_D74_REPORT_SHA256
EXPECTED_OPERATIONS = 23
EXPECTED_ACTIVE_FINAL_ASSIGNMENTS = 22
OUTPUT_PHASE = "P0F7.9D7.7-POST-EXECUTION-VERIFICATION-2026"
MARKER = "P0F79D77_POST_EXECUTION_JSON="
ACTIVE_STATUSES = ("active", "ativo")


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return payload


_JS_TEMPLATE = r'''const ctx = __CTX__;
const ACTIVE_STATUSES = __ACTIVE__;
const targetDb = db.getSiblingDB(__DB__);
const tenant = String(ctx.mantenedora_id || "");
const year = Number(ctx.academic_year || 0);
const yearFilter = {$in:[year,String(year)]};
const MARKER = "__MARKER__";

if (ctx.manifest_sha256 !== "__MANIFEST_SHA__") throw new Error("P0F79D77_MANIFEST_SHA_INVALID");
if (ctx.source_revised_plan_sha256 !== "__PLAN_SHA__") throw new Error("P0F79D77_PLAN_SHA_INVALID");
if (ctx.source_d74_report_sha256 !== "__D74_SHA__") throw new Error("P0F79D77_D74_SHA_INVALID");
if (!tenant || !year || !Array.isArray(ctx.operations) || ctx.operations.length !== 23) {
  throw new Error("P0F79D77_CONTEXT_INVALID");
}

function norm(v) {
  return v === null || v === undefined ? "" : String(v).trim();
}
function active(v) {
  return ACTIVE_STATUSES.indexOf(norm(v).toLowerCase()) >= 0;
}
function sameValue(a, b) {
  if ((typeof a === "number") || (typeof b === "number")) {
    const na = Number(a);
    const nb = Number(b);
    if (!Number.isNaN(na) && !Number.isNaN(nb)) return na === nb;
  }
  return norm(a) === norm(b);
}
function checkFields(doc, fields, code) {
  Object.keys(fields || {}).forEach((field) => {
    if (!sameValue(doc[field], fields[field])) throw new Error(code + ":" + field);
  });
}
function sameTuple(a, b) {
  return norm(a.mantenedora_id) === norm(b.mantenedora_id) &&
    Number(a.academic_year) === Number(b.academic_year) &&
    norm(a.school_id) === norm(b.school_id) &&
    norm(a.class_id) === norm(b.class_id) &&
    norm(a.staff_id) === norm(b.staff_id) &&
    norm(a.course_id) === norm(b.course_id) &&
    active(a.status) && active(b.status);
}

const assignmentIds = ctx.operations.map((op) => String(op.scope.assignment_id));
const projection = {
  _id:0,id:1,mantenedora_id:1,academic_year:1,school_id:1,class_id:1,
  staff_id:1,status:1,course_id:1,carga_horaria_semanal:1
};

// Query 1: all 23 affected assignments in a single bounded read.
const docs = targetDb.teacher_assignments.find({
  mantenedora_id: tenant,
  academic_year: yearFilter,
  id: {$in: assignmentIds}
}, projection).toArray();

if (docs.length !== 23) throw new Error("P0F79D77_AFFECTED_DOCUMENT_COUNT_INVALID:" + docs.length);
const byId = new Map();
docs.forEach((doc) => {
  const id = norm(doc.id);
  if (!id || byId.has(id)) throw new Error("P0F79D77_DUPLICATE_OR_EMPTY_ID");
  byId.set(id, doc);
});

const activeDocs = [];
ctx.operations.forEach((op) => {
  const doc = byId.get(String(op.scope.assignment_id));
  if (!doc) throw new Error("P0F79D77_SOURCE_MISSING:" + op.operation_index);
  if (norm(doc.mantenedora_id) !== tenant || Number(doc.academic_year) !== year ||
      norm(doc.school_id) !== norm(op.scope.school_id) ||
      norm(doc.class_id) !== norm(op.scope.class_id)) {
    throw new Error("P0F79D77_SCOPE_DRIFT:" + op.operation_index);
  }
  if (!norm(doc.staff_id)) throw new Error("P0F79D77_STAFF_ID_MISSING:" + op.operation_index);
  checkFields(doc, op.set_fields || {}, "P0F79D77_FINAL_FIELD_MISMATCH:" + op.operation_index);

  if (op.operation_type === "RETIRE_DUPLICATE_ASSIGNMENT") {
    if (norm(doc.status).toLowerCase() !== "inativo") {
      throw new Error("P0F79D77_RETIREMENT_NOT_INACTIVE");
    }
  } else {
    if (!active(doc.status)) throw new Error("P0F79D77_EXPECTED_ACTIVE_NOT_ACTIVE:" + op.operation_index);
    activeDocs.push(doc);
  }
});

if (activeDocs.length !== 22) {
  throw new Error("P0F79D77_ACTIVE_FINAL_COUNT_INVALID:" + activeDocs.length);
}

const tupleFilters = activeDocs.map((doc) => ({
  mantenedora_id: tenant,
  academic_year: yearFilter,
  school_id: String(doc.school_id),
  class_id: String(doc.class_id),
  staff_id: String(doc.staff_id),
  course_id: String(doc.course_id),
  status: {$in:ACTIVE_STATUSES}
}));

// Query 2: all possible active tuple collisions in one bounded OR read.
const candidates = targetDb.teacher_assignments.find({$or:tupleFilters}, projection).toArray();
activeDocs.forEach((doc) => {
  const matches = candidates.filter((candidate) => sameTuple(candidate, doc));
  if (matches.length !== 1 || norm(matches[0].id) !== norm(doc.id)) {
    throw new Error("P0F79D77_ACTIVE_TUPLE_NOT_UNIQUE:" + norm(doc.id) + ":" + matches.length);
  }
});

const retire = ctx.operations[21];
const survivor = ctx.operations[22];
if (retire.operation_type !== "RETIRE_DUPLICATE_ASSIGNMENT" ||
    survivor.operation_type !== "CONSOLIDATE_SURVIVOR") {
  throw new Error("P0F79D77_PAIR_ORDER_INVALID");
}
const retiredDoc = byId.get(String(retire.scope.assignment_id));
const survivorDoc = byId.get(String(survivor.scope.assignment_id));
if (!retiredDoc || norm(retiredDoc.status).toLowerCase() !== "inativo") {
  throw new Error("P0F79D77_RETIRED_POSTCONDITION_FAILED");
}
if (!survivorDoc || !active(survivorDoc.status) ||
    norm(survivorDoc.course_id) !== norm(survivor.set_fields.course_id) ||
    Number(survivorDoc.carga_horaria_semanal) !== 2) {
  throw new Error("P0F79D77_SURVIVOR_POSTCONDITION_FAILED");
}

print(MARKER + JSON.stringify({
  phase:"__OUTPUT_PHASE__",
  status:"PASS",
  manifest_sha256:ctx.manifest_sha256,
  source_revised_plan_sha256:ctx.source_revised_plan_sha256,
  source_d74_report_sha256:ctx.source_d74_report_sha256,
  operations_verified:23,
  documents_verified:23,
  active_final_assignments:22,
  active_unique_tuples_verified:22,
  retired_duplicate_verified:true,
  survivor_verified:true,
  survivor_canonical_weekly_workload:2,
  query_budget:2,
  query_calls:2,
  student_records_read:0,
  teacher_names_read:0,
  database_mutation:false,
  production_writes:0,
  remediation_final_state_verified:true,
  hard_delete:false,
  verified_at_utc:new Date().toISOString()
}));
'''

BANNED_MUTATION_TOKENS = (
    ".updateOne(", ".updateMany(", ".replaceOne(", ".deleteOne(", ".deleteMany(",
    ".insertOne(", ".insertMany(", ".bulkWrite(", ".findOneAndUpdate(",
    ".findOneAndDelete(", ".findOneAndReplace(",
)


def build_verifier(manifest: Mapping[str, Any], db_name: str) -> str:
    if not db_name or not all(ch.isalnum() or ch in "_.-" for ch in db_name):
        raise ValueError("DB_NAME_INVALID")
    ctx = d763.d761.d76.validate_manifest(manifest)
    js = (
        _JS_TEMPLATE
        .replace("__CTX__", json.dumps(ctx, ensure_ascii=False, separators=(",", ":")))
        .replace("__ACTIVE__", json.dumps(list(ACTIVE_STATUSES)))
        .replace("__DB__", json.dumps(db_name))
        .replace("__MARKER__", MARKER)
        .replace("__OUTPUT_PHASE__", OUTPUT_PHASE)
        .replace("__MANIFEST_SHA__", EXPECTED_MANIFEST_SHA256)
        .replace("__PLAN_SHA__", EXPECTED_REVISED_PLAN_SHA256)
        .replace("__D74_SHA__", EXPECTED_D74_REPORT_SHA256)
    )
    for token in BANNED_MUTATION_TOKENS:
        if token in js:
            raise ValueError(f"P0F7_9D77_MUTATION_PRIMITIVE_FORBIDDEN:{token}")
    if js.count("teacher_assignments.find(") != 2:
        raise ValueError("P0F7_9D77_QUERY_BUDGET_DRIFT")
    return js


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build P0-F7.9D7.7 read-only post-execution verifier")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--db", default="sigesc")
    parser.add_argument("--js", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    js = build_verifier(_load(args.manifest), args.db)
    args.js.parent.mkdir(parents=True, exist_ok=True)
    args.js.write_text(js, encoding="utf-8", newline="\n")
    print("P0F7_9D77_POST_EXECUTION_VERIFIER_BUILT=YES")
    print(f"MANIFEST_SHA256={EXPECTED_MANIFEST_SHA256}")
    print("QUERY_BUDGET=2")
    print("DATABASE_MUTATION=NO")
    print("PRODUCTION_WRITES=NO")
    print(f"VERIFIER={args.js}")


if __name__ == "__main__":
    main()
