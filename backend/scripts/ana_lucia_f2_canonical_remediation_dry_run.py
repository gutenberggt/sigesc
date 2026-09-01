#!/usr/bin/env python3
"""ANA-LUCIA-F2 — dry-run read-only do saneamento canônico dos 17 pares.

Esta fase NÃO escreve no MongoDB. Ela reutiliza integralmente a SSoT F2.9A para
obter a decisão de `teacher_class_assignments` e apenas acrescenta um inventário
privado/determinístico dos registros legados que dependeriam de uma fase futura.

Boundary:
- nenhuma mutação/backfill/reconciliação;
- nenhuma leitura de attendance.records;
- nenhum texto pedagógico de learning_objects/content_entries;
- IDs técnicos só existem no manifesto privado, nunca no snapshot público;
- apply deliberadamente não autorizado.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date
import hashlib
import json
import os
import re
import unicodedata
from typing import Any, Iterable, Mapping

from pymongo import MongoClient

import p0_250_f2_9a_global_dvd_reconciliation_plan as planner

ACADEMIC_YEAR = int(os.environ.get("ANA_LUCIA_F2_ACADEMIC_YEAR", "2026"))
REFERENCE_DATE = os.environ.get("ANA_LUCIA_F2_REFERENCE_DATE", date.today().isoformat())[:10]
TEACHER_NAME = "Ana Lucia Faria Pinto"
ACTIVE_STATUSES = ("ativo", "active")
EXPECTED_PLANNER_BLOB_SHA = "42178d99c479ab43d4345c4a5346cac6735eefd3"

TARGET_PAIRS: tuple[tuple[str, str], ...] = (
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


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


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


def classify_legacy_content(
    *,
    record_date: str,
    valid_from: str | None,
    binding_ready: bool,
    canonical_same_date_exists: bool = False,
) -> str:
    if not binding_ready or not valid_from:
        return "BLOCKED_BY_CANONICAL_BINDING"
    if canonical_same_date_exists:
        return "REVIEW_CANONICAL_CONTENT_OVERLAP"
    if record_date and record_date <= valid_from:
        return "KEEP_LEGACY_READ_ONLY_BRIDGE"
    return "PLAN_CONTENT_CANONICAL_BACKFILL"


def classify_legacy_attendance(
    *,
    record_date: str,
    valid_from: str | None,
    binding_ready: bool,
) -> str:
    if not binding_ready or not valid_from:
        return "BLOCKED_BY_CANONICAL_BINDING"
    if record_date and record_date < valid_from:
        return "KEEP_LEGACY_HISTORICAL_ACCESS"
    return "REVIEW_POST_CUTOVER_UNASSIGNED_ATTENDANCE"


def _unique_teacher_identity(db) -> tuple[dict[str, Any], dict[str, Any]]:
    users = list(
        db.users.find(
            {},
            {
                "_id": 0,
                "id": 1,
                "name": 1,
                "full_name": 1,
                "email": 1,
                "role": 1,
                "mantenedora_id": 1,
            },
        )
    )
    exact_users = [
        row for row in users
        if _norm(row.get("full_name") or row.get("name")) == _norm(TEACHER_NAME)
    ]

    staff_all = list(
        db.staff.find(
            {},
            {
                "_id": 0,
                "id": 1,
                "user_id": 1,
                "email": 1,
                "nome": 1,
                "name": 1,
                "full_name": 1,
                "mantenedora_id": 1,
            },
        )
    )
    exact_staff = [
        row for row in staff_all
        if _norm(row.get("nome") or row.get("full_name") or row.get("name")) == _norm(TEACHER_NAME)
    ]

    user: dict[str, Any] | None = exact_users[0] if len(exact_users) == 1 else None
    if user is None and not exact_users and len(exact_staff) == 1:
        staff = exact_staff[0]
        if _sid(staff.get("user_id")):
            matches = [u for u in users if _sid(u.get("id")) == _sid(staff.get("user_id"))]
            if len(matches) == 1:
                user = matches[0]
        if user is None and _sid(staff.get("email")):
            matches = [u for u in users if _norm(u.get("email")) == _norm(staff.get("email"))]
            if len(matches) == 1:
                user = matches[0]
    if user is None:
        raise RuntimeError(
            f"ANA_LUCIA_F2_USER_IDENTITY_UNRESOLVED:users={len(exact_users)}:staff={len(exact_staff)}"
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
    if len(deduped) != 1:
        raise RuntimeError(f"ANA_LUCIA_F2_STAFF_IDENTITY_NOT_UNIQUE:{len(deduped)}")
    return user, next(iter(deduped.values()))


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


def _resolve_target_keys(db, staff: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    staff_id = _sid(staff.get("id"))
    legacy = list(
        db.teacher_assignments.find(
            {
                "staff_id": staff_id,
                "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
                "status": {"$in": list(ACTIVE_STATUSES)},
            },
            {
                "_id": 0,
                "id": 1,
                "staff_id": 1,
                "class_id": 1,
                "course_id": 1,
                "school_id": 1,
                "mantenedora_id": 1,
                "academic_year": 1,
                "status": 1,
            },
        )
    )
    class_ids = sorted({_sid(row.get("class_id")) for row in legacy if _sid(row.get("class_id"))})
    course_ids = sorted({_sid(row.get("course_id")) for row in legacy if _sid(row.get("course_id"))})
    classes = list(
        db.classes.find(
            {"id": {"$in": class_ids}},
            {"_id": 0, "id": 1, "name": 1, "school_id": 1, "mantenedora_id": 1, "academic_year": 1},
        )
    )
    class_by_id = {_sid(row.get("id")): row for row in classes if _sid(row.get("id"))}
    courses_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in db.courses.find(
        {"id": {"$in": course_ids}},
        {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1},
    ):
        courses_by_id[_sid(row.get("id"))].append(row)
    school_ids = sorted({_sid(row.get("school_id")) for row in classes if _sid(row.get("school_id"))})
    school_by_id = {
        _sid(row.get("id")): row
        for row in db.schools.find(
            {"id": {"$in": school_ids}},
            {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1},
        )
    }

    resolved: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for target_class, target_component in TARGET_PAIRS:
        candidates: list[dict[str, Any]] = []
        for row in legacy:
            class_id = _sid(row.get("class_id"))
            course_id = _sid(row.get("course_id"))
            class_doc = class_by_id.get(class_id) or {}
            if _norm(class_doc.get("name")) != _norm(target_class):
                continue
            tenant_id = _sid(class_doc.get("mantenedora_id"))
            names = _course_names_for_id(courses_by_id, course_id, tenant_id)
            if not any(_norm(name) == _norm(target_component) for name in names):
                continue
            candidates.append(row)
        if len(candidates) != 1:
            raise RuntimeError(
                f"ANA_LUCIA_F2_TARGET_NOT_EXACT:{target_class}:{target_component}:count={len(candidates)}"
            )
        source = candidates[0]
        key = (staff_id, _sid(source.get("class_id")), _sid(source.get("course_id")))
        if key in seen_keys:
            raise RuntimeError(f"ANA_LUCIA_F2_DUPLICATE_TARGET_KEY:{target_class}:{target_component}")
        seen_keys.add(key)
        class_doc = class_by_id.get(key[1]) or {}
        school = school_by_id.get(_sid(class_doc.get("school_id"))) or {}
        resolved.append({
            "class": target_class,
            "component": target_component,
            "school": _sid(school.get("name")),
            "source_key": {
                "staff_id": key[0],
                "class_id": key[1],
                "course_id": key[2],
            },
            "source_assignment_id": _sid(source.get("id")),
        })
    if len(resolved) != 17:
        raise RuntimeError(f"ANA_LUCIA_F2_TARGET_COUNT_INVALID:{len(resolved)}")
    return resolved, class_by_id


def _capture_planner_decisions() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    captured: dict[str, Any] = {}
    original = planner._decision_manifest_rows

    def capture(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        materialized = [deepcopy(dict(row)) for row in rows]
        captured["decision_rows"] = materialized
        return original(materialized)

    planner._decision_manifest_rows = capture
    old_year = planner.ACADEMIC_YEAR
    old_date = planner.REFERENCE_DATE
    try:
        planner.ACADEMIC_YEAR = ACADEMIC_YEAR
        planner.REFERENCE_DATE = REFERENCE_DATE
        public = planner.run_live_plan()
    finally:
        planner.ACADEMIC_YEAR = old_year
        planner.REFERENCE_DATE = old_date
        planner._decision_manifest_rows = original
    rows = captured.get("decision_rows")
    if not isinstance(rows, list):
        raise RuntimeError("ANA_LUCIA_F2_PLANNER_DECISIONS_NOT_CAPTURED")
    return public, rows


def _current_canonical_assignment(db, *, teacher_id: str, class_id: str, component_id: str) -> dict[str, Any] | None:
    rows = list(
        db.teacher_class_assignments.find(
            {
                "teacher_id": teacher_id,
                "class_id": class_id,
                "deleted": {"$ne": True},
                "$or": [{"component_id": component_id}, {"component_id": None}, {"component_id": ""}],
            },
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
                "diary_settings": 1,
                "is_substitute": 1,
                "grades_official_owner": 1,
                "shift": 1,
                "deleted": 1,
                "source": 1,
                "migrated_from_legacy": 1,
                "synthetic_validity": 1,
                "created_by": 1,
            },
        )
    )
    valid = []
    for row in rows:
        semantic = planner.classify_teacher_class_assignment(row)
        if semantic.kind != planner.OPERATIONAL_DVD:
            continue
        try:
            settings = planner.effective_diary_settings(row)
        except planner.DiaryAssignmentAccessError:
            continue
        if not settings.enabled or not planner.is_assignment_active_on(row, REFERENCE_DATE):
            continue
        valid.append(row)
    if len(valid) != 1:
        return None
    return valid[0]


def _target_public(target: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not target:
        return None
    settings = target.get("diary_settings") or {}
    return {
        "valid_from": _day(target.get("valid_from")) or None,
        "valid_until": _day(target.get("valid_until")) or None,
        "profile": settings.get("profile"),
        "student_scope": settings.get("student_scope"),
        "is_substitute": bool(target.get("is_substitute")),
        "grades_official_owner": bool(target.get("grades_official_owner")),
        "shift": target.get("shift") or None,
    }


def _read_pair_metadata(
    db,
    *,
    source_key: Mapping[str, str],
    binding_target: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    class_id = source_key["class_id"]
    course_id = source_key["course_id"]
    binding_ready = bool(binding_target)
    valid_from = _day((binding_target or {}).get("valid_from")) or None
    year_scope = _year_scope()

    learning = list(
        db.learning_objects.find(
            {"$and": [{"class_id": class_id, "course_id": course_id}, year_scope]},
            {"_id": 0, "id": 1, "date": 1, "academic_year": 1, "recorded_by": 1},
        )
    )
    canonical_content = list(
        db.content_entries.find(
            {
                "$and": [
                    {"class_id": class_id},
                    {"$or": [{"component_id": course_id}, {"course_id": course_id}]},
                    year_scope,
                ]
            },
            {"_id": 0, "id": 1, "date": 1, "assignment_id": 1, "teacher_id": 1, "deleted": 1},
        )
    )
    canonical_content = [row for row in canonical_content if row.get("deleted") is not True]
    canonical_dates = {_day(row.get("date")) for row in canonical_content if _day(row.get("date"))}

    content_records = []
    for row in learning:
        record_date = _day(row.get("date"))
        action = classify_legacy_content(
            record_date=record_date,
            valid_from=valid_from,
            binding_ready=binding_ready,
            canonical_same_date_exists=record_date in canonical_dates,
        )
        content_records.append({
            "collection": "learning_objects",
            "id": _sid(row.get("id")) or None,
            "date": record_date or None,
            "action": action,
        })

    attendance_records = []
    attendance_projection = {
        "_id": 0,
        "id": 1,
        "date": 1,
        "academic_year": 1,
        "class_id": 1,
        "course_id": 1,
        "assignment_id": 1,
        "attendance_mode": 1,
        "attendance_purpose": 1,
    }
    for collection_name in ("attendance", "attendance_documentary"):
        collection = getattr(db, collection_name)
        rows = list(collection.find({"$and": [{"class_id": class_id}, year_scope]}, attendance_projection))
        for row in rows:
            if _sid(row.get("assignment_id")):
                continue
            if _sid(row.get("course_id")) != course_id:
                continue
            record_date = _day(row.get("date"))
            action = classify_legacy_attendance(
                record_date=record_date,
                valid_from=valid_from,
                binding_ready=binding_ready,
            )
            attendance_records.append({
                "collection": collection_name,
                "id": _sid(row.get("id")) or None,
                "date": record_date or None,
                "action": action,
            })

    content_records.sort(key=lambda item: (item.get("date") or "", item.get("id") or ""))
    attendance_records.sort(
        key=lambda item: (item.get("collection") or "", item.get("date") or "", item.get("id") or "")
    )

    private = {
        "content_legacy_records": content_records,
        "attendance_legacy_records": attendance_records,
        "canonical_content_existing_count": len(canonical_content),
    }
    content_counts = Counter(row["action"] for row in content_records)
    attendance_counts = Counter(row["action"] for row in attendance_records)
    public = {
        "legacy_content_total": len(content_records),
        "canonical_content_existing_count": len(canonical_content),
        "content_action_counts": dict(sorted(content_counts.items())),
        "legacy_attendance_total": len(attendance_records),
        "attendance_action_counts": dict(sorted(attendance_counts.items())),
    }
    return public, private


def _classification(pairs: Iterable[Mapping[str, Any]]) -> str:
    pairs = list(pairs)
    if any(row.get("canonical_decision") == "REQUIRES_REVIEW" for row in pairs):
        return "ANA_LUCIA_F2_REVIEW_REQUIRED"
    if any(
        int((row.get("record_plan") or {}).get("attendance_action_counts", {}).get(
            "REVIEW_POST_CUTOVER_UNASSIGNED_ATTENDANCE", 0
        ))
        or int((row.get("record_plan") or {}).get("content_action_counts", {}).get(
            "REVIEW_CANONICAL_CONTENT_OVERLAP", 0
        ))
        for row in pairs
    ):
        return "ANA_LUCIA_F2_PARTIAL_REVIEW_REQUIRED"
    return "ANA_LUCIA_F2_PLAN_READY"


def run_live_dry_run() -> tuple[dict[str, Any], dict[str, Any]]:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "sigesc")
    if not mongo_url:
        raise RuntimeError("ANA_LUCIA_F2_MONGO_URL_MISSING")

    client = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)
    db = client[db_name]
    try:
        user, staff = _unique_teacher_identity(db)
        targets, _ = _resolve_target_keys(db, staff)
        planner_public, planner_decisions = _capture_planner_decisions()
        decision_map = {
            (row.get("teacher_key"), row.get("class_key"), row.get("component_key")): row
            for row in planner_decisions
        }

        teacher_id = _sid(user.get("id"))
        public_pairs: list[dict[str, Any]] = []
        private_pairs: list[dict[str, Any]] = []
        for target in targets:
            source_key = target["source_key"]
            key = (source_key["staff_id"], source_key["class_id"], source_key["course_id"])
            decision = decision_map.get(key)
            if not decision:
                raise RuntimeError(
                    f"ANA_LUCIA_F2_TARGET_DECISION_MISSING:{target['class']}:{target['component']}"
                )

            canonical_decision = decision.get("decision")
            review_reasons = sorted(decision.get("review_reasons") or [])
            binding_target = deepcopy(decision.get("target_assignment")) if decision.get("target_assignment") else None
            if canonical_decision == "NOOP_ALREADY_CANONICAL":
                binding_target = _current_canonical_assignment(
                    db,
                    teacher_id=teacher_id,
                    class_id=source_key["class_id"],
                    component_id=source_key["course_id"],
                )
                if not binding_target:
                    canonical_decision = "REQUIRES_REVIEW"
                    review_reasons = sorted(set([*review_reasons, "CANONICAL_BINDING_NOT_UNIQUE_ON_RECHECK"]))

            record_public, record_private = _read_pair_metadata(
                db,
                source_key=source_key,
                binding_target=binding_target,
            )
            public_pairs.append({
                "class": target["class"],
                "component": target["component"],
                "school": target["school"],
                "canonical_decision": canonical_decision,
                "review_reasons": review_reasons,
                "target_envelope": _target_public(binding_target),
                "record_plan": record_public,
            })
            private_pairs.append({
                "class": target["class"],
                "component": target["component"],
                "school": target["school"],
                "source_key": source_key,
                "source_assignment_id": target.get("source_assignment_id") or None,
                "canonical_decision": canonical_decision,
                "review_reasons": review_reasons,
                "target_assignment": binding_target,
                "record_plan": record_private,
            })

        order = {pair: idx for idx, pair in enumerate(TARGET_PAIRS)}
        public_pairs.sort(key=lambda row: order[(row["class"], row["component"])])
        private_pairs.sort(key=lambda row: order[(row["class"], row["component"])])

        private_core = {
            "schema": "ANA_LUCIA_F2_PRIVATE_REMEDIATION_DRY_RUN_V1",
            "status": "PASS",
            "teacher": TEACHER_NAME,
            "academic_year": ACADEMIC_YEAR,
            "reference_date": REFERENCE_DATE,
            "database_mutation": False,
            "production_writes": False,
            "automatic_apply_authorized": False,
            "planner_schema": planner_public.get("schema"),
            "planner_decision_manifest_sha256": (planner_public.get("analysis") or {}).get(
                "decision_manifest_sha256"
            ),
            "pairs": private_pairs,
        }
        private_hash = _sha256(private_core)
        private_manifest = {**private_core, "manifest_sha256": private_hash}

        decision_counts = Counter(row["canonical_decision"] for row in public_pairs)
        review_counts: Counter[str] = Counter()
        content_counts: Counter[str] = Counter()
        attendance_counts: Counter[str] = Counter()
        for row in public_pairs:
            review_counts.update(row.get("review_reasons") or [])
            content_counts.update((row.get("record_plan") or {}).get("content_action_counts") or {})
            attendance_counts.update((row.get("record_plan") or {}).get("attendance_action_counts") or {})

        public_snapshot = {
            "schema": "ANA_LUCIA_F2_CANONICAL_REMEDIATION_DRY_RUN_V1",
            "status": "PASS",
            "classification": _classification(public_pairs),
            "database_mutation": False,
            "production_writes": False,
            "mongo_reads_only": True,
            "http_methods": [],
            "attendance_records_read": False,
            "student_data_read": False,
            "student_pii_emitted": False,
            "pedagogical_text_read": False,
            "record_ids_emitted": False,
            "assignment_ids_emitted": False,
            "teacher_ids_emitted": False,
            "staff_ids_emitted": False,
            "private_manifest_emitted": False,
            "private_manifest_digest_emitted": True,
            "automatic_apply_authorized": False,
            "target": {
                "teacher": TEACHER_NAME,
                "academic_year": ACADEMIC_YEAR,
                "reference_date": REFERENCE_DATE,
                "target_pair_count": len(TARGET_PAIRS),
            },
            "planner": {
                "schema": planner_public.get("schema"),
                "global_classification": planner_public.get("classification"),
                "decision_manifest_sha256": (planner_public.get("analysis") or {}).get(
                    "decision_manifest_sha256"
                ),
                "input_state_sha256": (planner_public.get("analysis") or {}).get("input_state_sha256"),
            },
            "summary": {
                "canonical_decision_counts": dict(sorted(decision_counts.items())),
                "review_reason_counts": dict(sorted(review_counts.items())),
                "content_action_counts": dict(sorted(content_counts.items())),
                "attendance_action_counts": dict(sorted(attendance_counts.items())),
                "planned_assignment_creates": int(decision_counts.get("PLAN_CREATE_CANONICAL_ASSIGNMENT", 0)),
                "private_manifest_sha256": private_hash,
            },
            "pairs": public_pairs,
        }
        return public_snapshot, private_manifest
    finally:
        client.close()


def main() -> None:
    public, private = run_live_dry_run()
    print("ANA_LUCIA_F2_PUBLIC_JSON=" + json.dumps(public, ensure_ascii=False, separators=(",", ":")))
    print("ANA_LUCIA_F2_PRIVATE_JSON=" + json.dumps(private, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
