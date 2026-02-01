"""
Router de Escolas - SIGESC
Endpoints para gestão de escolas.
"""

from fastapi import APIRouter, HTTPException, status, Request
from typing import List

from models import School, SchoolCreate, SchoolUpdate
from auth_middleware import AuthMiddleware

router = APIRouter(prefix="/schools", tags=["Escolas"])


def setup_router(db, audit_service, sandbox_db=None):
    """Configura o router com as dependências necessárias"""
    
    def get_db_for_user(user: dict):
        """Retorna o banco correto baseado no usuário"""
        if sandbox_db and (user.get('is_sandbox') or user.get('role') == 'admin_teste'):
            return sandbox_db
        return db

    @router.post("", response_model=School, status_code=status.HTTP_201_CREATED)
    async def create_school(school: SchoolCreate, request: Request):
        """Cria nova escola (apenas admin)"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste'])(request)
        current_db = get_db_for_user(current_user)
        
        school_obj = School(**school.model_dump())
        doc = school_obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        
        await current_db.schools.insert_one(doc)
        
        return school_obj

    @router.get("")
    async def list_schools(request: Request, skip: int = 0, limit: int = 100, include_student_count: bool = True):
        """Lista escolas com contagem opcional de alunos ativos"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        # Admin, admin_teste e SEMED veem todas as escolas
        if current_user['role'] in ['admin', 'admin_teste', 'semed']:
            schools = await current_db.schools.find({}, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
        else:
            # Outros papéis veem apenas escolas vinculadas
            schools = await current_db.schools.find(
                {"id": {"$in": current_user['school_ids']}},
                {"_id": 0}
            ).skip(skip).limit(limit).to_list(limit)
        
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
        ).to_list(100)
        
        return schools

    @router.get("/{school_id}", response_model=School)
    async def get_school(school_id: str, request: Request):
        """Busca escola por ID"""
        current_user = await AuthMiddleware.verify_school_access(request, school_id)
        
        school = await db.schools.find_one({"id": school_id}, {"_id": 0})
        
        if not school:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Escola não encontrada"
            )
        
        return School(**school)

    @router.put("/{school_id}", response_model=School)
    async def update_school(school_id: str, school_update: SchoolUpdate, request: Request):
        """Atualiza escola (admin ou secretário vinculado)"""
        current_user = await AuthMiddleware.get_current_user(request)
        
        # Admin pode editar qualquer escola
        # Secretário pode editar apenas escolas vinculadas
        if current_user['role'] == 'admin':
            pass  # Admin pode editar qualquer escola
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
        
        update_data = school_update.model_dump(exclude_unset=True)
        
        if update_data:
            result = await db.schools.update_one(
                {"id": school_id},
                {"$set": update_data}
            )
            
            if result.matched_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Escola não encontrada"
                )
        
        updated_school = await db.schools.find_one({"id": school_id}, {"_id": 0})
        return School(**updated_school)

    @router.delete("/{school_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_school(school_id: str, request: Request):
        """Deleta escola definitivamente"""
        current_user = await AuthMiddleware.require_roles(['admin'])(request)
        
        result = await db.schools.delete_one({"id": school_id})
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Escola não encontrada"
            )
        
        return None

    @router.post("/migrate-bercario", status_code=status.HTTP_200_OK)
    async def migrate_bercario(request: Request):
        """
        Remove o campo 'educacao_infantil_bercario' (antigo) de todas as escolas.
        Apenas admin pode executar.
        """
        current_user = await AuthMiddleware.require_roles(['admin'])(request)
        
        # Remove o campo educacao_infantil_bercario de todas as escolas
        result = await db.schools.update_many(
            {"educacao_infantil_bercario": {"$exists": True}},
            {"$unset": {"educacao_infantil_bercario": ""}}
        )
        
        return {
            "message": "Migração concluída",
            "escolas_atualizadas": result.modified_count
        }

    return router
