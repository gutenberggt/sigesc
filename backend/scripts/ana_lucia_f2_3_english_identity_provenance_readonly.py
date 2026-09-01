#!/usr/bin/env python3
"""ANA-LUCIA-F2.3 — proveniência read-only das identidades de Língua Inglesa.

Parte da evidência F2.2 de que os oito pares 6º/9º ano possuem histórico de
Língua Inglesa sob uma identidade técnica diferente daquela hoje usada pelos
vínculos da professora. Esta fase não escolhe um vencedor pedagógico nem altera
referências: ela determina a proveniência estrutural das identidades, o papel
operacional atual de cada uma e a abrangência das referências persistentes.

Perguntas respondidas:
- quais identidades de ``courses`` são realmente relevantes para os oito pares;
- qual identidade está nos vínculos ativos atuais da professora;
- qual identidade concentra o legado 2026 encontrado pela F2.2;
- quando cada documento ``courses`` declara ter sido criado/alterado;
- quais coleções referenciam cada identidade e em qual escala;
- se há trilha de auditoria do próprio ``courses``;
- se objetos copiados apontam para ancestrais de outra identidade;
- se o par colide pela identidade nominal P0 (tenant + nome + nível de ensino).

Boundary obrigatório:
- MongoDB somente leitura;
- nenhum HTTP/login;
- nenhuma leitura de attendance.records;
- nenhuma coleção de estudantes/matrículas;
- nenhum valor de notas/frequência nem texto pedagógico;
- nenhum ID técnico bruto emitido: somente fingerprints SHA-256 truncados;
- audit_logs sem projetar old_value/new_value/description;
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

ACADEMIC_YEAR = int(os.environ.get("ANA_LUCIA_F2_3_ACADEMIC_YEAR", "2026"))
REFERENCE_DATE = os.environ.get("ANA_LUCIA_F2_3_REFERENCE_DATE", date.today().isoformat())[:10]
TEACHER_NAME = "Ana Lucia Faria Pinto"
COMPONENT_NAME = "Língua Inglesa"
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

# Espelha a SSoT backend/services/course_reference_integrity.py sem importar a
# aplicação durante o collector injetado por stdin no container de produção.
REFERENCE_SPECS: tuple[tuple[str, str, str], ...] = (
    ("teacher_assignments", "course_id", "alocação docente legada"),
    ("teacher_allocations", "course_id", "alocação docente operacional"),
    ("teacher_class_assignments", "component_id", "vínculo docente canônico/DVD"),
    ("class_schedules", "schedule_slots.course_id", "grade de horário"),
    ("grades", "course_id", "notas/conceitos"),
    ("attendance", "course_id", "frequência"),
    ("content_entries", "component_id", "registro de conteúdos"),
    ("learning_objects", "course_id", "objetos de conhecimento legados"),
    ("student_dependencies", "course_id", "dependências de estudos"),
)

SAFE_REF_FIELDS: tuple[str, ...] = (
    "id", "class_id", "school_id", "academic_year", "date", "staff_id",
    "teacher_id", "created_by", "updated_by", "recorded_by", "status",
    "deleted", "valid_from", "valid_until", "created_at", "updated_at",
)


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


def _row_in_year(row: Mapping[str, Any]) -> bool:
    if _sid(row.get("academic_year")) == str(ACADEMIC_YEAR):
        return True
    day = _day(row.get("date"))
    return bool(day and day.startswith(f"{ACADEMIC_YEAR}-"))


def _active_like(row: Mapping[str, Any]) -> bool:
    if row.get("deleted") is True:
        return False
    status = _norm(row.get("status"))
    if status in {"inativo", "inactive", "excluido", "excluida", "deleted", "cancelado", "cancelada"}:
        return False
    valid_from = _day(row.get("valid_from"))
    valid_until = _day(row.get("valid_until"))
    if valid_from and valid_from > REFERENCE_DATE:
        return False
    if valid_until and valid_until < REFERENCE_DATE:
        return False
    return True


def _timestamp_candidates(row: Mapping[str, Any]) -> list[str]:
    out: list[str] = []
    for field in ("date", "created_at", "updated_at", "valid_from", "valid_until"):
        value = _sid(row.get(field))
        if value:
            out.append(value)
    return out


def _teacher_actor(row: Mapping[str, Any], *, user_id: str, staff_id: str) -> bool:
    if _sid(row.get("staff_id")) == staff_id and staff_id:
        return True
    return any(
        _sid(row.get(field)) == user_id and user_id
        for field in ("teacher_id", "created_by", "updated_by", "recorded_by")
    )


def classify_split(
    *,
    target_binding_current: int,
    target_binding_legacy: int,
    current_content_2026: int,
    legacy_content_2026: int,
    current_attendance_2026: int,
    legacy_attendance_2026: int,
) -> str:
    if target_binding_current and not target_binding_legacy and (
        legacy_content_2026 > current_content_2026 or legacy_attendance_2026 > current_attendance_2026
    ):
        return "CURRENT_BINDING_VS_LEGACY_DATA_IDENTITY_SPLIT"
    if target_binding_current and target_binding_legacy:
        return "MIXED_ACTIVE_BINDINGS_REQUIRE_REVIEW"
    if not target_binding_current and not target_binding_legacy:
        return "NO_ACTIVE_TARGET_BINDING_REQUIRE_REVIEW"
    return "IDENTITY_SPLIT_NOT_PROVEN"


def classify_creation_order(current_created_at: Any, legacy_created_at: Any) -> str:
    current = _sid(current_created_at)
    legacy = _sid(legacy_created_at)
    if not current or not legacy:
        return "COURSE_CREATION_ORDER_UNKNOWN"
    if current == legacy:
        return "COURSE_CREATION_TIMESTAMPS_EQUAL"
    return "CURRENT_ID_CREATED_AFTER_LEGACY_ID" if current > legacy else "CURRENT_ID_CREATED_BEFORE_LEGACY_ID"


def classify_p0_identity(current: Mapping[str, Any], legacy: Mapping[str, Any]) -> str:
    if _norm(current.get("name")) != _norm(legacy.get("name")):
        return "DISPLAY_NAME_DIFFERS"
    same_tenant = _sid(current.get("mantenedora_id")) == _sid(legacy.get("mantenedora_id"))
    same_level = _norm(current.get("nivel_ensino")) == _norm(legacy.get("nivel_ensino"))
    if same_tenant and same_level:
        return "P0_DUPLICATE_IDENTITY_KEY_COLLISION"
    if same_tenant:
        return "SAME_TENANT_AND_NAME_DIFFERENT_LEVEL_IDENTITY"
    return "SAME_NAME_DIFFERENT_TENANT_IDENTITY"


def _unique_teacher_identity(db) -> tuple[dict[str, Any], dict[str, Any]]:
    users = list(
        db.users.find(
            {"$or": [{"full_name": TEACHER_NAME}, {"name": TEACHER_NAME}]},
            {"_id": 0, "id": 1, "email": 1, "full_name": 1, "name": 1, "role": 1, "mantenedora_id": 1},
        ).limit(5)
    )
    users = [row for row in users if _norm(row.get("full_name") or row.get("name")) == _norm(TEACHER_NAME)]
    if len(users) != 1:
        raise RuntimeError(f"ANA_LUCIA_F2_3_TEACHER_USER_MATCHES:{len(users)}")
    user = users[0]
    if user.get("role") != "professor":
        raise RuntimeError(f"ANA_LUCIA_F2_3_TEACHER_ROLE:{user.get('role')}")

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
        raise RuntimeError(f"ANA_LUCIA_F2_3_STAFF_MATCHES:{len(dedup)}")
    return user, next(iter(dedup.values()))


def _load_course_map(db) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    projection = {
        "_id": 0, "id": 1, "name": 1, "nivel_ensino": 1, "mantenedora_id": 1,
        "status": 1, "active": 1, "created_at": 1, "updated_at": 1, "created_by": 1,
    }
    rows = list(db.courses.find({}, projection))
    return ({_sid(row.get("id")): row for row in rows if _sid(row.get("id"))}, rows)


def _resolve_target_context(
    db,
    *,
    user: Mapping[str, Any],
    staff: Mapping[str, Any],
    course_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], str, str]:
    assignments = list(
        db.teacher_assignments.find(
            {
                "staff_id": staff["id"],
                "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
                "status": {"$in": list(ACTIVE_STATUSES)},
            },
            {"_id": 0, "id": 1, "class_id": 1, "course_id": 1, "school_id": 1, "mantenedora_id": 1, "status": 1},
        )
    )
    class_ids = sorted({_sid(row.get("class_id")) for row in assignments if _sid(row.get("class_id"))})
    classes = list(
        db.classes.find(
            {"id": {"$in": class_ids}},
            {"_id": 0, "id": 1, "name": 1, "school_id": 1, "mantenedora_id": 1, "academic_year": 1, "course_ids": 1},
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

    targets: list[dict[str, Any]] = []
    current_ids: set[str] = set()
    tenants: set[str] = set()
    for target_name in TARGET_CLASSES:
        candidates = []
        for row in assignments:
            class_doc = class_by_id.get(_sid(row.get("class_id"))) or {}
            course_doc = course_by_id.get(_sid(row.get("course_id"))) or {}
            if _norm(class_doc.get("name")) != _norm(target_name):
                continue
            if _norm(course_doc.get("name")) != _norm(COMPONENT_NAME):
                continue
            candidates.append(row)
        if len(candidates) != 1:
            raise RuntimeError(f"ANA_LUCIA_F2_3_TARGET_BINDING_NOT_EXACT:{target_name}:{len(candidates)}")
        assignment = candidates[0]
        class_doc = class_by_id[_sid(assignment.get("class_id"))]
        school = school_by_id.get(_sid(class_doc.get("school_id"))) or {}
        tenant_id = _sid(class_doc.get("mantenedora_id") or school.get("mantenedora_id") or user.get("mantenedora_id"))
        if not tenant_id:
            raise RuntimeError(f"ANA_LUCIA_F2_3_TARGET_TENANT_MISSING:{target_name}")
        current_id = _sid(assignment.get("course_id"))
        current_ids.add(current_id)
        tenants.add(tenant_id)
        targets.append(
            {
                "class": target_name,
                "school": _sid(school.get("name")),
                "class_id": _sid(class_doc.get("id")),
                "school_id": _sid(class_doc.get("school_id")),
                "tenant_id": tenant_id,
                "current_course_id": current_id,
                "class_course_ids": [_sid(v) for v in class_doc.get("course_ids") or [] if _sid(v)],
            }
        )
    if len(current_ids) != 1:
        raise RuntimeError(f"ANA_LUCIA_F2_3_CURRENT_ID_NOT_UNIQUE:{len(current_ids)}")
    if len(tenants) != 1:
        raise RuntimeError(f"ANA_LUCIA_F2_3_TARGET_TENANT_NOT_UNIQUE:{len(tenants)}")
    return targets, next(iter(current_ids)), next(iter(tenants))


def _english_ids_for_tenant(course_rows: Iterable[Mapping[str, Any]], tenant_id: str) -> set[str]:
    ids = set()
    for row in course_rows:
        if _norm(row.get("name")) != _norm(COMPONENT_NAME):
            continue
        row_tenant = _sid(row.get("mantenedora_id"))
        if row_tenant and row_tenant != tenant_id:
            continue
        if _sid(row.get("id")):
            ids.add(_sid(row.get("id")))
    return ids


def _discover_relevant_ids(
    db,
    *,
    targets: Iterable[Mapping[str, Any]],
    current_id: str,
    english_ids: set[str],
    user_id: str,
    staff_id: str,
) -> tuple[set[str], dict[str, dict[str, int]]]:
    class_ids = sorted({_sid(row.get("class_id")) for row in targets})
    relevant = {current_id}
    counts: dict[str, Counter[str]] = defaultdict(Counter)

    sources = (
        ("learning_objects", "course_id", {"_id": 0, "course_id": 1, "class_id": 1, "academic_year": 1, "date": 1, "teacher_id": 1, "created_by": 1, "updated_by": 1, "recorded_by": 1}),
        ("attendance", "course_id", {"_id": 0, "course_id": 1, "class_id": 1, "academic_year": 1, "date": 1, "teacher_id": 1, "created_by": 1, "updated_by": 1}),
        ("content_entries", "component_id", {"_id": 0, "component_id": 1, "class_id": 1, "academic_year": 1, "date": 1, "teacher_id": 1, "created_by": 1, "updated_by": 1, "recorded_by": 1, "deleted": 1}),
    )
    for collection_name, field, projection in sources:
        query = {
            "$and": [
                {"class_id": {"$in": class_ids}},
                {field: {"$in": sorted(english_ids)}},
                _year_scope(),
            ]
        }
        for row in db[collection_name].find(query, projection):
            if row.get("deleted") is True:
                continue
            course_id = _sid(row.get(field))
            if not course_id:
                continue
            if _teacher_actor(row, user_id=user_id, staff_id=staff_id):
                relevant.add(course_id)
                counts[course_id][collection_name] += 1
    return relevant, {key: dict(value) for key, value in counts.items()}


def _reference_rows(db, collection_name: str, field: str, course_id: str) -> list[dict[str, Any]]:
    root = field.split(".", 1)[0]
    projection = {"_id": 0, root: 1, **{name: 1 for name in SAFE_REF_FIELDS}}
    return list(db[collection_name].find({field: course_id}, projection))


def _reference_summary(
    db,
    *,
    course_id: str,
    target_class_ids: set[str],
    target_school_ids: set[str],
    user_id: str,
    staff_id: str,
) -> tuple[dict[str, Any], set[str], set[str]]:
    by_collection: dict[str, Any] = {}
    all_classes: set[str] = set()
    all_schools: set[str] = set()
    for collection_name, field, _label in REFERENCE_SPECS:
        rows = _reference_rows(db, collection_name, field, course_id)
        year_rows = [row for row in rows if _row_in_year(row)]
        active_rows = [row for row in year_rows if _active_like(row)]
        class_ids = {_sid(row.get("class_id")) for row in year_rows if _sid(row.get("class_id"))}
        school_ids = {_sid(row.get("school_id")) for row in year_rows if _sid(row.get("school_id"))}
        all_classes.update(class_ids)
        all_schools.update(school_ids)
        timestamps = sorted(ts for row in rows for ts in _timestamp_candidates(row))
        by_collection[collection_name] = {
            "total_documents": len(rows),
            "documents_2026": len(year_rows),
            "active_like_2026": len(active_rows),
            "teacher_attributed_2026": sum(
                1 for row in year_rows if _teacher_actor(row, user_id=user_id, staff_id=staff_id)
            ),
            "target_classes_2026": sum(_sid(row.get("class_id")) in target_class_ids for row in year_rows),
            "target_schools_2026": sum(_sid(row.get("school_id")) in target_school_ids for row in year_rows),
            "distinct_class_count_2026": len(class_ids),
            "first_seen_metadata": timestamps[0] if timestamps else None,
            "last_seen_metadata": timestamps[-1] if timestamps else None,
        }
    return by_collection, all_classes, all_schools


def _class_matrix_summary(db, *, course_id: str, target_class_ids: set[str]) -> dict[str, Any]:
    rows = list(
        db.classes.find(
            {"course_ids": course_id},
            {"_id": 0, "id": 1, "school_id": 1, "academic_year": 1, "mantenedora_id": 1},
        )
    )
    target_year = [row for row in rows if _sid(row.get("academic_year")) == str(ACADEMIC_YEAR)]
    return {
        "total_classes": len(rows),
        "classes_2026": len(target_year),
        "target_classes_2026": sum(_sid(row.get("id")) in target_class_ids for row in target_year),
    }


def _course_audit_summary(db, *, course_id: str) -> dict[str, Any]:
    # old/new podem participar apenas do predicado Mongo; não são projetados nem
    # materializados pelo processo Python.
    query = {
        "collection": "courses",
        "$or": [
            {"document_id": course_id},
            {"old_value.id": course_id},
            {"new_value.id": course_id},
            {"extra_data.consolidated.removed_ids": course_id},
            {"extra_data.consolidated.kept_id": course_id},
        ],
    }
    projection = {
        "_id": 0, "action": 1, "document_id": 1, "timestamp": 1,
        "timestamp_utc": 1, "user_role": 1,
    }
    rows = list(db.audit_logs.find(query, projection).sort("timestamp", 1).limit(500))
    timestamps = [
        _sid(row.get("timestamp_utc") or row.get("timestamp"))
        for row in rows if _sid(row.get("timestamp_utc") or row.get("timestamp"))
    ]
    return {
        "event_count": len(rows),
        "action_counts": dict(sorted(Counter(_sid(row.get("action")) or "<unknown>" for row in rows).items())),
        "first_event_at": min(timestamps) if timestamps else None,
        "last_event_at": max(timestamps) if timestamps else None,
        "actor_role_counts": dict(sorted(Counter(_sid(row.get("user_role")) or "<unknown>" for row in rows).items())),
    }


def _copy_lineage_summary(
    db,
    *,
    course_id: str,
    target_class_ids: set[str],
    course_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    rows = list(
        db.learning_objects.find(
            {
                "$and": [
                    {"class_id": {"$in": sorted(target_class_ids)}},
                    {"course_id": course_id},
                    _year_scope(),
                ]
            },
            {"_id": 0, "id": 1, "course_id": 1, "class_id": 1, "copied_from_id": 1, "date": 1},
        )
    )
    parent_ids = sorted({_sid(row.get("copied_from_id")) for row in rows if _sid(row.get("copied_from_id"))})
    parents = []
    if parent_ids:
        parents = list(
            db.learning_objects.find(
                {"id": {"$in": parent_ids}},
                {"_id": 0, "id": 1, "course_id": 1, "class_id": 1, "date": 1},
            )
        )
    parent_course_counts = Counter()
    for row in parents:
        parent_course_id = _sid(row.get("course_id"))
        if not parent_course_id:
            parent_course_counts["<missing>"] += 1
            continue
        course = course_by_id.get(parent_course_id) or {}
        label = f"{_sid(course.get('name')) or '<unknown>'}:{_fp(parent_course_id)}"
        parent_course_counts[label] += 1
    return {
        "target_learning_objects_2026": len(rows),
        "copied_records_2026": len(parent_ids),
        "resolved_parent_records": len(parents),
        "parent_course_identity_counts": dict(sorted(parent_course_counts.items())),
    }


def _identity_public(
    *,
    role: str,
    course_id: str,
    course: Mapping[str, Any],
    references: Mapping[str, Any],
    class_matrix: Mapping[str, Any],
    audit: Mapping[str, Any],
    copy_lineage: Mapping[str, Any],
    global_class_count: int,
    global_school_count: int,
) -> dict[str, Any]:
    return {
        "role": role,
        "course_fingerprint": _fp(course_id),
        "name": _sid(course.get("name")),
        "nivel_ensino": _sid(course.get("nivel_ensino")) or None,
        "tenant_present": bool(_sid(course.get("mantenedora_id"))),
        "status": course.get("status"),
        "active": course.get("active"),
        "created_at": _sid(course.get("created_at")) or None,
        "updated_at": _sid(course.get("updated_at")) or None,
        "references": references,
        "class_matrix": dict(class_matrix),
        "course_audit": dict(audit),
        "copy_lineage": dict(copy_lineage),
        "global_distinct_class_count_2026": global_class_count,
        "global_distinct_school_count_2026": global_school_count,
    }


def run_live_audit() -> dict[str, Any]:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise RuntimeError("ANA_LUCIA_F2_3_MONGO_URL_MISSING")

    client = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)
    db = client[db_name]
    try:
        user, staff = _unique_teacher_identity(db)
        user_id = _sid(user.get("id"))
        staff_id = _sid(staff.get("id"))
        course_by_id, course_rows = _load_course_map(db)
        targets, current_id, tenant_id = _resolve_target_context(
            db, user=user, staff=staff, course_by_id=course_by_id
        )
        english_ids = _english_ids_for_tenant(course_rows, tenant_id)
        if current_id not in english_ids:
            raise RuntimeError("ANA_LUCIA_F2_3_CURRENT_ID_NOT_ENGLISH")

        relevant_ids, discovered_counts = _discover_relevant_ids(
            db,
            targets=targets,
            current_id=current_id,
            english_ids=english_ids,
            user_id=user_id,
            staff_id=staff_id,
        )
        if len(relevant_ids) != 2:
            raise RuntimeError(
                f"ANA_LUCIA_F2_3_RELEVANT_ID_COUNT:{len(relevant_ids)}:english_catalog={len(english_ids)}"
            )
        legacy_ids = relevant_ids - {current_id}
        if len(legacy_ids) != 1:
            raise RuntimeError(f"ANA_LUCIA_F2_3_LEGACY_ID_COUNT:{len(legacy_ids)}")
        legacy_id = next(iter(legacy_ids))
        current_course = course_by_id.get(current_id)
        legacy_course = course_by_id.get(legacy_id)
        if not current_course or not legacy_course:
            raise RuntimeError("ANA_LUCIA_F2_3_RELEVANT_COURSE_DOCUMENT_MISSING")

        target_class_ids = {_sid(row.get("class_id")) for row in targets}
        target_school_ids = {_sid(row.get("school_id")) for row in targets}

        identity_payloads: dict[str, dict[str, Any]] = {}
        raw_ref_classes: dict[str, set[str]] = {}
        raw_ref_schools: dict[str, set[str]] = {}
        for role, course_id, course in (
            ("CURRENT_BINDING_ID", current_id, current_course),
            ("LEGACY_DATA_ID", legacy_id, legacy_course),
        ):
            refs, ref_classes, ref_schools = _reference_summary(
                db,
                course_id=course_id,
                target_class_ids=target_class_ids,
                target_school_ids=target_school_ids,
                user_id=user_id,
                staff_id=staff_id,
            )
            raw_ref_classes[course_id] = ref_classes
            raw_ref_schools[course_id] = ref_schools
            # Converte classes referenciadas em escolas sem expor IDs.
            if ref_classes:
                rows = list(
                    db.classes.find(
                        {"id": {"$in": sorted(ref_classes)}},
                        {"_id": 0, "id": 1, "school_id": 1, "academic_year": 1},
                    )
                )
                ref_schools.update({_sid(row.get("school_id")) for row in rows if _sid(row.get("school_id"))})
            identity_payloads[course_id] = _identity_public(
                role=role,
                course_id=course_id,
                course=course,
                references=refs,
                class_matrix=_class_matrix_summary(db, course_id=course_id, target_class_ids=target_class_ids),
                audit=_course_audit_summary(db, course_id=course_id),
                copy_lineage=_copy_lineage_summary(
                    db,
                    course_id=course_id,
                    target_class_ids=target_class_ids,
                    course_by_id=course_by_id,
                ),
                global_class_count=len(ref_classes),
                global_school_count=len(ref_schools),
            )

        current_refs = identity_payloads[current_id]["references"]
        legacy_refs = identity_payloads[legacy_id]["references"]
        current_target_bindings = int((current_refs.get("teacher_assignments") or {}).get("target_classes_2026") or 0)
        legacy_target_bindings = int((legacy_refs.get("teacher_assignments") or {}).get("target_classes_2026") or 0)
        current_content = int((current_refs.get("learning_objects") or {}).get("target_classes_2026") or 0)
        legacy_content = int((legacy_refs.get("learning_objects") or {}).get("target_classes_2026") or 0)
        current_attendance = int((current_refs.get("attendance") or {}).get("target_classes_2026") or 0)
        legacy_attendance = int((legacy_refs.get("attendance") or {}).get("target_classes_2026") or 0)

        split = classify_split(
            target_binding_current=current_target_bindings,
            target_binding_legacy=legacy_target_bindings,
            current_content_2026=current_content,
            legacy_content_2026=legacy_content,
            current_attendance_2026=current_attendance,
            legacy_attendance_2026=legacy_attendance,
        )
        p0_identity = classify_p0_identity(current_course, legacy_course)
        creation_order = classify_creation_order(current_course.get("created_at"), legacy_course.get("created_at"))

        current_dvd = int((current_refs.get("teacher_class_assignments") or {}).get("target_classes_2026") or 0)
        legacy_dvd = int((legacy_refs.get("teacher_class_assignments") or {}).get("target_classes_2026") or 0)
        current_alloc = int((current_refs.get("teacher_allocations") or {}).get("target_classes_2026") or 0)
        legacy_alloc = int((legacy_refs.get("teacher_allocations") or {}).get("target_classes_2026") or 0)
        current_matrix = int(identity_payloads[current_id]["class_matrix"].get("target_classes_2026") or 0)
        legacy_matrix = int(identity_payloads[legacy_id]["class_matrix"].get("target_classes_2026") or 0)

        operational_authority = {
            "teacher_assignments_target_current": current_target_bindings,
            "teacher_assignments_target_legacy": legacy_target_bindings,
            "teacher_class_assignments_target_current": current_dvd,
            "teacher_class_assignments_target_legacy": legacy_dvd,
            "teacher_allocations_target_current": current_alloc,
            "teacher_allocations_target_legacy": legacy_alloc,
            "class_matrix_target_current": current_matrix,
            "class_matrix_target_legacy": legacy_matrix,
        }
        if current_target_bindings == len(TARGET_CLASSES) and legacy_target_bindings == 0:
            current_authority = "CURRENT_BINDING_ID_CONFIRMED_BY_ACTIVE_LEGACY_ASSIGNMENTS"
        else:
            current_authority = "CURRENT_OPERATIONAL_AUTHORITY_REQUIRES_REVIEW"

        catalog_same_name = [
            {
                "course_fingerprint": _fp(row.get("id")),
                "nivel_ensino": _sid(row.get("nivel_ensino")) or None,
                "created_at": _sid(row.get("created_at")) or None,
                "updated_at": _sid(row.get("updated_at")) or None,
                "is_relevant_to_target": _sid(row.get("id")) in relevant_ids,
            }
            for row in course_rows
            if _norm(row.get("name")) == _norm(COMPONENT_NAME)
            and (not _sid(row.get("mantenedora_id")) or _sid(row.get("mantenedora_id")) == tenant_id)
        ]
        catalog_same_name.sort(key=lambda row: (row.get("nivel_ensino") or "", row.get("created_at") or "", row.get("course_fingerprint") or ""))

        pair_table = []
        for target in targets:
            class_id = _sid(target.get("class_id"))
            pair_table.append(
                {
                    "class": target.get("class"),
                    "school": target.get("school"),
                    "current_binding_fingerprint": _fp(target.get("current_course_id")),
                    "class_matrix_contains_current": current_id in set(target.get("class_course_ids") or []),
                    "class_matrix_contains_legacy": legacy_id in set(target.get("class_course_ids") or []),
                    "learning_objects_current_2026": db.learning_objects.count_documents({"$and": [{"class_id": class_id, "course_id": current_id}, _year_scope()]}),
                    "learning_objects_legacy_2026": db.learning_objects.count_documents({"$and": [{"class_id": class_id, "course_id": legacy_id}, _year_scope()]}),
                    "attendance_current_2026": db.attendance.count_documents({"$and": [{"class_id": class_id, "course_id": current_id}, _year_scope()]}),
                    "attendance_legacy_2026": db.attendance.count_documents({"$and": [{"class_id": class_id, "course_id": legacy_id}, _year_scope()]}),
                }
            )

        return {
            "schema": "ANA_LUCIA_F2_3_ENGLISH_IDENTITY_PROVENANCE_READ_ONLY_V1",
            "status": "PASS",
            "classification": split,
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
            "audit_old_new_values_projected": False,
            "automatic_merge_authorized": False,
            "automatic_remap_authorized": False,
            "target": {
                "teacher": TEACHER_NAME,
                "component": COMPONENT_NAME,
                "academic_year": ACADEMIC_YEAR,
                "reference_date": REFERENCE_DATE,
                "target_pair_count": len(TARGET_CLASSES),
                "relevant_identity_count": len(relevant_ids),
                "same_name_catalog_identity_count": len(catalog_same_name),
            },
            "provenance": {
                "p0_identity_classification": p0_identity,
                "course_creation_order": creation_order,
                "current_operational_authority": current_authority,
                "operational_authority_evidence": operational_authority,
                "current_binding_fingerprint": _fp(current_id),
                "legacy_data_fingerprint": _fp(legacy_id),
                "discovered_target_teacher_metadata_counts": {
                    _fp(cid) or "<missing>": discovered_counts.get(cid, {})
                    for cid in sorted(relevant_ids)
                },
            },
            "identities": [identity_payloads[current_id], identity_payloads[legacy_id]],
            "same_name_catalog": catalog_same_name,
            "pairs": pair_table,
            "safety_decision": {
                "historical_data_presence_is_evidence_not_merge_authorization": True,
                "created_at_order_is_evidence_not_authority": True,
                "current_binding_is_operational_authority_not_semantic_merge_authorization": True,
                "next_step_requires_read_only_collision_preflight_before_any_write": True,
            },
        }
    finally:
        client.close()


def main() -> None:
    print(
        "ANA_LUCIA_F2_3_JSON="
        + json.dumps(run_live_audit(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


if __name__ == "__main__":
    main()
