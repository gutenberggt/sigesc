#!/usr/bin/env python3
"""ANA-LUCIA-F2.5B — adjudicação READ-ONLY de tenant e chave agregada legada.

Correção fail-closed da F2.5 após evidência runtime de que os oito documentos
``teacher_class_assignments`` do componente atual existem nas turmas-alvo, mas
não são atribuídos a Ana Lucia. Eles são inventariados, nunca usados para
inferir ``aula_numero`` ou tenant.

Princípios:
1. tenant ausente é adjudicado somente quando convergem o vínculo legado ativo
   de Ana, a turma, a escola e os demais anchors de tenant disponíveis;
2. ``aula_numero`` ausente em attendance legado NÃO é tratado como valor a ser
   inventado. O backend histórico preserva esse formato agregado; a auditoria
   verifica se a chave agregada (turma, data, período) pode ser preservada sem
   colisão nem mistura estrutural no conjunto que seria remapeado;
3. ``copied_from_id`` continua sendo adjudicado sem alteração de linhagem;
4. nenhuma escrita, backfill, remapeamento, merge ou saneamento é executado.

Boundary obrigatório:
- MongoDB somente leitura;
- nenhum HTTP/login;
- nenhuma leitura de attendance.records;
- nenhuma coleção de estudantes/matrículas;
- nenhum valor de notas/frequência e nenhum texto pedagógico;
- nenhum ID técnico bruto emitido; somente fingerprints SHA-256 truncados;
- audit_logs sem old/new/description;
- nenhuma mutação, backfill, merge, remapeamento, exclusão ou saneamento.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
import re
import unicodedata
from typing import Any, Iterable, Mapping

from pymongo import MongoClient

ACADEMIC_YEAR = int(os.environ.get("ANA_LUCIA_F2_5B_ACADEMIC_YEAR", "2026"))
TEACHER_NAME = "Ana Lucia Faria Pinto"
COMPONENT_NAME = "Língua Inglesa"
CURRENT_LEVEL = "fundamental_anos_finais"
LEGACY_LEVEL = "eja_final"
ACTIVE_STATUSES = ("ativo", "active")
TARGET_CLASSES: tuple[str, ...] = (
    "6º ANO A",
    "6º ANO B",
    "6º ANO C",
    "6º ANO D",
    "9º ANO A",
    "9º ANO B",
    "9º ANO C",
    "9º ANO D",
)

F2_4_BASELINE = {
    "learning_candidates": 198,
    "attendance_candidates": 392,
    "attendance_tenant_missing": 74,
    "attendance_missing_natural_key": 4,
    "copied_candidates": 74,
    "parent_in_candidate_set": 73,
    "parent_missing": 1,
}

COMMON_PROJECTION = {
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
    "created_at": 1,
    "updated_at": 1,
    "version": 1,
}


def _sid(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _norm(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", _sid(value))
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = raw.casefold().replace("º", "o").replace("ª", "a")
    return re.sub(r"\s+", " ", raw).strip()


def _fp(value: Any) -> str | None:
    raw = _sid(value)
    if not raw:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _day(value: Any) -> str:
    return _sid(value)[:10]


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


def _attendance_key(row: Mapping[str, Any]) -> tuple[str, str, str, str] | None:
    class_id = _sid(row.get("class_id"))
    day = _day(row.get("date"))
    aula = _sid(row.get("aula_numero"))
    if not class_id or not day or not aula:
        return None
    return class_id, day, _sid(row.get("period")) or "regular", aula


def _aggregate_key(row: Mapping[str, Any]) -> tuple[str, str, str] | None:
    class_id = _sid(row.get("class_id"))
    day = _day(row.get("date"))
    if not class_id or not day:
        return None
    return class_id, day, _sid(row.get("period")) or "regular"


def _missing_attendance_key_fields(row: Mapping[str, Any]) -> list[str]:
    missing = []
    if not _sid(row.get("class_id")):
        missing.append("class_id")
    if not _day(row.get("date")):
        missing.append("date")
    if not _sid(row.get("aula_numero")):
        missing.append("aula_numero")
    return missing


def _unique_teacher_identity(db) -> tuple[dict[str, Any], dict[str, Any]]:
    users = list(
        db.users.find(
            {"$or": [{"full_name": TEACHER_NAME}, {"name": TEACHER_NAME}]},
            {"_id": 0, "id": 1, "email": 1, "full_name": 1, "name": 1, "role": 1, "mantenedora_id": 1},
        ).limit(5)
    )
    users = [row for row in users if _norm(row.get("full_name") or row.get("name")) == _norm(TEACHER_NAME)]
    if len(users) != 1:
        raise RuntimeError(f"ANA_LUCIA_F2_5B_TEACHER_USER_MATCHES:{len(users)}")
    if users[0].get("role") != "professor":
        raise RuntimeError(f"ANA_LUCIA_F2_5B_TEACHER_ROLE:{users[0].get('role')}")
    user = users[0]

    clauses = [{"user_id": user["id"]}]
    if user.get("email"):
        clauses.append({"email": user["email"]})
    rows = list(
        db.staff.find(
            {"$or": clauses},
            {"_id": 0, "id": 1, "user_id": 1, "email": 1, "mantenedora_id": 1},
        ).limit(5)
    )
    dedup = {_sid(row.get("id")): row for row in rows if _sid(row.get("id"))}
    if len(dedup) != 1:
        raise RuntimeError(f"ANA_LUCIA_F2_5B_STAFF_MATCHES:{len(dedup)}")
    return user, next(iter(dedup.values()))


def _resolve_context(db, user: Mapping[str, Any], staff: Mapping[str, Any]) -> dict[str, Any]:
    assignments = list(
        db.teacher_assignments.find(
            {
                "staff_id": staff["id"],
                "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
                "status": {"$in": list(ACTIVE_STATUSES)},
            },
            {
                "_id": 0, "id": 1, "class_id": 1, "course_id": 1,
                "school_id": 1, "mantenedora_id": 1, "status": 1,
            },
        )
    )
    class_ids = sorted({_sid(row.get("class_id")) for row in assignments if _sid(row.get("class_id"))})
    classes = list(
        db.classes.find(
            {"id": {"$in": class_ids}},
            {"_id": 0, "id": 1, "name": 1, "school_id": 1, "mantenedora_id": 1, "academic_year": 1},
        )
    )
    class_by_id_raw = {_sid(row.get("id")): row for row in classes if _sid(row.get("id"))}
    school_ids = sorted({_sid(row.get("school_id")) for row in classes if _sid(row.get("school_id"))})
    schools = list(
        db.schools.find(
            {"id": {"$in": school_ids}},
            {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1},
        )
    )
    school_by_id = {_sid(row.get("id")): row for row in schools if _sid(row.get("id"))}
    assignment_course_ids = sorted({_sid(row.get("course_id")) for row in assignments if _sid(row.get("course_id"))})
    courses = list(
        db.courses.find(
            {"id": {"$in": assignment_course_ids}},
            {"_id": 0, "id": 1, "name": 1, "nivel_ensino": 1, "mantenedora_id": 1},
        )
    )
    course_by_id = {_sid(row.get("id")): row for row in courses if _sid(row.get("id"))}

    targets: list[dict[str, Any]] = []
    current_ids: set[str] = set()
    all_tenants: set[str] = set()
    for class_name in TARGET_CLASSES:
        matches = []
        for row in assignments:
            klass = class_by_id_raw.get(_sid(row.get("class_id"))) or {}
            course = course_by_id.get(_sid(row.get("course_id"))) or {}
            if _norm(klass.get("name")) == _norm(class_name) and _norm(course.get("name")) == _norm(COMPONENT_NAME):
                matches.append(row)
        if len(matches) != 1:
            raise RuntimeError(f"ANA_LUCIA_F2_5B_TARGET_NOT_EXACT:{class_name}:{len(matches)}")
        assignment = matches[0]
        klass = class_by_id_raw[_sid(assignment.get("class_id"))]
        school = school_by_id.get(_sid(klass.get("school_id"))) or {}
        anchors = {
            _sid(assignment.get("mantenedora_id")),
            _sid(klass.get("mantenedora_id")),
            _sid(school.get("mantenedora_id")),
            _sid(user.get("mantenedora_id")),
            _sid(staff.get("mantenedora_id")),
        }
        anchors.discard("")
        if len(anchors) != 1:
            raise RuntimeError(f"ANA_LUCIA_F2_5B_TENANT_ANCHORS_NOT_EXACT:{class_name}:{len(anchors)}")
        tenant_id = next(iter(anchors))
        current_id = _sid(assignment.get("course_id"))
        if not current_id:
            raise RuntimeError(f"ANA_LUCIA_F2_5B_CURRENT_COURSE_MISSING:{class_name}")
        all_tenants.add(tenant_id)
        current_ids.add(current_id)
        targets.append({
            "class": class_name,
            "class_id": _sid(klass.get("id")),
            "school": _sid(school.get("name")),
            "school_id": _sid(klass.get("school_id")),
            "tenant_id": tenant_id,
            "legacy_assignment_id": _sid(assignment.get("id")),
            "current_course_id": current_id,
        })

    if len(current_ids) != 1 or len(all_tenants) != 1:
        raise RuntimeError(
            f"ANA_LUCIA_F2_5B_NON_UNIQUE_CONTEXT:current={len(current_ids)}:tenant={len(all_tenants)}"
        )
    current_id = next(iter(current_ids))
    tenant_id = next(iter(all_tenants))

    same_name = list(
        db.courses.find(
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
        )
    )
    same_name = [row for row in same_name if _norm(row.get("name")) == _norm(COMPONENT_NAME)]
    current_matches = [
        row for row in same_name
        if _sid(row.get("id")) == current_id and _norm(row.get("nivel_ensino")) == _norm(CURRENT_LEVEL)
    ]
    legacy_matches = [row for row in same_name if _norm(row.get("nivel_ensino")) == _norm(LEGACY_LEVEL)]
    if len(current_matches) != 1:
        raise RuntimeError(f"ANA_LUCIA_F2_5B_CURRENT_IDENTITY_INVALID:{len(current_matches)}")
    if len(legacy_matches) != 1:
        raise RuntimeError(f"ANA_LUCIA_F2_5B_LEGACY_IDENTITY_INVALID:{len(legacy_matches)}")
    legacy_id = _sid(legacy_matches[0].get("id"))
    if legacy_id == current_id:
        raise RuntimeError("ANA_LUCIA_F2_5B_IDENTITIES_COLLAPSED")

    target_class_ids = [row["class_id"] for row in targets]
    dvd_rows = list(
        db.teacher_class_assignments.find(
            {
                "class_id": {"$in": target_class_ids},
                "component_id": current_id,
                "deleted": {"$ne": True},
            },
            {"_id": 0, "class_id": 1, "teacher_id": 1, "staff_id": 1, "created_by": 1, "updated_by": 1, "recorded_by": 1},
        )
    )
    actor_ids = {_sid(user.get("id")), _sid(staff.get("id"))} - {""}
    dvd_per_class = Counter(_sid(row.get("class_id")) for row in dvd_rows)
    dvd_teacher_attributed = sum(1 for row in dvd_rows if _teacher_actor(row, actor_ids))

    schedule_rows = list(
        db.class_schedules.find(
            {
                "class_id": {"$in": target_class_ids},
                "schedule_slots.course_id": {"$in": [current_id, legacy_id]},
            },
            {"_id": 0, "class_id": 1, "schedule_slots.course_id": 1},
        )
    )

    return {
        "targets": targets,
        "tenant_id": tenant_id,
        "current_id": current_id,
        "legacy_id": legacy_id,
        "current_course": current_matches[0],
        "legacy_course": legacy_matches[0],
        "class_by_id": {row["class_id"]: row for row in targets},
        "dvd_inventory": {
            "target_current_reference_documents": len(dvd_rows),
            "teacher_attributed_documents": dvd_teacher_attributed,
            "per_class_counts": {
                row["class"]: dvd_per_class.get(row["class_id"], 0) for row in targets
            },
            "used_as_tenant_anchor": False,
            "used_as_aula_anchor": False,
        },
        "schedule_inventory": {
            "target_class_schedule_documents_referencing_either_identity": len(schedule_rows),
            "used_as_aula_anchor": False,
        },
    }


def _assignment_owners(db, teacher_user_id: str) -> tuple[set[str], dict[str, str]]:
    rows = list(
        db.teacher_class_assignments.find(
            {},
            {"_id": 0, "id": 1, "teacher_id": 1, "deleted": 1},
        )
    )
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


def _load_rows(db, collection: str, *, class_ids: set[str], course_id: str) -> list[dict[str, Any]]:
    return list(
        db[collection].find(
            {
                "$and": [
                    {"class_id": {"$in": sorted(class_ids)}},
                    {"course_id": course_id},
                    _year_scope(),
                ]
            },
            COMMON_PROJECTION,
        )
    )


def _candidate_partition(
    rows: Iterable[Mapping[str, Any]],
    *,
    actor_ids: set[str],
    teacher_assignment_ids: set[str],
    assignment_owner: Mapping[str, str],
    teacher_user_id: str,
) -> tuple[list[Mapping[str, Any]], Counter[str]]:
    candidates: list[Mapping[str, Any]] = []
    excluded: Counter[str] = Counter()
    for row in rows:
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


def _tenant_adjudication(
    *,
    attendance_candidates: list[Mapping[str, Any]],
    class_by_id: Mapping[str, Mapping[str, Any]],
    tenant_id: str,
) -> dict[str, Any]:
    missing = [row for row in attendance_candidates if not _sid(row.get("mantenedora_id"))]
    decisions = Counter()
    per_class = Counter()
    unresolved_fps: list[str] = []
    for row in missing:
        class_id = _sid(row.get("class_id"))
        target = class_by_id.get(class_id)
        if not target:
            decisions["UNRESOLVED_CLASS_CONTEXT"] += 1
            unresolved_fps.append(_fp(row.get("id")) or "<missing-id>")
            continue
        if _sid(target.get("tenant_id")) != tenant_id:
            decisions["CONTRADICTORY_TARGET_TENANT"] += 1
            unresolved_fps.append(_fp(row.get("id")) or "<missing-id>")
            continue
        row_school = _sid(row.get("school_id"))
        target_school = _sid(target.get("school_id"))
        if row_school and row_school != target_school:
            decisions["ROW_SCHOOL_MISMATCH"] += 1
            unresolved_fps.append(_fp(row.get("id")) or "<missing-id>")
            continue
        decisions["DETERMINISTIC_FROM_ANA_LEGACY_ASSIGNMENT_CLASS_SCHOOL_CONTEXT"] += 1
        per_class[_sid(target.get("class"))] += 1

    deterministic = decisions["DETERMINISTIC_FROM_ANA_LEGACY_ASSIGNMENT_CLASS_SCHOOL_CONTEXT"]
    unresolved = len(missing) - deterministic
    return {
        "missing_tenant_candidates": len(missing),
        "deterministic_expected_tenant": deterministic,
        "unresolved_or_contradictory": unresolved,
        "decision_counts": dict(sorted(decisions.items())),
        "per_class_deterministic_counts": dict(sorted(per_class.items())),
        "expected_tenant_fingerprint": _fp(tenant_id),
        "unresolved_record_fingerprints": unresolved_fps[:50],
        "classification": (
            "TENANT_ADJUDICATION_DETERMINISTIC_FROM_ANA_LEGACY_CONTEXT"
            if missing and unresolved == 0
            else "TENANT_ADJUDICATION_PARTIAL_OR_BLOCKED"
            if missing
            else "NO_MISSING_TENANT"
        ),
        "write_authorized": False,
    }


def _adjudicate_legacy_aggregate_case(
    row: Mapping[str, Any],
    *,
    source_candidates: list[Mapping[str, Any]],
    target_attendance: list[Mapping[str, Any]],
) -> dict[str, Any]:
    missing = _missing_attendance_key_fields(row)
    result = {
        "record_fingerprint": _fp(row.get("id")),
        "missing_fields": missing,
        "date": _day(row.get("date")) or None,
        "period": _sid(row.get("period")) or "regular",
        "number_of_classes": row.get("number_of_classes"),
        "source_aggregate_rows_same_key": 0,
        "source_session_rows_same_day": 0,
        "target_aggregate_rows_same_key": 0,
        "target_session_rows_same_day": 0,
        "classification": "UNRESOLVED_INCOMPLETE_NATURAL_KEY",
        "aula_numero_backfill_required": False,
        "aula_numero_inferred": None,
    }
    if missing != ["aula_numero"]:
        if "date" in missing:
            result["classification"] = "UNRESOLVED_MISSING_DATE_NO_TIMESTAMP_INFERENCE"
        elif "class_id" in missing:
            result["classification"] = "UNRESOLVED_MISSING_CLASS"
        return result

    agg = _aggregate_key(row)
    if agg is None:
        return result
    source_same = [other for other in source_candidates if _aggregate_key(other) == agg]
    target_same = [other for other in target_attendance if _aggregate_key(other) == agg]
    source_aggregate = [other for other in source_same if not _sid(other.get("aula_numero"))]
    source_sessions = [other for other in source_same if _sid(other.get("aula_numero"))]
    target_aggregate = [other for other in target_same if not _sid(other.get("aula_numero"))]
    target_sessions = [other for other in target_same if _sid(other.get("aula_numero"))]
    result.update({
        "source_aggregate_rows_same_key": len(source_aggregate),
        "source_session_rows_same_day": len(source_sessions),
        "target_aggregate_rows_same_key": len(target_aggregate),
        "target_session_rows_same_day": len(target_sessions),
    })

    if len(source_aggregate) != 1:
        result["classification"] = "BLOCKED_DUPLICATE_LEGACY_AGGREGATE_SOURCE"
    elif target_aggregate:
        result["classification"] = "BLOCKED_LEGACY_AGGREGATE_TARGET_COLLISION"
    elif source_sessions:
        result["classification"] = "BLOCKED_MIXED_SOURCE_AGGREGATE_AND_SESSION_ROWS_SAME_DAY"
    elif target_sessions:
        result["classification"] = "BLOCKED_MIXED_TARGET_AGGREGATE_AND_SESSION_ROWS_SAME_DAY"
    else:
        result["classification"] = "LEGACY_AGGREGATE_KEY_PRESERVABLE_NO_AULA_BACKFILL"
    return result


def _natural_key_adjudication(
    *,
    attendance_candidates: list[Mapping[str, Any]],
    target_attendance: list[Mapping[str, Any]],
    class_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    incomplete = [row for row in attendance_candidates if _attendance_key(row) is None]
    cases = []
    counts = Counter()
    for row in incomplete:
        case = _adjudicate_legacy_aggregate_case(
            row,
            source_candidates=attendance_candidates,
            target_attendance=target_attendance,
        )
        target = class_by_id.get(_sid(row.get("class_id"))) or {}
        case["class"] = _sid(target.get("class")) or "<unresolved>"
        counts[case["classification"]] += 1
        cases.append(case)

    safe = counts["LEGACY_AGGREGATE_KEY_PRESERVABLE_NO_AULA_BACKFILL"]
    unresolved = len(incomplete) - safe
    return {
        "incomplete_candidates": len(incomplete),
        "legacy_aggregate_preservable_cases": safe,
        "unresolved_or_blocked_cases": unresolved,
        "classification_counts": dict(sorted(counts.items())),
        "cases": cases,
        "classification": (
            "NATURAL_KEY_ADJUDICATION_LEGACY_AGGREGATES_PRESERVABLE"
            if incomplete and unresolved == 0
            else "NATURAL_KEY_ADJUDICATION_PARTIAL_OR_BLOCKED"
            if incomplete
            else "NO_INCOMPLETE_NATURAL_KEY"
        ),
        "aula_numero_inference_used": False,
        "aula_numero_backfill_authorized": False,
        "write_authorized": False,
    }


def _audit_missing_parent(db, parent_id: str) -> dict[str, Any]:
    rows = list(
        db.audit_logs.find(
            {"collection": "learning_objects", "document_id": parent_id},
            {"_id": 0, "action": 1, "timestamp": 1, "timestamp_utc": 1, "user_role": 1},
        ).sort("timestamp", 1).limit(100)
    )
    actions = Counter(_sid(row.get("action")) or "<unknown>" for row in rows)
    return {
        "event_count": len(rows),
        "action_counts": dict(sorted(actions.items())),
        "has_delete_like_event": any(
            token in _norm(action)
            for action in actions
            for token in ("delete", "exclu", "remove")
        ),
    }


def _detect_candidate_cycles(edges: Mapping[str, str]) -> int:
    cycles = set()
    for start in edges:
        seen = set()
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


def _lineage_adjudication(
    db,
    *,
    learning_candidates: list[Mapping[str, Any]],
    legacy_id: str,
    current_id: str,
) -> dict[str, Any]:
    candidate_ids = {_sid(row.get("id")) for row in learning_candidates if _sid(row.get("id"))}
    copied = [row for row in learning_candidates if _sid(row.get("copied_from_id"))]
    parent_ids = sorted({_sid(row.get("copied_from_id")) for row in copied})
    parents = list(
        db.learning_objects.find(
            {"id": {"$in": parent_ids}},
            {"_id": 0, "id": 1, "course_id": 1, "class_id": 1, "date": 1, "mantenedora_id": 1, "deleted": 1, "status": 1},
        )
    ) if parent_ids else []
    by_id = {_sid(row.get("id")): row for row in parents if _sid(row.get("id"))}

    counts = Counter()
    edges: dict[str, str] = {}
    missing_details = []
    for child in copied:
        child_id = _sid(child.get("id"))
        parent_id = _sid(child.get("copied_from_id"))
        parent = by_id.get(parent_id)
        if not parent:
            counts["PREEXISTING_PARENT_MISSING"] += 1
            detail = {"parent_fingerprint": _fp(parent_id), "child_fingerprint": _fp(child_id)}
            detail.update(_audit_missing_parent(db, parent_id))
            missing_details.append(detail)
            continue
        if parent_id in candidate_ids:
            counts["PARENT_IN_CANDIDATE_REMAP_PRESERVES_EDGE"] += 1
            if child_id:
                edges[child_id] = parent_id
        elif _sid(parent.get("course_id")) == legacy_id:
            counts["PARENT_LEGACY_OUTSIDE_CANDIDATE_WOULD_CROSS_IDENTITY"] += 1
        elif _sid(parent.get("course_id")) == current_id:
            counts["PARENT_ALREADY_CURRENT_IDENTITY"] += 1
        else:
            counts["PARENT_OTHER_IDENTITY"] += 1

    cycle_count = _detect_candidate_cycles(edges)
    new_cross_identity = (
        counts["PARENT_LEGACY_OUTSIDE_CANDIDATE_WOULD_CROSS_IDENTITY"]
        + counts["PARENT_OTHER_IDENTITY"]
    )
    preexisting_missing = counts["PREEXISTING_PARENT_MISSING"]
    return {
        "copied_candidate_documents": len(copied),
        "distinct_parent_ids": len(parent_ids),
        "resolved_parent_ids": len(by_id),
        "decision_counts": dict(sorted(counts.items())),
        "candidate_graph_cycles": cycle_count,
        "new_cross_identity_edges_if_all_candidates_remapped": new_cross_identity,
        "preexisting_missing_parent_edges": preexisting_missing,
        "missing_parent_details": missing_details,
        "classification": (
            "LINEAGE_BLOCKED_NEW_CROSS_IDENTITY_OR_CYCLE"
            if new_cross_identity or cycle_count
            else "LINEAGE_PRESERVED_WITH_PREEXISTING_BROKEN_REFERENCE"
            if preexisting_missing
            else "LINEAGE_PRESERVED_BY_SET_REMAP"
        ),
        "remap_would_create_new_lineage_break": bool(new_cross_identity or cycle_count),
        "preexisting_missing_parent_requires_separate_sanitation": bool(preexisting_missing),
        "write_authorized": False,
    }


def _baseline_drift(
    *,
    learning_candidates: int,
    attendance_candidates: int,
    tenant_missing: int,
    incomplete_key: int,
    lineage: Mapping[str, Any],
) -> dict[str, int]:
    counts = lineage.get("decision_counts") or {}
    return {
        "learning_candidates": learning_candidates - F2_4_BASELINE["learning_candidates"],
        "attendance_candidates": attendance_candidates - F2_4_BASELINE["attendance_candidates"],
        "attendance_tenant_missing": tenant_missing - F2_4_BASELINE["attendance_tenant_missing"],
        "attendance_missing_natural_key": incomplete_key - F2_4_BASELINE["attendance_missing_natural_key"],
        "copied_candidates": lineage.get("copied_candidate_documents", 0) - F2_4_BASELINE["copied_candidates"],
        "parent_in_candidate_set": counts.get("PARENT_IN_CANDIDATE_REMAP_PRESERVES_EDGE", 0) - F2_4_BASELINE["parent_in_candidate_set"],
        "parent_missing": lineage.get("preexisting_missing_parent_edges", 0) - F2_4_BASELINE["parent_missing"],
    }


def run_live_audit() -> dict[str, Any]:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise RuntimeError("ANA_LUCIA_F2_5B_MONGO_URL_MISSING")

    client = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)
    db = client[db_name]
    try:
        user, staff = _unique_teacher_identity(db)
        context = _resolve_context(db, user, staff)
        targets = context["targets"]
        tenant_id = context["tenant_id"]
        current_id = context["current_id"]
        legacy_id = context["legacy_id"]
        class_by_id = context["class_by_id"]
        target_class_ids = set(class_by_id)

        teacher_user_id = _sid(user.get("id"))
        staff_id = _sid(staff.get("id"))
        actor_ids = {value for value in (teacher_user_id, staff_id) if value}
        teacher_assignment_ids, assignment_owner = _assignment_owners(db, teacher_user_id)

        raw_learning = _load_rows(db, "learning_objects", class_ids=target_class_ids, course_id=legacy_id)
        raw_attendance = _load_rows(db, "attendance", class_ids=target_class_ids, course_id=legacy_id)
        target_attendance = [
            row for row in _load_rows(db, "attendance", class_ids=target_class_ids, course_id=current_id)
            if _active_like(row)
        ]
        learning_candidates, learning_excluded = _candidate_partition(
            raw_learning,
            actor_ids=actor_ids,
            teacher_assignment_ids=teacher_assignment_ids,
            assignment_owner=assignment_owner,
            teacher_user_id=teacher_user_id,
        )
        attendance_candidates, attendance_excluded = _candidate_partition(
            raw_attendance,
            actor_ids=actor_ids,
            teacher_assignment_ids=teacher_assignment_ids,
            assignment_owner=assignment_owner,
            teacher_user_id=teacher_user_id,
        )

        tenant = _tenant_adjudication(
            attendance_candidates=attendance_candidates,
            class_by_id=class_by_id,
            tenant_id=tenant_id,
        )
        natural_key = _natural_key_adjudication(
            attendance_candidates=attendance_candidates,
            target_attendance=target_attendance,
            class_by_id=class_by_id,
        )
        lineage = _lineage_adjudication(
            db,
            learning_candidates=learning_candidates,
            legacy_id=legacy_id,
            current_id=current_id,
        )
        drift = _baseline_drift(
            learning_candidates=len(learning_candidates),
            attendance_candidates=len(attendance_candidates),
            tenant_missing=tenant["missing_tenant_candidates"],
            incomplete_key=natural_key["incomplete_candidates"],
            lineage=lineage,
        )

        tenant_clear = tenant["unresolved_or_contradictory"] == 0
        key_clear = natural_key["unresolved_or_blocked_cases"] == 0
        lineage_clear = not lineage["remap_would_create_new_lineage_break"]
        drift_clear = all(value == 0 for value in drift.values())
        if tenant_clear and key_clear and lineage_clear:
            overall = (
                "ADJUDICATION_CLEAR_FOR_SEPARATE_COURSE_ID_REMAP_DESIGN_PRESERVING_LEGACY_AGGREGATES_BUT_WRITE_NOT_AUTHORIZED"
                if drift_clear
                else "ADJUDICATION_STRUCTURALLY_CLEAR_WITH_BASELINE_DRIFT_REQUIRES_REVIEW"
            )
        else:
            overall = "ADJUDICATION_BLOCKED_REQUIRES_FURTHER_REVIEW_BEFORE_ANY_WRITE"

        return {
            "schema": "ANA_LUCIA_F2_5B_LEGACY_AGGREGATE_ADJUDICATION_READ_ONLY_V1",
            "status": "PASS",
            "classification": overall,
            "database_mutation": False,
            "production_writes": False,
            "mongo_reads_only": True,
            "http_methods": [],
            "login_endpoint_used": False,
            "attendance_records_read": False,
            "student_data_read": False,
            "student_pii_emitted": False,
            "grade_values_read": False,
            "attendance_status_values_read": False,
            "pedagogical_text_read": False,
            "technical_ids_emitted": False,
            "technical_id_fingerprints_emitted": True,
            "audit_old_new_description_read": False,
            "automatic_remap_authorized": False,
            "target": {
                "teacher": TEACHER_NAME,
                "component": COMPONENT_NAME,
                "academic_year": ACADEMIC_YEAR,
                "target_pair_count": len(targets),
                "current_course_fingerprint": _fp(current_id),
                "legacy_course_fingerprint": _fp(legacy_id),
                "current_level": _sid(context["current_course"].get("nivel_ensino")),
                "legacy_level": _sid(context["legacy_course"].get("nivel_ensino")),
                "tenant_fingerprint": _fp(tenant_id),
            },
            "structural_anchor_inventory": {
                "tenant_authority": "ANA_ACTIVE_LEGACY_ASSIGNMENT_PLUS_CLASS_SCHOOL",
                "dvd": context["dvd_inventory"],
                "schedule": context["schedule_inventory"],
                "foreign_dvd_slots_used_for_inference": False,
            },
            "candidate_scope": {
                "learning_candidates": len(learning_candidates),
                "learning_excluded": dict(sorted(learning_excluded.items())),
                "attendance_candidates": len(attendance_candidates),
                "attendance_excluded": dict(sorted(attendance_excluded.items())),
                "target_attendance_existing": len(target_attendance),
                "baseline_drift_vs_f2_4": drift,
            },
            "tenant_adjudication": tenant,
            "natural_key_adjudication": natural_key,
            "copy_lineage_adjudication": lineage,
            "safety_decision": {
                "write_authorized": False,
                "tenant_backfill_authorized": False,
                "aula_numero_backfill_authorized": False,
                "course_id_remap_authorized": False,
                "copied_from_id_mutation_authorized": False,
                "global_course_merge_authorized": False,
                "transferencia_institucional_touched": False,
                "mt1_touched": False,
                "next_step_requires_separate_explicit_write_authorization_even_if_clear": True,
            },
        }
    finally:
        client.close()


def main() -> None:
    print(
        "ANA_LUCIA_F2_5B_JSON="
        + json.dumps(run_live_audit(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


if __name__ == "__main__":
    main()
