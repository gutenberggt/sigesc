from fastapi import FastAPI, APIRouter, HTTPException, status, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os
import logging
import json
from pathlib import Path
from datetime import datetime, timezone

from auth_utils import decode_token, token_blacklist
from auth_middleware import AuthMiddleware
from audit_service import audit_service
from sandbox_service import sandbox_service

# Import routers
from routers import (
    setup_users_router,
    setup_schools_router,
    setup_courses_router,
    setup_classes_router,
    setup_guardians_router,
    setup_enrollments_router,
    setup_students_router,
    setup_grades_router,
    setup_attendance_router,
    setup_calendar_router,
    setup_staff_router,
    setup_announcements_router,
    setup_analytics_router,
)
from routers.sync import setup_sync_router
from routers.medical_certificates import setup_medical_certificates_router
from routers.class_schedule import setup_class_schedule_router
from routers.diary_dashboard import create_diary_dashboard_router
from routers.aee import setup_aee_router
from routers.auth import setup_router as setup_auth_router

# Importar novos roteadores extraídos (Phase 2)
from routers import (
    admin_messages as admin_messages_mod,
    assignments as assignments_mod,
    attendance_ext as attendance_ext_mod,
    audit_logs as audit_logs_mod,
    calendar_ext as calendar_ext_mod,
    class_details as class_details_mod,
    debug as debug_mod,
    documents as documents_mod,
    learning_objects as learning_objects_mod,
    maintenance as maintenance_mod,
    mantenedora as mantenedora_mod,
    notifications as notifications_mod,
    pre_matricula as pre_matricula_mod,
    professor as professor_mod,
    profiles as profiles_mod,
    social as social_mod,
    uploads as uploads_mod,
    admin as admin_mod,
    sandbox as sandbox_mod,
)
from routers import hr as hr_mod

# Utilitários compartilhados
from utils.connection_manager import ConnectionManager, ActiveSessionsTracker
from utils.academic_year import create_academic_year_validators

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'sigesc_db')]

# Sandbox database para admin_teste
sandbox_db_name = os.environ.get('DB_NAME', 'sigesc_db') + '_sandbox'
sandbox_db = client[sandbox_db_name]

# Logger
logger = logging.getLogger(__name__)

# Instâncias globais compartilhadas
connection_manager = ConnectionManager()
active_sessions = ActiveSessionsTracker()

# Validadores de ano letivo e bimestre
_validators = create_academic_year_validators(db)
verify_academic_year_open_or_raise = _validators['verify_academic_year_open_or_raise']
verify_bimestre_edit_deadline_or_raise = _validators['verify_bimestre_edit_deadline_or_raise']
check_academic_year_open = _validators['check_academic_year_open']
check_bimestre_edit_deadline = _validators['check_bimestre_edit_deadline']

# kwargs compartilhados para roteadores extraídos
_shared_kwargs = {
    'verify_academic_year_open_or_raise': verify_academic_year_open_or_raise,
    'verify_bimestre_edit_deadline_or_raise': verify_bimestre_edit_deadline_or_raise,
    'check_academic_year_open': check_academic_year_open,
    'check_bimestre_edit_deadline': check_bimestre_edit_deadline,
    'connection_manager': connection_manager,
}

# Inicializa o serviço de auditoria com a conexão do banco
audit_service.set_db(db)

# Create the main app
app = FastAPI(title="SIGESC API", version="1.0.0")

