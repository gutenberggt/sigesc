#!/usr/bin/env python3
"""F1 — auditoria comparativa READ-ONLY de registros docentes não exibidos.

Casos-alvo, ano letivo 2026:
- Ana Lucia Faria Pinto Tristão / E M E I E F Monsenhor Augusto Dias de Brito;
- Luiz Gomes dos Santos / E M E I E F Jose Pereira Barbosa.

Objetivo: distinguir ausência real de registros, drift de assignment e cisão de
identidade de componente (mesmo nome, course_id/component_id diferente), sem
qualquer mutação de produção.

Privacidade / boundary:
- não lê attendance.records;
- não lê estudantes, matrículas, notas ou texto pedagógico;
- não emite IDs técnicos brutos; somente fingerprints SHA-256 truncados;
- somente find/find_one/to_list em MongoDB;
- nenhuma escrita, backfill, migração ou remapeamento.
"""
from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
import os
import re
import unicodedata
from typing import Any, Iterable, Mapping

ACADEMIC_YEAR = int(os.environ.get("TEACHER_VISIBILITY_F1_ACADEMIC_YEAR", "2026"))
REFERENCE_DATE = os.environ.get("TEACHER_VISIBILITY_F1_REFERENCE_DATE", date.today().isoformat())[:10]
ACTIVE_LEGACY_STATUSES = {"ativo", "active"}

CASES: tuple[dict[str, Any], ...] = (
    {
        "key": "ANA_LUCIA",
        "teacher": "Ana Lucia Faria Pinto Tristão",
        "teacher_aliases": ("Ana Lucia Faria Pinto Tristão", "Ana Lucia Faria Pinto"),
        "school": "E M E I E F Monsenhor Augusto Dias de Brito",
        "pairs": (
            ("6º ANO A", "Língua Inglesa"),
            ("6º ANO B", "Língua Inglesa"),
            ("6º ANO C", "Língua Inglesa"),
            ("6º ANO D", "Língua Inglesa"),
            ("9º ANO A", "Língua Inglesa"),
            ("9º ANO B", "Língua Inglesa"),
            ("9º ANO C", "Língua Inglesa"),
            ("9º ANO D", "Língua Inglesa"),
            ("3ª ETAPA", "Língua Inglesa"),
            ("4ª ETAPA", "Língua Inglesa"),
            ("6º ANO C", "Literatura e Redação"),
            ("6º ANO D", "Literatura e Redação"),
            ("7º ANO B", "Literatura e Redação"),
            ("7º ANO C", "Literatura e Redação"),
            ("9º ANO C", "Literatura e Redação"),
            ("7º ANO A", "Estudos Amazônicos"),
            ("8º ANO C", "Estudos Amazônicos"),
        ),
    },
    {
        "key": "LUIZ_GOMES",
        "teacher": "Luiz Gomes dos Santos",
        "teacher_aliases": ("Luiz Gomes dos Santos",),
        "school": "E M E I E F Jose Pereira Barbosa",
        "pairs": (
            ("6º ANO A", "Matemática"),
            ("6º ANO B", "Matemática"),
            ("7º ANO A", "Matemática"),
            ("7º ANO B", "Matemática"),
            ("8º ANO A", "Matemática"),
            ("9º ANO A", "Matemática"),
        ),
    },
)


