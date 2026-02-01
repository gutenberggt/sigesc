"""
Router de Turmas - SIGESC
Endpoints para gestão de turmas (classes).
"""

from fastapi import APIRouter, HTTPException, status, Request
from typing import List, Optional

from models import Class, ClassCreate, ClassUpdate
from auth_middleware import AuthMiddleware

router = APIRouter(prefix="/classes", tags=["Turmas"])


def setup_router(db, audit_service, sandbox_db=None):
    """Configura o router com as dependências necessárias"""
    
    def get_db_for_user(user: dict):
        """Retorna o banco correto baseado no usuário"""
        if sandbox_db is not None and (user.get('is_sandbox') or user.get('role') == 'admin_teste'):
            return sandbox_db
        return db

    @router.post("", response_model=Class, status_code=status.HTTP_201_CREATED)
    async def create_class(class_data: ClassCreate, request: Request):
        """Cria nova turma"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        # Verifica acesso à escola
        await AuthMiddleware.verify_school_access(request, class_data.school_id)
        
        class_obj = Class(**class_data.model_dump())
        doc = class_obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        
        await current_db.classes.insert_one(doc)
        
        return class_obj

    @router.get("", response_model=List[Class])
    async def list_classes(request: Request, school_id: Optional[str] = None, skip: int = 0, limit: int = 100):
        """Lista turmas"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        # Constrói filtro
        filter_query = {}
        
        # Admin, admin_teste, SEMED e Secretário podem ver todas as turmas
        if current_user['role'] in ['admin', 'admin_teste', 'semed', 'secretario']:
            if school_id:
                filter_query['school_id'] = school_id
        else:
            # Outros papéis veem apenas das escolas vinculadas
            if school_id and school_id in current_user.get('school_ids', []):
                filter_query['school_id'] = school_id
            else:
                filter_query['school_id'] = {"$in": current_user.get('school_ids', [])}
        
        classes = await current_db.classes.find(filter_query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
        
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
        
        update_data = class_update.model_dump(exclude_unset=True)
        
        if update_data:
            await current_db.classes.update_one(
                {"id": class_id},
                {"$set": update_data}
            )
        
        updated_class = await current_db.classes.find_one({"id": class_id}, {"_id": 0})
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
        
        result = await current_db.classes.delete_one({"id": class_id})
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Turma não encontrada"
            )
        
        return None

    return router
