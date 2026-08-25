"""Segunda Onda DVD 2D-A — auditoria forense READ-ONLY de Abadia Alves Martins.

Escopo fixo:
- Abadia Alves Martins;
- 5º ANO A / 2026;
- Língua Portuguesa e Matemática;
- investigação de horário ambíguo, sem criar DVD e sem alterar class_schedules.

Fontes examinadas:
1. class_schedule atual da própria turma;
2. histórico auditável em audit_logs para class_schedules, reconstruindo before/after;
3. class_schedules do mesmo ano/escola/turno como evidência comparativa.

Nenhuma conclusão de correção é aplicada automaticamente. Um padrão histórico
completo e compatível pode ser classificado como evidência candidata; qualquer
ambiguidade ou conflito mantém o caso bloqueado para validação humana.
"""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from collections import defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from scripts.audit_dvd_schedule_recovery import (  # noqa: E402
    classify_time_recovery,
    pattern_signature,
    required_slot_numbers,
    schedule_time_consensus,
)

load_dotenv(BACKEND_DIR / ".env")

ACADEMIC_YEAR = 2026
TEACHER_USER_ID = "3d7b951f-0430-49d3-b090-9eda9fd730d7"
STAFF_ID = "90877172-bf65-4e63-a8d2-431dee5b63dd"
SCHOOL_ID = "736ea4a8-60ff-4fe0-9dcd-fa9ab6b76d29"
CLASS_ID = "5a0fe91e-1d61-4787-adf7-b9bc1ffb07a3"
EXPECTED_CLASS_NAME = "5º ANO A"
EXPECTED_SHIFT = "morning"
EXPECTED_SLOTS_PER_DAY = 4

TARGETS = {
    "62235d46-558f-4be0-8e48-397b4fbe5ed5": {
        "component_id": "cf7c3475-98b8-47a2-9fc8-b7b17f1f0b39",
        "component_name": "Matemática",
        "workload": 4,
    },
    "14939b59-9571-4a16-8ed1-14798876c454": {
        "component_id": "dcf9943c-e507-41e9-87bc-dc9b1bb9ba86",
        "component_name": "Língua Portuguesa",
        "workload": 4,
    },
}

MONGO_MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
)


class ForensicGateError(RuntimeError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def assert_script_read_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    executable = "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith('"') and "MONGO_MUTATOR_TOKENS" not in line
    )
    hits = [token for token in MONGO_MUTATOR_TOKENS if token in executable]
    if hits:
        raise ForensicGateError(f"READ_ONLY_GUARD_FAILED forbidden={hits}")
    if "--apply" in source or "--rollback" in source:
        raise ForensicGateError("READ_ONLY_GUARD_FAILED mutation_mode_present")


