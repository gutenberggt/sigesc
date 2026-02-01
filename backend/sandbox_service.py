"""
Serviço de Sandbox - SIGESC
Gerencia o banco de dados de teste para o papel admin_teste
"""

import os
import logging
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

class SandboxService:
    """
    Serviço para gerenciar o banco de dados sandbox (teste)
    - Copia dados do banco de produção para o sandbox
    - Reset automático diário à meia-noite
    """
    
    def __init__(self):
        self.mongo_url = os.environ.get('MONGO_URL')
        self.prod_db_name = os.environ.get('DB_NAME', 'sigesc_db')
        self.sandbox_db_name = f"{self.prod_db_name}_sandbox"
        self.client = None
        self.prod_db = None
        self.sandbox_db = None
        self.scheduler = None
        self.last_reset = None
        
    async def initialize(self, client: AsyncIOMotorClient):
        """Inicializa o serviço com o cliente MongoDB existente"""
        self.client = client
        self.prod_db = client[self.prod_db_name]
        self.sandbox_db = client[self.sandbox_db_name]
        
        # Configura o scheduler para reset automático
        self.scheduler = AsyncIOScheduler()
        self.scheduler.add_job(
            self.reset_sandbox,
            CronTrigger(hour=0, minute=0),  # Meia-noite
            id='sandbox_reset',
            name='Reset diário do banco sandbox',
            replace_existing=True
        )
        self.scheduler.start()
        logger.info(f"[Sandbox] Serviço inicializado. Banco sandbox: {self.sandbox_db_name}")
        logger.info("[Sandbox] Reset automático configurado para meia-noite")
        
        # Verifica se o sandbox já existe, se não, faz o primeiro reset
        collections = await self.sandbox_db.list_collection_names()
        if not collections:
            logger.info("[Sandbox] Banco sandbox vazio, realizando primeira cópia...")
            await self.reset_sandbox()
    
    def get_sandbox_db(self):
        """Retorna a referência do banco sandbox"""
        return self.sandbox_db
    
    async def reset_sandbox(self):
        """
        Reseta o banco sandbox copiando todos os dados do banco de produção
        """
        try:
            logger.info("[Sandbox] Iniciando reset do banco sandbox...")
            start_time = datetime.now(timezone.utc)
            
            # Lista todas as coleções do banco de produção
            collections = await self.prod_db.list_collection_names()
            
            # Remove todas as coleções do sandbox
            sandbox_collections = await self.sandbox_db.list_collection_names()
            for coll in sandbox_collections:
                await self.sandbox_db[coll].drop()
            
            # Copia cada coleção
            total_docs = 0
            for coll_name in collections:
                # Pula coleções de sistema
                if coll_name.startswith('system.'):
                    continue
                    
                # Busca todos os documentos da coleção de produção
                docs = await self.prod_db[coll_name].find({}).to_list(length=None)
                
                if docs:
                    # Insere no sandbox
                    await self.sandbox_db[coll_name].insert_many(docs)
                    total_docs += len(docs)
                    logger.info(f"[Sandbox] Copiados {len(docs)} documentos para {coll_name}")
            
            # Cria índices básicos no sandbox
            await self._create_sandbox_indexes()
            
            self.last_reset = datetime.now(timezone.utc)
            duration = (self.last_reset - start_time).total_seconds()
            
            logger.info(f"[Sandbox] Reset completo! {total_docs} documentos copiados em {duration:.2f}s")
            
            return {
                "success": True,
                "message": f"Sandbox resetado com sucesso",
                "documents_copied": total_docs,
                "collections_copied": len(collections),
                "duration_seconds": duration,
                "reset_at": self.last_reset.isoformat()
            }
            
        except Exception as e:
            logger.error(f"[Sandbox] Erro no reset: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _create_sandbox_indexes(self):
        """Cria índices essenciais no banco sandbox"""
        try:
            # Índices mínimos para performance
            await self.sandbox_db.users.create_index("id", unique=True)
            await self.sandbox_db.users.create_index("email", unique=True)
            await self.sandbox_db.students.create_index("id", unique=True)
            await self.sandbox_db.schools.create_index("id", unique=True)
            await self.sandbox_db.classes.create_index("id", unique=True)
            await self.sandbox_db.courses.create_index("id", unique=True)
            await self.sandbox_db.grades.create_index("id", unique=True)
            await self.sandbox_db.attendance.create_index("id", unique=True)
            await self.sandbox_db.staff.create_index("id", unique=True)
            logger.info("[Sandbox] Índices criados no banco sandbox")
        except Exception as e:
            logger.warning(f"[Sandbox] Aviso ao criar índices: {str(e)}")
    
    def get_status(self):
        """Retorna o status do serviço sandbox"""
        return {
            "sandbox_db_name": self.sandbox_db_name,
            "last_reset": self.last_reset.isoformat() if self.last_reset else None,
            "next_reset": "00:00 (meia-noite)",
            "scheduler_running": self.scheduler.running if self.scheduler else False
        }


# Instância global do serviço
sandbox_service = SandboxService()
