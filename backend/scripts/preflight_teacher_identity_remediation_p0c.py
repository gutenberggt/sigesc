#!/usr/bin/env python3
"""P0-C — preflight READ-ONLY para normalização da identidade docente.

Objetivo:
- classificar a ponte institucional ``teacher_class_assignments.teacher_id``
  (users.id) -> ``staff.id`` sem inferência por nome;
- propor SOMENTE backfill de ``staff.user_id`` quando a evidência estrutural for
  unívoca e os invariantes de tenant/ocupação/estado forem satisfeitos;
- produzir manifesto determinístico + SHA-256 para revisão humana posterior.

Este script NÃO possui modo apply e não altera MongoDB. A única escrita é o
arquivo JSON local informado em ``--manifest``.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

PHASE_ID = "P0C-TEACHER-IDENTITY-PREFLIGHT-2026"
MANIFEST_VERSION = 1
DEFAULT_MANIFEST = "/tmp/sigesc_p0c_teacher_identity_preflight.json"
ALLOWED_TEACHER_ROLES = {"professor", "coordenador"}
INACTIVE_STAFF_STATUSES = {"inativo", "inactive", "desligado", "afastado_definitivo"}

MUTATOR_TOKENS = (
    ".insert_one(",
    ".insert_many(",
    ".update_one(",
    ".update_many(",
    ".replace_one(",
    ".delete_one(",
    ".delete_many(",
    ".bulk_write(",
    ".find_one_and_update(",
    ".find_one_and_delete(",
    ".find_one_and_replace(",
)


def assert_read_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    executable = "\n".join(
        line
        for line in source.splitlines()
        if "MUTATOR_TOKENS" not in line and not line.lstrip().startswith('"')
    )
    forbidden = [token for token in MUTATOR_TOKENS if token in executable]
    if forbidden:
        raise RuntimeError(f"READ_ONLY_GUARD_FAILED forbidden={forbidden}")


def norm(value: Any) -> str:
    return str(value or "").strip()


def norm_email(value: Any) -> str:
    return norm(value).casefold()


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


def active_temporal(row: Mapping[str, Any], reference_date: str) -> bool:
    if row.get("deleted") is True:
        return False
    valid_from = norm(row.get("valid_from"))
    valid_until = norm(row.get("valid_until"))
    if valid_from and valid_from > reference_date:
        return False
    if valid_until and valid_until < reference_date:
        return False
    return True


def legacy_active_on(row: Mapping[str, Any], reference_date: str) -> bool:
    if norm(row.get("status")).casefold() != "ativo":
        return False
    if row.get("is_substituicao") is True:
        start = norm(row.get("data_inicio_substituicao"))
        end = norm(row.get("data_fim_substituicao"))
        if start and start > reference_date:
            return False
        if end and end < reference_date:
            return False
    return True


def build_multi_index(
    rows: Iterable[Mapping[str, Any]],
    field: str,
    *,
    casefold: bool = False,
) -> dict[str, list[Mapping[str, Any]]]:
    result: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        key = norm(row.get(field))
        if casefold:
            key = key.casefold()
        if key:
            result[key].append(row)
    return result


def select_structural_staff(candidate_sets: Iterable[set[str]]) -> tuple[Optional[str], str]:
    """Exige evidência exata e unânime para cada par turma+componente."""
    sets = [set(values) for values in candidate_sets]
    if not sets:
        return None, "NO_COMPONENT_EVIDENCE"
    if any(len(values) == 0 for values in sets):
        return None, "PAIR_MISSING"
    if any(len(values) > 1 for values in sets):
        return None, "PAIR_AMBIGUOUS"
    candidates = {next(iter(values)) for values in sets}
    if len(candidates) != 1:
        return None, "PAIR_CONFLICT"
    return next(iter(candidates)), "EXACT_PAIR_UNANIMOUS"


def tenant_for_class(
    klass: Mapping[str, Any],
    school_by_id: Mapping[str, Mapping[str, Any]],
) -> str:
    direct = norm(klass.get("mantenedora_id"))
    if direct:
        return direct
    school = school_by_id.get(norm(klass.get("school_id"))) or {}
    return norm(school.get("mantenedora_id"))


def email_signal(
    user: Mapping[str, Any],
    *,
    users_by_email: Mapping[str, list[Mapping[str, Any]]],
    staff_by_email: Mapping[str, list[Mapping[str, Any]]],
    structural_staff_id: Optional[str],
) -> tuple[str, Optional[str]]:
    email = norm_email(user.get("email"))
    if not email:
        return "NO_EMAIL", None
    user_matches = list(users_by_email.get(email, []))
    if len(user_matches) != 1:
        return "USER_EMAIL_AMBIGUOUS", None
    staff_matches = list(staff_by_email.get(email, []))
    if not staff_matches:
        return "NO_STAFF_EMAIL_MATCH", None
    if len(staff_matches) != 1:
        return "STAFF_EMAIL_AMBIGUOUS", None
    staff_id = norm(staff_matches[0].get("id")) or None
    if structural_staff_id and staff_id != structural_staff_id:
        return "EMAIL_STRUCTURAL_CONFLICT", staff_id
    return "UNIQUE_EMAIL_MATCH", staff_id


def classify_blockers(
    *,
    user_id: str,
    user: Mapping[str, Any],
    staff: Mapping[str, Any],
    class_tenants: set[str],
    staff_by_user_id: Mapping[str, list[Mapping[str, Any]]],
    email_evidence: str,
) -> list[str]:
    blockers: list[str] = []
    role = norm(user.get("role")).casefold()
    if role not in ALLOWED_TEACHER_ROLES:
        blockers.append("USER_ROLE_NOT_TEACHER")

    if norm(staff.get("cargo")).casefold() != "professor":
        blockers.append("STAFF_CARGO_NOT_PROFESSOR")
    if norm(staff.get("status")).casefold() in INACTIVE_STAFF_STATUSES:
        blockers.append("STAFF_INACTIVE")

    current_link = norm(staff.get("user_id"))
    if current_link and current_link != user_id:
        blockers.append("STAFF_ALREADY_LINKED_TO_OTHER_USER")

    target_links = list(staff_by_user_id.get(user_id, []))
    foreign_target_links = [row for row in target_links if norm(row.get("id")) != norm(staff.get("id"))]
    if foreign_target_links:
        blockers.append("USER_ALREADY_LINKED_TO_OTHER_STAFF")

    user_tenant = norm(user.get("mantenedora_id"))
    staff_tenant = norm(staff.get("mantenedora_id"))
    clean_class_tenants = {t for t in class_tenants if t}
    if not user_tenant:
        blockers.append("USER_TENANT_MISSING")
    if not staff_tenant:
        blockers.append("STAFF_TENANT_MISSING")
    if not clean_class_tenants:
        blockers.append("CLASS_TENANT_MISSING")
    if len(clean_class_tenants) > 1:
        blockers.append("DVD_CROSSES_TENANTS")
    if user_tenant and staff_tenant and user_tenant != staff_tenant:
        blockers.append("USER_STAFF_TENANT_MISMATCH")
    if user_tenant and clean_class_tenants and any(t != user_tenant for t in clean_class_tenants):
        blockers.append("USER_CLASS_TENANT_MISMATCH")
    if staff_tenant and clean_class_tenants and any(t != staff_tenant for t in clean_class_tenants):
        blockers.append("STAFF_CLASS_TENANT_MISMATCH")

    if email_evidence == "EMAIL_STRUCTURAL_CONFLICT":
        blockers.append("EMAIL_STRUCTURAL_CONFLICT")

    return sorted(set(blockers))


def decision_bucket(*, structural_status: str, blockers: list[str]) -> str:
    if blockers:
        return "BLOCKED"
    if structural_status != "EXACT_PAIR_UNANIMOUS":
        return "NEEDS_REVIEW"
    return "READY_SAFE"


async def collect_manifest(
    db: Any,
    *,
    academic_year: int,
    reference_date: str,
    mantenedora_id: Optional[str] = None,
    source_evidence_sha256: Optional[str] = None,
) -> dict[str, Any]:
    schools_query: dict[str, Any] = {}
    if mantenedora_id:
        schools_query["mantenedora_id"] = mantenedora_id
    schools = await db.schools.find(
        schools_query,
        {"_id": 0, "id": 1, "mantenedora_id": 1},
    ).to_list(10000)
    school_by_id = {norm(row.get("id")): row for row in schools if row.get("id")}
    school_ids = set(school_by_id)

    class_query: dict[str, Any] = {"academic_year": {"$in": [academic_year, str(academic_year)]}}
    if mantenedora_id:
        class_query["school_id"] = {"$in": sorted(school_ids)}
    classes = await db.classes.find(
        class_query,
        {"_id": 0, "id": 1, "school_id": 1, "mantenedora_id": 1, "academic_year": 1},
    ).to_list(20000)
    class_by_id = {norm(row.get("id")): row for row in classes if row.get("id")}
    class_ids = set(class_by_id)

    users = await db.users.find(
        {},
        {"_id": 0, "id": 1, "email": 1, "role": 1, "mantenedora_id": 1},
    ).to_list(50000)
    staff_rows = await db.staff.find(
        {},
        {"_id": 0, "id": 1, "user_id": 1, "email": 1, "cargo": 1, "status": 1, "mantenedora_id": 1},
    ).to_list(50000)
    user_by_id = {norm(row.get("id")): row for row in users if row.get("id")}
    staff_by_id = {norm(row.get("id")): row for row in staff_rows if row.get("id")}
    users_by_email = build_multi_index(users, "email", casefold=True)
    staff_by_email = build_multi_index(staff_rows, "email", casefold=True)
    staff_by_user_id = build_multi_index(staff_rows, "user_id")

    legacy_query: dict[str, Any] = {
        "academic_year": {"$in": [academic_year, str(academic_year)]},
        "status": "ativo",
    }
    if mantenedora_id:
        legacy_query["class_id"] = {"$in": sorted(class_ids)}
    legacy_rows_raw = await db.teacher_assignments.find(
        legacy_query,
        {
            "_id": 0,
            "id": 1,
            "staff_id": 1,
            "class_id": 1,
            "course_id": 1,
            "status": 1,
            "is_substituicao": 1,
            "data_inicio_substituicao": 1,
            "data_fim_substituicao": 1,
        },
    ).to_list(50000)
    legacy_rows = [row for row in legacy_rows_raw if legacy_active_on(row, reference_date)]

    legacy_by_pair: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    legacy_staff_by_class: dict[str, set[str]] = defaultdict(set)
    for row in legacy_rows:
        class_id = norm(row.get("class_id"))
        course_id = norm(row.get("course_id"))
        staff_id = norm(row.get("staff_id"))
        if class_id and course_id and staff_id:
            legacy_by_pair[(class_id, course_id)].append(row)
            legacy_staff_by_class[class_id].add(staff_id)

    dvd_rows_raw = await db.teacher_class_assignments.find(
        {"deleted": {"$ne": True}, "class_id": {"$in": sorted(class_ids)}},
        {
            "_id": 0,
            "id": 1,
            "teacher_id": 1,
            "class_id": 1,
            "component_id": 1,
            "valid_from": 1,
            "valid_until": 1,
            "deleted": 1,
        },
    ).to_list(50000)
    dvd_rows = [row for row in dvd_rows_raw if active_temporal(row, reference_date)]
    dvd_by_user: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in dvd_rows:
        teacher_id = norm(row.get("teacher_id"))
        if teacher_id:
            dvd_by_user[teacher_id].append(row)

    decisions = Counter()
    evidence_methods = Counter()
    blocker_counts = Counter()
    structural_counts = Counter()
    proposals: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []

    for user_id in sorted(dvd_by_user):
        rows = sorted(dvd_by_user[user_id], key=lambda row: norm(row.get("id")))
        user = user_by_id.get(user_id)
        if not user:
            decisions["NEEDS_REVIEW"] += 1
            structural_counts["USER_NOT_FOUND"] += 1
            cases.append({
                "teacher_user_id": user_id,
                "decision": "NEEDS_REVIEW",
                "structural_status": "USER_NOT_FOUND",
                "dvd_assignment_count": len(rows),
                "blockers": ["USER_NOT_FOUND"],
            })
            continue

        pair_evidence: list[dict[str, Any]] = []
        candidate_sets: list[set[str]] = []
        class_tenants: set[str] = set()
        class_wide_rows: list[Mapping[str, Any]] = []

        for row in rows:
            class_id = norm(row.get("class_id"))
            component_id = norm(row.get("component_id"))
            klass = class_by_id.get(class_id) or {}
            class_tenants.add(tenant_for_class(klass, school_by_id))
            if not component_id:
                class_wide_rows.append(row)
                continue
            legacy_matches = list(legacy_by_pair.get((class_id, component_id), []))
            staff_ids = {norm(item.get("staff_id")) for item in legacy_matches if norm(item.get("staff_id"))}
            candidate_sets.append(staff_ids)
            pair_evidence.append({
                "class_id": class_id,
                "component_id": component_id,
                "dvd_assignment_id": norm(row.get("id")),
                "legacy_assignment_ids": sorted(norm(item.get("id")) for item in legacy_matches if norm(item.get("id"))),
                "candidate_staff_ids": sorted(staff_ids),
            })

        structural_staff_id, structural_status = select_structural_staff(candidate_sets)
        structural_counts[structural_status] += 1

        direct_matches = list(staff_by_user_id.get(user_id, []))
        if len(direct_matches) > 1:
            decisions["BLOCKED"] += 1
            blocker_counts["MULTIPLE_STAFF_WITH_SAME_USER_ID"] += 1
            cases.append({
                "teacher_user_id": user_id,
                "decision": "BLOCKED",
                "structural_status": structural_status,
                "dvd_assignment_count": len(rows),
                "blockers": ["MULTIPLE_STAFF_WITH_SAME_USER_ID"],
                "pair_evidence": pair_evidence,
            })
            continue

        if len(direct_matches) == 1:
            direct_staff_id = norm(direct_matches[0].get("id"))
            if structural_staff_id and direct_staff_id != structural_staff_id:
                decisions["BLOCKED"] += 1
                blocker_counts["CANONICAL_STRUCTURAL_CONFLICT"] += 1
                cases.append({
                    "teacher_user_id": user_id,
                    "staff_id": direct_staff_id,
                    "decision": "BLOCKED",
                    "structural_status": structural_status,
                    "dvd_assignment_count": len(rows),
                    "blockers": ["CANONICAL_STRUCTURAL_CONFLICT"],
                    "pair_evidence": pair_evidence,
                })
            else:
                decisions["ALREADY_CANONICAL"] += 1
                cases.append({
                    "teacher_user_id": user_id,
                    "staff_id": direct_staff_id,
                    "decision": "ALREADY_CANONICAL",
                    "structural_status": structural_status,
                    "dvd_assignment_count": len(rows),
                    "blockers": [],
                })
            continue

        email_evidence, email_staff_id = email_signal(
            user,
            users_by_email=users_by_email,
            staff_by_email=staff_by_email,
            structural_staff_id=structural_staff_id,
        )

        if not structural_staff_id:
            decisions["NEEDS_REVIEW"] += 1
            evidence_methods["NONE"] += 1
            cases.append({
                "teacher_user_id": user_id,
                "decision": "NEEDS_REVIEW",
                "structural_status": structural_status,
                "email_signal": email_evidence,
                "dvd_assignment_count": len(rows),
                "class_wide_assignment_count": len(class_wide_rows),
                "blockers": [],
                "pair_evidence": pair_evidence,
            })
            continue

        staff = staff_by_id.get(structural_staff_id)
        if not staff:
            decisions["BLOCKED"] += 1
            blocker_counts["STRUCTURAL_STAFF_NOT_FOUND"] += 1
            cases.append({
                "teacher_user_id": user_id,
                "staff_id": structural_staff_id,
                "decision": "BLOCKED",
                "structural_status": structural_status,
                "email_signal": email_evidence,
                "dvd_assignment_count": len(rows),
                "blockers": ["STRUCTURAL_STAFF_NOT_FOUND"],
                "pair_evidence": pair_evidence,
            })
            continue

        blockers = classify_blockers(
            user_id=user_id,
            user=user,
            staff=staff,
            class_tenants=class_tenants,
            staff_by_user_id=staff_by_user_id,
            email_evidence=email_evidence,
        )

        # Vínculo class-wide só é aceito junto de identidade já provada por pares
        # componente exatos e se o mesmo staff aparece em alguma alocação legado
        # daquela turma. Não há inferência a partir do class-wide isoladamente.
        for row in class_wide_rows:
            class_id = norm(row.get("class_id"))
            if structural_staff_id not in legacy_staff_by_class.get(class_id, set()):
                blockers.append("CLASS_WIDE_NOT_SUPPORTED_BY_LEGACY")
        blockers = sorted(set(blockers))

        decision = decision_bucket(structural_status=structural_status, blockers=blockers)
        decisions[decision] += 1
        for blocker in blockers:
            blocker_counts[blocker] += 1

        method = "EXACT_PAIR_PLUS_EMAIL" if (
            email_evidence == "UNIQUE_EMAIL_MATCH" and email_staff_id == structural_staff_id
        ) else "EXACT_PAIR"
        evidence_methods[method] += 1

        case = {
            "teacher_user_id": user_id,
            "staff_id": structural_staff_id,
            "decision": decision,
            "structural_status": structural_status,
            "evidence_method": method,
            "email_signal": email_evidence,
            "dvd_assignment_count": len(rows),
            "component_assignment_count": len(pair_evidence),
            "class_wide_assignment_count": len(class_wide_rows),
            "tenant_ids": sorted(t for t in class_tenants if t),
            "staff_user_id_before": norm(staff.get("user_id")) or None,
            "blockers": blockers,
            "pair_evidence": pair_evidence,
        }
        cases.append(case)

        if decision == "READY_SAFE":
            proposal = {
                "operation": "BACKFILL_STAFF_USER_ID",
                "staff_id": structural_staff_id,
                "expected_user_id_before": norm(staff.get("user_id")) or None,
                "target_user_id": user_id,
                "mantenedora_id": norm(staff.get("mantenedora_id")) or None,
                "evidence_method": method,
                "dvd_assignment_ids": sorted(norm(row.get("id")) for row in rows if norm(row.get("id"))),
                "exact_pair_evidence": pair_evidence,
            }
            proposal["evidence_sha256"] = manifest_sha256(proposal)
            proposals.append(proposal)

    proposals.sort(key=lambda item: (item["staff_id"], item["target_user_id"]))
    cases.sort(key=lambda item: (item.get("decision", ""), item.get("teacher_user_id", "")))

    payload = {
        "phase": PHASE_ID,
        "manifest_version": MANIFEST_VERSION,
        "mode": "READ_ONLY_PREFLIGHT",
        "academic_year": academic_year,
        "reference_date": reference_date,
        "mantenedora_id": mantenedora_id,
        "source_p0b_evidence_sha256": source_evidence_sha256,
        "scope": {
            "schools": len(schools),
            "classes": len(classes),
            "active_legacy_rows": len(legacy_rows),
            "active_dvd_rows": len(dvd_rows),
            "dvd_teacher_users": len(dvd_by_user),
        },
        "summary": {
            "decision_counts": dict(sorted(decisions.items())),
            "structural_status_counts": dict(sorted(structural_counts.items())),
            "evidence_method_counts": dict(sorted(evidence_methods.items())),
            "blocker_counts": dict(sorted(blocker_counts.items())),
            "proposed_staff_user_id_backfills": len(proposals),
        },
        "safety_contract": {
            "database_mutation": False,
            "name_matching": False,
            "email_alone_sufficient": False,
            "exact_class_component_legacy_evidence_required": True,
            "tenant_consistency_required": True,
            "staff_user_id_must_be_empty_or_same": True,
            "ambiguous_cases": "NEEDS_REVIEW",
        },
        "proposals": proposals,
        "cases": cases,
    }
    return payload


async def run(args: argparse.Namespace) -> int:
    assert_read_only()
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        raise SystemExit("ERRO: MONGO_URL ou DB_NAME ausente.")

    client = AsyncIOMotorClient(mongo_url)
    try:
        db = client[db_name]
        payload = await collect_manifest(
            db,
            academic_year=args.academic_year,
            reference_date=args.reference_date,
            mantenedora_id=args.mantenedora_id,
            source_evidence_sha256=args.source_evidence_sha256,
        )
    finally:
        client.close()

    digest = manifest_sha256(payload)
    output = Path(args.manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    print(json.dumps({
        "phase": PHASE_ID,
        "mode": "READ_ONLY_PREFLIGHT",
        "manifest": str(output),
        "manifest_sha256": digest,
        "source_p0b_evidence_sha256": args.source_evidence_sha256,
        "scope": payload["scope"],
        "summary": payload["summary"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P0-C READ-ONLY — preflight da identidade docente")
    parser.add_argument("--academic-year", type=int, default=date.today().year)
    parser.add_argument("--reference-date", default=date.today().isoformat())
    parser.add_argument("--mantenedora-id", default=None)
    parser.add_argument("--source-evidence-sha256", default=None)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
