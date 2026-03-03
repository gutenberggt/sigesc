#!/usr/bin/env python3
"""
Script para remover matrículas duplicadas (enrollments) no SIGESC.
Encontra alunos com mais de 1 matrícula ativa na mesma turma/ano
e mantém apenas a mais antiga, removendo as duplicatas.

USO:
  1. Copie este arquivo para o servidor
  2. Entre no container backend:
     docker exec -it $(docker ps --filter "name=backend" -q) bash
  3. Execute em modo DRY RUN (apenas mostra, não apaga):
     python3 /tmp/fix_duplicates.py
  4. Para executar de fato:
     python3 /tmp/fix_duplicates.py --executar
"""

import asyncio
import os
import sys
from datetime import datetime

async def main():
    from motor.motor_asyncio import AsyncIOMotorClient

    modo_executar = '--executar' in sys.argv

    # Conexão com MongoDB
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://mongo:27017')
    db_name = os.environ.get('DB_NAME', 'sigesc')

    print("=" * 70)
    print("  SIGESC - Remoção de Matrículas Duplicadas")
    print("=" * 70)
    print(f"  MongoDB: {mongo_url}")
    print(f"  Banco:   {db_name}")
    print(f"  Modo:    {'EXECUÇÃO REAL' if modo_executar else 'DRY RUN (simulação)'}")
    print("=" * 70)
    print()

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    # Pipeline de agregação: agrupar por (student_id, class_id, academic_year, status=active)
    # e encontrar grupos com mais de 1 documento
    pipeline = [
        {"$match": {"status": "active"}},
        {"$group": {
            "_id": {
                "student_id": "$student_id",
                "class_id": "$class_id",
                "academic_year": "$academic_year"
            },
            "count": {"$sum": 1},
            "enrollment_ids": {"$push": "$id"},
            "mongo_ids": {"$push": "$_id"},
            "dates": {"$push": "$created_at"}
        }},
        {"$match": {"count": {"$gt": 1}}},
        {"$sort": {"count": -1}}
    ]

    duplicates = await db.enrollments.aggregate(pipeline).to_list(1000)

    if not duplicates:
        print("Nenhuma matrícula duplicada encontrada!")
        print("O banco está limpo.")
        client.close()
        return

    print(f"Encontrados {len(duplicates)} grupo(s) de matrículas duplicadas:\n")

    total_to_remove = 0
    removal_list = []

    for i, dup in enumerate(duplicates, 1):
        student_id = dup['_id']['student_id']
        class_id = dup['_id']['class_id']
        academic_year = dup['_id']['academic_year']
        count = dup['count']

        # Buscar nome do aluno
        student = await db.students.find_one(
            {"id": student_id}, {"_id": 0, "full_name": 1, "enrollment_number": 1}
        )
        student_name = student.get('full_name', 'N/A') if student else 'N/A'
        enrollment_num = student.get('enrollment_number', '') if student else ''

        # Buscar nome da turma
        turma = await db.classes.find_one(
            {"id": class_id}, {"_id": 0, "name": 1}
        )
        turma_name = turma.get('name', 'N/A') if turma else 'N/A'

        # Buscar todas as matrículas deste grupo com detalhes
        enrollments = await db.enrollments.find({
            "student_id": student_id,
            "class_id": class_id,
            "academic_year": academic_year,
            "status": "active"
        }, {"_id": 1, "id": 1, "created_at": 1, "enrollment_date": 1}).sort("created_at", 1).to_list(100)

        print(f"  {i}. {student_name} (Mat: {enrollment_num})")
        print(f"     Turma: {turma_name} | Ano: {academic_year}")
        print(f"     Matrículas ativas: {count}")

        # Manter a primeira (mais antiga), remover as demais
        keep = enrollments[0]
        to_remove = enrollments[1:]

        print(f"     MANTER:  ID={keep['id'][:15]}... (criada em {keep.get('created_at', '?')})")
        for rem in to_remove:
            print(f"     REMOVER: ID={rem['id'][:15]}... (criada em {rem.get('created_at', '?')})")
            removal_list.append(rem['_id'])

        total_to_remove += len(to_remove)
        print()

    print("-" * 70)
    print(f"  RESUMO: {total_to_remove} matrícula(s) duplicada(s) a remover")
    print(f"          {len(duplicates)} aluno(s) afetado(s)")
    print("-" * 70)
    print()

    if not modo_executar:
        print("  *** MODO DRY RUN - Nenhuma alteração foi feita ***")
        print("  Para executar de fato, rode:")
        print("  python3 /tmp/fix_duplicates.py --executar")
        print()
    else:
        print("  Removendo duplicatas...")
        removed = 0
        for mongo_id in removal_list:
            result = await db.enrollments.delete_one({"_id": mongo_id})
            if result.deleted_count:
                removed += 1

        print(f"\n  CONCLUÍDO: {removed} matrícula(s) duplicada(s) removida(s).")
        print(f"  Data/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        print()

        # Verificação pós-remoção
        remaining = await db.enrollments.aggregate(pipeline).to_list(1000)
        if not remaining:
            print("  Verificação: OK - Nenhuma duplicata restante.")
        else:
            print(f"  ATENÇÃO: Ainda restam {len(remaining)} grupo(s) duplicados!")

    client.close()

if __name__ == "__main__":
    asyncio.run(main())
