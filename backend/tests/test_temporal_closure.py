"""
Testes — Fechamento Temporal Composto (Passo 3 — Fev/2026).

Cobre os cenários obrigatórios do owner:
- Aluno sem evento → 1 período sole na matrícula ativa.
- Aluno com 1 transferência → 2 períodos (origem + destino).
- Aluno com supersession → apenas evento governante conta.
- Pendente é ignorado.
- Múltiplas movimentações no ano.
- Precedência (reclassificacao > transfer).
- Bimestre atribuído ao período cuja janela contém a data final do bimestre.
- compute_class_window_for_student retorna envelope correto.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.academic_event_lens import ensure_indexes  # noqa: E402
from utils.temporal_closure import (  # noqa: E402
    assign_bimesters_to_periods,
    compute_class_window_for_student,
    compute_composite_closure,
    compute_temporal_periods,
)


STUDENT_ID = "tc_stu_v1"
MANT_ID = "tc_mant_v1"
ACADEMIC_YEAR = 2026
CLASS_A = "tc_class_A"
CLASS_B = "tc_class_B"
CLASS_C = "tc_class_C"


@pytest_asyncio.fixture
async def db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    await ensure_indexes(db)
    yield db
    client.close()


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(db):
    """Limpa dados de teste entre runs."""
    await db.academic_events.delete_many({"student_id": STUDENT_ID})
    await db.enrollments.delete_many({"student_id": STUDENT_ID})
    await db.students.delete_many({"id": STUDENT_ID})
    await db.calendario_letivo.delete_many({"ano_letivo": ACADEMIC_YEAR})
    yield
    await db.academic_events.delete_many({"student_id": STUDENT_ID})
    await db.enrollments.delete_many({"student_id": STUDENT_ID})
    await db.students.delete_many({"id": STUDENT_ID})
    await db.calendario_letivo.delete_many({"ano_letivo": ACADEMIC_YEAR})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _seed_student(db, *, class_id: str = CLASS_A):
    await db.students.insert_one({
        "id": STUDENT_ID,
        "full_name": "Aluno Teste TC",
        "class_id": class_id,
        "mantenedora_id": MANT_ID,
    })


async def _seed_enrollment(db, *, class_id: str = CLASS_A):
    await db.enrollments.insert_one({
        "id": f"enr_{STUDENT_ID}_{class_id}",
        "student_id": STUDENT_ID,
        "class_id": class_id,
        "academic_year": ACADEMIC_YEAR,
        "status": "active",
        "mantenedora_id": MANT_ID,
        "created_at": _now_iso(),
    })


async def _seed_calendar(db):
    await db.calendario_letivo.insert_one({
        "ano_letivo": ACADEMIC_YEAR,
        "bimestre_1_inicio": "2026-02-01",
        "bimestre_1_fim": "2026-04-30",
        "bimestre_2_inicio": "2026-05-01",
        "bimestre_2_fim": "2026-07-15",
        "bimestre_3_inicio": "2026-08-01",
        "bimestre_3_fim": "2026-10-15",
        "bimestre_4_inicio": "2026-10-16",
        "bimestre_4_fim": "2026-12-15",
    })


async def _seed_event(
    db,
    *,
    event_id: str,
    event_type: str,
    effective_date: str,
    origin: str,
    destination: str,
    approval_status: str = "approved",
    superseded_by: str | None = None,
):
    await db.academic_events.insert_one({
        "id": event_id,
        "event_type": event_type,
        "effective_date": effective_date,
        "student_id": STUDENT_ID,
        "origin_class_id": origin,
        "destination_class_id": destination,
        "origin_school_id": None,
        "destination_school_id": None,
        "origin_teacher_id": None,
        "destination_teacher_id": None,
        "mantenedora_id": MANT_ID,
        "academic_year": ACADEMIC_YEAR,
        "rationale": "Teste de fechamento temporal composto — Passo 3 obrigatório.",
        "approval_required": True,
        "approval_status": approval_status,
        "approved_by_user_id": "u_admin",
        "approved_at": _now_iso(),
        "supersedes_event_id": None,
        "superseded_by_event_id": superseded_by,
        "superseded_at": _now_iso() if superseded_by else None,
        "superseded_reason": "Test supersession" if superseded_by else None,
        "created_by_user_id": "u_admin",
        "created_at": _now_iso(),
        "audit_trail": [],
    })


# ===========================================================================
# Cenários
# ===========================================================================
@pytest.mark.asyncio
async def test_no_events_returns_single_sole_period(db):
    await _seed_student(db, class_id=CLASS_A)
    await _seed_enrollment(db, class_id=CLASS_A)
    await _seed_calendar(db)

    periods = await compute_temporal_periods(
        db, student_id=STUDENT_ID, academic_year=ACADEMIC_YEAR, mantenedora_id=MANT_ID
    )
    assert len(periods) == 1
    p = periods[0]
    assert p["class_id"] == CLASS_A
    assert p["source"] == "sole"
    assert p["governing_event_id"] is None
    assert p["period_start"] == "2026-02-01"
    assert p["period_end"] == "2026-12-15"


@pytest.mark.asyncio
async def test_no_events_no_enrollment_returns_empty(db):
    """Aluno sem matrícula e sem evento → lista vazia."""
    periods = await compute_temporal_periods(
        db, student_id=STUDENT_ID, academic_year=ACADEMIC_YEAR, mantenedora_id=MANT_ID
    )
    assert periods == []


@pytest.mark.asyncio
async def test_single_transfer_creates_two_periods(db):
    await _seed_student(db, class_id=CLASS_A)
    await _seed_enrollment(db, class_id=CLASS_A)
    await _seed_calendar(db)
    await _seed_event(
        db, event_id="ev_1", event_type="transfer",
        effective_date="2026-08-15",
        origin=CLASS_A, destination=CLASS_B,
    )

    periods = await compute_temporal_periods(
        db, student_id=STUDENT_ID, academic_year=ACADEMIC_YEAR, mantenedora_id=MANT_ID
    )
    assert len(periods) == 2
    p0, p1 = periods
    assert p0["class_id"] == CLASS_A
    assert p0["source"] == "origin"
    assert p0["period_start"] == "2026-02-01"
    assert p0["period_end"] == "2026-08-14"
    assert p1["class_id"] == CLASS_B
    assert p1["source"] == "destination"
    assert p1["period_start"] == "2026-08-15"
    assert p1["period_end"] == "2026-12-15"
    assert p1["governing_event_id"] == "ev_1"


@pytest.mark.asyncio
async def test_pending_event_is_ignored(db):
    await _seed_student(db, class_id=CLASS_A)
    await _seed_enrollment(db, class_id=CLASS_A)
    await _seed_calendar(db)
    await _seed_event(
        db, event_id="ev_p", event_type="transfer",
        effective_date="2026-08-15",
        origin=CLASS_A, destination=CLASS_B,
        approval_status="pending",
    )

    periods = await compute_temporal_periods(
        db, student_id=STUDENT_ID, academic_year=ACADEMIC_YEAR, mantenedora_id=MANT_ID
    )
    # Sem evento aprovado → 1 período sole.
    assert len(periods) == 1
    assert periods[0]["source"] == "sole"


@pytest.mark.asyncio
async def test_superseded_event_is_ignored(db):
    """Evento superseded não influencia janelas."""
    await _seed_student(db, class_id=CLASS_A)
    await _seed_enrollment(db, class_id=CLASS_A)
    await _seed_calendar(db)
    # Evento velho (superseded)
    await _seed_event(
        db, event_id="ev_old", event_type="transfer",
        effective_date="2026-06-01",
        origin=CLASS_A, destination=CLASS_C,
        superseded_by="ev_new",
    )
    # Evento novo governante
    await _seed_event(
        db, event_id="ev_new", event_type="transfer",
        effective_date="2026-08-15",
        origin=CLASS_A, destination=CLASS_B,
    )

    periods = await compute_temporal_periods(
        db, student_id=STUDENT_ID, academic_year=ACADEMIC_YEAR, mantenedora_id=MANT_ID
    )
    # Deve ter exatamente 2 períodos (CLASS_A pré, CLASS_B pós) — CLASS_C nunca aparece.
    assert len(periods) == 2
    assert {p["class_id"] for p in periods} == {CLASS_A, CLASS_B}


@pytest.mark.asyncio
async def test_multiple_movements_create_multiple_periods(db):
    await _seed_student(db, class_id=CLASS_A)
    await _seed_enrollment(db, class_id=CLASS_A)
    await _seed_calendar(db)
    await _seed_event(
        db, event_id="ev_1", event_type="transfer",
        effective_date="2026-04-01",
        origin=CLASS_A, destination=CLASS_B,
    )
    await _seed_event(
        db, event_id="ev_2", event_type="remanejamento",
        effective_date="2026-09-01",
        origin=CLASS_B, destination=CLASS_C,
    )

    periods = await compute_temporal_periods(
        db, student_id=STUDENT_ID, academic_year=ACADEMIC_YEAR, mantenedora_id=MANT_ID
    )
    assert len(periods) == 3
    assert [p["class_id"] for p in periods] == [CLASS_A, CLASS_B, CLASS_C]
    assert periods[0]["period_end"] == "2026-03-31"
    assert periods[1]["period_start"] == "2026-04-01"
    assert periods[1]["period_end"] == "2026-08-31"
    assert periods[2]["period_start"] == "2026-09-01"


@pytest.mark.asyncio
async def test_precedence_reclassificacao_over_transfer(db):
    """Quando 2 eventos no mesmo segmento, reclassificacao tem precedência."""
    await _seed_student(db, class_id=CLASS_A)
    await _seed_enrollment(db, class_id=CLASS_A)
    await _seed_calendar(db)
    # Mesma data → mesmo segmento; reclassificacao deve vencer
    await _seed_event(
        db, event_id="ev_t", event_type="transfer",
        effective_date="2026-06-01",
        origin=CLASS_A, destination=CLASS_B,
    )
    await _seed_event(
        db, event_id="ev_r", event_type="reclassificacao",
        effective_date="2026-06-01",
        origin=CLASS_A, destination=CLASS_C,
    )

    periods = await compute_temporal_periods(
        db, student_id=STUDENT_ID, academic_year=ACADEMIC_YEAR, mantenedora_id=MANT_ID
    )
    # Pós-evento → CLASS_C (reclassificacao venceu)
    post = [p for p in periods if p["period_start"] >= "2026-06-01"]
    assert all(p["class_id"] == CLASS_C for p in post)
    assert post[0]["governing_event_type"] == "reclassificacao"


@pytest.mark.asyncio
async def test_bimester_assigned_to_period_owning_end_date(db):
    await _seed_student(db, class_id=CLASS_A)
    await _seed_enrollment(db, class_id=CLASS_A)
    await _seed_calendar(db)
    # Transferência em 06/01 — bimestre 2 termina em 07/15 (já é destino)
    # bimestre 1 termina em 04/30 (origem)
    await _seed_event(
        db, event_id="ev_b", event_type="transfer",
        effective_date="2026-06-01",
        origin=CLASS_A, destination=CLASS_B,
    )

    closure = await compute_composite_closure(
        db, student_id=STUDENT_ID, academic_year=ACADEMIC_YEAR, mantenedora_id=MANT_ID
    )
    assert closure["is_composite"] is True
    bims = {b["bimester"]: b for b in closure["bimesters"]}
    assert bims[1]["class_id"] == CLASS_A      # B1 fecha em 04/30 → origem
    assert bims[2]["class_id"] == CLASS_B      # B2 fecha em 07/15 → destino
    assert bims[3]["class_id"] == CLASS_B
    assert bims[4]["class_id"] == CLASS_B


@pytest.mark.asyncio
async def test_compute_class_window_returns_envelope(db):
    await _seed_student(db, class_id=CLASS_A)
    await _seed_enrollment(db, class_id=CLASS_A)
    await _seed_calendar(db)
    await _seed_event(
        db, event_id="ev_w", event_type="transfer",
        effective_date="2026-06-01",
        origin=CLASS_A, destination=CLASS_B,
    )

    win_a = await compute_class_window_for_student(
        db, student_id=STUDENT_ID, class_id=CLASS_A,
        academic_year=ACADEMIC_YEAR, mantenedora_id=MANT_ID,
    )
    assert win_a is not None
    assert win_a["envelope_start"] == "2026-02-01"
    assert win_a["envelope_end"] == "2026-05-31"

    win_b = await compute_class_window_for_student(
        db, student_id=STUDENT_ID, class_id=CLASS_B,
        academic_year=ACADEMIC_YEAR, mantenedora_id=MANT_ID,
    )
    assert win_b is not None
    assert win_b["envelope_start"] == "2026-06-01"
    assert win_b["envelope_end"] == "2026-12-15"

    # Turma não relacionada → None
    win_c = await compute_class_window_for_student(
        db, student_id=STUDENT_ID, class_id=CLASS_C,
        academic_year=ACADEMIC_YEAR, mantenedora_id=MANT_ID,
    )
    assert win_c is None


@pytest.mark.asyncio
async def test_assign_bimesters_orphan_when_outside_periods():
    """Bimestre fora de qualquer período → period_index None."""
    bim_cal = [
        {"bimester": 1, "start": __import__("datetime").date(2026, 2, 1),
         "end": __import__("datetime").date(2026, 4, 30)},
        {"bimester": 4, "start": __import__("datetime").date(2026, 10, 16),
         "end": __import__("datetime").date(2026, 12, 15)},
    ]
    periods = [
        {
            "period_index": 0, "class_id": "X", "source": "sole",
            "period_start": "2026-05-01", "period_end": "2026-09-30",
            "governing_event_id": None,
        },
    ]
    out = assign_bimesters_to_periods(bim_cal, periods)
    assert out[0]["period_index"] is None  # B1 fora
    assert out[1]["period_index"] is None  # B4 fora


@pytest.mark.asyncio
async def test_composite_closure_returns_canonical_shape(db):
    await _seed_student(db, class_id=CLASS_A)
    await _seed_enrollment(db, class_id=CLASS_A)
    await _seed_calendar(db)

    closure = await compute_composite_closure(
        db, student_id=STUDENT_ID, academic_year=ACADEMIC_YEAR, mantenedora_id=MANT_ID
    )
    assert closure["closure_version"] == "1"
    assert closure["student_id"] == STUDENT_ID
    assert closure["academic_year"] == ACADEMIC_YEAR
    assert "periods" in closure and isinstance(closure["periods"], list)
    assert "bimesters" in closure and isinstance(closure["bimesters"], list)
    assert closure["is_composite"] is False
