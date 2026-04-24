"""
Seed: cria (ou re-sincroniza) um usuário de teste com role='aluno'
vinculado a um aluno real (que já possua matrícula + notas).

Uso:
    python -m scripts.seed_test_student

Credenciais geradas:
    Email: aluno@sigesc.com
    Senha: aluno123
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Permite execução direta: python backend/scripts/seed_test_student.py
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from auth_utils import hash_password  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

TEST_EMAIL = "aluno@sigesc.com"
TEST_PASSWORD = "aluno123"


async def _pick_best_student(db) -> dict | None:
    """Prefere aluno com matrícula + turma que tenha courses + notas lançadas."""
    # 1) Com grades lançadas (melhor caso)
    student_ids_com_notas = await db.grades.distinct("student_id")
    if student_ids_com_notas:
        for sid in student_ids_com_notas[:20]:
            st = await db.students.find_one({"id": sid}, {"_id": 0})
            if st:
                return st
    # 2) Aluno em turma com courses
    async for enr in db.enrollments.find(
        {"status": {"$in": ["ativa", "active", "matriculado", "matriculada"]}},
        {"_id": 0, "student_id": 1, "class_id": 1},
    ).limit(100):
        class_doc = await db.classes.find_one({"id": enr.get("class_id")}, {"_id": 0, "course_ids": 1})
        if class_doc and (class_doc.get("course_ids") or []):
            st = await db.students.find_one({"id": enr["student_id"]}, {"_id": 0})
            if st:
                return st
    # 3) Qualquer enrollment ativa
    enr = await db.enrollments.find_one({"status": {"$in": ["ativa", "active", "matriculado", "matriculada"]}}, {"_id": 0})
    if enr and enr.get("student_id"):
        st = await db.students.find_one({"id": enr["student_id"]}, {"_id": 0})
        if st:
            return st
    # 4) Fallback: qualquer aluno
    return await db.students.find_one({}, {"_id": 0})


async def main():
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    student = await _pick_best_student(db)
    if not student:
        print("[ERRO] Nenhum aluno encontrado no banco. Cadastre alunos antes de rodar este seed.")
        return 1

    # Descobre escola e mantenedora do aluno
    school_id = student.get("school_id")
    mantenedora_id = student.get("mantenedora_id")
    if not mantenedora_id and school_id:
        school = await db.schools.find_one({"id": school_id}, {"_id": 0, "mantenedora_id": 1})
        mantenedora_id = (school or {}).get("mantenedora_id")
    if not mantenedora_id:
        # Fallback: primeira mantenedora
        m = await db.mantenedoras.find_one({}, {"_id": 0, "id": 1})
        mantenedora_id = (m or {}).get("id")

    now_iso = datetime.now(timezone.utc).isoformat()
    user_doc = {
        "id": str(uuid.uuid4()),
        "full_name": student.get("full_name") or student.get("name") or "Aluno Teste",
        "email": TEST_EMAIL,
        "role": "aluno",
        "roles": ["aluno"],
        "status": "active",
        "avatar_url": None,
        "school_links": [{"school_id": school_id, "roles": ["aluno"]}] if school_id else [],
        "mantenedora_id": mantenedora_id,
        "student_id": student["id"],
        "password_hash": hash_password(TEST_PASSWORD),
        "created_at": now_iso,
    }

    existing = await db.users.find_one({"email": TEST_EMAIL}, {"_id": 0, "id": 1})
    if existing:
        # Re-sincroniza vínculo e senha (idempotente)
        await db.users.update_one(
            {"email": TEST_EMAIL},
            {"$set": {
                "role": "aluno",
                "roles": ["aluno"],
                "status": "active",
                "student_id": student["id"],
                "mantenedora_id": mantenedora_id,
                "school_links": user_doc["school_links"],
                "password_hash": user_doc["password_hash"],
                "full_name": user_doc["full_name"],
            }},
        )
        print(f"[OK] Usuário existente resincronizado: {TEST_EMAIL}")
    else:
        await db.users.insert_one(user_doc)
        print(f"[OK] Usuário criado: {TEST_EMAIL}")

    print(f"      student_id   = {student['id']}")
    print(f"      aluno        = {user_doc['full_name']}")
    print(f"      school_id    = {school_id}")
    print(f"      mantenedora  = {mantenedora_id}")
    print(f"      Email        = {TEST_EMAIL}")
    print(f"      Senha        = {TEST_PASSWORD}")
    return 0


if __name__ == "__main__":
    code = asyncio.run(main())
    sys.exit(code or 0)
