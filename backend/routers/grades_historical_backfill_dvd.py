"""P0 — paridade histórica de escrita de Notas após o cutover DVD.

Contrato espelhado no PR #84 da Frequência:
- não retrodata ``teacher_class_assignments``;
- não cria exceção genérica de vigência;
- só atravessa ``valid_from`` quando a origem 38G-B foi revalidada;
- nunca usa a ponte para contornar ``valid_until``;
- legado já não-nulo e sem ownership continua sem apropriação automática;
- campo owned por outro assignment continua bloqueado;
- online e sync offline usam o mesmo motor ``_save_one_dvd_grade``.

A estratégia é deliberadamente estreita: o motor canônico
``apply_grade_field_ownership`` permanece a SSoT da autoria. Para um único campo
pré-cutover comprovado, este adaptador fornece a ele um contexto efêmero cuja
vigência começa no período autorizado. Esse contexto nunca é persistido; apenas
o snapshot do ownership recebe a evidência histórica explícita.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Optional

from services.grade_assignment_scope import (
    GRADE_OWNERSHIP_FIELDS,
    GRADE_PERIOD,
    assignment_overlaps_grade_period,
)
from services.grade_cutover_history import (
    HISTORICAL_WRITE_FLAG,
    HISTORICAL_WRITE_PERIOD_START_FLAG,
    HISTORICAL_WRITE_SOURCE_FLAG,
    historical_grade_write_evidence,
)


def _historical_context(context, evidence: Mapping[str, Any]):
    """Cria contexto efêmero para um campo já validado como pré-cutover."""
    assignment = dict(context.assignment)
    assignment["valid_from"] = evidence[HISTORICAL_WRITE_PERIOD_START_FLAG]
    access = replace(context.access, assignment=assignment)
    snapshot = dict(context.snapshot)
    snapshot.update(dict(evidence))
    return replace(context, access=access, snapshot=snapshot)


def _build_historical_ownership_adapter(base_apply):
    """Envolve a SSoT de ownership sem duplicar suas regras de autoria."""

    async def apply_with_historical_cutover(
        db,
        current_user,
        existing: Optional[Mapping[str, Any]],
        changes: Mapping[str, Any],
        context,
        *,
        periods: Mapping[int, tuple[str, str]],
        allow_management_override: bool = False,
        active_mantenedora_id: Optional[str] = None,
    ) -> dict[str, Any]:
        existing_doc = dict(existing or {})
        ownership = dict(existing_doc.get("grade_ownership") or {})
        working_existing = dict(existing_doc)
        working_existing["grade_ownership"] = ownership

        # Campo a campo evita que a evidência histórica de B2 seja copiada para
        # B3/B4 que já são autorizados pela vigência normal do mesmo vínculo.
        for field, new_value in changes.items():
            if field not in GRADE_OWNERSHIP_FIELDS:
                continue

            field_context = context
            if not assignment_overlaps_grade_period(context.assignment, field, periods):
                period_number = GRADE_PERIOD.get(field)
                period = periods.get(period_number) if period_number is not None else None
                evidence = None
                if period_number is not None and period is not None:
                    evidence = await historical_grade_write_evidence(
                        db,
                        context,
                        field=field,
                        period_number=period_number,
                        period=period,
                    )
                if evidence:
                    field_context = _historical_context(context, evidence)

            # Sem evidência válida, o motor original recebe o contexto original e
            # preserva exatamente GRADE_PERIOD_OUTSIDE_ASSIGNMENT.
            ownership = await base_apply(
                db,
                current_user,
                working_existing,
                {field: new_value},
                field_context,
                periods=periods,
                allow_management_override=allow_management_override,
                active_mantenedora_id=active_mantenedora_id,
            )
            working_existing["grade_ownership"] = ownership

        return ownership

    return apply_with_historical_cutover


def _historical_change_metadata(updated: Mapping[str, Any], change: Optional[dict]) -> Optional[dict]:
    """Projeta evidência do ownership no evento de auditoria já existente."""
    if not change:
        return change

    ownership = updated.get("grade_ownership") or {}
    changed_fields = set((change.get("new") or {}).keys())
    historical_fields: list[str] = []
    source_ids: set[str] = set()
    for field in changed_fields:
        snapshot = ownership.get(field)
        if not isinstance(snapshot, Mapping):
            continue
        if snapshot.get(HISTORICAL_WRITE_FLAG) is not True:
            continue
        historical_fields.append(field)
        source_id = snapshot.get(HISTORICAL_WRITE_SOURCE_FLAG)
        if source_id:
            source_ids.add(str(source_id))

    if not historical_fields:
        return change

    return {
        **change,
        "historical_grade_write": True,
        "historical_fields": sorted(historical_fields),
        "historical_source_legacy_assignment_ids": sorted(source_ids),
    }


def _build_historical_save_adapter(base_save):
    async def save_with_historical_audit(db, user, request, context, payload):
        updated, change = await base_save(db, user, request, context, payload)
        return updated, _historical_change_metadata(updated, change)

    return save_with_historical_audit


def install_grades_historical_backfill_dvd() -> None:
    """Instala a ponte sobre o adaptador Fase 5, sem criar novas rotas."""
    from routers import grades_dvd as dvd_mod

    if getattr(dvd_mod, "_historical_grade_backfill_p0_installed", False):
        return

    if not hasattr(dvd_mod, "_historical_grade_original_apply_ownership"):
        dvd_mod._historical_grade_original_apply_ownership = dvd_mod.apply_grade_field_ownership
        dvd_mod.apply_grade_field_ownership = _build_historical_ownership_adapter(
            dvd_mod._historical_grade_original_apply_ownership
        )

    if not hasattr(dvd_mod, "_historical_grade_original_save_one"):
        dvd_mod._historical_grade_original_save_one = dvd_mod._save_one_dvd_grade
        dvd_mod._save_one_dvd_grade = _build_historical_save_adapter(
            dvd_mod._historical_grade_original_save_one
        )

    dvd_mod._historical_grade_backfill_p0_installed = True
