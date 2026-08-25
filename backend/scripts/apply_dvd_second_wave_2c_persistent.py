"""Entrypoint de produção selado para a Segunda Onda DVD 2C.

O implementador 2C já fixa integralmente ano, escopo, manifesto, backup e recibos.
Este wrapper aceita somente modo e token de confirmação e mantém dry-run como
comportamento padrão.
"""
from __future__ import annotations

import asyncio
import sys
from typing import Sequence

from scripts import apply_dvd_second_wave_2c as implementation

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
    return [sys.argv[0], *validate_runtime_args(runtime_args)]


async def main() -> None:
    original_argv = sys.argv[:]
    try:
        sys.argv = build_locked_argv(original_argv[1:])
        await implementation.main()
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    asyncio.run(main())
