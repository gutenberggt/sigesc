"""Segunda Onda DVD 2D-A.1 — pacote de validação humana da fonte de horário.

Etapa estritamente READ-ONLY no MongoDB. Não corrige class_schedules, não cria DVD,
não aceita decisão humana por argumento e não possui apply/rollback.

Objetivo: transformar a auditoria forense 2D-A em um snapshot estável, com hash de
evidência e uma única pergunta institucional sobre o 3º horário do 5º ANO A.
Qualquer mudança nas evidências exige novo pacote e nova validação.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from scripts import audit_dvd_second_wave_2d_a_forensics as forensic  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

VALIDATION_ID = "DVD-SECOND-WAVE-2D-A1-5A-SLOT3-2026"
CANDIDATE_SLOT = 3
CANDIDATE_PAIR = ("09:30", "10:30")
HISTORICAL_CONSISTENT_PAIR = ("09:15", "09:30")
CURRENT_INVALID_PAIR = ("09:30", "09:30")
EXPECTED_RECOVERY_STATE = "time_pattern_ambiguous_school_shift"
EXPECTED_FORENSIC_CLASSIFICATION = "HISTORICAL_SOURCE_CANDIDATE_REQUIRES_REVIEW"
EXPECTED_TARGET_COUNT = 2

QUESTION = (
    "A unidade escolar confirma que, para o 5º ANO A, turno matutino, ano letivo "
    "2026, o 3º horário institucional de aula é das 09:30 às 10:30?"
)

RESPONSE_OPTIONS = (
    "CONFIRMADO_09_30_10_30",
    "NEGADO",
    "OUTRO_HORARIO",
)

MONGO_MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
)


class SourceValidationGateError(RuntimeError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _sha256_value(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def assert_script_read_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    executable = "\n".join(
        line
        for line in source.splitlines()
        if not line.lstrip().startswith('"')
        and "MONGO_MUTATOR_TOKENS" not in line
    )
    hits = [token for token in MONGO_MUTATOR_TOKENS if token in executable]
    if hits:
        raise SourceValidationGateError(
            f"READ_ONLY_GUARD_FAILED forbidden={hits}"
        )


def _pair(value: Mapping[str, Any] | None) -> tuple[str, str] | None:
    if not isinstance(value, Mapping):
        return None
    start = str(value.get("start") or "")
    end = str(value.get("end") or "")
    if not start or not end:
        return None
    return start, end


def _slot_pair_from_signature(signature: Any, slot: int) -> tuple[str, str] | None:
    if not isinstance(signature, list):
        return None
    for row in signature:
        if isinstance(row, list) and len(row) >= 3 and row[0] == slot:
            return str(row[1]), str(row[2])
    return None


def _historical_consistent_pairs(target: Mapping[str, Any]) -> dict[tuple[str, str], list[str]]:
    pairs: dict[tuple[str, str], list[str]] = {}
    for item in target.get("historical_snapshots") or []:
        analysis = item.get("analysis") or {}
        if analysis.get("complete") is not True:
            continue
        if analysis.get("conflicts"):
            continue
        pair = _slot_pair_from_signature(analysis.get("signature"), CANDIDATE_SLOT)
        if pair is None:
            continue
        pairs.setdefault(pair, []).append(str(item.get("timestamp") or ""))
    return pairs


def _latest_invalid_pair(target: Mapping[str, Any]) -> tuple[str, str] | None:
    found: list[tuple[str, tuple[str, str]]] = []
    for item in target.get("historical_snapshots") or []:
        changes = item.get("changes") or {}
        slot_times = changes.get("slot_times") or {}
        new_value = slot_times.get("new") or {}
        raw = new_value.get(str(CANDIDATE_SLOT)) or new_value.get(CANDIDATE_SLOT)
        pair = _pair(raw)
        if pair and pair[0] >= pair[1]:
            found.append((str(item.get("timestamp") or ""), pair))
    if not found:
        return None
    found.sort(key=lambda row: row[0])
    return found[-1][1]


def _donor_candidate_evidence(target: Mapping[str, Any]) -> dict[str, Any]:
    patterns = target.get("donor_patterns") or []
    if not patterns:
        raise SourceValidationGateError("DONOR_PATTERNS_MISSING")

    pairs: set[tuple[str, str]] = set()
    donors: list[dict[str, Any]] = []
    for pattern in patterns:
        pair = _pair((pattern.get("pattern") or {}).get(str(CANDIDATE_SLOT)))
        if pair is None:
            raise SourceValidationGateError("DONOR_SLOT3_PAIR_MISSING")
        pairs.add(pair)
        for donor in pattern.get("donors") or []:
            donors.append(
                {
                    "class_id": donor.get("class_id"),
                    "class_name": donor.get("class_name"),
                    "program": donor.get("program"),
                    "pattern_slot3": {"start": pair[0], "end": pair[1]},
                }
            )

    if pairs != {CANDIDATE_PAIR}:
        raise SourceValidationGateError(
            f"DONOR_SLOT3_NOT_UNANIMOUS expected={CANDIDATE_PAIR} actual={sorted(pairs)}"
        )
    if not donors:
        raise SourceValidationGateError("DONOR_COMPLETE_SCHEDULES_MISSING")

    donors.sort(
        key=lambda row: (
            str(row.get("class_name") or ""),
            str(row.get("class_id") or ""),
        )
    )
    return {
        "pair": {"start": CANDIDATE_PAIR[0], "end": CANDIDATE_PAIR[1]},
        "complete_schedule_count": len(donors),
        "donors": donors,
        "full_pattern_count": len(patterns),
    }


def _target_summary(legacy_id: str, target: Mapping[str, Any]) -> dict[str, Any]:
    current = target.get("current_schedule_analysis") or {}
    classification = target.get("forensic_classification") or {}

    if target.get("recovery_state_38d") != EXPECTED_RECOVERY_STATE:
        raise SourceValidationGateError(
            f"RECOVERY_STATE_DRIFT legacy={legacy_id} actual={target.get('recovery_state_38d')}"
        )
    if classification.get("classification") != EXPECTED_FORENSIC_CLASSIFICATION:
        raise SourceValidationGateError(
            "FORENSIC_CLASSIFICATION_DRIFT "
            f"legacy={legacy_id} actual={classification.get('classification')}"
        )
    if classification.get("automatic_action") is not False:
        raise SourceValidationGateError(
            f"FORENSIC_AUTOMATIC_ACTION_UNSAFE legacy={legacy_id}"
        )
    if current.get("complete") is not False:
        raise SourceValidationGateError(
            f"CURRENT_SCHEDULE_UNEXPECTEDLY_COMPLETE legacy={legacy_id}"
        )
    if current.get("required_slots") != [1, 2, 3, 4]:
        raise SourceValidationGateError(
            f"REQUIRED_SLOTS_DRIFT legacy={legacy_id} actual={current.get('required_slots')}"
        )
    if current.get("missing_slots") != [CANDIDATE_SLOT]:
        raise SourceValidationGateError(
            f"MISSING_SLOT_DRIFT legacy={legacy_id} actual={current.get('missing_slots')}"
        )

    donor = _donor_candidate_evidence(target)
    historical_pairs = _historical_consistent_pairs(target)
    if set(historical_pairs) != {HISTORICAL_CONSISTENT_PAIR}:
        raise SourceValidationGateError(
            "HISTORICAL_CONSISTENT_PAIR_DRIFT "
            f"legacy={legacy_id} actual={sorted(historical_pairs)}"
        )

    invalid_pair = _latest_invalid_pair(target)
    if invalid_pair != CURRENT_INVALID_PAIR:
        raise SourceValidationGateError(
            f"CURRENT_INVALID_PAIR_DRIFT legacy={legacy_id} actual={invalid_pair}"
        )

    return {
        "legacy_assignment_id": legacy_id,
        "component_id": target.get("component_id"),
        "component_name": target.get("component_name"),
        "workload": target.get("workload"),
        "recovery_state_38d": target.get("recovery_state_38d"),
        "forensic_classification": classification.get("classification"),
        "current_missing_slot": CANDIDATE_SLOT,
        "donor_slot3_consensus": donor,
        "historical_conflict_free_slot3": {
            "start": HISTORICAL_CONSISTENT_PAIR[0],
            "end": HISTORICAL_CONSISTENT_PAIR[1],
            "timestamps": sorted(historical_pairs[HISTORICAL_CONSISTENT_PAIR]),
        },
        "latest_invalid_slot3": {
            "start": invalid_pair[0],
            "end": invalid_pair[1],
        },
    }


def build_validation_packet(report: Mapping[str, Any]) -> dict[str, Any]:
    assert_script_read_only()

    meta = report.get("meta") or {}
    scope = report.get("scope") or {}
    targets = report.get("targets") or {}

    if meta.get("mutates_database") is not False:
        raise SourceValidationGateError("FORENSIC_REPORT_NOT_READ_ONLY")
    if int(report.get("existing_target_dvd_count") or 0) != 0:
        raise SourceValidationGateError(
            f"EXISTING_TARGET_DVD_PRESENT count={report.get('existing_target_dvd_count')}"
        )
    if len(targets) != EXPECTED_TARGET_COUNT or set(targets) != set(forensic.TARGETS):
        raise SourceValidationGateError(
            f"TARGET_SET_DRIFT expected={sorted(forensic.TARGETS)} actual={sorted(targets)}"
        )

    expected_scope = {
        "teacher_user_id": forensic.TEACHER_USER_ID,
        "staff_id": forensic.STAFF_ID,
        "school_id": forensic.SCHOOL_ID,
        "class_id": forensic.CLASS_ID,
        "class_name": forensic.EXPECTED_CLASS_NAME,
        "shift": forensic.EXPECTED_SHIFT,
        "slots_per_day": forensic.EXPECTED_SLOTS_PER_DAY,
    }
    for key, expected in expected_scope.items():
        if scope.get(key) != expected:
            raise SourceValidationGateError(
                f"SCOPE_DRIFT field={key} expected={expected!r} actual={scope.get(key)!r}"
            )

    current_consensus = report.get("current_schedule_consensus") or {}
    expected_consensus = {
        "1": {"start": "07:08", "end": "08:00"},
        "2": {"start": "08:00", "end": "09:00"},
        "4": {"start": "10:30", "end": "11:15"},
    }
    if current_consensus != expected_consensus:
        raise SourceValidationGateError(
            f"CURRENT_CONSENSUS_DRIFT actual={_canonical(current_consensus)}"
        )

    target_summaries = {
        legacy_id: _target_summary(legacy_id, targets[legacy_id])
        for legacy_id in sorted(targets)
    }

    donor_pairs = {
        _canonical(summary["donor_slot3_consensus"]["pair"])
        for summary in target_summaries.values()
    }
    historical_pairs = {
        _canonical(
            {
                "start": summary["historical_conflict_free_slot3"]["start"],
                "end": summary["historical_conflict_free_slot3"]["end"],
            }
        )
        for summary in target_summaries.values()
    }
    invalid_pairs = {
        _canonical(summary["latest_invalid_slot3"])
        for summary in target_summaries.values()
    }
    if len(donor_pairs) != 1 or len(historical_pairs) != 1 or len(invalid_pairs) != 1:
        raise SourceValidationGateError("TARGET_EVIDENCE_NOT_IDENTICAL")

    evidence_core = {
        "validation_id": VALIDATION_ID,
        "scope": {
            "academic_year": forensic.ACADEMIC_YEAR,
            "teacher_user_id": forensic.TEACHER_USER_ID,
            "staff_id": forensic.STAFF_ID,
            "teacher_name": scope.get("teacher_name"),
            "school_id": forensic.SCHOOL_ID,
            "class_id": forensic.CLASS_ID,
            "class_name": forensic.EXPECTED_CLASS_NAME,
            "shift": forensic.EXPECTED_SHIFT,
            "schedule_id": scope.get("schedule_id"),
            "slots_per_day": forensic.EXPECTED_SLOTS_PER_DAY,
        },
        "source_snapshot": {
            "current_schedule_created_at": scope.get("current_schedule_created_at"),
            "current_schedule_updated_at": scope.get("current_schedule_updated_at"),
            "current_schedule_consensus": current_consensus,
            "audit_log_count": report.get("audit_log_count"),
            "audit_snapshot_count": report.get("audit_snapshot_count"),
            "donor_schedule_count": report.get("donor_schedule_count"),
            "existing_target_dvd_count": report.get("existing_target_dvd_count"),
        },
        "candidate": {
            "slot": CANDIDATE_SLOT,
            "start": CANDIDATE_PAIR[0],
            "end": CANDIDATE_PAIR[1],
            "status": "REQUIRES_INSTITUTIONAL_CONFIRMATION",
        },
        "known_conflicting_evidence": {
            "historical_conflict_free_pair": {
                "start": HISTORICAL_CONSISTENT_PAIR[0],
                "end": HISTORICAL_CONSISTENT_PAIR[1],
            },
            "latest_invalid_pair": {
                "start": CURRENT_INVALID_PAIR[0],
                "end": CURRENT_INVALID_PAIR[1],
            },
        },
        "targets": target_summaries,
        "question": QUESTION,
        "response_options": list(RESPONSE_OPTIONS),
        "automatic_action": False,
    }

    return {
        "meta": {
            "mode": "SECOND_WAVE_2D_A1_SOURCE_VALIDATION_READ_ONLY",
            "mutates_database": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "evidence_sha256": _sha256_value(evidence_core),
        "evidence": evidence_core,
    }


def print_compact(packet: Mapping[str, Any]) -> None:
    evidence = packet["evidence"]
    candidate = evidence["candidate"]
    snapshot = evidence["source_snapshot"]
    print("=== DVD SEGUNDA ONDA 2D-A.1 — SOURCE VALIDATION READ-ONLY ===")
    print("VALIDATION_ID:", evidence["validation_id"])
    print("EVIDENCE_SHA256:", packet["evidence_sha256"])
    print("TEACHER:", evidence["scope"].get("teacher_name"))
    print("CLASS:", evidence["scope"].get("class_name"))
    print("SCHEDULE_ID:", evidence["scope"].get("schedule_id"))
    print("SCHEDULE_UPDATED_AT:", snapshot.get("current_schedule_updated_at"))
    print("CANDIDATE_SLOT:", candidate["slot"])
    print("CANDIDATE_TIME:", f"{candidate['start']}-{candidate['end']}")
    print(
        "HISTORICAL_CONFLICT_FREE_TIME:",
        f"{HISTORICAL_CONSISTENT_PAIR[0]}-{HISTORICAL_CONSISTENT_PAIR[1]}",
    )
    print(
        "LATEST_INVALID_TIME:",
        f"{CURRENT_INVALID_PAIR[0]}-{CURRENT_INVALID_PAIR[1]}",
    )
    for legacy_id, target in evidence["targets"].items():
        donor = target["donor_slot3_consensus"]
        print("---")
        print("LEGACY:", legacy_id)
        print("COMPONENT:", target["component_name"])
        print("DONOR_SLOT3_COMPLETE_SCHEDULES:", donor["complete_schedule_count"])
        print("DONOR_SLOT3_FULL_PATTERNS:", donor["full_pattern_count"])
        print("DONOR_SLOT3_CONSENSUS:", f"{CANDIDATE_PAIR[0]}-{CANDIDATE_PAIR[1]}")
        print("FORENSIC_CLASSIFICATION:", target["forensic_classification"])
    print("QUESTION:", evidence["question"])
    print("RESPONSE_OPTIONS:", ", ".join(evidence["response_options"]))
    print("RESPONSE_REQUIRED: SIM")
    print("MONGO_WRITES: 0")
    print("AUTOMATIC_ACTION: NAO")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args()

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        db = client[os.environ.get("DB_NAME", "sigesc")]
        report = await forensic.collect_forensics(db)
        packet = build_validation_packet(report)
        print_compact(packet)
        if args.json_path:
            path = Path(args.json_path)
            path.write_text(
                json.dumps(packet, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            print("JSON_LOCAL:", path)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