def _clean_doc(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    doc = dict(value)
    doc.pop("_id", None)
    return doc


def _is_target_schedule_doc(doc: Mapping[str, Any]) -> bool:
    return (
        str(doc.get("class_id") or "") == CLASS_ID
        and str(doc.get("academic_year") or "") in {"", str(ACADEMIC_YEAR)}
    )


def reconstruct_audit_snapshots(
    logs: list[Mapping[str, Any]],
    *,
    current_schedule_id: Optional[str],
) -> list[dict[str, Any]]:
    """Reconstrói snapshots completos quando old_value/new_value permitem.

    O endpoint de update usa $set e registra old_value completo + new_value parcial.
    Portanto o estado posterior pode ser reconstruído aplicando new_value sobre o
    old_value. Create usa new_value; delete usa old_value.
    """
    snapshots: list[dict[str, Any]] = []

    def add_snapshot(
        doc: Mapping[str, Any],
        *,
        log: Mapping[str, Any],
        side: str,
    ) -> None:
        clean = _clean_doc(doc)
        if not _is_target_schedule_doc(clean):
            return
        snapshots.append(
            {
                "source": "audit_log",
                "side": side,
                "action": log.get("action"),
                "timestamp": log.get("timestamp_utc") or log.get("timestamp"),
                "user_id": log.get("user_id"),
                "user_name": log.get("user_name"),
                "user_email": log.get("user_email"),
                "document_id": log.get("document_id"),
                "changes": log.get("changes"),
                "schedule": clean,
            }
        )

    ordered = sorted(
        logs,
        key=lambda row: str(row.get("timestamp_utc") or row.get("timestamp") or ""),
    )
    for log in ordered:
        document_id = str(log.get("document_id") or "")
        old_value = _clean_doc(log.get("old_value"))
        new_value = _clean_doc(log.get("new_value"))
        relevant = (
            (current_schedule_id and document_id == current_schedule_id)
            or _is_target_schedule_doc(old_value)
            or _is_target_schedule_doc(new_value)
        )
        if not relevant:
            continue

        action = str(log.get("action") or "")
        if action == "create":
            add_snapshot(new_value, log=log, side="create_after")
        elif action == "update":
            if _is_target_schedule_doc(old_value):
                add_snapshot(old_value, log=log, side="update_before")
                after = deepcopy(old_value)
                after.update(new_value)
                add_snapshot(after, log=log, side="update_after")
            elif current_schedule_id and document_id == current_schedule_id:
                # Sem old_value completo não inventamos o restante do documento.
                add_snapshot(new_value, log=log, side="update_partial")
        elif action == "delete":
            add_snapshot(old_value, log=log, side="delete_before")

    # Remove duplicatas estruturais, preservando o primeiro contexto auditável.
    dedup: dict[str, dict[str, Any]] = {}
    for item in snapshots:
        key = _canonical(item.get("schedule") or {})
        dedup.setdefault(key, item)
    return list(dedup.values())


def analyze_schedule_snapshot(
    schedule: Mapping[str, Any],
    *,
    component_id: str,
    current_consensus: Mapping[int, tuple[str, str]],
) -> dict[str, Any]:
    required = required_slot_numbers(schedule, component_id)
    consensus = schedule_time_consensus(schedule)
    signature = pattern_signature(consensus, required)
    missing = sorted(required - set(consensus))

    overlap = sorted(required & set(current_consensus) & set(consensus))
    conflicts = [
        {
            "slot": n,
            "current": {
                "start": current_consensus[n][0],
                "end": current_consensus[n][1],
            },
            "snapshot": {"start": consensus[n][0], "end": consensus[n][1]},
        }
        for n in overlap
        if consensus[n] != current_consensus[n]
    ]
    matches = [n for n in overlap if consensus[n] == current_consensus[n]]

    return {
        "required_slots": sorted(required),
        "consensus": {
            str(n): {"start": pair[0], "end": pair[1]}
            for n, pair in sorted(consensus.items())
        },
        "complete": signature is not None,
        "signature": [list(x) for x in signature] if signature is not None else None,
        "missing_slots": missing,
        "overlap_slots": overlap,
        "matching_overlap_slots": matches,
        "conflicts": conflicts,
    }


def group_donor_patterns(
    donor_schedules: list[Mapping[str, Any]],
    *,
    component_id: str,
    current_consensus: Mapping[int, tuple[str, str]],
    class_by_id: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    groups: dict[tuple, dict[str, Any]] = {}
    for donor in donor_schedules:
        analysis = analyze_schedule_snapshot(
            donor,
            component_id=component_id,
            current_consensus=current_consensus,
        )
        signature_raw = analysis.get("signature")
        if not signature_raw:
            continue
        signature = tuple(tuple(x) for x in signature_raw)
        group = groups.setdefault(
            signature,
            {
                "signature": signature_raw,
                "pattern": {
                    str(x[0]): {"start": x[1], "end": x[2]}
                    for x in signature
                },
                "donors": [],
                "zero_conflict_donors": 0,
            },
        )
        class_id = str(donor.get("class_id") or "")
        klass = class_by_id.get(class_id) or {}
        conflicts = analysis.get("conflicts") or []
        if not conflicts:
            group["zero_conflict_donors"] += 1
        group["donors"].append(
            {
                "class_id": class_id,
                "class_name": klass.get("name"),
                "program": klass.get("atendimento_programa") or klass.get("programa"),
                "overlap_slots": analysis.get("overlap_slots"),
                "matching_overlap_slots": analysis.get("matching_overlap_slots"),
                "conflicts": conflicts,
            }
        )

    result = list(groups.values())
    for group in result:
        group["donors"].sort(key=lambda x: (str(x.get("class_name") or ""), str(x.get("class_id") or "")))
    result.sort(key=lambda x: (-len(x["donors"]), _canonical(x["signature"])))
    return result


def classify_forensic_evidence(
    historical_analyses: list[Mapping[str, Any]],
    donor_patterns: list[Mapping[str, Any]],
) -> dict[str, Any]:
    historical_complete = [row for row in historical_analyses if row.get("analysis", {}).get("complete")]
    historical_consistent = [
        row for row in historical_complete
        if not (row.get("analysis", {}).get("conflicts") or [])
    ]
    hist_signatures = {
        _canonical(row.get("analysis", {}).get("signature"))
        for row in historical_consistent
        if row.get("analysis", {}).get("signature")
    }
    donor_zero_conflict = sum(int(row.get("zero_conflict_donors") or 0) for row in donor_patterns)

    if len(hist_signatures) == 1:
        return {
            "classification": "HISTORICAL_SOURCE_CANDIDATE_REQUIRES_REVIEW",
            "historical_consistent_complete_patterns": 1,
            "donor_zero_conflict_count": donor_zero_conflict,
            "automatic_action": False,
        }
    if len(hist_signatures) > 1:
        return {
            "classification": "BLOCKED_HISTORICAL_SOURCE_AMBIGUOUS",
            "historical_consistent_complete_patterns": len(hist_signatures),
            "donor_zero_conflict_count": donor_zero_conflict,
            "automatic_action": False,
        }
    if historical_complete:
        return {
            "classification": "BLOCKED_HISTORICAL_SOURCE_CONFLICTS_CURRENT",
            "historical_consistent_complete_patterns": 0,
            "historical_complete_conflicting_snapshots": len(historical_complete),
            "donor_zero_conflict_count": donor_zero_conflict,
            "automatic_action": False,
        }
    if len(donor_patterns) > 1:
        return {
            "classification": "BLOCKED_SOURCE_SCHEDULE_REQUIRES_VALIDATION",
            "historical_consistent_complete_patterns": 0,
            "donor_pattern_count": len(donor_patterns),
            "donor_zero_conflict_count": donor_zero_conflict,
            "automatic_action": False,
        }
    if len(donor_patterns) == 1 and donor_zero_conflict > 0:
        return {
            "classification": "DONOR_SOURCE_CANDIDATE_REQUIRES_REVIEW",
            "historical_consistent_complete_patterns": 0,
            "donor_pattern_count": 1,
            "donor_zero_conflict_count": donor_zero_conflict,
            "automatic_action": False,
        }
    return {
        "classification": "BLOCKED_NO_UNEQUIVOCAL_SOURCE_EVIDENCE",
        "historical_consistent_complete_patterns": 0,
        "donor_pattern_count": len(donor_patterns),
        "donor_zero_conflict_count": donor_zero_conflict,
        "automatic_action": False,
    }


async def collect_forensics(db) -> dict[str, Any]:
    assert_script_read_only()

    teacher = await db.users.find_one(
        {"id": TEACHER_USER_ID},
        {"_id": 0, "id": 1, "full_name": 1, "name": 1, "email": 1},
    )
    staff = await db.staff.find_one(
        {"id": STAFF_ID},
        {"_id": 0, "id": 1, "user_id": 1, "full_name": 1, "nome": 1, "email": 1},
    )
    klass = await db.classes.find_one({"id": CLASS_ID}, {"_id": 0})
    if not teacher or not staff or not klass:
        raise ForensicGateError("IDENTITY_OR_CLASS_NOT_FOUND")
    if str(klass.get("school_id") or "") != SCHOOL_ID:
        raise ForensicGateError("CLASS_SCHOOL_MISMATCH")
    if str(klass.get("name") or "") != EXPECTED_CLASS_NAME:
        raise ForensicGateError(f"CLASS_NAME_DRIFT actual={klass.get('name')!r}")
    if str(klass.get("shift") or "") != EXPECTED_SHIFT:
        raise ForensicGateError(f"CLASS_SHIFT_DRIFT actual={klass.get('shift')!r}")
    if staff.get("user_id") and str(staff.get("user_id")) != TEACHER_USER_ID:
        raise ForensicGateError("STAFF_USER_ID_MISMATCH")

    schedules = await db.class_schedules.find(
        {"class_id": CLASS_ID, "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}},
        {"_id": 0},
    ).to_list(10)
    if len(schedules) != 1:
        raise ForensicGateError(f"TARGET_SCHEDULE_NOT_UNIQUE count={len(schedules)}")
    current = schedules[0]
    if int(current.get("slots_per_day") or 0) != EXPECTED_SLOTS_PER_DAY:
        raise ForensicGateError(f"TARGET_SLOTS_PER_DAY_DRIFT actual={current.get('slots_per_day')}")
    schedule_id = str(current.get("id") or "")

    target_component_ids = {str(spec["component_id"]) for spec in TARGETS.values()}
    legacy_ids = sorted(TARGETS)
    legacy_rows = await db.teacher_assignments.find(
        {
            "id": {"$in": legacy_ids},
            "staff_id": STAFF_ID,
            "class_id": CLASS_ID,
            "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]},
            "status": "ativo",
        },
        {"_id": 0},
    ).to_list(10)
    legacy_by_id = {str(row.get("id") or ""): row for row in legacy_rows if row.get("id")}
    if set(legacy_by_id) != set(legacy_ids):
        raise ForensicGateError("TARGET_LEGACY_SET_MISMATCH")

    course_rows = await db.courses.find(
        {"id": {"$in": sorted(target_component_ids)}},
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(10)
    course_names = {str(row.get("id")): str(row.get("name") or "") for row in course_rows if row.get("id")}

    school_classes = await db.classes.find(
        {"school_id": SCHOOL_ID, "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}},
        {"_id": 0, "id": 1, "name": 1, "school_id": 1, "shift": 1, "atendimento_programa": 1, "programa": 1},
    ).to_list(1000)
    class_by_id = {str(row.get("id")): row for row in school_classes if row.get("id")}

    donor_schedules_all = await db.class_schedules.find(
        {"school_id": SCHOOL_ID, "academic_year": {"$in": [ACADEMIC_YEAR, str(ACADEMIC_YEAR)]}},
        {"_id": 0},
    ).to_list(1000)
    donors = []
    for row in donor_schedules_all:
        cid = str(row.get("class_id") or "")
        if cid == CLASS_ID:
            continue
        donor_class = class_by_id.get(cid) or {}
        shift = str(row.get("shift") or donor_class.get("shift") or "")
        if shift == EXPECTED_SHIFT:
            donors.append(row)

    # audit_logs pode conter IDs antigos caso a grade tenha sido removida/recriada.
    audit_logs_raw = await db.audit_logs.find(
        {"collection": "class_schedules", "academic_year": ACADEMIC_YEAR},
        {"_id": 0},
    ).sort("timestamp", 1).to_list(10000)
    relevant_logs = []
    for log in audit_logs_raw:
        old_value = _clean_doc(log.get("old_value"))
        new_value = _clean_doc(log.get("new_value"))
        if (
            str(log.get("document_id") or "") == schedule_id
            or _is_target_schedule_doc(old_value)
            or _is_target_schedule_doc(new_value)
        ):
            relevant_logs.append(log)
    snapshots = reconstruct_audit_snapshots(relevant_logs, current_schedule_id=schedule_id)

    existing_dvd = await db.teacher_class_assignments.find(
        {
            "teacher_id": TEACHER_USER_ID,
            "class_id": CLASS_ID,
            "component_id": {"$in": sorted(target_component_ids)},
            "deleted": {"$ne": True},
        },
        {"_id": 0, "id": 1, "teacher_id": 1, "class_id": 1, "component_id": 1, "diary_settings": 1, "source": 1},
    ).to_list(100)

    current_consensus = schedule_time_consensus(current)
    targets_report: dict[str, Any] = {}
    for legacy_id, spec in TARGETS.items():
        component_id = str(spec["component_id"])
        source = legacy_by_id[legacy_id]
        if str(source.get("course_id") or "") != component_id:
            raise ForensicGateError(f"COMPONENT_ID_DRIFT legacy={legacy_id}")
        if course_names.get(component_id) != spec["component_name"]:
            raise ForensicGateError(
                f"COMPONENT_NAME_DRIFT legacy={legacy_id} actual={course_names.get(component_id)!r}"
            )
        try:
            workload = int(source.get("carga_horaria_semanal"))
        except (TypeError, ValueError) as exc:
            raise ForensicGateError(f"WORKLOAD_INVALID legacy={legacy_id}") from exc
        if workload != int(spec["workload"]):
            raise ForensicGateError(f"WORKLOAD_DRIFT legacy={legacy_id} actual={workload}")

        current_analysis = analyze_schedule_snapshot(
            current,
            component_id=component_id,
            current_consensus=current_consensus,
        )
        donor_state, donor_state_evidence = classify_time_recovery(
            target_schedule=current,
            course_id=component_id,
            donor_schedules=donors,
        )
        donor_patterns = group_donor_patterns(
            donors,
            component_id=component_id,
            current_consensus=current_consensus,
            class_by_id=class_by_id,
        )

        historical_analyses = []
        for snapshot in snapshots:
            analysis = analyze_schedule_snapshot(
                snapshot["schedule"],
                component_id=component_id,
                current_consensus=current_consensus,
            )
            # Mantém apenas snapshots em que o componente realmente aparece.
            if analysis["required_slots"]:
                historical_analyses.append(
                    {
                        "timestamp": snapshot.get("timestamp"),
                        "action": snapshot.get("action"),
                        "side": snapshot.get("side"),
                        "document_id": snapshot.get("document_id"),
                        "user_id": snapshot.get("user_id"),
                        "user_name": snapshot.get("user_name"),
                        "user_email": snapshot.get("user_email"),
                        "changes": snapshot.get("changes"),
                        "analysis": analysis,
                    }
                )

        forensic_classification = classify_forensic_evidence(
            historical_analyses,
            donor_patterns,
        )
        targets_report[legacy_id] = {
            "legacy_assignment_id": legacy_id,
            "component_id": component_id,
            "component_name": spec["component_name"],
            "workload": workload,
            "current_schedule_analysis": current_analysis,
            "recovery_state_38d": donor_state,
            "recovery_evidence_38d": donor_state_evidence,
            "historical_snapshots": historical_analyses,
            "donor_patterns": donor_patterns,
            "forensic_classification": forensic_classification,
        }

    return {
        "meta": {
            "mode": "SECOND_WAVE_2D_A_FORENSICS_READ_ONLY",
            "mutates_database": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "academic_year": ACADEMIC_YEAR,
        },
        "scope": {
            "teacher_user_id": TEACHER_USER_ID,
            "staff_id": STAFF_ID,
            "teacher_name": teacher.get("full_name") or teacher.get("name") or staff.get("nome"),
            "school_id": SCHOOL_ID,
            "class_id": CLASS_ID,
            "class_name": klass.get("name"),
            "shift": klass.get("shift"),
            "program": klass.get("atendimento_programa") or klass.get("programa"),
            "schedule_id": schedule_id,
            "slots_per_day": current.get("slots_per_day"),
            "current_schedule_created_at": current.get("created_at"),
            "current_schedule_updated_at": current.get("updated_at"),
        },
        "current_schedule_consensus": {
            str(n): {"start": pair[0], "end": pair[1]}
            for n, pair in sorted(current_consensus.items())
        },
        "audit_log_count": len(relevant_logs),
        "audit_snapshot_count": len(snapshots),
        "donor_schedule_count": len(donors),
        "existing_target_dvd_count": len(existing_dvd),
        "existing_target_dvd": existing_dvd,
        "targets": targets_report,
    }


def print_compact(report: Mapping[str, Any]) -> None:
    scope = report["scope"]
    print("=== DVD SEGUNDA ONDA 2D-A — FORENSICS READ-ONLY ===")
    print("TEACHER:", scope.get("teacher_name"))
    print("CLASS:", scope.get("class_name"))
    print("SCHOOL_ID:", scope.get("school_id"))
    print("CLASS_ID:", scope.get("class_id"))
    print("SCHEDULE_ID:", scope.get("schedule_id"))
    print("SHIFT:", scope.get("shift"))
    print("PROGRAM:", scope.get("program"))
    print("SLOTS_PER_DAY:", scope.get("slots_per_day"))
    print("CURRENT_SCHEDULE_CREATED_AT:", scope.get("current_schedule_created_at"))
    print("CURRENT_SCHEDULE_UPDATED_AT:", scope.get("current_schedule_updated_at"))
    print("CURRENT_TIME_CONSENSUS:", json.dumps(report["current_schedule_consensus"], ensure_ascii=False, sort_keys=True))
    print("AUDIT_LOGS:", report["audit_log_count"])
    print("AUDIT_SNAPSHOTS:", report["audit_snapshot_count"])
    print("DONOR_SCHEDULES:", report["donor_schedule_count"])
    print("EXISTING_TARGET_DVD:", report["existing_target_dvd_count"])

    for legacy_id, target in report["targets"].items():
        print("---")
        print("LEGACY:", legacy_id)
        print("COMPONENT:", target["component_name"])
        print("WORKLOAD:", target["workload"])
        print("CURRENT_ANALYSIS:", json.dumps(target["current_schedule_analysis"], ensure_ascii=False, sort_keys=True))
        print("RECOVERY_STATE_38D:", target["recovery_state_38d"])
        print("HISTORICAL_SNAPSHOTS:", len(target["historical_snapshots"]))
        for item in target["historical_snapshots"]:
            print("HISTORY:", json.dumps(item, ensure_ascii=False, sort_keys=True, default=str))
        print("DONOR_PATTERN_COUNT:", len(target["donor_patterns"]))
        for index, pattern in enumerate(target["donor_patterns"], start=1):
            print(f"DONOR_PATTERN_{index}:", json.dumps(pattern, ensure_ascii=False, sort_keys=True, default=str))
        print("FORENSIC_CLASSIFICATION:", json.dumps(target["forensic_classification"], ensure_ascii=False, sort_keys=True))

    print("MONGO_WRITES: 0")
    print("AUTOMATIC_ACTION: NAO")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args()

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        db = client[os.environ.get("DB_NAME", "sigesc")]
        report = await collect_forensics(db)
        print_compact(report)
        if args.json_path:
            path = Path(args.json_path)
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            print("JSON_LOCAL:", path)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
