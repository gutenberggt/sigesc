"""
Router para Detalhes de Turma.
Extraído automaticamente de server.py.
"""

from fastapi import APIRouter, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from datetime import datetime
import logging

from models import *
from auth_middleware import AuthMiddleware
from pdf_cache import get_mantenedora_cached
from pdf_generator import generate_class_details_pdf
from services.class_details_roster import build_class_students

logger = logging.getLogger(__name__)


router = APIRouter(tags=["Detalhes de Turma"])


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências."""
    
    # Helper para obter DB correto (produção ou sandbox)
    def get_db_for_user(user: dict):
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db



    @router.get("/classes/{class_id}/details")
    async def get_class_details(class_id: str, request: Request):
        """
        Busca detalhes completos da turma incluindo:
        - Dados cadastrais da turma
        - Escola
        - Professor(es) alocado(s)
        - Lista de alunos matriculados com responsáveis
        """
        current_user = await AuthMiddleware.get_current_user(request)

        # Busca turma
        class_doc = await db.classes.find_one({"id": class_id}, {"_id": 0})
        if not class_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Turma não encontrada"
            )

        # Busca escola
        school = await db.schools.find_one({"id": class_doc.get('school_id')}, {"_id": 0, "id": 1, "name": 1})

        # Busca professores alocados na turma
        alocacoes = await db.teacher_assignments.find(
            {"class_id": class_id},
            {"_id": 0}
        ).to_list(100)

        # Agrupa por professor para evitar duplicação
        teachers_map = {}
        for alocacao in alocacoes:
            staff_id = alocacao.get('staff_id')
            if staff_id not in teachers_map:
                staff = await db.staff.find_one(
                    {"id": staff_id},
                    {"_id": 0, "id": 1, "nome": 1, "full_name": 1, "email": 1, "celular": 1}
                )
                if staff:
                    teachers_map[staff_id] = {
                        "staff_id": staff.get('id'),
                        "nome": staff.get('nome') or staff.get('full_name'),
                        "email": staff.get('email'),
                        "celular": staff.get('celular'),
                        "componentes": []
                    }

            # Adiciona componente se existir
            if staff_id in teachers_map and alocacao.get('course_id'):
                course = await db.courses.find_one(
                    {"id": alocacao.get('course_id')},
                    {"_id": 0, "id": 1, "name": 1, "nome": 1}
                )
                if course:
                    comp_name = course.get('name') or course.get('nome')
                    if comp_name and comp_name not in teachers_map[staff_id]["componentes"]:
                        teachers_map[staff_id]["componentes"].append(comp_name)

        # Formata lista de professores
        teachers = []
        for teacher_data in teachers_map.values():
            componentes = teacher_data.pop("componentes", [])
            teacher_data["componente"] = ", ".join(componentes) if componentes else None
            teachers.append(teacher_data)

        # Roster canônico compartilhado com o PDF. Inclui estudantes que já
        # pertenceram à turma (transferidos, remanejados, progredidos,
        # desistentes e reclassificados), preservando a série da matrícula.
        students_list = await build_class_students(db, class_doc)

        # Calcula contagem por série para turmas multisseriadas
        series_count = {}
        if class_doc.get('is_multi_grade') and class_doc.get('series'):
            for serie in class_doc.get('series', []):
                series_count[serie] = 0
            # Comparação case-insensitive para lidar com variações de maiúsculas/minúsculas
            series_lower_map = {s.lower(): s for s in series_count.keys()}
            for student in students_list:
                serie = student.get('student_series')
                if serie:
                    # Tenta correspondência exata primeiro, depois case-insensitive
                    if serie in series_count:
                        series_count[serie] += 1
                    elif serie.lower() in series_lower_map:
                        series_count[series_lower_map[serie.lower()]] += 1

        return {
            "class": class_doc,
            "school": school,
            "teachers": teachers,
            "students": students_list,
            "total_students": len(students_list),
            "series_count": series_count if series_count else None
        }


    @router.get("/classes/{class_id}/cancelled-enrollments")
    async def get_class_cancelled_enrollments(class_id: str, request: Request):
        """[Auditoria — somente leitura] Lista as matrículas CANCELADAS desta turma.

        Como alunos cancelados foram removidos das listas operacionais (notas/
        frequência), esta visão permite ao gestor rastrear quem foi cancelado,
        quando, por quem e o motivo. Não altera nada."""
        current_user = await AuthMiddleware.get_current_user(request)

        class_doc = await db.classes.find_one({"id": class_id}, {"_id": 0, "id": 1, "name": 1})
        if not class_doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turma não encontrada")

        cancelled = await db.enrollments.find(
            {"class_id": class_id, "status": "cancelled"},
            {"_id": 0, "student_id": 1, "enrollment_number": 1, "student_series": 1,
             "cancellation_reason": 1, "cancellation_date": 1, "cancelled_by": 1,
             "academic_year": 1}
        ).sort("cancellation_date", -1).to_list(1000)

        student_ids = list({e.get("student_id") for e in cancelled if e.get("student_id")})
        canceller_ids = list({e.get("cancelled_by") for e in cancelled if e.get("cancelled_by")})

        students_map = {}
        if student_ids:
            async for s in db.students.find(
                {"id": {"$in": student_ids}},
                {"_id": 0, "id": 1, "full_name": 1, "enrollment_number": 1}
            ):
                students_map[s["id"]] = s

        cancellers_map = {}
        if canceller_ids:
            async for u in db.users.find(
                {"id": {"$in": canceller_ids}},
                {"_id": 0, "id": 1, "full_name": 1, "name": 1, "email": 1}
            ):
                cancellers_map[u["id"]] = u.get("full_name") or u.get("name") or u.get("email")

        items = []
        for e in cancelled:
            sid = e.get("student_id")
            stu = students_map.get(sid, {})
            items.append({
                "student_id": sid,
                "full_name": stu.get("full_name") or "(estudante removido)",
                "enrollment_number": e.get("enrollment_number") or stu.get("enrollment_number"),
                "student_series": e.get("student_series"),
                "academic_year": e.get("academic_year"),
                "cancellation_reason": e.get("cancellation_reason") or "",
                "cancellation_date": e.get("cancellation_date") or "",
                "cancelled_by_name": cancellers_map.get(e.get("cancelled_by")) or "",
            })

        return {
            "class_id": class_id,
            "class_name": class_doc.get("name"),
            "total": len(items),
            "items": items,
        }



    @router.get("/classes/{class_id}/details/pdf")
    async def get_class_details_pdf(class_id: str, request: Request):
        """
        Gera PDF com detalhes completos da turma
        """
        current_user = await AuthMiddleware.get_current_user(request)

        # Busca turma
        class_doc = await db.classes.find_one({"id": class_id}, {"_id": 0})
        if not class_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Turma não encontrada"
            )

        # Busca escola
        school = await db.schools.find_one({"id": class_doc.get('school_id')}, {"_id": 0})
        if not school:
            school = {"name": "Escola Municipal"}

        # Busca mantenedora
        mantenedora = await get_mantenedora_cached(db)

        # Busca professores alocados na turma
        alocacoes = await db.teacher_assignments.find(
            {"class_id": class_id},
            {"_id": 0}
        ).to_list(100)

        # Agrupa por professor para evitar duplicação
        teachers_map = {}
        for alocacao in alocacoes:
            staff_id = alocacao.get('staff_id')
            if staff_id not in teachers_map:
                staff = await db.staff.find_one(
                    {"id": staff_id},
                    {"_id": 0, "id": 1, "nome": 1, "full_name": 1, "celular": 1}
                )
                if staff:
                    teachers_map[staff_id] = {
                        "nome": staff.get('nome') or staff.get('full_name'),
                        "celular": staff.get('celular'),
                        "componentes": []
                    }

            # Adiciona componente se existir
            if staff_id in teachers_map and alocacao.get('course_id'):
                course = await db.courses.find_one(
                    {"id": alocacao.get('course_id')},
                    {"_id": 0, "name": 1, "nome": 1}
                )
                if course:
                    comp_name = course.get('name') or course.get('nome')
                    if comp_name and comp_name not in teachers_map[staff_id]["componentes"]:
                        teachers_map[staff_id]["componentes"].append(comp_name)

        # Formata lista de professores
        teachers = []
        for teacher_data in teachers_map.values():
            componentes = teacher_data.pop("componentes", [])
            teacher_data["componente"] = ", ".join(componentes) if componentes else None
            teachers.append(teacher_data)

        # O PDF usa exatamente o mesmo roster canônico da tela Detalhes da Turma.
        # Matrículas canceladas permanecem fora e seguem na visão de auditoria.
        students_list = await build_class_students(db, class_doc)

        try:
            pdf_buffer = generate_class_details_pdf(
                class_info=class_doc,
                school=school,
                teachers=teachers,
                students=students_list,
                mantenedora=mantenedora
            )

            class_name = class_doc.get('name', 'turma').replace(' ', '_')
            academic_year = class_doc.get('academic_year') or datetime.now().year
            filename = f"Detalhes_Turma_{class_name}_{academic_year}.pdf"

            return StreamingResponse(
                pdf_buffer,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"'
                }
            )
        except Exception as e:
            logger.error(f"Erro ao gerar PDF de detalhes da turma: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")

    # ============= COURSE (COMPONENTE CURRICULAR) ROUTES - MOVIDO PARA routers/courses.py =============

    # ============= CPF VALIDATION ENDPOINTS =============


    # ============= STUDENT (ALUNO) ROUTES =============

    ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.pdf', '.doc', '.docx'}
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

    # PATCH 1.3: Rota de upload restrita a roles autorizados



    return router
