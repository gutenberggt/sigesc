#!/usr/bin/env python3
"""LUIZ-GOMES-F6.3b — recuperação forense via diary_snapshots, read-only.

Procura evidência congelada de conteúdos de Matemática do professor Luiz Gomes
no 8º ANO A e 9º ANO A, fevereiro-abril/2026, sem ler conteúdo pedagógico nem
registros individuais de frequência.

Nenhuma restauração ou mutação é realizada.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
import json
import os
import re
import unicodedata
from typing import Any, Mapping

from pymongo import MongoClient

ACADEMIC_YEAR = 2026
TEACHER_NAME = "Luiz Gomes dos Santos"
TARGET_SCHOOL = "E M E I E F Jose Pereira Barbosa"
TARGET_COMPONENT = "Matemática"
TARGET_CLASSES = ("8º ANO A", "9º ANO A")
START_DATE = "2026-02-01"
END_DATE = "2026-04-30"
ACTIVE_STATUSES = {"ativo", "active"}
INSTITUTIONAL_SNAPSHOT_STATUSES = {"published", "superseded", "revoked"}

SNAPSHOT_PROJECTION = {
    "_id": 0,
    "id": 1,
    "class_id": 1,
    "status": 1,
    "period_type": 1,
    "period_from": 1,
    "period_to": 1,
    "period_label": 1,
    "created_at": 1,
    "published_at": 1,
    "schema_version": 1,
    "semantic_rules_version": 1,
    "payload.period.from": 1,
    "payload.period.to": 1,
    "payload.period.academic_year": 1,
    "payload.days.date": 1,
    "payload.days.entries.component_id": 1,
    "payload.days.entries.component_name": 1,
    "payload.days.entries.teacher_id": 1,
    "payload.days.entries.teacher_name": 1,
    "payload.days.entries.content_status": 1,
    "payload.days.entries.content_entry_id": 1,
    "payload.days.entries.content_created_by": 1,
    "payload.days.entries.published_by": 1,
    "payload.days.entries.corrected_by": 1,
    "payload.days.entries.version": 1,
    "payload.days.entries.aula_numero": 1,
    "payload.days.entries.matched_by": 1,
    "payload.days.entries.expected_by_schedule": 1,
}

FORBIDDEN_SNAPSHOT_FIELDS = {
    "content_text",
    "content_methodology",
    "content_observations",
    "attendance_records",
    "student_id",
    "dependency_id",
}


def _sid(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _norm(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", _sid(value))
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = raw.casefold().replace("º", "o").replace("ª", "a")
    return re.sub(r"\s+", " ", raw).strip()


def _parse_iso_day(value: Any) -> date | None:
    raw = _sid(value)[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _in_target_period(value: Any) -> bool:
    day = _parse_iso_day(value)
    return bool(day and date(2026, 2, 1) <= day <= date(2026, 4, 30))


def _overlaps_target(period_from: Any, period_to: Any) -> bool:
    start = _parse_iso_day(period_from)
    end = _parse_iso_day(period_to)
    if not start or not end:
        return False
    return start <= date(2026, 4, 30) and end >= date(2026, 2, 1)


def _resolve_teacher(db) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    users = list(
        db.users.find(
            {"$or": [{"full_name": TEACHER_NAME}, {"name": TEACHER_NAME}]},
            {"_id": 0, "id": 1, "name": 1, "full_name": 1, "mantenedora_id": 1},
        ).limit(20)
    )
    users = [
        user for user in users
        if _norm(user.get("full_name") or user.get("name")) == _norm(TEACHER_NAME)
    ]
    if len(users) != 1:
        raise RuntimeError(f"LUIZ_GOMES_F6_3B_TEACHER_USER_MATCHES:{len(users)}")
    user = users[0]
    staff_rows = list(
        db.staff.find(
            {"user_id": _sid(user.get("id"))},
            {"_id": 0, "id": 1, "user_id": 1, "school_id": 1, "mantenedora_id": 1},
        ).limit(50)
    )
    if not staff_rows:
        raise RuntimeError("LUIZ_GOMES_F6_3B_STAFF_NOT_FOUND")
    return user, staff_rows


def _resolve_school(db, user: Mapping[str, Any], staff_rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    matches = [
        row
        for row in db.schools.find({}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1})
        if _norm(row.get("name")) == _norm(TARGET_SCHOOL)
    ]
    tenant_hints = {
        _sid(user.get("mantenedora_id")),
        *(_sid(row.get("mantenedora_id")) for row in staff_rows),
    }
    tenant_hints.discard("")
    if len(matches) > 1 and tenant_hints:
        matches = [row for row in matches if _sid(row.get("mantenedora_id")) in tenant_hints]
    if len(matches) != 1:
        raise RuntimeError(f"LUIZ_GOMES_F6_3B_SCHOOL_MATCHES:{len(matches)}")
    return matches[0]


def _catalog(db, school_id: str, tenant_id: str):
    classes = list(
        db.classes.find(
            {"school_id": school_id},
            {"_id": 0, "id": 1, "name": 1, "academic_year": 1, "mantenedora_id": 1},
        )
    )
    classes = [row for row in classes if _sid(row.get("mantenedora_id")) in {"", tenant_id}]
    class_by_id = {_sid(row.get("id")): row for row in classes if _sid(row.get("id"))}

    courses = list(
        db.courses.find(
            {},
            {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1},
        )
    )
    courses = [row for row in courses if _sid(row.get("mantenedora_id")) in {"", tenant_id}]
    course_by_id = {_sid(row.get("id")): row for row in courses if _sid(row.get("id"))}
    return class_by_id, course_by_id


def _resolve_target_classes(class_by_id: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for class_name in TARGET_CLASSES:
        matches = [
            class_id
            for class_id, row in class_by_id.items()
            if _norm(row.get("name")) == _norm(class_name)
            and _sid(row.get("academic_year")) in {"", str(ACADEMIC_YEAR)}
        ]
        if len(matches) != 1:
            raise RuntimeError(f"LUIZ_GOMES_F6_3B_CLASS_NOT_EXACT:{class_name}:{len(matches)}")
        result[class_name] = matches[0]
    return result


def _current_math_by_class(
    db,
    staff_ids: set[str],
    target_classes: Mapping[str, str],
    course_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, str]:
    rows = list(
        db.teacher_assignments.find(
            {
                "staff_id": {"$in": sorted(staff_ids)},
                "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
            },
            {"_id": 0, "class_id": 1, "course_id": 1, "status": 1},
        )
    )
    reverse = {class_id: name for name, class_id in target_classes.items()}
    result: dict[str, set[str]] = {name: set() for name in TARGET_CLASSES}
    for row in rows:
        if _norm(row.get("status")) not in ACTIVE_STATUSES:
            continue
        class_name = reverse.get(_sid(row.get("class_id")))
        if not class_name:
            continue
        course_id = _sid(row.get("course_id"))
        if course_id and _norm((course_by_id.get(course_id) or {}).get("name")) == _norm(TARGET_COMPONENT):
            result[class_name].add(course_id)
    exact: dict[str, str] = {}
    for class_name, course_ids in result.items():
        if len(course_ids) != 1:
            raise RuntimeError(f"LUIZ_GOMES_F6_3B_CURRENT_MATH_NOT_EXACT:{class_name}:{len(course_ids)}")
        exact[class_name] = next(iter(course_ids))
    return exact


def _snapshot_period(snapshot: Mapping[str, Any]) -> tuple[str | None, str | None]:
    payload_period = ((snapshot.get("payload") or {}).get("period") or {})
    period_from = _sid(snapshot.get("period_from") or payload_period.get("from")) or None
    period_to = _sid(snapshot.get("period_to") or payload_period.get("to")) or None
    return period_from, period_to


def _entry_is_luiz_math(
    entry: Mapping[str, Any], *, teacher_user_id: str, math_course_id: str
) -> bool:
    component_match = (
        _sid(entry.get("component_id")) == math_course_id
        or _norm(entry.get("component_name")) == _norm(TARGET_COMPONENT)
    )
    teacher_match = (
        _sid(entry.get("teacher_id")) == teacher_user_id
        or _norm(entry.get("teacher_name")) == _norm(TEACHER_NAME)
    )
    return component_match and teacher_match


def _content_evidence_strength(entry: Mapping[str, Any]) -> str:
    if _sid(entry.get("content_entry_id")):
        return "CONTENT_ENTRY_ID_FROZEN"
    status = _norm(entry.get("content_status"))
    if status and status not in {"missing", "empty", "none", "not expected", "not_expected"}:
        return "CONTENT_STATUS_FROZEN"
    return "NO_CONTENT_EVIDENCE"


def _extract_snapshot_evidence(
    snapshot: Mapping[str, Any], *, teacher_user_id: str, math_course_id: str
) -> list[dict[str, Any]]:
    status = _norm(snapshot.get("status"))
    institutional = status in INSTITUTIONAL_SNAPSHOT_STATUSES
    evidence: list[dict[str, Any]] = []
    for day in ((snapshot.get("payload") or {}).get("days") or []):
        lesson_date = _sid(day.get("date"))[:10]
        if not _in_target_period(lesson_date):
            continue
        for entry in day.get("entries") or []:
            if not _entry_is_luiz_math(
                entry, teacher_user_id=teacher_user_id, math_course_id=math_course_id
            ):
                continue
            strength = _content_evidence_strength(entry)
            evidence.append(
                {
                    "date": lesson_date,
                    "month": lesson_date[5:7],
                    "snapshot_status": status or None,
                    "institutional_snapshot": institutional,
                    "content_evidence_strength": strength,
                    "content_present": strength != "NO_CONTENT_EVIDENCE",
                    "content_status": _sid(entry.get("content_status")) or None,
                    "version": entry.get("version"),
                    "matched_by": _sid(entry.get("matched_by")) or None,
                    "expected_by_schedule": entry.get("expected_by_schedule"),
                    "aula_numero": entry.get("aula_numero"),
                }
            )
    return evidence


def _classify(snapshot_count: int, evidence: list[Mapping[str, Any]]) -> list[str]:
    present = [row for row in evidence if row.get("content_present")]
    institutional = [row for row in present if row.get("institutional_snapshot")]
    draft = [row for row in present if not row.get("institutional_snapshot")]
    if institutional:
        return ["INSTITUTIONAL_DIARY_SNAPSHOT_MATH_CONTENT_CONFIRMED"]
    if draft:
        return ["DRAFT_DIARY_SNAPSHOT_MATH_CONTENT_EVIDENCE"]
    if evidence:
        return ["DIARY_SNAPSHOT_MATH_EXPECTATION_WITHOUT_CONTENT"]
    if snapshot_count:
        return ["DIARY_SNAPSHOT_PRESENT_NO_LUIZ_MATH_ENTRY"]
    return ["NO_DIARY_SNAPSHOT_COVERING_TARGET_PERIOD"]


def _month_counts(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    counter = Counter(_sid(row.get("month")) for row in rows if row.get("content_present"))
    return {month: counter.get(month, 0) for month in ("02", "03", "04")}


def run_live_audit() -> dict[str, Any]:
    uri = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "sigesc")
    client = MongoClient(uri, serverSelectionTimeoutMS=10000)
    db = client[db_name]

    user, staff_rows = _resolve_teacher(db)
    school = _resolve_school(db, user, staff_rows)
    tenant_id = _sid(school.get("mantenedora_id") or user.get("mantenedora_id"))
    if not tenant_id:
        raise RuntimeError("LUIZ_GOMES_F6_3B_TENANT_NOT_FOUND")

    class_by_id, course_by_id = _catalog(db, _sid(school.get("id")), tenant_id)
    target_classes = _resolve_target_classes(class_by_id)
    staff_ids = {_sid(row.get("id")) for row in staff_rows if _sid(row.get("id"))}
    math_by_class = _current_math_by_class(db, staff_ids, target_classes, course_by_id)
    teacher_user_id = _sid(user.get("id"))

    raw_snapshots = list(
        db.diary_snapshots.find(
            {"class_id": {"$in": list(target_classes.values())}},
            SNAPSHOT_PROJECTION,
        ).sort("created_at", 1)
    )

    reverse = {class_id: name for name, class_id in target_classes.items()}
    targets: list[dict[str, Any]] = []
    for class_name in TARGET_CLASSES:
        class_id = target_classes[class_name]
        snapshots = []
        evidence: list[dict[str, Any]] = []
        for snapshot in raw_snapshots:
            if _sid(snapshot.get("class_id")) != class_id:
                continue
            period_from, period_to = _snapshot_period(snapshot)
            if not _overlaps_target(period_from, period_to):
                continue
            snapshot_evidence = _extract_snapshot_evidence(
                snapshot,
                teacher_user_id=teacher_user_id,
                math_course_id=math_by_class[class_name],
            )
            evidence.extend(snapshot_evidence)
            snapshots.append(
                {
                    "status": _sid(snapshot.get("status")) or None,
                    "period_from": period_from,
                    "period_to": period_to,
                    "created_at_date": _sid(snapshot.get("created_at"))[:10] or None,
                    "published_at_date": _sid(snapshot.get("published_at"))[:10] or None,
                    "institutional": _norm(snapshot.get("status")) in INSTITUTIONAL_SNAPSHOT_STATUSES,
                    "math_entries": len(snapshot_evidence),
                    "math_content_entries": sum(1 for row in snapshot_evidence if row["content_present"]),
                }
            )

        present = [row for row in evidence if row.get("content_present")]
        institutional_present = [row for row in present if row.get("institutional_snapshot")]
        targets.append(
            {
                "class": class_name,
                "classification": _classify(len(snapshots), evidence),
                "snapshot_count": len(snapshots),
                "snapshot_status_counts": dict(Counter(row.get("status") or "<none>" for row in snapshots)),
                "snapshots": snapshots,
                "math_entry_count": len(evidence),
                "math_content_evidence_count": len(present),
                "institutional_math_content_evidence_count": len(institutional_present),
                "math_content_distinct_dates": sorted({row["date"] for row in present}),
                "math_content_months": _month_counts(present),
                "evidence_strength_counts": dict(Counter(row["content_evidence_strength"] for row in evidence)),
                "evidence": evidence,
            }
        )

    result = {
        "schema": "LUIZ_GOMES_F6_3B_DIARY_SNAPSHOT_RECOVERY_READ_ONLY_V1",
        "academic_year": ACADEMIC_YEAR,
        "period": {"from": START_DATE, "to": END_DATE},
        "teacher": TEACHER_NAME,
        "school": TARGET_SCHOOL,
        "component": TARGET_COMPONENT,
        "raw_target_class_snapshot_count": sum(
            1 for snapshot in raw_snapshots if _sid(snapshot.get("class_id")) in reverse
        ),
        "targets": targets,
        "summary": {
            "classification_counts": dict(
                Counter(code for target in targets for code in target["classification"])
            ),
            "covering_snapshot_count": sum(target["snapshot_count"] for target in targets),
            "math_content_evidence_count": sum(
                target["math_content_evidence_count"] for target in targets
            ),
            "institutional_math_content_evidence_count": sum(
                target["institutional_math_content_evidence_count"] for target in targets
            ),
        },
        "database_mutation": False,
        "production_writes": False,
        "mongo_reads_only": True,
        "http_methods": [],
        "attendance_records_read": False,
        "student_data_read": False,
        "student_pii_emitted": False,
        "pedagogical_plaintext_read": False,
        "pedagogical_plaintext_emitted": False,
        "technical_ids_emitted": False,
        "snapshot_payload_text_read": False,
    }
    client.close()
    return result


if __name__ == "__main__":
    print(
        "LUIZ_GOMES_F6_3B_JSON="
        + json.dumps(run_live_audit(), ensure_ascii=False, sort_keys=True)
    )
