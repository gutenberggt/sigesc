"""Entrypoint de produção selado para a Segunda Onda DVD 2B.

Fixa integralmente o snapshot aprovado em produção após o preflight persistente.
Somente modo e token de confirmação podem ser informados em runtime.
Default: dry-run.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from typing import Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from scripts import apply_dvd_second_wave_2b as implementation  # noqa: E402

ACADEMIC_YEAR = 2026
REFERENCE_DATE = "2026-08-18"
APPROVED_READY_COUNT = 13
APPROVED_MANIFEST_SHA256 = "4d84e76b7236d2e6c5e0b8199165aa1e034d6d2529ceed05d248226ff9af72fc"
APPROVED_BACKUP_BUNDLE_SHA256 = "b481670bb416429254d1efb066ef614a50c2bf053957bd078fe5eba3ea8f81f6"
PERSISTENT_BACKUP_DIR = "/data/sigesc-dvd-backups/dvd-second-wave-2b-preflight-v1"
PERSISTENT_RECEIPT_DIR = "/data/sigesc-dvd-backups/receipts/second-wave-2b"

_ALLOWED_FLAGS = {"--apply", "--rollback"}


class PersistentSealArgumentError(RuntimeError):
    pass


def validate_runtime_args(args: Sequence[str]) -> list[str]:
    normalized = list(args)
    index = 0
    while index < len(normalized):
        token = normalized[index]
        if token in _ALLOWED_FLAGS:
            index += 1
            continue
        if token == "--confirm":
            if index + 1 >= len(normalized) or normalized[index + 1].startswith("--"):
                raise PersistentSealArgumentError("CONFIRM_VALUE_REQUIRED")
            index += 2
            continue
        if token.startswith("--confirm=") and token.split("=", 1)[1]:
            index += 1
            continue
        raise PersistentSealArgumentError(
            f"SEALED_ARGUMENT_OVERRIDE_NOT_ALLOWED argument={token}"
        )

    if "--apply" in normalized and "--rollback" in normalized:
        raise PersistentSealArgumentError("APPLY_ROLLBACK_MUTUALLY_EXCLUSIVE")
    return normalized


def build_locked_argv(runtime_args: Sequence[str]) -> list[str]:
    runtime = validate_runtime_args(runtime_args)
    return [
        str(Path(__file__)),
        "--academic-year",
        str(ACADEMIC_YEAR),
        "--reference-date",
        REFERENCE_DATE,
        "--expected-count",
        str(APPROVED_READY_COUNT),
        "--expected-manifest-sha256",
        APPROVED_MANIFEST_SHA256,
        "--expected-backup-sha256",
        APPROVED_BACKUP_BUNDLE_SHA256,
        "--backup-dir",
        PERSISTENT_BACKUP_DIR,
        "--receipt-dir",
        PERSISTENT_RECEIPT_DIR,
        *runtime,
    ]


async def main() -> None:
    original_argv = sys.argv[:]
    try:
        sys.argv = build_locked_argv(original_argv[1:])
        await implementation.main()
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    asyncio.run(main())
