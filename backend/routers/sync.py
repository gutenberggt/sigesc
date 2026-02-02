"""
Router de Sincronização Offline - SIGESC
Endpoints para sincronização bidirecional de dados offline/online

PATCHES DE SEGURANÇA FASE 2:
- PATCH 2.1: Filtragem de campos sensíveis
- PATCH 2.2: Paginação no sync pull
- PATCH 2.3: Rate limiting específico
"""
from fastapi import APIRouter, HTTPException, status, Request
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

# PATCH 2.1: Campos sensíveis que NUNCA devem ser sincronizados
SENSITIVE_FIELDS = {
    'students': ['password_hash', 'nis', 'cpf', 'rg', 'cartao_sus', 'certidao_nascimento', 
                 'guardian_cpf', 'mother_cpf', 'father_cpf', 'mother_rg', 'father_rg',
                 'bank_account', 'pix_key', 'income', 'bolsa_familia'],
    'users': ['password_hash', 'refresh_token', 'cpf', 'rg'],
    'staff': ['password_hash', 'cpf', 'rg', 'pis_pasep', 'bank_account', 'salary'],
    'schools': ['cnpj', 'bank_account', 'pix_key'],
    'guardians': ['cpf', 'rg', 'bank_account', 'pix_key', 'income'],
    # Coleções sem campos sensíveis
    'grades': [],
    'attendance': [],
    'classes': [],
    'courses': [],
    'enrollments': []
}

# PATCH 2.2: Limites de paginação
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500

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
    # PATCH 2.2: Parâmetros de paginação
    page: Optional[int] = 1  # Página atual (começa em 1)
    pageSize: Optional[int] = DEFAULT_PAGE_SIZE  # Itens por página

class SyncPullResponse(BaseModel):
    """Response do endpoint de pull"""
    data: Dict[str, List[Dict[str, Any]]]
    syncedAt: str
    counts: Dict[str, int]
    # PATCH 2.2: Informações de paginação
    pagination: Optional[Dict[str, Any]] = None


