"""
Script de Limpeza de Dados Órfãos - SIGESC
Identifica e remove referências órfãs no banco de dados.
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone
import os
from dotenv import load_dotenv

load_dotenv()


async def find_orphan_enrollments(db):
    """Encontra matrículas com referências inválidas"""
    orphans = []
    
    enrollments = await db.enrollments.find({}, {"_id": 0}).to_list(10000)
    
    for enrollment in enrollments:
        issues = []
        
        # Verifica se o aluno existe
        student = await db.students.find_one({"id": enrollment.get('student_id')})
        if not student:
            issues.append(f"Aluno não encontrado: {enrollment.get('student_id')}")
        
        # Verifica se a escola existe
        school = await db.schools.find_one({"id": enrollment.get('school_id')})
        if not school:
            issues.append(f"Escola não encontrada: {enrollment.get('school_id')}")
        
        # Verifica se a turma existe
        if enrollment.get('class_id'):
            class_doc = await db.classes.find_one({"id": enrollment.get('class_id')})
            if not class_doc:
                issues.append(f"Turma não encontrada: {enrollment.get('class_id')}")
        
        if issues:
            orphans.append({
                'id': enrollment.get('id'),
                'type': 'enrollment',
                'issues': issues,
                'data': enrollment
            })
    
    return orphans


async def find_orphan_grades(db):
    """Encontra notas com referências inválidas"""
    orphans = []
    
    grades = await db.grades.find({}, {"_id": 0}).to_list(50000)
    
    for grade in grades:
        issues = []
        
        # Verifica se o aluno existe
        student = await db.students.find_one({"id": grade.get('student_id')})
        if not student:
            issues.append(f"Aluno não encontrado: {grade.get('student_id')}")
        
        # Verifica se a turma existe
        class_doc = await db.classes.find_one({"id": grade.get('class_id')})
        if not class_doc:
            issues.append(f"Turma não encontrada: {grade.get('class_id')}")
        
        # Verifica se o componente existe
        course = await db.courses.find_one({"id": grade.get('course_id')})
        if not course:
            issues.append(f"Componente não encontrado: {grade.get('course_id')}")
        
        if issues:
            orphans.append({
                'id': grade.get('id'),
                'type': 'grade',
                'issues': issues,
                'data': {'student_id': grade.get('student_id'), 'class_id': grade.get('class_id'), 'course_id': grade.get('course_id')}
            })
    
    return orphans


async def find_orphan_school_assignments(db):
    """Encontra lotações com referências inválidas"""
    orphans = []
    
    assignments = await db.school_assignments.find({}, {"_id": 0}).to_list(10000)
    
    for assignment in assignments:
        issues = []
        
        # Verifica se o servidor existe
        staff = await db.staff.find_one({"id": assignment.get('staff_id')})
        if not staff:
            issues.append(f"Servidor não encontrado: {assignment.get('staff_id')}")
        
        # Verifica se a escola existe
        school = await db.schools.find_one({"id": assignment.get('school_id')})
        if not school:
            issues.append(f"Escola não encontrada: {assignment.get('school_id')}")
        
        if issues:
            orphans.append({
                'id': assignment.get('id'),
                'type': 'school_assignment',
                'issues': issues,
                'data': assignment
            })
    
    return orphans


async def find_orphan_teacher_assignments(db):
    """Encontra alocações de professores com referências inválidas"""
    orphans = []
    
    assignments = await db.teacher_assignments.find({}, {"_id": 0}).to_list(10000)
    
    for assignment in assignments:
        issues = []
        
        # Verifica se o servidor existe
        staff = await db.staff.find_one({"id": assignment.get('staff_id')})
        if not staff:
            issues.append(f"Servidor não encontrado: {assignment.get('staff_id')}")
        
        # Verifica se a escola existe
        school = await db.schools.find_one({"id": assignment.get('school_id')})
        if not school:
            issues.append(f"Escola não encontrada: {assignment.get('school_id')}")
        
        # Verifica se a turma existe
        class_doc = await db.classes.find_one({"id": assignment.get('class_id')})
        if not class_doc:
            issues.append(f"Turma não encontrada: {assignment.get('class_id')}")
        
        # Verifica se o componente existe
        if assignment.get('course_id'):
            course = await db.courses.find_one({"id": assignment.get('course_id')})
            if not course:
                issues.append(f"Componente não encontrado: {assignment.get('course_id')}")
        
        if issues:
            orphans.append({
                'id': assignment.get('id'),
                'type': 'teacher_assignment',
                'issues': issues,
                'data': assignment
            })
    
    return orphans


async def find_orphan_attendance(db):
    """Encontra frequências com referências inválidas"""
    orphans = []
    
    attendances = await db.attendance.find({}, {"_id": 0}).to_list(50000)
    
    for attendance in attendances:
        issues = []
        
        # Verifica se a turma existe
        class_doc = await db.classes.find_one({"id": attendance.get('class_id')})
        if not class_doc:
            issues.append(f"Turma não encontrada: {attendance.get('class_id')}")
        
        # Verifica se os alunos nos registros existem
        records = attendance.get('records', [])
        missing_students = 0
        for record in records:
            student = await db.students.find_one({"id": record.get('student_id')})
            if not student:
                missing_students += 1
        
        if missing_students > 0:
            issues.append(f"{missing_students} aluno(s) não encontrado(s) nos registros")
        
        if issues:
            orphans.append({
                'id': attendance.get('id'),
                'type': 'attendance',
                'issues': issues,
                'data': {'class_id': attendance.get('class_id'), 'date': attendance.get('date'), 'records_count': len(records)}
            })
    
    return orphans


async def delete_orphans(db, orphans: list, dry_run: bool = True):
    """Remove registros órfãos"""
    results = {
        'deleted': 0,
        'errors': 0,
        'details': []
    }
    
    collection_map = {
        'enrollment': 'enrollments',
        'grade': 'grades',
        'school_assignment': 'school_assignments',
        'teacher_assignment': 'teacher_assignments',
        'attendance': 'attendance'
    }
    
    for orphan in orphans:
        collection_name = collection_map.get(orphan['type'])
        if not collection_name:
            continue
        
        try:
            if not dry_run:
                await db[collection_name].delete_one({"id": orphan['id']})
            
            results['deleted'] += 1
            results['details'].append({
                'id': orphan['id'],
                'type': orphan['type'],
                'action': 'deleted' if not dry_run else 'would_delete'
            })
        except Exception as e:
            results['errors'] += 1
            results['details'].append({
                'id': orphan['id'],
                'type': orphan['type'],
                'error': str(e)
            })
    
    return results


async def run_cleanup_report(db):
    """Gera relatório de dados órfãos sem deletar"""
    print("=" * 60)
    print("RELATÓRIO DE DADOS ÓRFÃOS - SIGESC")
    print(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 60)
    
    all_orphans = []
    
    # Matrículas
    print("\n🔍 Verificando matrículas...")
    enrollment_orphans = await find_orphan_enrollments(db)
    all_orphans.extend(enrollment_orphans)
    print(f"   Encontrados: {len(enrollment_orphans)} registros órfãos")
    
    # Notas
    print("\n🔍 Verificando notas...")
    grade_orphans = await find_orphan_grades(db)
    all_orphans.extend(grade_orphans)
    print(f"   Encontrados: {len(grade_orphans)} registros órfãos")
    
    # Lotações
    print("\n🔍 Verificando lotações...")
    school_assignment_orphans = await find_orphan_school_assignments(db)
    all_orphans.extend(school_assignment_orphans)
    print(f"   Encontrados: {len(school_assignment_orphans)} registros órfãos")
    
    # Alocações de professores
    print("\n🔍 Verificando alocações de professores...")
    teacher_assignment_orphans = await find_orphan_teacher_assignments(db)
    all_orphans.extend(teacher_assignment_orphans)
    print(f"   Encontrados: {len(teacher_assignment_orphans)} registros órfãos")
    
    # Frequências
    print("\n🔍 Verificando frequências...")
    attendance_orphans = await find_orphan_attendance(db)
    all_orphans.extend(attendance_orphans)
    print(f"   Encontrados: {len(attendance_orphans)} registros órfãos")
    
    print("\n" + "=" * 60)
    print(f"TOTAL DE REGISTROS ÓRFÃOS: {len(all_orphans)}")
    print("=" * 60)
    
    return all_orphans


async def main():
    """Executa limpeza de dados órfãos"""
    mongo_url = os.environ.get('MONGO_URL')
    db_name = os.environ.get('DB_NAME', 'sigesc_db')
    
    if not mongo_url:
        print("❌ MONGO_URL não configurado!")
        return
    
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    print("Conectado ao banco de dados:", db_name)
    
    # Gera relatório
    orphans = await run_cleanup_report(db)
    
    if orphans:
        print("\n⚠️  Para remover os registros órfãos, execute novamente com --delete")
        print("    python cleanup_orphans.py --delete")
    else:
        print("\n✅ Nenhum registro órfão encontrado!")
    
    client.close()


if __name__ == "__main__":
    import sys
    asyncio.run(main())
