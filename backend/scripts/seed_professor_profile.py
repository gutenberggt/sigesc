"""Seed idempotente do PERFIL DE PROFESSOR para QA do fluxo offline (Fase A).

Cria/garante:
  - 1 doc `staff` vinculado a professor.teste@sigesc.com
  - alocações `teacher_assignments` (status 'ativo', 2026) na turma 'Turma Multi 1-2-3'

Sem isso, GET /api/professor/turmas devolve 404 e a tela /professor/frequencia
não popula Escola/Turma, bloqueando o E2E offline.

Uso: cd /app/backend && python scripts/seed_professor_profile.py
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

PROF_EMAIL = "professor.teste@sigesc.com"
CLASS_ID = "c09b8666-c8bb-40d1-b835-c2b0fa4b8ecd"  # Turma Multi 1-2-3 (Anos Iniciais)
COURSE_IDS = [
    "42d470dd-5183-48d3-ae9a-aa3e698ef01a",  # Língua Portuguesa
    "a090c6b9-b54f-4c30-933f-476c930411dd",  # Matemática
]
ACADEMIC_YEAR = 2026


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    user = await db.users.find_one({"email": PROF_EMAIL}, {"_id": 0})
    if not user:
        print(f"[seed] ERRO: usuário {PROF_EMAIL} não encontrado.")
        return
    turma = await db.classes.find_one({"id": CLASS_ID}, {"_id": 0})
    if not turma:
        print(f"[seed] ERRO: turma {CLASS_ID} não encontrada.")
        return

    tenant_id = turma.get("mantenedora_id") or user.get("mantenedora_id")
    school_id = turma.get("school_id")
    now = datetime.now(timezone.utc).isoformat()

    # 1. staff (idempotente por user_id)
    staff = await db.staff.find_one({"user_id": user["id"]}, {"_id": 0})
    if not staff:
        staff = await db.staff.find_one({"email": PROF_EMAIL}, {"_id": 0})
    if not staff:
        staff_id = str(uuid.uuid4())
        await db.staff.insert_one({
            "id": staff_id,
            "user_id": user["id"],
            "email": PROF_EMAIL,
            "full_name": user.get("full_name") or "Professor Teste QA",
            "staff_type": "professor",
            "school_id": school_id,
            "school_ids": [school_id],
            "mantenedora_id": tenant_id,
            "status": "ativo",
            "created_at": now,
        })
        print(f"[seed] staff criado: {staff_id}")
    else:
        staff_id = staff["id"]
        await db.staff.update_one(
            {"id": staff_id},
            {"$set": {"user_id": user["id"], "school_id": school_id,
                      "mantenedora_id": tenant_id, "status": "ativo"}},
        )
        print(f"[seed] staff já existente, atualizado: {staff_id}")

    # 2. teacher_assignments (idempotente por staff+class+course+ano)
    created = 0
    for course_id in COURSE_IDS:
        existing = await db.teacher_assignments.find_one({
            "staff_id": staff_id, "class_id": CLASS_ID,
            "course_id": course_id, "academic_year": ACADEMIC_YEAR,
        })
        if existing:
            await db.teacher_assignments.update_one(
                {"id": existing["id"]}, {"$set": {"status": "ativo"}}
            )
            continue
        await db.teacher_assignments.insert_one({
            "id": str(uuid.uuid4()),
            "staff_id": staff_id,
            "class_id": CLASS_ID,
            "course_id": course_id,
            "status": "ativo",
            "academic_year": ACADEMIC_YEAR,
            "school_id": school_id,
            "mantenedora_id": tenant_id,
            "created_at": now,
        })
        created += 1
    print(f"[seed] teacher_assignments garantidas (novas: {created}) p/ turma {turma.get('name')}")
    db.client.close()
    print("[seed] OK")


if __name__ == "__main__":
    asyncio.run(main())
