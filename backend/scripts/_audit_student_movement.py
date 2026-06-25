"""Auditoria de movimentação de alunos — coleta EVIDÊNCIA REAL de banco.
Cenário: aluno na Turma A com frequência/notas/conteúdo/AEE/Bolsa Família,
remanejado para Turma B (PUT + copy-data) e depois retornado para A.
Inspeciona preservação/duplicação em cada coleção. Sandbox isolado (AUDMOV-*).
"""
import os, json
from pathlib import Path
from datetime import datetime, timezone

import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001").rstrip("/")
EMAIL, PWD = "gutenberg@sigesc.com", "@Celta2007"
YEAR = datetime.now().year
P = "AUDMOV-"
TAG = {"audit_mov": True}


def teardown():
    cols = ["mantenedoras", "schools", "calendario_letivo", "classes", "students",
            "enrollments", "attendance", "grades", "content_entries", "planos_aee",
            "bolsa_familia_tracking", "student_history", "courses"]
    for c in cols:
        db[c].delete_many(TAG)
    # Docs criados pela API (sem tag): limpa por student_id e por prefixo de turma
    sid = f"{P}STU"
    cls = [f"{P}CLASS-A", f"{P}CLASS-B"]
    for c in ["enrollments", "grades", "planos_aee", "bolsa_familia_tracking", "student_history"]:
        db[c].delete_many({"student_id": sid})
    for c in ["attendance", "grades", "content_entries"]:
        db[c].delete_many({"class_id": {"$in": cls}})
    db.students.delete_many({"id": sid})
    db.academic_events.delete_many({"student_id": sid})


def login():
    d = requests.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PWD}, timeout=30).json()
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {d.get('access_token') or d.get('token')}",
                      "X-CSRF-Token": d.get("csrf_token") or "", "Content-Type": "application/json"})
    return s


def seed():
    teardown()
    mant = f"{P}MANT"
    sch = f"{P}SCH"
    db.mantenedoras.insert_one({**TAG, "id": mant, "nome": "AUD MANT", "name": "AUD MANT"})
    db.schools.insert_one({**TAG, "id": sch, "name": "AUD SCHOOL", "mantenedora_id": mant,
                           "status": "active", "niveis_ensino_oferecidos": ["fundamental_anos_iniciais"]})
    db.calendario_letivo.insert_one({**TAG, "id": f"{P}CAL", "ano_letivo": YEAR, "school_id": sch, "mantenedora_id": mant})
    course = f"{P}COURSE"
    db.courses.insert_one({**TAG, "id": course, "name": "Língua Portuguesa", "mantenedora_id": mant})
    for cl in ["A", "B"]:
        db.classes.insert_one({**TAG, "id": f"{P}CLASS-{cl}", "name": f"TURMA {cl}", "school_id": sch,
                               "mantenedora_id": mant, "grade_level": "1º Ano",
                               "education_level": "fundamental_anos_iniciais", "academic_year": YEAR,
                               "shift": "morning", "course_ids": [course],
                               "school_history": [{"school_id": sch, "start_date": f"{YEAR}-01-01", "end_date": None}]})
    sid = f"{P}STU"
    db.students.insert_one({**TAG, "id": sid, "full_name": "Aluno Auditoria", "birth_date": "2017-05-01",
                            "sex": "masculino", "school_id": sch, "class_id": f"{P}CLASS-A",
                            "mantenedora_id": mant, "status": "active"})
    db.enrollments.insert_one({**TAG, "id": f"{P}ENR-A", "student_id": sid, "school_id": sch,
                               "class_id": f"{P}CLASS-A", "academic_year": YEAR, "status": "active",
                               "enrollment_number": "AUD0001", "created_at": datetime.now(timezone.utc).isoformat()})
    # lançamentos na turma A
    db.grades.insert_one({**TAG, "id": f"{P}GRD-A", "student_id": sid, "class_id": f"{P}CLASS-A",
                          "course_id": course, "academic_year": YEAR, "b1": 8.0, "b2": 7.0})
    db.attendance.insert_one({**TAG, "id": f"{P}ATT-A", "class_id": f"{P}CLASS-A", "date": f"{YEAR}-03-10",
                              "academic_year": YEAR, "course_id": course, "period": "regular",
                              "records": [{"student_id": sid, "status": "P"}]})
    db.attendance.insert_one({**TAG, "id": f"{P}ATT-A2", "class_id": f"{P}CLASS-A", "date": f"{YEAR}-03-11",
                              "academic_year": YEAR, "course_id": course, "period": "regular",
                              "records": [{"student_id": sid, "status": "F"}]})
    db.content_entries.insert_one({**TAG, "id": f"{P}CNT-A", "class_id": f"{P}CLASS-A", "course_id": course,
                                   "date": f"{YEAR}-03-10", "content": "Conteúdo A", "school_id": sch})
    db.planos_aee.insert_one({**TAG, "id": f"{P}AEE", "student_id": sid, "school_id": sch, "academic_year": YEAR, "status": "ativo"})
    db.bolsa_familia_tracking.insert_one({**TAG, "student_id": sid, "school_id": sch, "academic_year": YEAR, "month": 3})
    return sid


