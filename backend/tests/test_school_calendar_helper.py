"""School Calendar (Fase 11) — testes.

Cenários:
1. Feriado nacional → dia status='non_school', sem entries expandidos.
2. Recesso escolar de intervalo → todos os dias do intervalo são non_school.
3. Sábado letivo (date com event_type=sabado_letivo) PROMOVE letivo:
   pula a regra de exclusão (mesmo se feriado coincide).
4. Snapshot congela o calendário letivo (mudança no evento NÃO afeta hash).
5. has_orphan_evidence em dia não-letivo NÃO força 'inconsistent'.
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
    "REACT_APP_BACKEND_URL", "https://matricula-dedup.preview.emergentagent.com"
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
    """Turma com 1 slot toda segunda (weekday=1, aula=3)."""
    class_id = str(uuid.uuid4())
    tca_id = str(uuid.uuid4())
    _run(lambda d: d.classes.insert_one({
        "id": class_id, "name": "School Cal Test",
        "school_id": "sch-cal-test",
        "academic_year": 2026, "shift": "morning",
        "education_level": "fundamental_anos_finais",  # strict por default
    }))
    _run(lambda d: d.teacher_class_assignments.insert_one({
        "id": tca_id, "class_id": class_id,
        "component_id": str(uuid.uuid4()), "teacher_id": str(uuid.uuid4()),
        "teacher_name": "Prof", "deleted": False,
        "valid_from": "2026-02-01", "valid_until": None,
        "weekly_slots": [{"weekday": 1, "aula_numero": 3,
                          "start_time": "08:00", "end_time": "08:45"}],
    }))
    events_created: list = []
    yield {
        "class_id": class_id, "tca_id": tca_id,
        "events_created": events_created,
    }
    _run(lambda d: d.classes.delete_one({"id": class_id}))
    _run(lambda d: d.teacher_class_assignments.delete_one({"id": tca_id}))
    for eid in events_created:
        _run(lambda d, eid=eid: d.calendar_events.delete_one({"id": eid}))
    _run(lambda d: d.attendance.delete_many({"class_id": class_id}))
    _run(lambda d: d.diary_snapshots.delete_many({"class_id": class_id}))


def _create_event(events_created, event_type, start_date, end_date=None, title="X"):
    eid = str(uuid.uuid4())
    _run(lambda d: d.calendar_events.insert_one({
        "id": eid, "academic_year": 2026,
        "event_type": event_type,
        "start_date": start_date,
        "end_date": end_date or start_date,
        "title": title,
    }))
    events_created.append(eid)
    return eid


# ===========================================================================
def test_dia_fora_do_periodo_letivo_eh_non_school(session, setup):
    """Cadastra calendario_letivo com bimestre1=2026-02-03..2026-04-25.
    Janeiro/2026 deve ser non_school automático (fora do período letivo)."""
    s = setup
    cal_id = str(uuid.uuid4())
    _run(lambda d: d.calendario_letivo.insert_one({
        "id": cal_id,
        "ano_letivo": 2026,
        "school_id": "sch-cal-test",   # mesmo school_id da turma do fixture
        "bimestre_1_inicio": "2026-02-03",
        "bimestre_1_fim": "2026-04-25",
        "bimestre_2_inicio": "2026-04-28",
        "bimestre_2_fim": "2026-07-04",
        "bimestre_3_inicio": "2026-07-21",
        "bimestre_3_fim": "2026-09-26",
        "bimestre_4_inicio": "2026-09-29",
        "bimestre_4_fim": "2026-12-19",
        "dias_letivos_previstos": 200,
    }))
    try:
        # 2026-01-19 = segunda-feira (slot esperado da turma) — mas FORA do letivo
        r = session.get(
            f"{BASE_URL}/api/calendar/diary-state/{s['class_id']}",
            params={"from": "2026-01-19", "to": "2026-01-19"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        day = r.json()["days"][0]
        assert day["status"] == "non_school"
        assert day["expected_slots"] == 0
        assert day["school_calendar_event"]["event_type"] == "fora_periodo_letivo"

        # 2026-04-26 (sábado) e 2026-04-27 (domingo) entre bimestres = non_school
        # 2026-04-27 é segunda — entre bimestre 1 (fim 25/04) e bimestre 2 (início 28/04)
        r2 = session.get(
            f"{BASE_URL}/api/calendar/diary-state/{s['class_id']}",
            params={"from": "2026-04-27", "to": "2026-04-27"},
            timeout=20,
        )
        day2 = r2.json()["days"][0]
        assert day2["status"] == "non_school"
        assert day2["school_calendar_event"]["event_type"] == "fora_periodo_letivo"

        # Já 2026-02-09 (segunda dentro do bimestre 1) deve ser dia letivo normal
        r3 = session.get(
            f"{BASE_URL}/api/calendar/diary-state/{s['class_id']}",
            params={"from": "2026-02-09", "to": "2026-02-09"},
            timeout=20,
        )
        day3 = r3.json()["days"][0]
        assert day3["status"] != "non_school"
        assert day3["expected_slots"] >= 1
    finally:
        _run(lambda d: d.calendario_letivo.delete_one({"id": cal_id}))


# ===========================================================================
def test_holiday_marks_day_as_non_school(session, setup):
    """2026-02-09 é segunda. Criar feriado nesse dia. Dia deve virar 'non_school'."""
    s = setup
    _create_event(s["events_created"], "feriado_nacional", "2026-02-09",
                  title="Carnaval (teste)")
    r = session.get(
        f"{BASE_URL}/api/calendar/diary-state/{s['class_id']}",
        params={"from": "2026-02-09", "to": "2026-02-09"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    day = data["days"][0]
    assert day["status"] == "non_school"
    assert day["expected_slots"] == 0
    assert len(day["entries"]) == 0
    assert day["school_calendar_event"]["title"] == "Carnaval (teste)"
    assert day["school_calendar_event"]["event_type"] == "feriado_nacional"


# ===========================================================================
def test_recesso_intervalo_aplica_a_todos_dias(session, setup):
    """Recesso 09-13/Fev/2026 (seg-sex). Todos os 5 dias devem ser non_school."""
    s = setup
    _create_event(s["events_created"], "recesso_escolar",
                  "2026-02-09", "2026-02-13", title="Recesso de Carnaval")
    r = session.get(
        f"{BASE_URL}/api/calendar/diary-state/{s['class_id']}",
        params={"from": "2026-02-09", "to": "2026-02-13"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    non_school_count = sum(1 for d in data["days"] if d["status"] == "non_school")
    assert non_school_count == 5


# ===========================================================================
def test_sabado_letivo_promote_dia(session, setup):
    """Sábado letivo deve aparecer como non_school=False mesmo se há feriado coincidente."""
    s = setup
    # Criar feriado E sábado letivo no mesmo dia
    _create_event(s["events_created"], "feriado_municipal", "2026-03-14",
                  title="Feriado bobo")
    _create_event(s["events_created"], "sabado_letivo", "2026-03-14",
                  title="Reposição")
    r = session.get(
        f"{BASE_URL}/api/calendar/diary-state/{s['class_id']}",
        params={"from": "2026-03-14", "to": "2026-03-14"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    day = data["days"][0]
    # Sábado letivo vence — não é non_school
    assert day["status"] != "non_school"
    # Marca como dia letivo explícito
    assert day.get("is_explicit_school_day") is True
    assert day["school_calendar_event"]["event_type"] == "sabado_letivo"


# ===========================================================================
def test_orphan_em_dia_nao_letivo_nao_vira_inconsistent(session, setup):
    """Attendance em dia de feriado NÃO deve marcar o dia como inconsistent."""
    s = setup
    _create_event(s["events_created"], "feriado_nacional", "2026-02-09",
                  title="Feriado")
    # Lança um attendance órfão no feriado
    att_id = str(uuid.uuid4())
    _run(lambda d: d.attendance.insert_one({
        "id": att_id, "class_id": s["class_id"],
        "date": "2026-02-09", "aula_numero": 5,
        "records": [{"student_id": "x", "present": True}],
    }))
    try:
        r = session.get(
            f"{BASE_URL}/api/calendar/diary-state/{s['class_id']}",
            params={"from": "2026-02-09", "to": "2026-02-09"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        day = r.json()["days"][0]
        # Mesmo com órfão, dia é non_school (regra institucional)
        assert day["status"] == "non_school"
    finally:
        _run(lambda d: d.attendance.delete_one({"id": att_id}))


# ===========================================================================
def test_snapshot_congela_calendario_letivo(session, setup):
    """Snapshot publicado preserva os non_school_days mesmo após apagar
    o evento da collection calendar_events."""
    s = setup
    eid = _create_event(s["events_created"], "feriado_nacional",
                        "2026-02-09", title="Feriado Freeze")

    # Publish snapshot do dia
    create = session.post(
        f"{BASE_URL}/api/diary/snapshots",
        json={
            "class_id": s["class_id"], "period_type": "custom",
            "period_from": "2026-02-09", "period_to": "2026-02-09",
            "period_label": "Freeze Test",
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
    day_v1 = snap_v1["payload"]["days"][0]
    assert day_v1["status"] == "non_school"

    # Apaga o evento
    _run(lambda d: d.calendar_events.delete_one({"id": eid}))

    # Re-busca snapshot
    refetch = session.get(
        f"{BASE_URL}/api/diary/snapshots/{snap_id}", timeout=20,
    )
    snap_v2 = refetch.json()
    assert snap_v2["payload_hash_sha256"] == hash_v1
    assert snap_v2["payload"]["days"][0]["status"] == "non_school"