# Configurar rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.on_event("startup")
async def create_indexes():
    """Cria índices otimizados no MongoDB durante o startup"""
    try:
        # Índices para students
        await db.students.create_index("id", unique=True)
        await db.students.create_index("cpf", sparse=True)
        await db.students.create_index("school_id")
        await db.students.create_index("class_id")
        await db.students.create_index([("full_name", 1)])
        
        # Índices para grades (notas) - muito consultada
        await db.grades.create_index("id", unique=True)
        await db.grades.create_index([("student_id", 1), ("academic_year", 1)])
        await db.grades.create_index([("class_id", 1), ("course_id", 1), ("academic_year", 1)])
        await db.grades.create_index("student_id")
        
        # Índices para attendance (frequência)
        await db.attendance.create_index("id", unique=True)
        await db.attendance.create_index([("class_id", 1), ("date", 1)])
        await db.attendance.create_index([("class_id", 1), ("academic_year", 1)])
        
        # Índices para enrollments (matrículas)
        await db.enrollments.create_index("id", unique=True)
        await db.enrollments.create_index([("student_id", 1), ("academic_year", 1)])
        await db.enrollments.create_index("school_id")
        # Índice parcial único para prevenir duplicatas de matrícula ativa na mesma turma
        await db.enrollments.create_index(
            [("student_id", 1), ("class_id", 1), ("academic_year", 1)],
            unique=True,
            partialFilterExpression={"status": "active"},
            name="unique_active_enrollment_per_class"
        )
        
        # Índices para classes (turmas)
        await db.classes.create_index("id", unique=True)
        await db.classes.create_index("school_id")
        await db.classes.create_index([("school_id", 1), ("academic_year", 1)])
        
        # Índices para staff (servidores)
        await db.staff.create_index("id", unique=True)
        await db.staff.create_index("email", sparse=True)
        await db.staff.create_index("cpf", sparse=True)
        
        # Índices para school_assignments (lotações)
        await db.school_assignments.create_index("id", unique=True)
        await db.school_assignments.create_index([("staff_id", 1), ("academic_year", 1)])
        await db.school_assignments.create_index([("school_id", 1), ("academic_year", 1)])
        
        # Índices para teacher_assignments (alocações)
        await db.teacher_assignments.create_index("id", unique=True)
        await db.teacher_assignments.create_index([("staff_id", 1), ("academic_year", 1)])
        await db.teacher_assignments.create_index([("class_id", 1), ("course_id", 1)])
        
        # Índices para courses (componentes)
        await db.courses.create_index("id", unique=True)
        await db.courses.create_index("nivel_ensino")
        
        # Índices para schools
        await db.schools.create_index("id", unique=True)
        
        # Índices para users
        await db.users.create_index("id", unique=True)
        await db.users.create_index("email", unique=True)
        
        # Índices para audit_logs
        await db.audit_logs.create_index([("timestamp", -1)])
        await db.audit_logs.create_index("user_id")
        await db.audit_logs.create_index("collection")
        await db.audit_logs.create_index([("collection", 1), ("document_id", 1)])
        
        # Índices para medical_certificates (atestados médicos)
        await db.medical_certificates.create_index("id", unique=True)
        await db.medical_certificates.create_index("student_id")
        await db.medical_certificates.create_index([("student_id", 1), ("start_date", 1), ("end_date", 1)])
        
        # Índices para RH / Folha
        await db.payroll_competencies.create_index("id", unique=True)
        await db.payroll_competencies.create_index([("year", -1), ("month", -1)], unique=True)
        await db.school_payrolls.create_index("id", unique=True)
        await db.school_payrolls.create_index([("competency_id", 1), ("school_id", 1)], unique=True)
        await db.school_payrolls.create_index("school_id")
        await db.payroll_items.create_index("id", unique=True)
        await db.payroll_items.create_index("school_payroll_id")
        await db.payroll_items.create_index([("competency_id", 1), ("employee_id", 1)])
        await db.payroll_occurrences.create_index("id", unique=True)
        await db.payroll_occurrences.create_index("payroll_item_id")
        
        logger.info("Índices MongoDB criados/verificados com sucesso")
        
        # Inicializa o serviço de sandbox
        await sandbox_service.initialize(client)
        
        # PATCH 3.3: Inicializa o serviço de blacklist de tokens
        token_blacklist.set_db(db)
        await token_blacklist.ensure_index()
        
    except Exception as e:
        logger.error(f"Erro ao criar índices MongoDB: {e}")

# Create uploads directory
UPLOADS_DIR = ROOT_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

