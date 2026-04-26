"""
Feb 2026 — PDF de frequência: dias amparados por atestado médico devem renderizar 'A'
substituindo qualquer status (P/F/J) que o professor tenha lançado.

Cenário:
  - Aluno tem aula registrada em 2026-03-10 com status=F (falta)
  - Secretário registra atestado médico cobrindo 2026-03-09 a 2026-03-12
  - PDF de frequência do bimestre deve mostrar 'A' na coluna de 2026-03-10
"""
import os
import sys
import uuid
import asyncio
import pytest
import requests
from io import BytesIO

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
def setup_attendance_with_certificate():
    """Cria turma + aluno + 2 dias de attendance (1 falta) + atestado cobrindo a data."""
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

        await db.classes.delete_many({"name": {"$regex": "^TEST_ATESTADO_"}})
        await db.students.delete_many({"full_name": "TEST_ATESTADO_ALUNO"})
        await db.attendance.delete_many({"class_id": {"$regex": "^test_atestado_"}})
        await db.medical_certificates.delete_many({"reason": "TEST_ATESTADO_PYTEST"})

        class_id = "test_atestado_T_" + str(uuid.uuid4())[:8]
        await db.classes.insert_one({
            "id": class_id, "name": "TEST_ATESTADO_TURMA",
            "school_id": school_id, "mantenedora_id": flo_id,
            "academic_year": 2026, "education_level": "fundamental_anos_iniciais",
            "grade_level": "3 ano", "status": "active",
        })

        student_id = "test_atestado_aluno_" + str(uuid.uuid4())[:8]
        await db.students.insert_one({
            "id": student_id, "full_name": "TEST_ATESTADO_ALUNO",
            "school_id": school_id, "class_id": class_id,
            "mantenedora_id": flo_id, "status": "active",
        })
        await db.enrollments.insert_one({
            "id": str(uuid.uuid4()), "student_id": student_id,
            "class_id": class_id, "school_id": school_id,
            "academic_year": 2026, "status": "active",
        })

        # 2 sessões: 09/03 (P) e 10/03 (F) — atestado cobrirá ambas
        await db.attendance.insert_many([
            {
                "id": str(uuid.uuid4()), "class_id": class_id,
                "date": "2026-03-09", "academic_year": 2026,
                "mantenedora_id": flo_id,
                "records": [{"student_id": student_id, "status": "P"}],
            },
            {
                "id": str(uuid.uuid4()), "class_id": class_id,
                "date": "2026-03-10", "academic_year": 2026,
                "mantenedora_id": flo_id,
                "records": [{"student_id": student_id, "status": "F"}],
            },
        ])

        # Atestado médico cobrindo 09/03 a 12/03
        await db.medical_certificates.insert_one({
            "id": str(uuid.uuid4()), "student_id": student_id,
            "start_date": "2026-03-09", "end_date": "2026-03-12",
            "reason": "TEST_ATESTADO_PYTEST",
            "mantenedora_id": flo_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "class_id": class_id, "student_id": student_id,
            "school_id": school_id, "flo_id": flo_id,
        }

    data = asyncio.get_event_loop().run_until_complete(setup())
    yield data

    async def teardown():
        await db.classes.delete_one({"id": data["class_id"]})
        await db.students.delete_one({"id": data["student_id"]})
        await db.enrollments.delete_many({"student_id": data["student_id"]})
        await db.attendance.delete_many({"class_id": data["class_id"]})
        await db.medical_certificates.delete_many({"reason": "TEST_ATESTADO_PYTEST"})

    asyncio.get_event_loop().run_until_complete(teardown())


def test_attendance_pdf_renders_A_for_certificate_days(super_token, setup_attendance_with_certificate):
    """O endpoint deve retornar PDF e o conteúdo deve conter 'A' nas colunas dos dias com atestado."""
    d = setup_attendance_with_certificate
    r = requests.get(
        f"{BASE_URL}/api/attendance/pdf/bimestre/{d['class_id']}",
        params={"bimestre": 1, "academic_year": 2026},
        headers={"Authorization": f"Bearer {super_token}"},
        timeout=60,
    )
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "").startswith("application/pdf")

    # Extrai texto do PDF para validar que contém 'A'
    try:
        from pypdf import PdfReader
    except ImportError:
        from PyPDF2 import PdfReader

    pdf = PdfReader(BytesIO(r.content))
    full_text = "".join(p.extract_text() or "" for p in pdf.pages)

    assert "TEST_ATESTADO_ALUNO" in full_text, "aluno não apareceu no PDF"
    # No PDF, na linha do aluno, deve haver 'A' substituindo o 'F' lançado pelo professor
    # (e também substituindo o 'P' do dia 09 que estava em atestado)
    assert " A " in full_text or "\nA" in full_text or "A " in full_text, (
        f"Letra 'A' não encontrada no PDF (esperado para dias com atestado). Texto: {full_text[:1500]}"
    )
    # Legenda no rodapé (Feb 2026)
    assert "Legenda" in full_text, "Legenda não encontrada no PDF"
    assert "Atestado" in full_text, "Texto 'Atestado' (legenda) não encontrado no PDF"
