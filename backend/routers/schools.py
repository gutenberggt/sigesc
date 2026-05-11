"""
Router de Escolas - SIGESC
Endpoints para gestão de escolas.
"""

from fastapi import APIRouter, HTTPException, status, Request
from typing import List

from models import School, SchoolCreate, SchoolUpdate
from auth_middleware import AuthMiddleware
from utils.cache import cache, CACHE_TTL_SCHOOLS
from tenant_scope import apply_tenant_filter, get_mantenedora_scope, assert_same_tenant, is_super_admin

router = APIRouter(prefix="/schools", tags=["Escolas"])


def setup_router(db, audit_service, sandbox_db=None):
    """Configura o router com as dependências necessárias"""
    
    def get_db_for_user(user: dict):
        """Retorna o banco correto baseado no usuário"""
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db

    @router.post("", response_model=School, status_code=status.HTTP_201_CREATED)
    async def create_school(request: Request):
        """Cria nova escola (apenas admin)"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste'])(request)
        current_db = get_db_for_user(current_user)
        
        # Recebe body como dict e limpa strings vazias antes da validação Pydantic
        raw_data = await request.json()
        cleaned_data = {k: (None if v == '' else v) for k, v in raw_data.items()}
        school = SchoolCreate(**cleaned_data)
        
        # [Mai/2026] CAPS lock automático removido — preserva capitalização do usuário.
        school_dict = school.model_dump()
        school_obj = School(**school_dict)
        doc = school_obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        
        # Multi-tenancy: injeta mantenedora_id
        tenant_id = get_mantenedora_scope(current_user, request)
        if tenant_id is None and not is_super_admin(current_user):
            raise HTTPException(status_code=400, detail="Usuário sem mantenedora definida")
        if tenant_id is None:
            # super_admin criando sem tenant selecionado — exige seleção explícita
            raise HTTPException(status_code=400, detail="Selecione uma mantenedora antes de criar a escola")
        doc['mantenedora_id'] = tenant_id
        
        await current_db.schools.insert_one(doc)
        
        cache.invalidate('schools')
        return school_obj

    @router.get("")
    async def list_schools(request: Request, skip: int = 0, limit: int = 100, include_student_count: bool = True):
        """Lista escolas com contagem opcional de alunos ativos"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        # Escopo do tenant para esta request
        tenant_id = get_mantenedora_scope(current_user, request)
        
        # Cache key baseada no papel, escolas do usuário e tenant ativo
        cache_params = {
            'role': current_user['role'],
            'school_ids': sorted(current_user.get('school_ids', [])),
            'tenant': tenant_id or 'ALL',
            'skip': skip, 'limit': limit, 'include_student_count': include_student_count
        }
        cached = cache.get('schools', cache_params)
        if cached is not None:
            return cached
        
        # Papéis que veem todas as escolas (dentro do tenant): admin, admin_teste, super_admin, gerente,
        # semed (Tutor SEMED), semed1 (Tutor), semed2 (Analista), semed3 (Administração),
        # ass_social, ass_social_2, agente_vacinas — todos papéis globais da mantenedora.
        # Alinhado com /app/frontend/src/pages/Users.js (mapa de permissões `schools: 'view'`).
        wide_roles = ['admin', 'admin_teste', 'super_admin', 'gerente', 'semed', 'semed1', 'semed2', 'semed3', 'ass_social', 'ass_social_2', 'agente_vacinas']
        
        base_filter = {}
        if current_user['role'] not in wide_roles:
            base_filter = {"id": {"$in": current_user.get('school_ids', [])}}
        
        # Aplica filtro multi-tenant (respeita super_admin cross-tenant quando sem seleção)
        query = apply_tenant_filter(base_filter, current_user, request)
        
        schools = await current_db.schools.find(query, {"_id": 0}).sort("name", 1).collation({"locale": "pt", "strength": 1}).skip(skip).limit(limit).to_list(limit)
        
        # Adicionar contagem de alunos ativos se solicitado
        if include_student_count and schools:
            school_ids = [s['id'] for s in schools]
            
            # Agregação para contar alunos ativos por escola
            pipeline = [
                {"$match": {"school_id": {"$in": school_ids}, "status": "active"}},
                {"$group": {"_id": "$school_id", "count": {"$sum": 1}}}
            ]
            
            student_counts = await current_db.students.aggregate(pipeline).to_list(None)
            count_map = {item['_id']: item['count'] for item in student_counts}
            
            # Adicionar contagem a cada escola
            for school in schools:
                school['student_count'] = count_map.get(school['id'], 0)
        
        cache.set('schools', cache_params, schools, CACHE_TTL_SCHOOLS)
        return schools

    @router.get("/pre-matricula", response_model=List[School])
    async def list_schools_with_pre_matricula():
        """Lista escolas com pré-matrícula ativa (rota pública)"""
        schools = await db.schools.find(
            {
                "pre_matricula_ativa": True,
                "status": "active"
            },
            {"_id": 0}
        ).sort("name", 1).collation({"locale": "pt", "strength": 1}).to_list(100)
        
        return schools

    @router.get("/{school_id}", response_model=School)
    async def get_school(school_id: str, request: Request):
        """Busca escola por ID"""
        current_user = await AuthMiddleware.verify_school_access(request, school_id)
        current_db = get_db_for_user(current_user)
        
        school = await current_db.schools.find_one({"id": school_id}, {"_id": 0})
        
        if not school:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Escola não encontrada"
            )
        
        # Multi-tenancy: garante que pertence ao tenant atual
        assert_same_tenant(school, current_user, request)
        
        return School(**school)

    @router.put("/{school_id}", response_model=School)
    async def update_school(school_id: str, request: Request):
        """Atualiza escola (admin ou secretário vinculado)"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        # Admin pode editar qualquer escola
        # Secretário pode editar apenas escolas vinculadas
        if current_user['role'] in ['admin', 'admin_teste', 'super_admin', 'gerente']:
            pass  # Admin/super_admin/gerente podem editar
        elif current_user['role'] == 'secretario':
            if school_id not in current_user.get('school_ids', []):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Você não tem permissão para editar esta escola"
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Apenas administradores e secretários podem editar escolas"
            )
        
        # Recebe body como dict e limpa strings vazias antes da validação Pydantic
        raw_data = await request.json()
        cleaned_data = {k: (None if v == '' else v) for k, v in raw_data.items()}
        school_update = SchoolUpdate(**cleaned_data)
        
        update_data = school_update.model_dump(exclude_unset=True)
        
        # [Mai/2026] CAPS lock automático removido — preserva capitalização do usuário.
        
        if update_data:
            # Multi-tenancy: verifica tenant antes de atualizar
            existing = await current_db.schools.find_one({"id": school_id}, {"_id": 0, "mantenedora_id": 1})
            if not existing:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Escola não encontrada"
                )
            assert_same_tenant(existing, current_user, request)
            
            result = await current_db.schools.update_one(
                {"id": school_id},
                {"$set": update_data}
            )
            
            if result.matched_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Escola não encontrada"
                )
        
        updated_school = await current_db.schools.find_one({"id": school_id}, {"_id": 0})
        cache.invalidate('schools')
        return School(**updated_school)

    @router.delete("/{school_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_school(school_id: str, request: Request):
        """Deleta escola definitivamente"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste'])(request)
        current_db = get_db_for_user(current_user)
        
        # Multi-tenancy: verifica tenant antes de deletar
        existing = await current_db.schools.find_one({"id": school_id}, {"_id": 0, "mantenedora_id": 1})
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Escola não encontrada"
            )
        assert_same_tenant(existing, current_user, request)
        
        result = await current_db.schools.delete_one({"id": school_id})
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Escola não encontrada"
            )
        
        cache.invalidate('schools')
        return None

    @router.post("/migrate-bercario", status_code=status.HTTP_200_OK)
    async def migrate_bercario(request: Request):
        """
        Remove o campo 'educacao_infantil_bercario' (antigo) de todas as escolas.
        Apenas admin pode executar.
        """
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste'])(request)
        current_db = get_db_for_user(current_user)
        
        # Remove o campo educacao_infantil_bercario de todas as escolas
        result = await current_db.schools.update_many(
            {"educacao_infantil_bercario": {"$exists": True}},
            {"$unset": {"educacao_infantil_bercario": ""}}
        )
        
        return {
            "message": "Migração concluída",
            "escolas_atualizadas": result.modified_count
        }

    return router