# PATCH 1.2: Rota de uploads com validação anti-traversal
@app.get("/api/uploads/{file_path:path}")
async def serve_upload(file_path: str):
    """Serve uploaded files com validação de segurança"""
    # Validação anti-traversal: rejeita caminhos com ".." ou absolutos
    if '..' in file_path or file_path.startswith('/') or file_path.startswith('\\'):
        logger.warning(f"Tentativa de path traversal detectada: {file_path}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Caminho de arquivo inválido"
        )
    
    # Resolve o caminho e verifica se está dentro do diretório de uploads
    file_location = (UPLOADS_DIR / file_path).resolve()
    uploads_resolved = UPLOADS_DIR.resolve()
    
    # Verifica se o arquivo está realmente dentro do diretório de uploads
    try:
        file_location.relative_to(uploads_resolved)
    except ValueError:
        logger.warning(f"Tentativa de acesso fora do diretório de uploads: {file_path}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Acesso negado"
        )
    
    if file_location.exists() and file_location.is_file():
        # Determine content type
        suffix = file_location.suffix.lower()
        content_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.pdf': 'application/pdf',
        }
        content_type = content_types.get(suffix, 'application/octet-stream')
        return FileResponse(str(file_location), media_type=content_type)
    raise HTTPException(status_code=404, detail="File not found")

# Mount static files directory for backups
STATIC_DIR = ROOT_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Criar diretório para certificados
CERTIFICADOS_DIR = UPLOADS_DIR / "certificados"
CERTIFICADOS_DIR.mkdir(exist_ok=True)

# Endpoint de upload de certificados

# ============= HEALTH CHECK =============

@api_router.get("/")
async def root():
    """Health check"""
    return {
        "message": "SIGESC API - Sistema Integrado de Gestão Escolar",
        "version": "1.0.0",
        "status": "online"
    }

@api_router.get("/health")
async def health_check():
    """Verifica saúde da aplicação"""
    try:
        # Testa conexão com MongoDB
        await db.command('ping')
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "database": "disconnected",
                "error": str(e)
            }
        )

# ============= SETUP E REGISTRO DE ROTEADORES =============

# Helper para banco correto (produção ou sandbox)
def get_db_for_user(user: dict):
    if user.get('is_sandbox'):
        return sandbox_db if sandbox_db else db
    return db

# --- Roteadores com setup function própria ---
# Fase 1 (já existentes)
users_router = setup_users_router(db, audit_service, sandbox_db)
schools_router = setup_schools_router(db, audit_service, sandbox_db)
courses_router = setup_courses_router(db, audit_service)
classes_router = setup_classes_router(db, audit_service, sandbox_db)
guardians_router = setup_guardians_router(db, audit_service)
enrollments_router = setup_enrollments_router(db, audit_service)

students_router = setup_students_router(db, audit_service, sandbox_db)
grades_router = setup_grades_router(db, audit_service, verify_academic_year_open_or_raise, verify_bimestre_edit_deadline_or_raise, sandbox_db)
attendance_router = setup_attendance_router(db, audit_service, sandbox_db)
calendar_router = setup_calendar_router(db, audit_service, sandbox_db)
staff_router = setup_staff_router(db, audit_service, None, sandbox_db)
announcements_router = setup_announcements_router(db, audit_service, connection_manager, sandbox_db)
analytics_router = setup_analytics_router(db, audit_service, sandbox_db)
class_schedule_router = setup_class_schedule_router(db, audit_service, sandbox_db)

# Roteadores especiais
sync_router = setup_sync_router(db, AuthMiddleware, limiter)
medical_certificates_router = setup_medical_certificates_router(db, AuthMiddleware)
diary_dashboard_router = create_diary_dashboard_router()
aee_router = setup_aee_router(db, audit_service)
auth_router = setup_auth_router(db, audit_service)

# --- Fase 2: Roteadores extraídos automaticamente ---
admin_messages_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)
assignments_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)
attendance_ext_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)
audit_logs_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)
calendar_ext_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)
class_details_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)
debug_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)
documents_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)
learning_objects_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)
maintenance_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)
mantenedora_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)
notifications_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)
pre_matricula_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)
professor_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)
profiles_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)
social_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)
uploads_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)
admin_mod.setup_router(db, active_sessions=active_sessions, connection_manager=connection_manager, get_db_for_user=get_db_for_user)
sandbox_mod.setup_router(sandbox_service=sandbox_service)
hr_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)

