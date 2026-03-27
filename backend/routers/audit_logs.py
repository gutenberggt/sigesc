"""
Router para Auditoria.
Extraído automaticamente de server.py.
"""

from fastapi import APIRouter, Request
from typing import Optional
from datetime import datetime, timezone, timedelta

from models import *
from auth_middleware import AuthMiddleware


router = APIRouter(tags=["Auditoria"])


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências."""
    
    # Helper para obter DB correto (produção ou sandbox)
    def get_db_for_user(user: dict):
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db



    @router.get("/audit-logs")
    async def list_audit_logs(
        request: Request,
        skip: int = 0,
        limit: int = 50,
        user_id: Optional[str] = None,
        user_role: Optional[str] = None,
        school_id: Optional[str] = None,
        collection: Optional[str] = None,
        action: Optional[str] = None,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        academic_year: Optional[int] = None,
        search: Optional[str] = None
    ):
        """
        Lista logs de auditoria com filtros.
        Apenas admin e secretário podem visualizar.
        """
        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'semed', 'semed1', 'semed2', 'semed3'])(request)

        filters = {
            'user_id': user_id,
            'user_role': user_role,
            'school_id': school_id,
            'collection': collection,
            'action': action,
            'category': category,
            'severity': severity,
            'start_date': start_date,
            'end_date': end_date,
            'academic_year': academic_year,
            'search': search
        }

        # Remove filtros vazios
        filters = {k: v for k, v in filters.items() if v is not None}

        logs, total = await audit_service.get_logs(filters, skip, limit)

        return {
            'items': logs,
            'total': total,
            'skip': skip,
            'limit': limit
        }


    @router.get("/audit-logs/user/{user_id}")
    async def get_user_audit_logs(user_id: str, request: Request, limit: int = 20):
        """Retorna atividades recentes de um usuário específico"""
        current_user = await AuthMiddleware.require_roles(['admin', 'semed3'])(request)

        logs = await audit_service.get_user_activity(user_id, limit)
        return {'items': logs}


    @router.get("/audit-logs/document/{collection}/{document_id}")
    async def get_document_audit_history(collection: str, document_id: str, request: Request):
        """Retorna histórico de alterações de um documento específico"""
        current_user = await AuthMiddleware.require_roles(['admin', 'semed3', 'diretor'])(request)

        logs = await audit_service.get_document_history(collection, document_id)
        return {'items': logs}


    @router.get("/audit-logs/critical")
    async def get_critical_audit_events(request: Request, hours: int = 24):
        """Retorna eventos críticos das últimas X horas"""
        current_user = await AuthMiddleware.require_roles(['admin', 'semed3'])(request)

        logs = await audit_service.get_critical_events(hours)
        return {'items': logs, 'hours': hours}


    @router.get("/audit-logs/stats")
    async def get_audit_stats(request: Request, days: int = 7):
        """Retorna estatísticas de auditoria"""
        current_user = await AuthMiddleware.require_roles(['admin', 'semed3'])(request)

        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        # Estatísticas por ação
        pipeline_action = [
            {'$match': {'timestamp': {'$gte': cutoff}}},
            {'$group': {'_id': '$action', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}
        ]

        # Estatísticas por coleção
        pipeline_collection = [
            {'$match': {'timestamp': {'$gte': cutoff}}},
            {'$group': {'_id': '$collection', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}
        ]

        # Estatísticas por usuário
        pipeline_user = [
            {'$match': {'timestamp': {'$gte': cutoff}}},
            {'$group': {'_id': {'id': '$user_id', 'email': '$user_email'}, 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}},
            {'$limit': 10}
        ]

        # Estatísticas por severidade
        pipeline_severity = [
            {'$match': {'timestamp': {'$gte': cutoff}}},
            {'$group': {'_id': '$severity', 'count': {'$sum': 1}}}
        ]

        by_action = await db.audit_logs.aggregate(pipeline_action).to_list(length=20)
        by_collection = await db.audit_logs.aggregate(pipeline_collection).to_list(length=20)
        by_user = await db.audit_logs.aggregate(pipeline_user).to_list(length=10)
        by_severity = await db.audit_logs.aggregate(pipeline_severity).to_list(length=5)

        total = await db.audit_logs.count_documents({'timestamp': {'$gte': cutoff}})

        return {
            'period_days': days,
            'total_events': total,
            'by_action': by_action,
            'by_collection': by_collection,
            'by_user': by_user,
            'by_severity': by_severity
        }

    return router
