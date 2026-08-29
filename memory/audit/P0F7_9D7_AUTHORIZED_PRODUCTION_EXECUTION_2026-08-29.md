# P0-F7.9D7 — Authorized production execution

Date: 2026-08-29

## Authorization scope

An explicit user authorization was recorded for **exactly 23 production `teacher_assignments` course-id remediations** previously sealed by P0-F7.9D4, revalidated by P0-F7.9D5 and simulated by P0-F7.9D6.

The authorization does **not** extend to other collections, other assignments, other fields, bulk cleanup, historical metadata repair, orphan remediation, the 21 `NO_SAFE_TARGET` cases, the 44 series-scope review cases, or the 98 metadata-blocked cases.

Compensating rollback writes are authorized only when necessary to restore already-mutated D7 entries after a fail-closed forward-execution failure.

## Required execution strategy

Production topology from P0-F7.9D5:

- `STANDALONE_OR_TRANSACTION_UNAVAILABLE`
- multi-document transactions unavailable
- required strategy: `CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED`

The D7 executor therefore performs no multi-document transaction and no bulk mutation.

## Mandatory freshness chain

Immediately before D7 execution:

1. Re-run P0-F7.9D5 against production.
2. Require 23/23 `CLEAR_FOR_EXECUTION_AUTHORIZATION`, zero collisions, zero drift and zero curriculum rejection.
3. Rebuild and rerun P0-F7.9D6 from that fresh D5 report/snapshot.
4. Build the D7 executor from the same D4 + fresh D5 + fresh D6 package/report.
5. The D7 builder rejects any broken SHA chain.

## Exact mutation surface

Collection: `teacher_assignments`

Forward mutation per sealed entry:

- operation: `updateOne`
- field changed: `course_id` only
- expected CAS match: exactly one active source assignment
- scope: exact tenant + academic year + school + class + assignment id + source course id + staff id
- active status required
- no `updated_at` mutation
- no insert, delete, replace, updateMany or bulkWrite

Before and after each forward mutation, the executor checks that no active duplicate target tuple exists for the same staff + school + class + target course + academic year.

## Failure policy

`FAIL_CLOSED_NO_PARTIAL_GUESSING`

The executor first preflights all 23 entries before the first write. During forward execution it rechecks source CAS and target collision immediately before each mutation. After each mutation it verifies the target postcondition and target collision again. After all writes it performs a final global postcondition/collision verification.

On any failure after one or more forward writes:

1. stop forward progress immediately;
2. rollback already-applied entries in reverse order;
3. rollback with an exact target-state CAS filter;
4. verify each restored source postcondition;
5. continue best-effort rollback of all already-applied entries even if one rollback reports an error;
6. emit a machine-readable receipt.

Receipt status semantics:

- `PASS`: all 23 forward writes applied and verified; no rollback.
- `FAILED_BEFORE_FIRST_WRITE`: safe abort, zero mutation.
- `FAILED_ROLLED_BACK`: forward execution failed, but all applied changes were restored and verified.
- `CRITICAL_ROLLBACK_INCOMPLETE`: manual recovery required; do not retry D7 automatically.

## Production safety boundary

The version-controlled PowerShell wrapper cannot SSH to production and cannot run mongosh. It only validates inputs and locally generates the authorized executor JS. The actual production invocation is a separate, visible operator action.

The generated executor contains no credentials, student data or teacher names. It uses structural identifiers only.

## Post-execution seal

`backend/scripts/validate_p0f7_9d7_execution_receipt_offline.py` validates the machine receipt offline and classifies the result as:

- `PASS / REMEDIATION_APPLIED_AND_VERIFIED`
- `SAFE_ABORT / NO_MUTATION_FAILURE`
- `SAFE_ROLLBACK / FORWARD_FAILED_FULL_COMPENSATION_VERIFIED`
- `CRITICAL / MANUAL_RECOVERY_REQUIRED`
