"""
Router para Documentos.
Extraído automaticamente de server.py.
"""

from fastapi import APIRouter, HTTPException, status, Request, Response
from fastapi.responses import StreamingResponse
from datetime import datetime, timedelta
from io import BytesIO
import logging
import unicodedata

from models import *
from auth_middleware import AuthMiddleware
from pdf_generator import (
    generate_boletim_pdf,
    generate_certificado_pdf,
    generate_declaracao_frequencia_pdf,
    generate_declaracao_matricula_pdf,
    generate_declaracao_transferencia_pdf,
    generate_ficha_individual_pdf,
    generate_livro_promocao_pdf,
)

logger = logging.getLogger(__name__)

# Cache simples para dados que raramente mudam (mantenedora, escolas)
import time as _time
_doc_cache = {}
_CACHE_TTL = 300  # 5 minutos

async def _get_cached(db_ref, collection, query, cache_key):
    now = _time.time()
    if cache_key in _doc_cache and (now - _doc_cache[cache_key]['ts']) < _CACHE_TTL:
        return _doc_cache[cache_key]['data']
    data = await db_ref[collection].find_one(query, {"_id": 0})
    _doc_cache[cache_key] = {'data': data, 'ts': now}
    return data

async def get_mantenedora_cached(db_ref):
    return await _get_cached(db_ref, 'mantenedora', {}, 'mantenedora')

async def get_school_cached(db_ref, school_id):
    return await _get_cached(db_ref, 'schools', {"id": school_id}, f'school_{school_id}')


