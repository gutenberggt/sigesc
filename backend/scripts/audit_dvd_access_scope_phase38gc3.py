"""38G-C3 — censo READ-ONLY de escopo de login dos 228 vínculos DVD.

Objetivo: classificar todos os vínculos ativados no 38G-B sem parar no primeiro
bloqueio. Reproduz a regra real de /auth/login para role/school_ids e compara
com escola/tenant do vínculo. Não altera MongoDB.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
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

from scripts.apply_dvd_cutover_phase38g import (  # noqa: E402
    APPROVED_BACKUP_BUNDLE_SHA256,
    APPROVED_MANIFEST_SHA256,
    APPROVED_READY_COUNT,
    load_and_verify_backup,
)
from scripts.audit_dvd_post_cutover_phase38gc import validate_receipt  # noqa: E402
from services.diary_assignment_access import PEDAGOGICAL_OWNER_ROLES  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

ROLE_PRIORITY = {
    "diretor": 5,
    "coordenador": 4,
    "auxiliar_secretaria": 4,
    "secretario": 3,
    "professor": 2,
    "auxiliar": 1,
}

MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
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


def school_ids_from_links(links: Any) -> list[str]:
    result = []
    for link in links or []:
        if isinstance(link, Mapping):
            school_id = link.get("school_id")
        else:
            school_id = getattr(link, "school_id", None)
        if school_id:
            result.append(str(school_id))
    return result


def effective_role_and_schools(base_role: str, base_links: Any, lotacoes: list[Mapping[str, Any]]) -> tuple[str, list[str]]:
    role = str(base_role or "")
    links = list(base_links or [])
    if lotacoes:
        highest = ROLE_PRIORITY.get(role, 0)
        role_links = []
        for lot in lotacoes:
            funcao = str(lot.get("funcao") or "").lower()
            priority = ROLE_PRIORITY.get(funcao, 0)
            if priority > highest:
                highest = priority
                role = funcao
            role_links.append({"school_id": lot.get("school_id"), "role": funcao})
        links = role_links
    return role, school_ids_from_links(links)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--academic-year", type=int, default=2026)
    parser.add_argument("--expected-manifest-sha256", default=APPROVED_MANIFEST_SHA256)
    parser.add_argument("--expected-count", type=int, default=APPROVED_READY_COUNT)
    parser.add_argument("--expected-backup-sha256", default=APPROVED_BACKUP_BUNDLE_SHA256)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--json", default=None)
    args = parser.parse_args()

    assert_read_only()
    backup = load_and_verify_backup(
        Path(args.backup_dir),
        expected_manifest_sha256=args.expected_manifest_sha256,
        expected_count=args.expected_count,
        expected_backup_sha256=args.expected_backup_sha256,
    )
    validate_receipt(Path(args.receipt), args.expected_manifest_sha256, args.expected_backup_sha256, args.expected_count)
    manifest = list(backup["manifest"])
    ids = [str(row["id"]) for row in manifest]

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        db = client[os.environ["DB_NAME"]]
        persisted = await db.teacher_class_assignments.find(
            {"id": {"$in": ids}}, {"_id": 0}
        ).to_list(args.expected_count + 20)
        by_id = {str(row.get("id")): row for row in persisted if row.get("id")}
        if len(by_id) != args.expected_count:
            raise RuntimeError(f"PERSISTED_COUNT_MISMATCH actual={len(by_id)} expected={args.expected_count}")

        teacher_ids = sorted({str(row.get("teacher_id")) for row in persisted if row.get("teacher_id")})
        users = await db.users.find(
            {"id": {"$in": teacher_ids}},
            {"_id": 0, "id": 1, "email": 1, "role": 1, "status": 1, "school_links": 1,
             "mantenedora_id": 1, "full_name": 1, "name": 1},
        ).to_list(len(teacher_ids) + 20)
        users_by_id = {str(row.get("id")): row for row in users if row.get("id")}
        user_emails = sorted({
            str(row.get("email") or "").strip()
            for row in users
            if str(row.get("email") or "").strip()
        })

        legacy_ids = sorted({
            str((row.get("cutover_provenance") or {}).get("source_legacy_assignment_id"))
            for row in persisted
            if (row.get("cutover_provenance") or {}).get("source_legacy_assignment_id")
        })
        legacy = await db.teacher_assignments.find(
            {"id": {"$in": legacy_ids}},
            {"_id": 0, "id": 1, "staff_id": 1, "school_id": 1, "class_id": 1,
             "course_id": 1, "academic_year": 1, "status": 1},
        ).to_list(len(legacy_ids) + 20)
        legacy_by_id = {str(row.get("id")): row for row in legacy if row.get("id")}

        legacy_staff_ids = sorted({str(row.get("staff_id")) for row in legacy if row.get("staff_id")})
        staff_query_parts = []
        if legacy_staff_ids:
            staff_query_parts.append({"id": {"$in": legacy_staff_ids}})
        if user_emails:
            staff_query_parts.append({"email": {"$in": user_emails}})
        staff_query = {"$or": staff_query_parts} if staff_query_parts else {"id": {"$in": []}}
        staff = await db.staff.find(
            staff_query,
            {"_id": 0, "id": 1, "user_id": 1, "email": 1, "nome": 1, "full_name": 1, "status": 1},
        ).to_list(max(len(legacy_staff_ids) + len(user_emails) + 100, 500))
        staff_by_id = {str(row.get("id")): row for row in staff if row.get("id")}
        staff_by_email: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in staff:
            email = str(row.get("email") or "").strip().casefold()
            if email:
                staff_by_email[email].append(row)

        relevant_staff_ids = sorted({str(row.get("id")) for row in staff if row.get("id")})
        all_lotacoes = await db.school_assignments.find(
            {"staff_id": {"$in": relevant_staff_ids}, "status": "ativo"},
            {"_id": 0, "id": 1, "staff_id": 1, "school_id": 1, "funcao": 1,
             "academic_year": 1, "status": 1, "mantenedora_id": 1},
        ).to_list(10000)
        lots_by_staff: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in all_lotacoes:
            lots_by_staff[str(row.get("staff_id") or "")].append(row)

        counts = Counter()
        teacher_blockers: dict[str, set[str]] = defaultdict(set)
        details = []

        for assignment_id in ids:
            a = by_id[assignment_id]
            teacher_id = str(a.get("teacher_id") or "")
            school_id = str(a.get("school_id") or "")
            tenant_id = str(a.get("mantenedora_id") or "")
            user = users_by_id.get(teacher_id)
            blockers = []
            notes = []
            source = (a.get("cutover_provenance") or {}).get("source_legacy_assignment_id")
            legacy_row = legacy_by_id.get(str(source or ""))
            source_staff_id = str((legacy_row or {}).get("staff_id") or "")
            source_staff = staff_by_id.get(source_staff_id)
            exact_lots: list[dict[str, Any]] = []
            login_school_ids: list[str] = []
            effective_role = ""

            if not user:
                blockers.append("USER_MISSING")
            else:
                if user.get("status") != "active":
                    blockers.append("USER_NOT_ACTIVE")

                email = str(user.get("email") or "").strip().casefold()
                email_staff_rows = staff_by_email.get(email, []) if email else []
                if not email_staff_rows:
                    blockers.append("LOGIN_STAFF_BY_EMAIL_MISSING")
                    login_staff_id = ""
                else:
                    # O login usa find_one({email}); duplicidade é ambígua por natureza.
                    # Para o censo, se houver >1 não fingimos saber qual vencerá.
                    if len(email_staff_rows) > 1:
                        blockers.append("DUPLICATE_STAFF_EMAIL_LOGIN_AMBIGUOUS")
                    login_staff_id = str(email_staff_rows[0].get("id") or "")
                    if source_staff_id and all(str(r.get("id") or "") != source_staff_id for r in email_staff_rows):
                        blockers.append("LOGIN_STAFF_EMAIL_SET_EXCLUDES_LEGACY_STAFF")
                    elif source_staff_id and login_staff_id != source_staff_id:
                        notes.append("LOGIN_FIRST_STAFF_DIFFERS_FROM_LEGACY_STAFF")

                exact_lots = [
                    row for row in lots_by_staff.get(login_staff_id, [])
                    if row.get("academic_year") == args.academic_year
                ] if login_staff_id else []
                string_year_lots = [
                    row for row in lots_by_staff.get(login_staff_id, [])
                    if str(row.get("academic_year") or "") == str(args.academic_year)
                    and row.get("academic_year") != args.academic_year
                ] if login_staff_id else []
                if string_year_lots and not exact_lots:
                    notes.append("ACTIVE_LOTACAO_YEAR_ONLY_NON_INT")

                effective_role, login_school_ids = effective_role_and_schools(
                    str(user.get("role") or ""), user.get("school_links") or [], exact_lots
                )

                if school_id not in login_school_ids:
                    blockers.append("LOGIN_SCHOOL_SCOPE_MISMATCH")
                    if exact_lots:
                        notes.append("ACTIVE_LOTACAO_EXISTS_OTHER_SCHOOL")
                    elif school_id in school_ids_from_links(user.get("school_links") or []):
                        notes.append("USER_SCHOOL_LINK_HAS_ASSIGNMENT_SCHOOL")
                    else:
                        notes.append("NO_LOGIN_SCOPE_SOURCE_FOR_ASSIGNMENT_SCHOOL")

                if effective_role not in PEDAGOGICAL_OWNER_ROLES:
                    blockers.append("EFFECTIVE_ROLE_NOT_PEDAGOGICAL_OWNER")

                user_tenant = str(user.get("mantenedora_id") or "")
                if not user_tenant or not tenant_id or user_tenant != tenant_id:
                    blockers.append("TENANT_SCOPE_MISMATCH")

            if source_staff is None:
                blockers.append("LEGACY_STAFF_MISSING")
            elif source_staff.get("user_id") and str(source_staff.get("user_id")) != teacher_id:
                blockers.append("LEGACY_STAFF_USER_ID_MISMATCH")

            if legacy_row:
                legacy_school = str(legacy_row.get("school_id") or "")
                if legacy_school and legacy_school != school_id:
                    blockers.append("LEGACY_ASSIGNMENT_SCHOOL_MISMATCH")
            else:
                blockers.append("LEGACY_ASSIGNMENT_MISSING")

            unique_blockers = sorted(set(blockers))
            unique_notes = sorted(set(notes))
            if unique_blockers:
                counts["blocked_assignments"] += 1
                for b in unique_blockers:
                    counts[b] += 1
                    teacher_blockers[teacher_id].add(b)
            else:
                counts["ok_assignments"] += 1
                counts["LOGIN_SCOPE_OK"] += 1
            for n in unique_notes:
                counts[n] += 1

            details.append({
                "assignment_id": assignment_id,
                "teacher_id": teacher_id,
                "teacher_name": (user or {}).get("full_name") or (user or {}).get("name") or a.get("teacher_name"),
                "assignment_school_id": school_id,
                "assignment_mantenedora_id": tenant_id,
                "legacy_assignment_id": source,
                "legacy_staff_id": source_staff_id or None,
                "base_role": (user or {}).get("role"),
                "effective_role": effective_role,
                "login_school_ids": login_school_ids,
                "active_2026_lotacoes": [
                    {"school_id": row.get("school_id"), "funcao": row.get("funcao"), "academic_year": row.get("academic_year")}
                    for row in exact_lots
                ],
                "blockers": unique_blockers,
                "notes": unique_notes,
            })

        blocked_teachers = {tid for tid, bs in teacher_blockers.items() if bs}
        report = {
            "status": "PASS" if counts["blocked_assignments"] == 0 else "REVIEW_REQUIRED",
            "mode": "38G_C3_ACCESS_SCOPE_CENSUS_READ_ONLY",
            "expected_assignments": args.expected_count,
            "audited_assignments": len(ids),
            "distinct_teachers": len(teacher_ids),
            "ok_assignments": counts["ok_assignments"],
            "blocked_assignments": counts["blocked_assignments"],
            "blocked_teachers": len(blocked_teachers),
            "counts": dict(sorted(counts.items())),
            "details": details,
            "mongo_writes": 0,
        }

        print("=== DVD 38G-C3 — CENSO DE ESCOPO DE LOGIN READ-ONLY ===")
        print("STATUS:", report["status"])
        print("ESPERADO:", report["expected_assignments"])
        print("AUDITADOS:", report["audited_assignments"])
        print("PROFESSORES_DISTINTOS:", report["distinct_teachers"])
        print("VINCULOS_LOGIN_OK:", report["ok_assignments"])
        print("VINCULOS_BLOQUEADOS:", report["blocked_assignments"])
        print("PROFESSORES_COM_BLOQUEIO:", report["blocked_teachers"])
        print("--- CONTAGENS ---")
        for key, value in sorted(report["counts"].items()):
            if key not in {"ok_assignments", "blocked_assignments"}:
                print(f"{key}: {value}")
        print("--- PRIMEIROS BLOQUEIOS ---")
        shown = 0
        for row in details:
            if not row["blockers"]:
                continue
            print(json.dumps({
                "assignment_id": row["assignment_id"],
                "teacher_id": row["teacher_id"],
                "teacher_name": row["teacher_name"],
                "assignment_school_id": row["assignment_school_id"],
                "effective_role": row["effective_role"],
                "login_school_ids": row["login_school_ids"],
                "blockers": row["blockers"],
                "notes": row["notes"],
            }, ensure_ascii=False))
            shown += 1
            if shown >= 20:
                break
        print("MONGO_WRITES: 0")

        if args.json:
            path = Path(args.json)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print("REPORT_JSON:", path)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