# --- Incluir TODOS os roteadores na app ---
# Fase 1
app.include_router(students_router, prefix="/api")
app.include_router(grades_router, prefix="/api")
app.include_router(attendance_router, prefix="/api")
app.include_router(calendar_router, prefix="/api")
app.include_router(staff_router, prefix="/api")
app.include_router(announcements_router, prefix="/api")
app.include_router(analytics_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(schools_router, prefix="/api")
app.include_router(courses_router, prefix="/api")
app.include_router(classes_router, prefix="/api")
app.include_router(guardians_router, prefix="/api")
app.include_router(enrollments_router, prefix="/api")
app.include_router(sync_router, prefix="/api")
app.include_router(medical_certificates_router, prefix="/api")
app.include_router(class_schedule_router, prefix="/api")
app.include_router(diary_dashboard_router, prefix="/api")
app.include_router(aee_router, prefix="/api")
app.include_router(auth_router, prefix="/api")

# Fase 2 - roteadores extraídos
app.include_router(admin_messages_mod.router, prefix="/api")
app.include_router(assignments_mod.router, prefix="/api")
app.include_router(attendance_ext_mod.router, prefix="/api")
app.include_router(audit_logs_mod.router, prefix="/api")
app.include_router(calendar_ext_mod.router, prefix="/api")
app.include_router(class_details_mod.router, prefix="/api")
app.include_router(debug_mod.router, prefix="/api")
app.include_router(documents_mod.router, prefix="/api")
app.include_router(learning_objects_mod.router, prefix="/api")
app.include_router(maintenance_mod.router, prefix="/api")
app.include_router(mantenedora_mod.router, prefix="/api")
app.include_router(notifications_mod.router, prefix="/api")
app.include_router(pre_matricula_mod.router, prefix="/api")
app.include_router(professor_mod.router, prefix="/api")
app.include_router(profiles_mod.router, prefix="/api")
app.include_router(social_mod.router, prefix="/api")
app.include_router(uploads_mod.router, prefix="/api")
app.include_router(admin_mod.router, prefix="/api")
app.include_router(sandbox_mod.router, prefix="/api")
app.include_router(hr_mod.router, prefix="/api")

# Include the legacy api_router AFTER modular routers
app.include_router(api_router)


# ============= WEBSOCKET ENDPOINT =============

@app.websocket("/api/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str):
    """Endpoint WebSocket para mensagens em tempo real"""
    try:
        # Decodificar token para obter user_id
        payload = decode_token(token)
        if not payload:
            logger.warning(f"WebSocket: Token inválido")
            await websocket.close(code=4001)
            return
        
        # O token usa 'sub' como chave para user_id
        user_id = payload.get('sub')
        if not user_id:
            logger.warning(f"WebSocket: Token sem user_id")
            await websocket.close(code=4001)
            return
        
        logger.info(f"WebSocket: Tentando conectar user_id={user_id}")
        
        # Conectar
        await connection_manager.connect(websocket, user_id)
        
        try:
            while True:
                # Aguardar mensagens do cliente (ping/pong ou comandos)
                data = await websocket.receive_text()
                
                # Se receber ping, responder com pong
                if data == "ping":
                    await websocket.send_text("pong")
                else:
                    # Processar outros comandos se necessário
                    try:
                        message = json.loads(data)
                        # Aqui pode processar comandos específicos
                        if message.get('type') == 'mark_read':
                            # Marcar mensagens como lidas
                            pass
                    except json.JSONDecodeError:
                        pass
                        
        except WebSocketDisconnect:
            connection_manager.disconnect(websocket, user_id)
            
    except Exception as e:
        logger.error(f"Erro no WebSocket: {e}")
        try:
            await websocket.close(code=4000)
        except:
            pass

# Middleware para rastrear sessões ativas
@app.middleware("http")
async def track_active_sessions(request: Request, call_next):
    response = await call_next(request)
    if response.status_code < 400:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                token = auth_header.split(" ")[1]
                payload = decode_token(token)
                user_id = payload.get("sub")
                if user_id:
                    user = await db.users.find_one({"id": user_id}, {"_id": 0})
                    if user:
                        active_sessions.update(user_id, user)
            except Exception:
                pass
    return response

# Global exception handler para garantir CORS em erros 500
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno do servidor"}
    )

# CORS middleware (deve ser o último middleware adicionado)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    """Fecha conexão com MongoDB ao desligar"""
    client.close()
    logger.info("MongoDB connection closed")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
