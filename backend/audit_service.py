"""
Serviço de Auditoria - SIGESC.

P0 MT-1 (2026-09-06):
- novos eventos persistem ``mantenedora_id`` quando há contexto operacional;
- leituras operacionais exigem tenant explícito e são fail-closed;
- logs legados sem tenant só aparecem quando existe evidência inequívoca por
  ``school_id`` ou pelo usuário ator pertencente à mantenedora ativa;
- nenhum backfill é executado por esta camada.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List, Literal
from fastapi import Request
import logging
import re

from utils.client_time import current_time_context, local_day_bounds_utc, local_now

logger = logging.getLogger(__name__)

AUDITED_COLLECTIONS = {
    'grades': {'severity': 'critical', 'category': 'academic'},
    'attendance': {'severity': 'critical', 'category': 'academic'},
    'students': {'severity': 'warning', 'category': 'administrative'},
    'student_health_profiles': {'severity': 'critical', 'category': 'health'},
    'enrollments': {'severity': 'warning', 'category': 'administrative'},
    'staff': {'severity': 'warning', 'category': 'administrative'},
    'school_assignments': {'severity': 'warning', 'category': 'administrative'},
    'teacher_assignments': {'severity': 'warning', 'category': 'administrative'},
    'classes': {'severity': 'info', 'category': 'administrative'},
    'schools': {'severity': 'info', 'category': 'administrative'},
    'courses': {'severity': 'info', 'category': 'administrative'},
    'users': {'severity': 'critical', 'category': 'auth'},
    'mantenedora': {'severity': 'warning', 'category': 'administrative'},
    'calendario_letivo': {'severity': 'info', 'category': 'administrative'},
}

ACTION_DESCRIPTIONS = {
    'create': 'criou',
    'update': 'alterou',
    'delete': 'excluiu',
    'login': 'entrou no sistema',
    'logout': 'saiu do sistema',
    'export': 'exportou',
    'import': 'importou',
    'approve': 'aprovou',
    'reject': 'rejeitou',
    'access': 'acessou',
}

COLLECTION_NAMES = {
    'grades': 'notas',
    'attendance': 'frequência',
    'students': 'estudante',
    'student_health_profiles': 'ficha de saúde do estudante',
    'enrollments': 'matrícula',
    'staff': 'servidor',
    'school_assignments': 'lotação',
    'teacher_assignments': 'alocação de professor',
    'classes': 'turma',
    'schools': 'escola',
    'courses': 'componente curricular',
    'users': 'usuário',
    'mantenedora': 'mantenedora',
    'calendario_letivo': 'calendário letivo',
    'learning_objects': 'objeto de conhecimento',
    'content_entries': 'conteúdo pedagógico',
}


class AuditService:
    """Serviço de auditoria com isolamento obrigatório por mantenedora."""

    def __init__(self):
        self.db = None
        self._enabled = True

    def set_db(self, db):
        self.db = db

    def disable(self):
        self._enabled = False

    def enable(self):
        self._enabled = True

    @staticmethod
    def _normalized_tenant_id(value) -> Optional[str]:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    async def _resolve_log_tenant_id(self, user: dict, school_id: str = None) -> Optional[str]:
        """Resolve tenant do novo evento sem confiar em payload arbitrário do cliente."""
        tenant_id = self._normalized_tenant_id(
            (user or {}).get('active_mantenedora_id') or (user or {}).get('mantenedora_id')
        )
        if tenant_id or not school_id or self.db is None:
            return tenant_id

        school = await self.db.schools.find_one(
            {'id': school_id},
            {'_id': 0, 'mantenedora_id': 1},
        )
        return self._normalized_tenant_id((school or {}).get('mantenedora_id'))

    async def build_tenant_scope_query(self, tenant_id: str) -> dict:
        """Monta filtro tenant-scoped, incluindo legado apenas com evidência forte.

        Logs novos usam ``mantenedora_id`` diretamente. Para o legado sem esse
        campo, aceitamos somente:
        - ``school_id`` de escola pertencente ao tenant; ou
        - ``user_id`` de usuário cujo documento atual declara o mesmo tenant.

        Sem tenant, retorna filtro impossível (fail-closed). Nenhum documento é
        modificado, apropriado ou retroativamente associado.
        """
        tenant_id = self._normalized_tenant_id(tenant_id)
        if not tenant_id or self.db is None:
            return {'_id': {'$exists': False}}

        school_docs = await self.db.schools.find(
            {'mantenedora_id': tenant_id},
            {'_id': 0, 'id': 1},
        ).to_list(length=None)
        user_docs = await self.db.users.find(
            {'mantenedora_id': tenant_id},
            {'_id': 0, 'id': 1},
        ).to_list(length=None)

        school_ids = [d.get('id') for d in school_docs if d.get('id')]
        user_ids = [d.get('id') for d in user_docs if d.get('id')]

        evidence = []
        if school_ids:
            evidence.append({'school_id': {'$in': school_ids}})
        if user_ids:
            evidence.append({'user_id': {'$in': user_ids}})

        direct = {'mantenedora_id': tenant_id}
        if not evidence:
            return direct

        unscoped = {
            '$or': [
                {'mantenedora_id': {'$exists': False}},
                {'mantenedora_id': None},
                {'mantenedora_id': ''},
            ]
        }
        legacy_with_evidence = {'$and': [unscoped, {'$or': evidence}]}
        return {'$or': [direct, legacy_with_evidence]}

    @staticmethod
    def _combine_query(scope_query: dict, domain_query: dict) -> dict:
        if not domain_query:
            return scope_query
        return {'$and': [scope_query, domain_query]}

    async def log(
        self,
        action: Literal['create', 'update', 'delete', 'login', 'logout', 'export', 'import', 'approve', 'reject', 'access'],
        collection: str,
        user: dict,
        request: Request = None,
        document_id: str = None,
        description: str = None,
        old_value: dict = None,
        new_value: dict = None,
        school_id: str = None,
        school_name: str = None,
        academic_year: int = None,
        extra_data: dict = None,
    ):
        if not self._enabled or self.db is None:
            return

        try:
            collection_config = AUDITED_COLLECTIONS.get(
                collection, {'severity': 'info', 'category': 'system'}
            )

            if not description:
                action_text = ACTION_DESCRIPTIONS.get(action, action)
                collection_text = COLLECTION_NAMES.get(collection, collection)
                description = f"Usuário {action_text} {collection_text}"
                if document_id:
                    description += f" (ID: {document_id[:8]}...)"

            changes = None
            if old_value and new_value and action == 'update':
                changes = self._calculate_changes(old_value, new_value)

            ip_address = None
            user_agent = None
            if request:
                ip_address = request.client.host if request.client else None
                user_agent = request.headers.get('user-agent', '')[:200]

            now_utc = datetime.now(timezone.utc)
            time_ctx = current_time_context(now_utc)
            tenant_id = await self._resolve_log_tenant_id(user or {}, school_id)

            audit_record = {
                'action': action,
                'collection': collection,
                'document_id': document_id,
                'mantenedora_id': tenant_id,
                'user_id': (user or {}).get('id'),
                'user_email': (user or {}).get('email'),
                'user_role': (user or {}).get('role'),
                'user_name': (user or {}).get('full_name') or (user or {}).get('name'),
                'school_id': school_id,
                'school_name': school_name,
                'academic_year': academic_year or local_now(now_utc).year,
                'description': description,
                'old_value': self._sanitize_value(old_value),
                'new_value': self._sanitize_value(new_value),
                'changes': changes,
                'ip_address': ip_address,
                'user_agent': user_agent,
                'timestamp': now_utc.isoformat(),
                'timestamp_utc': time_ctx['timestamp_utc'],
                'timestamp_local': time_ctx['timestamp_local'],
                'timezone': time_ctx['timezone'],
                'utc_offset_minutes': time_ctx['utc_offset_minutes'],
                'timezone_source': time_ctx['timezone_source'],
                'severity': collection_config['severity'],
                'category': collection_config['category'],
            }
            if extra_data:
                audit_record['extra_data'] = extra_data

            await self.db.audit_logs.insert_one(audit_record)
            logger.info(
                "AUDIT: [%s] %s - %s - User: %s - Tenant: %s",
                action.upper(), collection, description, (user or {}).get('email'), tenant_id,
            )
        except Exception as exc:
            # Auditoria não derruba a operação principal, mas o erro é observável.
            logger.error("Erro ao registrar auditoria: %s", str(exc))

    def _calculate_changes(self, old_value: dict, new_value: dict) -> dict:
        changes = {}
        ignore_fields = {'_id', 'created_at', 'updated_at', 'id'}
        all_keys = set(old_value.keys()) | set(new_value.keys())
        for key in all_keys:
            if key in ignore_fields:
                continue
            old_val = old_value.get(key)
            new_val = new_value.get(key)
            if old_val != new_val:
                changes[key] = {'old': old_val, 'new': new_val}
        return changes if changes else None

    def _sanitize_value(self, value: dict) -> dict:
        if not value:
            return None
        sensitive_fields = {
            'password', 'password_hash', 'token', 'access_token', 'refresh_token', 'secret',
            'blood_type', 'has_allergies', 'allergies_description',
            'has_comorbidities', 'comorbidities_description',
            'uses_continuous_medication', 'continuous_medication_description',
            'continuous_medication_instructions', 'individualized_nutritional_need',
            'nutritional_need_details', 'health_notes',
        }
        sanitized = {}
        for key, val in value.items():
            if key.lower() in sensitive_fields:
                sanitized[key] = '***REDACTED***'
            elif key == '_id':
                sanitized[key] = str(val)
            elif isinstance(val, dict):
                sanitized[key] = self._sanitize_value(val)
            else:
                sanitized[key] = val
        return sanitized

    async def get_logs(
        self,
        filters: dict = None,
        skip: int = 0,
        limit: int = 50,
        sort_by: str = 'timestamp',
        sort_order: int = -1,
        tenant_id: str = None,
    ) -> tuple:
        """Busca logs exclusivamente da mantenedora operacional informada."""
        if self.db is None:
            return [], 0

        scope_query = await self.build_tenant_scope_query(tenant_id)
        query = {}
        filters = filters or {}

        for key in (
            'user_id', 'user_role', 'school_id', 'collection', 'action',
            'category', 'severity', 'academic_year', 'document_id',
        ):
            if filters.get(key) is not None:
                query[key] = filters[key]

        if filters.get('start_date') or filters.get('end_date'):
            start_utc, end_utc = local_day_bounds_utc(
                filters.get('start_date'), filters.get('end_date')
            )
            query['timestamp'] = {}
            if start_utc:
                query['timestamp']['$gte'] = start_utc
            if end_utc:
                query['timestamp']['$lte'] = end_utc

        if filters.get('timestamp_gte'):
            query.setdefault('timestamp', {})['$gte'] = filters['timestamp_gte']

        if filters.get('search'):
            query['description'] = {'$regex': filters['search'], '$options': 'i'}

        query = self._combine_query(scope_query, query)
        total = await self.db.audit_logs.count_documents(query)

        pipeline = [
            {'$match': query},
            {'$sort': {sort_by: sort_order}},
            {'$skip': max(0, int(skip or 0))},
            {'$limit': max(1, min(2000, int(limit or 50)))},
            {'$project': {'_id': 0}},
        ]
        logs = await self.db.audit_logs.aggregate(pipeline).to_list(length=limit)

        await self._enrich_actor_names(logs, tenant_id)
        await self._enrich_subject_names(logs, tenant_id)
        for log in logs:
            log['tempo_dias'] = self._compute_tempo_dias(log)
        return logs, total

    async def _enrich_actor_names(self, logs: list, tenant_id: str):
        ids = {log.get('user_id') for log in logs if log.get('user_id') and not log.get('user_name')}
        if not ids or not tenant_id:
            return
        cursor = self.db.users.find(
            {'id': {'$in': list(ids)}, 'mantenedora_id': str(tenant_id)},
            {'_id': 0, 'id': 1, 'full_name': 1, 'name': 1, 'email': 1},
        )
        resolved = {}
        async for doc in cursor:
            resolved[doc.get('id')] = doc.get('full_name') or doc.get('name') or doc.get('email')
        for log in logs:
            if not log.get('user_name') and resolved.get(log.get('user_id')):
                log['user_name'] = resolved[log.get('user_id')]

    async def _enrich_subject_names(self, logs: list, tenant_id: str):
        name_map = {
            'students': ('students', ['full_name', 'name']),
            'staff': ('staff', ['full_name', 'name', 'nome']),
            'users': ('users', ['full_name', 'name']),
            'schools': ('schools', ['name']),
            'classes': ('classes', ['name']),
        }
        id_paren = re.compile(r'\s*\(ID:[^)]*\)')
        need = {}
        for log in logs:
            collection = log.get('collection')
            document_id = log.get('document_id')
            description = log.get('description') or ''
            if collection in name_map and document_id and '(ID:' in description:
                need.setdefault(collection, set()).add(document_id)
        if not need or not tenant_id:
            return

        resolved = {}
        for collection, ids in need.items():
            mongo_collection, fields = name_map[collection]
            projection = {'_id': 0, 'id': 1}
            for field in fields:
                projection[field] = 1
            query = {'id': {'$in': list(ids)}, 'mantenedora_id': str(tenant_id)}
            async for doc in self.db[mongo_collection].find(query, projection):
                name = next((doc.get(field) for field in fields if doc.get(field)), None)
                if name:
                    resolved[(collection, doc['id'])] = name

        for log in logs:
            name = resolved.get((log.get('collection'), log.get('document_id')))
            if name and log.get('description'):
                log['description'] = id_paren.sub(f': {name}', log['description'])

    def _compute_tempo_dias(self, log: dict):
        if log.get('action') != 'create':
            return None
        if log.get('collection') not in ('attendance', 'content_entries', 'grades'):
            return None

        extra = log.get('extra_data') or {}
        record_date = extra.get('date') or extra.get('tempo_ref_date')
        if not record_date:
            match = re.search(r'(\d{4}-\d{2}-\d{2})', log.get('description') or '')
            record_date = match.group(1) if match else None
        if not record_date:
            return None

        try:
            reference = datetime.strptime(str(record_date)[:10], '%Y-%m-%d').date()
            timestamp = log.get('timestamp')
            if not timestamp:
                return None
            saved = datetime.fromisoformat(str(timestamp).replace('Z', '+00:00')).date()
            diff = (saved - reference).days
            if log.get('collection') == 'grades':
                return abs(diff)
            return diff if diff >= 0 else None
        except Exception:
            return None

    async def get_user_activity(self, user_id: str, limit: int = 20, tenant_id: str = None) -> List[dict]:
        logs, _ = await self.get_logs(
            {'user_id': user_id}, skip=0, limit=limit, tenant_id=tenant_id
        )
        return logs

    async def get_document_history(
        self, collection: str, document_id: str, tenant_id: str = None
    ) -> List[dict]:
        logs, _ = await self.get_logs(
            {'collection': collection, 'document_id': document_id},
            skip=0,
            limit=100,
            tenant_id=tenant_id,
        )
        return logs

    async def get_critical_events(self, hours: int = 24, tenant_id: str = None) -> List[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        logs, _ = await self.get_logs(
            {'severity': 'critical', 'timestamp_gte': cutoff},
            skip=0,
            limit=100,
            tenant_id=tenant_id,
        )
        return logs

    async def get_stats(self, days: int = 7, tenant_id: str = None) -> dict:
        scope_query = await self.build_tenant_scope_query(tenant_id)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        match = self._combine_query(scope_query, {'timestamp': {'$gte': cutoff}})

        async def grouped(field: str, length: int, limit: int = None):
            pipeline = [
                {'$match': match},
                {'$group': {'_id': f'${field}', 'count': {'$sum': 1}}},
                {'$sort': {'count': -1}},
            ]
            if limit:
                pipeline.append({'$limit': limit})
            return await self.db.audit_logs.aggregate(pipeline).to_list(length=length)

        by_action = await grouped('action', 20)
        by_collection = await grouped('collection', 20)
        by_severity = await grouped('severity', 10)

        pipeline_user = [
            {'$match': match},
            {'$group': {'_id': {'id': '$user_id', 'email': '$user_email'}, 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}},
            {'$limit': 10},
        ]
        by_user = await self.db.audit_logs.aggregate(pipeline_user).to_list(length=10)
        total = await self.db.audit_logs.count_documents(match)

        return {
            'period_days': days,
            'total_events': total,
            'by_action': by_action,
            'by_collection': by_collection,
            'by_user': by_user,
            'by_severity': by_severity,
        }


audit_service = AuditService()
