"""
Router de Componentes Curriculares - SIGESC
Endpoints para gestão de componentes curriculares (disciplinas).
"""

from fastapi import APIRouter, HTTPException, status, Request
from typing import List, Optional

from models import Course, CourseCreate, CourseUpdate
from auth_middleware import AuthMiddleware
from utils.cache import cache, CACHE_TTL_COURSES
from tenant_scope import apply_tenant_filter, assert_same_tenant, resolve_tenant_id_for_create, get_mantenedora_scope

router = APIRouter(prefix="/courses", tags=["Componentes Curriculares"])


def setup_router(db, audit_service):
    """Configura o router com as dependências necessárias"""

    @router.post("", response_model=Course, status_code=status.HTTP_201_CREATED)
    async def create_course(course_data: CourseCreate, request: Request):
        """Cria novo componente curricular (por mantenedora)"""
        current_user = await AuthMiddleware.require_roles(['super_admin'])(request)
        
        # [Mai/2026] CAPS lock automático removido — preserva capitalização do usuário.
        course_dict = course_data.model_dump()
        course_obj = Course(**course_dict)
        doc = course_obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        
        # Multi-tenancy: injeta mantenedora_id do scope do usuário
        doc['mantenedora_id'] = await resolve_tenant_id_for_create(db, current_user, request)
        
        await db.courses.insert_one(doc)
        
        cache.invalidate('courses')
        return course_obj

    @router.get("", response_model=List[Course])
    async def list_courses(request: Request, nivel_ensino: Optional[str] = None, skip: int = 0, limit: int = 500):
        """Lista componentes curriculares (por mantenedora)"""
        current_user = await AuthMiddleware.get_current_user(request)
        
        tenant_id = get_mantenedora_scope(current_user, request)
        cache_params = {'nivel_ensino': nivel_ensino, 'skip': skip, 'limit': limit, 'tenant': tenant_id or 'ALL'}
        cached = cache.get('courses', cache_params)
        if cached is not None:
            return cached
        
        # Constrói filtro
        filter_query = {}
        
        if nivel_ensino:
            filter_query['nivel_ensino'] = nivel_ensino
        
        # Multi-tenancy
        filter_query = apply_tenant_filter(filter_query, current_user, request)
        
        courses = await db.courses.find(filter_query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
        
        cache.set('courses', cache_params, courses, CACHE_TTL_COURSES)
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
        
        assert_same_tenant(course_doc, current_user, request)
        
        return Course(**course_doc)

    @router.put("/{course_id}", response_model=Course)
    async def update_course(course_id: str, course_update: CourseUpdate, request: Request):
        """Atualiza componente curricular"""
        current_user = await AuthMiddleware.require_roles(['super_admin'])(request)
        
        # Busca componente
        course_doc = await db.courses.find_one({"id": course_id}, {"_id": 0})
        if not course_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Componente curricular não encontrado"
            )
        
        assert_same_tenant(course_doc, current_user, request)
        
        update_data = course_update.model_dump(exclude_unset=True)
        
        # [Mai/2026] CAPS lock automático removido — preserva capitalização do usuário.
        
        if update_data:
            await db.courses.update_one(
                {"id": course_id},
                {"$set": update_data}
            )
        
        updated_course = await db.courses.find_one({"id": course_id}, {"_id": 0})
        cache.invalidate('courses')
        return Course(**updated_course)

    @router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_course(course_id: str, request: Request):
        """Deleta componente curricular"""
        current_user = await AuthMiddleware.require_roles(['super_admin'])(request)
        
        # Valida tenant antes de deletar
        existing = await db.courses.find_one({"id": course_id}, {"_id": 0, "mantenedora_id": 1})
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Componente curricular não encontrado"
            )
        assert_same_tenant(existing, current_user, request)

        # [Fev/2026] Bloqueia exclusão se houver dependência ativa deste componente.
        active_deps = await db.student_dependencies.count_documents({
            "course_id": course_id, "status": "active",
        })
        if active_deps > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Não é possível excluir este componente: {active_deps} aluno(s) com dependência de estudos ativa vinculada(s). Cancele/conclua as dependências antes."
            )
        
        result = await db.courses.delete_one({"id": course_id})
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Componente curricular não encontrado"
            )
        
        cache.invalidate('courses')
        return None

    return router
