#!/usr/bin/env python3
"""ANA-LUCIA-F2.4 — preflight READ-ONLY de remapeamento cirúrgico.

A F2.3 comprovou uma cisão referencial: os oito vínculos atuais de Língua
Inglesa dos 6º/9º anos apontam para o componente de Anos Finais, enquanto
histórico de conteúdo/frequência foi persistido sob o componente de EJA Final.

Esta fase NÃO remapeia nada. Ela calcula o conjunto candidato e testa se um
futuro remapeamento localizado de ``course_id`` poderia colidir com documentos
já existentes na identidade correta, usando as mesmas chaves naturais auditadas
pelo P0-F3:

- learning_objects: class_id + date (após colapsar course_id);
- attendance: class_id + date + period(default=regular) + aula_numero.

Também verifica atribuição à professora, tenant, estado lógico, assignment_id,
duplicidade interna e linhagem copied_from_id. Qualquer colisão é apenas
classificada; valores pedagógicos, attendance.records e PII não são lidos.

Boundary obrigatório:
- MongoDB somente leitura;
- nenhum HTTP/login;
- nenhuma leitura de attendance.records;
- nenhuma coleção de estudantes/matrículas;
- nenhum valor de notas/frequência e nenhum texto pedagógico;
- nenhum ID técnico bruto emitido, somente fingerprints SHA-256 truncados;
- nenhuma mutação, backfill, merge, remapeamento, exclusão ou saneamento.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import os
import re
import unicodedata
from typing import Any, Iterable, Mapping

from pymongo import MongoClient

ACADEMIC_YEAR = int(os.environ.get("ANA_LUCIA_F2_4_ACADEMIC_YEAR", "2026"))
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

# Baseline exclusivamente para detectar drift desde F2.2/F2.3; nunca autoriza
# escrita e não torna a auditoria inválida se o estado tiver evoluído.
F2_BASELINE = {
    "learning_objects_teacher_attributed": 198,
    "attendance_teacher_attributed": 392,
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


def _learning_key(row: Mapping[str, Any]) -> tuple[str, str] | None:
    class_id = _sid(row.get("class_id"))
    day = _day(row.get("date"))
    if not class_id or not day:
        return None
    return class_id, day


def _attendance_key(row: Mapping[str, Any]) -> tuple[str, str, str, str] | None:
    class_id = _sid(row.get("class_id"))
    day = _day(row.get("date"))
    aula = _sid(row.get("aula_numero"))
    if not class_id or not day or not aula:
        return None
    return class_id, day, _sid(row.get("period")) or "regular", aula


def _key_hash(key: Any) -> str:
    raw = json.dumps(key, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _group_keys(
    rows: Iterable[Mapping[str, Any]],
    key_fn,
) -> tuple[dict[Any, list[Mapping[str, Any]]], int]:
    groups: dict[Any, list[Mapping[str, Any]]] = defaultdict(list)
    missing = 0
    for row in rows:
        key = key_fn(row)
        if key is None:
            missing += 1
        else:
            groups[key].append(row)
    return groups, missing


def classify_preflight(
    *,
    candidates: int,
    missing_natural_key: int,
    duplicate_source_keys: int,
    duplicate_target_keys: int,
    collision_keys: int,
    assignment_bound: int,
    tenant_missing: int,
    tenant_mismatch: int,
) -> str:
    if candidates <= 0:
        return "NO_CANDIDATES"
    if tenant_missing or tenant_mismatch:
        return "BLOCKED_TENANT_INTEGRITY"
    if assignment_bound:
        return "BLOCKED_ASSIGNMENT_BOUND_RECORDS"
    if missing_natural_key:
        return "BLOCKED_INCOMPLETE_NATURAL_KEY"
    if duplicate_source_keys or duplicate_target_keys:
        return "BLOCKED_INTERNAL_MULTIPLICITY"
    if collision_keys:
        return "BLOCKED_TARGET_COLLISIONS_REQUIRE_ADJUDICATION"
    return "STRUCTURALLY_SAFE_FOR_FUTURE_COURSE_ID_REMAP"


def _unique_teacher_identity(db) -> tuple[dict[str, Any], dict[str, Any]]:
    users = list(
        db.users.find(
            {"$or": [{"full_name": TEACHER_NAME}, {"name": TEACHER_NAME}]},
            {"_id": 0, "id": 1, "email": 1, "full_name": 1, "name": 1, "role": 1, "mantenedora_id": 1},
        ).limit(5)
    )
    users = [row for row in users if _norm(row.get("full_name") or row.get("name")) == _norm(TEACHER_NAME)]
    if len(users) != 1:
        raise RuntimeError(f"ANA_LUCIA_F2_4_TEACHER_USER_MATCHES:{len(users)}")
    if users[0].get("role") != "professor":
        raise RuntimeError(f"ANA_LUCIA_F2_4_TEACHER_ROLE:{users[0].get('role')}")
    user = users[0]

    clauses = [{"user_id": user["id"]}]
    if user.get("email"):
        clauses.append({"email": user["email"]})
    staff_rows = list(
        db.staff.find(
            {"$or": clauses},
            {"_id": 0, "id": 1, "user_id": 1, "email": 1, "mantenedora_id": 1},
        ).limit(5)
    )
    dedup = {_sid(row.get("id")): row for row in staff_rows if _sid(row.get("id"))}
    if len(dedup) != 1:
        raise RuntimeError(f"ANA_LUCIA_F2_4_STAFF_MATCHES:{len(dedup)}")
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
        if _sid(row.get("id")) and _sid(row.get("teacher_id")) == teacher_user_id
    }
    return teacher_ids, owner


def _resolve_context(db, user: Mapping[str, Any], staff: Mapping[str, Any]) -> dict[str, Any]:
    assignments = list(
        db.teacher_assignments.find(
            {
                "staff_id": staff["id"],
                "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
                "status": {"$in": list(ACTIVE_STATUSES)},
            },
            {"_id": 0, "id": 1, "class_id": 1, "course_id": 1, "school_id": 1, "mantenedora_id": 1},
        )
    )
    assignment_class_ids = sorted({_sid(row.get("class_id")) for row in assignments if _sid(row.get("class_id"))})
    classes = list(
        db.classes.find(
            {"id": {"$in": assignment_class_ids}},
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
    assignment_course_ids = sorted({_sid(row.get("course_id")) for row in assignments if _sid(row.get("course_id"))})
    assignment_courses = list(
        db.courses.find(
            {"id": {"$in": assignment_course_ids}},
            {"_id": 0, "id": 1, "name": 1, "nivel_ensino": 1, "mantenedora_id": 1},
        )
    )
    course_by_id = {_sid(row.get("id")): row for row in assignment_courses if _sid(row.get("id"))}

    targets: list[dict[str, Any]] = []
    current_ids: set[str] = set()
    tenant_ids: set[str] = set()
    for class_name in TARGET_CLASSES:
        candidates: list[dict[str, Any]] = []
        for row in assignments:
            klass = class_by_id.get(_sid(row.get("class_id"))) or {}
            course = course_by_id.get(_sid(row.get("course_id"))) or {}
            if _norm(klass.get("name")) != _norm(class_name):
                continue
            if _norm(course.get("name")) != _norm(COMPONENT_NAME):
                continue
            candidates.append(row)
        if len(candidates) != 1:
            raise RuntimeError(f"ANA_LUCIA_F2_4_TARGET_NOT_EXACT:{class_name}:{len(candidates)}")
        assignment = candidates[0]
        klass = class_by_id[_sid(assignment.get("class_id"))]
        school = school_by_id.get(_sid(klass.get("school_id"))) or {}
        tenant_id = _sid(klass.get("mantenedora_id") or school.get("mantenedora_id") or user.get("mantenedora_id"))
        current_id = _sid(assignment.get("course_id"))
        if not tenant_id or not current_id:
            raise RuntimeError(f"ANA_LUCIA_F2_4_TARGET_CONTEXT_MISSING:{class_name}")
        current_ids.add(current_id)
        tenant_ids.add(tenant_id)
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
            f"ANA_LUCIA_F2_4_NON_UNIQUE_CONTEXT:current={len(current_ids)}:tenant={len(tenant_ids)}"
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
            {"_id": 0, "id": 1, "name": 1, "nivel_ensino": 1, "mantenedora_id": 1, "created_at": 1},
        )
    )
    same_name = [row for row in same_name if _norm(row.get("name")) == _norm(COMPONENT_NAME)]
    current_matches = [
        row for row in same_name
        if _sid(row.get("id")) == current_id and _norm(row.get("nivel_ensino")) == _norm(CURRENT_LEVEL)
    ]
    if len(current_matches) != 1:
        raise RuntimeError(f"ANA_LUCIA_F2_4_CURRENT_COURSE_IDENTITY_INVALID:{len(current_matches)}")
    legacy_matches = [row for row in same_name if _norm(row.get("nivel_ensino")) == _norm(LEGACY_LEVEL)]
    if len(legacy_matches) != 1:
        raise RuntimeError(f"ANA_LUCIA_F2_4_LEGACY_COURSE_IDENTITY_INVALID:{len(legacy_matches)}")
    legacy_id = _sid(legacy_matches[0].get("id"))
    if legacy_id == current_id:
        raise RuntimeError("ANA_LUCIA_F2_4_IDENTITIES_COLLAPSED_UNEXPECTEDLY")

    return {
        "targets": targets,
        "tenant_id": tenant_id,
        "current_id": current_id,
        "legacy_id": legacy_id,
        "current_course": current_matches[0],
        "legacy_course": legacy_matches[0],
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


def _collection_preflight(
    *,
    collection: str,
    source_rows: list[Mapping[str, Any]],
    target_rows: list[Mapping[str, Any]],
    tenant_id: str,
    key_fn,
) -> dict[str, Any]:
    source_groups, source_missing_key = _group_keys(source_rows, key_fn)
    target_groups, target_missing_key = _group_keys(target_rows, key_fn)
    duplicate_source = {key: rows for key, rows in source_groups.items() if len(rows) > 1}
    duplicate_target = {key: rows for key, rows in target_groups.items() if len(rows) > 1}
    shared = sorted(set(source_groups) & set(target_groups), key=repr)

    assignment_bound = sum(1 for row in source_rows if _sid(row.get("assignment_id")))
    tenant_missing = sum(1 for row in source_rows if not _sid(row.get("mantenedora_id")))
    tenant_mismatch = sum(
        1 for row in source_rows
        if _sid(row.get("mantenedora_id")) and _sid(row.get("mantenedora_id")) != tenant_id
    )
    collision_source_documents = sum(len(source_groups[key]) for key in shared)
    collision_target_documents = sum(len(target_groups[key]) for key in shared)
    safe_source_documents = len(source_rows) - collision_source_documents

    classification = classify_preflight(
        candidates=len(source_rows),
        missing_natural_key=source_missing_key,
        duplicate_source_keys=len(duplicate_source),
        duplicate_target_keys=len(duplicate_target),
        collision_keys=len(shared),
        assignment_bound=assignment_bound,
        tenant_missing=tenant_missing,
        tenant_mismatch=tenant_mismatch,
    )
    return {
        "collection": collection,
        "natural_key": (
            ["class_id", "date"]
            if collection == "learning_objects"
            else ["class_id", "date", "period(default=regular)", "aula_numero"]
        ),
        "candidate_documents": len(source_rows),
        "target_existing_documents": len(target_rows),
        "source_missing_natural_key": source_missing_key,
        "target_missing_natural_key": target_missing_key,
        "duplicate_source_natural_keys": len(duplicate_source),
        "duplicate_target_natural_keys": len(duplicate_target),
        "collision_natural_keys": len(shared),
        "collision_source_documents": collision_source_documents,
        "collision_target_documents": collision_target_documents,
        "structurally_noncolliding_source_documents": safe_source_documents,
        "assignment_bound_candidate_documents": assignment_bound,
        "tenant_missing_candidate_documents": tenant_missing,
        "tenant_mismatch_candidate_documents": tenant_mismatch,
        "collision_key_fingerprints": [_key_hash(key) for key in shared[:50]],
        "duplicate_source_key_fingerprints": [_key_hash(key) for key in sorted(duplicate_source, key=repr)[:50]],
        "duplicate_target_key_fingerprints": [_key_hash(key) for key in sorted(duplicate_target, key=repr)[:50]],
        "classification": classification,
        "direct_remap_authorized": False,
    }


def _lineage_preflight(
    db,
    *,
    candidates: list[Mapping[str, Any]],
    candidate_ids: set[str],
    legacy_id: str,
    current_id: str,
) -> dict[str, Any]:
    parent_ids = sorted({_sid(row.get("copied_from_id")) for row in candidates if _sid(row.get("copied_from_id"))})
    if not parent_ids:
        return {
            "copied_candidates": 0,
            "resolved_parents": 0,
            "parent_in_candidate_set": 0,
            "parent_legacy_outside_candidate_set": 0,
            "parent_current_identity": 0,
            "parent_other_identity": 0,
            "parent_missing": 0,
            "post_remap_cross_identity_lineage_requires_review": False,
        }
    parents = list(
        db.learning_objects.find(
            {"id": {"$in": parent_ids}},
            {"_id": 0, "id": 1, "course_id": 1, "class_id": 1, "date": 1},
        )
    )
    by_id = {_sid(row.get("id")): row for row in parents if _sid(row.get("id"))}
    counts = Counter()
    for parent_id in parent_ids:
        parent = by_id.get(parent_id)
        if not parent:
            counts["parent_missing"] += 1
        elif parent_id in candidate_ids:
            counts["parent_in_candidate_set"] += 1
        elif _sid(parent.get("course_id")) == legacy_id:
            counts["parent_legacy_outside_candidate_set"] += 1
        elif _sid(parent.get("course_id")) == current_id:
            counts["parent_current_identity"] += 1
        else:
            counts["parent_other_identity"] += 1
    outside = counts["parent_legacy_outside_candidate_set"] + counts["parent_other_identity"]
    return {
        "copied_candidates": len(parent_ids),
        "resolved_parents": len(by_id),
        "parent_in_candidate_set": counts["parent_in_candidate_set"],
        "parent_legacy_outside_candidate_set": counts["parent_legacy_outside_candidate_set"],
        "parent_current_identity": counts["parent_current_identity"],
        "parent_other_identity": counts["parent_other_identity"],
        "parent_missing": counts["parent_missing"],
        "post_remap_cross_identity_lineage_requires_review": bool(outside or counts["parent_missing"]),
    }


def _per_class_summary(
    *,
    targets: Iterable[Mapping[str, Any]],
    source_learning: Iterable[Mapping[str, Any]],
    target_learning: Iterable[Mapping[str, Any]],
    source_attendance: Iterable[Mapping[str, Any]],
    target_attendance: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    sl = list(source_learning)
    tl = list(target_learning)
    sa = list(source_attendance)
    ta = list(target_attendance)
    rows: list[dict[str, Any]] = []
    for target in targets:
        class_id = _sid(target.get("class_id"))
        slc = [r for r in sl if _sid(r.get("class_id")) == class_id]
        tlc = [r for r in tl if _sid(r.get("class_id")) == class_id]
        sac = [r for r in sa if _sid(r.get("class_id")) == class_id]
        tac = [r for r in ta if _sid(r.get("class_id")) == class_id]
        sl_keys = {_learning_key(r) for r in slc if _learning_key(r) is not None}
        tl_keys = {_learning_key(r) for r in tlc if _learning_key(r) is not None}
        sa_keys = {_attendance_key(r) for r in sac if _attendance_key(r) is not None}
        ta_keys = {_attendance_key(r) for r in tac if _attendance_key(r) is not None}
        rows.append({
            "class": target.get("class"),
            "school": target.get("school"),
            "learning_candidate": len(slc),
            "learning_target_existing": len(tlc),
            "learning_collision_keys": len(sl_keys & tl_keys),
            "attendance_candidate": len(sac),
            "attendance_target_existing": len(tac),
            "attendance_collision_keys": len(sa_keys & ta_keys),
        })
    return rows


def run_live_audit() -> dict[str, Any]:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise RuntimeError("ANA_LUCIA_F2_4_MONGO_URL_MISSING")

    client = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)
    db = client[db_name]
    try:
        user, staff = _unique_teacher_identity(db)
        context = _resolve_context(db, user, staff)
        targets = context["targets"]
        tenant_id = context["tenant_id"]
        current_id = context["current_id"]
        legacy_id = context["legacy_id"]
        target_class_ids = {_sid(row.get("class_id")) for row in targets}

        teacher_user_id = _sid(user.get("id"))
        staff_id = _sid(staff.get("id"))
        actor_ids = {value for value in (teacher_user_id, staff_id) if value}
        teacher_assignment_ids, assignment_owner = _assignment_owners(db, teacher_user_id)

        raw_learning_source = _load_rows(
            db, "learning_objects", class_ids=target_class_ids, course_id=legacy_id
        )
        raw_attendance_source = _load_rows(
            db, "attendance", class_ids=target_class_ids, course_id=legacy_id
        )
        target_learning = [
            row for row in _load_rows(db, "learning_objects", class_ids=target_class_ids, course_id=current_id)
            if _active_like(row)
        ]
        target_attendance = [
            row for row in _load_rows(db, "attendance", class_ids=target_class_ids, course_id=current_id)
            if _active_like(row)
        ]

        learning_candidates, learning_excluded = _candidate_partition(
            raw_learning_source,
            actor_ids=actor_ids,
            teacher_assignment_ids=teacher_assignment_ids,
            assignment_owner=assignment_owner,
            teacher_user_id=teacher_user_id,
        )
        attendance_candidates, attendance_excluded = _candidate_partition(
            raw_attendance_source,
            actor_ids=actor_ids,
            teacher_assignment_ids=teacher_assignment_ids,
            assignment_owner=assignment_owner,
            teacher_user_id=teacher_user_id,
        )

        learning_preflight = _collection_preflight(
            collection="learning_objects",
            source_rows=learning_candidates,
            target_rows=target_learning,
            tenant_id=tenant_id,
            key_fn=_learning_key,
        )
        attendance_preflight = _collection_preflight(
            collection="attendance",
            source_rows=attendance_candidates,
            target_rows=target_attendance,
            tenant_id=tenant_id,
            key_fn=_attendance_key,
        )

        candidate_learning_ids = {_sid(row.get("id")) for row in learning_candidates if _sid(row.get("id"))}
        lineage = _lineage_preflight(
            db,
            candidates=learning_candidates,
            candidate_ids=candidate_learning_ids,
            legacy_id=legacy_id,
            current_id=current_id,
        )

        baseline_drift = {
            "learning_objects": len(learning_candidates) - F2_BASELINE["learning_objects_teacher_attributed"],
            "attendance": len(attendance_candidates) - F2_BASELINE["attendance_teacher_attributed"],
        }
        collection_states = {
            "learning_objects": learning_preflight["classification"],
            "attendance": attendance_preflight["classification"],
        }
        if all(value == "STRUCTURALLY_SAFE_FOR_FUTURE_COURSE_ID_REMAP" for value in collection_states.values()):
            overall = "PRECHECK_CLEAR_BUT_WRITE_NOT_AUTHORIZED"
        elif any(value.startswith("BLOCKED_") for value in collection_states.values()):
            overall = "PRECHECK_BLOCKED_REQUIRES_ADJUDICATION_BEFORE_ANY_WRITE"
        else:
            overall = "PRECHECK_REQUIRES_REVIEW"

        return {
            "schema": "ANA_LUCIA_F2_4_SURGICAL_REMAP_PREFLIGHT_READ_ONLY_V1",
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
            "automatic_remap_authorized": False,
            "target": {
                "teacher": TEACHER_NAME,
                "component": COMPONENT_NAME,
                "academic_year": ACADEMIC_YEAR,
                "target_pair_count": len(targets),
                "tenant_present": bool(tenant_id),
                "current_course_fingerprint": _fp(current_id),
                "legacy_course_fingerprint": _fp(legacy_id),
                "current_level": _sid(context["current_course"].get("nivel_ensino")),
                "legacy_level": _sid(context["legacy_course"].get("nivel_ensino")),
            },
            "candidate_scope": {
                "learning_objects_raw_legacy_target_classes_2026": len(raw_learning_source),
                "learning_objects_teacher_attributed_active_candidates": len(learning_candidates),
                "learning_objects_excluded": dict(sorted(learning_excluded.items())),
                "attendance_raw_legacy_target_classes_2026": len(raw_attendance_source),
                "attendance_teacher_attributed_active_candidates": len(attendance_candidates),
                "attendance_excluded": dict(sorted(attendance_excluded.items())),
                "baseline_drift_vs_f2_2": baseline_drift,
            },
            "collections": {
                "learning_objects": learning_preflight,
                "attendance": attendance_preflight,
            },
            "copy_lineage": lineage,
            "pairs": _per_class_summary(
                targets=targets,
                source_learning=learning_candidates,
                target_learning=target_learning,
                source_attendance=attendance_candidates,
                target_attendance=target_attendance,
            ),
            "safety_decision": {
                "write_authorized": False,
                "course_catalog_merge_authorized": False,
                "global_course_id_remap_authorized": False,
                "surgical_course_id_remap_authorized": False,
                "collision_payload_values_not_read": True,
                "collision_keys_are_structural_only": True,
                "non_attributed_legacy_documents_are_excluded_from_candidate_scope": True,
                "next_step_requires_human_adjudication_if_any_blocker": any(
                    value.startswith("BLOCKED_") for value in collection_states.values()
                ),
                "next_step_requires_separate_explicit_write_authorization_even_if_clear": True,
            },
        }
    finally:
        client.close()


def main() -> None:
    print(
        "ANA_LUCIA_F2_4_JSON="
        + json.dumps(run_live_audit(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


if __name__ == "__main__":
    main()
