"""
Router para Frequência Estendida.
Extraído automaticamente de server.py.
"""

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from typing import Optional
from datetime import datetime, timedelta
import logging

from models import *
from auth_middleware import AuthMiddleware
from pdf_generator import generate_relatorio_frequencia_bimestre_pdf

logger = logging.getLogger(__name__)


router = APIRouter(tags=["Frequência Estendida"])


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências."""
    
    # Helper para obter DB correto (produção ou sandbox)
    def get_db_for_user(user: dict):
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db



    @router.get("/attendance/frequency/student/{student_id}")
    async def get_student_frequency_for_social(
        student_id: str,
        request: Request,
        academic_year: Optional[int] = None
    ):
        """
        Calcula a frequência do aluno usando a fórmula:
        ((Dias Letivos até hoje - Faltas) / Dias Letivos até hoje) × 100

        Este endpoint é usado pela Assistência Social.
        """
        await AuthMiddleware.get_current_user(request)

        if not academic_year:
            academic_year = datetime.now().year

        # Busca dados do aluno
        student = await db.students.find_one({"id": student_id}, {"_id": 0})
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        # Busca a turma do aluno (pode vir da matrícula ativa ou do campo class_id)
        class_id = student.get('class_id')

        # Tenta buscar pela matrícula ativa se não tiver class_id
        if not class_id:
            enrollment = await db.enrollments.find_one(
                {"student_id": student_id, "status": "active", "academic_year": academic_year},
                {"_id": 0, "class_id": 1}
            )
            if enrollment:
                class_id = enrollment.get('class_id')

        # Data de início do ano letivo (padrão: 1 de fevereiro)
        year_start = f"{academic_year}-02-01"
        today = datetime.now().strftime("%Y-%m-%d")

        # Busca eventos do calendário que NÃO são dias letivos (feriados, recessos, etc.)
        non_school_events = await db.calendar_events.find({
            "academic_year": academic_year,
            "is_school_day": False,
            "start_date": {"$lte": today}
        }, {"_id": 0, "start_date": 1, "end_date": 1}).to_list(1000)

        # Busca sábados letivos
        saturday_school_events = await db.calendar_events.find({
            "academic_year": academic_year,
            "event_type": "sabado_letivo",
            "start_date": {"$lte": today}
        }, {"_id": 0, "start_date": 1, "end_date": 1}).to_list(1000)

        # Calcula dias letivos até hoje
        from datetime import timedelta

        start_date = datetime.strptime(max(year_start, f"{academic_year}-02-01"), "%Y-%m-%d")
        end_date = datetime.strptime(today, "%Y-%m-%d")

        # Conta dias úteis (seg-sex) de start_date até end_date
        school_days = 0
        current_date = start_date

        # Cria conjunto de datas não letivas
        non_school_dates = set()
        for event in non_school_events:
            event_start = datetime.strptime(event['start_date'], "%Y-%m-%d")
            event_end = datetime.strptime(event['end_date'], "%Y-%m-%d")
            delta = event_end - event_start
            for i in range(delta.days + 1):
                non_school_dates.add((event_start + timedelta(days=i)).strftime("%Y-%m-%d"))

        # Cria conjunto de sábados letivos
        saturday_school_dates = set()
        for event in saturday_school_events:
            event_start = datetime.strptime(event['start_date'], "%Y-%m-%d")
            event_end = datetime.strptime(event['end_date'], "%Y-%m-%d")
            delta = event_end - event_start
            for i in range(delta.days + 1):
                saturday_school_dates.add((event_start + timedelta(days=i)).strftime("%Y-%m-%d"))

        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            weekday = current_date.weekday()  # 0=segunda, 6=domingo

            # Verifica se é dia letivo
            if weekday < 5:  # Segunda a sexta
                if date_str not in non_school_dates:
                    school_days += 1
            elif weekday == 5:  # Sábado
                if date_str in saturday_school_dates:
                    school_days += 1
            # Domingo nunca é letivo

            current_date += timedelta(days=1)

        # Busca todas as faltas do aluno no ano até hoje
        attendances = await db.attendance.find(
            {
                "academic_year": academic_year,
                "records.student_id": student_id,
                "date": {"$lte": today}
            },
            {"_id": 0, "date": 1, "records": 1}
        ).to_list(1000)

        # Conta faltas (status 'F')
        absences = 0
        presences = 0
        justified = 0

        for att in attendances:
            for record in att.get('records', []):
                if record['student_id'] == student_id:
                    if record['status'] == 'F':
                        absences += 1
                    elif record['status'] == 'P':
                        presences += 1
                    elif record['status'] == 'J':
                        justified += 1

        # Calcula porcentagem usando a fórmula:
        # ((Dias Letivos até hoje - Faltas) / Dias Letivos até hoje) × 100
        if school_days > 0:
            attendance_percentage = ((school_days - absences) / school_days) * 100
        else:
            attendance_percentage = 100.0  # Se não há dias letivos, considera 100%

        # Garante que não seja negativo
        attendance_percentage = max(0, attendance_percentage)

        return {
            "student_id": student_id,
            "student_name": student.get('full_name'),
            "academic_year": academic_year,
            "class_id": class_id,
            "calculation_date": today,
            "summary": {
                "school_days_until_today": school_days,
                "absences": absences,
                "presences": presences,
                "justified": justified,
                "attendance_percentage": round(attendance_percentage, 1),
                "status": "regular" if attendance_percentage >= 75 else "alerta"
            },
            "formula": f"(({school_days} - {absences}) / {school_days}) × 100 = {round(attendance_percentage, 1)}%"
        }


    @router.get("/attendance/pdf/bimestre/{class_id}")
    async def get_attendance_bimestre_pdf(
        class_id: str,
        request: Request,
        bimestre: int = Query(..., ge=1, le=4, description="Número do bimestre (1-4)"),
        academic_year: Optional[int] = None
    ):
        """Gera PDF do relatório de frequência por bimestre"""
        await AuthMiddleware.get_current_user(request)

        if not academic_year:
            academic_year = datetime.now().year

        # Busca dados da turma
        turma = await db.classes.find_one({"id": class_id}, {"_id": 0})
        if not turma:
            raise HTTPException(status_code=404, detail="Turma não encontrada")

        # Busca escola
        school = await db.schools.find_one({"id": turma.get('school_id')}, {"_id": 0})
        if not school:
            raise HTTPException(status_code=404, detail="Escola não encontrada")

        # Buscar mantenedora
        mantenedora = await db.config.find_one({"tipo": "mantenedora"}, {"_id": 0})

        # Definir período do bimestre
        bimestre_periodos = {
            1: (f"{academic_year}-02-01", f"{academic_year}-04-30"),
            2: (f"{academic_year}-05-01", f"{academic_year}-07-15"),
            3: (f"{academic_year}-07-16", f"{academic_year}-09-30"),
            4: (f"{academic_year}-10-01", f"{academic_year}-12-20"),
        }

        period_start, period_end = bimestre_periodos.get(bimestre, (None, None))

        # Busca alunos matriculados na turma
        enrollments = await db.enrollments.find(
            {"class_id": class_id, "status": "active", "academic_year": academic_year},
            {"_id": 0, "student_id": 1, "enrollment_number": 1}
        ).to_list(1000)

        student_ids = [e['student_id'] for e in enrollments]
        enrollment_numbers = {e['student_id']: e.get('enrollment_number') for e in enrollments}

        # Busca dados dos alunos
        students = []
        if student_ids:
            students = await db.students.find(
                {"id": {"$in": student_ids}},
                {"_id": 0, "id": 1, "full_name": 1, "enrollment_number": 1}
            ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).to_list(1000)

        # Busca frequências do período do bimestre
        attendances = await db.attendance.find(
            {
                "class_id": class_id,
                "academic_year": academic_year,
                "date": {"$gte": period_start, "$lte": period_end}
            },
            {"_id": 0}
        ).sort("date", 1).to_list(1000)

        # Coletar dias únicos com frequência registrada
        attendance_days = sorted(list(set([att['date'] for att in attendances])))

        # Montar dados de frequência por aluno
        students_attendance = []
        for student in students:
            attendance_by_date = {}

            for att in attendances:
                for record in att.get('records', []):
                    if record['student_id'] == student['id']:
                        status_map = {'P': 'present', 'F': 'absent', 'J': 'justified'}
                        attendance_by_date[att['date']] = status_map.get(record['status'], '')

            students_attendance.append({
                'name': student['full_name'],
                'enrollment_number': enrollment_numbers.get(student['id']) or student.get('enrollment_number'),
                'attendance_by_date': attendance_by_date
            })

        # Buscar professor responsável (opcional)
        teacher_name = ""
        teacher_assignment = await db.teacher_assignments.find_one(
            {"class_id": class_id, "academic_year": academic_year},
            {"_id": 0, "staff_id": 1}
        )
        if teacher_assignment:
            teacher = await db.staff.find_one(
                {"id": teacher_assignment['staff_id']},
                {"_id": 0, "nome": 1}
            )
            if teacher:
                teacher_name = teacher.get('nome', '')

        # Gerar PDF
        try:
            pdf_buffer = generate_relatorio_frequencia_bimestre_pdf(
                school=school,
                class_info=turma,
                course_info=None,  # Frequência diária
                students_attendance=students_attendance,
                bimestre=bimestre,
                academic_year=academic_year,
                period_start=period_start,
                period_end=period_end,
                attendance_days=attendance_days,
                aulas_previstas=len(attendance_days),
                aulas_ministradas=len(attendance_days),
                teacher_name=teacher_name,
                mantenedora=mantenedora
            )

            filename = f"frequencia_{turma.get('name', 'turma')}_{bimestre}bim_{academic_year}.pdf"
            filename = filename.replace(' ', '_').replace('/', '-')

            return StreamingResponse(
                pdf_buffer,
                media_type="application/pdf",
                headers={"Content-Disposition": f"inline; filename={filename}"}
            )
        except Exception as e:
            logger.error(f"Erro ao gerar PDF de frequência: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")


    @router.get("/attendance/alerts")
    async def get_attendance_alerts(
        request: Request,
        school_id: Optional[str] = None,
        academic_year: Optional[int] = None
    ):
        """Lista alunos com frequência abaixo de 75%"""
        current_user = await AuthMiddleware.get_current_user(request)

        if not academic_year:
            academic_year = datetime.now().year

        # Busca todas as turmas (opcionalmente filtrada por escola)
        class_query = {}
        if school_id:
            class_query["school_id"] = school_id

        # Se for professor, limitar às turmas vinculadas via teacher_assignments
        if current_user.get('role') == 'professor':
            staff = await db.staff.find_one({"user_id": current_user['id']}, {"_id": 0, "id": 1})
            if staff:
                assignments = await db.teacher_assignments.find(
                    {"staff_id": staff['id'], "status": "ativo", "academic_year": academic_year},
                    {"_id": 0, "class_id": 1}
                ).to_list(1000)
                linked_class_ids = list(set(a['class_id'] for a in assignments))
                class_query["id"] = {"$in": linked_class_ids}
            else:
                return {"academic_year": academic_year, "total_alerts": 0, "alerts": []}

        classes = await db.classes.find(class_query, {"_id": 0}).to_list(1000)

        all_alerts = []

        for turma in classes:
            # Busca alunos matriculados na turma através da coleção enrollments
            enrollments = await db.enrollments.find(
                {"class_id": turma['id'], "status": "active", "academic_year": academic_year},
                {"_id": 0, "student_id": 1}
            ).to_list(1000)

            student_ids = [e['student_id'] for e in enrollments]

            # Busca dados dos alunos matriculados
            students = []
            if student_ids:
                students = await db.students.find(
                    {"id": {"$in": student_ids}},
                    {"_id": 0, "id": 1, "full_name": 1}
                ).to_list(1000)

            # Busca frequências da turma
            attendances = await db.attendance.find(
                {"class_id": turma['id'], "academic_year": academic_year},
                {"_id": 0}
            ).to_list(1000)

            for student in students:
                present = 0
                absent = 0
                justified = 0

                for att in attendances:
                    for record in att.get('records', []):
                        if record['student_id'] == student['id']:
                            if record['status'] == 'P':
                                present += 1
                            elif record['status'] == 'F':
                                absent += 1
                            elif record['status'] == 'J':
                                justified += 1

                total = present + absent + justified
                if total > 0:
                    percentage = ((present + justified) / total * 100)

                    if percentage < 75:
                        all_alerts.append({
                            "student_id": student['id'],
                            "student_name": student['full_name'],
                            "class_id": turma['id'],
                            "class_name": turma.get('name'),
                            "school_id": turma.get('school_id'),
                            "attendance_percentage": round(percentage, 1),
                            "total_records": total,
                            "absent": absent
                        })

        # Ordena por percentual de frequência (menor primeiro)
        all_alerts.sort(key=lambda x: x['attendance_percentage'])

        return {
            "academic_year": academic_year,
            "total_alerts": len(all_alerts),
            "alerts": all_alerts
        }



    return router
