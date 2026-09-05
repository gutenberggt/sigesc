#!/usr/bin/env python3
"""LUIZ-GOMES-F1 — auditoria forense READ-ONLY de conteúdo/frequência.

Escopo solicitado pelo proprietário em 2026-09-03 e refinado em 2026-09-03
(pedido de precisão): investigar exatamente os 2 pares (turma, componente)
Matemática / 8º ANO A e Matemática / 9º ANO A de Luiz Gomes dos Santos
(E M E I E F Jose Pereira Barbosa), ano letivo 2026, com detalhamento mês a
mês de conteúdo (`learning_objects`) para fevereiro/março/abril de 2026 —
sem qualquer mutação de produção.

Escopo reduzido deliberadamente de 6 para 2 pares (excluindo 6ºA, 6ºB, 7ºA,
7ºB) a pedido do proprietário, para minimizar a superfície de leitura em
produção e tornar a autorização e a leitura do resultado mais diretas.

Mesmo padrão estrutural e as mesmas garantias de privacidade da
ANA-LUCIA-F1 (`backend/scripts/ana_lucia_f1_readonly_audit.py`), reaplicadas
a um segundo professor/escola independente. A execução em produção só ocorre
sob o mesmo gate owner-scoped (issue com SHA exato + confirmação literal);
nenhuma execução foi autorizada neste commit.

O coletor lê somente metadados estruturais necessários para responder:
- o vínculo legado existe?
- há vínculo DVD atual/histórico?
- existem learning_objects/content_entries/attendance persistidos?
- em quais dos meses-alvo (fev/mar/abr 2026) há `learning_objects` lançados?
- os registros pertencem ao assignment atual, a um assignment histórico, ou
  estão sem assignment_id?
- a regra de projeção atual conseguiria alcançá-los?

Privacidade e segurança:
- nenhum texto pedagógico é lido;
- attendance.records não é lido (nenhum estudante/status individual);
- nenhum valor de nota é lido;
- IDs de usuário, staff, assignment e registros nunca são emitidos;
- fingerprints SHA-256 truncados são usados somente para distinguir vínculos;
- somente find/find_one/to_list em MongoDB; nenhuma escrita/backfill/remapeamento.
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

ACADEMIC_YEAR = int(os.environ.get("LUIZ_GOMES_F1_ACADEMIC_YEAR", "2026"))
REFERENCE_DATE = os.environ.get("LUIZ_GOMES_F1_REFERENCE_DATE", date.today().isoformat())[:10]
TEACHER_NAME = "Luiz Gomes dos Santos"
ACTIVE_LEGACY_STATUSES = ("ativo", "active")

TARGET_PAIRS: tuple[tuple[str, str], ...] = (
    ("8º ANO A", "Matemática"),
    ("9º ANO A", "Matemática"),
)

# Meses-alvo do detalhamento de conteúdo, pedido explicitamente pelo
# proprietário ("fevereiro, março e abril"). Formato YYYY-MM, comparável
# diretamente com o prefixo de `_day(date)`.
TARGET_MONTHS: tuple[str, ...] = (
    f"{ACADEMIC_YEAR}-02",
    f"{ACADEMIC_YEAR}-03",
    f"{ACADEMIC_YEAR}-04",
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
    rows = list(rows)
    dates = sorted({_day(row.get("date")) for row in rows if _day(row.get("date"))})
    return {
        "documents": len(rows),
        "distinct_dates": len(dates),
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
    }


def _month_breakdown(rows: Iterable[Mapping[str, Any]], months: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Detalha `rows` por mês (prefixo YYYY-MM de `date`), restrito a `months`.

    Não lê nem projeta nenhum campo além de `date` (já presente em `rows`);
    serve só para responder "em quais meses há registro" sem abrir o payload
    pedagógico.
    """
    rows = list(rows)
    buckets: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        day = _day(row.get("date"))
        month = day[:7]
        if month in months and day:
            buckets[month].append(day)
    return {
        month: {
            "documents": len(buckets.get(month, [])),
            "distinct_dates": len(set(buckets.get(month, []))),
        }
        for month in months
    }