def snap(sid, label):
    A, B = f"{P}CLASS-A", f"{P}CLASS-B"
    out = {
        "label": label,
        "student.class_id": db.students.find_one({"id": sid})["class_id"],
        "grades_A": db.grades.count_documents({"student_id": sid, "class_id": A}),
        "grades_B": db.grades.count_documents({"student_id": sid, "class_id": B}),
        "grades_B_migrated": db.grades.count_documents({"student_id": sid, "class_id": B, "migrated_from_class_id": {"$exists": True}}),
        "att_A_recs": db.attendance.count_documents({"class_id": A, "records.student_id": sid}),
        "att_B_recs": db.attendance.count_documents({"class_id": B, "records.student_id": sid}),
        "content_A": db.content_entries.count_documents({"class_id": A}),
        "content_B": db.content_entries.count_documents({"class_id": B}),
        "enroll_active": [e["class_id"] for e in db.enrollments.find({"student_id": sid, "status": "active"}, {"_id": 0, "class_id": 1})],
        "enroll_all": [(e["class_id"], e["status"]) for e in db.enrollments.find({"student_id": sid}, {"_id": 0, "class_id": 1, "status": 1})],
        "aee": db.planos_aee.count_documents({"student_id": sid}),
        "bolsa": db.bolsa_familia_tracking.count_documents({"student_id": sid}),
    }
    return out


def move(s, sid, target, hint):
    r = s.put(f"{BASE}/api/students/{sid}", json={"class_id": target, "action_hint": hint}, timeout=30)
    cp = s.post(f"{BASE}/api/students/{sid}/copy-data",
                json={"source_class_id": db.students.find_one({'id': sid})['class_id'],
                      "target_class_id": target, "copy_type": hint, "academic_year": YEAR}, timeout=30)
    return r.status_code, cp.status_code


def main():
    import asyncio
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from services.history_consolidator import build_consolidated_history

    sid = seed()
    s = login()
    results = [snap(sid, "BASELINE (Turma A)")]

    # A -> B (remanejamento)
    src_before = db.students.find_one({'id': sid})['class_id']
    r1 = s.put(f"{BASE}/api/students/{sid}", json={"class_id": f"{P}CLASS-B", "action_hint": "remanejamento"}, timeout=30)
    cp1 = s.post(f"{BASE}/api/students/{sid}/copy-data",
                 json={"source_class_id": src_before, "target_class_id": f"{P}CLASS-B",
                       "copy_type": "remanejamento", "academic_year": YEAR}, timeout=30)
    results.append({"_http": f"PUT={r1.status_code} copy={cp1.status_code}"})
    results.append(snap(sid, "APÓS A→B (remanejamento)"))

    # B -> A (retorno)
    r2 = s.put(f"{BASE}/api/students/{sid}", json={"class_id": f"{P}CLASS-A", "action_hint": "remanejamento"}, timeout=30)
    cp2 = s.post(f"{BASE}/api/students/{sid}/copy-data",
                 json={"source_class_id": f"{P}CLASS-B", "target_class_id": f"{P}CLASS-A",
                       "copy_type": "remanejamento", "academic_year": YEAR}, timeout=30)
    results.append({"_http": f"PUT={r2.status_code} copy={cp2.status_code}"})
    results.append(snap(sid, "APÓS B→A (retorno)"))

    # Histórico consolidado (usa motor async)
    from motor.motor_asyncio import AsyncIOMotorClient
    amc = AsyncIOMotorClient(os.environ["MONGO_URL"])
    adb = amc[os.environ["DB_NAME"]]
    hist = asyncio.new_event_loop().run_until_complete(build_consolidated_history(adb, student_id=sid))
    hist_summary = {
        "n_records": len(hist["records"]),
        "records": [{"ano": r["ano_letivo"], "serie": r["serie"], "escola": r["escola"],
                     "grades": r["grades"], "freq": r["frequencia"], "class_id": r.get("_class_id")} for r in hist["records"]],
        "from_enrollments": hist["consolidated_meta"]["from_enrollments"],
    }

    print(json.dumps({"snapshots": results, "historico_consolidado": hist_summary}, indent=2, ensure_ascii=False))
    teardown()


if __name__ == "__main__":
    main()
