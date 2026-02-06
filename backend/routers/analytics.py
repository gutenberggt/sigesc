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
        limit: int = Query(10, description="Limite de resultados")
    ):
        """
        Retorna ranking das escolas por desempenho
        """
        current_db = get_current_db(request)
        user = await AuthMiddleware.get_current_user(request)
        
        is_global = user.get('role') in ['admin', 'admin_teste', 'semed']
        user_school_ids = user.get('school_ids', []) or []
        if user.get('school_links'):
            user_school_ids = [link.get('school_id') for link in user.get('school_links', [])]
        
        # Buscar todas as escolas
        school_filter = {'status': 'active'}
        if not is_global and user_school_ids:
            school_filter['id'] = {'$in': user_school_ids}
        
        schools = {}
        async for school in current_db.schools.find(school_filter, {'id': 1, 'name': 1}):
            schools[school['id']] = {
                'name': school['name'],
                'enrollments': 0,
                'avg_attendance': 0,
                'avg_grade': 0
            }
        
        if not schools:
            return []
        
        school_ids = list(schools.keys())
        
        # Matrículas por escola
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
                schools[doc['_id']]['enrollments'] = doc['count']
        
        # Frequência por escola
        attendance_pipeline = [
            {'$match': {
                'school_id': {'$in': school_ids},
                'date': {'$regex': f'^{academic_year}'}
            }},
            {'$group': {
                '_id': '$school_id',
                'total': {'$sum': 1},
                'present': {
                    '$sum': {'$cond': [{'$in': ['$status', ['present', 'justified']]}, 1, 0]}
                }
            }}
        ]
        async for doc in current_db.attendance.aggregate(attendance_pipeline):
            if doc['_id'] in schools and doc['total'] > 0:
                schools[doc['_id']]['avg_attendance'] = round(doc['present'] / doc['total'] * 100, 1)
        
        # Notas por escola (através das turmas)
        classes_map = {}
        async for cls in current_db.classes.find(
            {'school_id': {'$in': school_ids}, 'academic_year': year_filter(academic_year)},
            {'id': 1, 'school_id': 1}
        ):
            classes_map[cls['id']] = cls['school_id']
        
        if classes_map:
            grades_pipeline = [
                {'$match': {
                    'class_id': {'$in': list(classes_map.keys())},
                    'academic_year': year_filter(academic_year)
                }},
                {'$group': {
                    '_id': '$class_id',
                    'avg_grade': {'$avg': '$grade'}
                }}
            ]
            
            school_grades = {}
            school_grade_counts = {}
            async for doc in current_db.grades.aggregate(grades_pipeline):
                school_id = classes_map.get(doc['_id'])
                if school_id:
                    if school_id not in school_grades:
                        school_grades[school_id] = 0
                        school_grade_counts[school_id] = 0
                    school_grades[school_id] += doc['avg_grade'] or 0
                    school_grade_counts[school_id] += 1
            
            for school_id, total in school_grades.items():
                if school_grade_counts[school_id] > 0:
                    schools[school_id]['avg_grade'] = round(total / school_grade_counts[school_id], 1)
        
        # ============================================
        # CÁLCULO DO SCORE - RANKING DE ESCOLAS
        # ============================================
        # O Score é uma pontuação de 0 a 100 que indica o desempenho geral da escola.
        # 
        # COMPOSIÇÃO DO SCORE:
        # - 40% Frequência Média (0-100%)
        # - 40% Nota/Conceito Médio (0-10, normalizado para 0-100)
        # - 20% Taxa de Ocupação (matrículas / capacidade estimada)
        #
        # FÓRMULA:
        # Score = (Frequência × 0.4) + (Nota × 10 × 0.4) + (Taxa_Ocupação × 0.2)
        #
        # EXEMPLO:
        # Escola com 85% frequência, nota 7.5 e 80% ocupação:
        # Score = (85 × 0.4) + (75 × 0.4) + (80 × 0.2) = 34 + 30 + 16 = 80 pontos
        # ============================================
        
        result = []
        max_enrollments = max([data['enrollments'] for data in schools.values()]) if schools else 1
        
        for school_id, data in schools.items():
            # Componentes do score
            freq_score = data['avg_attendance'] * 0.4  # 40% da frequência
            grade_score = data['avg_grade'] * 10 * 0.4  # 40% da nota (normalizada 0-100)
            
            # Taxa de ocupação relativa (comparado com a escola com mais matrículas)
            occupancy_rate = (data['enrollments'] / max_enrollments * 100) if max_enrollments > 0 else 0
            occupancy_score = occupancy_rate * 0.2  # 20% da taxa de ocupação
            
            # Score final
            score = freq_score + grade_score + occupancy_score
            
            result.append({
                'school_id': school_id,
                'school_name': data['name'],
                'enrollments': data['enrollments'],
                'avg_attendance': data['avg_attendance'],
                'avg_grade': data['avg_grade'],
                'score': round(score, 1)
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
