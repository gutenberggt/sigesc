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
        academic_year: Optional[int] = None,
        course_id: Optional[str] = Query(None, description="ID do componente curricular")
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

        # Buscar mantenedora (coleção correta)
        mantenedora = await db.mantenedora.find_one({}, {"_id": 0})

        # Buscar calendário letivo para datas reais dos bimestres e cálculo de dias previstos
        calendario = await db.calendario_letivo.find_one(
            {"ano_letivo": academic_year, "school_id": None}, {"_id": 0}
        )
        if not calendario:
            calendario = await db.calendario_letivo.find_one(
                {"ano_letivo": academic_year}, {"_id": 0}
            )

        # Definir período do bimestre a partir do calendário ou fallback
        bimestre_key_inicio = f"bimestre_{bimestre}_inicio"
        bimestre_key_fim = f"bimestre_{bimestre}_fim"

        if calendario and calendario.get(bimestre_key_inicio) and calendario.get(bimestre_key_fim):
            period_start = str(calendario[bimestre_key_inicio])[:10]
            period_end = str(calendario[bimestre_key_fim])[:10]
        else:
            bimestre_periodos = {
                1: (f"{academic_year}-02-01", f"{academic_year}-04-30"),
                2: (f"{academic_year}-05-01", f"{academic_year}-07-15"),
                3: (f"{academic_year}-07-16", f"{academic_year}-09-30"),
                4: (f"{academic_year}-10-01", f"{academic_year}-12-20"),
            }
            period_start, period_end = bimestre_periodos.get(bimestre, (None, None))

        # Calcular aulas previstas para o bimestre (dias letivos no período)
        aulas_previstas_bimestre = 0
        if calendario:
            eventos_nao_letivos = ['feriado_nacional', 'feriado_estadual', 'feriado_municipal', 'recesso_escolar']
            events = await db.calendar_events.find(
                {"academic_year": academic_year}, {"_id": 0}
            ).to_list(1000)

            datas_nao_letivas = set()
            datas_sabados_letivos = set()
            for event in events:
                event_type = event.get('event_type', '')
                start_date_str = event.get('start_date')
                end_date_str = event.get('end_date') or start_date_str
                if not start_date_str:
                    continue
                try:
                    from datetime import date as date_type
                    start_date = datetime.strptime(start_date_str[:10], '%Y-%m-%d').date()
                    end_date = datetime.strptime(end_date_str[:10], '%Y-%m-%d').date()
                    current = start_date
                    while current <= end_date:
                        if event_type in eventos_nao_letivos:
                            datas_nao_letivas.add(current)
                        elif event_type == 'sabado_letivo' or (event.get('is_school_day') and current.weekday() == 5):
                            datas_sabados_letivos.add(current)
                        current += timedelta(days=1)
                except (ValueError, TypeError):
                    continue

            try:
                inicio = datetime.strptime(period_start, '%Y-%m-%d').date()
                fim = datetime.strptime(period_end, '%Y-%m-%d').date()
                current = inicio
                while current <= fim:
                    if current in datas_sabados_letivos:
                        aulas_previstas_bimestre += 1
                    elif current.weekday() < 5 and current not in datas_nao_letivas:
                        aulas_previstas_bimestre += 1
                    current += timedelta(days=1)
            except (ValueError, TypeError):
                pass

        # Busca alunos matriculados - mesma lógica robusta do endpoint de frequência
        # Fonte 1: Matrículas ativas
        enrollments_active = await db.enrollments.find(
            {"class_id": class_id, "status": "active"},
            {"_id": 0, "student_id": 1, "enrollment_number": 1, "academic_year": 1}
        ).to_list(1000)

        enrollment_student_ids = set()
        enrollment_numbers = {}
        for e in enrollments_active:
            sid = e.get('student_id')
            enrollment_student_ids.add(sid)
            enrollment_numbers[sid] = e.get('enrollment_number')

        # Fonte 2: Matrículas inativas (transferidos, desistentes, etc.)
        inactive_enrollments = await db.enrollments.find(
            {"class_id": class_id, "status": {"$in": ["transferred", "dropout", "cancelled", "relocated", "progressed"]}},
            {"_id": 0, "student_id": 1, "enrollment_number": 1}
        ).to_list(1000)

        for e in inactive_enrollments:
            sid = e.get('student_id')
            if sid not in enrollment_student_ids:
                enrollment_student_ids.add(sid)
            if sid not in enrollment_numbers:
                enrollment_numbers[sid] = e.get('enrollment_number')

        # Fonte 3: Alunos com class_id direto (fallback)
        direct_students = await db.students.find(
            {"class_id": class_id, "status": {"$in": ["active", "Ativo"]}},
            {"_id": 0, "id": 1, "enrollment_number": 1}
        ).to_list(1000)

        for s in direct_students:
            sid = s.get('id')
            if sid not in enrollment_student_ids:
                enrollment_student_ids.add(sid)
            if sid not in enrollment_numbers:
                enrollment_numbers[sid] = s.get('enrollment_number')

        student_ids = list(enrollment_student_ids)

        # Busca dados dos alunos
        students = []
        if student_ids:
            students = await db.students.find(
                {"id": {"$in": student_ids}},
                {"_id": 0, "id": 1, "full_name": 1, "enrollment_number": 1}
            ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).to_list(1000)

        # Busca frequências do período do bimestre (filtrando por course_id se informado)
        att_query = {
            "class_id": class_id,
            "academic_year": academic_year,
            "date": {"$gte": period_start, "$lte": period_end}
        }
        if course_id:
            att_query["course_id"] = course_id
        attendances = await db.attendance.find(
            att_query,
            {"_id": 0}
        ).sort("date", 1).to_list(1000)

        # Coletar dias únicos com frequência registrada
        attendance_days = sorted(list(set([att['date'] for att in attendances])))

        # Montar dados de frequência por aluno
        # Para anos finais: cada registro de attendance é 1 aula separada (coluna no PDF)
        # Detectar se estamos no modelo novo (com aula_numero) ou legado
        has_aula_numero = any(att.get('aula_numero') is not None for att in attendances)
        
        if has_aula_numero:
            # Modelo novo: cada registro = 1 aula = 1 coluna no PDF
            # Ordenar por data + aula_numero
            sorted_attendances = sorted(attendances, key=lambda a: (a.get('date', ''), a.get('aula_numero', 1)))
            # attendance_days_expanded: lista de tuplas (date, aula_numero) - cada entrada = 1 coluna
            attendance_days_expanded = [(att['date'], att.get('aula_numero', 1)) for att in sorted_attendances]
            
            students_attendance = []
            for student in students:
                attendance_by_session = {}
                for att in sorted_attendances:
                    key = (att['date'], att.get('aula_numero', 1))
                    for record in att.get('records', []):
                        if record['student_id'] == student['id']:
                            status_map = {'P': 'present', 'F': 'absent', 'J': 'justified'}
                            attendance_by_session[key] = status_map.get(record['status'], '')
                
                # Converter para formato compatível com o PDF (attendance_by_date usa string key)
                attendance_by_date = {}
                attendance_classes_by_date = {}
                for i, key in enumerate(attendance_days_expanded):
                    str_key = f"{key[0]}#{key[1]}"
                    attendance_by_date[str_key] = attendance_by_session.get(key, '')
                    attendance_classes_by_date[str_key] = 1
                
                students_attendance.append({
                    'name': student['full_name'],
                    'enrollment_number': enrollment_numbers.get(student['id']) or student.get('enrollment_number'),
                    'attendance_by_date': attendance_by_date,
                    'attendance_classes_by_date': attendance_classes_by_date
                })
            
            # Substituir attendance_days por chaves expandidas
            attendance_days = [f"{d[0]}#{d[1]}" for d in attendance_days_expanded]
        else:
            # Modelo legado: usar number_of_classes para expandir
            students_attendance = []
            for student in students:
                attendance_by_date = {}
                attendance_classes_by_date = {}

                for att in attendances:
                    num_classes = att.get('number_of_classes', 1)
                    for record in att.get('records', []):
                        if record['student_id'] == student['id']:
                            status_map = {'P': 'present', 'F': 'absent', 'J': 'justified'}
                            attendance_by_date[att['date']] = status_map.get(record['status'], '')
                            attendance_classes_by_date[att['date']] = num_classes

                students_attendance.append({
                    'name': student['full_name'],
                    'enrollment_number': enrollment_numbers.get(student['id']) or student.get('enrollment_number'),
                    'attendance_by_date': attendance_by_date,
                    'attendance_classes_by_date': attendance_classes_by_date
                })

        # Buscar professor responsável pelo componente (ou turma, se não houver componente)
        teacher_name = ""
        teacher_query = {"class_id": class_id, "academic_year": academic_year}
        if course_id:
            teacher_query["course_id"] = course_id
        teacher_assignment = await db.teacher_assignments.find_one(
            teacher_query,
            {"_id": 0, "staff_id": 1}
        )
        if teacher_assignment:
            teacher = await db.staff.find_one(
                {"id": teacher_assignment['staff_id']},
                {"_id": 0, "nome": 1}
            )
            if teacher:
                teacher_name = teacher.get('nome', '')

        # Buscar componente curricular (para Anos Finais/EJA)
        course_info = None
        if course_id:
            course_info = await db.courses.find_one({"id": course_id}, {"_id": 0})

        # Para anos finais: tudo baseado em hora-aula (number_of_classes)
        # Detectar nível de ensino
        education_level = turma.get('education_level') or turma.get('nivel_ensino') or ''
        if not education_level:
            import re
            ref = (turma.get('grade_level') or turma.get('name') or '').upper()
            if re.search(r'PRÉ|BERÇÁRIO|MATERNAL|CRECHE|INFANTIL', ref):
                education_level = 'educacao_infantil'
            elif re.search(r'\bEJA\b', ref):
                education_level = 'eja_final' if re.search(r'FINAL|[6-9]', ref) else 'eja_inicial'
            else:
                m = re.match(r'(\d+)', ref)
                if m:
                    num = int(m.group(1))
                    education_level = 'fundamental_anos_iniciais' if num <= 5 else 'fundamental_anos_finais'

        is_anos_finais = education_level in ['fundamental_anos_finais', 'eja_final']

        if is_anos_finais and course_id:
            # Aulas ministradas: cada registro com aula_numero = 1 aula
            if has_aula_numero:
                aulas_ministradas_total = len([a for a in attendances if a.get('aula_numero') is not None])
                # Incluir registros legados (sem aula_numero) usando number_of_classes
                aulas_ministradas_total += sum(a.get('number_of_classes', 1) for a in attendances if a.get('aula_numero') is None)
            else:
                aulas_ministradas_total = sum(att.get('number_of_classes', 1) for att in attendances)

            # Aulas previstas = carga horária anual do componente / 4 bimestres
            aulas_previstas_bimestre_calc = 0
            if course_info:
                workload_anual = course_info.get('workload', 0) or 0
                if workload_anual > 0:
                    aulas_previstas_bimestre_calc = round(workload_anual / 4)

            # Fallback: usar schedule_slots se workload não disponível
            if aulas_previstas_bimestre_calc == 0:
                schedule = await db.class_schedules.find_one(
                    {"class_id": class_id}, {"_id": 0}
                )
                if schedule and schedule.get('schedule_slots'):
                    aulas_semana = sum(
                        1 for s in schedule['schedule_slots']
                        if s.get('course_id') == course_id
                    )
                    if aulas_semana > 0:
                        # semanas no bimestre × aulas por semana
                        aulas_previstas_bimestre_calc = round((aulas_previstas_bimestre / 5) * aulas_semana)

            if aulas_previstas_bimestre_calc > 0:
                aulas_previstas_bimestre = aulas_previstas_bimestre_calc
        else:
            # Anos iniciais / Infantil: conta por dias letivos
            aulas_ministradas_total = len(attendance_days)

        # Gerar PDF
        try:
            pdf_buffer = generate_relatorio_frequencia_bimestre_pdf(
                school=school,
                class_info=turma,
                course_info=course_info,
                students_attendance=students_attendance,
                bimestre=bimestre,
                academic_year=academic_year,
                period_start=period_start,
                period_end=period_end,
                attendance_days=attendance_days,
                aulas_previstas=aulas_previstas_bimestre,
                aulas_ministradas=aulas_ministradas_total,
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
                    has_aula_num = att.get('aula_numero') is not None
                    num_classes = 1 if has_aula_num else att.get('number_of_classes', 1)
                    for record in att.get('records', []):
                        if record['student_id'] == student['id']:
                            if record['status'] == 'P':
                                present += num_classes
                            elif record['status'] == 'F':
                                absent += num_classes
                            elif record['status'] == 'J':
                                justified += num_classes

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
