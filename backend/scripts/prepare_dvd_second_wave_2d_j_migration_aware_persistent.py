"""Entrypoint persistente da Segunda Onda DVD 2D-J migration-aware.

Permite executar o preflight diretamente em produção com:
    cd /app
    python scripts/prepare_dvd_second_wave_2d_j_migration_aware_persistent.py ...

Este wrapper somente corrige a resolução de imports quando o script é executado
por caminho. Toda a lógica permanece em ``prepare_dvd_second_wave_2d_j_migration_aware``.
Nenhum mutador Mongo existe aqui.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from scripts import prepare_dvd_second_wave_2d_j_migration_aware as implementation  # noqa: E402


if __name__ == "__main__":
    asyncio.run(implementation.main())
