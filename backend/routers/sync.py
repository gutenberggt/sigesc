"""
Router de Sincronização Offline - SIGESC
Endpoints para sincronização bidirecional de dados offline/online
"""
from fastapi import APIRouter, HTTPException, status, Request
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

# ============= MODELOS PYDANTIC =============

class SyncOperation(BaseModel):
    """Uma operação de sincronização individual"""
    collection: str  # 'grades' ou 'attendance'
    operation: str   # 'create', 'update', 'delete'
    recordId: str
    data: Optional[Dict[str, Any]] = None
    timestamp: str

class SyncPushRequest(BaseModel):
    """Request para enviar operações pendentes ao servidor"""
    operations: List[SyncOperation]

class SyncPushResult(BaseModel):
    """Resultado de uma operação de push"""
    recordId: str
    success: bool
    serverId: Optional[str] = None
    error: Optional[str] = None

class SyncPushResponse(BaseModel):
    """Response do endpoint de push"""
    processed: int
    succeeded: int
    failed: int
    results: List[SyncPushResult]

class SyncPullRequest(BaseModel):
    """Request para baixar dados do servidor"""
    collections: List[str]  # Quais coleções sincronizar
    classId: Optional[str] = None  # Filtro por turma
    academicYear: Optional[str] = None  # Filtro por ano letivo
    lastSync: Optional[str] = None  # Data da última sincronização (para delta sync)

class SyncPullResponse(BaseModel):
    """Response do endpoint de pull"""
    data: Dict[str, List[Dict[str, Any]]]
    syncedAt: str
    counts: Dict[str, int]


def setup_sync_router(db, auth_middleware):
    """Configura o router de sincronização"""
    
    router = APIRouter(prefix="/sync", tags=["Sincronização Offline"])
    
    @router.post("/push", response_model=SyncPushResponse)
    async def sync_push(request: Request, body: SyncPushRequest):
        """
        Recebe operações pendentes do cliente e processa no servidor.
        Usado quando o cliente volta online após edições offline.
        """
        current_user = await auth_middleware.get_current_user(request)
        
        results = []
        succeeded = 0
        failed = 0
        
        for op in body.operations:
            try:
                result = await process_sync_operation(db, current_user, op)
                results.append(result)
                if result.success:
                    succeeded += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"[Sync] Erro ao processar operação {op.recordId}: {e}")
                results.append(SyncPushResult(
                    recordId=op.recordId,
                    success=False,
                    error=str(e)
                ))
                failed += 1
        
        return SyncPushResponse(
            processed=len(body.operations),
            succeeded=succeeded,
            failed=failed,
            results=results
        )
    
    @router.post("/pull", response_model=SyncPullResponse)
    async def sync_pull(request: Request, body: SyncPullRequest):
        """
        Envia dados do servidor para o cliente popular o cache local.
        Usado para sincronização inicial ou refresh de dados.
        """
        current_user = await auth_middleware.get_current_user(request)
        
        data = {}
        counts = {}
        
        for collection in body.collections:
            try:
                collection_data = await fetch_collection_data(
                    db, 
                    current_user, 
                    collection, 
                    body.classId, 
                    body.academicYear,
                    body.lastSync
                )
                data[collection] = collection_data
                counts[collection] = len(collection_data)
            except Exception as e:
                logger.error(f"[Sync] Erro ao buscar {collection}: {e}")
                data[collection] = []
                counts[collection] = 0
        
        return SyncPullResponse(
            data=data,
            syncedAt=datetime.now(timezone.utc).isoformat(),
            counts=counts
        )
    
    @router.get("/status")
    async def sync_status(request: Request):
        """
        Retorna status de sincronização do usuário.
        """
        current_user = await auth_middleware.get_current_user(request)
        
        # Conta registros nas coleções principais
        grades_count = await db.grades.count_documents({})
        attendance_count = await db.attendance.count_documents({})
        students_count = await db.students.count_documents({})
        classes_count = await db.classes.count_documents({})
        courses_count = await db.courses.count_documents({})
        
        return {
            "serverTime": datetime.now(timezone.utc).isoformat(),
            "collections": {
                "grades": grades_count,
                "attendance": attendance_count,
                "students": students_count,
                "classes": classes_count,
                "courses": courses_count
            },
            "user": {
                "id": current_user["id"],
                "role": current_user["role"]
            }
        }
    
    return router