def setup_sync_router(db, auth_middleware, limiter=None):
    """Configura o router de sincronização"""
    
    router = APIRouter(prefix="/sync", tags=["Sincronização Offline"])
    
    @router.post("/push", response_model=SyncPushResponse)
    async def sync_push(request: Request, body: SyncPushRequest):
        """
        Recebe operações pendentes do cliente e processa no servidor.
        Usado quando o cliente volta online após edições offline.
        
        PATCH 2.3: Rate limited para evitar abuso
        """
        current_user = await auth_middleware.get_current_user(request)
        
        # PATCH 2.3: Limite de operações por requisição
        MAX_OPERATIONS_PER_REQUEST = 100
        if len(body.operations) > MAX_OPERATIONS_PER_REQUEST:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Máximo de {MAX_OPERATIONS_PER_REQUEST} operações por requisição. Envie em lotes menores."
            )
        
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
        
        PATCH 2.1: Campos sensíveis são filtrados automaticamente
        PATCH 2.2: Suporta paginação para evitar sobrecarga
        """
        current_user = await auth_middleware.get_current_user(request)
        
        # PATCH 2.2: Validar e limitar tamanho da página
        page = max(1, body.page or 1)
        page_size = min(MAX_PAGE_SIZE, max(1, body.pageSize or DEFAULT_PAGE_SIZE))
        
        # PATCH 2.3: Limite de coleções por requisição
        MAX_COLLECTIONS_PER_REQUEST = 5
        if len(body.collections) > MAX_COLLECTIONS_PER_REQUEST:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Máximo de {MAX_COLLECTIONS_PER_REQUEST} coleções por requisição."
            )
        
        data = {}
        counts = {}
        pagination_info = {}
        
        for collection in body.collections:
            try:
                # PATCH 2.2: Busca com paginação
                collection_data, total_count = await fetch_collection_data_paginated(
                    db, 
                    current_user, 
                    collection, 
                    body.classId, 
                    body.academicYear,
                    body.lastSync,
                    page,
                    page_size
                )
                
                # PATCH 2.1: Filtrar campos sensíveis
                filtered_data = filter_sensitive_fields(collection_data, collection)
                
                data[collection] = filtered_data
                counts[collection] = len(filtered_data)
                
                # PATCH 2.2: Informações de paginação por coleção
                total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
                pagination_info[collection] = {
                    "page": page,
                    "pageSize": page_size,
                    "totalItems": total_count,
                    "totalPages": total_pages,
                    "hasMore": page < total_pages
                }
                
            except Exception as e:
                logger.error(f"[Sync] Erro ao buscar {collection}: {e}")
                data[collection] = []
                counts[collection] = 0
                pagination_info[collection] = {"error": str(e)}
        
        return SyncPullResponse(
            data=data,
            syncedAt=datetime.now(timezone.utc).isoformat(),
            counts=counts,
            pagination=pagination_info
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


# PATCH 2.1: Função para filtrar campos sensíveis
def filter_sensitive_fields(data: List[Dict[str, Any]], collection: str) -> List[Dict[str, Any]]:
    """
    Remove campos sensíveis dos dados antes de enviar ao cliente.
    PATCH 2.1: Proteção contra vazamento de dados pessoais no sync offline.
    """
    sensitive = SENSITIVE_FIELDS.get(collection, [])
    
    if not sensitive:
        return data  # Nenhum campo sensível para esta coleção
    
    filtered = []
    for item in data:
        # Cria cópia sem os campos sensíveis
        filtered_item = {k: v for k, v in item.items() if k not in sensitive}
        filtered.append(filtered_item)
    
    if data and sensitive:
        logger.debug(f"[Sync] Filtrados {len(sensitive)} campos sensíveis de {len(data)} registros em {collection}")
    
    return filtered


# PATCH 2.2: Função de busca com paginação
async def fetch_collection_data_paginated(
    db, 
    user, 
    collection: str, 
    class_id: Optional[str],
    academic_year: Optional[str],
    last_sync: Optional[str],
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE
) -> tuple:
    """
    Busca dados de uma coleção para sincronização com paginação.
    Retorna tupla (dados, total_count) para suportar paginação.
    
    PATCH 2.2: Implementa paginação para evitar sobrecarga de memória.
    """
    
    query = {}
    skip = (page - 1) * page_size
    
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
        total = await db.grades.count_documents(query)
        cursor = db.grades.find(query, {'_id': 0}).skip(skip).limit(page_size)
        return await cursor.to_list(page_size), total
        
    elif collection == 'attendance':
        total = await db.attendance.count_documents(query)
        cursor = db.attendance.find(query, {'_id': 0}).skip(skip).limit(page_size)
        return await cursor.to_list(page_size), total
        
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
        
        total = await db.students.count_documents(student_query)
        cursor = db.students.find(student_query, {'_id': 0}).skip(skip).limit(page_size)
        return await cursor.to_list(page_size), total
        
    elif collection == 'classes':
        class_query = {}
        if academic_year:
            class_query['academic_year'] = academic_year
            
        # Filtra por escolas do usuário se não for admin
        if user['role'] not in ['admin', 'admin_teste'] and user.get('school_ids'):
            class_query['school_id'] = {'$in': user['school_ids']}
        
        total = await db.classes.count_documents(class_query)
        cursor = db.classes.find(class_query, {'_id': 0}).skip(skip).limit(page_size)
        return await cursor.to_list(page_size), total
        
    elif collection == 'courses':
        course_query = {}
        
        # Filtra por escolas do usuário se não for admin
        if user['role'] not in ['admin', 'admin_teste'] and user.get('school_ids'):
            course_query['school_id'] = {'$in': user['school_ids']}
        
        total = await db.courses.count_documents(course_query)
        cursor = db.courses.find(course_query, {'_id': 0}).skip(skip).limit(page_size)
        return await cursor.to_list(page_size), total
        
    elif collection == 'schools':
        school_query = {}
        
        # Filtra por escolas do usuário se não for admin
        if user['role'] not in ['admin', 'admin_teste'] and user.get('school_ids'):
            school_query['id'] = {'$in': user['school_ids']}
        
        total = await db.schools.count_documents(school_query)
        cursor = db.schools.find(school_query, {'_id': 0}).skip(skip).limit(page_size)
        return await cursor.to_list(page_size), total
    
    else:
        logger.warning(f"[Sync] Coleção desconhecida para pull: {collection}")
        return [], 0


# Mantém função antiga para compatibilidade (deprecated)
async def fetch_collection_data(
    db, 
    user, 
    collection: str, 
    class_id: Optional[str],
    academic_year: Optional[str],
    last_sync: Optional[str]
) -> List[Dict[str, Any]]:
    """
    DEPRECATED: Use fetch_collection_data_paginated
    Mantida para compatibilidade com código existente.
    """
    data, _ = await fetch_collection_data_paginated(
        db, user, collection, class_id, academic_year, last_sync, 
        page=1, page_size=5000  # Limite alto para compatibilidade
    )
    return data
