"""Filtros semânticos da listagem de Estudantes (#350.1).

Esta camada é deliberadamente read-only e instalada sobre ``GET /students``.
Sem nenhum dos filtros novos, delega integralmente ao endpoint existente. Com
filtros novos, usa o resultado já autorizado/tenant-scoped da rota canônica
como universo candidato e aplica somente a semântica adicional.

Invariantes:
- nenhuma escrita ou migração;
- RBAC/escola/tenant continuam pertencendo ao endpoint canônico;
- Nível de Ensino prioriza a série da matrícula ativa/estudante, necessária em
  turmas multisseriadas, e usa turma apenas como fallback;
- AEE usa a Fonte Efetiva V2 existente e jamais a mera existência de
  ``planos_aee``; rascunho/encerrado/cancelado não classificam AEE vigente;
- equivalências de Condição Especial só são aplicadas quando inequívocas;
  categorias históricas ambíguas nunca são reinterpretadas silenciosamente;
- combinações com o ``$or`` legado de turma especial permanecem corretas porque
  a nova seleção é aplicada depois do universo candidato já autorizado.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Optional

from fastapi import HTTPException, Request, status as http_status

from aee_v2.plan_list_effective import resolve_plan_list_effective_batch
from auth_middleware import AuthMiddleware
from tenant_scope import apply_tenant_filter
from utils.serie_canonical import UNRECOGNIZED_KEY, canonicalize_serie


logger = logging.getLogger(__name__)

ROUTE_PATH = "/students"
MAX_FILTER_CANDIDATES = 20_000

_SPECIAL_PROGRAMS = frozenset({"aee", "recomposicao_aprendizagem", "reforco_escolar"})
_AEE_CURRENT_EFFECTIVE_STATUSES = frozenset({"active", "review"})

_CURRENT_TDAH = "Transtorno do Déficit de Atenção e Hiperatividade (TDAH)"
_LEGACY_TDAH = "Transtorno de Déficit de Atenção e Hiperatividade (TDAH)"
_CONDITION_EQUIVALENTS = {
    _CURRENT_TDAH: frozenset({_CURRENT_TDAH, _LEGACY_TDAH}),
    _LEGACY_TDAH: frozenset({_CURRENT_TDAH, _LEGACY_TDAH}),
}


def _db_for_user(db, sandbox_db, current_user: dict):
    if current_user.get("is_sandbox"):
        return sandbox_db if sandbox_db is not None else db
    return db


def _remove_route(base_router: Any, path: str, method: str):
    for route in list(base_router.routes):
        if (
            getattr(route, "path", None) == path
            and method.upper() in (getattr(route, "methods", set()) or set())
        ):
            endpoint = route.endpoint
            base_router.routes.remove(route)
            return endpoint
    return None


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _condition_query_values(value: str) -> frozenset[str]:
    """Expande apenas equivalências históricas inequívocas.

    ``Deficiência Visual`` e ``Deficiência Múltipla`` continuam sendo categorias
    legadas explícitas: não são convertidas para categorias atuais porque a
    conversão não é semanticamente 1:1.
    """
    return _CONDITION_EQUIVALENTS.get(value, frozenset({value}))


def _education_level_from_series(raw: Any) -> Optional[str]:
    canon = canonicalize_serie(raw)
    if not canon:
        return None
    if canon in {"BERÇÁRIO I", "BERÇÁRIO II", "MATERNAL I", "MATERNAL II", "PRÉ I", "PRÉ II"}:
        return "educacao_infantil"
    if canon in {f"{n}º ANO" for n in range(1, 6)}:
        return "fundamental_anos_iniciais"
    if canon in {f"{n}º ANO" for n in range(6, 10)}:
        return "fundamental_anos_finais"
    if canon in {"1ª ETAPA", "2ª ETAPA"}:
        return "eja"
    if canon in {"3ª ETAPA", "4ª ETAPA"}:
        return "eja_final"
    return None


def _class_program(class_doc: Optional[dict]) -> str:
    return _norm((class_doc or {}).get("atendimento_programa"))


def _select_main_enrollment(student: dict, enrollments: list[dict], classes: dict[str, dict]):
    """Resolve a matrícula regular principal sem escolher silenciosamente entre ambíguas."""
    projected_class_id = str(student.get("class_id") or "").strip()
    exact = [e for e in enrollments if str(e.get("class_id") or "").strip() == projected_class_id]
    if len(exact) == 1:
        return exact[0], False
    if len(exact) > 1:
        return None, True

    regular = [
        e for e in enrollments
        if _class_program(classes.get(str(e.get("class_id") or ""))) not in _SPECIAL_PROGRAMS
    ]
    if len(regular) == 1:
        return regular[0], False
    if len(regular) > 1:
        return None, True
    return None, False


def _effective_student_context(
    student: dict,
    enrollments: list[dict],
    classes: dict[str, dict],
) -> dict[str, Any]:
    main_enrollment, ambiguous = _select_main_enrollment(student, enrollments, classes)
    class_id = (
        str((main_enrollment or {}).get("class_id") or "").strip()
        or str(student.get("class_id") or "").strip()
    )
    class_doc = classes.get(class_id) if class_id else None

    effective_series = (
        (main_enrollment or {}).get("student_series")
        or student.get("student_series")
        or (class_doc or {}).get("grade_level")
    )
    series_level = _education_level_from_series(effective_series)
    class_level = str((class_doc or {}).get("education_level") or "").strip() or None
    education_level = series_level or class_level

    main_program = _class_program(class_doc)
    program_type = _norm(student.get("atendimento_programa_tipo"))
    program_class_id = str(student.get("atendimento_programa_class_id") or "").strip()
    program_class = classes.get(program_class_id) if program_class_id else None
    program_class_type = _class_program(program_class)

    return {
        "ambiguous_main_enrollment": ambiguous,
        "main_class_id": class_id or None,
        "main_program": main_program,
        "effective_series": effective_series,
        "education_level": education_level,
        "is_regular": not main_program,
        "is_integral": main_program == "atendimento_integral",
        "is_recomposicao": (
            main_program == "recomposicao_aprendizagem"
            or program_type == "recomposicao_aprendizagem"
            or program_class_type == "recomposicao_aprendizagem"
        ),
    }


async def _effective_aee_student_ids(
    current_db,
    *,
    candidate_ids: set[str],
    current_user: dict,
    request: Request,
) -> set[str]:
    """Retorna estudantes com Plano AEE efetivamente vigente/em revisão.

    A identidade dos candidatos vem da listagem de Estudantes já tenant-scoped.
    O school_id do Plano também precisa pertencer ao tenant ativo. Qualquer erro
    estrutural da Fonte Efetiva bloqueia o filtro, em vez de cair no legado cru.
    """
    if not candidate_ids:
        return set()

    school_scope = apply_tenant_filter({}, current_user, request)
    allowed_schools = await current_db.schools.find(
        school_scope, {"_id": 0, "id": 1}
    ).to_list(None)
    allowed_school_ids = {str(s.get("id")) for s in allowed_schools if s.get("id")}
    if not allowed_school_ids:
        return set()

    plans = await current_db.planos_aee.find(
        {
            "student_id": {"$in": list(candidate_ids)},
            "school_id": {"$in": list(allowed_school_ids)},
        },
        {
            "_id": 0,
            "id": 1,
            "student_id": 1,
            "school_id": 1,
            "academic_year": 1,
            "status": 1,
            "dias_atendimento": 1,
        },
    ).to_list(None)
    if not plans:
        return set()

    try:
        resolved = await resolve_plan_list_effective_batch(current_db, plans)
    except Exception as exc:
        logger.exception("[students-filter] falha ao resolver Fonte Efetiva AEE")
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="AEE_EFFECTIVE_FILTER_INTEGRITY_BLOCKED",
        ) from exc

    plan_student = {
        str(plan.get("id")): str(plan.get("student_id"))
        for plan in plans
        if plan.get("id") and plan.get("student_id")
    }
    active: set[str] = set()
    blocked: set[str] = set()
    for summary in resolved.get("items") or []:
        plan_id = str(summary.get("legacy_plano_id") or "")
        student_id = plan_student.get(plan_id)
        if not student_id:
            continue
        if summary.get("integrity_error") or summary.get("effective_source") is None:
            blocked.add(student_id)
            continue
        if summary.get("effective_lifecycle_status") in _AEE_CURRENT_EFFECTIVE_STATUSES:
            active.add(student_id)

    if blocked:
        logger.warning(
            "[students-filter] AEE efetivo bloqueou %s estudante(s) por integridade",
            len(blocked),
        )
    return active - blocked


def _matches_modalidade(modalidade: str, context: dict[str, Any], aee_ids: set[str], student_id: str) -> bool:
    if modalidade == "regular":
        return bool(context.get("is_regular"))
    if modalidade == "atendimento_integral":
        return bool(context.get("is_integral"))
    if modalidade == "recomposicao_aprendizagem":
        return bool(context.get("is_recomposicao"))
    if modalidade == "aee":
        return student_id in aee_ids
    return False


def _increment_series(series_counts: dict[str, int], unmapped: dict[str, int], raw: Any) -> None:
    canon = canonicalize_serie(raw)
    if canon:
        series_counts[canon] = series_counts.get(canon, 0) + 1
    else:
        series_counts[UNRECOGNIZED_KEY] = series_counts.get(UNRECOGNIZED_KEY, 0) + 1
        label = str(raw or "").strip() or "(vazio)"
        unmapped[label] = unmapped.get(label, 0) + 1


def install_student_list_filters(base_router: Any, db, sandbox_db=None):
    """Instala os cinco filtros revisados sobre GET /students."""
    if getattr(base_router, "_student_list_filters_installed", False):
        return base_router

    current_list = _remove_route(base_router, ROUTE_PATH, "GET")
    if current_list is None:
        raise RuntimeError("Student List Filters não encontrou GET /students para envolver.")

    @base_router.get("")
    async def list_students_with_filters(
        request: Request,
        school_id: Optional[str] = None,
        class_id: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        completeness_band: Optional[str] = None,
        color_race: Optional[str] = None,
        comunidade_tradicional: Optional[str] = None,
        education_level: Optional[str] = None,
        modalidade: Optional[str] = None,
        disability: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
        skip: int = 0,
        limit: int = 5000,
    ):
        semantic_filters_active = any(
            [color_race, comunidade_tradicional, education_level, modalidade, disability]
        )
        if not semantic_filters_active:
            return await current_list(
                request=request,
                school_id=school_id,
                class_id=class_id,
                status=status,
                search=search,
                completeness_band=completeness_band,
                page=page,
                page_size=page_size,
                skip=skip,
                limit=limit,
            )

        # O endpoint canônico continua responsável por RBAC, escola, tenant,
        # busca, status, turma especial e completude. Para os filtros semânticos
        # precisamos do universo completo antes de paginar.
        base_result = await current_list(
            request=request,
            school_id=school_id,
            class_id=class_id,
            status=status,
            search=search,
            completeness_band=completeness_band,
            page=1,
            page_size=MAX_FILTER_CANDIDATES,
            skip=0,
            limit=MAX_FILTER_CANDIDATES,
        )
        base_total = int(base_result.get("total") or 0)
        if base_total > MAX_FILTER_CANDIDATES:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Filtro avançado excede o limite seguro de candidatos. "
                    "Restrinja por escola, turma ou busca antes de aplicar o filtro."
                ),
            )

        candidate_items = list(base_result.get("items") or [])
        candidate_ids = {str(item.get("id")) for item in candidate_items if item.get("id")}
        if not candidate_ids:
            return {
                **base_result,
                "items": [],
                "total": 0,
                "active_count": 0,
                "race_counts": {},
                "traditional_community_counts": {},
                "series_counts": {},
                "unmapped_series": {},
                "modalidade_counts": {
                    "regular": 0,
                    "atendimento_integral": 0,
                    "aee": 0,
                    "recomposicao_aprendizagem": 0,
                },
                "completeness_counts": {"green": 0, "yellow": 0, "red": 0},
                "page": page,
                "page_size": page_size,
                "total_pages": 0,
            }

        current_user = await AuthMiddleware.get_current_user(request)
        current_db = _db_for_user(db, sandbox_db, current_user)

        detail_filter = apply_tenant_filter(
            {"id": {"$in": list(candidate_ids)}}, current_user, request
        )
        raw_students = await current_db.students.find(
            detail_filter,
            {
                "_id": 0,
                "id": 1,
                "class_id": 1,
                "school_id": 1,
                "status": 1,
                "student_series": 1,
                "color_race": 1,
                "comunidade_tradicional": 1,
                "disabilities": 1,
                "atendimento_programa_tipo": 1,
                "atendimento_programa_class_id": 1,
            },
        ).to_list(None)
        student_map = {str(s.get("id")): s for s in raw_students if s.get("id")}

        enrollments = await current_db.enrollments.find(
            {"student_id": {"$in": list(candidate_ids)}, "status": "active"},
            {"_id": 0, "student_id": 1, "class_id": 1, "student_series": 1},
        ).to_list(None)
        enrollments_by_student: dict[str, list[dict]] = defaultdict(list)
        for enrollment in enrollments:
            sid = str(enrollment.get("student_id") or "")
            if sid in candidate_ids:
                enrollments_by_student[sid].append(enrollment)

        class_ids: set[str] = set()
        for student in raw_students:
            if student.get("class_id"):
                class_ids.add(str(student["class_id"]))
            if student.get("atendimento_programa_class_id"):
                class_ids.add(str(student["atendimento_programa_class_id"]))
        for enrollment in enrollments:
            if enrollment.get("class_id"):
                class_ids.add(str(enrollment["class_id"]))

        classes: dict[str, dict] = {}
        if class_ids:
            class_filter = apply_tenant_filter(
                {"id": {"$in": list(class_ids)}}, current_user, request
            )
            class_docs = await current_db.classes.find(
                class_filter,
                {
                    "_id": 0,
                    "id": 1,
                    "grade_level": 1,
                    "education_level": 1,
                    "atendimento_programa": 1,
                },
            ).to_list(None)
            classes = {str(c.get("id")): c for c in class_docs if c.get("id")}

        contexts = {
            sid: _effective_student_context(
                student_map.get(sid, {}), enrollments_by_student.get(sid, []), classes
            )
            for sid in candidate_ids
        }

        # O indicador AEE e o filtro AEE compartilham a mesma Fonte Efetiva.
        aee_ids = await _effective_aee_student_ids(
            current_db,
            candidate_ids=candidate_ids,
            current_user=current_user,
            request=request,
        )

        disability_values = _condition_query_values(disability) if disability else frozenset()
        filtered_items: list[dict] = []
        filtered_ids: set[str] = set()
        ambiguous_semantic_ids: set[str] = set()

        for item in candidate_items:
            sid = str(item.get("id") or "")
            student = student_map.get(sid)
            if not student:
                continue
            context = contexts.get(sid, {})

            if color_race and student.get("color_race") != color_race:
                continue
            if comunidade_tradicional and student.get("comunidade_tradicional") != comunidade_tradicional:
                continue
            if disability:
                values = set(student.get("disabilities") or [])
                if not values.intersection(disability_values):
                    continue

            if education_level:
                if context.get("ambiguous_main_enrollment"):
                    ambiguous_semantic_ids.add(sid)
                    continue
                if context.get("education_level") != education_level:
                    continue

            if modalidade:
                if modalidade != "aee" and context.get("ambiguous_main_enrollment"):
                    ambiguous_semantic_ids.add(sid)
                    continue
                if not _matches_modalidade(modalidade, context, aee_ids, sid):
                    continue

            filtered_items.append(item)
            filtered_ids.add(sid)

        if ambiguous_semantic_ids:
            logger.warning(
                "[students-filter] %s estudante(s) excluídos fail-closed por múltiplas matrículas principais ativas",
                len(ambiguous_semantic_ids),
            )

        # Indicadores passam a refletir exatamente o universo filtrado, mantendo
        # a regra histórica de calculá-los sobre estudantes ATIVOS.
        active_ids = {
            sid for sid in filtered_ids
            if _norm(student_map.get(sid, {}).get("status")) in {"active", "ativo"}
        }
        race_counts: dict[str, int] = {}
        traditional_counts: dict[str, int] = {}
        series_counts: dict[str, int] = {}
        unmapped_series: dict[str, int] = {}
        modalidade_counts = {
            "regular": 0,
            "atendimento_integral": 0,
            "aee": 0,
            "recomposicao_aprendizagem": 0,
        }
        completeness_counts = {"green": 0, "yellow": 0, "red": 0}
        item_by_id = {str(i.get("id")): i for i in filtered_items if i.get("id")}

        for sid in active_ids:
            student = student_map.get(sid, {})
            race_key = student.get("color_race") or "nao_informada"
            community_key = student.get("comunidade_tradicional") or "nao_informada"
            race_counts[race_key] = race_counts.get(race_key, 0) + 1
            traditional_counts[community_key] = traditional_counts.get(community_key, 0) + 1

            context = contexts.get(sid, {})
            _increment_series(series_counts, unmapped_series, context.get("effective_series"))
            if context.get("is_regular"):
                modalidade_counts["regular"] += 1
            if context.get("is_integral"):
                modalidade_counts["atendimento_integral"] += 1
            if context.get("is_recomposicao"):
                modalidade_counts["recomposicao_aprendizagem"] += 1
            if sid in aee_ids:
                modalidade_counts["aee"] += 1

            pct = int(item_by_id.get(sid, {}).get("completeness") or 0)
            if pct >= 80:
                completeness_counts["green"] += 1
            elif pct >= 50:
                completeness_counts["yellow"] += 1
            else:
                completeness_counts["red"] += 1

        total = len(filtered_items)
        if page > 0:
            effective_skip = (page - 1) * page_size
            effective_limit = page_size
        else:
            effective_skip = skip
            effective_limit = limit
        paged_items = filtered_items[effective_skip: effective_skip + effective_limit]
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0

        return {
            "items": paged_items,
            "total": total,
            "active_count": len(active_ids),
            "race_counts": race_counts,
            "traditional_community_counts": traditional_counts,
            "series_counts": series_counts,
            "unmapped_series": unmapped_series,
            "modalidade_counts": modalidade_counts,
            "completeness_counts": completeness_counts,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    setattr(base_router, "_student_list_filters_installed", True)
    return base_router
