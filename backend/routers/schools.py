"""
Router de Escolas - SIGESC
Endpoints para gestão de escolas.
"""

from fastapi import APIRouter, HTTPException, status, Request
from typing import List

from models import School, SchoolCreate, SchoolUpdate
from auth_middleware import AuthMiddleware

router = APIRouter(prefix="/schools", tags=["Escolas"])


def setup_router(db, audit_service):
    """Configura o router com as dependências necessárias"""

    @router.post("", response_model=School, status_code=status.HTTP_201_CREATED)
    async def create_school(school: SchoolCreate, request: Request):
        """Cria nova escola (apenas admin)"""
        current_user = await AuthMiddleware.require_roles(['admin'])(request)
        
        school_obj = School(**school.model_dump())
        doc = school_obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        
        await db.schools.insert_one(doc)
        
        return school_obj

    @router.get("", response_model=List[School])
    async def list_schools(request: Request, skip: int = 0, limit: int = 100):
        """Lista escolas"""
        current_user = await AuthMiddleware.get_current_user(request)
        
        # Admin e SEMED veem todas as escolas
        if current_user['role'] in ['admin', 'semed']:
            schools = await db.schools.find({}, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
        else:
            # Outros papéis veem apenas escolas vinculadas
            schools = await db.schools.find(
                {"id": {"$in": current_user['school_ids']}},
                {"_id": 0}
            ).skip(skip).limit(limit).to_list(limit)
        
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
        """Atualiza escola"""
        current_user = await AuthMiddleware.require_roles(['admin'])(request)
        
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

    return router
