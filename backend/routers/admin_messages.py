"""
Router para Admin - Mensagens.
Extraído automaticamente de server.py.
"""

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone

from models import *
from auth_middleware import AuthMiddleware


router = APIRouter(tags=["Admin - Mensagens"])


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências."""
    
    # Helper para obter DB correto (produção ou sandbox)
    def get_db_for_user(user: dict):
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db



    @router.get("/admin/message-logs")
    async def list_message_logs(request: Request, user_id: str = None, limit: int = 100):
        """Lista logs de mensagens (apenas admin)"""
        current_user = await AuthMiddleware.get_current_user(request)

        if current_user['role'] != 'admin':
            raise HTTPException(status_code=403, detail="Apenas administradores podem acessar os logs")

        # Filtrar por usuário se especificado
        query = {}
        if user_id:
            query["$or"] = [
                {"sender_id": user_id},
                {"receiver_id": user_id}
            ]

        logs = await db.message_logs.find(query, {"_id": 0}).sort("logged_at", -1).limit(limit).to_list(limit)

        return logs


    @router.get("/admin/message-logs/users")
    async def list_users_with_logs(request: Request):
        """Lista usuários que têm logs de mensagens (apenas admin)"""
        current_user = await AuthMiddleware.get_current_user(request)

        if current_user['role'] != 'admin':
            raise HTTPException(status_code=403, detail="Apenas administradores podem acessar os logs")

        # Agregar usuários únicos dos logs
        pipeline = [
            {"$group": {
                "_id": None,
                "sender_ids": {"$addToSet": "$sender_id"},
                "receiver_ids": {"$addToSet": "$receiver_id"}
            }},
            {"$project": {
                "user_ids": {"$setUnion": ["$sender_ids", "$receiver_ids"]}
            }}
        ]

        result = await db.message_logs.aggregate(pipeline).to_list(1)

        if not result or not result[0].get('user_ids'):
            return []

        user_ids = result[0]['user_ids']

        # Buscar dados dos usuários
        users_with_logs = []
        for uid in user_ids:
            user = await db.users.find_one({"id": uid}, {"_id": 0, "password_hash": 0})
            if user:
                # Contar mensagens no log
                msg_count = await db.message_logs.count_documents({
                    "$or": [{"sender_id": uid}, {"receiver_id": uid}]
                })

                # Contar anexos
                attachments_pipeline = [
                    {"$match": {"$or": [{"sender_id": uid}, {"receiver_id": uid}]}},
                    {"$unwind": {"path": "$attachments", "preserveNullAndEmptyArrays": False}},
                    {"$count": "total"}
                ]
                att_result = await db.message_logs.aggregate(attachments_pipeline).to_list(1)
                att_count = att_result[0]['total'] if att_result else 0

                users_with_logs.append({
                    "user_id": uid,
                    "full_name": user.get('full_name', ''),
                    "email": user.get('email', ''),
                    "role": user.get('role', ''),
                    "total_messages": msg_count,
                    "total_attachments": att_count
                })

        # Ordenar por total de mensagens
        users_with_logs.sort(key=lambda x: x['total_messages'], reverse=True)

        return users_with_logs


    @router.get("/admin/message-logs/user/{user_id}")
    async def get_user_conversation_logs(user_id: str, request: Request):
        """Obtém logs de todas as conversas de um usuário específico (apenas admin)"""
        current_user = await AuthMiddleware.get_current_user(request)

        if current_user['role'] != 'admin':
            raise HTTPException(status_code=403, detail="Apenas administradores podem acessar os logs")

        # Buscar dados do usuário
        target_user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
        if not target_user:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")

        # Buscar todos os logs do usuário
        logs = await db.message_logs.find({
            "$or": [{"sender_id": user_id}, {"receiver_id": user_id}]
        }, {"_id": 0}).sort("created_at", -1).to_list(1000)

        # Agrupar por conversa (connection_id)
        conversations = {}
        for log in logs:
            conn_id = log.get('connection_id', 'unknown')
            if conn_id not in conversations:
                # Determinar o outro participante
                other_id = log['receiver_id'] if log['sender_id'] == user_id else log['sender_id']
                other_name = log['receiver_name'] if log['sender_id'] == user_id else log['sender_name']
                other_email = log['receiver_email'] if log['sender_id'] == user_id else log['sender_email']

                conversations[conn_id] = {
                    "connection_id": conn_id,
                    "other_user_id": other_id,
                    "other_user_name": other_name,
                    "other_user_email": other_email,
                    "messages": [],
                    "total_attachments": 0
                }

            conversations[conn_id]["messages"].append(log)
            if log.get('attachments'):
                conversations[conn_id]["total_attachments"] += len(log['attachments'])

        # Calcular estatísticas
        total_messages = len(logs)
        total_attachments = sum(len(log.get('attachments', [])) for log in logs)

        # Determinar range de datas
        dates = [log.get('created_at') for log in logs if log.get('created_at')]
        date_range = None
        if dates:
            date_range = {
                "start": min(dates),
                "end": max(dates)
            }

        return {
            "user_id": user_id,
            "user_name": target_user.get('full_name', ''),
            "user_email": target_user.get('email', ''),
            "total_messages": total_messages,
            "total_attachments": total_attachments,
            "date_range": date_range,
            "conversations": list(conversations.values())
        }


    @router.delete("/admin/message-logs/expired")
    async def cleanup_expired_logs(request: Request):
        """Remove logs expirados (mais de 30 dias após exclusão) - apenas admin"""
        current_user = await AuthMiddleware.get_current_user(request)

        if current_user['role'] != 'admin':
            raise HTTPException(status_code=403, detail="Apenas administradores podem executar esta ação")

        # Remover logs expirados
        now = datetime.now(timezone.utc).isoformat()
        result = await db.message_logs.delete_many({
            "expires_at": {"$lt": now}
        })

        return {"message": f"{result.deleted_count} log(s) expirado(s) removido(s)"}

    # ============= PDF DOCUMENT GENERATION ENDPOINTS =============

    return router
