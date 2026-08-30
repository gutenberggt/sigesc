"""P0-F7.9D7.6 — materialize the explicitly authorized revised production executor.

This builder is local-only. It consumes the exact D7.5 manifest authorized by
the responsible human, validates the full hash chain and operation contract,
and materializes a mongosh writer plus immutable metadata.

The builder itself never connects to MongoDB/network and never executes the
writer. Production writes occur only if the generated JS is later sent to
mongosh by an operator.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

MANIFEST_PHASE = "P0F7.9D7.5-SEALED-REVISED-EXECUTOR-MANIFEST-2026"
MANIFEST_MODE = "LOCAL_OFFLINE_EXECUTOR_SPECIFICATION_NON_EXECUTABLE"
OUTPUT_PHASE = "P0F7.9D7.6-AUTHORIZED-REVISED-PRODUCTION-EXECUTOR-2026"
EXPECTED_MANIFEST_SHA256 = (
    "89e0f72d97f7cfa8b2d4b5dd7b5d35a01376a813d69d46f5bce7fa9c11440fcc"
)
EXPECTED_REVISED_PLAN_SHA256 = (
    "b6cfcfd3fec964fe58ebdcc7aea6e9fe1953207d7178da35b7e1bd4dea8c39fb"
)
EXPECTED_D74_REPORT_SHA256 = (
    "b835f5393e035dee0703f1aa0ae0dd52c779b81d5f73b8c05d0adff3fbcedc9e"
)
EXPECTED_OPERATIONS = 23
EXPECTED_STRATEGY = "CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED"
AUTHORIZATION_MARKER = (
    "P0-F7.9D7.6-EXPLICIT-MANIFEST-"
    "89e0f72d97f7cfa8b2d4b5dd7b5d35a01376a813d69d46f5bce7fa9c11440fcc-"
    "AUTHORIZED-2026-08-30"
)
ACTIVE_STATUSES = ("active", "ativo")


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


def _unsigned_hash(payload: Mapping[str, Any], field: str) -> str:
    unsigned = dict(payload)
    unsigned.pop(field, None)
    return _canonical_sha256(unsigned)


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return payload


def _validate_operation(op: Mapping[str, Any], expected_index: int) -> dict[str, Any]:
    index = int(op.get("operation_index") or 0)
    op_type = _norm(op.get("operation_type"))
    scope = dict(op.get("scope") or {})
    cas = dict(op.get("cas_expected") or {})
    set_fields = dict(op.get("set_fields") or {})
    rollback = dict(op.get("rollback_set_fields") or {})

    if index != expected_index:
        raise ValueError("P0F7_9D76_OPERATION_SEQUENCE_INVALID")
    for field in ("mantenedora_id", "school_id", "class_id", "assignment_id"):
        if not _norm(scope.get(field)):
            raise ValueError("P0F7_9D76_OPERATION_SCOPE_INVALID")
    if int(scope.get("academic_year") or 0) <= 0:
        raise ValueError("P0F7_9D76_OPERATION_YEAR_INVALID")
    if op.get("d74_preflight") != "CAS_DRY_RUN_CLEAR":
        raise ValueError("P0F7_9D76_OPERATION_NOT_D74_CLEAR")

    if op_type == "REMAP_COURSE":
        if set(set_fields) != {"course_id"} or set(rollback) != {"course_id"}:
            raise ValueError("P0F7_9D76_REMAP_FIELDS_INVALID")
        if not _norm(cas.get("course_id")):
            raise ValueError("P0F7_9D76_REMAP_CAS_INVALID")
        if _norm(set_fields.get("course_id")) == _norm(rollback.get("course_id")):
            raise ValueError("P0F7_9D76_REMAP_NOOP_FORBIDDEN")
    elif op_type == "RETIRE_DUPLICATE_ASSIGNMENT":
        if set_fields != {"status": "inativo"} or set(rollback) != {"status"}:
            raise ValueError("P0F7_9D76_RETIRE_FIELDS_INVALID")
        if _norm(cas.get("status")) != "ativo_or_active":
            raise ValueError("P0F7_9D76_RETIRE_STATUS_CAS_INVALID")
        if "carga_horaria_semanal" not in cas or not _norm(cas.get("course_id")):
            raise ValueError("P0F7_9D76_RETIRE_CAS_INVALID")
    elif op_type == "CONSOLIDATE_SURVIVOR":
        if "course_id" not in set_fields or "course_id" not in rollback:
            raise ValueError("P0F7_9D76_SURVIVOR_FIELDS_INVALID")
        if not _norm(set_fields.get("course_id")) or not _norm(cas.get("course_id")):
            raise ValueError("P0F7_9D76_SURVIVOR_COURSE_INVALID")
        if "carga_horaria_semanal" not in cas:
            raise ValueError("P0F7_9D76_SURVIVOR_WORKLOAD_CAS_REQUIRED")
        if (
            "carga_horaria_semanal" in set_fields
            and int(set_fields["carga_horaria_semanal"]) != 2
        ):
            raise ValueError("P0F7_9D76_SURVIVOR_WORKLOAD_INVALID")
    else:
        raise ValueError("P0F7_9D76_OPERATION_TYPE_INVALID")

    return {
        "operation_index": index,
        "operation_type": op_type,
        "scope": {
            "mantenedora_id": _norm(scope["mantenedora_id"]),
            "academic_year": int(scope["academic_year"]),
            "school_id": _norm(scope["school_id"]),
            "class_id": _norm(scope["class_id"]),
            "assignment_id": _norm(scope["assignment_id"]),
        },
        "cas_expected": cas,
        "set_fields": set_fields,
        "rollback_set_fields": rollback,
    }


def validate_manifest(
    manifest: Mapping[str, Any],
    *,
    expected_manifest_sha: str = EXPECTED_MANIFEST_SHA256,
) -> dict[str, Any]:
    if (
        manifest.get("phase") != MANIFEST_PHASE
        or manifest.get("status") != "PASS"
        or manifest.get("mode") != MANIFEST_MODE
    ):
        raise ValueError("P0F7_9D76_MANIFEST_INVALID")

    manifest_sha = _norm(manifest.get("manifest_sha256"))
    if not manifest_sha or manifest_sha != _unsigned_hash(manifest, "manifest_sha256"):
        raise ValueError("P0F7_9D76_MANIFEST_SHA_INVALID")
    if manifest_sha != expected_manifest_sha:
        raise ValueError("P0F7_9D76_MANIFEST_NOT_EXPLICITLY_AUTHORIZED")

    if _norm(manifest.get("source_revised_plan_sha256")) != EXPECTED_REVISED_PLAN_SHA256:
        raise ValueError("P0F7_9D76_REVISED_PLAN_CHAIN_MISMATCH")
    if _norm(manifest.get("source_d74_report_sha256")) != EXPECTED_D74_REPORT_SHA256:
        raise ValueError("P0F7_9D76_D74_CHAIN_MISMATCH")
    if manifest.get("strategy") != EXPECTED_STRATEGY:
        raise ValueError("P0F7_9D76_STRATEGY_DRIFT")

    summary = manifest.get("summary") or {}
    exact_counts = {
        "operations": EXPECTED_OPERATIONS,
        "remap_course": 21,
        "retire_duplicate_assignment": 1,
        "consolidate_survivor": 1,
        "cas_preflight_clear": EXPECTED_OPERATIONS,
    }
    for field, expected in exact_counts.items():
        if int(summary.get(field) or 0) != expected:
            raise ValueError(f"P0F7_9D76_MANIFEST_SUMMARY_INVALID:{field}")
    for field in (
        "forward_simulation_clear",
        "pair_postconditions_clear",
        "rollback_simulation_clear",
        "manifest_ready_for_explicit_authorization",
    ):
        if summary.get(field) is not True:
            raise ValueError(f"P0F7_9D76_MANIFEST_GATE_CLOSED:{field}")
    for field in (
        "production_write_authorized",
        "executor_authorized",
        "executor_materialized",
        "database_mutation",
        "production_writes",
        "remediation_executed",
    ):
        if summary.get(field) is not False:
            raise ValueError(f"P0F7_9D76_MANIFEST_UNSAFE_STATE:{field}")

    contract = manifest.get("execution_contract") or {}
    if (
        contract.get("executable") is not False
        or contract.get("writer_implementation_present") is not False
        or contract.get("executor_materialized") is not False
        or contract.get("requires_separate_explicit_production_write_authorization") is not True
        or contract.get("authorization_must_pin_manifest_sha256") is not True
        or contract.get("authorization_must_pin_revised_plan_sha256") is not True
        or contract.get("authorization_must_pin_d74_report_sha256") is not True
        or contract.get("old_23_write_authorization_reusable") is not False
        or contract.get("failure_policy") != "FAIL_CLOSED_NO_PARTIAL_GUESSING"
        or contract.get("required_execution_strategy") != EXPECTED_STRATEGY
        or contract.get("required_operation_order") != "SEALED_OPERATION_INDEX_ASC"
        or contract.get("required_pair_order")
        != "RETIRE_DUPLICATE_BEFORE_CONSOLIDATE_SURVIVOR"
        or contract.get("required_rollback_order") != "REVERSE_OPERATION_ORDER"
        or contract.get("hard_delete_allowed") is not False
    ):
        raise ValueError("P0F7_9D76_EXECUTION_CONTRACT_INVALID")

    safety = manifest.get("safety") or {}
    if (
        safety.get("production_access") is not False
        or safety.get("database_mutation") is not False
        or safety.get("production_writes") is not False
        or safety.get("remediation_executed") is not False
        or int(safety.get("student_records_read") or 0) != 0
        or int(safety.get("teacher_names_read") or 0) != 0
        or safety.get("staff_id_exposed") is not False
        or safety.get("hard_delete_allowed") is not False
    ):
        raise ValueError("P0F7_9D76_MANIFEST_SAFETY_INVALID")

    raw_operations = list(manifest.get("operations") or [])
    if len(raw_operations) != EXPECTED_OPERATIONS:
        raise ValueError("P0F7_9D76_OPERATION_COUNT_INVALID")
    operations = [
        _validate_operation(op, index)
        for index, op in enumerate(raw_operations, start=1)
    ]
    types = [op["operation_type"] for op in operations]
    if types.count("REMAP_COURSE") != 21:
        raise ValueError("P0F7_9D76_REMAP_COUNT_INVALID")
    if types[-2:] != ["RETIRE_DUPLICATE_ASSIGNMENT", "CONSOLIDATE_SURVIVOR"]:
        raise ValueError("P0F7_9D76_PAIR_ORDER_INVALID")

    assignment_ids = [op["scope"]["assignment_id"] for op in operations]
    if len(set(assignment_ids)) != EXPECTED_OPERATIONS:
        raise ValueError("P0F7_9D76_ASSIGNMENT_ID_DUPLICATE")

    tenants = {op["scope"]["mantenedora_id"] for op in operations}
    years = {op["scope"]["academic_year"] for op in operations}
    if len(tenants) != 1 or len(years) != 1:
        raise ValueError("P0F7_9D76_CONTEXT_DRIFT")

    tenant = next(iter(tenants))
    year = next(iter(years))
    if _norm(manifest.get("mantenedora_id")) != tenant:
        raise ValueError("P0F7_9D76_TENANT_DRIFT")
    if int(manifest.get("academic_year") or 0) != year:
        raise ValueError("P0F7_9D76_YEAR_DRIFT")

    return {
        "phase": OUTPUT_PHASE,
        "authorization_marker": AUTHORIZATION_MARKER,
        "manifest_sha256": manifest_sha,
        "source_revised_plan_sha256": EXPECTED_REVISED_PLAN_SHA256,
        "source_d74_report_sha256": EXPECTED_D74_REPORT_SHA256,
        "mantenedora_id": tenant,
        "academic_year": year,
        "strategy": EXPECTED_STRATEGY,
        "operations": operations,
    }


_JS_TEMPLATE = r'''const ctx = __CTX__;
const AUTHORIZATION_MARKER = __AUTH__;
const ACTIVE_STATUSES = __ACTIVE__;
const RECEIPT_PREFIX = "P0F79D76_EXECUTION_RECEIPT=";
const targetDb = db.getSiblingDB(__DB__);
const tenant = String(ctx.mantenedora_id || "");
const year = Number(ctx.academic_year || 0);
const yearFilter = {$in:[year,String(year)]};

if (ctx.phase !== "__OUTPUT_PHASE__") throw new Error("P0F79D76_PHASE_INVALID");
if (ctx.authorization_marker !== AUTHORIZATION_MARKER) throw new Error("P0F79D76_AUTHORIZATION_MARKER_INVALID");
if (ctx.manifest_sha256 !== "__MANIFEST_SHA__") throw new Error("P0F79D76_MANIFEST_SHA_INVALID");
if (ctx.source_revised_plan_sha256 !== "__PLAN_SHA__") throw new Error("P0F79D76_REVISED_PLAN_SHA_INVALID");
if (ctx.source_d74_report_sha256 !== "__D74_SHA__") throw new Error("P0F79D76_D74_SHA_INVALID");
if (ctx.strategy !== "__STRATEGY__") throw new Error("P0F79D76_STRATEGY_INVALID");
if (!tenant || !year || !Array.isArray(ctx.operations) || ctx.operations.length !== 23) {
  throw new Error("P0F79D76_CONTEXT_INVALID");
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
function baseScope(op) {
  return {
    mantenedora_id: tenant,
    academic_year: yearFilter,
    school_id: String(op.scope.school_id),
    class_id: String(op.scope.class_id),
    id: String(op.scope.assignment_id)
  };
}
function casFilter(op) {
  const f = baseScope(op);
  const expected = op.cas_expected || {};
  Object.keys(expected).forEach((field) => {
    const value = expected[field];
    if (field === "status" && norm(value) === "ativo_or_active") {
      f.status = {$in:["active","ativo"]};
    } else {
      f[field] = value;
    }
  });
  return f;
}
function rollbackCasFilter(op) {
  const f = baseScope(op);
  const after = op.set_fields || {};
  Object.keys(after).forEach((field) => { f[field] = after[field]; });
  return f;
}
function checkFields(doc, fields, code) {
  Object.keys(fields || {}).forEach((field) => {
    if (!sameValue(doc[field], fields[field])) throw new Error(code + ":" + field);
  });
}
function collisionFor(doc, op, setFields) {
  const afterStatus = Object.prototype.hasOwnProperty.call(setFields, "status")
    ? setFields.status : doc.status;
  if (!active(afterStatus)) return null;
  const afterCourse = Object.prototype.hasOwnProperty.call(setFields, "course_id")
    ? setFields.course_id : doc.course_id;
  if (!norm(afterCourse)) throw new Error("P0F79D76_TARGET_COURSE_EMPTY");
  return targetDb.teacher_assignments.findOne({
    mantenedora_id: tenant,
    academic_year: yearFilter,
    school_id: String(op.scope.school_id),
    class_id: String(op.scope.class_id),
    staff_id: String(doc.staff_id),
    course_id: String(afterCourse),
    status: {$in:["active","ativo"]},
    id: {$ne:String(op.scope.assignment_id)}
  }, {projection:{_id:0,id:1}});
}
function receiptBase() {
  return {
    phase: ctx.phase,
    manifest_sha256: ctx.manifest_sha256,
    source_revised_plan_sha256: ctx.source_revised_plan_sha256,
    source_d74_report_sha256: ctx.source_d74_report_sha256,
    strategy: ctx.strategy,
    expected_operations: 23,
    hard_delete: false,
    generated_at_utc: new Date().toISOString()
  };
}
function emitReceipt(payload) { print(RECEIPT_PREFIX + JSON.stringify(payload)); }

const applied = [];
let forwardWrites = 0;
let rollbackWrites = 0;

try {
  // Global CAS gate before the first write.
  ctx.operations.forEach((op) => {
    const doc = targetDb.teacher_assignments.findOne(
      casFilter(op),
      {projection:{_id:0,id:1,staff_id:1,status:1,course_id:1,carga_horaria_semanal:1}}
    );
    if (!doc) throw new Error("P0F79D76_GLOBAL_CAS_BLOCKED:" + op.operation_index);
    if (!norm(doc.staff_id)) throw new Error("P0F79D76_STAFF_ID_REQUIRED:" + op.operation_index);
  });

  for (const op of ctx.operations) {
    const before = targetDb.teacher_assignments.findOne(
      casFilter(op),
      {projection:{_id:0,id:1,staff_id:1,status:1,course_id:1,carga_horaria_semanal:1}}
    );
    if (!before) throw new Error("P0F79D76_IMMEDIATE_CAS_BLOCKED:" + op.operation_index);
    if (!norm(before.staff_id)) throw new Error("P0F79D76_STAFF_ID_REQUIRED:" + op.operation_index);

    const collision = collisionFor(before, op, op.set_fields || {});
    if (collision) {
      throw new Error("P0F79D76_IMMEDIATE_COLLISION:" + op.operation_index + ":" + String(collision.id));
    }

    const writeResult = targetDb.teacher_assignments.updateOne(casFilter(op), {$set:op.set_fields});
    if (Number(writeResult.matchedCount || 0) !== 1 || Number(writeResult.modifiedCount || 0) !== 1) {
      throw new Error("P0F79D76_FORWARD_CAS_WRITE_FAILED:" + op.operation_index);
    }
    forwardWrites += 1;
    applied.push(op);

    const after = targetDb.teacher_assignments.findOne(
      baseScope(op),
      {projection:{_id:0,id:1,staff_id:1,status:1,course_id:1,carga_horaria_semanal:1}}
    );
    if (!after) throw new Error("P0F79D76_FORWARD_POST_MISSING:" + op.operation_index);
    checkFields(after, op.set_fields || {}, "P0F79D76_FORWARD_POST_MISMATCH:" + op.operation_index);
  }

  // Final uniqueness and pair postconditions. Any failure triggers full rollback.
  for (const op of ctx.operations) {
    const doc = targetDb.teacher_assignments.findOne(
      baseScope(op),
      {projection:{_id:0,id:1,staff_id:1,status:1,course_id:1,carga_horaria_semanal:1}}
    );
    if (!doc) throw new Error("P0F79D76_FINAL_SOURCE_MISSING:" + op.operation_index);
    checkFields(doc, op.set_fields || {}, "P0F79D76_FINAL_FIELD_MISMATCH:" + op.operation_index);
    if (active(doc.status)) {
      const duplicateCount = targetDb.teacher_assignments.countDocuments({
        mantenedora_id: tenant,
        academic_year: yearFilter,
        school_id: String(op.scope.school_id),
        class_id: String(op.scope.class_id),
        staff_id: String(doc.staff_id),
        course_id: String(doc.course_id),
        status: {$in:["active","ativo"]}
      });
      if (Number(duplicateCount) !== 1) {
        throw new Error("P0F79D76_FINAL_ACTIVE_TUPLE_NOT_UNIQUE:" + op.operation_index);
      }
    }
  }

  const retire = ctx.operations[21];
  const survivor = ctx.operations[22];
  if (retire.operation_type !== "RETIRE_DUPLICATE_ASSIGNMENT" || survivor.operation_type !== "CONSOLIDATE_SURVIVOR") {
    throw new Error("P0F79D76_PAIR_ORDER_RUNTIME_INVALID");
  }
  const retiredDoc = targetDb.teacher_assignments.findOne(baseScope(retire));
  const survivorDoc = targetDb.teacher_assignments.findOne(baseScope(survivor));
  if (!retiredDoc || norm(retiredDoc.status).toLowerCase() !== "inativo") {
    throw new Error("P0F79D76_RETIRED_POSTCONDITION_FAILED");
  }
  if (!survivorDoc || !active(survivorDoc.status) ||
      norm(survivorDoc.course_id) !== norm(survivor.set_fields.course_id) ||
      Number(survivorDoc.carga_horaria_semanal) !== 2) {
    throw new Error("P0F79D76_SURVIVOR_POSTCONDITION_FAILED");
  }

  const receipt = receiptBase();
  receipt.status = "APPLIED";
  receipt.forward_writes = forwardWrites;
  receipt.rollback_writes = rollbackWrites;
  receipt.mutation_operations = forwardWrites + rollbackWrites;
  receipt.remediation_executed = true;
  receipt.production_writes = true;
  receipt.rollback_complete = true;
  receipt.operation_results = ctx.operations.map((op) => ({
    operation_index: op.operation_index,
    operation_type: op.operation_type,
    assignment_id: op.scope.assignment_id,
    state: "APPLIED"
  }));
  emitReceipt(receipt);
} catch (err) {
  const failure = String(err && err.message ? err.message : err);
  const rollbackFailures = [];

  for (let i = applied.length - 1; i >= 0; i -= 1) {
    const op = applied[i];
    try {
      const rollbackResult = targetDb.teacher_assignments.updateOne(
        rollbackCasFilter(op), {$set:op.rollback_set_fields}
      );
      if (Number(rollbackResult.matchedCount || 0) !== 1 || Number(rollbackResult.modifiedCount || 0) !== 1) {
        throw new Error("ROLLBACK_CAS_WRITE_FAILED");
      }
      rollbackWrites += 1;
      const restored = targetDb.teacher_assignments.findOne(
        baseScope(op),
        {projection:{_id:0,id:1,status:1,course_id:1,carga_horaria_semanal:1}}
      );
      if (!restored) throw new Error("ROLLBACK_POST_MISSING");
      checkFields(restored, op.rollback_set_fields || {}, "ROLLBACK_POST_MISMATCH:" + op.operation_index);
    } catch (rbErr) {
      rollbackFailures.push({
        operation_index: op.operation_index,
        error: String(rbErr && rbErr.message ? rbErr.message : rbErr)
      });
    }
  }

  const receipt = receiptBase();
  receipt.status = rollbackFailures.length === 0 ? "SAFE_ROLLBACK" : "ROLLBACK_INCOMPLETE";
  receipt.failure = failure;
  receipt.forward_writes = forwardWrites;
  receipt.rollback_writes = rollbackWrites;
  receipt.mutation_operations = forwardWrites + rollbackWrites;
  receipt.remediation_executed = false;
  receipt.production_writes = forwardWrites > 0 || rollbackWrites > 0;
  receipt.rollback_complete = rollbackFailures.length === 0 && rollbackWrites === forwardWrites;
  receipt.rollback_failures = rollbackFailures;
  emitReceipt(receipt);

  if (rollbackFailures.length > 0) throw new Error("P0F79D76_ROLLBACK_INCOMPLETE:" + failure);
  throw new Error("P0F79D76_SAFE_ROLLBACK:" + failure);
}
'''


def build_executor(
    manifest: Mapping[str, Any],
    db_name: str,
    *,
    authorized: bool,
    expected_manifest_sha: str = EXPECTED_MANIFEST_SHA256,
) -> tuple[str, dict[str, Any]]:
    if authorized is not True:
        raise ValueError("P0F7_9D76_EXPLICIT_PRODUCTION_AUTHORIZATION_REQUIRED")
    if not db_name or not all(ch.isalnum() or ch in "_.-" for ch in db_name):
        raise ValueError("DB_NAME_INVALID")

    ctx = validate_manifest(manifest, expected_manifest_sha=expected_manifest_sha)
    js = (
        _JS_TEMPLATE
        .replace("__CTX__", json.dumps(ctx, ensure_ascii=False, separators=(",", ":")))
        .replace("__AUTH__", json.dumps(AUTHORIZATION_MARKER))
        .replace("__ACTIVE__", json.dumps(list(ACTIVE_STATUSES)))
        .replace("__DB__", json.dumps(db_name))
        .replace("__OUTPUT_PHASE__", OUTPUT_PHASE)
        .replace("__MANIFEST_SHA__", expected_manifest_sha)
        .replace("__PLAN_SHA__", EXPECTED_REVISED_PLAN_SHA256)
        .replace("__D74_SHA__", EXPECTED_D74_REPORT_SHA256)
        .replace("__STRATEGY__", EXPECTED_STRATEGY)
    )
    executor_sha = hashlib.sha256(js.encode("utf-8")).hexdigest()
    metadata = {
        "phase": OUTPUT_PHASE,
        "status": "PASS",
        "manifest_sha256": ctx["manifest_sha256"],
        "source_revised_plan_sha256": ctx["source_revised_plan_sha256"],
        "source_d74_report_sha256": ctx["source_d74_report_sha256"],
        "authorization_marker": AUTHORIZATION_MARKER,
        "strategy": EXPECTED_STRATEGY,
        "expected_operations": EXPECTED_OPERATIONS,
        "executor_sha256": executor_sha,
        "executor_materialized": True,
        "production_write_authorized": True,
        "executor_authorized": True,
        "execution_performed": False,
        "database_mutation": False,
        "production_writes": False,
        "hard_delete_allowed": False,
    }
    metadata["metadata_sha256"] = _canonical_sha256(metadata)
    return js, metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize authorized P0-F7.9D7.6 revised mongosh executor"
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--db", default="sigesc")
    parser.add_argument("--js", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--authorize-production-writes", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    js, metadata = build_executor(
        _load(args.manifest),
        args.db,
        authorized=args.authorize_production_writes,
    )
    args.js.parent.mkdir(parents=True, exist_ok=True)
    args.metadata.parent.mkdir(parents=True, exist_ok=True)
    args.js.write_text(js, encoding="utf-8", newline="\n")
    args.metadata.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("P0F7_9D76_AUTHORIZED_EXECUTOR_MATERIALIZED=YES")
    print(f"MANIFEST_SHA256={metadata['manifest_sha256']}")
    print(f"EXECUTOR_SHA256={metadata['executor_sha256']}")
    print(f"METADATA_SHA256={metadata['metadata_sha256']}")
    print(f"EXECUTOR={args.js}")
    print(f"METADATA={args.metadata}")
    print("PRODUCTION_WRITE_AUTHORIZED=YES")
    print("EXECUTOR_AUTHORIZED=YES")
    print("EXECUTION_PERFORMED=NO")
    print("DATABASE_MUTATION=NO")
    print("PRODUCTION_WRITES=NO")


if __name__ == "__main__":
    main()
