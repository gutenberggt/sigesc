"""Entrypoint de produção selado para a Segunda Onda DVD 2A-B.

Este wrapper fixa o snapshot aprovado em produção após a validação do volume
persistente do Coolify. Ele delega toda a inspeção, dry-run, apply e rollback ao
implementador genérico ``apply_dvd_second_wave_2a.py``, mas impede override dos
parâmetros autorizativos.

Default: dry-run. Nenhuma escrita ocorre sem ``--apply`` e a confirmação já
exigida pelo implementador 2A-B.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from typing import Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from scripts import apply_dvd_second_wave_2a as implementation  # noqa: E402

ACADEMIC_YEAR = 2026
REFERENCE_DATE = "2026-08-18"
APPROVED_READY_COUNT = 27
APPROVED_MANIFEST_SHA256 = "7ab088f1705c28894adadd4b9d294440cf07d77030ed6ae2d8af7435b043b546"
APPROVED_BACKUP_BUNDLE_SHA256 = "4126da5a84ee2db2dd5071b58a9e019a04db56896c2ad4c24ba0474b0fd58620"
PERSISTENT_BACKUP_DIR = "/data/sigesc-dvd-backups/dvd-second-wave-2a-preflight-v2"
PERSISTENT_RECEIPT_DIR = "/data/sigesc-dvd-backups/receipts/second-wave-2a"

_ALLOWED_FLAGS = {"--apply", "--rollback"}
_ALLOWED_VALUE_OPTIONS = {"--confirm"}


class PersistentSealArgumentError(RuntimeError):
    pass


def validate_runtime_args(args: Sequence[str]) -> list[str]:
    """Aceita somente seleção de modo e confirmação; todo o escopo fica selado."""
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
