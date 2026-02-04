"""
SIGESC - App Factory Pattern
PATCH 4.x: Refatoração do server.py para melhor organização e manutenibilidade

Este módulo implementa o padrão Factory para criar a aplicação FastAPI,
permitindo melhor testabilidade e separação de responsabilidades.
"""
from fastapi import FastAPI, APIRouter
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pathlib import Path
from dotenv import load_dotenv
import os
import logging

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')


def create_app(testing: bool = False) -> FastAPI:
    """
    Factory function para criar a aplicação FastAPI.
    
    Args:
        testing: Se True, usa configurações de teste
        
    Returns:
        Instância configurada do FastAPI
    """
    app = FastAPI(
        title="SIGESC API",
        version="1.0.0",
        description="Sistema Integrado de Gestão Escolar",
        docs_url="/api/docs" if not testing else "/docs",
        redoc_url="/api/redoc" if not testing else "/redoc"
    )
    
    # Configura rate limiting
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    
    # Configura CORS
    configure_cors(app)
    
    # Configura diretórios estáticos
    configure_static_dirs(app)
    
    return app


def configure_cors(app: FastAPI):
    """Configura CORS para a aplicação"""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def configure_static_dirs(app: FastAPI):
    """Configura diretórios estáticos"""
    # Diretório de uploads
    uploads_dir = ROOT_DIR / "uploads"
    uploads_dir.mkdir(exist_ok=True)
    
    # Diretório estático
    static_dir = ROOT_DIR / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


def get_database_client():
    """Retorna cliente MongoDB configurado"""
    mongo_url = os.environ['MONGO_URL']
    return AsyncIOMotorClient(mongo_url)


def get_database(client: AsyncIOMotorClient):
    """Retorna banco de dados principal"""
    db_name = os.environ.get('DB_NAME', 'sigesc_db')
    return client[db_name]


def get_sandbox_database(client: AsyncIOMotorClient):
    """Retorna banco de dados sandbox para testes"""
    db_name = os.environ.get('DB_NAME', 'sigesc_db')
    return client[f"{db_name}_sandbox"]


async def create_indexes(db):
    """Cria índices otimizados no MongoDB"""
    try:
        # Índices para students
        await db.students.create_index("id", unique=True)
        await db.students.create_index("cpf", sparse=True)
        await db.students.create_index("school_id")
        await db.students.create_index("class_id")
        await db.students.create_index([("full_name", 1)])
        
        # Índices para grades (notas)
        await db.grades.create_index("id", unique=True)
        await db.grades.create_index([("student_id", 1), ("academic_year", 1)])
        await db.grades.create_index([("class_id", 1), ("course_id", 1), ("academic_year", 1)])
        
        # Índices para attendance (frequência)
        await db.attendance.create_index("id", unique=True)
        await db.attendance.create_index([("class_id", 1), ("date", 1)])
        
        # Índices para enrollments (matrículas)
        await db.enrollments.create_index("id", unique=True)
        await db.enrollments.create_index([("student_id", 1), ("academic_year", 1)])
        
        # Índices para classes (turmas)
        await db.classes.create_index("id", unique=True)
        await db.classes.create_index("school_id")
        
        # Índices para staff (servidores)
        await db.staff.create_index("id", unique=True)
        await db.staff.create_index("email", sparse=True)
        
        # Índices para users
        await db.users.create_index("id", unique=True)
        await db.users.create_index("email", unique=True)
        
        # Índices para audit_logs
        await db.audit_logs.create_index([("timestamp", -1)])
        await db.audit_logs.create_index("user_id")
        
        logger.info("Índices MongoDB criados/verificados com sucesso")
        
    except Exception as e:
        logger.error(f"Erro ao criar índices MongoDB: {e}")


def get_db_for_user(user: dict, production_db, sandbox_db):
    """
    Retorna o banco de dados correto baseado no usuário.
    Agora todos os usuários usam o banco de produção (sandbox desabilitado).
    """
    # Sandbox desabilitado - todos usam produção
    return production_db
