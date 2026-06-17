"""
Regressão — Sábado Letivo tratado como dia letivo normal (Jun/2026).

Objetivo: um sábado marcado como `sabado_letivo` deve GERAR AULAS no diário
seguindo a ROTAÇÃO (1º sábado letivo do ano = aulas de Segunda, 2º = Terça, …).
Antes, o diário expandia a grade apenas por `isoweekday`, e como a grade só tem
Seg–Sex, o sábado (dia 6) nunca casava → nenhuma aula no sábado letivo.

Cobre:
  - get_saturday_weekday_map (rotação cíclica Seg–Sex);
  - GET /api/calendar/diary-state: aulas aparecem no sábado letivo (carga horária,
    frequência e diário derivam dessa expansão).
"""
import os
import uuid
import asyncio
from datetime import date, timedelta

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

from services.school_calendar_helper import get_saturday_weekday_map

API = "http://localhost:8001"
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PWD = os.getenv("SIGESC_TEST_ADMIN_PASSWORD", "@Celta2007")
YEAR = 2026


def _first_saturdays(n, start=date(YEAR, 3, 1)):
    d = start
    while d.weekday() != 5:  # 5 = sábado
        d += timedelta(days=1)
    return [d + timedelta(days=7 * i) for i in range(n)]


async def _run():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    tag = uuid.uuid4().hex[:8]
    mant = f"MANT_SAB_{tag}"
    class_id = f"CLS_SAB_{tag}"
    school_id = f"SCH_SAB_{tag}"
    assign_id = f"ASG_SAB_{tag}"

    sats = _first_saturdays(6)
    target_sat = sats[0]            # 1º sábado letivo
    control_sat = sats[1]           # sábado NÃO letivo (controle)

    created_events = []
    try:
        await db.classes.insert_one({
            "id": class_id, "name": f"Turma Sábado {tag}", "school_id": school_id,
            "academic_year": YEAR, "mantenedora_id": mant, "education_level": "anos_iniciais",
        })
        # Evento sábado letivo APENAS no target (1º sábado) → rotação index 0.
        ev_id = str(uuid.uuid4())
        await db.calendar_events.insert_one({
            "id": ev_id, "event_type": "sabado_letivo", "academic_year": YEAR,
            "mantenedora_id": mant, "is_school_day": True,
            "start_date": target_sat.isoformat(), "end_date": target_sat.isoformat(),
            "title": "Sábado Letivo (teste)",
        })
        created_events.append(ev_id)

        # Descobre o dia da semana correspondente pela rotação e cria um slot nesse dia.
        sat_map = await get_saturday_weekday_map(db, academic_year=YEAR, mantenedora_id=mant)
        corresponding_wd = sat_map.get(target_sat.isoformat())

        await db.teacher_class_assignments.insert_one({
            "id": assign_id, "class_id": class_id, "deleted": False,
            "valid_from": f"{YEAR}-01-01", "valid_until": None,
            "component_id": "comp_test", "component_name": "Matemática (teste)",
            "teacher_id": "teacher_test", "teacher_name": "Prof. Teste",
            "weekly_slots": [{"weekday": corresponding_wd, "aula_numero": 1,
                              "start_time": "07:00", "end_time": "07:50"}],
        })

        async with httpx.AsyncClient(base_url=API, timeout=40) as c:
            lg = (await c.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PWD})).json()
            h = {"Authorization": f"Bearer {lg['access_token']}"}
            d_from = (target_sat - timedelta(days=2)).isoformat()
            d_to = (control_sat + timedelta(days=1)).isoformat()
            r = await c.get(f"/api/calendar/diary-state/{class_id}?from={d_from}&to={d_to}", headers=h)
        return sat_map, sats, target_sat, control_sat, corresponding_wd, r.status_code, (r.json() if r.status_code == 200 else r.text)
    finally:
        await db.classes.delete_one({"id": class_id})
        await db.teacher_class_assignments.delete_many({"id": assign_id})
        await db.calendar_events.delete_many({"id": {"$in": created_events}})