router = APIRouter(tags=["Documentos"])


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências."""
    
    # Helper para obter DB correto (produção ou sandbox)
    def get_db_for_user(user: dict):
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db

    async def validate_student_for_document(student: dict, current_user: dict) -> tuple:
        """Valida se o aluno pode ter documentos gerados e se o usuário tem permissão."""
        if not student.get('class_id'):
            return False, "Aluno(a) sem matrícula"
        if current_user.get('role') in ['admin', 'admin_teste']:
            return True, None
        user_school_id = current_user.get('school_id')
        student_school_id = student.get('school_id')
        if user_school_id and student_school_id and user_school_id != student_school_id:
            return False, "Aluno não matriculado nesta escola"
        return True, None



    @router.get("/documents/boletim/{student_id}")
    async def generate_boletim(student_id: str, request: Request, academic_year: str = None):
        """
        Gera o Boletim Escolar do aluno em PDF

        Args:
            student_id: ID do aluno
            academic_year: Ano letivo (default: 2025)
        """
        current_user = await AuthMiddleware.get_current_user(request)

        # Buscar dados do aluno
        student = await db.students.find_one({"id": student_id}, {"_id": 0})
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        # Validar permissão para gerar documento
        is_valid, error_message = await validate_student_for_document(student, current_user)
        if not is_valid:
            raise HTTPException(status_code=403, detail=error_message)

        # Verificar se o aluno está ativo ou transferido (transferidos podem gerar boletim/ficha)
        student_status = student.get('status', 'active')
        allowed_statuses_for_docs = ['active', 'transferred']
        if student_status not in allowed_statuses_for_docs:
            status_labels = {
                'inactive': 'Inativo',
                'graduated': 'Formado',
                'deceased': 'Falecido',
                'cancelled': 'Matrícula Cancelada',
                'dropout': 'Desistente'
            }
            status_label = status_labels.get(student_status, student_status)
            raise HTTPException(
                status_code=400, 
                detail=f"Não é possível gerar documentos para este aluno. Status atual: {status_label}. Apenas alunos com status 'Ativo' ou 'Transferido' podem ter documentos gerados."
            )

        # Buscar matrícula do aluno (ativa ou transferida)
        academic_year_int_query = int(academic_year) if academic_year else datetime.now().year
        enrollment = await db.enrollments.find_one({
            "student_id": student_id,
            "status": {"$in": ["active", "transferred"]},
            "academic_year": academic_year_int_query
        }, {"_id": 0})

        if not enrollment:
            # Tentar buscar qualquer matrícula do aluno
            enrollment = await db.enrollments.find_one({
                "student_id": student_id
            }, {"_id": 0})

        # Se não houver matrícula, usar dados do próprio aluno
        if not enrollment:
            enrollment = {
                "student_id": student_id,
                "class_id": student.get("class_id"),
                "registration_number": student.get("enrollment_number", "N/A"),
                "status": "active",
                "academic_year": academic_year,
                "student_series": student.get("student_series")
            }

        # Garantir que student_series venha do aluno se a matrícula não tiver
        if not enrollment.get('student_series') and student.get('student_series'):
            enrollment['student_series'] = student['student_series']

        # Buscar turma (do enrollment ou do aluno)
        class_id = enrollment.get("class_id") or student.get("class_id")
        class_info = await db.classes.find_one({"id": class_id}, {"_id": 0})
        if not class_info:
            # Criar turma padrão se não existir
            class_info = {"name": "Turma não informada", "shift": "N/A", "school_id": student.get("school_id")}

        # Usar o ano letivo da turma em vez do parâmetro (a turma determina o ano)
        actual_academic_year = str(class_info.get("academic_year", academic_year))

        # Buscar escola
        school_id = class_info.get("school_id") or student.get("school_id")
        school = await get_school_cached(db, school_id)
        if not school:
            school = {"name": "Escola Municipal", "cnpj": "N/A", "phone": "N/A", "city": "Município"}

        # Buscar notas do aluno
        # IMPORTANTE: academic_year deve ser int para corresponder ao banco de dados
        academic_year_int = int(actual_academic_year) if actual_academic_year else 2025
        grades = await db.grades.find({
            "student_id": student_id,
            "academic_year": academic_year_int
        }, {"_id": 0}).to_list(100)

        # ===== FILTRAR COMPONENTES CURRICULARES PELA TURMA =====
        # Usar teacher_assignments para obter apenas os componentes alocados na turma
        class_assignments = await db.teacher_assignments.find(
            {"class_id": class_id, "status": {"$in": ["active", "Ativo"]}},
            {"_id": 0, "course_id": 1}
        ).to_list(100)
        assigned_course_ids = list(set(a['course_id'] for a in class_assignments if a.get('course_id')))

        if assigned_course_ids:
            # Buscar apenas os componentes alocados na turma
            filtered_courses = await db.courses.find(
                {"id": {"$in": assigned_course_ids}},
                {"_id": 0}
            ).to_list(100)
        else:
            # Fallback: se não há alocações, buscar por nível de ensino
            nivel_ensino = class_info.get('nivel_ensino')
            grade_level = enrollment.get('student_series') or class_info.get('grade_level', '')
            grade_level_lower = grade_level.lower() if grade_level else ''
            if not nivel_ensino:
                if any(x in grade_level_lower for x in ['berçário', 'bercario', 'maternal', 'pré', 'pre']):
                    nivel_ensino = 'educacao_infantil'
                elif any(x in grade_level_lower for x in ['1º ano', '2º ano', '3º ano', '4º ano', '5º ano', '1 ano', '2 ano', '3 ano', '4 ano', '5 ano']):
                    nivel_ensino = 'fundamental_anos_iniciais'
                elif any(x in grade_level_lower for x in ['6º ano', '7º ano', '8º ano', '9º ano', '6 ano', '7 ano', '8 ano', '9 ano']):
                    nivel_ensino = 'fundamental_anos_finais'
                elif any(x in grade_level_lower for x in ['eja', 'etapa']):
                    if any(x in grade_level_lower for x in ['3', '4', 'final']):
                        nivel_ensino = 'eja_final'
                    else:
                        nivel_ensino = 'eja'
            courses_query = {"nivel_ensino": nivel_ensino} if nivel_ensino else {}
            filtered_courses = await db.courses.find(courses_query, {"_id": 0}).to_list(100)

        logger.info(f"Boletim: {len(filtered_courses)} componentes para turma {class_id} (via {'teacher_assignments' if assigned_course_ids else 'fallback nivel_ensino'})")

        # Ordenar por nome
        filtered_courses.sort(key=lambda x: x.get('name', ''))

        # Se não houver componentes após filtragem, buscar todos do nível
        if not filtered_courses:
            if nivel_ensino:
                filtered_courses = await db.courses.find({
                    "nivel_ensino": nivel_ensino,
                    "$or": [
                        {"atendimento_programa": None},
                        {"atendimento_programa": {"$exists": False}}
                    ]
                }, {"_id": 0}).to_list(50)
            else:
                # Fallback: buscar todos
                filtered_courses = await db.courses.find({}, {"_id": 0}).to_list(50)

        courses = filtered_courses

        # Buscar dados da mantenedora
        mantenedora = await get_mantenedora_cached(db)

        # Buscar calendário letivo para obter os dias letivos (usar ano da turma)
        calendario_letivo = await db.calendario_letivo.find_one({
            "ano_letivo": int(actual_academic_year),
            "school_id": None  # Calendário geral
        }, {"_id": 0})

        # Calcular total de dias letivos do ano (mesmo cálculo da ficha individual)
        dias_letivos_ano = 200  # Padrão LDB
        if calendario_letivo:
            # Buscar eventos do calendário para o ano
            eventos = await db.calendar_events.find({
                "year": int(actual_academic_year)
            }, {"_id": 0}).to_list(500)

            datas_nao_letivas = set()
            datas_sabados_letivos = set()

            for evento in eventos:
                tipo = evento.get('type', '')
                data_str = evento.get('date', '')

                if tipo in ['feriado', 'recesso', 'ferias', 'nao_letivo', 'ponto_facultativo', 'conselho']:
                    try:
                        data = datetime.strptime(data_str[:10], '%Y-%m-%d').date()
                        datas_nao_letivas.add(data)
                    except:
                        pass
                elif tipo == 'sabado_letivo':
                    try:
                        data = datetime.strptime(data_str[:10], '%Y-%m-%d').date()
                        datas_sabados_letivos.add(data)
                    except:
                        pass

            def calcular_dias_letivos_periodo(inicio_str, fim_str):
                if not inicio_str or not fim_str:
                    return 0
                try:
                    inicio = datetime.strptime(str(inicio_str)[:10], '%Y-%m-%d').date()
                    fim = datetime.strptime(str(fim_str)[:10], '%Y-%m-%d').date()
                except:
                    return 0

                dias = 0
                current = inicio
                while current <= fim:
                    dia_semana = current.weekday()
                    if dia_semana < 5:
                        if current not in datas_nao_letivas:
                            dias += 1
                    elif dia_semana == 5:
                        if current in datas_sabados_letivos:
                            dias += 1
                    current += timedelta(days=1)
                return dias

            b1 = calcular_dias_letivos_periodo(calendario_letivo.get('bimestre_1_inicio'), calendario_letivo.get('bimestre_1_fim'))
            b2 = calcular_dias_letivos_periodo(calendario_letivo.get('bimestre_2_inicio'), calendario_letivo.get('bimestre_2_fim'))
            b3 = calcular_dias_letivos_periodo(calendario_letivo.get('bimestre_3_inicio'), calendario_letivo.get('bimestre_3_fim'))
            b4 = calcular_dias_letivos_periodo(calendario_letivo.get('bimestre_4_inicio'), calendario_letivo.get('bimestre_4_fim'))

            dias_letivos_ano = b1 + b2 + b3 + b4
            if dias_letivos_ano == 0:
                dias_letivos_ano = calendario_letivo.get('dias_letivos_previstos', 200) or 200

        # ===== BUSCAR DADOS DE FREQUÊNCIA (MESMA LÓGICA DA FICHA INDIVIDUAL) =====
        class_id = student.get('class_id')
        turma_integral = class_info.get('atendimento_programa', '') == 'atendimento_integral'
        attendance_records = await db.attendance.find(
            {"class_id": class_id, "academic_year": int(actual_academic_year)},
            {"_id": 0}
        ).to_list(500)

        # Separar faltas por tipo: Regular (diário) e Escola Integral (por componente)
        faltas_regular = 0
        faltas_por_componente = {}

        for att_record in attendance_records:
            period = att_record.get('period', 'regular')
            course_id = att_record.get('course_id')
            attendance_type = att_record.get('attendance_type', 'daily')

            student_records = att_record.get('records', [])
            for sr in student_records:
                if sr.get('student_id') == student_id:
                    status = sr.get('status', '')
                    if status == 'F':
                        if attendance_type == 'daily' and period == 'regular':
                            faltas_regular += 1
                        elif course_id:
                            if course_id not in faltas_por_componente:
                                faltas_por_componente[course_id] = 0
                            faltas_por_componente[course_id] += 1

        logger.info(f"Boletim: Faltas Regular={faltas_regular}, Faltas por componente={faltas_por_componente}")

        # Preparar attendance_data para o PDF
        attendance_data = {
            '_meta': {
                'faltas_regular': faltas_regular,
                'faltas_por_componente': faltas_por_componente,
                'is_escola_integral': turma_integral  # Usa atendimento da TURMA
            }
        }

        for course in courses:
            course_id = course.get('id')
            atendimento = course.get('atendimento_programa')

            if atendimento == 'atendimento_integral':
                faltas = faltas_por_componente.get(course_id, 0)
            else:
                faltas = 0

            attendance_data[course_id] = {
                'absences': faltas,
                'atendimento_programa': atendimento
            }

        # Gerar PDF
        try:
            pdf_buffer = generate_boletim_pdf(
                student=student,
                school=school,
                enrollment=enrollment,
                class_info=class_info,
                grades=grades,
                courses=courses,
                academic_year=actual_academic_year,
                mantenedora=mantenedora,
                dias_letivos_ano=dias_letivos_ano,
                calendario_letivo=calendario_letivo,
                attendance_data=attendance_data
            )

            filename = f"boletim_{student.get('full_name', 'aluno').replace(' ', '_')}_{actual_academic_year}.pdf"

            return StreamingResponse(
                pdf_buffer,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'inline; filename="{filename}"'
                }
            )
        except Exception as e:
            logger.error(f"Erro ao gerar boletim: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")


    @router.get("/documents/declaracao-matricula/{student_id}")
    async def generate_declaracao_matricula(
        student_id: str, 
        request: Request, 
        academic_year: str = None,
        purpose: str = "fins comprobatórios"
    ):
        """
        Gera a Declaração de Matrícula do aluno em PDF

        Args:
            student_id: ID do aluno
            academic_year: Ano letivo
            purpose: Finalidade da declaração
        """
        current_user = await AuthMiddleware.get_current_user(request)
        if not academic_year:
            academic_year = str(datetime.now().year)


        # Buscar dados do aluno
        student = await db.students.find_one({"id": student_id}, {"_id": 0})
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        # Validar permissão para gerar documento
        is_valid, error_message = await validate_student_for_document(student, current_user)
        if not is_valid:
            raise HTTPException(status_code=403, detail=error_message)

        # Verificar se o aluno está ativo
        student_status = student.get('status', 'active')
        if student_status != 'active':
            status_labels = {
                'inactive': 'Inativo',
                'transferred': 'Transferido',
                'graduated': 'Formado',
                'deceased': 'Falecido',
                'cancelled': 'Matrícula Cancelada',
                'dropout': 'Desistente'
            }
            status_label = status_labels.get(student_status, student_status)
            raise HTTPException(
                status_code=400, 
                detail=f"Não é possível gerar documentos para este aluno. Status atual: {status_label}. Apenas alunos com status 'Ativo' podem ter documentos gerados."
            )

        # Buscar matrícula
        enrollment = await db.enrollments.find_one({
            "student_id": student_id,
            "status": "active"
        }, {"_id": 0})

        if not enrollment:
            enrollment = await db.enrollments.find_one({
                "student_id": student_id
            }, {"_id": 0})

        # Se não houver matrícula, usar dados do próprio aluno
        if not enrollment:
            enrollment = {
                "student_id": student_id,
                "class_id": student.get("class_id"),
                "registration_number": student.get("enrollment_number", "N/A"),
                "status": "active",
                "academic_year": academic_year,
                "student_series": student.get("student_series")
            }

        # Garantir que student_series venha do aluno se a matrícula não tiver
        if not enrollment.get('student_series') and student.get('student_series'):
            enrollment['student_series'] = student['student_series']

        # Garantir que o número de matrícula seja preenchido corretamente
        # Prioridade: registration_number do enrollment > enrollment_number do aluno
        if not enrollment.get("registration_number") or enrollment.get("registration_number") == "N/A":
            enrollment["registration_number"] = student.get("enrollment_number", "N/A")

        # Buscar turma
        class_id = enrollment.get("class_id") or student.get("class_id")
        class_info = await db.classes.find_one({"id": class_id}, {"_id": 0})
        if not class_info:
            class_info = {"name": "Turma não informada", "shift": "N/A", "school_id": student.get("school_id")}

        # Usar o ano letivo da turma em vez do parâmetro (a turma determina o ano)
        actual_academic_year = str(class_info.get("academic_year", academic_year))

        # Buscar escola
        school_id = class_info.get("school_id") or student.get("school_id")
        school = await get_school_cached(db, school_id)
        if not school:
            school = {
                "name": "Escola Municipal", 
                "cnpj": "N/A", 
                "phone": "N/A", 
                "city": "Município",
                "address": "Endereço não informado"
            }

        # Buscar dados da mantenedora
        mantenedora = await get_mantenedora_cached(db)

        # Gerar PDF
        try:
            pdf_buffer = generate_declaracao_matricula_pdf(
                student=student,
                school=school,
                enrollment=enrollment,
                class_info=class_info,
                academic_year=actual_academic_year,
                purpose=purpose,
                mantenedora=mantenedora
            )

            filename = f"declaracao_matricula_{student.get('full_name', 'aluno').replace(' ', '_')}.pdf"

            return StreamingResponse(
                pdf_buffer,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'inline; filename="{filename}"'
                }
            )
        except Exception as e:
            logger.error(f"Erro ao gerar declaração: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")


    @router.get("/documents/declaracao-transferencia/{student_id}")
    async def generate_declaracao_transferencia(
        student_id: str, 
        request: Request, 
        academic_year: str = None
    ):
        """
        Gera a Declaração de Transferência do aluno em PDF
        """
        current_user = await AuthMiddleware.get_current_user(request)
        if not academic_year:
            academic_year = str(datetime.now().year)

        student = await db.students.find_one({"id": student_id}, {"_id": 0})
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        is_valid, error_message = await validate_student_for_document(student, current_user)
        if not is_valid:
            raise HTTPException(status_code=403, detail=error_message)

        # Buscar matrícula
        enrollment = await db.enrollments.find_one({
            "student_id": student_id,
            "status": "active"
        }, {"_id": 0})
        if not enrollment:
            enrollment = await db.enrollments.find_one({"student_id": student_id}, {"_id": 0})
        if not enrollment:
            enrollment = {
                "student_id": student_id,
                "class_id": student.get("class_id"),
                "registration_number": student.get("enrollment_number", "N/A"),
                "status": "active",
                "academic_year": academic_year,
                "student_series": student.get("student_series")
            }

        if not enrollment.get('student_series') and student.get('student_series'):
            enrollment['student_series'] = student['student_series']
        if not enrollment.get("registration_number") or enrollment.get("registration_number") == "N/A":
            enrollment["registration_number"] = student.get("enrollment_number", "N/A")

        # Buscar turma
        class_id = enrollment.get("class_id") or student.get("class_id")
        class_info = await db.classes.find_one({"id": class_id}, {"_id": 0})
        if not class_info:
            class_info = {"name": "Turma não informada", "shift": "N/A", "school_id": student.get("school_id")}

        actual_academic_year = str(class_info.get("academic_year", academic_year))

        # Buscar escola
        school_id = class_info.get("school_id") or student.get("school_id")
        school = await get_school_cached(db, school_id)
        if not school:
            school = {"name": "Escola Municipal", "cnpj": "N/A", "phone": "N/A", "city": "Município", "address": "Endereço não informado"}

        mantenedora = await get_mantenedora_cached(db)

        try:
            pdf_buffer = generate_declaracao_transferencia_pdf(
                student=student,
                school=school,
                enrollment=enrollment,
                class_info=class_info,
                academic_year=actual_academic_year,
                mantenedora=mantenedora
            )

            filename = f"declaracao_transferencia_{student.get('full_name', 'aluno').replace(' ', '_')}.pdf"

            return StreamingResponse(
                pdf_buffer,
                media_type="application/pdf",
                headers={"Content-Disposition": f'inline; filename="{filename}"'}
            )
        except Exception as e:
            logger.error(f"Erro ao gerar declaração de transferência: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")


    @router.get("/documents/declaracao-frequencia/{student_id}")
    async def generate_declaracao_frequencia(
        student_id: str, 
        request: Request, 
        academic_year: str = None
    ):
        """
        Gera a Declaração de Frequência do aluno em PDF

        Args:
            student_id: ID do aluno
            academic_year: Ano letivo
        """
        if not academic_year:
            academic_year = str(datetime.now().year)

        current_user = await AuthMiddleware.get_current_user(request)

        # Buscar dados do aluno
        student = await db.students.find_one({"id": student_id}, {"_id": 0})
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        # Validar permissão para gerar documento
        is_valid, error_message = await validate_student_for_document(student, current_user)
        if not is_valid:
            raise HTTPException(status_code=403, detail=error_message)

        # Verificar se o aluno está ativo
        student_status = student.get('status', 'active')
        if student_status != 'active':
            status_labels = {
                'inactive': 'Inativo',
                'transferred': 'Transferido',
                'graduated': 'Formado',
                'deceased': 'Falecido',
                'cancelled': 'Matrícula Cancelada',
                'dropout': 'Desistente'
            }
            status_label = status_labels.get(student_status, student_status)
            raise HTTPException(
                status_code=400, 
                detail=f"Não é possível gerar documentos para este aluno. Status atual: {status_label}. Apenas alunos com status 'Ativo' podem ter documentos gerados."
            )

        # Buscar matrícula
        enrollment = await db.enrollments.find_one({
            "student_id": student_id,
            "status": "active"
        }, {"_id": 0})

        if not enrollment:
            enrollment = await db.enrollments.find_one({
                "student_id": student_id
            }, {"_id": 0})

        # Se não houver matrícula, usar dados do próprio aluno
        if not enrollment:
            enrollment = {
                "student_id": student_id,
                "class_id": student.get("class_id"),
                "registration_number": student.get("enrollment_number", "N/A"),
                "status": "active",
                "academic_year": academic_year,
                "student_series": student.get("student_series")
            }

        # Garantir que student_series venha do aluno se a matrícula não tiver
        if not enrollment.get('student_series') and student.get('student_series'):
            enrollment['student_series'] = student['student_series']


        # Buscar turma
        class_id = enrollment.get("class_id") or student.get("class_id")
        class_info = await db.classes.find_one({"id": class_id}, {"_id": 0})
        if not class_info:
            class_info = {"name": "Turma não informada", "shift": "N/A", "school_id": student.get("school_id")}

        # Usar o ano letivo da turma em vez do parâmetro (a turma determina o ano)
        actual_academic_year = str(class_info.get("academic_year", academic_year))

        # Buscar escola
        school_id = class_info.get("school_id") or student.get("school_id")
        school = await get_school_cached(db, school_id)
        if not school:
            school = {
                "name": "Escola Municipal", 
                "cnpj": "N/A", 
                "phone": "N/A", 
                "city": "Município",
                "address": "Endereço não informado"
            }

        # Garantir que o número de matrícula seja preenchido corretamente
        if not enrollment.get("registration_number") or enrollment.get("registration_number") == "N/A":
            enrollment["registration_number"] = student.get("enrollment_number", "N/A")

        # Calcular dias letivos até a data de emissão
        academic_year_int = int(actual_academic_year) if actual_academic_year else datetime.now().year

        # Buscar calendário letivo
        calendario = await db.calendario_letivo.find_one(
            {"ano_letivo": academic_year_int, "school_id": None}, 
            {"_id": 0}
        )

        # Buscar eventos do calendário (feriados, sábados letivos, etc.)
        events = await db.calendar_events.find({
            "academic_year": academic_year_int
        }, {"_id": 0}).to_list(1000)

        eventos_nao_letivos = ['feriado_nacional', 'feriado_estadual', 'feriado_municipal', 'recesso_escolar']

        datas_nao_letivas = set()
        datas_sabados_letivos = set()

        for event in events:
            event_type = event.get('event_type', '')
            start_date_str = event.get('start_date')
            end_date_str = event.get('end_date') or start_date_str

            if not start_date_str:
                continue

            try:
                from datetime import timedelta
                start_date_ev = datetime.strptime(start_date_str[:10], '%Y-%m-%d').date()
                end_date_ev = datetime.strptime(end_date_str[:10], '%Y-%m-%d').date()

                current_ev = start_date_ev
                while current_ev <= end_date_ev:
                    if event_type in eventos_nao_letivos:
                        datas_nao_letivas.add(current_ev)
                    elif event_type == 'sabado_letivo':
                        datas_sabados_letivos.add(current_ev)
                    elif event.get('is_school_day', False) and current_ev.weekday() == 5:
                        datas_sabados_letivos.add(current_ev)
                    current_ev += timedelta(days=1)
            except (ValueError, TypeError):
                continue

        # Calcular dias letivos até hoje
        def calcular_dias_letivos_ate_data(calendario, data_limite):
            """Calcula dias letivos desde o início do ano até a data limite"""
            if not calendario:
                return 0

            inicio_str = calendario.get('bimestre_1_inicio')
            if not inicio_str:
                return 0

            try:
                from datetime import timedelta
                inicio = datetime.strptime(inicio_str[:10], '%Y-%m-%d').date()
                fim = data_limite
            except (ValueError, TypeError):
                return 0

            dias_letivos = 0
            current = inicio

            while current <= fim:
                dia_semana = current.weekday()

                if current in datas_sabados_letivos:
                    dias_letivos += 1
                elif dia_semana < 5:  # Seg-Sex
                    if current not in datas_nao_letivas:
                        dias_letivos += 1

                current += timedelta(days=1)

            return dias_letivos

        # Calcular dias letivos até hoje
        from datetime import date as date_type
        hoje = date_type.today()
        total_dias_letivos_ate_hoje = calcular_dias_letivos_ate_data(calendario, hoje)

        # Buscar todas as faltas do aluno
        attendances = await db.attendance.find({
            "student_id": student_id,
            "academic_year": actual_academic_year
        }, {"_id": 0}).to_list(500)

        # Calcular total de faltas
        total_faltas = sum(1 for a in attendances if a.get('status') in ['absent', 'F', 'A'])

        # Se não houver calendário configurado, usar fallback baseado na data
        if total_dias_letivos_ate_hoje == 0:
            # Calcular aproximadamente considerando 200 dias letivos por ano
            # e uma distribuição proporcional ao longo do ano
            inicio_ano = date_type(academic_year_int, 2, 1)  # Início típico em fevereiro
            fim_ano = date_type(academic_year_int, 12, 20)  # Fim típico em dezembro

            if hoje < inicio_ano:
                total_dias_letivos_ate_hoje = 0
            elif hoje > fim_ano:
                total_dias_letivos_ate_hoje = 200
            else:
                dias_transcorridos = (hoje - inicio_ano).days
                dias_totais_ano = (fim_ano - inicio_ano).days
                total_dias_letivos_ate_hoje = int(200 * dias_transcorridos / dias_totais_ano) if dias_totais_ano > 0 else 0

        # Calcular presenças: dias letivos - faltas
        total_days = total_dias_letivos_ate_hoje
        absent_days = total_faltas
        present_days = max(0, total_days - absent_days)

        # Calcular percentual de frequência
        frequency_percentage = (present_days / total_days * 100) if total_days > 0 else 100

        attendance_data = {
            "total_days": total_days,
            "present_days": present_days,
            "absent_days": absent_days,
            "frequency_percentage": frequency_percentage
        }

        # Buscar dados da mantenedora
        mantenedora = await get_mantenedora_cached(db)

        # Gerar PDF
        try:
            pdf_buffer = generate_declaracao_frequencia_pdf(
                student=student,
                school=school,
                enrollment=enrollment,
                class_info=class_info,
                attendance_data=attendance_data,
                academic_year=actual_academic_year,
                period=f"ano letivo de {actual_academic_year}",
                mantenedora=mantenedora
            )

            filename = f"declaracao_frequencia_{student.get('full_name', 'aluno').replace(' ', '_')}.pdf"

            return StreamingResponse(
                pdf_buffer,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'inline; filename="{filename}"'
                }
            )
        except Exception as e:
            logger.error(f"Erro ao gerar declaração de frequência: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")


    @router.get("/documents/ficha-individual/{student_id}")
    async def get_ficha_individual(
        student_id: str,
        academic_year: int = 2025,
        request: Request = None
    ):
        """Gera a Ficha Individual do Aluno em PDF"""
        current_user = await AuthMiddleware.get_current_user(request)

        # Buscar aluno
        student = await db.students.find_one({"id": student_id}, {"_id": 0})
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        # Validar permissão para gerar documento
        is_valid, error_message = await validate_student_for_document(student, current_user)
        if not is_valid:
            raise HTTPException(status_code=403, detail=error_message)

        # Verificar se o aluno está ativo ou transferido (transferidos podem gerar ficha individual)
        student_status = student.get('status', 'active')
        allowed_statuses_for_docs = ['active', 'transferred']
        if student_status not in allowed_statuses_for_docs:
            status_labels = {
                'inactive': 'Inativo',
                'graduated': 'Formado',
                'deceased': 'Falecido',
                'cancelled': 'Matrícula Cancelada',
                'dropout': 'Desistente'
            }
            status_label = status_labels.get(student_status, student_status)
            raise HTTPException(
                status_code=400, 
                detail=f"Não é possível gerar documentos para este aluno. Status atual: {status_label}. Apenas alunos com status 'Ativo' ou 'Transferido' podem ter documentos gerados."
            )

        # Buscar escola
        school = await get_school_cached(db, student.get("school_id"))
        if not school:
            school = {"name": "Escola Municipal", "city": "Município"}

        # Buscar turma
        class_id = student.get("class_id")
        class_info = await db.classes.find_one({"id": class_id}, {"_id": 0})
        if not class_info:
            class_info = {"name": "N/A", "grade_level": "N/A", "shift": "N/A"}

        # Usar o ano letivo da turma em vez do parâmetro (a turma determina o ano)
        actual_academic_year = class_info.get("academic_year", academic_year)

        # Buscar matrícula (priorizar ativa sobre relocated)
        enrollment = await db.enrollments.find_one(
            {"student_id": student_id, "academic_year": actual_academic_year, "status": "active"},
            {"_id": 0}
        )
        if not enrollment:
            enrollment = await db.enrollments.find_one(
                {"student_id": student_id, "academic_year": actual_academic_year},
                {"_id": 0}
            )
        if not enrollment:
            enrollment = {"registration_number": student.get("enrollment_number", "N/A")}

        # Buscar notas do aluno
        grades = await db.grades.find(
            {"student_id": student_id, "academic_year": actual_academic_year},
            {"_id": 0}
        ).to_list(100)

        # Buscar componentes curriculares da turma/escola
        # Filtrar por nível de ensino - usar série do ALUNO para turmas multisseriadas
        nivel_ensino = class_info.get('nivel_ensino')
        grade_level = enrollment.get('student_series') or class_info.get('grade_level', '')
        grade_level_lower = grade_level.lower() if grade_level else ''
        school_id = student.get('school_id')

        # Se não tem nivel_ensino definido, inferir pelo grade_level
        if not nivel_ensino:
            if any(x in grade_level_lower for x in ['berçário', 'bercario', 'maternal', 'pré', 'pre']):
                nivel_ensino = 'educacao_infantil'
            elif any(x in grade_level_lower for x in ['1º ano', '2º ano', '3º ano', '4º ano', '5º ano', '1 ano', '2 ano', '3 ano', '4 ano', '5 ano']):
                nivel_ensino = 'fundamental_anos_iniciais'
            elif any(x in grade_level_lower for x in ['6º ano', '7º ano', '8º ano', '9º ano', '6 ano', '7 ano', '8 ano', '9 ano']):
                nivel_ensino = 'fundamental_anos_finais'
            elif any(x in grade_level_lower for x in ['eja', 'etapa']):
                if any(x in grade_level_lower for x in ['3', '4', 'final']):
                    nivel_ensino = 'eja_final'
                else:
                    nivel_ensino = 'eja'
            else:
                nivel_ensino = 'fundamental_anos_iniciais'  # Fallback

        # Log para debug
        logger.info(f"Ficha Individual: grade_level={grade_level}, nivel_ensino inferido={nivel_ensino}")

        # ===== FILTRAR COMPONENTES CURRICULARES PELA TURMA =====
        # Usar teacher_assignments para obter apenas os componentes alocados na turma
        class_assignments = await db.teacher_assignments.find(
            {"class_id": class_id, "status": {"$in": ["active", "Ativo"]}},
            {"_id": 0, "course_id": 1}
        ).to_list(100)
        assigned_course_ids = list(set(a['course_id'] for a in class_assignments if a.get('course_id')))

        if assigned_course_ids:
            filtered_courses = await db.courses.find(
                {"id": {"$in": assigned_course_ids}},
                {"_id": 0}
            ).to_list(100)
        else:
            # Fallback: se não há alocações, buscar por nível de ensino
            courses_filter = {"nivel_ensino": nivel_ensino} if nivel_ensino else {}
            filtered_courses = await db.courses.find(courses_filter, {"_id": 0}).to_list(100)

        logger.info(f"Ficha Individual: {len(filtered_courses)} componentes para turma {class_id} (via {'teacher_assignments' if assigned_course_ids else 'fallback nivel_ensino'})")

        # Ordenar por nome
        filtered_courses.sort(key=lambda x: x.get('name', ''))

        # Se não encontrar componentes após filtragem, buscar todos do nível sem atendimento específico
        if not filtered_courses:
            filtered_courses = await db.courses.find({
                "nivel_ensino": nivel_ensino,
                "$or": [
                    {"atendimento_programa": None},
                    {"atendimento_programa": {"$exists": False}}
                ]
            }, {"_id": 0}).to_list(100)

        courses = filtered_courses

        # Buscar dados de frequência do aluno
        # A estrutura de attendance é: {class_id, date, attendance_type, period, course_id, records: [{student_id, status}]}

        # Buscar todos os registros de frequência da turma do aluno
        turma_integral = class_info.get('atendimento_programa', '') == 'atendimento_integral'
        attendance_records = await db.attendance.find(
            {"class_id": class_id, "academic_year": actual_academic_year},
            {"_id": 0}
        ).to_list(500)

        # Separar faltas por tipo: Regular (diário) e Escola Integral (por componente)
        faltas_regular = 0  # Faltas do período regular (frequência diária)
        faltas_por_componente = {}  # Faltas por componente (escola integral)

        for att_record in attendance_records:
            period = att_record.get('period', 'regular')
            course_id = att_record.get('course_id')
            attendance_type = att_record.get('attendance_type', 'daily')

            student_records = att_record.get('records', [])
            for sr in student_records:
                if sr.get('student_id') == student_id:
                    status = sr.get('status', '')
                    if status == 'F':  # Falta
                        if attendance_type == 'daily' and period == 'regular':
                            # Frequência diária regular - soma nas faltas gerais
                            faltas_regular += 1
                        elif course_id:
                            # Frequência por componente (escola integral)
                            if course_id not in faltas_por_componente:
                                faltas_por_componente[course_id] = 0
                            faltas_por_componente[course_id] += 1

        logger.info(f"Ficha Individual: Faltas Regular={faltas_regular}, Faltas por componente={faltas_por_componente}")

        # Preparar attendance_data com informações detalhadas
        # Adicionar metadados sobre faltas para o PDF generator usar
        attendance_data = {
            '_meta': {
                'faltas_regular': faltas_regular,
                'faltas_por_componente': faltas_por_componente,
                'is_escola_integral': turma_integral  # Usa atendimento da TURMA
            }
        }

        # Preencher dados por componente
        for course in courses:
            course_id = course.get('id')
            atendimento = course.get('atendimento_programa')

            if atendimento == 'atendimento_integral':
                # Componente de escola integral - faltas individuais
                faltas = faltas_por_componente.get(course_id, 0)
            else:
                # Componente regular - todas as faltas vão para Língua Portuguesa
                faltas = 0  # Será preenchido apenas para Língua Portuguesa no PDF

            attendance_data[course_id] = {
                'absences': faltas,
                'atendimento_programa': atendimento
            }

        # Buscar dados da mantenedora
        mantenedora = await get_mantenedora_cached(db)

        # Buscar calendário letivo para dias letivos e data fim do 4º bimestre
        calendario_letivo = await db.calendario_letivo.find_one({
            "ano_letivo": actual_academic_year
        }, {"_id": 0})

        # Calcular dias letivos reais com base nos períodos bimestrais e eventos
        dias_letivos_calculados = None
        if calendario_letivo:
            # Buscar eventos do calendário para o ano
            eventos = await db.calendar_events.find({
                "year": actual_academic_year
            }, {"_id": 0}).to_list(500)

            # Identificar datas não letivas (feriados, recessos, etc.)
            datas_nao_letivas = set()
            datas_sabados_letivos = set()

            for evento in eventos:
                tipo = evento.get('type', '')
                data_str = evento.get('date', '')

                # Tipos que removem dias letivos
                if tipo in ['feriado', 'recesso', 'ferias', 'nao_letivo', 'ponto_facultativo', 'conselho']:
                    try:
                        data = datetime.strptime(data_str[:10], '%Y-%m-%d').date()
                        datas_nao_letivas.add(data)
                    except:
                        pass
                # Sábados letivos
                elif tipo == 'sabado_letivo':
                    try:
                        data = datetime.strptime(data_str[:10], '%Y-%m-%d').date()
                        datas_sabados_letivos.add(data)
                    except:
                        pass

            def calcular_dias_letivos_periodo(inicio_str, fim_str):
                if not inicio_str or not fim_str:
                    return 0
                try:
                    inicio = datetime.strptime(str(inicio_str)[:10], '%Y-%m-%d').date()
                    fim = datetime.strptime(str(fim_str)[:10], '%Y-%m-%d').date()
                except:
                    return 0

                dias = 0
                current = inicio
                while current <= fim:
                    dia_semana = current.weekday()
                    if dia_semana < 5:  # Segunda a sexta
                        if current not in datas_nao_letivas:
                            dias += 1
                    elif dia_semana == 5:  # Sábado
                        if current in datas_sabados_letivos:
                            dias += 1
                    current += timedelta(days=1)
                return dias

            b1 = calcular_dias_letivos_periodo(calendario_letivo.get('bimestre_1_inicio'), calendario_letivo.get('bimestre_1_fim'))
            b2 = calcular_dias_letivos_periodo(calendario_letivo.get('bimestre_2_inicio'), calendario_letivo.get('bimestre_2_fim'))
            b3 = calcular_dias_letivos_periodo(calendario_letivo.get('bimestre_3_inicio'), calendario_letivo.get('bimestre_3_fim'))
            b4 = calcular_dias_letivos_periodo(calendario_letivo.get('bimestre_4_inicio'), calendario_letivo.get('bimestre_4_fim'))

            dias_letivos_calculados = b1 + b2 + b3 + b4
            logger.info(f"Ficha Individual: Dias letivos calculados = {dias_letivos_calculados} (B1={b1}, B2={b2}, B3={b3}, B4={b4})")

        # Adicionar dias letivos calculados ao calendário
        if calendario_letivo:
            calendario_letivo['dias_letivos_calculados'] = dias_letivos_calculados

        # ===== DETECTAR REMANEJAMENTO (mesma escola) =====
        relocated_enrollments = await db.enrollments.find({
            "student_id": student_id,
            "academic_year": actual_academic_year,
            "status": "relocated"
        }, {"_id": 0}).to_list(10)

        # Filtrar apenas remanejamentos dentro da mesma escola
        origin_data_list = []
        current_school_id = class_info.get("school_id") or student.get("school_id")
        for rel_enroll in relocated_enrollments:
            origin_class = await db.classes.find_one({"id": rel_enroll.get("class_id")}, {"_id": 0})
            if origin_class and origin_class.get("school_id") == current_school_id:
                origin_data_list.append({
                    "enrollment": rel_enroll,
                    "class_info": origin_class
                })

        if origin_data_list:
            # REMANEJAMENTO DETECTADO - Gerar 2 fichas (destino + origem)
            from PyPDF2 import PdfMerger
            logger.info(f"Ficha Individual: Remanejamento detectado - {len(origin_data_list)} turma(s) de origem")

            # Coletar class_ids de origem
            origin_class_ids = [od["class_info"].get("id") or od["enrollment"].get("class_id") for od in origin_data_list]

            # ===== PÁGINA 1: FICHA DESTINO (notas combinadas + frequências somadas) =====
            # Notas: a query atual já busca TODAS as notas do aluno no ano (sem filtro de class_id)
            # Então `grades` já contém as notas de ambas as turmas - perfeito para destino
            
            # Frequência destino: somar faltas da turma atual + turmas de origem
            combined_faltas_regular = faltas_regular
            combined_faltas_por_componente = dict(faltas_por_componente)

            for origin_cid in origin_class_ids:
                origin_att_records = await db.attendance.find(
                    {"class_id": origin_cid, "academic_year": actual_academic_year},
                    {"_id": 0}
                ).to_list(500)
                for att_record in origin_att_records:
                    period = att_record.get('period', 'regular')
                    o_course_id = att_record.get('course_id')
                    attendance_type = att_record.get('attendance_type', 'daily')
                    for sr in att_record.get('records', []):
                        if sr.get('student_id') == student_id and sr.get('status') == 'F':
                            if attendance_type == 'daily' and period == 'regular':
                                combined_faltas_regular += 1
                            elif o_course_id:
                                combined_faltas_por_componente[o_course_id] = combined_faltas_por_componente.get(o_course_id, 0) + 1

            # Montar attendance_data combinado para destino
            combined_attendance_data = {
                '_meta': {
                    'faltas_regular': combined_faltas_regular,
                    'faltas_por_componente': combined_faltas_por_componente,
                    'is_escola_integral': turma_integral
                }
            }
            for course in courses:
                cid = course.get('id')
                atendimento_c = course.get('atendimento_programa')
                if atendimento_c == 'atendimento_integral':
                    f = combined_faltas_por_componente.get(cid, 0)
                else:
                    f = 0
                combined_attendance_data[cid] = {'absences': f, 'atendimento_programa': atendimento_c}

            # Gerar ficha DESTINO
            pdf_destino = generate_ficha_individual_pdf(
                student=student,
                school=school,
                class_info=class_info,
                enrollment=enrollment,
                academic_year=actual_academic_year,
                grades=grades,
                courses=courses,
                attendance_data=combined_attendance_data,
                mantenedora=mantenedora,
                calendario_letivo=calendario_letivo
            )

            # ===== PÁGINA 2: FICHA ORIGEM (apenas notas/frequências da turma de origem) =====
            merger = PdfMerger()
            merger.append(pdf_destino)

            for origin_data in origin_data_list:
                origin_class_info = origin_data["class_info"]
                origin_enrollment = origin_data["enrollment"]
                origin_class_id = origin_class_info.get("id") or origin_enrollment.get("class_id")

                # Escola de origem (pode ser a mesma)
                origin_school_id = origin_class_info.get("school_id")
                origin_school = await get_school_cached(db, origin_school_id)
                if not origin_school:
                    origin_school = school

                # Notas: filtrar apenas da turma de origem
                origin_grades = [g for g in grades if g.get('class_id') == origin_class_id]

                # Frequência: apenas da turma de origem
                origin_att_records = await db.attendance.find(
                    {"class_id": origin_class_id, "academic_year": actual_academic_year},
                    {"_id": 0}
                ).to_list(500)
                origin_faltas_regular = 0
                origin_faltas_por_componente = {}
                for att_record in origin_att_records:
                    period = att_record.get('period', 'regular')
                    o_course_id = att_record.get('course_id')
                    attendance_type = att_record.get('attendance_type', 'daily')
                    for sr in att_record.get('records', []):
                        if sr.get('student_id') == student_id and sr.get('status') == 'F':
                            if attendance_type == 'daily' and period == 'regular':
                                origin_faltas_regular += 1
                            elif o_course_id:
                                origin_faltas_por_componente[o_course_id] = origin_faltas_por_componente.get(o_course_id, 0) + 1

                # Componentes curriculares da turma de origem
                origin_nivel_ensino = origin_class_info.get('nivel_ensino')
                origin_grade_level = origin_enrollment.get('student_series') or origin_class_info.get('grade_level', '')
                origin_gl_lower = origin_grade_level.lower() if origin_grade_level else ''
                if not origin_nivel_ensino:
                    if any(x in origin_gl_lower for x in ['berçário', 'bercario', 'maternal', 'pré', 'pre']):
                        origin_nivel_ensino = 'educacao_infantil'
                    elif any(x in origin_gl_lower for x in ['1º ano', '2º ano', '3º ano', '4º ano', '5º ano', '1 ano', '2 ano', '3 ano', '4 ano', '5 ano']):
                        origin_nivel_ensino = 'fundamental_anos_iniciais'
                    elif any(x in origin_gl_lower for x in ['6º ano', '7º ano', '8º ano', '9º ano', '6 ano', '7 ano', '8 ano', '9 ano']):
                        origin_nivel_ensino = 'fundamental_anos_finais'
                    elif any(x in origin_gl_lower for x in ['eja', 'etapa']):
                        origin_nivel_ensino = 'eja_final' if any(x in origin_gl_lower for x in ['3', '4', 'final']) else 'eja'
                    else:
                        origin_nivel_ensino = nivel_ensino  # fallback para o mesmo nível

                origin_turma_atendimento = origin_class_info.get('atendimento_programa', '')
                origin_turma_integral = origin_turma_atendimento == 'atendimento_integral'

                origin_courses_filter = {
                    "$and": [
                        {"nivel_ensino": origin_nivel_ensino},
                        {"$or": [
                            {"school_id": {"$exists": False}},
                            {"school_id": None},
                            {"school_id": ""},
                            {"school_id": origin_school_id}
                        ]}
                    ]
                }
                origin_all_courses = await db.courses.find(origin_courses_filter, {"_id": 0}).to_list(100)

                origin_filtered_courses = []
                for oc in origin_all_courses:
                    oc_atendimento = oc.get('atendimento_programa')
                    oc_grade_levels = oc.get('grade_levels', [])
                    if oc_atendimento == 'transversal_formativa':
                        pass
                    elif oc_atendimento == 'atendimento_integral':
                        if not origin_turma_integral:
                            continue
                    elif oc_atendimento and oc_atendimento not in ['atendimento_integral', 'transversal_formativa']:
                        if origin_turma_atendimento != oc_atendimento:
                            continue
                    if oc_grade_levels and origin_grade_level and origin_grade_level not in oc_grade_levels:
                        continue
                    origin_filtered_courses.append(oc)

                origin_filtered_courses.sort(key=lambda x: x.get('name', ''))
                if not origin_filtered_courses:
                    origin_filtered_courses = courses  # fallback

                # Montar attendance_data para origem
                origin_attendance_data = {
                    '_meta': {
                        'faltas_regular': origin_faltas_regular,
                        'faltas_por_componente': origin_faltas_por_componente,
                        'is_escola_integral': origin_turma_integral
                    }
                }
                for oc in origin_filtered_courses:
                    cid = oc.get('id')
                    oc_atendimento = oc.get('atendimento_programa')
                    if oc_atendimento == 'atendimento_integral':
                        f = origin_faltas_por_componente.get(cid, 0)
                    else:
                        f = 0
                    origin_attendance_data[cid] = {'absences': f, 'atendimento_programa': oc_atendimento}

                # Gerar ficha ORIGEM
                pdf_origem = generate_ficha_individual_pdf(
                    student=student,
                    school=origin_school,
                    class_info=origin_class_info,
                    enrollment=origin_enrollment,
                    academic_year=actual_academic_year,
                    grades=origin_grades,
                    courses=origin_filtered_courses,
                    attendance_data=origin_attendance_data,
                    mantenedora=mantenedora,
                    calendario_letivo=calendario_letivo
                )
                merger.append(pdf_origem)

            # Mesclar PDFs
            merged_buffer = BytesIO()
            merger.write(merged_buffer)
            merger.close()
            merged_buffer.seek(0)

            filename = f"ficha_individual_{student.get('full_name', 'aluno').replace(' ', '_')}.pdf"
            return StreamingResponse(
                merged_buffer,
                media_type="application/pdf",
                headers={"Content-Disposition": f'inline; filename="{filename}"'}
            )

        # ===== CASO NORMAL (sem remanejamento) =====
        # Gerar PDF
        try:
            pdf_buffer = generate_ficha_individual_pdf(
                student=student,
                school=school,
                class_info=class_info,
                enrollment=enrollment,
                academic_year=actual_academic_year,
                grades=grades,
                courses=courses,
                attendance_data=attendance_data,
                mantenedora=mantenedora,
                calendario_letivo=calendario_letivo
            )

            filename = f"ficha_individual_{student.get('full_name', 'aluno').replace(' ', '_')}.pdf"

            return StreamingResponse(
                pdf_buffer,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'inline; filename="{filename}"'
                }
            )
        except Exception as e:
            logger.error(f"Erro ao gerar ficha individual: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")


    @router.get("/documents/certificado/{student_id}")
    async def get_certificado(
        student_id: str,
        academic_year: int = 2025,
        request: Request = None
    ):
        """
        Gera o Certificado de Conclusão em PDF.
        Uso exclusivo para turmas do 9º Ano e EJA 4ª Etapa.
        """
        current_user = await AuthMiddleware.get_current_user(request)

        # Buscar aluno
        student = await db.students.find_one({"id": student_id}, {"_id": 0})
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        # Validar permissão para gerar documento
        is_valid, error_message = await validate_student_for_document(student, current_user)
        if not is_valid:
            raise HTTPException(status_code=403, detail=error_message)

        # Buscar escola
        school = await get_school_cached(db, student.get("school_id"))
        if not school:
            school = {"name": "Escola Municipal", "city": "Município"}

        # Buscar turma
        class_info = await db.classes.find_one({"id": student.get("class_id")}, {"_id": 0})
        if not class_info:
            class_info = {"name": "N/A", "grade_level": "N/A", "shift": "N/A"}

        # Validar se a turma é elegível para certificado (9º Ano ou EJA 4ª Etapa)
        grade_level = str(class_info.get('grade_level', '')).lower()
        education_level = str(class_info.get('education_level', '')).lower()

        is_9ano = '9' in grade_level and 'ano' in grade_level
        is_eja_4etapa = ('eja' in education_level or 'eja' in grade_level) and ('4' in grade_level or 'etapa' in grade_level)

        if not (is_9ano or is_eja_4etapa):
            raise HTTPException(
                status_code=400, 
                detail="Certificado disponível apenas para turmas do 9º Ano ou EJA 4ª Etapa"
            )

        # Buscar matrícula
        enrollment = await db.enrollments.find_one(
            {"student_id": student_id, "academic_year": int(academic_year) if academic_year else datetime.now().year},
            {"_id": 0}
        )
        if not enrollment:
            enrollment = {"registration_number": student.get("enrollment_number", "N/A")}

        # Buscar mantenedora (para o brasão)
        mantenedora = await get_mantenedora_cached(db)

        # Gerar PDF
        try:
            pdf_buffer = generate_certificado_pdf(
                student=student,
                school=school,
                class_info=class_info,
                enrollment=enrollment,
                academic_year=academic_year,
                mantenedora=mantenedora
            )

            filename = f"certificado_{student.get('full_name', 'aluno').replace(' ', '_')}.pdf"

            return StreamingResponse(
                pdf_buffer,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'inline; filename="{filename}"'
                }
            )
        except Exception as e:
            logger.error(f"Erro ao gerar certificado: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")


    @router.get("/documents/promotion/{class_id}")
    async def get_livro_promocao_pdf(
        class_id: str,
        academic_year: int = 2025,
        request: Request = None
    ):
        """
        Gera o PDF do Livro de Promoção para uma turma.

        O Livro de Promoção contém:
        - Lista de alunos com notas de todos os bimestres
        - Recuperações semestrais
        - Total de pontos e média final por componente
        - Resultado final (Aprovado/Reprovado/etc)
        """
        current_user = await AuthMiddleware.get_current_user(request)

        try:
            # Buscar turma
            class_info = await db.classes.find_one({"id": class_id}, {"_id": 0})
            if not class_info:
                raise HTTPException(status_code=404, detail="Turma não encontrada")

            # Buscar escola
            school = await get_school_cached(db, class_info.get("school_id"))
            if not school:
                school = {"name": "Escola Municipal"}

            # Buscar mantenedora
            mantenedora = await get_mantenedora_cached(db)

            # Buscar matrículas da turma
            enrollments = await db.enrollments.find({
                "class_id": class_id
            }, {"_id": 0}).to_list(1000)

            if not enrollments:
                raise HTTPException(status_code=404, detail="Nenhum aluno matriculado nesta turma")

            student_ids = [e.get("student_id") for e in enrollments]

            # Buscar dados dos alunos
            students = await db.students.find({
                "id": {"$in": student_ids}
            }, {"_id": 0}).to_list(1000)

            # Criar mapa de alunos por ID
            students_map = {s.get("id"): s for s in students}

            # Buscar componentes curriculares
            nivel_ensino = class_info.get('education_level', '')
            grade_level = class_info.get('grade_level', '')

            courses = await db.courses.find({
                "$or": [
                    {"grade_levels": grade_level},
                    {"grade_levels": {"$size": 0}},
                    {"grade_levels": {"$exists": False}}
                ]
            }, {"_id": 0}).to_list(100)

            # Se não encontrar, buscar todos
            if not courses:
                courses = await db.courses.find({}, {"_id": 0}).to_list(100)

            # Criar mapa de componentes
            courses_map = {c.get("id"): c for c in courses}

            # Processar dados de cada aluno
            students_data = []

            for enrollment in enrollments:
                student_id = enrollment.get("student_id")
                student = students_map.get(student_id)

                if not student:
                    continue

                # Buscar notas do aluno
                grades = await db.grades.find({
                    "student_id": student_id,
                    "academic_year": academic_year
                }, {"_id": 0}).to_list(500)

                # Organizar notas por componente
                grades_by_component = {}

                for grade in grades:
                    course_id = grade.get("course_id")
                    if course_id not in grades_by_component:
                        grades_by_component[course_id] = {
                            "b1": None, "b2": None, "b3": None, "b4": None,
                            "rec1": None, "rec2": None,
                            "totalPoints": None, "finalAverage": None
                        }

                    # As notas já vêm com os campos b1, b2, b3, b4, rec_s1, rec_s2
                    grades_by_component[course_id]["b1"] = grade.get("b1")
                    grades_by_component[course_id]["b2"] = grade.get("b2")
                    grades_by_component[course_id]["b3"] = grade.get("b3")
                    grades_by_component[course_id]["b4"] = grade.get("b4")
                    grades_by_component[course_id]["rec1"] = grade.get("rec_s1")
                    grades_by_component[course_id]["rec2"] = grade.get("rec_s2")

                # Calcular total e média para cada componente
                for course_id, comp_grades in grades_by_component.items():
                    b1 = comp_grades.get("b1") or 0
                    b2 = comp_grades.get("b2") or 0
                    b3 = comp_grades.get("b3") or 0
                    b4 = comp_grades.get("b4") or 0
                    rec1 = comp_grades.get("rec1")
                    rec2 = comp_grades.get("rec2")

                    # Aplicar recuperação 1º semestre (substitui menor entre B1 e B2)
                    if rec1 is not None:
                        if b1 <= b2 and rec1 > b1:
                            b1 = rec1
                        elif b2 < b1 and rec1 > b2:
                            b2 = rec1

                    # Aplicar recuperação 2º semestre (substitui menor entre B3 e B4)
                    if rec2 is not None:
                        if b3 <= b4 and rec2 > b3:
                            b3 = rec2
                        elif b4 < b3 and rec2 > b4:
                            b4 = rec2

                    # Calcular total e média
                    total = b1 + b2 + b3 + b4
                    media = total / 4

                    comp_grades["totalPoints"] = total
                    comp_grades["finalAverage"] = media

                # Determinar resultado final
                result = "CURSANDO"
                status = (enrollment.get("status") or "").lower()

                if status in ["desistencia", "desistente"]:
                    result = "DESISTENTE"
                elif status in ["transferencia", "transferido"]:
                    result = "TRANSFERIDO"
                else:
                    # Verificar médias
                    averages = [g.get("finalAverage") for g in grades_by_component.values() if g.get("finalAverage") is not None]
                    if averages:
                        all_approved = all(avg >= 6 for avg in averages)
                        if all_approved:
                            result = "APROVADO"
                        else:
                            failed_count = sum(1 for avg in averages if avg < 6)
                            if failed_count >= 3:
                                result = "REPROVADO"

                # Adicionar dados do aluno
                students_data.append({
                    "studentId": student_id,
                    "studentName": student.get("full_name", ""),
                    "sex": "M" if student.get("sex", "").lower() in ["m", "masculino"] else "F",
                    "grades": grades_by_component,
                    "result": result
                })

            # Ordenar por nome
            students_data.sort(key=lambda x: unicodedata.normalize('NFD', x.get("studentName", "")).encode('ascii', 'ignore').decode('ascii'))

            # Gerar PDF
            pdf_buffer = generate_livro_promocao_pdf(
                school=school,
                class_info=class_info,
                students_data=students_data,
                courses=courses,
                academic_year=academic_year,
                mantenedora=mantenedora
            )

            # Gerar nome do arquivo
            turma_nome = class_info.get("name", "turma").replace(" ", "_")
            filename = f"livro_promocao_{turma_nome}_{academic_year}.pdf"

            return Response(
                content=pdf_buffer.getvalue(),
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'inline; filename="{filename}"'
                }
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Erro ao gerar Livro de Promoção: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")


    @router.get("/documents/batch/{class_id}/{document_type}")
    async def get_batch_documents(
        class_id: str,
        document_type: str,
        academic_year: int = 2025,
        request: Request = None
    ):
        """
        Gera um único PDF consolidado com todos os documentos da turma.

        document_type: 'boletim', 'ficha_individual', 'certificado'
        """
        from PyPDF2 import PdfMerger

        current_user = await AuthMiddleware.get_current_user(request)

        # Validar tipo de documento
        valid_types = ['boletim', 'ficha_individual', 'certificado']
        if document_type not in valid_types:
            raise HTTPException(status_code=400, detail=f"Tipo de documento inválido. Use: {', '.join(valid_types)}")

        # Buscar turma
        class_info = await db.classes.find_one({"id": class_id}, {"_id": 0})
        if not class_info:
            raise HTTPException(status_code=404, detail="Turma não encontrada")

        # Validar elegibilidade para certificado (9º Ano ou EJA 4ª Etapa)
        if document_type == 'certificado':
            grade_level = str(class_info.get('grade_level', '')).lower()
            education_level = str(class_info.get('education_level', '')).lower()

            is_9ano = '9' in grade_level and 'ano' in grade_level
            is_eja_4etapa = ('eja' in education_level or 'eja' in grade_level) and ('4' in grade_level or 'etapa' in grade_level)

            if not (is_9ano or is_eja_4etapa):
                raise HTTPException(
                    status_code=400, 
                    detail="Certificado disponível apenas para turmas do 9º Ano ou EJA 4ª Etapa"
                )

        # Buscar escola da turma
        school = await get_school_cached(db, class_info.get("school_id"))
        if not school:
            school = {"name": "Escola Municipal"}

        # Buscar mantenedora
        mantenedora = await get_mantenedora_cached(db)

        # Buscar calendário letivo para data fim do 4º bimestre
        calendario_letivo = await db.calendar.find_one({
            "year": academic_year
        }, {"_id": 0})

        # Buscar alunos matriculados na turma (ativos e transferidos)
        academic_year_int_livro = int(academic_year) if academic_year else datetime.now().year
        enrollments = await db.enrollments.find(
            {"class_id": class_id, "status": {"$in": ["active", "transferred"]}, "academic_year": academic_year_int_livro},
            {"_id": 0}
        ).to_list(1000)

        if not enrollments:
            raise HTTPException(status_code=404, detail="Nenhum aluno matriculado nesta turma")

        student_ids = [e['student_id'] for e in enrollments]
        enrollment_map = {e['student_id']: e for e in enrollments}

        # Buscar dados dos alunos
        students = await db.students.find(
            {"id": {"$in": student_ids}},
            {"_id": 0}
        ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).to_list(1000)

        if not students:
            raise HTTPException(status_code=404, detail="Alunos não encontrados")

        # Buscar componentes curriculares para o boletim
        courses = []
        if document_type in ['boletim', 'ficha_individual']:
            courses = await db.courses.find({}, {"_id": 0}).to_list(100)

        # Criar merger para juntar os PDFs
        merger = PdfMerger()

        try:
            for student in students:
                enrollment = enrollment_map.get(student['id'], {})

                # Buscar notas do aluno se necessário
                grades = []
                if document_type in ['boletim', 'ficha_individual']:
                    grades = await db.grades.find(
                        {"student_id": student['id'], "academic_year": academic_year},
                        {"_id": 0}
                    ).to_list(100)

                # Gerar PDF individual
                if document_type == 'boletim':
                    pdf_buffer = generate_boletim_pdf(
                        student=student,
                        school=school,
                        enrollment=enrollment,
                        class_info=class_info,
                        grades=grades,
                        courses=courses,
                        academic_year=str(academic_year),
                        mantenedora=mantenedora,
                        calendario_letivo=calendario_letivo
                    )
                elif document_type == 'ficha_individual':
                    # Buscar frequência do aluno
                    attendances = await db.attendance.find(
                        {"class_id": class_id, "academic_year": academic_year, "records.student_id": student['id']},
                        {"_id": 0}
                    ).to_list(1000)

                    attendance_data = {"present": 0, "absent": 0, "justified": 0, "total": 0}
                    for att in attendances:
                        for record in att.get('records', []):
                            if record['student_id'] == student['id']:
                                attendance_data['total'] += 1
                                if record['status'] == 'P':
                                    attendance_data['present'] += 1
                                elif record['status'] == 'F':
                                    attendance_data['absent'] += 1
                                elif record['status'] == 'J':
                                    attendance_data['justified'] += 1

                    pdf_buffer = generate_ficha_individual_pdf(
                        student=student,
                        school=school,
                        enrollment=enrollment,
                        class_info=class_info,
                        grades=grades,
                        courses=courses,
                        attendance_data=attendance_data,
                        academic_year=academic_year,
                        mantenedora=mantenedora,
                        calendario_letivo=calendario_letivo
                    )
                elif document_type == 'certificado':
                    pdf_buffer = generate_certificado_pdf(
                        student=student,
                        school=school,
                        class_info=class_info,
                        enrollment=enrollment,
                        academic_year=academic_year,
                        mantenedora=mantenedora
                    )

                # Adicionar ao merger
                merger.append(pdf_buffer)

            # Gerar PDF final consolidado
            output_buffer = BytesIO()
            merger.write(output_buffer)
            merger.close()
            output_buffer.seek(0)

            # Nome do arquivo
            class_name = class_info.get('name', 'turma').replace(' ', '_')
            type_names = {
                'boletim': 'Boletins',
                'ficha_individual': 'Fichas_Individuais',
                'certificado': 'Certificados'
            }
            filename = f"{type_names.get(document_type, document_type)}_{class_name}_{academic_year}.pdf"

            return StreamingResponse(
                output_buffer,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'inline; filename="{filename}"'
                }
            )

        except Exception as e:
            logger.error(f"Erro ao gerar documentos em lote: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")



    return router
