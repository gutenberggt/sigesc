#!/usr/bin/env python3
"""ANA-LUCIA-F2.5 — adjudicação READ-ONLY de tenant, chave natural e linhagem.

Escopo:
1. Revalidar o conjunto candidato herdado da F2.4.
2. Adjudicar os attendance sem mantenedora_id por âncoras estruturais
   turma -> escola -> vínculo atual/DVD, sem escrever o tenant.
3. Adjudicar attendance com chave natural incompleta. aula_numero só é
   considerado determinístico quando o vínculo DVD oferece exatamente um
   slot possível para a data e não há conflito estrutural já ocupado.
4. Classificar copied_from_id de learning_objects distinguindo:
   - arestas preservadas porque pai e filho estão no mesmo conjunto candidato;
   - pais externos em identidade legacy/current/outra;
   - referência já quebrada antes do remapeamento, com sinal estrutural de
     audit_logs quando disponível.

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

from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
import os
import re
import unicodedata
from typing import Any, Iterable, Mapping

from pymongo import MongoClient

ACADEMIC_YEAR = int(os.environ.get("ANA_LUCIA_F2_5_ACADEMIC_YEAR", "2026"))
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
        raise RuntimeError(f"ANA_LUCIA_F2_5_TEACHER_USER_MATCHES:{len(users)}")
    if users[0].get("role") != "professor":
        raise RuntimeError(f"ANA_LUCIA_F2_5_TEACHER_ROLE:{users[0].get('role')}")
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
        raise RuntimeError(f"ANA_LUCIA_F2_5_STAFF_MATCHES:{len(dedup)}")
    return user, next(iter(dedup.values()))


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


def _resolve_context(db, user: Mapping[str, Any], staff: Mapping[str, Any]) -> dict[str, Any]:
    legacy_assignments = list(
        db.teacher_assignments.find(
            {
                "staff_id": staff["id"],
                "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
                "status": {"$in": list(ACTIVE_STATUSES)},
            },
            {"_id": 0, "id": 1, "class_id": 1, "course_id": 1, "school_id": 1, "mantenedora_id": 1},
        )
    )
    class_ids = sorted({_sid(row.get("class_id")) for row in legacy_assignments if _sid(row.get("class_id"))})
    classes = list(
        db.classes.find(
            {"id": {"$in": class_ids}},
            {"_id": 0, "id": 1, "name": 1, "school_id": 1, "mantenedora_id": 1, "academic_year": 1},
        )
    )
    class_by_id = {_sid(row.get("id")): row for row in classes if _sid(row.get("id"))}
    school_ids = sorted({_sid(row.get("school_id")) for row in classes if _sid(row.get("school_id"))})
    schools = list(
        db.schools.find(
            {"id": {"$in": school_ids}},
            {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1},
        )
    )
    school_by_id = {_sid(row.get("id")): row for row in schools if _sid(row.get("id"))}

    assignment_course_ids = sorted({_sid(row.get("course_id")) for row in legacy_assignments if _sid(row.get("course_id"))})
    courses = list(
        db.courses.find(
            {"id": {"$in": assignment_course_ids}},
            {"_id": 0, "id": 1, "name": 1, "nivel_ensino": 1, "mantenedora_id": 1},
        )
    )
    course_by_id = {_sid(row.get("id")): row for row in courses if _sid(row.get("id"))}

    targets: list[dict[str, Any]] = []
    current_ids: set[str] = set()
    tenant_ids: set[str] = set()
    for class_name in TARGET_CLASSES:
        matches = []
        for row in legacy_assignments:
            klass = class_by_id.get(_sid(row.get("class_id"))) or {}
            course = course_by_id.get(_sid(row.get("course_id"))) or {}
            if _norm(klass.get("name")) == _norm(class_name) and _norm(course.get("name")) == _norm(COMPONENT_NAME):
                matches.append(row)
        if len(matches) != 1:
            raise RuntimeError(f"ANA_LUCIA_F2_5_TARGET_NOT_EXACT:{class_name}:{len(matches)}")
        assignment = matches[0]
        klass = class_by_id[_sid(assignment.get("class_id"))]
        school = school_by_id.get(_sid(klass.get("school_id"))) or {}
        tenant_id = _sid(klass.get("mantenedora_id") or school.get("mantenedora_id") or user.get("mantenedora_id"))
        current_id = _sid(assignment.get("course_id"))
        if not tenant_id or not current_id:
            raise RuntimeError(f"ANA_LUCIA_F2_5_TARGET_CONTEXT_MISSING:{class_name}")
        tenant_ids.add(tenant_id)
        current_ids.add(current_id)
        targets.append({
            "class": class_name,
            "class_id": _sid(klass.get("id")),
            "school": _sid(school.get("name")),
            "school_id": _sid(klass.get("school_id")),
            "tenant_id": tenant_id,
            "current_course_id": current_id,
        })
    if len(current_ids) != 1 or len(tenant_ids) != 1:
        raise RuntimeError(
            f"ANA_LUCIA_F2_5_NON_UNIQUE_CONTEXT:current={len(current_ids)}:tenant={len(tenant_ids)}"
        )
    current_id = next(iter(current_ids))
    tenant_id = next(iter(tenant_ids))

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
        raise RuntimeError(f"ANA_LUCIA_F2_5_CURRENT_COURSE_IDENTITY_INVALID:{len(current_matches)}")
    if len(legacy_matches) != 1:
        raise RuntimeError(f"ANA_LUCIA_F2_5_LEGACY_COURSE_IDENTITY_INVALID:{len(legacy_matches)}")
    legacy_id = _sid(legacy_matches[0].get("id"))
    if legacy_id == current_id:
        raise RuntimeError("ANA_LUCIA_F2_5_IDENTITIES_COLLAPSED_UNEXPECTEDLY")

    dvd_rows = list(
        db.teacher_class_assignments.find(
            {
                "teacher_id": _sid(user.get("id")),
                "class_id": {"$in": [row["class_id"] for row in targets]},
                "component_id": current_id,
                "deleted": {"$ne": True},
            },
            {
                "_id": 0,
                "id": 1,
                "teacher_id": 1,
                "class_id": 1,
                "component_id": 1,
                "mantenedora_id": 1,
                "school_id": 1,
                "weekly_slots": 1,
                "valid_from": 1,
                "valid_until": 1,
                "deleted": 1,
                "source_legacy_assignment_id": 1,
            },
        )
    )
    dvd_by_class: dict[str, dict[str, Any]] = {}
    for target in targets:
        rows = [row for row in dvd_rows if _sid(row.get("class_id")) == target["class_id"]]
        if len(rows) != 1:
            raise RuntimeError(f"ANA_LUCIA_F2_5_DVD_BINDING_NOT_EXACT:{target['class']}:{len(rows)}")
        dvd = rows[0]
        if _sid(dvd.get("mantenedora_id")) and _sid(dvd.get("mantenedora_id")) != tenant_id:
            raise RuntimeError(f"ANA_LUCIA_F2_5_DVD_TENANT_MISMATCH:{target['class']}")
        dvd_by_class[target["class_id"]] = dvd

    return {
        "targets": targets,
        "tenant_id": tenant_id,
        "current_id": current_id,
        "legacy_id": legacy_id,
        "current_course": current_matches[0],
        "legacy_course": legacy_matches[0],
        "dvd_by_class": dvd_by_class,
        "class_by_id": {row["class_id"]: row for row in targets},
    }


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
    dvd_by_class: Mapping[str, Mapping[str, Any]],
    tenant_id: str,
) -> dict[str, Any]:
    missing = [row for row in attendance_candidates if not _sid(row.get("mantenedora_id"))]
    decisions = Counter()
    per_class = Counter()
    unresolved_fps: list[str] = []
    for row in missing:
        class_id = _sid(row.get("class_id"))
        target = class_by_id.get(class_id)
        dvd = dvd_by_class.get(class_id)
        if not target or not dvd:
            decisions["UNRESOLVED_CLASS_OR_DVD_CONTEXT"] += 1
            unresolved_fps.append(_fp(row.get("id")) or "<missing-id>")
            continue

        anchors = {
            _sid(target.get("tenant_id")),
            _sid(dvd.get("mantenedora_id")),
        }
        anchors.discard("")
        if anchors != {tenant_id}:
            decisions["CONTRADICTORY_TENANT_ANCHORS"] += 1
            unresolved_fps.append(_fp(row.get("id")) or "<missing-id>")
            continue

        row_school = _sid(row.get("school_id"))
        target_school = _sid(target.get("school_id"))
        if row_school and row_school != target_school:
            decisions["ROW_SCHOOL_MISMATCH"] += 1
            unresolved_fps.append(_fp(row.get("id")) or "<missing-id>")
            continue

        decisions["DETERMINISTIC_FROM_CLASS_DVD_CONTEXT"] += 1
        per_class[_sid(target.get("class"))] += 1

    deterministic = decisions["DETERMINISTIC_FROM_CLASS_DVD_CONTEXT"]
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
            "TENANT_ADJUDICATION_DETERMINISTIC"
            if missing and unresolved == 0
            else "TENANT_ADJUDICATION_PARTIAL_OR_BLOCKED"
            if missing
            else "NO_MISSING_TENANT"
        ),
        "write_authorized": False,
    }


def _slots_for_day(assignment: Mapping[str, Any], day: str) -> list[str]:
    try:
        weekday = date.fromisoformat(day).isoweekday()
    except ValueError:
        return []
    values = []
    seen = set()
    for raw in assignment.get("weekly_slots") or []:
        if raw.get("weekday") != weekday:
            continue
        aula = _sid(raw.get("aula_numero"))
        if not aula or aula in seen:
            continue
        seen.add(aula)
        values.append(aula)
    return sorted(values, key=lambda value: (int(value) if value.isdigit() else 10**9, value))


def _adjudicate_missing_key_case(
    row: Mapping[str, Any],
    *,
    dvd: Mapping[str, Any] | None,
    source_complete: list[Mapping[str, Any]],
    target_complete: list[Mapping[str, Any]],
) -> dict[str, Any]:
    missing = _missing_attendance_key_fields(row)
    result = {
        "record_fingerprint": _fp(row.get("id")),
        "missing_fields": missing,
        "date": _day(row.get("date")) or None,
        "period": _sid(row.get("period")) or "regular",
        "number_of_classes": row.get("number_of_classes"),
        "current_weekly_slots": [],
        "occupied_source_slots_same_day": [],
        "occupied_target_slots_same_day": [],
        "remaining_slots": [],
        "classification": "UNRESOLVED_INCOMPLETE_NATURAL_KEY",
        "inferred_aula_numero": None,
    }
    if missing != ["aula_numero"]:
        if "date" in missing:
            result["classification"] = "UNRESOLVED_MISSING_DATE_NO_TIMESTAMP_INFERENCE"
        elif "class_id" in missing:
            result["classification"] = "UNRESOLVED_MISSING_CLASS"
        return result

    day = _day(row.get("date"))
    if not day or not dvd:
        result["classification"] = "UNRESOLVED_DVD_OR_DATE"
        return result

    slots = _slots_for_day(dvd, day)
    period = _sid(row.get("period")) or "regular"
    class_id = _sid(row.get("class_id"))
    source_slots = sorted({
        _sid(other.get("aula_numero"))
        for other in source_complete
        if _sid(other.get("class_id")) == class_id
        and _day(other.get("date")) == day
        and (_sid(other.get("period")) or "regular") == period
        and _sid(other.get("aula_numero"))
    })
    target_slots = sorted({
        _sid(other.get("aula_numero"))
        for other in target_complete
        if _sid(other.get("class_id")) == class_id
        and _day(other.get("date")) == day
        and (_sid(other.get("period")) or "regular") == period
        and _sid(other.get("aula_numero"))
    })
    occupied = set(source_slots) | set(target_slots)
    remaining = [slot for slot in slots if slot not in occupied]

    result.update({
        "current_weekly_slots": slots,
        "occupied_source_slots_same_day": source_slots,
        "occupied_target_slots_same_day": target_slots,
        "remaining_slots": remaining,
    })
    if len(remaining) == 1:
        result["classification"] = "DETERMINISTIC_UNIQUE_UNOCCUPIED_DVD_SLOT"
        result["inferred_aula_numero"] = remaining[0]
    elif not slots:
        result["classification"] = "UNRESOLVED_NO_DVD_SLOT_FOR_WEEKDAY"
    elif len(remaining) == 0:
        result["classification"] = "BLOCKED_ALL_DVD_SLOTS_ALREADY_OCCUPIED"
    else:
        result["classification"] = "UNRESOLVED_MULTIPLE_DVD_SLOTS"
    return result


def _natural_key_adjudication(
    *,
    attendance_candidates: list[Mapping[str, Any]],
    target_attendance: list[Mapping[str, Any]],
    class_by_id: Mapping[str, Mapping[str, Any]],
    dvd_by_class: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    incomplete = [row for row in attendance_candidates if _attendance_key(row) is None]
    complete_source = [row for row in attendance_candidates if _attendance_key(row) is not None]
    complete_target = [row for row in target_attendance if _attendance_key(row) is not None]
    cases = []
    counts = Counter()
    for row in incomplete:
        class_id = _sid(row.get("class_id"))
        case = _adjudicate_missing_key_case(
            row,
            dvd=dvd_by_class.get(class_id),
            source_complete=complete_source,
            target_complete=complete_target,
        )
        target = class_by_id.get(class_id) or {}
        case["class"] = _sid(target.get("class")) or "<unresolved>"
        counts[case["classification"]] += 1
        cases.append(case)

    deterministic = counts["DETERMINISTIC_UNIQUE_UNOCCUPIED_DVD_SLOT"]
    unresolved = len(incomplete) - deterministic
    return {
        "incomplete_candidates": len(incomplete),
        "deterministic_cases": deterministic,
        "unresolved_or_blocked_cases": unresolved,
        "classification_counts": dict(sorted(counts.items())),
        "cases": cases,
        "classification": (
            "NATURAL_KEY_ADJUDICATION_DETERMINISTIC"
            if incomplete and unresolved == 0
            else "NATURAL_KEY_ADJUDICATION_PARTIAL_OR_BLOCKED"
            if incomplete
            else "NO_INCOMPLETE_NATURAL_KEY"
        ),
        "write_authorized": False,
    }


def _audit_missing_parent(db, parent_id: str) -> dict[str, Any]:
    rows = list(
        db.audit_logs.find(
            {
                "collection": "learning_objects",
                "document_id": parent_id,
            },
            {
                "_id": 0,
                "action": 1,
                "timestamp": 1,
                "timestamp_utc": 1,
                "user_role": 1,
            },
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
        seen: dict[str, int] = {}
        cur = start
        step = 0
        while cur in edges:
            if cur in seen:
                cycle_nodes = []
                marker = cur
                while True:
                    cycle_nodes.append(marker)
                    marker = edges[marker]
                    if marker == cur:
                        break
                cycles.add(tuple(sorted(cycle_nodes)))
                break
            seen[cur] = step
            step += 1
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
            {
                "_id": 0,
                "id": 1,
                "course_id": 1,
                "class_id": 1,
                "date": 1,
                "mantenedora_id": 1,
                "deleted": 1,
                "status": 1,
            },
        )
    ) if parent_ids else []
    by_id = {_sid(row.get("id")): row for row in parents if _sid(row.get("id"))}

    counts = Counter()
    edges_in_candidate: dict[str, str] = {}
    missing_details = []
    for child in copied:
        child_id = _sid(child.get("id"))
        parent_id = _sid(child.get("copied_from_id"))
        parent = by_id.get(parent_id)
        if not parent:
            counts["PREEXISTING_PARENT_MISSING"] += 1
            detail = {
                "parent_fingerprint": _fp(parent_id),
                "child_fingerprint": _fp(child_id),
            }
            detail.update(_audit_missing_parent(db, parent_id))
            missing_details.append(detail)
            continue
        if parent_id in candidate_ids:
            counts["PARENT_IN_CANDIDATE_REMAP_PRESERVES_EDGE"] += 1
            if child_id:
                edges_in_candidate[child_id] = parent_id
        elif _sid(parent.get("course_id")) == legacy_id:
            counts["PARENT_LEGACY_OUTSIDE_CANDIDATE_WOULD_CROSS_IDENTITY"] += 1
        elif _sid(parent.get("course_id")) == current_id:
            counts["PARENT_ALREADY_CURRENT_IDENTITY"] += 1
        else:
            counts["PARENT_OTHER_IDENTITY"] += 1

    cycle_count = _detect_candidate_cycles(edges_in_candidate)
    new_cross_identity = (
        counts["PARENT_LEGACY_OUTSIDE_CANDIDATE_WOULD_CROSS_IDENTITY"]
        + counts["PARENT_OTHER_IDENTITY"]
    )
    preexisting_broken = counts["PREEXISTING_PARENT_MISSING"]
    return {
        "copied_candidate_documents": len(copied),
        "distinct_parent_ids": len(parent_ids),
        "resolved_parent_ids": len(by_id),
        "decision_counts": dict(sorted(counts.items())),
        "candidate_graph_cycles": cycle_count,
        "new_cross_identity_edges_if_all_candidates_remapped": new_cross_identity,
        "preexisting_missing_parent_edges": preexisting_broken,
        "missing_parent_details": missing_details,
        "classification": (
            "LINEAGE_BLOCKED_NEW_CROSS_IDENTITY_OR_CYCLE"
            if new_cross_identity or cycle_count
            else "LINEAGE_PRESERVED_WITH_PREEXISTING_BROKEN_REFERENCE"
            if preexisting_broken
            else "LINEAGE_PRESERVED_BY_SET_REMAP"
        ),
        "remap_would_create_new_lineage_break": bool(new_cross_identity or cycle_count),
        "preexisting_missing_parent_requires_separate_sanitation": bool(preexisting_broken),
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
        raise RuntimeError("ANA_LUCIA_F2_5_MONGO_URL_MISSING")

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
        dvd_by_class = context["dvd_by_class"]
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
            dvd_by_class=dvd_by_class,
            tenant_id=tenant_id,
        )
        natural_key = _natural_key_adjudication(
            attendance_candidates=attendance_candidates,
            target_attendance=target_attendance,
            class_by_id=class_by_id,
            dvd_by_class=dvd_by_class,
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
        lineage_new_break_clear = not lineage["remap_would_create_new_lineage_break"]
        drift_clear = all(value == 0 for value in drift.values())

        if tenant_clear and key_clear and lineage_new_break_clear:
            overall = (
                "ADJUDICATION_CLEAR_FOR_SEPARATE_WRITE_DESIGN_BUT_WRITE_NOT_AUTHORIZED"
                if drift_clear
                else "ADJUDICATION_STRUCTURALLY_CLEAR_WITH_BASELINE_DRIFT_REQUIRES_REVIEW"
            )
        else:
            overall = "ADJUDICATION_BLOCKED_REQUIRES_FURTHER_REVIEW_BEFORE_ANY_WRITE"

        return {
            "schema": "ANA_LUCIA_F2_5_ADJUDICATION_READ_ONLY_V1",
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
                "dvd_binding_count": len(dvd_by_class),
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
        "ANA_LUCIA_F2_5_JSON="
        + json.dumps(run_live_audit(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


if __name__ == "__main__":
    main()
