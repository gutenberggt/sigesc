"""Testes — Consolidação pedagógica na movimentação + Reconstrução de Histórico.
Evidência em banco real (sandbox MOVTEST-*, self-teardown).
Cobre: preservação da origem, continuidade (freq+notas+CONTEÚDO) no destino,
idempotência, dedup do histórico e a ferramenta de Reconstrução (dry-run/execute/recibo).
"""
import os, uuid
from pathlib import Path
from datetime import datetime, timezone

import pytest, requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001").rstrip("/")
EMAIL = os.environ.get("TRANSFER_TEST_EMAIL", "gutenberg@sigesc.com")
PWD = os.environ.get("TRANSFER_TEST_PASSWORD", "@Celta2007")
_db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
P = "MOVTEST-"
YEAR = datetime.now().year


@pytest.fixture(scope="module")
def auth():
    d = requests.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PWD}, timeout=30).json()
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {d.get('access_token') or d.get('token')}",
                      "X-CSRF-Token": d.get("csrf_token") or "", "Content-Type": "application/json"})
    return s


def _teardown():
    sid = f"{P}STU"
    cls = [f"{P}CLASS-A", f"{P}CLASS-B"]
    for c in ["enrollments", "grades", "planos_aee", "bolsa_familia_tracking", "student_history", "academic_events"]:
        _db[c].delete_many({"student_id": sid})
    for c in ["attendance", "grades", "content_entries"]:
        _db[c].delete_many({"class_id": {"$in": cls}})
    _db.students.delete_many({"id": sid})
    for c in ["classes", "schools", "mantenedoras", "calendario_letivo", "courses", "history_reconstruction_audit"]:
        _db[c].delete_many({"id": {"$regex": f"^{P}"}})
    _db.history_reconstruction_audit.delete_many({"school_id": f"{P}SCH"})


@pytest.fixture
def world():
    _teardown()
    mant, sch, course, sid = f"{P}MANT", f"{P}SCH", f"{P}COURSE", f"{P}STU"
    now = datetime.now(timezone.utc).isoformat()
    _db.mantenedoras.insert_one({"id": mant, "nome": "MOV MANT", "name": "MOV MANT"})
    _db.schools.insert_one({"id": sch, "name": "MOV SCHOOL", "mantenedora_id": mant, "status": "active",
                            "niveis_ensino_oferecidos": ["fundamental_anos_iniciais"]})
    _db.calendario_letivo.insert_one({"id": f"{P}CAL", "ano_letivo": YEAR, "school_id": sch, "mantenedora_id": mant})
    _db.courses.insert_one({"id": course, "name": "Língua Portuguesa", "mantenedora_id": mant})
    for cl in ["A", "B"]:
        _db.classes.insert_one({"id": f"{P}CLASS-{cl}", "name": f"MOV {cl}", "school_id": sch, "mantenedora_id": mant,
                                "grade_level": "1º Ano", "education_level": "fundamental_anos_iniciais",
                                "academic_year": YEAR, "shift": "morning", "course_ids": [course],
                                "school_history": [{"school_id": sch, "start_date": f"{YEAR}-01-01", "end_date": None}]})
    _db.students.insert_one({"id": sid, "full_name": "Aluno Mov", "birth_date": "2017-05-01", "sex": "masculino",
                             "school_id": sch, "class_id": f"{P}CLASS-A", "mantenedora_id": mant, "status": "active"})
    _db.enrollments.insert_one({"id": f"{P}ENR", "student_id": sid, "school_id": sch, "class_id": f"{P}CLASS-A",
                                "academic_year": YEAR, "status": "active", "enrollment_number": "MOV1", "created_at": now})
    _db.grades.insert_one({"id": f"{P}GRD", "student_id": sid, "class_id": f"{P}CLASS-A", "course_id": course,
                           "academic_year": YEAR, "b1": 8.0, "b2": 7.0})
    _db.attendance.insert_one({"id": f"{P}ATT1", "class_id": f"{P}CLASS-A", "date": f"{YEAR}-03-10", "academic_year": YEAR,
                               "course_id": course, "period": "regular", "records": [{"student_id": sid, "status": "P"}]})
    _db.attendance.insert_one({"id": f"{P}ATT2", "class_id": f"{P}CLASS-A", "date": f"{YEAR}-03-11", "academic_year": YEAR,
                               "course_id": course, "period": "regular", "records": [{"student_id": sid, "status": "F"}]})
    _db.content_entries.insert_one({"id": f"{P}CNT", "class_id": f"{P}CLASS-A", "course_id": course,
                                    "date": f"{YEAR}-03-10", "content": "Conteúdo A", "school_id": sch, "academic_year": YEAR})
    yield {"sid": sid, "A": f"{P}CLASS-A", "B": f"{P}CLASS-B", "school": sch}
    _teardown()


