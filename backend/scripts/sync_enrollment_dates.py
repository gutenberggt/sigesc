#!/usr/bin/env python3
"""
Script para sincronizar enrollment_date dos alunos a partir do historico.

Para cada aluno/matricula ativa sem enrollment_date, busca a data da acao
"matricula" mais recente no student_history e atualiza:
  - students.enrollment_date
  - enrollments.enrollment_date

Uso:
  python3 sync_enrollment_dates.py --dry-run    # apenas mostra o que seria feito
  python3 sync_enrollment_dates.py              # executa de fato

Se precisar informar conexao diferente:
  MONGO_URL="mongodb://localhost:27017" DB_NAME="sigesc" python3 sync_enrollment_dates.py --dry-run
"""

import asyncio
import sys
import os

DRY_RUN = '--dry-run' in sys.argv

# Tenta carregar .env se existir no diretorio atual ou no pai
for env_path in ['.env', '../.env', 'backend/.env', os.path.join(os.path.dirname(__file__), '.env'), os.path.join(os.path.dirname(__file__), '..', '.env')]:
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    val = val.strip().strip('"').strip("'")
                    if key.strip() not in os.environ:
                        os.environ[key.strip()] = val
        break

try:
    from motor.motor_asyncio import AsyncIOMotorClient
except ImportError:
    print("ERRO: motor nao encontrado. Instale com: pip install motor")
    sys.exit(1)


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
            # Fallback: data de criacao da matricula ativa
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

        student = await db.students.find_one({"id": sid}, {"_id": 0, "full_name": 1, "enrollment_date": 1})
        name = student.get('full_name', sid) if student else sid

        print(f"  {name}: enrollment_date = {enrollment_date}")

        if not DRY_RUN:
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
