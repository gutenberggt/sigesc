"""
Router de Avisos - SIGESC
PATCH 4.x: Rotas de avisos extraídas do server.py

Endpoints para gestão de avisos incluindo:
- CRUD de avisos
- Sistema de destinatários (todos, escola, turma)
- Marcação de leitura
- Notificações via WebSocket
"""

from fastapi import APIRouter, HTTPException, status, Request
from typing import List, Optional
from datetime import datetime, timezone
import uuid

from models import (
    AnnouncementCreate, AnnouncementUpdate, AnnouncementResponse, 
    AnnouncementRecipient
)
from auth_middleware import AuthMiddleware

router = APIRouter(prefix="/announcements", tags=["Avisos"])


def can_user_create_announcement(user: dict, recipient: dict) -> bool:
    """Verifica se o usuário pode criar um aviso para os destinatários especificados"""
    user_role = user.get('role', '')
    recipient_type = recipient.get('type', '')
    
    # Admin e SEMED podem enviar para qualquer destinatário
    if user_role in ['admin', 'admin_teste', 'semed']:
        return True
    
    # Diretor/Coordenador podem enviar para sua escola
    if user_role in ['diretor', 'coordenador']:
        if recipient_type in ['school', 'class']:
            return True
    
    # Professor pode enviar para suas turmas
    if user_role == 'professor':
        if recipient_type == 'class':
            return True
    
    # Secretário pode enviar para escolas vinculadas
    if user_role == 'secretario':
        if recipient_type in ['school', 'class', 'all']:
            return True
    
    return False


async def get_announcement_target_users(db, recipient: dict, sender: dict) -> List[str]:
    """Obtém a lista de user_ids que devem receber o aviso"""
    target_users = set()
    recipient_type = recipient.get('type', '')
    
    if recipient_type == 'all':
        # Todos os usuários ativos
        users = await db.users.find({'status': 'active'}, {'id': 1}).to_list(5000)
        target_users = {u['id'] for u in users}
        
    elif recipient_type == 'school':
        school_id = recipient.get('school_id')
        if school_id:
            # Usuários vinculados à escola
            users = await db.users.find(
                {'school_links.school_id': school_id, 'status': 'active'},
                {'id': 1}
            ).to_list(1000)
            target_users = {u['id'] for u in users}
            
    elif recipient_type == 'class':
        class_id = recipient.get('class_id')
        if class_id:
            # Professores da turma
            assignments = await db.teacher_assignments.find(
                {'class_id': class_id},
                {'staff_id': 1}
            ).to_list(100)
            
            for assignment in assignments:
                staff = await db.staff.find_one({'id': assignment['staff_id']}, {'user_id': 1})
                if staff and staff.get('user_id'):
                    target_users.add(staff['user_id'])
            
            # Responsáveis dos alunos da turma
            enrollments = await db.enrollments.find(
                {'class_id': class_id, 'status': 'active'},
                {'student_id': 1}
            ).to_list(500)
            
            for enrollment in enrollments:
                guardians = await db.guardians.find(
                    {'student_ids': enrollment['student_id']},
                    {'user_id': 1}
                ).to_list(10)
                
                for guardian in guardians:
                    if guardian.get('user_id'):
                        target_users.add(guardian['user_id'])
                        
    elif recipient_type == 'semed':
        # Apenas usuários com role SEMED
        users = await db.users.find(
            {'role': 'semed', 'status': 'active'},
            {'id': 1}
        ).to_list(100)
        target_users = {u['id'] for u in users}
    
    # Adiciona o remetente para que ele também veja o aviso
    target_users.add(sender.get('id'))
    
    return list(target_users)


