"""P0-E4 — contenção de referências históricas a courses.id ausentes.

Este módulo atua exclusivamente na camada de resposta. Ele nunca remapeia o
``course_id`` persistido, não cria componentes e não executa mutações MongoDB.

A regra é genérica: qualquer registro histórico que referencie um ``course_id``
que não exista mais em ``courses`` recebe um estado explícito e um rótulo seguro
para exibição. O UUID concreto encontrado na investigação P0-E não é codificado
na aplicação.
"""
from __future__ import annotations

from functools import wraps
from typing import Any, Iterable, Mapping


HISTORICAL_COURSE_MISSING_STATE = "HISTORICAL_COURSE_MISSING"
HISTORICAL_COURSE_UNAVAILABLE_LABEL = "Componente histórico indisponível"

_TARGETS = {
    "learning_objects": {
        ("/learning-objects", "GET"),
        ("/learning-objects/{object_id}", "GET"),
    },
    "assignments": {
        ("/teacher-assignments", "GET"),
    },
}


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _iter_records(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, dict):
        yield payload
        return
    if isinstance(payload, list):
        for row in payload:
            if isinstance(row, dict):
                yield row


async def enrich_course_reference_response(db: Any, payload: Any) -> Any:
    """Enriquece somente a resposta em memória; nunca persiste alterações.

    - preserva o ``course_id`` original;
    - se o componente existir, completa ``course_name`` quando necessário;
    - se estiver ausente, usa rótulo explícito e metadados de integridade;
    - nunca escolhe um ``course_id`` substituto.
    """
    rows = list(_iter_records(payload))
    course_ids = sorted({_norm(row.get("course_id")) for row in rows if _norm(row.get("course_id"))})
    if not course_ids:
        return payload

    courses = await db.courses.find(
        {"id": {"$in": course_ids}},
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(len(course_ids))
    course_by_id = {_norm(row.get("id")): row for row in courses if _norm(row.get("id"))}

    for row in rows:
        course_id = _norm(row.get("course_id"))
        if not course_id:
            continue

        course = course_by_id.get(course_id)
        if course:
            if not _norm(row.get("course_name")):
                row["course_name"] = course.get("name") or ""
            continue

        row["course_name"] = HISTORICAL_COURSE_UNAVAILABLE_LABEL
        row["course_reference_state"] = HISTORICAL_COURSE_MISSING_STATE
        row["course_reference_integrity"] = {
            "state": HISTORICAL_COURSE_MISSING_STATE,
            "course_id": course_id,
            "remap_applied": False,
            "automatic_course_creation": False,
            "source_preserved": True,
        }

    return payload


def _route_key(route: Any) -> set[tuple[str, str]]:
    path = getattr(route, "path", None)
    methods = getattr(route, "methods", None) or set()
    if not path:
        return set()
    return {(path, str(method).upper()) for method in methods}


def _wrap_router_read_responses(router: Any, db: Any, targets: set[tuple[str, str]]) -> Any:
    for route in getattr(router, "routes", []):
        if not (_route_key(route) & targets):
            continue

        dependant = getattr(route, "dependant", None)
        original = getattr(dependant, "call", None)
        if original is None or getattr(original, "_p0e4_course_missing_containment", False):
            continue

        @wraps(original)
        async def contained(*args: Any, __original=original, **kwargs: Any) -> Any:
            result = await __original(*args, **kwargs)
            return await enrich_course_reference_response(db, result)

        contained._p0e4_course_missing_containment = True  # type: ignore[attr-defined]
        route.endpoint = contained
        dependant.call = contained

    return router


def _install_module_setup(module: Any, *, module_key: str) -> None:
    marker = f"_p0e4_{module_key}_installed"
    if getattr(module, marker, False):
        return

    original_setup = module.setup_router
    targets = _TARGETS[module_key]

    @wraps(original_setup)
    def setup_with_containment(db: Any, *args: Any, **kwargs: Any) -> Any:
        router = original_setup(db, *args, **kwargs)
        return _wrap_router_read_responses(router, db, targets)

    module.setup_router = setup_with_containment
    setattr(module, marker, True)


def install_course_missing_containment_setup(learning_objects_module: Any, assignments_module: Any) -> None:
    """Instala contenção aditiva nos readers legados afetados pelo P0-E.

    A instalação envolve somente os ``setup_router`` dos módulos. Nenhum writer é
    alterado e nenhuma regra de criação/edição/exclusão é relaxada.
    """
    _install_module_setup(learning_objects_module, module_key="learning_objects")
    _install_module_setup(assignments_module, module_key="assignments")
