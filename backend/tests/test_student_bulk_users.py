"""
Testes do service de criação em massa de usuários de alunos.
Valida regras de email/senha e idempotência sem depender de HTTP.
"""
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

from services.student_account_service import (
    _parse_birth_date,
    _build_email_base,
    _slug,
    build_plan_for_students,
    apply_plan,
)

load_dotenv()


def test_parse_birth_date_variants():
    assert _parse_birth_date("2014-03-15") == ("15", "03", "2014")
    assert _parse_birth_date("15/03/2014") == ("15", "03", "2014")
    assert _parse_birth_date("2014/03/15") == ("15", "03", "2014")
    assert _parse_birth_date("2014-03-15T00:00:00") == ("15", "03", "2014")
    assert _parse_birth_date(None) is None
    assert _parse_birth_date("abc") is None


def test_slug_removes_accents_and_special_chars():
    assert _slug("JOSÉ DA SILVA") == "josedasilva"
    assert _slug("ANA-MARIA") == "anamaria"
    assert _slug("Ção") == "cao"


def test_build_email_base_first_and_last():
    assert _build_email_base("ANA MARIA OLIVEIRA", "03") == "anaoliveira03"
    assert _build_email_base("JOÃO  SILVA", "11") == "joaosilva11"
    assert _build_email_base("ANA", "03") is None
    assert _build_email_base("", "03") is None


async def _async_plan_shape():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    plan = await build_plan_for_students(db, mantenedora_id="a991c1ac-56b1-46a8-b122-effedbe19b21")
    assert "totals" in plan
    assert plan["totals"]["scanned"] >= 1
    for row in plan["to_create"]:
        assert row["email"].endswith("@sigesc.com")
        assert len(row["password"]) == 8 and row["password"].isdigit()


def test_build_plan_shape():
    asyncio.run(_async_plan_shape())


async def _async_idempotent():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    plan1 = await build_plan_for_students(db)
    res1 = await apply_plan(db, plan1)
    inserted_first = res1["inserted"]
    plan2 = await build_plan_for_students(db)
    assert plan2["totals"]["to_create"] == 0
    assert plan2["totals"]["already_has_user"] >= inserted_first


def test_apply_is_idempotent():
    asyncio.run(_async_idempotent())
