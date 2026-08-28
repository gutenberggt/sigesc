#!/usr/bin/env python3
"""P0-D1 — executor controlado para backfill de ``staff.user_id``.

Escopo aprovado pela evidência P0-C Semantic V3:
- 6 propostas ``BACKFILL_STAFF_USER_ID``;
- manifesto canônico fixado por SHA-256;
- somente ``staff.user_id`` pode ser alterado.

Segurança:
- default = DRY-RUN;
- dry-run recalcula o manifesto V3 vivo e exige hash idêntico ao aprovado;
- dry-run cria snapshot imutável + BACKUP-SEAL e NÃO altera MongoDB;
- apply exige ``--apply`` + confirmação literal + hash aprovado do backup;
- cada escrita usa CAS sobre id + tenant + valor/presença anterior de ``user_id``;
- falha parcial tenta compensação imediata, também por CAS;
- rollback exige confirmação própria + o mesmo backup selado;
- nenhum outro campo/collection é alterado; auditoria é gravada somente em arquivos.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid
from typing import Any, Iterable, Mapping, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from scripts import preflight_teacher_identity_remediation_p0c as base  # noqa: E402
from scripts import preflight_teacher_identity_remediation_p0c_semantic as semantic_v3  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

PHASE_ID = "P0D-TEACHER-IDENTITY-BACKFILL-2026"
BACKUP_MODE = "P0D-TEACHER-IDENTITY-PREFLIGHT-SNAPSHOT"
ACTOR = "p0d-teacher-identity-backfill"

ACADEMIC_YEAR = 2026
REFERENCE_DATE = "2026-08-27"
APPROVED_MANIFEST_PHASE = "P0C-TEACHER-IDENTITY-PREFLIGHT-2026-SEMANTIC-V3"
APPROVED_MANIFEST_VERSION = 3
APPROVED_MANIFEST_SHA256 = "68165e38d51e58071bd0d9b8d91114872b97841f987e8b630b9b6208b77bda9a"
APPROVED_SOURCE_P0B_SHA256 = "519f078008fae82dc1277975fcf7de141a9231f391da9d1d47666db9e5f781be"
APPROVED_READY_COUNT = 6
APPROVED_ALREADY_CANONICAL = 33
APPROVED_EVIDENCE_METHOD = "EXACT_PAIR_PLUS_EMAIL"

APPLY_CONFIRMATION = "APPLY-P0D-TEACHER-IDENTITY-6"
ROLLBACK_CONFIRMATION = "ROLLBACK-P0D-TEACHER-IDENTITY-6"

DEFAULT_BACKUP_DIR = "/tmp/sigesc-p0d-teacher-identity-backup"
DEFAULT_RECEIPT_DIR = "/tmp/sigesc-p0d-teacher-identity-receipts"


class P0DGateError(RuntimeError):
    """Falha de gate P0-D; nenhuma inferência permissiva é permitida."""


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _sha256_value(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _proposal_without_hash(proposal: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(proposal)
    result.pop("evidence_sha256", None)
    return result


def load_and_validate_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise P0DGateError(f"MANIFEST_FILE_MISSING path={path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    actual_sha = base.manifest_sha256(payload)
    if actual_sha != APPROVED_MANIFEST_SHA256:
        raise P0DGateError(
            "MANIFEST_SHA_NOT_APPROVED "
            f"expected={APPROVED_MANIFEST_SHA256} actual={actual_sha}"
        )

    if payload.get("phase") != APPROVED_MANIFEST_PHASE:
        raise P0DGateError(
            f"MANIFEST_PHASE_INVALID actual={payload.get('phase')}"
        )
    if int(payload.get("manifest_version") or 0) != APPROVED_MANIFEST_VERSION:
        raise P0DGateError(
            f"MANIFEST_VERSION_INVALID actual={payload.get('manifest_version')}"
        )
    if payload.get("mode") != "READ_ONLY_PREFLIGHT":
        raise P0DGateError(f"MANIFEST_MODE_INVALID actual={payload.get('mode')}")
    if payload.get("status") != "PASS":
        raise P0DGateError(f"MANIFEST_STATUS_NOT_PASS actual={payload.get('status')}")
    if payload.get("source_p0b_evidence_sha256") != APPROVED_SOURCE_P0B_SHA256:
        raise P0DGateError("MANIFEST_SOURCE_P0B_SHA_MISMATCH")

    semantic = payload.get("semantic_partition") or {}
    if semantic.get("remediation_gate") != "PASS":
        raise P0DGateError(
            f"MANIFEST_REMEDIATION_GATE_NOT_PASS actual={semantic.get('remediation_gate')}"
        )
    if int((semantic.get("counts") or {}).get("LEGACY_MIGRATION_DRIFT", 0)) != 0:
        raise P0DGateError("MANIFEST_LEGACY_MIGRATION_DRIFT_NONZERO")

    summary = payload.get("summary") or {}
    decisions = summary.get("decision_counts") or {}
    if int(decisions.get("READY_SAFE", 0)) != APPROVED_READY_COUNT:
        raise P0DGateError(
            "MANIFEST_READY_COUNT_MISMATCH "
            f"expected={APPROVED_READY_COUNT} actual={decisions.get('READY_SAFE', 0)}"
        )
    if int(decisions.get("ALREADY_CANONICAL", 0)) != APPROVED_ALREADY_CANONICAL:
        raise P0DGateError(
            "MANIFEST_ALREADY_CANONICAL_MISMATCH "
            f"expected={APPROVED_ALREADY_CANONICAL} "
            f"actual={decisions.get('ALREADY_CANONICAL', 0)}"
        )
    if summary.get("blocker_counts"):
        raise P0DGateError("MANIFEST_BLOCKERS_PRESENT")

    proposals = payload.get("proposals")
    if not isinstance(proposals, list) or len(proposals) != APPROVED_READY_COUNT:
        raise P0DGateError(
            f"MANIFEST_PROPOSALS_COUNT_INVALID actual={len(proposals or [])}"
        )

    staff_ids: list[str] = []
    target_ids: list[str] = []
    for index, proposal in enumerate(proposals):
        if proposal.get("operation") != "BACKFILL_STAFF_USER_ID":
            raise P0DGateError(
                f"PROPOSAL_OPERATION_INVALID index={index} operation={proposal.get('operation')}"
            )
        staff_id = _norm(proposal.get("staff_id"))
        target_user_id = _norm(proposal.get("target_user_id"))
        tenant_id = _norm(proposal.get("mantenedora_id"))
        if not staff_id or not target_user_id or not tenant_id:
            raise P0DGateError(f"PROPOSAL_REQUIRED_FIELD_MISSING index={index}")
        if proposal.get("expected_user_id_before") not in (None, ""):
            raise P0DGateError(
                f"PROPOSAL_EXPECTED_BEFORE_NOT_EMPTY index={index}"
            )
        if proposal.get("evidence_method") != APPROVED_EVIDENCE_METHOD:
            raise P0DGateError(
                "PROPOSAL_EVIDENCE_METHOD_INVALID "
                f"index={index} actual={proposal.get('evidence_method')}"
            )
        expected_evidence_sha = _norm(proposal.get("evidence_sha256"))
        calculated_evidence_sha = base.manifest_sha256(
            _proposal_without_hash(proposal)
        )
        if expected_evidence_sha != calculated_evidence_sha:
            raise P0DGateError(
                f"PROPOSAL_EVIDENCE_SHA_MISMATCH index={index}"
            )
        if not proposal.get("dvd_assignment_ids"):
            raise P0DGateError(f"PROPOSAL_DVD_EVIDENCE_EMPTY index={index}")
        if not proposal.get("exact_pair_evidence"):
            raise P0DGateError(f"PROPOSAL_PAIR_EVIDENCE_EMPTY index={index}")
        staff_ids.append(staff_id)
        target_ids.append(target_user_id)

    if len(staff_ids) != len(set(staff_ids)):
        raise P0DGateError("PROPOSAL_DUPLICATE_STAFF_ID")
    if len(target_ids) != len(set(target_ids)):
        raise P0DGateError("PROPOSAL_DUPLICATE_TARGET_USER_ID")

    return payload


def _before_matches(doc: Mapping[str, Any], proposal: Mapping[str, Any]) -> bool:
    expected = proposal.get("expected_user_id_before")
    return _norm(doc.get("user_id")) == _norm(expected)


def _target_matches(doc: Mapping[str, Any], proposal: Mapping[str, Any]) -> bool:
    return _norm(doc.get("user_id")) == _norm(proposal.get("target_user_id"))


def _snapshot_row(
    staff_doc: Mapping[str, Any],
    proposal: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "id": _norm(staff_doc.get("id")),
        "mantenedora_id": _norm(staff_doc.get("mantenedora_id")) or None,
        "user_id_present": "user_id" in staff_doc,
        "user_id": staff_doc.get("user_id"),
        "target_user_id": _norm(proposal.get("target_user_id")),
        "proposal_evidence_sha256": _norm(proposal.get("evidence_sha256")),
    }


async def inspect_live_state(
    db: Any,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    proposals = list(manifest["proposals"])
    staff_ids = [str(p["staff_id"]) for p in proposals]
    target_ids = [str(p["target_user_id"]) for p in proposals]

    staff_rows = await db.staff.find(
        {"id": {"$in": staff_ids}},
        {
            "_id": 0,
            "id": 1,
            "user_id": 1,
            "mantenedora_id": 1,
            "cargo": 1,
            "status": 1,
        },
    ).to_list(APPROVED_READY_COUNT + 10)
    if len(staff_rows) != APPROVED_READY_COUNT:
        raise P0DGateError(
            f"LIVE_STAFF_COUNT_MISMATCH expected={APPROVED_READY_COUNT} actual={len(staff_rows)}"
        )
    staff_by_id = {_norm(row.get("id")): row for row in staff_rows}
    if len(staff_by_id) != APPROVED_READY_COUNT:
        raise P0DGateError("LIVE_STAFF_DUPLICATE_OR_MISSING_ID")

    users = await db.users.find(
        {"id": {"$in": target_ids}},
        {"_id": 0, "id": 1, "role": 1, "mantenedora_id": 1},
    ).to_list(APPROVED_READY_COUNT + 10)
    user_by_id = {_norm(row.get("id")): row for row in users}
    if len(user_by_id) != APPROVED_READY_COUNT:
        raise P0DGateError(
            f"LIVE_TARGET_USERS_COUNT_MISMATCH expected={APPROVED_READY_COUNT} actual={len(user_by_id)}"
        )

    linked_rows = await db.staff.find(
        {"user_id": {"$in": target_ids}},
        {"_id": 0, "id": 1, "user_id": 1},
    ).to_list(APPROVED_READY_COUNT * 4)
    linked_by_user: dict[str, list[str]] = {}
    for row in linked_rows:
        uid = _norm(row.get("user_id"))
        sid = _norm(row.get("id"))
        if uid and sid:
            linked_by_user.setdefault(uid, []).append(sid)

    before = 0
    target = 0
    details: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []

    for proposal in proposals:
        sid = _norm(proposal.get("staff_id"))
        uid = _norm(proposal.get("target_user_id"))
        tenant = _norm(proposal.get("mantenedora_id"))
        staff = staff_by_id.get(sid)
        user = user_by_id.get(uid)
        if not staff or not user:
            raise P0DGateError(f"LIVE_ENTITY_MISSING staff_id={sid} user_id={uid}")

        if _norm(staff.get("mantenedora_id")) != tenant:
            raise P0DGateError(f"LIVE_STAFF_TENANT_DRIFT staff_id={sid}")
        user_tenant = _norm(user.get("mantenedora_id"))
        if user_tenant and user_tenant != tenant:
            raise P0DGateError(f"LIVE_USER_TENANT_DRIFT user_id={uid}")
        if _norm(staff.get("cargo")).casefold() != "professor":
            raise P0DGateError(f"LIVE_STAFF_CARGO_DRIFT staff_id={sid}")
        if _norm(staff.get("status")).casefold() in base.INACTIVE_STAFF_STATUSES:
            raise P0DGateError(f"LIVE_STAFF_INACTIVE staff_id={sid}")
        if _norm(user.get("role")).casefold() not in base.ALLOWED_TEACHER_ROLES:
            raise P0DGateError(f"LIVE_USER_ROLE_DRIFT user_id={uid}")

        foreign_links = [
            linked_sid
            for linked_sid in linked_by_user.get(uid, [])
            if linked_sid != sid
        ]
        if foreign_links:
            raise P0DGateError(
                f"LIVE_TARGET_USER_ALREADY_LINKED_ELSEWHERE user_id={uid} staff_ids={foreign_links}"
            )

        is_before = _before_matches(staff, proposal)
        is_target = _target_matches(staff, proposal)
        if is_before:
            before += 1
            state = "EXPECTED_BEFORE"
        elif is_target:
            target += 1
            state = "TARGET_ALREADY_SET"
        else:
            raise P0DGateError(
                "LIVE_STAFF_USER_ID_DRIFT "
                f"staff_id={sid} current={staff.get('user_id')!r}"
            )

        details.append({
            "staff_id": sid,
            "target_user_id": uid,
            "state": state,
        })
        snapshots.append(_snapshot_row(staff, proposal))

    if before == APPROVED_READY_COUNT and target == 0:
        state = "READY"
    elif target == APPROVED_READY_COUNT and before == 0:
        state = "ALREADY_APPLIED"
    else:
        raise P0DGateError(
            f"PARTIAL_APPLY_STATE_DETECTED before={before} target={target}"
        )

    snapshots.sort(key=lambda row: row["id"])
    details.sort(key=lambda row: row["staff_id"])
    return {
        "state": state,
        "before_count": before,
        "target_count": target,
        "details": details,
        "staff_snapshot": snapshots,
    }


async def assert_live_manifest_unchanged(
    db: Any,
) -> str:
    live = await semantic_v3.collect_manifest(
        db,
        academic_year=ACADEMIC_YEAR,
        reference_date=REFERENCE_DATE,
        source_evidence_sha256=APPROVED_SOURCE_P0B_SHA256,
    )
    actual_sha = base.manifest_sha256(live)
    if actual_sha != APPROVED_MANIFEST_SHA256:
        raise P0DGateError(
            "LIVE_MANIFEST_DRIFT "
            f"expected={APPROVED_MANIFEST_SHA256} actual={actual_sha}"
        )
    return actual_sha


def write_backup_directory(
    backup_dir: Path,
    *,
    manifest: Mapping[str, Any],
    staff_snapshot: list[Mapping[str, Any]],
    live_manifest_sha256: str,
) -> dict[str, Any]:
    if backup_dir.exists():
        raise P0DGateError(f"BACKUP_DIR_ALREADY_EXISTS path={backup_dir}")

    backup_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = backup_dir / "manifest.json"
    staff_path = backup_dir / "staff_before.json"
    metadata_path = backup_dir / "backup-metadata.json"

    metadata = {
        "phase": PHASE_ID,
        "mode": BACKUP_MODE,
        "created_at": _utc_now(),
        "academic_year": ACADEMIC_YEAR,
        "reference_date": REFERENCE_DATE,
        "manifest_sha256": APPROVED_MANIFEST_SHA256,
        "live_manifest_sha256": live_manifest_sha256,
        "source_p0b_evidence_sha256": APPROVED_SOURCE_P0B_SHA256,
        "ready_count": APPROVED_READY_COUNT,
        "mutates_database": False,
        "scope": "staff.user_id only",
    }

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    staff_path.write_text(
        json.dumps(staff_snapshot, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    file_hashes = {
        "backup-metadata.json": _sha256_file(metadata_path),
        "manifest.json": _sha256_file(manifest_path),
        "staff_before.json": _sha256_file(staff_path),
    }
    bundle_sha = _sha256_value({"file_sha256": file_hashes})
    seal = {
        "phase": PHASE_ID,
        "mode": BACKUP_MODE,
        "files": file_hashes,
        "backup_bundle_sha256": bundle_sha,
    }
    (backup_dir / "BACKUP-SEAL.json").write_text(
        json.dumps(seal, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "backup_dir": str(backup_dir),
        "backup_bundle_sha256": bundle_sha,
        "files": file_hashes,
    }


def load_and_verify_backup(
    backup_dir: Path,
    *,
    expected_backup_sha256: str,
) -> dict[str, Any]:
    names = (
        "BACKUP-SEAL.json",
        "backup-metadata.json",
        "manifest.json",
        "staff_before.json",
    )
    for name in names:
        if not (backup_dir / name).is_file():
            raise P0DGateError(f"BACKUP_FILE_MISSING file={name}")

    seal = json.loads((backup_dir / "BACKUP-SEAL.json").read_text(encoding="utf-8"))
    files = seal.get("files")
    if not isinstance(files, dict) or set(files) != {
        "backup-metadata.json",
        "manifest.json",
        "staff_before.json",
    }:
        raise P0DGateError("BACKUP_SEAL_FILES_INVALID")

    for name, expected_hash in sorted(files.items()):
        actual_hash = _sha256_file(backup_dir / name)
        if actual_hash != expected_hash:
            raise P0DGateError(
                f"BACKUP_FILE_HASH_MISMATCH file={name}"
            )

    bundle_sha = _sha256_value({"file_sha256": files})
    if bundle_sha != seal.get("backup_bundle_sha256"):
        raise P0DGateError("BACKUP_BUNDLE_SEAL_MISMATCH")
    if bundle_sha != expected_backup_sha256:
        raise P0DGateError(
            "BACKUP_BUNDLE_NOT_APPROVED "
            f"expected={expected_backup_sha256} actual={bundle_sha}"
        )

    metadata = json.loads((backup_dir / "backup-metadata.json").read_text(encoding="utf-8"))
    if metadata.get("phase") != PHASE_ID or metadata.get("mode") != BACKUP_MODE:
        raise P0DGateError("BACKUP_METADATA_PHASE_OR_MODE_INVALID")
    if metadata.get("mutates_database") is not False:
        raise P0DGateError("BACKUP_METADATA_MUTATION_FLAG_INVALID")
    if metadata.get("manifest_sha256") != APPROVED_MANIFEST_SHA256:
        raise P0DGateError("BACKUP_METADATA_MANIFEST_SHA_MISMATCH")
    if metadata.get("live_manifest_sha256") != APPROVED_MANIFEST_SHA256:
        raise P0DGateError("BACKUP_METADATA_LIVE_MANIFEST_SHA_MISMATCH")
    if metadata.get("source_p0b_evidence_sha256") != APPROVED_SOURCE_P0B_SHA256:
        raise P0DGateError("BACKUP_METADATA_SOURCE_SHA_MISMATCH")
    if int(metadata.get("ready_count") or 0) != APPROVED_READY_COUNT:
        raise P0DGateError("BACKUP_METADATA_READY_COUNT_MISMATCH")

    manifest = load_and_validate_manifest(backup_dir / "manifest.json")
    snapshot = json.loads((backup_dir / "staff_before.json").read_text(encoding="utf-8"))
    if not isinstance(snapshot, list) or len(snapshot) != APPROVED_READY_COUNT:
        raise P0DGateError("BACKUP_STAFF_SNAPSHOT_INVALID")

    snap_ids = [str(row.get("id") or "") for row in snapshot]
    if any(not sid for sid in snap_ids) or len(snap_ids) != len(set(snap_ids)):
        raise P0DGateError("BACKUP_STAFF_SNAPSHOT_IDS_INVALID")

    return {
        "seal": seal,
        "metadata": metadata,
        "manifest": manifest,
        "staff_before": snapshot,
        "backup_bundle_sha256": bundle_sha,
    }


def _cas_before_filter(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    base_filter: dict[str, Any] = {
        "id": snapshot["id"],
        "mantenedora_id": snapshot["mantenedora_id"],
    }
    if snapshot.get("user_id_present") is False:
        base_filter["user_id"] = {"$exists": False}
    elif snapshot.get("user_id") is None:
        base_filter["$and"] = [
            {"user_id": {"$exists": True}},
            {"user_id": None},
        ]
    else:
        base_filter["user_id"] = snapshot.get("user_id")
    return base_filter


def _restore_update(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    if snapshot.get("user_id_present") is False:
        return {"$unset": {"user_id": ""}}
    return {"$set": {"user_id": snapshot.get("user_id")}}


def _target_filter(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": snapshot["id"],
        "mantenedora_id": snapshot["mantenedora_id"],
        "user_id": snapshot["target_user_id"],
    }


def _snapshot_map(snapshot: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row["id"]): dict(row) for row in snapshot}


def assert_current_matches_backup_before(
    live_snapshot: Iterable[Mapping[str, Any]],
    backup_snapshot: Iterable[Mapping[str, Any]],
) -> None:
    live = _snapshot_map(live_snapshot)
    sealed = _snapshot_map(backup_snapshot)
    if set(live) != set(sealed):
        raise P0DGateError("BACKUP_LIVE_STAFF_ID_SET_MISMATCH")

    for sid in sorted(sealed):
        current = live[sid]
        expected = sealed[sid]
        for field in (
            "mantenedora_id",
            "user_id_present",
            "user_id",
            "target_user_id",
            "proposal_evidence_sha256",
        ):
            if current.get(field) != expected.get(field):
                raise P0DGateError(
                    f"BACKUP_BASELINE_DRIFT staff_id={sid} field={field}"
                )


async def _compensate_apply(
    db: Any,
    applied: list[Mapping[str, Any]],
) -> list[str]:
    failures: list[str] = []
    for snapshot in reversed(applied):
        result = await db.staff.update_one(
            _target_filter(snapshot),
            _restore_update(snapshot),
        )
        if getattr(result, "matched_count", 0) != 1:
            failures.append(str(snapshot["id"]))
    return failures


async def apply_backfills(
    db: Any,
    backup: Mapping[str, Any],
) -> list[dict[str, Any]]:
    manifest = backup["manifest"]
    state = await inspect_live_state(db, manifest)
    if state["state"] == "ALREADY_APPLIED":
        return []
    if state["state"] != "READY":
        raise P0DGateError(f"APPLY_STATE_INVALID state={state['state']}")

    await assert_live_manifest_unchanged(db)
    assert_current_matches_backup_before(
        state["staff_snapshot"],
        backup["staff_before"],
    )

    snapshot_by_id = _snapshot_map(backup["staff_before"])
    applied: list[Mapping[str, Any]] = []
    changes: list[dict[str, Any]] = []

    for proposal in manifest["proposals"]:
        sid = str(proposal["staff_id"])
        snapshot = snapshot_by_id[sid]
        result = await db.staff.update_one(
            _cas_before_filter(snapshot),
            {"$set": {"user_id": proposal["target_user_id"]}},
        )
        if getattr(result, "matched_count", 0) != 1:
            compensation_failures = await _compensate_apply(db, applied)
            if compensation_failures:
                raise P0DGateError(
                    "APPLY_CAS_FAILED_COMPENSATION_INCOMPLETE "
                    f"staff_id={sid} compensation_failures={compensation_failures}"
                )
            raise P0DGateError(
                f"APPLY_CAS_FAILED_COMPENSATED staff_id={sid}"
            )

        applied.append(snapshot)
        changes.append({
            "staff_id": sid,
            "before_present": snapshot.get("user_id_present"),
            "before_user_id": snapshot.get("user_id"),
            "after_user_id": proposal["target_user_id"],
        })

    post = await inspect_live_state(db, manifest)
    if post["state"] != "ALREADY_APPLIED":
        raise P0DGateError(
            f"POST_APPLY_STATE_INVALID state={post['state']}"
        )
    return changes


async def _compensate_rollback(
    db: Any,
    rolled_back: list[Mapping[str, Any]],
) -> list[str]:
    failures: list[str] = []
    for snapshot in reversed(rolled_back):
        result = await db.staff.update_one(
            _cas_before_filter(snapshot),
            {"$set": {"user_id": snapshot["target_user_id"]}},
        )
        if getattr(result, "matched_count", 0) != 1:
            failures.append(str(snapshot["id"]))
    return failures


async def rollback_backfills(
    db: Any,
    backup: Mapping[str, Any],
) -> list[dict[str, Any]]:
    manifest = backup["manifest"]
    state = await inspect_live_state(db, manifest)
    if state["state"] == "READY":
        assert_current_matches_backup_before(
            state["staff_snapshot"],
            backup["staff_before"],
        )
        return []
    if state["state"] != "ALREADY_APPLIED":
        raise P0DGateError(f"ROLLBACK_STATE_INVALID state={state['state']}")

    snapshot_by_id = _snapshot_map(backup["staff_before"])
    rolled_back: list[Mapping[str, Any]] = []
    changes: list[dict[str, Any]] = []

    for proposal in reversed(manifest["proposals"]):
        sid = str(proposal["staff_id"])
        snapshot = snapshot_by_id[sid]
        result = await db.staff.update_one(
            _target_filter(snapshot),
            _restore_update(snapshot),
        )
        if getattr(result, "matched_count", 0) != 1:
            compensation_failures = await _compensate_rollback(db, rolled_back)
            if compensation_failures:
                raise P0DGateError(
                    "ROLLBACK_CAS_FAILED_COMPENSATION_INCOMPLETE "
                    f"staff_id={sid} compensation_failures={compensation_failures}"
                )
            raise P0DGateError(
                f"ROLLBACK_CAS_FAILED_COMPENSATED staff_id={sid}"
            )

        rolled_back.append(snapshot)
        changes.append({
            "staff_id": sid,
            "before_user_id": proposal["target_user_id"],
            "after_present": snapshot.get("user_id_present"),
            "after_user_id": snapshot.get("user_id"),
        })

    post = await inspect_live_state(db, manifest)
    if post["state"] != "READY":
        raise P0DGateError(
            f"POST_ROLLBACK_STATE_INVALID state={post['state']}"
        )
    assert_current_matches_backup_before(
        post["staff_snapshot"],
        backup["staff_before"],
    )
    return changes


def write_receipt(
    receipt_dir: Path,
    *,
    mode: str,
    state_before: str,
    state_after: str,
    backup_bundle_sha256: Optional[str],
    changes: list[Mapping[str, Any]],
    database_mutation: bool,
) -> Path:
    receipt_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid.uuid4())
    payload = {
        "phase": PHASE_ID,
        "run_id": run_id,
        "created_at": _utc_now(),
        "mode": mode,
        "actor": ACTOR,
        "academic_year": ACADEMIC_YEAR,
        "reference_date": REFERENCE_DATE,
        "manifest_sha256": APPROVED_MANIFEST_SHA256,
        "source_p0b_evidence_sha256": APPROVED_SOURCE_P0B_SHA256,
        "backup_bundle_sha256": backup_bundle_sha256,
        "state_before": state_before,
        "state_after": state_after,
        "database_mutation": database_mutation,
        "changes": list(changes),
    }
    payload["receipt_sha256"] = _sha256_value(payload)
    path = receipt_dir / f"{mode.lower()}-{run_id}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return path


async def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.apply and args.rollback:
        raise P0DGateError("APPLY_ROLLBACK_MUTUALLY_EXCLUSIVE")

    manifest = load_and_validate_manifest(Path(args.manifest))
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        raise P0DGateError("MONGO_URL_OR_DB_NAME_MISSING")

    client = AsyncIOMotorClient(mongo_url)
    try:
        db = client[db_name]

        if not args.apply and not args.rollback:
            state = await inspect_live_state(db, manifest)
            if state["state"] != "READY":
                raise P0DGateError(
                    f"DRY_RUN_REQUIRES_READY_STATE actual={state['state']}"
                )
            live_sha = await assert_live_manifest_unchanged(db)
            sealed = write_backup_directory(
                Path(args.backup_dir),
                manifest=manifest,
                staff_snapshot=state["staff_snapshot"],
                live_manifest_sha256=live_sha,
            )
            receipt = write_receipt(
                Path(args.receipt_dir),
                mode="DRY_RUN",
                state_before="READY",
                state_after="READY",
                backup_bundle_sha256=sealed["backup_bundle_sha256"],
                changes=[],
                database_mutation=False,
            )
            return {
                "phase": PHASE_ID,
                "mode": "DRY_RUN",
                "status": "PASS",
                "database_mutation": False,
                "manifest_sha256": APPROVED_MANIFEST_SHA256,
                "source_p0b_evidence_sha256": APPROVED_SOURCE_P0B_SHA256,
                "ready_count": APPROVED_READY_COUNT,
                "live_state": state["state"],
                "backup_dir": sealed["backup_dir"],
                "backup_bundle_sha256": sealed["backup_bundle_sha256"],
                "receipt": str(receipt),
            }

        expected_backup_sha = _norm(args.expected_backup_sha256)
        if not expected_backup_sha:
            raise P0DGateError("EXPECTED_BACKUP_SHA_REQUIRED")
        backup = load_and_verify_backup(
            Path(args.backup_dir),
            expected_backup_sha256=expected_backup_sha,
        )

        state_before = await inspect_live_state(db, manifest)
        if args.apply:
            if args.confirm != APPLY_CONFIRMATION:
                raise P0DGateError("APPLY_CONFIRMATION_REQUIRED")
            changes = await apply_backfills(db, backup)
            state_after = (await inspect_live_state(db, manifest))["state"]
            receipt = write_receipt(
                Path(args.receipt_dir),
                mode="APPLY" if changes else "APPLY_NOOP",
                state_before=state_before["state"],
                state_after=state_after,
                backup_bundle_sha256=expected_backup_sha,
                changes=changes,
                database_mutation=bool(changes),
            )
            return {
                "phase": PHASE_ID,
                "mode": "APPLY",
                "status": "PASS",
                "database_mutation": bool(changes),
                "modified_count": len(changes),
                "state_before": state_before["state"],
                "state_after": state_after,
                "manifest_sha256": APPROVED_MANIFEST_SHA256,
                "backup_bundle_sha256": expected_backup_sha,
                "receipt": str(receipt),
            }

        if args.confirm != ROLLBACK_CONFIRMATION:
            raise P0DGateError("ROLLBACK_CONFIRMATION_REQUIRED")
        changes = await rollback_backfills(db, backup)
        state_after = (await inspect_live_state(db, manifest))["state"]
        receipt = write_receipt(
            Path(args.receipt_dir),
            mode="ROLLBACK" if changes else "ROLLBACK_NOOP",
            state_before=state_before["state"],
            state_after=state_after,
            backup_bundle_sha256=expected_backup_sha,
            changes=changes,
            database_mutation=bool(changes),
        )
        return {
            "phase": PHASE_ID,
            "mode": "ROLLBACK",
            "status": "PASS",
            "database_mutation": bool(changes),
            "modified_count": len(changes),
            "state_before": state_before["state"],
            "state_after": state_after,
            "manifest_sha256": APPROVED_MANIFEST_SHA256,
            "backup_bundle_sha256": expected_backup_sha,
            "receipt": str(receipt),
        }
    finally:
        client.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="P0-D1 — backfill controlado de staff.user_id; default DRY-RUN"
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--backup-dir", default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--receipt-dir", default=DEFAULT_RECEIPT_DIR)
    parser.add_argument("--expected-backup-sha256", default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--confirm", default=None)
    return parser.parse_args()


async def main() -> None:
    result = await run(parse_args())
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
