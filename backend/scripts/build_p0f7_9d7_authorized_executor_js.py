"""Build the explicitly authorized P0-F7.9D7 mongosh executor.

This builder runs locally only. It consumes the sealed D4 plan, a freshly
revalidated D5 report, and the D6 dry-run package/report. The generated JS is
the only production-writing artifact: it applies exactly 23 ``course_id``
changes to ``teacher_assignments`` using per-document compare-and-swap (CAS),
rechecks duplicate collisions immediately around each write, verifies
postconditions, and performs compensating rollback in reverse order on any
failure.

The builder is fail-closed and requires an explicit authorization flag. It
never connects to MongoDB itself and never embeds credentials.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

PLAN_PHASE = "P0F7.9D4-SEALED-REMEDIATION-PLAN-2026"
PLAN_MODE = "SEALED_PROPOSAL_ONLY_NON_EXECUTABLE"
D5_PHASE = "P0F7.9D5-OFFLINE-LAST-MILE-PREFLIGHT-2026"
D6_PACKAGE_PHASE = "P0F7.9D6-CAS-DRY-RUN-PACKAGE-2026"
D6_PACKAGE_MODE = "DRY_RUN_ONLY_NON_EXECUTABLE"
D6_REPORT_PHASE = "P0F7.9D6-OFFLINE-CAS-DRY-RUN-2026"
OUTPUT_PHASE = "P0F7.9D7-AUTHORIZED-PRODUCTION-EXECUTOR-2026"
EXPECTED_ENTRIES = 23
EXPECTED_STRATEGY = "CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED"
AUTHORIZATION_MARKER = "P0-F7.9D7-EXPLICIT-23-WRITES-AUTHORIZED-2026-08-29"
AUTHORIZED_PLAN_SHA256 = "6d39d8425c0555b36b69c8f5d00832fc8f93e1c4f38c35c0f29ea8e72fcf1312"
ACTIVE_STATUSES = ["active", "ativo"]


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


def _unsigned_hash(payload: Mapping[str, Any], signature_field: str) -> str:
    unsigned = dict(payload)
    unsigned.pop(signature_field, None)
    return _canonical_sha256(unsigned)


def _validate_sources(
    plan: Mapping[str, Any],
    d5: Mapping[str, Any],
    package: Mapping[str, Any],
    d6_report: Mapping[str, Any],
) -> tuple[str, int, list[dict[str, Any]], dict[str, str]]:
    if plan.get("phase") != PLAN_PHASE or plan.get("status") != "PASS" or plan.get("mode") != PLAN_MODE:
        raise ValueError("P0F7_9D4_PLAN_INVALID")
    plan_sha = _norm(plan.get("plan_sha256"))
    if not plan_sha or plan_sha != _unsigned_hash(plan, "plan_sha256"):
        raise ValueError("P0F7_9D4_PLAN_SHA256_INVALID")
    if plan_sha != AUTHORIZED_PLAN_SHA256:
        raise ValueError("P0F7_9D7_PLAN_NOT_AUTHORIZED")
    if (plan.get("execution_contract") or {}).get("executable") is not False:
        raise ValueError("P0F7_9D4_PLAN_MUST_BE_NON_EXECUTABLE")

    plan_entries = list(plan.get("entries") or [])
    if len(plan_entries) != EXPECTED_ENTRIES:
        raise ValueError("P0F7_9D7_PLAN_ENTRY_COUNT_INVALID")
    plan_by_id: dict[str, Mapping[str, Any]] = {}
    for row in plan_entries:
        assignment_id = _norm((row or {}).get("assignment_id"))
        if not assignment_id or assignment_id in plan_by_id:
            raise ValueError("P0F7_9D7_PLAN_ENTRY_ID_INVALID_OR_DUPLICATE")
        plan_by_id[assignment_id] = row

    if d5.get("phase") != D5_PHASE or d5.get("status") != "PASS":
        raise ValueError("P0F7_9D5_REPORT_INVALID")
    d5_sha = _norm(d5.get("report_sha256"))
    if not d5_sha or d5_sha != _unsigned_hash(d5, "report_sha256"):
        raise ValueError("P0F7_9D5_REPORT_SHA256_INVALID")
    if _norm(d5.get("sealed_plan_sha256")) != plan_sha:
        raise ValueError("P0F7_9D7_D5_PLAN_CHAIN_MISMATCH")
    summary5 = d5.get("summary") or {}
    if int(summary5.get("sealed_entries") or 0) != EXPECTED_ENTRIES:
        raise ValueError("P0F7_9D7_D5_ENTRY_COUNT_INVALID")
    if int(summary5.get("clear_for_execution_authorization") or 0) != EXPECTED_ENTRIES:
        raise ValueError("P0F7_9D7_D5_NOT_ALL_CLEAR")
    for field in (
        "active_target_already_exists",
        "source_drift_review_required",
        "target_curriculum_rejected",
    ):
        if int(summary5.get(field) or 0) != 0:
            raise ValueError(f"P0F7_9D7_D5_BLOCKED:{field}")
    if summary5.get("proposal_only") is not True or summary5.get("production_write_authorized") is not False:
        raise ValueError("P0F7_9D7_D5_STATE_INVALID")
    topology = d5.get("topology") or {}
    if topology.get("multi_document_transactions_available") is not False:
        raise ValueError("P0F7_9D7_EXPECTED_STANDALONE_TOPOLOGY")
    if _norm(topology.get("required_future_execution_strategy")) != EXPECTED_STRATEGY:
        raise ValueError("P0F7_9D7_STRATEGY_DRIFT")

    d5_by_id: dict[str, Mapping[str, Any]] = {}
    for row in d5.get("results") or []:
        assignment_id = _norm((row or {}).get("assignment_id"))
        if not assignment_id or assignment_id in d5_by_id:
            raise ValueError("P0F7_9D7_D5_ENTRY_ID_INVALID_OR_DUPLICATE")
        d5_by_id[assignment_id] = row
    if len(d5_by_id) != EXPECTED_ENTRIES:
        raise ValueError("P0F7_9D7_D5_RESULT_COUNT_INVALID")

    if (
        package.get("phase") != D6_PACKAGE_PHASE
        or package.get("status") != "PASS"
        or package.get("mode") != D6_PACKAGE_MODE
    ):
        raise ValueError("P0F7_9D6_PACKAGE_INVALID")
    package_sha = _norm(package.get("package_sha256"))
    if not package_sha or package_sha != _unsigned_hash(package, "package_sha256"):
        raise ValueError("P0F7_9D6_PACKAGE_SHA256_INVALID")
    if _norm(package.get("sealed_plan_sha256")) != plan_sha:
        raise ValueError("P0F7_9D7_PACKAGE_PLAN_CHAIN_MISMATCH")
    if _norm(package.get("source_p0f7_9d5_report_sha256")) != d5_sha:
        raise ValueError("P0F7_9D7_PACKAGE_D5_CHAIN_MISMATCH")
    summary6 = package.get("summary") or {}
    execution6 = package.get("execution_contract") or {}
    if int(summary6.get("entries") or 0) != EXPECTED_ENTRIES:
        raise ValueError("P0F7_9D7_PACKAGE_ENTRY_COUNT_INVALID")
    if (
        summary6.get("dry_run_only") is not True
        or summary6.get("production_write_authorized") is not False
        or execution6.get("executable") is not False
        or execution6.get("writer_implementation_present") is not False
    ):
        raise ValueError("P0F7_9D7_PACKAGE_STATE_INVALID")
    if _norm(package.get("strategy")) != EXPECTED_STRATEGY:
        raise ValueError("P0F7_9D7_PACKAGE_STRATEGY_DRIFT")

    if d6_report.get("phase") != D6_REPORT_PHASE or d6_report.get("status") != "PASS":
        raise ValueError("P0F7_9D6_REPORT_INVALID")
    d6_report_sha = _norm(d6_report.get("report_sha256"))
    if not d6_report_sha or d6_report_sha != _unsigned_hash(d6_report, "report_sha256"):
        raise ValueError("P0F7_9D6_REPORT_SHA256_INVALID")
    if _norm(d6_report.get("package_sha256")) != package_sha:
        raise ValueError("P0F7_9D7_D6_REPORT_PACKAGE_CHAIN_MISMATCH")
    summary6r = d6_report.get("summary") or {}
    for field in ("entries", "cas_match_verified", "postconditions_verified", "rollback_verified"):
        if int(summary6r.get(field) or 0) != EXPECTED_ENTRIES:
            raise ValueError(f"P0F7_9D7_D6_REPORT_COUNT_INVALID:{field}")
    if int(summary6r.get("active_collisions") or 0) != 0:
        raise ValueError("P0F7_9D7_D6_REPORT_COLLISION")
    if (
        summary6r.get("dry_run_only") is not True
        or summary6r.get("production_write_authorized") is not False
        or summary6r.get("production_writes") is not False
        or summary6r.get("remediation_executed") is not False
    ):
        raise ValueError("P0F7_9D7_D6_REPORT_STATE_INVALID")

    tenant = _norm(plan.get("mantenedora_id"))
    year = int(plan.get("academic_year") or 0)
    if not tenant or year <= 0:
        raise ValueError("P0F7_9D7_CONTEXT_INVALID")
    if _norm(d5.get("mantenedora_id")) != tenant or int(d5.get("academic_year") or 0) != year:
        raise ValueError("P0F7_9D7_D5_CONTEXT_DRIFT")

    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    package_entries = list(package.get("entries") or [])
    if len(package_entries) != EXPECTED_ENTRIES:
        raise ValueError("P0F7_9D7_PACKAGE_ENTRY_COUNT_INVALID")
    for item in package_entries:
        assignment_id = _norm(item.get("assignment_id"))
        school_id = _norm(item.get("school_id"))
        class_id = _norm(item.get("class_id"))
        source_course_id = _norm(item.get("source_course_id"))
        target_course_id = _norm(item.get("target_course_id"))
        ordinal = int(item.get("ordinal") or 0)
        if (
            not assignment_id
            or assignment_id in seen
            or not school_id
            or not class_id
            or not source_course_id
            or not target_course_id
            or source_course_id == target_course_id
            or ordinal <= 0
        ):
            raise ValueError("P0F7_9D7_ENTRY_INVALID")
        seen.add(assignment_id)

        plan_row = plan_by_id.get(assignment_id)
        if not plan_row:
            raise ValueError(f"P0F7_9D7_PACKAGE_ENTRY_NOT_IN_AUTHORIZED_PLAN:{assignment_id}")
        expected_plan = {
            "ordinal": int(plan_row.get("ordinal") or 0),
            "school_id": _norm(plan_row.get("school_id")),
            "class_id": _norm(plan_row.get("class_id")),
            "source_course_id": _norm((plan_row.get("source") or {}).get("course_id")),
            "target_course_id": _norm((plan_row.get("target") or {}).get("course_id")),
        }
        actual = {
            "ordinal": ordinal,
            "school_id": school_id,
            "class_id": class_id,
            "source_course_id": source_course_id,
            "target_course_id": target_course_id,
        }
        if actual != expected_plan:
            raise ValueError(f"P0F7_9D7_PACKAGE_ENTRY_AUTHORIZED_PLAN_DRIFT:{assignment_id}")

        d5_row = d5_by_id.get(assignment_id)
        if not d5_row or _norm(d5_row.get("preflight")) != "CLEAR_FOR_EXECUTION_AUTHORIZATION":
            raise ValueError(f"P0F7_9D7_D5_ENTRY_NOT_CLEAR:{assignment_id}")
        for field, expected in {
            "school_id": school_id,
            "class_id": class_id,
            "source_course_id": source_course_id,
            "target_course_id": target_course_id,
        }.items():
            if _norm(d5_row.get(field)) != expected:
                raise ValueError(f"P0F7_9D7_D5_ENTRY_DRIFT:{assignment_id}:{field}")

        entries.append(
            {
                "ordinal": ordinal,
                "assignment_id": assignment_id,
                "school_id": school_id,
                "class_id": class_id,
                "source_course_id": source_course_id,
                "target_course_id": target_course_id,
            }
        )
    entries.sort(key=lambda row: row["ordinal"])
    if [row["ordinal"] for row in entries] != list(range(1, EXPECTED_ENTRIES + 1)):
        raise ValueError("P0F7_9D7_ORDINAL_SEQUENCE_INVALID")

    hashes = {
        "plan_sha256": plan_sha,
        "d5_report_sha256": d5_sha,
        "d6_package_sha256": package_sha,
        "d6_report_sha256": d6_report_sha,
    }
    return tenant, year, entries, hashes


def build_js(
    plan: Mapping[str, Any],
    d5: Mapping[str, Any],
    package: Mapping[str, Any],
    d6_report: Mapping[str, Any],
    db_name: str,
    *,
    authorized: bool,
) -> str:
    if authorized is not True:
        raise ValueError("P0F7_9D7_EXPLICIT_AUTHORIZATION_REQUIRED")
    if not db_name or not all(ch.isalnum() or ch in "_.-" for ch in db_name):
        raise ValueError("DB_NAME_INVALID")

    tenant, year, entries, hashes = _validate_sources(plan, d5, package, d6_report)
    ctx = {
        "phase": OUTPUT_PHASE,
        "authorization_marker": AUTHORIZATION_MARKER,
        "mantenedora_id": tenant,
        "academic_year": year,
        "expected_entries": EXPECTED_ENTRIES,
        "strategy": EXPECTED_STRATEGY,
        "hashes": hashes,
        "entries": entries,
    }
    request = json.dumps(ctx, ensure_ascii=False, separators=(",", ":"))
    database = json.dumps(db_name, ensure_ascii=False)
    active_statuses = json.dumps(ACTIVE_STATUSES, ensure_ascii=False)

    return f'''const ctx = {request};
const AUTHORIZATION_MARKER = {json.dumps(AUTHORIZATION_MARKER)};
const ACTIVE_STATUSES = {active_statuses};
const targetDb = db.getSiblingDB({database});
const tenant = String(ctx.mantenedora_id || "");
const year = Number(ctx.academic_year || 0);
const yearFilter = {{$in:[year,String(year)]}};

if (ctx.authorization_marker !== AUTHORIZATION_MARKER) throw new Error("P0F79D7_AUTHORIZATION_MARKER_INVALID");
if (ctx.phase !== {json.dumps(OUTPUT_PHASE)}) throw new Error("P0F79D7_PHASE_INVALID");
if (!tenant || !year || !Array.isArray(ctx.entries) || ctx.entries.length !== {EXPECTED_ENTRIES}) throw new Error("P0F79D7_CONTEXT_INVALID");
if (ctx.strategy !== {json.dumps(EXPECTED_STRATEGY)}) throw new Error("P0F79D7_STRATEGY_INVALID");

function sourceFilter(e, staffId) {{
  const f = {{
    mantenedora_id: tenant,
    academic_year: yearFilter,
    school_id: String(e.school_id),
    class_id: String(e.class_id),
    id: String(e.assignment_id),
    course_id: String(e.source_course_id),
    status: {{$in:ACTIVE_STATUSES}}
  }};
  if (staffId) f.staff_id = String(staffId);
  return f;
}}

function targetFilter(e, staffId) {{
  return {{
    mantenedora_id: tenant,
    academic_year: yearFilter,
    school_id: String(e.school_id),
    class_id: String(e.class_id),
    id: String(e.assignment_id),
    course_id: String(e.target_course_id),
    status: {{$in:ACTIVE_STATUSES}},
    staff_id: String(staffId)
  }};
}}

function collisionFilter(e, staffId) {{
  return {{
    mantenedora_id: tenant,
    academic_year: yearFilter,
    school_id: String(e.school_id),
    class_id: String(e.class_id),
    course_id: String(e.target_course_id),
    staff_id: String(staffId),
    status: {{$in:ACTIVE_STATUSES}},
    id: {{$ne:String(e.assignment_id)}}
  }};
}}

const receipt = {{
  phase: ctx.phase,
  status: "STARTED",
  authorization_marker: AUTHORIZATION_MARKER,
  hashes: ctx.hashes,
  expected_entries: {EXPECTED_ENTRIES},
  forward_writes: 0,
  rollback_writes: 0,
  mutation_operations: 0,
  postconditions_verified: 0,
  final_verifications: 0,
  collision_checks: 0,
  rollback_attempted: false,
  rollback_complete: false,
  production_writes_authorized: true,
  remediation_executed: false,
  entries: [],
  error: null,
  rollback_errors: []
}};
const prepared = [];
const applied = [];

function safePrint() {{
  print("P0F79D7_EXECUTION_JSON=" + JSON.stringify(receipt));
}}

try {{
  // Whole-set preflight before the first write.
  for (const e of ctx.entries) {{
    const source = targetDb.teacher_assignments.findOne(
      sourceFilter(e, null),
      {{_id:0,id:1,staff_id:1,school_id:1,class_id:1,course_id:1,academic_year:1,status:1,mantenedora_id:1}}
    );
    if (!source) throw new Error("P0F79D7_SOURCE_CAS_MISS:" + e.assignment_id);
    const staffId = String(source.staff_id || "");
    if (!staffId) throw new Error("P0F79D7_STAFF_ID_REQUIRED:" + e.assignment_id);
    const collisions = targetDb.teacher_assignments.countDocuments(collisionFilter(e, staffId));
    receipt.collision_checks += 1;
    if (collisions !== 0) throw new Error("P0F79D7_PREFLIGHT_COLLISION:" + e.assignment_id);
    prepared.push({{e:e,staff_id:staffId}});
  }}
  if (prepared.length !== {EXPECTED_ENTRIES}) throw new Error("P0F79D7_PREPARED_COUNT_INVALID");

  // Sequential CAS. Any anomaly stops forward progress and triggers reverse rollback.
  for (const p of prepared) {{
    const e = p.e;
    const staffId = p.staff_id;

    const sourceNow = targetDb.teacher_assignments.findOne(sourceFilter(e, staffId), {{_id:0,id:1,course_id:1,staff_id:1}});
    if (!sourceNow) throw new Error("P0F79D7_IMMEDIATE_SOURCE_DRIFT:" + e.assignment_id);
    const beforeCollision = targetDb.teacher_assignments.countDocuments(collisionFilter(e, staffId));
    receipt.collision_checks += 1;
    if (beforeCollision !== 0) throw new Error("P0F79D7_IMMEDIATE_COLLISION:" + e.assignment_id);

    const result = targetDb.teacher_assignments.updateOne(
      sourceFilter(e, staffId),
      {{$set:{{course_id:String(e.target_course_id)}}}}
    );
    if (Number(result.matchedCount || 0) !== 1 || Number(result.modifiedCount || 0) !== 1) {{
      throw new Error("P0F79D7_CAS_UPDATE_FAILED:" + e.assignment_id);
    }}

    applied.push({{e:e,staff_id:staffId}});
    receipt.forward_writes += 1;
    receipt.mutation_operations += 1;

    const post = targetDb.teacher_assignments.findOne(targetFilter(e, staffId), {{_id:0,id:1,course_id:1,staff_id:1}});
    if (!post) throw new Error("P0F79D7_POSTCONDITION_FAILED:" + e.assignment_id);
    const afterCollision = targetDb.teacher_assignments.countDocuments(collisionFilter(e, staffId));
    receipt.collision_checks += 1;
    if (afterCollision !== 0) throw new Error("P0F79D7_POSTWRITE_COLLISION:" + e.assignment_id);
    receipt.postconditions_verified += 1;
    receipt.entries.push({{ordinal:Number(e.ordinal),assignment_id:String(e.assignment_id),status:"APPLIED_AND_VERIFIED"}});
  }}

  // Final global verification after all 23 writes.
  for (const p of prepared) {{
    const e = p.e;
    const staffId = p.staff_id;
    const finalDoc = targetDb.teacher_assignments.findOne(targetFilter(e, staffId), {{_id:0,id:1,course_id:1}});
    if (!finalDoc) throw new Error("P0F79D7_FINAL_POSTCONDITION_FAILED:" + e.assignment_id);
    const finalCollision = targetDb.teacher_assignments.countDocuments(collisionFilter(e, staffId));
    receipt.collision_checks += 1;
    if (finalCollision !== 0) throw new Error("P0F79D7_FINAL_COLLISION:" + e.assignment_id);
    receipt.final_verifications += 1;
  }}

  if (receipt.forward_writes !== {EXPECTED_ENTRIES} || receipt.postconditions_verified !== {EXPECTED_ENTRIES} || receipt.final_verifications !== {EXPECTED_ENTRIES}) {{
    throw new Error("P0F79D7_FINAL_COUNT_INVALID");
  }}

  receipt.status = "PASS";
  receipt.remediation_executed = true;
  receipt.rollback_complete = false;
  safePrint();
}} catch (err) {{
  receipt.error = String(err && err.message ? err.message : err);
  receipt.status = "FORWARD_FAILED_ROLLBACK_REQUIRED";
  receipt.rollback_attempted = applied.length > 0;

  for (let i = applied.length - 1; i >= 0; i--) {{
    const p = applied[i];
    const e = p.e;
    const staffId = p.staff_id;
    try {{
      const rollback = targetDb.teacher_assignments.updateOne(
        targetFilter(e, staffId),
        {{$set:{{course_id:String(e.source_course_id)}}}}
      );
      if (Number(rollback.matchedCount || 0) !== 1 || Number(rollback.modifiedCount || 0) !== 1) {{
        throw new Error("ROLLBACK_CAS_FAILED");
      }}
      receipt.rollback_writes += 1;
      receipt.mutation_operations += 1;
      const restored = targetDb.teacher_assignments.findOne(sourceFilter(e, staffId), {{_id:0,id:1,course_id:1}});
      if (!restored) throw new Error("ROLLBACK_POSTCONDITION_FAILED");
    }} catch (rbErr) {{
      receipt.rollback_errors.push({{assignment_id:String(e.assignment_id),error:String(rbErr && rbErr.message ? rbErr.message : rbErr)}});
    }}
  }}

  if (receipt.rollback_attempted && receipt.rollback_errors.length === 0 && receipt.rollback_writes === applied.length) {{
    receipt.status = "FAILED_ROLLED_BACK";
    receipt.rollback_complete = true;
    receipt.remediation_executed = false;
  }} else if (!receipt.rollback_attempted) {{
    receipt.status = "FAILED_BEFORE_FIRST_WRITE";
    receipt.rollback_complete = true;
    receipt.remediation_executed = false;
  }} else {{
    receipt.status = "CRITICAL_ROLLBACK_INCOMPLETE";
    receipt.rollback_complete = false;
    receipt.remediation_executed = false;
  }}
  safePrint();
  throw err;
}}
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build P0-F7.9D7 explicitly authorized production CAS executor")
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--d5-report", required=True, type=Path)
    parser.add_argument("--d6-package", required=True, type=Path)
    parser.add_argument("--d6-report", required=True, type=Path)
    parser.add_argument("--db", required=True)
    parser.add_argument("--js", required=True, type=Path)
    parser.add_argument("--authorize-production-writes", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    js = build_js(
        _load(args.plan),
        _load(args.d5_report),
        _load(args.d6_package),
        _load(args.d6_report),
        args.db,
        authorized=args.authorize_production_writes,
    )
    args.js.parent.mkdir(parents=True, exist_ok=True)
    args.js.write_text(js, encoding="utf-8")
    print(f"P0F7_9D7_AUTHORIZED_EXECUTOR_BUILT=YES path={args.js}")
    print(f"P0F7_9D7_EXPECTED_FORWARD_WRITES={EXPECTED_ENTRIES}")
    print(f"P0F7_9D7_AUTHORIZED_PLAN_SHA256={AUTHORIZED_PLAN_SHA256}")
    print(f"P0F7_9D7_STRATEGY={EXPECTED_STRATEGY}")
    print("P0F7_9D7_AUTHORIZATION=EXPLICIT_USER_AUTHORIZATION_RECORDED")
    print("EXECUTION_NOT_PERFORMED_BY_BUILDER=YES")


if __name__ == "__main__":
    main()
