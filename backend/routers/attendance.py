"""
Router de Frequência - SIGESC
PATCH 4.x: Rotas de frequência extraídas do server.py

Endpoints para gestão de frequência incluindo:
- Lançamento por turma/data
- Configurações de ano letivo
- Relatórios por aluno e turma
- Alertas de infrequência
"""

from fastapi import APIRouter, HTTPException, status, Request
from typing import Optional, List
from datetime import datetime, timezone
from pydantic import BaseModel
import uuid
import logging

from auth_middleware import AuthMiddleware

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/attendance", tags=["Frequência"])


class AttendanceRecord(BaseModel):
    student_id: str
    status: str  # present, absent, justified, late - pipe-separated for multi-class: "P|F|P|J"


class AttendanceCreate(BaseModel):
    class_id: str
    date: str
    records: List[AttendanceRecord]
    course_id: Optional[str] = None
    period: str = "regular"
    observations: Optional[str] = None
    number_of_classes: int = 1
    aula_numero: Optional[int] = None  # Para anos finais: identifica a aula (1, 2, 3...)


def setup_attendance_router(db, audit_service, sandbox_db=None):
    """Configura o router de frequência com as dependências necessárias"""
    
    def get_db_for_user(user: dict):
        """Retorna o banco correto baseado no usuário"""
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db

    @router.get("/settings/{academic_year}")
    async def get_attendance_settings(academic_year: int, request: Request):
        """Obtém configurações de frequência para o ano letivo"""
        await AuthMiddleware.get_current_user(request)
        
        settings = await db.attendance_settings.find_one(
            {"academic_year": academic_year}, 
            {"_id": 0}
        )
        
        if not settings:
            return {
                "academic_year": academic_year,
                "allow_future_dates": False
            }
        
        return settings

    @router.put("/settings/{academic_year}")
    async def update_attendance_settings(academic_year: int, request: Request, allow_future_dates: bool):
        """Atualiza configurações de frequência (apenas Admin/Secretário)"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        existing = await current_db.attendance_settings.find_one({"academic_year": academic_year})
        
        if existing:
            await current_db.attendance_settings.update_one(
                {"academic_year": academic_year},
                {"$set": {
                    "allow_future_dates": allow_future_dates,
                    "updated_by": current_user['id'],
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
        else:
            await current_db.attendance_settings.insert_one({
                "id": str(uuid.uuid4()),
                "academic_year": academic_year,
                "allow_future_dates": allow_future_dates,
                "updated_by": current_user['id'],
                "updated_at": datetime.now(timezone.utc).isoformat()
            })
        
        return await current_db.attendance_settings.find_one({"academic_year": academic_year}, {"_id": 0})

    @router.get("/check-date/{date}")
    async def check_attendance_date(date: str, request: Request):
        """Verifica se uma data é válida para lançamento de frequência"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        is_future = date > today
        
        year = int(date.split("-")[0])
        settings = await current_db.attendance_settings.find_one({"academic_year": year}, {"_id": 0})
        allow_future = settings.get("allow_future_dates", False) if settings else False
        
        can_use_future = current_user['role'] in ['admin', 'admin_teste', 'secretario'] and allow_future
        
        # Verifica eventos do calendário
        events = await current_db.calendar_events.find({
            "start_date": {"$lte": date},
            "end_date": {"$gte": date}
        }, {"_id": 0}).to_list(100)
        
        is_school_day = True
        blocking_events = []
        
        for event in events:
            if not event.get('is_school_day', True):
                is_school_day = False
                blocking_events.append(event)
        
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        is_weekend = date_obj.weekday() in [5, 6]
        
        can_record = is_school_day and not is_weekend
        if is_future and not can_use_future:
            can_record = False
        
        return {
            "date": date,
            "is_school_day": is_school_day,
            "is_weekend": is_weekend,
            "is_future": is_future,
            "allow_future_dates": allow_future,
            "can_record": can_record,
            "blocking_events": blocking_events,
            "message": (
                "Data futura não permitida" if is_future and not can_use_future
                else "Final de semana" if is_weekend
                else "Dia não letivo" if not is_school_day
                else "Liberado para lançamento"
            )
        }

    @router.get("/by-class/{class_id}/{date}")
    async def get_attendance_by_class(
        class_id: str, 
        date: str, 
        request: Request,
        course_id: Optional[str] = None,
        period: str = "regular"
    ):
        """Obtém frequência de uma turma em uma data"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        turma = await current_db.classes.find_one({"id": class_id}, {"_id": 0})
        if not turma:
            raise HTTPException(status_code=404, detail="Turma não encontrada")
        
        education_level = turma.get('education_level', '')
        
        if education_level in ['fundamental_anos_iniciais', 'eja']:
            attendance_type = 'daily'
        else:
            attendance_type = 'by_course'
        
        academic_year = turma.get('academic_year', datetime.now().year)
        
        # Busca alunos matriculados - usando múltiplas fontes para maior robustez
        # Estratégia 1: Busca na coleção enrollments (matrícula formal - ativos)
        enrollments = await current_db.enrollments.find(
            {"class_id": class_id, "status": "active"},
            {"_id": 0, "student_id": 1, "enrollment_number": 1, "academic_year": 1, "enrollment_date": 1}
        ).to_list(1000)
        
        enrollment_student_ids = set()
        enrollment_numbers = {}
        enrollment_dates = {}
        for e in enrollments:
            student_id = e.get('student_id')
            enrollment_student_ids.add(student_id)
            if student_id not in enrollment_numbers or e.get('academic_year') == academic_year:
                enrollment_numbers[student_id] = e.get('enrollment_number')
            if e.get('enrollment_date'):
                enrollment_dates[student_id] = e.get('enrollment_date')
        
        # Busca alunos inativos que JÁ ESTIVERAM nesta turma (transferidos, desistentes, etc.)
        inactive_enrollments = await current_db.enrollments.find(
            {"class_id": class_id, "status": {"$in": ["transferred", "dropout", "cancelled", "relocated", "progressed"]}},
            {"_id": 0, "student_id": 1, "enrollment_number": 1, "academic_year": 1, "status": 1}
        ).to_list(1000)
        
        inactive_student_ids = set()
        inactive_enrollment_status = {}
        for e in inactive_enrollments:
            sid = e.get('student_id')
            if sid not in enrollment_student_ids:
                inactive_student_ids.add(sid)
                if sid not in enrollment_numbers or e.get('academic_year') == academic_year:
                    enrollment_numbers[sid] = e.get('enrollment_number')
                inactive_enrollment_status[sid] = e.get('status')
        
        # Estratégia 2: Busca alunos diretamente com class_id (fallback)
        direct_students = await current_db.students.find(
            {"class_id": class_id, "status": {"$in": ["active", "Ativo"]}},
            {"_id": 0, "id": 1, "enrollment_number": 1}
        ).to_list(1000)
        
        for s in direct_students:
            student_id = s.get('id')
            if student_id not in enrollment_numbers:
                enrollment_numbers[student_id] = s.get('enrollment_number')
        
        direct_student_ids = {s.get('id') for s in direct_students}
        
        # Combina todas as fontes
        all_student_ids = list(enrollment_student_ids.union(direct_student_ids).union(inactive_student_ids))
        
        students = []
        if all_student_ids:
            students = await current_db.students.find(
                {"id": {"$in": all_student_ids}},
                {"_id": 0, "id": 1, "full_name": 1, "enrollment_number": 1, "status": 1, "class_id": 1}
            ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).to_list(1000)
        
        # Busca ação mais recente (data e tipo) para alunos inativos
        action_info_map = {}
        if inactive_student_ids:
            action_type_map = {
                'transferencia_saida': 'Transferido',
                'remanejamento': 'Remanejado',
                'progressao': 'Progredido',
                'desistencia': 'Desistente',
                'cancelamento': 'Cancelado'
            }
            history_entries = await current_db.student_history.find(
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
        
        # Busca frequência existente
        query = {"class_id": class_id, "date": date}
        if course_id:
            query["course_id"] = course_id
        if period != "regular":
            query["period"] = period
        
        # Buscar TODAS as sessões para esta data (anos finais podem ter múltiplas)
        all_sessions = await current_db.attendance.find(query, {"_id": 0}).sort("aula_numero", 1).to_list(100)
        
        # Para compatibilidade: pegar a primeira sessão como "attendance" principal
        attendance = all_sessions[0] if all_sessions else None
        
        records_map = {}
        if attendance and attendance.get('records'):
            records_map = {r['student_id']: r['status'] for r in attendance['records']}
        
        # Montar sessões para anos finais
        sessions = []
        for sess in all_sessions:
            sess_records = {r['student_id']: r['status'] for r in sess.get('records', [])}
            sessions.append({
                "id": sess.get('id'),
                "aula_numero": sess.get('aula_numero', 1),
                "number_of_classes": sess.get('number_of_classes', 1),
                "observations": sess.get('observations'),
                "records": sess_records
            })
        
        return {
            "class_id": class_id,
            "class_name": turma.get('name'),
            "date": date,
            "attendance_type": attendance_type,
            "course_id": course_id,
            "period": period,
            "attendance_id": attendance.get('id') if attendance else None,
            "observations": attendance.get('observations') if attendance else None,
            "number_of_classes": attendance.get('number_of_classes', 1) if attendance else 1,
            "total_sessions": len(all_sessions),
            "sessions": sessions,
            "students": [
                {
                    "id": s['id'],
                    "full_name": s['full_name'],
                    "enrollment_number": enrollment_numbers.get(s['id']) or s.get('enrollment_number'),
                    "status": records_map.get(s['id'], None),
                    "student_status": s.get('status', 'active'),
                    "current_class_id": s.get('class_id'),
                    "is_transferred_from_class": s.get('class_id') and s.get('class_id') != class_id,
                    "action_label": action_info_map.get(s['id'], {}).get('action_label', ''),
                    "action_date": action_info_map.get(s['id'], {}).get('action_date', ''),
                    "enrollment_date": enrollment_dates.get(s['id'], s.get('enrollment_date', ''))
                }
                for s in students
            ]
        }

    @router.post("")
    async def create_or_update_attendance(attendance: AttendanceCreate, request: Request):
        """Cria ou atualiza frequência de uma turma"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario', 'professor', 'coordenador', 'auxiliar_secretaria'])(request)
        current_db = get_db_for_user(current_user)
        
        # Detectar se é anos finais para usar aula_numero
        turma = await current_db.classes.find_one({"id": attendance.class_id}, {"_id": 0})
        education_level = turma.get('education_level', '') if turma else ''
        is_anos_finais = education_level in ['fundamental_anos_finais', 'eja_final']
        
        query = {"class_id": attendance.class_id, "date": attendance.date}
        if attendance.course_id:
            query["course_id"] = attendance.course_id
        if attendance.period != "regular":
            query["period"] = attendance.period
        
        # Para anos finais: cada aula é um registro separado (usa aula_numero na query)
        if is_anos_finais and attendance.aula_numero is not None:
            query["aula_numero"] = attendance.aula_numero
        
        existing = await current_db.attendance.find_one(query)
        
        records_data = [{"student_id": r.student_id, "status": r.status} for r in attendance.records]
        
        if existing:
            update_data = {
                "records": records_data,
                "observations": attendance.observations,
                "number_of_classes": 1 if is_anos_finais else attendance.number_of_classes,
                "updated_by": current_user['id'],
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            if is_anos_finais and attendance.aula_numero is not None:
                update_data["aula_numero"] = attendance.aula_numero
            
            await current_db.attendance.update_one(
                {"id": existing['id']},
                {"$set": update_data}
            )
            
            class_info = await current_db.classes.find_one({"id": attendance.class_id}, {"_id": 0, "name": 1, "school_id": 1})
            await audit_service.log(
                action='update',
                collection='attendance',
                user=current_user,
                request=request,
                document_id=existing['id'],
                description=f"Atualizou frequência da turma {class_info.get('name', 'N/A')} em {attendance.date}",
                school_id=class_info.get('school_id') if class_info else None
            )
            
            updated = await current_db.attendance.find_one({"id": existing['id']}, {"_id": 0})
            return updated
        else:
            turma = await current_db.classes.find_one({"id": attendance.class_id}, {"_id": 0})
            education_level = turma.get('education_level', '') if turma else ''
            
            attendance_type = 'daily' if education_level in ['fundamental_anos_iniciais', 'eja'] else 'by_course'
            
            new_attendance = {
                "id": str(uuid.uuid4()),
                "class_id": attendance.class_id,
                "date": attendance.date,
                "course_id": attendance.course_id,
                "period": attendance.period,
                "attendance_type": attendance_type,
                "records": records_data,
                "observations": attendance.observations,
                "number_of_classes": 1 if is_anos_finais else attendance.number_of_classes,
                "academic_year": turma.get('academic_year', datetime.now().year) if turma else datetime.now().year,
                "created_by": current_user['id'],
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Para anos finais: definir aula_numero automaticamente
            if is_anos_finais:
                if attendance.aula_numero is not None:
                    new_attendance["aula_numero"] = attendance.aula_numero
                else:
                    # Auto-incrementar: contar quantas aulas já existem nesse dia/componente
                    count_query = {"class_id": attendance.class_id, "date": attendance.date}
                    if attendance.course_id:
                        count_query["course_id"] = attendance.course_id
                    existing_count = await current_db.attendance.count_documents(count_query)
                    new_attendance["aula_numero"] = existing_count + 1
            
            await current_db.attendance.insert_one(new_attendance)
            
            class_info = await current_db.classes.find_one({"id": attendance.class_id}, {"_id": 0, "name": 1, "school_id": 1})
            await audit_service.log(
                action='create',
                collection='attendance',
                user=current_user,
                request=request,
                document_id=new_attendance['id'],
                description=f"Lançou frequência da turma {class_info.get('name', 'N/A')} em {attendance.date}",
                school_id=class_info.get('school_id') if class_info else None
            )
            
            return await current_db.attendance.find_one({"id": new_attendance['id']}, {"_id": 0})

    @router.delete("/{attendance_id}")
    async def delete_attendance(attendance_id: str, request: Request):
        """Remove registro de frequência"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario', 'professor'])(request)
        current_db = get_db_for_user(current_user)
        
        existing = await current_db.attendance.find_one({"id": attendance_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Registro de frequência não encontrado")
        
        await current_db.attendance.delete_one({"id": attendance_id})
        
        try:
            class_info = await current_db.classes.find_one({"id": existing.get('class_id')}, {"_id": 0, "name": 1, "school_id": 1})
            await audit_service.log(
                action='delete',
                collection='attendance',
                user=current_user,
                request=request,
                document_id=attendance_id,
                description=f"EXCLUIU frequência da turma {class_info.get('name', 'N/A') if class_info else 'N/A'} de {existing.get('date')}",
                school_id=class_info.get('school_id') if class_info else None,
                academic_year=existing.get('academic_year'),
                old_value={'date': existing.get('date'), 'records_count': len(existing.get('records', []))}
            )
        except Exception as e:
            logger.error(f"Falha ao registrar auditoria de exclusão de frequência: {e}")
        
        return {"message": "Frequência removida com sucesso"}

    @router.get("/report/student/{student_id}")
    async def get_student_attendance_report(
        student_id: str,
        request: Request,
        academic_year: Optional[int] = None
    ):
        """Relatório de frequência de um aluno"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        if not academic_year:
            academic_year = datetime.now().year
        
        student = await current_db.students.find_one({"id": student_id}, {"_id": 0})
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        
        # Busca todos os registros de frequência do aluno
        attendances = await current_db.attendance.find(
            {"academic_year": academic_year},
            {"_id": 0}
        ).to_list(5000)
        
        # Filtra registros do aluno
        student_attendances = []
        for att in attendances:
            for record in att.get('records', []):
                if record.get('student_id') == student_id:
                    student_attendances.append({
                        'date': att.get('date'),
                        'class_id': att.get('class_id'),
                        'status': record.get('status'),
                        'period': att.get('period', 'regular'),
                        'course_id': att.get('course_id')
                    })
        
        # Calcula estatísticas
        total = len(student_attendances)
        present = sum(1 for a in student_attendances if a['status'] in ['present', 'P'])
        absent = sum(1 for a in student_attendances if a['status'] in ['absent', 'F', 'A'])
        justified = sum(1 for a in student_attendances if a['status'] in ['justified', 'J'])
        late = sum(1 for a in student_attendances if a['status'] in ['late', 'L'])
        
        return {
            "student": student,
            "academic_year": academic_year,
            "total_records": total,
            "present": present,
            "absent": absent,
            "justified": justified,
            "late": late,
            "attendance_rate": round(present / total * 100, 2) if total > 0 else 0,
            "details": sorted(student_attendances, key=lambda x: x['date'], reverse=True)[:50]
        }

    @router.get("/report/class/{class_id}")
    async def get_class_attendance_report(
        class_id: str,
        request: Request,
        academic_year: Optional[int] = None,
        course_id: Optional[str] = None,
        bimestre: Optional[int] = None
    ):
        """Relatório de frequência de uma turma (filtro opcional por componente)"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        if not academic_year:
            academic_year = datetime.now().year
        
        turma = await current_db.classes.find_one({"id": class_id}, {"_id": 0})
        if not turma:
            raise HTTPException(status_code=404, detail="Turma não encontrada")
        
        # Busca alunos matriculados - usando múltiplas fontes
        enrollments = await current_db.enrollments.find(
            {"class_id": class_id, "status": "active"},
            {"_id": 0, "student_id": 1, "enrollment_number": 1, "academic_year": 1}
        ).to_list(1000)
        
        enrollment_student_ids = set()
        enrollment_numbers = {}
        for e in enrollments:
            student_id = e.get('student_id')
            enrollment_student_ids.add(student_id)
            if student_id not in enrollment_numbers or e.get('academic_year') == academic_year:
                enrollment_numbers[student_id] = e.get('enrollment_number')
        
        # Busca alunos diretamente com class_id (fallback)
        direct_students = await current_db.students.find(
            {"class_id": class_id, "status": {"$in": ["active", "Ativo"]}},
            {"_id": 0, "id": 1, "enrollment_number": 1}
        ).to_list(1000)
        
        for s in direct_students:
            student_id = s.get('id')
            if student_id not in enrollment_numbers:
                enrollment_numbers[student_id] = s.get('enrollment_number')
        
        direct_student_ids = {s.get('id') for s in direct_students}
        all_student_ids = list(enrollment_student_ids.union(direct_student_ids))
        
        students = []
        if all_student_ids:
            students = await current_db.students.find(
                {"id": {"$in": all_student_ids}},
                {"_id": 0, "id": 1, "full_name": 1}
            ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).to_list(1000)
        
        # Filtrar por bimestre (datas) se informado
        period_start = None
        period_end = None
        if bimestre:
            calendario = await current_db.calendario_letivo.find_one(
                {"ano_letivo": academic_year, "school_id": None}, {"_id": 0}
            )
            if not calendario:
                calendario = await current_db.calendario_letivo.find_one(
                    {"ano_letivo": academic_year}, {"_id": 0}
                )
            if calendario:
                bim_inicio = calendario.get(f"bimestre_{bimestre}_inicio")
                bim_fim = calendario.get(f"bimestre_{bimestre}_fim")
                if bim_inicio and bim_fim:
                    period_start = str(bim_inicio)[:10]
                    period_end = str(bim_fim)[:10]
            if not period_start:
                bimestre_periodos = {
                    1: (f"{academic_year}-02-01", f"{academic_year}-04-30"),
                    2: (f"{academic_year}-05-01", f"{academic_year}-07-15"),
                    3: (f"{academic_year}-07-16", f"{academic_year}-09-30"),
                    4: (f"{academic_year}-10-01", f"{academic_year}-12-20"),
                }
                period_start, period_end = bimestre_periodos.get(bimestre, (None, None))

        # Busca todos os registros de frequência da turma
        att_query = {"class_id": class_id, "academic_year": academic_year}
        if course_id:
            att_query["course_id"] = course_id
        if period_start and period_end:
            att_query["date"] = {"$gte": period_start, "$lte": period_end}
        attendances = await current_db.attendance.find(
            att_query,
            {"_id": 0}
        ).to_list(1000)
        
        # Calcula estatísticas por aluno
        student_stats = {}
        for student in students:
            student_stats[student['id']] = {
                'present': 0,
                'absent': 0,
                'justified': 0,
                'late': 0,
                'total': 0
            }
        
        # Coleta datas de aula para calcular atestados
        attendance_dates = set()
        total_aulas_registradas = 0
        for att in attendances:
            att_date = att.get('date', '')[:10]
            has_aula_numero = att.get('aula_numero') is not None
            num_classes = 1 if has_aula_numero else att.get('number_of_classes', 1)
            total_aulas_registradas += num_classes
            if att_date:
                attendance_dates.add(att_date)
            for record in att.get('records', []):
                sid = record.get('student_id')
                if sid in student_stats:
                    raw_status = record.get('status', '')
                    
                    if '|' in raw_status:
                        # Pipe-separated statuses (legado multi-aula)
                        statuses = raw_status.split('|')
                        student_stats[sid]['total'] += len(statuses)
                        for s in statuses:
                            s = s.strip()
                            if s in ['present', 'P']:
                                student_stats[sid]['present'] += 1
                            elif s in ['absent', 'F', 'A']:
                                student_stats[sid]['absent'] += 1
                            elif s in ['justified', 'J']:
                                student_stats[sid]['justified'] += 1
                    else:
                        student_stats[sid]['total'] += num_classes
                        if raw_status in ['present', 'P']:
                            student_stats[sid]['present'] += num_classes
                        elif raw_status in ['absent', 'F', 'A']:
                            student_stats[sid]['absent'] += num_classes
                        elif raw_status in ['justified', 'J']:
                            student_stats[sid]['justified'] += num_classes
                        elif raw_status in ['late', 'L']:
                            student_stats[sid]['late'] += num_classes
        
        # Busca atestados médicos para os alunos da turma
        medical_days = {}
        if all_student_ids and attendance_dates:
            sorted_dates = sorted(attendance_dates)
            min_date = sorted_dates[0]
            max_date = sorted_dates[-1]
            certificates = await current_db.medical_certificates.find(
                {
                    "student_id": {"$in": all_student_ids},
                    "start_date": {"$lte": max_date},
                    "end_date": {"$gte": min_date}
                },
                {"_id": 0, "student_id": 1, "start_date": 1, "end_date": 1}
            ).to_list(None)
            
            for cert in certificates:
                sid = cert.get('student_id')
                if sid not in medical_days:
                    medical_days[sid] = set()
                start = cert.get('start_date', '')[:10]
                end = cert.get('end_date', '')[:10]
                for d in attendance_dates:
                    if start <= d <= end:
                        medical_days[sid].add(d)
        
        report = []
        for student in students:
            stats = student_stats.get(student['id'], {})
            total = stats.get('total', 0)
            present = stats.get('present', 0)
            justified = stats.get('justified', 0)
            absent = stats.get('absent', 0)
            
            # Calcula percentual de frequência (presença + justificadas contam)
            attendance_percentage = round((present + justified) / total * 100, 1) if total > 0 else 0
            
            # Define status baseado na frequência mínima (75%)
            freq_status = 'regular' if attendance_percentage >= 75 else 'infrequente'
            
            report.append({
                "student_id": student['id'],
                "student_name": student['full_name'],
                "enrollment_number": enrollment_numbers.get(student['id']),
                "present": present,
                "absent": absent,
                "justified": justified,
                "medical": len(medical_days.get(student['id'], set())),
                "late": stats.get('late', 0),
                "total": total,
                "attendance_percentage": attendance_percentage,
                "status": freq_status
            })
        
        # Detectar se é Anos Finais para ajustar label
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
        
        return {
            "class": turma,
            "academic_year": academic_year,
            "course_id": course_id,
            "total_records": total_aulas_registradas,
            "total_school_days_recorded": total_aulas_registradas,
            "total_students": len(students),
            "report_type": "aulas" if is_anos_finais else "dias",
            "students": report
        }


    @router.get("/attendance-summary/{class_id}")
    async def get_attendance_summary(
        class_id: str,
        request: Request,
        academic_year: Optional[int] = None,
        course_id: Optional[str] = None
    ):
        """
        Resumo de frequência da turma: dias/aulas previstos, registrados e restantes.
        Para anos iniciais/infantil: conta dias distintos.
        Para anos finais: conta aulas (soma de number_of_classes por registro).
        """
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)

        if not academic_year:
            academic_year = datetime.now().year

        # Buscar turma
        turma = await current_db.classes.find_one({"id": class_id}, {"_id": 0})
        if not turma:
            raise HTTPException(status_code=404, detail="Turma não encontrada")

        # Buscar calendário letivo (coleção: calendario_letivo, calendário geral com school_id=None)
        calendario = await current_db.calendario_letivo.find_one(
            {"ano_letivo": academic_year, "school_id": None}, {"_id": 0}
        )
        if not calendario:
            calendario = await current_db.calendario_letivo.find_one(
                {"ano_letivo": academic_year}, {"_id": 0}
            )

        dias_letivos_previstos = 0
        if calendario:
            # Calcular dias letivos — lógica idêntica ao endpoint /calendario-letivo/{ano}/dias-letivos
            from datetime import timedelta

            eventos_nao_letivos = ['feriado_nacional', 'feriado_estadual', 'feriado_municipal', 'recesso_escolar']
            events = await current_db.calendar_events.find(
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
                    start_date = datetime.strptime(start_date_str[:10], '%Y-%m-%d').date()
                    end_date = datetime.strptime(end_date_str[:10], '%Y-%m-%d').date()
                    current = start_date
                    while current <= end_date:
                        if event_type in eventos_nao_letivos:
                            datas_nao_letivas.add(current)
                        elif event_type == 'sabado_letivo':
                            datas_sabados_letivos.add(current)
                        elif event.get('is_school_day', False) and current.weekday() == 5:
                            datas_sabados_letivos.add(current)
                        current += timedelta(days=1)
                except (ValueError, TypeError):
                    continue

            def _calcular_dias_periodo(inicio_str, fim_str):
                if not inicio_str or not fim_str:
                    return 0
                try:
                    inicio = datetime.strptime(str(inicio_str)[:10], '%Y-%m-%d').date()
                    fim = datetime.strptime(str(fim_str)[:10], '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    return 0
                dias = 0
                current = inicio
                while current <= fim:
                    if current in datas_sabados_letivos:
                        dias += 1
                    elif current.weekday() < 5:
                        if current not in datas_nao_letivas:
                            dias += 1
                    current += timedelta(days=1)
                return dias

            b1 = _calcular_dias_periodo(calendario.get('bimestre_1_inicio'), calendario.get('bimestre_1_fim'))
            b2 = _calcular_dias_periodo(calendario.get('bimestre_2_inicio'), calendario.get('bimestre_2_fim'))
            b3 = _calcular_dias_periodo(calendario.get('bimestre_3_inicio'), calendario.get('bimestre_3_fim'))
            b4 = _calcular_dias_periodo(calendario.get('bimestre_4_inicio'), calendario.get('bimestre_4_fim'))
            dias_letivos_previstos = b1 + b2 + b3 + b4

            # Fallback para o campo dias_letivos_previstos se cálculo dos bimestres retornar 0
            if dias_letivos_previstos == 0:
                dias_letivos_previstos = calendario.get('dias_letivos_previstos', 200) or 200

        # Detectar nível de ensino
        education_level = turma.get('education_level') or turma.get('nivel_ensino') or ''
        # Inferir do nome se não tem campo
        if not education_level:
            ref = (turma.get('grade_level') or turma.get('name') or '').upper()
            import re
            if re.search(r'PRÉ|BERÇÁRIO|MATERNAL|CRECHE|INFANTIL', ref):
                education_level = 'educacao_infantil'
            elif re.search(r'\bEJA\b', ref):
                education_level = 'eja_final' if re.search(r'FINAL|[6-9]', ref) else 'eja_inicial'
            else:
                m = re.match(r'(\d+)', ref)
                if m:
                    num = int(m.group(1))
                    education_level = 'fundamental_anos_iniciais' if num <= 5 else 'fundamental_anos_finais'
                else:
                    if turma.get('series'):
                        m2 = re.match(r'(\d+)', str(turma['series'][0]))
                        if m2:
                            num = int(m2.group(1))
                            education_level = 'fundamental_anos_iniciais' if num <= 5 else 'fundamental_anos_finais'

        is_anos_finais = education_level in ['fundamental_anos_finais', 'eja_final']

        # Buscar registros de frequência
        att_query = {"class_id": class_id, "academic_year": academic_year}
        if course_id:
            att_query["course_id"] = course_id
        attendances = await current_db.attendance.find(att_query, {"_id": 0}).to_list(5000)

        if is_anos_finais:
            # Para anos finais: cada registro com aula_numero conta como 1 aula
            # Registros legados sem aula_numero usam number_of_classes
            aulas_registradas = 0
            for att in attendances:
                if att.get('aula_numero') is not None:
                    aulas_registradas += 1  # Cada registro = 1 aula
                else:
                    aulas_registradas += att.get('number_of_classes', 1)  # Compatibilidade legado

            # Calcular aulas previstas: usar carga horária do componente (workload)
            # Fonte primária: workload do curso (total anual de hora-aula)
            aulas_previstas = 0
            if course_id:
                course = await current_db.courses.find_one({"id": course_id}, {"_id": 0})
                if course:
                    aulas_previstas = course.get('workload', 0) or 0

            # Fallback: usar schedule_slots se workload não definido
            if aulas_previstas == 0 and course_id:
                schedule = await current_db.class_schedules.find_one(
                    {"class_id": class_id}, {"_id": 0}
                )
                if schedule and schedule.get('schedule_slots'):
                    aulas_semana = sum(
                        1 for s in schedule['schedule_slots']
                        if s.get('course_id') == course_id
                    )
                    aulas_previstas = int((dias_letivos_previstos / 5) * aulas_semana) if aulas_semana > 0 else 0

            return {
                "type": "aulas",
                "previstos": aulas_previstas,
                "registrados": aulas_registradas,
                "restantes": max(0, aulas_previstas - aulas_registradas)
            }
        else:
            # Para anos iniciais/infantil: contar DIAS distintos
            dias_registrados = len(set(att.get('date') for att in attendances if att.get('date')))

            return {
                "type": "dias",
                "previstos": dias_letivos_previstos,
                "registrados": dias_registrados,
                "restantes": max(0, dias_letivos_previstos - dias_registrados)
            }


    return router
