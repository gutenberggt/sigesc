"""
Feb 2026 — Congelamento de origem + migração com restrição de edição.

Cenário:
  T1: Aluno na Turma de Origem (B1 já em curso)
  Super_admin executa REMANEJAMENTO (action_date = 10/03/2026)
  → copy-data deve copiar grades e attendance da origem para destino
  → registros copiados ficam marcados com migrated_from_class_id
  → professor da turma destino NÃO pode editar registros migrados
  → secretario/gerente/super_admin/admin podem editar
  → load_grades_by_class na origem retorna grade.b2,b3,b4=null para o aluno saído
    (B1 que contém a action_date fica visível mas em blocked_after_action)
"""
import os
import sys
import uuid
import asyncio
import pytest
import requests

sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

SUPER_CREDS = {
    "email": "gutenberg@sigesc.com",
    "password": os.getenv("SIGESC_TEST_ADMIN_PASSWORD", "@Celta2007"),
}


@pytest.fixture(scope="module")
def super_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=SUPER_CREDS, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def setup_classes_and_student():
    """Cria turma origem T1, turma destino T2, aluno A1 com grade e attendance em T1."""
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    from motor.motor_asyncio import AsyncIOMotorClient
    from datetime import datetime, timezone

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    async def setup():
        flo = await db.mantenedoras.find_one({}, {"_id": 0})
        flo_id = flo["id"]
        school = await db.schools.find_one({"mantenedora_id": flo_id}, {"_id": 0})
        school_id = school["id"]

        # Limpa registros prévios
        await db.classes.delete_many({"name": {"$regex": "^TEST_FREEZE_"}})
        await db.students.delete_many({"full_name": "TEST_FREEZE_ALUNO"})
        await db.grades.delete_many({"student_id": {"$regex": "^test_freeze_"}})
        await db.attendance.delete_many({"class_id": {"$regex": "^test_freeze_"}})

        # Cria 2 turmas
        t1_id = "test_freeze_T1_" + str(uuid.uuid4())[:8]
        t2_id = "test_freeze_T2_" + str(uuid.uuid4())[:8]
        await db.classes.insert_many([
            {
                "id": t1_id, "name": "TEST_FREEZE_T1_ORIGEM",
                "school_id": school_id, "mantenedora_id": flo_id,
                "academic_year": 2026, "education_level": "fundamental_anos_iniciais",
                "grade_level": "3 ano", "status": "active",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "id": t2_id, "name": "TEST_FREEZE_T2_DESTINO",
                "school_id": school_id, "mantenedora_id": flo_id,
                "academic_year": 2026, "education_level": "fundamental_anos_iniciais",
                "grade_level": "3 ano", "status": "active",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        ])

        # Cria aluno na T1
        student_id = "test_freeze_aluno_" + str(uuid.uuid4())[:8]
        await db.students.insert_one({
            "id": student_id, "full_name": "TEST_FREEZE_ALUNO",
            "school_id": school_id, "class_id": t1_id,
            "mantenedora_id": flo_id, "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        await db.enrollments.insert_one({
            "id": str(uuid.uuid4()), "student_id": student_id,
            "class_id": t1_id, "school_id": school_id,
            "academic_year": 2026, "status": "active",
            "enrollment_date": "2026-02-01T00:00:00+00:00",
        })

        # Curso (componente curricular fictício)
        course_id = "test_freeze_course_" + str(uuid.uuid4())[:8]
        await db.courses.insert_one({
            "id": course_id, "name": "TEST_FREEZE_COURSE",
            "school_id": school_id, "mantenedora_id": flo_id,
            "academic_year": 2026,
        })

        # Grade no T1: B1=8.5 (já lançado antes da ação)
        grade_id = str(uuid.uuid4())
        await db.grades.insert_one({
            "id": grade_id, "student_id": student_id,
            "class_id": t1_id, "course_id": course_id,
            "academic_year": 2026, "mantenedora_id": flo_id,
            "b1": 8.5, "b2": None, "b3": None, "b4": None,
            "rec_s1": None, "rec_s2": None, "recovery": None,
            "final_average": None, "status": "cursando",
        })

        # Attendance em T1: 02/03 (presente) e 12/03 (após ação) e 02/04 (após ação)
        for date_iso, status in [("2026-03-02", "P"), ("2026-03-12", "F"), ("2026-04-02", "P")]:
            await db.attendance.insert_one({
                "id": str(uuid.uuid4()), "class_id": t1_id, "date": date_iso,
                "academic_year": 2026, "mantenedora_id": flo_id,
                "records": [{"student_id": student_id, "status": status}],
                "course_id": None, "period": "regular",
            })

        return {
            "school_id": school_id, "flo_id": flo_id,
            "t1_id": t1_id, "t2_id": t2_id,
            "student_id": student_id, "course_id": course_id,
            "grade_id": grade_id,
        }

    data = asyncio.get_event_loop().run_until_complete(setup())
    yield data

    async def teardown():
        await db.classes.delete_many({"id": {"$in": [data["t1_id"], data["t2_id"]]}})
        await db.students.delete_one({"id": data["student_id"]})
        await db.enrollments.delete_many({"student_id": data["student_id"]})
        await db.grades.delete_many({"student_id": data["student_id"]})
        await db.attendance.delete_many({"class_id": {"$in": [data["t1_id"], data["t2_id"]]}})
        await db.courses.delete_one({"id": data["course_id"]})
        await db.student_history.delete_many({"student_id": data["student_id"]})

    asyncio.get_event_loop().run_until_complete(teardown())


def test_copy_data_marks_migration_for_attendance_and_grades(super_token, setup_classes_and_student):
    """Após copy-data, registros de origem aparecem em destino com flag migrated_from_class_id."""
    d = setup_classes_and_student
    body = {
        "source_class_id": d["t1_id"],
        "target_class_id": d["t2_id"],
        "copy_type": "remanejamento",
        "academic_year": 2026,
    }
    r = requests.post(
        f"{BASE_URL}/api/students/{d['student_id']}/copy-data",
        headers={"Authorization": f"Bearer {super_token}"},
        json=body, timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["copied_data"]["attendance_records"] == 3
    assert body["copied_data"]["grades_records"] == 1

    # Valida no banco que os registros estão marcados como migrados
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    async def check():
        # grade na turma destino deve ter migrated_from_class_id
        g = await db.grades.find_one(
            {"class_id": d["t2_id"], "student_id": d["student_id"]}, {"_id": 0}
        )
        assert g is not None
        assert g.get("migrated_from_class_id") == d["t1_id"]
        # attendance em T2 com record do aluno deve ter migrated
        att_docs = await db.attendance.find(
            {"class_id": d["t2_id"]}, {"_id": 0}
        ).to_list(50)
        assert len(att_docs) == 3
        for a in att_docs:
            rec = next((r for r in a["records"] if r["student_id"] == d["student_id"]), None)
            assert rec is not None
            assert rec.get("migrated_from_class_id") == d["t1_id"]

    asyncio.get_event_loop().run_until_complete(check())


def test_blocked_after_action_includes_bimestre_of_action_date(super_token, setup_classes_and_student):
    """load_grades_by_class na origem deve incluir B1 (que contém 10/03/2026) em blocked_after_action."""
    d = setup_classes_and_student

    # Garante que existe student_history para a action_date
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    async def add_history():
        await db.student_history.delete_many({"student_id": d["student_id"]})
        await db.student_history.insert_one({
            "id": str(uuid.uuid4()),
            "student_id": d["student_id"],
            "class_id": d["t1_id"],
            "action_type": "remanejamento",
            "action_date": "2026-03-10T12:00:00+00:00",
        })
        # Marca aluno como inativo na turma origem (matrícula relocated)
        await db.enrollments.update_many(
            {"student_id": d["student_id"], "class_id": d["t1_id"]},
            {"$set": {"status": "relocated"}}
        )
        # Move student.class_id para T2 (estado normal pós-remanejamento)
        await db.students.update_one(
            {"id": d["student_id"]}, {"$set": {"class_id": d["t2_id"]}}
        )

    asyncio.get_event_loop().run_until_complete(add_history())

    r = requests.get(
        f"{BASE_URL}/api/grades/by-class/{d['t1_id']}/{d['course_id']}",
        params={"academic_year": 2026},
        headers={"Authorization": f"Bearer {super_token}"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    target = next((it for it in rows if it["student"]["id"] == d["student_id"]), None)
    assert target is not None, f"Aluno não retornado: {[it['student']['id'] for it in rows]}"
    blocked = target["student"]["blocked_after_action"]
    # B1 (fev-abr) contém 10/03/2026 → deve estar bloqueado (regra Feb 2026)
    assert 1 in blocked, f"B1 deveria estar bloqueado, retornou: {blocked}"
    assert 2 in blocked and 3 in blocked and 4 in blocked
    # B1 mantém valor visível (8.5), B2/B3/B4 vão como null
    assert target["grade"]["b1"] == 8.5
    assert target["grade"]["b2"] is None
    assert target["grade"]["b3"] is None
    assert target["grade"]["b4"] is None
