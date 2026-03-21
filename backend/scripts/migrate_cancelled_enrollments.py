"""
Script de migração: Limpeza retroativa de matrículas canceladas.

Aplica a mesma lógica do novo cancelamento para alunos já cancelados anteriormente:
1. Remove o aluno dos registros de frequência das turmas
2. Deleta notas do aluno nas turmas
3. Deleta as matrículas canceladas
4. Seta status do aluno para 'inactive' com school_id e class_id limpos

USO:
  python migrate_cancelled_enrollments.py             # Modo prévia (dry-run)
  python migrate_cancelled_enrollments.py --execute   # Executa de fato
"""

import asyncio
import sys
import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "sigesc")

DRY_RUN = "--execute" not in sys.argv


async def migrate():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    print("=" * 60)
    print(f"  MIGRAÇÃO: Limpeza de matrículas canceladas")
    print(f"  Banco: {DB_NAME}")
    print(f"  Modo: {'PRÉVIA (dry-run)' if DRY_RUN else 'EXECUÇÃO REAL'}")
    print("=" * 60)

    # 1. Busca alunos com status 'cancelled'
    cancelled_students = await db.students.find(
        {"status": {"$in": ["cancelled", "cancelado"]}},
        {"_id": 0, "id": 1, "full_name": 1, "school_id": 1, "class_id": 1}
    ).to_list(1000)

    # 2. Busca matrículas com status 'cancelled' (podem incluir alunos que já mudaram de status)
    cancelled_enrollments = await db.enrollments.find(
        {"status": "cancelled"},
        {"_id": 0, "id": 1, "student_id": 1, "class_id": 1, "school_id": 1}
    ).to_list(5000)

    # Consolida: student_ids de ambas as fontes
    student_ids_from_students = {s["id"] for s in cancelled_students}
    student_ids_from_enrollments = {e["student_id"] for e in cancelled_enrollments}
    all_student_ids = student_ids_from_students | student_ids_from_enrollments

    print(f"\nAlunos com status cancelled: {len(cancelled_students)}")
    print(f"Matrículas com status cancelled: {len(cancelled_enrollments)}")
    print(f"Total de alunos afetados: {len(all_student_ids)}")

    if not all_student_ids:
        print("\nNenhum dado para migrar.")
        return

    total_attendance_cleaned = 0
    total_grades_deleted = 0
    total_enrollments_deleted = 0
    total_students_updated = 0

    for sid in sorted(all_student_ids):
        student = await db.students.find_one({"id": sid}, {"_id": 0, "id": 1, "full_name": 1, "status": 1, "school_id": 1, "class_id": 1})
        name = student.get("full_name", "???") if student else "???"

        # Busca class_ids das matrículas canceladas desse aluno
        enrollments = await db.enrollments.find(
            {"student_id": sid, "status": "cancelled"},
            {"_id": 0, "class_id": 1, "id": 1}
        ).to_list(50)
        class_ids = list(set(e.get("class_id") for e in enrollments if e.get("class_id")))

        # Conta dados a serem afetados
        att_count = 0
        if class_ids:
            att_count = await db.attendance.count_documents(
                {"class_id": {"$in": class_ids}, "records.student_id": sid}
            )
        grade_count = 0
        if class_ids:
            grade_count = await db.grades.count_documents(
                {"student_id": sid, "class_id": {"$in": class_ids}}
            )

        print(f"\n  [{name}] (id: {sid})")
        print(f"    Status atual: {student.get('status') if student else '?'}")
        print(f"    Matrículas canceladas a deletar: {len(enrollments)}")
        print(f"    Turmas: {class_ids}")
        print(f"    Registros de frequência a limpar: {att_count}")
        print(f"    Notas a deletar: {grade_count}")

        if not DRY_RUN:
            # 1. Remove aluno dos registros de frequência
            if class_ids:
                result = await db.attendance.update_many(
                    {"class_id": {"$in": class_ids}},
                    {"$pull": {"records": {"student_id": sid}}}
                )
                total_attendance_cleaned += result.modified_count

            # 2. Deleta notas
            if class_ids:
                result = await db.grades.delete_many(
                    {"student_id": sid, "class_id": {"$in": class_ids}}
                )
                total_grades_deleted += result.deleted_count

            # 3. Deleta matrículas canceladas
            result = await db.enrollments.delete_many(
                {"student_id": sid, "status": "cancelled"}
            )
            total_enrollments_deleted += result.deleted_count

            # 4. Atualiza status do aluno para inactive
            if student and student.get("status") in ["cancelled", "cancelado"]:
                await db.students.update_one(
                    {"id": sid},
                    {"$set": {"status": "inactive", "school_id": "", "class_id": ""}}
                )
                total_students_updated += 1
                print(f"    -> Aluno atualizado: inactive, escola/turma limpos")
        else:
            total_attendance_cleaned += att_count
            total_grades_deleted += grade_count
            total_enrollments_deleted += len(enrollments)
            if student and student.get("status") in ["cancelled", "cancelado"]:
                total_students_updated += 1

    print("\n" + "=" * 60)
    print("  RESUMO")
    print("=" * 60)
    print(f"  Alunos atualizados para inactive:    {total_students_updated}")
    print(f"  Matrículas deletadas:                {total_enrollments_deleted}")
    print(f"  Frequências limpas:                  {total_attendance_cleaned}")
    print(f"  Notas deletadas:                     {total_grades_deleted}")

    if DRY_RUN:
        print("\n  (Modo PRÉVIA - nenhuma alteração foi feita)")
        print("  Para executar de fato, rode:")
        print("    python migrate_cancelled_enrollments.py --execute")
    else:
        print("\n  Migração concluída com sucesso!")


if __name__ == "__main__":
    asyncio.run(migrate())
