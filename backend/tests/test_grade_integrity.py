"""Tests do Integrity Report da Grade Horária (Fase 6 — Mai/2026).

Cada teste constrói um cenário isolado e mínimo via inserção direta no
banco, então invoca o serviço diretamente (não HTTP — mais rápido e
deterministico).
"""
import asyncio
import os
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

from services.grade_integrity_service import compute_integrity_report

load_dotenv()


@pytest.fixture
def db():
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return cli[os.environ["DB_NAME"]]


@pytest.fixture
def cleanup():
    """Marca docs criados com tag única e limpa ao final."""
    tag = f"test-integrity-{uuid.uuid4().hex[:8]}"
    created = {"class_ids": [], "assignment_ids": [], "user_ids": [], "tag": tag}
    yield created
    # cleanup síncrono via pymongo
    from pymongo import MongoClient
    sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    if created["class_ids"]:
        sync.classes.delete_many({"id": {"$in": created["class_ids"]}})
    if created["assignment_ids"]:
        sync.teacher_class_assignments.delete_many({"id": {"$in": created["assignment_ids"]}})
    if created["user_ids"]:
        sync.users.delete_many({"id": {"$in": created["user_ids"]}})


async def _make_class(db, cleanup, *, school_id, ay=2099, status="active"):
    cid = str(uuid.uuid4())
    await db.classes.insert_one({
        "id": cid, "name": f"Turma {cleanup['tag']}",
        "school_id": school_id, "academic_year": ay, "status": status,
    })
    cleanup["class_ids"].append(cid)
    return cid


async def _make_teacher(db, cleanup):
    uid = str(uuid.uuid4())
    await db.users.insert_one({
        "id": uid, "full_name": f"Prof {cleanup['tag']}",
        "role": "professor", "status": "active",
        "email": f"{uid}@test.local",
    })
    cleanup["user_ids"].append(uid)
    return uid


async def _make_assignment(db, cleanup, *, class_id, teacher_id, school_id, component_id,
                           vf, vu=None, slots=None, is_sub=False):
    aid = str(uuid.uuid4())
    await db.teacher_class_assignments.insert_one({
        "id": aid, "teacher_id": teacher_id, "teacher_name": "—",
        "class_id": class_id, "class_name": "—", "school_id": school_id,
        "component_id": component_id, "shift": "morning",
        "weekly_slots": slots or [{"weekday": 1, "aula_numero": 1, "start_time": "07:00", "end_time": "07:50"}],
        "valid_from": vf, "valid_until": vu, "is_substitute": is_sub,
        "source": "test", "deleted": False,
    })
    cleanup["assignment_ids"].append(aid)
    return aid


SCHOOL = "test-school-integrity-fixed"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ============================================================================
# 1. TEMPORAL_GAP
# ============================================================================
def test_temporal_gap_detected(db, cleanup):
    async def scenario():
        teacher = await _make_teacher(db, cleanup)
        klass = await _make_class(db, cleanup, school_id=SCHOOL)
        # Assignment A: 2099-01-01 → 2099-03-31 (encerrado)
        await _make_assignment(db, cleanup, class_id=klass, teacher_id=teacher,
                               school_id=SCHOOL, component_id="math",
                               vf="2099-01-01", vu="2099-03-31")
        # Assignment B: começa em 2099-05-01 (gap em abril)
        await _make_assignment(db, cleanup, class_id=klass, teacher_id=teacher,
                               school_id=SCHOOL, component_id="math",
                               vf="2099-05-01", vu="2099-12-31")
        return await compute_integrity_report(
            db, class_id=klass, reference_date="2099-06-01", academic_year=2099,
        )
    r = _run(scenario())
    kinds = [it["kind"] for it in r["issues"]]
    assert "TEMPORAL_GAP" in kinds
    gap = next(it for it in r["issues"] if it["kind"] == "TEMPORAL_GAP")
    assert gap["gap_from"] == "2099-04-01"
    assert gap["gap_to"] == "2099-04-30"
    assert gap["severity"] == "high"


