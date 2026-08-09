"""
Serviço de Auditoria - SIGESC
Rastreia todas as alterações críticas no sistema.

Uso:
    from audit_service import audit_service
    
    await audit_service.log(
        action='update',
        collection='grades',
        document_id=grade_id,
        user=current_user,
        request=request,
        description='Alterou nota do aluno João Silva',
        old_value={'b1': 7.5},
        new_value={'b1': 8.0}
    )
"""

from datetime import datetime, timezone
from typing import Optional, List, Literal
from fastapi import Request
import logging

logger = logging.getLogger(__name__)

# Coleções que devem ser auditadas
AUDITED_COLLECTIONS = {
    'grades': {'severity': 'critical', 'category': 'academic'},
    'attendance': {'severity': 'critical', 'category': 'academic'},
    'students': {'severity': 'warning', 'category': 'administrative'},
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

# Descrições legíveis das ações
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
}

# Nomes legíveis das coleções
COLLECTION_NAMES = {
    'grades': 'notas',
    'attendance': 'frequência',
    'students': 'aluno',
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
}


class AuditService:
    """Serviço de auditoria para rastrear alterações no sistema"""
    
    def __init__(self):
        self.db = None
        self._enabled = True
    
    def set_db(self, db):
        """Define a conexão com o banco de dados"""
        self.db = db
    
    def disable(self):
        """Desabilita temporariamente a auditoria (útil para migrações)"""
        self._enabled = False
    
    def enable(self):
        """Reabilita a auditoria"""
        self._enabled = True
    
    async def log(
        self,
        action: Literal['create', 'update', 'delete', 'login', 'logout', 'export', 'import', 'approve', 'reject'],
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
        extra_data: dict = None
    ):
        """
        Registra uma ação de auditoria.
        
        Args:
            action: Tipo da ação (create, update, delete, etc.)
            collection: Nome da coleção afetada
            user: Dicionário com dados do usuário (id, email, role)
            request: Objeto Request do FastAPI (para extrair IP e user-agent)
            document_id: ID do documento afetado
            description: Descrição legível da ação (gerada automaticamente se não fornecida)
            old_value: Valor anterior (para updates)
            new_value: Novo valor
            school_id: ID da escola relacionada
            school_name: Nome da escola
            academic_year: Ano letivo
            extra_data: Dados adicionais para incluir no log
        """
        if not self._enabled or self.db is None:
            return
        
        try:
            # Determina severidade e categoria
            collection_config = AUDITED_COLLECTIONS.get(collection, {'severity': 'info', 'category': 'system'})
            
            # Gera descrição automática se não fornecida
            if not description:
                action_text = ACTION_DESCRIPTIONS.get(action, action)
                collection_text = COLLECTION_NAMES.get(collection, collection)
                description = f"Usuário {action_text} {collection_text}"
                if document_id:
                    description += f" (ID: {document_id[:8]}...)"
            
            # Calcula diferenças entre old_value e new_value
            changes = None
            if old_value and new_value and action == 'update':
                changes = self._calculate_changes(old_value, new_value)
            
            # Extrai informações do request
            ip_address = None
            user_agent = None
            if request:
                ip_address = request.client.host if request.client else None
                user_agent = request.headers.get('user-agent', '')[:200]  # Limita tamanho
            
            # Monta o registro de auditoria
            audit_record = {
                'action': action,
                'collection': collection,
                'document_id': document_id,
                'user_id': user.get('id'),
                'user_email': user.get('email'),
                'user_role': user.get('role'),
                'user_name': user.get('full_name') or user.get('name'),
                'school_id': school_id,
                'school_name': school_name,
                'academic_year': academic_year or datetime.now().year,
                'description': description,
                'old_value': self._sanitize_value(old_value),
                'new_value': self._sanitize_value(new_value),
                'changes': changes,
                'ip_address': ip_address,
                'user_agent': user_agent,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'severity': collection_config['severity'],
                'category': collection_config['category'],
            }
            
            # Adiciona dados extras se fornecidos
            if extra_data:
                audit_record['extra_data'] = extra_data
            
            # Insere no banco
            await self.db.audit_logs.insert_one(audit_record)
            
            # Log também no console para monitoramento
            logger.info(f"AUDIT: [{action.upper()}] {collection} - {description} - User: {user.get('email')}")
            
        except Exception as e:
            # Não deve falhar silenciosamente, mas também não deve quebrar a operação principal
            logger.error(f"Erro ao registrar auditoria: {str(e)}")
    
    def _calculate_changes(self, old_value: dict, new_value: dict) -> dict:
        """Calcula as diferenças entre dois valores"""
        changes = {}
        
        # Campos a ignorar na comparação
        ignore_fields = {'_id', 'created_at', 'updated_at', 'id'}
        
        all_keys = set(old_value.keys()) | set(new_value.keys())
        
        for key in all_keys:
            if key in ignore_fields:
                continue
            
            old_val = old_value.get(key)
            new_val = new_value.get(key)
            
            if old_val != new_val:
                changes[key] = {
                    'old': old_val,
                    'new': new_val
                }
        
        return changes if changes else None
    
    def _sanitize_value(self, value: dict) -> dict:
        """Remove campos sensíveis e limita tamanho do valor"""
        if not value:
            return None
        
        # Campos sensíveis que não devem ser logados
        sensitive_fields = {'password', 'password_hash', 'token', 'access_token', 'refresh_token', 'secret'}
        
        sanitized = {}
        for key, val in value.items():
            if key.lower() in sensitive_fields:
                sanitized[key] = '***REDACTED***'
            elif key == '_id':
                sanitized[key] = str(val)  # Converte ObjectId para string
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
        sort_order: int = -1
    ) -> tuple:
        """
        Busca logs de auditoria com filtros.
        Enriquece os logs com os nomes dos usuários da coleção users.
        
        Returns:
            Tuple (logs, total_count)
        """
        if self.db is None:
            return [], 0
        
        query = {}
        
        if filters:
            if filters.get('user_id'):
                query['user_id'] = filters['user_id']
            if filters.get('user_role'):
                query['user_role'] = filters['user_role']
            if filters.get('school_id'):
                query['school_id'] = filters['school_id']
            if filters.get('collection'):
                query['collection'] = filters['collection']
            if filters.get('action'):
                query['action'] = filters['action']
            if filters.get('category'):
                query['category'] = filters['category']
            if filters.get('severity'):
                query['severity'] = filters['severity']
            if filters.get('academic_year'):
                query['academic_year'] = filters['academic_year']
            
            # Filtro de data
            if filters.get('start_date') or filters.get('end_date'):
                query['timestamp'] = {}
                if filters.get('start_date'):
                    query['timestamp']['$gte'] = filters['start_date']
                if filters.get('end_date'):
                    query['timestamp']['$lte'] = filters['end_date'] + 'T23:59:59'
            
            # Busca por texto na descrição
            if filters.get('search'):
                query['description'] = {'$regex': filters['search'], '$options': 'i'}
        
        # Conta total
        total = await self.db.audit_logs.count_documents(query)
        
        # Pipeline de agregação com lookup para enriquecer com nomes de usuários
        pipeline = [
            {'$match': query},
            {'$sort': {sort_by: sort_order}},
            {'$skip': skip},
            {'$limit': limit},
            # Lookup para buscar o nome do usuário na coleção users
            {
                '$lookup': {
                    'from': 'users',
                    'localField': 'user_id',
                    'foreignField': 'id',
                    'as': 'user_info'
                }
            },
            # Adiciona o nome do usuário encontrado ou usa o existente
            {
                '$addFields': {
                    'user_name': {
                        '$ifNull': [
                            '$user_name',  # Usa o nome existente no log se disponível
                            {'$arrayElemAt': ['$user_info.full_name', 0]}  # Senão busca do lookup
                        ]
                    }
                }
            },
            # Remove o campo temporário user_info e _id
            {
                '$project': {
                    '_id': 0,
                    'user_info': 0
                }
            }
        ]
        
        logs = await self.db.audit_logs.aggregate(pipeline).to_list(length=limit)

        # Enriquecimento: descrições genéricas "(ID: xxxx...)" → nome do aluno/servidor/usuário
        await self._enrich_subject_names(logs)

        # Enriquecimento: coluna "Tempo" — dias entre a data do lançamento e a
        # data do 1º salvamento. Apenas para CREATE de frequência/conteúdos/notas.
        for lg in logs:
            lg['tempo_dias'] = self._compute_tempo_dias(lg)

        return logs, total

    async def _enrich_subject_names(self, logs: list):
        """Torna a descrição objetiva: quando o log se refere a um aluno, servidor ou
        usuário e a descrição contém apenas o ID genérico "(ID: xxxx...)", substitui pelo
        nome real do sujeito. Descrições que já trazem o nome não são alteradas.
        """
        import re
        NAME_MAP = {
            'students': ('students', ['full_name', 'name']),
            'staff': ('staff', ['full_name', 'name', 'nome']),
            'users': ('users', ['full_name', 'name']),
            'schools': ('schools', ['name']),
            'classes': ('classes', ['name']),
        }
        id_paren = re.compile(r'\s*\(ID:[^)]*\)')
        need = {}
        for lg in logs:
            col = lg.get('collection')
            did = lg.get('document_id')
            desc = lg.get('description') or ''
            if col in NAME_MAP and did and '(ID:' in desc:
                need.setdefault(col, set()).add(did)
        if not need:
            return
        resolved = {}
        for col, ids in need.items():
            mongo_col, fields = NAME_MAP[col]
            proj = {'_id': 0, 'id': 1}
            for f in fields:
                proj[f] = 1
            async for doc in self.db[mongo_col].find({'id': {'$in': list(ids)}}, proj):
                name = next((doc.get(f) for f in fields if doc.get(f)), None)
                if name:
                    resolved[(col, doc['id'])] = name
        for lg in logs:
            nm = resolved.get((lg.get('collection'), lg.get('document_id')))
            if nm and lg.get('description'):
                lg['description'] = id_paren.sub(f': {nm}', lg['description'])

    def _compute_tempo_dias(self, log: dict):
        """Diferença, em dias, entre a data do 1º salvamento (timestamp) e a data do
        registro (aula/lançamento). Somente para o PRIMEIRO salvamento (action='create')
        de frequência (attendance) ou conteúdos (content_entries). Edições e demais casos
        retornam None (exibidos como '-'). Notas não possuem data de aula → None.
        """
        if log.get('action') != 'create':
            return None
        if log.get('collection') not in ('attendance', 'content_entries', 'grades'):
            return None
        extra = log.get('extra_data') or {}
        # frequência/conteúdos → data da aula; notas → fim do bimestre (tempo_ref_date)
        rec_date = extra.get('date') or extra.get('tempo_ref_date')
        if not rec_date:
            import re
            m = re.search(r'(\d{4}-\d{2}-\d{2})', log.get('description') or '')
            rec_date = m.group(1) if m else None
        if not rec_date:
            return None
        try:
            rd = datetime.strptime(str(rec_date)[:10], '%Y-%m-%d').date()
            ts = log.get('timestamp')
            if not ts:
                return None
            td = datetime.fromisoformat(str(ts).replace('Z', '+00:00')).date()
            diff = (td - rd).days
            # Notas: "dias entre o lançamento e o fim do bimestre" = distância (valor absoluto).
            # Frequência/Conteúdos: atraso do lançamento em relação à aula (>= 0).
            if log.get('collection') == 'grades':
                return abs(diff)
            return diff if diff >= 0 else None
        except Exception:
            return None
    
    async def get_user_activity(self, user_id: str, limit: int = 20) -> List[dict]:
        """Retorna atividades recentes de um usuário específico"""
        cursor = self.db.audit_logs.find(
            {'user_id': user_id},
            {'_id': 0}
        ).sort('timestamp', -1).limit(limit)
        
        return await cursor.to_list(length=limit)
    
    async def get_document_history(self, collection: str, document_id: str) -> List[dict]:
        """Retorna histórico de alterações de um documento específico"""
        cursor = self.db.audit_logs.find(
            {'collection': collection, 'document_id': document_id},
            {'_id': 0}
        ).sort('timestamp', -1)
        
        return await cursor.to_list(length=100)
    
    async def get_critical_events(self, hours: int = 24) -> List[dict]:
        """Retorna eventos críticos das últimas X horas"""
        from datetime import timedelta
        
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        
        cursor = self.db.audit_logs.find(
            {
                'severity': 'critical',
                'timestamp': {'$gte': cutoff}
            },
            {'_id': 0}
        ).sort('timestamp', -1)
        
        return await cursor.to_list(length=100)


# Instância singleton do serviço
audit_service = AuditService()
