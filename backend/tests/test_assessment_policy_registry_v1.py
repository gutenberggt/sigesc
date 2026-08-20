"""Testes puros do Registry da Assessment Policy v1."""

from datetime import date, datetime, timezone

import pytest

from assessment_policy.canonical import calculate_rule_hash
from assessment_policy.exceptions import (
    AssessmentPolicyError,
    POLICY_CONCURRENT_MODIFICATION,
    POLICY_CONFLICT,
    POLICY_CONFLICT_CHECK_REQUIRED,
    POLICY_IDENTITY_IMMUTABLE,
    POLICY_IMMUTABLE,
    POLICY_TENANT_MISMATCH,
    POLICY_VERSION_EXISTS,
)
from assessment_policy.indexes import ASSESSMENT_POLICY_INDEXES
from assessment_policy.models import (
    AcademicOutcomeRule,
    AssessmentMode,
    AssessmentPolicy,
    AssessmentRule,
    AttendanceBasis,
    CalculationRule,
    CalculationStrategy,
    ConceptScaleEntry,
    NormativeSource,
    PeriodRule,
    PolicyScope,
    PolicyStatus,
    RecoveryGroup,
    RecoveryRule,
)
from assessment_policy.registry import AssessmentPolicyRegistry
from assessment_policy.repository import AssessmentPolicyRepository


FIXED_NOW = datetime(2026, 8, 19, 21, 0, tzinfo=timezone.utc)


def _policy(*, tenant="tenant-a", policy_id="p1", version=1):
    return AssessmentPolicy(
        id=policy_id,
        policy_key="EF_1_2_CONCEITUAL",
        version=version,
        mantenedora_id=tenant,
        name="EF — 1º e 2º Ano — 2026",
        status=PolicyStatus.DRAFT,
        academic_year=2026,
        effective_from=date(2026, 1, 1),
        effective_until=date(2026, 12, 31),
        scope=PolicyScope(series=["1º Ano", "2º Ano"]),
        assessment=AssessmentRule(
            mode=AssessmentMode.CONCEPTUAL,
            conceptual_scale=[
                ConceptScaleEntry(code="C", label="Consolidado", numeric_value=10),
                ConceptScaleEntry(code="ED", label="Em Desenvolvimento", numeric_value=7.5),
                ConceptScaleEntry(code="ND", label="Não Desenvolvido", numeric_value=5),
            ],
            periods=[
                PeriodRule(code="b1", label="1º Bimestre", weight=2),
                PeriodRule(code="b2", label="2º Bimestre", weight=3),
                PeriodRule(code="b3", label="3º Bimestre", weight=2),
                PeriodRule(code="b4", label="4º Bimestre", weight=3),
            ],
            calculation=CalculationRule(strategy=CalculationStrategy.WEIGHTED_AVERAGE),
        ),
        recovery=RecoveryRule(
            enabled=True,
            groups=[
                RecoveryGroup(
                    code="r1",
                    label="Recuperação 1",
                    input_code="rec_s1",
                    period_codes=["b1", "b2"],
                    only_if_improves=True,
                ),
                RecoveryGroup(
                    code="r2",
                    label="Recuperação 2",
                    input_code="rec_s2",
                    period_codes=["b3", "b4"],
                    only_if_improves=True,
                ),
            ],
        ),
        academic_outcome=AcademicOutcomeRule(
            minimum_component_average=5,
            minimum_attendance_percentage=75,
            attendance_basis=AttendanceBasis.GLOBAL,
        ),
        normative_sources=[
            NormativeSource(type="internal_policy", title="Política formal da mantenedora")
        ],
    )


class FakeRepository:
    def __init__(self):
        self.docs = {}
        self.force_replace_failure = False

    async def get(self, policy_id, mantenedora_id):
        return self.docs.get((mantenedora_id, policy_id))

    async def insert(self, policy):
        self.docs[(policy.mantenedora_id, policy.id)] = policy
        return policy

    async def replace_if_status(self, policy, expected_statuses):
        if self.force_replace_failure:
            return False
        key = (policy.mantenedora_id, policy.id)
        current = self.docs.get(key)
        if current is None or current.status not in set(expected_statuses):
            return False
        self.docs[key] = policy
        return True

    async def exists_policy_version(self, mantenedora_id, policy_key, version):
        return any(
            doc.mantenedora_id == mantenedora_id
            and doc.policy_key == policy_key
            and doc.version == version
            for doc in self.docs.values()
        )


