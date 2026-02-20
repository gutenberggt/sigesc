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

from auth_middleware import AuthMiddleware

router = APIRouter(prefix="/attendance", tags=["Frequência"])


class AttendanceRecord(BaseModel):
    student_id: str
    status: str  # present, absent, justified, late


class AttendanceCreate(BaseModel):
    class_id: str
    date: str
    records: List[AttendanceRecord]
    course_id: Optional[str] = None
    period: str = "regular"
    observations: Optional[str] = None


def setup_attendance_router(db, audit_service, sandbox_db=None):
    """Configura o router de frequência com as dependências necessárias"""
    
    def get_db_for_user(user: dict):
        """Retorna o banco correto baseado no usuário"""
        if False:  # Sandbox desabilitado
            return sandbox_db
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
        # Estratégia 1: Busca na coleção enrollments (matrícula formal)
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
        
        # Combina ambas as fontes
        all_student_ids = list(enrollment_student_ids.union(direct_student_ids))
        
        students = []
        if all_student_ids:
            # Inclui status do aluno para verificação de bloqueio
            students = await current_db.students.find(
                {"id": {"$in": all_student_ids}},
                {"_id": 0, "id": 1, "full_name": 1, "enrollment_number": 1, "status": 1, "class_id": 1}
            ).sort("full_name", 1).to_list(1000)
        
        # Busca frequência existente
        query = {"class_id": class_id, "date": date}
        if course_id:
            query["course_id"] = course_id
        if period != "regular":
            query["period"] = period
        
        attendance = await current_db.attendance.find_one(query, {"_id": 0})
        
        records_map = {}
        if attendance and attendance.get('records'):
            records_map = {r['student_id']: r['status'] for r in attendance['records']}
        
        return {
            "class_id": class_id,
            "class_name": turma.get('name'),
            "date": date,
            "attendance_type": attendance_type,
            "course_id": course_id,
            "period": period,
            "attendance_id": attendance.get('id') if attendance else None,
            "observations": attendance.get('observations') if attendance else None,
            "students": [
                {
                    "id": s['id'],
                    "full_name": s['full_name'],
                    "enrollment_number": enrollment_numbers.get(s['id']) or s.get('enrollment_number'),
                    "status": records_map.get(s['id'], None),
                    # Inclui status do aluno e turma atual para verificação de bloqueio
                    "student_status": s.get('status', 'active'),
                    "current_class_id": s.get('class_id'),
                    # Indica se o aluno foi remanejado/progredido para outra turma
                    "is_transferred_from_class": s.get('class_id') and s.get('class_id') != class_id
                }
                for s in students
            ]
        }

    @router.post("")
    async def create_or_update_attendance(attendance: AttendanceCreate, request: Request):
        """Cria ou atualiza frequência de uma turma"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario', 'professor', 'coordenador'])(request)
        current_db = get_db_for_user(current_user)
        
        query = {"class_id": attendance.class_id, "date": attendance.date}
        if attendance.course_id:
            query["course_id"] = attendance.course_id
        if attendance.period != "regular":
            query["period"] = attendance.period
        
        existing = await current_db.attendance.find_one(query)
        
        records_data = [{"student_id": r.student_id, "status": r.status} for r in attendance.records]
        
        if existing:
            await current_db.attendance.update_one(
                {"id": existing['id']},
                {"$set": {
                    "records": records_data,
                    "observations": attendance.observations,
                    "updated_by": current_user['id'],
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
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
                "academic_year": turma.get('academic_year', datetime.now().year) if turma else datetime.now().year,
                "created_by": current_user['id'],
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
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
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        existing = await current_db.attendance.find_one({"id": attendance_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Registro de frequência não encontrado")
        
        await current_db.attendance.delete_one({"id": attendance_id})
        
        class_info = await current_db.classes.find_one({"id": existing.get('class_id')}, {"_id": 0, "name": 1, "school_id": 1})
        await audit_service.log(
            action='delete',
            collection='attendance',
            user=current_user,
            request=request,
            document_id=attendance_id,
            description=f"EXCLUIU frequência da turma {class_info.get('name', 'N/A')} de {existing.get('date')}",
            school_id=class_info.get('school_id') if class_info else None,
            academic_year=existing.get('academic_year'),
            old_value={'date': existing.get('date'), 'records_count': len(existing.get('records', []))}
        )
        
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
        academic_year: Optional[int] = None
    ):
        """Relatório de frequência de uma turma"""
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
            ).sort("full_name", 1).to_list(1000)
        
        # Busca todos os registros de frequência da turma
        attendances = await current_db.attendance.find(
            {"class_id": class_id, "academic_year": academic_year},
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
        
        for att in attendances:
            for record in att.get('records', []):
                sid = record.get('student_id')
                if sid in student_stats:
                    student_stats[sid]['total'] += 1
                    status = record.get('status', '')
                    if status in ['present', 'P']:
                        student_stats[sid]['present'] += 1
                    elif status in ['absent', 'F', 'A']:
                        student_stats[sid]['absent'] += 1
                    elif status in ['justified', 'J']:
                        student_stats[sid]['justified'] += 1
                    elif status in ['late', 'L']:
                        student_stats[sid]['late'] += 1
        
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
            status = 'regular' if attendance_percentage >= 75 else 'infrequente'
            
            report.append({
                "student_id": student['id'],
                "student_name": student['full_name'],
                "enrollment_number": enrollment_numbers.get(student['id']),
                "present": present,
                "absent": absent,
                "justified": justified,
                "late": stats.get('late', 0),
                "total": total,
                "attendance_percentage": attendance_percentage,
                "status": status
            })
        
        return {
            "class": turma,
            "academic_year": academic_year,
            "total_records": len(attendances),
            "total_school_days_recorded": len(attendances),
            "total_students": len(students),
            "students": report
        }

    return router
