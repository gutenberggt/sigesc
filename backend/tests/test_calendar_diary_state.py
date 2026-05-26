"""Fase 4 — Tests do endpoint agregador GET /calendar/diary-state/{class_id}.

Cobre os 5 status semânticos:
  - empty (sem evidências)
  - partial (parte dos slots preenchida)
  - complete (todos publicados)
  - corrected (ao menos 1 content corrigido)
  - inconsistent (evidência fora de slot esperado)

E também:
  - summary global
  - validações (range, formato data)
  - expected_by_schedule sempre true
"""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://school-integrity-fix.preview.emergentagent.com"
).rstrip("/")
ADMIN = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}
# Turma seedada — 6º ANO A com 3 assignments do seed.
CLASS_ID = "3da4e569-6522-432c-9b42-1e344a2f0c69"
TEACHER_ID = "61c5f200-8d18-4d96-98dc-c567bbd13cc3"  # Ricleide (regente seedado)
COMP_REGENTE = "regente-fundamental"
STUDENT_A = "dc09b180-6b6d-488c-9744-0ec19f9117ea"

# Range fora do uso real — semana inteira longe dos seeds de produção.
# 2027-03 não é tocada por outros testes.
DATE_FROM = "2027-03-01"  # Segunda
DATE_TO = "2027-03-05"    # Sexta

_RUN_TAG = uuid.uuid4().hex[:8]


@pytest.fixture(scope="module", autouse=True)
def _clean():
    from pymongo import MongoClient
    from dotenv import load_dotenv
    load_dotenv()
    cli = MongoClient(os.environ["MONGO_URL"])
    db = cli[os.environ["DB_NAME"]]
    db.attendance.delete_many({"class_id": CLASS_ID, "date": {"$regex": "^2027-03-"}})
    db.content_entries.delete_many({"class_id": CLASS_ID, "date": {"$regex": "^2027-03-"}})
    # Garante que apenas os 3 assignments do seed cobrem esta turma — remove
    # leftover de outras suites de teste para que `expected_slots` seja determinístico.
    db.teacher_class_assignments.delete_many({
        "class_id": CLASS_ID, "source": {"$ne": "seed"},
    })
    # Fase 11: o helper de calendário letivo passou a filtrar dias fora dos
    # bimestres. Como este test usa datas em 2027 com turma de academic_year
    # 2026, inserimos um calendario_letivo school-specific cobrindo amplamente.
    cal_id = f"cal-test-{_RUN_TAG}"
    db.calendario_letivo.delete_many({"id": cal_id})
    db.calendario_letivo.insert_one({
        "id": cal_id,
        "ano_letivo": 2026,
        "school_id": "220d4022-ec5e-4fb6-86fc-9233112b87b2",
        "bimestre_1_inicio": "2026-01-01",
        "bimestre_1_fim": "2027-12-31",
        "bimestre_2_inicio": "2026-01-01",
        "bimestre_2_fim": "2027-12-31",
        "bimestre_3_inicio": "2026-01-01",
        "bimestre_3_fim": "2027-12-31",
        "bimestre_4_inicio": "2026-01-01",
        "bimestre_4_fim": "2027-12-31",
    })
    yield
    db.attendance.delete_many({"class_id": CLASS_ID, "date": {"$regex": "^2027-03-"}})
    db.content_entries.delete_many({"class_id": CLASS_ID, "date": {"$regex": "^2027-03-"}})
    db.calendario_letivo.delete_one({"id": cal_id})


@pytest.fixture(scope="module")
def headers():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=20)
    d = r.json()
    return {
        "Authorization": f"Bearer {d.get('access_token') or d.get('token')}",
        "X-CSRF-Token": d.get("csrf_token") or "",
        "Content-Type": "application/json",
    }


def _state(headers, **q):
    qs = "&".join(f"{k}={v}" for k, v in q.items())
    return requests.get(
        f"{BASE_URL}/api/calendar/diary-state/{CLASS_ID}?{qs}",
        headers=headers, timeout=20,
    )


