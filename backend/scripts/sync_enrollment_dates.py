#!/usr/bin/env python3
"""
Script para sincronizar enrollment_date dos alunos a partir do historico.

Para cada aluno/matricula ativa sem enrollment_date, busca a data da acao
"matricula" mais recente no student_history e atualiza:
  - students.enrollment_date
  - enrollments.enrollment_date

Uso no servidor de producao:
  cd /root/sigesc/backend
  python3 scripts/sync_enrollment_dates.py

Ou com dry-run (apenas mostra o que seria feito):
  python3 scripts/sync_enrollment_dates.py --dry-run
"""

import asyncio
import sys
import os

# Adiciona o diretorio do backend ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

DRY_RUN = '--dry-run' in sys.argv


async def main():
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'sigesc')

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    print(f"Conectado ao banco: {db_name}")
    print(f"Modo: {'DRY-RUN (nenhuma alteracao sera feita)' if DRY_RUN else 'EXECUCAO REAL'}")
    print("-" * 60)

    # 1. Buscar todas as matriculas ativas sem enrollment_date
    enrollments_sem_data = await db.enrollments.find(
        {
            "status": "active",
            "$or": [
                {"enrollment_date": {"$exists": False}},
                {"enrollment_date": None},
                {"enrollment_date": ""}
            ]
        },
        {"_id": 0, "id": 1, "student_id": 1, "class_id": 1}
    ).to_list(None)

    print(f"Matriculas ativas sem enrollment_date: {len(enrollments_sem_data)}")

    # 2. Buscar alunos ativos sem enrollment_date
    students_sem_data = await db.students.find(
        {
            "status": "active",
            "$or": [
                {"enrollment_date": {"$exists": False}},
                {"enrollment_date": None},
                {"enrollment_date": ""}
            ]
        },
        {"_id": 0, "id": 1, "full_name": 1}
    ).to_list(None)

    print(f"Alunos ativos sem enrollment_date: {len(students_sem_data)}")
    print("-" * 60)

    # Coletar todos os student_ids unicos
    student_ids = set()
    for e in enrollments_sem_data:
        student_ids.add(e['student_id'])
    for s in students_sem_data:
        student_ids.add(s['id'])

    if not student_ids:
        print("Nenhum aluno/matricula precisa de atualizacao.")
        return

    # 3. Buscar historico de matricula para esses alunos
    # Pega a ULTIMA acao de matricula para cada aluno (mais recente)
    history_entries = await db.student_history.find(
        {
            "student_id": {"$in": list(student_ids)},
            "action_type": "matricula"
        },
        {"_id": 0, "student_id": 1, "action_date": 1}
    ).sort("action_date", -1).to_list(None)

    # Mapa: student_id -> data da matricula mais recente
    history_map = {}
    for h in history_entries:
        sid = h['student_id']
        if sid not in history_map:
            action_date = h.get('action_date', '')
            if action_date:
                # Extrair apenas a data (YYYY-MM-DD)
                date_str = str(action_date)[:10]
                history_map[sid] = date_str

    print(f"Historicos de matricula encontrados: {len(history_map)} alunos")
    print("-" * 60)

    updated_students = 0
    updated_enrollments = 0
    skipped = 0

    for sid in student_ids:
        enrollment_date = history_map.get(sid)

        if not enrollment_date:
            # Fallback: buscar a data de criacao da matricula ativa
            enrollment = await db.enrollments.find_one(
                {"student_id": sid, "status": "active"},
                {"_id": 0, "created_at": 1}
            )
            if enrollment and enrollment.get('created_at'):
                enrollment_date = str(enrollment['created_at'])[:10]

        if not enrollment_date:
            student = await db.students.find_one({"id": sid}, {"_id": 0, "full_name": 1})
            name = student.get('full_name', sid) if student else sid
            print(f"  SKIP: {name} - sem historico de matricula e sem created_at")
            skipped += 1
            continue

        # Buscar nome para log
        student = await db.students.find_one({"id": sid}, {"_id": 0, "full_name": 1, "enrollment_date": 1})
        name = student.get('full_name', sid) if student else sid

        print(f"  {name}: enrollment_date = {enrollment_date}")

        if not DRY_RUN:
            # Atualizar student
            result_s = await db.students.update_one(
                {"id": sid, "$or": [
                    {"enrollment_date": {"$exists": False}},
                    {"enrollment_date": None},
                    {"enrollment_date": ""}
                ]},
                {"$set": {"enrollment_date": enrollment_date}}
            )
            if result_s.modified_count > 0:
                updated_students += 1

            # Atualizar enrollment(s) ativa(s)
            result_e = await db.enrollments.update_many(
                {"student_id": sid, "status": "active", "$or": [
                    {"enrollment_date": {"$exists": False}},
                    {"enrollment_date": None},
                    {"enrollment_date": ""}
                ]},
                {"$set": {"enrollment_date": enrollment_date}}
            )
            updated_enrollments += result_e.modified_count
        else:
            updated_students += 1
            updated_enrollments += 1

    print("-" * 60)
    print(f"Resultado:")
    print(f"  Alunos atualizados: {updated_students}")
    print(f"  Matriculas atualizadas: {updated_enrollments}")
    print(f"  Ignorados (sem data): {skipped}")

    if DRY_RUN:
        print("\n[DRY-RUN] Nenhuma alteracao foi feita no banco.")
    else:
        print("\nAtualizacao concluida com sucesso!")


if __name__ == '__main__':
    asyncio.run(main())
