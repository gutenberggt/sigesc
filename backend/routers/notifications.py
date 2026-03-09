"""
Router para Notificações.
Extraído automaticamente de server.py.
"""

from fastapi import APIRouter, Request

from models import *
from auth_middleware import AuthMiddleware


router = APIRouter(tags=["Notificações"])


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências."""
    
    # Helper para obter DB correto (produção ou sandbox)
    def get_db_for_user(user: dict):
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db



    @router.get("/notifications/unread-count", response_model=NotificationCount)
    async def get_unread_count(request: Request):
        """Obter contagem de notificações não lidas (mensagens + avisos)"""
        current_user = await AuthMiddleware.get_current_user(request)
        user_id = current_user['id']
        # Contar mensagens não lidas
        unread_messages = await db.messages.count_documents({
            'receiver_id': user_id,
            'is_read': False
        })

        # Contar avisos não lidos
        # Primeiro, buscar IDs de avisos já lidos
        read_announcements = await db.announcement_reads.find(
            {'user_id': user_id},
            {'_id': 0, 'announcement_id': 1}
        ).to_list(10000)

        read_announcement_ids = [r['announcement_id'] for r in read_announcements]

        # Contar avisos destinados ao usuário que não foram lidos
        unread_announcements = await db.announcements.count_documents({
            'target_user_ids': user_id,
            'id': {'$nin': read_announcement_ids}
        })

        return NotificationCount(
            unread_messages=unread_messages,
            unread_announcements=unread_announcements,
            total=unread_messages + unread_announcements
        )



    return router
