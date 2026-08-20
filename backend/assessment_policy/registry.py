"""Registry/lifecycle da Assessment Policy Multi-Mantenedora v1.

O Registry coordena estados e invariantes, mas permanece isolado do runtime de
Notas nesta sprint. Não depende de FastAPI e aceita repository/checker por
contrato para permitir testes puros.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Awaitable, Callable, Iterable, Optional, Protocol, Sequence

from .exceptions import (
    AssessmentPolicyError,
    POLICY_CONCURRENT_MODIFICATION,
    POLICY_CONFLICT,
    POLICY_CONFLICT_CHECK_REQUIRED,
    POLICY_IDENTITY_IMMUTABLE,
    POLICY_IMMUTABLE,
    POLICY_INVALID_STATE,
    POLICY_NOT_FOUND,
    POLICY_TENANT_MISMATCH,
    POLICY_VALIDATION_FAILED,
    POLICY_VERSION_EXISTS,
)
from .models import AssessmentPolicy, PolicyStatus
from .validator import PolicyValidationReport, validate_policy


class PolicyRepository(Protocol):
    async def get(self, policy_id: str, mantenedora_id: str) -> Optional[AssessmentPolicy]: ...

    async def insert(self, policy: AssessmentPolicy) -> AssessmentPolicy: ...

    async def replace_if_status(
        self,
        policy: AssessmentPolicy,
        expected_statuses: Iterable[PolicyStatus],
    ) -> bool: ...

    async def exists_policy_version(
        self,
        mantenedora_id: str,
        policy_key: str,
        version: int,
    ) -> bool: ...


class PolicyConflictChecker(Protocol):
    async def find_publish_conflicts(self, policy: AssessmentPolicy) -> Sequence[str]: ...


NowFactory = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AssessmentPolicyRegistry:
    """Lifecycle determinístico e tenant-scoped das políticas avaliativas."""

    def __init__(
        self,
        repository: PolicyRepository,
        *,
        conflict_checker: Optional[PolicyConflictChecker] = None,
        now_factory: NowFactory = _utc_now,
    ):
        self.repository = repository
        self.conflict_checker = conflict_checker
        self.now_factory = now_factory

    @staticmethod
    def _require_tenant(policy: AssessmentPolicy, mantenedora_id: str) -> None:
        if policy.mantenedora_id != mantenedora_id:
            raise AssessmentPolicyError(
                POLICY_TENANT_MISMATCH,
                "A política não pertence à mantenedora ativa.",
                details={
                    "policy_mantenedora_id": policy.mantenedora_id,
                    "requested_mantenedora_id": mantenedora_id,
                },
            )

    @staticmethod
    def _require_mutable_draft(current: AssessmentPolicy) -> None:
        if current.status in {
            PolicyStatus.PUBLISHED,
            PolicyStatus.SUPERSEDED,
            PolicyStatus.RETIRED,
        }:
            raise AssessmentPolicyError(
                POLICY_IMMUTABLE,
                "Política publicada/histórica é imutável; crie uma nova versão.",
            )
        if current.status != PolicyStatus.DRAFT:
            raise AssessmentPolicyError(
                POLICY_INVALID_STATE,
                f"Operação exige status draft; status atual={current.status.value}.",
            )

    @staticmethod
    def _require_identity_unchanged(
        current: AssessmentPolicy,
        candidate: AssessmentPolicy,
    ) -> None:
        immutable_identity = (
            "id",
            "mantenedora_id",
            "policy_key",
            "version",
        )
        changed = [
            field
            for field in immutable_identity
            if getattr(current, field) != getattr(candidate, field)
        ]
        if changed:
            raise AssessmentPolicyError(
                POLICY_IDENTITY_IMMUTABLE,
                "A identidade da versão da política não pode ser alterada.",
                details={"changed_fields": changed},
            )

    async def _get_required(
        self,
        policy_id: str,
        mantenedora_id: str,
    ) -> AssessmentPolicy:
        current = await self.repository.get(policy_id, mantenedora_id)
        if current is None:
            raise AssessmentPolicyError(
                POLICY_NOT_FOUND,
                "Política avaliativa não encontrada no escopo da mantenedora ativa.",
            )
        self._require_tenant(current, mantenedora_id)
        return current

    async def _replace_or_conflict(
        self,
        policy: AssessmentPolicy,
        expected_statuses: Iterable[PolicyStatus],
    ) -> AssessmentPolicy:
        replaced = await self.repository.replace_if_status(policy, expected_statuses)
        if not replaced:
            raise AssessmentPolicyError(
                POLICY_CONCURRENT_MODIFICATION,
                "A política foi alterada por outra operação; recarregue antes de continuar.",
            )
        return policy

    async def create_draft(
        self,
        mantenedora_id: str,
        policy: AssessmentPolicy,
        *,
        actor_id: str,
    ) -> AssessmentPolicy:
        self._require_tenant(policy, mantenedora_id)

        if policy.status != PolicyStatus.DRAFT:
            raise AssessmentPolicyError(
                POLICY_INVALID_STATE,
                "Nova política deve ser criada em status draft.",
            )
        if policy.rule_hash is not None:
            raise AssessmentPolicyError(
                POLICY_INVALID_STATE,
                "Draft novo não pode carregar rule_hash de versão publicada/validada.",
            )
        if await self.repository.exists_policy_version(
            mantenedora_id,
            policy.policy_key,
            policy.version,
        ):
            raise AssessmentPolicyError(
                POLICY_VERSION_EXISTS,
                "Já existe esta versão da política para a mantenedora.",
            )

        now = self.now_factory()
        created = policy.model_copy(
            update={
                "status": PolicyStatus.DRAFT,
                "rule_hash": None,
                "created_by": actor_id,
                "created_at": now,
                "validated_by": None,
                "validated_at": None,
                "published_by": None,
                "published_at": None,
            }
        )
        return await self.repository.insert(created)

    async def save_draft(
        self,
        mantenedora_id: str,
        policy: AssessmentPolicy,
        *,
        actor_id: str,
    ) -> AssessmentPolicy:
        del actor_id  # autoria detalhada de edição será registrada no audit adapter futuro

        self._require_tenant(policy, mantenedora_id)
        current = await self._get_required(policy.id, mantenedora_id)
        self._require_mutable_draft(current)
        self._require_identity_unchanged(current, policy)

        candidate = policy.model_copy(
            update={
                "status": PolicyStatus.DRAFT,
                "rule_hash": None,
                "created_by": current.created_by,
                "created_at": current.created_at,
                "validated_by": None,
                "validated_at": None,
                "published_by": None,
                "published_at": None,
            }
        )
        return await self._replace_or_conflict(candidate, [PolicyStatus.DRAFT])

    async def validate_draft(
        self,
        mantenedora_id: str,
        policy_id: str,
        *,
        actor_id: str,
    ) -> tuple[AssessmentPolicy, PolicyValidationReport]:
        current = await self._get_required(policy_id, mantenedora_id)
        self._require_mutable_draft(current)

        report = validate_policy(current, for_publish=True)
        if not report.valid:
            raise AssessmentPolicyError(
                POLICY_VALIDATION_FAILED,
                "A política possui erros e não pode ser validada.",
                details=report.model_dump(mode="json"),
            )

        validated = current.model_copy(
            update={
                "status": PolicyStatus.VALIDATED,
                "rule_hash": report.calculated_rule_hash,
                "validated_by": actor_id,
                "validated_at": self.now_factory(),
            }
        )
        validated = await self._replace_or_conflict(validated, [PolicyStatus.DRAFT])
        return validated, report

    async def reopen_validated(
        self,
        mantenedora_id: str,
        policy_id: str,
        *,
        actor_id: str,
    ) -> AssessmentPolicy:
        del actor_id

        current = await self._get_required(policy_id, mantenedora_id)
        if current.status != PolicyStatus.VALIDATED:
            if current.status in {
                PolicyStatus.PUBLISHED,
                PolicyStatus.SUPERSEDED,
                PolicyStatus.RETIRED,
            }:
                raise AssessmentPolicyError(
                    POLICY_IMMUTABLE,
                    "Política publicada/histórica não pode voltar para draft.",
                )
            raise AssessmentPolicyError(
                POLICY_INVALID_STATE,
                f"Operação exige status validated; status atual={current.status.value}.",
            )

        reopened = current.model_copy(
            update={
                "status": PolicyStatus.DRAFT,
                "rule_hash": None,
                "validated_by": None,
                "validated_at": None,
                "published_by": None,
                "published_at": None,
            }
        )
        return await self._replace_or_conflict(reopened, [PolicyStatus.VALIDATED])

    async def publish(
        self,
        mantenedora_id: str,
        policy_id: str,
        *,
        actor_id: str,
    ) -> AssessmentPolicy:
        current = await self._get_required(policy_id, mantenedora_id)

        if current.status in {
            PolicyStatus.PUBLISHED,
            PolicyStatus.SUPERSEDED,
            PolicyStatus.RETIRED,
        }:
            raise AssessmentPolicyError(
                POLICY_IMMUTABLE,
                "Política publicada/histórica é imutável.",
            )
        if current.status != PolicyStatus.VALIDATED:
            raise AssessmentPolicyError(
                POLICY_INVALID_STATE,
                f"Publicação exige status validated; status atual={current.status.value}.",
            )

        report = validate_policy(current, for_publish=True)
        if not report.valid or current.rule_hash != report.calculated_rule_hash:
            raise AssessmentPolicyError(
                POLICY_VALIDATION_FAILED,
                "A política mudou após a validação ou não satisfaz mais o contrato de publicação.",
                details=report.model_dump(mode="json"),
            )

        # A checagem de conflitos depende do Resolver/escopos persistidos. Até
        # existir um checker real, publicação deve falhar fechado — nunca assumir
        # que ausência de checker significa ausência de conflito.
        if self.conflict_checker is None:
            raise AssessmentPolicyError(
                POLICY_CONFLICT_CHECK_REQUIRED,
                "Publicação exige verificação explícita de conflitos de escopo/vigência.",
            )

        conflicts = list(await self.conflict_checker.find_publish_conflicts(current))
        if conflicts:
            raise AssessmentPolicyError(
                POLICY_CONFLICT,
                "A política conflita com outra versão publicada no mesmo contexto.",
                details={"conflicts": conflicts},
            )

        published = current.model_copy(
            update={
                "status": PolicyStatus.PUBLISHED,
                "rule_hash": report.calculated_rule_hash,
                "published_by": actor_id,
                "published_at": self.now_factory(),
            }
        )
        return await self._replace_or_conflict(published, [PolicyStatus.VALIDATED])