def _year_type_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        value = row.get("academic_year")
        if value is None:
            counts["missing"] += 1
        elif isinstance(value, int):
            counts["int"] += 1
        elif isinstance(value, str):
            counts["str"] += 1
        else:
            counts[type(value).__name__] += 1
    return dict(sorted(counts.items()))


def _is_current_enabled(row: Mapping[str, Any]) -> bool:
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


def _course_names_for_id(
    courses_by_id: Mapping[str, list[Mapping[str, Any]]],
    course_id: str,
    tenant_id: str,
) -> set[str]:
    docs = list(courses_by_id.get(course_id) or [])
    tenant_docs = [
        row for row in docs
        if not _sid(row.get("mantenedora_id")) or _sid(row.get("mantenedora_id")) == tenant_id
    ]
    chosen = tenant_docs or docs
    return {_sid(row.get("name")) for row in chosen if _sid(row.get("name"))}


def _matches_target_name(names: Iterable[str], target: str) -> bool:
    target_norm = _norm(target)
    return any(_norm(name) == target_norm for name in names)


def _assignment_snapshot_complete(row: Mapping[str, Any]) -> bool:
    required = (
        "assignment_id", "teacher_id", "class_id", "school_id", "mantenedora_id",
        "assignment_profile_at_record", "assignment_schema_version_at_record",
    )
    return all(row.get(field) not in (None, "") for field in required)


def _partition_content_entries(
    rows: list[dict[str, Any]],
    *,
    current_assignment_ids: set[str],
    target_teacher_assignment_ids: set[str],
    target_teacher_id: str,
    assignment_owner_by_id: Mapping[str, str],
) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        assignment_id = _sid(row.get("assignment_id"))
        if assignment_id in current_assignment_ids:
            key = "current_assignment"
        elif assignment_id and assignment_id in target_teacher_assignment_ids:
            key = "historical_same_teacher_assignment"
        elif assignment_id and _sid(assignment_owner_by_id.get(assignment_id)) == target_teacher_id:
            key = "other_same_teacher_assignment"
        elif not assignment_id:
            key = "without_assignment_id"
        else:
            key = "foreign_or_unknown_assignment"
        groups[key].append(row)
    return {
        key: {
            **_date_summary(groups.get(key, [])),
            "assignment_fingerprints": sorted({
                fp for fp in (_fp(row.get("assignment_id")) for row in groups.get(key, [])) if fp
            }),
        }
        for key in (
            "current_assignment",
            "historical_same_teacher_assignment",
            "other_same_teacher_assignment",
            "without_assignment_id",
            "foreign_or_unknown_assignment",
        )
    }


def _partition_attendance(
    rows: list[dict[str, Any]],
    *,
    current_assignment_ids: set[str],
    target_teacher_assignment_ids: set[str],
    target_teacher_id: str,
    assignment_owner_by_id: Mapping[str, str],
    target_course_id: str,
) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    class_daily_unattributed: list[dict[str, Any]] = []
    for row in rows:
        assignment_id = _sid(row.get("assignment_id"))
        course_id = _sid(row.get("course_id"))
        if not assignment_id and not course_id:
            class_daily_unattributed.append(row)
            continue
        if course_id and course_id != target_course_id and assignment_id not in target_teacher_assignment_ids:
            continue
        if assignment_id in current_assignment_ids:
            key = "current_assignment"
        elif assignment_id and assignment_id in target_teacher_assignment_ids:
            key = "historical_same_teacher_assignment"
        elif assignment_id and _sid(assignment_owner_by_id.get(assignment_id)) == target_teacher_id:
            key = "other_same_teacher_assignment"
        elif not assignment_id and course_id == target_course_id:
            key = "legacy_same_course_without_assignment"
        else:
            key = "foreign_or_unknown_assignment"
        groups[key].append(row)

    result = {
        key: {
            **_date_summary(groups.get(key, [])),
            "academic_year_types": _year_type_counts(groups.get(key, [])),
            "assignment_fingerprints": sorted({
                fp for fp in (_fp(row.get("assignment_id")) for row in groups.get(key, [])) if fp
            }),
            "snapshot_complete": sum(
                1 for row in groups.get(key, []) if _assignment_snapshot_complete(row)
            ),
            "snapshot_incomplete": sum(
                1 for row in groups.get(key, []) if row.get("assignment_id") and not _assignment_snapshot_complete(row)
            ),
        }
        for key in (
            "current_assignment",
            "historical_same_teacher_assignment",
            "other_same_teacher_assignment",
            "legacy_same_course_without_assignment",
            "foreign_or_unknown_assignment",
        )
    }
    result["legacy_class_daily_unattributed"] = {
        **_date_summary(class_daily_unattributed),
        "academic_year_types": _year_type_counts(class_daily_unattributed),
    }
    return result