async def process_sync_operation(db, user, op: SyncOperation) -> SyncPushResult:
    """Processa uma operação de sincronização individual"""
    
    collection_name = op.collection
    operation = op.operation
    record_id = op.recordId
    data = op.data or {}
    
    # Mapeia nome da coleção para a collection do MongoDB
    collection_map = {
        'grades': db.grades,
        'attendance': db.attendance,
        'students': db.students
    }
    
    if collection_name not in collection_map:
        return SyncPushResult(
            recordId=record_id,
            success=False,
            error=f"Coleção desconhecida: {collection_name}"
        )
    
    collection = collection_map[collection_name]
    
    try:
        if operation == 'create':
            # Remove campos de controle local
            clean_data = clean_sync_data(data)
            
            # Verifica se é um ID temporário
            if record_id.startswith('temp_'):
                # Gera novo ID no servidor
                import uuid
                server_id = str(uuid.uuid4())
                clean_data['id'] = server_id
            else:
                clean_data['id'] = record_id
                server_id = record_id
            
            # Adiciona metadados
            clean_data['created_at'] = datetime.now(timezone.utc).isoformat()
            clean_data['created_by'] = user['id']
            
            await collection.insert_one(clean_data)
            
            return SyncPushResult(
                recordId=record_id,
                success=True,
                serverId=server_id
            )
            
        elif operation == 'update':
            clean_data = clean_sync_data(data)
            clean_data['updated_at'] = datetime.now(timezone.utc).isoformat()
            clean_data['updated_by'] = user['id']
            
            # Atualiza o registro
            result = await collection.update_one(
                {'id': record_id},
                {'$set': clean_data}
            )
            
            if result.matched_count == 0:
                return SyncPushResult(
                    recordId=record_id,
                    success=False,
                    error="Registro não encontrado no servidor"
                )
            
            return SyncPushResult(
                recordId=record_id,
                success=True,
                serverId=record_id
            )
            
        elif operation == 'delete':
            result = await collection.delete_one({'id': record_id})
            
            return SyncPushResult(
                recordId=record_id,
                success=True if result.deleted_count > 0 else False,
                error=None if result.deleted_count > 0 else "Registro não encontrado"
            )
            
        else:
            return SyncPushResult(
                recordId=record_id,
                success=False,
                error=f"Operação desconhecida: {operation}"
            )
            
    except Exception as e:
        logger.error(f"[Sync] Erro em {operation} {collection_name}/{record_id}: {e}")
        return SyncPushResult(
            recordId=record_id,
            success=False,
            error=str(e)
        )


def clean_sync_data(data: dict) -> dict:
    """Remove campos de controle local dos dados"""
    if not data:
        return {}
    
    # Campos que devem ser removidos
    local_fields = ['localId', 'syncStatus', '_id']
    
    cleaned = {k: v for k, v in data.items() if k not in local_fields}
    
    # Remove ID temporário
    if cleaned.get('id', '').startswith('temp_'):
        del cleaned['id']
    
    return cleaned


async def fetch_collection_data(
    db, 
    user, 
    collection: str, 
    class_id: Optional[str],
    academic_year: Optional[str],
    last_sync: Optional[str]
) -> List[Dict[str, Any]]:
    """Busca dados de uma coleção para sincronização"""
    
    query = {}
    
    # Filtros comuns
    if class_id:
        query['class_id'] = class_id
    if academic_year:
        query['academic_year'] = academic_year
    
    # Delta sync - apenas registros modificados após última sincronização
    if last_sync:
        try:
            query['$or'] = [
                {'created_at': {'$gte': last_sync}},
                {'updated_at': {'$gte': last_sync}}
            ]
        except:
            pass  # Ignora se formato de data inválido
    
    # Busca baseada na coleção
    if collection == 'grades':
        cursor = db.grades.find(query, {'_id': 0})
        return await cursor.to_list(5000)
        
    elif collection == 'attendance':
        cursor = db.attendance.find(query, {'_id': 0})
        return await cursor.to_list(5000)
        
    elif collection == 'students':
        student_query = {}
        if class_id:
            # Busca matrículas da turma e depois os alunos
            enrollments = await db.enrollments.find(
                {'class_id': class_id, 'status': 'active'},
                {'student_id': 1}
            ).to_list(500)
            
            student_ids = [e['student_id'] for e in enrollments]
            student_query['id'] = {'$in': student_ids}
        
        cursor = db.students.find(student_query, {'_id': 0})
        return await cursor.to_list(1000)
        
    elif collection == 'classes':
        class_query = {}
        if academic_year:
            class_query['academic_year'] = academic_year
            
        # Filtra por escolas do usuário se não for admin
        if user['role'] != 'admin' and user.get('school_ids'):
            class_query['school_id'] = {'$in': user['school_ids']}
        
        cursor = db.classes.find(class_query, {'_id': 0})
        return await cursor.to_list(500)
        
    elif collection == 'courses':
        course_query = {}
        
        # Filtra por escolas do usuário se não for admin
        if user['role'] != 'admin' and user.get('school_ids'):
            course_query['school_id'] = {'$in': user['school_ids']}
        
        cursor = db.courses.find(course_query, {'_id': 0})
        return await cursor.to_list(500)
        
    elif collection == 'schools':
        school_query = {}
        
        # Filtra por escolas do usuário se não for admin
        if user['role'] != 'admin' and user.get('school_ids'):
            school_query['id'] = {'$in': user['school_ids']}
        
        cursor = db.schools.find(school_query, {'_id': 0})
        return await cursor.to_list(100)
    
    else:
        logger.warning(f"[Sync] Coleção desconhecida para pull: {collection}")
        return []
