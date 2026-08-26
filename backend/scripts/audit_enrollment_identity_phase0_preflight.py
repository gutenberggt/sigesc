#!/usr/bin/env python3
"""Fase 0 — preflight READ-ONLY da identidade numérica de matrículas.

Objetivo:
- reproduzir a classificação forense das divergências entre
  ``students.enrollment_number`` e a matrícula REGULAR ativa canônica;
- isolar apenas os casos de alta confiança em que a evidência histórica apoia
  ``enrollments.enrollment_number``;
- executar guardas de segurança sobre o estado vivo;
- gerar manifesto determinístico + SHA-256 para revisão posterior.

IMPORTANTE:
- NÃO existe modo ``--apply``;
- NÃO há insert/update/delete/upsert/bulk write no MongoDB;
- a única escrita é opcional no filesystem local para o manifesto JSON.

Uso em produção:
    cd /app
    python scripts/audit_enrollment_identity_phase0_preflight.py

Por padrão, grava o manifesto em:
    /tmp/sigesc_enrollment_identity_phase0_manifest.json
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from motor.motor_asyncio import AsyncIOMotorClient

PHASE_ID = "ENROLLMENT-IDENTITY-2026-PHASE0-PREFLIGHT"
BASE_MAIN_SHA = "cc35f47e8404f30ae0a324d9ae53361779467b0a"
EXPECTED_CONFIRMED_ENROLLMENT = 3049
DEFAULT_MANIFEST = "/tmp/sigesc_enrollment_identity_phase0_manifest.json"
SPECIAL_PROGRAMS = {"aee", "recomposicao_aprendizagem", "reforco_escolar"}
NUMBER_RX = re.compile(r"(?<!\d)(?:2025|2026)\d{4,5}(?!\d)", re.I)


def norm(value: Any) -> str:
    return str(value or "").strip()


def is_active(value: Any) -> bool:
    return norm(value).lower() == "active"


def year_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def enrollment_sort_key(doc: dict[str, Any]) -> tuple[Any, ...]:
    return (
        year_value(doc.get("academic_year")),
        norm(doc.get("enrollment_date")),
        norm(doc.get("created_at")),
        norm(doc.get("id")),
    )


def numbers_in(obj: Any) -> set[str]:
    try:
        text = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        text = str(obj)
    return set(NUMBER_RX.findall(text))


def is_special_class(class_doc: dict[str, Any] | None) -> bool:
    return norm((class_doc or {}).get("atendimento_programa")).lower() in SPECIAL_PROGRAMS


def select_active_regular(
    enrollment_docs: Iterable[dict[str, Any]],
    classes: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = [
        e
        for e in enrollment_docs
        if is_active(e.get("status"))
        and e.get("class_id")
        and not is_special_class(classes.get(e.get("class_id")))
    ]
    rows.sort(key=enrollment_sort_key, reverse=True)
    return rows


def classify_first_log(student_number: str, enrollment_number: str, first_log_number: str | None) -> str:
    historical = norm(first_log_number)
    sn = norm(student_number)
    en = norm(enrollment_number)
    if not historical:
        return "NO_LOG"
    if historical == en and historical != sn:
        return "LOG_CONFIRMS_ENROLLMENT"
    if historical == sn and historical != en:
        return "LOG_CONFIRMS_STUDENT"
    if historical == sn == en:
        return "LOG_CONFIRMS_BOTH"
    return "THIRD_NUMBER_IN_LOG"


def classify_complementary_evidence(
    student_number: str,
    enrollment_number: str,
    evidence: set[str],
) -> str:
    sn = norm(student_number)
    en = norm(enrollment_number)
    has_student = bool(sn and sn in evidence)
    has_enrollment = bool(en and en in evidence)
    third = {n for n in evidence if n not in {sn, en}}
    if has_enrollment and not has_student:
        return "EVIDENCE_SUPPORTS_ENROLLMENT"
    if has_student and not has_enrollment:
        return "EVIDENCE_SUPPORTS_STUDENT"
    if has_student and has_enrollment:
        return "BOTH_IN_HISTORY"
    if third:
        return "ONLY_THIRD_NUMBERS"
    return "NO_ADDITIONAL_NUMERIC_EVIDENCE"


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def manifest_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def evaluate_safety(
    *,
    candidate: dict[str, Any],
    student: dict[str, Any] | None,
    primary: dict[str, Any] | None,
    active_regular: list[dict[str, Any]],
    target_student_owners: set[str],
    target_enrollment_owners: set[str],
) -> list[str]:
    """Avalia apenas invariantes; não faz I/O nem mutação."""
    blockers: list[str] = []
    sid = norm(candidate.get("student_id"))
    expected_enrollment_id = norm(candidate.get("primary_enrollment_id"))
    expected_student_number = norm(candidate.get("student_number_before"))
    expected_target = norm(candidate.get("target_number"))

    if not student:
        return ["STUDENT_NOT_FOUND"]
    if norm(student.get("id")) != sid:
        blockers.append("STUDENT_ID_DIVERGED")
    if not is_active(student.get("status")):
        blockers.append("STUDENT_NOT_ACTIVE")
    if norm(student.get("enrollment_number")) != expected_student_number:
        blockers.append("STUDENT_NUMBER_CHANGED")

    if not primary:
        blockers.append("PRIMARY_ENROLLMENT_NOT_FOUND")
    else:
        if norm(primary.get("id")) != expected_enrollment_id:
            blockers.append("PRIMARY_ENROLLMENT_CHANGED")
        if not is_active(primary.get("status")):
            blockers.append("PRIMARY_ENROLLMENT_NOT_ACTIVE")
        if norm(primary.get("enrollment_number")) != expected_target:
            blockers.append("TARGET_NUMBER_CHANGED")
        if norm(primary.get("class_id")) != norm(candidate.get("class_id")):
            blockers.append("PRIMARY_CLASS_CHANGED")
        if norm(primary.get("school_id")) != norm(candidate.get("school_id")):
            blockers.append("PRIMARY_SCHOOL_CHANGED")

    if len(active_regular) != 1:
        blockers.append("ACTIVE_REGULAR_COUNT_NOT_ONE")

    if primary:
        if norm(student.get("class_id")) != norm(primary.get("class_id")):
            blockers.append("STUDENT_CLASS_PROJECTION_MISMATCH")
        if norm(student.get("school_id")) != norm(primary.get("school_id")):
            blockers.append("STUDENT_SCHOOL_PROJECTION_MISMATCH")

    foreign_student_owners = {x for x in target_student_owners if norm(x) and norm(x) != sid}
    if foreign_student_owners:
        blockers.append("TARGET_NUMBER_USED_BY_OTHER_STUDENT")

    foreign_enrollment_owners = {x for x in target_enrollment_owners if norm(x) and norm(x) != sid}
    if foreign_enrollment_owners:
        blockers.append("TARGET_NUMBER_USED_BY_OTHER_ENROLLMENT_OWNER")

    return sorted(set(blockers))


def blocker_bucket(blockers: list[str]) -> str:
    collision = {
        "TARGET_NUMBER_USED_BY_OTHER_STUDENT",
        "TARGET_NUMBER_USED_BY_OTHER_ENROLLMENT_OWNER",
    }
    state = {
        "STUDENT_NOT_FOUND",
        "STUDENT_ID_DIVERGED",
        "STUDENT_NOT_ACTIVE",
        "STUDENT_NUMBER_CHANGED",
        "PRIMARY_ENROLLMENT_NOT_FOUND",
        "PRIMARY_ENROLLMENT_CHANGED",
        "PRIMARY_ENROLLMENT_NOT_ACTIVE",
        "TARGET_NUMBER_CHANGED",
        "PRIMARY_CLASS_CHANGED",
        "PRIMARY_SCHOOL_CHANGED",
        "STUDENT_CLASS_PROJECTION_MISMATCH",
        "STUDENT_SCHOOL_PROJECTION_MISMATCH",
    }
    bset = set(blockers)
    if bset & collision:
        return "BLOCKED_COLLISION"
    if bset & state:
        return "BLOCKED_STATE_CHANGED"
    if blockers:
        return "BLOCKED_OTHER"
    return "READY_SAFE"


async def run(output_path: str) -> int:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        raise SystemExit("ERRO: MONGO_URL ou DB_NAME ausente.")

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    try:
        class_docs = await db.classes.find(
            {}, {"_id": 0, "id": 1, "atendimento_programa": 1}
        ).to_list(None)
        classes = {c["id"]: c for c in class_docs if c.get("id")}

        enrollments = await db.enrollments.find({}, {"_id": 0}).to_list(None)
        by_student: dict[str, list[dict[str, Any]]] = defaultdict(list)
        current_number_owners: dict[str, set[str]] = defaultdict(set)
        historical_number_owners: dict[str, set[str]] = defaultdict(set)

        for e in enrollments:
            sid = norm(e.get("student_id"))
            if sid:
                by_student[sid].append(e)
            number = norm(e.get("enrollment_number"))
            previous = norm(e.get("previous_enrollment_number"))
            if number and sid:
                current_number_owners[number].add(sid)
            if previous and sid:
                historical_number_owners[previous].add(sid)

        students = await db.students.find(
            {},
            {
                "_id": 0,
                "id": 1,
                "full_name": 1,
                "status": 1,
                "school_id": 1,
                "class_id": 1,
                "enrollment_number": 1,
            },
        ).to_list(None)
        student_by_id = {norm(s.get("id")): s for s in students if norm(s.get("id"))}
        student_number_owners: dict[str, set[str]] = defaultdict(set)
        for s in students:
            sid = norm(s.get("id"))
            number = norm(s.get("enrollment_number"))
            if sid and number:
                student_number_owners[number].add(sid)

        mismatches: dict[str, dict[str, Any]] = {}
        for s in students:
            sid = norm(s.get("id"))
            regular = select_active_regular(by_student.get(sid, []), classes)
            if not regular:
                continue
            primary = regular[0]
            sn = norm(s.get("enrollment_number"))
            en = norm(primary.get("enrollment_number"))
            if sn != en:
                mismatches[sid] = {
                    "student": s,
                    "primary": primary,
                    "student_number": sn,
                    "enrollment_number": en,
                }

        mismatch_ids = list(mismatches)
        matric_logs = await db.audit_logs.find(
            {
                "collection": "students",
                "document_id": {"$in": mismatch_ids},
                "extra_data.action_type": "matricula",
            },
            {"_id": 0, "document_id": 1, "timestamp": 1, "extra_data": 1},
        ).sort("timestamp", 1).to_list(None)

        first_log_number: dict[str, str] = {}
        for log in matric_logs:
            sid = norm(log.get("document_id"))
            if sid in first_log_number:
                continue
            nums = sorted(numbers_in(log.get("extra_data") or {}))
            if nums:
                first_log_number[sid] = nums[0]

        initial_classification = Counter()
        confirmed: dict[str, dict[str, Any]] = {}
        unresolved_ids: list[str] = []

        for sid, row in mismatches.items():
            cls = classify_first_log(
                row["student_number"], row["enrollment_number"], first_log_number.get(sid)
            )
            initial_classification[cls] += 1
            if cls == "LOG_CONFIRMS_ENROLLMENT":
                confirmed[sid] = {**row, "evidence_basis": "LOG_ORIGINAL"}
            elif cls in {"NO_LOG", "THIRD_NUMBER_IN_LOG"}:
                unresolved_ids.append(sid)

        all_logs = await db.audit_logs.find(
            {"document_id": {"$in": unresolved_ids}}, {"_id": 0}
        ).sort("timestamp", 1).to_list(None)
        logs_by_student: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for log in all_logs:
            logs_by_student[norm(log.get("document_id"))].append(log)

        histories = await db.student_history.find(
            {"student_id": {"$in": unresolved_ids}}, {"_id": 0}
        ).to_list(None)
        history_by_student: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for hist in histories:
            history_by_student[norm(hist.get("student_id"))].append(hist)

        complementary = Counter()
        for sid in unresolved_ids:
            row = mismatches[sid]
            evidence: set[str] = set()
            for log in logs_by_student.get(sid, []):
                evidence |= numbers_in(log)
            for hist in history_by_student.get(sid, []):
                evidence |= numbers_in(hist)

            primary_id = norm(row["primary"].get("id"))
            for e in by_student.get(sid, []):
                if norm(e.get("id")) == primary_id:
                    previous = norm(e.get("previous_enrollment_number"))
                    if previous:
                        evidence.add(previous)
                    continue
                number = norm(e.get("enrollment_number"))
                previous = norm(e.get("previous_enrollment_number"))
                if number:
                    evidence.add(number)
                if previous:
                    evidence.add(previous)

            cls = classify_complementary_evidence(
                row["student_number"], row["enrollment_number"], evidence
            )
            complementary[cls] += 1
            if cls == "EVIDENCE_SUPPORTS_ENROLLMENT":
                confirmed[sid] = {**row, "evidence_basis": "COMPLEMENTARY_HISTORY"}

        candidates: list[dict[str, Any]] = []
        for sid, row in confirmed.items():
            primary = row["primary"]
            candidates.append(
                {
                    "student_id": sid,
                    "full_name": norm(row["student"].get("full_name")),
                    "student_number_before": row["student_number"],
                    "target_number": row["enrollment_number"],
                    "primary_enrollment_id": norm(primary.get("id")),
                    "academic_year": primary.get("academic_year"),
                    "school_id": norm(primary.get("school_id")),
                    "class_id": norm(primary.get("class_id")),
                    "evidence_basis": row["evidence_basis"],
                }
            )
        candidates.sort(key=lambda x: x["student_id"])

        safety_counts = Counter()
        manifest_rows: list[dict[str, Any]] = []
        for candidate in candidates:
            sid = candidate["student_id"]
            student = student_by_id.get(sid)
            regular = select_active_regular(by_student.get(sid, []), classes)
            primary = regular[0] if regular else None
            target = candidate["target_number"]
            target_owners = set(current_number_owners.get(target, set())) | set(
                historical_number_owners.get(target, set())
            )
            blockers = evaluate_safety(
                candidate=candidate,
                student=student,
                primary=primary,
                active_regular=regular,
                target_student_owners=set(student_number_owners.get(target, set())),
                target_enrollment_owners=target_owners,
            )
            bucket = blocker_bucket(blockers)
            safety_counts[bucket] += 1

            if student and norm(student.get("enrollment_number")) == candidate["student_number_before"]:
                safety_counts["STILL_MATCHES_LIVE_STATE"] += 1
            if not ({x for x in student_number_owners.get(target, set()) if x != sid}):
                safety_counts["TARGET_NUMBER_FREE_IN_STUDENTS"] += 1
            if not ({x for x in target_owners if x != sid}):
                safety_counts["TARGET_NUMBER_OWNED_ONLY_BY_SAME_STUDENT"] += 1
            if len(regular) == 1:
                safety_counts["SINGLE_ACTIVE_REGULAR_ENROLLMENT"] += 1
            if student and primary and norm(student.get("class_id")) == norm(primary.get("class_id")) and norm(student.get("school_id")) == norm(primary.get("school_id")):
                safety_counts["SAME_CLASS_AND_SCHOOL"] += 1

            manifest_rows.append(
                {
                    **candidate,
                    "disposition": bucket,
                    "blockers": blockers,
                }
            )

        manifest = {
            "phase_id": PHASE_ID,
            "base_main_sha": BASE_MAIN_SHA,
            "expected_confirmed_enrollment": EXPECTED_CONFIRMED_ENROLLMENT,
            "observed": {
                "students_total": len(students),
                "enrollments_total": len(enrollments),
                "divergences_total": len(mismatches),
                "initial_classification": dict(sorted(initial_classification.items())),
                "complementary_classification": dict(sorted(complementary.items())),
                "confirmed_enrollment": len(candidates),
                "baseline_match": len(candidates) == EXPECTED_CONFIRMED_ENROLLMENT,
            },
            "safety": {
                "still_matches_live_state": safety_counts["STILL_MATCHES_LIVE_STATE"],
                "target_number_free_in_students": safety_counts["TARGET_NUMBER_FREE_IN_STUDENTS"],
                "target_number_owned_only_by_same_student": safety_counts[
                    "TARGET_NUMBER_OWNED_ONLY_BY_SAME_STUDENT"
                ],
                "single_active_regular_enrollment": safety_counts[
                    "SINGLE_ACTIVE_REGULAR_ENROLLMENT"
                ],
                "same_class_and_school": safety_counts["SAME_CLASS_AND_SCHOOL"],
                "ready_safe": safety_counts["READY_SAFE"],
                "blocked_collision": safety_counts["BLOCKED_COLLISION"],
                "blocked_state_changed": safety_counts["BLOCKED_STATE_CHANGED"],
                "blocked_other": safety_counts["BLOCKED_OTHER"],
            },
            "candidates": manifest_rows,
            "mongo_writes": 0,
        }

        digest = manifest_sha256(manifest)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )

        print("=" * 88)
        print("SIGESC — FASE 0 PREFLIGHT READ-ONLY DA IDENTIDADE DE MATRÍCULA")
        print("=" * 88)
        print(f"PHASE_ID: {PHASE_ID}")
        print(f"BASE_MAIN_SHA: {BASE_MAIN_SHA}")
        print(f"DIVERGENCIAS_TOTAL: {len(mismatches)}")
        print(f"EXPECTED_CONFIRMED_ENROLLMENT: {EXPECTED_CONFIRMED_ENROLLMENT}")
        print(f"CONFIRMED_ENROLLMENT: {len(candidates)}")
        print(f"BASELINE_MATCH: {'SIM' if len(candidates) == EXPECTED_CONFIRMED_ENROLLMENT else 'NAO'}")
        print(f"STILL_MATCHES_LIVE_STATE: {safety_counts['STILL_MATCHES_LIVE_STATE']}")
        print(f"TARGET_NUMBER_FREE_IN_STUDENTS: {safety_counts['TARGET_NUMBER_FREE_IN_STUDENTS']}")
        print(
            "TARGET_NUMBER_OWNED_ONLY_BY_SAME_STUDENT: "
            f"{safety_counts['TARGET_NUMBER_OWNED_ONLY_BY_SAME_STUDENT']}"
        )
        print(f"SINGLE_ACTIVE_REGULAR_ENROLLMENT: {safety_counts['SINGLE_ACTIVE_REGULAR_ENROLLMENT']}")
        print(f"SAME_CLASS_AND_SCHOOL: {safety_counts['SAME_CLASS_AND_SCHOOL']}")
        print(f"READY_SAFE: {safety_counts['READY_SAFE']}")
        print(f"BLOCKED_COLLISION: {safety_counts['BLOCKED_COLLISION']}")
        print(f"BLOCKED_STATE_CHANGED: {safety_counts['BLOCKED_STATE_CHANGED']}")
        print(f"BLOCKED_OTHER: {safety_counts['BLOCKED_OTHER']}")
        print(f"MANIFEST: {path}")
        print(f"MANIFEST_SHA256: {digest}")
        print("MONGO_WRITES: 0")
        print("READ_ONLY: SIM")
        print("=" * 88)
        return 0
    finally:
        client.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preflight read-only da identidade numérica")
    parser.add_argument("--output", default=DEFAULT_MANIFEST, help="Caminho local do manifesto JSON")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(asyncio.run(run(args.output)))
