"""
Router para Histórico Escolar.
CRUD de registros anuais do histórico do aluno + geração de PDF.
"""
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
import uuid
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Histórico Escolar"])


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências."""
    from auth_middleware import AuthMiddleware

    ALLOWED_ROLES = ['admin', 'secretario', 'diretor', 'auxiliar_secretaria']

    async def get_db(request):
        current_user = await AuthMiddleware.get_current_user(request)
        role = current_user.get('role', '')
        if role not in ALLOWED_ROLES:
            raise HTTPException(status_code=403, detail="Acesso negado. Apenas Administrador, Secretário, Diretor e Auxiliar de Secretaria podem gerenciar históricos.")
        if sandbox_db is not None and current_user.get('sandbox'):
            return sandbox_db, current_user
        return db, current_user

    @router.get("/student-history/{student_id}")
    async def get_student_history(student_id: str, request: Request):
        """Retorna o histórico escolar completo do aluno."""
        current_db, current_user = await get_db(request)

        student = await current_db.students.find_one({"id": student_id}, {"_id": 0})
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        history = await current_db.student_history.find_one(
            {"student_id": student_id}, {"_id": 0}
        )

        if not history:
            history = {
                "student_id": student_id,
                "records": [],
                "observations": "",
                "media_aprovacao": 6.0
            }

        return history

    @router.post("/student-history/{student_id}")
    async def save_student_history(student_id: str, request: Request):
        """Cria ou atualiza o histórico escolar do aluno."""
        current_db, current_user = await get_db(request)

        student = await current_db.students.find_one({"id": student_id}, {"_id": 0})
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        body = await request.json()
        records = body.get('records', [])
        observations = body.get('observations', '')
        media_aprovacao = body.get('media_aprovacao', 6.0)

        # Validar cada registro
        for rec in records:
            if not rec.get('serie'):
                raise HTTPException(status_code=400, detail="Cada registro precisa ter uma série/ano")

        now = datetime.now(timezone.utc).isoformat()

        existing = await current_db.student_history.find_one({"student_id": student_id})

        history_data = {
            "student_id": student_id,
            "records": records,
            "observations": observations,
            "media_aprovacao": media_aprovacao,
            "updated_at": now,
            "updated_by": current_user.get('id', '')
        }

        if existing:
            await current_db.student_history.update_one(
                {"student_id": student_id},
                {"$set": history_data}
            )
        else:
            history_data["id"] = str(uuid.uuid4())
            history_data["created_at"] = now
            history_data["created_by"] = current_user.get('id', '')
            await current_db.student_history.insert_one(history_data)

        result = await current_db.student_history.find_one(
            {"student_id": student_id}, {"_id": 0}
        )
        return result

    @router.delete("/student-history/{student_id}/{serie}")
    async def delete_history_record(student_id: str, serie: str, request: Request):
        """Remove um registro de uma série específica do histórico."""
        current_db, current_user = await get_db(request)

        result = await current_db.student_history.update_one(
            {"student_id": student_id},
            {"$pull": {"records": {"serie": serie}}}
        )

        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Registro não encontrado")

        return {"message": f"Registro da série {serie} removido"}

    @router.get("/student-history/{student_id}/import")
    async def import_student_data(student_id: str, request: Request):
        """
        Importa dados do sistema para o histórico.
        Retorna todas as matrículas do aluno com notas, escola, série, resultado.
        """
        current_db, current_user = await get_db(request)

        student = await current_db.students.find_one({"id": student_id}, {"_id": 0})
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        # Buscar todas as matrículas do aluno (ativas e transferidas)
        enrollments = await current_db.enrollments.find(
            {"student_id": student_id},
            {"_id": 0}
        ).to_list(100)

        imported_records = []

        for enrollment in enrollments:
            class_id = enrollment.get('class_id')
            academic_year = enrollment.get('academic_year')
            student_series = enrollment.get('student_series', '')

            if not class_id:
                continue

            # Buscar dados da turma
            class_info = await current_db.classes.find_one({"id": class_id}, {"_id": 0})
            if not class_info:
                continue

            # Buscar escola
            school = await current_db.schools.find_one(
                {"id": class_info.get('school_id')},
                {"_id": 0, "name": 1, "city": 1, "municipio": 1, "state": 1, "uf": 1}
            )

            # Inferir a série (1º, 2º, etc.)
            serie = ''
            grade_level = student_series or class_info.get('grade_level', '')
            for s in ['1º', '2º', '3º', '4º', '5º', '6º', '7º', '8º', '9º']:
                if s in grade_level:
                    serie = s
                    break

            if not serie:
                continue

            # Buscar notas do aluno neste ano
            grades = await current_db.grades.find(
                {"student_id": student_id, "academic_year": academic_year},
                {"_id": 0}
            ).to_list(100)

            # Mapear course_id -> nota final
            grades_map = {}
            resultado = 'E'  # Em andamento por padrão
            has_all_grades = True

            for grade in grades:
                course = await current_db.courses.find_one(
                    {"id": grade.get('course_id')},
                    {"_id": 0, "name": 1}
                )
                if course:
                    final_avg = grade.get('final_average')
                    if final_avg is not None:
                        grades_map[course['name']] = round(float(final_avg), 1)
                    else:
                        has_all_grades = False

                # Determinar resultado
                status = grade.get('status', '')
                if status == 'reprovado':
                    resultado = 'REP'

            if has_all_grades and grades and resultado != 'REP':
                resultado = 'APV'

            school_name = ''
            school_city = ''
            school_uf = ''
            if school:
                school_name = school.get('name', '')
                school_city = school.get('city') or school.get('municipio', '')
                school_uf = school.get('state') or school.get('uf', '')

            # Buscar carga horária do calendário letivo
            carga_horaria = 800
            calendario = await current_db.calendario_letivo.find_one(
                {"ano_letivo": academic_year, "school_id": None},
                {"_id": 0, "dias_letivos_previstos": 1}
            )
            if calendario:
                dias = calendario.get('dias_letivos_previstos', 200)
                carga_horaria = dias * 4  # Estimativa: 4h/dia

            imported_records.append({
                "serie": serie,
                "ano_letivo": academic_year,
                "escola": school_name,
                "cidade": school_city,
                "uf": school_uf,
                "carga_horaria": carga_horaria,
                "resultado": resultado,
                "grades": grades_map
            })

        # Ordenar por série
        series_order = ['1º', '2º', '3º', '4º', '5º', '6º', '7º', '8º', '9º']
        imported_records.sort(key=lambda r: series_order.index(r['serie']) if r['serie'] in series_order else 99)

        return {"records": imported_records, "student_name": student.get('full_name', '')}



    return router