# --- Validações de entrada -------------------------------------------------

def test_invalid_date_format_returns_400(headers):
    r = _state(headers, **{"from": "abc", "to": "2027-03-05"})
    assert r.status_code == 400


def test_to_before_from_returns_400(headers):
    r = _state(headers, **{"from": "2027-03-10", "to": "2027-03-01"})
    assert r.status_code == 400


def test_range_too_long_returns_400(headers):
    r = _state(headers, **{"from": "2027-01-01", "to": "2027-12-31"})
    assert r.status_code == 400


# --- Status: empty ---------------------------------------------------------

def test_empty_when_no_evidence(headers):
    """Quando há slots esperados mas zero evidência → empty.
    Quando NÃO há slots esperados (fim de semana / dia sem grade) → not_expected.
    """
    r = _state(headers, **{"from": DATE_FROM, "to": DATE_TO})
    assert r.status_code == 200, r.text[:400]
    d = r.json()
    assert d["class_id"] == CLASS_ID
    assert d["range_days"] == 5
    assert d["summary"]["expected_slots"] >= 8
    for day in d["days"]:
        if day["expected_slots"] > 0:
            assert day["status"] == "empty"
            for e in day["entries"]:
                assert e["expected_by_schedule"] is True
                assert e["attendance_status"] == "missing"
                assert e["content_status"] == "missing"
        else:
            # Dia sem slots esperados (não havia aula) NÃO pode ser "empty".
            assert day["status"] == "not_expected"


def test_not_expected_for_weekend(headers):
    """Sábado/Domingo sem assignments → status `not_expected`, expected_slots=0.

    Crítico semanticamente: separa 'não deveria existir lançamento' de 'deveria
    existir mas não veio'. UI usa para silenciar visualmente fins de semana.
    """
    # 2027-03-06 = Sábado, 2027-03-07 = Domingo. Seed só tem Seg-Sex.
    r = _state(headers, **{"from": "2027-03-06", "to": "2027-03-07"})
    d = r.json()
    assert d["range_days"] == 2
    for day in d["days"]:
        assert day["expected_slots"] == 0
        assert day["status"] == "not_expected"
    assert d["summary"]["day_status_counts"]["not_expected"] == 2
    assert d["summary"]["day_status_counts"]["empty"] == 0


# --- Status: partial (cria 1 attendance num único dia) ----------------------

def test_partial_when_only_attendance_lancada(headers):
    # Cria attendance da Segunda (2027-03-01) — leva slot regente aula 1 a "completed".
    # Mas content ainda missing → partial.
    r = requests.post(
        f"{BASE_URL}/api/attendance",
        json={
            "class_id": CLASS_ID, "date": "2027-03-01",
            "records": [{"student_id": STUDENT_A, "status": "P"}],
        },
        headers=headers, timeout=20,
    )
    assert r.status_code == 200, r.text[:300]
    r = _state(headers, **{"from": DATE_FROM, "to": DATE_TO})
    monday = next(d for d in r.json()["days"] if d["date"] == "2027-03-01")
    assert monday["status"] == "partial", monday
    completed_entries = [e for e in monday["entries"] if e["attendance_status"] == "completed"]
    assert len(completed_entries) >= 1


# --- Status: complete (attendance + content publicado para todos slots) ----

