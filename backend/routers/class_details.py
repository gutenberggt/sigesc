"""
Router para Detalhes de Turma.
Extraído automaticamente de server.py.
"""

from fastapi import APIRouter, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from datetime import datetime
import logging

from models import *
from auth_middleware import AuthMiddleware
from pdf_generator import generate_class_details_pdf

logger = logging.getLogger(__name__)


router = APIRouter(tags=["Detalhes de Turma"])


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências."""
    
    # Helper para obter DB correto (produção ou sandbox)
    def get_db_for_user(user: dict):
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db



    @router.get("/classes/{class_id}/details")
    async def get_class_details(class_id: str, request: Request):
        """
        Busca detalhes completos da turma incluindo:
        - Dados cadastrais da turma
        - Escola
        - Professor(es) alocado(s)
        - Lista de alunos matriculados com responsáveis
        """
        current_user = await AuthMiddleware.get_current_user(request)

        # Busca turma
        class_doc = await db.classes.find_one({"id": class_id}, {"_id": 0})
        if not class_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Turma não encontrada"
            )

        # Busca escola
        school = await db.schools.find_one({"id": class_doc.get('school_id')}, {"_id": 0, "id": 1, "name": 1})

        # Busca professores alocados na turma
        alocacoes = await db.teacher_assignments.find(
            {"class_id": class_id},
            {"_id": 0}
        ).to_list(100)

        # Agrupa por professor para evitar duplicação
        teachers_map = {}
        for alocacao in alocacoes:
            staff_id = alocacao.get('staff_id')
            if staff_id not in teachers_map:
                staff = await db.staff.find_one(
                    {"id": staff_id},
                    {"_id": 0, "id": 1, "nome": 1, "full_name": 1, "email": 1, "celular": 1}
                )
                if staff:
                    teachers_map[staff_id] = {
                        "staff_id": staff.get('id'),
                        "nome": staff.get('nome') or staff.get('full_name'),
                        "email": staff.get('email'),
                        "celular": staff.get('celular'),
                        "componentes": []
                    }

            # Adiciona componente se existir
            if staff_id in teachers_map and alocacao.get('course_id'):
                course = await db.courses.find_one(
                    {"id": alocacao.get('course_id')},
                    {"_id": 0, "id": 1, "name": 1, "nome": 1}
                )
                if course:
                    comp_name = course.get('name') or course.get('nome')
                    if comp_name and comp_name not in teachers_map[staff_id]["componentes"]:
                        teachers_map[staff_id]["componentes"].append(comp_name)

        # Formata lista de professores
        teachers = []
        for teacher_data in teachers_map.values():
            componentes = teacher_data.pop("componentes", [])
            teacher_data["componente"] = ", ".join(componentes) if componentes else None
            teachers.append(teacher_data)

        # Busca alunos matriculados - usando múltiplas fontes para maior robustez
        academic_year = class_doc.get('academic_year', datetime.now().year)

        # Estratégia 1: Busca na coleção enrollments (matrícula formal)
        enrollments = await db.enrollments.find(
            {"class_id": class_id, "status": "active"},
            {"_id": 0, "student_id": 1, "enrollment_number": 1, "student_series": 1, "academic_year": 1}
        ).to_list(1000)

        enrollment_map = {}
        enrollment_student_ids = set()
        for e in enrollments:
            student_id = e.get('student_id')
            enrollment_student_ids.add(student_id)
            if student_id not in enrollment_map or e.get('academic_year') == academic_year:
                enrollment_map[student_id] = {
                    'enrollment_number': e.get('enrollment_number'),
                    'student_series': e.get('student_series')
                }

        # Busca alunos inativos que JÁ ESTIVERAM nesta turma
        inactive_enrollments = await db.enrollments.find(
            {"class_id": class_id, "status": {"$in": ["transferred", "dropout", "cancelled", "relocated", "progressed"]}},
            {"_id": 0, "student_id": 1, "enrollment_number": 1, "student_series": 1, "academic_year": 1}
        ).to_list(1000)

        inactive_student_ids = set()
        for e in inactive_enrollments:
            sid = e.get('student_id')
            if sid not in enrollment_student_ids:
                inactive_student_ids.add(sid)
                if sid not in enrollment_map or e.get('academic_year') == academic_year:
                    enrollment_map[sid] = {
                        'enrollment_number': e.get('enrollment_number'),
                        'student_series': e.get('student_series')
                    }

        # Estratégia 2: Busca alunos diretamente com class_id (fallback para dados antigos/inconsistentes)
        direct_students = await db.students.find(
            {"class_id": class_id, "status": {"$in": ["active", "Ativo"]}},
            {"_id": 0, "id": 1}
        ).to_list(1000)
        direct_student_ids = {s.get('id') for s in direct_students}

        # Combina todas as fontes (união de IDs)
        all_student_ids = list(enrollment_student_ids.union(direct_student_ids).union(inactive_student_ids))

        # Busca ação mais recente para alunos inativos
        action_info_map = {}
        if inactive_student_ids:
            action_type_map = {
                'transferencia_saida': 'Transferido',
                'remanejamento': 'Remanejado',
                'progressao': 'Progredido',
                'desistencia': 'Desistente',
                'cancelamento': 'Cancelado'
            }
            history_entries = await db.student_history.find(
                {
                    "student_id": {"$in": list(inactive_student_ids)},
                    "class_id": class_id,
                    "action_type": {"$in": list(action_type_map.keys())}
                },
                {"_id": 0, "student_id": 1, "action_type": 1, "action_date": 1}
            ).sort("action_date", -1).to_list(1000)

            for h in history_entries:
                sid = h.get('student_id')
                if sid not in action_info_map:
                    action_info_map[sid] = {
                        "action_label": action_type_map.get(h.get('action_type'), ''),
                        "action_date": h.get('action_date', '')
                    }

        students_list = []
        if all_student_ids:
            students = await db.students.find(
                {"id": {"$in": all_student_ids}},
                {"_id": 0, "id": 1, "full_name": 1, "birth_date": 1, "guardian_name": 1, "guardian_phone": 1, "guardian_relationship": 1, "mother_name": 1, "mother_phone": 1, "father_name": 1, "father_phone": 1, "enrollment_number": 1}
            ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).to_list(1000)

            for student in students:
                # Determina responsável principal
                guardian_name = student.get('guardian_name') or student.get('mother_name') or student.get('father_name') or '-'
                guardian_phone = student.get('guardian_phone') or student.get('mother_phone') or student.get('father_phone') or ''

                # Busca info de matrícula (da coleção enrollments ou do próprio aluno)
                enrollment_info = enrollment_map.get(student.get('id'), {})
                enrollment_number = enrollment_info.get('enrollment_number') or student.get('enrollment_number')

                students_list.append({
                    "id": student.get('id'),
                    "full_name": student.get('full_name'),
                    "enrollment_number": enrollment_number,
                    "student_series": enrollment_info.get('student_series') or class_doc.get('grade_level'),
                    "birth_date": student.get('birth_date'),
                    "guardian_name": guardian_name,
                    "guardian_phone": guardian_phone,
                    "action_label": action_info_map.get(student.get('id'), {}).get('action_label', ''),
                    "action_date": action_info_map.get(student.get('id'), {}).get('action_date', '')
                })

        # Calcula contagem por série para turmas multisseriadas
        series_count = {}
        if class_doc.get('is_multi_grade') and class_doc.get('series'):
            for serie in class_doc.get('series', []):
                series_count[serie] = 0
            # Comparação case-insensitive para lidar com variações de maiúsculas/minúsculas
            series_lower_map = {s.lower(): s for s in series_count.keys()}
            for student in students_list:
                serie = student.get('student_series')
                if serie:
                    # Tenta correspondência exata primeiro, depois case-insensitive
                    if serie in series_count:
                        series_count[serie] += 1
                    elif serie.lower() in series_lower_map:
                        series_count[series_lower_map[serie.lower()]] += 1

        return {
            "class": class_doc,
            "school": school,
            "teachers": teachers,
            "students": students_list,
            "total_students": len(students_list),
            "series_count": series_count if series_count else None
        }


    @router.get("/classes/{class_id}/details/pdf")
    async def get_class_details_pdf(class_id: str, request: Request):
        """
        Gera PDF com detalhes completos da turma
        """
        current_user = await AuthMiddleware.get_current_user(request)

        # Busca turma
        class_doc = await db.classes.find_one({"id": class_id}, {"_id": 0})
        if not class_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Turma não encontrada"
            )

        # Busca escola
        school = await db.schools.find_one({"id": class_doc.get('school_id')}, {"_id": 0})
        if not school:
            school = {"name": "Escola Municipal"}

        # Busca mantenedora
        mantenedora = await db.mantenedora.find_one({}, {"_id": 0})

        # Busca professores alocados na turma
        alocacoes = await db.teacher_assignments.find(
            {"class_id": class_id},
            {"_id": 0}
        ).to_list(100)

        # Agrupa por professor para evitar duplicação
        teachers_map = {}
        for alocacao in alocacoes:
            staff_id = alocacao.get('staff_id')
            if staff_id not in teachers_map:
                staff = await db.staff.find_one(
                    {"id": staff_id},
                    {"_id": 0, "id": 1, "nome": 1, "full_name": 1, "celular": 1}
                )
                if staff:
                    teachers_map[staff_id] = {
                        "nome": staff.get('nome') or staff.get('full_name'),
                        "celular": staff.get('celular'),
                        "componentes": []
                    }

            # Adiciona componente se existir
            if staff_id in teachers_map and alocacao.get('course_id'):
                course = await db.courses.find_one(
                    {"id": alocacao.get('course_id')},
                    {"_id": 0, "name": 1, "nome": 1}
                )
                if course:
                    comp_name = course.get('name') or course.get('nome')
                    if comp_name and comp_name not in teachers_map[staff_id]["componentes"]:
                        teachers_map[staff_id]["componentes"].append(comp_name)

        # Formata lista de professores
        teachers = []
        for teacher_data in teachers_map.values():
            componentes = teacher_data.pop("componentes", [])
            teacher_data["componente"] = ", ".join(componentes) if componentes else None
            teachers.append(teacher_data)

        # Busca alunos matriculados - usando múltiplas fontes para maior robustez
        academic_year = class_doc.get('academic_year', datetime.now().year)

        # Estratégia 1: Busca na coleção enrollments (matrícula formal)
        enrollments = await db.enrollments.find(
            {"class_id": class_id, "status": "active"},
            {"_id": 0, "student_id": 1, "academic_year": 1}
        ).to_list(1000)

        enrollment_student_ids = set()
        for e in enrollments:
            enrollment_student_ids.add(e.get('student_id'))

        # Estratégia 2: Busca alunos diretamente com class_id (fallback para dados antigos/inconsistentes)
        direct_students = await db.students.find(
            {"class_id": class_id, "status": {"$in": ["active", "Ativo"]}},
            {"_id": 0, "id": 1}
        ).to_list(1000)
        direct_student_ids = {s.get('id') for s in direct_students}

        # Combina ambas as fontes (união de IDs)
        all_student_ids = list(enrollment_student_ids.union(direct_student_ids))

        students_list = []
        if all_student_ids:
            students = await db.students.find(
                {"id": {"$in": all_student_ids}},
                {"_id": 0, "id": 1, "full_name": 1, "birth_date": 1, "guardian_name": 1, "guardian_phone": 1, "mother_name": 1, "mother_phone": 1, "father_name": 1, "father_phone": 1}
            ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).to_list(1000)

            for student in students:
                guardian_name = student.get('guardian_name') or student.get('mother_name') or student.get('father_name') or '-'
                guardian_phone = student.get('guardian_phone') or student.get('mother_phone') or student.get('father_phone') or ''

                students_list.append({
                    "full_name": student.get('full_name'),
                    "birth_date": student.get('birth_date'),
                    "guardian_name": guardian_name,
                    "guardian_phone": guardian_phone
                })

        try:
            pdf_buffer = generate_class_details_pdf(
                class_info=class_doc,
                school=school,
                teachers=teachers,
                students=students_list,
                mantenedora=mantenedora
            )

            class_name = class_doc.get('name', 'turma').replace(' ', '_')
            filename = f"Detalhes_Turma_{class_name}_{academic_year}.pdf"

            return StreamingResponse(
                pdf_buffer,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'inline; filename="{filename}"'
                }
            )
        except Exception as e:
            logger.error(f"Erro ao gerar PDF de detalhes da turma: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")

    # ============= COURSE (COMPONENTE CURRICULAR) ROUTES - MOVIDO PARA routers/courses.py =============

    # ============= CPF VALIDATION ENDPOINTS =============


    # ============= STUDENT (ALUNO) ROUTES =============

    ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.pdf', '.doc', '.docx'}
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

    # PATCH 1.3: Rota de upload restrita a roles autorizados



    return router
