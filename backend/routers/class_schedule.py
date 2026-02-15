"""
Class Schedule Router - Horário de Aulas
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from typing import Optional, List
from datetime import datetime, timezone, date, timedelta
from bson import ObjectId
from auth_middleware import AuthMiddleware
from models import ClassSchedule, ClassScheduleCreate, ClassScheduleUpdate, ClassScheduleSlot

router = APIRouter(prefix="/class-schedules", tags=["Class Schedules"])


def setup_class_schedule_router(db, audit_service=None, sandbox_db=None):
    """Setup class schedule router with database connection"""
    
    def get_current_db(request: Request):
        """Get current database based on sandbox mode"""
        is_sandbox = hasattr(request.state, 'is_sandbox') and request.state.is_sandbox
        if sandbox_db is not None and is_sandbox:
            return sandbox_db
        return db
    
    @router.get("")
    async def list_class_schedules(
        request: Request,
        school_id: Optional[str] = Query(None, description="Filtrar por escola"),
        class_id: Optional[str] = Query(None, description="Filtrar por turma"),
        academic_year: Optional[int] = Query(None, description="Filtrar por ano letivo")
    ):
        """
        Lista horários de aulas com filtros.
        Permissões:
        - Admin/SEMED: Vê todos
        - Secretário/Diretor/Coordenador: Vê apenas das escolas vinculadas
        - Professor: Vê apenas das turmas alocadas
        - Aluno/Responsável: Vê apenas da turma matriculada
        """
        current_db = get_current_db(request)
        user = await AuthMiddleware.get_current_user(request)
        
        query = {}
        
        # Filtros opcionais
        if school_id:
            query['school_id'] = school_id
        if class_id:
            query['class_id'] = class_id
        if academic_year:
            query['academic_year'] = academic_year
        
        # Aplicar filtros de permissão
        user_role = user.get('role', '')
        user_school_ids = user.get('school_ids', []) or []
        if user.get('school_links'):
            user_school_ids = [link.get('school_id') for link in user.get('school_links', [])]
        
        if user_role in ['admin', 'admin_teste', 'semed']:
            # Vê todos
            pass
        elif user_role in ['secretario', 'diretor', 'coordenador']:
            # Filtra por escolas vinculadas
            if user_school_ids:
                query['school_id'] = {'$in': user_school_ids}
            else:
                return []
        elif user_role == 'professor':
            # Filtra por turmas alocadas
            allocations = await current_db.teacher_allocations.find({
                'staff_id': user.get('staff_id'),
                'status': 'ativo'
            }).to_list(None)
            class_ids = list(set([a.get('class_id') for a in allocations if a.get('class_id')]))
            if class_ids:
                query['class_id'] = {'$in': class_ids}
            else:
                return []
        elif user_role in ['aluno', 'responsavel']:
            # Filtra por turma matriculada
            student_id = user.get('student_id')
            if student_id:
                enrollments = await current_db.enrollments.find({
                    'student_id': student_id,
                    'status': 'active'
                }).to_list(None)
                class_ids = [e.get('class_id') for e in enrollments if e.get('class_id')]
                if class_ids:
                    query['class_id'] = {'$in': class_ids}
                else:
                    return []
            else:
                return []
        
        schedules = await current_db.class_schedules.find(query).to_list(None)
        
        # Enriquecer com dados da turma e escola
        for schedule in schedules:
            schedule['id'] = schedule.pop('_id', schedule.get('id'))
            
            # Buscar nome da turma
            class_info = await current_db.classes.find_one({'id': schedule.get('class_id')})
            if class_info:
                schedule['class_name'] = class_info.get('name')
                schedule['shift'] = class_info.get('shift')
            
            # Buscar nome da escola
            school_info = await current_db.schools.find_one({'id': schedule.get('school_id')})
            if school_info:
                schedule['school_name'] = school_info.get('name')
        
        return schedules
    
    @router.get("/by-class/{class_id}")
    async def get_schedule_by_class(
        request: Request,
        class_id: str,
        academic_year: Optional[int] = Query(None, description="Ano letivo")
    ):
        """Busca o horário de uma turma específica"""
        current_db = get_current_db(request)
        user = await AuthMiddleware.get_current_user(request)
        
        query = {'class_id': class_id}
        if academic_year:
            query['academic_year'] = academic_year
        
        schedule = await current_db.class_schedules.find_one(query)
        
        if schedule:
            schedule['id'] = schedule.pop('_id', schedule.get('id'))
            
            # Enriquecer com dados da turma
            class_info = await current_db.classes.find_one({'id': class_id})
            if class_info:
                schedule['class_name'] = class_info.get('name')
                schedule['shift'] = class_info.get('shift')
            
            # Enriquecer slots com nome do componente
            for slot in schedule.get('schedule_slots', []):
                if slot.get('course_id'):
                    course = await current_db.courses.find_one({'id': slot.get('course_id')})
                    if course:
                        slot['course_name'] = course.get('name')
        
        return schedule
    
    @router.get("/saturday-schedule")
    async def get_saturday_schedule(
        request: Request,
        class_id: str,
        saturday_date: str,  # YYYY-MM-DD
        academic_year: int
    ):
        """
        Retorna o horário para um sábado letivo específico.
        O horário é baseado no dia da semana correspondente:
        - 1º sábado letivo = aulas de segunda
        - 2º sábado letivo = aulas de terça
        - etc. (até o 12º, depois volta ao início)
        """
        current_db = get_current_db(request)
        
        # Buscar todos os sábados letivos do ano
        saturday_events = await current_db.calendar_events.find({
            'academic_year': academic_year,
            'event_type': 'sabado_letivo',
            'is_school_day': True
        }).sort('start_date', 1).to_list(None)
        
        # Encontrar a posição do sábado solicitado
        saturday_dates = [e.get('start_date') for e in saturday_events]
        
        if saturday_date not in saturday_dates:
            return None
        
        saturday_index = saturday_dates.index(saturday_date)
        
        # Mapear para o dia da semana (0 = segunda, 1 = terça, etc.)
        day_index = saturday_index % 5  # Cicla de 0-4 (segunda a sexta)
        days = ['segunda', 'terca', 'quarta', 'quinta', 'sexta']
        day_labels = {'segunda': 'Segunda', 'terca': 'Terça', 'quarta': 'Quarta', 'quinta': 'Quinta', 'sexta': 'Sexta'}
        corresponding_day = days[day_index]
        
        # Buscar o horário da turma
        schedule = await current_db.class_schedules.find_one({
            'class_id': class_id,
            'academic_year': academic_year
        })
        
        # Mesmo sem horário, retornar info do sábado
        if not schedule:
            return {
                'saturday_date': saturday_date,
                'saturday_number': saturday_index + 1,
                'corresponding_day': corresponding_day,
                'corresponding_day_label': day_labels[corresponding_day],
                'slots': []
            }
        
        # Filtrar apenas os slots do dia correspondente
        saturday_slots = [
            slot for slot in schedule.get('schedule_slots', [])
            if slot.get('day') == corresponding_day
        ]
        
        # Enriquecer com nome dos componentes
        for slot in saturday_slots:
            if slot.get('course_id'):
                course = await current_db.courses.find_one({'id': slot.get('course_id')})
                if course:
                    slot['course_name'] = course.get('name')
        
        return {
            'saturday_date': saturday_date,
            'saturday_number': saturday_index + 1,
            'corresponding_day': corresponding_day,
            'corresponding_day_label': day_labels[corresponding_day],
            'slots': saturday_slots
        }
    
    @router.get("/week-view")
    async def get_week_view(
        request: Request,
        class_id: str,
        week_start: str,  # YYYY-MM-DD (deve ser uma segunda-feira)
        academic_year: int
    ):
        """
        Retorna a visualização semanal do horário, incluindo sábado letivo se houver.
        """
        current_db = get_current_db(request)
        
        # Buscar o horário da turma
        schedule = await current_db.class_schedules.find_one({
            'class_id': class_id,
            'academic_year': academic_year
        })
        
        # Calcular datas da semana
        start_date = datetime.strptime(week_start, '%Y-%m-%d').date()
        week_dates = {}
        days = ['segunda', 'terca', 'quarta', 'quinta', 'sexta', 'sabado']
        
        for i, day in enumerate(days[:5]):  # Segunda a sexta
            current_date = start_date + timedelta(days=i)
            week_dates[day] = current_date.strftime('%Y-%m-%d')
        
        # Verificar se há sábado letivo na semana
        saturday_date = (start_date + timedelta(days=5)).strftime('%Y-%m-%d')
        week_dates['sabado'] = saturday_date
        
        saturday_event = await current_db.calendar_events.find_one({
            'start_date': saturday_date,
            'event_type': 'sabado_letivo',
            'is_school_day': True
        })
        
        has_saturday = saturday_event is not None
        
        # Se houver sábado letivo, buscar o horário correspondente
        saturday_slots = []
        saturday_info = None
        if has_saturday:
            saturday_data = await get_saturday_schedule(request, class_id, saturday_date, academic_year)
            if saturday_data:
                saturday_slots = saturday_data.get('slots', [])
                saturday_info = {
                    'saturday_number': saturday_data.get('saturday_number'),
                    'corresponding_day': saturday_data.get('corresponding_day')
                }
        
        # Se não há horário cadastrado, retornar estrutura mínima com info do sábado
        if not schedule:
            return {
                'schedule': None,
                'week_dates': week_dates,
                'has_saturday': has_saturday,
                'saturday_slots': saturday_slots,
                'saturday_info': saturday_info,
                'class_name': None,
                'shift': None
            }
        
        schedule['id'] = schedule.pop('_id', schedule.get('id'))
        
        # Enriquecer slots com nome dos componentes
        for slot in schedule.get('schedule_slots', []):
            if slot.get('course_id'):
                course = await current_db.courses.find_one({'id': slot.get('course_id')})
                if course:
                    slot['course_name'] = course.get('name')
        
        # Buscar informações da turma
        class_info = await current_db.classes.find_one({'id': class_id})
        
        return {
            'schedule': schedule,
            'week_dates': week_dates,
            'has_saturday': has_saturday,
            'saturday_slots': saturday_slots,
            'saturday_info': saturday_info,
            'class_name': class_info.get('name') if class_info else None,
            'shift': class_info.get('shift') if class_info else None
        }
    
    @router.post("")
    async def create_class_schedule(
        request: Request,
        schedule_data: ClassScheduleCreate
    ):
        """
        Cria um novo horário de aulas.
        Apenas admin e secretário podem criar.
        """
        current_db = get_current_db(request)
        user = await AuthMiddleware.get_current_user(request)
        
        # Verificar permissão
        if user.get('role') not in ['admin', 'admin_teste', 'secretario']:
            raise HTTPException(status_code=403, detail="Apenas administradores e secretários podem criar horários")
        
        # Verificar se já existe horário para esta turma/ano
        existing = await current_db.class_schedules.find_one({
            'class_id': schedule_data.class_id,
            'academic_year': schedule_data.academic_year
        })
        
        if existing:
            raise HTTPException(status_code=400, detail="Já existe um horário para esta turma neste ano letivo")
        
        # Buscar o turno da turma
        class_info = await current_db.classes.find_one({'id': schedule_data.class_id})
        if not class_info:
            raise HTTPException(status_code=404, detail="Turma não encontrada")
        
        # Criar o horário
        schedule_dict = schedule_data.model_dump()
        schedule_dict['id'] = str(__import__('uuid').uuid4())
        schedule_dict['shift'] = class_info.get('shift')
        schedule_dict['created_at'] = datetime.now(timezone.utc).isoformat()
        
        await current_db.class_schedules.insert_one(schedule_dict)
        
        # Remove MongoDB _id before returning
        schedule_dict.pop('_id', None)
        
        # Audit log
        if audit_service:
            await audit_service.log(
                action='create',
                collection='class_schedules',
                document_id=schedule_dict['id'],
                user_id=user.get('id'),
                user_email=user.get('email'),
                user_role=user.get('role'),
                school_id=schedule_data.school_id,
                academic_year=schedule_data.academic_year,
                new_data=schedule_dict
            )
        
        return schedule_dict
    
    @router.put("/{schedule_id}")
    async def update_class_schedule(
        request: Request,
        schedule_id: str,
        update_data: ClassScheduleUpdate
    ):
        """
        Atualiza um horário de aulas existente.
        Apenas admin e secretário podem editar.
        """
        current_db = get_current_db(request)
        user = await AuthMiddleware.get_current_user(request)
        
        # Verificar permissão
        if user.get('role') not in ['admin', 'admin_teste', 'secretario']:
            raise HTTPException(status_code=403, detail="Apenas administradores e secretários podem editar horários")
        
        # Buscar horário existente
        existing = await current_db.class_schedules.find_one({'id': schedule_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Horário não encontrado")
        
        # Atualizar
        update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
        update_dict['updated_at'] = datetime.now(timezone.utc).isoformat()
        
        await current_db.class_schedules.update_one(
            {'id': schedule_id},
            {'$set': update_dict}
        )
        
        # Audit log
        if audit_service:
            await audit_service.log(
                action='update',
                collection='class_schedules',
                document_id=schedule_id,
                user_id=user.get('id'),
                user_email=user.get('email'),
                user_role=user.get('role'),
                school_id=existing.get('school_id'),
                academic_year=existing.get('academic_year'),
                old_data=existing,
                new_data=update_dict
            )
        
        # Retornar atualizado
        updated = await current_db.class_schedules.find_one({'id': schedule_id})
        updated.pop('_id', None)  # Remove MongoDB _id
        return updated
    
    @router.delete("/{schedule_id}")
    async def delete_class_schedule(
        request: Request,
        schedule_id: str
    ):
        """
        Remove um horário de aulas.
        Apenas admin pode excluir.
        """
        current_db = get_current_db(request)
        user = await AuthMiddleware.get_current_user(request)
        
        # Verificar permissão
        if user.get('role') not in ['admin', 'admin_teste']:
            raise HTTPException(status_code=403, detail="Apenas administradores podem excluir horários")
        
        # Buscar horário existente
        existing = await current_db.class_schedules.find_one({'id': schedule_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Horário não encontrado")
        
        await current_db.class_schedules.delete_one({'id': schedule_id})
        
        # Audit log
        if audit_service:
            await audit_service.log(
                action='delete',
                collection='class_schedules',
                document_id=schedule_id,
                user_id=user.get('id'),
                user_email=user.get('email'),
                user_role=user.get('role'),
                school_id=existing.get('school_id'),
                academic_year=existing.get('academic_year'),
                old_data=existing
            )
        
        return {"message": "Horário excluído com sucesso"}
    
    @router.get("/validate-conflicts")
    async def validate_schedule_conflicts(
        request: Request,
        class_id: str,
        day: str,
        slot_number: int,
        course_id: str,
        academic_year: int
    ):
        """
        Valida se há conflito de professor no horário.
        Verifica se o professor alocado para o componente já tem aula
        em outra turma no mesmo dia/horário (mesmo em outra escola).
        """
        current_db = get_current_db(request)
        
        # Buscar professor alocado para este componente nesta turma
        allocation = await current_db.teacher_allocations.find_one({
            'class_id': class_id,
            'course_id': course_id,
            'academic_year': {'$in': [academic_year, str(academic_year)]},
            'status': 'ativo'
        })
        
        if not allocation:
            # Sem professor alocado, não há conflito
            return {'has_conflict': False, 'message': 'Componente sem professor alocado'}
        
        staff_id = allocation.get('staff_id')
        
        # Buscar todas as alocações deste professor
        all_allocations = await current_db.teacher_allocations.find({
            'staff_id': staff_id,
            'academic_year': {'$in': [academic_year, str(academic_year)]},
            'status': 'ativo'
        }).to_list(None)
        
        # Para cada alocação, verificar se há aula no mesmo dia/horário
        conflicts = []
        for alloc in all_allocations:
            other_class_id = alloc.get('class_id')
            if other_class_id == class_id:
                continue  # Mesma turma, não é conflito
            
            other_course_id = alloc.get('course_id')
            
            # Buscar o horário da outra turma
            other_schedule = await current_db.class_schedules.find_one({
                'class_id': other_class_id,
                'academic_year': academic_year
            })
            
            if not other_schedule:
                continue
            
            # Verificar se há aula no mesmo dia/horário
            for slot in other_schedule.get('schedule_slots', []):
                if slot.get('day') == day and slot.get('slot_number') == slot_number:
                    # Há conflito!
                    other_class = await current_db.classes.find_one({'id': other_class_id})
                    other_school = await current_db.schools.find_one({'id': other_schedule.get('school_id')})
                    other_course = await current_db.courses.find_one({'id': slot.get('course_id')})
                    staff = await current_db.staff.find_one({'id': staff_id})
                    
                    conflicts.append({
                        'staff_name': staff.get('nome') if staff else 'Professor',
                        'class_name': other_class.get('name') if other_class else 'Turma',
                        'school_name': other_school.get('name') if other_school else 'Escola',
                        'course_name': other_course.get('name') if other_course else 'Componente',
                        'day': day,
                        'slot_number': slot_number
                    })
        
        if conflicts:
            return {
                'has_conflict': True,
                'message': f'Professor já tem aula neste horário',
                'conflicts': conflicts
            }
        
        return {'has_conflict': False, 'message': 'Sem conflitos'}
    
    @router.get("/all-conflicts")
    async def get_all_network_conflicts(
        request: Request,
        academic_year: int,
        school_id: Optional[str] = Query(None, description="Filtrar por escola específica")
    ):
        """
        Retorna todos os conflitos de horário na rede de ensino.
        Um conflito ocorre quando um professor está alocado para dar aula
        em duas turmas diferentes no mesmo dia/horário.
        
        Apenas admin, semed e secretário podem visualizar.
        """
        current_db = get_current_db(request)
        user = await AuthMiddleware.get_current_user(request)
        
        # Verificar permissão
        if user.get('role') not in ['admin', 'admin_teste', 'semed', 'secretario']:
            raise HTTPException(status_code=403, detail="Sem permissão para visualizar conflitos da rede")
        
        # Buscar todos os horários do ano
        schedule_query = {'academic_year': academic_year}
        if school_id:
            schedule_query['school_id'] = school_id
        
        all_schedules = await current_db.class_schedules.find(schedule_query).to_list(None)
        
        if not all_schedules:
            return {
                'total_conflicts': 0,
                'conflicts_by_teacher': [],
                'conflicts_by_day': {},
                'summary': 'Nenhum horário cadastrado para este ano letivo'
            }
        
        # Buscar todas as alocações de professores
        allocation_query = {
            'academic_year': {'$in': [academic_year, str(academic_year)]},
            'status': 'ativo'
        }
        all_allocations = await current_db.teacher_allocations.find(allocation_query).to_list(None)
        
        # Criar mapa de alocações por turma/componente
        allocation_map = {}
        for alloc in all_allocations:
            key = f"{alloc.get('class_id')}_{alloc.get('course_id')}"
            allocation_map[key] = alloc.get('staff_id')
        
        # Criar mapa de slots por professor: {staff_id: [{day, slot_number, class_id, school_id, course_id}]}
        teacher_slots = {}
        
        for schedule in all_schedules:
            class_id = schedule.get('class_id')
            school_id_sched = schedule.get('school_id')
            
            for slot in schedule.get('schedule_slots', []):
                course_id = slot.get('course_id')
                if not course_id:
                    continue
                
                # Encontrar o professor alocado
                alloc_key = f"{class_id}_{course_id}"
                staff_id = allocation_map.get(alloc_key)
                
                if not staff_id:
                    continue
                
                if staff_id not in teacher_slots:
                    teacher_slots[staff_id] = []
                
                teacher_slots[staff_id].append({
                    'day': slot.get('day'),
                    'slot_number': slot.get('slot_number'),
                    'class_id': class_id,
                    'school_id': school_id_sched,
                    'course_id': course_id,
                    'course_name': slot.get('course_name')
                })
        
        # Detectar conflitos por professor
        conflicts_by_teacher = []
        conflicts_by_day = {'segunda': 0, 'terca': 0, 'quarta': 0, 'quinta': 0, 'sexta': 0}
        total_conflicts = 0
        
        # Cache para dados enriquecidos
        staff_cache = {}
        class_cache = {}
        school_cache = {}
        course_cache = {}
        
        for staff_id, slots in teacher_slots.items():
            # Agrupar por dia/horário
            slot_groups = {}
            for slot in slots:
                key = f"{slot['day']}_{slot['slot_number']}"
                if key not in slot_groups:
                    slot_groups[key] = []
                slot_groups[key].append(slot)
            
            # Encontrar grupos com conflito (mais de 1 aula no mesmo horário)
            teacher_conflicts = []
            for key, group in slot_groups.items():
                if len(group) > 1:
                    # Há conflito!
                    day = group[0]['day']
                    conflicts_by_day[day] = conflicts_by_day.get(day, 0) + 1
                    total_conflicts += 1
                    
                    # Enriquecer dados
                    conflict_details = []
                    for item in group:
                        # Class info
                        if item['class_id'] not in class_cache:
                            cls = await current_db.classes.find_one({'id': item['class_id']})
                            class_cache[item['class_id']] = cls
                        cls = class_cache[item['class_id']]
                        
                        # School info
                        if item['school_id'] not in school_cache:
                            sch = await current_db.schools.find_one({'id': item['school_id']})
                            school_cache[item['school_id']] = sch
                        sch = school_cache[item['school_id']]
                        
                        # Course info
                        if item['course_id'] not in course_cache:
                            crs = await current_db.courses.find_one({'id': item['course_id']})
                            course_cache[item['course_id']] = crs
                        crs = course_cache[item['course_id']]
                        
                        conflict_details.append({
                            'class_name': cls.get('name') if cls else 'Turma não encontrada',
                            'class_shift': cls.get('shift') if cls else None,
                            'school_name': sch.get('name') if sch else 'Escola não encontrada',
                            'course_name': crs.get('name') if crs else item.get('course_name', 'Componente')
                        })
                    
                    teacher_conflicts.append({
                        'day': day,
                        'slot_number': group[0]['slot_number'],
                        'conflicting_classes': conflict_details
                    })
            
            if teacher_conflicts:
                # Staff info
                if staff_id not in staff_cache:
                    stf = await current_db.staff.find_one({'id': staff_id})
                    staff_cache[staff_id] = stf
                stf = staff_cache[staff_id]
                
                conflicts_by_teacher.append({
                    'staff_id': staff_id,
                    'staff_name': stf.get('nome') if stf else 'Professor não encontrado',
                    'staff_cpf': stf.get('cpf') if stf else None,
                    'conflicts_count': len(teacher_conflicts),
                    'conflicts': teacher_conflicts
                })
        
        # Ordenar por número de conflitos (maior primeiro)
        conflicts_by_teacher.sort(key=lambda x: x['conflicts_count'], reverse=True)
        
        return {
            'academic_year': academic_year,
            'total_conflicts': total_conflicts,
            'teachers_with_conflicts': len(conflicts_by_teacher),
            'conflicts_by_teacher': conflicts_by_teacher,
            'conflicts_by_day': conflicts_by_day,
            'summary': f'{total_conflicts} conflito(s) encontrado(s) envolvendo {len(conflicts_by_teacher)} professor(es)'
        }
    
    return router
