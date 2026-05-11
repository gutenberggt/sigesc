"""
Router de Turmas - SIGESC
Endpoints para gestão de turmas (classes).
"""

from fastapi import APIRouter, HTTPException, status, Request
from typing import List, Optional

from models import Class, ClassCreate, ClassUpdate
from auth_middleware import AuthMiddleware
from utils.cache import cache, CACHE_TTL_CLASSES
from tenant_scope import apply_tenant_filter, assert_same_tenant, resolve_tenant_id_for_create, get_mantenedora_scope

router = APIRouter(prefix="/classes", tags=["Turmas"])


def setup_router(db, audit_service, sandbox_db=None):
    """Configura o router com as dependências necessárias"""
    
    def get_db_for_user(user: dict):
        """Retorna o banco correto baseado no usuário"""
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db

    @router.post("", response_model=Class, status_code=status.HTTP_201_CREATED)
    async def create_class(class_data: ClassCreate, request: Request):
        """Cria nova turma"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        # Verifica acesso à escola
        await AuthMiddleware.verify_school_access(request, class_data.school_id)
        
        # [Mai/2026] CAPS lock automático removido — preserva capitalização do usuário.
        class_dict = class_data.model_dump()
        class_obj = Class(**class_dict)
        doc = class_obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        
        # Multi-tenancy: injeta mantenedora_id derivada da escola
        doc['mantenedora_id'] = await resolve_tenant_id_for_create(
            current_db, current_user, request, school_id=class_data.school_id
        )
        
        await current_db.classes.insert_one(doc)
        
        cache.invalidate('classes')
        return class_obj

    @router.get("")
    async def list_classes(request: Request, school_id: Optional[str] = None, skip: int = 0, limit: int = 1000):
        """Lista turmas"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        tenant_id = get_mantenedora_scope(current_user, request)
        
        cache_params = {
            'role': current_user['role'],
            'school_ids': sorted(current_user.get('school_ids', [])),
            'tenant': tenant_id or 'ALL',
            'school_id': school_id, 'skip': skip, 'limit': limit
        }
        cached = cache.get('classes', cache_params)
        if cached is not None:
            return cached
        
        # Constrói filtro
        filter_query = {}
        
        # Papéis com visão tenant-wide das turmas (apenas leitura para semed1/semed2):
        # admin, admin_teste, super_admin, gerente, semed, semed1 (Tutor), semed2 (Analista),
        # semed3 (Administração), secretario, ass_social, ass_social_2, agente_vacinas.
        # Alinhado com /app/frontend/src/pages/Users.js (`classes: 'view'`) e com
        # /app/backend/routers/schools.py::list_schools.
        if current_user['role'] in ['admin', 'admin_teste', 'super_admin', 'gerente', 'semed', 'semed1', 'semed2', 'semed3', 'secretario', 'ass_social', 'ass_social_2', 'agente_vacinas']:
            if school_id:
                filter_query['school_id'] = school_id
        else:
            # Outros papéis veem apenas das escolas vinculadas
            if school_id and school_id in current_user.get('school_ids', []):
                filter_query['school_id'] = school_id
            else:
                filter_query['school_id'] = {"$in": current_user.get('school_ids', [])}
        
        # Multi-tenancy: aplica filtro por mantenedora
        filter_query = apply_tenant_filter(filter_query, current_user, request)
        
        classes = await current_db.classes.find(filter_query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
        
        # Ordenar: números primeiro, depois letras, ambos em ordem natural
        import re
        def class_sort_key(c):
            name = (c.get('name') or '').strip()
            starts_with_digit = bool(name and name[0].isdigit())
            # Extrair número inicial para ordenação natural
            m = re.match(r'^(\d+)', name)
            num = int(m.group(1)) if m else float('inf')
            return (0 if starts_with_digit else 1, num, name.lower())
        
        classes.sort(key=class_sort_key)
        
        # Adicionar contagem de alunos matriculados por turma
        if classes:
            class_ids = [c['id'] for c in classes]
            pipeline = [
                {"$match": {"class_id": {"$in": class_ids}, "status": "active"}},
                {"$group": {"_id": "$class_id", "count": {"$sum": 1}}}
            ]
            counts = await current_db.enrollments.aggregate(pipeline).to_list(1000)
            count_map = {c['_id']: c['count'] for c in counts}
            for c in classes:
                c['student_count'] = count_map.get(c['id'], 0)
        
        cache.set('classes', cache_params, classes, CACHE_TTL_CLASSES)
        return classes

    @router.get("/{class_id}", response_model=Class)
    async def get_class(class_id: str, request: Request):
        """Busca turma por ID"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        class_doc = await current_db.classes.find_one({"id": class_id}, {"_id": 0})
        
        if not class_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Turma não encontrada"
            )
        
        # Verifica acesso à escola da turma
        await AuthMiddleware.verify_school_access(request, class_doc['school_id'])
        
        # Multi-tenancy: valida tenant
        assert_same_tenant(class_doc, current_user, request)
        
        return Class(**class_doc)

    @router.put("/{class_id}", response_model=Class)
    async def update_class(class_id: str, class_update: ClassUpdate, request: Request):
        """Atualiza turma"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        # Busca turma
        class_doc = await current_db.classes.find_one({"id": class_id}, {"_id": 0})
        if not class_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Turma não encontrada"
            )
        
        # Verifica acesso
        await AuthMiddleware.verify_school_access(request, class_doc['school_id'])
        assert_same_tenant(class_doc, current_user, request)
        
        update_data = class_update.model_dump(exclude_unset=True)
        
        # [Mai/2026] CAPS lock automático removido — preserva capitalização do usuário.
        
        if update_data:
            await current_db.classes.update_one(
                {"id": class_id},
                {"$set": update_data}
            )
        
        updated_class = await current_db.classes.find_one({"id": class_id}, {"_id": 0})
        cache.invalidate('classes')
        return Class(**updated_class)

    @router.delete("/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_class(class_id: str, request: Request):
        """Deleta turma"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        # Busca turma
        class_doc = await current_db.classes.find_one({"id": class_id}, {"_id": 0})
        if not class_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Turma não encontrada"
            )
        
        # Verifica acesso
        await AuthMiddleware.verify_school_access(request, class_doc['school_id'])
        assert_same_tenant(class_doc, current_user, request)

        # [Fev/2026] Bloqueia exclusão se houver dependência ativa vinculada a esta turma.
        # Ver /app/docs/STUDENT_DEPENDENCY.md.
        active_deps = await current_db.student_dependencies.count_documents({
            "class_id": class_id, "status": "active",
        })
        if active_deps > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Não é possível excluir esta turma: {active_deps} aluno(s) com dependência de estudos ativa vinculada(s). Cancele/conclua as dependências antes."
            )
        
        result = await current_db.classes.delete_one({"id": class_id})
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Turma não encontrada"
            )
        
        cache.invalidate('classes')
        return None

    return router