class AllowConflicts:
    async def find_publish_conflicts(self, policy):
        return []


class DenyConflicts:
    async def find_publish_conflicts(self, policy):
        return ["policy-other-v1"]


def _registry(repo, checker=None):
    return AssessmentPolicyRegistry(
        repo,
        conflict_checker=checker,
        now_factory=lambda: FIXED_NOW,
    )


@pytest.mark.asyncio
async def test_create_draft_is_tenant_scoped_and_sets_audit_metadata():
    repo = FakeRepository()
    created = await _registry(repo).create_draft("tenant-a", _policy(), actor_id="admin-1")

    assert created.status == PolicyStatus.DRAFT
    assert created.mantenedora_id == "tenant-a"
    assert created.created_by == "admin-1"
    assert created.created_at == FIXED_NOW
    assert await repo.get("p1", "tenant-b") is None


@pytest.mark.asyncio
async def test_cross_tenant_create_fails_closed():
    with pytest.raises(AssessmentPolicyError) as exc:
        await _registry(FakeRepository()).create_draft(
            "tenant-b",
            _policy(tenant="tenant-a"),
            actor_id="admin-1",
        )

    assert exc.value.code == POLICY_TENANT_MISMATCH


@pytest.mark.asyncio
async def test_duplicate_policy_key_version_is_rejected_per_tenant():
    repo = FakeRepository()
    registry = _registry(repo)
    await registry.create_draft("tenant-a", _policy(policy_id="p1"), actor_id="admin")

    with pytest.raises(AssessmentPolicyError) as exc:
        await registry.create_draft(
            "tenant-a",
            _policy(policy_id="p2"),
            actor_id="admin",
        )

    assert exc.value.code == POLICY_VERSION_EXISTS

    # Mesma chave/versão em outra mantenedora é permitida.
    other = await registry.create_draft(
        "tenant-b",
        _policy(tenant="tenant-b", policy_id="p3"),
        actor_id="admin-b",
    )
    assert other.mantenedora_id == "tenant-b"


@pytest.mark.asyncio
async def test_draft_identity_cannot_be_changed_on_save():
    repo = FakeRepository()
    registry = _registry(repo)
    current = await registry.create_draft("tenant-a", _policy(), actor_id="admin")
    mutated = current.model_copy(update={"policy_key": "OUTRA_CHAVE"})

    with pytest.raises(AssessmentPolicyError) as exc:
        await registry.save_draft("tenant-a", mutated, actor_id="admin")

    assert exc.value.code == POLICY_IDENTITY_IMMUTABLE


@pytest.mark.asyncio
async def test_validate_draft_sets_hash_and_validated_state():
    repo = FakeRepository()
    registry = _registry(repo)
    await registry.create_draft("tenant-a", _policy(), actor_id="admin")

    validated, report = await registry.validate_draft("tenant-a", "p1", actor_id="reviewer")

    assert report.valid is True
    assert validated.status == PolicyStatus.VALIDATED
    assert validated.rule_hash == calculate_rule_hash(validated)
    assert validated.validated_by == "reviewer"
    assert validated.validated_at == FIXED_NOW


@pytest.mark.asyncio
async def test_reopen_validated_clears_hash_and_validation_metadata():
    repo = FakeRepository()
    registry = _registry(repo)
    await registry.create_draft("tenant-a", _policy(), actor_id="admin")
    await registry.validate_draft("tenant-a", "p1", actor_id="reviewer")

    reopened = await registry.reopen_validated("tenant-a", "p1", actor_id="admin")

    assert reopened.status == PolicyStatus.DRAFT
    assert reopened.rule_hash is None
    assert reopened.validated_by is None
    assert reopened.validated_at is None


