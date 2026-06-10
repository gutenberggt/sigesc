"""Diary Matching Mode (Fase 10) — 5 cenários obrigatórios (Fev/2026).

1. STRICT mantém comportamento atual (orphan quando aula_numero diverge).
2. FLEXIBLE aceita mesma_data + mesmo_professor.
3. FLEXIBLE aceita mesma_data + mesmo_componente.
4. FLEXIBLE REJEITA quando NEM professor NEM componente batem.
5. Snapshot congela matching_mode_used (mutar a turma depois NÃO afeta).
"""
import asyncio
import os
import uuid

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://login-offline-mode.preview.emergentagent.com"
).rstrip("/")
ADMIN = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}


def _run(coro_factory):
    async def _inner():
        client = AsyncIOMotorClient(os.environ['MONGO_URL'])
        try:
            return await coro_factory(client[os.environ['DB_NAME']])
        finally:
            client.close()
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_inner())
    finally:
        loop.close()


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    s.headers.update({
        "Authorization": f"Bearer {d.get('access_token') or d.get('token')}",
        "X-CSRF-Token": d.get("csrf_token") or "",
        "Content-Type": "application/json",
    })
    return s


def _setup_class_with_assignment(mode):
    """Cria turma + 1 TCA com slot (quarta, aula=3) e 1 student."""
    class_id = str(uuid.uuid4())
    tca_id = str(uuid.uuid4())
    component_id = str(uuid.uuid4())
    teacher_id = str(uuid.uuid4())
    student_id = str(uuid.uuid4())
    _run(lambda d: d.classes.insert_one({
        "id": class_id, "name": f"Matching Test {mode}",
        "school_id": "match-test-school",
        "academic_year": 2026, "shift": "morning",
        "education_level": "fundamental_anos_iniciais",
        "diary_matching_mode": mode,
    }))
    _run(lambda d: d.teacher_class_assignments.insert_one({
        "id": tca_id, "class_id": class_id,
        "component_id": component_id, "teacher_id": teacher_id,
        "teacher_name": "Prof Match Test",
        "valid_from": "2026-02-01", "valid_until": None, "deleted": False,
        "weekly_slots": [{
            "weekday": 3, "aula_numero": 3,
            "start_time": "09:00", "end_time": "09:45",
        }],
    }))
    return {
        "class_id": class_id, "tca_id": tca_id,
        "component_id": component_id, "teacher_id": teacher_id,
        "student_id": student_id,
    }


def _cleanup(ctx):
    _run(lambda d: d.classes.delete_one({"id": ctx["class_id"]}))
    _run(lambda d: d.teacher_class_assignments.delete_one({"id": ctx["tca_id"]}))
    _run(lambda d: d.attendance.delete_many({"class_id": ctx["class_id"]}))
    _run(lambda d: d.content_entries.delete_many({"class_id": ctx["class_id"]}))
    _run(lambda d: d.diary_snapshots.delete_many({"class_id": ctx["class_id"]}))


# ===========================================================================
def test_unit_infer_default_modes():
    """Pure inference function — sem rede."""
    from services.diary_matching_mode import (
        infer_default_matching_mode, resolve_matching_mode,
    )
    assert infer_default_matching_mode({"education_level": "educacao_infantil"}) == "flexible"
    assert infer_default_matching_mode({"education_level": "fundamental_anos_iniciais"}) == "flexible"
    assert infer_default_matching_mode({"education_level": "fundamental_anos_finais"}) == "strict"
    assert infer_default_matching_mode({"education_level": "ensino_medio"}) == "strict"
    assert infer_default_matching_mode({"education_level": "eja_anos_iniciais"}) == "flexible"
    assert infer_default_matching_mode({"education_level": "eja_anos_finais"}) == "strict"
    assert infer_default_matching_mode({"is_multi_grade": True,
                                         "education_level": "ensino_medio"}) == "flexible"
    # Explicit override sempre vence
    assert resolve_matching_mode({"diary_matching_mode": "flexible",
                                  "education_level": "ensino_medio"}) == "flexible"
    assert resolve_matching_mode({"diary_matching_mode": "strict",
                                  "education_level": "educacao_infantil"}) == "strict"


