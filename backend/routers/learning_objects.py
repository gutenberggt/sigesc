"""
Router para Objetos de Aprendizagem.
Extraído automaticamente de server.py.
"""

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from typing import Optional
from datetime import datetime, timezone
import logging

from models import *
from auth_middleware import AuthMiddleware
from pdf_generator import generate_learning_objects_pdf
from text_utils import format_data_uppercase

logger = logging.getLogger(__name__)


router = APIRouter(tags=["Objetos de Aprendizagem"])


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências."""
    
    # Helper para obter DB correto (produção ou sandbox)
    def get_db_for_user(user: dict):
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db

    # Helpers passados via kwargs
    check_bimestre_edit_deadline = kwargs.get('check_bimestre_edit_deadline')
    verify_bimestre_edit_deadline_or_raise = kwargs.get('verify_bimestre_edit_deadline_or_raise')
    verify_academic_year_open_or_raise = kwargs.get('verify_academic_year_open_or_raise')
    check_academic_year_open = kwargs.get('check_academic_year_open')

    @router.get("/learning-objects")
    async def list_learning_objects(
        request: Request,
        class_id: Optional[str] = None,
        course_id: Optional[str] = None,
        date: Optional[str] = None,
        academic_year: Optional[int] = None,
        month: Optional[int] = None
    ):
        """Lista objetos de conhecimento (conteúdos ministrados)"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'coordenador', 'auxiliar_secretaria', 'professor', 'semed', 'semed1', 'semed2', 'semed3'])(request)

        query = {}
        if class_id:
            query["class_id"] = class_id
        if course_id:
            query["course_id"] = course_id
        if date:
            query["date"] = date
        if academic_year:
            query["academic_year"] = academic_year

        # Filtrar por mês se especificado
        if month and academic_year:
            start_date = f"{academic_year}-{month:02d}-01"
            if month == 12:
                end_date = f"{academic_year + 1}-01-01"
            else:
                end_date = f"{academic_year}-{month + 1:02d}-01"
            query["date"] = {"$gte": start_date, "$lt": end_date}

        objects = await db.learning_objects.find(query, {"_id": 0}).sort("date", -1).to_list(1000)

        # Enriquecer com nomes
        for obj in objects:
            turma = await db.classes.find_one({"id": obj["class_id"]}, {"_id": 0, "name": 1})
            course = await db.courses.find_one({"id": obj["course_id"]}, {"_id": 0, "name": 1})
            obj["class_name"] = turma.get("name", "") if turma else ""
            obj["course_name"] = course.get("name", "") if course else ""

        return objects


    @router.get("/learning-objects/{object_id}")
    async def get_learning_object(object_id: str, request: Request):
        """Retorna um objeto de conhecimento específico"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'coordenador', 'auxiliar_secretaria', 'professor', 'semed', 'semed1', 'semed2', 'semed3'])(request)

        obj = await db.learning_objects.find_one({"id": object_id}, {"_id": 0})
        if not obj:
            raise HTTPException(status_code=404, detail="Registro não encontrado")

        return obj


    @router.post("/learning-objects")
    async def create_learning_object(data: LearningObjectCreate, request: Request):
        """Cria um registro de objeto de conhecimento"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'coordenador', 'auxiliar_secretaria', 'professor'])(request)
        user_role = current_user.get('role', '')

        # Verifica se o ano letivo está aberto (apenas para não-admins)
        academic_year = data.academic_year or datetime.now().year
        if user_role != 'admin':
            class_doc = await db.classes.find_one(
                {"id": data.class_id},
                {"_id": 0, "school_id": 1, "academic_year": 1}
            )
            if class_doc:
                academic_year = data.academic_year or class_doc.get('academic_year', datetime.now().year)
                await verify_academic_year_open_or_raise(
                    class_doc['school_id'],
                    academic_year
                )

        # Verifica a data limite de edição por bimestre (apenas para não-admins e não-secretarios)
        if user_role not in ['admin', 'secretario']:
            calendario = await db.calendario_letivo.find_one(
                {"ano_letivo": academic_year},
                {"_id": 0}
            )
            if calendario:
                object_date = data.date
                for i in range(1, 5):
                    inicio = calendario.get(f"bimestre_{i}_inicio")
                    fim = calendario.get(f"bimestre_{i}_fim")
                    if inicio and fim and object_date >= inicio and object_date <= fim:
                        await verify_bimestre_edit_deadline_or_raise(academic_year, i, user_role)
                        break

        # Verifica se já existe registro para esta data/turma/componente
        existing = await db.learning_objects.find_one({
            "class_id": data.class_id,
            "course_id": data.course_id,
            "date": data.date
        })

        if existing:
            raise HTTPException(
                status_code=400, 
                detail="Já existe um registro para esta turma/componente nesta data. Use a opção de editar."
            )

        new_object = LearningObject(
            **format_data_uppercase(data.model_dump()),
            recorded_by=current_user['id']
        )

        await db.learning_objects.insert_one(new_object.model_dump())

        return await db.learning_objects.find_one({"id": new_object.id}, {"_id": 0})


    @router.put("/learning-objects/{object_id}")
    async def update_learning_object(object_id: str, data: LearningObjectUpdate, request: Request):
        """Atualiza um registro de objeto de conhecimento"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'coordenador', 'auxiliar_secretaria', 'professor'])(request)
        user_role = current_user.get('role', '')

        existing = await db.learning_objects.find_one({"id": object_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Registro não encontrado")

        # Verifica a data limite de edição por bimestre (apenas para não-admins e não-secretarios)
        if user_role not in ['admin', 'secretario']:
            academic_year = existing.get('academic_year', datetime.now().year)
            calendario = await db.calendario_letivo.find_one(
                {"ano_letivo": academic_year},
                {"_id": 0}
            )
            if calendario:
                object_date = existing.get('date')
                for i in range(1, 5):
                    inicio = calendario.get(f"bimestre_{i}_inicio")
                    fim = calendario.get(f"bimestre_{i}_fim")
                    if inicio and fim and object_date >= inicio and object_date <= fim:
                        await verify_bimestre_edit_deadline_or_raise(academic_year, i, user_role)
                        break

        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        update_data = format_data_uppercase(update_data)
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        await db.learning_objects.update_one(
            {"id": object_id},
            {"$set": update_data}
        )

        return await db.learning_objects.find_one({"id": object_id}, {"_id": 0})


    @router.delete("/learning-objects/{object_id}")
    async def delete_learning_object(object_id: str, request: Request):
        """Exclui um registro de objeto de conhecimento"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'coordenador', 'auxiliar_secretaria', 'professor'])(request)

        existing = await db.learning_objects.find_one({"id": object_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Registro não encontrado")

        await db.learning_objects.delete_one({"id": object_id})

        return {"message": "Registro excluído com sucesso"}


    @router.get("/learning-objects/check-date/{class_id}/{course_id}/{date}")
    async def check_learning_object_date(class_id: str, course_id: str, date: str, request: Request):
        """Verifica se existe registro para uma data específica"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'coordenador', 'auxiliar_secretaria', 'professor', 'semed', 'semed1', 'semed2', 'semed3'])(request)

        existing = await db.learning_objects.find_one({
            "class_id": class_id,
            "course_id": course_id,
            "date": date
        }, {"_id": 0})

        return {
            "has_record": existing is not None,
            "record": existing
        }



    @router.get("/learning-objects/pdf/bimestre/{class_id}")
    async def get_learning_objects_pdf(
        class_id: str,
        request: Request,
        bimestre: int = Query(..., ge=1, le=4),
        academic_year: Optional[int] = None,
        course_id: Optional[str] = None
    ):
        """Gera PDF dos objetos de conhecimento por bimestre"""
        await AuthMiddleware.get_current_user(request)

        if not academic_year:
            academic_year = datetime.now().year

        # Buscar turma
        turma = await db.classes.find_one({"id": class_id}, {"_id": 0})
        if not turma:
            raise HTTPException(status_code=404, detail="Turma não encontrada")

        # Buscar escola
        school = await db.schools.find_one({"id": turma.get('school_id')}, {"_id": 0})
        if not school:
            raise HTTPException(status_code=404, detail="Escola não encontrada")

        # Buscar mantenedora
        mantenedora = await db.mantenedora.find_one({}, {"_id": 0})

        # Buscar calendário para datas do bimestre
        calendario = await db.calendario_letivo.find_one(
            {"ano_letivo": academic_year, "school_id": None}, {"_id": 0}
        )
        if not calendario:
            calendario = await db.calendario_letivo.find_one(
                {"ano_letivo": academic_year}, {"_id": 0}
            )

        bk_inicio = f"bimestre_{bimestre}_inicio"
        bk_fim = f"bimestre_{bimestre}_fim"

        if calendario and calendario.get(bk_inicio) and calendario.get(bk_fim):
            period_start = str(calendario[bk_inicio])[:10]
            period_end = str(calendario[bk_fim])[:10]
        else:
            periodos = {
                1: (f"{academic_year}-02-01", f"{academic_year}-04-30"),
                2: (f"{academic_year}-05-01", f"{academic_year}-07-15"),
                3: (f"{academic_year}-07-16", f"{academic_year}-09-30"),
                4: (f"{academic_year}-10-01", f"{academic_year}-12-20"),
            }
            period_start, period_end = periodos.get(bimestre, (None, None))

        # Buscar registros do bimestre
        query = {
            "class_id": class_id,
            "academic_year": academic_year,
            "date": {"$gte": period_start, "$lte": period_end}
        }
        if course_id:
            query["course_id"] = course_id

        records = await db.learning_objects.find(query, {"_id": 0}).sort("date", 1).to_list(1000)

        # Enriquecer com nomes dos componentes
        course_names = {}
        for r in records:
            cid = r.get('course_id')
            if cid and cid not in course_names:
                course = await db.courses.find_one({"id": cid}, {"_id": 0, "name": 1})
                course_names[cid] = course.get('name', '') if course else ''
            r['course_name'] = course_names.get(cid, '')

        # Buscar professor (se course_id, buscar professor específico do componente)
        teacher_name = ""
        ta_query = {"class_id": class_id, "academic_year": academic_year}
        if course_id:
            ta_query["course_id"] = course_id
        teacher_assignment = await db.teacher_assignments.find_one(
            ta_query,
            {"_id": 0, "staff_id": 1}
        )
        if teacher_assignment:
            teacher = await db.staff.find_one(
                {"id": teacher_assignment['staff_id']},
                {"_id": 0, "nome": 1}
            )
            if teacher:
                teacher_name = teacher.get('nome', '')

        # Calcular dias previstos no bimestre (para Anos Iniciais / Ed. Infantil)
        dias_previstos = 0
        if calendario and period_start and period_end:
            from datetime import datetime as dt_calc, timedelta
            eventos_nao_letivos = ['feriado_nacional', 'feriado_estadual', 'feriado_municipal', 'recesso_escolar']
            non_school_dates = set()
            for ev in calendario.get('eventos', []):
                if ev.get('tipo') in eventos_nao_letivos:
                    ev_start = str(ev.get('data_inicio', ''))[:10]
                    ev_end = str(ev.get('data_fim', ev_start))[:10]
                    try:
                        d = dt_calc.strptime(ev_start, '%Y-%m-%d')
                        end = dt_calc.strptime(ev_end, '%Y-%m-%d')
                        while d <= end:
                            non_school_dates.add(d.strftime('%Y-%m-%d'))
                            d += timedelta(days=1)
                    except:
                        pass
            try:
                d = dt_calc.strptime(period_start, '%Y-%m-%d')
                end = dt_calc.strptime(period_end, '%Y-%m-%d')
                while d <= end:
                    if d.weekday() < 5 and d.strftime('%Y-%m-%d') not in non_school_dates:
                        dias_previstos += 1
                    d += timedelta(days=1)
            except:
                pass

        try:
            pdf_buffer = generate_learning_objects_pdf(
                school=school,
                class_info=turma,
                records=records,
                bimestre=bimestre,
                academic_year=academic_year,
                period_start=period_start,
                period_end=period_end,
                teacher_name=teacher_name,
                mantenedora=mantenedora,
                dias_previstos=dias_previstos
            )

            course_name_part = ""
            if course_id and records:
                course_name_part = f"_{records[0].get('course_name', '')}"
            filename = f"objetos_conhecimento_{turma.get('name', 'turma')}{course_name_part}_{bimestre}bim_{academic_year}.pdf"
            filename = filename.replace(' ', '_').replace('/', '-')

            return StreamingResponse(
                pdf_buffer,
                media_type="application/pdf",
                headers={"Content-Disposition": f"inline; filename={filename}"}
            )
        except Exception as e:
            import traceback
            logger.error(f"Erro ao gerar PDF de objetos de conhecimento: {e}\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")


    return router