# ============================================================================
# 2. OVERLAP
# ============================================================================
def test_overlap_detected(db, cleanup):
    async def scenario():
        t1 = await _make_teacher(db, cleanup)
        t2 = await _make_teacher(db, cleanup)
        klass = await _make_class(db, cleanup, school_id=SCHOOL)
        slot = [{"weekday": 1, "aula_numero": 1, "start_time": "07:00", "end_time": "07:50"}]
        # 2 professores ATIVOS no mesmo (class, weekday, aula) sem is_substitute
        await _make_assignment(db, cleanup, class_id=klass, teacher_id=t1,
                               school_id=SCHOOL, component_id="math",
                               vf="2099-01-01", vu=None, slots=slot)
        await _make_assignment(db, cleanup, class_id=klass, teacher_id=t2,
                               school_id=SCHOOL, component_id="math",
                               vf="2099-01-01", vu=None, slots=slot)
        return await compute_integrity_report(
            db, class_id=klass, reference_date="2099-06-01", academic_year=2099,
        )
    r = _run(scenario())
    overlaps = [it for it in r["issues"] if it["kind"] == "OVERLAP"]
    assert len(overlaps) >= 1
    assert overlaps[0]["severity"] == "high"


# ============================================================================
# 3. OVERLAP NÃO disparado quando is_substitute=True
# ============================================================================
def test_overlap_suppressed_by_substitute(db, cleanup):
    async def scenario():
        t1 = await _make_teacher(db, cleanup)
        t2 = await _make_teacher(db, cleanup)
        klass = await _make_class(db, cleanup, school_id=SCHOOL)
        slot = [{"weekday": 1, "aula_numero": 1, "start_time": "07:00", "end_time": "07:50"}]
        await _make_assignment(db, cleanup, class_id=klass, teacher_id=t1,
                               school_id=SCHOOL, component_id="math",
                               vf="2099-01-01", vu=None, slots=slot)
        await _make_assignment(db, cleanup, class_id=klass, teacher_id=t2,
                               school_id=SCHOOL, component_id="math",
                               vf="2099-01-01", vu=None, slots=slot, is_sub=True)
        return await compute_integrity_report(
            db, class_id=klass, reference_date="2099-06-01", academic_year=2099,
        )
    r = _run(scenario())
    overlaps = [it for it in r["issues"] if it["kind"] == "OVERLAP"]
    assert len(overlaps) == 0


# ============================================================================
# 4. EXPIRED_NO_SUCCESSOR
# ============================================================================
def test_expired_no_successor_detected(db, cleanup):
    async def scenario():
        teacher = await _make_teacher(db, cleanup)
        klass = await _make_class(db, cleanup, school_id=SCHOOL)
        await _make_assignment(db, cleanup, class_id=klass, teacher_id=teacher,
                               school_id=SCHOOL, component_id="math",
                               vf="2099-01-01", vu="2099-03-31")
        # reference_date depois do vencimento, sem sucessor
        return await compute_integrity_report(
            db, class_id=klass, reference_date="2099-06-01", academic_year=2099,
        )
    r = _run(scenario())
    expired = [it for it in r["issues"] if it["kind"] == "EXPIRED_NO_SUCCESSOR"]
    assert len(expired) >= 1
    assert expired[0]["days_since_expiration"] > 0


# ============================================================================
# 5. ORPHAN_TEACHER
# ============================================================================
def test_orphan_teacher_detected(db, cleanup):
    async def scenario():
        # teacher_id que NÃO existe em users
        fake_teacher = "ghost-" + uuid.uuid4().hex
        klass = await _make_class(db, cleanup, school_id=SCHOOL)
        await _make_assignment(db, cleanup, class_id=klass, teacher_id=fake_teacher,
                               school_id=SCHOOL, component_id="math",
                               vf="2099-01-01", vu=None)
        return await compute_integrity_report(
            db, class_id=klass, reference_date="2099-06-01", academic_year=2099,
        )
    r = _run(scenario())
    orph = [it for it in r["issues"] if it["kind"] == "ORPHAN_TEACHER"]
    assert len(orph) == 1
    assert orph[0]["severity"] == "medium"


# ============================================================================
# 6. TEACHER_DOUBLE_BOOKING
# ============================================================================
def test_teacher_double_booking_detected(db, cleanup):
    async def scenario():
        teacher = await _make_teacher(db, cleanup)
        klass_a = await _make_class(db, cleanup, school_id=SCHOOL)
        klass_b = await _make_class(db, cleanup, school_id=SCHOOL)
        slot = [{"weekday": 1, "aula_numero": 1, "start_time": "07:00", "end_time": "07:50"}]
        await _make_assignment(db, cleanup, class_id=klass_a, teacher_id=teacher,
                               school_id=SCHOOL, component_id="math",
                               vf="2099-01-01", vu=None, slots=slot)
        await _make_assignment(db, cleanup, class_id=klass_b, teacher_id=teacher,
                               school_id=SCHOOL, component_id="math",
                               vf="2099-01-01", vu=None, slots=slot)
        # Filter por school_id pra pegar os 2
        return await compute_integrity_report(
            db, school_id=SCHOOL, reference_date="2099-06-01", academic_year=2099,
        )
    r = _run(scenario())
    db_issues = [it for it in r["issues"] if it["kind"] == "TEACHER_DOUBLE_BOOKING"]
    # Pode haver outros do school SCHOOL — verificar se o teacher criado neste
    # teste aparece em DB
    teacher_ids_with_issue = {it["teacher_id"] for it in db_issues}
    assert any(t in teacher_ids_with_issue for t in cleanup["user_ids"])


