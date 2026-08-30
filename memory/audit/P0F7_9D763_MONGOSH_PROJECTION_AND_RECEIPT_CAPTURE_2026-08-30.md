# P0-F7.9D7.6.3 — Mongosh projection contract and receipt capture

Data: 2026-08-30

## Incident observed

The first production invocation of the materialized D7.6.1 executor failed with:

`Cannot do inclusion on field id in exclusion projection`

The failure occurred in the global CAS gate, before the first `updateOne` can be reached. Therefore that invocation performed zero forward writes and zero rollback writes.

## Root cause 1 — mongosh `findOne` projection position

The reviewed writer template used Node-driver style calls such as:

`findOne(filter, {projection:{_id:0,id:1,...}})`

The runtime is `mongosh`, whose `db.collection.findOne()` contract is positional:

`findOne(query, projection, options)`

The nested `projection` object was therefore interpreted as the projection document itself and failed at runtime.

D7.6.3 patches only these read-only safety-query call shapes to direct second-argument projections:

`findOne(filter, {_id:0,id:1,...})`

The patch fails closed if the exact expected template occurrences drift. It does not change:

- the authorized D7.5 manifest;
- the D7.3.1/D7.4 SHA chain;
- operation count or order;
- CAS predicates;
- set/rollback fields;
- collision logic;
- `updateOne` writer semantics;
- rollback strategy;
- hard-delete prohibition.

A newly materialized executor will necessarily have a new SHA-256 because its bytes changed. The prior D7.6.1 executor SHA must not be executed again.

## Root cause 2 — PowerShell native stderr capture

The manual production harness had `$ErrorActionPreference = 'Stop'` while assigning pipeline output from `ssh`. When mongosh emitted the final error through SSH stderr, PowerShell terminated the assignment before `$RemoteOutput` was replaced. The variable therefore retained an older D7.4 value, which explains why an old `P0F79D74_REVISED_LAST_MILE_JSON=` marker appeared in the diagnostic output.

The previous empty receipt file is not a valid execution receipt and must never be validated or used as evidence of execution state.

## Safe capture rule for the next invocation

Before any future SSH invocation:

1. set `$RemoteOutput = @()` explicitly;
2. temporarily use `$ErrorActionPreference = 'Continue'` only around the native SSH pipeline so stderr does not abort assignment;
3. restore the prior error preference immediately afterward;
4. persist the newly captured output before parsing;
5. require an exact `P0F79D76_EXECUTION_RECEIPT=` marker;
6. if the marker is absent, stop and do not rerun automatically;
7. validate the receipt offline against the exact manifest, metadata and executor hash.

## Security state

The failed invocation never reached a writer primitive because the global CAS gate failed during its first read projection. No remediation was applied.

D7.6.3 itself is local-only and does not access production. The repository wrapper remains unable to invoke SSH/mongosh remotely.
