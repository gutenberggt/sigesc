"""
Router de Notas - SIGESC
PATCH 4.x: Rotas de notas extraídas do server.py

Endpoints para gestão de notas incluindo:
- CRUD básico
- Consultas por turma e aluno
- Atualização em lote
- Cálculo automático de médias
"""

from fastapi import APIRouter, HTTPException, status, Request
from typing import Optional, List
from datetime import datetime, timezone
import uuid

from models import Grade, GradeCreate, GradeUpdate
from auth_middleware import AuthMiddleware

router = APIRouter(prefix="/grades", tags=["Notas"])


async def calculate_and_update_grade(db, grade_id: str):
    """Calcula média final e atualiza status da nota"""
    grade = await db.grades.find_one({"id": grade_id}, {"_id": 0})
    if not grade:
        return None
    
    # Coleta notas bimestrais
    notas = []
    for bim in ['b1', 'b2', 'b3', 'b4']:
        nota = grade.get(bim)
        if nota is not None:
            notas.append(float(nota))
    
    # Calcula média se houver notas
    if notas:
        media = sum(notas) / len(notas)
        
        # Considera recuperação semestral
        rec_s1 = grade.get('rec_s1')
        rec_s2 = grade.get('rec_s2')
        
        # Lógica de recuperação semestral
        if rec_s1 is not None and grade.get('b1') is not None and grade.get('b2') is not None:
            media_s1 = (float(grade.get('b1', 0)) + float(grade.get('b2', 0))) / 2
            if float(rec_s1) > media_s1:
                # Recalcula com nota de recuperação
                notas_recalc = [float(rec_s1), float(rec_s1)]
                if grade.get('b3') is not None:
                    notas_recalc.append(float(grade.get('b3')))
                if grade.get('b4') is not None:
                    notas_recalc.append(float(grade.get('b4')))
                media = sum(notas_recalc) / len(notas_recalc)
        
        if rec_s2 is not None and grade.get('b3') is not None and grade.get('b4') is not None:
            media_s2 = (float(grade.get('b3', 0)) + float(grade.get('b4', 0))) / 2
            if float(rec_s2) > media_s2:
                # Recalcula com nota de recuperação
                notas_recalc = []
                if grade.get('b1') is not None:
                    notas_recalc.append(float(grade.get('b1')))
                if grade.get('b2') is not None:
                    notas_recalc.append(float(grade.get('b2')))
                notas_recalc.extend([float(rec_s2), float(rec_s2)])
                media = sum(notas_recalc) / len(notas_recalc)
        
        # Considera recuperação final
        recovery = grade.get('recovery')
        if recovery is not None and media < 6.0:
            media = (media + float(recovery)) / 2
        
        # Determina status
        if len(notas) == 4:  # Todas as notas lançadas
            if media >= 6.0:
                status_nota = 'aprovado'
            elif recovery is not None:
                status_nota = 'aprovado' if media >= 5.0 else 'reprovado'
            else:
                status_nota = 'recuperacao' if media >= 4.0 else 'reprovado'
        else:
            status_nota = 'cursando'
        
        # Atualiza no banco
        await db.grades.update_one(
            {"id": grade_id},
            {"$set": {
                "final_average": round(media, 2),
                "status": status_nota,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        grade['final_average'] = round(media, 2)
        grade['status'] = status_nota
    
    return grade


def setup_grades_router(db, audit_service, verify_academic_year_open_or_raise=None, verify_bimestre_edit_deadline_or_raise=None, sandbox_db=None):
    """Configura o router de notas com as dependências necessárias"""
    
    def get_db_for_user(user: dict):
        """Retorna o banco correto baseado no usuário"""
        if False:  # Sandbox desabilitado
            return sandbox_db
        return db

    @router.get("")
    async def list_grades(
        request: Request, 
        student_id: Optional[str] = None,
        class_id: Optional[str] = None,
        course_id: Optional[str] = None,
        academic_year: Optional[int] = None
    ):
        """Lista notas com filtros opcionais"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        filter_query = {}
        
        if student_id:
            filter_query['student_id'] = student_id
        if class_id:
            filter_query['class_id'] = class_id
        if course_id:
            filter_query['course_id'] = course_id
        if academic_year:
            filter_query['academic_year'] = academic_year
        
        grades = await current_db.grades.find(filter_query, {"_id": 0}).to_list(1000)
        return grades

    @router.get("/by-class/{class_id}/{course_id}")
    async def get_grades_by_class(class_id: str, course_id: str, request: Request, academic_year: Optional[int] = None):
        """Busca todas as notas de uma turma para um componente curricular"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        if not academic_year:
            academic_year = datetime.now().year
        
        # Busca alunos matriculados
        enrollments = await current_db.enrollments.find(
            {"class_id": class_id, "status": "active", "academic_year": academic_year},
            {"_id": 0, "student_id": 1, "enrollment_number": 1}
        ).to_list(1000)
        
        student_ids = [e['student_id'] for e in enrollments]
        enrollment_numbers = {e['student_id']: e.get('enrollment_number') for e in enrollments}
        
        # Busca dados dos alunos (inclui status para verificação de bloqueio)
        students = []
        if student_ids:
            students = await current_db.students.find(
                {"id": {"$in": student_ids}},
                {"_id": 0, "id": 1, "full_name": 1, "enrollment_number": 1, "status": 1, "class_id": 1}
            ).sort("full_name", 1).to_list(1000)
        
        # Busca notas existentes
        grades = await current_db.grades.find(
            {"class_id": class_id, "course_id": course_id, "academic_year": academic_year},
            {"_id": 0}
        ).to_list(1000)
        
        grades_map = {g['student_id']: g for g in grades}
        
        result = []
        for student in students:
            grade = grades_map.get(student['id'], {
                'student_id': student['id'],
                'class_id': class_id,
                'course_id': course_id,
                'academic_year': academic_year,
                'b1': None, 'b2': None, 'b3': None, 'b4': None,
                'rec_s1': None, 'rec_s2': None,
                'recovery': None, 'final_average': None, 'status': 'cursando'
            })
            student_data = {
                'id': student['id'],
                'full_name': student['full_name'],
                'enrollment_number': enrollment_numbers.get(student['id']) or student.get('enrollment_number'),
                # Inclui status do aluno e turma atual para verificação de bloqueio
                'student_status': student.get('status', 'active'),
                'current_class_id': student.get('class_id'),
                'is_transferred_from_class': student.get('class_id') and student.get('class_id') != class_id
            }
            result.append({
                'student': student_data,
                'grade': grade
            })
        
        return result

    @router.get("/by-student/{student_id}")
    async def get_grades_by_student(student_id: str, request: Request, academic_year: Optional[int] = None):
        """Busca todas as notas de um aluno"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        if not academic_year:
            academic_year = datetime.now().year
        
        student = await current_db.students.find_one({"id": student_id}, {"_id": 0})
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        
        grades = await current_db.grades.find(
            {"student_id": student_id, "academic_year": academic_year},
            {"_id": 0}
        ).to_list(100)
        
        # Enriquece com nome do componente
        course_ids = list(set(g['course_id'] for g in grades))
        courses = await current_db.courses.find({"id": {"$in": course_ids}}, {"_id": 0}).to_list(100)
        courses_map = {c['id']: c for c in courses}
        
        for grade in grades:
            course = courses_map.get(grade['course_id'], {})
            grade['course_name'] = course.get('name', 'N/A')
        
        return {
            'student': student,
            'grades': grades,
            'academic_year': academic_year
        }

    @router.post("", response_model=Grade)
    async def create_grade(grade_data: GradeCreate, request: Request):
        """Cria ou atualiza nota de um aluno"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario', 'professor', 'coordenador'])(request)
        current_db = get_db_for_user(current_user)
        
        existing = await current_db.grades.find_one({
            "student_id": grade_data.student_id,
            "class_id": grade_data.class_id,
            "course_id": grade_data.course_id,
            "academic_year": grade_data.academic_year
        }, {"_id": 0})
        
        if existing:
            update_data = grade_data.model_dump(exclude_unset=True, exclude={'student_id', 'class_id', 'course_id', 'academic_year'})
            update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
            
            await current_db.grades.update_one(
                {"id": existing['id']},
                {"$set": update_data}
            )
            
            updated = await calculate_and_update_grade(current_db, existing['id'])
            return Grade(**updated)
        
        grade_dict = grade_data.model_dump()
        grade_dict['id'] = str(uuid.uuid4())
        grade_dict['created_at'] = datetime.now(timezone.utc).isoformat()
        grade_dict['final_average'] = None
        grade_dict['status'] = 'cursando'
        
        await current_db.grades.insert_one(grade_dict)
        
        if any([grade_data.b1, grade_data.b2, grade_data.b3, grade_data.b4]):
            updated = await calculate_and_update_grade(current_db, grade_dict['id'])
            return Grade(**updated)
        
        return Grade(**grade_dict)

    @router.put("/{grade_id}", response_model=Grade)
    async def update_grade(grade_id: str, grade_update: GradeUpdate, request: Request):
        """Atualiza notas de um aluno"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario', 'professor', 'coordenador'])(request)
        current_db = get_db_for_user(current_user)
        
        grade = await current_db.grades.find_one({"id": grade_id}, {"_id": 0})
        if not grade:
            raise HTTPException(status_code=404, detail="Nota não encontrada")
        
        update_data = grade_update.model_dump(exclude_unset=True)
        update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
        
        await current_db.grades.update_one(
            {"id": grade_id},
            {"$set": update_data}
        )
        
        updated = await calculate_and_update_grade(current_db, grade_id)
        return Grade(**updated)

    @router.post("/batch")
    async def update_grades_batch(request: Request, grades: List[dict]):
        """Atualiza notas em lote (por turma)"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario', 'professor', 'coordenador'])(request)
        current_db = get_db_for_user(current_user)
        user_role = current_user.get('role', '')
        
        # Verifica ano letivo aberto (para não-admins)
        if grades and user_role not in ['admin', 'admin_teste'] and verify_academic_year_open_or_raise:
            first_grade = grades[0]
            class_doc = await current_db.classes.find_one(
                {"id": first_grade['class_id']},
                {"_id": 0, "school_id": 1}
            )
            if class_doc:
                await verify_academic_year_open_or_raise(
                    class_doc['school_id'],
                    first_grade['academic_year']
                )
        
        # Verifica deadline do bimestre
        if grades and user_role not in ['admin', 'admin_teste', 'secretario'] and verify_bimestre_edit_deadline_or_raise:
            first_grade = grades[0]
            academic_year = first_grade.get('academic_year')
            
            bimestres_editados = set()
            for grade_data in grades:
                for bim in ['b1', 'b2', 'b3', 'b4']:
                    if grade_data.get(bim) is not None:
                        bimestres_editados.add(int(bim[1]))
            
            for bimestre in bimestres_editados:
                await verify_bimestre_edit_deadline_or_raise(academic_year, bimestre, user_role)
        
        results = []
        audit_changes = []
        
        for grade_data in grades:
            existing = await current_db.grades.find_one({
                "student_id": grade_data['student_id'],
                "class_id": grade_data['class_id'],
                "course_id": grade_data['course_id'],
                "academic_year": grade_data['academic_year']
            }, {"_id": 0})
            
            if existing:
                update_fields = {k: v for k, v in grade_data.items() 
                              if k in ['b1', 'b2', 'b3', 'b4', 'rec_s1', 'rec_s2', 'recovery', 'observations'] and v is not None}
                update_fields['updated_at'] = datetime.now(timezone.utc).isoformat()
                
                old_values = {k: existing.get(k) for k in update_fields.keys() if k != 'updated_at'}
                new_values = {k: v for k, v in update_fields.items() if k != 'updated_at'}
                
                await current_db.grades.update_one(
                    {"id": existing['id']},
                    {"$set": update_fields}
                )
                
                updated = await calculate_and_update_grade(current_db, existing['id'])
                results.append(updated)
                
                if old_values != new_values:
                    audit_changes.append({
                        'student_id': grade_data['student_id'],
                        'grade_id': existing['id'],
                        'old': old_values,
                        'new': new_values
                    })
            else:
                new_grade = {
                    'id': str(uuid.uuid4()),
                    'student_id': grade_data['student_id'],
                    'class_id': grade_data['class_id'],
                    'course_id': grade_data['course_id'],
                    'academic_year': grade_data['academic_year'],
                    'b1': grade_data.get('b1'),
                    'b2': grade_data.get('b2'),
                    'b3': grade_data.get('b3'),
                    'b4': grade_data.get('b4'),
                    'rec_s1': grade_data.get('rec_s1'),
                    'rec_s2': grade_data.get('rec_s2'),
                    'recovery': grade_data.get('recovery'),
                    'observations': grade_data.get('observations'),
                    'final_average': None,
                    'status': 'cursando',
                    'created_at': datetime.now(timezone.utc).isoformat()
                }
                
                await current_db.grades.insert_one(new_grade)
                updated = await calculate_and_update_grade(current_db, new_grade['id'])
                results.append(updated)
                
                audit_changes.append({
                    'student_id': grade_data['student_id'],
                    'grade_id': new_grade['id'],
                    'action': 'create',
                    'new': {k: v for k, v in new_grade.items() if k in ['b1', 'b2', 'b3', 'b4', 'rec_s1', 'rec_s2']}
                })
        
        # Auditoria em lote
        if audit_changes:
            class_info = None
            school_id = None
            if grades:
                class_info = await current_db.classes.find_one(
                    {"id": grades[0].get('class_id')},
                    {"_id": 0, "name": 1, "school_id": 1}
                )
                school_id = class_info.get('school_id') if class_info else None
            
            await audit_service.log(
                action='update',
                collection='grades',
                user=current_user,
                request=request,
                description=f"Atualizou notas de {len(audit_changes)} aluno(s) da turma {class_info.get('name', 'N/A') if class_info else 'N/A'}",
                school_id=school_id,
                academic_year=grades[0].get('academic_year') if grades else None,
                extra_data={'changes': audit_changes[:10]}
            )
        
        return {"updated": len(results), "grades": results}

    @router.delete("/{grade_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_grade(grade_id: str, request: Request):
        """Remove uma nota"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste'])(request)
        current_db = get_db_for_user(current_user)
        
        result = await current_db.grades.delete_one({"id": grade_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Nota não encontrada")
        
        return None

    return router
