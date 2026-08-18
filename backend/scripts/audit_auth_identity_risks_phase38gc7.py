"""38G-C7 — diagnóstico READ-ONLY dos riscos de identidade encontrados no 38G-C6.

Foco:
- Sandra Gomes de Oliveira: e-mail exato associado a dois registros staff;
- Joana Darc Teotonio Monteiro: duas contas users, com staff ligado a apenas uma;
- preserva o princípio fail-closed e não altera MongoDB.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Mapping

from motor.motor_asyncio import AsyncIOMotorClient

MUTATOR_TOKENS = (
    ".insert_one(", ".insert_many(", ".update_one(", ".update_many(",
    ".replace_one(", ".delete_one(", ".delete_many(", ".bulk_write(",
    ".find_one_and_update(", ".find_one_and_delete(", ".find_one_and_replace(",
)

SANDRA_USER_ID = "af6a3ac3-d05c-40c4-a449-0f0a2c2e1deb"
SANDRA_EMAIL = "oliveirasophia2010@hotmail.com"
JOANA_CANONICAL_USER_ID = "3ef89160-eff8-4a80-9985-f49ba942bbf9"
JOANA_LEGACY_USER_ID = "7f62ef1d-9b27-4450-9416-78bb0ee94fb9"
JOANA_STAFF_EMAIL = "joanadarc7173@gmail.com"
YEAR = 2026


def assert_read_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    executable = "\n".join(
        line for line in source.splitlines()
        if "MUTATOR_TOKENS" not in line and not line.lstrip().startswith('"')
    )
    forbidden = [token for token in MUTATOR_TOKENS if token in executable]
    if forbidden:
        raise RuntimeError(f"READ_ONLY_GUARD_FAILED forbidden={forbidden}")


def clean(doc: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if doc is None:
        return None
    result = dict(doc)
    result.pop("_id", None)
    result.pop("password_hash", None)
    return result


def dump(label: str, value: Any) -> None:
    print(f"\n=== {label} ===")
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


async def users_by_ids(db, ids: list[str]) -> list[dict[str, Any]]:
    rows = await db.users.find(
        {"id": {"$in": ids}},
        {
            "_id": 0,
            "id": 1,
            "full_name": 1,
            "name": 1,
            "email": 1,
            "role": 1,
            "status": 1,
            "school_links": 1,
            "mantenedora_id": 1,
            "created_at": 1,
            "updated_at": 1,
        },
    ).to_list(20)
    return sorted(rows, key=lambda r: str(r.get("id") or ""))


async def staff_for_user_or_email(db, user_ids: list[str], emails: list[str]) -> list[dict[str, Any]]:
    rows = await db.staff.find(
        {"$or": [
            {"user_id": {"$in": user_ids}},
            {"email": {"$in": emails}},
        ]},
        {
            "_id": 0,
            "id": 1,
            "user_id": 1,
            "nome": 1,
            "full_name": 1,
            "email": 1,
            "cpf": 1,
            "status": 1,
            "mantenedora_id": 1,
            "created_at": 1,
            "updated_at": 1,
        },
    ).to_list(50)
    return sorted(rows, key=lambda r: str(r.get("id") or ""))


async def related_records(db, staff_ids: list[str], user_ids: list[str]) -> dict[str, Any]:
    lotacoes = await db.school_assignments.find(
        {"staff_id": {"$in": staff_ids}},
        {
            "_id": 0,
            "id": 1,
            "staff_id": 1,
            "school_id": 1,
            "funcao": 1,
            "status": 1,
            "academic_year": 1,
            "mantenedora_id": 1,
        },
    ).to_list(200)

    teacher_legacy = await db.teacher_assignments.find(
        {
            "staff_id": {"$in": staff_ids},
            "academic_year": {"$in": [YEAR, str(YEAR)]},
        },
        {
            "_id": 0,
            "id": 1,
            "staff_id": 1,
            "school_id": 1,
            "class_id": 1,
            "course_id": 1,
            "academic_year": 1,
            "status": 1,
            "is_substituicao": 1,
        },
    ).to_list(1000)

    dvd = await db.teacher_class_assignments.find(
        {"teacher_id": {"$in": user_ids}, "deleted": {"$ne": True}},
        {
            "_id": 0,
            "id": 1,
            "teacher_id": 1,
            "teacher_name": 1,
            "school_id": 1,
            "class_id": 1,
            "class_name": 1,
            "component_id": 1,
            "component_name": 1,
            "valid_from": 1,
            "valid_until": 1,
            "source": 1,
            "cutover_provenance": 1,
        },
    ).to_list(1000)

    school_ids = sorted({
        str(r.get("school_id"))
        for r in [*lotacoes, *teacher_legacy, *dvd]
        if r.get("school_id")
    })
    schools = await db.schools.find(
        {"id": {"$in": school_ids}},
        {"_id": 0, "id": 1, "name": 1, "status": 1, "mantenedora_id": 1},
    ).to_list(100)
    schools_by_id = {str(r.get("id")): r for r in schools if r.get("id")}

    for row in lotacoes:
        row["school_name"] = (schools_by_id.get(str(row.get("school_id"))) or {}).get("name")
    for row in teacher_legacy:
        row["school_name"] = (schools_by_id.get(str(row.get("school_id"))) or {}).get("name")
    for row in dvd:
        row["school_name"] = (schools_by_id.get(str(row.get("school_id"))) or {}).get("name")

    return {
        "school_assignments": sorted(lotacoes, key=lambda r: (str(r.get("staff_id")), str(r.get("academic_year")), str(r.get("school_id")))),
        "teacher_assignments_2026": sorted(teacher_legacy, key=lambda r: (str(r.get("staff_id")), str(r.get("class_id")), str(r.get("course_id")))),
        "dvd_assignments": sorted(dvd, key=lambda r: (str(r.get("teacher_id")), str(r.get("class_id")), str(r.get("component_id")))),
    }


async def recent_audit(db, user_ids: list[str]) -> list[dict[str, Any]]:
    rows = await db.audit_logs.find(
        {"user_id": {"$in": user_ids}},
        {
            "_id": 0,
            "timestamp": 1,
            "user_id": 1,
            "action": 1,
            "collection": 1,
            "document_id": 1,
            "description": 1,
        },
    ).sort("timestamp", -1).to_list(100)
    return rows


async def main() -> None:
    assert_read_only()
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        db = client[os.environ["DB_NAME"]]

        sandra_users = await users_by_ids(db, [SANDRA_USER_ID])
        sandra_staff = await staff_for_user_or_email(db, [SANDRA_USER_ID], [SANDRA_EMAIL])
        sandra_staff_ids = [str(r["id"]) for r in sandra_staff if r.get("id")]
        sandra_related = await related_records(db, sandra_staff_ids, [SANDRA_USER_ID])
        sandra_audit = await recent_audit(db, [SANDRA_USER_ID])

        joana_ids = [JOANA_CANONICAL_USER_ID, JOANA_LEGACY_USER_ID]
        joana_users = await users_by_ids(db, joana_ids)
        joana_emails = [JOANA_STAFF_EMAIL] + [str(r.get("email") or "") for r in joana_users if r.get("email")]
        joana_staff = await staff_for_user_or_email(db, joana_ids, sorted(set(joana_emails)))
        joana_staff_ids = [str(r["id"]) for r in joana_staff if r.get("id")]
        joana_related = await related_records(db, joana_staff_ids, joana_ids)
        joana_audit = await recent_audit(db, joana_ids)

        report = {
            "status": "REVIEW_REQUIRED",
            "mode": "38G_C7_TARGETED_IDENTITY_RISK_READ_ONLY",
            "sandra": {
                "users": sandra_users,
                "staff": sandra_staff,
                "related": sandra_related,
                "recent_audit": sandra_audit,
            },
            "joana": {
                "users": joana_users,
                "staff": joana_staff,
                "related": joana_related,
                "recent_audit": joana_audit,
            },
            "mongo_writes": 0,
        }

        print("=== DVD 38G-C7 — DIAGNOSTICO DIRECIONADO DE IDENTIDADE READ-ONLY ===")
        print("STATUS: REVIEW_REQUIRED")
        print("SANDRA_USERS:", len(sandra_users))
        print("SANDRA_STAFF_CANDIDATES:", len(sandra_staff))
        print("SANDRA_LOTACOES:", len(sandra_related["school_assignments"]))
        print("SANDRA_TEACHER_ASSIGNMENTS_2026:", len(sandra_related["teacher_assignments_2026"]))
        print("SANDRA_DVD_ASSIGNMENTS:", len(sandra_related["dvd_assignments"]))
        print("JOANA_USERS:", len(joana_users))
        print("JOANA_STAFF_CANDIDATES:", len(joana_staff))
        print("JOANA_LOTACOES:", len(joana_related["school_assignments"]))
        print("JOANA_TEACHER_ASSIGNMENTS_2026:", len(joana_related["teacher_assignments_2026"]))
        print("JOANA_DVD_ASSIGNMENTS:", len(joana_related["dvd_assignments"]))
        print("MONGO_WRITES: 0")

        dump("SANDRA — USERS", sandra_users)
        dump("SANDRA — STAFF CANDIDATOS", sandra_staff)
        dump("SANDRA — LOTACOES", sandra_related["school_assignments"])
        dump("SANDRA — TEACHER_ASSIGNMENTS 2026", sandra_related["teacher_assignments_2026"])
        dump("SANDRA — DVD ASSIGNMENTS", sandra_related["dvd_assignments"])
        dump("SANDRA — AUDITORIA RECENTE", sandra_audit[:30])

        dump("JOANA — USERS", joana_users)
        dump("JOANA — STAFF CANDIDATOS", joana_staff)
        dump("JOANA — LOTACOES", joana_related["school_assignments"])
        dump("JOANA — TEACHER_ASSIGNMENTS 2026", joana_related["teacher_assignments_2026"])
        dump("JOANA — DVD ASSIGNMENTS", joana_related["dvd_assignments"])
        dump("JOANA — AUDITORIA RECENTE", joana_audit[:50])

        output = "/tmp/dvd38gc7-report.json"
        Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print("REPORT_JSON:", output)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