def _root_causes(
    *,
    current_diaries: list[dict[str, Any]],
    content_legacy: list[dict[str, Any]],
    content_partition: Mapping[str, Mapping[str, Any]],
    legacy_visible_count: int,
    legacy_after_cutover_count: int,
    attendance_partition: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    causes: list[str] = []
    if not current_diaries:
        causes.append("NO_CURRENT_CANONICAL_DIARY")

    content_total = len(content_legacy) + sum(
        int((content_partition.get(key) or {}).get("documents") or 0)
        for key in (
            "current_assignment", "historical_same_teacher_assignment",
            "other_same_teacher_assignment", "without_assignment_id",
            "foreign_or_unknown_assignment",
        )
    )
    if content_total == 0:
        causes.append("CONTENT_NOT_FOUND")
    if int((content_partition.get("historical_same_teacher_assignment") or {}).get("documents") or 0):
        causes.append("CONTENT_ON_HISTORICAL_ASSIGNMENT")
    if int((content_partition.get("other_same_teacher_assignment") or {}).get("documents") or 0):
        causes.append("CONTENT_ON_OTHER_SAME_TEACHER_ASSIGNMENT")
    if int((content_partition.get("without_assignment_id") or {}).get("documents") or 0):
        causes.append("CONTENT_ENTRY_WITHOUT_ASSIGNMENT")
    if legacy_after_cutover_count:
        causes.append("LEGACY_CONTENT_AFTER_CURRENT_CUTOVER")
    if legacy_visible_count or int((content_partition.get("current_assignment") or {}).get("documents") or 0):
        causes.append("CONTENT_METADATA_PROJECTABLE_BY_CURRENT_RULES")

    attendance_target_total = sum(
        int((attendance_partition.get(key) or {}).get("documents") or 0)
        for key in (
            "current_assignment", "historical_same_teacher_assignment",
            "other_same_teacher_assignment", "legacy_same_course_without_assignment",
            "foreign_or_unknown_assignment",
        )
    )
    if attendance_target_total == 0:
        causes.append("ATTENDANCE_TARGET_RECORD_NOT_FOUND")
    if int((attendance_partition.get("historical_same_teacher_assignment") or {}).get("documents") or 0):
        causes.append("ATTENDANCE_ON_HISTORICAL_ASSIGNMENT")
    if int((attendance_partition.get("other_same_teacher_assignment") or {}).get("documents") or 0):
        causes.append("ATTENDANCE_ON_OTHER_SAME_TEACHER_ASSIGNMENT")
    if int((attendance_partition.get("legacy_same_course_without_assignment") or {}).get("documents") or 0):
        causes.append("ATTENDANCE_LEGACY_WITHOUT_ASSIGNMENT")
    if int((attendance_partition.get("legacy_class_daily_unattributed") or {}).get("documents") or 0):
        causes.append("CLASS_HAS_LEGACY_CLASS_DAILY_ATTENDANCE_UNATTRIBUTED")

    current_att = attendance_partition.get("current_assignment") or {}
    if int(current_att.get("documents") or 0):
        causes.append("ATTENDANCE_CURRENT_ASSIGNMENT_PRESENT")
        if int(current_att.get("snapshot_incomplete") or 0):
            causes.append("ATTENDANCE_CURRENT_ASSIGNMENT_SNAPSHOT_INCOMPLETE")
        year_types = current_att.get("academic_year_types") or {}
        if int(year_types.get("str") or 0) and not int(year_types.get("int") or 0):
            causes.append("ATTENDANCE_CURRENT_ASSIGNMENT_YEAR_STORED_AS_STRING")

    return list(dict.fromkeys(causes))


async def _unique_teacher_identity(db) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    user_projection = {
        "_id": 0, "id": 1, "name": 1, "full_name": 1, "email": 1,
        "role": 1, "roles": 1, "mantenedora_id": 1, "school_ids": 1, "school_links": 1,
    }
    users = await db.users.find({}, user_projection).to_list(50000)
    exact_users = [
        user for user in users
        if _norm(user.get("full_name") or user.get("name")) == _norm(TEACHER_NAME)
    ]

    staff_projection = {
        "_id": 0, "id": 1, "user_id": 1, "email": 1,
        "nome": 1, "name": 1, "full_name": 1, "mantenedora_id": 1,
    }
    staff_all = await db.staff.find({}, staff_projection).to_list(50000)
    exact_staff = [
        row for row in staff_all
        if _norm(row.get("nome") or row.get("full_name") or row.get("name")) == _norm(TEACHER_NAME)
    ]

    if len(exact_users) == 1:
        user = exact_users[0]
    elif not exact_users and len(exact_staff) == 1:
        staff = exact_staff[0]
        user = None
        if _sid(staff.get("user_id")):
            user = next((u for u in users if _sid(u.get("id")) == _sid(staff.get("user_id"))), None)
        if user is None and _sid(staff.get("email")):
            email_norm = _norm(staff.get("email"))
            matches = [u for u in users if _norm(u.get("email")) == email_norm]
            if len(matches) == 1:
                user = matches[0]
        if user is None:
            raise RuntimeError("LUIZ_GOMES_F1_USER_IDENTITY_UNRESOLVED")
    else:
        raise RuntimeError(
            f"LUIZ_GOMES_F1_USER_IDENTITY_AMBIGUOUS:users={len(exact_users)}:staff={len(exact_staff)}"
        )

    user_id = _sid(user.get("id"))
    email_norm = _norm(user.get("email"))
    linked_staff = [
        row for row in staff_all
        if (_sid(row.get("user_id")) and _sid(row.get("user_id")) == user_id)
        or (email_norm and _norm(row.get("email")) == email_norm)
        or row in exact_staff
    ]
    deduped = {_sid(row.get("id")): row for row in linked_staff if _sid(row.get("id"))}
    linked_staff = list(deduped.values())
    if not linked_staff:
        raise RuntimeError("LUIZ_GOMES_F1_STAFF_IDENTITY_UNRESOLVED")
    return user, linked_staff


async def _run_live_audit() -> dict[str, Any]:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise RuntimeError("LUIZ_GOMES_F1_MONGO_URL_MISSING")

    from motor.motor_asyncio import AsyncIOMotorClient  # pylint: disable=import-outside-toplevel
    from services.teacher_diaries import list_teacher_diaries  # pylint: disable=import-outside-toplevel

    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=10000)
    db = client[db_name]
    try:
        user, staff_rows = await _unique_teacher_identity(db)
        teacher_id = _sid(user.get("id"))
        staff_ids = sorted({_sid(row.get("id")) for row in staff_rows if _sid(row.get("id"))})

        legacy_assignments = await db.teacher_assignments.find(
            {
                "staff_id": {"$in": staff_ids},
                "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
                "status": {"$in": list(ACTIVE_LEGACY_STATUSES)},
            },
            {
                "_id": 0, "id": 1, "staff_id": 1, "school_id": 1,
                "class_id": 1, "course_id": 1, "academic_year": 1,
                "status": 1, "mantenedora_id": 1,
            },
        ).to_list(10000)

        dvd_all = await db.teacher_class_assignments.find(
            {"teacher_id": teacher_id},
            {
                "_id": 0, "id": 1, "teacher_id": 1, "class_id": 1,
                "component_id": 1, "school_id": 1, "mantenedora_id": 1,
                "valid_from": 1, "valid_until": 1, "deleted": 1,
                "diary_settings": 1, "assignment_schema_version": 1,
            },
        ).to_list(10000)

        class_ids = sorted({
            _sid(row.get("class_id"))
            for row in [*legacy_assignments, *dvd_all]
            if _sid(row.get("class_id"))
        })
        classes = await db.classes.find(
            {"id": {"$in": class_ids}},
            {
                "_id": 0, "id": 1, "name": 1, "school_id": 1,
                "mantenedora_id": 1, "academic_year": 1,
            },
        ).to_list(max(1, len(class_ids) * 3)) if class_ids else []
        classes_by_id = {_sid(row.get("id")): row for row in classes if _sid(row.get("id"))}

        course_ids = sorted({
            _sid(row.get("course_id") or row.get("component_id"))
            for row in [*legacy_assignments, *dvd_all]
            if _sid(row.get("course_id") or row.get("component_id"))
        })
        courses = await db.courses.find(
            {"id": {"$in": course_ids}},
            {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1},
        ).to_list(max(1, len(course_ids) * 5)) if course_ids else []
        courses_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in courses:
            courses_by_id[_sid(row.get("id"))].append(row)

        school_ids = sorted({
            _sid(row.get("school_id")) for row in classes if _sid(row.get("school_id"))
        })
        schools = await db.schools.find(
            {"id": {"$in": school_ids}},
            {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1},
        ).to_list(max(1, len(school_ids) * 3)) if school_ids else []
        schools_by_id = {_sid(row.get("id")): row for row in schools if _sid(row.get("id"))}

        diaries_payload = await list_teacher_diaries(
            db,
            user,
            academic_year=ACADEMIC_YEAR,
            reference_date=REFERENCE_DATE,
            active_mantenedora_id=user.get("mantenedora_id"),
        )
        current_diaries_all = list(diaries_payload.get("items") or [])

        # Índice de pares realmente atribuídos à professora por qualquer uma das
        # duas representações. Isso evita buscar turmas homônimas de outras escolas.
        pair_candidates: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
        for legacy in legacy_assignments:
            class_id = _sid(legacy.get("class_id"))
            course_id = _sid(legacy.get("course_id"))
            class_doc = classes_by_id.get(class_id) or {}
            tenant_id = _sid(class_doc.get("mantenedora_id"))
            class_name = _sid(class_doc.get("name"))
            course_names = _course_names_for_id(courses_by_id, course_id, tenant_id)
            for target_class, target_course in TARGET_PAIRS:
                if _norm(class_name) == _norm(target_class) and _matches_target_name(course_names, target_course):
                    pair_candidates[(target_class, target_course)].add((class_id, course_id))

        for dvd in dvd_all:
            class_id = _sid(dvd.get("class_id"))
            course_id = _sid(dvd.get("component_id"))
            if not class_id or not course_id:
                continue
            class_doc = classes_by_id.get(class_id) or {}
            tenant_id = _sid(class_doc.get("mantenedora_id"))
            class_name = _sid(class_doc.get("name"))
            course_names = _course_names_for_id(courses_by_id, course_id, tenant_id)
            for target_class, target_course in TARGET_PAIRS:
                if _norm(class_name) == _norm(target_class) and _matches_target_name(course_names, target_course):
                    pair_candidates[(target_class, target_course)].add((class_id, course_id))

        results: list[dict[str, Any]] = []
        all_record_assignment_ids: set[str] = set()
        raw_cache: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = {}

        # Primeira passagem: lê somente metadados dos registros alvo e coleta IDs
        # de assignment referenciados para resolver a propriedade de forma agrupada.
        for target_class, target_course in TARGET_PAIRS:
            candidates = sorted(pair_candidates.get((target_class, target_course)) or set())
            if len(candidates) != 1:
                results.append({
                    "class": target_class,
                    "component": target_course,
                    "resolution": "NOT_BOUND" if not candidates else "AMBIGUOUS_BINDING",
                    "candidate_pair_count": len(candidates),
                })
                continue
            class_id, course_id = candidates[0]
            year_scope = _year_scope()
            learning_rows = await db.learning_objects.find(
                {"$and": [
                    {"class_id": class_id, "course_id": course_id},
                    year_scope,
                ]},
                {
                    "_id": 0, "date": 1, "academic_year": 1,
                    "recorded_by": 1, "created_by": 1, "teacher_id": 1,
                },
            ).to_list(10000)
            content_rows = await db.content_entries.find(
                {"$and": [
                    {"class_id": class_id},
                    {"$or": [{"component_id": course_id}, {"course_id": course_id}]},
                    year_scope,
                ]},
                {
                    "_id": 0, "date": 1, "academic_year": 1,
                    "assignment_id": 1, "teacher_id": 1, "recorded_by": 1,
                    "created_by": 1, "deleted": 1, "status": 1,
                    "component_id": 1, "course_id": 1,
                },
            ).to_list(10000)
            content_rows = [row for row in content_rows if row.get("deleted") is not True]

            attendance_projection = {
                "_id": 0, "date": 1, "academic_year": 1, "class_id": 1,
                "course_id": 1, "assignment_id": 1, "teacher_id": 1,
                "created_by": 1, "updated_by": 1,
                "attendance_mode": 1, "attendance_purpose": 1,
                "assignment_profile_at_record": 1,
                "assignment_schema_version_at_record": 1,
                "assignment_student_scope_at_record": 1,
                "school_id": 1, "mantenedora_id": 1,
            }
            attendance_rows = await db.attendance.find(
                {"$and": [{"class_id": class_id}, year_scope]},
                attendance_projection,
            ).to_list(20000)
            documentary_rows = await db.attendance_documentary.find(
                {"$and": [{"class_id": class_id}, year_scope]},
                attendance_projection,
            ).to_list(20000)

            raw_cache[(class_id, course_id)] = {
                "learning": learning_rows,
                "content": content_rows,
                "attendance": attendance_rows,
                "attendance_documentary": documentary_rows,
            }
            for row in [*content_rows, *attendance_rows, *documentary_rows]:
                if _sid(row.get("assignment_id")):
                    all_record_assignment_ids.add(_sid(row.get("assignment_id")))

        assignment_owner_by_id: dict[str, str] = {}
        if all_record_assignment_ids:
            referenced = await db.teacher_class_assignments.find(
                {"id": {"$in": sorted(all_record_assignment_ids)}},
                {"_id": 0, "id": 1, "teacher_id": 1},
            ).to_list(len(all_record_assignment_ids) + 100)
            assignment_owner_by_id = {
                _sid(row.get("id")): _sid(row.get("teacher_id"))
                for row in referenced if _sid(row.get("id"))
            }

        # Segunda passagem: classificação estrutural por alvo.
        detailed_results: list[dict[str, Any]] = []
        for base in results:
            if base.get("resolution") != "EXACT":
                detailed_results.append(base)

        unresolved_keys = {
            (item["class"], item["component"])
            for item in results if item.get("resolution") != "EXACT"
        }

        for target_class, target_course in TARGET_PAIRS:
            if (target_class, target_course) in unresolved_keys:
                continue
            candidates = sorted(pair_candidates.get((target_class, target_course)) or set())
            if len(candidates) != 1:
                continue
            class_id, course_id = candidates[0]
            class_doc = classes_by_id.get(class_id) or {}
            school = schools_by_id.get(_sid(class_doc.get("school_id"))) or {}
            tenant_id = _sid(class_doc.get("mantenedora_id"))

            legacy_for_pair = [
                row for row in legacy_assignments
                if _sid(row.get("class_id")) == class_id and _sid(row.get("course_id")) == course_id
            ]
            dvd_for_pair = [
                row for row in dvd_all
                if _sid(row.get("class_id")) == class_id
                and (not _sid(row.get("component_id")) or _sid(row.get("component_id")) == course_id)
            ]
            teacher_pair_assignment_ids = {
                _sid(row.get("id")) for row in dvd_for_pair if _sid(row.get("id"))
            }
            current_diaries = [
                diary for diary in current_diaries_all
                if _sid(diary.get("class_id")) == class_id
                and _sid(diary.get("component_id")) == course_id
            ]
            current_assignment_ids = {
                _sid(row.get("assignment_id")) for row in current_diaries if _sid(row.get("assignment_id"))
            }

            raw = raw_cache[(class_id, course_id)]
            learning_rows = raw["learning"]
            content_rows = raw["content"]
            content_partition = _partition_content_entries(
                content_rows,
                current_assignment_ids=current_assignment_ids,
                target_teacher_assignment_ids=teacher_pair_assignment_ids,
                target_teacher_id=teacher_id,
                assignment_owner_by_id=assignment_owner_by_id,
            )

            current_valid_froms = sorted({
                _day(row.get("valid_from")) for row in current_diaries if _day(row.get("valid_from"))
            })
            current_valid_from = current_valid_froms[0] if len(current_valid_froms) == 1 else None
            content_enabled = any(
                (row.get("capabilities") or {}).get("content_enabled") is True for row in current_diaries
            )
            if current_valid_from and content_enabled:
                legacy_visible = [
                    row for row in learning_rows
                    if _day(row.get("date")) and _day(row.get("date")) <= current_valid_from
                ]
                legacy_after_cutover = [
                    row for row in learning_rows
                    if _day(row.get("date")) and _day(row.get("date")) > current_valid_from
                ]
            else:
                legacy_visible = []
                legacy_after_cutover = list(learning_rows)

            official_partition = _partition_attendance(
                raw["attendance"],
                current_assignment_ids=current_assignment_ids,
                target_teacher_assignment_ids=teacher_pair_assignment_ids,
                target_teacher_id=teacher_id,
                assignment_owner_by_id=assignment_owner_by_id,
                target_course_id=course_id,
            )
            documentary_partition = _partition_attendance(
                raw["attendance_documentary"],
                current_assignment_ids=current_assignment_ids,
                target_teacher_assignment_ids=teacher_pair_assignment_ids,
                target_teacher_id=teacher_id,
                assignment_owner_by_id=assignment_owner_by_id,
                target_course_id=course_id,
            )

            # Para a causa principal, agrega oficial + documental sem ler records.
            merged_attendance: dict[str, dict[str, Any]] = {}
            for key in official_partition:
                left = official_partition.get(key) or {}
                right = documentary_partition.get(key) or {}
                merged_attendance[key] = {
                    "documents": int(left.get("documents") or 0) + int(right.get("documents") or 0),
                    "snapshot_incomplete": int(left.get("snapshot_incomplete") or 0) + int(right.get("snapshot_incomplete") or 0),
                    "academic_year_types": dict(Counter({
                        **(left.get("academic_year_types") or {}),
                    }) + Counter(right.get("academic_year_types") or {})),
                }

            causes = _root_causes(
                current_diaries=current_diaries,
                content_legacy=learning_rows,
                content_partition=content_partition,
                legacy_visible_count=len(legacy_visible),
                legacy_after_cutover_count=len(legacy_after_cutover),
                attendance_partition=merged_attendance,
            )

            diary_summary = [
                {
                    "assignment_fingerprint": _fp(row.get("assignment_id")),
                    "valid_from": row.get("valid_from"),
                    "valid_until": row.get("valid_until"),
                    "profile": row.get("profile"),
                    "content_enabled": (row.get("capabilities") or {}).get("content_enabled"),
                    "attendance_enabled": (row.get("capabilities") or {}).get("attendance_enabled"),
                    "attendance_mode": (row.get("capabilities") or {}).get("attendance_mode"),
                    "attendance_purpose": (row.get("capabilities") or {}).get("attendance_purpose"),
                }
                for row in current_diaries
            ]

            detailed_results.append({
                "class": target_class,
                "component": target_course,
                "school": _sid(school.get("name")),
                "resolution": "EXACT",
                "bindings": {
                    "legacy_active_count": len(legacy_for_pair),
                    "dvd_total_count": len(dvd_for_pair),
                    "dvd_current_enabled_structural_count": sum(_is_current_enabled(row) for row in dvd_for_pair),
                    "current_authorized_diary_count": len(current_diaries),
                    "legacy_assignment_fingerprints": sorted({
                        fp for fp in (_fp(row.get("id")) for row in legacy_for_pair) if fp
                    }),
                    "dvd_assignment_fingerprints": sorted({
                        fp for fp in (_fp(row.get("id")) for row in dvd_for_pair) if fp
                    }),
                    "current_diaries": diary_summary,
                },
                "content": {
                    "learning_objects": {
                        **_date_summary(learning_rows),
                        "recorded_by_target_teacher": sum(
                            1 for row in learning_rows if _sid(row.get("recorded_by")) == teacher_id
                        ),
                        "recorded_by_other_or_unknown": sum(
                            1 for row in learning_rows if _sid(row.get("recorded_by")) != teacher_id
                        ),
                        "projectable_via_current_legacy_bridge": len(legacy_visible),
                        "after_current_cutover": len(legacy_after_cutover),
                        "monthly_breakdown_target_months": _month_breakdown(learning_rows, TARGET_MONTHS),
                    },
                    "content_entries": {
                        **content_partition,
                        "monthly_breakdown_target_months": _month_breakdown(content_rows, TARGET_MONTHS),
                    },
                    "current_projection_metadata_count_estimate": (
                        int((content_partition.get("current_assignment") or {}).get("documents") or 0)
                        + len(legacy_visible)
                    ),
                },
                "attendance": {
                    "official": official_partition,
                    "documentary": documentary_partition,
                },
                "root_cause_codes": causes,
            })

        # Mantém a ordem exatamente igual à lista autorizada.
        order = {pair: idx for idx, pair in enumerate(TARGET_PAIRS)}
        detailed_results.sort(key=lambda row: order[(row["class"], row["component"])])

        summary_counts = Counter()
        for row in detailed_results:
            for code in row.get("root_cause_codes") or []:
                summary_counts[code] += 1

        return {
            "schema": "LUIZ_GOMES_F1_READ_ONLY_AUDIT_V1",
            "status": "PASS",
            "database_mutation": False,
            "production_writes": False,
            "mongo_reads_only": True,
            "http_methods": [],
            "academic_payload_values_read": False,
            "pedagogical_text_read": False,
            "attendance_records_read": False,
            "student_data_read": False,
            "student_pii_emitted": False,
            "record_ids_emitted": False,
            "assignment_ids_emitted": False,
            "teacher_ids_emitted": False,
            "staff_ids_emitted": False,
            "hashed_assignment_fingerprints_emitted": True,
            "target": {
                "teacher": TEACHER_NAME,
                "academic_year": ACADEMIC_YEAR,
                "reference_date": REFERENCE_DATE,
                "target_pair_count": len(TARGET_PAIRS),
            },
            "identity": {
                "primary_role": user.get("role"),
                "linked_staff_records": len(staff_rows),
                "tenant_present": bool(user.get("mantenedora_id")),
                "current_authorized_diaries_total": len(current_diaries_all),
                "blocked_current_diaries_total": int(diaries_payload.get("blocked_total") or 0),
            },
            "summary": {
                "pairs_exactly_resolved": sum(row.get("resolution") == "EXACT" for row in detailed_results),
                "pairs_not_bound": sum(row.get("resolution") == "NOT_BOUND" for row in detailed_results),
                "pairs_ambiguous": sum(row.get("resolution") == "AMBIGUOUS_BINDING" for row in detailed_results),
                "root_cause_counts": dict(sorted(summary_counts.items())),
            },
            "pairs": detailed_results,
        }
    finally:
        client.close()


def run_live_audit() -> dict[str, Any]:
    return asyncio.run(_run_live_audit())


def main() -> None:
    print(
        "LUIZ_GOMES_F1_AUDIT_JSON="
        + json.dumps(run_live_audit(), ensure_ascii=False, separators=(",", ":"))
    )


if __name__ == "__main__":
    main()
