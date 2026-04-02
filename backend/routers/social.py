"""
Router para Conexões e Mensagens.
Extraído automaticamente de server.py.
"""

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone, timedelta
import uuid

from models import *
from auth_middleware import AuthMiddleware


router = APIRouter(tags=["Conexões e Mensagens"])


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências."""
    
    # Helper para obter DB correto (produção ou sandbox)
    def get_db_for_user(user: dict):
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db


    connection_manager = kwargs.get('connection_manager')

    @router.post("/connections/invite")
    async def send_connection_invite(data: ConnectionCreate, request: Request):
        """Envia um convite de conexão para outro usuário"""
        current_user = await AuthMiddleware.get_current_user(request)
        requester_id = current_user['id']
        receiver_id = data.receiver_id

        # Não pode se conectar consigo mesmo
        if requester_id == receiver_id:
            raise HTTPException(status_code=400, detail="Não é possível se conectar consigo mesmo")

        # Verificar se já existe conexão ou convite pendente
        existing = await db.connections.find_one({
            "$or": [
                {"requester_id": requester_id, "receiver_id": receiver_id},
                {"requester_id": receiver_id, "receiver_id": requester_id}
            ]
        })

        if existing:
            if existing['status'] == 'accepted':
                raise HTTPException(status_code=400, detail="Vocês já estão conectados")
            elif existing['status'] == 'pending':
                raise HTTPException(status_code=400, detail="Já existe um convite pendente")

        # Criar o convite
        connection = {
            "id": str(uuid.uuid4()),
            "requester_id": requester_id,
            "receiver_id": receiver_id,
            "status": "pending",
            "message": data.message,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None
        }

        await db.connections.insert_one(connection)

        # Notificar via WebSocket
        await connection_manager.send_notification(receiver_id, {
            "type": "connection_invite",
            "from_user_id": requester_id,
            "from_user_name": current_user.get('full_name', ''),
            "connection_id": connection['id'],
            "message": data.message
        })

        return {"message": "Convite enviado com sucesso", "connection_id": connection['id']}


    @router.post("/connections/{connection_id}/accept")
    async def accept_connection(connection_id: str, request: Request):
        """Aceita um convite de conexão"""
        current_user = await AuthMiddleware.get_current_user(request)

        connection = await db.connections.find_one({"id": connection_id}, {"_id": 0})
        if not connection:
            raise HTTPException(status_code=404, detail="Convite não encontrado")

        # Só o destinatário pode aceitar
        if connection['receiver_id'] != current_user['id']:
            raise HTTPException(status_code=403, detail="Você não tem permissão para aceitar este convite")

        if connection['status'] != 'pending':
            raise HTTPException(status_code=400, detail="Este convite já foi processado")

        await db.connections.update_one(
            {"id": connection_id},
            {"$set": {"status": "accepted", "updated_at": datetime.now(timezone.utc).isoformat()}}
        )

        # Notificar o solicitante via WebSocket
        await connection_manager.send_notification(connection['requester_id'], {
            "type": "connection_accepted",
            "by_user_id": current_user['id'],
            "by_user_name": current_user.get('full_name', ''),
            "connection_id": connection_id
        })

        return {"message": "Conexão aceita com sucesso"}


    @router.post("/connections/{connection_id}/reject")
    async def reject_connection(connection_id: str, request: Request):
        """Rejeita um convite de conexão"""
        current_user = await AuthMiddleware.get_current_user(request)

        connection = await db.connections.find_one({"id": connection_id}, {"_id": 0})
        if not connection:
            raise HTTPException(status_code=404, detail="Convite não encontrado")

        # Só o destinatário pode rejeitar
        if connection['receiver_id'] != current_user['id']:
            raise HTTPException(status_code=403, detail="Você não tem permissão para rejeitar este convite")

        if connection['status'] != 'pending':
            raise HTTPException(status_code=400, detail="Este convite já foi processado")

        await db.connections.update_one(
            {"id": connection_id},
            {"$set": {"status": "rejected", "updated_at": datetime.now(timezone.utc).isoformat()}}
        )

        return {"message": "Convite rejeitado"}


    @router.delete("/connections/{connection_id}")
    async def remove_connection(connection_id: str, request: Request):
        """Remove uma conexão existente"""
        current_user = await AuthMiddleware.get_current_user(request)

        connection = await db.connections.find_one({"id": connection_id}, {"_id": 0})
        if not connection:
            raise HTTPException(status_code=404, detail="Conexão não encontrada")

        # Qualquer um dos dois pode remover a conexão
        if connection['requester_id'] != current_user['id'] and connection['receiver_id'] != current_user['id']:
            raise HTTPException(status_code=403, detail="Você não faz parte desta conexão")

        await db.connections.delete_one({"id": connection_id})

        return {"message": "Conexão removida"}


    @router.get("/connections")
    async def list_connections(request: Request):
        """Lista todas as conexões aceitas do usuário"""
        current_user = await AuthMiddleware.get_current_user(request)
        user_id = current_user['id']

        # Buscar conexões aceitas
        connections = await db.connections.find({
            "$or": [
                {"requester_id": user_id, "status": "accepted"},
                {"receiver_id": user_id, "status": "accepted"}
            ]
        }, {"_id": 0}).to_list(100)

        results = []
        for conn in connections:
            # Determinar o ID do outro usuário
            other_user_id = conn['receiver_id'] if conn['requester_id'] == user_id else conn['requester_id']

            # Buscar dados do outro usuário
            other_user = await db.users.find_one({"id": other_user_id}, {"_id": 0, "password_hash": 0})
            if not other_user:
                continue

            # Buscar perfil do outro usuário
            profile = await db.user_profiles.find_one({"user_id": other_user_id}, {"_id": 0})

            results.append({
                "id": conn['id'],
                "user_id": other_user_id,
                "full_name": other_user.get('full_name', ''),
                "email": other_user.get('email', ''),
                "role": other_user.get('role', ''),
                "headline": profile.get('headline') if profile else None,
                "foto_url": profile.get('foto_url') if profile else other_user.get('avatar_url'),
                "status": conn['status'],
                "connected_at": conn.get('updated_at') or conn.get('created_at')
            })

        return results


    @router.get("/connections/pending")
    async def list_pending_connections(request: Request):
        """Lista convites de conexão pendentes recebidos"""
        current_user = await AuthMiddleware.get_current_user(request)

        # Buscar convites pendentes recebidos
        connections = await db.connections.find({
            "receiver_id": current_user['id'],
            "status": "pending"
        }, {"_id": 0}).to_list(50)

        results = []
        for conn in connections:
            # Buscar dados do solicitante
            requester = await db.users.find_one({"id": conn['requester_id']}, {"_id": 0, "password_hash": 0})
            if not requester:
                continue

            profile = await db.user_profiles.find_one({"user_id": conn['requester_id']}, {"_id": 0})

            results.append({
                "id": conn['id'],
                "user_id": conn['requester_id'],
                "full_name": requester.get('full_name', ''),
                "email": requester.get('email', ''),
                "role": requester.get('role', ''),
                "headline": profile.get('headline') if profile else None,
                "foto_url": profile.get('foto_url') if profile else requester.get('avatar_url'),
                "message": conn.get('message'),
                "created_at": conn.get('created_at')
            })

        return results


    @router.get("/connections/sent")
    async def list_sent_connections(request: Request):
        """Lista convites de conexão enviados pendentes"""
        current_user = await AuthMiddleware.get_current_user(request)

        connections = await db.connections.find({
            "requester_id": current_user['id'],
            "status": "pending"
        }, {"_id": 0}).to_list(50)

        results = []
        for conn in connections:
            receiver = await db.users.find_one({"id": conn['receiver_id']}, {"_id": 0, "password_hash": 0})
            if not receiver:
                continue

            profile = await db.user_profiles.find_one({"user_id": conn['receiver_id']}, {"_id": 0})

            results.append({
                "id": conn['id'],
                "user_id": conn['receiver_id'],
                "full_name": receiver.get('full_name', ''),
                "headline": profile.get('headline') if profile else None,
                "foto_url": profile.get('foto_url') if profile else receiver.get('avatar_url'),
                "created_at": conn.get('created_at')
            })

        return results


    @router.get("/connections/status/{user_id}")
    async def get_connection_status(user_id: str, request: Request):
        """Verifica o status da conexão com um usuário específico"""
        current_user = await AuthMiddleware.get_current_user(request)

        if current_user['id'] == user_id:
            return {"status": "self"}

        connection = await db.connections.find_one({
            "$or": [
                {"requester_id": current_user['id'], "receiver_id": user_id},
                {"requester_id": user_id, "receiver_id": current_user['id']}
            ]
        }, {"_id": 0})

        if connection:
            is_requester = connection['requester_id'] == current_user['id']
            return {
                "status": connection['status'],
                "connection_id": connection['id'],
                "is_requester": is_requester
            }

        # Se admin está envolvido, permitir mensagem direta (status virtual)
        current_is_admin = current_user.get('role') in ('admin', 'admin_teste')
        other_is_admin = await _is_admin(user_id)
        if current_is_admin or other_is_admin:
            return {"status": "admin_direct", "connection_id": None, "is_requester": False}

        return {"status": "none", "connection_id": None}


    async def _is_admin(user_id: str) -> bool:
        """Verifica se um usuário é administrador"""
        u = await db.users.find_one({"id": user_id}, {"_id": 0, "role": 1})
        return u.get('role') in ('admin', 'admin_teste') if u else False

    async def _ensure_connection(user_a_id: str, user_b_id: str):
        """Garante que existe uma conexão aceita entre dois usuários. Cria se não existir."""
        connection = await db.connections.find_one({
            "$or": [
                {"requester_id": user_a_id, "receiver_id": user_b_id},
                {"requester_id": user_b_id, "receiver_id": user_a_id}
            ]
        })
        if connection:
            if connection['status'] != 'accepted':
                await db.connections.update_one(
                    {"id": connection['id']},
                    {"$set": {"status": "accepted", "accepted_at": datetime.now(timezone.utc).isoformat()}}
                )
                connection['status'] = 'accepted'
            return connection
        # Criar nova conexão aceita
        new_conn = {
            "id": str(uuid.uuid4()),
            "requester_id": user_a_id,
            "receiver_id": user_b_id,
            "status": "accepted",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "accepted_at": datetime.now(timezone.utc).isoformat()
        }
        await db.connections.insert_one(new_conn)
        return new_conn

    @router.post("/connections/direct/{user_id}")
    async def create_direct_connection(user_id: str, request: Request):
        """Cria conexão direta com um usuário (admin pode com qualquer um, qualquer um pode com admin)"""
        current_user = await AuthMiddleware.get_current_user(request)
        if current_user['id'] == user_id:
            raise HTTPException(status_code=400, detail="Não pode conectar consigo mesmo")
        
        sender_is_admin = current_user.get('role') in ('admin', 'admin_teste')
        receiver_is_admin = await _is_admin(user_id)
        
        if not sender_is_admin and not receiver_is_admin:
            raise HTTPException(status_code=403, detail="Conexão direta disponível apenas com administradores")
        
        # Buscar dados do outro usuário
        other_user = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not other_user:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        
        connection = await _ensure_connection(current_user['id'], user_id)
        other_profile = await db.user_profiles.find_one({"user_id": user_id}, {"_id": 0})
        
        return {
            "id": connection['id'],
            "user_id": user_id,
            "full_name": other_user.get('full_name', ''),
            "foto_url": other_profile.get('foto_url') if other_profile else None,
            "headline": other_profile.get('headline', '') if other_profile else '',
            "status": "accepted"
        }

    @router.post("/messages")
    async def send_message(data: MessageCreate, request: Request):
        """Envia uma mensagem para um usuário conectado (admin pode enviar para qualquer um)"""
        current_user = await AuthMiddleware.get_current_user(request)
        sender_id = current_user['id']
        receiver_id = data.receiver_id

        sender_is_admin = current_user.get('role') in ('admin', 'admin_teste')
        receiver_is_admin = await _is_admin(receiver_id)

        # Verificar se estão conectados
        connection = await db.connections.find_one({
            "$or": [
                {"requester_id": sender_id, "receiver_id": receiver_id, "status": "accepted"},
                {"requester_id": receiver_id, "receiver_id": sender_id, "status": "accepted"}
            ]
        })

        if not connection:
            # Se admin está envolvido, criar conexão automaticamente
            if sender_is_admin or receiver_is_admin:
                connection = await _ensure_connection(sender_id, receiver_id)
            else:
                raise HTTPException(status_code=403, detail="Vocês não estão conectados")

        # Validar que tem conteúdo ou anexo
        if not data.content and not data.attachments:
            raise HTTPException(status_code=400, detail="Mensagem deve ter texto ou anexo")

        # Criar a mensagem
        message = {
            "id": str(uuid.uuid4()),
            "connection_id": connection['id'],
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "content": data.content,
            "attachments": data.attachments or [],
            "is_read": False,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        await db.messages.insert_one(message)

        # Buscar dados do remetente para a resposta
        sender_profile = await db.user_profiles.find_one({"user_id": sender_id}, {"_id": 0})

        message_response = {
            "id": message['id'],
            "sender_id": sender_id,
            "sender_name": current_user.get('full_name', ''),
            "sender_foto_url": sender_profile.get('foto_url') if sender_profile else current_user.get('avatar_url'),
            "receiver_id": receiver_id,
            "content": message['content'],
            "attachments": message['attachments'],
            "is_read": message['is_read'],
            "created_at": message['created_at']
        }

        # Notificar via WebSocket
        await connection_manager.send_message(receiver_id, {
            "type": "new_message",
            "message": message_response
        })

        return message_response


    @router.get("/messages/{connection_id}")
    async def get_messages(connection_id: str, request: Request, limit: int = 50, before: str = None):
        """Lista mensagens de uma conexão"""
        current_user = await AuthMiddleware.get_current_user(request)

        # Verificar se o usuário faz parte da conexão
        connection = await db.connections.find_one({"id": connection_id}, {"_id": 0})
        if not connection:
            raise HTTPException(status_code=404, detail="Conexão não encontrada")

        if connection['requester_id'] != current_user['id'] and connection['receiver_id'] != current_user['id']:
            raise HTTPException(status_code=403, detail="Você não faz parte desta conexão")

        # Buscar mensagens
        query = {"connection_id": connection_id}
        if before:
            query["created_at"] = {"$lt": before}

        messages = await db.messages.find(
            query, {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(limit)

        # Marcar mensagens como lidas
        await db.messages.update_many(
            {"connection_id": connection_id, "receiver_id": current_user['id'], "is_read": False},
            {"$set": {"is_read": True}}
        )

        # Buscar dados dos usuários
        user_ids = set()
        for msg in messages:
            user_ids.add(msg['sender_id'])

        users_data = {}
        for uid in user_ids:
            user = await db.users.find_one({"id": uid}, {"_id": 0, "password_hash": 0})
            profile = await db.user_profiles.find_one({"user_id": uid}, {"_id": 0})
            if user:
                users_data[uid] = {
                    "name": user.get('full_name', ''),
                    "foto_url": profile.get('foto_url') if profile else user.get('avatar_url')
                }

        # Formatar resposta
        results = []
        for msg in reversed(messages):  # Reverter para ordem cronológica
            results.append({
                "id": msg['id'],
                "sender_id": msg['sender_id'],
                "sender_name": users_data.get(msg['sender_id'], {}).get('name', ''),
                "sender_foto_url": users_data.get(msg['sender_id'], {}).get('foto_url'),
                "receiver_id": msg['receiver_id'],
                "content": msg.get('content'),
                "attachments": msg.get('attachments', []),
                "is_read": msg.get('is_read', False),
                "created_at": msg['created_at']
            })

        return results


    @router.get("/messages/conversations/list")
    async def list_conversations(request: Request):
        """Lista todas as conversas do usuário"""
        current_user = await AuthMiddleware.get_current_user(request)
        user_id = current_user['id']

        # Buscar conexões aceitas
        connections = await db.connections.find({
            "$or": [
                {"requester_id": user_id, "status": "accepted"},
                {"receiver_id": user_id, "status": "accepted"}
            ]
        }, {"_id": 0}).to_list(100)

        results = []
        for conn in connections:
            other_user_id = conn['receiver_id'] if conn['requester_id'] == user_id else conn['requester_id']

            # Buscar dados do outro usuário
            other_user = await db.users.find_one({"id": other_user_id}, {"_id": 0, "password_hash": 0})
            if not other_user:
                continue

            profile = await db.user_profiles.find_one({"user_id": other_user_id}, {"_id": 0})

            # Buscar última mensagem
            last_message = await db.messages.find_one(
                {"connection_id": conn['id']},
                {"_id": 0}
            , sort=[("created_at", -1)])

            # Contar mensagens não lidas
            unread_count = await db.messages.count_documents({
                "connection_id": conn['id'],
                "receiver_id": user_id,
                "is_read": False
            })

            results.append({
                "connection_id": conn['id'],
                "user_id": other_user_id,
                "full_name": other_user.get('full_name', ''),
                "foto_url": profile.get('foto_url') if profile else other_user.get('avatar_url'),
                "headline": profile.get('headline') if profile else None,
                "last_message": last_message.get('content') if last_message else None,
                "last_message_at": last_message.get('created_at') if last_message else None,
                "unread_count": unread_count
            })

        # Ordenar por última mensagem
        results.sort(key=lambda x: x['last_message_at'] or '', reverse=True)

        return results


    @router.post("/messages/{message_id}/read")
    async def mark_message_read(message_id: str, request: Request):
        """Marca uma mensagem como lida"""
        current_user = await AuthMiddleware.get_current_user(request)

        result = await db.messages.update_one(
            {"id": message_id, "receiver_id": current_user['id']},
            {"$set": {"is_read": True}}
        )

        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Mensagem não encontrada")

        return {"message": "Mensagem marcada como lida"}


    @router.get("/messages/unread/count")
    async def get_unread_count(request: Request):
        """Retorna o total de mensagens não lidas"""
        current_user = await AuthMiddleware.get_current_user(request)

        count = await db.messages.count_documents({
            "receiver_id": current_user['id'],
            "is_read": False
        })

        return {"unread_count": count}

    # ============= MESSAGE DELETION ENDPOINTS =============

    async def log_message_before_delete(message: dict, deleted_by_id: str):
        """Cria log da mensagem antes de excluir (retenção de 30 dias)"""
        from datetime import timedelta

        # Buscar dados dos usuários
        sender = await db.users.find_one({"id": message['sender_id']}, {"_id": 0})
        receiver = await db.users.find_one({"id": message['receiver_id']}, {"_id": 0})

        log_entry = {
            "id": str(uuid.uuid4()),
            "original_message_id": message['id'],
            "connection_id": message.get('connection_id', ''),
            "sender_id": message['sender_id'],
            "sender_name": sender.get('full_name', '') if sender else '',
            "sender_email": sender.get('email', '') if sender else '',
            "receiver_id": message['receiver_id'],
            "receiver_name": receiver.get('full_name', '') if receiver else '',
            "receiver_email": receiver.get('email', '') if receiver else '',
            "content": message.get('content'),
            "attachments": message.get('attachments', []),
            "created_at": message.get('created_at'),
            "logged_at": datetime.now(timezone.utc).isoformat(),
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": deleted_by_id,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        }

        await db.message_logs.insert_one(log_entry)
        return log_entry


    @router.delete("/messages/{message_id}")
    async def delete_message(message_id: str, request: Request):
        """Exclui uma mensagem (cria log antes de excluir)"""
        current_user = await AuthMiddleware.get_current_user(request)

        # Buscar mensagem
        message = await db.messages.find_one({"id": message_id}, {"_id": 0})
        if not message:
            raise HTTPException(status_code=404, detail="Mensagem não encontrada")

        # Verificar se o usuário é o remetente ou destinatário
        if message['sender_id'] != current_user['id'] and message['receiver_id'] != current_user['id']:
            raise HTTPException(status_code=403, detail="Você não tem permissão para excluir esta mensagem")

        # Criar log antes de excluir
        await log_message_before_delete(message, current_user['id'])

        # Excluir mensagem
        await db.messages.delete_one({"id": message_id})

        # Notificar o outro usuário via WebSocket
        other_user_id = message['receiver_id'] if message['sender_id'] == current_user['id'] else message['sender_id']
        await connection_manager.send_message(other_user_id, {
            "type": "message_deleted",
            "message_id": message_id,
            "connection_id": message.get('connection_id')
        })

        return {"message": "Mensagem excluída com sucesso"}


    @router.delete("/messages/conversation/{connection_id}")
    async def delete_conversation(connection_id: str, request: Request):
        """Exclui todas as mensagens de uma conversa (cria logs antes de excluir)"""
        current_user = await AuthMiddleware.get_current_user(request)

        # Verificar se o usuário faz parte da conexão
        connection = await db.connections.find_one({"id": connection_id}, {"_id": 0})
        if not connection:
            raise HTTPException(status_code=404, detail="Conexão não encontrada")

        if connection['requester_id'] != current_user['id'] and connection['receiver_id'] != current_user['id']:
            raise HTTPException(status_code=403, detail="Você não faz parte desta conexão")

        # Buscar todas as mensagens da conversa
        messages = await db.messages.find({"connection_id": connection_id}, {"_id": 0}).to_list(1000)

        # Criar log de cada mensagem antes de excluir
        for message in messages:
            await log_message_before_delete(message, current_user['id'])

        # Excluir todas as mensagens
        result = await db.messages.delete_many({"connection_id": connection_id})

        # Notificar o outro usuário via WebSocket
        other_user_id = connection['receiver_id'] if connection['requester_id'] == current_user['id'] else connection['requester_id']
        await connection_manager.send_message(other_user_id, {
            "type": "conversation_deleted",
            "connection_id": connection_id
        })

        return {"message": f"{result.deleted_count} mensagem(ns) excluída(s) com sucesso"}



    return router
