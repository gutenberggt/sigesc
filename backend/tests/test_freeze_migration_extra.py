"""
Cobertura adicional do congelamento + migração (Feb 2026):

  (a) Edição de grade migrated negada para professor (403).
  (b) Edição permitida para super_admin com preservação da flag.
  (c) PDF de frequência por bimestre responde 200 (application/pdf) sem erro
      em turma com aluno transferido (action_date 2026-03-10).
  (d) Cross-tenant guard em GET /api/schools/{id}: gerente da Mantenedora A
      com school_link residual de escola B recebe 403.

Observação: o test de designar_gerente revoga tokens (scope=function por
conta disso). Cada teste relogga o gerente após a designação.
"""
import os
import sys
import uuid
import asyncio
import pytest
import requests
from datetime import datetime, timezone

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


def _login(email, pwd):
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": pwd},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _get_db():
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def super_token():
    return _login(SUPER_CREDS["email"], SUPER_CREDS["password"])


# ─────────────────────────────────────────────────────────────────────────────
#  Fixture: cenário origem→destino com aluno transferido em 10/03/2026
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def migration_scenario(super_token):
    """Turma origem T1 + destino T2 + aluno transferido + grade migrated em T2."""
    from auth_utils import hash_password

    db = _get_db()

    async def setup():
        flo = await db.mantenedoras.find_one({}, {"_id": 0})
        flo_id = flo["id"]
        school = await db.schools.find_one({"mantenedora_id": flo_id}, {"_id": 0})
        school_id = school["id"]

        await db.classes.delete_many({"name": {"$regex": "^TEST_FME_"}})
        await db.students.delete_many({"full_name": "TEST_FME_ALUNO"})
        await db.users.delete_many({"email": {"$regex": "^test_fme_"}})

        t1_id = "test_fme_T1_" + str(uuid.uuid4())[:8]
        t2_id = "test_fme_T2_" + str(uuid.uuid4())[:8]
        await db.classes.insert_many([
            {
                "id": t1_id, "name": "TEST_FME_T1_ORIGEM",
                "school_id": school_id, "mantenedora_id": flo_id,
                "academic_year": 2026, "education_level": "fundamental_anos_iniciais",
                "grade_level": "3 ano", "status": "active",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "id": t2_id, "name": "TEST_FME_T2_DESTINO",
                "school_id": school_id, "mantenedora_id": flo_id,
                "academic_year": 2026, "education_level": "fundamental_anos_iniciais",
                "grade_level": "3 ano", "status": "active",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        ])

        student_id = "test_fme_aluno_" + str(uuid.uuid4())[:8]
        await db.students.insert_one({
            "id": student_id, "full_name": "TEST_FME_ALUNO",
            "school_id": school_id, "class_id": t2_id,  # já migrado
            "mantenedora_id": flo_id, "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        await db.enrollments.insert_many([
            {
                "id": str(uuid.uuid4()), "student_id": student_id,
                "class_id": t1_id, "school_id": school_id,
                "academic_year": 2026, "status": "relocated",
                "enrollment_date": "2026-02-01T00:00:00+00:00",
            },
            {
                "id": str(uuid.uuid4()), "student_id": student_id,
                "class_id": t2_id, "school_id": school_id,
                "academic_year": 2026, "status": "active",
                "enrollment_date": "2026-03-10T00:00:00+00:00",
            },
        ])

        course_id = "test_fme_course_" + str(uuid.uuid4())[:8]
        await db.courses.insert_one({
            "id": course_id, "name": "TEST_FME_COURSE",
            "school_id": school_id, "mantenedora_id": flo_id,
            "academic_year": 2026,
        })

        # Grade em T2 já migrada
        grade_id = str(uuid.uuid4())
        await db.grades.insert_one({
            "id": grade_id, "student_id": student_id,
            "class_id": t2_id, "course_id": course_id,
            "academic_year": 2026, "mantenedora_id": flo_id,
            "b1": 8.5, "b2": None, "b3": None, "b4": None,
            "rec_s1": None, "rec_s2": None, "recovery": None,
            "final_average": None, "status": "cursando",
            "migrated_from_class_id": t1_id,
            "migrated_at": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        # Histórico de remanejamento (action_date)
        await db.student_history.insert_one({
            "id": str(uuid.uuid4()),
            "student_id": student_id,
            "class_id": t1_id,
            "action_type": "remanejamento",
            "action_date": "2026-03-10T12:00:00+00:00",
        })

        # Attendance em T2: 02/03 (P) e 12/03 (P) — 12/03 é após action_date
        for date_iso, status in [("2026-03-02", "P"), ("2026-03-12", "P")]:
            await db.attendance.insert_one({
                "id": str(uuid.uuid4()), "class_id": t2_id, "date": date_iso,
                "academic_year": 2026, "mantenedora_id": flo_id,
                "records": [{
                    "student_id": student_id, "status": status,
                    "migrated_from_class_id": t1_id,
                }],
                "course_id": None, "period": "regular",
            })

        # Cria professor vinculado à T2
        prof_id = str(uuid.uuid4())
        prof_email = f"test_fme_prof_{uuid.uuid4().hex[:6]}@sigesc.com"
        prof_pwd = "test123"
        await db.users.insert_one({
            "id": prof_id,
            "email": prof_email,
            "full_name": "TEST FME PROFESSOR",
            "role": "professor",
            "roles": ["professor"],
            "status": "active",
            "mantenedora_id": flo_id,
            "school_ids": [school_id],
            "school_links": [{"school_id": school_id, "role": "professor"}],
            "class_ids": [t2_id],
            "password_hash": hash_password(prof_pwd),
            "created_at": datetime.now(timezone.utc),
        })
        # Aloca o professor no curso/turma
        await db.teacher_allocations.insert_one({
            "id": str(uuid.uuid4()),
            "teacher_id": prof_id,
            "class_id": t2_id,
            "course_id": course_id,
            "school_id": school_id,
            "academic_year": 2026,
            "status": "active",
        })

        return {
            "school_id": school_id, "flo_id": flo_id,
            "t1_id": t1_id, "t2_id": t2_id,
            "student_id": student_id, "course_id": course_id,
            "grade_id": grade_id,
            "prof_email": prof_email, "prof_pwd": prof_pwd, "prof_id": prof_id,
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
        await db.users.delete_one({"id": data["prof_id"]})
        await db.teacher_allocations.delete_many({"teacher_id": data["prof_id"]})

    asyncio.get_event_loop().run_until_complete(teardown())


# (a) Professor não pode editar grade migrada → 403
def test_professor_cannot_edit_migrated_grade(migration_scenario):
    d = migration_scenario
    prof_token = _login(d["prof_email"], d["prof_pwd"])

    # PUT direto no grade_id
    r = requests.put(
        f"{BASE_URL}/api/grades/{d['grade_id']}",
        headers={"Authorization": f"Bearer {prof_token}"},
        json={"b1": 9.9},
        timeout=30,
    )
    assert r.status_code == 403, f"esperado 403, veio {r.status_code}: {r.text}"
    detail = r.json().get("detail", "").lower()
    assert "migrada" in detail or "secretário" in detail or "secretario" in detail

    # POST (upsert) também deve bloquear
    r = requests.post(
        f"{BASE_URL}/api/grades",
        headers={"Authorization": f"Bearer {prof_token}"},
        json={
            "student_id": d["student_id"],
            "class_id": d["t2_id"],
            "course_id": d["course_id"],
            "academic_year": 2026,
            "b1": 5.0,
        },
        timeout=30,
    )
    assert r.status_code == 403, f"esperado 403, veio {r.status_code}: {r.text}"

    # Batch também
    r = requests.post(
        f"{BASE_URL}/api/grades/batch",
        headers={"Authorization": f"Bearer {prof_token}"},
        json=[{
            "student_id": d["student_id"],
            "class_id": d["t2_id"],
            "course_id": d["course_id"],
            "academic_year": 2026,
            "b1": 4.0,
        }],
        timeout=30,
    )
    assert r.status_code == 403, f"esperado 403, veio {r.status_code}: {r.text}"


# (b) super_admin pode editar e flag migrated_from_class_id é preservada
def test_super_admin_can_edit_migrated_grade_preserving_flag(super_token, migration_scenario):
    d = migration_scenario

    r = requests.put(
        f"{BASE_URL}/api/grades/{d['grade_id']}",
        headers={"Authorization": f"Bearer {super_token}"},
        json={"b2": 7.0},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["b2"] == 7.0
    assert body["b1"] == 8.5  # unchanged

    # Verifica no DB que migrated_from_class_id ainda está presente
    db = _get_db()

    async def check():
        g = await db.grades.find_one({"id": d["grade_id"]}, {"_id": 0})
        assert g is not None
        assert g.get("migrated_from_class_id") == d["t1_id"], (
            f"Flag migrated perdida após update: {g}"
        )
        assert g.get("b2") == 7.0

    asyncio.get_event_loop().run_until_complete(check())


# (c) PDF de frequência da turma destino responde 200 (application/pdf)
def test_attendance_pdf_bimestre_returns_pdf(super_token, migration_scenario):
    d = migration_scenario
    r = requests.get(
        f"{BASE_URL}/api/attendance/pdf/bimestre/{d['t2_id']}",
        params={"bimestre": 1, "academic_year": 2026, "course_id": d["course_id"]},
        headers={"Authorization": f"Bearer {super_token}"},
        timeout=60,
    )
    assert r.status_code == 200, f"PDF bimestre falhou: {r.status_code} - {r.text[:500]}"
    ctype = r.headers.get("content-type", "")
    assert "pdf" in ctype.lower(), f"Content-type esperado pdf, veio: {ctype}"
    # PDF magic bytes
    assert r.content[:4] == b"%PDF", "Conteúdo não parece ser um PDF válido"


# Também valida PDF da turma origem (com action_date — datas >= 10/03 ficam em branco)
def test_attendance_pdf_origin_class_with_action_date(super_token, migration_scenario):
    d = migration_scenario
    r = requests.get(
        f"{BASE_URL}/api/attendance/pdf/bimestre/{d['t1_id']}",
        params={"bimestre": 1, "academic_year": 2026, "course_id": d["course_id"]},
        headers={"Authorization": f"Bearer {super_token}"},
        timeout=60,
    )
    assert r.status_code == 200, f"PDF origem falhou: {r.status_code} - {r.text[:500]}"
    assert "pdf" in r.headers.get("content-type", "").lower()
    assert r.content[:4] == b"%PDF"


# ─────────────────────────────────────────────────────────────────────────────
#  (d) Cross-tenant guard em verify_school_access
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="function")
def cross_tenant_setup():
    """Cria gerente da Mantenedora A (Floresta) com school_link residual
    de uma escola da Mantenedora B (Pau Darco - TEST). Sem o fix, GET
    /api/schools/{B} passaria; com o fix retorna 403.
    """
    from auth_utils import hash_password
    db = _get_db()

    async def setup():
        flo = await db.mantenedoras.find_one({}, {"_id": 0})
        flo_id = flo["id"]
        flo_school = await db.schools.find_one({"mantenedora_id": flo_id}, {"_id": 0})
        flo_sid = flo_school["id"]

        # Mantenedora B
        pau = await db.mantenedoras.find_one(
            {"name": "TEST_CrossTenant_Mant_B"}, {"_id": 0}
        )
        if not pau:
            pau_id = str(uuid.uuid4())
            await db.mantenedoras.insert_one({
                "id": pau_id, "name": "TEST_CrossTenant_Mant_B",
                "created_at": datetime.now(timezone.utc),
            })
        else:
            pau_id = pau["id"]
        # Escola da Mant B
        sch_b = await db.schools.find_one(
            {"name": "TEST_CrossTenant_School_B", "mantenedora_id": pau_id},
            {"_id": 0},
        )
        if not sch_b:
            pau_sid = str(uuid.uuid4())
            await db.schools.insert_one({
                "id": pau_sid, "name": "TEST_CrossTenant_School_B",
                "mantenedora_id": pau_id, "status": "active",
                "created_at": datetime.now(timezone.utc),
            })
        else:
            pau_sid = sch_b["id"]

        # Gerente da Mant A com school_link residual à escola da Mant B
        await db.users.delete_one({"email": "test_crosstenant_gerente@sigesc.com"})
        uid = str(uuid.uuid4())
        await db.users.insert_one({
            "id": uid,
            "email": "test_crosstenant_gerente@sigesc.com",
            "full_name": "TEST CROSSTENANT GERENTE",
            "role": "gerente",
            "roles": ["gerente"],
            "status": "active",
            "mantenedora_id": flo_id,           # tenant A
            "school_ids": [flo_sid, pau_sid],    # vazamento residual
            "school_links": [
                {"school_id": flo_sid, "role": "gerente"},
                {"school_id": pau_sid, "role": "gerente"},  # residual
            ],
            "password_hash": hash_password("test123"),
            "created_at": datetime.now(timezone.utc),
        })
        return {"flo_id": flo_id, "pau_id": pau_id, "flo_sid": flo_sid, "pau_sid": pau_sid, "uid": uid}

    data = asyncio.get_event_loop().run_until_complete(setup())
    yield data

    async def teardown():
        await db.users.delete_one({"id": data["uid"]})

    asyncio.get_event_loop().run_until_complete(teardown())


def test_cross_tenant_guard_blocks_school_from_other_mantenedora(cross_tenant_setup):
    d = cross_tenant_setup
    token = _login("test_crosstenant_gerente@sigesc.com", "test123")

    # Acesso à escola da própria mantenedora: OK
    r = requests.get(
        f"{BASE_URL}/api/schools/{d['flo_sid']}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    assert r.status_code == 200, r.text

    # Acesso à escola de OUTRA mantenedora: 403
    r = requests.get(
        f"{BASE_URL}/api/schools/{d['pau_sid']}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    assert r.status_code == 403, f"esperado 403 cross-tenant, veio {r.status_code}: {r.text}"
    detail = r.json().get("detail", "").lower()
    assert "outra mantenedora" in detail or "tenant" in detail or "negado" in detail
