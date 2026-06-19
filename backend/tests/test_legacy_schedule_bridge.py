"""Legacy Schedule Bridge — testes dos 4 cenários aprovados (Fev/2026).

1. Legacy puro    → bridge ativa, slots reconhecidos, sem orphan indevido.
2. Modelo novo    → bridge IGNORADO completamente.
3. Slot sem prof  → não explode; warning observável; status coerente.
4. Snapshot       → bridge preserva semântica no congelamento.
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
    "REACT_APP_BACKEND_URL", "https://school-reorganize.preview.emergentagent.com"
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


@pytest.fixture
def legacy_class_setup():
    """Cria turma + class_schedule + teacher_assignment legacy.

    Retorna {class_id, course_id, teacher_id, cleanup()}.
    """
    class_id = str(uuid.uuid4())
    course_id = str(uuid.uuid4())
    teacher_id = str(uuid.uuid4())
    schedule_id = str(uuid.uuid4())
    ta_id = str(uuid.uuid4())

    _run(lambda d: d.classes.insert_one({
        "id": class_id, "name": "Bridge Test Class",
        "school_id": "bridge-test-school",
        "academic_year": 2026, "shift": "morning",
    }))
    _run(lambda d: d.class_schedules.insert_one({
        "id": schedule_id, "class_id": class_id,
        "school_id": "bridge-test-school",
        "academic_year": 2026, "slots_per_day": 8, "shift": "morning",
        "slot_times": {"1": {"start": "07:00", "end": "07:45"}},
        "schedule_slots": [
            {"day": "segunda", "slot_number": 1,
             "course_id": course_id, "course_name": "MAT"},
            {"day": "terca", "slot_number": 1,
             "course_id": course_id, "course_name": "MAT"},
        ],
    }))
    _run(lambda d: d.teacher_assignments.insert_one({
        "id": ta_id, "class_id": class_id, "staff_id": teacher_id,
        "course_id": course_id, "academic_year": 2026,
        "carga_horaria_semanal": 2, "status": "ativo",
    }))
    # staff é fonte canônica de servidores (teacher_assignments.staff_id → staff.id)
    _run(lambda d: d.staff.insert_one({
        "id": teacher_id, "full_name": "Prof Bridge Test",
    }))

    yield {
        "class_id": class_id, "course_id": course_id,
        "teacher_id": teacher_id,
    }

    # Cleanup
    _run(lambda d: d.classes.delete_one({"id": class_id}))
    _run(lambda d: d.class_schedules.delete_one({"id": schedule_id}))
    _run(lambda d: d.teacher_assignments.delete_one({"id": ta_id}))
    _run(lambda d: d.staff.delete_one({"id": teacher_id}))
    _run(lambda d: d.attendance.delete_many({"class_id": class_id}))
    _run(lambda d: d.teacher_class_assignments.delete_many({"class_id": class_id}))
    _run(lambda d: d.diary_snapshots.delete_many({"class_id": class_id}))


# ===========================================================================
def test_scenario_1_legacy_puro_reconhece_slots(session, legacy_class_setup):
    """Turma sem teacher_class_assignments mas com legacy → slots reconhecidos."""
    s = legacy_class_setup
    r = session.get(
        f"{BASE_URL}/api/calendar/diary-state/{s['class_id']}",
        params={"from": "2026-02-02", "to": "2026-02-06"},  # seg-sex
        timeout=20,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # 2026-02-02 = segunda; 2026-02-03 = terça
    by_date = {d["date"]: d for d in data["days"]}
    assert by_date["2026-02-02"]["expected_slots"] == 1
    assert by_date["2026-02-02"]["status"] == "empty"  # esperado mas sem evidência
    assert by_date["2026-02-03"]["expected_slots"] == 1
    # Quarta-feira não está na grade
    assert by_date["2026-02-04"]["expected_slots"] == 0
    assert by_date["2026-02-04"]["status"] == "not_expected"
    # Entry deve trazer o teacher resolvido + nome legível + componente legível
    entries = by_date["2026-02-02"]["entries"]
    assert entries[0]["teacher_id"] == s["teacher_id"]
    assert entries[0]["teacher_name"] == "Prof Bridge Test"
    assert entries[0]["component_name"] == "MAT"
    assert entries[0]["assignment_source"] == "legacy_bridge"


# ===========================================================================
def test_scenario_2_modelo_novo_ignora_legacy(session, legacy_class_setup):
    """Quando teacher_class_assignments existe, legacy é COMPLETAMENTE ignorado."""
    s = legacy_class_setup

    # Insere um TCA com slot diferente da grade legacy (quarta-feira)
    tca_id = str(uuid.uuid4())
    new_course = str(uuid.uuid4())
    new_teacher = str(uuid.uuid4())
    _run(lambda d: d.teacher_class_assignments.insert_one({
        "id": tca_id, "class_id": s["class_id"],
        "component_id": new_course, "teacher_id": new_teacher,
        "teacher_name": "Prof NEW model",
        "valid_from": "2026-02-01", "valid_until": None,
        "deleted": False,
        "weekly_slots": [
            {"weekday": 3, "aula_numero": 5,
             "start_time": "10:00", "end_time": "10:45"},
        ],
    }))
    try:
        r = session.get(
            f"{BASE_URL}/api/calendar/diary-state/{s['class_id']}",
            params={"from": "2026-02-02", "to": "2026-02-06"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        by_date = {d["date"]: d for d in data["days"]}
        # Quarta agora tem slot do modelo novo
        assert by_date["2026-02-04"]["expected_slots"] == 1
        # Segunda e terça (que vinham do legacy) NÃO devem ter slots — bridge ignorado
        assert by_date["2026-02-02"]["expected_slots"] == 0
        assert by_date["2026-02-02"]["status"] == "not_expected"
        # Conferir que o slot ativo é do modelo novo
        entries = by_date["2026-02-04"]["entries"]
        assert entries[0]["teacher_id"] == new_teacher
    finally:
        _run(lambda d: d.teacher_class_assignments.delete_one({"id": tca_id}))


# ===========================================================================
def test_scenario_3_slot_sem_professor_nao_explode(session, legacy_class_setup):
    """Slot na grade legacy sem teacher_assignment correspondente.

    O calendário deve responder 200, slot reconhecido, teacher_id=None.
    Não pode crashar.
    """
    s = legacy_class_setup
    # Insere um slot extra com course_id que NÃO tem teacher_assignment
    orphan_course = str(uuid.uuid4())
    _run(lambda d: d.class_schedules.update_one(
        {"class_id": s["class_id"]},
        {"$push": {"schedule_slots": {
            "day": "quinta", "slot_number": 2,
            "course_id": orphan_course, "course_name": "ORPHAN COURSE",
        }}},
    ))
    try:
        r = session.get(
            f"{BASE_URL}/api/calendar/diary-state/{s['class_id']}",
            params={"from": "2026-02-02", "to": "2026-02-06"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        by_date = {d["date"]: d for d in data["days"]}
        # Quinta-feira (2026-02-05) tem o slot órfão
        thursday = by_date["2026-02-05"]
        assert thursday["expected_slots"] == 1
        # O entry deve existir com teacher_id=None (não crash)
        entry = thursday["entries"][0]
        assert entry["teacher_id"] is None
    finally:
        _run(lambda d: d.class_schedules.update_one(
            {"class_id": s["class_id"]},
            {"$pull": {"schedule_slots": {"course_id": orphan_course}}},
        ))


# ===========================================================================
def test_scenario_4_snapshot_congela_bridge(session, legacy_class_setup):
    """Snapshot publicado usando bridge preserva o congelamento.

    Após publicar:
      - alterar class_schedules
      - alterar teacher_assignments
    O snapshot NÃO muda (hash imutável + payload congelado).
    """
    s = legacy_class_setup

    # Publica snapshot (cria → publish)
    create = session.post(
        f"{BASE_URL}/api/diary/snapshots",
        json={
            "class_id": s["class_id"], "period_type": "custom",
            "period_from": "2026-02-02", "period_to": "2026-02-06",
            "period_label": "Bridge Test Period",
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
    hash_v1 = snap_v1["payload_hash_sha256"]
    days_v1 = snap_v1["payload"]["days"]
    expected_slots_v1 = sum(d["expected_slots"] for d in days_v1)
    assert expected_slots_v1 > 0  # bridge funcionou no snapshot

    # Mutação do legacy (apaga um slot da grade + apaga o teacher_assignment)
    _run(lambda d: d.class_schedules.update_one(
        {"class_id": s["class_id"]},
        {"$set": {"schedule_slots": []}},
    ))
    _run(lambda d: d.teacher_assignments.delete_many({"class_id": s["class_id"]}))

    # Re-busca o snapshot
    refetch = session.get(
        f"{BASE_URL}/api/diary/snapshots/{snap_id}", timeout=20,
    )
    assert refetch.status_code == 200
    snap_v2 = refetch.json()
    # Hash IMUTÁVEL
    assert snap_v2["payload_hash_sha256"] == hash_v1
    # Payload congelado
    days_v2 = snap_v2["payload"]["days"]
    expected_slots_v2 = sum(d["expected_slots"] for d in days_v2)
    assert expected_slots_v2 == expected_slots_v1
