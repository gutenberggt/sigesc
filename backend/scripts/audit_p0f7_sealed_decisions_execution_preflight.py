"""P0-F7 — preflight READ-ONLY para execução de decisões humanas P0-F6 seladas.

Valida a cadeia P0-F5 -> P0-F6 selado, compara as decisões com o estado atual
do MongoDB e produz um plano operacional sem executar qualquer mutação.
O relatório privado não replica valores acadêmicos: usa hashes, IDs e contratos
CAS para uma futura fase executora separada.

P0-F7 não autoriza executor, não remapeia courses, não mescla documentos, não
exclui registros e não altera o banco.
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
P0F3_PATH = SCRIPT_DIR / "audit_duplicate_course_semantic_collision_p0f3.py"
P0F6_PATH = SCRIPT_DIR / "build_p0f6_private_human_adjudication_station.py"
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

PHASE_ID = "P0F7-SEALED-DECISIONS-EXECUTION-PREFLIGHT-READ-ONLY-2026"
MANIFEST_VERSION = 1

MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
)

REVIEW_COLLECTIONS = {"grades", "attendance", "learning_objects"}
ALLOWED_DECISIONS = {"KEEP_SOURCE", "KEEP_TARGET", "MANUAL_RECONCILIATION"}


def assert_read_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    executable = "\n".join(
        line for line in source.splitlines()
        if "MUTATOR_TOKENS" not in line and not line.lstrip().startswith('"')
    )
    forbidden = [token for token in MUTATOR_TOKENS if token in executable]
    if forbidden:
        raise RuntimeError(f"READ_ONLY_GUARD_FAILED forbidden={forbidden}")


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"IMPORT_FAILED:{name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canonical_sha256(payload: Any) -> str:
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _normalized(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        normalized = [_normalized(v) for v in value]
        return sorted(
            normalized,
            key=lambda v: json.dumps(v, sort_keys=True, default=str),
        )
    if isinstance(value, Mapping):
        return {k: _normalized(v) for k, v in sorted(value.items())}
    return value


def _value_sha256(value: Any) -> str:
    return _canonical_sha256({"value": _normalized(value)})


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


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return payload


def _verify_embedded_sha(
    payload: Mapping[str, Any], *, field: str, label: str,
) -> str:
    stored = str(payload.get(field) or "")
    if not stored:
        raise ValueError(f"{label}_SHA_MISSING")
    canonical = dict(payload)
    canonical.pop(field, None)
    actual = _canonical_sha256(canonical)
    if actual != stored:
        raise ValueError(f"{label}_SHA_MISMATCH")
    return stored


def _iter_packet_units(packet: Mapping[str, Any]):
    for case in packet.get("cases") or []:
        for conflict in case.get("conflicts") or []:
            for unit in conflict.get("review_units") or []:
                yield case, conflict, unit


def validate_chain(
    packet: Mapping[str, Any], sealed: Mapping[str, Any],
) -> dict[str, Any]:
    p0f6 = _load_module(P0F6_PATH, "p0f6_contract")
    packet_validation = p0f6.validate_p0f5_packet(packet)

    if sealed.get("phase") != p0f6.SEALED_DECISION_PHASE:
        raise ValueError("SEALED_PHASE_MISMATCH")
    if sealed.get("status") != "SEALED_COMPLETE_HUMAN_DECISIONS":
        raise ValueError("SEALED_STATUS_MISMATCH")

    sealed_sha = _verify_embedded_sha(
        sealed,
        field="decision_manifest_sha256",
        label="SEALED_DECISION_MANIFEST",
    )
    packet_sha = packet_validation["packet_sha256"]

    if sealed.get("source_p0f5_manifest_sha256") != packet_sha:
        raise ValueError("SEALED_SOURCE_P0F5_SHA_MISMATCH")
    if int(sealed.get("source_review_unit_count") or 0) != packet_validation["review_unit_count"]:
        raise ValueError("SEALED_SOURCE_REVIEW_UNIT_COUNT_MISMATCH")

    summary = sealed.get("summary") or {}
    safety = sealed.get("safety") or {}
    if int(summary.get("decisions") or 0) != packet_validation["review_unit_count"]:
        raise ValueError("SEALED_DECISION_COUNT_MISMATCH")
    if int(summary.get("pending_human_decisions") or 0) != 0:
        raise ValueError("SEALED_PENDING_DECISIONS_PRESENT")
    if summary.get("complete_decision_coverage") is not True:
        raise ValueError("SEALED_COVERAGE_INCOMPLETE")
    if summary.get("automatic_recommendation") is not False:
        raise ValueError("SEALED_AUTOMATIC_RECOMMENDATION_INVALID")
    if summary.get("automatic_resolution") is not False:
        raise ValueError("SEALED_AUTOMATIC_RESOLUTION_INVALID")
    if summary.get("database_mutation") is not False:
        raise ValueError("SEALED_DATABASE_MUTATION_INVALID")
    if safety.get("no_database_access") is not True:
        raise ValueError("SEALED_SAFETY_NO_DATABASE_ACCESS_INVALID")
    if safety.get("no_database_mutation") is not True:
        raise ValueError("SEALED_SAFETY_NO_DATABASE_MUTATION_INVALID")
    if safety.get("not_authorization_for_executor") is not True:
        raise ValueError("SEALED_EXECUTOR_AUTHORIZATION_INVALID")

    expected = packet_validation["review_units"]
    seen: dict[str, dict[str, Any]] = {}
    for row in sealed.get("decisions") or []:
        if not isinstance(row, Mapping):
            raise ValueError("SEALED_DECISION_ROW_MUST_BE_OBJECT")
        unit_id = str(row.get("review_unit_id") or "")
        if not unit_id:
            raise ValueError("SEALED_DECISION_WITHOUT_UNIT_ID")
        if unit_id in seen:
            raise ValueError(f"SEALED_DUPLICATE_DECISION:{unit_id}")
        if unit_id not in expected:
            raise ValueError(f"SEALED_UNKNOWN_REVIEW_UNIT:{unit_id}")
        decision = str(row.get("decision") or "")
        if decision not in ALLOWED_DECISIONS:
            raise ValueError(f"SEALED_INVALID_DECISION:{unit_id}:{decision}")
        note = row.get("decision_note")
        if decision == "MANUAL_RECONCILIATION" and not str(note or "").strip():
            raise ValueError(f"SEALED_MANUAL_NOTE_REQUIRED:{unit_id}")
        seen[unit_id] = {
            "review_unit_id": unit_id,
            "decision": decision,
            "decision_note": note,
        }

    missing = sorted(set(expected) - set(seen))
    if missing:
        raise ValueError(f"SEALED_MISSING_DECISIONS:{len(missing)}")
    if len(seen) != packet_validation["review_unit_count"]:
        raise ValueError("SEALED_EXACT_COVERAGE_MISMATCH")

    return {
        "packet_sha256": packet_sha,
        "sealed_manifest_sha256": sealed_sha,
        "packet_validation": packet_validation,
        "decisions": seen,
    }


def _attendance_student_value(
    doc: Mapping[str, Any], student_id: str,
) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for rec in doc.get("records") or []:
        if not isinstance(rec, Mapping):
            continue
        if str(rec.get("student_id") or "").strip() != student_id:
            continue
        values.append({
            "status": rec.get("status"),
            "dependency_id": rec.get("dependency_id"),
        })
    return values


def _current_unit_value(unit: Mapping[str, Any], doc: Mapping[str, Any]) -> Any:
    field = str(unit.get("field_name") or "")
    if (
        unit.get("unit_type") == "ATTENDANCE_STUDENT_DECISION"
        and field == "records.status_or_dependency_id"
    ):
        return _attendance_student_value(doc, str(unit.get("student_id") or ""))
    return doc.get(field)


def _packet_case_pairs(
    packet: Mapping[str, Any],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    for case in packet.get("cases") or []:
        source = str(case.get("source_id") or "")
        target = str(case.get("target_id") or "")
        if not source or not target:
            raise ValueError("P0F5_CASE_WITHOUT_SOURCE_TARGET")
        key = (source, target)
        if key in result:
            raise ValueError(f"P0F5_DUPLICATE_SOURCE_TARGET_PAIR:{source}:{target}")
        result[key] = case
    return result


def _live_case_pairs(
    p0f3_report: Mapping[str, Any],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    for case in p0f3_report.get("cases") or []:
        source = str(case.get("source_id") or "")
        target = str(case.get("target_id") or "")
        if source and target:
            result[(source, target)] = case
    return result


def _semantic_blockers(
    packet: Mapping[str, Any], p0f3_report: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    deterministic_candidates: list[dict[str, Any]] = []
    packet_pairs = _packet_case_pairs(packet)
    live_pairs = _live_case_pairs(p0f3_report)

    scoped_reference_counts: dict[str, dict[str, int]] = {}
    scoped_hard_conflicts = 0
    expected_hard_conflicts = 0
    source_reference_document_candidates = 0

    for pair, pcase in packet_pairs.items():
        source_id, target_id = pair
        live = live_pairs.get(pair)
        group_name = (pcase.get("identity") or {}).get("display_name")
        expected_case_hard = int(pcase.get("p0f4_conflicts") or 0)
        expected_hard_conflicts += expected_case_hard

        if not live:
            blockers.append({
                "reason": "LIVE_DUPLICATE_PAIR_NOT_FOUND",
                "group_name": group_name,
                "source_id": source_id,
                "target_id": target_id,
            })
            continue

        live_hard = int(live.get("hard_conflicts") or 0)
        scoped_hard_conflicts += live_hard
        if live_hard != expected_case_hard:
            blockers.append({
                "reason": "LIVE_HARD_CONFLICT_COUNT_CHANGED",
                "group_name": group_name,
                "source_id": source_id,
                "target_id": target_id,
                "expected": expected_case_hard,
                "current": live_hard,
            })

        unsupported = int(live.get("unsupported_reference_count") or 0)
        if unsupported:
            blockers.append({
                "reason": "UNSUPPORTED_COURSE_REFERENCES_PRESENT",
                "group_name": group_name,
                "source_id": source_id,
                "target_id": target_id,
                "count": unsupported,
            })

        per_collection: dict[str, int] = {}
        for collection, counts in (live.get("reference_counts") or {}).items():
            source_count = int((counts or {}).get(source_id) or 0)
            per_collection[collection] = source_count
            source_reference_document_candidates += source_count
        scoped_reference_counts[group_name or source_id] = dict(sorted(per_collection.items()))

        analyses = live.get("analyses") or {}
        ta = analyses.get("teacher_assignments") or {}
        for classification, count_value in (ta.get("classifications") or {}).items():
            count = int(count_value or 0)
            if not count:
                continue
            if "REQUIRES_REVIEW" in classification:
                blockers.append({
                    "reason": "TEACHER_ASSIGNMENT_SEMANTIC_REVIEW_REQUIRED",
                    "group_name": group_name,
                    "classification": classification,
                    "count": count,
                })
            elif classification == "EXACT_ACTIVE_ASSIGNMENT_DUPLICATE":
                deterministic_candidates.append({
                    "kind": "EXACT_TEACHER_ASSIGNMENT_DEDUPLICATION_CANDIDATE",
                    "group_name": group_name,
                    "count": count,
                })

        tca = analyses.get("teacher_class_assignments") or {}
        for classification, count_value in (tca.get("classifications") or {}).items():
            count = int(count_value or 0)
            if not count:
                continue
            if "REQUIRES_REVIEW" in classification:
                blockers.append({
                    "reason": "TEACHER_CLASS_ASSIGNMENT_REVIEW_REQUIRED",
                    "group_name": group_name,
                    "classification": classification,
                    "count": count,
                })
            elif classification == "EXACT_ASSIGNMENT_DUPLICATE":
                deterministic_candidates.append({
                    "kind": "EXACT_TEACHER_CLASS_ASSIGNMENT_DEDUPLICATION_CANDIDATE",
                    "group_name": group_name,
                    "count": count,
                })

        schedules = analyses.get("class_schedules") or {}
        same_slot = int(schedules.get("same_day_slot_collisions") or 0)
        unresolved_slot = int(schedules.get("unresolved_slot_identities") or 0)
        if same_slot:
            blockers.append({
                "reason": "SCHEDULE_SLOT_COLLISION_REQUIRES_REVIEW",
                "group_name": group_name,
                "count": same_slot,
            })
        if unresolved_slot:
            blockers.append({
                "reason": "SCHEDULE_SLOT_IDENTITY_UNRESOLVED",
                "group_name": group_name,
                "count": unresolved_slot,
            })

        deps = analyses.get("student_dependencies") or {}
        dep_collisions = int(deps.get("collision_items") or 0)
        if dep_collisions:
            blockers.append({
                "reason": "STUDENT_DEPENDENCY_COLLISION_REQUIRES_PLAN",
                "group_name": group_name,
                "count": dep_collisions,
            })

        for collection in ("grades", "attendance", "learning_objects"):
            analysis = analyses.get(collection) or {}
            for classification, count_value in (analysis.get("classifications") or {}).items():
                count = int(count_value or 0)
                if not count:
                    continue
                if classification in {
                    "EXACT_EQUIVALENT",
                    "COMPLEMENTARY_MERGEABLE",
                    "RECORDS_MERGE_COMPATIBLE",
                }:
                    deterministic_candidates.append({
                        "kind": f"{collection.upper()}_{classification}",
                        "group_name": group_name,
                        "count": count,
                    })

    return blockers, deterministic_candidates, {
        "expected_hard_conflicts": expected_hard_conflicts,
        "live_hard_conflicts": scoped_hard_conflicts,
        "source_reference_document_candidates": source_reference_document_candidates,
        "source_reference_counts_by_group": scoped_reference_counts,
    }


def build_preflight(
    packet: Mapping[str, Any],
    sealed: Mapping[str, Any],
    p0f3_report: Mapping[str, Any],
    current_documents: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, Any]:
    chain = validate_chain(packet, sealed)
    decisions = chain["decisions"]

    blockers: list[dict[str, Any]] = []
    intents: list[dict[str, Any]] = []
    cas_documents: dict[tuple[str, str], dict[str, Any]] = {}
    decision_counts = Counter()
    drift_units = 0
    missing_documents = 0
    deterministic_units = 0
    manual_units = 0
    target_change_intents = 0
    target_preserve_intents = 0
    target_write_docs: set[tuple[str, str]] = set()

    for case, conflict, unit in _iter_packet_units(packet):
        unit_id = str(unit.get("review_unit_id") or "")
        decision_row = decisions[unit_id]
        decision = decision_row["decision"]
        decision_counts[decision] += 1
        collection = str(conflict.get("collection") or "")
        if collection not in REVIEW_COLLECTIONS:
            blockers.append({
                "reason": "UNSUPPORTED_REVIEW_COLLECTION",
                "review_unit_id": unit_id,
                "collection": collection,
            })
            continue

        source_ids = [str(v) for v in unit.get("source_document_ids") or []]
        target_ids = [str(v) for v in unit.get("target_document_ids") or []]
        if len(source_ids) != 1 or len(target_ids) != 1:
            blockers.append({
                "reason": "REVIEW_UNIT_DOCUMENT_MULTIPLICITY",
                "review_unit_id": unit_id,
                "source_document_count": len(source_ids),
                "target_document_count": len(target_ids),
            })
            continue

        source_id, target_id = source_ids[0], target_ids[0]
        source_doc = (current_documents.get(collection) or {}).get(source_id)
        target_doc = (current_documents.get(collection) or {}).get(target_id)

        if source_doc is None or target_doc is None:
            missing_documents += 1
            blockers.append({
                "reason": "REVIEW_DOCUMENT_MISSING",
                "review_unit_id": unit_id,
                "collection": collection,
                "source_document_id": source_id,
                "target_document_id": target_id,
                "source_present": source_doc is not None,
                "target_present": target_doc is not None,
            })
            continue

        for role, doc_id, doc in (
            ("source", source_id, source_doc),
            ("target", target_id, target_doc),
        ):
            key = (collection, doc_id)
            existing = cas_documents.setdefault(key, {
                "collection": collection,
                "document_id": doc_id,
                "document_sha256": _canonical_sha256(dict(doc)),
                "roles": set(),
            })
            existing["roles"].add(role)

        current_source_value = _current_unit_value(unit, source_doc)
        current_target_value = _current_unit_value(unit, target_doc)
        source_snapshot = unit.get("source_value")
        target_snapshot = unit.get("target_value")
        source_matches = _normalized(current_source_value) == _normalized(source_snapshot)
        target_matches = _normalized(current_target_value) == _normalized(target_snapshot)

        if not source_matches or not target_matches:
            drift_units += 1
            blockers.append({
                "reason": "REVIEW_UNIT_VALUE_DRIFT",
                "review_unit_id": unit_id,
                "collection": collection,
                "source_document_id": source_id,
                "target_document_id": target_id,
                "source_snapshot_matches": source_matches,
                "target_snapshot_matches": target_matches,
            })

        base_intent = {
            "review_unit_id": unit_id,
            "group_number": case.get("group_number"),
            "group_name": (case.get("identity") or {}).get("display_name"),
            "collection": collection,
            "unit_type": unit.get("unit_type"),
            "field_name": unit.get("field_name"),
            "student_id": unit.get("student_id"),
            "source_document_id": source_id,
            "target_document_id": target_id,
            "source_snapshot_value_sha256": _value_sha256(source_snapshot),
            "target_snapshot_value_sha256": _value_sha256(target_snapshot),
            "source_current_value_sha256": _value_sha256(current_source_value),
            "target_current_value_sha256": _value_sha256(current_target_value),
            "source_document_cas_sha256": cas_documents[(collection, source_id)]["document_sha256"],
            "target_document_cas_sha256": cas_documents[(collection, target_id)]["document_sha256"],
            "decision": decision,
            "database_mutation": False,
        }

        if decision == "MANUAL_RECONCILIATION":
            manual_units += 1
            note = str(decision_row.get("decision_note") or "").strip()
            base_intent.update({
                "intent": "BLOCKED_STRUCTURED_RECONCILIATION_REQUIRED",
                "decision_note_present": bool(note),
                "decision_note_sha256": _value_sha256(note),
                "machine_applicable_value_present": False,
            })
            blockers.append({
                "reason": "MANUAL_RECONCILIATION_REQUIRES_STRUCTURED_VALUE",
                "review_unit_id": unit_id,
                "group_name": (case.get("identity") or {}).get("display_name"),
                "collection": collection,
                "field_name": unit.get("field_name"),
                "source_document_id": source_id,
                "target_document_id": target_id,
                "decision_note_present": bool(note),
                "decision_note_sha256": _value_sha256(note),
            })
        elif decision == "KEEP_SOURCE":
            deterministic_units += 1
            target_change_intents += 1
            target_write_docs.add((collection, target_id))
            base_intent.update({
                "intent": "SET_TARGET_FROM_SOURCE",
                "desired_value_sha256": _value_sha256(source_snapshot),
                "target_change_expected": True,
            })
        elif decision == "KEEP_TARGET":
            deterministic_units += 1
            target_preserve_intents += 1
            base_intent.update({
                "intent": "PRESERVE_TARGET_VALUE",
                "desired_value_sha256": _value_sha256(target_snapshot),
                "target_change_expected": False,
            })
        intents.append(base_intent)

    semantic_blockers, deterministic_semantic, semantic_summary = _semantic_blockers(
        packet, p0f3_report
    )
    blockers.extend(semantic_blockers)

    serialized_cas = []
    for row in cas_documents.values():
        serialized_cas.append({
            **{k: v for k, v in row.items() if k != "roles"},
            "roles": sorted(row["roles"]),
        })
    serialized_cas.sort(key=lambda row: (row["collection"], row["document_id"]))

    blocker_counts = Counter(str(row.get("reason")) for row in blockers)
    executor_readiness = "BLOCKED" if blockers else "READY_FOR_EXECUTOR_DESIGN"
    p0f7_1_required = manual_units > 0

    report: dict[str, Any] = {
        "phase": PHASE_ID,
        "manifest_version": MANIFEST_VERSION,
        "mode": "READ_ONLY_SEALED_DECISIONS_EXECUTION_PREFLIGHT",
        "status": "PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_p0f5_manifest_sha256": chain["packet_sha256"],
        "source_p0f6_decision_manifest_sha256": chain["sealed_manifest_sha256"],
        "summary": {
            "review_units": len(intents),
            "decision_counts": dict(sorted(decision_counts.items())),
            "deterministic_human_decision_units": deterministic_units,
            "manual_reconciliation_units": manual_units,
            "human_target_change_intents": target_change_intents,
            "human_target_preserve_intents": target_preserve_intents,
            "human_target_document_write_candidates": len(target_write_docs),
            "snapshot_drift_units": drift_units,
            "missing_review_documents": missing_documents,
            "cas_documents": len(serialized_cas),
            "semantic_deterministic_candidates": sum(
                int(row.get("count") or 0) for row in deterministic_semantic
            ),
            "source_reference_document_candidates":
                semantic_summary["source_reference_document_candidates"],
            "blockers": len(blockers),
            "blocker_counts": dict(sorted(blocker_counts.items())),
            "executor_readiness": executor_readiness,
            "p0f7_1_structured_manual_reconciliation_required": p0f7_1_required,
            "final_executor_write_count": None,
            "database_mutation": False,
        },
        "semantic_snapshot": {
            **semantic_summary,
            "deterministic_candidates": deterministic_semantic,
        },
        "execution_order_contract": [
            "1_VALIDATE_CHAIN_AND_CAS",
            "2_MATERIALIZE_STRUCTURED_MANUAL_RECONCILIATIONS",
            "3_APPLY_HUMAN_FIELD_RESOLUTIONS_WITH_CAS",
            "4_RESOLVE_NON_HUMAN_SEMANTIC_COLLISIONS",
            "5_REMAP_NON_COLLIDING_SOURCE_COURSE_REFERENCES",
            "6_VERIFY_ZERO_SOURCE_REFERENCES",
            "7_RETIRE_DUPLICATE_SOURCE_COURSES_LAST",
            "8_POST_EXECUTION_AUDIT_AND_RECEIPT",
        ],
        "rollback_contract": {
            "required_before_image_per_written_document": True,
            "required_document_sha256_before_write": True,
            "required_document_sha256_after_write": True,
            "reverse_execution_order": True,
            "source_course_retirement_must_be_last": True,
            "rollback_requires_separate_explicit_authorization": True,
        },
        "safety": {
            "read_only": True,
            "automatic_recommendation": False,
            "automatic_resolution": False,
            "automatic_remap": False,
            "automatic_merge": False,
            "automatic_delete": False,
            "database_mutation": False,
            "production_writes_executed": False,
            "not_authorization_for_executor": True,
            "final_write_count_intentionally_unfinalized_while_blocked": True,
            "sensitive_academic_values_copied_to_report": False,
        },
        "blockers": blockers,
        "human_operation_intents": intents,
        "cas_documents": serialized_cas,
    }
    report["manifest_sha256"] = _canonical_sha256(report)
    return report


async def _load_current_review_documents(
    db: Any, packet: Mapping[str, Any],
) -> dict[str, dict[str, dict[str, Any]]]:
    ids_by_collection: dict[str, set[str]] = defaultdict(set)
    for _, conflict, unit in _iter_packet_units(packet):
        collection = str(conflict.get("collection") or "")
        if collection not in REVIEW_COLLECTIONS:
            continue
        ids_by_collection[collection].update(
            str(v) for v in unit.get("source_document_ids") or [] if v
        )
        ids_by_collection[collection].update(
            str(v) for v in unit.get("target_document_ids") or [] if v
        )

    result: dict[str, dict[str, dict[str, Any]]] = {}
    for collection, ids in ids_by_collection.items():
        rows = await db[collection].find(
            {"id": {"$in": sorted(ids)}}, {"_id": 0}
        ).to_list(len(ids) + 20)
        result[collection] = {
            str(row.get("id")): row for row in rows if row.get("id")
        }
    return result


async def collect_report(
    db: Any,
    *,
    packet_path: Path,
    sealed_path: Path,
    academic_year: int,
    mantenedora_id: str | None,
    audit_history_limit: int,
    collision_example_limit: int,
) -> dict[str, Any]:
    packet = _load_json(packet_path)
    sealed = _load_json(sealed_path)

    # Fail closed before consulting live state.
    validate_chain(packet, sealed)

    p0f3 = _load_module(P0F3_PATH, "p0f3_semantic_collision")
    p0f3.assert_read_only()
    live_p0f3 = await p0f3.collect_report(
        db,
        academic_year=academic_year,
        mantenedora_id=mantenedora_id,
        audit_history_limit=audit_history_limit,
        example_limit=collision_example_limit,
    )
    current_documents = await _load_current_review_documents(db, packet)
    return build_preflight(packet, sealed, live_p0f3, current_documents)


def compact_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "phase": report.get("phase"),
        "mode": report.get("mode"),
        "status": report.get("status"),
        "source_p0f5_manifest_sha256": report.get("source_p0f5_manifest_sha256"),
        "source_p0f6_decision_manifest_sha256":
            report.get("source_p0f6_decision_manifest_sha256"),
        "summary": report.get("summary"),
        "manifest_sha256": report.get("manifest_sha256"),
        "sensitive_payload_printed": False,
        "database_mutation": False,
        "executor_authorized": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="P0-F7 sealed decisions execution preflight, read-only"
    )
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--sealed", required=True, type=Path)
    parser.add_argument("--academic-year", required=True, type=int)
    parser.add_argument("--mantenedora-id")
    parser.add_argument("--audit-history-limit", type=int, default=200)
    parser.add_argument("--collision-example-limit", type=int, default=10000)
    parser.add_argument(
        "--json", dest="json_path", required=True, type=Path,
        help="Arquivo privado obrigatório; detalhes operacionais não vão ao stdout",
    )
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
            packet_path=args.packet,
            sealed_path=args.sealed,
            academic_year=args.academic_year,
            mantenedora_id=args.mantenedora_id,
            audit_history_limit=args.audit_history_limit,
            collision_example_limit=args.collision_example_limit,
        )
    finally:
        client.close()

    _private_write_json(args.json_path, report)
    print(json.dumps(compact_summary(report), ensure_ascii=False, indent=2, default=str))
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