# ============================================================================
# 7. CLASS_WITHOUT_ASSIGNMENT
# ============================================================================
def test_class_without_assignment_detected(db, cleanup):
    async def scenario():
        klass = await _make_class(db, cleanup, school_id=SCHOOL)  # sem assignment
        return await compute_integrity_report(
            db, school_id=SCHOOL, class_id=klass, reference_date="2099-06-01", academic_year=2099,
        )
    r = _run(scenario())
    cwa = [it for it in r["issues"] if it["kind"] == "CLASS_WITHOUT_ASSIGNMENT"]
    assert len(cwa) >= 1
    assert cwa[0]["severity"] == "high"


# ============================================================================
# 8. DUPLICATE_SLOT
# ============================================================================
def test_duplicate_slot_detected(db, cleanup):
    async def scenario():
        teacher = await _make_teacher(db, cleanup)
        klass = await _make_class(db, cleanup, school_id=SCHOOL)
        await _make_assignment(db, cleanup, class_id=klass, teacher_id=teacher,
                               school_id=SCHOOL, component_id="math",
                               vf="2099-01-01", vu=None, slots=[
                                   {"weekday": 1, "aula_numero": 1, "start_time": "07:00", "end_time": "07:50"},
                                   {"weekday": 1, "aula_numero": 1, "start_time": "07:00", "end_time": "07:50"},
                               ])
        return await compute_integrity_report(
            db, class_id=klass, reference_date="2099-06-01", academic_year=2099,
        )
    r = _run(scenario())
    dup = [it for it in r["issues"] if it["kind"] == "DUPLICATE_SLOT"]
    assert len(dup) == 1
    assert dup[0]["severity"] == "low"


# ============================================================================
# 9. INVERTED_VALIDITY
# ============================================================================
def test_inverted_validity_detected(db, cleanup):
    async def scenario():
        teacher = await _make_teacher(db, cleanup)
        klass = await _make_class(db, cleanup, school_id=SCHOOL)
        await _make_assignment(db, cleanup, class_id=klass, teacher_id=teacher,
                               school_id=SCHOOL, component_id="math",
                               vf="2099-06-01", vu="2099-01-01")  # invertido
        return await compute_integrity_report(
            db, class_id=klass, reference_date="2099-12-01", academic_year=2099,
        )
    r = _run(scenario())
    inv = [it for it in r["issues"] if it["kind"] == "INVERTED_VALIDITY"]
    assert len(inv) >= 1


# ============================================================================
# 10. Cenário SAUDÁVEL (zero issues)
# ============================================================================
def test_healthy_scenario_no_issues(db, cleanup):
    async def scenario():
        teacher = await _make_teacher(db, cleanup)
        klass = await _make_class(db, cleanup, school_id=SCHOOL)
        slot = [{"weekday": 1, "aula_numero": 1, "start_time": "07:00", "end_time": "07:50"}]
        await _make_assignment(db, cleanup, class_id=klass, teacher_id=teacher,
                               school_id=SCHOOL, component_id="math",
                               vf="2099-01-01", vu=None, slots=slot)
        return await compute_integrity_report(
            db, class_id=klass, reference_date="2099-06-01", academic_year=2099,
        )
    r = _run(scenario())
    assert r["summary"]["total_issues"] == 0


# ============================================================================
# 11. Summary tem todos os campos esperados
# ============================================================================
def test_summary_shape(db, cleanup):
    async def scenario():
        klass = await _make_class(db, cleanup, school_id=SCHOOL)
        return await compute_integrity_report(
            db, school_id=SCHOOL, class_id=klass, reference_date="2099-06-01", academic_year=2099,
        )
    r = _run(scenario())
    assert "summary" in r
    assert "by_severity" in r["summary"]
    assert "by_kind" in r["summary"]
    assert "classes_scanned" in r["summary"]
    assert "assignments_scanned" in r["summary"]
    assert "reference_date" in r
    assert "filters" in r
