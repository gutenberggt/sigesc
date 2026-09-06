"""P0 — visibilidade institucional de notas autorizadas no DVD.

Regra de negócio:
- ``grades`` é um registro acadêmico institucional da turma/componente;
- um perfil autorizado a ler esse escopo deve enxergar os valores já salvos;
- ``grade_ownership`` continua governando AUTORIA e ESCRITA, nunca ocultação do
  valor acadêmico;
- campos pertencentes a outro vínculo permanecem somente leitura para o
  professor e seus snapshots de autoria não são expostos.

A camada é instalada depois de ``grades_dvd_hardening`` e
``grades_dvd_parity``. Ela não altera documentos, ownership, cálculo de média ou
regras de escrita; apenas corrige as projeções de leitura e o pull offline.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from services.grade_assignment_scope import (
    GRADE_OWNERSHIP_FIELDS,
    owned_fields_for_assignment,
)
from services.teacher_grade_access import (
    list_teacher_grade_scopes,
    resolve_teacher_grade_scope,
)
from tenant_scope import apply_tenant_filter, get_mantenedora_scope


def _non_null_fields(grade: Mapping[str, Any]) -> set[str]:
    return {
        field
        for field in GRADE_OWNERSHIP_FIELDS
        if grade.get(field) is not None
    }


def _project_authorized_grade_for_assignment(
    grade: Mapping[str, Any],
    context,
    *,
    mask_foreign: bool = True,
) -> dict[str, Any]:
    """Exibe todos os valores do escopo autorizado e preserva trava de autoria."""
    out = dict(grade)
    ownership = grade.get("grade_ownership") or {}
    owned = set(owned_fields_for_assignment(grade, context.assignment_id))
    present = _non_null_fields(grade)
    locked = present - owned

    # Metadado de autoria de outro professor/vínculo não é necessário para a
    # leitura institucional. O valor acadêmico é visível; a identidade do autor
    # permanece restrita ao próprio vínculo/gestão.
    if mask_foreign:
        out["grade_ownership"] = {
            field: dict(snapshot)
            for field, snapshot in ownership.items()
            if field in owned and isinstance(snapshot, Mapping)
        }

    legacy_allowed = bool(
        getattr(context, "snapshot", {}).get("legacy_grade_history_read")
    )
    legacy_fields = {
        field
        for field in present
        if legacy_allowed and field not in ownership
    }

    out["dvd_assignment_id"] = context.assignment_id
    out["dvd_owned_fields"] = sorted(owned)
    out["dvd_locked_fields"] = sorted(locked)
    out["dvd_read_only_fields"] = sorted(legacy_fields)
    out["legacy_history"] = bool(legacy_fields)
    if legacy_fields and owned:
        out["history_source"] = "grades_mixed"
    elif legacy_fields:
        out["history_source"] = "grades_legacy"
    else:
        out["history_source"] = "grades_dvd"

    # Deliberadamente NÃO mascara b1..b4, recuperações, média ou situação.
    # A autorização já foi resolvida para turma/componente; ownership só decide
    # quem pode alterar cada campo.
    return out


def _project_authorized_grade_for_teacher(
    grade: Mapping[str, Any],
    teacher_id: str,
) -> dict[str, Any]:
    """Projeção agregada: valores visíveis, autoria alheia somente leitura."""
    out = dict(grade)
    ownership = grade.get("grade_ownership") or {}
    owned = {
        field
        for field, snapshot in ownership.items()
        if isinstance(snapshot, Mapping)
        and str(snapshot.get("teacher_id") or "") == str(teacher_id or "")
    }
    present = _non_null_fields(grade)
    locked = present - owned
    no_snapshot = {
        field
        for field in present
        if field not in ownership
    }

    out["grade_ownership"] = {
        field: dict(snapshot)
        for field, snapshot in ownership.items()
        if field in owned and isinstance(snapshot, Mapping)
    }
    out["dvd_owned_fields"] = sorted(owned)
    out["dvd_locked_fields"] = sorted(locked)
    out["dvd_read_only_fields"] = sorted(no_snapshot)
    return out


def install_grades_dvd_institutional_visibility() -> None:
    """Instala a política sem substituir regras de escrita do DVD."""
    from routers import grades_dvd as dvd_mod
    from routers import grades_dvd_hardening as hardening_mod
    from routers import grades_dvd_parity as parity_mod
    from routers import grades_dvd_student_scope as student_scope_mod
    import routers.sync as sync_mod

    if getattr(dvd_mod, "_dvd_institutional_grade_visibility_installed", False):
        return

    # Rotas por turma/componente e respostas de create/update/batch.
    dvd_mod._mask_grade_for_assignment = _project_authorized_grade_for_assignment
    dvd_mod._mask_grade_for_teacher = _project_authorized_grade_for_teacher

    # Leituras agregadas usadas por Livro de Promoção e compatibilidade híbrida.
    hardening_mod._mask_grade_for_teacher = _project_authorized_grade_for_teacher

    # Histórico e aba Por Estudante usam a mesma política de leitura.
    parity_mod._project_grade_for_assignment = _project_authorized_grade_for_assignment
    student_scope_mod._project_grade_for_assignment = _project_authorized_grade_for_assignment

    # O hardening anterior filtrava o pull offline por teacher_id dentro de
    # grade_ownership. Isso confundia autorização de leitura com autoria. O novo
    # pull filtra primeiro pelo escopo híbrido autorizado e só depois projeta os
    # metadados de autoria.
    previous_fetch = sync_mod.fetch_collection_data_paginated

    async def institutional_fetch(
        db_arg,
        user,
        collection,
        class_id,
        academic_year,
        last_sync,
        page=1,
        page_size=100,
        request=None,
    ):
        if collection != "grades" or user.get("role") != "professor":
            return await previous_fetch(
                db_arg,
                user,
                collection,
                class_id,
                academic_year,
                last_sync,
                page,
                page_size,
                request,
            )

        year = int(academic_year or datetime.now().year)
        scopes = await list_teacher_grade_scopes(
            db_arg,
            user,
            academic_year=year,
            active_mantenedora_id=get_mantenedora_scope(user, request),
        )
        if class_id:
            scopes = [
                scope
                for scope in scopes
                if str(scope.class_id) == str(class_id)
            ]
        if not scopes:
            return [], 0

        scope_clauses: list[dict[str, Any]] = []
        seen: set[tuple[str, str | None]] = set()
        for scope in scopes:
            key = (str(scope.class_id), scope.component_id)
            if key in seen:
                continue
            seen.add(key)
            clause: dict[str, Any] = {"class_id": scope.class_id}
            if scope.component_id is not None:
                clause["course_id"] = scope.component_id
            scope_clauses.append(clause)

        query: dict[str, Any] = {
            "academic_year": {"$in": [year, str(year)]},
            "$and": [{"$or": scope_clauses}],
        }
        if last_sync:
            query["$and"].append(
                {
                    "$or": [
                        {"created_at": {"$gte": last_sync}},
                        {"updated_at": {"$gte": last_sync}},
                    ]
                }
            )
        query = apply_tenant_filter(query, user, request)

        safe_page = max(1, int(page or 1))
        safe_size = max(1, min(500, int(page_size or 100)))
        skip = (safe_page - 1) * safe_size
        total = await db_arg.grades.count_documents(query)
        docs = await (
            db_arg.grades.find(query, {"_id": 0})
            .skip(skip)
            .limit(safe_size)
            .to_list(safe_size)
        )

        visible: list[dict[str, Any]] = []
        for grade in docs:
            scope = resolve_teacher_grade_scope(
                scopes,
                class_id=grade.get("class_id"),
                course_id=grade.get("course_id"),
            )
            if scope is None:
                continue
            if scope.source == "legacy":
                visible.append(grade)
            else:
                visible.append(
                    _project_authorized_grade_for_teacher(
                        grade,
                        str(user.get("id") or ""),
                    )
                )
        return visible, total

    sync_mod.fetch_collection_data_paginated = institutional_fetch
    dvd_mod._dvd_institutional_grade_visibility_installed = True