@pytest.mark.asyncio
async def test_publish_requires_conflict_checker_fail_closed():
    repo = FakeRepository()
    registry = _registry(repo)
    await registry.create_draft("tenant-a", _policy(), actor_id="admin")
    await registry.validate_draft("tenant-a", "p1", actor_id="reviewer")

    with pytest.raises(AssessmentPolicyError) as exc:
        await registry.publish("tenant-a", "p1", actor_id="publisher")

    assert exc.value.code == POLICY_CONFLICT_CHECK_REQUIRED


@pytest.mark.asyncio
async def test_publish_rejects_ambiguous_scope_conflict():
    repo = FakeRepository()
    registry = _registry(repo, DenyConflicts())
    await registry.create_draft("tenant-a", _policy(), actor_id="admin")
    await registry.validate_draft("tenant-a", "p1", actor_id="reviewer")

    with pytest.raises(AssessmentPolicyError) as exc:
        await registry.publish("tenant-a", "p1", actor_id="publisher")

    assert exc.value.code == POLICY_CONFLICT
    assert exc.value.details == {"conflicts": ["policy-other-v1"]}


@pytest.mark.asyncio
async def test_publish_freezes_policy_and_blocks_future_edit():
    repo = FakeRepository()
    registry = _registry(repo, AllowConflicts())
    await registry.create_draft("tenant-a", _policy(), actor_id="admin")
    await registry.validate_draft("tenant-a", "p1", actor_id="reviewer")

    published = await registry.publish("tenant-a", "p1", actor_id="publisher")

    assert published.status == PolicyStatus.PUBLISHED
    assert published.published_by == "publisher"
    assert published.published_at == FIXED_NOW
    assert published.rule_hash == calculate_rule_hash(published)

    with pytest.raises(AssessmentPolicyError) as exc:
        await registry.save_draft("tenant-a", published, actor_id="admin")

    assert exc.value.code == POLICY_IMMUTABLE


@pytest.mark.asyncio
async def test_concurrent_state_change_fails_instead_of_overwriting():
    repo = FakeRepository()
    registry = _registry(repo)
    await registry.create_draft("tenant-a", _policy(), actor_id="admin")
    repo.force_replace_failure = True

    with pytest.raises(AssessmentPolicyError) as exc:
        await registry.validate_draft("tenant-a", "p1", actor_id="reviewer")

    assert exc.value.code == POLICY_CONCURRENT_MODIFICATION


class CaptureCollection:
    def __init__(self):
        self.query = None

    async def find_one(self, query, projection):
        self.query = query
        return None


class CaptureDB:
    def __init__(self):
        self.collection = CaptureCollection()

    def __getitem__(self, name):
        assert name == "assessment_policies"
        return self.collection


@pytest.mark.asyncio
async def test_mongo_repository_get_always_filters_policy_and_tenant():
    db = CaptureDB()
    repository = AssessmentPolicyRepository(db)

    assert await repository.get("policy-x", "tenant-a") is None
    assert db.collection.query == {
        "id": "policy-x",
        "mantenedora_id": "tenant-a",
    }


def test_index_specs_keep_identity_unique_inside_tenant():
    specs = {spec.name: spec for spec in ASSESSMENT_POLICY_INDEXES}

    assert specs["uq_assessment_policy_tenant_id"].unique is True
    assert specs["uq_assessment_policy_tenant_key_version"].unique is True
    assert specs["uq_assessment_policy_tenant_key_version"].keys == (
        ("mantenedora_id", 1),
        ("policy_key", 1),
        ("version", 1),
    )


def test_scope_indexes_never_combine_multiple_array_dimensions():
    array_fields = {
        "scope.school_ids",
        "scope.class_ids",
        "scope.component_ids",
        "scope.series",
        "scope.education_stages",
        "scope.modalities",
    }

    for spec in ASSESSMENT_POLICY_INDEXES:
        used_arrays = [field for field, _ in spec.keys if field in array_fields]
        assert len(used_arrays) <= 1, spec.name
