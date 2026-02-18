"""
Router de Componentes Curriculares - SIGESC
Endpoints para gestão de componentes curriculares (disciplinas).
"""

from fastapi import APIRouter, HTTPException, status, Request
from typing import List, Optional

from models import Course, CourseCreate, CourseUpdate
from auth_middleware import AuthMiddleware
from text_utils import format_data_uppercase

router = APIRouter(prefix="/courses", tags=["Componentes Curriculares"])


def setup_router(db, audit_service):
    """Configura o router com as dependências necessárias"""

    @router.post("", response_model=Course, status_code=status.HTTP_201_CREATED)
    async def create_course(course_data: CourseCreate, request: Request):
        """Cria novo componente curricular (global para todas as escolas)"""
        current_user = await AuthMiddleware.require_roles(['admin'])(request)
        
        # Converte dados para maiúsculas
        course_dict = format_data_uppercase(course_data.model_dump())
        course_obj = Course(**course_dict)
        doc = course_obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        
        await db.courses.insert_one(doc)
        
        return course_obj

    @router.get("", response_model=List[Course])
    async def list_courses(request: Request, nivel_ensino: Optional[str] = None, skip: int = 0, limit: int = 100):
        """Lista componentes curriculares (global)"""
        current_user = await AuthMiddleware.get_current_user(request)
        
        # Constrói filtro
        filter_query = {}
        
        if nivel_ensino:
            filter_query['nivel_ensino'] = nivel_ensino
        
        courses = await db.courses.find(filter_query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
        
        return courses

    @router.get("/{course_id}", response_model=Course)
    async def get_course(course_id: str, request: Request):
        """Busca componente curricular por ID"""
        current_user = await AuthMiddleware.get_current_user(request)
        
        course_doc = await db.courses.find_one({"id": course_id}, {"_id": 0})
        
        if not course_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Componente curricular não encontrado"
            )
        
        return Course(**course_doc)

    @router.put("/{course_id}", response_model=Course)
    async def update_course(course_id: str, course_update: CourseUpdate, request: Request):
        """Atualiza componente curricular"""
        current_user = await AuthMiddleware.require_roles(['admin'])(request)
        
        # Busca componente
        course_doc = await db.courses.find_one({"id": course_id}, {"_id": 0})
        if not course_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Componente curricular não encontrado"
            )
        
        update_data = course_update.model_dump(exclude_unset=True)
        
        # Converte dados para maiúsculas
        update_data = format_data_uppercase(update_data)
        
        if update_data:
            await db.courses.update_one(
                {"id": course_id},
                {"$set": update_data}
            )
        
        updated_course = await db.courses.find_one({"id": course_id}, {"_id": 0})
        return Course(**updated_course)

    @router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_course(course_id: str, request: Request):
        """Deleta componente curricular"""
        current_user = await AuthMiddleware.require_roles(['admin'])(request)
        
        result = await db.courses.delete_one({"id": course_id})
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Componente curricular não encontrado"
            )
        
        return None

    return router