def setup_announcements_router(db, audit_service, connection_manager=None, sandbox_db=None):
    """Configura o router de avisos com as dependências necessárias"""
    
    def get_db_for_user(user: dict):
        """Retorna o banco correto baseado no usuário"""
        if False:  # Sandbox desabilitado
            return sandbox_db
        return db

    @router.post("", response_model=AnnouncementResponse, status_code=status.HTTP_201_CREATED)
    async def create_announcement(announcement_data: AnnouncementCreate, request: Request):
        """Criar um novo aviso"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        user_data = await current_db.users.find_one({'id': current_user['id']}, {'_id': 0})
        if not user_data:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        
        if not can_user_create_announcement(user_data, announcement_data.recipient.model_dump()):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você não tem permissão para enviar avisos para esses destinatários"
            )
        
        profile = await current_db.user_profiles.find_one({'user_id': current_user['id']}, {'_id': 0})
        sender_foto = profile.get('foto_url') if profile else None
        
        announcement = {
            'id': str(uuid.uuid4()),
            'title': announcement_data.title,
            'content': announcement_data.content,
            'recipient': announcement_data.recipient.model_dump(),
            'sender_id': current_user['id'],
            'sender_name': user_data.get('full_name', 'Usuário'),
            'sender_role': user_data.get('role', current_user['role']),
            'sender_foto_url': sender_foto,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': None
        }
        
        target_users = await get_announcement_target_users(current_db, announcement_data.recipient.model_dump(), user_data)
        announcement['target_user_ids'] = target_users
        
        await current_db.announcements.insert_one(announcement)
        
        # Notificar via WebSocket
        if connection_manager:
            for user_id in target_users:
                await connection_manager.send_notification(user_id, {
                    'type': 'new_announcement',
                    'announcement': {
                        'id': announcement['id'],
                        'title': announcement['title'],
                        'sender_name': announcement['sender_name']
                    }
                })
        
        await audit_service.log(
            action='create',
            collection='announcements',
            user=current_user,
            request=request,
            document_id=announcement['id'],
            description=f"Criou aviso: {announcement['title']}"
        )
        
        return AnnouncementResponse(
            id=announcement['id'],
            title=announcement['title'],
            content=announcement['content'],
            recipient=announcement_data.recipient,
            sender_id=announcement['sender_id'],
            sender_name=announcement['sender_name'],
            sender_role=announcement['sender_role'],
            sender_foto_url=sender_foto,
            created_at=datetime.fromisoformat(announcement['created_at']),
            updated_at=None,
            is_read=False,
            read_at=None
        )

    @router.get("", response_model=List[AnnouncementResponse])
    async def list_announcements(request: Request, skip: int = 0, limit: int = 50):
        """Listar avisos do usuário atual"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        user_id = current_user['id']
        
        announcements = await current_db.announcements.find(
            {'$or': [
                {'target_user_ids': user_id},
                {'sender_id': user_id}
            ]},
            {'_id': 0}
        ).sort('created_at', -1).skip(skip).limit(limit).to_list(limit)
        
        read_statuses = await current_db.announcement_reads.find(
            {'user_id': user_id},
            {'_id': 0}
        ).to_list(1000)
        
        read_map = {r['announcement_id']: r['read_at'] for r in read_statuses}
        
        result = []
        for ann in announcements:
            is_read = ann['id'] in read_map
            read_at = read_map.get(ann['id'])
            
            result.append(AnnouncementResponse(
                id=ann['id'],
                title=ann['title'],
                content=ann['content'],
                recipient=AnnouncementRecipient(**ann['recipient']),
                sender_id=ann['sender_id'],
                sender_name=ann['sender_name'],
                sender_role=ann['sender_role'],
                sender_foto_url=ann.get('sender_foto_url'),
                created_at=datetime.fromisoformat(ann['created_at']) if isinstance(ann['created_at'], str) else ann['created_at'],
                updated_at=datetime.fromisoformat(ann['updated_at']) if ann.get('updated_at') and isinstance(ann['updated_at'], str) else ann.get('updated_at'),
                is_read=is_read,
                read_at=datetime.fromisoformat(read_at) if read_at and isinstance(read_at, str) else read_at
            ))
        
        return result

    @router.get("/{announcement_id}", response_model=AnnouncementResponse)
    async def get_announcement(announcement_id: str, request: Request):
        """Obter detalhes de um aviso"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        user_id = current_user['id']
        
        announcement = await current_db.announcements.find_one(
            {'id': announcement_id},
            {'_id': 0}
        )
        
        if not announcement:
            raise HTTPException(status_code=404, detail="Aviso não encontrado")
        
        if user_id not in announcement.get('target_user_ids', []) and user_id != announcement['sender_id']:
            raise HTTPException(status_code=403, detail="Acesso negado")
        
        read_status = await current_db.announcement_reads.find_one(
            {'announcement_id': announcement_id, 'user_id': user_id},
            {'_id': 0}
        )
        
        return AnnouncementResponse(
            id=announcement['id'],
            title=announcement['title'],
            content=announcement['content'],
            recipient=AnnouncementRecipient(**announcement['recipient']),
            sender_id=announcement['sender_id'],
            sender_name=announcement['sender_name'],
            sender_role=announcement['sender_role'],
            sender_foto_url=announcement.get('sender_foto_url'),
            created_at=datetime.fromisoformat(announcement['created_at']) if isinstance(announcement['created_at'], str) else announcement['created_at'],
            updated_at=datetime.fromisoformat(announcement['updated_at']) if announcement.get('updated_at') and isinstance(announcement['updated_at'], str) else announcement.get('updated_at'),
            is_read=read_status is not None,
            read_at=datetime.fromisoformat(read_status['read_at']) if read_status and isinstance(read_status.get('read_at'), str) else read_status.get('read_at') if read_status else None
        )

    @router.put("/{announcement_id}", response_model=AnnouncementResponse)
    async def update_announcement(announcement_id: str, update_data: AnnouncementUpdate, request: Request):
        """Atualizar um aviso (apenas o remetente pode editar)"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        announcement = await current_db.announcements.find_one({'id': announcement_id}, {'_id': 0})
        
        if not announcement:
            raise HTTPException(status_code=404, detail="Aviso não encontrado")
        
        if announcement['sender_id'] != current_user['id'] and current_user['role'] not in ['admin', 'admin_teste']:
            raise HTTPException(status_code=403, detail="Apenas o remetente pode editar o aviso")
        
        update_fields = {}
        if update_data.title is not None:
            update_fields['title'] = update_data.title
        if update_data.content is not None:
            update_fields['content'] = update_data.content
        
        if update_fields:
            update_fields['updated_at'] = datetime.now(timezone.utc).isoformat()
            await current_db.announcements.update_one(
                {'id': announcement_id},
                {'$set': update_fields}
            )
        
        updated = await current_db.announcements.find_one({'id': announcement_id}, {'_id': 0})
        
        return AnnouncementResponse(
            id=updated['id'],
            title=updated['title'],
            content=updated['content'],
            recipient=AnnouncementRecipient(**updated['recipient']),
            sender_id=updated['sender_id'],
            sender_name=updated['sender_name'],
            sender_role=updated['sender_role'],
            sender_foto_url=updated.get('sender_foto_url'),
            created_at=datetime.fromisoformat(updated['created_at']) if isinstance(updated['created_at'], str) else updated['created_at'],
            updated_at=datetime.fromisoformat(updated['updated_at']) if updated.get('updated_at') and isinstance(updated['updated_at'], str) else updated.get('updated_at'),
            is_read=False,
            read_at=None
        )

    @router.delete("/{announcement_id}")
    async def delete_announcement(announcement_id: str, request: Request):
        """Excluir um aviso (apenas o remetente ou admin pode excluir)"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        announcement = await current_db.announcements.find_one({'id': announcement_id}, {'_id': 0})
        
        if not announcement:
            raise HTTPException(status_code=404, detail="Aviso não encontrado")
        
        if announcement['sender_id'] != current_user['id'] and current_user['role'] not in ['admin', 'admin_teste']:
            raise HTTPException(status_code=403, detail="Apenas o remetente ou admin pode excluir o aviso")
        
        await current_db.announcements.delete_one({'id': announcement_id})
        await current_db.announcement_reads.delete_many({'announcement_id': announcement_id})
        
        await audit_service.log(
            action='delete',
            collection='announcements',
            user=current_user,
            request=request,
            document_id=announcement_id,
            description=f"EXCLUIU aviso: {announcement.get('title')}"
        )
        
        return {"message": "Aviso excluído com sucesso"}

    @router.post("/{announcement_id}/read")
    async def mark_announcement_read(announcement_id: str, request: Request):
        """Marcar aviso como lido"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        user_id = current_user['id']
        
        announcement = await current_db.announcements.find_one({'id': announcement_id}, {'_id': 0})
        
        if not announcement:
            raise HTTPException(status_code=404, detail="Aviso não encontrado")
        
        if user_id not in announcement.get('target_user_ids', []) and user_id != announcement['sender_id']:
            raise HTTPException(status_code=403, detail="Acesso negado")
        
        existing = await current_db.announcement_reads.find_one({
            'announcement_id': announcement_id,
            'user_id': user_id
        })
        
        if not existing:
            await current_db.announcement_reads.insert_one({
                'id': str(uuid.uuid4()),
                'announcement_id': announcement_id,
                'user_id': user_id,
                'read_at': datetime.now(timezone.utc).isoformat()
            })
        
        return {"message": "Aviso marcado como lido"}

    @router.get("/{announcement_id}/readers")
    async def get_announcement_readers(announcement_id: str, request: Request):
        """Lista quem leu o aviso (apenas para o remetente)"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        announcement = await current_db.announcements.find_one({'id': announcement_id}, {'_id': 0})
        
        if not announcement:
            raise HTTPException(status_code=404, detail="Aviso não encontrado")
        
        if announcement['sender_id'] != current_user['id'] and current_user['role'] not in ['admin', 'admin_teste', 'semed']:
            raise HTTPException(status_code=403, detail="Apenas o remetente pode ver quem leu")
        
        reads = await current_db.announcement_reads.find(
            {'announcement_id': announcement_id},
            {'_id': 0}
        ).to_list(1000)
        
        readers = []
        for read in reads:
            user = await current_db.users.find_one({'id': read['user_id']}, {'_id': 0, 'full_name': 1, 'role': 1})
            if user:
                readers.append({
                    'user_id': read['user_id'],
                    'user_name': user.get('full_name', 'Usuário'),
                    'user_role': user.get('role'),
                    'read_at': read['read_at']
                })
        
        return {
            'announcement_id': announcement_id,
            'total_targets': len(announcement.get('target_user_ids', [])),
            'total_reads': len(readers),
            'readers': readers
        }

    return router