def test_complete_when_all_slots_have_attendance_and_published_content(headers):
    # Terça 2027-03-02 → regente aula 1 e 2. Anos finais: 1 attendance POR aula.
    for aula in (1, 2):
        requests.post(
            f"{BASE_URL}/api/attendance",
            json={
                "class_id": CLASS_ID, "date": "2027-03-02",
                "aula_numero": aula,
                "records": [{"student_id": STUDENT_A, "status": "P"}],
            },
            headers=headers, timeout=20,
        )
        c = requests.post(
            f"{BASE_URL}/api/content-entries",
            json={
                "class_id": CLASS_ID, "date": "2027-03-02",
                "component_id": COMP_REGENTE, "aula_numero": aula,
                "teacher_id": TEACHER_ID,
                "content": f"Aula {aula} de terça",
            },
            headers=headers, timeout=20,
        ).json()
        pub = requests.post(
            f"{BASE_URL}/api/content-entries/{c['id']}/publish",
            json={}, headers=headers, timeout=20,
        )
        assert pub.status_code == 200, pub.text[:200]

    r = _state(headers, **{"from": "2027-03-02", "to": "2027-03-02"})
    day = r.json()["days"][0]
    assert day["status"] == "complete", day
    # Todos entries com attendance completed + content published
    for e in day["entries"]:
        assert e["attendance_status"] in ("completed", "validated")
        assert e["content_status"] in ("published", "corrected")


# --- Status: corrected -----------------------------------------------------

def test_corrected_when_any_content_is_corrected(headers):
    # Quarta 2027-03-03: cria 1 content na aula 1 (regente), publica, corrige.
    # Aula 2 (regente) + Qua Aula 3 (EdFis) ficam missing → status final = corrected
    # (porque há 1 corrigido) — mas se "complete" exigir tudo, fica corrected aqui só
    # quando partial+corrected. Vamos testar exatamente isso.
    requests.post(
        f"{BASE_URL}/api/attendance",
        json={
            "class_id": CLASS_ID, "date": "2027-03-03",
            "records": [{"student_id": STUDENT_A, "status": "P"}],
        },
        headers=headers, timeout=20,
    )
    c = requests.post(
        f"{BASE_URL}/api/content-entries",
        json={
            "class_id": CLASS_ID, "date": "2027-03-03",
            "component_id": COMP_REGENTE, "aula_numero": 1,
            "teacher_id": TEACHER_ID,
            "content": "Conteúdo original quarta",
        },
        headers=headers, timeout=20,
    ).json()
    requests.post(f"{BASE_URL}/api/content-entries/{c['id']}/publish", json={}, headers=headers, timeout=20)
    requests.post(
        f"{BASE_URL}/api/content-entries/{c['id']}/correct",
        json={"change_note": "ajuste pedagógico", "content": "Conteúdo corrigido"},
        headers=headers, timeout=20,
    )
    r = _state(headers, **{"from": "2027-03-03", "to": "2027-03-03"})
    day = r.json()["days"][0]
    assert day["status"] == "corrected", day
    assert any(e["content_status"] == "corrected" for e in day["entries"])


# --- Status: inconsistent (evidência sem slot esperado) ---------------------

def test_inconsistent_when_attendance_on_day_without_expected_slots(headers):
    # Domingo 2027-03-07 não tem slots esperados (não há domingo no seed).
    # Criamos attendance lá → orphan_attendance_dates + status inconsistent.
    r = requests.post(
        f"{BASE_URL}/api/attendance",
        json={
            "class_id": CLASS_ID, "date": "2027-03-07",
            "records": [{"student_id": STUDENT_A, "status": "P"}],
        },
        headers=headers, timeout=20,
    )
    assert r.status_code == 200
    r = _state(headers, **{"from": "2027-03-07", "to": "2027-03-07"})
    d = r.json()
    assert "2027-03-07" in d["summary"]["orphan_attendance_dates"]
    day = d["days"][0]
    assert day["status"] == "inconsistent", day
    assert day["has_orphan_evidence"] is True


# --- Summary global --------------------------------------------------------

def test_summary_counts_aggregate(headers):
    # Já temos: 1 attendance Seg, 1 attendance Ter + 2 content publicados, 1 corrigido Qua, 1 órfão Dom.
    # Pega a semana toda.
    r = _state(headers, **{"from": DATE_FROM, "to": "2027-03-07"})
    d = r.json()
    s = d["summary"]
    assert s["expected_slots"] >= 8
    assert s["attendance_completed"] >= 1
    assert s["content_published"] >= 1
    assert s["content_corrected"] >= 1
    assert "2027-03-07" in s["orphan_attendance_dates"]
