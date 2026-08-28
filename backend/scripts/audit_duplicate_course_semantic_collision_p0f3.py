"""P0-F3 — análise semântica READ-ONLY de colisões em pares de courses duplicados.

Refina os sinais conservadores do P0-F2 usando as chaves de negócio efetivamente
usadas pelos writers do SIGESC. O objetivo é distinguir coexistência estrutural
normal de colisões que uma futura consolidação source→target teria de resolver.

Não escolhe automaticamente curso canônico, não remapeia, não mescla, não exclui,
não cria e não altera documentos. Dados pedagógicos sensíveis não são impressos:
os exemplos contêm apenas IDs de documento, hash de chave e nomes de campos.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Mapping, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from services.course_reference_integrity import (  # noqa: E402
    COURSE_REFERENCE_SPECS,
    extract_reference_ids,
)

load_dotenv(BACKEND_DIR / ".env")

PHASE_ID = "P0F3-DUPLICATE-COURSE-SEMANTIC-COLLISION-READ-ONLY-2026"
MANIFEST_VERSION = 1

MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
)

SUPPORTED_COLLECTIONS = {
    "teacher_assignments",
    "teacher_class_assignments",
    "class_schedules",
    "grades",
    "attendance",
    "learning_objects",
    "student_dependencies",
}

GRADE_FIELDS = (
    "dependency_id", "b1", "b2", "b3", "b4", "rec_s1", "rec_s2",
    "recovery", "observations",
)

LEARNING_FIELDS = (
    "content", "observations", "methodology", "resources", "number_of_classes",
    "skill_codigos", "adaptation_ids", "evidencia_aprendizagem",
    "pratica_pedagogica",
)

TA_COMPARE_FIELDS = (
    "school_id", "carga_horaria_semanal", "is_substituicao",
    "substituted_staff_id", "data_inicio_substituicao", "data_fim_substituicao",
)


def assert_read_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    executable = "\n".join(
        line for line in source.splitlines()
        if "MUTATOR_TOKENS" not in line and not line.lstrip().startswith('"')
    )
    forbidden = [token for token in MUTATOR_TOKENS if token in executable]
    if forbidden:
        raise RuntimeError(f"READ_ONLY_GUARD_FAILED forbidden={forbidden}")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _same_year(value: Any, year: int) -> bool:
    if value in (None, ""):
        return True
    try:
        return int(value) == int(year)
    except (TypeError, ValueError):
        return False


def _canonical_json_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _key_hash(key: Any) -> str:
    return _canonical_json_sha256({"key": key})


def _present(value: Any) -> bool:
    return value not in (None, "", [], {})


def _normalized_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return sorted((_normalized_value(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True, default=str))
    if isinstance(value, dict):
        return {k: _normalized_value(v) for k, v in sorted(value.items())}
    return value


def compare_sparse_fields(
    source: Mapping[str, Any], target: Mapping[str, Any], fields: tuple[str, ...]
) -> dict[str, list[str]]:
    conflicts: list[str] = []
    complementary: list[str] = []
    equal_nonempty: list[str] = []
    for field in fields:
        a = _normalized_value(source.get(field))
        b = _normalized_value(target.get(field))
        pa, pb = _present(a), _present(b)
        if pa and pb:
            if a == b:
                equal_nonempty.append(field)
            else:
                conflicts.append(field)
        elif pa != pb:
            complementary.append(field)
    return {
        "conflicts": conflicts,
        "complementary": complementary,
        "equal_nonempty": equal_nonempty,
    }


def course_identity_key(course: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        _norm(course.get("mantenedora_id")),
        _norm(course.get("name")).casefold(),
        _norm(course.get("nivel_ensino")).casefold(),
    )


def build_duplicate_groups(
    courses: list[Mapping[str, Any]],
) -> list[tuple[tuple[str, str, str], list[Mapping[str, Any]]]]:
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for course in courses:
        grouped[course_identity_key(course)].append(course)
    return sorted(
        ((key, rows) for key, rows in grouped.items() if key[1] and len(rows) > 1),
        key=lambda item: item[0],
    )


async def _load_course_audit_history(
    db: Any, course_ids: list[str], limit: int,
) -> list[dict[str, Any]]:
    query = {
        "collection": "courses",
        "$or": [
            {"document_id": {"$in": course_ids}},
            {"old_value.id": {"$in": course_ids}},
            {"new_value.id": {"$in": course_ids}},
            {"extra_data.consolidated.removed_ids": {"$in": course_ids}},
            {"extra_data.consolidated.kept_id": {"$in": course_ids}},
        ],
    }
    projection = {
        "_id": 0,
        "document_id": 1,
        "timestamp": 1,
        "timestamp_utc": 1,
        "extra_data.consolidated": 1,
    }
    return await db.audit_logs.find(query, projection).sort("timestamp", -1).to_list(limit)


def historical_kept_candidates(
    history: list[Mapping[str, Any]], group_ids: set[str],
) -> list[str]:
    candidates: set[str] = set()
    for row in history:
        consolidated = ((row.get("extra_data") or {}).get("consolidated") or [])
        for entry in consolidated:
            if not isinstance(entry, Mapping):
                continue
            kept = _norm(entry.get("kept_id"))
            if kept in group_ids:
                candidates.add(kept)
    return sorted(candidates)


def _group_by(rows: list[dict[str, Any]], key_fn: Callable[[Mapping[str, Any]], Any]) -> dict[Any, list[dict[str, Any]]]:
    out: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = key_fn(row)
        if key is not None:
            out[key].append(row)
    return out


def _shared_key_pairs(
    source_rows: list[dict[str, Any]],
    target_rows: list[dict[str, Any]],
    key_fn: Callable[[Mapping[str, Any]], Any],
) -> tuple[dict[Any, list[dict[str, Any]]], dict[Any, list[dict[str, Any]]], list[Any]]:
    source_map = _group_by(source_rows, key_fn)
    target_map = _group_by(target_rows, key_fn)
    shared = sorted(set(source_map) & set(target_map), key=lambda x: repr(x))
    return source_map, target_map, shared


def analyze_grades(source_rows: list[dict[str, Any]], target_rows: list[dict[str, Any]], example_limit: int) -> dict[str, Any]:
    def key(row: Mapping[str, Any]):
        return (_norm(row.get("student_id")), _norm(row.get("class_id")), _norm(row.get("academic_year")))

    sm, tm, shared = _shared_key_pairs(source_rows, target_rows, key)
    counts = Counter()
    examples: list[dict[str, Any]] = []
    for k in shared:
        srows, trows = sm[k], tm[k]
        if len(srows) != 1 or len(trows) != 1:
            counts["MULTIPLICITY_CONFLICT"] += 1
            kind = "MULTIPLICITY_CONFLICT"
            fields: list[str] = []
        else:
            cmp = compare_sparse_fields(srows[0], trows[0], GRADE_FIELDS)
            if cmp["conflicts"]:
                kind = "VALUE_CONFLICT"
                counts[kind] += 1
                fields = cmp["conflicts"]
            elif cmp["complementary"]:
                kind = "COMPLEMENTARY_MERGEABLE"
                counts[kind] += 1
                fields = cmp["complementary"]
            else:
                kind = "EXACT_EQUIVALENT"
                counts[kind] += 1
                fields = []
        if len(examples) < example_limit:
            examples.append({
                "key_sha256": _key_hash(k),
                "classification": kind,
                "field_names": fields,
                "source_document_ids": [_norm(r.get("id")) for r in srows],
                "target_document_ids": [_norm(r.get("id")) for r in trows],
            })
    hard = counts["VALUE_CONFLICT"] + counts["MULTIPLICITY_CONFLICT"]
    return {
        "natural_key": ["student_id", "class_id", "academic_year"],
        "source_count": len(source_rows),
        "target_count": len(target_rows),
        "shared_natural_keys": len(shared),
        "classifications": dict(sorted(counts.items())),
        "hard_conflicts": hard,
        "collision_items": len(shared),
        "examples": examples,
    }


def _attendance_key(row: Mapping[str, Any]):
    return (
        _norm(row.get("class_id")),
        _norm(row.get("date")),
        _norm(row.get("period")) or "regular",
        _norm(row.get("aula_numero")) or "<MISSING_AULA_NUMERO>",
    )


def _attendance_records_map(row: Mapping[str, Any]) -> tuple[dict[str, tuple[str, str]], bool]:
    result: dict[str, tuple[str, str]] = {}
    duplicate_student = False
    for rec in row.get("records") or []:
        sid = _norm((rec or {}).get("student_id"))
        if not sid:
            continue
        value = (_norm((rec or {}).get("status")), _norm((rec or {}).get("dependency_id")))
        if sid in result and result[sid] != value:
            duplicate_student = True
        result[sid] = value
    return result, duplicate_student


def analyze_attendance(source_rows: list[dict[str, Any]], target_rows: list[dict[str, Any]], example_limit: int) -> dict[str, Any]:
    sm, tm, shared = _shared_key_pairs(source_rows, target_rows, _attendance_key)
    counts = Counter()
    missing_aula = 0
    examples: list[dict[str, Any]] = []
    for k in shared:
        srows, trows = sm[k], tm[k]
        conflict_students = 0
        field_names: list[str] = []
        if k[-1] == "<MISSING_AULA_NUMERO>":
            missing_aula += 1
        if len(srows) != 1 or len(trows) != 1:
            kind = "MULTIPLICITY_CONFLICT"
            counts[kind] += 1
        else:
            sr, tr = srows[0], trows[0]
            smap, sdup = _attendance_records_map(sr)
            tmap, tdup = _attendance_records_map(tr)
            if sdup or tdup:
                kind = "DATA_CONFLICT"
                field_names.append("records.duplicate_student_id")
            else:
                overlap = set(smap) & set(tmap)
                conflict_students = sum(1 for sid in overlap if smap[sid] != tmap[sid])
                obs_a, obs_b = _norm(sr.get("observations")), _norm(tr.get("observations"))
                classes_a, classes_b = sr.get("number_of_classes"), tr.get("number_of_classes")
                if conflict_students:
                    field_names.append("records.status_or_dependency_id")
                if obs_a and obs_b and obs_a != obs_b:
                    field_names.append("observations")
                if classes_a is not None and classes_b is not None and classes_a != classes_b:
                    field_names.append("number_of_classes")
                if field_names:
                    kind = "DATA_CONFLICT"
                elif smap == tmap and obs_a == obs_b and classes_a == classes_b:
                    kind = "EXACT_EQUIVALENT"
                else:
                    kind = "RECORDS_MERGE_COMPATIBLE"
            counts[kind] += 1
        if len(examples) < example_limit:
            examples.append({
                "key_sha256": _key_hash(k),
                "classification": kind,
                "conflicting_student_count": conflict_students,
                "field_names": field_names,
                "source_document_ids": [_norm(r.get("id")) for r in srows],
                "target_document_ids": [_norm(r.get("id")) for r in trows],
            })
    hard = counts["DATA_CONFLICT"] + counts["MULTIPLICITY_CONFLICT"] + missing_aula
    return {
        "natural_key": ["class_id", "date", "period(default=regular)", "aula_numero"],
        "writer_semantics": "fundamental_anos_finais/eja_final",
        "source_count": len(source_rows),
        "target_count": len(target_rows),
        "shared_natural_keys": len(shared),
        "missing_aula_numero_shared_keys": missing_aula,
        "classifications": dict(sorted(counts.items())),
        "hard_conflicts": hard,
        "collision_items": len(shared),
        "examples": examples,
    }


def _learning_key(row: Mapping[str, Any]):
    return (_norm(row.get("class_id")), _norm(row.get("date")))


def analyze_learning_objects(source_rows: list[dict[str, Any]], target_rows: list[dict[str, Any]], example_limit: int) -> dict[str, Any]:
    sm, tm, shared = _shared_key_pairs(source_rows, target_rows, _learning_key)
    counts = Counter()
    examples: list[dict[str, Any]] = []
    for k in shared:
        srows, trows = sm[k], tm[k]
        fields: list[str] = []
        if len(srows) != 1 or len(trows) != 1:
            kind = "MULTIPLICITY_CONFLICT"
            counts[kind] += 1
        else:
            cmp = compare_sparse_fields(srows[0], trows[0], LEARNING_FIELDS)
            if cmp["conflicts"]:
                kind = "PEDAGOGICAL_CONTENT_CONFLICT"
                fields = cmp["conflicts"]
            elif cmp["complementary"]:
                kind = "COMPLEMENTARY_MERGEABLE"
                fields = cmp["complementary"]
            else:
                kind = "EXACT_EQUIVALENT"
            counts[kind] += 1
        if len(examples) < example_limit:
            examples.append({
                "key_sha256": _key_hash(k),
                "classification": kind,
                "field_names": fields,
                "source_document_ids": [_norm(r.get("id")) for r in srows],
                "target_document_ids": [_norm(r.get("id")) for r in trows],
            })
    hard = counts["PEDAGOGICAL_CONTENT_CONFLICT"] + counts["MULTIPLICITY_CONFLICT"]
    return {
        "natural_key": ["class_id", "date"],
        "source_count": len(source_rows),
        "target_count": len(target_rows),
        "shared_natural_keys": len(shared),
        "classifications": dict(sorted(counts.items())),
        "hard_conflicts": hard,
        "collision_items": len(shared),
        "examples": examples,
    }


def _active_status(value: Any) -> bool:
    return _norm(value).casefold() in {"ativo", "active"}


def analyze_teacher_assignments(source_rows: list[dict[str, Any]], target_rows: list[dict[str, Any]], example_limit: int) -> dict[str, Any]:
    source_active = [r for r in source_rows if _active_status(r.get("status"))]
    target_active = [r for r in target_rows if _active_status(r.get("status"))]

    def key(row: Mapping[str, Any]):
        return (_norm(row.get("staff_id")), _norm(row.get("class_id")), _norm(row.get("academic_year")))

    sm, tm, shared = _shared_key_pairs(source_active, target_active, key)
    counts = Counter()
    examples: list[dict[str, Any]] = []
    for k in shared:
        srows, trows = sm[k], tm[k]
        fields: list[str] = []
        if len(srows) != 1 or len(trows) != 1:
            kind = "MULTIPLICITY_REQUIRES_REVIEW"
        else:
            sr, tr = srows[0], trows[0]
            if sr.get("is_substituicao") is True or tr.get("is_substituicao") is True:
                kind = "SUBSTITUTION_COEXISTENCE_REQUIRES_REVIEW"
            else:
                cmp = compare_sparse_fields(sr, tr, TA_COMPARE_FIELDS)
                fields = cmp["conflicts"] + cmp["complementary"]
                kind = "DIVERGENT_ACTIVE_ASSIGNMENT_REQUIRES_REVIEW" if fields else "EXACT_ACTIVE_ASSIGNMENT_DUPLICATE"
        counts[kind] += 1
        if len(examples) < example_limit:
            examples.append({
                "key_sha256": _key_hash(k),
                "classification": kind,
                "field_names": fields,
                "source_document_ids": [_norm(r.get("id")) for r in srows],
                "target_document_ids": [_norm(r.get("id")) for r in trows],
            })
    return {
        "natural_key": ["staff_id", "class_id", "academic_year", "status=active"],
        "source_active_count": len(source_active),
        "target_active_count": len(target_active),
        "shared_natural_keys": len(shared),
        "classifications": dict(sorted(counts.items())),
        "hard_conflicts": 0,
        "collision_items": len(shared),
        "examples": examples,
    }


def _periods_overlap(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    af, bf = _norm(a.get("valid_from")), _norm(b.get("valid_from"))
    if not af or not bf:
        return True
    au = _norm(a.get("valid_until")) or "9999-12-31"
    bu = _norm(b.get("valid_until")) or "9999-12-31"
    return max(af, bf) <= min(au, bu)


def _slot_identity(slot: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        _norm(slot.get("weekday")),
        _norm(slot.get("aula_numero")),
        _norm(slot.get("start_time")),
        _norm(slot.get("end_time")),
    )


def _slots_overlap(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    if _norm(a.get("weekday")) != _norm(b.get("weekday")):
        return False
    if _norm(a.get("aula_numero")) and _norm(a.get("aula_numero")) == _norm(b.get("aula_numero")):
        return True
    ast, aet = _norm(a.get("start_time")), _norm(a.get("end_time"))
    bst, bet = _norm(b.get("start_time")), _norm(b.get("end_time"))
    if ast and aet and bst and bet:
        return max(ast, bst) < min(aet, bet)
    return False


def analyze_teacher_class_assignments(source_rows: list[dict[str, Any]], target_rows: list[dict[str, Any]], example_limit: int) -> dict[str, Any]:
    srows = [r for r in source_rows if r.get("deleted") is not True]
    trows = [r for r in target_rows if r.get("deleted") is not True]
    collisions: list[dict[str, Any]] = []
    counts = Counter()
    for sr in srows:
        for tr in trows:
            if _norm(sr.get("teacher_id")) != _norm(tr.get("teacher_id")):
                continue
            if _norm(sr.get("class_id")) != _norm(tr.get("class_id")):
                continue
            if not _periods_overlap(sr, tr):
                continue
            slot_pairs = [
                (a, b)
                for a in (sr.get("weekly_slots") or [])
                for b in (tr.get("weekly_slots") or [])
                if _slots_overlap(a or {}, b or {})
            ]
            if not slot_pairs:
                continue
            same_business = (
                _norm(sr.get("valid_from")) == _norm(tr.get("valid_from"))
                and _norm(sr.get("valid_until")) == _norm(tr.get("valid_until"))
                and bool(sr.get("is_substitute")) == bool(tr.get("is_substitute"))
                and sorted(_slot_identity(x or {}) for x in (sr.get("weekly_slots") or []))
                    == sorted(_slot_identity(x or {}) for x in (tr.get("weekly_slots") or []))
                and _normalized_value(sr.get("diary_settings")) == _normalized_value(tr.get("diary_settings"))
            )
            kind = "EXACT_ASSIGNMENT_DUPLICATE" if same_business else "OPERATIONAL_SLOT_OVERLAP_REQUIRES_REVIEW"
            counts[kind] += 1
            if len(collisions) < example_limit:
                collisions.append({
                    "classification": kind,
                    "source_document_id": _norm(sr.get("id")),
                    "target_document_id": _norm(tr.get("id")),
                    "overlapping_slot_pairs": len(slot_pairs),
                })
    return {
        "natural_collision_semantics": "same teacher + class + overlapping validity + overlapping weekly slot",
        "source_active_count": len(srows),
        "target_active_count": len(trows),
        "classifications": dict(sorted(counts.items())),
        "hard_conflicts": 0,
        "collision_items": sum(counts.values()),
        "examples": collisions,
    }


def _schedule_slot_key(slot: Mapping[str, Any]) -> Optional[tuple[str, str]]:
    day = _norm(slot.get("day") or slot.get("weekday")).casefold()
    number = _norm(slot.get("slot_number") or slot.get("aula_numero"))
    if not day or not number:
        return None
    return day, number


def analyze_class_schedules(rows: list[dict[str, Any]], source_id: str, target_id: str, example_limit: int) -> dict[str, Any]:
    shared_docs = 0
    exact_slot_collisions = 0
    unresolved_slot_identities = 0
    examples: list[dict[str, Any]] = []
    for row in rows:
        slots = row.get("schedule_slots") or []
        src = [s for s in slots if _norm((s or {}).get("course_id")) == source_id]
        tgt = [s for s in slots if _norm((s or {}).get("course_id")) == target_id]
        if not src or not tgt:
            continue
        shared_docs += 1
        src_keys = {_schedule_slot_key(s or {}) for s in src}
        tgt_keys = {_schedule_slot_key(s or {}) for s in tgt}
        unresolved_slot_identities += int(None in src_keys) + int(None in tgt_keys)
        src_keys.discard(None)
        tgt_keys.discard(None)
        collisions = sorted(src_keys & tgt_keys)
        exact_slot_collisions += len(collisions)
        if len(examples) < example_limit:
            examples.append({
                "document_id": _norm(row.get("id")),
                "class_id": _norm(row.get("class_id")),
                "source_slots": len(src),
                "target_slots": len(tgt),
                "same_day_slot_collisions": len(collisions),
            })
    hard = unresolved_slot_identities
    return {
        "slot_identity": ["day/weekday", "slot_number/aula_numero"],
        "shared_schedule_documents": shared_docs,
        "same_day_slot_collisions": exact_slot_collisions,
        "unresolved_slot_identities": unresolved_slot_identities,
        "hard_conflicts": hard,
        "collision_items": exact_slot_collisions,
        "examples": examples,
    }


def analyze_student_dependencies(source_rows: list[dict[str, Any]], target_rows: list[dict[str, Any]], example_limit: int) -> dict[str, Any]:
    sactive = [r for r in source_rows if _norm(r.get("status")).casefold() == "active"]
    tactive = [r for r in target_rows if _norm(r.get("status")).casefold() == "active"]

    def key(row: Mapping[str, Any]):
        return (_norm(row.get("student_id")), _norm(row.get("origin_academic_year")))

    sm, tm, shared = _shared_key_pairs(sactive, tactive, key)
    examples = [
        {
            "key_sha256": _key_hash(k),
            "source_document_ids": [_norm(r.get("id")) for r in sm[k]],
            "target_document_ids": [_norm(r.get("id")) for r in tm[k]],
        }
        for k in shared[:example_limit]
    ]
    return {
        "natural_key": ["student_id", "origin_academic_year", "status=active"],
        "source_active_count": len(sactive),
        "target_active_count": len(tactive),
        "shared_natural_keys": len(shared),
        "hard_conflicts": 0,
        "collision_items": len(shared),
        "examples": examples,
    }


async def _load_pair_references(
    db: Any, ids: list[str], academic_year: int,
) -> tuple[dict[str, dict[str, list[dict[str, Any]]]], dict[str, dict[str, int]]]:
    by_collection: dict[str, dict[str, list[dict[str, Any]]]] = {}
    counts: dict[str, dict[str, int]] = {}
    for spec in COURSE_REFERENCE_SPECS:
        rows = await db[spec.collection].find(
            {spec.field: {"$in": ids}}, {"_id": 0}
        ).to_list(50000)
        rows = [r for r in rows if _same_year(r.get("academic_year"), academic_year)]
        per_id: dict[str, list[dict[str, Any]]] = {course_id: [] for course_id in ids}
        for row in rows:
            row_ids = set(extract_reference_ids(row, spec.field))
            for course_id in ids:
                if course_id in row_ids:
                    per_id[course_id].append(row)
        by_collection[spec.collection] = per_id
        counts[spec.collection] = {course_id: len(per_id[course_id]) for course_id in ids}
    return by_collection, counts


def classify_group(
    *, unique_kept: bool, unsupported_reference_count: int, hard_conflicts: int, collision_items: int,
) -> str:
    if not unique_kept:
        return "NO_UNIQUE_HISTORICAL_KEPT_BLOCKED"
    if unsupported_reference_count:
        return "UNANALYZED_REFERENCES_BLOCKED"
    if hard_conflicts:
        return "SEMANTIC_DATA_CONFLICTS_FOUND_BLOCKED"
    if collision_items:
        return "SEMANTIC_COLLISIONS_REQUIRE_DETERMINISTIC_PLAN"
    return "NO_SEMANTIC_COLLISIONS_REQUIRES_REVIEW"


async def collect_report(
    db: Any,
    *,
    academic_year: int,
    mantenedora_id: Optional[str] = None,
    audit_history_limit: int = 200,
    example_limit: int = 20,
) -> dict[str, Any]:
    course_query: dict[str, Any] = {}
    if mantenedora_id:
        course_query["mantenedora_id"] = mantenedora_id
    courses = await db.courses.find(
        course_query,
        {"_id": 0, "id": 1, "name": 1, "nivel_ensino": 1, "mantenedora_id": 1,
         "status": 1, "active": 1, "created_at": 1, "updated_at": 1},
    ).to_list(50000)
    duplicate_groups = build_duplicate_groups(courses)

    cases: list[dict[str, Any]] = []
    classification_counts = Counter()

    for group_number, (identity, rows) in enumerate(duplicate_groups, 1):
        ids = sorted(_norm(r.get("id")) for r in rows if _norm(r.get("id")))
        history = await _load_course_audit_history(db, ids, audit_history_limit)
        kept = historical_kept_candidates(history, set(ids))
        target_id = kept[0] if len(kept) == 1 else None
        source_ids = [course_id for course_id in ids if target_id and course_id != target_id]
        source_id = source_ids[0] if len(source_ids) == 1 else None

        refs, reference_counts = await _load_pair_references(db, ids, academic_year)
        unsupported = {
            collection: counts
            for collection, counts in reference_counts.items()
            if collection not in SUPPORTED_COLLECTIONS and sum(counts.values()) > 0
        }
        unsupported_reference_count = sum(sum(v.values()) for v in unsupported.values())

        analyses: dict[str, Any] = {}
        hard_conflicts = 0
        collision_items = 0

        if source_id and target_id:
            analyses["grades"] = analyze_grades(
                refs["grades"][source_id], refs["grades"][target_id], example_limit
            )
            analyses["attendance"] = analyze_attendance(
                refs["attendance"][source_id], refs["attendance"][target_id], example_limit
            )
            analyses["learning_objects"] = analyze_learning_objects(
                refs["learning_objects"][source_id], refs["learning_objects"][target_id], example_limit
            )
            analyses["teacher_assignments"] = analyze_teacher_assignments(
                refs["teacher_assignments"][source_id], refs["teacher_assignments"][target_id], example_limit
            )
            analyses["teacher_class_assignments"] = analyze_teacher_class_assignments(
                refs["teacher_class_assignments"][source_id],
                refs["teacher_class_assignments"][target_id],
                example_limit,
            )
            schedule_union: dict[str, dict[str, Any]] = {}
            for row in refs["class_schedules"][source_id] + refs["class_schedules"][target_id]:
                schedule_union[_norm(row.get("id")) or _canonical_json_sha256(row)] = row
            analyses["class_schedules"] = analyze_class_schedules(
                list(schedule_union.values()), source_id, target_id, example_limit
            )
            analyses["student_dependencies"] = analyze_student_dependencies(
                refs["student_dependencies"][source_id],
                refs["student_dependencies"][target_id],
                example_limit,
            )
            hard_conflicts = sum(int(a.get("hard_conflicts") or 0) for a in analyses.values())
            collision_items = sum(int(a.get("collision_items") or 0) for a in analyses.values())

        classification = classify_group(
            unique_kept=len(kept) == 1 and source_id is not None,
            unsupported_reference_count=unsupported_reference_count,
            hard_conflicts=hard_conflicts,
            collision_items=collision_items,
        )
        classification_counts[classification] += 1

        cases.append({
            "group_number": group_number,
            "identity": {
                "mantenedora_id": identity[0] or None,
                "display_name": rows[0].get("name"),
                "display_nivel_ensino": rows[0].get("nivel_ensino"),
            },
            "course_ids": ids,
            "historical_kept_candidates": kept,
            "source_id": source_id,
            "target_id": target_id,
            "reference_counts": reference_counts,
            "unsupported_referenced_collections": unsupported,
            "unsupported_reference_count": unsupported_reference_count,
            "analyses": analyses,
            "hard_conflicts": hard_conflicts,
            "collision_items": collision_items,
            "forensic_classification": classification,
            "ready_for_executor": False,
            "database_mutation": False,
        })

    report: dict[str, Any] = {
        "phase": PHASE_ID,
        "manifest_version": MANIFEST_VERSION,
        "mode": "READ_ONLY_SEMANTIC_COLLISION_ANALYSIS",
        "status": "PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "academic_year": academic_year,
        "mantenedora_id": mantenedora_id,
        "summary": {
            "courses_audited": len(courses),
            "duplicate_identity_groups": len(cases),
            "groups_with_unique_historical_kept": sum(1 for c in cases if len(c["historical_kept_candidates"]) == 1),
            "hard_conflicts": sum(c["hard_conflicts"] for c in cases),
            "collision_items": sum(c["collision_items"] for c in cases),
            "unsupported_reference_count": sum(c["unsupported_reference_count"] for c in cases),
            "classification_counts": dict(sorted(classification_counts.items())),
            "database_mutation": False,
        },
        "safety": {
            "payload_values_redacted_from_examples": True,
            "historical_kept_is_evidence_not_authorization": True,
            "no_classification_means_safe_to_merge": True,
            "automatic_canonical_choice": False,
            "automatic_remap": False,
            "automatic_merge": False,
            "automatic_delete": False,
        },
        "cases": cases,
    }
    report["manifest_sha256"] = _canonical_json_sha256(report)
    return report


def compact_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "phase": report.get("phase"),
        "mode": report.get("mode"),
        "status": report.get("status"),
        "summary": report.get("summary"),
        "cases": [
            {
                "group_number": c.get("group_number"),
                "name": (c.get("identity") or {}).get("display_name"),
                "source_id": c.get("source_id"),
                "target_id": c.get("target_id"),
                "hard_conflicts": c.get("hard_conflicts"),
                "collision_items": c.get("collision_items"),
                "unsupported_reference_count": c.get("unsupported_reference_count"),
                "forensic_classification": c.get("forensic_classification"),
                "analyses": {
                    name: {
                        key: value
                        for key, value in analysis.items()
                        if key in {
                            "shared_natural_keys", "classifications", "hard_conflicts",
                            "collision_items", "shared_schedule_documents",
                            "same_day_slot_collisions", "unresolved_slot_identities",
                            "missing_aula_numero_shared_keys",
                        }
                    }
                    for name, analysis in (c.get("analyses") or {}).items()
                },
            }
            for c in report.get("cases") or []
        ],
        "manifest_sha256": report.get("manifest_sha256"),
        "database_mutation": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P0-F3 semantic collision read-only auditor")
    parser.add_argument("--academic-year", required=True, type=int)
    parser.add_argument("--mantenedora-id")
    parser.add_argument("--audit-history-limit", type=int, default=200)
    parser.add_argument("--example-limit", type=int, default=20)
    parser.add_argument("--json", dest="json_path")
    return parser.parse_args()


async def async_main() -> int:
    assert_read_only()
    args = parse_args()
    mongo_url = os.getenv("MONGO_URL")
    db_name = os.getenv("DB_NAME")
    if not mongo_url or not db_name:
        raise RuntimeError("MONGO_URL and DB_NAME are required")
    client = AsyncIOMotorClient(mongo_url)
    try:
        report = await collect_report(
            client[db_name],
            academic_year=args.academic_year,
            mantenedora_id=args.mantenedora_id,
            audit_history_limit=args.audit_history_limit,
            example_limit=args.example_limit,
        )
    finally:
        client.close()

    rendered = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.json_path:
        path = Path(args.json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
        print(json.dumps(compact_summary(report), ensure_ascii=False, indent=2, default=str))
    else:
        print(rendered)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
