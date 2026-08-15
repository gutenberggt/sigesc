"""
Testes — Resolução Temporal de Escola (Fase 1.5) + Histórico Escolar.

Cobre:
  - utils/school_resolution.resolve_school_at (intervalos, bordas, fallback)
  - utils/school_resolution.resolve_school_period (segmentação por intervalo)
  - history_consolidator: ano da turma transferida é atribuído à escola CORRETA
    (origem onde o ano foi conduzido), não ao destino do re-homing.
"""
from __future__ import annotations

import os
import uuid
import asyncio
import pytest
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from utils.school_resolution import resolve_school_at, resolve_school_period
from services.history_consolidator import build_consolidated_history

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

A = "school-A"
B = "school-B"
HIST = [
    {"school_id": A, "start_date": "2026-02-05T00:00:00+00:00", "end_date": "2026-07-01T00:00:00+00:00"},
    {"school_id": B, "start_date": "2026-07-01T00:00:00+00:00", "end_date": None},
]


# ----------------------------------------------------------------- resolve_school_at
def test_resolve_no_history_uses_fallback():
    assert resolve_school_at(None, "2026-05-01", fallback_school_id="cur") == "cur"
    assert resolve_school_at([], "2026-05-01", fallback_school_id="cur") == "cur"


def test_resolve_before_first_start_returns_origin():
    # 1 jan 2026 antecede o início (5 fev) → origem A
    assert resolve_school_at(HIST, "2026-01-01") == A


def test_resolve_inside_origin_interval():
    assert resolve_school_at(HIST, "2026-05-01") == A
    assert resolve_school_at(HIST, "2026-06-30") == A


def test_resolve_after_transfer_returns_destination():
    assert resolve_school_at(HIST, "2026-09-01") == B
    assert resolve_school_at(HIST, "2027-01-01") == B  # intervalo aberto


def test_resolve_boundary_is_half_open():
    # exatamente no start do destino → B (intervalo [start, end))
    assert resolve_school_at(HIST, "2026-07-01") == B


def test_resolve_no_reference_uses_current_open_interval():
    assert resolve_school_at(HIST, None, fallback_school_id="cur") == B


# ----------------------------------------------------------------- resolve_school_period
def test_period_splits_across_transfer():
    segs = resolve_school_period(HIST, "2026-05-01", "2026-09-30")
    ids = [s["school_id"] for s in segs]
    assert ids == [A, B]


def test_period_fully_in_origin():
    segs = resolve_school_period(HIST, "2026-03-01", "2026-06-01")
    assert [s["school_id"] for s in segs] == [A]


def test_period_no_history_single_segment():
    segs = resolve_school_period(None, "2026-01-01", "2026-12-31", fallback_school_id="cur")
    assert len(segs) == 1 and segs[0]["school_id"] == "cur"


# ----------------------------------------------------------------- Histórico Escolar (integração)
@pytest.fixture
def db_and_seed():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    sfx = uuid.uuid4().hex[:8]
    sid = f"stud-{sfx}"
    cid = f"cls-{sfx}"
    origin_id = f"orig-{sfx}"
    dest_id = f"dest-{sfx}"

    async def seed():
        await db.schools.insert_one({"id": origin_id, "name": "Escola Origem Hist", "status": "active"})
        await db.schools.insert_one({"id": dest_id, "name": "Escola Destino Hist", "status": "active"})
        # turma transferida: A (origem) → B (destino) em jul/2026
        await db.classes.insert_one({
            "id": cid, "school_id": dest_id, "academic_year": 2026,
            "grade_level": "5º ano", "course_ids": [],
            "school_history": [
                {"school_id": origin_id, "start_date": "2026-02-05T00:00:00+00:00", "end_date": "2026-07-01T00:00:00+00:00"},
                {"school_id": dest_id, "start_date": "2026-07-01T00:00:00+00:00", "end_date": None},
            ],
        })
        await db.students.insert_one({"id": sid, "full_name": "Aluno Hist", "school_id": dest_id, "class_id": cid})
        await db.enrollments.insert_one({
            "id": f"enr-{sfx}", "student_id": sid, "class_id": cid,
            "academic_year": 2026, "status": "completed", "school_id": dest_id,
            "created_at": "2026-02-10T00:00:00+00:00",
        })

    async def cleanup():
        await db.schools.delete_many({"id": {"$in": [origin_id, dest_id]}})
        await db.classes.delete_one({"id": cid})
        await db.students.delete_one({"id": sid})
        await db.enrollments.delete_many({"student_id": sid})

    asyncio.get_event_loop().run_until_complete(seed())
    yield {"db": db, "sid": sid, "cid": cid, "origin": origin_id, "dest": dest_id}
    asyncio.get_event_loop().run_until_complete(cleanup())


def test_history_attributes_year_to_origin_not_destination(db_and_seed):
    ctx = db_and_seed
    history = asyncio.get_event_loop().run_until_complete(
        build_consolidated_history(ctx["db"], student_id=ctx["sid"])
    )
    rows_2026 = [r for r in history["records"] if r.get("ano_letivo") == "2026"]
    assert rows_2026, "deveria haver registro consolidado de 2026"
    row = rows_2026[0]
    # Apesar de classes.school_id == destino, o Histórico atribui à ORIGEM
    # (escola onde o ano letivo de 2026 foi efetivamente conduzido).
    assert row["escola"] == "Escola Origem Hist", row
    assert row["_school_id"] == ctx["origin"]
