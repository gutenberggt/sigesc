"""38G-C6 — auditoria global READ-ONLY da resolução users↔staff usada na autenticação.

Objetivo: validar se `staff.user_id` pode ser promovido a chave primária de
resolução de identidade no login/refresh, mantendo `staff.email` apenas como
fallback legado. Não altera MongoDB.
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

load_dotenv(BACKEND_DIR / ".env")

SCHOOL_ROLES = ["professor", "secretario", "coordenador", "auxiliar_secretaria", "diretor"]
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
    result: set[str] = set()
    for link in links or []:
        sid = link.get("school_id") if isinstance(link, Mapping) else None
        if sid:
            result.add(str(sid))
    return sorted(result)


def effective_context(user: Mapping[str, Any], lots: list[Mapping[str, Any]]) -> dict[str, Any]:
    role = str(user.get("role") or "")
    links = list(user.get("school_links") or [])
    if lots:
        highest = ROLE_PRIORITY.get(role, 0)
        links = []
        for lot in lots:
            funcao = str(lot.get("funcao") or "").lower()
            priority = ROLE_PRIORITY.get(funcao, 0)
            if priority > highest:
                highest = priority
                role = funcao
            links.append({"school_id": lot.get("school_id"), "role": funcao})
    return {"effective_role": role, "school_ids": school_ids_from_links(links)}


def compact_staff(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": row.get("id"),
            "user_id": row.get("user_id"),
            "email": row.get("email"),
            "status": row.get("status"),
            "mantenedora_id": row.get("mantenedora_id"),
            "name": row.get("nome") or row.get("full_name"),
        }
        for row in rows
    ]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--academic-year", type=int, default=2026)
    parser.add_argument("--json", default=None)
    args = parser.parse_args()

    assert_read_only()
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        db = client[os.environ["DB_NAME"]]
        users = await db.users.find(
            {"status": "active", "role": {"$in": SCHOOL_ROLES}},
            {"_id": 0, "id": 1, "email": 1, "full_name": 1, "name": 1,
             "role": 1, "status": 1, "school_links": 1, "mantenedora_id": 1},
        ).to_list(10000)
        user_ids = {str(u.get("id")) for u in users if u.get("id")}

        # Carrega somente campos de identidade; coleção de staff é pequena e esta
        # forma permite detectar também divergências de caixa no e-mail.
        staff = await db.staff.find(
            {},
            {"_id": 0, "id": 1, "user_id": 1, "email": 1, "nome": 1,
             "full_name": 1, "status": 1, "mantenedora_id": 1},
        ).to_list(50000)

        by_uid: dict[str, list[dict[str, Any]]] = defaultdict(list)
        by_email_exact: dict[str, list[dict[str, Any]]] = defaultdict(list)
        by_email_ci: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in staff:
            uid = str(row.get("user_id") or "").strip()
            email = str(row.get("email") or "").strip()
            if uid:
                by_uid[uid].append(row)
            if email:
                by_email_exact[email].append(row)
                by_email_ci[email.casefold()].append(row)

        relevant_staff_ids = {
            str(row.get("id"))
            for row in staff
            if row.get("id") and (
                str(row.get("user_id") or "") in user_ids
                or str(row.get("email") or "") in {
                    str(u.get("email") or "") for u in users if u.get("email")
                }
            )
        }
        lots = await db.school_assignments.find(
            {
                "staff_id": {"$in": sorted(relevant_staff_ids)},
                "status": "ativo",
                "academic_year": args.academic_year,
            },
            {"_id": 0, "id": 1, "staff_id": 1, "school_id": 1,
             "funcao": 1, "academic_year": 1, "status": 1, "mantenedora_id": 1},
        ).to_list(20000)
        lots_by_staff: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in lots:
            lots_by_staff[str(row.get("staff_id") or "")].append(row)

        counts = Counter()
        risks: list[dict[str, Any]] = []
        user_id_only: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []

        for user in users:
            counts["USERS_AUDITED"] += 1
            uid = str(user.get("id") or "")
            email = str(user.get("email") or "").strip()
            uid_rows = by_uid.get(uid, [])
            exact_rows = by_email_exact.get(email, []) if email else []
            ci_rows = by_email_ci.get(email.casefold(), []) if email else []

            counts[f"USER_ID_MATCHES_{min(len(uid_rows), 2)}" if len(uid_rows) <= 1 else "USER_ID_MATCHES_MULTIPLE"] += 1
            counts[f"EMAIL_EXACT_MATCHES_{min(len(exact_rows), 2)}" if len(exact_rows) <= 1 else "EMAIL_EXACT_MATCHES_MULTIPLE"] += 1

            issues: list[str] = []
            notes: list[str] = []

            if len(uid_rows) > 1:
                issues.append("DUPLICATE_STAFF_USER_ID")
            if len(exact_rows) > 1:
                issues.append("DUPLICATE_STAFF_EMAIL_EXACT")
            if not exact_rows and ci_rows:
                notes.append("EMAIL_CASE_ONLY_MATCH")

            uid_ids = {str(r.get("id") or "") for r in uid_rows}
            email_ids = {str(r.get("id") or "") for r in exact_rows}
            if uid_rows and exact_rows and uid_ids != email_ids:
                issues.append("USER_ID_AND_EMAIL_RESOLVE_DIFFERENT_STAFF_SET")

            for row in exact_rows:
                linked_uid = str(row.get("user_id") or "")
                if linked_uid and linked_uid != uid:
                    issues.append("EMAIL_STAFF_LINKED_TO_OTHER_USER")

            for row in uid_rows:
                status = str(row.get("status") or "")
                if status and status not in {"ativo", "active"}:
                    issues.append("USER_ID_STAFF_NOT_ACTIVE")
                user_mid = str(user.get("mantenedora_id") or "")
                staff_mid = str(row.get("mantenedora_id") or "")
                if user_mid and staff_mid and user_mid != staff_mid:
                    issues.append("USER_ID_STAFF_TENANT_MISMATCH")

            # Simulação fail-closed da resolução pretendida.
            selected = None
            resolution = "NONE"
            if len(uid_rows) == 1:
                selected = uid_rows[0]
                resolution = "USER_ID"
            elif len(uid_rows) == 0 and len(exact_rows) == 1:
                selected = exact_rows[0]
                resolution = "EMAIL_FALLBACK"
            elif len(uid_rows) > 1 or (len(uid_rows) == 0 and len(exact_rows) > 1):
                resolution = "AMBIGUOUS"

            if selected:
                selected_id = str(selected.get("id") or "")
                context = effective_context(user, lots_by_staff.get(selected_id, []))
            else:
                context = effective_context(user, [])

            if len(uid_rows) == 1 and len(exact_rows) == 0:
                counts["USER_ID_ONLY"] += 1
                if context["school_ids"]:
                    counts["USER_ID_ONLY_WITH_SCHOOL_SCOPE"] += 1
                else:
                    counts["USER_ID_ONLY_WITHOUT_SCHOOL_SCOPE"] += 1
                user_id_only.append({
                    "user_id": uid,
                    "name": user.get("full_name") or user.get("name"),
                    "user_email": email,
                    "staff": compact_staff(uid_rows)[0],
                    "active_lotacoes": [
                        {"school_id": l.get("school_id"), "funcao": l.get("funcao"),
                         "academic_year": l.get("academic_year")}
                        for l in lots_by_staff.get(str(uid_rows[0].get("id") or ""), [])
                    ],
                    "proposed_context": context,
                    "notes": sorted(set(notes)),
                })

            if not uid_rows and not exact_rows:
                counts["NO_STAFF_BY_USER_ID_OR_EXACT_EMAIL"] += 1
                unresolved.append({
                    "user_id": uid,
                    "name": user.get("full_name") or user.get("name"),
                    "user_email": email,
                    "base_role": user.get("role"),
                    "school_links": school_ids_from_links(user.get("school_links") or []),
                    "case_insensitive_email_staff": compact_staff(ci_rows),
                })

            unique_issues = sorted(set(issues))
            for issue in unique_issues:
                counts[issue] += 1
            if unique_issues:
                counts["USERS_WITH_IDENTITY_RISK"] += 1
                risks.append({
                    "user_id": uid,
                    "name": user.get("full_name") or user.get("name"),
                    "user_email": email,
                    "base_role": user.get("role"),
                    "user_mantenedora_id": user.get("mantenedora_id"),
                    "user_id_staff": compact_staff(uid_rows),
                    "email_exact_staff": compact_staff(exact_rows),
                    "email_case_insensitive_staff": compact_staff(ci_rows),
                    "resolution_fail_closed": resolution,
                    "issues": unique_issues,
                    "notes": sorted(set(notes)),
                })

        report = {
            "status": "PASS" if not risks else "REVIEW_REQUIRED",
            "mode": "38G_C6_AUTH_STAFF_IDENTITY_READ_ONLY",
            "academic_year": args.academic_year,
            "counts": dict(sorted(counts.items())),
            "risk_users": risks,
            "user_id_only": user_id_only,
            "unresolved": unresolved,
            "mongo_writes": 0,
        }

        print("=== DVD 38G-C6 — INTEGRIDADE users↔staff READ-ONLY ===")
        print("STATUS:", report["status"])
        ordered = [
            "USERS_AUDITED",
            "USER_ID_MATCHES_0", "USER_ID_MATCHES_1", "USER_ID_MATCHES_MULTIPLE",
            "EMAIL_EXACT_MATCHES_0", "EMAIL_EXACT_MATCHES_1", "EMAIL_EXACT_MATCHES_MULTIPLE",
            "USER_ID_ONLY", "USER_ID_ONLY_WITH_SCHOOL_SCOPE", "USER_ID_ONLY_WITHOUT_SCHOOL_SCOPE",
            "NO_STAFF_BY_USER_ID_OR_EXACT_EMAIL",
            "USERS_WITH_IDENTITY_RISK",
            "DUPLICATE_STAFF_USER_ID", "DUPLICATE_STAFF_EMAIL_EXACT",
            "USER_ID_AND_EMAIL_RESOLVE_DIFFERENT_STAFF_SET",
            "EMAIL_STAFF_LINKED_TO_OTHER_USER", "USER_ID_STAFF_NOT_ACTIVE",
            "USER_ID_STAFF_TENANT_MISMATCH",
        ]
        for key in ordered:
            print(f"{key}: {counts.get(key, 0)}")

        print("--- USER_ID_ONLY ---")
        for row in user_id_only:
            print(json.dumps(row, ensure_ascii=False, default=str))
        print("--- RISCOS DE IDENTIDADE ---")
        for row in risks:
            print(json.dumps(row, ensure_ascii=False, default=str))
        print("--- SEM STAFF POR USER_ID OU EMAIL EXATO ---")
        for row in unresolved:
            print(json.dumps(row, ensure_ascii=False, default=str))
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