def test_sabado_letivo_rotation_and_diary():
    sat_map, sats, target_sat, control_sat, cwd, status, body = asyncio.run(_run())

    # ---- Rotação cíclica Seg–Sex (relativa, robusta a eventos globais) ----
    # Para os 6 sábados deste mantenedora apenas o 1º é letivo neste teste,
    # então valida-se o valor pontual + a regra de ciclo via helper sintético.
    assert cwd in (1, 2, 3, 4, 5), f"Dia correspondente deve ser Seg–Sex, veio {cwd}"

    # ---- Diário: aulas no sábado letivo ----
    assert status == 200, f"diary-state deve retornar 200: {body}"
    days = {d["date"]: d for d in body["days"]}
    tgt = days[target_sat.isoformat()]
    ctl = days[control_sat.isoformat()]

    assert tgt["expected_slots"] >= 1, (
        f"Sábado letivo {target_sat} deveria ter aulas (slot do dia {cwd}), "
        f"veio expected_slots={tgt['expected_slots']}"
    )
    assert tgt.get("is_explicit_school_day") is True, "Sábado letivo deve ser marcado como dia letivo explícito"
    assert ctl["expected_slots"] == 0, (
        f"Sábado comum {control_sat} NÃO pode gerar aulas, veio {ctl['expected_slots']}"
    )
    print(f"✓ Sábado letivo {target_sat} → aulas do dia {cwd} | slots={tgt['expected_slots']} | controle={ctl['expected_slots']}")


def test_rotation_is_cyclic_mon_to_fri():
    """get_saturday_weekday_map deve produzir ciclo consecutivo Seg→Sex (1..5)."""
    async def _seed_and_map():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        tag = uuid.uuid4().hex[:8]
        mant = f"MANT_ROT_{tag}"
        sats = _first_saturdays(6)
        ids = []
        try:
            for s in sats:
                eid = str(uuid.uuid4()); ids.append(eid)
                await db.calendar_events.insert_one({
                    "id": eid, "event_type": "sabado_letivo", "academic_year": YEAR,
                    "mantenedora_id": mant, "is_school_day": True,
                    "start_date": s.isoformat(), "end_date": s.isoformat(),
                })
            m = await get_saturday_weekday_map(db, academic_year=YEAR, mantenedora_id=mant)
            return [m[s.isoformat()] for s in sats]
        finally:
            await db.calendar_events.delete_many({"id": {"$in": ids}})

    seq = asyncio.run(_seed_and_map())
    # AUDITORIA EXPLÍCITA (pedido do cliente):
    #   1º sábado letivo → Segunda (isoweekday 1)
    #   2º sábado letivo → Terça   (isoweekday 2)
    DAY = {1: "Segunda", 2: "Terça", 3: "Quarta", 4: "Quinta", 5: "Sexta"}
    assert seq[0] == 1, f"1º sábado deve ser Segunda(1), veio {DAY.get(seq[0], seq[0])}"
    assert seq[1] == 2, f"2º sábado deve ser Terça(2), veio {DAY.get(seq[1], seq[1])}"
    assert seq == [1, 2, 3, 4, 5, 1], f"Rotação esperada Seg→Sex→Seg, veio {[DAY.get(x) for x in seq]}"
    # Consecutivo cíclico em 1..5
    for i in range(1, len(seq)):
        assert seq[i] == (seq[i - 1] % 5) + 1, f"Rotação não cíclica: {seq}"
    print("✓ Rotação confirmada: " + " | ".join(f"{i+1}º→{DAY[w]}" for i, w in enumerate(seq)))


if __name__ == "__main__":
    test_rotation_is_cyclic_mon_to_fri()
    test_sabado_letivo_rotation_and_diary()
    print("OK")
