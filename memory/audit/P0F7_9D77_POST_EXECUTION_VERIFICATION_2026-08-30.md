# P0-F7.9D7.7 — Post-execution verification and final seal

Data: 2026-08-30

## Purpose

Verify, read-only, the production state after the authorized D7.6.3 remediation and emit a final immutable seal.

## Execution evidence entering D7.7

The manually dispatched GitHub Actions workflow `P0-F7.9D7.6.4 GitHub-only Production Execution #1` completed with `Success`. Its workflow contract fails closed unless the captured D7.6 receipt is `APPLIED`, with exactly 23 forward writes, zero rollback writes, and `remediation_executed=true`. `SAFE_ROLLBACK`, `ROLLBACK_INCOMPLETE`, unknown status, invalid counts, or missing receipt cannot produce a successful job.

## Immutable chain

- revised plan D7.3.1: `b6cfcfd3fec964fe58ebdcc7aea6e9fe1953207d7178da35b7e1bd4dea8c39fb`
- D7.4 preflight: `b835f5393e035dee0703f1aa0ae0dd52c779b81d5f73b8c05d0adff3fbcedc9e`
- D7.5 manifest: `89e0f72d97f7cfa8b2d4b5dd7b5d35a01376a813d69d46f5bce7fa9c11440fcc`
- authorized D7.6.3 executor: `aa61676f8e3841436b34d8f345d235304380eda866984319b815ceec638e4e5b`

## D7.7 verification design

The verifier is generated inside GitHub Actions from the exact sealed manifest and performs exactly two bounded `teacher_assignments.find()` reads:

1. fetch all 23 affected assignments in one query;
2. fetch all possible active tuple collisions for the 22 final active assignments in one OR query.

The verifier checks:

- all 23 affected records exist in the exact tenant/year/school/class scope;
- all operation `set_fields` remain applied;
- the 21 remaps and survivor are active;
- the retired duplicate is `inativo`;
- all 22 active semantic tuples are unique;
- the adjudicated survivor remains on the target course with canonical weekly workload `2`;
- no student records or teacher names are read.

## Safety

D7.7 is strictly read-only:

- no update/replace/delete/insert/bulk writer primitives;
- query budget: 2;
- `DATABASE_MUTATION=NO`;
- `PRODUCTION_WRITES=NO`;
- zero hard delete;
- SSH host trust remains pinned by the `production` Environment secret.

The production verification workflow is manual (`workflow_dispatch`) and requires the exact confirmation `VERIFY_P0F79D77_READ_ONLY` on `main`.

## Final seal

After the production snapshot passes, the offline sealer emits an artifact with classification:

`REMEDIATION_APPLIED_AND_POST_STATE_VERIFIED`

The seal pins the D7.3.1/D7.4/D7.5/D7.6.3 chain, the post-execution snapshot hash, the GitHub Actions run ID, and the code SHA. Evidence is retained as a GitHub Actions artifact for 90 days.
