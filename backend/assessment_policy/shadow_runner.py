"""Shadow Runner read-only da Assessment Policy v1.

Esta camada é deliberadamente operacional, mas não participa do runtime oficial
de Notas. Ela lê snapshots legados, resolve a policy publicada pelo contexto
acadêmico e delega a comparação ao Shadow Engine puro.

Invariantes:
- nenhuma escrita em Mongo;
- nenhuma chamada ao motor legado de cálculo;
- nenhuma inferência de mapping de campos;
- tenant scope deriva primeiro das turmas da mantenedora;
- falhas por registro são reportadas, não mascaradas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Optional, Sequence

from .context_builder import build_assessment_policy_context
from .exceptions import AssessmentPolicyError, POLICY_CONTEXT_MISMATCH
from .repository import AssessmentPolicyRepository
from .resolver import AssessmentPolicyResolver
from .shadow import (
    LegacyGradeFieldMapping,
    LegacyGradeSnapshot,
    ShadowBatchReport,
    calculate_mapping_hash,
    compare_legacy_grade_batch,
    legacy_grade_snapshot_from_document,
    validate_shadow_mapping,
)


SHADOW_RUNNER_MAPPING_REQUIRED = "ASSESSMENT_SHADOW_RUNNER_MAPPING_REQUIRED"
SHADOW_RUNNER_GRADE_TENANT_MISMATCH = "ASSESSMENT_SHADOW_RUNNER_GRADE_TENANT_MISMATCH"


@dataclass(frozen=True)
class ShadowRunnerIssue:
    grade_id: Optional[str]
    student_id: Optional[str]
    class_id: Optional[str]
    course_id: Optional[str]
    error_code: str
    error_message: str
    error_details: Optional[Any] = None


@dataclass(frozen=True)
class ShadowRunnerPolicyReport:
    policy_id: str
    policy_key: str
    policy_version: int
    rule_hash: str
    mapping_hash: str
    report: ShadowBatchReport


@dataclass(frozen=True)
class ShadowRunnerReport:
    mantenedora_id: str
    academic_year: int
    reference_date: date
    scanned: int
    compared: int
    unresolved: int
    comparable: int
    matches: int
    differences: int
    match_rate: Optional[float]
    groups: tuple[ShadowRunnerPolicyReport, ...]
    issues: tuple[ShadowRunnerIssue, ...]


class ShadowGradeReader:
    """Adapter Mongo estritamente read-only para o Shadow Runner."""

    BASE_GRADE_FIELDS = {
        "id",
        "student_id",
        "class_id",
        "course_id",
        "academic_year",
        "mantenedora_id",
        "final_average",
        "status",
    }

    def __init__(self, db):
        self.db = db

    async def list_tenant_classes(
        self,
        mantenedora_id: str,
        academic_year: int,
    ) -> dict[str, str]:
        cursor = self.db.classes.find(
            {
                "mantenedora_id": mantenedora_id,
                "academic_year": {"$in": [int(academic_year), str(int(academic_year))]},
            },
            {"_id": 0, "id": 1, "school_id": 1},
        )
        rows = await cursor.to_list(length=None)

        result: dict[str, str] = {}
        for row in rows:
            class_id = str(row.get("id") or "").strip()
            school_id = str(row.get("school_id") or "").strip()
            if not class_id or not school_id:
                raise AssessmentPolicyError(
                    POLICY_CONTEXT_MISMATCH,
                    "Turma do tenant não possui identidade/escola suficiente para o Shadow Runner.",
                    details={"class_id": class_id or None, "school_id": school_id or None},
                )
            result[class_id] = school_id
        return result

    async def list_grade_documents(
        self,
        *,
        class_ids: Sequence[str],
        academic_year: int,
        source_fields: Sequence[str],
        limit: Optional[int] = None,
    ) -> list[dict]:
        if not class_ids:
            return []

        projection = {field: 1 for field in self.BASE_GRADE_FIELDS | set(source_fields)}
        projection["_id"] = 0

        cursor = self.db.grades.find(
            {
                "class_id": {"$in": list(class_ids)},
                "academic_year": {"$in": [int(academic_year), str(int(academic_year))]},
            },
            projection,
        ).sort([("id", 1)])
        return await cursor.to_list(length=limit)


def _issue_from_exception(document: Mapping[str, Any], exc: AssessmentPolicyError) -> ShadowRunnerIssue:
    return ShadowRunnerIssue(
        grade_id=(str(document.get("id")) if document.get("id") is not None else None),
        student_id=(
            str(document.get("student_id"))
            if document.get("student_id") is not None
            else None
        ),
        class_id=(
            str(document.get("class_id"))
            if document.get("class_id") is not None
            else None
        ),
        course_id=(
            str(document.get("course_id"))
            if document.get("course_id") is not None
            else None
        ),
        error_code=exc.code,
        error_message=exc.message,
        error_details=exc.details,
    )


def _mapping_source_fields(
    mappings_by_policy_id: Mapping[str, LegacyGradeFieldMapping],
) -> tuple[str, ...]:
    fields: set[str] = set()
    for mapping in mappings_by_policy_id.values():
        fields.update(str(item) for item in mapping.period_field_map.keys())
        fields.update(str(item) for item in mapping.recovery_field_map.keys())
    return tuple(sorted(fields))


async def run_shadow_dry_run(
    db,
    *,
    mantenedora_id: str,
    academic_year: int,
    reference_date: date,
    mappings_by_policy_id: Mapping[str, LegacyGradeFieldMapping],
    class_ids: Optional[Sequence[str]] = None,
    tolerance: Any = "0.01",
    limit: Optional[int] = None,
    current_year: Optional[int] = None,
) -> ShadowRunnerReport:
    """Executa comparação read-only sobre Grade legado do tenant/ano.

    `mappings_by_policy_id` é obrigatório e explícito. O runner não conhece
    convenções municipais como b1/b2/rec_s1 e nunca cria mapping por heurística.
    """

    tenant = str(mantenedora_id or "").strip()
    if not tenant:
        raise AssessmentPolicyError(
            POLICY_CONTEXT_MISMATCH,
            "mantenedora_id é obrigatório para o Shadow Runner.",
        )
    year = int(academic_year)
    if reference_date.year != year:
        raise AssessmentPolicyError(
            POLICY_CONTEXT_MISMATCH,
            "reference_date deve pertencer ao academic_year do dry-run.",
            details={"academic_year": year, "reference_date": reference_date.isoformat()},
        )
    if limit is not None and int(limit) <= 0:
        raise AssessmentPolicyError(
            POLICY_CONTEXT_MISMATCH,
            "limit deve ser positivo quando informado.",
            details={"limit": limit},
        )

    reader = ShadowGradeReader(db)
    tenant_classes = await reader.list_tenant_classes(tenant, year)

    if class_ids is None:
        selected_class_ids = tuple(sorted(tenant_classes))
    else:
        selected_class_ids = tuple(sorted({str(item).strip() for item in class_ids if str(item).strip()}))
        outside = sorted(set(selected_class_ids) - set(tenant_classes))
        if outside:
            raise AssessmentPolicyError(
                POLICY_CONTEXT_MISMATCH,
                "class_ids contém turma fora do tenant/ano informado.",
                details={"class_ids": outside},
            )

    documents = await reader.list_grade_documents(
        class_ids=selected_class_ids,
        academic_year=year,
        source_fields=_mapping_source_fields(mappings_by_policy_id),
        limit=(int(limit) if limit is not None else None),
    )

    resolver = AssessmentPolicyResolver(AssessmentPolicyRepository(db))
    issues: list[ShadowRunnerIssue] = []
    grouped: dict[
        tuple[str, str],
        tuple[Any, LegacyGradeFieldMapping, list[LegacyGradeSnapshot]],
    ] = {}

    for document in documents:
        try:
            snapshot = legacy_grade_snapshot_from_document(document)

            explicit_tenant = str(document.get("mantenedora_id") or "").strip()
            if explicit_tenant and explicit_tenant != tenant:
                raise AssessmentPolicyError(
                    SHADOW_RUNNER_GRADE_TENANT_MISMATCH,
                    "Grade legado declara mantenedora diferente da turma tenant-scoped.",
                    details={
                        "grade_mantenedora_id": explicit_tenant,
                        "mantenedora_id": tenant,
                        "grade_id": snapshot.grade_id,
                    },
                )

            school_id = tenant_classes.get(snapshot.class_id)
            if not school_id:
                raise AssessmentPolicyError(
                    POLICY_CONTEXT_MISMATCH,
                    "Grade legado referencia turma fora do conjunto tenant-scoped.",
                    details={"class_id": snapshot.class_id},
                )

            context = await build_assessment_policy_context(
                db,
                mantenedora_id=tenant,
                school_id=school_id,
                class_id=snapshot.class_id,
                student_id=snapshot.student_id,
                component_id=snapshot.course_id,
                academic_year=year,
                reference_date=reference_date,
                current_year=current_year,
            )
            resolved = await resolver.resolve(context)
            policy = resolved.policy

            mapping = mappings_by_policy_id.get(policy.id)
            if mapping is None:
                raise AssessmentPolicyError(
                    SHADOW_RUNNER_MAPPING_REQUIRED,
                    "Policy resolvida não possui mapping legado explícito para o dry-run.",
                    details={
                        "policy_id": policy.id,
                        "policy_key": policy.policy_key,
                        "version": policy.version,
                    },
                )

            validated_mapping = validate_shadow_mapping(policy, mapping)
            mapping_hash = calculate_mapping_hash(validated_mapping)
            key = (policy.id, mapping_hash)
            if key not in grouped:
                grouped[key] = (policy, validated_mapping, [])
            grouped[key][2].append(snapshot)
        except AssessmentPolicyError as exc:
            issues.append(_issue_from_exception(document, exc))

    group_reports: list[ShadowRunnerPolicyReport] = []
    for key in sorted(grouped):
        policy, mapping, snapshots = grouped[key]
        report = compare_legacy_grade_batch(
            policy,
            snapshots,
            mapping,
            tolerance=tolerance,
        )
        group_reports.append(
            ShadowRunnerPolicyReport(
                policy_id=policy.id,
                policy_key=policy.policy_key,
                policy_version=policy.version,
                rule_hash=str(policy.rule_hash),
                mapping_hash=report.mapping_hash,
                report=report,
            )
        )

    compared = sum(item.report.total for item in group_reports)
    comparable = sum(item.report.comparable for item in group_reports)
    matches = sum(item.report.matches for item in group_reports)
    differences = sum(item.report.differences for item in group_reports)

    return ShadowRunnerReport(
        mantenedora_id=tenant,
        academic_year=year,
        reference_date=reference_date,
        scanned=len(documents),
        compared=compared,
        unresolved=len(issues),
        comparable=comparable,
        matches=matches,
        differences=differences,
        match_rate=(matches / comparable if comparable else None),
        groups=tuple(group_reports),
        issues=tuple(issues),
    )
