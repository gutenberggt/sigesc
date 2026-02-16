"""
Router de Dashboard de Acompanhamento de Diários
Fornece estatísticas de preenchimento de frequência, notas e conteúdos
"""
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from typing import Optional
from datetime import datetime, timedelta
from database import db
from routers.auth import AuthMiddleware
import logging

logger = logging.getLogger(__name__)

def create_diary_dashboard_router():
    router = APIRouter(prefix="/diary-dashboard", tags=["Diary Dashboard"])

    # Roles permitidos para acessar o dashboard
    ALLOWED_ROLES = ['admin', 'admin_teste', 'diretor', 'coordenador', 'secretario', 'auxiliar_secretaria', 'semed_nivel_2', 'semed_nivel_3']

    async def check_access(request: Request):
        """Verifica se o usuário tem acesso ao dashboard"""
        user = await AuthMiddleware.get_current_user(request)
        if user.get('role') not in ALLOWED_ROLES:
            raise HTTPException(status_code=403, detail="Acesso não autorizado")
        return user

    @router.get("/attendance")
    async def get_attendance_stats(
        request: Request,
        academic_year: int = Query(...),
        school_id: Optional[str] = None,
        class_id: Optional[str] = None,
        course_id: Optional[str] = None
    ):
        """Retorna estatísticas de preenchimento de frequência"""
        user = await check_access(request)
        
        try:
            # Construir filtro base
            filter_query = {"academic_year": academic_year}
            
            if school_id:
                # Buscar turmas da escola
                school_classes = await db.classes.find(
                    {"school_id": school_id, "status": "active"},
                    {"id": 1}
                ).to_list(1000)
                class_ids = [c['id'] for c in school_classes]
                filter_query["class_id"] = {"$in": class_ids}
            
            if class_id:
                filter_query["class_id"] = class_id
            
            # Contar registros de frequência por mês
            pipeline = [
                {"$match": filter_query},
                {"$addFields": {
                    "month": {"$month": {"$dateFromString": {"dateString": "$date"}}}
                }},
                {"$group": {
                    "_id": "$month",
                    "count": {"$sum": 1}
                }},
                {"$sort": {"_id": 1}}
            ]
            
            monthly_data = await db.attendance.aggregate(pipeline).to_list(12)
            
            # Calcular total de dias letivos esperados (aproximado)
            total_records = await db.attendance.count_documents(filter_query)
            
            # Estimar taxa de preenchimento
            # Assumindo ~200 dias letivos por ano
            expected_days = 200
            if school_id:
                # Ajustar baseado nas turmas
                class_count = len(class_ids) if 'class_ids' in dir() else 1
                expected_days = expected_days * class_count
            
            completion_rate = min(100, round((total_records / max(expected_days, 1)) * 100))
            
            # Formatar dados por mês
            month_names = ['', 'Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
            by_month = []
            for m in monthly_data:
                month_num = m['_id']
                preenchido = min(100, round((m['count'] / 20) * 100))  # ~20 dias úteis por mês
                by_month.append({
                    "month": month_names[month_num] if month_num <= 12 else str(month_num),
                    "preenchido": preenchido,
                    "pendente": 100 - preenchido
                })
            
            return {
                "completion_rate": completion_rate,
                "total_records": total_records,
                "by_month": by_month
            }
            
        except Exception as e:
            logger.error(f"Erro ao buscar estatísticas de frequência: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/grades")
    async def get_grades_stats(
        request: Request,
        academic_year: int = Query(...),
        school_id: Optional[str] = None,
        class_id: Optional[str] = None,
        course_id: Optional[str] = None
    ):
        """Retorna estatísticas de preenchimento de notas"""
        user = await check_access(request)
        
        try:
            # Construir filtro base
            filter_query = {"academic_year": academic_year}
            
            if school_id:
                # Buscar turmas da escola
                school_classes = await db.classes.find(
                    {"school_id": school_id, "status": "active"},
                    {"id": 1}
                ).to_list(1000)
                class_ids = [c['id'] for c in school_classes]
                filter_query["class_id"] = {"$in": class_ids}
            
            if class_id:
                filter_query["class_id"] = class_id
            
            if course_id:
                filter_query["course_id"] = course_id
            
            # Contar notas por bimestre
            pipeline = [
                {"$match": filter_query},
                {"$group": {
                    "_id": "$bimestre",
                    "count": {"$sum": 1}
                }},
                {"$sort": {"_id": 1}}
            ]
            
            bimestre_data = await db.grades.aggregate(pipeline).to_list(4)
            
            # Calcular taxa de preenchimento geral
            total_records = await db.grades.count_documents(filter_query)
            
            # Estimar esperado (alunos x componentes x 4 bimestres)
            enrollment_count = await db.enrollments.count_documents({
                "academic_year": academic_year,
                "status": "active",
                **({"class_id": {"$in": class_ids}} if school_id and 'class_ids' in dir() else {}),
                **({"class_id": class_id} if class_id else {})
            })
            
            course_count = 10  # Assumir 10 componentes por turma em média
            expected_total = enrollment_count * course_count * 4  # 4 bimestres
            
            completion_rate = min(100, round((total_records / max(expected_total, 1)) * 100))
            
            # Formatar dados por bimestre
            by_bimestre = []
            for bim in [1, 2, 3, 4]:
                bim_data = next((b for b in bimestre_data if b['_id'] == bim), None)
                count = bim_data['count'] if bim_data else 0
                expected_bim = expected_total / 4
                preenchido = min(100, round((count / max(expected_bim, 1)) * 100))
                by_bimestre.append({
                    "name": f"{bim}º Bim",
                    "preenchido": preenchido,
                    "pendente": 100 - preenchido
                })
            
            return {
                "completion_rate": completion_rate,
                "total_records": total_records,
                "by_bimestre": by_bimestre
            }
            
        except Exception as e:
            logger.error(f"Erro ao buscar estatísticas de notas: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/content")
    async def get_content_stats(
        request: Request,
        academic_year: int = Query(...),
        school_id: Optional[str] = None,
        class_id: Optional[str] = None,
        course_id: Optional[str] = None
    ):
        """Retorna estatísticas de preenchimento de conteúdos/objetos de conhecimento"""
        user = await check_access(request)
        
        try:
            # Construir filtro base
            filter_query = {"academic_year": academic_year}
            
            if school_id:
                filter_query["school_id"] = school_id
            
            if class_id:
                filter_query["class_id"] = class_id
            
            if course_id:
                filter_query["course_id"] = course_id
            
            # Contar registros por mês
            pipeline = [
                {"$match": filter_query},
                {"$addFields": {
                    "month": {"$month": {"$dateFromString": {"dateString": "$date"}}}
                }},
                {"$group": {
                    "_id": "$month",
                    "count": {"$sum": 1},
                    "total_classes": {"$sum": "$number_of_classes"}
                }},
                {"$sort": {"_id": 1}}
            ]
            
            monthly_data = await db.learning_objects.aggregate(pipeline).to_list(12)
            
            # Total de registros
            total_records = await db.learning_objects.count_documents(filter_query)
            
            # Estimar taxa de preenchimento
            # ~200 dias letivos x componentes
            expected_days = 200
            completion_rate = min(100, round((total_records / max(expected_days, 1)) * 100))
            
            # Formatar dados por mês
            month_names = ['', 'Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
            by_month = []
            for m in monthly_data:
                month_num = m['_id']
                by_month.append({
                    "month": month_names[month_num] if month_num <= 12 else str(month_num),
                    "registros": m['count'],
                    "aulas": m.get('total_classes', m['count'])
                })
            
            return {
                "completion_rate": completion_rate,
                "total_records": total_records,
                "by_month": by_month
            }
            
        except Exception as e:
            logger.error(f"Erro ao buscar estatísticas de conteúdos: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router
