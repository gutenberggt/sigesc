"""
Analytics Router - Dashboard Analítico para acompanhamento do município
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from typing import Optional, List
from datetime import datetime
from bson import ObjectId
from auth_middleware import AuthMiddleware

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def setup_analytics_router(db, audit_service=None, sandbox_db=None):
    """Setup analytics router with database connection"""
    
    def get_current_db(request: Request):
        """Get current database based on sandbox mode"""
        is_sandbox = hasattr(request.state, 'is_sandbox') and request.state.is_sandbox
        if sandbox_db is not None and is_sandbox:
            return sandbox_db
        return db
    
    def year_filter(year):
        """Retorna filtro que aceita ano como int ou string"""
        return {'$in': [str(year), year]}
    
    @router.get("/overview")
    async def get_analytics_overview(
        request: Request,
        academic_year: Optional[int] = Query(None, description="Ano letivo"),
        school_id: Optional[str] = Query(None, description="ID da escola"),
        class_id: Optional[str] = Query(None, description="ID da turma")
    ):
        """
        Retorna visão geral das estatísticas do município/escola
        """
        current_db = get_current_db(request)
        user = await AuthMiddleware.get_current_user(request)
        
        # Determina se usuário tem visão global ou restrita
        is_global = user.get('role') in ['admin', 'admin_teste', 'semed']
        user_school_ids = user.get('school_ids', []) or []
        if user.get('school_links'):
            user_school_ids = [link.get('school_id') for link in user.get('school_links', [])]
        
        # ============ CONTAGEM DE ESCOLAS ============
        # Conta apenas escolas ATIVAS (status = "active")
        school_query = {"status": "active"}
        if school_id:
            school_query['id'] = school_id
        elif not is_global and user_school_ids:
            school_query['id'] = {'$in': user_school_ids}
        
        total_schools = await current_db.schools.count_documents(school_query)
        
        # ============ CONTAGEM DE TURMAS ============
        # Primeiro tenta com o ano especificado, depois sem
        class_base_filter = {}
        if school_id:
            class_base_filter['school_id'] = school_id
        elif not is_global and user_school_ids:
            class_base_filter['school_id'] = {'$in': user_school_ids}
        
        # Filtro de turmas com ano letivo (aceita int ou string)
        class_filter_with_year = {**class_base_filter}
        if academic_year:
            class_filter_with_year['academic_year'] = {'$in': [str(academic_year), academic_year]}
        
        total_classes = await current_db.classes.count_documents(class_filter_with_year)
        
        # ============ CONTAGEM DE ALUNOS ATIVOS ============
        # Conta alunos com status "Ativo", "active" ou sem status definido
        # Nota: status "transferred" não é contabilizado como ativo
        student_filter = {
            '$or': [
                {'status': {'$in': ['Ativo', 'ativo', 'active', 'Active', None]}},
                {'status': {'$exists': False}}
            ]
        }
        if school_id:
            student_filter['school_id'] = school_id
        elif not is_global and user_school_ids:
            student_filter['school_id'] = {'$in': user_school_ids}
        
        total_students = await current_db.students.count_documents(student_filter)
        
        # Também conta o total geral de alunos (para informação)
        total_students_all = await current_db.students.count_documents(
            {'school_id': school_id} if school_id else 
            {'school_id': {'$in': user_school_ids}} if not is_global and user_school_ids else {}
        )
        
        # ============ CONTAGEM DE MATRÍCULAS ============
        # Matrículas são os vínculos aluno-turma por ano letivo
        enrollment_base_filter = {}
        if school_id:
            enrollment_base_filter['school_id'] = school_id
        elif not is_global and user_school_ids:
            enrollment_base_filter['school_id'] = {'$in': user_school_ids}
        if class_id:
            enrollment_base_filter['class_id'] = class_id
        
        # Filtro com ano letivo (aceita int ou string)
        enrollment_filter = {**enrollment_base_filter}
        if academic_year:
            enrollment_filter['academic_year'] = {'$in': [str(academic_year), academic_year]}
        
        # Contagem de matrículas por status
        enrollments_pipeline = [
            {'$match': enrollment_filter},
            {'$group': {
                '_id': '$status',
                'count': {'$sum': 1}
            }}
        ]
        enrollment_stats = {}
        async for doc in current_db.enrollments.aggregate(enrollments_pipeline):
            enrollment_stats[doc['_id'] or 'active'] = doc['count']
        
        total_enrollments = sum(enrollment_stats.values())
        active_enrollments = enrollment_stats.get('active', 0) + enrollment_stats.get('Ativo', 0) + enrollment_stats.get('ativo', 0)
        
        # ============ TRANSFERÊNCIAS ============
        # Lógica: 
        # - Se escola específica: contar matrículas transferidas daquela escola (da collection enrollments)
        # - Se todas as escolas: contar apenas alunos com status "Transferido" (saíram da rede)
        
        if school_id:
            # Escola específica: contar transferências da escola via enrollments
            transfer_count = enrollment_stats.get('transferred', 0) + enrollment_stats.get('Transferido', 0) + enrollment_stats.get('transferido', 0)
        else:
            # Todas as escolas: contar alunos com status "Transferido" (saíram da rede municipal)
            student_transfer_filter = {
                'status': {'$in': ['Transferido', 'transferred', 'transferido']}
            }
            if not is_global and user_school_ids:
                student_transfer_filter['school_id'] = {'$in': user_school_ids}
            transfer_count = await current_db.students.count_documents(student_transfer_filter)
        
        # Calcular porcentagem de transferências
        transfer_base = total_enrollments if school_id else total_students_all
        transfer_rate = round((transfer_count / transfer_base * 100), 1) if transfer_base > 0 else 0
        
        # ============ DESISTÊNCIAS ============
        # Contar matrículas/alunos com status de desistência
        desistencia_statuses = ['desistente', 'Desistente', 'desistencia', 'Desistência', 'dropout', 'Dropout', 'cancelled', 'Cancelado', 'cancelado']
        
        if school_id:
            # Escola específica: contar via enrollments
            desistencia_count = sum(enrollment_stats.get(s, 0) for s in desistencia_statuses)
        else:
            # Todas as escolas: contar via students
            student_desistencia_filter = {
                'status': {'$in': desistencia_statuses}
            }
            if not is_global and user_school_ids:
                student_desistencia_filter['school_id'] = {'$in': user_school_ids}
            desistencia_count = await current_db.students.count_documents(student_desistencia_filter)
        
        # Calcular porcentagem de desistências
        desistencia_base = total_enrollments if school_id else total_students_all
        desistencia_rate = round((desistencia_count / desistencia_base * 100), 1) if desistencia_base > 0 else 0
        
        # Estatísticas de frequência
        attendance_base_filter = {}
        if school_id:
            attendance_base_filter['school_id'] = school_id
        elif not is_global and user_school_ids:
            attendance_base_filter['school_id'] = {'$in': user_school_ids}
        if class_id:
            attendance_base_filter['class_id'] = class_id
        
        attendance_filter = {**attendance_base_filter}
        if academic_year:
            attendance_filter['date'] = {'$regex': f'^{academic_year}'}
        
        attendance_pipeline = [
            {'$match': attendance_filter},
            {'$group': {
                '_id': None,
                'total_records': {'$sum': 1},
                'present_count': {
                    '$sum': {'$cond': [{'$eq': ['$status', 'present']}, 1, 0]}
                },
                'absent_count': {
                    '$sum': {'$cond': [{'$eq': ['$status', 'absent']}, 1, 0]}
                },
                'justified_count': {
                    '$sum': {'$cond': [{'$eq': ['$status', 'justified']}, 1, 0]}
                }
            }}
        ]
        
        attendance_stats = {'total_records': 0, 'present_count': 0, 'absent_count': 0, 'justified_count': 0}
        async for doc in current_db.attendance.aggregate(attendance_pipeline):
            attendance_stats = doc
        
        attendance_rate = 0
        if attendance_stats['total_records'] > 0:
            attendance_rate = round(
                (attendance_stats['present_count'] + attendance_stats['justified_count']) / 
                attendance_stats['total_records'] * 100, 1
            )
        
        # Estatísticas de notas
        grades_filter = {}
        if class_id:
            grades_filter['class_id'] = class_id
        if academic_year:
            grades_filter['academic_year'] = str(academic_year)
        
        # Se tem filtro de escola, buscar turmas da escola primeiro
        if school_id or (not is_global and user_school_ids):
            school_ids_to_filter = [school_id] if school_id else user_school_ids
            classes_in_school = await current_db.classes.find(
                {'school_id': {'$in': school_ids_to_filter}},
                {'id': 1}
            ).to_list(None)
            class_ids = [c['id'] for c in classes_in_school]
            if class_ids:
                grades_filter['class_id'] = {'$in': class_ids}
        
        grades_pipeline = [
            {'$match': grades_filter},
            {'$group': {
                '_id': None,
                'avg_grade': {'$avg': '$grade'},
                'total_grades': {'$sum': 1},
                'approved': {
                    '$sum': {'$cond': [{'$gte': ['$grade', 6]}, 1, 0]}
                },
                'failed': {
                    '$sum': {'$cond': [{'$lt': ['$grade', 6]}, 1, 0]}
                }
            }}
        ]
        
        grades_stats = {'avg_grade': 0, 'total_grades': 0, 'approved': 0, 'failed': 0}
        async for doc in current_db.grades.aggregate(grades_pipeline):
            grades_stats = doc
            if grades_stats['avg_grade']:
                grades_stats['avg_grade'] = round(grades_stats['avg_grade'], 1)
        
        approval_rate = 0
        if grades_stats['total_grades'] > 0:
            approval_rate = round(grades_stats['approved'] / grades_stats['total_grades'] * 100, 1)
        
        return {
            'schools': {
                'total': total_schools
            },
            'classes': {
                'total': total_classes
            },
            'students': {
                'active': total_students,
                'total': total_students_all
            },
            'enrollments': {
                'total': total_enrollments,
                'active': active_enrollments,
                'by_status': enrollment_stats
            },
            'transfers': {
                'total': transfer_count,
                'rate': transfer_rate
            },
            'dropouts': {
                'total': desistencia_count,
                'rate': desistencia_rate
            },
            'attendance': {
                'total_records': attendance_stats.get('total_records', 0),
                'present': attendance_stats.get('present_count', 0),
                'absent': attendance_stats.get('absent_count', 0),
                'justified': attendance_stats.get('justified_count', 0),
                'rate': attendance_rate
            },
            'grades': {
                'average': grades_stats.get('avg_grade', 0),
                'total': grades_stats.get('total_grades', 0),
                'approved': grades_stats.get('approved', 0),
                'failed': grades_stats.get('failed', 0),
                'approval_rate': approval_rate
            }
        }
    
    @router.get("/enrollments/trend")
    async def get_enrollments_trend(
        request: Request,
        school_id: Optional[str] = Query(None),
        class_id: Optional[str] = Query(None)
    ):
        """
        Retorna tendência de matrículas por ano letivo
        """
        current_db = get_current_db(request)
        user = await AuthMiddleware.get_current_user(request)
        
        is_global = user.get('role') in ['admin', 'admin_teste', 'semed']
        user_school_ids = user.get('school_ids', []) or []
        if user.get('school_links'):
            user_school_ids = [link.get('school_id') for link in user.get('school_links', [])]
        
        match_filter = {}
        if school_id:
            match_filter['school_id'] = school_id
        elif not is_global and user_school_ids:
            match_filter['school_id'] = {'$in': user_school_ids}
        
        if class_id:
            match_filter['class_id'] = class_id
        
        pipeline = [
            {'$match': match_filter},
            {'$group': {
                '_id': {
                    'year': '$academic_year',
                    'status': '$status'
                },
                'count': {'$sum': 1}
            }},
            {'$group': {
                '_id': '$_id.year',
                'total': {'$sum': '$count'},
                'statuses': {
                    '$push': {
                        'status': '$_id.status',
                        'count': '$count'
                    }
                }
            }},
            {'$sort': {'_id': 1}}
        ]
        
        result = []
        async for doc in current_db.enrollments.aggregate(pipeline):
            year_data = {
                'year': doc['_id'],
                'total': doc['total'],
                'active': 0,
                'transferred': 0,
                'cancelled': 0
            }
            for status in doc['statuses']:
                status_key = status['status'] or 'active'
                if status_key in ['active', 'ativo', 'Ativo']:
                    year_data['active'] += status['count']
                elif status_key in ['transferred', 'Transferido', 'transferido']:
                    year_data['transferred'] += status['count']
                elif status_key in ['cancelled', 'Cancelado', 'cancelado']:
                    year_data['cancelled'] += status['count']
            result.append(year_data)
        
        return result
    
    @router.get("/attendance/monthly")
    async def get_attendance_monthly(
        request: Request,
        academic_year: int = Query(..., description="Ano letivo"),
        school_id: Optional[str] = Query(None),
        class_id: Optional[str] = Query(None),
        student_id: Optional[str] = Query(None)
    ):
        """
        Retorna frequência mensal
        """
        current_db = get_current_db(request)
        user = await AuthMiddleware.get_current_user(request)
        
        is_global = user.get('role') in ['admin', 'admin_teste', 'semed']
        user_school_ids = user.get('school_ids', []) or []
        if user.get('school_links'):
            user_school_ids = [link.get('school_id') for link in user.get('school_links', [])]
        
        match_filter = {
            'date': {'$regex': f'^{academic_year}'}
        }
        
        if student_id:
            match_filter['student_id'] = student_id
        if class_id:
            match_filter['class_id'] = class_id
        if school_id:
            match_filter['school_id'] = school_id
        elif not is_global and user_school_ids:
            match_filter['school_id'] = {'$in': user_school_ids}
        
        pipeline = [
            {'$match': match_filter},
            {'$addFields': {
                'month': {'$substr': ['$date', 5, 2]}
            }},
            {'$group': {
                '_id': '$month',
                'total': {'$sum': 1},
                'present': {
                    '$sum': {'$cond': [{'$eq': ['$status', 'present']}, 1, 0]}
                },
                'absent': {
                    '$sum': {'$cond': [{'$eq': ['$status', 'absent']}, 1, 0]}
                },
                'justified': {
                    '$sum': {'$cond': [{'$eq': ['$status', 'justified']}, 1, 0]}
                }
            }},
            {'$sort': {'_id': 1}}
        ]
        
        months_map = {
            '01': 'Jan', '02': 'Fev', '03': 'Mar', '04': 'Abr',
            '05': 'Mai', '06': 'Jun', '07': 'Jul', '08': 'Ago',
            '09': 'Set', '10': 'Out', '11': 'Nov', '12': 'Dez'
        }
        
        result = []
        async for doc in current_db.attendance.aggregate(pipeline):
            month_num = doc['_id']
            rate = 0
            if doc['total'] > 0:
                rate = round((doc['present'] + doc['justified']) / doc['total'] * 100, 1)
            
            result.append({
                'month': months_map.get(month_num, month_num),
                'month_num': month_num,
                'total': doc['total'],
                'present': doc['present'],
                'absent': doc['absent'],
                'justified': doc['justified'],
                'rate': rate
            })
        
        return result
    
    @router.get("/grades/by-subject")
    async def get_grades_by_subject(
        request: Request,
        academic_year: int = Query(..., description="Ano letivo"),
        school_id: Optional[str] = Query(None),
        class_id: Optional[str] = Query(None),
        student_id: Optional[str] = Query(None)
    ):
        """
        Retorna média de notas por componente curricular
        """
        current_db = get_current_db(request)
        user = await AuthMiddleware.get_current_user(request)
        
        is_global = user.get('role') in ['admin', 'admin_teste', 'semed']
        user_school_ids = user.get('school_ids', []) or []
        if user.get('school_links'):
            user_school_ids = [link.get('school_id') for link in user.get('school_links', [])]
        
        match_filter = {
            'academic_year': year_filter(academic_year)
        }
        
        if student_id:
            match_filter['student_id'] = student_id
        if class_id:
            match_filter['class_id'] = class_id
        
        # Filtro por escola (através das turmas)
        if school_id or (not is_global and user_school_ids):
            school_ids_to_filter = [school_id] if school_id else user_school_ids
            classes_in_school = await current_db.classes.find(
                {'school_id': {'$in': school_ids_to_filter}},
                {'id': 1}
            ).to_list(None)
            class_ids = [c['id'] for c in classes_in_school]
            if class_ids and not class_id:
                match_filter['class_id'] = {'$in': class_ids}
        
        pipeline = [
            {'$match': match_filter},
            {'$group': {
                '_id': '$course_id',
                'avg_grade': {'$avg': '$grade'},
                'total_students': {'$addToSet': '$student_id'},
                'max_grade': {'$max': '$grade'},
                'min_grade': {'$min': '$grade'}
            }},
            {'$project': {
                'course_id': '$_id',
                'avg_grade': {'$round': ['$avg_grade', 1]},
                'total_students': {'$size': '$total_students'},
                'max_grade': 1,
                'min_grade': 1
            }},
            {'$sort': {'avg_grade': -1}}
        ]
        
        # Buscar nomes dos cursos
        courses = {}
        async for course in current_db.courses.find({}, {'id': 1, 'name': 1, 'abbreviation': 1}):
            courses[course['id']] = {
                'name': course.get('name', 'N/A'),
                'abbreviation': course.get('abbreviation', course.get('name', 'N/A')[:3])
            }
        
        result = []
        async for doc in current_db.grades.aggregate(pipeline):
            course_info = courses.get(doc['_id'], {'name': 'Desconhecido', 'abbreviation': 'N/A'})
            result.append({
                'course_id': doc['_id'],
                'course_name': course_info['name'],
                'abbreviation': course_info['abbreviation'],
                'avg_grade': doc['avg_grade'] or 0,
                'total_students': doc['total_students'],
                'max_grade': doc.get('max_grade', 0),
                'min_grade': doc.get('min_grade', 0)
            })
        
        return result
    
    @router.get("/grades/by-period")
    async def get_grades_by_period(
        request: Request,
        academic_year: int = Query(..., description="Ano letivo"),
        school_id: Optional[str] = Query(None),
        class_id: Optional[str] = Query(None),
        student_id: Optional[str] = Query(None)
    ):
        """
        Retorna média de notas por bimestre/período
        """
        current_db = get_current_db(request)
        user = await AuthMiddleware.get_current_user(request)
        
        is_global = user.get('role') in ['admin', 'admin_teste', 'semed']
        user_school_ids = user.get('school_ids', []) or []
        if user.get('school_links'):
            user_school_ids = [link.get('school_id') for link in user.get('school_links', [])]
        
        match_filter = {
            'academic_year': year_filter(academic_year)
        }
        
        if student_id:
            match_filter['student_id'] = student_id
        if class_id:
            match_filter['class_id'] = class_id
        
        if school_id or (not is_global and user_school_ids):
            school_ids_to_filter = [school_id] if school_id else user_school_ids
            classes_in_school = await current_db.classes.find(
                {'school_id': {'$in': school_ids_to_filter}},
                {'id': 1}
            ).to_list(None)
            class_ids = [c['id'] for c in classes_in_school]
            if class_ids and not class_id:
                match_filter['class_id'] = {'$in': class_ids}
        
        pipeline = [
            {'$match': match_filter},
            {'$group': {
                '_id': '$period',
                'avg_grade': {'$avg': '$grade'},
                'total_grades': {'$sum': 1},
                'approved': {
                    '$sum': {'$cond': [{'$gte': ['$grade', 6]}, 1, 0]}
                }
            }},
            {'$sort': {'_id': 1}}
        ]
        
        period_names = {
            '1': '1º Bimestre',
            '2': '2º Bimestre',
            '3': '3º Bimestre',
            '4': '4º Bimestre',
            'final': 'Nota Final'
        }
        
        result = []
        async for doc in current_db.grades.aggregate(pipeline):
            period = str(doc['_id']) if doc['_id'] else '1'
            approval_rate = 0
            if doc['total_grades'] > 0:
                approval_rate = round(doc['approved'] / doc['total_grades'] * 100, 1)
            
            result.append({
                'period': period,
                'period_name': period_names.get(period, f'Período {period}'),
                'avg_grade': round(doc['avg_grade'] or 0, 1),
                'total_grades': doc['total_grades'],
                'approval_rate': approval_rate
            })
        
        return result
    
    @router.get("/schools/ranking")
    async def get_schools_ranking(
        request: Request,
        academic_year: int = Query(..., description="Ano letivo"),
        limit: int = Query(10, description="Limite de resultados"),
        bimestre: Optional[int] = Query(None, description="Bimestre para cálculo de evolução (1-4)")
    ):
        """
        Retorna ranking das escolas por desempenho usando Score V2.1
        
        ============================================
        SCORE V2.1 - COMPOSIÇÃO (100 pontos)
        ============================================
        
        BLOCO APRENDIZAGEM (45 pts):
        - Nota Média (25 pts): (média_final / 10) × 100
        - Taxa de Aprovação (10 pts): (aprovados / total_avaliados) × 100
        - Ganho/Evolução (10 pts): clamp(50 + delta×25, 0, 100)
        
        BLOCO PERMANÊNCIA/FLUXO (35 pts):
        - Frequência Média (25 pts): (P + J) / total × 100
        - Retenção/Anti-evasão (10 pts): 100 - (dropouts / matrículas) × 100
        
        BLOCO GESTÃO/PROCESSO (20 pts):
        - Cobertura Curricular (10 pts): (aulas_com_registro / aulas_previstas) × 100
        - SLA Frequência - 3 dias úteis (5 pts): (lançamentos_no_prazo / total) × 100
        - SLA Notas - 7 dias (5 pts): (lançamentos_no_prazo / total) × 100
        
        INDICADOR INFORMATIVO (não entra no score):
        - Distorção Idade-Série: % de alunos fora da idade adequada
        ============================================
        """
        from datetime import timedelta
        
        current_db = get_current_db(request)
        user = await AuthMiddleware.get_current_user(request)
        
        is_global = user.get('role') in ['admin', 'admin_teste', 'semed']
        user_school_ids = user.get('school_ids', []) or []
        if user.get('school_links'):
            user_school_ids = [link.get('school_id') for link in user.get('school_links', [])]
        
        # Buscar todas as escolas ativas
        school_filter = {'status': 'active'}
        if not is_global and user_school_ids:
            school_filter['id'] = {'$in': user_school_ids}
        
        schools = {}
        async for school in current_db.schools.find(school_filter, {'id': 1, 'name': 1}):
            schools[school['id']] = {
                'name': school['name'],
                # Indicadores brutos
                'enrollments_start': 0,  # Matrículas no início do ano
                'enrollments_active': 0,  # Matrículas ativas atuais
                'dropouts': 0,  # Evasões (não conta transferência)
                'avg_grade': 0,  # Média de notas (0-10)
                'approved_count': 0,  # Alunos aprovados
                'evaluated_count': 0,  # Alunos com status final
                'attendance_present': 0,  # Presenças + Justificadas
                'attendance_total': 0,  # Total de registros de frequência
                'grade_b1_avg': 0,  # Média B1
                'grade_b2_avg': 0,  # Média B2
                'grade_b3_avg': 0,  # Média B3
                'grade_b4_avg': 0,  # Média B4
                'learning_objects_count': 0,  # Objetos de conhecimento registrados
                'expected_classes': 0,  # Aulas previstas (estimativa)
                'attendance_on_time': 0,  # Frequências lançadas no prazo (3 dias)
                'attendance_records_total': 0,  # Total de registros para SLA
                'grades_on_time': 0,  # Notas lançadas no prazo (7 dias)
                'grades_records_total': 0,  # Total de notas para SLA
                'age_distortion_count': 0,  # Alunos com distorção idade-série
                'students_with_birthdate': 0,  # Alunos com data de nascimento
            }
        
        if not schools:
            return []
        
        school_ids = list(schools.keys())
        
        # ============================================
        # 1. MATRÍCULAS E EVASÃO
        # ============================================
        # Matrículas ativas (atuais)
        enrollment_pipeline = [
            {'$match': {
                'school_id': {'$in': school_ids},
                'academic_year': year_filter(academic_year),
                'status': {'$in': ['active', 'ativo', 'Ativo', None]}
            }},
            {'$group': {
                '_id': '$school_id',
                'count': {'$sum': 1}
            }}
        ]
        async for doc in current_db.enrollments.aggregate(enrollment_pipeline):
            if doc['_id'] in schools:
                schools[doc['_id']]['enrollments_active'] = doc['count']
        
        # Matrículas totais (início do ano) = ativas + transferidas + evasões
        enrollment_start_pipeline = [
            {'$match': {
                'school_id': {'$in': school_ids},
                'academic_year': year_filter(academic_year)
            }},
            {'$group': {
                '_id': {'school_id': '$school_id', 'status': '$status'},
                'count': {'$sum': 1}
            }}
        ]
        async for doc in current_db.enrollments.aggregate(enrollment_start_pipeline):
            school_id = doc['_id']['school_id']
            status = doc['_id']['status'] or 'active'
            if school_id in schools:
                schools[school_id]['enrollments_start'] += doc['count']
                # Conta evasões (dropout, desistente, cancelado - NÃO conta transferido)
                if status.lower() in ['dropout', 'desistente', 'desistencia', 'cancelled', 'cancelado', 'abandono']:
                    schools[school_id]['dropouts'] += doc['count']
        
        # ============================================
        # 2. FREQUÊNCIA (P + J) / Total
        # ============================================
        # Busca turmas por escola
        classes_by_school = {}
        async for cls in current_db.classes.find(
            {'school_id': {'$in': school_ids}, 'academic_year': year_filter(academic_year)},
            {'id': 1, 'school_id': 1}
        ):
            classes_by_school[cls['id']] = cls['school_id']
        
        # Frequência agregada por escola (através dos registros de attendance)
        attendance_pipeline = [
            {'$match': {
                'class_id': {'$in': list(classes_by_school.keys())},
                'date': {'$regex': f'^{academic_year}'}
            }},
            {'$unwind': '$records'},
            {'$group': {
                '_id': '$class_id',
                'total': {'$sum': 1},
                'present': {
                    '$sum': {'$cond': [{'$in': ['$records.status', ['P', 'present', 'J', 'justified']]}, 1, 0]}
                }
            }}
        ]
        async for doc in current_db.attendance.aggregate(attendance_pipeline):
            school_id = classes_by_school.get(doc['_id'])
            if school_id and school_id in schools:
                schools[school_id]['attendance_total'] += doc['total']
                schools[school_id]['attendance_present'] += doc['present']
        
        # ============================================
        # 3. NOTAS E APROVAÇÃO
        # ============================================
        # Busca notas por turma e calcula médias bimestrais e aprovação
        grades_pipeline = [
            {'$match': {
                'class_id': {'$in': list(classes_by_school.keys())},
                'academic_year': year_filter(academic_year)
            }},
            {'$group': {
                '_id': '$class_id',
                'avg_final': {'$avg': '$final_average'},
                'avg_b1': {'$avg': '$b1'},
                'avg_b2': {'$avg': '$b2'},
                'avg_b3': {'$avg': '$b3'},
                'avg_b4': {'$avg': '$b4'},
                'approved': {
                    '$sum': {'$cond': [{'$eq': ['$status', 'aprovado']}, 1, 0]}
                },
                'evaluated': {
                    '$sum': {'$cond': [{'$in': ['$status', ['aprovado', 'reprovado', 'reprovado_nota', 'reprovado_frequencia']]}, 1, 0]}
                },
                'total_grades': {'$sum': 1}
            }}
        ]
        
        school_grade_data = {sid: {'sum_avg': 0, 'count': 0, 'b1': [], 'b2': [], 'b3': [], 'b4': []} for sid in school_ids}
        async for doc in current_db.grades.aggregate(grades_pipeline):
            school_id = classes_by_school.get(doc['_id'])
            if school_id and school_id in schools:
                if doc['avg_final']:
                    school_grade_data[school_id]['sum_avg'] += doc['avg_final']
                    school_grade_data[school_id]['count'] += 1
                if doc['avg_b1']:
                    school_grade_data[school_id]['b1'].append(doc['avg_b1'])
                if doc['avg_b2']:
                    school_grade_data[school_id]['b2'].append(doc['avg_b2'])
                if doc['avg_b3']:
                    school_grade_data[school_id]['b3'].append(doc['avg_b3'])
                if doc['avg_b4']:
                    school_grade_data[school_id]['b4'].append(doc['avg_b4'])
                schools[school_id]['approved_count'] += doc['approved']
                schools[school_id]['evaluated_count'] += doc['evaluated']
        
        for school_id, data in school_grade_data.items():
            if data['count'] > 0:
                schools[school_id]['avg_grade'] = round(data['sum_avg'] / data['count'], 2)
            if data['b1']:
                schools[school_id]['grade_b1_avg'] = round(sum(data['b1']) / len(data['b1']), 2)
            if data['b2']:
                schools[school_id]['grade_b2_avg'] = round(sum(data['b2']) / len(data['b2']), 2)
            if data['b3']:
                schools[school_id]['grade_b3_avg'] = round(sum(data['b3']) / len(data['b3']), 2)
            if data['b4']:
                schools[school_id]['grade_b4_avg'] = round(sum(data['b4']) / len(data['b4']), 2)
        
        # ============================================
        # 4. COBERTURA CURRICULAR (Objetos de Conhecimento)
        # ============================================
        learning_obj_pipeline = [
            {'$match': {
                'class_id': {'$in': list(classes_by_school.keys())},
                'academic_year': year_filter(academic_year)
            }},
            {'$group': {
                '_id': '$class_id',
                'count': {'$sum': '$number_of_classes'}
            }}
        ]
        async for doc in current_db.learning_objects.aggregate(learning_obj_pipeline):
            school_id = classes_by_school.get(doc['_id'])
            if school_id and school_id in schools:
                schools[school_id]['learning_objects_count'] += doc['count']
        
        # Estimar aulas previstas (200 dias letivos × número de turmas × 5 aulas/dia)
        for school_id in school_ids:
            num_classes = len([c for c, s in classes_by_school.items() if s == school_id])
            schools[school_id]['expected_classes'] = num_classes * 200 * 5  # Estimativa básica
        
        # ============================================
        # 5. SLA FREQUÊNCIA (3 dias úteis)
        # ============================================
        # Verifica se a frequência foi lançada dentro de 3 dias úteis após a data
        sla_freq_pipeline = [
            {'$match': {
                'class_id': {'$in': list(classes_by_school.keys())},
                'date': {'$regex': f'^{academic_year}'}
            }},
            {'$project': {
                'class_id': 1,
                'date': 1,
                'created_at': 1,
                'days_diff': {
                    '$divide': [
                        {'$subtract': [
                            {'$dateFromString': {'dateString': '$created_at'}},
                            {'$dateFromString': {'dateString': '$date'}}
                        ]},
                        86400000  # ms to days
                    ]
                }
            }},
            {'$group': {
                '_id': '$class_id',
                'total': {'$sum': 1},
                'on_time': {
                    '$sum': {'$cond': [{'$lte': ['$days_diff', 3]}, 1, 0]}
                }
            }}
        ]
        try:
            async for doc in current_db.attendance.aggregate(sla_freq_pipeline):
                school_id = classes_by_school.get(doc['_id'])
                if school_id and school_id in schools:
                    schools[school_id]['attendance_records_total'] += doc['total']
                    schools[school_id]['attendance_on_time'] += doc['on_time']
        except Exception:
            # Se o cálculo falhar (dados inconsistentes), usa 100% como fallback
            for school_id in school_ids:
                schools[school_id]['attendance_on_time'] = schools[school_id]['attendance_records_total'] = 1
        
        # ============================================
        # 6. SLA NOTAS (7 dias)
        # ============================================
        # Como não temos "data da avaliação", usamos data de criação vs data limite do bimestre
        # Por simplicidade, consideramos 100% até implementar datas limite
        for school_id in school_ids:
            total_grades = school_grade_data[school_id]['count']
            schools[school_id]['grades_records_total'] = total_grades
            schools[school_id]['grades_on_time'] = total_grades  # Placeholder: 100%
        
        # ============================================
        # 7. DISTORÇÃO IDADE-SÉRIE (informativo)
        # ============================================
        # Busca alunos com data de nascimento para calcular distorção
        # Regra: 1º ano = 6 anos, 2º ano = 7 anos, etc.
        grade_expected_age = {
            'Berçário I': 0, 'Berçário II': 1,
            'Maternal I': 2, 'Maternal II': 3,
            'Pré I': 4, 'Pré II': 5,
            '1º Ano': 6, '2º Ano': 7, '3º Ano': 8, '4º Ano': 9, '5º Ano': 10,
            '6º Ano': 11, '7º Ano': 12, '8º Ano': 13, '9º Ano': 14,
            '1ª Etapa': 15, '2ª Etapa': 16, '3ª Etapa': 17, '4ª Etapa': 18
        }
        
        # Busca turmas com série
        class_grades = {}
        async for cls in current_db.classes.find(
            {'school_id': {'$in': school_ids}, 'academic_year': year_filter(academic_year)},
            {'id': 1, 'school_id': 1, 'grade_level': 1}
        ):
            class_grades[cls['id']] = {
                'school_id': cls['school_id'],
                'grade_level': cls.get('grade_level', '')
            }
        
        # Busca alunos com turma e data de nascimento
        students_with_age = []
        async for student in current_db.students.find(
            {
                'school_id': {'$in': school_ids},
                'birth_date': {'$exists': True, '$ne': None},
                'status': {'$in': ['active', 'Active', 'Ativo', 'ativo', None]}
            },
            {'id': 1, 'school_id': 1, 'class_id': 1, 'birth_date': 1}
        ):
            if student.get('birth_date') and student.get('class_id'):
                students_with_age.append(student)
        
        # Calcula distorção
        current_year = academic_year
        for student in students_with_age:
            school_id = student['school_id']
            class_id = student['class_id']
            birth_date_str = student['birth_date']
            
            if school_id not in schools:
                continue
            
            schools[school_id]['students_with_birthdate'] += 1
            
            class_info = class_grades.get(class_id, {})
            grade_level = class_info.get('grade_level', '')
            expected_age = grade_expected_age.get(grade_level)
            
            if expected_age is not None:
                try:
                    # Parse birth_date (formato dd/mm/aaaa ou yyyy-mm-dd)
                    if '/' in birth_date_str:
                        parts = birth_date_str.split('/')
                        birth_year = int(parts[2])
                    else:
                        birth_year = int(birth_date_str.split('-')[0])
                    
                    student_age = current_year - birth_year
                    # Distorção: 2+ anos acima da idade esperada
                    if student_age >= expected_age + 2:
                        schools[school_id]['age_distortion_count'] += 1
                except (ValueError, IndexError):
                    pass
        
        # ============================================
        # CÁLCULO DO SCORE V2.1 FINAL
        # ============================================
        result = []
        
        for school_id, data in schools.items():
            # --- INDICADORES NORMALIZADOS (0-100) ---
            
            # 1. Nota Média (0-10 → 0-100)
            nota_100 = (data['avg_grade'] / 10) * 100 if data['avg_grade'] else 0
            
            # 2. Taxa de Aprovação
            aprovacao_100 = (data['approved_count'] / data['evaluated_count'] * 100) if data['evaluated_count'] > 0 else 0
            
            # 3. Ganho (Evolução Bimestral)
            # Calcula delta entre bimestres consecutivos
            ganho_100 = 50  # Neutro se não houver dados
            if bimestre and bimestre > 1:
                bim_anterior = f'grade_b{bimestre-1}_avg'
                bim_atual = f'grade_b{bimestre}_avg'
                avg_anterior = data.get(bim_anterior, 0)
                avg_atual = data.get(bim_atual, 0)
                if avg_anterior > 0 and avg_atual > 0:
                    delta = avg_atual - avg_anterior
                    ganho_100 = max(0, min(100, 50 + delta * 25))
            else:
                # Sem bimestre específico: usa média de evolução B1→B2, B2→B3, B3→B4
                deltas = []
                if data['grade_b1_avg'] > 0 and data['grade_b2_avg'] > 0:
                    deltas.append(data['grade_b2_avg'] - data['grade_b1_avg'])
                if data['grade_b2_avg'] > 0 and data['grade_b3_avg'] > 0:
                    deltas.append(data['grade_b3_avg'] - data['grade_b2_avg'])
                if data['grade_b3_avg'] > 0 and data['grade_b4_avg'] > 0:
                    deltas.append(data['grade_b4_avg'] - data['grade_b3_avg'])
                if deltas:
                    avg_delta = sum(deltas) / len(deltas)
                    ganho_100 = max(0, min(100, 50 + avg_delta * 25))
            
            # 4. Frequência Média
            frequencia_100 = (data['attendance_present'] / data['attendance_total'] * 100) if data['attendance_total'] > 0 else 0
            
            # 5. Retenção (Anti-evasão)
            # 100 - (dropouts / matrículas_inicio) × 100
            retencao_100 = 100 - (data['dropouts'] / data['enrollments_start'] * 100) if data['enrollments_start'] > 0 else 100
            
            # 6. Cobertura Curricular (proxy)
            cobertura_100 = (data['learning_objects_count'] / data['expected_classes'] * 100) if data['expected_classes'] > 0 else 0
            cobertura_100 = min(100, cobertura_100)  # Cap em 100%
            
            # 7. SLA Frequência (3 dias úteis)
            sla_freq_100 = (data['attendance_on_time'] / data['attendance_records_total'] * 100) if data['attendance_records_total'] > 0 else 100
            
            # 8. SLA Notas (7 dias)
            sla_notas_100 = (data['grades_on_time'] / data['grades_records_total'] * 100) if data['grades_records_total'] > 0 else 100
            
            # --- SCORE FINAL V2.1 ---
            # Aprendizagem (45): Nota(25) + Aprovação(10) + Ganho(10)
            # Permanência (35): Frequência(25) + Retenção(10)
            # Gestão (20): Cobertura(10) + SLA_Freq(5) + SLA_Notas(5)
            
            score_aprendizagem = (nota_100 * 0.25) + (aprovacao_100 * 0.10) + (ganho_100 * 0.10)
            score_permanencia = (frequencia_100 * 0.25) + (retencao_100 * 0.10)
            score_gestao = (cobertura_100 * 0.10) + (sla_freq_100 * 0.05) + (sla_notas_100 * 0.05)
            
            score_total = score_aprendizagem + score_permanencia + score_gestao
            
            # --- DISTORÇÃO IDADE-SÉRIE (informativo) ---
            distorcao_pct = (data['age_distortion_count'] / data['students_with_birthdate'] * 100) if data['students_with_birthdate'] > 0 else 0
            
            result.append({
                'school_id': school_id,
                'school_name': data['name'],
                'score': round(score_total, 1),
                # Breakdown por bloco
                'score_aprendizagem': round(score_aprendizagem, 1),
                'score_permanencia': round(score_permanencia, 1),
                'score_gestao': round(score_gestao, 1),
                # Indicadores detalhados
                'indicators': {
                    'nota_media': round(data['avg_grade'], 2),
                    'nota_100': round(nota_100, 1),
                    'aprovacao_pct': round(aprovacao_100, 1),
                    'ganho_100': round(ganho_100, 1),
                    'frequencia_pct': round(frequencia_100, 1),
                    'retencao_pct': round(retencao_100, 1),
                    'cobertura_pct': round(cobertura_100, 1),
                    'sla_frequencia_pct': round(sla_freq_100, 1),
                    'sla_notas_pct': round(sla_notas_100, 1),
                    'distorcao_idade_serie_pct': round(distorcao_pct, 1),
                },
                # Dados brutos
                'raw_data': {
                    'enrollments_active': data['enrollments_active'],
                    'enrollments_start': data['enrollments_start'],
                    'dropouts': data['dropouts'],
                    'approved_count': data['approved_count'],
                    'evaluated_count': data['evaluated_count'],
                    'attendance_present': data['attendance_present'],
                    'attendance_total': data['attendance_total'],
                    'learning_objects_count': data['learning_objects_count'],
                    'age_distortion_count': data['age_distortion_count'],
                    'students_with_birthdate': data['students_with_birthdate'],
                },
                # Médias bimestrais para análise de evolução
                'grade_evolution': {
                    'b1': data['grade_b1_avg'],
                    'b2': data['grade_b2_avg'],
                    'b3': data['grade_b3_avg'],
                    'b4': data['grade_b4_avg'],
                }
            })
        
        result.sort(key=lambda x: x['score'], reverse=True)
        return result[:limit]
    
    @router.get("/students/performance")
    async def get_students_performance(
        request: Request,
        academic_year: int = Query(..., description="Ano letivo"),
        school_id: Optional[str] = Query(None),
        class_id: Optional[str] = Query(None),
        limit: int = Query(20, description="Limite de resultados")
    ):
        """
        Retorna desempenho individual dos alunos
        """
        current_db = get_current_db(request)
        user = await AuthMiddleware.get_current_user(request)
        
        is_global = user.get('role') in ['admin', 'admin_teste', 'semed']
        user_school_ids = user.get('school_ids', []) or []
        if user.get('school_links'):
            user_school_ids = [link.get('school_id') for link in user.get('school_links', [])]
        
        # Filtro de matrículas
        enrollment_filter = {
            'academic_year': year_filter(academic_year),
            'status': {'$in': ['active', 'ativo', 'Ativo', None]}
        }
        
        if class_id:
            enrollment_filter['class_id'] = class_id
        if school_id:
            enrollment_filter['school_id'] = school_id
        elif not is_global and user_school_ids:
            enrollment_filter['school_id'] = {'$in': user_school_ids}
        
        # Buscar matrículas
        enrollments = await current_db.enrollments.find(
            enrollment_filter,
            {'student_id': 1, 'class_id': 1, 'school_id': 1}
        ).to_list(None)
        
        if not enrollments:
            return []
        
        student_ids = [e['student_id'] for e in enrollments]
        enrollment_map = {e['student_id']: e for e in enrollments}
        
        # Buscar dados dos alunos
        students = {}
        async for student in current_db.students.find(
            {'id': {'$in': student_ids}},
            {'id': 1, 'name': 1}
        ):
            students[student['id']] = {
                'name': student['name'],
                'class_id': enrollment_map.get(student['id'], {}).get('class_id'),
                'avg_grade': 0,
                'attendance_rate': 0,
                'total_grades': 0,
                'total_attendance': 0
            }
        
        # Notas por aluno
        grades_pipeline = [
            {'$match': {
                'student_id': {'$in': student_ids},
                'academic_year': year_filter(academic_year)
            }},
            {'$group': {
                '_id': '$student_id',
                'avg_grade': {'$avg': '$grade'},
                'total': {'$sum': 1}
            }}
        ]
        async for doc in current_db.grades.aggregate(grades_pipeline):
            if doc['_id'] in students:
                students[doc['_id']]['avg_grade'] = round(doc['avg_grade'] or 0, 1)
                students[doc['_id']]['total_grades'] = doc['total']
        
        # Frequência por aluno
        attendance_pipeline = [
            {'$match': {
                'student_id': {'$in': student_ids},
                'date': {'$regex': f'^{academic_year}'}
            }},
            {'$group': {
                '_id': '$student_id',
                'total': {'$sum': 1},
                'present': {
                    '$sum': {'$cond': [{'$in': ['$status', ['present', 'justified']]}, 1, 0]}
                }
            }}
        ]
        async for doc in current_db.attendance.aggregate(attendance_pipeline):
            if doc['_id'] in students and doc['total'] > 0:
                students[doc['_id']]['attendance_rate'] = round(doc['present'] / doc['total'] * 100, 1)
                students[doc['_id']]['total_attendance'] = doc['total']
        
        # Buscar nomes das turmas
        class_ids = list(set(s['class_id'] for s in students.values() if s['class_id']))
        classes = {}
        async for cls in current_db.classes.find({'id': {'$in': class_ids}}, {'id': 1, 'name': 1}):
            classes[cls['id']] = cls['name']
        
        result = []
        for student_id, data in students.items():
            result.append({
                'student_id': student_id,
                'student_name': data['name'],
                'class_name': classes.get(data['class_id'], 'N/A'),
                'avg_grade': data['avg_grade'],
                'attendance_rate': data['attendance_rate'],
                'total_grades': data['total_grades'],
                'total_attendance': data['total_attendance']
            })
        
        # Ordenar por média de nota (decrescente)
        result.sort(key=lambda x: x['avg_grade'], reverse=True)
        return result[:limit]
    
    @router.get("/distribution/grades")
    async def get_grades_distribution(
        request: Request,
        academic_year: int = Query(..., description="Ano letivo"),
        school_id: Optional[str] = Query(None),
        class_id: Optional[str] = Query(None)
    ):
        """
        Retorna distribuição de notas por faixa
        """
        current_db = get_current_db(request)
        user = await AuthMiddleware.get_current_user(request)
        
        is_global = user.get('role') in ['admin', 'admin_teste', 'semed']
        user_school_ids = user.get('school_ids', []) or []
        if user.get('school_links'):
            user_school_ids = [link.get('school_id') for link in user.get('school_links', [])]
        
        match_filter = {
            'academic_year': year_filter(academic_year)
        }
        
        if class_id:
            match_filter['class_id'] = class_id
        elif school_id or (not is_global and user_school_ids):
            school_ids_to_filter = [school_id] if school_id else user_school_ids
            classes_in_school = await current_db.classes.find(
                {'school_id': {'$in': school_ids_to_filter}},
                {'id': 1}
            ).to_list(None)
            class_ids = [c['id'] for c in classes_in_school]
            if class_ids:
                match_filter['class_id'] = {'$in': class_ids}
        
        pipeline = [
            {'$match': match_filter},
            {'$bucket': {
                'groupBy': '$grade',
                'boundaries': [0, 3, 5, 6, 7, 8, 9, 10.1],
                'default': 'other',
                'output': {
                    'count': {'$sum': 1}
                }
            }}
        ]
        
        boundaries_labels = {
            0: '0-2.9',
            3: '3-4.9',
            5: '5-5.9',
            6: '6-6.9',
            7: '7-7.9',
            8: '8-8.9',
            9: '9-10'
        }
        
        result = []
        async for doc in current_db.grades.aggregate(pipeline):
            boundary = doc['_id']
            if boundary != 'other':
                result.append({
                    'range': boundaries_labels.get(boundary, str(boundary)),
                    'count': doc['count'],
                    'boundary': boundary
                })
        
        # Ordenar por boundary
        result.sort(key=lambda x: x.get('boundary', 0))
        return result
    
    return router
