#!/usr/bin/env python3
"""P0-D2 — entrypoint selado do backfill de identidade docente.

Este wrapper NÃO implementa mutações próprias. Ele fixa a evidência aprovada em
produção e delega apply/rollback ao executor P0-D1 já testado.

Contrato:
- manifesto P0-C Semantic V3 fixo;
- exatamente 6 propostas READY_SAFE;
- backup P0-D1 fixo por ``backup_bundle_sha256``;
- default = VERIFY_ONLY, sem escrita;
- apply/rollback só alcançam P0-D1 com confirmação literal;
- nenhum argumento permite substituir manifesto, hash ou contagem aprovados.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys
from typing import Any, Optional, Sequence

from motor.motor_asyncio import AsyncIOMotorClient

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from scripts import apply_teacher_identity_backfill_p0d as implementation  # noqa: E402

PHASE_ID = "P0D2-SEALED-TEACHER-IDENTITY-BACKFILL-2026"
APPROVED_MANIFEST_SHA256 = (
    "68165e38d51e58071bd0d9b8d91114872b97841f987e8b630b9b6208b77bda9a"
)
APPROVED_SOURCE_P0B_SHA256 = (
    "519f078008fae82dc1277975fcf7de141a9231f391da9d1d47666db9e5f781be"
)
APPROVED_READY_COUNT = 6
APPROVED_BACKUP_BUNDLE_SHA256 = (
    "fac42381eb1d702002334be1e25d06ade594bf6376125a5008d09b995c7cc100"
)
APPROVED_DRY_RUN_EVIDENCE_DIR = "/root/sigesc-p0-audits/p0d1_20260828T025345Z"

APPLY_CONFIRMATION = "APPLY-P0D-TEACHER-IDENTITY-6"
ROLLBACK_CONFIRMATION = "ROLLBACK-P0D-TEACHER-IDENTITY-6"
DEFAULT_RECEIPT_DIR = "/tmp/sigesc-p0d2-teacher-identity-receipts"


class P0D2SealError(RuntimeError):
    """Violação do contrato selado P0-D2."""


def assert_implementation_contract() -> None:
    expected = {
        "APPROVED_MANIFEST_SHA256": APPROVED_MANIFEST_SHA256,
        "APPROVED_SOURCE_P0B_SHA256": APPROVED_SOURCE_P0B_SHA256,
        "APPROVED_READY_COUNT": APPROVED_READY_COUNT,
        "APPLY_CONFIRMATION": APPLY_CONFIRMATION,
        "ROLLBACK_CONFIRMATION": ROLLBACK_CONFIRMATION,
    }
    actual = {
        "APPROVED_MANIFEST_SHA256": implementation.APPROVED_MANIFEST_SHA256,
        "APPROVED_SOURCE_P0B_SHA256": implementation.APPROVED_SOURCE_P0B_SHA256,
        "APPROVED_READY_COUNT": implementation.APPROVED_READY_COUNT,
        "APPLY_CONFIRMATION": implementation.APPLY_CONFIRMATION,
        "ROLLBACK_CONFIRMATION": implementation.ROLLBACK_CONFIRMATION,
    }
    if actual != expected:
        raise P0D2SealError(
            f"P0D1_IMPLEMENTATION_CONTRACT_DRIFT expected={expected} actual={actual}"
        )


def build_implementation_args(args: argparse.Namespace) -> argparse.Namespace:
    backup_dir = Path(args.backup_dir)
    return argparse.Namespace(
        manifest=str(backup_dir / "manifest.json"),
        backup_dir=str(backup_dir),
        receipt_dir=str(Path(args.receipt_dir)),
        expected_backup_sha256=APPROVED_BACKUP_BUNDLE_SHA256,
        apply=bool(args.apply),
        rollback=bool(args.rollback),
        confirm=args.confirm,
    )


async def verify_only(db: Any, backup_dir: Path) -> dict[str, Any]:
    backup = implementation.load_and_verify_backup(
        backup_dir,
        expected_backup_sha256=APPROVED_BACKUP_BUNDLE_SHA256,
    )
    manifest = backup["manifest"]
    state = await implementation.inspect_live_state(db, manifest)

    live_manifest_sha: Optional[str] = None
    if state["state"] == "READY":
        live_manifest_sha = await implementation.assert_live_manifest_unchanged(db)
    elif state["state"] != "ALREADY_APPLIED":
        raise P0D2SealError(f"VERIFY_STATE_INVALID state={state['state']}")

    return {
        "phase": PHASE_ID,
        "mode": "VERIFY_ONLY",
        "status": "PASS",
        "database_mutation": False,
        "live_state": state["state"],
        "ready_count": APPROVED_READY_COUNT,
        "manifest_sha256": APPROVED_MANIFEST_SHA256,
        "live_manifest_sha256": live_manifest_sha,
        "source_p0b_evidence_sha256": APPROVED_SOURCE_P0B_SHA256,
        "backup_bundle_sha256": APPROVED_BACKUP_BUNDLE_SHA256,
        "backup_dir": str(backup_dir),
    }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    assert_implementation_contract()

    if args.apply and args.rollback:
        raise P0D2SealError("APPLY_ROLLBACK_MUTUALLY_EXCLUSIVE")

    backup_dir = Path(args.backup_dir)
    if not backup_dir.is_dir():
        raise P0D2SealError(f"BACKUP_DIR_MISSING path={backup_dir}")

    if not args.apply and not args.rollback:
        mongo_url = os.environ.get("MONGO_URL")
        db_name = os.environ.get("DB_NAME")
        if not mongo_url or not db_name:
            raise P0D2SealError("MONGO_URL_OR_DB_NAME_MISSING")
        client = AsyncIOMotorClient(mongo_url)
        try:
            return await verify_only(client[db_name], backup_dir)
        finally:
            client.close()

    impl_args = build_implementation_args(args)
    result = await implementation.run(impl_args)
    return {
        **result,
        "sealed_phase": PHASE_ID,
        "sealed_manifest_sha256": APPROVED_MANIFEST_SHA256,
        "sealed_backup_bundle_sha256": APPROVED_BACKUP_BUNDLE_SHA256,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "P0-D2 — entrypoint selado; default VERIFY_ONLY; "
            "apply/rollback exigem confirmação literal"
        )
    )
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--receipt-dir", default=DEFAULT_RECEIPT_DIR)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--confirm", default=None)
    return parser.parse_args(argv)


async def main() -> None:
    result = await run(parse_args())
    import json

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
