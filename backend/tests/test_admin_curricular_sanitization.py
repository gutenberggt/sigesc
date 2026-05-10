"""
E2E HTTP — Saneamento Curricular Supervisionado (Fev/2026).

Cobre:
- GET /api/admin/diagnose-class-courses/{class_id} retorna shape com safe_to_remove
- POST /api/admin/classes/{class_id}/remove-course bloqueia sem X-Academic-Confirm (428)
- POST .../remove-course bloqueia se há vínculo acadêmico (409 COURSE_HAS_ACADEMIC_RECORDS)
- POST .../remove-course bloqueia reason curta (< 30 chars) → 422
- POST .../remove-course aplica soft removal + audit em curso fantasma → 200
- Dupla remoção do mesmo curso → 409 COURSE_NOT_LINKED_TO_CLASS

Princípio: boletim continua espelho fiel; sistema preserva evidência;
saneamento exige decisão humana auditada.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = "@Celta2007"
TENANT = "fix_mant_v1"


def _now():
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
               timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    csrf = data.get("csrf_token") or r.headers.get("X-CSRF-Token")
    token = data.get("access_token") or data.get("token")
    s.headers.update({
        "X-Mantenedora-Id": TENANT,
        "X-CSRF-Token": csrf or "",
        "Content-Type": "application/json",
    })
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    yield s


@pytest.fixture
def seeded_class():
    """Cria turma + 3 cursos: 2 com mesmo nome (1 ativo c/ nota, 1 fantasma).

    Retorna ids para o teste e limpa no final.
    Usa Mongo direto (semeadura controlada) — independente da API.
    """
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient

    suffix = uuid.uuid4().hex[:8]
    school_id = f"acs_school_{suffix}"
    class_id = f"acs_class_{suffix}"
    course_main = f"acs_course_main_{suffix}"
    course_ghost = f"acs_course_ghost_{suffix}"
    course_pt = f"acs_course_pt_{suffix}"
    student_id = f"acs_stu_{suffix}"

    async def _seed():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.schools.insert_one({
            "id": school_id, "name": "ESCOLA TESTE ACS",
            "mantenedora_id": TENANT,
        })
        await db.classes.insert_one({
            "id": class_id, "name": "7 ANO TESTE ACS",
            "school_id": school_id,
            "course_ids": [course_main, course_ghost, course_pt],
            "academic_year": 2026,
            "mantenedora_id": TENANT,
            "grade_level": "7º ANO",
        })
        await db.courses.insert_many([
            {"id": course_main, "name": "Ciências", "active": True,
             "mantenedora_id": TENANT},
            {"id": course_ghost, "name": "Ciências", "active": False,
             "mantenedora_id": TENANT},
            {"id": course_pt, "name": "Português", "active": True,
             "mantenedora_id": TENANT},
        ])
        await db.students.insert_one({
            "id": student_id, "full_name": "ALUNO TESTE ACS",
            "registration_number": f"ACS-{suffix}",
            "class_id": class_id, "school_id": school_id,
            "mantenedora_id": TENANT, "dependency_mode": "none",
        })
        # Apenas course_main tem nota (course_ghost é fantasma puro)
        await db.grades.insert_one({
            "id": f"acs_g_{suffix}", "student_id": student_id,
            "academic_year": 2026, "class_id": class_id,
            "course_id": course_main, "b1": 8.0, "final_average": 8.0,
            "mantenedora_id": TENANT,
        })
        client.close()

    async def _cleanup():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.schools.delete_many({"id": school_id})
        await db.classes.delete_many({"id": class_id})
        await db.courses.delete_many({"id": {"$in": [course_main, course_ghost, course_pt]}})
        await db.students.delete_many({"id": student_id})
        await db.grades.delete_many({"student_id": student_id})
        client.close()

    asyncio.run(_seed())
    yield {
        "class_id": class_id,
        "course_main": course_main,
        "course_ghost": course_ghost,
        "course_pt": course_pt,
        "student_id": student_id,
        "school_id": school_id,
    }
    asyncio.run(_cleanup())


def test_01_diagnose_returns_safe_to_remove_flag(session, seeded_class):
    r = session.get(
        f"{BASE_URL}/api/admin/diagnose-class-courses/{seeded_class['class_id']}",
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["class_id"] == seeded_class["class_id"]
    by_id = {c["course_id"]: c for c in body["courses"]}

    main = by_id[seeded_class["course_main"]]
    assert main["grades_count"] == 1
    assert main["safe_to_remove"] is False  # tem nota → bloqueado

    ghost = by_id[seeded_class["course_ghost"]]
    assert ghost["grades_count"] == 0
    assert ghost["attendance_count"] == 0
    assert ghost["safe_to_remove"] is True  # fantasma puro

    # Duplicidade detectada
    dup_names = [d["course_name"] for d in body["duplicates_by_name"]]
    assert "Ciências" in dup_names
    assert body["summary"]["duplicate_groups"] == 1
    assert body["summary"]["safe_to_remove_count"] >= 1


def test_02_remove_without_confirm_header_returns_428(session, seeded_class):
    # Garante que o cabeçalho NÃO esteja presente
    r = requests.post(
        f"{BASE_URL}/api/admin/classes/{seeded_class['class_id']}/remove-course",
        json={
            "course_id": seeded_class["course_ghost"],
            "reason": "Saneamento curricular: curso fantasma duplicado de Ciências",
        },
        headers={
            **{k: v for k, v in session.headers.items()
               if k.lower() != "x-academic-confirm"},
        },
        timeout=30,
    )
    assert r.status_code == 428, r.text
    body = r.json()
    detail = body.get("detail") or body
    assert (detail.get("error") if isinstance(detail, dict) else None) == \
        "ACADEMIC_CONFIRMATION_REQUIRED"


def test_03_remove_with_short_reason_returns_422(session, seeded_class):
    r = session.post(
        f"{BASE_URL}/api/admin/classes/{seeded_class['class_id']}/remove-course",
        json={"course_id": seeded_class["course_ghost"], "reason": "curto"},
        headers={**session.headers, "X-Academic-Confirm": "true"},
        timeout=30,
    )
    assert r.status_code == 422, r.text


def test_04_remove_course_with_grades_blocked_409(session, seeded_class):
    """Mesmo com X-Academic-Confirm + reason válida, curso com nota → 409."""
    r = session.post(
        f"{BASE_URL}/api/admin/classes/{seeded_class['class_id']}/remove-course",
        json={
            "course_id": seeded_class["course_main"],
            "reason": (
                "Tentativa de remoção bloqueada — curso com notas reais "
                "lançadas. Este teste valida o bloqueio."
            ),
        },
        headers={**session.headers, "X-Academic-Confirm": "true"},
        timeout=30,
    )
    assert r.status_code == 409, r.text
    body = r.json()
    detail = body.get("detail") or body
    assert detail.get("error") == "COURSE_HAS_ACADEMIC_RECORDS"
    assert detail["linked"]["grades_count"] >= 1


def test_05_remove_ghost_course_succeeds_with_soft_removal(session, seeded_class):
    """Curso fantasma com confirm + reason válida → 200 + soft removal + audit."""
    r = session.post(
        f"{BASE_URL}/api/admin/classes/{seeded_class['class_id']}/remove-course",
        json={
            "course_id": seeded_class["course_ghost"],
            "reason": (
                "Saneamento curricular: componente 'Ciências' duplicado "
                "sem registros acadêmicos, validado via diagnóstico."
            ),
        },
        headers={**session.headers, "X-Academic-Confirm": "true"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["removed_course_id"] == seeded_class["course_ghost"]
    assert body["override_recorded"] is True
    assert body["course_ids_after_count"] == body["course_ids_before_count"] - 1

    # Verifica que diagnose agora não lista mais o curso fantasma em course_ids_in_class
    r2 = session.get(
        f"{BASE_URL}/api/admin/diagnose-class-courses/{seeded_class['class_id']}",
        timeout=30,
    )
    assert r2.status_code == 200
    body2 = r2.json()
    assert seeded_class["course_ghost"] not in body2["course_ids_in_class"]
    # Duplicidade resolvida
    assert body2["summary"]["duplicate_groups"] == 0


def test_06_double_remove_returns_409_not_linked(session, seeded_class):
    """Após remover uma vez, segunda tentativa deve retornar 409 estável."""
    # Primeira remoção
    r1 = session.post(
        f"{BASE_URL}/api/admin/classes/{seeded_class['class_id']}/remove-course",
        json={
            "course_id": seeded_class["course_ghost"],
            "reason": (
                "Primeira remoção legítima do componente fantasma duplicado "
                "para o teste de idempotência seguinte."
            ),
        },
        headers={**session.headers, "X-Academic-Confirm": "true"},
        timeout=30,
    )
    assert r1.status_code == 200, r1.text

    # Segunda tentativa
    r2 = session.post(
        f"{BASE_URL}/api/admin/classes/{seeded_class['class_id']}/remove-course",
        json={
            "course_id": seeded_class["course_ghost"],
            "reason": (
                "Segunda tentativa idempotente — deve falhar com mensagem "
                "explícita e sem alterar estado da turma."
            ),
        },
        headers={**session.headers, "X-Academic-Confirm": "true"},
        timeout=30,
    )
    assert r2.status_code == 409, r2.text
    body = r2.json()
    detail = body.get("detail") or body
    assert detail.get("error") == "COURSE_NOT_LINKED_TO_CLASS"


def test_07_unauthenticated_remove_blocked():
    r = requests.post(
        f"{BASE_URL}/api/admin/classes/any/remove-course",
        json={"course_id": "any", "reason": "x" * 40},
        headers={"X-Academic-Confirm": "true",
                 "Content-Type": "application/json"},
        timeout=30,
    )
    assert r.status_code in (401, 403)
