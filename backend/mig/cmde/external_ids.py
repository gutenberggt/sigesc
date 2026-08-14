"""Registro persistente e separado de IDs externos SGP/CMDE.

Fase B.5 da interoperabilidade Student + Enrollment.

A coleção MIG é a fonte de verdade da integração para vínculos entre IDs internos
SIGESC e identificadores atribuídos pelo SGP. O serviço NÃO altera ``Student.id``
/ ``Enrollment.id`` e NÃO escreve nos documentos escolares durante reconciliação.

Princípios:
- tenant obrigatório para impedir colisões entre redes;
- somente ``student`` e ``enrollment`` nesta fase;
- IDs SGP normalizados como string decimal positiva, mesmo quando a API os retorna
  como inteiros;
- vínculo idempotente quando o mesmo par já existe;
- conflito explícito quando um ID interno tenta receber outro ID SGP ou quando um
  mesmo ID SGP tenta apontar para outro registro interno;
- nenhuma reatribuição silenciosa;
- auditoria operacional sem registrar o valor do ID externo.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict
from pymongo.errors import DuplicateKeyError

from mig.core.audit import MigAuditService


COLLECTION = "mig_sgp_external_ids"
PROVIDER = "cmde"
NAMESPACE = "sgp"

EntityType = Literal["student", "enrollment"]
LinkSource = Literal[
    "cmde_lookup",
    "lot_reconciliation",
    "manual_reconciliation",
    "legacy_compatibility",
]

_ALLOWED_ENTITY_TYPES = {"student", "enrollment"}
_ALLOWED_SOURCES = {
    "cmde_lookup",
    "lot_reconciliation",
    "manual_reconciliation",
    "legacy_compatibility",
}


class SgpExternalIdError(ValueError):
    """Erro base da camada de identidade externa SGP."""


class SgpExternalIdConflict(SgpExternalIdError):
    """O vínculo solicitado conflita com um vínculo persistido."""


class SgpExternalIdRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    provider: Literal["cmde"] = PROVIDER
    namespace: Literal["sgp"] = NAMESPACE
    tenant_id: str
    entity_type: EntityType
    internal_id: str
    external_id: str
    source: LinkSource
    correlation_id: Optional[str] = None
    lote_id: Optional[str] = None
    created_at: str
    updated_at: str


class SgpExternalIdLinkResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record: SgpExternalIdRecord
    created: bool
    idempotent: bool


class SgpExternalIdPair(BaseModel):
    """IDs SGP resolvidos para um Student + Enrollment interno."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    student_external_id: Optional[str] = None
    enrollment_external_id: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise SgpExternalIdError(f"{field_name}: valor textual obrigatório")
    normalized = value.strip()
    if not normalized:
        raise SgpExternalIdError(f"{field_name}: valor não pode ser vazio")
    return normalized


def _validate_entity_type(value: Any) -> EntityType:
    if value not in _ALLOWED_ENTITY_TYPES:
        raise SgpExternalIdError(
            "entity_type: somente student ou enrollment são suportados na B.5"
        )
    return value


def _validate_source(value: Any) -> LinkSource:
    if value not in _ALLOWED_SOURCES:
        raise SgpExternalIdError("source: origem de vínculo SGP não suportada")
    return value


def normalize_sgp_external_id(value: Any) -> str:
    """Normaliza IDs SGP para decimal positivo representado como string.

    A API pública CMDEB v2 apresenta ``id_sgp_estudante`` e
    ``id_sgp_matricula`` como inteiros. Persistir como string evita acoplamento
    ao limite numérico do provider e mantém estabilidade do contrato interno.
    """
    if isinstance(value, bool):
        raise SgpExternalIdError("external_id: booleano não é ID SGP válido")

    if isinstance(value, int):
        if value <= 0:
            raise SgpExternalIdError("external_id: ID SGP deve ser positivo")
        return str(value)

    if isinstance(value, str):
        normalized = value.strip()
        if not normalized.isdigit():
            raise SgpExternalIdError(
                "external_id: ID SGP deve conter somente dígitos"
            )
        normalized = normalized.lstrip("0") or "0"
        if normalized == "0":
            raise SgpExternalIdError("external_id: ID SGP deve ser positivo")
        return normalized

    raise SgpExternalIdError("external_id: tipo não suportado para ID SGP")