def _move(auth, sid, target, hint="remanejamento"):
    return auth.put(f"{BASE}/api/students/{sid}", json={"class_id": target, "action_hint": hint}, timeout=30)


def test_movement_backend_consolidates_freq_grades_content(auth, world):
    sid, A, B = world["sid"], world["A"], world["B"]
    r = _move(auth, sid, B)
    assert r.status_code in (200, 201), r.text[:300]
    # ORIGEM preservada
    assert _db.grades.count_documents({"student_id": sid, "class_id": A}) == 1
    assert _db.attendance.count_documents({"class_id": A, "records.student_id": sid}) == 2
    assert _db.content_entries.count_documents({"class_id": A}) == 1
    # DESTINO recebe continuidade (incl. CONTEÚDO) — consolidado pelo BACKEND, sem copy-data do front
    assert _db.grades.count_documents({"student_id": sid, "class_id": B}) == 1
    assert _db.attendance.count_documents({"class_id": B, "records.student_id": sid}) == 2
    assert _db.content_entries.count_documents({"class_id": B}) == 1, "conteúdo deve ser copiado no backend"


def test_movement_idempotent(auth, world):
    sid, A, B = world["sid"], world["A"], world["B"]
    _move(auth, sid, B)
    # chama copy-data de novo (idempotente) e mais um PUT B->B (no-op)
    auth.post(f"{BASE}/api/students/{sid}/copy-data",
              json={"source_class_id": A, "target_class_id": B, "copy_type": "remanejamento", "academic_year": YEAR}, timeout=30)
    assert _db.grades.count_documents({"student_id": sid, "class_id": B}) == 1
    assert _db.content_entries.count_documents({"class_id": B}) == 1


def test_historico_dedup_single_record(auth, world):
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    from services.history_consolidator import build_consolidated_history
    sid = world["sid"]
    _move(auth, sid, world["B"])
    adb = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    hist = asyncio.new_event_loop().run_until_complete(build_consolidated_history(adb, student_id=sid))
    same_year = [r for r in hist["records"] if r["ano_letivo"] == str(YEAR)]
    assert len(same_year) == 1, f"Histórico deve ter 1 registro por ano/série, veio {len(same_year)}"
    assert same_year[0]["frequencia"] == 50.0


def test_reconstruction_dryrun_and_execute(auth, world):
    sid = world["sid"]
    # cria divergência: move A->B mas remove a nota copiada do destino (simula legado inconsistente)
    _move(auth, sid, world["B"])
    _db.grades.delete_many({"student_id": sid, "class_id": world["B"]})
    assert _db.grades.count_documents({"student_id": sid, "class_id": world["B"]}) == 0

    dr = auth.post(f"{BASE}/api/admin/history-reconstruction/dry-run",
                   json={"scope": "student", "student_id": sid, "academic_year": YEAR}, timeout=40)
    assert dr.status_code == 200, dr.text[:300]
    assert dr.json()["to_consolidate"]["grades"] >= 1

    ex = auth.post(f"{BASE}/api/admin/history-reconstruction/execute",
                   json={"scope": "student", "student_id": sid, "academic_year": YEAR,
                         "reason": "Reconstrucao teste automatizado"}, timeout=60)
    assert ex.status_code == 200, ex.text[:300]
    proto = ex.json()["protocol"]
    assert ex.json()["applied_counts"]["grades"] >= 1
    # nota recuperada no destino
    assert _db.grades.count_documents({"student_id": sid, "class_id": world["B"]}) == 1

    rc = auth.get(f"{BASE}/api/admin/history-reconstruction/{proto}/receipt", timeout=40)
    assert rc.status_code == 200 and rc.content[:4] == b"%PDF"


def test_reconstruction_requires_super_admin():
    r = requests.post(f"{BASE}/api/admin/history-reconstruction/dry-run", json={"scope": "student", "student_id": "x"}, timeout=15)
    assert r.status_code in (401, 403)