# ===========================================================================
def test_scenario_1_strict_mantem_comportamento(session):
    """STRICT: attendance com aula_numero ERRADO → vira ÓRFÃO."""
    ctx = _setup_class_with_assignment("strict")
    att_id = str(uuid.uuid4())
    _run(lambda d: d.attendance.insert_one({
        "id": att_id, "class_id": ctx["class_id"],
        "date": "2026-02-04",   # quarta-feira (esperado!)
        "aula_numero": 7,        # ERRADO (esperado é aula=3)
        "course_id": ctx["component_id"],  # mesmo componente
        "records": [{"student_id": ctx["student_id"], "present": True}],
        "created_by": ctx["teacher_id"],
    }))
    try:
        r = session.get(
            f"{BASE_URL}/api/calendar/diary-state/{ctx['class_id']}",
            params={"from": "2026-02-04", "to": "2026-02-04"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["matching_mode"] == "strict"
        day = data["days"][0]
        # O slot esperado (aula 3) NÃO foi casado
        assert day["entries"][0].get("attendance_id") is None
        # O attendance vira órfão → dia INCONSISTENT
        assert day["has_orphan_evidence"] is True
        assert day["status"] == "inconsistent"
    finally:
        _cleanup(ctx)


# ===========================================================================
def test_scenario_2_flexible_same_teacher(session):
    """FLEXIBLE: aula_numero ERRADO mas mesmo professor → matched flexível."""
    ctx = _setup_class_with_assignment("flexible")
    att_id = str(uuid.uuid4())
    other_component = str(uuid.uuid4())
    _run(lambda d: d.attendance.insert_one({
        "id": att_id, "class_id": ctx["class_id"],
        "date": "2026-02-04",
        "aula_numero": 7,        # ERRADO
        "course_id": other_component,  # COMPONENTE DIFERENTE
        "records": [{"student_id": ctx["student_id"], "present": True}],
        "created_by": ctx["teacher_id"],  # MESMO professor
    }))
    try:
        r = session.get(
            f"{BASE_URL}/api/calendar/diary-state/{ctx['class_id']}",
            params={"from": "2026-02-04", "to": "2026-02-04"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["matching_mode"] == "flexible"
        day = data["days"][0]
        entry = day["entries"][0]
        assert entry["attendance_id"] == att_id
        assert entry["matched_by"] == "flexible"
        assert entry["flexible_match_reason"] == "same_teacher_same_day"
        # Não deve haver órfão
        assert day["has_orphan_evidence"] is False
        assert day["status"] != "inconsistent"
    finally:
        _cleanup(ctx)


# ===========================================================================
def test_scenario_3_flexible_same_component(session):
    """FLEXIBLE: aula_numero E professor errados, mas mesmo componente."""
    ctx = _setup_class_with_assignment("flexible")
    att_id = str(uuid.uuid4())
    other_teacher = str(uuid.uuid4())
    _run(lambda d: d.attendance.insert_one({
        "id": att_id, "class_id": ctx["class_id"],
        "date": "2026-02-04",
        "aula_numero": 7,        # ERRADO
        "course_id": ctx["component_id"],  # MESMO componente
        "records": [{"student_id": ctx["student_id"], "present": True}],
        "created_by": other_teacher,  # PROFESSOR DIFERENTE
    }))
    try:
        r = session.get(
            f"{BASE_URL}/api/calendar/diary-state/{ctx['class_id']}",
            params={"from": "2026-02-04", "to": "2026-02-04"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        day = data["days"][0]
        entry = day["entries"][0]
        assert entry["attendance_id"] == att_id
        assert entry["matched_by"] == "flexible"
        assert entry["flexible_match_reason"] == "same_component_same_day"
        assert day["has_orphan_evidence"] is False
    finally:
        _cleanup(ctx)


# ===========================================================================
def test_scenario_4_flexible_fanout_covers_unrelated_record(session):
    """FLEXIBLE: registro no dia (mesmo com prof e componente diferentes)
    é CONSIDERADO pelo fan-out diário. Pedagogicamente: 'tem registro = lançado'.

    NOTA: este é o comportamento aprovado pelo owner em Fev/2026
    especificamente para etapas pedagogicamente integradas (Infantil/AI/EJA-AI).
    STRICT continua rejeitando — coberto pelo cenário 1.
    """
    ctx = _setup_class_with_assignment("flexible")
    att_id = str(uuid.uuid4())
    other_teacher = str(uuid.uuid4())
    other_component = str(uuid.uuid4())
    _run(lambda d: d.attendance.insert_one({
        "id": att_id, "class_id": ctx["class_id"],
        "date": "2026-02-04",
        "aula_numero": 7,
        "course_id": other_component,
        "records": [{"student_id": ctx["student_id"], "present": True}],
        "created_by": other_teacher,
    }))
    try:
        r = session.get(
            f"{BASE_URL}/api/calendar/diary-state/{ctx['class_id']}",
            params={"from": "2026-02-04", "to": "2026-02-04"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        day = data["days"][0]
        entry = day["entries"][0]
        # Fan-out: o entry esperado recebe o registro mesmo sem vínculo direto
        assert entry["attendance_id"] == att_id
        assert entry["matched_by"] == "flexible"
        assert entry["flexible_match_reason"] == "day_fanout_attendance"
        assert day["has_orphan_evidence"] is False
        assert day["status"] != "inconsistent"
    finally:
        _cleanup(ctx)


# ===========================================================================
def test_scenario_6_flexible_fanout_multi_aulas(session):
    """FLEXIBLE: TURMA com 3 slots no mesmo dia + 1 content_entry no dia.
    Todos os 3 entries devem aparecer 'Lançado' por fan-out."""
    class_id = str(uuid.uuid4())
    tca_id = str(uuid.uuid4())
    component_id = str(uuid.uuid4())
    teacher_id = str(uuid.uuid4())
    ce_id = str(uuid.uuid4())
    _run(lambda d: d.classes.insert_one({
        "id": class_id, "name": "Multi-Slot Test",
        "school_id": "match-test-school",
        "academic_year": 2026, "shift": "morning",
        "education_level": "educacao_infantil",
        # default infere flexible; deixa o campo ausente para também testar isso
    }))
    _run(lambda d: d.teacher_class_assignments.insert_one({
        "id": tca_id, "class_id": class_id,
        "component_id": component_id, "teacher_id": teacher_id,
        "teacher_name": "Prof Multi",
        "valid_from": "2026-02-01", "valid_until": None, "deleted": False,
        "weekly_slots": [
            {"weekday": 3, "aula_numero": 1, "start_time": "07:00", "end_time": "07:45"},
            {"weekday": 3, "aula_numero": 2, "start_time": "07:45", "end_time": "08:30"},
            {"weekday": 3, "aula_numero": 3, "start_time": "08:30", "end_time": "09:15"},
        ],
    }))
    _run(lambda d: d.content_entries.insert_one({
        "id": ce_id, "class_id": class_id,
        "date": "2026-02-04",
        "aula_numero": 1,
        "component_id": component_id,
        "teacher_id": teacher_id,
        "status": "published",
        "version": 1,
        "deleted": False,
        "content": "Rotina pedagógica do dia",
    }))
    try:
        r = session.get(
            f"{BASE_URL}/api/calendar/diary-state/{class_id}",
            params={"from": "2026-02-04", "to": "2026-02-04"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # Modo deve ser inferido como flexible (educacao_infantil)
        assert data["matching_mode"] == "flexible"
        day = data["days"][0]
        # 3 entries esperados
        assert len(day["entries"]) == 3
        # TODOS devem ter content_entry_id (fan-out)
        for e in day["entries"]:
            assert e["content_entry_id"] == ce_id
            assert e["content_status"] == "published"
        # Pelo menos 2 devem ter sido marcados via fanout (o primeiro pode
        # ter ido por strict porque aula_numero=1 bate)
        fanout_count = sum(
            1 for e in day["entries"]
            if e.get("flexible_match_reason") == "day_fanout_content"
        )
        assert fanout_count >= 2
    finally:
        _run(lambda d: d.classes.delete_one({"id": class_id}))
        _run(lambda d: d.teacher_class_assignments.delete_one({"id": tca_id}))
        _run(lambda d: d.content_entries.delete_one({"id": ce_id}))


# ===========================================================================
def test_scenario_5_snapshot_freezes_matching_mode(session):
    """Snapshot publicado congela matching_mode_used. Mudança posterior no
    campo `diary_matching_mode` da turma NÃO afeta o snapshot."""
    ctx = _setup_class_with_assignment("flexible")
    att_id = str(uuid.uuid4())
    _run(lambda d: d.attendance.insert_one({
        "id": att_id, "class_id": ctx["class_id"],
        "date": "2026-02-04",
        "aula_numero": 7, "course_id": ctx["component_id"],
        "records": [{"student_id": ctx["student_id"], "present": True}],
        "created_by": ctx["teacher_id"],
    }))

    try:
        create = session.post(
            f"{BASE_URL}/api/diary/snapshots",
            json={
                "class_id": ctx["class_id"], "period_type": "custom",
                "period_from": "2026-02-04", "period_to": "2026-02-04",
                "period_label": "Match Test Period",
            },
            timeout=20,
        )
        assert create.status_code == 200, create.text
        snap_id = create.json()["snapshot"]["id"]

        publish = session.post(
            f"{BASE_URL}/api/diary/snapshots/{snap_id}/publish", timeout=20,
        )
        assert publish.status_code == 200, publish.text
        snap_v1 = publish.json()["snapshot"]
        assert snap_v1["payload"].get("matching_mode_used") == "flexible"
        hash_v1 = snap_v1["payload_hash_sha256"]
        entry_v1 = snap_v1["payload"]["days"][0]["entries"][0]
        assert entry_v1["matched_by"] == "flexible"

        # Muta o modo da turma para strict
        _run(lambda d: d.classes.update_one(
            {"id": ctx["class_id"]},
            {"$set": {"diary_matching_mode": "strict"}},
        ))

        refetch = session.get(
            f"{BASE_URL}/api/diary/snapshots/{snap_id}", timeout=20,
        )
        assert refetch.status_code == 200
        snap_v2 = refetch.json()
        assert snap_v2["payload_hash_sha256"] == hash_v1
        assert snap_v2["payload"]["matching_mode_used"] == "flexible"
    finally:
        _cleanup(ctx)
