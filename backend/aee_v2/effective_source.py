"""Fase 6.1A — resolver central read-only da fonte efetiva do AEE.

Esta camada não cria, atualiza nem remove documentos. Ela apenas resolve qual
representação canônica deve ser consumida:

- snapshot V2 vigente, quando o head possui ``active_snapshot_id`` válido;
- projeção em memória do ``planos_aee`` legado, quando não existe V2 vigente.

Um ponteiro ativo quebrado/corrompido é falha de integridade e nunca provoca
fallback silencioso para o legado.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from .contracts import AEEDossierV2, AEELegacyMappingReport
from .legacy_mapper import project_legacy_plan
from .repository import AEEV2IntegrityError, AEEV2NotFound, AEEV2Repository
from .versioning import AEEV2Snapshot


class AEEEffectiveDossier(BaseModel):
    """Contrato único de leitura para futuros consumidores do AEE."""

    model_config = ConfigDict(extra="ignore")

    legacy_plano_id: str
    source: Literal["legacy", "sidecar_active"]
    dossier: AEEDossierV2
    active_snapshot_id: Optional[str] = None
    document_version: Optional[int] = None
    revision: Optional[int] = None
    legacy_mapping_report: Optional[AEELegacyMappingReport] = None


class AEEEffectiveSourceResolver:
    """Resolve a fonte efetiva sem qualquer efeito colateral de persistência."""

    def __init__(self, db):
        self.db = db
        self.repo = AEEV2Repository(db)

    async def resolve(self, legacy_plano_id: str) -> AEEEffectiveDossier:
        if not legacy_plano_id:
            raise ValueError("legacy_plano_id é obrigatório")

        legacy_plan = await self.db.planos_aee.find_one(
            {"id": legacy_plano_id},
            {"_id": 0},
        )
        head = await self.repo.get_head(legacy_plano_id)

        if not legacy_plan:
            if head:
                raise AEEV2IntegrityError(
                    "Head AEE v2 existe sem o Plano AEE legado que ancora a cadeia histórica."
                )
            raise AEEV2NotFound("Plano AEE legado não encontrado.")

        if not head or not head.get("active_snapshot_id"):
            projection = project_legacy_plan(legacy_plan)
            return AEEEffectiveDossier(
                legacy_plano_id=legacy_plano_id,
                source="legacy",
                dossier=projection.dossier,
                legacy_mapping_report=projection.report,
            )

        active_snapshot_id = str(head["active_snapshot_id"])
        active_raw = await self.repo.get_snapshot(active_snapshot_id)
        if not active_raw:
            raise AEEV2IntegrityError(
                "Head AEE v2 aponta para snapshot vigente inexistente; "
                "fallback legado foi bloqueado."
            )

        try:
            active = AEEV2Snapshot.model_validate(active_raw)
        except Exception as exc:
            raise AEEV2IntegrityError(
                "Snapshot vigente AEE v2 não atende ao contrato persistido."
            ) from exc

        if active.legacy_plano_id != legacy_plano_id:
            raise AEEV2IntegrityError(
                "Head AEE v2 aponta para snapshot de outro Plano AEE legado."
            )

        return AEEEffectiveDossier(
            legacy_plano_id=legacy_plano_id,
            source="sidecar_active",
            dossier=active.dossier,
            active_snapshot_id=active.id,
            document_version=active.document_version,
            revision=active.revision,
            legacy_mapping_report=None,
        )


async def resolve_effective_dossier(db, legacy_plano_id: str) -> AEEEffectiveDossier:
    """Atalho funcional para consumidores que não precisam reter o resolver."""

    return await AEEEffectiveSourceResolver(db).resolve(legacy_plano_id)