def _document_to_record(document: dict[str, Any]) -> SgpExternalIdRecord:
    clean = dict(document)
    clean.pop("_id", None)
    return SgpExternalIdRecord.model_validate(clean)


class SgpExternalIdStore:
    """Repositório MongoDB dos vínculos SIGESC -> SGP.

    O objeto ``db`` segue a interface assíncrona já usada no SIGESC/MIG
    (Motor): ``db[collection].find_one/insert_one/create_index``.
    """

    def __init__(self, db, audit: Optional[MigAuditService] = None):
        if db is None:
            raise SgpExternalIdError("db é obrigatório para persistência B.5")
        self.db = db
        self.collection = db[COLLECTION]
        self.audit = audit or MigAuditService(db)

    async def ensure_indexes(self) -> None:
        """Cria índices idempotentes de identidade e anti-colisão."""
        await self.collection.create_index("id", unique=True, name="ux_sgp_ext_id")
        await self.collection.create_index(
            [
                ("provider", 1),
                ("namespace", 1),
                ("tenant_id", 1),
                ("entity_type", 1),
                ("internal_id", 1),
            ],
            unique=True,
            name="ux_sgp_internal_link",
        )
        await self.collection.create_index(
            [
                ("provider", 1),
                ("namespace", 1),
                ("tenant_id", 1),
                ("entity_type", 1),
                ("external_id", 1),
            ],
            unique=True,
            name="ux_sgp_external_link",
        )
        await self.collection.create_index(
            [("tenant_id", 1), ("entity_type", 1), ("updated_at", -1)],
            name="ix_sgp_tenant_entity_updated",
        )

    @staticmethod
    def _base_query(*, tenant_id: str, entity_type: EntityType) -> dict[str, Any]:
        _validate_entity_type(entity_type)
        return {
            "provider": PROVIDER,
            "namespace": NAMESPACE,
            "tenant_id": _required_text(tenant_id, "tenant_id"),
            "entity_type": entity_type,
        }

    async def get(
        self,
        *,
        tenant_id: str,
        entity_type: EntityType,
        internal_id: str,
    ) -> Optional[SgpExternalIdRecord]:
        query = {
            **self._base_query(tenant_id=tenant_id, entity_type=entity_type),
            "internal_id": _required_text(internal_id, "internal_id"),
        }
        document = await self.collection.find_one(query)
        return _document_to_record(document) if document else None

    async def get_by_external(
        self,
        *,
        tenant_id: str,
        entity_type: EntityType,
        external_id: Any,
    ) -> Optional[SgpExternalIdRecord]:
        query = {
            **self._base_query(tenant_id=tenant_id, entity_type=entity_type),
            "external_id": normalize_sgp_external_id(external_id),
        }
        document = await self.collection.find_one(query)
        return _document_to_record(document) if document else None

    async def _audit_link(
        self,
        *,
        tenant_id: str,
        entity_type: EntityType,
        correlation_id: Optional[str],
        status: str,
        error_code: Optional[str] = None,
    ) -> None:
        await self.audit.record(
            {
                "provider": PROVIDER,
                "tenant": tenant_id,
                "operation": f"external_id.link.{entity_type}",
                "status": status,
                "correlation_id": correlation_id,
                "feature": "sgp_external_ids",
                "records_processed": 1,
                "error_code": error_code,
            }
        )

    async def link(
        self,
        *,
        tenant_id: str,
        entity_type: EntityType,
        internal_id: str,
        external_id: Any,
        source: LinkSource,
        correlation_id: Optional[str] = None,
        lote_id: Optional[str] = None,
    ) -> SgpExternalIdLinkResult:
        """Persiste um vínculo imutável quanto à identidade.

        Repetir exatamente o mesmo vínculo é idempotente. Qualquer tentativa de
        reatribuir um dos lados gera ``SgpExternalIdConflict``.
        """
        _validate_entity_type(entity_type)
        _validate_source(source)
        tenant = _required_text(tenant_id, "tenant_id")
        internal = _required_text(internal_id, "internal_id")
        external = normalize_sgp_external_id(external_id)
        correlation = (
            _required_text(correlation_id, "correlation_id")
            if correlation_id is not None
            else None
        )
        lote = _required_text(lote_id, "lote_id") if lote_id is not None else None

        current = await self.get(
            tenant_id=tenant,
            entity_type=entity_type,
            internal_id=internal,
        )
        if current is not None:
            if current.external_id == external:
                await self._audit_link(
                    tenant_id=tenant,
                    entity_type=entity_type,
                    correlation_id=correlation,
                    status="success",
                )
                return SgpExternalIdLinkResult(
                    record=current,
                    created=False,
                    idempotent=True,
                )

            await self._audit_link(
                tenant_id=tenant,
                entity_type=entity_type,
                correlation_id=correlation,
                status="error",
                error_code="external_id_internal_conflict",
            )
            raise SgpExternalIdConflict(
                f"{entity_type}:{internal} já possui outro ID SGP"
            )

        external_owner = await self.get_by_external(
            tenant_id=tenant,
            entity_type=entity_type,
            external_id=external,
        )
        if external_owner is not None and external_owner.internal_id != internal:
            await self._audit_link(
                tenant_id=tenant,
                entity_type=entity_type,
                correlation_id=correlation,
                status="error",
                error_code="external_id_external_conflict",
            )
            raise SgpExternalIdConflict(
                f"ID SGP de {entity_type} já está vinculado a outro registro SIGESC"
            )

        now = _now_iso()
        document = {
            "id": str(uuid.uuid4()),
            "provider": PROVIDER,
            "namespace": NAMESPACE,
            "tenant_id": tenant,
            "entity_type": entity_type,
            "internal_id": internal,
            "external_id": external,
            "source": source,
            "correlation_id": correlation,
            "lote_id": lote,
            "created_at": now,
            "updated_at": now,
        }

        try:
            await self.collection.insert_one(dict(document))
        except DuplicateKeyError as exc:
            # Corrida concorrente: refaz leitura para distinguir idempotência de conflito.
            winner = await self.get(
                tenant_id=tenant,
                entity_type=entity_type,
                internal_id=internal,
            )
            if winner is not None and winner.external_id == external:
                await self._audit_link(
                    tenant_id=tenant,
                    entity_type=entity_type,
                    correlation_id=correlation,
                    status="success",
                )
                return SgpExternalIdLinkResult(
                    record=winner,
                    created=False,
                    idempotent=True,
                )

            await self._audit_link(
                tenant_id=tenant,
                entity_type=entity_type,
                correlation_id=correlation,
                status="error",
                error_code="external_id_duplicate_key_conflict",
            )
            raise SgpExternalIdConflict(
                "conflito concorrente ao persistir vínculo de ID SGP"
            ) from exc

        record = _document_to_record(document)
        await self._audit_link(
            tenant_id=tenant,
            entity_type=entity_type,
            correlation_id=correlation,
            status="success",
        )
        return SgpExternalIdLinkResult(record=record, created=True, idempotent=False)

    async def resolve_pair(
        self,
        *,
        tenant_id: str,
        student_internal_id: str,
        enrollment_internal_id: str,
    ) -> SgpExternalIdPair:
        """Resolve IDs externos para hidratação futura do contrato canônico B.6."""
        student = await self.get(
            tenant_id=tenant_id,
            entity_type="student",
            internal_id=student_internal_id,
        )
        enrollment = await self.get(
            tenant_id=tenant_id,
            entity_type="enrollment",
            internal_id=enrollment_internal_id,
        )
        return SgpExternalIdPair(
            student_external_id=student.external_id if student else None,
            enrollment_external_id=enrollment.external_id if enrollment else None,
        )