def _sid(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _norm(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", _sid(value))
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = raw.casefold().replace("º", "o").replace("ª", "a")
    return re.sub(r"\s+", " ", raw).strip()


def _day(value: Any) -> str:
    return _sid(value)[:10]


def _fp(value: Any) -> str | None:
    raw = _sid(value)
    if not raw:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _year_scope() -> dict[str, Any]:
    return {
        "$or": [
            {"academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}},
            {"date": {"$gte": f"{ACADEMIC_YEAR}-01-01", "$lte": f"{ACADEMIC_YEAR}-12-31"}},
        ]
    }


def _date_summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    values = list(rows)
    dates = sorted({_day(row.get("date")) for row in values if _day(row.get("date"))})
    return {
        "documents": len(values),
        "distinct_dates": len(dates),
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
    }


def _academic_year_types(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    result: Counter[str] = Counter()
    for row in rows:
        value = row.get("academic_year")
        if value is None:
            result["missing"] += 1
        elif isinstance(value, int):
            result["int"] += 1
        elif isinstance(value, str):
            result["str"] += 1
        else:
            result[type(value).__name__] += 1
    return dict(sorted(result.items()))


def _attendance_shape(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    result: Counter[str] = Counter()
    for row in rows:
        if _sid(row.get("aula_numero")):
            result["with_aula_numero"] += 1
        else:
            result["without_aula_numero"] += 1
        if row.get("number_of_classes") not in (None, ""):
            result["with_number_of_classes"] += 1
    return dict(sorted(result.items()))


def _is_dvd_current(row: Mapping[str, Any]) -> bool:
    if row.get("deleted") is True:
        return False
    settings = row.get("diary_settings") or {}
    if settings.get("enabled") is not True:
        return False
    valid_from = _day(row.get("valid_from"))
    valid_until = _day(row.get("valid_until"))
    if not valid_from or valid_from > REFERENCE_DATE:
        return False
    return not valid_until or valid_until >= REFERENCE_DATE


def _record_course_id(row: Mapping[str, Any]) -> str:
    return _sid(row.get("course_id") or row.get("component_id"))


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
) -> bool:
    if _teacher_actor(row, actor_ids):
        return True
    assignment_id = _sid(row.get("assignment_id"))
    return bool(assignment_id and assignment_id in teacher_assignment_ids)


def _partition_assignment_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    current_assignment_ids: set[str],
    same_teacher_assignment_ids: set[str],
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        assignment_id = _sid(row.get("assignment_id"))
        if not assignment_id:
            counts["without_assignment"] += 1
        elif assignment_id in current_assignment_ids:
            counts["current_assignment"] += 1
        elif assignment_id in same_teacher_assignment_ids:
            counts["historical_same_teacher_assignment"] += 1
        else:
            counts["foreign_or_unknown_assignment"] += 1
    return {
        key: counts.get(key, 0)
        for key in (
            "current_assignment",
            "historical_same_teacher_assignment",
            "without_assignment",
            "foreign_or_unknown_assignment",
        )
    }


def _effective_binding(
    *,
    current_ids: set[str],
    legacy_active_ids: set[str],
    dvd_current_ids: set[str],
) -> tuple[set[str], str | None]:
    if current_ids:
        return set(current_ids), "canonical_diary"
    if legacy_active_ids:
        return set(legacy_active_ids), "legacy_active_teacher_assignment"
    if dvd_current_ids:
        return set(dvd_current_ids), "dvd_structural"
    return set(), None


def _classify_pair(
    *,
    current_ids: set[str],
    effective_binding_ids: set[str],
    effective_binding_source: str | None,
    dvd_current_ids: set[str],
    legacy_active_ids: set[str],
    same_name_tenant_ids: set[str],
    raw_data_ids: set[str],
    attributed_data_ids: set[str],
    attributed_counts: Mapping[str, int],
    assignment_drift_present: bool,
    assignmentless_present: bool,
    unresolved_attributed_refs: int,
    cross_tenant_attributed_refs: int,
    teacher_class_daily_without_course: int,
) -> list[str]:
    codes: list[str] = []
    if not current_ids:
        codes.append("NO_CURRENT_AUTHORIZED_DIARY")
    if effective_binding_source == "legacy_active_teacher_assignment":
        codes.append("EFFECTIVE_BINDING_FROM_LEGACY_ASSIGNMENT")
    elif effective_binding_source == "dvd_structural":
        codes.append("EFFECTIVE_BINDING_FROM_DVD_STRUCTURAL")
    if len(current_ids) > 1:
        codes.append("MULTIPLE_CURRENT_AUTHORIZED_COMPONENT_IDENTITIES")
    if len(effective_binding_ids) > 1:
        codes.append("MULTIPLE_EFFECTIVE_COMPONENT_IDENTITIES")
    if len(dvd_current_ids) > 1:
        codes.append("MULTIPLE_CURRENT_DVD_COMPONENT_IDENTITIES")
    if len(same_name_tenant_ids) > 1:
        codes.append("MULTIPLE_SAME_NAME_COMPONENT_IDENTITIES_IN_TENANT")

    if not raw_data_ids:
        codes.append("TARGET_COMPONENT_DATA_NOT_FOUND")
    elif not attributed_data_ids:
        codes.append("SAME_NAME_DATA_PRESENT_BUT_NOT_ATTRIBUTABLE_TO_TEACHER")

    alt_data_ids = {
        cid for cid in attributed_data_ids
        if cid not in effective_binding_ids and int(attributed_counts.get(cid, 0)) > 0
    }
    effective_data_ids = {
        cid for cid in attributed_data_ids
        if cid in effective_binding_ids and int(attributed_counts.get(cid, 0)) > 0
    }
    if effective_binding_ids and alt_data_ids:
        codes.append("CURRENT_BINDING_VS_SAME_NAME_DATA_IDENTITY_SPLIT")
    if effective_binding_ids and alt_data_ids and not effective_data_ids:
        codes.append("CURRENT_IDENTITY_EMPTY_ALT_IDENTITY_HAS_DATA")
    if effective_binding_ids and effective_data_ids and not alt_data_ids:
        codes.append("DATA_IDENTITY_ALIGNED_TO_CURRENT_BINDING")
    if current_ids and legacy_active_ids and legacy_active_ids != current_ids:
        codes.append("LEGACY_BINDING_DIFFERS_FROM_CURRENT_BINDING")
    if assignment_drift_present:
        codes.append("RECORDS_ON_HISTORICAL_SAME_TEACHER_ASSIGNMENT")
    if assignmentless_present:
        codes.append("LEGACY_RECORDS_WITHOUT_ASSIGNMENT")
    if unresolved_attributed_refs:
        codes.append("TEACHER_HAS_DATA_WITH_UNRESOLVED_COURSE_ID_IN_CLASS")
    if cross_tenant_attributed_refs:
        codes.append("CROSS_TENANT_SAME_NAME_COMPONENT_REFERENCE")
    if teacher_class_daily_without_course:
        codes.append("TEACHER_ATTRIBUTED_CLASS_DAILY_ATTENDANCE_UNATTRIBUTED_TO_COMPONENT")
    return list(dict.fromkeys(codes))


async def _resolve_teacher(db, aliases: tuple[str, ...]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    alias_norms = {_norm(value) for value in aliases}
    users = await db.users.find(
        {},
        {
            "_id": 0,
            "id": 1,
            "name": 1,
            "full_name": 1,
            "role": 1,
            "roles": 1,
            "mantenedora_id": 1,
            "school_ids": 1,
            "school_links": 1,
        },
    ).to_list(50000)
    staff_all = await db.staff.find(
        {},
        {
            "_id": 0,
            "id": 1,
            "user_id": 1,
            "nome": 1,
            "name": 1,
            "full_name": 1,
            "mantenedora_id": 1,
            "school_id": 1,
            "school_ids": 1,
        },
    ).to_list(50000)

    user_matches = [
        row for row in users
        if _norm(row.get("full_name") or row.get("name")) in alias_norms
    ]
    staff_matches = [
        row for row in staff_all
        if _norm(row.get("nome") or row.get("full_name") or row.get("name")) in alias_norms
    ]

    if len(user_matches) == 1:
        user = user_matches[0]
    elif not user_matches and len(staff_matches) == 1 and _sid(staff_matches[0].get("user_id")):
        linked = [row for row in users if _sid(row.get("id")) == _sid(staff_matches[0].get("user_id"))]
        if len(linked) != 1:
            raise RuntimeError("TEACHER_VISIBILITY_F1_USER_LINK_NOT_UNIQUE")
        user = linked[0]
    else:
        raise RuntimeError(
            f"TEACHER_VISIBILITY_F1_TEACHER_IDENTITY_AMBIGUOUS:users={len(user_matches)}:staff={len(staff_matches)}"
        )

    user_id = _sid(user.get("id"))
    linked_staff = [
        row for row in staff_all
        if (_sid(row.get("user_id")) and _sid(row.get("user_id")) == user_id)
        or _norm(row.get("nome") or row.get("full_name") or row.get("name")) in alias_norms
    ]
    deduped = {_sid(row.get("id")): row for row in linked_staff if _sid(row.get("id"))}
    linked_staff = list(deduped.values())
    if not linked_staff:
        raise RuntimeError("TEACHER_VISIBILITY_F1_STAFF_IDENTITY_UNRESOLVED")
    return user, linked_staff


async def _resolve_school(db, *, target_name: str, user: Mapping[str, Any], staff_rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    schools = await db.schools.find(
        {},
        {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1},
    ).to_list(10000)
    matches = [row for row in schools if _norm(row.get("name")) == _norm(target_name)]
    if not matches:
        raise RuntimeError("TEACHER_VISIBILITY_F1_TARGET_SCHOOL_NOT_FOUND")

    school_ids: set[str] = {_sid(value) for value in (user.get("school_ids") or []) if _sid(value)}
    for link in user.get("school_links") or []:
        if isinstance(link, Mapping) and _sid(link.get("school_id")):
            school_ids.add(_sid(link.get("school_id")))
    for row in staff_rows:
        if _sid(row.get("school_id")):
            school_ids.add(_sid(row.get("school_id")))
        school_ids.update(_sid(value) for value in (row.get("school_ids") or []) if _sid(value))

    by_link = [row for row in matches if _sid(row.get("id")) in school_ids]
    if len(by_link) == 1:
        return by_link[0]

    tenant_ids = {_sid(user.get("mantenedora_id"))}
    tenant_ids.update(_sid(row.get("mantenedora_id")) for row in staff_rows)
    tenant_ids.discard("")
    by_tenant = [row for row in matches if _sid(row.get("mantenedora_id")) in tenant_ids]
    if len(by_tenant) == 1:
        return by_tenant[0]
    if len(matches) == 1 and (not tenant_ids or _sid(matches[0].get("mantenedora_id")) in tenant_ids):
        return matches[0]
    raise RuntimeError("TEACHER_VISIBILITY_F1_TARGET_SCHOOL_AMBIGUOUS")


async def _case_audit(db, case: Mapping[str, Any]) -> dict[str, Any]:
    from services.teacher_diaries import list_teacher_diaries  # pylint: disable=import-outside-toplevel

    user, staff_rows = await _resolve_teacher(db, tuple(case["teacher_aliases"]))
    teacher_id = _sid(user.get("id"))
    staff_ids = {_sid(row.get("id")) for row in staff_rows if _sid(row.get("id"))}
    actor_ids = {teacher_id, *staff_ids}
    actor_ids.discard("")

    school = await _resolve_school(db, target_name=str(case["school"]), user=user, staff_rows=staff_rows)
    school_id = _sid(school.get("id"))
    tenant_id = _sid(school.get("mantenedora_id"))

    classes = await db.classes.find(
        {
            "school_id": school_id,
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
        },
        {"_id": 0, "id": 1, "name": 1, "school_id": 1, "mantenedora_id": 1, "academic_year": 1},
    ).to_list(10000)
    classes_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in classes:
        classes_by_name[_norm(row.get("name"))].append(row)

    all_courses = await db.courses.find(
        {},
        {
            "_id": 0,
            "id": 1,
            "name": 1,
            "nivel_ensino": 1,
            "mantenedora_id": 1,
            "created_at": 1,
            "updated_at": 1,
        },
    ).to_list(50000)
    course_by_id = {_sid(row.get("id")): row for row in all_courses if _sid(row.get("id"))}

    legacy_assignments = await db.teacher_assignments.find(
        {
            "staff_id": {"$in": sorted(staff_ids)},
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
        },
        {
            "_id": 0,
            "id": 1,
            "staff_id": 1,
            "school_id": 1,
            "class_id": 1,
            "course_id": 1,
            "academic_year": 1,
            "status": 1,
            "mantenedora_id": 1,
        },
    ).to_list(20000)

    dvd_all = await db.teacher_class_assignments.find(
        {"teacher_id": teacher_id},
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
    ).to_list(20000)

    diaries_payload = await list_teacher_diaries(
        db,
        user,
        academic_year=ACADEMIC_YEAR,
        reference_date=REFERENCE_DATE,
        active_mantenedora_id=tenant_id,
    )
    diaries = list(diaries_payload.get("items") or [])
    same_teacher_assignment_ids = {_sid(row.get("id")) for row in dvd_all if _sid(row.get("id"))}

    pair_results: list[dict[str, Any]] = []
    for class_name, component_name in case["pairs"]:
        class_matches = classes_by_name.get(_norm(class_name), [])
        if len(class_matches) != 1:
            pair_results.append(
                {
                    "class": class_name,
                    "component": component_name,
                    "resolution": "CLASS_NOT_FOUND" if not class_matches else "CLASS_AMBIGUOUS",
                    "class_match_count": len(class_matches),
                    "root_cause_codes": ["TARGET_CLASS_RESOLUTION_FAILED"],
                }
            )
            continue
        class_doc = class_matches[0]
        class_id = _sid(class_doc.get("id"))

        catalog_same_name = [
            row for row in all_courses
            if _norm(row.get("name")) == _norm(component_name)
            and _sid(row.get("mantenedora_id")) in {"", tenant_id}
        ]
        catalog_same_name_ids = {_sid(row.get("id")) for row in catalog_same_name if _sid(row.get("id"))}

        class_legacy = [row for row in legacy_assignments if _sid(row.get("class_id")) == class_id]
        class_dvd = [row for row in dvd_all if _sid(row.get("class_id")) == class_id]
        class_diaries = [row for row in diaries if _sid(row.get("class_id")) == class_id]

        def is_target_course_id(course_id: str) -> bool:
            course = course_by_id.get(course_id)
            return bool(course and _norm(course.get("name")) == _norm(component_name))

        legacy_target = [row for row in class_legacy if is_target_course_id(_sid(row.get("course_id")))]
        dvd_target = [row for row in class_dvd if is_target_course_id(_sid(row.get("component_id")))]
        diary_target = [row for row in class_diaries if is_target_course_id(_sid(row.get("component_id")))]

        current_ids = {_sid(row.get("component_id")) for row in diary_target if _sid(row.get("component_id"))}
        dvd_current_ids = {
            _sid(row.get("component_id"))
            for row in dvd_target
            if _sid(row.get("component_id")) and _is_dvd_current(row)
        }
        legacy_active_ids = {
            _sid(row.get("course_id"))
            for row in legacy_target
            if _sid(row.get("course_id")) and _norm(row.get("status")) in ACTIVE_LEGACY_STATUSES
        }
        current_assignment_ids = {
            _sid(row.get("assignment_id")) for row in diary_target if _sid(row.get("assignment_id"))
        }
        effective_binding_ids, effective_binding_source = _effective_binding(
            current_ids=current_ids,
            legacy_active_ids=legacy_active_ids,
            dvd_current_ids=dvd_current_ids,
        )

        year_scope = _year_scope()
        learning_rows = await db.learning_objects.find(
            {"$and": [{"class_id": class_id}, year_scope]},
            {
                "_id": 0,
                "date": 1,
                "academic_year": 1,
                "course_id": 1,
                "staff_id": 1,
                "recorded_by": 1,
                "created_by": 1,
                "updated_by": 1,
                "teacher_id": 1,
            },
        ).to_list(30000)
        content_rows = await db.content_entries.find(
            {"$and": [{"class_id": class_id}, year_scope]},
            {
                "_id": 0,
                "date": 1,
                "academic_year": 1,
                "component_id": 1,
                "course_id": 1,
                "assignment_id": 1,
                "staff_id": 1,
                "teacher_id": 1,
                "created_by": 1,
                "recorded_by": 1,
                "updated_by": 1,
                "deleted": 1,
            },
        ).to_list(30000)
        content_rows = [row for row in content_rows if row.get("deleted") is not True]
        attendance_projection = {
            "_id": 0,
            "date": 1,
            "academic_year": 1,
            "course_id": 1,
            "assignment_id": 1,
            "staff_id": 1,
            "teacher_id": 1,
            "recorded_by": 1,
            "created_by": 1,
            "updated_by": 1,
            "school_id": 1,
            "mantenedora_id": 1,
            "assignment_profile_at_record": 1,
            "assignment_schema_version_at_record": 1,
            "aula_numero": 1,
            "period": 1,
            "number_of_classes": 1,
            "attendance_mode": 1,
            "attendance_purpose": 1,
        }
        attendance_rows = await db.attendance.find(
            {"$and": [{"class_id": class_id}, year_scope]}, attendance_projection
        ).to_list(50000)
        documentary_rows = await db.attendance_documentary.find(
            {"$and": [{"class_id": class_id}, year_scope]}, attendance_projection
        ).to_list(50000)

        all_rows = [*learning_rows, *content_rows, *attendance_rows, *documentary_rows]
        all_data_course_ids = {_record_course_id(row) for row in all_rows if _record_course_id(row)}
        raw_target_data_ids = {cid for cid in all_data_course_ids if is_target_course_id(cid)}

        attributed_rows = [
            row for row in all_rows
            if _teacher_attributed(
                row,
                actor_ids=actor_ids,
                teacher_assignment_ids=same_teacher_assignment_ids,
            )
        ]
        attributed_course_ids = {_record_course_id(row) for row in attributed_rows if _record_course_id(row)}
        attributed_target_data_ids = {cid for cid in attributed_course_ids if is_target_course_id(cid)}

        cross_tenant_same_name_ids = {
            cid for cid in attributed_course_ids
            if cid in course_by_id
            and _norm(course_by_id[cid].get("name")) == _norm(component_name)
            and _sid(course_by_id[cid].get("mantenedora_id")) not in {"", tenant_id}
        }
        unresolved_attributed_ids = {cid for cid in attributed_course_ids if cid not in course_by_id}
        teacher_class_daily_without_course_rows = [
            row for row in [*attendance_rows, *documentary_rows]
            if not _record_course_id(row)
            and _teacher_attributed(
                row,
                actor_ids=actor_ids,
                teacher_assignment_ids=same_teacher_assignment_ids,
            )
        ]

        identity_ids = sorted(
            catalog_same_name_ids
            | raw_target_data_ids
            | attributed_target_data_ids
            | current_ids
            | dvd_current_ids
            | legacy_active_ids
        )
        identity_rows: list[dict[str, Any]] = []
        attributed_counts: dict[str, int] = {}
        assignment_drift_present = False
        assignmentless_present = False

        for cid in identity_ids:
            course = course_by_id.get(cid) or {}
            lo_all = [row for row in learning_rows if _record_course_id(row) == cid]
            ce_all = [row for row in content_rows if _record_course_id(row) == cid]
            att_all = [row for row in attendance_rows if _record_course_id(row) == cid]
            doc_all = [row for row in documentary_rows if _record_course_id(row) == cid]

            def attributed(rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
                return [
                    row for row in rows
                    if _teacher_attributed(
                        row,
                        actor_ids=actor_ids,
                        teacher_assignment_ids=same_teacher_assignment_ids,
                    )
                ]

            lo = attributed(lo_all)
            ce = attributed(ce_all)
            att = attributed(att_all)
            doc = attributed(doc_all)
            ce_assignment = _partition_assignment_rows(
                ce,
                current_assignment_ids=current_assignment_ids,
                same_teacher_assignment_ids=same_teacher_assignment_ids,
            )
            att_assignment = _partition_assignment_rows(
                [*att, *doc],
                current_assignment_ids=current_assignment_ids,
                same_teacher_assignment_ids=same_teacher_assignment_ids,
            )
            if ce_assignment["historical_same_teacher_assignment"] or att_assignment["historical_same_teacher_assignment"]:
                assignment_drift_present = True
            if ce_assignment["without_assignment"] or att_assignment["without_assignment"]:
                assignmentless_present = True

            attributed_total = len(lo) + len(ce) + len(att) + len(doc)
            raw_total = len(lo_all) + len(ce_all) + len(att_all) + len(doc_all)
            attributed_counts[cid] = attributed_total
            identity_rows.append(
                {
                    "course_fingerprint": _fp(cid),
                    "name": _sid(course.get("name")) or "<unresolved>",
                    "nivel_ensino": course.get("nivel_ensino"),
                    "tenant_relation": (
                        "target" if _sid(course.get("mantenedora_id")) == tenant_id
                        else "global_or_missing" if not _sid(course.get("mantenedora_id"))
                        else "other_tenant"
                    ),
                    "roles": {
                        "current_authorized_diary": cid in current_ids,
                        "effective_binding": cid in effective_binding_ids,
                        "current_dvd": cid in dvd_current_ids,
                        "legacy_active_binding": cid in legacy_active_ids,
                        "catalog_same_name": cid in catalog_same_name_ids,
                        "raw_data_present": raw_total > 0,
                        "teacher_attributed_data_present": attributed_total > 0,
                    },
                    "records": {
                        "raw_total_metadata_records": raw_total,
                        "teacher_attributed_total_metadata_records": attributed_total,
                        "learning_objects": {
                            "raw": _date_summary(lo_all),
                            "teacher_attributed": _date_summary(lo),
                        },
                        "content_entries": {
                            "raw": _date_summary(ce_all),
                            "teacher_attributed": _date_summary(ce),
                            "teacher_assignment_partition": ce_assignment,
                        },
                        "attendance": {
                            "raw": _date_summary(att_all),
                            "teacher_attributed": _date_summary(att),
                            "academic_year_types": _academic_year_types(att),
                            "shape": _attendance_shape(att),
                        },
                        "attendance_documentary": {
                            "raw": _date_summary(doc_all),
                            "teacher_attributed": _date_summary(doc),
                            "academic_year_types": _academic_year_types(doc),
                            "shape": _attendance_shape(doc),
                        },
                        "teacher_attendance_assignment_partition": att_assignment,
                    },
                }
            )

        codes = _classify_pair(
            current_ids=current_ids,
            effective_binding_ids=effective_binding_ids,
            effective_binding_source=effective_binding_source,
            dvd_current_ids=dvd_current_ids,
            legacy_active_ids=legacy_active_ids,
            same_name_tenant_ids=catalog_same_name_ids,
            raw_data_ids=raw_target_data_ids,
            attributed_data_ids=attributed_target_data_ids,
            attributed_counts=attributed_counts,
            assignment_drift_present=assignment_drift_present,
            assignmentless_present=assignmentless_present,
            unresolved_attributed_refs=len(unresolved_attributed_ids),
            cross_tenant_attributed_refs=len(cross_tenant_same_name_ids),
            teacher_class_daily_without_course=len(teacher_class_daily_without_course_rows),
        )

        pair_results.append(
            {
                "class": class_name,
                "component": component_name,
                "resolution": "EXACT_CLASS",
                "binding_counts": {
                    "current_authorized_diaries": len(diary_target),
                    "current_dvd": sum(1 for row in dvd_target if _is_dvd_current(row)),
                    "legacy_active": sum(1 for row in legacy_target if _norm(row.get("status")) in ACTIVE_LEGACY_STATUSES),
                    "same_name_catalog_identities": len(catalog_same_name_ids),
                },
                "effective_binding_source": effective_binding_source,
                "effective_binding_fingerprints": sorted(
                    fp for fp in (_fp(cid) for cid in effective_binding_ids) if fp
                ),
                "identity_matrix": identity_rows,
                "teacher_attributed_class_daily_without_course": len(teacher_class_daily_without_course_rows),
                "unresolved_teacher_attributed_course_refs_in_class": len(unresolved_attributed_ids),
                "cross_tenant_teacher_attributed_same_name_refs_in_class": len(cross_tenant_same_name_ids),
                "root_cause_codes": codes,
            }
        )

    cause_counts: Counter[str] = Counter()
    for row in pair_results:
        for code in row.get("root_cause_codes") or []:
            cause_counts[code] += 1
    return {
        "case": case["key"],
        "teacher": case["teacher"],
        "school": case["school"],
        "pair_count": len(case["pairs"]),
        "identity": {
            "primary_role": user.get("role"),
            "linked_staff_records": len(staff_rows),
            "tenant_present": bool(tenant_id),
            "current_authorized_diaries_total": len(diaries),
            "blocked_current_diaries_total": int(diaries_payload.get("blocked_total") or 0),
        },
        "summary": {
            "root_cause_counts": dict(sorted(cause_counts.items())),
            "pairs_with_identity_split": cause_counts.get("CURRENT_BINDING_VS_SAME_NAME_DATA_IDENTITY_SPLIT", 0),
            "pairs_with_assignment_drift": cause_counts.get("RECORDS_ON_HISTORICAL_SAME_TEACHER_ASSIGNMENT", 0),
            "pairs_without_target_data": cause_counts.get("TARGET_COMPONENT_DATA_NOT_FOUND", 0),
            "pairs_with_only_unattributed_same_name_data": cause_counts.get(
                "SAME_NAME_DATA_PRESENT_BUT_NOT_ATTRIBUTABLE_TO_TEACHER", 0
            ),
        },
        "pairs": pair_results,
    }


async def _run_live_audit() -> dict[str, Any]:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise RuntimeError("TEACHER_VISIBILITY_F1_MONGO_URL_MISSING")

    from motor.motor_asyncio import AsyncIOMotorClient  # pylint: disable=import-outside-toplevel

    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=10000)
    db = client[db_name]
    try:
        cases = [await _case_audit(db, case) for case in CASES]
        return {
            "schema": "TEACHER_VISIBILITY_F1_READ_ONLY_V1",
            "status": "PASS",
            "database_mutation": False,
            "production_writes": False,
            "mongo_reads_only": True,
            "http_methods": [],
            "attendance_records_read": False,
            "student_data_read": False,
            "student_pii_emitted": False,
            "grade_values_read": False,
            "pedagogical_text_read": False,
            "technical_ids_emitted": False,
            "audit_old_new_description_read": False,
            "automatic_remap_authorized": False,
            "academic_year": ACADEMIC_YEAR,
            "reference_date": REFERENCE_DATE,
            "target_pair_count": sum(len(case["pairs"]) for case in CASES),
            "cases": cases,
        }
    finally:
        client.close()


def run_live_audit() -> dict[str, Any]:
    return asyncio.run(_run_live_audit())


def main() -> None:
    print(
        "TEACHER_VISIBILITY_F1_JSON="
        + json.dumps(run_live_audit(), ensure_ascii=False, separators=(",", ":"))
    )


if __name__ == "__main__":
    main()
