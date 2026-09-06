#!/usr/bin/env python3
"""ANA-LUCIA-F2.6 — remapeamento cirúrgico autorizado de course_id.

Escopo estrito: 8 pares de Língua Inglesa dos 6º/9º anos de 2026 atribuíveis
à professora Ana Lucia Faria Pinto. O executor altera SOMENTE ``course_id``
do identificador legado EJA Final para o identificador canônico de Anos Finais.

Proteções:
- resolução dinâmica da professora, turma, escola, tenant e duas identidades;
- baseline F2.4/F2.5B exato antes de qualquer escrita;
- colisões por chave natural zeradas;
- 74 tenants ausentes apenas adjudicados, nunca preenchidos;
- 4 frequências agregadas sem aula_numero preservadas sem inferência;
- copied_from_id preservado; 1 pai ausente é quebra preexistente;
- update_one CAS por documento;
- rollback compensatório em ordem reversa se qualquer etapa falhar;
- pós-condições revalidadas antes de declarar sucesso.

Nenhum estudante, attendance.records, nota ou texto pedagógico é lido.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
import re
import sys
import unicodedata
from typing import Any, Iterable, Mapping

from pymongo import MongoClient

ACADEMIC_YEAR = 2026
TEACHER_NAME = "Ana Lucia Faria Pinto"
COMPONENT_NAME = "Língua Inglesa"
CURRENT_LEVEL = "fundamental_anos_finais"
LEGACY_LEVEL = "eja_final"
ACTIVE_STATUSES = ("ativo", "active")
TARGET_CLASSES: tuple[str, ...] = (
    "6º ANO A", "6º ANO B", "6º ANO C", "6º ANO D",
    "9º ANO A", "9º ANO B", "9º ANO C", "9º ANO D",
)

BASELINE = {
    "learning_candidates": 198,
    "attendance_candidates": 392,
    "learning_target_existing": 8,
    "attendance_target_existing": 17,
    "attendance_raw_legacy": 399,
    "attendance_excluded_not_teacher": 7,
    "attendance_tenant_missing": 74,
    "attendance_incomplete_key": 4,
    "copied_candidates": 74,
    "parent_in_candidate_set": 73,
    "parent_missing": 1,
}

PROJECTION = {
    "_id": 0,
    "id": 1,
    "class_id": 1,
    "school_id": 1,
    "course_id": 1,
    "academic_year": 1,
    "date": 1,
    "period": 1,
    "aula_numero": 1,
    "number_of_classes": 1,
    "assignment_id": 1,
    "teacher_id": 1,
    "staff_id": 1,
    "recorded_by": 1,
    "created_by": 1,
    "updated_by": 1,
    "mantenedora_id": 1,
    "status": 1,
    "deleted": 1,
    "copied_from_id": 1,
    "version": 1,
}


def _sid(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _norm(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", _sid(value))
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = raw.casefold().replace("º", "o").replace("ª", "a")
    return re.sub(r"\s+", " ", raw).strip()


def _day(value: Any) -> str:
    return _sid(value)[:10]


def _fp(value: Any, size: int = 12) -> str | None:
    raw = _sid(value)
    if not raw:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:size]


def _error_fp(exc: BaseException) -> str:
    return hashlib.sha256(str(exc).encode("utf-8")).hexdigest()[:16]


def _year_scope() -> dict[str, Any]:
    return {
        "$or": [
            {"academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}},
            {"date": {"$gte": f"{ACADEMIC_YEAR}-01-01", "$lte": f"{ACADEMIC_YEAR}-12-31"}},
        ]
    }


def _active_like(row: Mapping[str, Any]) -> bool:
    if row.get("deleted") is True:
        return False
    return _norm(row.get("status")) not in {
        "inativo", "inactive", "excluido", "excluida", "deleted",
        "cancelado", "cancelada",
    }


def _teacher_actor(row: Mapping[str, Any], actor_ids: set[str]) -> bool:
    return any(
        _sid(row.get(field)) in actor_ids
        for field in ("staff_id", "teacher_id", "recorded_by", "created_by", "updated_by")
        if _sid(row.get(field))
    )


def _teacher_attributed(
    row: Mapping[str, Any],
    *,
    actor_ids: set[str],
    teacher_assignment_ids: set[str],
    assignment_owner: Mapping[str, str],
    teacher_user_id: str,
) -> bool:
    if _teacher_actor(row, actor_ids):
        return True
    assignment_id = _sid(row.get("assignment_id"))
    return bool(
        assignment_id
        and (
            assignment_id in teacher_assignment_ids
            or assignment_owner.get(assignment_id) == teacher_user_id
        )
    )


def _learning_key(row: Mapping[str, Any]) -> tuple[str, str] | None:
    class_id = _sid(row.get("class_id"))
    date = _day(row.get("date"))
    if not class_id or not date:
        return None
    return class_id, date


def _attendance_key(row: Mapping[str, Any]) -> tuple[str, str, str, str] | None:
    class_id = _sid(row.get("class_id"))
    date = _day(row.get("date"))
    aula = _sid(row.get("aula_numero"))
    if not class_id or not date or not aula:
        return None
    return class_id, date, _sid(row.get("period")) or "regular", aula


def _aggregate_key(row: Mapping[str, Any]) -> tuple[str, str, str] | None:
    class_id = _sid(row.get("class_id"))
    date = _day(row.get("date"))
    if not class_id or not date:
        return None
    return class_id, date, _sid(row.get("period")) or "regular"


def _group(rows: Iterable[Mapping[str, Any]], key_fn) -> tuple[dict[Any, list[Mapping[str, Any]]], int]:
    groups: dict[Any, list[Mapping[str, Any]]] = defaultdict(list)
    missing = 0
    for row in rows:
        key = key_fn(row)
        if key is None:
            missing += 1
        else:
            groups[key].append(row)
    return groups, missing


def _unique_teacher_identity(db) -> tuple[dict[str, Any], dict[str, Any]]:
    users = list(db.users.find(
        {"$or": [{"full_name": TEACHER_NAME}, {"name": TEACHER_NAME}]},
        {"_id": 0, "id": 1, "email": 1, "full_name": 1, "name": 1, "role": 1, "mantenedora_id": 1},
    ).limit(5))
    users = [row for row in users if _norm(row.get("full_name") or row.get("name")) == _norm(TEACHER_NAME)]
    if len(users) != 1 or users[0].get("role") != "professor":
        raise RuntimeError(f"ANA_LUCIA_F2_6_TEACHER_IDENTITY_INVALID:{len(users)}")
    user = users[0]

    clauses = [{"user_id": user["id"]}]
    if user.get("email"):
        clauses.append({"email": user["email"]})
    rows = list(db.staff.find(
        {"$or": clauses},
        {"_id": 0, "id": 1, "user_id": 1, "email": 1, "mantenedora_id": 1},
    ).limit(5))
    dedup = {_sid(row.get("id")): row for row in rows if _sid(row.get("id"))}
    if len(dedup) != 1:
        raise RuntimeError(f"ANA_LUCIA_F2_6_STAFF_IDENTITY_INVALID:{len(dedup)}")
    return user, next(iter(dedup.values()))


def _assignment_owners(db, teacher_user_id: str) -> tuple[set[str], dict[str, str]]:
    rows = list(db.teacher_class_assignments.find(
        {}, {"_id": 0, "id": 1, "teacher_id": 1, "deleted": 1}
    ))
    owner = {
        _sid(row.get("id")): _sid(row.get("teacher_id"))
        for row in rows if _sid(row.get("id"))
    }
    teacher_ids = {
        _sid(row.get("id"))
        for row in rows
        if _sid(row.get("id"))
        and _sid(row.get("teacher_id")) == teacher_user_id
        and row.get("deleted") is not True
    }
    return teacher_ids, owner


def _resolve_context(db, user: Mapping[str, Any], staff: Mapping[str, Any]) -> dict[str, Any]:
    assignments = list(db.teacher_assignments.find(
        {
            "staff_id": staff["id"],
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
            "status": {"$in": list(ACTIVE_STATUSES)},
        },
        {"_id": 0, "id": 1, "class_id": 1, "course_id": 1, "school_id": 1, "mantenedora_id": 1},
    ))
    class_ids = sorted({_sid(row.get("class_id")) for row in assignments if _sid(row.get("class_id"))})
    classes = list(db.classes.find(
        {"id": {"$in": class_ids}},
        {"_id": 0, "id": 1, "name": 1, "school_id": 1, "mantenedora_id": 1, "academic_year": 1},
    ))
    class_by_id = {_sid(row.get("id")): row for row in classes if _sid(row.get("id"))}
    school_ids = sorted({_sid(row.get("school_id")) for row in classes if _sid(row.get("school_id"))})
    schools = list(db.schools.find(
        {"id": {"$in": school_ids}},
        {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1},
    ))
    school_by_id = {_sid(row.get("id")): row for row in schools if _sid(row.get("id"))}
    course_ids = sorted({_sid(row.get("course_id")) for row in assignments if _sid(row.get("course_id"))})
    courses = list(db.courses.find(
        {"id": {"$in": course_ids}},
        {"_id": 0, "id": 1, "name": 1, "nivel_ensino": 1, "mantenedora_id": 1},
    ))
    course_by_id = {_sid(row.get("id")): row for row in courses if _sid(row.get("id"))}

    targets: list[dict[str, Any]] = []
    current_ids: set[str] = set()
    tenants: set[str] = set()
    for class_name in TARGET_CLASSES:
        matches = []
        for assignment in assignments:
            klass = class_by_id.get(_sid(assignment.get("class_id"))) or {}
            course = course_by_id.get(_sid(assignment.get("course_id"))) or {}
            if _norm(klass.get("name")) == _norm(class_name) and _norm(course.get("name")) == _norm(COMPONENT_NAME):
                matches.append(assignment)
        if len(matches) != 1:
            raise RuntimeError(f"ANA_LUCIA_F2_6_TARGET_NOT_EXACT:{class_name}:{len(matches)}")
        assignment = matches[0]
        klass = class_by_id[_sid(assignment.get("class_id"))]
        school = school_by_id.get(_sid(klass.get("school_id"))) or {}
        anchors = {
            _sid(assignment.get("mantenedora_id")),
            _sid(klass.get("mantenedora_id")),
            _sid(school.get("mantenedora_id")),
            _sid(user.get("mantenedora_id")),
            _sid(staff.get("mantenedora_id")),
        } - {""}
        if len(anchors) != 1:
            raise RuntimeError(f"ANA_LUCIA_F2_6_TENANT_ANCHORS_INVALID:{class_name}:{len(anchors)}")
        tenant_id = next(iter(anchors))
        current_id = _sid(assignment.get("course_id"))
        if not current_id:
            raise RuntimeError(f"ANA_LUCIA_F2_6_CURRENT_COURSE_MISSING:{class_name}")
        current_ids.add(current_id)
        tenants.add(tenant_id)
        targets.append({
            "class": class_name,
            "class_id": _sid(klass.get("id")),
            "school_id": _sid(klass.get("school_id")),
            "tenant_id": tenant_id,
        })

    if len(current_ids) != 1 or len(tenants) != 1:
        raise RuntimeError("ANA_LUCIA_F2_6_CONTEXT_NOT_UNIQUE")
    current_id = next(iter(current_ids))
    tenant_id = next(iter(tenants))

    same_name = list(db.courses.find(
        {
            "name": {"$exists": True},
            "$or": [
                {"mantenedora_id": tenant_id},
                {"mantenedora_id": {"$exists": False}},
                {"mantenedora_id": None},
                {"mantenedora_id": ""},
            ],
        },
        {"_id": 0, "id": 1, "name": 1, "nivel_ensino": 1, "mantenedora_id": 1},
    ))
    same_name = [row for row in same_name if _norm(row.get("name")) == _norm(COMPONENT_NAME)]
    current_matches = [
        row for row in same_name
        if _sid(row.get("id")) == current_id
        and _norm(row.get("nivel_ensino")) == _norm(CURRENT_LEVEL)
    ]
    legacy_matches = [row for row in same_name if _norm(row.get("nivel_ensino")) == _norm(LEGACY_LEVEL)]
    if len(current_matches) != 1 or len(legacy_matches) != 1:
        raise RuntimeError(
            f"ANA_LUCIA_F2_6_COURSE_IDENTITIES_INVALID:{len(current_matches)}:{len(legacy_matches)}"
        )
    legacy_id = _sid(legacy_matches[0].get("id"))
    if legacy_id == current_id:
        raise RuntimeError("ANA_LUCIA_F2_6_IDENTITIES_ALREADY_COLLAPSED")

    return {
        "targets": targets,
        "class_by_id": {row["class_id"]: row for row in targets},
        "tenant_id": tenant_id,
        "current_id": current_id,
        "legacy_id": legacy_id,
    }


def _load_rows(db, collection: str, *, class_ids: set[str], course_id: str) -> list[dict[str, Any]]:
    return list(db[collection].find(
        {
            "$and": [
                {"class_id": {"$in": sorted(class_ids)}},
                {"course_id": course_id},
                _year_scope(),
            ]
        },
        PROJECTION,
    ))


def _partition(
    rows: Iterable[Mapping[str, Any]],
    *,
    actor_ids: set[str],
    teacher_assignment_ids: set[str],
    assignment_owner: Mapping[str, str],
    teacher_user_id: str,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    candidates: list[dict[str, Any]] = []
    excluded: Counter[str] = Counter()
    for raw in rows:
        row = dict(raw)
        if not _active_like(row):
            excluded["INACTIVE_OR_DELETED"] += 1
            continue
        if not _teacher_attributed(
            row,
            actor_ids=actor_ids,
            teacher_assignment_ids=teacher_assignment_ids,
            assignment_owner=assignment_owner,
            teacher_user_id=teacher_user_id,
        ):
            excluded["NOT_ATTRIBUTABLE_TO_TEACHER"] += 1
            continue
        candidates.append(row)
    return candidates, excluded


def _validate_tenant(candidates: list[Mapping[str, Any]], class_by_id: Mapping[str, Mapping[str, Any]], tenant_id: str) -> int:
    missing = 0
    for row in candidates:
        row_tenant = _sid(row.get("mantenedora_id"))
        target = class_by_id.get(_sid(row.get("class_id")))
        if not target or _sid(target.get("tenant_id")) != tenant_id:
            raise RuntimeError("ANA_LUCIA_F2_6_TENANT_CLASS_CONTEXT_INVALID")
        if row_tenant:
            if row_tenant != tenant_id:
                raise RuntimeError("ANA_LUCIA_F2_6_TENANT_MISMATCH")
        else:
            row_school = _sid(row.get("school_id"))
            target_school = _sid(target.get("school_id"))
            if row_school and row_school != target_school:
                raise RuntimeError("ANA_LUCIA_F2_6_MISSING_TENANT_SCHOOL_MISMATCH")
            missing += 1
    return missing


def _validate_learning_keys(source: list[Mapping[str, Any]], target: list[Mapping[str, Any]]) -> None:
    source_groups, source_missing = _group(source, _learning_key)
    target_groups, target_missing = _group(target, _learning_key)
    if source_missing or target_missing:
        raise RuntimeError("ANA_LUCIA_F2_6_LEARNING_KEY_MISSING")
    if any(len(rows) != 1 for rows in source_groups.values()):
        raise RuntimeError("ANA_LUCIA_F2_6_LEARNING_SOURCE_DUPLICATE")
    if any(len(rows) != 1 for rows in target_groups.values()):
        raise RuntimeError("ANA_LUCIA_F2_6_LEARNING_TARGET_DUPLICATE")
    if set(source_groups) & set(target_groups):
        raise RuntimeError("ANA_LUCIA_F2_6_LEARNING_TARGET_COLLISION")


def _validate_attendance_keys(source: list[Mapping[str, Any]], target: list[Mapping[str, Any]]) -> int:
    source_groups, source_missing = _group(source, _attendance_key)
    target_groups, _ = _group(target, _attendance_key)
    if any(len(rows) != 1 for rows in source_groups.values()):
        raise RuntimeError("ANA_LUCIA_F2_6_ATTENDANCE_SOURCE_DUPLICATE")
    if any(len(rows) != 1 for rows in target_groups.values()):
        raise RuntimeError("ANA_LUCIA_F2_6_ATTENDANCE_TARGET_DUPLICATE")
    if set(source_groups) & set(target_groups):
        raise RuntimeError("ANA_LUCIA_F2_6_ATTENDANCE_TARGET_COLLISION")

    incomplete = [row for row in source if _attendance_key(row) is None]
    if len(incomplete) != source_missing:
        raise RuntimeError("ANA_LUCIA_F2_6_ATTENDANCE_KEY_ACCOUNTING")
    for row in incomplete:
        if not _sid(row.get("class_id")) or not _day(row.get("date")) or _sid(row.get("aula_numero")):
            raise RuntimeError("ANA_LUCIA_F2_6_INCOMPLETE_KEY_NOT_LEGACY_AGGREGATE")
        agg = _aggregate_key(row)
        if agg is None:
            raise RuntimeError("ANA_LUCIA_F2_6_AGGREGATE_KEY_MISSING")
        source_same = [other for other in source if _aggregate_key(other) == agg]
        target_same = [other for other in target if _aggregate_key(other) == agg]
        source_aggregate = [other for other in source_same if not _sid(other.get("aula_numero"))]
        source_sessions = [other for other in source_same if _sid(other.get("aula_numero"))]
        target_aggregate = [other for other in target_same if not _sid(other.get("aula_numero"))]
        target_sessions = [other for other in target_same if _sid(other.get("aula_numero"))]
        if len(source_aggregate) != 1 or source_sessions or target_aggregate or target_sessions:
            raise RuntimeError("ANA_LUCIA_F2_6_AGGREGATE_NOT_PRESERVABLE")
    return len(incomplete)


def _detect_cycles(edges: Mapping[str, str]) -> int:
    cycles: set[tuple[str, ...]] = set()
    for start in edges:
        seen: set[str] = set()
        cur = start
        while cur in edges:
            if cur in seen:
                cycle = []
                marker = cur
                while True:
                    cycle.append(marker)
                    marker = edges[marker]
                    if marker == cur:
                        break
                cycles.add(tuple(sorted(cycle)))
                break
            seen.add(cur)
            cur = edges[cur]
    return len(cycles)


def _validate_lineage(db, learning_candidates: list[Mapping[str, Any]], legacy_id: str, current_id: str) -> dict[str, int]:
    candidate_ids = {_sid(row.get("id")) for row in learning_candidates if _sid(row.get("id"))}
    if len(candidate_ids) != len(learning_candidates):
        raise RuntimeError("ANA_LUCIA_F2_6_LEARNING_ID_NOT_UNIQUE")
    copied = [row for row in learning_candidates if _sid(row.get("copied_from_id"))]
    parent_ids = sorted({_sid(row.get("copied_from_id")) for row in copied})
    parents = list(db.learning_objects.find(
        {"id": {"$in": parent_ids}},
        {"_id": 0, "id": 1, "course_id": 1},
    )) if parent_ids else []
    by_id = {_sid(row.get("id")): row for row in parents if _sid(row.get("id"))}
    counts = Counter()
    edges: dict[str, str] = {}
    for child in copied:
        child_id = _sid(child.get("id"))
        parent_id = _sid(child.get("copied_from_id"))
        parent = by_id.get(parent_id)
        if not parent:
            counts["parent_missing"] += 1
        elif parent_id in candidate_ids:
            counts["parent_in_candidate_set"] += 1
            edges[child_id] = parent_id
        elif _sid(parent.get("course_id")) == legacy_id:
            counts["parent_legacy_outside_candidate"] += 1
        elif _sid(parent.get("course_id")) == current_id:
            counts["parent_current"] += 1
        else:
            counts["parent_other"] += 1
    cycles = _detect_cycles(edges)
    if counts["parent_legacy_outside_candidate"] or counts["parent_other"] or cycles:
        raise RuntimeError("ANA_LUCIA_F2_6_LINEAGE_WOULD_BREAK")
    return {
        "copied_candidates": len(copied),
        "parent_in_candidate_set": counts["parent_in_candidate_set"],
        "parent_missing": counts["parent_missing"],
        "cycles": cycles,
    }


def _candidate_ids(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    ids = [_sid(row.get("id")) for row in rows]
    if not all(ids) or len(ids) != len(set(ids)):
        raise RuntimeError("ANA_LUCIA_F2_6_CANDIDATE_IDS_INVALID")
    return ids


def _baseline_state(db, context: Mapping[str, Any], user: Mapping[str, Any], staff: Mapping[str, Any]) -> dict[str, Any]:
    class_ids = set(context["class_by_id"])
    legacy_id = context["legacy_id"]
    current_id = context["current_id"]
    teacher_user_id = _sid(user.get("id"))
    actor_ids = {teacher_user_id, _sid(staff.get("id"))} - {""}
    teacher_assignment_ids, assignment_owner = _assignment_owners(db, teacher_user_id)

    raw_learning = _load_rows(db, "learning_objects", class_ids=class_ids, course_id=legacy_id)
    raw_attendance = _load_rows(db, "attendance", class_ids=class_ids, course_id=legacy_id)
    target_learning = [row for row in _load_rows(db, "learning_objects", class_ids=class_ids, course_id=current_id) if _active_like(row)]
    target_attendance = [row for row in _load_rows(db, "attendance", class_ids=class_ids, course_id=current_id) if _active_like(row)]
    learning_candidates, learning_excluded = _partition(
        raw_learning,
        actor_ids=actor_ids,
        teacher_assignment_ids=teacher_assignment_ids,
        assignment_owner=assignment_owner,
        teacher_user_id=teacher_user_id,
    )
    attendance_candidates, attendance_excluded = _partition(
        raw_attendance,
        actor_ids=actor_ids,
        teacher_assignment_ids=teacher_assignment_ids,
        assignment_owner=assignment_owner,
        teacher_user_id=teacher_user_id,
    )

    return {
        "raw_learning": raw_learning,
        "raw_attendance": raw_attendance,
        "target_learning": target_learning,
        "target_attendance": target_attendance,
        "learning_candidates": learning_candidates,
        "attendance_candidates": attendance_candidates,
        "learning_excluded": learning_excluded,
        "attendance_excluded": attendance_excluded,
    }


def _validate_prewrite(db, state: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    learning = state["learning_candidates"]
    attendance = state["attendance_candidates"]
    target_learning = state["target_learning"]
    target_attendance = state["target_attendance"]

    if len(learning) != BASELINE["learning_candidates"]:
        raise RuntimeError(f"ANA_LUCIA_F2_6_LEARNING_BASELINE_DRIFT:{len(learning)}")
    if len(attendance) != BASELINE["attendance_candidates"]:
        raise RuntimeError(f"ANA_LUCIA_F2_6_ATTENDANCE_BASELINE_DRIFT:{len(attendance)}")
    if len(target_learning) != BASELINE["learning_target_existing"]:
        raise RuntimeError(f"ANA_LUCIA_F2_6_LEARNING_TARGET_DRIFT:{len(target_learning)}")
    if len(target_attendance) != BASELINE["attendance_target_existing"]:
        raise RuntimeError(f"ANA_LUCIA_F2_6_ATTENDANCE_TARGET_DRIFT:{len(target_attendance)}")
    if len(state["raw_attendance"]) != BASELINE["attendance_raw_legacy"]:
        raise RuntimeError(f"ANA_LUCIA_F2_6_ATTENDANCE_RAW_DRIFT:{len(state['raw_attendance'])}")
    if dict(state["learning_excluded"]):
        raise RuntimeError("ANA_LUCIA_F2_6_UNEXPECTED_LEARNING_EXCLUSIONS")
    if dict(state["attendance_excluded"]) != {"NOT_ATTRIBUTABLE_TO_TEACHER": BASELINE["attendance_excluded_not_teacher"]}:
        raise RuntimeError("ANA_LUCIA_F2_6_ATTENDANCE_EXCLUSIONS_DRIFT")
    if any(_sid(row.get("assignment_id")) for row in [*learning, *attendance]):
        raise RuntimeError("ANA_LUCIA_F2_6_ASSIGNMENT_BOUND_CANDIDATE")

    tenant_missing_learning = _validate_tenant(learning, context["class_by_id"], context["tenant_id"])
    tenant_missing_attendance = _validate_tenant(attendance, context["class_by_id"], context["tenant_id"])
    if tenant_missing_learning != 0 or tenant_missing_attendance != BASELINE["attendance_tenant_missing"]:
        raise RuntimeError("ANA_LUCIA_F2_6_TENANT_ADJUDICATION_DRIFT")

    _validate_learning_keys(learning, target_learning)
    incomplete = _validate_attendance_keys(attendance, target_attendance)
    if incomplete != BASELINE["attendance_incomplete_key"]:
        raise RuntimeError("ANA_LUCIA_F2_6_AGGREGATE_BASELINE_DRIFT")

    lineage = _validate_lineage(db, learning, context["legacy_id"], context["current_id"])
    if lineage["copied_candidates"] != BASELINE["copied_candidates"]:
        raise RuntimeError("ANA_LUCIA_F2_6_COPIED_BASELINE_DRIFT")
    if lineage["parent_in_candidate_set"] != BASELINE["parent_in_candidate_set"]:
        raise RuntimeError("ANA_LUCIA_F2_6_LINEAGE_PARENT_SET_DRIFT")
    if lineage["parent_missing"] != BASELINE["parent_missing"]:
        raise RuntimeError("ANA_LUCIA_F2_6_LINEAGE_MISSING_PARENT_DRIFT")

    return {
        "learning_ids": _candidate_ids(learning),
        "attendance_ids": _candidate_ids(attendance),
        "lineage": lineage,
        "tenant_missing_attendance": tenant_missing_attendance,
        "legacy_aggregate_attendance": incomplete,
    }


def _already_applied(state: Mapping[str, Any]) -> bool:
    return (
        len(state["learning_candidates"]) == 0
        and len(state["attendance_candidates"]) == 0
        and len(state["raw_learning"]) == 0
        and len(state["raw_attendance"]) == BASELINE["attendance_excluded_not_teacher"]
        and len(state["target_learning"]) == BASELINE["learning_target_existing"] + BASELINE["learning_candidates"]
        and len(state["target_attendance"]) == BASELINE["attendance_target_existing"] + BASELINE["attendance_candidates"]
    )


def _apply_one(db, collection: str, row: Mapping[str, Any], legacy_id: str, current_id: str) -> None:
    result = db[collection].update_one(
        {"id": _sid(row.get("id")), "class_id": _sid(row.get("class_id")), "course_id": legacy_id},
        {"$set": {"course_id": current_id}},
    )
    if result.matched_count != 1 or result.modified_count != 1:
        raise RuntimeError(f"ANA_LUCIA_F2_6_CAS_UPDATE_FAILED:{collection}")


def _rollback(db, applied: list[tuple[str, str, str]], legacy_id: str, current_id: str) -> bool:
    ok = True
    for collection, row_id, class_id in reversed(applied):
        result = db[collection].update_one(
            {"id": row_id, "class_id": class_id, "course_id": current_id},
            {"$set": {"course_id": legacy_id}},
        )
        if result.matched_count != 1 or result.modified_count != 1:
            ok = False
    return ok


def _verify_candidate_course(db, collection: str, ids: list[str], current_id: str, legacy_id: str) -> None:
    if db[collection].count_documents({"id": {"$in": ids}, "course_id": current_id}) != len(ids):
        raise RuntimeError(f"ANA_LUCIA_F2_6_POST_CURRENT_COUNT_FAILED:{collection}")
    if db[collection].count_documents({"id": {"$in": ids}, "course_id": legacy_id}) != 0:
        raise RuntimeError(f"ANA_LUCIA_F2_6_POST_LEGACY_COUNT_FAILED:{collection}")


def _verify_lineage_unchanged(db, before: Mapping[str, str], ids: list[str]) -> None:
    rows = list(db.learning_objects.find(
        {"id": {"$in": ids}}, {"_id": 0, "id": 1, "copied_from_id": 1}
    ))
    after = {_sid(row.get("id")): _sid(row.get("copied_from_id")) for row in rows}
    if after != dict(before):
        raise RuntimeError("ANA_LUCIA_F2_6_COPIED_FROM_CHANGED")


def _postverify(db, context: Mapping[str, Any], learning_ids: list[str], attendance_ids: list[str], lineage_before: Mapping[str, str]) -> dict[str, Any]:
    _verify_candidate_course(db, "learning_objects", learning_ids, context["current_id"], context["legacy_id"])
    _verify_candidate_course(db, "attendance", attendance_ids, context["current_id"], context["legacy_id"])
    _verify_lineage_unchanged(db, lineage_before, learning_ids)

    class_ids = set(context["class_by_id"])
    current_learning = [row for row in _load_rows(db, "learning_objects", class_ids=class_ids, course_id=context["current_id"]) if _active_like(row)]
    current_attendance = [row for row in _load_rows(db, "attendance", class_ids=class_ids, course_id=context["current_id"]) if _active_like(row)]
    if len(current_learning) != BASELINE["learning_target_existing"] + BASELINE["learning_candidates"]:
        raise RuntimeError("ANA_LUCIA_F2_6_POST_LEARNING_TOTAL_FAILED")
    if len(current_attendance) != BASELINE["attendance_target_existing"] + BASELINE["attendance_candidates"]:
        raise RuntimeError("ANA_LUCIA_F2_6_POST_ATTENDANCE_TOTAL_FAILED")

    learning_groups, learning_missing = _group(current_learning, _learning_key)
    if learning_missing or any(len(rows) != 1 for rows in learning_groups.values()):
        raise RuntimeError("ANA_LUCIA_F2_6_POST_LEARNING_COLLISION")
    attendance_groups, _ = _group(current_attendance, _attendance_key)
    if any(len(rows) != 1 for rows in attendance_groups.values()):
        raise RuntimeError("ANA_LUCIA_F2_6_POST_ATTENDANCE_COLLISION")

    legacy_learning = _load_rows(db, "learning_objects", class_ids=class_ids, course_id=context["legacy_id"])
    legacy_attendance = _load_rows(db, "attendance", class_ids=class_ids, course_id=context["legacy_id"])
    if legacy_learning:
        raise RuntimeError("ANA_LUCIA_F2_6_POST_LEGACY_LEARNING_REMAINS")
    if len(legacy_attendance) != BASELINE["attendance_excluded_not_teacher"]:
        raise RuntimeError("ANA_LUCIA_F2_6_POST_LEGACY_ATTENDANCE_REMAINDER_DRIFT")

    return {
        "learning_current_total": len(current_learning),
        "attendance_current_total": len(current_attendance),
        "legacy_learning_remaining": len(legacy_learning),
        "legacy_attendance_non_teacher_remaining": len(legacy_attendance),
    }


def run_authorized_remap(*, authorize_production_writes: bool) -> dict[str, Any]:
    if not authorize_production_writes:
        raise RuntimeError("ANA_LUCIA_F2_6_EXPLICIT_PRODUCTION_WRITE_AUTHORIZATION_REQUIRED")
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise RuntimeError("ANA_LUCIA_F2_6_MONGO_URL_MISSING")

    client = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)
    db = client[db_name]
    applied: list[tuple[str, str, str]] = []
    context: dict[str, Any] | None = None
    try:
        user, staff = _unique_teacher_identity(db)
        context = _resolve_context(db, user, staff)
        state = _baseline_state(db, context, user, staff)

        if _already_applied(state):
            return {
                "schema": "ANA_LUCIA_F2_6_SURGICAL_COURSE_ID_REMAP_V1",
                "status": "ALREADY_APPLIED_VERIFIED",
                "production_writes": False,
                "database_mutation": False,
                "updated_fields": [],
                "target_pair_count": 8,
                "learning_documents": BASELINE["learning_candidates"],
                "attendance_documents": BASELINE["attendance_candidates"],
                "legacy_course_fingerprint": _fp(context["legacy_id"]),
                "current_course_fingerprint": _fp(context["current_id"]),
                "rollback_performed": False,
            }

        validated = _validate_prewrite(db, state, context)
        learning_ids = validated["learning_ids"]
        attendance_ids = validated["attendance_ids"]
        lineage_before = {
            _sid(row.get("id")): _sid(row.get("copied_from_id"))
            for row in state["learning_candidates"]
        }

        try:
            for row in state["learning_candidates"]:
                _apply_one(db, "learning_objects", row, context["legacy_id"], context["current_id"])
                applied.append(("learning_objects", _sid(row.get("id")), _sid(row.get("class_id"))))
            for row in state["attendance_candidates"]:
                _apply_one(db, "attendance", row, context["legacy_id"], context["current_id"])
                applied.append(("attendance", _sid(row.get("id")), _sid(row.get("class_id"))))

            post = _postverify(db, context, learning_ids, attendance_ids, lineage_before)
        except BaseException as exc:  # compensating rollback is mandatory
            rollback_ok = _rollback(db, applied, context["legacy_id"], context["current_id"])
            return {
                "schema": "ANA_LUCIA_F2_6_SURGICAL_COURSE_ID_REMAP_V1",
                "status": "SAFE_ROLLBACK" if rollback_ok else "MANUAL_RECOVERY_REQUIRED",
                "production_writes": bool(applied),
                "database_mutation": bool(applied),
                "updated_fields": ["course_id"] if applied else [],
                "attempted_documents": len(applied),
                "rollback_performed": bool(applied),
                "rollback_complete": rollback_ok,
                "error_fingerprint": _error_fp(exc),
                "legacy_course_fingerprint": _fp(context["legacy_id"]),
                "current_course_fingerprint": _fp(context["current_id"]),
            }

        return {
            "schema": "ANA_LUCIA_F2_6_SURGICAL_COURSE_ID_REMAP_V1",
            "status": "APPLIED_AND_VERIFIED",
            "production_writes": True,
            "database_mutation": True,
            "updated_fields": ["course_id"],
            "target_pair_count": 8,
            "learning_documents": len(learning_ids),
            "attendance_documents": len(attendance_ids),
            "total_documents": len(learning_ids) + len(attendance_ids),
            "tenant_backfill_documents": 0,
            "aula_numero_backfill_documents": 0,
            "copied_from_id_mutations": 0,
            "legacy_aggregate_attendance_preserved": validated["legacy_aggregate_attendance"],
            "attendance_missing_tenant_preserved": validated["tenant_missing_attendance"],
            "preexisting_missing_parent_preserved": validated["lineage"]["parent_missing"],
            "legacy_course_fingerprint": _fp(context["legacy_id"]),
            "current_course_fingerprint": _fp(context["current_id"]),
            "rollback_performed": False,
            "postconditions": post,
        }
    finally:
        client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorize-production-writes", action="store_true")
    args = parser.parse_args(argv)
    payload = run_authorized_remap(authorize_production_writes=args.authorize_production_writes)
    print("ANA_LUCIA_F2_6_JSON=" + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if payload.get("status") in {"APPLIED_AND_VERIFIED", "ALREADY_APPLIED_VERIFIED"} else 2


if __name__ == "__main__":
    sys.exit(main())
