"""
Testes — Academic Event Lens (Fase 3).

Cobre os cenários obrigatórios do owner Fev/2026 (cf. ACADEMIC_EVENT_CONTRACT.md):
- test_origin_teacher_can_edit_before_effective_date
- test_origin_teacher_blocked_after_effective_date
- test_destination_teacher_readonly_before_effective_date
- test_destination_teacher_editable_after_effective_date
- test_superseded_event_not_deleted
- test_governing_event_precedence
- test_historical_visibility_preserved_after_transfer
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.academic_event_lens import (  # noqa: E402
    ACADEMIC_EVENT_PRECEDENCE,
    DECISION_VERSION,
    annotate_items_with_lens,
    ensure_indexes,
    pick_governing_event,
    resolve_student_ownership,
)


@pytest_asyncio.fixture
async def db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    await ensure_indexes(db)
    yield db
    client.close()


@pytest_asyncio.fixture
async def base_event(db):
    """Cria um evento de transferência ativa: stuA migra de classO para classD em 2026-08-15."""
    ev = {
        "id": "ae_test_transfer",
        "event_type": "transfer",
        "effective_date": "2026-08-15",
        "student_id": "ae_stu",
        "origin_class_id": "ae_class_origin",
        "destination_class_id": "ae_class_dest",
        "origin_teacher_id": "tch_origin",
        "destination_teacher_id": "tch_dest",
        "mantenedora_id": "ae_mant",
        "academic_year": 2026,
        "rationale": "Teste — transferência por requisição do responsável (motivos diversos).",
        "approval_required": True,
        "approval_status": "approved",
        "approved_by_user_id": "u_admin",
        "approved_at": "2026-08-10T10:00:00+00:00",
        "rejection_reason": None,
        "created_by_user_id": "u_admin",
        "created_at": "2026-08-10T10:00:00+00:00",
        "supersedes_event_id": None,
        "superseded_by_event_id": None,
        "audit_trail": [],
    }
    await db.academic_events.delete_many({"student_id": "ae_stu"})
    await db.academic_events.insert_one(ev)
    yield ev
    await db.academic_events.delete_many({"student_id": "ae_stu"})


# =========================================================================
# Cenários canônicos do owner
# =========================================================================
@pytest.mark.asyncio
async def test_origin_teacher_can_edit_before_effective_date(db, base_event):
    """Cenário §4.1: registros pré-effective_date editáveis na origem."""
    state = await resolve_student_ownership(
        db, student_id="ae_stu", class_id="ae_class_origin",
        target_date="2026-05-10",  # antes de 2026-08-15
        mantenedora_id="ae_mant",
    )
    assert state["editable"] is True
    assert state["source"] == "origin"
    assert state["sync_mode"] == "origin_authoritative"
    assert state["owner_teacher_id"] == "tch_origin"
    assert state["blocked_reason"] is None
    assert state["governing_event_type"] == "transfer"
    assert state["historical_cutoff_date"] == "2026-08-15"
    assert state["decision_version"] == DECISION_VERSION


@pytest.mark.asyncio
async def test_origin_teacher_blocked_after_effective_date(db, base_event):
    """Cenário §5.1: registros pós-effective_date bloqueados na origem."""
    state = await resolve_student_ownership(
        db, student_id="ae_stu", class_id="ae_class_origin",
        target_date="2026-09-10",  # após 2026-08-15
        mantenedora_id="ae_mant",
    )
    assert state["editable"] is False
    assert state["source"] == "origin"
    assert state["sync_mode"] == "isolated"
    assert state["blocked_reason"] == "AFTER_EFFECTIVE_DATE"
    assert state["governing_event_id"] == "ae_test_transfer"


@pytest.mark.asyncio
async def test_destination_teacher_readonly_before_effective_date(db, base_event):
    """Cenário §4.2: destino vê registros pré-evento como herdados read-only."""
    state = await resolve_student_ownership(
        db, student_id="ae_stu", class_id="ae_class_dest",
        target_date="2026-05-10",
        mantenedora_id="ae_mant",
    )
    assert state["editable"] is False
    assert state["source"] == "destination"
    assert state["sync_mode"] == "origin_authoritative"
    assert state["blocked_reason"] == "BEFORE_EFFECTIVE_DATE_DESTINATION"
    assert state["owner_teacher_id"] == "tch_origin"  # origem é dona


@pytest.mark.asyncio
async def test_destination_teacher_editable_after_effective_date(db, base_event):
    """Cenário §5.2: destino exclusivo após effective_date."""
    state = await resolve_student_ownership(
        db, student_id="ae_stu", class_id="ae_class_dest",
        target_date="2026-09-10",
        mantenedora_id="ae_mant",
    )
    assert state["editable"] is True
    assert state["source"] == "destination"
    assert state["sync_mode"] == "isolated"
    assert state["owner_teacher_id"] == "tch_dest"
    assert state["blocked_reason"] is None


@pytest.mark.asyncio
async def test_superseded_event_not_deleted(db, base_event):
    """Cenário §17.1: supersession não deleta — antigo permanece com flag."""
    # Marca antigo como superseded
    await db.academic_events.update_one(
        {"id": "ae_test_transfer"},
        {"$set": {"approval_status": "superseded",
                  "superseded_by_event_id": "ae_new_event"}},
    )
    new_ev = {k: v for k, v in base_event.items() if k != "_id"}
    new_ev.update({
        "id": "ae_new_event",
        "effective_date": "2026-09-01",
        "supersedes_event_id": "ae_test_transfer",
        "superseded_by_event_id": None,
        "approval_status": "approved",
    })
    await db.academic_events.insert_one(new_ev)

    # Antigo continua na coleção
    old = await db.academic_events.find_one({"id": "ae_test_transfer"}, {"_id": 0})
    assert old is not None
    assert old["approval_status"] == "superseded"
    assert old["superseded_by_event_id"] == "ae_new_event"

    # Lens ignora antigo, usa novo
    state = await resolve_student_ownership(
        db, student_id="ae_stu", class_id="ae_class_dest",
        target_date="2026-08-20",  # ainda antes do NOVO effective_date 2026-09-01
        mantenedora_id="ae_mant",
    )
    # Como o evento novo tem effective_date 2026-09-01, em 2026-08-20 destino é READ-ONLY
    assert state["governing_event_id"] == "ae_new_event"
    assert state["editable"] is False
    assert state["blocked_reason"] == "BEFORE_EFFECTIVE_DATE_DESTINATION"

    await db.academic_events.delete_one({"id": "ae_new_event"})


@pytest.mark.asyncio
async def test_governing_event_precedence(db):
    """Cenário §15: reclassificacao > progressao_parcial > remanejamento > transfer."""
    base = {
        "student_id": "ae_stu_prec",
        "origin_class_id": "ae_o", "destination_class_id": "ae_d",
        "academic_year": 2026, "approval_status": "approved",
        "superseded_by_event_id": None,
        "rationale": "x" * 35, "created_at": "2026-01-01T00:00:00Z",
    }
    events = [
        {**base, "id": "e1", "event_type": "transfer", "effective_date": "2026-09-01"},
        {**base, "id": "e2", "event_type": "remanejamento", "effective_date": "2026-08-01"},
        {**base, "id": "e3", "event_type": "reclassificacao", "effective_date": "2026-07-01"},
    ]
    chosen = pick_governing_event(events)
    assert chosen["id"] == "e3"  # reclassificacao vence apesar de data anterior
    # Sem reclassificacao, próximo é progressao (não tem) → remanejamento
    chosen2 = pick_governing_event(events[:2])
    assert chosen2["id"] == "e2"  # remanejamento vence sobre transfer

    # Com mesma precedência, effective_date mais recente vence
    same_prec = [
        {**base, "id": "x1", "event_type": "transfer", "effective_date": "2026-03-01"},
        {**base, "id": "x2", "event_type": "transfer", "effective_date": "2026-09-01"},
    ]
    chosen3 = pick_governing_event(same_prec)
    assert chosen3["id"] == "x2"


@pytest.mark.asyncio
async def test_historical_visibility_preserved_after_transfer(db, base_event):
    """Cenário §16.1: visibilidade preservada — `visible: true` SEMPRE."""
    # Origem após movimentação (aluno foi embora) — DEVE permanecer visível
    state_origin_after = await resolve_student_ownership(
        db, student_id="ae_stu", class_id="ae_class_origin",
        target_date="2026-12-15",
        mantenedora_id="ae_mant",
    )
    assert state_origin_after["visible"] is True
    assert state_origin_after["editable"] is False  # mas não editável

    # Destino antes da movimentação — visível como herdado
    state_dest_before = await resolve_student_ownership(
        db, student_id="ae_stu", class_id="ae_class_dest",
        target_date="2026-04-10",
        mantenedora_id="ae_mant",
    )
    assert state_dest_before["visible"] is True


# =========================================================================
# Anotação de listas (não filtra)
# =========================================================================
@pytest.mark.asyncio
async def test_annotate_items_does_not_filter(db, base_event):
    items = [
        {"student_id": "ae_stu", "student_name": "Aluno Teste"},
        {"student_id": "ae_stu_outro", "student_name": "Outro"},
    ]
    annotated = await annotate_items_with_lens(
        db, items,
        class_id="ae_class_origin",
        course_id=None,
        target_date="2026-12-15",
        mantenedora_id="ae_mant",
    )
    assert len(annotated) == 2  # nada foi filtrado
    aff = next(it for it in annotated if it["student_id"] == "ae_stu")
    assert aff["_locked"] is True
    assert aff["_lock_reason"] == "AFTER_EFFECTIVE_DATE"
    other = next(it for it in annotated if it["student_id"] == "ae_stu_outro")
    assert other["_locked"] is False


# =========================================================================
# Sem evento — comportamento padrão
# =========================================================================
@pytest.mark.asyncio
async def test_no_event_returns_default_decision(db):
    state = await resolve_student_ownership(
        db, student_id="ae_no_event_stu", class_id="ae_no_class",
        target_date="2026-08-15", mantenedora_id="ae_mant",
    )
    assert state["editable"] is True
    assert state["source"] == "neutral"
    assert state["governing_event_id"] is None
    assert state["sync_mode"] == "neutral"


# =========================================================================
# Pending events ignorados pela lens
# =========================================================================
@pytest.mark.asyncio
async def test_pending_event_ignored_by_lens(db):
    pending = {
        "id": "ae_pending", "event_type": "transfer", "effective_date": "2026-05-01",
        "student_id": "ae_stu_p", "origin_class_id": "ae_o_p", "destination_class_id": "ae_d_p",
        "mantenedora_id": "ae_mant", "academic_year": 2026,
        "approval_status": "pending", "superseded_by_event_id": None,
        "rationale": "x" * 35, "created_at": "2026-01-01",
    }
    await db.academic_events.insert_one(pending)
    try:
        state = await resolve_student_ownership(
            db, student_id="ae_stu_p", class_id="ae_o_p",
            target_date="2026-08-15", mantenedora_id="ae_mant",
        )
        assert state["governing_event_id"] is None
        assert state["editable"] is True
    finally:
        await db.academic_events.delete_one({"id": "ae_pending"})


# =========================================================================
# Constantes
# =========================================================================
def test_precedence_constant_order():
    assert ACADEMIC_EVENT_PRECEDENCE == (
        "reclassificacao", "progressao_parcial", "remanejamento", "transfer",
    )


def test_decision_version_is_v1():
    assert DECISION_VERSION == "1"
