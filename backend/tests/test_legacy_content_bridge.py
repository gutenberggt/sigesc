"""Legacy Content Bridge — testes (Fev/2026).

Cenários:
  1. Turma sem content_entries mas com learning_objects → bridge alimenta
  2. Em modo flexible, o fan-out de conteúdo cobre todas as aulas do dia
  3. Modelo novo presente → bridge ignorado
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
    "REACT_APP_BACKEND_URL", "https://sla-trio-weighted.preview.emergentagent.com"
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
def setup():
    """Cria turma de educação infantil (mode flexible) + grade (3 slots no dia)
    + 1 learning_object no dia (sem aula_numero específico)."""
    class_id = str(uuid.uuid4())
    tca_id = str(uuid.uuid4())
    component_id = str(uuid.uuid4())
    teacher_id = str(uuid.uuid4())
    lo_id = str(uuid.uuid4())

    _run(lambda d: d.classes.insert_one({
        "id": class_id, "name": "Content Bridge Test",
        "school_id": "ctnt-bridge-school",
        "academic_year": 2026, "shift": "morning",
        "education_level": "educacao_infantil",  # → flexible
    }))
    _run(lambda d: d.teacher_class_assignments.insert_one({
        "id": tca_id, "class_id": class_id,
        "component_id": component_id, "teacher_id": teacher_id,
        "teacher_name": "Prof CB",
        "valid_from": "2026-02-01", "valid_until": None, "deleted": False,
        "weekly_slots": [
            {"weekday": 1, "aula_numero": 1, "start_time": "07:00", "end_time": "07:45"},
            {"weekday": 1, "aula_numero": 2, "start_time": "07:45", "end_time": "08:30"},
            {"weekday": 1, "aula_numero": 3, "start_time": "08:30", "end_time": "09:15"},
        ],
    }))
    _run(lambda d: d.learning_objects.insert_one({
        "id": lo_id, "class_id": class_id,
        "course_id": component_id,
        "date": "2026-02-02",   # segunda
        "academic_year": 2026,
        "content": "Música cabeça, ombro, joelho e pé.",
        "methodology": "Música cantada.",
        "observations": "",
        "resources": "TV",
        "number_of_classes": 1,
        "recorded_by": teacher_id,
    }))

    ctx = {
        "class_id": class_id, "tca_id": tca_id, "lo_id": lo_id,
        "component_id": component_id, "teacher_id": teacher_id,
    }
    yield ctx

    _run(lambda d: d.classes.delete_one({"id": class_id}))
    _run(lambda d: d.teacher_class_assignments.delete_one({"id": tca_id}))
    _run(lambda d: d.learning_objects.delete_one({"id": lo_id}))
    _run(lambda d: d.content_entries.delete_many({"class_id": class_id}))
    _run(lambda d: d.diary_snapshots.delete_many({"class_id": class_id}))


# ===========================================================================
def test_unit_bridge_returns_shape():
    """Função pura: monta a estrutura corretamente."""
    from services.legacy_content_bridge import build_content_entries_from_legacy

    class FakeDB:
        class learning_objects:
            @staticmethod
            def find(*a, **k):
                class Cur:
                    async def to_list(self, n):
                        return [{
                            "id": "lo1", "class_id": "c1",
                            "course_id": "comp1", "date": "2026-02-02",
                            "academic_year": 2026,
                            "content": "x", "methodology": "y",
                            "observations": "", "resources": "",
                            "number_of_classes": 1,
                            "recorded_by": "t1",
                        }]
                return Cur()

    async def call():
        return await build_content_entries_from_legacy(
            FakeDB(), class_id="c1", dates_in_range=["2026-02-02"],
        )

    result = asyncio.get_event_loop().run_until_complete(call()) \
        if not asyncio.get_event_loop().is_running() \
        else None
    if result is None:
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(call())
        finally:
            loop.close()
    assert len(result) == 1
    r = result[0]
    assert r["id"] == "lo1"
    assert r["component_id"] == "comp1"
    assert r["course_id"] == "comp1"
    assert r["teacher_id"] == "t1"
    assert r["status"] == "published"
    assert r["aula_numero"] is None
    assert r["source"] == "legacy_content_bridge"
    assert r["synthetic_validity"] is True


# ===========================================================================
def test_calendar_uses_legacy_bridge_for_content(session, setup):
    """E2E: calendar_diary_state busca learning_objects via bridge, e o
    fan-out flexível propaga para todas as 3 aulas do dia."""
    s = setup
    r = session.get(
        f"{BASE_URL}/api/calendar/diary-state/{s['class_id']}",
        params={"from": "2026-02-02", "to": "2026-02-02"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["matching_mode"] == "flexible"
    day = data["days"][0]
    assert len(day["entries"]) == 3
    # Todas as 3 aulas devem ter content_entry_id (via fan-out a partir do bridge)
    for e in day["entries"]:
        assert e["content_entry_id"] == s["lo_id"]
        assert e["content_status"] == "published"
    # Não pode haver órfão
    assert day["has_orphan_evidence"] is False
    assert day["status"] != "inconsistent"


# ===========================================================================
def test_new_model_takes_precedence(session, setup):
    """Quando content_entries TEM dado real, bridge é IGNORADO."""
    s = setup
    ce_id = str(uuid.uuid4())
    _run(lambda d: d.content_entries.insert_one({
        "id": ce_id, "class_id": s["class_id"],
        "date": "2026-02-02", "aula_numero": 1,
        "component_id": s["component_id"], "teacher_id": s["teacher_id"],
        "status": "published", "version": 5,
        "deleted": False,
        "content": "Modelo novo — vence!",
    }))
    try:
        r = session.get(
            f"{BASE_URL}/api/calendar/diary-state/{s['class_id']}",
            params={"from": "2026-02-02", "to": "2026-02-02"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        day = data["days"][0]
        # Pelo menos uma aula deve ter o content_entry_id do MODELO NOVO
        new_model_hits = sum(
            1 for e in day["entries"] if e.get("content_entry_id") == ce_id
        )
        assert new_model_hits >= 1
        # E NENHUMA deve ter o legacy lo_id
        legacy_hits = sum(
            1 for e in day["entries"] if e.get("content_entry_id") == s["lo_id"]
        )
        assert legacy_hits == 0
    finally:
        _run(lambda d: d.content_entries.delete_one({"id": ce_id}))
