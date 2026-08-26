"""Reseal controlado da Fase 2 para o bundle persistente recriado em produção.

Este entrypoint NÃO altera a lógica do apply original. Ele apenas substitui o selo
imutável do bundle de backup efêmero perdido pelo bundle persistente atual, mantendo
manifesto, escopo, contagens, confirmações, optimistic concurrency e pós-check.

Motivo do novo BACKUP_BUNDLE_SHA256:
- o preflight inclui ``meta.generated_at`` em ``scope_v2_snapshot.json``;
- ao recriar o mesmo preflight em outro instante, o MANIFEST_SHA256 e o
  SCOPE_V2_SHA256 permanecem iguais, mas o hash do bundle muda por desenho;
- o novo bundle está em volume persistente homologado no Coolify.

Este script continua DRY-RUN por padrão. ``--apply`` continua exigindo autorização
humana explícita e as três confirmações do apply-base.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from scripts import apply_initial_years_schedule_normalization_phase2 as base  # noqa: E402

PREVIOUS_EPHEMERAL_BACKUP_BUNDLE_SHA256 = (
    "7fbb0bcee57d7b81e67a5aaf35f0e75aec86ca6f44e2d96a8d96ef53ebfc512f"
)
RESEALED_PERSISTENT_BACKUP_BUNDLE_SHA256 = (
    "30d346a56ee7cf991ba7dd7cd466a5b5a4e7293b11cfff6c3a70e0a99a313f59"
)
APPROVED_MANIFEST_SHA256 = (
    "550812a8358a587f1dbbf56ae1ebe1999889d66fd0829de66d69b72062a4e554"
)
APPROVED_SCOPE_V2_SHA256 = (
    "1815d025770d24f2bb109cb5598bc990f2f0ca4ce361095dc1446cbbb2de9b7d"
)
APPROVED_BACKUP_DIR = Path(
    "/data/sigesc-schedule-backups/initial-years-phase1-preflight-v1"
)


class Phase2ResealError(RuntimeError):
    pass


def activate_reseal() -> None:
    """Troca somente o hash autorizado do bundle; operação idempotente."""
    if base.APPROVED_MANIFEST_SHA256 != APPROVED_MANIFEST_SHA256:
        raise Phase2ResealError(
            "BASE_MANIFEST_SEAL_DRIFT "
            f"expected={APPROVED_MANIFEST_SHA256} actual={base.APPROVED_MANIFEST_SHA256}"
        )
    if base.APPROVED_SCOPE_V2_SHA256 != APPROVED_SCOPE_V2_SHA256:
        raise Phase2ResealError(
            "BASE_SCOPE_SEAL_DRIFT "
            f"expected={APPROVED_SCOPE_V2_SHA256} actual={base.APPROVED_SCOPE_V2_SHA256}"
        )
    if base.APPROVED_BACKUP_DIR.resolve() != APPROVED_BACKUP_DIR.resolve():
        raise Phase2ResealError(
            "BASE_BACKUP_DIR_DRIFT "
            f"expected={APPROVED_BACKUP_DIR} actual={base.APPROVED_BACKUP_DIR}"
        )

    current = base.APPROVED_BACKUP_BUNDLE_SHA256
    if current == RESEALED_PERSISTENT_BACKUP_BUNDLE_SHA256:
        return
    if current != PREVIOUS_EPHEMERAL_BACKUP_BUNDLE_SHA256:
        raise Phase2ResealError(
            "BASE_BACKUP_SEAL_UNEXPECTED "
            f"expected_old={PREVIOUS_EPHEMERAL_BACKUP_BUNDLE_SHA256} "
            f"expected_new={RESEALED_PERSISTENT_BACKUP_BUNDLE_SHA256} actual={current}"
        )

    base.APPROVED_BACKUP_BUNDLE_SHA256 = RESEALED_PERSISTENT_BACKUP_BUNDLE_SHA256


def main() -> None:
    activate_reseal()
    asyncio.run(base.main())


if __name__ == "__main__":
    main()
