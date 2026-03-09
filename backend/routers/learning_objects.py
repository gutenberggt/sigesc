"""
Router para Objetos de Aprendizagem.
Extraído automaticamente de server.py.
"""

from fastapi import APIRouter, HTTPException, status, Request, Query, UploadFile, File
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse, JSONResponse
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import uuid
import json
import re
import io
import os
import ftplib

from models import *
from auth_middleware import AuthMiddleware
from text_utils import format_data_uppercase


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
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'coordenador', 'professor', 'semed', 'semed3'])(request)

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
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'coordenador', 'professor', 'semed', 'semed3'])(request)

        obj = await db.learning_objects.find_one({"id": object_id}, {"_id": 0})
        if not obj:
            raise HTTPException(status_code=404, detail="Registro não encontrado")

        return obj


    @router.post("/learning-objects")
    async def create_learning_object(data: LearningObjectCreate, request: Request):
        """Cria um registro de objeto de conhecimento"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'coordenador', 'professor'])(request)
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
            **data.model_dump(),
            recorded_by=current_user['id']
        )

        await db.learning_objects.insert_one(new_object.model_dump())

        return await db.learning_objects.find_one({"id": new_object.id}, {"_id": 0})


    @router.put("/learning-objects/{object_id}")
    async def update_learning_object(object_id: str, data: LearningObjectUpdate, request: Request):
        """Atualiza um registro de objeto de conhecimento"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'coordenador', 'professor'])(request)
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
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        await db.learning_objects.update_one(
            {"id": object_id},
            {"$set": update_data}
        )

        return await db.learning_objects.find_one({"id": object_id}, {"_id": 0})


    @router.delete("/learning-objects/{object_id}")
    async def delete_learning_object(object_id: str, request: Request):
        """Exclui um registro de objeto de conhecimento"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'coordenador', 'professor'])(request)

        existing = await db.learning_objects.find_one({"id": object_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Registro não encontrado")

        await db.learning_objects.delete_one({"id": object_id})

        return {"message": "Registro excluído com sucesso"}


    @router.get("/learning-objects/check-date/{class_id}/{course_id}/{date}")
    async def check_learning_object_date(class_id: str, course_id: str, date: str, request: Request):
        """Verifica se existe registro para uma data específica"""
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'coordenador', 'professor', 'semed', 'semed3'])(request)

        existing = await db.learning_objects.find_one({
            "class_id": class_id,
            "course_id": course_id,
            "date": date
        }, {"_id": 0})

        return {
            "has_record": existing is not None,
            "record": existing
        }



    return router
