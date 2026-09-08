"""S2 — Resolver canônico de escopos de cutover para reporting de Conteúdo.

Esta camada é estritamente READ-ONLY. Ela transforma vínculos DVD válidos em
``ContentReportingCutoverScope`` para alimentar a projeção institucional criada
na S1, sem alterar consumidores operacionais e sem executar shadow em produção.

Princípios:
- ``classes`` ancora mantenedora + ano letivo;
- o vínculo precisa ser canonicamente válido para Conteúdo na ``reference_date``;
- ``diary_settings.enabled`` isolado nunca basta: a capability CONTENT também
  precisa estar habilitada pelo contrato do Diário por Vínculo;
- vínculo excluído, desabilitado, futuro ou encerrado não cria corte;
- componente específico e class-wide podem coexistir; a precedência do
  específico é aplicada posteriormente pelo read model S1;
- mais de um vínculo vigente para o mesmo escopo com ``valid_from`` diferente é
  ambíguo e falha fechado;
- nenhuma data é inferida de ``content_entries``, ``learning_objects`` ou da
  primeira ocorrência encontrada.

Nenhuma função deste módulo executa insert/update/replace/delete/bulk_write.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Optional

from services.content_reporting_projection import ContentReportingCutoverScope
from services.diary_assignment_access import DiaryAssignmentAccessError, effective_diary_settings
from services.diary_assignment_contract import is_class_in_scope


class ContentReportingCutoverResolutionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _iso_day(value: Any, *, code: str, label: str, required: bool = False) -> Optional[str]:
    if value is None or _norm(value) == "":
        if required:
            raise ContentReportingCutoverResolutionError(code, f"{label} é obrigatório.")
        return None
    if isinstance(value, datetime):
        normalized = value.date().isoformat()
    elif isinstance(value, date):
        normalized = value.isoformat()
    else:
        normalized = _norm(value)[:10]
    try:
        date.fromisoformat(normalized)
    except ValueError as exc:
        raise ContentReportingCutoverResolutionError(
            code,
            f"{label} deve usar data ISO YYYY-MM-DD válida.",
        ) from exc
    return normalized


def _year(value: Any) -> int:
    try:
        year = int(value)
    except (TypeError, ValueError) as exc:
        raise ContentReportingCutoverResolutionError(
            "CONTENT_REPORTING_CUTOVER_YEAR_INVALID",
            "O resolver S2 exige academic_year válido.",
        ) from exc
    if year < 1900 or year > 2200:
        raise ContentReportingCutoverResolutionError(
            "CONTENT_REPORTING_CUTOVER_YEAR_INVALID",
            "O resolver S2 exige academic_year válido.",
        )
    return year


def _reference_day(value: Any, *, academic_year: int) -> str:
    reference = _iso_day(
        value,
        code="CONTENT_REPORTING_CUTOVER_REFERENCE_DATE_INVALID",
        label="reference_date",
        required=True,
    )
    assert reference is not None
    if int(reference[:4]) != academic_year:
        raise ContentReportingCutoverResolutionError(
            "CONTENT_REPORTING_CUTOVER_REFERENCE_YEAR_MISMATCH",
            "reference_date deve pertencer ao academic_year consultado.",
        )
    return reference


def _validate_assignment_temporal(assignment: Mapping[str, Any]) -> tuple[str, Optional[str]]:
    valid_from = _iso_day(
        assignment.get("valid_from"),
        code="CONTENT_REPORTING_CUTOVER_VALID_FROM_INVALID",
        label="valid_from do vínculo",
        required=True,
    )
    valid_until = _iso_day(
        assignment.get("valid_until"),
        code="CONTENT_REPORTING_CUTOVER_VALID_UNTIL_INVALID",
        label="valid_until do vínculo",
    )
    assert valid_from is not None
    if valid_until and valid_until < valid_from:
        raise ContentReportingCutoverResolutionError(
            "CONTENT_REPORTING_CUTOVER_VALIDITY_INVALID",
            "valid_until do vínculo não pode ser anterior a valid_from.",
        )
    return valid_from, valid_until


def _is_current(valid_from: str, valid_until: Optional[str], reference_date: str) -> bool:
    return valid_from <= reference_date and (valid_until is None or valid_until >= reference_date)


@dataclass(frozen=True)
class ContentReportingCutoverResolution:
    mantenedora_id: str
    academic_year: int
    reference_date: str
    scopes: tuple[ContentReportingCutoverScope, ...]
    diagnostics: Mapping[str, int]


async def resolve_content_reporting_cutover_scopes(
    db,
    *,
    mantenedora_id: str,
    academic_year: int,
    reference_date: str,
    class_ids: Optional[Iterable[str]] = None,
) -> ContentReportingCutoverResolution:
    """Resolve escopos DVD vigentes sem alterar nenhuma coleção.

    O resolver é deliberadamente institucional: não autoriza um usuário nem
    substitui ``authorize_assignment_access``. Ele reutiliza apenas as invariantes
    canônicas necessárias para provar que o escopo já estava efetivamente no DVD
    para Conteúdo na data de referência.
    """
    tenant = _norm(mantenedora_id)
    if not tenant:
        raise ContentReportingCutoverResolutionError(
            "CONTENT_REPORTING_CUTOVER_TENANT_REQUIRED",
            "O resolver S2 exige mantenedora_id explícito.",
        )
    year = _year(academic_year)
    reference = _reference_day(reference_date, academic_year=year)
    requested_classes = {_norm(value) for value in (class_ids or []) if _norm(value)}

    class_query: dict[str, Any] = {
        "mantenedora_id": tenant,
        "academic_year": {"$in": [year, str(year)]},
    }
    if requested_classes:
        class_query["id"] = {"$in": sorted(requested_classes)}

    class_docs = await db.classes.find(
        class_query,
        {
            "_id": 0,
            "id": 1,
            "school_id": 1,
            "mantenedora_id": 1,
            "academic_year": 1,
            "education_level": 1,
            "nivel_ensino": 1,
            "grade_level": 1,
            "grade": 1,
            "atendimento_programa": 1,
        },
    ).to_list(5000)
    classes_by_id = {
        _norm(item.get("id")): dict(item)
        for item in class_docs
        if _norm(item.get("id"))
    }
    allowed_classes = set(classes_by_id)
    if requested_classes and allowed_classes != requested_classes:
        raise ContentReportingCutoverResolutionError(
            "CONTENT_REPORTING_CUTOVER_CLASS_OUT_OF_SCOPE",
            "Uma ou mais turmas não pertencem à mantenedora/ano consultados.",
        )

    diagnostics = {
        "classes_considered": len(allowed_classes),
        "assignments_seen": 0,
        "assignments_current_content": 0,
        "assignments_ignored_deleted": 0,
        "assignments_ignored_disabled": 0,
        "assignments_ignored_no_content_capability": 0,
        "assignments_ignored_not_current": 0,
        "duplicate_same_cutover_collapsed": 0,
    }
    if not allowed_classes:
        return ContentReportingCutoverResolution(
            mantenedora_id=tenant,
            academic_year=year,
            reference_date=reference,
            scopes=(),
            diagnostics=diagnostics,
        )

    assignments = await db.teacher_class_assignments.find(
        {"class_id": {"$in": sorted(allowed_classes)}},
        {
            "_id": 0,
            "id": 1,
            "teacher_id": 1,
            "class_id": 1,
            "component_id": 1,
            "school_id": 1,
            "mantenedora_id": 1,
            "valid_from": 1,
            "valid_until": 1,
            "deleted": 1,
            "diary_settings": 1,
        },
    ).to_list(30000)

    resolved: dict[tuple[str, Optional[str]], str] = {}
    for assignment in assignments:
        diagnostics["assignments_seen"] += 1
        class_id = _norm(assignment.get("class_id"))
        class_info = classes_by_id.get(class_id)
        if class_info is None:
            raise ContentReportingCutoverResolutionError(
                "CONTENT_REPORTING_CUTOVER_CLASS_OUT_OF_SCOPE",
                "Vínculo DVD referencia turma fora do tenant/ano autorizado.",
            )

        if assignment.get("deleted") is not False:
            diagnostics["assignments_ignored_deleted"] += 1
            continue

        assignment_tenant = _norm(assignment.get("mantenedora_id"))
        if assignment_tenant and assignment_tenant != tenant:
            raise ContentReportingCutoverResolutionError(
                "CONTENT_REPORTING_CUTOVER_TENANT_MISMATCH",
                "O tenant persistido no vínculo diverge da turma/mantenedora autorizada.",
            )

        assignment_school = _norm(assignment.get("school_id"))
        class_school = _norm(class_info.get("school_id"))
        if assignment_school and class_school and assignment_school != class_school:
            raise ContentReportingCutoverResolutionError(
                "CONTENT_REPORTING_CUTOVER_SCHOOL_MISMATCH",
                "A escola persistida no vínculo diverge da escola real da turma.",
            )

        try:
            settings = effective_diary_settings(assignment)
        except DiaryAssignmentAccessError as exc:
            raise ContentReportingCutoverResolutionError(
                "CONTENT_REPORTING_CUTOVER_SETTINGS_INVALID",
                f"Configuração DVD inválida no vínculo: {exc.code}.",
            ) from exc
        if not settings.enabled:
            diagnostics["assignments_ignored_disabled"] += 1
            continue
        if not settings.capabilities.content_enabled:
            diagnostics["assignments_ignored_no_content_capability"] += 1
            continue
        if not is_class_in_scope(class_info):
            raise ContentReportingCutoverResolutionError(
                "CONTENT_REPORTING_CUTOVER_CLASS_OUT_OF_DVD_SCOPE",
                "Há vínculo DVD de Conteúdo habilitado em turma fora do escopo canônico v1.",
            )

        valid_from, valid_until = _validate_assignment_temporal(assignment)
        if not _is_current(valid_from, valid_until, reference):
            diagnostics["assignments_ignored_not_current"] += 1
            continue

        diagnostics["assignments_current_content"] += 1
        component_id = _norm(assignment.get("component_id")) or None
        key = (class_id, component_id)
        previous = resolved.get(key)
        if previous is None:
            resolved[key] = valid_from
            continue
        if previous != valid_from:
            raise ContentReportingCutoverResolutionError(
                "CONTENT_REPORTING_CUTOVER_AMBIGUOUS",
                "Há vínculos DVD vigentes com datas de corte diferentes para o mesmo escopo.",
            )
        diagnostics["duplicate_same_cutover_collapsed"] += 1

    scopes = tuple(
        ContentReportingCutoverScope(
            class_id=class_id,
            component_id=component_id,
            valid_from=valid_from,
        )
        for (class_id, component_id), valid_from in sorted(
            resolved.items(),
            key=lambda item: (item[0][0], item[0][1] is None, item[0][1] or ""),
        )
    )
    return ContentReportingCutoverResolution(
        mantenedora_id=tenant,
        academic_year=year,
        reference_date=reference,
        scopes=scopes,
        diagnostics=diagnostics,
    )
