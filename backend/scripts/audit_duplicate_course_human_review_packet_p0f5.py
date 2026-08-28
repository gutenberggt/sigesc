"""P0-F5 — pacote privado READ-ONLY para revisão humana de conflitos de courses duplicados.

Parte exclusivamente do dossiê P0-F4 e expande cada conflito duro em unidades
humanas de decisão. Diferentemente do P0-F4, este pacote pode conter valores
acadêmicos e nomes de estudantes, porque esses dados são necessários para a
adjudicação humana. Por segurança, o payload sensível NUNCA é impresso em stdout:
é obrigatório fornecer --json e o arquivo é gravado com permissão 0600.

O P0-F5 não escolhe vencedor, não altera banco, não gera decisões automáticas e
não constitui autorização para qualquer executor futuro.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
P0F4_PATH = SCRIPT_DIR / "audit_duplicate_course_conflict_provenance_p0f4.py"
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

PHASE_ID = "P0F5-DUPLICATE-COURSE-HUMAN-REVIEW-PACKET-READ-ONLY-2026"
MANIFEST_VERSION = 1

MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
)

ALLOWED_HUMAN_DECISIONS = (
    "KEEP_SOURCE",
    "KEEP_TARGET",
    "MANUAL_RECONCILIATION",
)

GRADE_VALUE_FIELDS = (
    "dependency_id", "b1", "b2", "b3", "b4", "rec_s1", "rec_s2",
    "recovery", "observations",
)

LEARNING_VALUE_FIELDS = (
    "content", "observations", "methodology", "resources", "number_of_classes",
    "skill_codigos", "adaptation_ids", "evidencia_aprendizagem",
    "pratica_pedagogica",
)

SUPPORTED_REVIEW_COLLECTIONS = {"grades", "attendance", "learning_objects"}


def assert_read_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    executable = "\n".join(
        line for line in source.splitlines()
        if "MUTATOR_TOKENS" not in line and not line.lstrip().startswith('"')
    )
    forbidden = [token for token in MUTATOR_TOKENS if token in executable]
    if forbidden:
        raise RuntimeError(f"READ_ONLY_GUARD_FAILED forbidden={forbidden}")


def _load_p0f4_module():
    spec = importlib.util.spec_from_file_location("p0f4_conflict_provenance", P0F4_PATH)
    if not spec or not spec.loader:
        raise RuntimeError("P0F4_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _canonical_sha(payload: Any) -> str:
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _stable_id(payload: Mapping[str, Any]) -> str:
    return _canonical_sha(dict(payload))


def _private_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(rendered)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    os.chmod(path, 0o600)


def _decision_contract() -> dict[str, Any]:
    return {
        "status": "PENDING_HUMAN_DECISION",
        "allowed_decisions": list(ALLOWED_HUMAN_DECISIONS),
        "automatic_recommendation": None,
        "decision": None,
        "decision_note": None,
    }


def _review_unit_id(
    *, group_number: Any, collection: str, key_sha256: str | None,
    unit_type: str, field_name: str | None = None, student_id: str | None = None,
) -> str:
    return _stable_id({
        "phase": PHASE_ID,
        "group_number": group_number,
        "collection": collection,
        "key_sha256": key_sha256,
        "unit_type": unit_type,
        "field_name": field_name,
        "student_id": student_id,
    })


def _conflict_id(group_number: Any, conflict: Mapping[str, Any]) -> str:
    return _stable_id({
        "phase": PHASE_ID,
        "group_number": group_number,
        "collection": conflict.get("collection"),
        "key_sha256": conflict.get("key_sha256"),
        "classification": conflict.get("p0f3_classification"),
        "source_document_ids": conflict.get("source_document_ids") or [],
        "target_document_ids": conflict.get("target_document_ids") or [],
    })


def _first_doc(ids: list[str], docs: Mapping[str, Mapping[str, Any]]) -> Mapping[str, Any] | None:
    for doc_id in ids:
        if doc_id in docs:
            return docs[doc_id]
    return None


def _human_context(
    source: Mapping[str, Any] | None,
    target: Mapping[str, Any] | None,
    *, classes: Mapping[str, Mapping[str, Any]],
    schools: Mapping[str, Mapping[str, Any]],
    students: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    row = source or target or {}
    class_id = _norm(row.get("class_id")) or None
    class_info = classes.get(class_id or "", {})
    school_id = _norm(row.get("school_id")) or _norm(class_info.get("school_id")) or None
    school_info = schools.get(school_id or "", {})
    student_id = _norm(row.get("student_id")) or None
    student_info = students.get(student_id or "", {})
    return {
        "school_id": school_id,
        "school_name": school_info.get("name"),
        "class_id": class_id,
        "class_name": class_info.get("name"),
        "academic_year": row.get("academic_year") or class_info.get("academic_year"),
        "date": row.get("date"),
        "period": row.get("period"),
        "aula_numero": row.get("aula_numero"),
        "student_id": student_id,
        "student_name": student_info.get("full_name"),
    }


def _actor_context(
    doc: Mapping[str, Any] | None,
    *, users: Mapping[str, Mapping[str, Any]],
    staff: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    doc = doc or {}
    result: dict[str, Any] = {}
    for field in ("created_by", "updated_by", "recorded_by", "teacher_id", "staff_id"):
        actor_id = _norm(doc.get(field))
        if not actor_id:
            continue
        actor = users.get(actor_id) or staff.get(actor_id) or {}
        result[field] = {
            "id": actor_id,
            "name": actor.get("full_name") or actor.get("name"),
        }
    return result


def _base_unit(
    *, group_number: Any, collection: str, key_sha256: str | None,
    unit_type: str, field_name: str | None, student_id: str | None,
    context: Mapping[str, Any], source_document_ids: list[str],
    target_document_ids: list[str], source_value: Any, target_value: Any,
    source_actor: Mapping[str, Any], target_actor: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "review_unit_id": _review_unit_id(
            group_number=group_number,
            collection=collection,
            key_sha256=key_sha256,
            unit_type=unit_type,
            field_name=field_name,
            student_id=student_id,
        ),
        "unit_type": unit_type,
        "field_name": field_name,
        "student_id": student_id,
        "context": dict(context),
        "source_document_ids": list(source_document_ids),
        "target_document_ids": list(target_document_ids),
        "source_actor": dict(source_actor),
        "target_actor": dict(target_actor),
        "source_value": source_value,
        "target_value": target_value,
        "decision_contract": _decision_contract(),
    }


def expand_grade_conflict(
    *, group_number: Any, conflict: Mapping[str, Any], docs: Mapping[str, Mapping[str, Any]],
    classes: Mapping[str, Mapping[str, Any]], schools: Mapping[str, Mapping[str, Any]],
    students: Mapping[str, Mapping[str, Any]], users: Mapping[str, Mapping[str, Any]],
    staff: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], str | None]:
    source_ids = [str(v) for v in conflict.get("source_document_ids") or []]
    target_ids = [str(v) for v in conflict.get("target_document_ids") or []]
    if len(source_ids) != 1 or len(target_ids) != 1:
        return [], "GRADE_MULTIPLICITY_REQUIRES_DEEP_REVIEW"
    source, target = docs.get(source_ids[0]), docs.get(target_ids[0])
    if not source or not target:
        return [], "GRADE_DOCUMENT_MISSING"
    fields = [f for f in conflict.get("field_names") or [] if f in GRADE_VALUE_FIELDS]
    if not fields:
        return [], "GRADE_CONFLICT_FIELDS_UNRESOLVED"
    context = _human_context(source, target, classes=classes, schools=schools, students=students)
    source_actor = _actor_context(source, users=users, staff=staff)
    target_actor = _actor_context(target, users=users, staff=staff)
    units = [
        _base_unit(
            group_number=group_number, collection="grades",
            key_sha256=conflict.get("key_sha256"), unit_type="GRADE_FIELD_DECISION",
            field_name=field, student_id=_norm(source.get("student_id")) or None,
            context=context, source_document_ids=source_ids, target_document_ids=target_ids,
            source_value=source.get(field), target_value=target.get(field),
            source_actor=source_actor, target_actor=target_actor,
        )
        for field in fields
    ]
    return units, None


def _attendance_record_lists(row: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in row.get("records") or []:
        if not isinstance(rec, Mapping):
            continue
        sid = _norm(rec.get("student_id"))
        if not sid:
            continue
        result[sid].append({
            "status": rec.get("status"),
            "dependency_id": rec.get("dependency_id"),
        })
    return dict(result)


def expand_attendance_conflict(
    *, group_number: Any, conflict: Mapping[str, Any], docs: Mapping[str, Mapping[str, Any]],
    classes: Mapping[str, Mapping[str, Any]], schools: Mapping[str, Mapping[str, Any]],
    students: Mapping[str, Mapping[str, Any]], users: Mapping[str, Mapping[str, Any]],
    staff: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], str | None]:
    source_ids = [str(v) for v in conflict.get("source_document_ids") or []]
    target_ids = [str(v) for v in conflict.get("target_document_ids") or []]
    if len(source_ids) != 1 or len(target_ids) != 1:
        return [], "ATTENDANCE_MULTIPLICITY_REQUIRES_DEEP_REVIEW"
    source, target = docs.get(source_ids[0]), docs.get(target_ids[0])
    if not source or not target:
        return [], "ATTENDANCE_DOCUMENT_MISSING"

    context = _human_context(source, target, classes=classes, schools=schools, students=students)
    source_actor = _actor_context(source, users=users, staff=staff)
    target_actor = _actor_context(target, users=users, staff=staff)
    fields = set(conflict.get("field_names") or [])
    units: list[dict[str, Any]] = []

    if "records.status_or_dependency_id" in fields or "records.duplicate_student_id" in fields:
        smap = _attendance_record_lists(source)
        tmap = _attendance_record_lists(target)
        for sid in sorted(set(smap) & set(tmap)):
            if smap[sid] == tmap[sid]:
                continue
            student_context = dict(context)
            student_context["student_id"] = sid
            student_context["student_name"] = (students.get(sid) or {}).get("full_name")
            units.append(_base_unit(
                group_number=group_number, collection="attendance",
                key_sha256=conflict.get("key_sha256"), unit_type="ATTENDANCE_STUDENT_DECISION",
                field_name="records.status_or_dependency_id", student_id=sid,
                context=student_context, source_document_ids=source_ids, target_document_ids=target_ids,
                source_value=smap[sid], target_value=tmap[sid],
                source_actor=source_actor, target_actor=target_actor,
            ))

    for field in ("observations", "number_of_classes"):
        if field not in fields:
            continue
        units.append(_base_unit(
            group_number=group_number, collection="attendance",
            key_sha256=conflict.get("key_sha256"), unit_type="ATTENDANCE_DOCUMENT_FIELD_DECISION",
            field_name=field, student_id=None,
            context=context, source_document_ids=source_ids, target_document_ids=target_ids,
            source_value=source.get(field), target_value=target.get(field),
            source_actor=source_actor, target_actor=target_actor,
        ))

    if not units:
        return [], "ATTENDANCE_CONFLICT_EXPANSION_EMPTY"
    return units, None


def expand_learning_conflict(
    *, group_number: Any, conflict: Mapping[str, Any], docs: Mapping[str, Mapping[str, Any]],
    classes: Mapping[str, Mapping[str, Any]], schools: Mapping[str, Mapping[str, Any]],
    students: Mapping[str, Mapping[str, Any]], users: Mapping[str, Mapping[str, Any]],
    staff: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], str | None]:
    source_ids = [str(v) for v in conflict.get("source_document_ids") or []]
    target_ids = [str(v) for v in conflict.get("target_document_ids") or []]
    if len(source_ids) != 1 or len(target_ids) != 1:
        return [], "LEARNING_MULTIPLICITY_REQUIRES_DEEP_REVIEW"
    source, target = docs.get(source_ids[0]), docs.get(target_ids[0])
    if not source or not target:
        return [], "LEARNING_DOCUMENT_MISSING"
    fields = [f for f in conflict.get("field_names") or [] if f in LEARNING_VALUE_FIELDS]
    if not fields:
        return [], "LEARNING_CONFLICT_FIELDS_UNRESOLVED"
    context = _human_context(source, target, classes=classes, schools=schools, students=students)
    source_actor = _actor_context(source, users=users, staff=staff)
    target_actor = _actor_context(target, users=users, staff=staff)
    units = [
        _base_unit(
            group_number=group_number, collection="learning_objects",
            key_sha256=conflict.get("key_sha256"), unit_type="PEDAGOGICAL_CONTENT_FIELD_DECISION",
            field_name=field, student_id=None,
            context=context, source_document_ids=source_ids, target_document_ids=target_ids,
            source_value=source.get(field), target_value=target.get(field),
            source_actor=source_actor, target_actor=target_actor,
        )
        for field in fields
    ]
    return units, None


async def _load_full_documents(
    db: Any, ids_by_collection: Mapping[str, set[str]],
) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for collection, ids in ids_by_collection.items():
        if not ids:
            out[collection] = {}
            continue
        rows = await db[collection].find({"id": {"$in": sorted(ids)}}, {"_id": 0}).to_list(len(ids) + 20)
        out[collection] = {str(row.get("id")): row for row in rows if row.get("id")}
    return out


async def _load_lookup(
    db: Any, collection: str, ids: set[str], projection: Mapping[str, int],
) -> dict[str, dict[str, Any]]:
    if not ids:
        return {}
    rows = await db[collection].find(
        {"id": {"$in": sorted(ids)}}, {"_id": 0, **dict(projection)}
    ).to_list(len(ids) + 50)
    return {str(row.get("id")): row for row in rows if row.get("id")}


def _collect_lookup_ids(
    documents: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> tuple[set[str], set[str], set[str]]:
    class_ids: set[str] = set()
    student_ids: set[str] = set()
    actor_ids: set[str] = set()
    for per_collection in documents.values():
        for doc in per_collection.values():
            if _norm(doc.get("class_id")):
                class_ids.add(_norm(doc.get("class_id")))
            if _norm(doc.get("student_id")):
                student_ids.add(_norm(doc.get("student_id")))
            for rec in doc.get("records") or []:
                if isinstance(rec, Mapping) and _norm(rec.get("student_id")):
                    student_ids.add(_norm(rec.get("student_id")))
            for field in ("created_by", "updated_by", "recorded_by", "teacher_id", "staff_id"):
                if _norm(doc.get(field)):
                    actor_ids.add(_norm(doc.get(field)))
    return class_ids, student_ids, actor_ids


async def collect_report(
    db: Any,
    *,
    academic_year: int,
    mantenedora_id: str | None,
    audit_history_limit: int,
    audit_events_per_doc: int,
) -> dict[str, Any]:
    p0f4 = _load_p0f4_module()
    p0f4_report = await p0f4.collect_report(
        db,
        academic_year=academic_year,
        mantenedora_id=mantenedora_id,
        audit_history_limit=audit_history_limit,
        audit_events_per_doc=audit_events_per_doc,
    )

    ids_by_collection: dict[str, set[str]] = defaultdict(set)
    for case in p0f4_report.get("cases") or []:
        for conflict in case.get("conflicts") or []:
            collection = str(conflict.get("collection") or "")
            if collection not in SUPPORTED_REVIEW_COLLECTIONS:
                continue
            ids_by_collection[collection].update(str(v) for v in conflict.get("source_document_ids") or [] if v)
            ids_by_collection[collection].update(str(v) for v in conflict.get("target_document_ids") or [] if v)

    documents = await _load_full_documents(db, ids_by_collection)
    class_ids, student_ids, actor_ids = _collect_lookup_ids(documents)
    classes = await _load_lookup(
        db, "classes", class_ids,
        {"id": 1, "name": 1, "school_id": 1, "academic_year": 1, "grade_level": 1},
    )
    school_ids = {_norm(row.get("school_id")) for row in classes.values() if _norm(row.get("school_id"))}
    schools = await _load_lookup(db, "schools", school_ids, {"id": 1, "name": 1})
    students = await _load_lookup(db, "students", student_ids, {"id": 1, "full_name": 1})
    users = await _load_lookup(db, "users", actor_ids, {"id": 1, "full_name": 1})
    staff = await _load_lookup(db, "staff", actor_ids, {"id": 1, "full_name": 1, "name": 1})

    cases: list[dict[str, Any]] = []
    conflicts_expanded = 0
    review_units_total = 0
    unresolved_conflicts: list[dict[str, Any]] = []
    unit_type_counts: Counter[str] = Counter()
    unit_collection_counts: Counter[str] = Counter()

    for case in p0f4_report.get("cases") or []:
        group_number = case.get("group_number")
        expanded_conflicts: list[dict[str, Any]] = []
        case_unit_count = 0
        for conflict in case.get("conflicts") or []:
            collection = str(conflict.get("collection") or "")
            conflict_id = _conflict_id(group_number, conflict)
            common = dict(
                group_number=group_number,
                conflict=conflict,
                docs=documents.get(collection, {}),
                classes=classes,
                schools=schools,
                students=students,
                users=users,
                staff=staff,
            )
            if collection == "grades":
                units, error = expand_grade_conflict(**common)
            elif collection == "attendance":
                units, error = expand_attendance_conflict(**common)
            elif collection == "learning_objects":
                units, error = expand_learning_conflict(**common)
            else:
                units, error = [], "UNSUPPORTED_REVIEW_COLLECTION"

            if error or not units:
                unresolved_conflicts.append({
                    "conflict_id": conflict_id,
                    "group_number": group_number,
                    "collection": collection,
                    "key_sha256": conflict.get("key_sha256"),
                    "reason": error or "EMPTY_REVIEW_UNIT_SET",
                })
            else:
                conflicts_expanded += 1
                for unit in units:
                    unit_type_counts[str(unit.get("unit_type"))] += 1
                    unit_collection_counts[collection] += 1
                review_units_total += len(units)
                case_unit_count += len(units)

            expanded_conflicts.append({
                "conflict_id": conflict_id,
                "collection": collection,
                "key_sha256": conflict.get("key_sha256"),
                "p0f3_classification": conflict.get("p0f3_classification"),
                "field_names": list(conflict.get("field_names") or []),
                "provenance_state": conflict.get("provenance_state"),
                "resolution_requirement": conflict.get("resolution_requirement"),
                "source_metadata": conflict.get("source_metadata"),
                "target_metadata": conflict.get("target_metadata"),
                "source_audit": conflict.get("source_audit"),
                "target_audit": conflict.get("target_audit"),
                "review_units": units,
                "expansion_error": error,
                "automatic_resolution": False,
            })

        cases.append({
            "group_number": group_number,
            "identity": case.get("identity"),
            "source_id": case.get("source_id"),
            "target_id": case.get("target_id"),
            "p0f4_conflicts": case.get("conflicts_documented"),
            "review_units": case_unit_count,
            "conflicts": expanded_conflicts,
            "automatic_resolution": False,
            "database_mutation": False,
        })

    expected_conflicts = int((p0f4_report.get("summary") or {}).get("conflicts_documented") or 0)
    complete = (
        p0f4_report.get("status") == "PASS"
        and conflicts_expanded == expected_conflicts
        and not unresolved_conflicts
    )
    status = "PASS" if complete else "BLOCKED_INCOMPLETE_HUMAN_REVIEW_PACKET"

    report: dict[str, Any] = {
        "phase": PHASE_ID,
        "manifest_version": MANIFEST_VERSION,
        "mode": "READ_ONLY_PRIVATE_HUMAN_REVIEW_PACKET",
        "status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "academic_year": academic_year,
        "mantenedora_id": mantenedora_id,
        "source_p0f4_manifest_sha256": p0f4_report.get("manifest_sha256"),
        "summary": {
            "duplicate_identity_groups": len(cases),
            "p0f4_conflicts": expected_conflicts,
            "conflicts_expanded": conflicts_expanded,
            "complete_conflict_coverage": complete,
            "review_units": review_units_total,
            "review_units_by_collection": dict(sorted(unit_collection_counts.items())),
            "review_units_by_type": dict(sorted(unit_type_counts.items())),
            "unresolved_review_conflicts": len(unresolved_conflicts),
            "pending_human_decisions": review_units_total,
            "automatic_resolution": False,
            "database_mutation": False,
        },
        "safety": {
            "sensitive_payload_in_packet": True,
            "stdout_contains_sensitive_payload": False,
            "private_file_mode": "0600",
            "contains_student_names": True,
            "contains_grade_values_when_conflicting": True,
            "contains_attendance_values_when_conflicting": True,
            "contains_pedagogical_text_when_conflicting": True,
            "automatic_recommendation": False,
            "automatic_resolution": False,
            "automatic_remap": False,
            "automatic_merge": False,
            "automatic_delete": False,
        },
        "unresolved_conflicts": unresolved_conflicts,
        "cases": cases,
    }
    report["manifest_sha256"] = _canonical_sha(report)
    return report


def compact_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") or {}
    return {
        "phase": report.get("phase"),
        "mode": report.get("mode"),
        "status": report.get("status"),
        "summary": summary,
        "cases": [
            {
                "group_number": case.get("group_number"),
                "name": (case.get("identity") or {}).get("display_name"),
                "p0f4_conflicts": case.get("p0f4_conflicts"),
                "review_units": case.get("review_units"),
            }
            for case in report.get("cases") or []
        ],
        "manifest_sha256": report.get("manifest_sha256"),
        "sensitive_payload_printed": False,
        "database_mutation": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P0-F5 private human review packet, read-only")
    parser.add_argument("--academic-year", required=True, type=int)
    parser.add_argument("--mantenedora-id")
    parser.add_argument("--audit-history-limit", type=int, default=200)
    parser.add_argument("--audit-events-per-doc", type=int, default=50)
    parser.add_argument("--json", dest="json_path", required=True,
                        help="Arquivo PRIVADO obrigatório; o payload sensível nunca é impresso")
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
            audit_events_per_doc=args.audit_events_per_doc,
        )
    finally:
        client.close()

    path = Path(args.json_path)
    _private_write_json(path, report)
    print(json.dumps(compact_summary(report), ensure_ascii=False, indent=2, default=str))
    return 0 if report.get("status") == "PASS" else 2


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
