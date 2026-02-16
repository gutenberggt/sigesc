from fastapi import FastAPI, APIRouter, HTTPException, status, Depends, Request, UploadFile, File, WebSocket, WebSocketDisconnect, Response, Query
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os
import logging
import uuid
import shutil
import json
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime, timezone, timedelta
from io import BytesIO

# Import models and utilities
from models import (
    User, UserCreate, UserUpdate, UserResponse, UserInDB,
    LoginRequest, TokenResponse, RefreshTokenRequest,
    UserProfile, UserProfileCreate, UserProfileUpdate,
    ProfileExperience, ProfileEducation, ProfileSkill, ProfileCertification,
    Connection, ConnectionCreate, ConnectionResponse,
    Message, MessageCreate, MessageResponse, MessageAttachment, ConversationResponse,
    School, SchoolCreate, SchoolUpdate,
    Class, ClassCreate, ClassUpdate,
    Course, CourseCreate, CourseUpdate,
    Student, StudentCreate, StudentUpdate,
    Guardian, GuardianCreate, GuardianUpdate,
    Enrollment, EnrollmentCreate, EnrollmentUpdate,
    Grade, GradeCreate, GradeUpdate,
    Attendance, AttendanceCreate, AttendanceUpdate, AttendanceRecord, AttendanceSettings,
    Notice, NoticeCreate, NoticeUpdate,
    Document, DocumentCreate,
    CalendarEvent, CalendarEventCreate, CalendarEventUpdate,
    Staff, StaffCreate, StaffUpdate,
    SchoolAssignment, SchoolAssignmentCreate, SchoolAssignmentUpdate,
    TeacherAssignment, TeacherAssignmentCreate, TeacherAssignmentUpdate,
    Announcement, AnnouncementCreate, AnnouncementUpdate, AnnouncementResponse,
    AnnouncementRecipient, AnnouncementReadStatus, NotificationCount,
    Mantenedora, MantenedoraUpdate,
    AuditLog, AuditLogFilter,
    PreMatricula, PreMatriculaCreate
)
from auth_utils import (
    hash_password, verify_password, create_access_token, 
    create_refresh_token, decode_token, get_school_ids_from_links,
    token_blacklist  # PATCH 3.3: Serviço de blacklist de tokens
)
from auth_middleware import AuthMiddleware
from audit_service import audit_service
from sandbox_service import sandbox_service
from pdf_generator import (
    generate_boletim_pdf,
    generate_declaracao_matricula_pdf,
    generate_declaracao_frequencia_pdf,
    generate_ficha_individual_pdf,
    generate_certificado_pdf,
    generate_class_details_pdf,
    generate_livro_promocao_pdf,
    generate_relatorio_frequencia_bimestre_pdf
)
from ftp_upload import upload_to_ftp, delete_from_ftp
from grade_calculator import calculate_and_update_grade

# Import routers
from routers import (
    setup_users_router,
    setup_schools_router,
    setup_courses_router,
    setup_classes_router,
    setup_guardians_router,
    setup_enrollments_router,
    setup_students_router,       # PATCH 4.x
    setup_grades_router,         # PATCH 4.x
    setup_attendance_router,     # PATCH 4.x
    setup_calendar_router,       # PATCH 4.x
    setup_staff_router,          # PATCH 4.x
    setup_announcements_router,  # PATCH 4.x
    setup_analytics_router       # Dashboard Analítico
)
from routers.sync import setup_sync_router
from routers.medical_certificates import setup_medical_certificates_router
from routers.class_schedule import setup_class_schedule_router
from routers.diary_dashboard import create_diary_dashboard_router

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'sigesc_db')]

# Sandbox database para admin_teste
sandbox_db_name = os.environ.get('DB_NAME', 'sigesc_db') + '_sandbox'
sandbox_db = client[sandbox_db_name]

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
@api_router.post("/upload/certificado")
async def upload_certificado(request: Request, file: UploadFile = File(...)):
    """Upload de certificado de formação/especialização"""
    from auth_middleware import AuthMiddleware
    
    # Verificar autenticação
    try:
        user = await AuthMiddleware.get_current_user(request)
    except:
        raise HTTPException(status_code=401, detail="Não autorizado")
    
    # Validar tipo de arquivo
    allowed_types = ['application/pdf', 'image/jpeg', 'image/png', 'image/jpg']
    allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
    
    file_ext = Path(file.filename).suffix.lower() if file.filename else ''
    if file_ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Tipo de arquivo não permitido. Use PDF, JPG ou PNG.")
    
    # Gerar nome único
    import uuid
    unique_name = f"{uuid.uuid4()}{file_ext}"
    file_path = CERTIFICADOS_DIR / unique_name
    
    # Salvar arquivo
    try:
        content = await file.read()
        with open(file_path, 'wb') as f:
            f.write(content)
        
        return {"url": f"/api/uploads/certificados/{unique_name}"}
    except Exception as e:
        logger.error(f"Erro ao salvar certificado: {e}")
        raise HTTPException(status_code=500, detail="Erro ao salvar arquivo")

# Endpoint de diagnóstico FTP (temporário - remover após debug)
@api_router.get("/debug/ftp-config")
async def debug_ftp_config(request: Request):
    """Endpoint temporário para verificar configuração FTP em produção"""
    from ftp_upload import get_ftp_config
    config = get_ftp_config()
    return {
        "ftp_host": config["host"] if config["host"] else "NÃO CONFIGURADO",
        "ftp_port": config["port"],
        "ftp_user": config["user"] if config["user"] else "NÃO CONFIGURADO",
        "ftp_password": "***" if config["password"] else "NÃO CONFIGURADO",
        "ftp_base_path": config["base_path"],
        "ftp_base_url": config["base_url"],
        "env_vars_found": {
            "FTP_HOST": bool(os.environ.get("FTP_HOST")),
            "FTP_USER": bool(os.environ.get("FTP_USER")),
            "FTP_PASSWORD": bool(os.environ.get("FTP_PASSWORD")),
            "FTP_BASE_PATH": bool(os.environ.get("FTP_BASE_PATH")),
            "FTP_BASE_URL": bool(os.environ.get("FTP_BASE_URL")),
        }
    }

# Helper para obter o banco de dados correto (produção ou sandbox)
def get_db_for_user(user: dict):
    """Retorna o banco de dados correto baseado no usuário"""
    if user.get('is_sandbox') or user.get('role') == 'admin_teste':
        return sandbox_db
    return db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# PATCH 1.1: Rotas de backup DESATIVADAS por segurança
# Para reativar em ambiente controlado, defina ENABLE_BACKUP_DOWNLOAD=true no .env
ENABLE_BACKUP_DOWNLOAD = os.environ.get('ENABLE_BACKUP_DOWNLOAD', 'false').lower() == 'true'

@app.get("/api/download-backup")
async def download_backup(request: Request):
    """Download database backup file - RESTRITO"""
    if not ENABLE_BACKUP_DOWNLOAD:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Download de backup desativado por segurança. Contate o administrador."
        )
    
    # Requer autenticação de admin
    current_user = await AuthMiddleware.require_roles(['admin'])(request)
    
    backup_path = STATIC_DIR / "backup_sigesc.tar.gz"
    if backup_path.exists():
        return FileResponse(
            path=str(backup_path),
            filename="backup_sigesc.tar.gz",
            media_type="application/gzip"
        )
    return {"error": "Backup file not found"}

@app.get("/api/download-uploads")
async def download_uploads(request: Request):
    """Download uploads backup file - RESTRITO"""
    if not ENABLE_BACKUP_DOWNLOAD:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Download de backup desativado por segurança. Contate o administrador."
        )
    
    # Requer autenticação de admin
    current_user = await AuthMiddleware.require_roles(['admin'])(request)
    
    backup_path = STATIC_DIR / "uploads_backup.tar.gz"
    if backup_path.exists():
        return FileResponse(
            path=str(backup_path),
            filename="uploads_backup.tar.gz",
            media_type="application/gzip"
        )
    return {"error": "Uploads backup file not found"}

# ============= WEBSOCKET CONNECTION MANAGER =============

class ConnectionManager:
    """Gerenciador de conexões WebSocket para mensagens em tempo real"""
    
    def __init__(self):
        # Mapeia user_id -> lista de WebSocket connections
        self.active_connections: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str):
        """Aceita nova conexão WebSocket"""
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logger.info(f"WebSocket conectado: user_id={user_id}")
    
    def disconnect(self, websocket: WebSocket, user_id: str):
        """Remove conexão WebSocket"""
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        logger.info(f"WebSocket desconectado: user_id={user_id}")
    
    async def send_message(self, user_id: str, message: dict):
        """Envia mensagem para um usuário específico"""
        if user_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Erro ao enviar mensagem WebSocket: {e}")
                    disconnected.append(connection)
            # Remover conexões falhas
            for conn in disconnected:
                self.active_connections[user_id].remove(conn)
    
    async def send_notification(self, user_id: str, notification: dict):
        """Envia notificação para um usuário"""
        await self.send_message(user_id, notification)
    
    async def broadcast(self, message: dict, exclude_user_id: str = None):
        """Envia mensagem para todos os usuários conectados"""
        for user_id, connections in self.active_connections.items():
            if user_id != exclude_user_id:
                await self.send_message(user_id, message)

# Instância global do gerenciador de conexões
connection_manager = ConnectionManager()

# ============= ACADEMIC YEAR STATUS VERIFICATION =============

async def check_academic_year_open(school_id: str, academic_year: int) -> bool:
    """
    Verifica se o ano letivo está aberto para uma escola específica.
    Retorna True se o ano está aberto ou não configurado, False se está fechado.
    """
    school = await db.schools.find_one(
        {"id": school_id},
        {"_id": 0, "anos_letivos": 1}
    )
    
    if not school or not school.get('anos_letivos'):
        return True  # Se não há configuração, permite edição
    
    year_config = school['anos_letivos'].get(str(academic_year))
    if not year_config:
        return True  # Se o ano não está configurado, permite edição
    
    return year_config.get('status', 'aberto') != 'fechado'

async def verify_academic_year_open_or_raise(school_id: str, academic_year: int):
    """
    Verifica se o ano letivo está aberto e lança exceção se estiver fechado.
    """
    is_open = await check_academic_year_open(school_id, academic_year)
    if not is_open:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"O ano letivo {academic_year} está fechado para esta escola. Não é possível fazer alterações."
        )

async def check_bimestre_edit_deadline(academic_year: int, bimestre: int = None) -> dict:
    """
    Verifica se a data limite de edição do bimestre foi ultrapassada.
    Se bimestre não for especificado, verifica todos os bimestres.
    
    Retorna:
        {
            "can_edit": bool,
            "bimestre": int or None,
            "data_limite": str or None,
            "message": str
        }
    """
    from datetime import date
    
    today = date.today().isoformat()
    
    # Busca o calendário letivo do ano
    calendario = await db.calendario_letivo.find_one(
        {"ano_letivo": academic_year},
        {"_id": 0}
    )
    
    if not calendario:
        return {"can_edit": True, "bimestre": None, "data_limite": None, "message": "Calendário letivo não configurado"}
    
    # Se bimestre específico
    if bimestre:
        data_limite = calendario.get(f"bimestre_{bimestre}_data_limite")
        if not data_limite:
            return {"can_edit": True, "bimestre": bimestre, "data_limite": None, "message": f"Data limite do {bimestre}º bimestre não configurada"}
        
        if today > data_limite:
            return {
                "can_edit": False, 
                "bimestre": bimestre, 
                "data_limite": data_limite,
                "message": f"O prazo para edição do {bimestre}º bimestre encerrou em {data_limite}"
            }
        return {"can_edit": True, "bimestre": bimestre, "data_limite": data_limite, "message": "Dentro do prazo"}
    
    # Verifica todos os bimestres e retorna o bimestre atual baseado na data
    for i in range(1, 5):
        inicio = calendario.get(f"bimestre_{i}_inicio")
        fim = calendario.get(f"bimestre_{i}_fim")
        data_limite = calendario.get(f"bimestre_{i}_data_limite")
        
        if inicio and fim and today >= inicio and today <= fim:
            # Estamos dentro deste bimestre
            if data_limite and today > data_limite:
                return {
                    "can_edit": False,
                    "bimestre": i,
                    "data_limite": data_limite,
                    "message": f"O prazo para edição do {i}º bimestre encerrou em {data_limite}"
                }
            return {"can_edit": True, "bimestre": i, "data_limite": data_limite, "message": "Dentro do prazo"}
    
    return {"can_edit": True, "bimestre": None, "data_limite": None, "message": "Fora do período letivo"}

async def verify_bimestre_edit_deadline_or_raise(academic_year: int, bimestre: int, user_role: str):
    """
    Verifica se pode editar notas/frequência do bimestre e lança exceção se não puder.
    Admin e secretário podem editar mesmo após a data limite.
    """
    # Admin e secretário podem sempre editar
    if user_role in ['admin', 'secretario']:
        return True
    
    check = await check_bimestre_edit_deadline(academic_year, bimestre)
    
    if not check["can_edit"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=check["message"]
        )
    
    return True

# Hierarquia de roles (maior valor = maior permissão)
ROLE_HIERARCHY = {
    'diretor': 5,
    'coordenador': 4,
    'secretario': 3,
    'professor': 2,
    'aluno': 1,
    'responsavel': 1
}

async def get_effective_role_from_lotacoes(user_email: str, base_role: str) -> tuple:
    """
    Determina o role efetivo do usuário baseado nas suas lotações.
    Retorna (effective_role, school_links)
    
    Hierarquia: diretor > coordenador > secretario > professor
    """
    # Busca servidor vinculado ao email do usuário
    staff = await db.staff.find_one(
        {"email": {"$regex": f"^{user_email}$", "$options": "i"}},
        {"_id": 0, "id": 1, "nome": 1, "full_name": 1}
    )
    
    if not staff:
        # Tenta buscar pelo user_id
        user = await db.users.find_one({"email": user_email}, {"_id": 0, "id": 1, "full_name": 1})
        if user:
            staff = await db.staff.find_one(
                {"user_id": user['id']},
                {"_id": 0, "id": 1, "nome": 1, "full_name": 1}
            )
    
    if not staff:
        return base_role, []
    
    # Busca todas as lotações ativas do servidor
    lotacoes = await db.school_assignments.find(
        {"staff_id": staff['id'], "status": "ativo"},
        {"_id": 0, "school_id": 1, "funcao": 1}
    ).to_list(100)
    
    if not lotacoes:
        return base_role, []
    
    # Determina o role de maior hierarquia e coleta school_links
    highest_role = base_role
    highest_priority = ROLE_HIERARCHY.get(base_role, 0)
    
    # Agrupa lotações por escola
    school_roles = {}
    for lotacao in lotacoes:
        funcao = lotacao.get('funcao', 'professor')
        school_id = lotacao.get('school_id')
        
        if school_id not in school_roles:
            school_roles[school_id] = []
        school_roles[school_id].append(funcao)
        
        # Verifica se é o role de maior hierarquia
        role_priority = ROLE_HIERARCHY.get(funcao, 0)
        if role_priority > highest_priority:
            highest_priority = role_priority
            highest_role = funcao
    
    # Monta school_links no formato correto (SchoolLink)
    school_links = [
        {
            "school_id": school_id,
            "roles": roles,
            "class_ids": []
        }
        for school_id, roles in school_roles.items()
    ]
    
    return highest_role, school_links

# ============= AUTH ROUTES =============

@api_router.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate):
    """Registra novo usuário"""
    # Verifica se email já existe
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email já cadastrado"
        )
    
    # Cria usuário
    user_dict = user_data.model_dump(exclude={'password'})
    user_obj = UserInDB(
        **user_dict,
        password_hash=hash_password(user_data.password)
    )
    
    # Salva no banco
    doc = user_obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    
    await db.users.insert_one(doc)
    
    # Retorna sem password_hash
    return UserResponse(**user_obj.model_dump(exclude={'password_hash'}))

@api_router.post("/auth/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(credentials: LoginRequest, request: Request):
    """Autentica usuário e retorna tokens. Rate limited: 5 tentativas por minuto."""
    
    # Verifica se é login de teste (email com sufixo +teste)
    email = credentials.email
    is_sandbox_login = '+teste@' in email
    
    if is_sandbox_login:
        # Remove o sufixo +teste para buscar o usuário real
        # Ex: gutenberg+teste@sigesc.com -> gutenberg@sigesc.com
        email = email.replace('+teste@', '@')
    
    # Busca usuário no banco de produção
    user_doc = await db.users.find_one({"email": email}, {"_id": 0})
    
    if not user_doc:
        # Registra tentativa de login falhada
        await audit_service.log(
            action='login',
            collection='users',
            user={'id': 'unknown', 'email': credentials.email, 'role': 'unknown'},
            request=request,
            description=f"Tentativa de login falhada - usuário não encontrado: {credentials.email}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos"
        )
    
    user = UserInDB(**user_doc)
    
    # Verifica se o usuário é admin para poder usar modo teste
    if is_sandbox_login and user.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores podem usar o modo teste"
        )
    
    # Verifica senha
    if not verify_password(credentials.password, user.password_hash):
        # Registra tentativa de login falhada
        await audit_service.log(
            action='login',
            collection='users',
            user={'id': user.id, 'email': user.email, 'role': user.role},
            request=request,
            description=f"Tentativa de login falhada - senha incorreta: {credentials.email}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos"
        )
    
    # Verifica se usuário está ativo
    if user.status != 'active':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário inativo"
        )
    
    # Determina role efetivo
    effective_role = user.role
    effective_school_links = user.school_links or []
    
    # Se for login de teste, muda o role para admin_teste
    if is_sandbox_login:
        effective_role = 'admin_teste'
        logger.info(f"[Sandbox] Login de teste realizado: {user.email}")
    elif user.role in ['professor', 'secretario', 'coordenador', 'diretor']:
        effective_role, lotacao_school_links = await get_effective_role_from_lotacoes(user.email, user.role)
        
        # Usa school_links das lotações se existirem, senão usa os do cadastro
        if lotacao_school_links:
            effective_school_links = lotacao_school_links
    
    # Cria tokens com role efetivo
    school_ids = [link.get('school_id') for link in effective_school_links if link.get('school_id')]
    token_data = {
        "sub": user.id,
        "email": user.email,
        "role": effective_role,
        "school_ids": school_ids,
        "is_sandbox": is_sandbox_login  # Flag para identificar modo sandbox
    }
    
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token({"sub": user.id})
    
    # Registra login bem sucedido
    await audit_service.log(
        action='login',
        collection='users',
        user={'id': user.id, 'email': user.email, 'role': effective_role, 'full_name': user.full_name},
        request=request,
        document_id=user.id,
        description=f"Login realizado: {user.full_name}" + (" (MODO TESTE)" if is_sandbox_login else "")
    )
    
    # Retorna usuário com role efetivo
    user_response_data = user.model_dump(exclude={'password_hash'})
    user_response_data['role'] = effective_role
    user_response_data['school_links'] = effective_school_links
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse(**user_response_data)
    )

@api_router.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token(refresh_request: RefreshTokenRequest):
    """
    Renova access token usando refresh token.
    PATCH 3.2: Implementa rotação de tokens - o refresh token antigo é revogado.
    PATCH 3.3: Verifica blacklist antes de aceitar o token.
    """
    payload = decode_token(refresh_request.refresh_token)
    
    if not payload or payload.get('type') != 'refresh':
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido"
        )
    
    user_id = payload.get('sub')
    token_jti = payload.get('jti')  # PATCH 3.2: ID único do token
    token_iat = payload.get('iat')  # PATCH 3.3: Timestamp de criação
    
    # PATCH 3.3: Verifica se o token foi revogado
    if await token_blacklist.is_token_revoked(jti=token_jti, user_id=user_id, issued_at=token_iat):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revogado. Faça login novamente."
        )
    
    user_doc = await db.users.find_one({"id": user_id}, {"_id": 0})
    
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado"
        )
    
    user = UserInDB(**user_doc)
    
    if user.status != 'active':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário inativo"
        )
    
    # PATCH 3.2: Revoga o refresh token atual (rotação)
    if token_jti:
        token_exp = payload.get('exp')
        if token_exp:
            from datetime import datetime, timezone
            exp_datetime = datetime.fromtimestamp(token_exp, tz=timezone.utc)
            await token_blacklist.revoke_token(
                jti=token_jti,
                user_id=user_id,
                expires_at=exp_datetime,
                reason='token_rotation'
            )
    
    # Determina role efetivo baseado nas lotações
    effective_role = user.role
    effective_school_links = user.school_links or []
    
    if user.role in ['professor', 'secretario', 'coordenador', 'diretor']:
        effective_role, lotacao_school_links = await get_effective_role_from_lotacoes(user.email, user.role)
        if lotacao_school_links:
            effective_school_links = lotacao_school_links
    
    # Cria novos tokens com role efetivo
    school_ids = [link.get('school_id') for link in effective_school_links if link.get('school_id')]
    token_data = {
        "sub": user.id,
        "email": user.email,
        "role": effective_role,
        "school_ids": school_ids
    }
    
    access_token = create_access_token(token_data)
    new_refresh_token = create_refresh_token({"sub": user.id})  # PATCH 3.2: Novo refresh token com novo jti
    
    # Retorna usuário com role efetivo
    user_response_data = user.model_dump(exclude={'password_hash'})
    user_response_data['role'] = effective_role
    user_response_data['school_links'] = effective_school_links
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        user=UserResponse(**user_response_data)
    )

# PATCH 3.3: Endpoint de logout para revogar tokens
@api_router.post("/auth/logout")
async def logout(request: Request):
    """
    Revoga o refresh token atual do usuário.
    PATCH 3.3: Implementa logout seguro com revogação de token.
    """
    current_user = await AuthMiddleware.get_current_user(request)
    
    # Tenta extrair o refresh token do body se fornecido
    try:
        body = await request.json()
        refresh_token = body.get('refresh_token')
        
        if refresh_token:
            payload = decode_token(refresh_token)
            if payload and payload.get('jti'):
                token_exp = payload.get('exp')
                exp_datetime = datetime.fromtimestamp(token_exp, tz=timezone.utc) if token_exp else datetime.now(timezone.utc) + timedelta(days=7)
                
                await token_blacklist.revoke_token(
                    jti=payload.get('jti'),
                    user_id=current_user['id'],
                    expires_at=exp_datetime,
                    reason='user_logout'
                )
    except:
        pass  # Body vazio ou sem refresh_token - ok
    
    # Registra logout
    await audit_service.log(
        action='logout',
        collection='users',
        user=current_user,
        request=request,
        document_id=current_user['id'],
        description=f"Logout realizado"
    )
    
    return {"message": "Logout realizado com sucesso"}

# PATCH 3.3: Endpoint para revogar todas as sessões
@api_router.post("/auth/logout-all")
async def logout_all_sessions(request: Request):
    """
    Revoga TODOS os refresh tokens do usuário (logout de todas as sessões).
    PATCH 3.3: Útil quando o usuário suspeita de acesso não autorizado.
    """
    current_user = await AuthMiddleware.get_current_user(request)
    
    await token_blacklist.revoke_all_user_tokens(
        user_id=current_user['id'],
        reason='user_logout_all'
    )
    
    # Registra logout global
    await audit_service.log(
        action='logout_all',
        collection='users',
        user=current_user,
        request=request,
        document_id=current_user['id'],
        description=f"Logout de todas as sessões realizado"
    )
    
    return {"message": "Todas as sessões foram encerradas. Faça login novamente."}

@api_router.get("/auth/me", response_model=UserResponse)
async def get_current_user_info(request: Request):
    """Retorna informações do usuário autenticado com role efetivo"""
    current_user = await AuthMiddleware.get_current_user(request)
    
    user_doc = await db.users.find_one({"id": current_user['id']}, {"_id": 0})
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado"
        )
    
    # Substitui o role do banco pelo role efetivo do token (que já considera lotações)
    user_doc['role'] = current_user.get('role', user_doc.get('role'))
    
    return UserResponse(**user_doc)

@api_router.get("/auth/permissions")
async def get_user_permissions(request: Request):
    """Retorna as permissões do usuário autenticado baseado no seu role"""
    current_user = await AuthMiddleware.get_current_user(request)
    
    permissions = AuthMiddleware.get_user_permissions(current_user)
    permissions['school_ids'] = current_user.get('school_ids', [])
    
    return permissions

# ============= USER ROUTES - MOVIDO PARA routers/users.py =============

# ============= SCHOOL ROUTES - MOVIDO PARA routers/schools.py =============

# ============= CLASS (TURMA) ROUTES - CRUD MOVIDO PARA routers/classes.py =============
# Os endpoints de detalhes permanecem aqui por sua complexidade

@api_router.get("/classes/{class_id}/details")
async def get_class_details(class_id: str, request: Request):
    """
    Busca detalhes completos da turma incluindo:
    - Dados cadastrais da turma
    - Escola
    - Professor(es) alocado(s)
    - Lista de alunos matriculados com responsáveis
    """
    current_user = await AuthMiddleware.get_current_user(request)
    
    # Busca turma
    class_doc = await db.classes.find_one({"id": class_id}, {"_id": 0})
    if not class_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turma não encontrada"
        )
    
    # Busca escola
    school = await db.schools.find_one({"id": class_doc.get('school_id')}, {"_id": 0, "id": 1, "name": 1})
    
    # Busca professores alocados na turma
    alocacoes = await db.teacher_assignments.find(
        {"class_id": class_id},
        {"_id": 0}
    ).to_list(100)
    
    # Agrupa por professor para evitar duplicação
    teachers_map = {}
    for alocacao in alocacoes:
        staff_id = alocacao.get('staff_id')
        if staff_id not in teachers_map:
            staff = await db.staff.find_one(
                {"id": staff_id},
                {"_id": 0, "id": 1, "nome": 1, "full_name": 1, "email": 1, "celular": 1}
            )
            if staff:
                teachers_map[staff_id] = {
                    "staff_id": staff.get('id'),
                    "nome": staff.get('nome') or staff.get('full_name'),
                    "email": staff.get('email'),
                    "celular": staff.get('celular'),
                    "componentes": []
                }
        
        # Adiciona componente se existir
        if staff_id in teachers_map and alocacao.get('course_id'):
            course = await db.courses.find_one(
                {"id": alocacao.get('course_id')},
                {"_id": 0, "id": 1, "name": 1, "nome": 1}
            )
            if course:
                comp_name = course.get('name') or course.get('nome')
                if comp_name and comp_name not in teachers_map[staff_id]["componentes"]:
                    teachers_map[staff_id]["componentes"].append(comp_name)
    
    # Formata lista de professores
    teachers = []
    for teacher_data in teachers_map.values():
        componentes = teacher_data.pop("componentes", [])
        teacher_data["componente"] = ", ".join(componentes) if componentes else None
        teachers.append(teacher_data)
    
    # Busca alunos matriculados
    academic_year = class_doc.get('academic_year', datetime.now().year)
    enrollments = await db.enrollments.find(
        {"class_id": class_id, "status": "active", "academic_year": academic_year},
        {"_id": 0, "student_id": 1, "enrollment_number": 1, "student_series": 1}
    ).to_list(1000)
    
    student_ids = [e['student_id'] for e in enrollments]
    enrollment_map = {e['student_id']: {
        'enrollment_number': e.get('enrollment_number'),
        'student_series': e.get('student_series')
    } for e in enrollments}
    
    students_list = []
    if student_ids:
        students = await db.students.find(
            {"id": {"$in": student_ids}},
            {"_id": 0, "id": 1, "full_name": 1, "birth_date": 1, "guardian_name": 1, "guardian_phone": 1, "guardian_relationship": 1, "mother_name": 1, "mother_phone": 1, "father_name": 1, "father_phone": 1}
        ).sort("full_name", 1).to_list(1000)
        
        for student in students:
            # Determina responsável principal
            guardian_name = student.get('guardian_name') or student.get('mother_name') or student.get('father_name') or '-'
            guardian_phone = student.get('guardian_phone') or student.get('mother_phone') or student.get('father_phone') or ''
            
            enrollment_info = enrollment_map.get(student.get('id'), {})
            students_list.append({
                "id": student.get('id'),
                "full_name": student.get('full_name'),
                "enrollment_number": enrollment_info.get('enrollment_number'),
                "student_series": enrollment_info.get('student_series'),
                "birth_date": student.get('birth_date'),
                "guardian_name": guardian_name,
                "guardian_phone": guardian_phone
            })
    
    # Calcula contagem por série para turmas multisseriadas
    series_count = {}
    if class_doc.get('is_multi_grade') and class_doc.get('series'):
        for serie in class_doc.get('series', []):
            series_count[serie] = 0
        for student in students_list:
            serie = student.get('student_series')
            if serie and serie in series_count:
                series_count[serie] += 1
    
    return {
        "class": class_doc,
        "school": school,
        "teachers": teachers,
        "students": students_list,
        "total_students": len(students_list),
        "series_count": series_count if series_count else None
    }

@api_router.get("/classes/{class_id}/details/pdf")
async def get_class_details_pdf(class_id: str, request: Request):
    """
    Gera PDF com detalhes completos da turma
    """
    current_user = await AuthMiddleware.get_current_user(request)
    
    # Busca turma
    class_doc = await db.classes.find_one({"id": class_id}, {"_id": 0})
    if not class_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turma não encontrada"
        )
    
    # Busca escola
    school = await db.schools.find_one({"id": class_doc.get('school_id')}, {"_id": 0})
    if not school:
        school = {"name": "Escola Municipal"}
    
    # Busca mantenedora
    mantenedora = await db.mantenedora.find_one({}, {"_id": 0})
    
    # Busca professores alocados na turma
    alocacoes = await db.teacher_assignments.find(
        {"class_id": class_id},
        {"_id": 0}
    ).to_list(100)
    
    # Agrupa por professor para evitar duplicação
    teachers_map = {}
    for alocacao in alocacoes:
        staff_id = alocacao.get('staff_id')
        if staff_id not in teachers_map:
            staff = await db.staff.find_one(
                {"id": staff_id},
                {"_id": 0, "id": 1, "nome": 1, "full_name": 1, "celular": 1}
            )
            if staff:
                teachers_map[staff_id] = {
                    "nome": staff.get('nome') or staff.get('full_name'),
                    "celular": staff.get('celular'),
                    "componentes": []
                }
        
        # Adiciona componente se existir
        if staff_id in teachers_map and alocacao.get('course_id'):
            course = await db.courses.find_one(
                {"id": alocacao.get('course_id')},
                {"_id": 0, "name": 1, "nome": 1}
            )
            if course:
                comp_name = course.get('name') or course.get('nome')
                if comp_name and comp_name not in teachers_map[staff_id]["componentes"]:
                    teachers_map[staff_id]["componentes"].append(comp_name)
    
    # Formata lista de professores
    teachers = []
    for teacher_data in teachers_map.values():
        componentes = teacher_data.pop("componentes", [])
        teacher_data["componente"] = ", ".join(componentes) if componentes else None
        teachers.append(teacher_data)
    
    # Busca alunos matriculados
    academic_year = class_doc.get('academic_year', datetime.now().year)
    enrollments = await db.enrollments.find(
        {"class_id": class_id, "status": "active", "academic_year": academic_year},
        {"_id": 0, "student_id": 1}
    ).to_list(1000)
    
    student_ids = [e['student_id'] for e in enrollments]
    
    students_list = []
    if student_ids:
        students = await db.students.find(
            {"id": {"$in": student_ids}},
            {"_id": 0, "id": 1, "full_name": 1, "birth_date": 1, "guardian_name": 1, "guardian_phone": 1, "mother_name": 1, "mother_phone": 1, "father_name": 1, "father_phone": 1}
        ).sort("full_name", 1).to_list(1000)
        
        for student in students:
            guardian_name = student.get('guardian_name') or student.get('mother_name') or student.get('father_name') or '-'
            guardian_phone = student.get('guardian_phone') or student.get('mother_phone') or student.get('father_phone') or ''
            
            students_list.append({
                "full_name": student.get('full_name'),
                "birth_date": student.get('birth_date'),
                "guardian_name": guardian_name,
                "guardian_phone": guardian_phone
            })
    
    try:
        pdf_buffer = generate_class_details_pdf(
            class_info=class_doc,
            school=school,
            teachers=teachers,
            students=students_list,
            mantenedora=mantenedora
        )
        
        class_name = class_doc.get('name', 'turma').replace(' ', '_')
        filename = f"Detalhes_Turma_{class_name}_{academic_year}.pdf"
        
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"'
            }
        )
    except Exception as e:
        logger.error(f"Erro ao gerar PDF de detalhes da turma: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")

# ============= COURSE (COMPONENTE CURRICULAR) ROUTES - MOVIDO PARA routers/courses.py =============

# ============= STUDENT (ALUNO) ROUTES =============

@api_router.post("/students", response_model=Student, status_code=status.HTTP_201_CREATED)
async def create_student(student_data: StudentCreate, request: Request):
    """Cria novo aluno"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
    
    # Verifica acesso à escola
    await AuthMiddleware.verify_school_access(request, student_data.school_id)
    
    student_obj = Student(**student_data.model_dump())
    doc = student_obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    
    await db.students.insert_one(doc)
    
    # Registra auditoria
    school = await db.schools.find_one({"id": student_data.school_id}, {"_id": 0, "name": 1})
    await audit_service.log(
        action='create',
        collection='students',
        user=current_user,
        request=request,
        document_id=student_obj.id,
        description=f"Cadastrou aluno: {student_obj.full_name}",
        school_id=student_data.school_id,
        school_name=school.get('name') if school else None,
        new_value={'full_name': student_obj.full_name, 'cpf': student_obj.cpf, 'class_id': student_obj.class_id}
    )
    
    return student_obj

@api_router.get("/students/{student_id}", response_model=Student)
async def get_student(student_id: str, request: Request):
    """Busca aluno por ID"""
    current_user = await AuthMiddleware.get_current_user(request)
    student_doc = await db.students.find_one({"id": student_id}, {"_id": 0})
    
    if not student_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aluno não encontrado"
        )
    
    # Verifica acesso à escola do aluno
    await AuthMiddleware.verify_school_access(request, student_doc['school_id'])
    
    return Student(**student_doc)

@api_router.put("/students/{student_id}", response_model=Student)
async def update_student(student_id: str, student_update: StudentUpdate, request: Request):
    """
    Atualiza aluno com suporte a:
    - Edição de dados básicos
    - Remanejamento (mudança de turma na mesma escola)
    - Preparação para transferência (mudança de status)
    
    NOTA: Coordenadores NÃO podem editar alunos (apenas visualizar).
    """
    # Coordenador não pode editar alunos - apenas visualizar
    current_user = await AuthMiddleware.require_roles_with_coordinator_edit(
        ['admin', 'secretario', 'coordenador'], 
        'students'
    )(request)
    
    # Busca aluno
    student_doc = await db.students.find_one({"id": student_id}, {"_id": 0})
    if not student_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aluno não encontrado"
        )
    
    # Verifica se o usuário tem acesso à escola do aluno
    user_school_ids = current_user.get('school_ids', [])
    current_school_id = student_doc.get('school_id')
    student_status = student_doc.get('status', '')
    
    # Admin tem acesso total
    if current_user.get('role') == 'admin':
        pass  # Admin pode editar qualquer aluno
    # Secretário: pode editar alunos ATIVOS da sua escola OU alunos NÃO ATIVOS de qualquer escola
    elif current_user.get('role') == 'secretario':
        is_active = student_status in ['active', 'Ativo']
        is_from_user_school = current_school_id in user_school_ids if current_school_id else False
        
        # Se o aluno está ATIVO, só pode editar se for da escola do secretário
        if is_active and not is_from_user_school:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você só pode editar alunos ativos da sua escola"
            )
        # Se não está ativo, pode editar de qualquer escola (ok, não precisa validar)
    # SEMED e outros roles com acesso limitado
    elif current_user.get('role') not in ['semed']:
        if current_school_id and current_school_id not in user_school_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você não tem permissão para editar alunos desta escola"
            )
    
    update_data = student_update.model_dump(exclude_unset=True)
    
    if not update_data:
        return Student(**student_doc)
    
    # Detecta tipo de operação
    old_class_id = student_doc.get('class_id')
    old_school_id = student_doc.get('school_id')
    old_status = student_doc.get('status')
    new_class_id = update_data.get('class_id', old_class_id)
    new_school_id = update_data.get('school_id', old_school_id)
    new_status = update_data.get('status', old_status)
    
    action_type = 'edicao'
    history_obs = None
    
    # Verifica se é mudança de turma (remanejamento)
    if new_class_id and new_class_id != old_class_id and new_school_id == old_school_id:
        action_type = 'remanejamento'
        
        # Atualiza matrícula ativa
        academic_year = datetime.now().year
        await db.enrollments.update_one(
            {"student_id": student_id, "school_id": old_school_id, "status": "active", "academic_year": academic_year},
            {"$set": {"class_id": new_class_id}}
        )
        
        # Busca nome da nova turma
        new_class = await db.classes.find_one({"id": new_class_id}, {"_id": 0, "name": 1})
        history_obs = f"Remanejado para turma: {new_class.get('name') if new_class else new_class_id}"
    
    # Verifica se é mudança de status para transferência
    if new_status != old_status:
        if new_status == 'transferred':
            action_type = 'transferencia_saida'
            history_obs = "Aluno marcado para transferência"
            
            # Atualiza matrícula para transferida
            await db.enrollments.update_many(
                {"student_id": student_id, "status": "active"},
                {"$set": {"status": "transferred"}}
            )
    
    # Atualiza o aluno
    await db.students.update_one(
        {"id": student_id},
        {"$set": update_data}
    )
    
    # Busca dados para o histórico
    school = await db.schools.find_one({"id": new_school_id or old_school_id}, {"_id": 0, "name": 1})
    class_info = await db.classes.find_one({"id": new_class_id or old_class_id}, {"_id": 0, "name": 1})
    
    # Registra no histórico
    history_entry = {
        "id": str(uuid.uuid4()),
        "student_id": student_id,
        "school_id": new_school_id or old_school_id,
        "school_name": school.get('name') if school else 'N/A',
        "class_id": new_class_id or old_class_id,
        "class_name": class_info.get('name') if class_info else 'N/A',
        "action_type": action_type,
        "previous_status": old_status,
        "new_status": new_status,
        "observations": history_obs,
        "user_id": current_user.get('id'),
        "user_name": current_user.get('full_name') or current_user.get('email'),
        "action_date": datetime.now(timezone.utc).isoformat()
    }
    
    await db.student_history.insert_one(history_entry)
    
    # Registra auditoria
    await audit_service.log(
        action='update',
        collection='students',
        user=current_user,
        request=request,
        document_id=student_id,
        description=f"Atualizou aluno: {student_doc.get('full_name')} - {action_type}",
        school_id=new_school_id or old_school_id,
        school_name=school.get('name') if school else None,
        old_value={'class_id': old_class_id, 'school_id': old_school_id, 'status': old_status},
        new_value={'class_id': new_class_id, 'school_id': new_school_id, 'status': new_status},
        extra_data={'action_type': action_type, 'observations': history_obs}
    )
    
    updated_student = await db.students.find_one({"id": student_id}, {"_id": 0})
    return Student(**updated_student)

@api_router.post("/students/{student_id}/transfer")
async def transfer_student(student_id: str, request: Request):
    """
    Transfere aluno para outra escola.
    Requer que o aluno esteja com status 'transferred' na escola de origem.
    """
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
    body = await request.json()
    new_school_id = body.get('school_id')
    new_class_id = body.get('class_id')
    academic_year = body.get('academic_year', datetime.now().year)
    
    if not new_school_id or not new_class_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="school_id e class_id são obrigatórios"
        )
    
    # Busca aluno
    student = await db.students.find_one({"id": student_id}, {"_id": 0})
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aluno não encontrado"
        )
    
    # Verifica se aluno está marcado como transferido
    if student.get('status') != 'transferred':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O aluno precisa estar com status 'Transferido' na escola de origem para ser matriculado em outra escola"
        )
    
    # Verifica se a escola de destino é diferente da atual
    if student.get('school_id') == new_school_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A escola de destino deve ser diferente da escola atual. Para mudança de turma na mesma escola, use o remanejamento."
        )
    
    # Busca informações da nova escola e turma
    new_school = await db.schools.find_one({"id": new_school_id}, {"_id": 0, "name": 1})
    new_class = await db.classes.find_one({"id": new_class_id}, {"_id": 0, "name": 1})
    
    if not new_school or not new_class:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escola ou turma de destino não encontrada"
        )
    
    # Gera número de matrícula
    last_enrollment = await db.enrollments.find_one(
        {"academic_year": academic_year},
        sort=[("enrollment_number", -1)]
    )
    if last_enrollment and last_enrollment.get('enrollment_number'):
        try:
            last_num = int(str(last_enrollment['enrollment_number'])[-5:])
            new_enrollment_number = f"{academic_year}{str(last_num + 1).zfill(5)}"
        except:
            new_enrollment_number = f"{academic_year}00001"
    else:
        new_enrollment_number = f"{academic_year}00001"
    
    # Cria nova matrícula
    enrollment_id = str(uuid.uuid4())
    new_enrollment = {
        "id": enrollment_id,
        "student_id": student_id,
        "school_id": new_school_id,
        "class_id": new_class_id,
        "academic_year": academic_year,
        "enrollment_number": new_enrollment_number,
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.enrollments.insert_one(new_enrollment)
    
    # Atualiza dados do aluno
    old_school_id = student.get('school_id')
    old_class_id = student.get('class_id')
    
    await db.students.update_one(
        {"id": student_id},
        {"$set": {
            "school_id": new_school_id,
            "class_id": new_class_id,
            "status": "active"
        }}
    )
    
    # Registra no histórico
    history_entry = {
        "id": str(uuid.uuid4()),
        "student_id": student_id,
        "school_id": new_school_id,
        "school_name": new_school.get('name'),
        "class_id": new_class_id,
        "class_name": new_class.get('name'),
        "enrollment_id": enrollment_id,
        "action_type": "transferencia_entrada",
        "previous_status": "transferred",
        "new_status": "active",
        "observations": f"Transferido da escola anterior. Nova matrícula: {new_enrollment_number}",
        "user_id": current_user.get('id'),
        "user_name": current_user.get('full_name') or current_user.get('email'),
        "action_date": datetime.now(timezone.utc).isoformat()
    }
    
    await db.student_history.insert_one(history_entry)
    
    updated_student = await db.students.find_one({"id": student_id}, {"_id": 0})
    return {
        "message": "Aluno transferido com sucesso",
        "student": updated_student,
        "enrollment": new_enrollment
    }

@api_router.delete("/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_student(student_id: str, request: Request):
    """Deleta aluno"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
    
    # Busca aluno
    student_doc = await db.students.find_one({"id": student_id}, {"_id": 0})
    if not student_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aluno não encontrado"
        )
    
    # Verifica acesso
    await AuthMiddleware.verify_school_access(request, student_doc['school_id'])
    
    result = await db.students.delete_one({"id": student_id})
    
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aluno não encontrado"
        )
    
    # Registra auditoria (CRÍTICO - exclusão de aluno)
    school = await db.schools.find_one({"id": student_doc.get('school_id')}, {"_id": 0, "name": 1})
    await audit_service.log(
        action='delete',
        collection='students',
        user=current_user,
        request=request,
        document_id=student_id,
        description=f"EXCLUIU aluno: {student_doc.get('full_name')} (CPF: {student_doc.get('cpf', 'N/A')})",
        school_id=student_doc.get('school_id'),
        school_name=school.get('name') if school else None,
        old_value={'full_name': student_doc.get('full_name'), 'cpf': student_doc.get('cpf'), 'class_id': student_doc.get('class_id')}
    )
    
    return None

# ============= GUARDIAN (RESPONSÁVEL) ROUTES - MOVIDO PARA routers/guardians.py =============

# ============= ENROLLMENT (MATRÍCULA) ROUTES - MOVIDO PARA routers/enrollments.py =============

# ============= GRADES ROUTES =============

@api_router.post("/grades/batch")
async def update_grades_batch(request: Request, grades: List[dict]):
    """Atualiza notas em lote (por turma)"""
    # Coordenador PODE editar notas (área do diário)
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'professor', 'coordenador'])(request)
    user_role = current_user.get('role', '')
    # Verifica se o ano letivo está aberto (apenas para não-admins)
    if grades and user_role != 'admin':
        first_grade = grades[0]
        class_doc = await db.classes.find_one(
            {"id": first_grade['class_id']},
            {"_id": 0, "school_id": 1}
        )
        if class_doc:
            await verify_academic_year_open_or_raise(
                class_doc['school_id'],
                first_grade['academic_year']
            )
    
    # Verifica a data limite de edição por bimestre (apenas para não-admins e não-secretarios)
    if grades and user_role not in ['admin', 'secretario']:
        first_grade = grades[0]
        academic_year = first_grade.get('academic_year')
        
        # Identifica quais bimestres estão sendo editados
        bimestres_editados = set()
        for grade_data in grades:
            for bim in ['b1', 'b2', 'b3', 'b4']:
                if grade_data.get(bim) is not None:
                    bimestres_editados.add(int(bim[1]))  # Extrai o número do bimestre
        
        # Verifica cada bimestre sendo editado
        for bimestre in bimestres_editados:
            await verify_bimestre_edit_deadline_or_raise(academic_year, bimestre, user_role)
    
    results = []
    audit_changes = []  # Para acumular mudanças para auditoria
    
    for grade_data in grades:
        # Verifica se já existe
        existing = await db.grades.find_one({
            "student_id": grade_data['student_id'],
            "class_id": grade_data['class_id'],
            "course_id": grade_data['course_id'],
            "academic_year": grade_data['academic_year']
        }, {"_id": 0})
        
        if existing:
            # Atualiza
            update_fields = {k: v for k, v in grade_data.items() 
                          if k in ['b1', 'b2', 'b3', 'b4', 'rec_s1', 'rec_s2', 'recovery', 'observations'] and v is not None}
            update_fields['updated_at'] = datetime.now(timezone.utc).isoformat()
            
            # Guarda valor antigo para auditoria
            old_values = {k: existing.get(k) for k in update_fields.keys() if k != 'updated_at'}
            new_values = {k: v for k, v in update_fields.items() if k != 'updated_at'}
            
            await db.grades.update_one(
                {"id": existing['id']},
                {"$set": update_fields}
            )
            
            updated = await calculate_and_update_grade(db, existing['id'])
            results.append(updated)
            
            # Registra alteração para auditoria
            if old_values != new_values:
                audit_changes.append({
                    'student_id': grade_data['student_id'],
                    'grade_id': existing['id'],
                    'old': old_values,
                    'new': new_values
                })
        else:
            # Cria novo
            new_grade = {
                'id': str(uuid.uuid4()),
                'student_id': grade_data['student_id'],
                'class_id': grade_data['class_id'],
                'course_id': grade_data['course_id'],
                'academic_year': grade_data['academic_year'],
                'b1': grade_data.get('b1'),
                'b2': grade_data.get('b2'),
                'b3': grade_data.get('b3'),
                'b4': grade_data.get('b4'),
                'rec_s1': grade_data.get('rec_s1'),
                'rec_s2': grade_data.get('rec_s2'),
                'recovery': grade_data.get('recovery'),
                'observations': grade_data.get('observations'),
                'final_average': None,
                'status': 'cursando',
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            
            await db.grades.insert_one(new_grade)
            updated = await calculate_and_update_grade(db, new_grade['id'])
            results.append(updated)
            
            # Registra criação para auditoria
            audit_changes.append({
                'student_id': grade_data['student_id'],
                'grade_id': new_grade['id'],
                'action': 'create',
                'new': {k: v for k, v in new_grade.items() if k in ['b1', 'b2', 'b3', 'b4', 'rec_s1', 'rec_s2']}
            })
    
    # Registra auditoria em lote
    if audit_changes:
        # Busca informações da turma para contexto
        class_info = None
        school_id = None
        if grades:
            class_info = await db.classes.find_one(
                {"id": grades[0].get('class_id')},
                {"_id": 0, "name": 1, "school_id": 1}
            )
            school_id = class_info.get('school_id') if class_info else None
        
        await audit_service.log(
            action='update',
            collection='grades',
            user=current_user,
            request=request,
            description=f"Atualizou notas de {len(audit_changes)} aluno(s) da turma {class_info.get('name', 'N/A') if class_info else 'N/A'}",
            school_id=school_id,
            academic_year=grades[0].get('academic_year') if grades else None,
            extra_data={'changes': audit_changes[:10]}  # Limita para não sobrecarregar
        )
    
    return {"updated": len(results), "grades": results}

@api_router.delete("/grades/{grade_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_grade(grade_id: str, request: Request):
    """Remove uma nota"""
    current_user = await AuthMiddleware.require_roles(['admin'])(request)
    
    result = await db.grades.delete_one({"id": grade_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Nota não encontrada")
    
    return None

# ============= FILE UPLOAD ROUTES =============

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.pdf', '.doc', '.docx'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

# PATCH 1.3: Rota de upload restrita a roles autorizados
@api_router.post("/upload")
async def upload_file(
    request: Request, 
    file: UploadFile = File(...), 
    file_type: Optional[str] = "default"
):
    """Upload de arquivo (foto, documento, laudo, etc.) para servidor externo via FTP - RESTRITO"""
    # Apenas roles autorizados podem fazer upload
    current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario', 'diretor', 'coordenador'])(request)
    
    # Verifica extensão
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de arquivo não permitido. Permitidos: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Verifica tamanho (lendo em chunks)
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Arquivo muito grande. Máximo: 5MB"
        )
    
    # Faz upload via FTP para servidor externo
    success, result, filename = upload_to_ftp(content, file.filename, file_type)
    
    if not success:
        # Fallback: salva localmente se FTP falhar
        logger.warning(f"Upload FTP falhou, salvando localmente: {result}")
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = UPLOADS_DIR / unique_filename
        
        with open(file_path, "wb") as buffer:
            buffer.write(content)
        
        file_url = f"/api/uploads/{unique_filename}"
        
        return {
            "filename": unique_filename,
            "original_name": file.filename,
            "url": file_url,
            "size": len(content),
            "storage": "local"
        }
    
    # Retorna URL do servidor externo
    return {
        "filename": filename,
        "original_name": file.filename,
        "url": result,  # URL completa do servidor externo
        "size": len(content),
        "storage": "external"
    }

@api_router.delete("/upload/{filename}")
async def delete_file(filename: str, request: Request):
    """Remove arquivo enviado"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
    
    file_path = UPLOADS_DIR / filename
    
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo não encontrado"
        )
    
    file_path.unlink()
    
    return {"message": "Arquivo removido com sucesso"}

@api_router.get("/uploads/{filename}")
async def serve_uploaded_file(filename: str):
    """Serve arquivos de upload com o content-type correto"""
    import mimetypes
    
    file_path = UPLOADS_DIR / filename
    
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo não encontrado"
        )
    
    # Detecta o tipo MIME com base na extensão
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if not mime_type:
        mime_type = "application/octet-stream"
    
    return FileResponse(
        path=str(file_path),
        media_type=mime_type,
        filename=filename
    )

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

# ============= SANDBOX (MODO TESTE) =============

@api_router.get("/sandbox/status")
async def get_sandbox_status(request: Request):
    """Retorna o status do banco sandbox (apenas admin)"""
    current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste'])(request)
    return sandbox_service.get_status()

@api_router.post("/sandbox/reset")
async def reset_sandbox_manual(request: Request):
    """Reseta o banco sandbox manualmente (apenas admin)"""
    current_user = await AuthMiddleware.require_roles(['admin'])(request)
    result = await sandbox_service.reset_sandbox()
    if not result.get('success'):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get('error', 'Erro ao resetar sandbox')
        )
    return result

# ============= CALENDAR EVENTS =============

# Cores padrão para cada tipo de evento
EVENT_COLORS = {
    'feriado_nacional': '#EF4444',  # Vermelho
    'feriado_estadual': '#F97316',  # Laranja
    'feriado_municipal': '#EAB308',  # Amarelo
    'sabado_letivo': '#22C55E',  # Verde
    'recesso_escolar': '#3B82F6',  # Azul
    'evento_escolar': '#8B5CF6',  # Roxo
    'outros': '#6B7280'  # Cinza
}

@api_router.get("/calendar/check-date/{date}")
async def check_calendar_date(date: str, request: Request):
    """
    Verifica se uma data específica é dia letivo ou não.
    Retorna informações sobre eventos nessa data.
    """
    await AuthMiddleware.get_current_user(request)
    # Busca eventos que incluem essa data
    events = await db.calendar_events.find({
        "start_date": {"$lte": date},
        "end_date": {"$gte": date}
    }, {"_id": 0}).to_list(100)
    
    # Determina se é dia letivo
    is_school_day = True  # Por padrão é dia letivo
    blocking_events = []
    enabling_events = []
    
    for event in events:
        if event.get('is_school_day'):
            enabling_events.append(event)
        else:
            blocking_events.append(event)
            is_school_day = False
    
    # Se há sábado letivo habilitando, considera letivo
    for event in enabling_events:
        if event.get('event_type') == 'sabado_letivo':
            is_school_day = True
            break
    
    return {
        "date": date,
        "is_school_day": is_school_day,
        "events": events,
        "blocking_events": blocking_events,
        "enabling_events": enabling_events
    }

@api_router.get("/calendar/summary/{academic_year}")
async def get_calendar_summary(academic_year: int, request: Request):
    """
    Retorna resumo do calendário letivo para um ano.
    Conta dias letivos, feriados, etc.
    """
    await AuthMiddleware.get_current_user(request)
    
    events = await db.calendar_events.find(
        {"academic_year": academic_year}, 
        {"_id": 0}
    ).to_list(1000)
    
    summary = {
        "academic_year": academic_year,
        "total_events": len(events),
        "by_type": {},
        "school_days_added": 0,  # Sábados letivos
        "non_school_days": 0  # Feriados/Recessos
    }
    
    for event in events:
        event_type = event.get('event_type', 'outros')
        if event_type not in summary["by_type"]:
            summary["by_type"][event_type] = 0
        summary["by_type"][event_type] += 1
        
        if event.get('is_school_day'):
            summary["school_days_added"] += 1
        else:
            summary["non_school_days"] += 1
    
    return summary

# ============= CALENDÁRIO LETIVO - PERÍODOS BIMESTRAIS =============

@api_router.get("/calendario-letivo/{ano_letivo}")
async def get_calendario_letivo(ano_letivo: int, request: Request, school_id: Optional[str] = None):
    """
    Obtém a configuração do calendário letivo com os períodos bimestrais.
    Se school_id for fornecido, busca configuração específica da escola.
    """
    await AuthMiddleware.get_current_user(request)
    
    query = {"ano_letivo": ano_letivo}
    if school_id:
        query["school_id"] = school_id
    else:
        query["school_id"] = None  # Configuração global
    
    calendario = await db.calendario_letivo.find_one(query, {"_id": 0})
    
    if not calendario:
        # Retorna configuração padrão vazia
        return {
            "ano_letivo": ano_letivo,
            "school_id": school_id,
            "bimestre_1_inicio": None,
            "bimestre_1_fim": None,
            "bimestre_2_inicio": None,
            "bimestre_2_fim": None,
            "bimestre_3_inicio": None,
            "bimestre_3_fim": None,
            "bimestre_4_inicio": None,
            "bimestre_4_fim": None,
            "recesso_inicio": None,
            "recesso_fim": None,
            "dias_letivos_previstos": 200
        }
    
    return calendario

@api_router.get("/calendario-letivo/{ano_letivo}/dias-letivos")
async def calcular_dias_letivos(ano_letivo: int, request: Request, school_id: Optional[str] = None):
    """
    Calcula automaticamente os dias letivos de cada bimestre com base em:
    - Datas de início e fim de cada bimestre
    - Eventos do calendário (feriados, recessos, sábados letivos)
    
    Dias letivos = dias úteis (seg-sex) - feriados - recessos + sábados letivos
    """
    await AuthMiddleware.get_current_user(request)
    
    # Buscar configuração do calendário letivo
    query = {"ano_letivo": ano_letivo}
    if school_id:
        query["school_id"] = school_id
    else:
        query["school_id"] = None
    
    calendario = await db.calendario_letivo.find_one(query, {"_id": 0})
    
    if not calendario:
        return {
            "bimestre_1_dias_letivos": 0,
            "bimestre_2_dias_letivos": 0,
            "bimestre_3_dias_letivos": 0,
            "bimestre_4_dias_letivos": 0,
            "total_dias_letivos": 0
        }
    
    # Buscar todos os eventos do ano
    events = await db.calendar_events.find({
        "academic_year": ano_letivo
    }, {"_id": 0}).to_list(1000)
    
    # Tipos de eventos que REMOVEM dias letivos
    eventos_nao_letivos = ['feriado_nacional', 'feriado_estadual', 'feriado_municipal', 'recesso_escolar']
    
    # Criar set de datas não letivas
    datas_nao_letivas = set()
    datas_sabados_letivos = set()
    
    for event in events:
        event_type = event.get('event_type', '')
        start_date_str = event.get('start_date')
        end_date_str = event.get('end_date') or start_date_str
        
        if not start_date_str:
            continue
        
        try:
            start_date = datetime.strptime(start_date_str[:10], '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str[:10], '%Y-%m-%d').date()
            
            # Iterar por todas as datas do evento
            current = start_date
            while current <= end_date:
                if event_type in eventos_nao_letivos:
                    datas_nao_letivas.add(current)
                # Sábado letivo: tipo sabado_letivo OU qualquer evento com is_school_day=True em sábado
                elif event_type == 'sabado_letivo':
                    datas_sabados_letivos.add(current)
                elif event.get('is_school_day', False) and current.weekday() == 5:  # Sábado
                    datas_sabados_letivos.add(current)
                current += timedelta(days=1)
        except (ValueError, TypeError):
            continue
    
    def calcular_dias_letivos_periodo(inicio_str, fim_str):
        """Calcula dias letivos entre duas datas"""
        if not inicio_str or not fim_str:
            return 0
        
        try:
            inicio = datetime.strptime(inicio_str[:10], '%Y-%m-%d').date()
            fim = datetime.strptime(fim_str[:10], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return 0
        
        dias_letivos = 0
        current = inicio
        
        while current <= fim:
            dia_semana = current.weekday()  # 0=segunda, 6=domingo
            
            # Verificar se é dia letivo
            if dia_semana < 5:  # Segunda a sexta
                if current not in datas_nao_letivas:
                    dias_letivos += 1
            elif dia_semana == 5:  # Sábado
                if current in datas_sabados_letivos:
                    dias_letivos += 1
            # Domingo nunca é letivo
            
            current += timedelta(days=1)
        
        return dias_letivos
    
    # Calcular dias letivos de cada bimestre
    b1 = calcular_dias_letivos_periodo(
        calendario.get('bimestre_1_inicio'),
        calendario.get('bimestre_1_fim')
    )
    b2 = calcular_dias_letivos_periodo(
        calendario.get('bimestre_2_inicio'),
        calendario.get('bimestre_2_fim')
    )
    b3 = calcular_dias_letivos_periodo(
        calendario.get('bimestre_3_inicio'),
        calendario.get('bimestre_3_fim')
    )
    b4 = calcular_dias_letivos_periodo(
        calendario.get('bimestre_4_inicio'),
        calendario.get('bimestre_4_fim')
    )
    
    return {
        "bimestre_1_dias_letivos": b1,
        "bimestre_2_dias_letivos": b2,
        "bimestre_3_dias_letivos": b3,
        "bimestre_4_dias_letivos": b4,
        "total_dias_letivos": b1 + b2 + b3 + b4
    }

@api_router.put("/calendario-letivo/{ano_letivo}")
async def update_calendario_letivo(ano_letivo: int, request: Request, school_id: Optional[str] = None):
    """
    Cria ou atualiza a configuração do calendário letivo.
    """
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'semed'])(request)
    
    body = await request.json()
    
    query = {"ano_letivo": ano_letivo}
    if school_id:
        query["school_id"] = school_id
    else:
        query["school_id"] = None
    
    existing = await db.calendario_letivo.find_one(query)
    
    update_data = {
        "bimestre_1_inicio": body.get("bimestre_1_inicio"),
        "bimestre_1_fim": body.get("bimestre_1_fim"),
        "bimestre_1_data_limite": body.get("bimestre_1_data_limite"),
        "bimestre_2_inicio": body.get("bimestre_2_inicio"),
        "bimestre_2_fim": body.get("bimestre_2_fim"),
        "bimestre_2_data_limite": body.get("bimestre_2_data_limite"),
        "bimestre_3_inicio": body.get("bimestre_3_inicio"),
        "bimestre_3_fim": body.get("bimestre_3_fim"),
        "bimestre_3_data_limite": body.get("bimestre_3_data_limite"),
        "bimestre_4_inicio": body.get("bimestre_4_inicio"),
        "bimestre_4_fim": body.get("bimestre_4_fim"),
        "bimestre_4_data_limite": body.get("bimestre_4_data_limite"),
        "recesso_inicio": body.get("recesso_inicio"),
        "recesso_fim": body.get("recesso_fim"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": current_user['id']
    }
    
    if existing:
        await db.calendario_letivo.update_one(query, {"$set": update_data})
    else:
        new_calendario = {
            "id": str(uuid.uuid4()),
            "ano_letivo": ano_letivo,
            "school_id": school_id,
            **update_data,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.calendario_letivo.insert_one(new_calendario)
    
    return await db.calendario_letivo.find_one(query, {"_id": 0})

@api_router.get("/calendario-letivo/{ano_letivo}/periodos")
async def get_periodos_bimestrais(ano_letivo: int, request: Request, school_id: Optional[str] = None):
    """
    Retorna os períodos bimestrais formatados de forma simplificada.
    """
    await AuthMiddleware.get_current_user(request)
    
    query = {"ano_letivo": ano_letivo}
    if school_id:
        query["school_id"] = school_id
    else:
        query["school_id"] = None
    
    calendario = await db.calendario_letivo.find_one(query, {"_id": 0})
    
    periodos = []
    if calendario:
        for i in range(1, 5):
            inicio = calendario.get(f"bimestre_{i}_inicio")
            fim = calendario.get(f"bimestre_{i}_fim")
            if inicio and fim:
                periodos.append({
                    "bimestre": i,
                    "nome": f"{i}º Bimestre",
                    "data_inicio": inicio,
                    "data_fim": fim
                })
    
    return {
        "ano_letivo": ano_letivo,
        "periodos": periodos,
        "recesso": {
            "inicio": calendario.get("recesso_inicio") if calendario else None,
            "fim": calendario.get("recesso_fim") if calendario else None
        } if calendario else None
    }

@api_router.get("/calendario-letivo/{ano_letivo}/status-edicao")
async def get_edit_status(ano_letivo: int, request: Request, bimestre: Optional[int] = None):
    """
    Verifica o status de edição para o ano letivo.
    Retorna se cada bimestre está aberto ou fechado para edição.
    """
    current_user = await AuthMiddleware.get_current_user(request)
    user_role = current_user.get('role', '')
    
    # Buscar calendário para obter as datas limite configuradas
    calendario = await db.calendario_letivo.find_one(
        {"ano_letivo": ano_letivo},
        {"_id": 0}
    )
    
    # Admin e secretário sempre podem editar, mas devem ver as datas limite
    if user_role in ['admin', 'secretario']:
        bimestres_status = []
        for i in range(1, 5):
            data_limite = calendario.get(f"bimestre_{i}_data_limite") if calendario else None
            bimestres_status.append({
                "bimestre": i, 
                "pode_editar": True, 
                "data_limite": data_limite, 
                "motivo": "Permissão administrativa"
            })
        
        return {
            "ano_letivo": ano_letivo,
            "pode_editar_todos": True,
            "motivo": "Usuário com permissão de administração",
            "bimestres": bimestres_status
        }
    
    check = await check_bimestre_edit_deadline(ano_letivo, bimestre)
    
    if bimestre:
        return {
            "ano_letivo": ano_letivo,
            "bimestre": bimestre,
            "pode_editar": check["can_edit"],
            "data_limite": check["data_limite"],
            "motivo": check["message"]
        }
    
    # Retorna status de todos os bimestres
    # (calendário já foi buscado no início da função)
    
    from datetime import date
    today = date.today().isoformat()
    
    bimestres_status = []
    for i in range(1, 5):
        data_limite = calendario.get(f"bimestre_{i}_data_limite") if calendario else None
        pode_editar = True
        motivo = "Dentro do prazo"
        
        if data_limite and today > data_limite:
            pode_editar = False
            motivo = f"Prazo encerrado em {data_limite}"
        elif not data_limite:
            motivo = "Sem data limite configurada"
        
        bimestres_status.append({
            "bimestre": i,
            "pode_editar": pode_editar,
            "data_limite": data_limite,
            "motivo": motivo
        })
    
    return {
        "ano_letivo": ano_letivo,
        "pode_editar_todos": all(b["pode_editar"] for b in bimestres_status),
        "bimestres": bimestres_status
    }

# ============= ATTENDANCE (FREQUÊNCIA) =============

@api_router.delete("/attendance/{attendance_id}")
async def delete_attendance(attendance_id: str, request: Request):
    """Remove um registro de frequência"""
    # Coordenador PODE editar frequência (área do diário)
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'professor', 'coordenador'])(request)
    # Verifica se existe
    existing = await db.attendance.find_one({"id": attendance_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Registro de frequência não encontrado")
    
    # Guarda dados para auditoria antes de deletar
    class_info = await db.classes.find_one({"id": existing.get('class_id')}, {"_id": 0, "name": 1, "school_id": 1})
    
    # Remove o registro
    result = await db.attendance.delete_one({"id": attendance_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Erro ao remover frequência")
    
    # Auditoria de exclusão
    await audit_service.log(
        action='delete',
        collection='attendance',
        user=current_user,
        request=request,
        document_id=attendance_id,
        description=f"EXCLUIU frequência da turma {class_info.get('name', 'N/A')} de {existing.get('date')}",
        school_id=class_info.get('school_id') if class_info else None,
        academic_year=existing.get('academic_year'),
        old_value={'date': existing.get('date'), 'records_count': len(existing.get('records', []))}
    )
    
    return {"message": "Frequência removida com sucesso"}

@api_router.get("/attendance/report/student/{student_id}")
async def get_student_attendance_report(
    student_id: str,
    request: Request,
    academic_year: Optional[int] = None
):
    """Relatório de frequência de um aluno"""
    await AuthMiddleware.get_current_user(request)
    
    if not academic_year:
        academic_year = datetime.now().year
    
    # Busca dados do aluno
    student = await db.students.find_one({"id": student_id}, {"_id": 0})
    if not student:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    
    # Busca todas as frequências do aluno no ano
    attendances = await db.attendance.find(
        {
            "academic_year": academic_year,
            "records.student_id": student_id
        },
        {"_id": 0}
    ).sort("date", 1).to_list(1000)
    
    # Conta presenças, faltas e justificadas
    total_days = 0
    present = 0
    absent = 0
    justified = 0
    
    daily_records = []
    
    for att in attendances:
        for record in att.get('records', []):
            if record['student_id'] == student_id:
                total_days += 1
                if record['status'] == 'P':
                    present += 1
                elif record['status'] == 'F':
                    absent += 1
                elif record['status'] == 'J':
                    justified += 1
                
                daily_records.append({
                    "date": att['date'],
                    "status": record['status'],
                    "period": att.get('period', 'regular'),
                    "course_id": att.get('course_id')
                })
    
    # Calcula percentual (considera justificadas como presença para o cálculo)
    attendance_percentage = ((present + justified) / total_days * 100) if total_days > 0 else 0
    
    return {
        "student": student,
        "academic_year": academic_year,
        "summary": {
            "total_days": total_days,
            "present": present,
            "absent": absent,
            "justified": justified,
            "attendance_percentage": round(attendance_percentage, 1),
            "status": "regular" if attendance_percentage >= 75 else "alerta"
        },
        "daily_records": daily_records
    }

@api_router.get("/attendance/report/class/{class_id}")
async def get_class_attendance_report(
    class_id: str,
    request: Request,
    academic_year: Optional[int] = None
):
    """Relatório de frequência de uma turma"""
    await AuthMiddleware.get_current_user(request)
    
    if not academic_year:
        academic_year = datetime.now().year
    
    # Busca dados da turma
    turma = await db.classes.find_one({"id": class_id}, {"_id": 0})
    if not turma:
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    
    # Busca alunos matriculados na turma através da coleção enrollments
    enrollments = await db.enrollments.find(
        {"class_id": class_id, "status": "active", "academic_year": academic_year},
        {"_id": 0, "student_id": 1, "enrollment_number": 1}
    ).to_list(1000)
    
    student_ids = [e['student_id'] for e in enrollments]
    enrollment_numbers = {e['student_id']: e.get('enrollment_number') for e in enrollments}
    
    # Busca dados dos alunos matriculados
    students = []
    if student_ids:
        students = await db.students.find(
            {"id": {"$in": student_ids}},
            {"_id": 0, "id": 1, "full_name": 1, "enrollment_number": 1}
        ).sort("full_name", 1).to_list(1000)
    
    # Busca todas as frequências da turma no ano
    attendances = await db.attendance.find(
        {"class_id": class_id, "academic_year": academic_year},
        {"_id": 0}
    ).sort("date", 1).to_list(1000)
    
    # Conta total de dias letivos com frequência registrada
    unique_dates = set()
    for att in attendances:
        unique_dates.add(att['date'])
    
    total_school_days = len(unique_dates)
    
    # Calcula frequência de cada aluno
    student_stats = []
    low_attendance_alerts = []
    
    for student in students:
        present = 0
        absent = 0
        justified = 0
        
        for att in attendances:
            for record in att.get('records', []):
                if record['student_id'] == student['id']:
                    if record['status'] == 'P':
                        present += 1
                    elif record['status'] == 'F':
                        absent += 1
                    elif record['status'] == 'J':
                        justified += 1
        
        total = present + absent + justified
        percentage = ((present + justified) / total * 100) if total > 0 else 0
        
        stat = {
            "student_id": student['id'],
            "student_name": student['full_name'],
            "enrollment_number": enrollment_numbers.get(student['id']) or student.get('enrollment_number'),
            "present": present,
            "absent": absent,
            "justified": justified,
            "total_records": total,
            "attendance_percentage": round(percentage, 1),
            "status": "regular" if percentage >= 75 else "alerta"
        }
        
        student_stats.append(stat)
        
        if percentage < 75 and total > 0:
            low_attendance_alerts.append(stat)
    
    return {
        "class": turma,
        "academic_year": academic_year,
        "total_school_days_recorded": total_school_days,
        "total_students": len(students),
        "students": student_stats,
        "low_attendance_alerts": low_attendance_alerts,
        "alert_count": len(low_attendance_alerts)
    }

@api_router.get("/attendance/pdf/bimestre/{class_id}")
async def get_attendance_bimestre_pdf(
    class_id: str,
    request: Request,
    bimestre: int = Query(..., ge=1, le=4, description="Número do bimestre (1-4)"),
    academic_year: Optional[int] = None
):
    """Gera PDF do relatório de frequência por bimestre"""
    await AuthMiddleware.get_current_user(request)
    
    if not academic_year:
        academic_year = datetime.now().year
    
    # Busca dados da turma
    turma = await db.classes.find_one({"id": class_id}, {"_id": 0})
    if not turma:
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    
    # Busca escola
    school = await db.schools.find_one({"id": turma.get('school_id')}, {"_id": 0})
    if not school:
        raise HTTPException(status_code=404, detail="Escola não encontrada")
    
    # Buscar mantenedora
    mantenedora = await db.config.find_one({"tipo": "mantenedora"}, {"_id": 0})
    
    # Definir período do bimestre
    bimestre_periodos = {
        1: (f"{academic_year}-02-01", f"{academic_year}-04-30"),
        2: (f"{academic_year}-05-01", f"{academic_year}-07-15"),
        3: (f"{academic_year}-07-16", f"{academic_year}-09-30"),
        4: (f"{academic_year}-10-01", f"{academic_year}-12-20"),
    }
    
    period_start, period_end = bimestre_periodos.get(bimestre, (None, None))
    
    # Busca alunos matriculados na turma
    enrollments = await db.enrollments.find(
        {"class_id": class_id, "status": "active", "academic_year": academic_year},
        {"_id": 0, "student_id": 1, "enrollment_number": 1}
    ).to_list(1000)
    
    student_ids = [e['student_id'] for e in enrollments]
    enrollment_numbers = {e['student_id']: e.get('enrollment_number') for e in enrollments}
    
    # Busca dados dos alunos
    students = []
    if student_ids:
        students = await db.students.find(
            {"id": {"$in": student_ids}},
            {"_id": 0, "id": 1, "full_name": 1, "enrollment_number": 1}
        ).sort("full_name", 1).to_list(1000)
    
    # Busca frequências do período do bimestre
    attendances = await db.attendance.find(
        {
            "class_id": class_id,
            "academic_year": academic_year,
            "date": {"$gte": period_start, "$lte": period_end}
        },
        {"_id": 0}
    ).sort("date", 1).to_list(1000)
    
    # Coletar dias únicos com frequência registrada
    attendance_days = sorted(list(set([att['date'] for att in attendances])))
    
    # Montar dados de frequência por aluno
    students_attendance = []
    for student in students:
        attendance_by_date = {}
        
        for att in attendances:
            for record in att.get('records', []):
                if record['student_id'] == student['id']:
                    status_map = {'P': 'present', 'F': 'absent', 'J': 'justified'}
                    attendance_by_date[att['date']] = status_map.get(record['status'], '')
        
        students_attendance.append({
            'name': student['full_name'],
            'enrollment_number': enrollment_numbers.get(student['id']) or student.get('enrollment_number'),
            'attendance_by_date': attendance_by_date
        })
    
    # Buscar professor responsável (opcional)
    teacher_name = ""
    teacher_assignment = await db.teacher_assignments.find_one(
        {"class_id": class_id, "academic_year": academic_year},
        {"_id": 0, "staff_id": 1}
    )
    if teacher_assignment:
        teacher = await db.staff.find_one(
            {"id": teacher_assignment['staff_id']},
            {"_id": 0, "nome": 1}
        )
        if teacher:
            teacher_name = teacher.get('nome', '')
    
    # Gerar PDF
    try:
        pdf_buffer = generate_relatorio_frequencia_bimestre_pdf(
            school=school,
            class_info=turma,
            course_info=None,  # Frequência diária
            students_attendance=students_attendance,
            bimestre=bimestre,
            academic_year=academic_year,
            period_start=period_start,
            period_end=period_end,
            attendance_days=attendance_days,
            aulas_previstas=len(attendance_days),
            aulas_ministradas=len(attendance_days),
            teacher_name=teacher_name,
            mantenedora=mantenedora
        )
        
        filename = f"frequencia_{turma.get('name', 'turma')}_{bimestre}bim_{academic_year}.pdf"
        filename = filename.replace(' ', '_').replace('/', '-')
        
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename={filename}"}
        )
    except Exception as e:
        logger.error(f"Erro ao gerar PDF de frequência: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")

@api_router.get("/attendance/alerts")
async def get_attendance_alerts(
    request: Request,
    school_id: Optional[str] = None,
    academic_year: Optional[int] = None
):
    """Lista alunos com frequência abaixo de 75%"""
    await AuthMiddleware.get_current_user(request)
    
    if not academic_year:
        academic_year = datetime.now().year
    
    # Busca todas as turmas (opcionalmente filtrada por escola)
    class_query = {}
    if school_id:
        class_query["school_id"] = school_id
    
    classes = await db.classes.find(class_query, {"_id": 0}).to_list(1000)
    
    all_alerts = []
    
    for turma in classes:
        # Busca alunos matriculados na turma através da coleção enrollments
        enrollments = await db.enrollments.find(
            {"class_id": turma['id'], "status": "active", "academic_year": academic_year},
            {"_id": 0, "student_id": 1}
        ).to_list(1000)
        
        student_ids = [e['student_id'] for e in enrollments]
        
        # Busca dados dos alunos matriculados
        students = []
        if student_ids:
            students = await db.students.find(
                {"id": {"$in": student_ids}},
                {"_id": 0, "id": 1, "full_name": 1}
            ).to_list(1000)
        
        # Busca frequências da turma
        attendances = await db.attendance.find(
            {"class_id": turma['id'], "academic_year": academic_year},
            {"_id": 0}
        ).to_list(1000)
        
        for student in students:
            present = 0
            absent = 0
            justified = 0
            
            for att in attendances:
                for record in att.get('records', []):
                    if record['student_id'] == student['id']:
                        if record['status'] == 'P':
                            present += 1
                        elif record['status'] == 'F':
                            absent += 1
                        elif record['status'] == 'J':
                            justified += 1
            
            total = present + absent + justified
            if total > 0:
                percentage = ((present + justified) / total * 100)
                
                if percentage < 75:
                    all_alerts.append({
                        "student_id": student['id'],
                        "student_name": student['full_name'],
                        "class_id": turma['id'],
                        "class_name": turma.get('name'),
                        "school_id": turma.get('school_id'),
                        "attendance_percentage": round(percentage, 1),
                        "total_records": total,
                        "absent": absent
                    })
    
    # Ordena por percentual de frequência (menor primeiro)
    all_alerts.sort(key=lambda x: x['attendance_percentage'])
    
    return {
        "academic_year": academic_year,
        "total_alerts": len(all_alerts),
        "alerts": all_alerts
    }

# ============= STAFF (SERVIDORES) =============

@api_router.post("/staff/{staff_id}/photo")
async def upload_staff_photo(staff_id: str, request: Request, file: UploadFile = File(...)):
    """Upload de foto do servidor para servidor externo via FTP"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
    existing = await db.staff.find_one({"id": staff_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")
    
    # Validar tipo de arquivo
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Arquivo deve ser uma imagem")
    
    # Ler conteúdo do arquivo
    content = await file.read()
    
    # Upload via FTP
    success, result, filename = upload_to_ftp(content, file.filename, "staff")
    
    if success:
        foto_url = result  # URL completa do servidor externo
    else:
        # Fallback: salva localmente se FTP falhar
        logger.warning(f"Upload FTP falhou, salvando localmente: {result}")
        file_ext = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
        filename = f"staff_{staff_id}.{file_ext}"
        filepath = f"/app/backend/uploads/staff/{filename}"
        
        os.makedirs("/app/backend/uploads/staff", exist_ok=True)
        
        with open(filepath, "wb") as f:
            f.write(content)
        
        foto_url = f"/api/uploads/staff/{filename}"
    
    # Atualizar URL da foto no banco
    await db.staff.update_one(
        {"id": staff_id},
        {"$set": {"foto_url": foto_url, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {"foto_url": foto_url}

# ============= SCHOOL ASSIGNMENTS (LOTAÇÕES) =============

@api_router.get("/school-assignments")
async def list_school_assignments(
    request: Request, 
    school_id: Optional[str] = None, 
    staff_id: Optional[str] = None,
    status: Optional[str] = None,
    academic_year: Optional[int] = None
):
    """Lista lotações"""
    await AuthMiddleware.require_roles(['admin', 'secretario', 'semed', 'diretor'])(request)
    
    query = {}
    if school_id:
        query["school_id"] = school_id
    if staff_id:
        query["staff_id"] = staff_id
    if status:
        query["status"] = status
    if academic_year:
        query["academic_year"] = academic_year
    
    assignments = await db.school_assignments.find(query, {"_id": 0}).to_list(1000)
    
    # Enriquecer com dados
    for assign in assignments:
        staff = await db.staff.find_one({"id": assign['staff_id']}, {"_id": 0})
        if staff:
            assign['staff'] = staff
        
        school = await db.schools.find_one({"id": assign['school_id']}, {"_id": 0, "name": 1})
        if school:
            assign['school_name'] = school['name']
    
    return assignments

@api_router.post("/school-assignments")
async def create_school_assignment(assignment: SchoolAssignmentCreate, request: Request):
    """Cria nova lotação"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
    
    # Verifica se servidor existe
    staff = await db.staff.find_one({"id": assignment.staff_id})
    if not staff:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")
    
    # Verifica se escola existe
    school = await db.schools.find_one({"id": assignment.school_id})
    if not school:
        raise HTTPException(status_code=404, detail="Escola não encontrada")
    
    # Verifica se já existe lotação ativa para mesma escola/ano/função
    # Permite múltiplas funções na mesma escola
    existing = await db.school_assignments.find_one({
        "staff_id": assignment.staff_id,
        "school_id": assignment.school_id,
        "academic_year": assignment.academic_year,
        "funcao": assignment.funcao,
        "status": "ativo"
    })
    if existing:
        raise HTTPException(status_code=400, detail="Servidor já possui lotação ativa com esta função nesta escola para este ano")
    
    new_assignment = SchoolAssignment(**assignment.model_dump())
    await db.school_assignments.insert_one(new_assignment.model_dump())
    
    # Auditoria de criação de lotação
    await audit_service.log(
        action='create',
        collection='school_assignments',
        user=current_user,
        request=request,
        document_id=new_assignment.id,
        description=f"Criou lotação do servidor {staff.get('full_name', 'N/A')} como {assignment.funcao} na escola {school.get('name', 'N/A')}",
        school_id=assignment.school_id,
        school_name=school.get('name'),
        academic_year=assignment.academic_year,
        new_value={'staff_id': assignment.staff_id, 'funcao': assignment.funcao, 'carga_horaria': assignment.carga_horaria}
    )
    
    return await db.school_assignments.find_one({"id": new_assignment.id}, {"_id": 0})

@api_router.get("/school-assignments/staff/{staff_id}/schools")
async def get_staff_schools(staff_id: str, request: Request, academic_year: Optional[int] = None):
    """Busca as escolas onde um servidor está lotado"""
    await AuthMiddleware.get_current_user(request)
    
    query = {
        "staff_id": staff_id,
        "status": "ativo"
    }
    if academic_year:
        query["academic_year"] = academic_year
    
    lotacoes = await db.school_assignments.find(query, {"_id": 0}).to_list(100)
    
    # Busca os dados das escolas
    schools = []
    for lot in lotacoes:
        school = await db.schools.find_one({"id": lot['school_id']}, {"_id": 0})
        if school:
            schools.append(school)
    
    return schools

@api_router.put("/school-assignments/{assignment_id}")
async def update_school_assignment(assignment_id: str, assignment_data: SchoolAssignmentUpdate, request: Request):
    """Atualiza lotação"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
    
    existing = await db.school_assignments.find_one({"id": assignment_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Lotação não encontrada")
    
    update_data = {k: v for k, v in assignment_data.model_dump().items() if v is not None}
    update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
    
    await db.school_assignments.update_one({"id": assignment_id}, {"$set": update_data})
    
    # Auditoria de atualização de lotação
    staff = await db.staff.find_one({"id": existing.get('staff_id')}, {"_id": 0, "full_name": 1})
    school = await db.schools.find_one({"id": existing.get('school_id')}, {"_id": 0, "name": 1})
    await audit_service.log(
        action='update',
        collection='school_assignments',
        user=current_user,
        request=request,
        document_id=assignment_id,
        description=f"Atualizou lotação do servidor {staff.get('full_name', 'N/A') if staff else 'N/A'}",
        school_id=existing.get('school_id'),
        school_name=school.get('name') if school else None,
        academic_year=existing.get('academic_year'),
        old_value={'funcao': existing.get('funcao'), 'status': existing.get('status'), 'carga_horaria': existing.get('carga_horaria')},
        new_value=update_data
    )
    
    return await db.school_assignments.find_one({"id": assignment_id}, {"_id": 0})

@api_router.delete("/school-assignments/{assignment_id}")
async def delete_school_assignment(assignment_id: str, request: Request):
    """Remove lotação"""
    current_user = await AuthMiddleware.require_roles(['admin'])(request)
    
    existing = await db.school_assignments.find_one({"id": assignment_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Lotação não encontrada")
    
    # Guarda dados para auditoria
    staff = await db.staff.find_one({"id": existing.get('staff_id')}, {"_id": 0, "full_name": 1})
    school = await db.schools.find_one({"id": existing.get('school_id')}, {"_id": 0, "name": 1})
    
    await db.school_assignments.delete_one({"id": assignment_id})
    
    # Auditoria de exclusão de lotação
    await audit_service.log(
        action='delete',
        collection='school_assignments',
        user=current_user,
        request=request,
        document_id=assignment_id,
        description=f"EXCLUIU lotação do servidor {staff.get('full_name', 'N/A') if staff else 'N/A'} da escola {school.get('name', 'N/A') if school else 'N/A'}",
        school_id=existing.get('school_id'),
        school_name=school.get('name') if school else None,
        academic_year=existing.get('academic_year'),
        old_value={'staff_id': existing.get('staff_id'), 'funcao': existing.get('funcao'), 'status': existing.get('status')}
    )
    
    return {"message": "Lotação removida com sucesso"}

# ============= TEACHER ASSIGNMENTS (ALOCAÇÃO DE PROFESSORES) =============

@api_router.get("/teacher-assignments")
async def list_teacher_assignments(
    request: Request,
    school_id: Optional[str] = None,
    staff_id: Optional[str] = None,
    class_id: Optional[str] = None,
    course_id: Optional[str] = None,
    academic_year: Optional[int] = None,
    status: Optional[str] = None
):
    """Lista alocações de professores"""
    await AuthMiddleware.require_roles(['admin', 'secretario', 'semed', 'diretor', 'coordenador'])(request)
    
    query = {}
    if school_id:
        query["school_id"] = school_id
    if staff_id:
        query["staff_id"] = staff_id
    if class_id:
        query["class_id"] = class_id
    if course_id:
        query["course_id"] = course_id
    if academic_year:
        query["academic_year"] = academic_year
    if status:
        query["status"] = status
    
    assignments = await db.teacher_assignments.find(query, {"_id": 0}).to_list(1000)
    
    # Enriquecer com dados
    for assign in assignments:
        staff = await db.staff.find_one({"id": assign['staff_id']}, {"_id": 0})
        if staff:
            assign['staff_name'] = staff.get('nome')
        
        turma = await db.classes.find_one({"id": assign['class_id']}, {"_id": 0, "name": 1})
        if turma:
            assign['class_name'] = turma['name']
        
        course = await db.courses.find_one({"id": assign['course_id']}, {"_id": 0, "name": 1})
        if course:
            assign['course_name'] = course['name']
        
        school = await db.schools.find_one({"id": assign['school_id']}, {"_id": 0, "name": 1})
        if school:
            assign['school_name'] = school['name']
    
    return assignments

@api_router.post("/teacher-assignments")
async def create_teacher_assignment(assignment: TeacherAssignmentCreate, request: Request):
    """Cria nova alocação de professor"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor'])(request)
    
    # Verifica se servidor existe e é professor
    staff = await db.staff.find_one({"id": assignment.staff_id})
    if not staff:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")
    if staff['cargo'] != 'professor':
        raise HTTPException(status_code=400, detail="Servidor não é professor")
    
    # Verifica se turma existe
    turma = await db.classes.find_one({"id": assignment.class_id})
    if not turma:
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    
    # Verifica se componente existe
    course = await db.courses.find_one({"id": assignment.course_id})
    if not course:
        raise HTTPException(status_code=404, detail="Componente curricular não encontrado")
    
    # Verifica se o MESMO professor já está alocado para o MESMO componente na MESMA turma/ano
    # (permite múltiplos componentes na mesma turma, mas não duplicar a mesma alocação)
    existing = await db.teacher_assignments.find_one({
        "staff_id": assignment.staff_id,
        "class_id": assignment.class_id,
        "course_id": assignment.course_id,
        "academic_year": assignment.academic_year,
        "status": "ativo"
    })
    if existing:
        raise HTTPException(status_code=400, detail="Este professor já está alocado para este componente nesta turma")
    
    new_assignment = TeacherAssignment(**assignment.model_dump())
    await db.teacher_assignments.insert_one(new_assignment.model_dump())
    
    return await db.teacher_assignments.find_one({"id": new_assignment.id}, {"_id": 0})

@api_router.put("/teacher-assignments/{assignment_id}")
async def update_teacher_assignment(assignment_id: str, assignment_data: TeacherAssignmentUpdate, request: Request):
    """Atualiza alocação de professor"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor'])(request)
    
    existing = await db.teacher_assignments.find_one({"id": assignment_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Alocação não encontrada")
    
    update_data = {k: v for k, v in assignment_data.model_dump().items() if v is not None}
    update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
    
    await db.teacher_assignments.update_one({"id": assignment_id}, {"$set": update_data})
    
    return await db.teacher_assignments.find_one({"id": assignment_id}, {"_id": 0})

@api_router.delete("/teacher-assignments/{assignment_id}")
async def delete_teacher_assignment(assignment_id: str, request: Request):
    """Remove alocação de professor"""
    await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
    
    existing = await db.teacher_assignments.find_one({"id": assignment_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Alocação não encontrada")
    
    await db.teacher_assignments.delete_one({"id": assignment_id})
    return {"message": "Alocação removida com sucesso"}

@api_router.get("/uploads/staff/{filename}")
async def get_staff_photo(filename: str):
    """Serve foto do servidor"""
    from fastapi.responses import FileResponse
    filepath = f"/app/backend/uploads/staff/{filename}"
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Foto não encontrada")
    return FileResponse(filepath)

# ============= OBJETOS DE CONHECIMENTO =============

from models import LearningObject, LearningObjectCreate, LearningObjectUpdate

@api_router.get("/learning-objects")
async def list_learning_objects(
    request: Request,
    class_id: Optional[str] = None,
    course_id: Optional[str] = None,
    date: Optional[str] = None,
    academic_year: Optional[int] = None,
    month: Optional[int] = None
):
    """Lista objetos de conhecimento (conteúdos ministrados)"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'coordenador', 'professor', 'semed'])(request)
    
    query = {}
    if class_id:
        query["class_id"] = class_id
    if course_id:
        query["course_id"] = course_id
    if date:
        query["date"] = date
    if academic_year:
        query["academic_year"] = academic_year
    
    # Filtrar por mês se especificado
    if month and academic_year:
        start_date = f"{academic_year}-{month:02d}-01"
        if month == 12:
            end_date = f"{academic_year + 1}-01-01"
        else:
            end_date = f"{academic_year}-{month + 1:02d}-01"
        query["date"] = {"$gte": start_date, "$lt": end_date}
    
    objects = await db.learning_objects.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    
    # Enriquecer com nomes
    for obj in objects:
        turma = await db.classes.find_one({"id": obj["class_id"]}, {"_id": 0, "name": 1})
        course = await db.courses.find_one({"id": obj["course_id"]}, {"_id": 0, "name": 1})
        obj["class_name"] = turma.get("name", "") if turma else ""
        obj["course_name"] = course.get("name", "") if course else ""
    
    return objects

@api_router.get("/learning-objects/{object_id}")
async def get_learning_object(object_id: str, request: Request):
    """Retorna um objeto de conhecimento específico"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'coordenador', 'professor', 'semed'])(request)
    
    obj = await db.learning_objects.find_one({"id": object_id}, {"_id": 0})
    if not obj:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    
    return obj

@api_router.post("/learning-objects")
async def create_learning_object(data: LearningObjectCreate, request: Request):
    """Cria um registro de objeto de conhecimento"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'coordenador', 'professor'])(request)
    user_role = current_user.get('role', '')
    
    # Verifica se o ano letivo está aberto (apenas para não-admins)
    academic_year = data.academic_year or datetime.now().year
    if user_role != 'admin':
        class_doc = await db.classes.find_one(
            {"id": data.class_id},
            {"_id": 0, "school_id": 1, "academic_year": 1}
        )
        if class_doc:
            academic_year = data.academic_year or class_doc.get('academic_year', datetime.now().year)
            await verify_academic_year_open_or_raise(
                class_doc['school_id'],
                academic_year
            )
    
    # Verifica a data limite de edição por bimestre (apenas para não-admins e não-secretarios)
    if user_role not in ['admin', 'secretario']:
        calendario = await db.calendario_letivo.find_one(
            {"ano_letivo": academic_year},
            {"_id": 0}
        )
        if calendario:
            object_date = data.date
            for i in range(1, 5):
                inicio = calendario.get(f"bimestre_{i}_inicio")
                fim = calendario.get(f"bimestre_{i}_fim")
                if inicio and fim and object_date >= inicio and object_date <= fim:
                    await verify_bimestre_edit_deadline_or_raise(academic_year, i, user_role)
                    break
    
    # Verifica se já existe registro para esta data/turma/componente
    existing = await db.learning_objects.find_one({
        "class_id": data.class_id,
        "course_id": data.course_id,
        "date": data.date
    })
    
    if existing:
        raise HTTPException(
            status_code=400, 
            detail="Já existe um registro para esta turma/componente nesta data. Use a opção de editar."
        )
    
    new_object = LearningObject(
        **data.model_dump(),
        recorded_by=current_user['id']
    )
    
    await db.learning_objects.insert_one(new_object.model_dump())
    
    return await db.learning_objects.find_one({"id": new_object.id}, {"_id": 0})

@api_router.put("/learning-objects/{object_id}")
async def update_learning_object(object_id: str, data: LearningObjectUpdate, request: Request):
    """Atualiza um registro de objeto de conhecimento"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'coordenador', 'professor'])(request)
    user_role = current_user.get('role', '')
    
    existing = await db.learning_objects.find_one({"id": object_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    
    # Verifica a data limite de edição por bimestre (apenas para não-admins e não-secretarios)
    if user_role not in ['admin', 'secretario']:
        academic_year = existing.get('academic_year', datetime.now().year)
        calendario = await db.calendario_letivo.find_one(
            {"ano_letivo": academic_year},
            {"_id": 0}
        )
        if calendario:
            object_date = existing.get('date')
            for i in range(1, 5):
                inicio = calendario.get(f"bimestre_{i}_inicio")
                fim = calendario.get(f"bimestre_{i}_fim")
                if inicio and fim and object_date >= inicio and object_date <= fim:
                    await verify_bimestre_edit_deadline_or_raise(academic_year, i, user_role)
                    break
    
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.learning_objects.update_one(
        {"id": object_id},
        {"$set": update_data}
    )
    
    return await db.learning_objects.find_one({"id": object_id}, {"_id": 0})

@api_router.delete("/learning-objects/{object_id}")
async def delete_learning_object(object_id: str, request: Request):
    """Exclui um registro de objeto de conhecimento"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'coordenador', 'professor'])(request)
    
    existing = await db.learning_objects.find_one({"id": object_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    
    await db.learning_objects.delete_one({"id": object_id})
    
    return {"message": "Registro excluído com sucesso"}

@api_router.get("/learning-objects/check-date/{class_id}/{course_id}/{date}")
async def check_learning_object_date(class_id: str, course_id: str, date: str, request: Request):
    """Verifica se existe registro para uma data específica"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'coordenador', 'professor', 'semed'])(request)
    
    existing = await db.learning_objects.find_one({
        "class_id": class_id,
        "course_id": course_id,
        "date": date
    }, {"_id": 0})
    
    return {
        "has_record": existing is not None,
        "record": existing
    }

# ============= PORTAL DO PROFESSOR =============

@api_router.get("/professor/me")
async def get_professor_profile(request: Request):
    """Retorna os dados do professor logado"""
    current_user = await AuthMiddleware.require_roles(['professor'])(request)
    
    # Busca o staff vinculado ao usuário
    staff = await db.staff.find_one({"user_id": current_user['id']}, {"_id": 0})
    if not staff:
        # Tenta buscar pelo email
        staff = await db.staff.find_one({"email": current_user['email']}, {"_id": 0})
    
    if not staff:
        raise HTTPException(status_code=404, detail="Perfil de professor não encontrado")
    
    return staff

@api_router.get("/professor/turmas")
async def get_professor_turmas(request: Request, academic_year: Optional[int] = None):
    """Retorna as turmas do professor logado (apenas turmas onde foi alocado)"""
    current_user = await AuthMiddleware.require_roles(['professor'])(request)
    
    # Busca o staff vinculado ao usuário
    staff = await db.staff.find_one({"user_id": current_user['id']}, {"_id": 0})
    if not staff:
        staff = await db.staff.find_one({"email": current_user['email']}, {"_id": 0})
    
    if not staff:
        raise HTTPException(status_code=404, detail="Perfil de professor não encontrado")
    
    # Busca as alocações do professor
    query = {"staff_id": staff['id'], "status": "ativo"}
    if academic_year:
        query["academic_year"] = academic_year
    else:
        query["academic_year"] = datetime.now().year
    
    alocacoes = await db.teacher_assignments.find(query, {"_id": 0}).to_list(1000)
    
    # Agrupa por turma
    turmas_dict = {}
    for aloc in alocacoes:
        class_id = aloc['class_id']
        if class_id not in turmas_dict:
            # Busca dados da turma
            turma = await db.classes.find_one({"id": class_id}, {"_id": 0})
            if turma:
                # Busca nome da escola
                school = await db.schools.find_one({"id": turma.get('school_id')}, {"_id": 0, "name": 1})
                turma['school_name'] = school.get('name', '') if school else ''
                turma['componentes'] = []
                turmas_dict[class_id] = turma
        
        if class_id in turmas_dict:
            # Busca dados do componente
            course = await db.courses.find_one({"id": aloc['course_id']}, {"_id": 0})
            if course:
                turmas_dict[class_id]['componentes'].append({
                    "id": course['id'],
                    "name": course.get('name'),
                    "workload": course.get('workload'),
                    "assignment_id": aloc['id']
                })
    
    return list(turmas_dict.values())

@api_router.get("/professor/turmas/{class_id}/alunos")
async def get_professor_turma_alunos(class_id: str, request: Request):
    """Retorna os alunos de uma turma do professor"""
    current_user = await AuthMiddleware.require_roles(['professor'])(request)
    
    # Verifica se o professor tem alocação nesta turma
    staff = await db.staff.find_one({"user_id": current_user['id']}, {"_id": 0})
    if not staff:
        staff = await db.staff.find_one({"email": current_user['email']}, {"_id": 0})
    
    if not staff:
        raise HTTPException(status_code=404, detail="Perfil de professor não encontrado")
    
    alocacao = await db.teacher_assignments.find_one({
        "staff_id": staff['id'],
        "class_id": class_id,
        "status": "ativo"
    })
    
    if not alocacao:
        raise HTTPException(status_code=403, detail="Você não tem acesso a esta turma")
    
    # Busca as matrículas da turma
    enrollments = await db.enrollments.find({
        "class_id": class_id,
        "status": "active"
    }, {"_id": 0}).to_list(1000)
    
    # Busca dados dos alunos
    alunos = []
    for enrollment in enrollments:
        student = await db.students.find_one({"id": enrollment['student_id']}, {"_id": 0})
        if student:
            student['enrollment_id'] = enrollment['id']
            alunos.append(student)
    
    # Ordena por nome
    alunos.sort(key=lambda x: x.get('full_name', ''))
    
    return alunos

@api_router.get("/professor/turmas/{class_id}/componentes/{course_id}/notas")
async def get_professor_turma_notas(class_id: str, course_id: str, request: Request, bimestre: Optional[int] = None):
    """Retorna as notas dos alunos de uma turma/componente"""
    current_user = await AuthMiddleware.require_roles(['professor'])(request)
    
    # Verifica se o professor tem alocação nesta turma/componente
    staff = await db.staff.find_one({"user_id": current_user['id']}, {"_id": 0})
    if not staff:
        staff = await db.staff.find_one({"email": current_user['email']}, {"_id": 0})
    
    if not staff:
        raise HTTPException(status_code=404, detail="Perfil de professor não encontrado")
    
    alocacao = await db.teacher_assignments.find_one({
        "staff_id": staff['id'],
        "class_id": class_id,
        "course_id": course_id,
        "status": "ativo"
    })
    
    if not alocacao:
        raise HTTPException(status_code=403, detail="Você não tem acesso a este componente nesta turma")
    
    # Busca as notas
    query = {
        "class_id": class_id,
        "course_id": course_id
    }
    if bimestre:
        query["bimestre"] = bimestre
    
    notas = await db.grades.find(query, {"_id": 0}).to_list(1000)
    
    # Enriquecer com dados do aluno
    for nota in notas:
        student = await db.students.find_one({"id": nota['student_id']}, {"_id": 0, "full_name": 1, "registration_number": 1})
        if student:
            nota['student_name'] = student.get('full_name', '')
            nota['student_registration'] = student.get('registration_number', '')
    
    return notas

@api_router.get("/professor/turmas/{class_id}/componentes/{course_id}/frequencia")
async def get_professor_turma_frequencia(class_id: str, course_id: str, request: Request, month: Optional[int] = None, year: Optional[int] = None):
    """Retorna a frequência dos alunos de uma turma/componente"""
    current_user = await AuthMiddleware.require_roles(['professor'])(request)
    
    # Verifica se o professor tem alocação nesta turma/componente
    staff = await db.staff.find_one({"user_id": current_user['id']}, {"_id": 0})
    if not staff:
        staff = await db.staff.find_one({"email": current_user['email']}, {"_id": 0})
    
    if not staff:
        raise HTTPException(status_code=404, detail="Perfil de professor não encontrado")
    
    alocacao = await db.teacher_assignments.find_one({
        "staff_id": staff['id'],
        "class_id": class_id,
        "course_id": course_id,
        "status": "ativo"
    })
    
    if not alocacao:
        raise HTTPException(status_code=403, detail="Você não tem acesso a este componente nesta turma")
    
    # Busca a frequência
    query = {
        "class_id": class_id,
        "course_id": course_id
    }
    
    if month and year:
        # Filtra por mês/ano
        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            end_date = f"{year+1}-01-01"
        else:
            end_date = f"{year}-{month+1:02d}-01"
        query["date"] = {"$gte": start_date, "$lt": end_date}
    
    frequencias = await db.attendance.find(query, {"_id": 0}).to_list(1000)
    
    return frequencias

# ============= FIM PORTAL DO PROFESSOR =============

# ============= USER PROFILE ENDPOINTS =============

@api_router.get("/profiles/me")
async def get_my_profile(request: Request):
    """Retorna o perfil do usuário logado"""
    current_user = await AuthMiddleware.get_current_user(request)
    
    # Busca dados completos do usuário no banco
    user_data = await db.users.find_one({"id": current_user['id']}, {"_id": 0, "password_hash": 0})
    
    profile = await db.user_profiles.find_one({"user_id": current_user['id']}, {"_id": 0})
    
    if not profile:
        # Criar perfil automaticamente se não existir
        profile = {
            "id": str(uuid.uuid4()),
            "user_id": current_user['id'],
            "headline": None,
            "sobre": None,
            "localizacao": None,
            "telefone": None,
            "website": None,
            "linkedin_url": None,
            "foto_capa_url": None,
            "foto_url": user_data.get('avatar_url') if user_data else None,
            "is_public": True,
            "experiencias": [],
            "formacoes": [],
            "competencias": [],
            "certificacoes": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None
        }
        await db.user_profiles.insert_one(profile)
        profile.pop('_id', None)
    
    # Adicionar dados do usuário
    profile['user'] = {
        'id': current_user['id'],
        'full_name': user_data.get('full_name', '') if user_data else '',
        'email': user_data.get('email', '') if user_data else current_user.get('email', ''),
        'role': user_data.get('role', '') if user_data else current_user.get('role', '')
    }
    
    return profile

@api_router.get("/profiles/search")
async def search_public_profiles(q: str = "", request: Request = None):
    """Busca perfis públicos pelo nome do usuário (mínimo 3 caracteres)"""
    # Validar mínimo de 3 caracteres
    if len(q) < 3:
        return []
    
    # Buscar usuários cujo nome começa com a query (case insensitive)
    import re
    regex_pattern = f"^{re.escape(q)}"
    
    users = await db.users.find(
        {"full_name": {"$regex": regex_pattern, "$options": "i"}},
        {"_id": 0, "password_hash": 0}
    ).to_list(20)
    
    results = []
    for user in users:
        # Verificar se o perfil é público
        profile = await db.user_profiles.find_one({"user_id": user['id']}, {"_id": 0})
        
        # Se não tem perfil, considera como público (padrão)
        is_public = True
        if profile:
            is_public = profile.get('is_public', True)
        
        if is_public:
            results.append({
                "user_id": user['id'],
                "full_name": user.get('full_name', ''),
                "email": user.get('email', ''),
                "role": user.get('role', ''),
                "headline": profile.get('headline') if profile else None,
                "foto_url": profile.get('foto_url') if profile else user.get('avatar_url')
            })
    
    return results

@api_router.get("/profiles/{user_id}")
async def get_profile_by_user_id(user_id: str, request: Request):
    """Retorna o perfil de um usuário específico"""
    current_user = None
    try:
        current_user = await AuthMiddleware.get_current_user(request)
    except:
        pass
    
    profile = await db.user_profiles.find_one({"user_id": user_id}, {"_id": 0})
    
    if not profile:
        # Buscar usuário para criar perfil
        user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
        if not user:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        
        # Criar perfil automaticamente
        profile = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "headline": None,
            "sobre": None,
            "localizacao": None,
            "telefone": None,
            "website": None,
            "linkedin_url": None,
            "foto_capa_url": None,
            "foto_url": user.get('avatar_url'),
            "is_public": True,
            "experiencias": [],
            "formacoes": [],
            "competencias": [],
            "certificacoes": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None
        }
        await db.user_profiles.insert_one(profile)
        profile.pop('_id', None)
    else:
        # Verificar visibilidade
        is_owner = current_user and current_user['id'] == user_id
        is_admin = current_user and current_user.get('role') == 'admin'
        
        if not profile.get('is_public', True) and not is_owner and not is_admin:
            raise HTTPException(status_code=403, detail="Este perfil é privado")
    
    # Buscar dados do usuário
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if user:
        profile['user'] = {
            'id': user['id'],
            'full_name': user.get('full_name', ''),
            'email': user.get('email', ''),
            'role': user.get('role', '')
        }
    
    return profile

@api_router.put("/profiles/me")
async def update_my_profile(profile_data: UserProfileUpdate, request: Request):
    """Atualiza o perfil do usuário logado"""
    current_user = await AuthMiddleware.get_current_user(request)
    
    # Verificar se perfil existe
    profile = await db.user_profiles.find_one({"user_id": current_user['id']})
    
    update_data = profile_data.model_dump(exclude_unset=True)
    update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
    
    if not profile:
        # Criar perfil se não existir
        new_profile = {
            "id": str(uuid.uuid4()),
            "user_id": current_user['id'],
            "headline": None,
            "sobre": None,
            "localizacao": None,
            "telefone": None,
            "website": None,
            "linkedin_url": None,
            "foto_capa_url": None,
            "foto_url": current_user.get('avatar_url'),
            "is_public": True,
            "experiencias": [],
            "formacoes": [],
            "competencias": [],
            "certificacoes": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            **update_data
        }
        await db.user_profiles.insert_one(new_profile)
        new_profile.pop('_id', None)
        return new_profile
    
    await db.user_profiles.update_one(
        {"user_id": current_user['id']},
        {"$set": update_data}
    )
    
    updated_profile = await db.user_profiles.find_one({"user_id": current_user['id']}, {"_id": 0})
    return updated_profile

@api_router.put("/profiles/{user_id}")
async def update_profile_by_admin(user_id: str, profile_data: UserProfileUpdate, request: Request):
    """Admin pode atualizar perfil de qualquer usuário"""
    current_user = await AuthMiddleware.require_roles(['admin'])(request)
    
    # Verificar se perfil existe
    profile = await db.user_profiles.find_one({"user_id": user_id})
    
    update_data = profile_data.model_dump(exclude_unset=True)
    update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
    
    if not profile:
        # Verificar se usuário existe
        user = await db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        
        # Criar perfil
        new_profile = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "headline": None,
            "sobre": None,
            "localizacao": None,
            "telefone": None,
            "website": None,
            "linkedin_url": None,
            "foto_capa_url": None,
            "foto_url": user.get('avatar_url'),
            "is_public": True,
            "experiencias": [],
            "formacoes": [],
            "competencias": [],
            "certificacoes": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            **update_data
        }
        await db.user_profiles.insert_one(new_profile)
        new_profile.pop('_id', None)
        return new_profile
    
    await db.user_profiles.update_one(
        {"user_id": user_id},
        {"$set": update_data}
    )
    
    updated_profile = await db.user_profiles.find_one({"user_id": user_id}, {"_id": 0})
    return updated_profile

# ============= CONNECTION ENDPOINTS =============

@api_router.post("/connections/invite")
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

@api_router.post("/connections/{connection_id}/accept")
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

@api_router.post("/connections/{connection_id}/reject")
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

@api_router.delete("/connections/{connection_id}")
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

@api_router.get("/connections")
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

@api_router.get("/connections/pending")
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

@api_router.get("/connections/sent")
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

@api_router.get("/connections/status/{user_id}")
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
    
    if not connection:
        return {"status": "none", "connection_id": None}
    
    # Verificar se o convite foi enviado por mim ou recebido
    is_requester = connection['requester_id'] == current_user['id']
    
    return {
        "status": connection['status'],
        "connection_id": connection['id'],
        "is_requester": is_requester
    }

# ============= MESSAGE ENDPOINTS =============

@api_router.post("/messages")
async def send_message(data: MessageCreate, request: Request):
    """Envia uma mensagem para um usuário conectado"""
    current_user = await AuthMiddleware.get_current_user(request)
    sender_id = current_user['id']
    receiver_id = data.receiver_id
    
    # Verificar se estão conectados
    connection = await db.connections.find_one({
        "$or": [
            {"requester_id": sender_id, "receiver_id": receiver_id, "status": "accepted"},
            {"requester_id": receiver_id, "receiver_id": sender_id, "status": "accepted"}
        ]
    })
    
    if not connection:
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

@api_router.get("/messages/{connection_id}")
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

@api_router.get("/messages/conversations/list")
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

@api_router.post("/messages/{message_id}/read")
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

@api_router.get("/messages/unread/count")
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

@api_router.delete("/messages/{message_id}")
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

@api_router.delete("/messages/conversation/{connection_id}")
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

# ============= MESSAGE LOGS ENDPOINTS (ADMIN ONLY) =============

@api_router.get("/admin/message-logs")
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

@api_router.get("/admin/message-logs/users")
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

@api_router.get("/admin/message-logs/user/{user_id}")
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

@api_router.delete("/admin/message-logs/expired")
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

async def validate_student_for_document(student: dict, current_user: dict) -> tuple:
    """
    Valida se o aluno pode ter documentos gerados e se o usuário tem permissão.
    
    Retorna: (is_valid, error_message)
    """
    # Verificar se o aluno tem escola e turma definidos
    if not student.get('school_id') and not student.get('class_id'):
        return False, "Aluno(a) sem matrícula"
    
    # Admins podem ver qualquer aluno
    if current_user.get('role') in ['admin', 'admin_teste']:
        return True, None
    
    # Para outros papéis, verificar se o usuário tem vínculo com a escola do aluno
    user_school_id = current_user.get('school_id')
    student_school_id = student.get('school_id')
    
    # Se o usuário tem escola vinculada e o aluno está em outra escola
    if user_school_id and student_school_id and user_school_id != student_school_id:
        return False, "Aluno não matriculado nesta escola"
    
    return True, None

@api_router.get("/documents/boletim/{student_id}")
async def generate_boletim(student_id: str, request: Request, academic_year: str = "2025"):
    """
    Gera o Boletim Escolar do aluno em PDF
    
    Args:
        student_id: ID do aluno
        academic_year: Ano letivo (default: 2025)
    """
    current_user = await AuthMiddleware.get_current_user(request)
    
    # Buscar dados do aluno
    student = await db.students.find_one({"id": student_id}, {"_id": 0})
    if not student:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    
    # Validar permissão para gerar documento
    is_valid, error_message = await validate_student_for_document(student, current_user)
    if not is_valid:
        raise HTTPException(status_code=403, detail=error_message)
    
    # Verificar se o aluno está ativo
    student_status = student.get('status', 'active')
    if student_status != 'active':
        status_labels = {
            'inactive': 'Inativo',
            'transferred': 'Transferido',
            'graduated': 'Formado',
            'deceased': 'Falecido',
            'cancelled': 'Matrícula Cancelada',
            'dropout': 'Desistente'
        }
        status_label = status_labels.get(student_status, student_status)
        raise HTTPException(
            status_code=400, 
            detail=f"Não é possível gerar documentos para este aluno. Status atual: {status_label}. Apenas alunos com status 'Ativo' podem ter documentos gerados."
        )
    
    # Buscar matrícula ativa do aluno
    enrollment = await db.enrollments.find_one({
        "student_id": student_id,
        "status": "active",
        "academic_year": academic_year
    }, {"_id": 0})
    
    if not enrollment:
        # Tentar buscar qualquer matrícula do aluno
        enrollment = await db.enrollments.find_one({
            "student_id": student_id
        }, {"_id": 0})
    
    # Se não houver matrícula, usar dados do próprio aluno
    if not enrollment:
        enrollment = {
            "student_id": student_id,
            "class_id": student.get("class_id"),
            "registration_number": student.get("enrollment_number", "N/A"),
            "status": "active",
            "academic_year": academic_year
        }
    
    # Buscar turma (do enrollment ou do aluno)
    class_id = enrollment.get("class_id") or student.get("class_id")
    class_info = await db.classes.find_one({"id": class_id}, {"_id": 0})
    if not class_info:
        # Criar turma padrão se não existir
        class_info = {"name": "Turma não informada", "shift": "N/A", "school_id": student.get("school_id")}
    
    # Usar o ano letivo da turma em vez do parâmetro (a turma determina o ano)
    actual_academic_year = str(class_info.get("academic_year", academic_year))
    
    # Buscar escola
    school_id = class_info.get("school_id") or student.get("school_id")
    school = await db.schools.find_one({"id": school_id}, {"_id": 0})
    if not school:
        school = {"name": "Escola Municipal", "cnpj": "N/A", "phone": "N/A", "city": "Município"}
    
    # Buscar notas do aluno
    # IMPORTANTE: academic_year deve ser int para corresponder ao banco de dados
    academic_year_int = int(actual_academic_year) if actual_academic_year else 2025
    grades = await db.grades.find({
        "student_id": student_id,
        "academic_year": academic_year_int
    }, {"_id": 0}).to_list(100)
    
    # ===== FILTRAR COMPONENTES CURRICULARES =====
    # Determinar nível de ensino e série da turma
    nivel_ensino = class_info.get('nivel_ensino')
    grade_level = class_info.get('grade_level', '')
    grade_level_lower = grade_level.lower() if grade_level else ''
    
    # Se não tem nivel_ensino definido, inferir pelo grade_level
    if not nivel_ensino:
        if any(x in grade_level_lower for x in ['berçário', 'bercario', 'maternal', 'pré', 'pre']):
            nivel_ensino = 'educacao_infantil'
        elif any(x in grade_level_lower for x in ['1º ano', '2º ano', '3º ano', '4º ano', '5º ano', '1 ano', '2 ano', '3 ano', '4 ano', '5 ano']):
            nivel_ensino = 'fundamental_anos_iniciais'
        elif any(x in grade_level_lower for x in ['6º ano', '7º ano', '8º ano', '9º ano', '6 ano', '7 ano', '8 ano', '9 ano']):
            nivel_ensino = 'fundamental_anos_finais'
        elif any(x in grade_level_lower for x in ['eja', 'etapa']):
            if any(x in grade_level_lower for x in ['3', '4', 'final']):
                nivel_ensino = 'eja_final'
            else:
                nivel_ensino = 'eja'
    
    # Log para debug
    logger.info(f"Boletim: grade_level={grade_level}, nivel_ensino inferido={nivel_ensino}")
    
    # Determinar o tipo de atendimento/programa da TURMA (não da escola)
    # Se a turma tem atendimento_programa definido, usa ele. Senão, é turma regular.
    turma_atendimento = class_info.get('atendimento_programa', '')
    turma_integral = turma_atendimento == 'atendimento_integral'
    logger.info(f"Boletim: turma_atendimento={turma_atendimento}, turma_integral={turma_integral}")
    
    # Construir query para buscar componentes curriculares
    courses_query = {}
    
    # Filtrar por nível de ensino (OBRIGATÓRIO se temos um nível)
    if nivel_ensino:
        courses_query['nivel_ensino'] = nivel_ensino
    
    # Buscar componentes do nível de ensino
    all_courses = await db.courses.find(courses_query, {"_id": 0}).to_list(100)
    logger.info(f"Boletim: {len(all_courses)} componentes encontrados para nivel_ensino={nivel_ensino}")
    
    # Filtrar componentes baseado no atendimento/programa da TURMA
    filtered_courses = []
    excluded_courses = []  # Para debug
    for course in all_courses:
        atendimento = course.get('atendimento_programa')
        course_grade_levels = course.get('grade_levels', [])
        course_name = course.get('name', 'N/A')
        
        # Componentes Transversais/Formativos aparecem em TODAS as turmas
        if atendimento == 'transversal_formativa':
            # Sempre incluir - é transversal a todas as turmas
            pass
        # Verificar se o componente é específico de Escola Integral
        elif atendimento == 'atendimento_integral':
            # Só incluir se a TURMA é integral (não a escola)
            if not turma_integral:
                excluded_courses.append(f"{course_name} (excluído: atendimento_integral e turma não é integral)")
                continue
        # Verificar se o componente é de outro atendimento (AEE, reforço, etc)
        elif atendimento and atendimento not in ['atendimento_integral', 'transversal_formativa']:
            # Verificar se a turma tem esse atendimento específico
            if turma_atendimento != atendimento:
                excluded_courses.append(f"{course_name} (excluído: atendimento={atendimento} diferente do atendimento da turma={turma_atendimento})")
                continue
        
        # Verificar se o componente é específico para certas séries
        if course_grade_levels:
            # Se o componente tem séries específicas, verificar se a turma é de uma delas
            if grade_level and grade_level not in course_grade_levels:
                excluded_courses.append(f"{course_name} (excluído: grade_levels={course_grade_levels} não inclui {grade_level})")
                continue
        
        filtered_courses.append(course)
    
    # Log de debug detalhado
    logger.info(f"Boletim: {len(filtered_courses)} componentes incluídos após filtragem")
    if excluded_courses:
        logger.warning(f"Boletim: {len(excluded_courses)} componentes EXCLUÍDOS:")
        for exc in excluded_courses:
            logger.warning(f"  - {exc}")
    
    # Log dos componentes incluídos
    included_names = [c.get('name', 'N/A') for c in filtered_courses]
    logger.info(f"Boletim: Componentes incluídos: {included_names}")
    
    # Ordenar por nome
    filtered_courses.sort(key=lambda x: x.get('name', ''))
    
    # Se não houver componentes após filtragem, buscar todos do nível
    if not filtered_courses:
        if nivel_ensino:
            filtered_courses = await db.courses.find({
                "nivel_ensino": nivel_ensino,
                "$or": [
                    {"atendimento_programa": None},
                    {"atendimento_programa": {"$exists": False}}
                ]
            }, {"_id": 0}).to_list(50)
        else:
            # Fallback: buscar todos
            filtered_courses = await db.courses.find({}, {"_id": 0}).to_list(50)
    
    courses = filtered_courses
    
    # Buscar dados da mantenedora
    mantenedora = await db.mantenedora.find_one({}, {"_id": 0})
    
    # Buscar calendário letivo para obter os dias letivos (usar ano da turma)
    calendario_letivo = await db.calendario_letivo.find_one({
        "ano_letivo": int(actual_academic_year),
        "school_id": None  # Calendário geral
    }, {"_id": 0})
    
    # Calcular total de dias letivos do ano (mesmo cálculo da ficha individual)
    dias_letivos_ano = 200  # Padrão LDB
    if calendario_letivo:
        # Buscar eventos do calendário para o ano
        eventos = await db.calendar_events.find({
            "year": int(actual_academic_year)
        }, {"_id": 0}).to_list(500)
        
        from datetime import datetime, timedelta
        datas_nao_letivas = set()
        datas_sabados_letivos = set()
        
        for evento in eventos:
            tipo = evento.get('type', '')
            data_str = evento.get('date', '')
            
            if tipo in ['feriado', 'recesso', 'ferias', 'nao_letivo', 'ponto_facultativo', 'conselho']:
                try:
                    data = datetime.strptime(data_str[:10], '%Y-%m-%d').date()
                    datas_nao_letivas.add(data)
                except:
                    pass
            elif tipo == 'sabado_letivo':
                try:
                    data = datetime.strptime(data_str[:10], '%Y-%m-%d').date()
                    datas_sabados_letivos.add(data)
                except:
                    pass
        
        def calcular_dias_letivos_periodo(inicio_str, fim_str):
            if not inicio_str or not fim_str:
                return 0
            try:
                inicio = datetime.strptime(str(inicio_str)[:10], '%Y-%m-%d').date()
                fim = datetime.strptime(str(fim_str)[:10], '%Y-%m-%d').date()
            except:
                return 0
            
            dias = 0
            current = inicio
            while current <= fim:
                dia_semana = current.weekday()
                if dia_semana < 5:
                    if current not in datas_nao_letivas:
                        dias += 1
                elif dia_semana == 5:
                    if current in datas_sabados_letivos:
                        dias += 1
                current += timedelta(days=1)
            return dias
        
        b1 = calcular_dias_letivos_periodo(calendario_letivo.get('bimestre_1_inicio'), calendario_letivo.get('bimestre_1_fim'))
        b2 = calcular_dias_letivos_periodo(calendario_letivo.get('bimestre_2_inicio'), calendario_letivo.get('bimestre_2_fim'))
        b3 = calcular_dias_letivos_periodo(calendario_letivo.get('bimestre_3_inicio'), calendario_letivo.get('bimestre_3_fim'))
        b4 = calcular_dias_letivos_periodo(calendario_letivo.get('bimestre_4_inicio'), calendario_letivo.get('bimestre_4_fim'))
        
        dias_letivos_ano = b1 + b2 + b3 + b4
        if dias_letivos_ano == 0:
            dias_letivos_ano = calendario_letivo.get('dias_letivos_previstos', 200) or 200
    
    # ===== BUSCAR DADOS DE FREQUÊNCIA (MESMA LÓGICA DA FICHA INDIVIDUAL) =====
    class_id = student.get('class_id')
    attendance_records = await db.attendance.find(
        {"class_id": class_id, "academic_year": int(actual_academic_year)},
        {"_id": 0}
    ).to_list(500)
    
    # Separar faltas por tipo: Regular (diário) e Escola Integral (por componente)
    faltas_regular = 0
    faltas_por_componente = {}
    
    for att_record in attendance_records:
        period = att_record.get('period', 'regular')
        course_id = att_record.get('course_id')
        attendance_type = att_record.get('attendance_type', 'daily')
        
        student_records = att_record.get('records', [])
        for sr in student_records:
            if sr.get('student_id') == student_id:
                status = sr.get('status', '')
                if status == 'F':
                    if attendance_type == 'daily' and period == 'regular':
                        faltas_regular += 1
                    elif course_id:
                        if course_id not in faltas_por_componente:
                            faltas_por_componente[course_id] = 0
                        faltas_por_componente[course_id] += 1
    
    logger.info(f"Boletim: Faltas Regular={faltas_regular}, Faltas por componente={faltas_por_componente}")
    
    # Preparar attendance_data para o PDF
    attendance_data = {
        '_meta': {
            'faltas_regular': faltas_regular,
            'faltas_por_componente': faltas_por_componente,
            'is_escola_integral': turma_integral  # Usa atendimento da TURMA
        }
    }
    
    for course in courses:
        course_id = course.get('id')
        atendimento = course.get('atendimento_programa')
        
        if atendimento == 'atendimento_integral':
            faltas = faltas_por_componente.get(course_id, 0)
        else:
            faltas = 0
        
        attendance_data[course_id] = {
            'absences': faltas,
            'atendimento_programa': atendimento
        }
    
    # Gerar PDF
    try:
        pdf_buffer = generate_boletim_pdf(
            student=student,
            school=school,
            enrollment=enrollment,
            class_info=class_info,
            grades=grades,
            courses=courses,
            academic_year=actual_academic_year,
            mantenedora=mantenedora,
            dias_letivos_ano=dias_letivos_ano,
            calendario_letivo=calendario_letivo,
            attendance_data=attendance_data
        )
        
        filename = f"boletim_{student.get('full_name', 'aluno').replace(' ', '_')}_{actual_academic_year}.pdf"
        
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"'
            }
        )
    except Exception as e:
        logger.error(f"Erro ao gerar boletim: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")

@api_router.get("/documents/declaracao-matricula/{student_id}")
async def generate_declaracao_matricula(
    student_id: str, 
    request: Request, 
    academic_year: str = "2025",
    purpose: str = "fins comprobatórios"
):
    """
    Gera a Declaração de Matrícula do aluno em PDF
    
    Args:
        student_id: ID do aluno
        academic_year: Ano letivo
        purpose: Finalidade da declaração
    """
    current_user = await AuthMiddleware.get_current_user(request)
    
    # Buscar dados do aluno
    student = await db.students.find_one({"id": student_id}, {"_id": 0})
    if not student:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    
    # Validar permissão para gerar documento
    is_valid, error_message = await validate_student_for_document(student, current_user)
    if not is_valid:
        raise HTTPException(status_code=403, detail=error_message)
    
    # Verificar se o aluno está ativo
    student_status = student.get('status', 'active')
    if student_status != 'active':
        status_labels = {
            'inactive': 'Inativo',
            'transferred': 'Transferido',
            'graduated': 'Formado',
            'deceased': 'Falecido',
            'cancelled': 'Matrícula Cancelada',
            'dropout': 'Desistente'
        }
        status_label = status_labels.get(student_status, student_status)
        raise HTTPException(
            status_code=400, 
            detail=f"Não é possível gerar documentos para este aluno. Status atual: {status_label}. Apenas alunos com status 'Ativo' podem ter documentos gerados."
        )
    
    # Buscar matrícula
    enrollment = await db.enrollments.find_one({
        "student_id": student_id,
        "status": "active"
    }, {"_id": 0})
    
    if not enrollment:
        enrollment = await db.enrollments.find_one({
            "student_id": student_id
        }, {"_id": 0})
    
    # Se não houver matrícula, usar dados do próprio aluno
    if not enrollment:
        enrollment = {
            "student_id": student_id,
            "class_id": student.get("class_id"),
            "registration_number": student.get("enrollment_number", "N/A"),
            "status": "active",
            "academic_year": academic_year
        }
    
    # Garantir que o número de matrícula seja preenchido corretamente
    # Prioridade: registration_number do enrollment > enrollment_number do aluno
    if not enrollment.get("registration_number") or enrollment.get("registration_number") == "N/A":
        enrollment["registration_number"] = student.get("enrollment_number", "N/A")
    
    # Buscar turma
    class_id = enrollment.get("class_id") or student.get("class_id")
    class_info = await db.classes.find_one({"id": class_id}, {"_id": 0})
    if not class_info:
        class_info = {"name": "Turma não informada", "shift": "N/A", "school_id": student.get("school_id")}
    
    # Usar o ano letivo da turma em vez do parâmetro (a turma determina o ano)
    actual_academic_year = str(class_info.get("academic_year", academic_year))
    
    # Buscar escola
    school_id = class_info.get("school_id") or student.get("school_id")
    school = await db.schools.find_one({"id": school_id}, {"_id": 0})
    if not school:
        school = {
            "name": "Escola Municipal", 
            "cnpj": "N/A", 
            "phone": "N/A", 
            "city": "Município",
            "address": "Endereço não informado"
        }
    
    # Buscar dados da mantenedora
    mantenedora = await db.mantenedora.find_one({}, {"_id": 0})
    
    # Gerar PDF
    try:
        pdf_buffer = generate_declaracao_matricula_pdf(
            student=student,
            school=school,
            enrollment=enrollment,
            class_info=class_info,
            academic_year=actual_academic_year,
            purpose=purpose,
            mantenedora=mantenedora
        )
        
        filename = f"declaracao_matricula_{student.get('full_name', 'aluno').replace(' ', '_')}.pdf"
        
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"'
            }
        )
    except Exception as e:
        logger.error(f"Erro ao gerar declaração: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")

@api_router.get("/documents/declaracao-frequencia/{student_id}")
async def generate_declaracao_frequencia(
    student_id: str, 
    request: Request, 
    academic_year: str = "2025"
):
    """
    Gera a Declaração de Frequência do aluno em PDF
    
    Args:
        student_id: ID do aluno
        academic_year: Ano letivo
    """
    current_user = await AuthMiddleware.get_current_user(request)
    
    # Buscar dados do aluno
    student = await db.students.find_one({"id": student_id}, {"_id": 0})
    if not student:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    
    # Validar permissão para gerar documento
    is_valid, error_message = await validate_student_for_document(student, current_user)
    if not is_valid:
        raise HTTPException(status_code=403, detail=error_message)
    
    # Verificar se o aluno está ativo
    student_status = student.get('status', 'active')
    if student_status != 'active':
        status_labels = {
            'inactive': 'Inativo',
            'transferred': 'Transferido',
            'graduated': 'Formado',
            'deceased': 'Falecido',
            'cancelled': 'Matrícula Cancelada',
            'dropout': 'Desistente'
        }
        status_label = status_labels.get(student_status, student_status)
        raise HTTPException(
            status_code=400, 
            detail=f"Não é possível gerar documentos para este aluno. Status atual: {status_label}. Apenas alunos com status 'Ativo' podem ter documentos gerados."
        )
    
    # Buscar matrícula
    enrollment = await db.enrollments.find_one({
        "student_id": student_id,
        "status": "active"
    }, {"_id": 0})
    
    if not enrollment:
        enrollment = await db.enrollments.find_one({
            "student_id": student_id
        }, {"_id": 0})
    
    # Se não houver matrícula, usar dados do próprio aluno
    if not enrollment:
        enrollment = {
            "student_id": student_id,
            "class_id": student.get("class_id"),
            "registration_number": student.get("enrollment_number", "N/A"),
            "status": "active",
            "academic_year": academic_year
        }
    
    
    # Buscar turma
    class_id = enrollment.get("class_id") or student.get("class_id")
    class_info = await db.classes.find_one({"id": class_id}, {"_id": 0})
    if not class_info:
        class_info = {"name": "Turma não informada", "shift": "N/A", "school_id": student.get("school_id")}
    
    # Usar o ano letivo da turma em vez do parâmetro (a turma determina o ano)
    actual_academic_year = str(class_info.get("academic_year", academic_year))
    
    # Buscar escola
    school_id = class_info.get("school_id") or student.get("school_id")
    school = await db.schools.find_one({"id": school_id}, {"_id": 0})
    if not school:
        school = {
            "name": "Escola Municipal", 
            "cnpj": "N/A", 
            "phone": "N/A", 
            "city": "Município",
            "address": "Endereço não informado"
        }
    
    # Garantir que o número de matrícula seja preenchido corretamente
    if not enrollment.get("registration_number") or enrollment.get("registration_number") == "N/A":
        enrollment["registration_number"] = student.get("enrollment_number", "N/A")
    
    # Calcular dias letivos até a data de emissão
    academic_year_int = int(actual_academic_year) if actual_academic_year else datetime.now().year
    
    # Buscar calendário letivo
    calendario = await db.calendario_letivo.find_one(
        {"ano_letivo": academic_year_int, "school_id": None}, 
        {"_id": 0}
    )
    
    # Buscar eventos do calendário (feriados, sábados letivos, etc.)
    events = await db.calendar_events.find({
        "academic_year": academic_year_int
    }, {"_id": 0}).to_list(1000)
    
    eventos_nao_letivos = ['feriado_nacional', 'feriado_estadual', 'feriado_municipal', 'recesso_escolar']
    
    datas_nao_letivas = set()
    datas_sabados_letivos = set()
    
    for event in events:
        event_type = event.get('event_type', '')
        start_date_str = event.get('start_date')
        end_date_str = event.get('end_date') or start_date_str
        
        if not start_date_str:
            continue
        
        try:
            from datetime import timedelta
            start_date_ev = datetime.strptime(start_date_str[:10], '%Y-%m-%d').date()
            end_date_ev = datetime.strptime(end_date_str[:10], '%Y-%m-%d').date()
            
            current_ev = start_date_ev
            while current_ev <= end_date_ev:
                if event_type in eventos_nao_letivos:
                    datas_nao_letivas.add(current_ev)
                elif event_type == 'sabado_letivo':
                    datas_sabados_letivos.add(current_ev)
                elif event.get('is_school_day', False) and current_ev.weekday() == 5:
                    datas_sabados_letivos.add(current_ev)
                current_ev += timedelta(days=1)
        except (ValueError, TypeError):
            continue
    
    # Calcular dias letivos até hoje
    def calcular_dias_letivos_ate_data(calendario, data_limite):
        """Calcula dias letivos desde o início do ano até a data limite"""
        if not calendario:
            return 0
        
        inicio_str = calendario.get('bimestre_1_inicio')
        if not inicio_str:
            return 0
        
        try:
            from datetime import timedelta
            inicio = datetime.strptime(inicio_str[:10], '%Y-%m-%d').date()
            fim = data_limite
        except (ValueError, TypeError):
            return 0
        
        dias_letivos = 0
        current = inicio
        
        while current <= fim:
            dia_semana = current.weekday()
            
            if current in datas_sabados_letivos:
                dias_letivos += 1
            elif dia_semana < 5:  # Seg-Sex
                if current not in datas_nao_letivas:
                    dias_letivos += 1
            
            current += timedelta(days=1)
        
        return dias_letivos
    
    # Calcular dias letivos até hoje
    from datetime import date as date_type
    hoje = date_type.today()
    total_dias_letivos_ate_hoje = calcular_dias_letivos_ate_data(calendario, hoje)
    
    # Buscar todas as faltas do aluno
    attendances = await db.attendance.find({
        "student_id": student_id,
        "academic_year": actual_academic_year
    }, {"_id": 0}).to_list(500)
    
    # Calcular total de faltas
    total_faltas = sum(1 for a in attendances if a.get('status') in ['absent', 'F', 'A'])
    
    # Se não houver calendário configurado, usar fallback baseado na data
    if total_dias_letivos_ate_hoje == 0:
        # Calcular aproximadamente considerando 200 dias letivos por ano
        # e uma distribuição proporcional ao longo do ano
        inicio_ano = date_type(academic_year_int, 2, 1)  # Início típico em fevereiro
        fim_ano = date_type(academic_year_int, 12, 20)  # Fim típico em dezembro
        
        if hoje < inicio_ano:
            total_dias_letivos_ate_hoje = 0
        elif hoje > fim_ano:
            total_dias_letivos_ate_hoje = 200
        else:
            dias_transcorridos = (hoje - inicio_ano).days
            dias_totais_ano = (fim_ano - inicio_ano).days
            total_dias_letivos_ate_hoje = int(200 * dias_transcorridos / dias_totais_ano) if dias_totais_ano > 0 else 0
    
    # Calcular presenças: dias letivos - faltas
    total_days = total_dias_letivos_ate_hoje
    absent_days = total_faltas
    present_days = max(0, total_days - absent_days)
    
    # Calcular percentual de frequência
    frequency_percentage = (present_days / total_days * 100) if total_days > 0 else 100
    
    attendance_data = {
        "total_days": total_days,
        "present_days": present_days,
        "absent_days": absent_days,
        "frequency_percentage": frequency_percentage
    }
    
    # Buscar dados da mantenedora
    mantenedora = await db.mantenedora.find_one({}, {"_id": 0})
    
    # Gerar PDF
    try:
        pdf_buffer = generate_declaracao_frequencia_pdf(
            student=student,
            school=school,
            enrollment=enrollment,
            class_info=class_info,
            attendance_data=attendance_data,
            academic_year=actual_academic_year,
            period=f"ano letivo de {actual_academic_year}",
            mantenedora=mantenedora
        )
        
        filename = f"declaracao_frequencia_{student.get('full_name', 'aluno').replace(' ', '_')}.pdf"
        
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"'
            }
        )
    except Exception as e:
        logger.error(f"Erro ao gerar declaração de frequência: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")

@api_router.get("/documents/ficha-individual/{student_id}")
async def get_ficha_individual(
    student_id: str,
    academic_year: int = 2025,
    request: Request = None
):
    """Gera a Ficha Individual do Aluno em PDF"""
    current_user = await AuthMiddleware.get_current_user(request)
    
    # Buscar aluno
    student = await db.students.find_one({"id": student_id}, {"_id": 0})
    if not student:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    
    # Verificar se o aluno está ativo
    student_status = student.get('status', 'active')
    if student_status != 'active':
        status_labels = {
            'inactive': 'Inativo',
            'transferred': 'Transferido',
            'graduated': 'Formado',
            'deceased': 'Falecido',
            'cancelled': 'Matrícula Cancelada',
            'dropout': 'Desistente'
        }
        status_label = status_labels.get(student_status, student_status)
        raise HTTPException(
            status_code=400, 
            detail=f"Não é possível gerar documentos para este aluno. Status atual: {status_label}. Apenas alunos com status 'Ativo' podem ter documentos gerados."
        )
    
    # Buscar escola
    school = await db.schools.find_one({"id": student.get("school_id")}, {"_id": 0})
    if not school:
        school = {"name": "Escola Municipal", "city": "Município"}
    
    # Buscar turma
    class_info = await db.classes.find_one({"id": student.get("class_id")}, {"_id": 0})
    if not class_info:
        class_info = {"name": "N/A", "grade_level": "N/A", "shift": "N/A"}
    
    # Usar o ano letivo da turma em vez do parâmetro (a turma determina o ano)
    actual_academic_year = class_info.get("academic_year", academic_year)
    
    # Buscar matrícula
    enrollment = await db.enrollments.find_one(
        {"student_id": student_id, "academic_year": actual_academic_year},
        {"_id": 0}
    )
    if not enrollment:
        enrollment = {"registration_number": student.get("enrollment_number", "N/A")}
    
    # Buscar notas do aluno
    grades = await db.grades.find(
        {"student_id": student_id, "academic_year": actual_academic_year},
        {"_id": 0}
    ).to_list(100)
    
    # Buscar componentes curriculares da turma/escola
    # Filtrar por nível de ensino da turma
    nivel_ensino = class_info.get('nivel_ensino')
    grade_level = class_info.get('grade_level', '')
    grade_level_lower = grade_level.lower() if grade_level else ''
    school_id = student.get('school_id')
    
    # Se não tem nivel_ensino definido, inferir pelo grade_level
    if not nivel_ensino:
        if any(x in grade_level_lower for x in ['berçário', 'bercario', 'maternal', 'pré', 'pre']):
            nivel_ensino = 'educacao_infantil'
        elif any(x in grade_level_lower for x in ['1º ano', '2º ano', '3º ano', '4º ano', '5º ano', '1 ano', '2 ano', '3 ano', '4 ano', '5 ano']):
            nivel_ensino = 'fundamental_anos_iniciais'
        elif any(x in grade_level_lower for x in ['6º ano', '7º ano', '8º ano', '9º ano', '6 ano', '7 ano', '8 ano', '9 ano']):
            nivel_ensino = 'fundamental_anos_finais'
        elif any(x in grade_level_lower for x in ['eja', 'etapa']):
            if any(x in grade_level_lower for x in ['3', '4', 'final']):
                nivel_ensino = 'eja_final'
            else:
                nivel_ensino = 'eja'
        else:
            nivel_ensino = 'fundamental_anos_iniciais'  # Fallback
    
    # Log para debug
    logger.info(f"Ficha Individual: grade_level={grade_level}, nivel_ensino inferido={nivel_ensino}")
    
    # Determinar o tipo de atendimento/programa da TURMA (não da escola)
    turma_atendimento = class_info.get('atendimento_programa', '')
    turma_integral = turma_atendimento == 'atendimento_integral'
    logger.info(f"Ficha Individual: turma_atendimento={turma_atendimento}, turma_integral={turma_integral}")
    
    # Buscar componentes: globais (sem school_id) OU específicos da escola
    courses_filter = {
        "$and": [
            {"nivel_ensino": nivel_ensino},
            {"$or": [
                {"school_id": {"$exists": False}},
                {"school_id": None},
                {"school_id": ""},
                {"school_id": school_id}
            ]}
        ]
    }
    all_courses = await db.courses.find(courses_filter, {"_id": 0}).to_list(100)
    logger.info(f"Ficha Individual: {len(all_courses)} componentes encontrados para nivel_ensino={nivel_ensino}")
    
    # Filtrar componentes baseado no atendimento/programa da TURMA
    filtered_courses = []
    excluded_courses = []  # Para debug
    for course in all_courses:
        atendimento = course.get('atendimento_programa')
        course_grade_levels = course.get('grade_levels', [])
        course_name = course.get('name', 'N/A')
        
        # Componentes Transversais/Formativos aparecem em TODAS as turmas
        if atendimento == 'transversal_formativa':
            # Sempre incluir - é transversal a todas as turmas
            pass
        # Verificar se o componente é específico de Escola Integral
        elif atendimento == 'atendimento_integral':
            if not turma_integral:
                excluded_courses.append(f"{course_name} (excluído: atendimento_integral e turma não é integral)")
                continue
        # Verificar se o componente é de outro atendimento (AEE, reforço, etc)
        elif atendimento and atendimento not in ['atendimento_integral', 'transversal_formativa']:
            if turma_atendimento != atendimento:
                excluded_courses.append(f"{course_name} (excluído: atendimento={atendimento} diferente do atendimento da turma={turma_atendimento})")
                continue
        
        # Verificar se o componente é específico para certas séries
        if course_grade_levels:
            if grade_level and grade_level not in course_grade_levels:
                excluded_courses.append(f"{course_name} (excluído: grade_levels={course_grade_levels} não inclui {grade_level})")
                continue
        
        filtered_courses.append(course)
    
    # Log de debug detalhado
    logger.info(f"Ficha Individual: {len(filtered_courses)} componentes incluídos após filtragem")
    if excluded_courses:
        logger.warning(f"Ficha Individual: {len(excluded_courses)} componentes EXCLUÍDOS:")
        for exc in excluded_courses:
            logger.warning(f"  - {exc}")
    
    # Log dos componentes incluídos
    included_names = [c.get('name', 'N/A') for c in filtered_courses]
    logger.info(f"Ficha Individual: Componentes incluídos: {included_names}")
    
    # Ordenar por nome
    filtered_courses.sort(key=lambda x: x.get('name', ''))
    
    # Se não encontrar componentes após filtragem, buscar todos do nível sem atendimento específico
    if not filtered_courses:
        filtered_courses = await db.courses.find({
            "nivel_ensino": nivel_ensino,
            "$or": [
                {"atendimento_programa": None},
                {"atendimento_programa": {"$exists": False}}
            ]
        }, {"_id": 0}).to_list(100)
    
    courses = filtered_courses
    
    # Buscar dados de frequência do aluno
    # A estrutura de attendance é: {class_id, date, attendance_type, period, course_id, records: [{student_id, status}]}
    
    # Buscar todos os registros de frequência da turma do aluno
    class_id = student.get('class_id')
    attendance_records = await db.attendance.find(
        {"class_id": class_id, "academic_year": actual_academic_year},
        {"_id": 0}
    ).to_list(500)
    
    # Separar faltas por tipo: Regular (diário) e Escola Integral (por componente)
    faltas_regular = 0  # Faltas do período regular (frequência diária)
    faltas_por_componente = {}  # Faltas por componente (escola integral)
    
    for att_record in attendance_records:
        period = att_record.get('period', 'regular')
        course_id = att_record.get('course_id')
        attendance_type = att_record.get('attendance_type', 'daily')
        
        student_records = att_record.get('records', [])
        for sr in student_records:
            if sr.get('student_id') == student_id:
                status = sr.get('status', '')
                if status == 'F':  # Falta
                    if attendance_type == 'daily' and period == 'regular':
                        # Frequência diária regular - soma nas faltas gerais
                        faltas_regular += 1
                    elif course_id:
                        # Frequência por componente (escola integral)
                        if course_id not in faltas_por_componente:
                            faltas_por_componente[course_id] = 0
                        faltas_por_componente[course_id] += 1
    
    logger.info(f"Ficha Individual: Faltas Regular={faltas_regular}, Faltas por componente={faltas_por_componente}")
    
    # Preparar attendance_data com informações detalhadas
    # Adicionar metadados sobre faltas para o PDF generator usar
    attendance_data = {
        '_meta': {
            'faltas_regular': faltas_regular,
            'faltas_por_componente': faltas_por_componente,
            'is_escola_integral': turma_integral  # Usa atendimento da TURMA
        }
    }
    
    # Preencher dados por componente
    for course in courses:
        course_id = course.get('id')
        atendimento = course.get('atendimento_programa')
        
        if atendimento == 'atendimento_integral':
            # Componente de escola integral - faltas individuais
            faltas = faltas_por_componente.get(course_id, 0)
        else:
            # Componente regular - todas as faltas vão para Língua Portuguesa
            faltas = 0  # Será preenchido apenas para Língua Portuguesa no PDF
        
        attendance_data[course_id] = {
            'absences': faltas,
            'atendimento_programa': atendimento
        }
    
    # Buscar dados da mantenedora
    mantenedora = await db.mantenedora.find_one({}, {"_id": 0})
    
    # Buscar calendário letivo para dias letivos e data fim do 4º bimestre
    calendario_letivo = await db.calendario_letivo.find_one({
        "ano_letivo": actual_academic_year
    }, {"_id": 0})
    
    # Calcular dias letivos reais com base nos períodos bimestrais e eventos
    dias_letivos_calculados = None
    if calendario_letivo:
        # Buscar eventos do calendário para o ano
        eventos = await db.calendar_events.find({
            "year": actual_academic_year
        }, {"_id": 0}).to_list(500)
        
        # Identificar datas não letivas (feriados, recessos, etc.)
        from datetime import datetime, timedelta
        datas_nao_letivas = set()
        datas_sabados_letivos = set()
        
        for evento in eventos:
            tipo = evento.get('type', '')
            data_str = evento.get('date', '')
            
            # Tipos que removem dias letivos
            if tipo in ['feriado', 'recesso', 'ferias', 'nao_letivo', 'ponto_facultativo', 'conselho']:
                try:
                    data = datetime.strptime(data_str[:10], '%Y-%m-%d').date()
                    datas_nao_letivas.add(data)
                except:
                    pass
            # Sábados letivos
            elif tipo == 'sabado_letivo':
                try:
                    data = datetime.strptime(data_str[:10], '%Y-%m-%d').date()
                    datas_sabados_letivos.add(data)
                except:
                    pass
        
        def calcular_dias_letivos_periodo(inicio_str, fim_str):
            if not inicio_str or not fim_str:
                return 0
            try:
                inicio = datetime.strptime(str(inicio_str)[:10], '%Y-%m-%d').date()
                fim = datetime.strptime(str(fim_str)[:10], '%Y-%m-%d').date()
            except:
                return 0
            
            dias = 0
            current = inicio
            while current <= fim:
                dia_semana = current.weekday()
                if dia_semana < 5:  # Segunda a sexta
                    if current not in datas_nao_letivas:
                        dias += 1
                elif dia_semana == 5:  # Sábado
                    if current in datas_sabados_letivos:
                        dias += 1
                current += timedelta(days=1)
            return dias
        
        b1 = calcular_dias_letivos_periodo(calendario_letivo.get('bimestre_1_inicio'), calendario_letivo.get('bimestre_1_fim'))
        b2 = calcular_dias_letivos_periodo(calendario_letivo.get('bimestre_2_inicio'), calendario_letivo.get('bimestre_2_fim'))
        b3 = calcular_dias_letivos_periodo(calendario_letivo.get('bimestre_3_inicio'), calendario_letivo.get('bimestre_3_fim'))
        b4 = calcular_dias_letivos_periodo(calendario_letivo.get('bimestre_4_inicio'), calendario_letivo.get('bimestre_4_fim'))
        
        dias_letivos_calculados = b1 + b2 + b3 + b4
        logger.info(f"Ficha Individual: Dias letivos calculados = {dias_letivos_calculados} (B1={b1}, B2={b2}, B3={b3}, B4={b4})")
    
    # Adicionar dias letivos calculados ao calendário
    if calendario_letivo:
        calendario_letivo['dias_letivos_calculados'] = dias_letivos_calculados
    
    # Gerar PDF
    try:
        pdf_buffer = generate_ficha_individual_pdf(
            student=student,
            school=school,
            class_info=class_info,
            enrollment=enrollment,
            academic_year=actual_academic_year,
            grades=grades,
            courses=courses,
            attendance_data=attendance_data,
            mantenedora=mantenedora,
            calendario_letivo=calendario_letivo
        )
        
        filename = f"ficha_individual_{student.get('full_name', 'aluno').replace(' ', '_')}.pdf"
        
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"'
            }
        )
    except Exception as e:
        logger.error(f"Erro ao gerar ficha individual: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")

@api_router.get("/documents/certificado/{student_id}")
async def get_certificado(
    student_id: str,
    academic_year: int = 2025,
    request: Request = None
):
    """
    Gera o Certificado de Conclusão em PDF.
    Uso exclusivo para turmas do 9º Ano e EJA 4ª Etapa.
    """
    current_user = await AuthMiddleware.get_current_user(request)
    
    # Buscar aluno
    student = await db.students.find_one({"id": student_id}, {"_id": 0})
    if not student:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    
    # Buscar escola
    school = await db.schools.find_one({"id": student.get("school_id")}, {"_id": 0})
    if not school:
        school = {"name": "Escola Municipal", "city": "Município"}
    
    # Buscar turma
    class_info = await db.classes.find_one({"id": student.get("class_id")}, {"_id": 0})
    if not class_info:
        class_info = {"name": "N/A", "grade_level": "N/A", "shift": "N/A"}
    
    # Validar se a turma é elegível para certificado (9º Ano ou EJA 4ª Etapa)
    grade_level = str(class_info.get('grade_level', '')).lower()
    education_level = str(class_info.get('education_level', '')).lower()
    
    is_9ano = '9' in grade_level and 'ano' in grade_level
    is_eja_4etapa = ('eja' in education_level or 'eja' in grade_level) and ('4' in grade_level or 'etapa' in grade_level)
    
    if not (is_9ano or is_eja_4etapa):
        raise HTTPException(
            status_code=400, 
            detail="Certificado disponível apenas para turmas do 9º Ano ou EJA 4ª Etapa"
        )
    
    # Buscar matrícula
    enrollment = await db.enrollments.find_one(
        {"student_id": student_id, "academic_year": academic_year},
        {"_id": 0}
    )
    if not enrollment:
        enrollment = {"registration_number": student.get("enrollment_number", "N/A")}
    
    # Buscar mantenedora (para o brasão)
    mantenedora = await db.mantenedora.find_one({}, {"_id": 0})
    
    # Gerar PDF
    try:
        pdf_buffer = generate_certificado_pdf(
            student=student,
            school=school,
            class_info=class_info,
            enrollment=enrollment,
            academic_year=academic_year,
            mantenedora=mantenedora
        )
        
        filename = f"certificado_{student.get('full_name', 'aluno').replace(' ', '_')}.pdf"
        
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"'
            }
        )
    except Exception as e:
        logger.error(f"Erro ao gerar certificado: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")

@api_router.get("/documents/promotion/{class_id}")
async def get_livro_promocao_pdf(
    class_id: str,
    academic_year: int = 2025,
    request: Request = None
):
    """
    Gera o PDF do Livro de Promoção para uma turma.
    
    O Livro de Promoção contém:
    - Lista de alunos com notas de todos os bimestres
    - Recuperações semestrais
    - Total de pontos e média final por componente
    - Resultado final (Aprovado/Reprovado/etc)
    """
    current_user = await AuthMiddleware.get_current_user(request)
    
    try:
        # Buscar turma
        class_info = await db.classes.find_one({"id": class_id}, {"_id": 0})
        if not class_info:
            raise HTTPException(status_code=404, detail="Turma não encontrada")
        
        # Buscar escola
        school = await db.schools.find_one({"id": class_info.get("school_id")}, {"_id": 0})
        if not school:
            school = {"name": "Escola Municipal"}
        
        # Buscar mantenedora
        mantenedora = await db.mantenedora.find_one({}, {"_id": 0})
        
        # Buscar matrículas da turma
        enrollments = await db.enrollments.find({
            "class_id": class_id
        }, {"_id": 0}).to_list(1000)
        
        if not enrollments:
            raise HTTPException(status_code=404, detail="Nenhum aluno matriculado nesta turma")
        
        student_ids = [e.get("student_id") for e in enrollments]
        
        # Buscar dados dos alunos
        students = await db.students.find({
            "id": {"$in": student_ids}
        }, {"_id": 0}).to_list(1000)
        
        # Criar mapa de alunos por ID
        students_map = {s.get("id"): s for s in students}
        
        # Buscar componentes curriculares
        nivel_ensino = class_info.get('education_level', '')
        grade_level = class_info.get('grade_level', '')
        
        courses = await db.courses.find({
            "$or": [
                {"grade_levels": grade_level},
                {"grade_levels": {"$size": 0}},
                {"grade_levels": {"$exists": False}}
            ]
        }, {"_id": 0}).to_list(100)
        
        # Se não encontrar, buscar todos
        if not courses:
            courses = await db.courses.find({}, {"_id": 0}).to_list(100)
        
        # Criar mapa de componentes
        courses_map = {c.get("id"): c for c in courses}
        
        # Processar dados de cada aluno
        students_data = []
        
        for enrollment in enrollments:
            student_id = enrollment.get("student_id")
            student = students_map.get(student_id)
            
            if not student:
                continue
            
            # Buscar notas do aluno
            grades = await db.grades.find({
                "student_id": student_id,
                "academic_year": academic_year
            }, {"_id": 0}).to_list(500)
            
            # Organizar notas por componente
            grades_by_component = {}
            
            for grade in grades:
                course_id = grade.get("course_id")
                if course_id not in grades_by_component:
                    grades_by_component[course_id] = {
                        "b1": None, "b2": None, "b3": None, "b4": None,
                        "rec1": None, "rec2": None,
                        "totalPoints": None, "finalAverage": None
                    }
                
                # As notas já vêm com os campos b1, b2, b3, b4, rec_s1, rec_s2
                grades_by_component[course_id]["b1"] = grade.get("b1")
                grades_by_component[course_id]["b2"] = grade.get("b2")
                grades_by_component[course_id]["b3"] = grade.get("b3")
                grades_by_component[course_id]["b4"] = grade.get("b4")
                grades_by_component[course_id]["rec1"] = grade.get("rec_s1")
                grades_by_component[course_id]["rec2"] = grade.get("rec_s2")
            
            # Calcular total e média para cada componente
            for course_id, comp_grades in grades_by_component.items():
                b1 = comp_grades.get("b1") or 0
                b2 = comp_grades.get("b2") or 0
                b3 = comp_grades.get("b3") or 0
                b4 = comp_grades.get("b4") or 0
                rec1 = comp_grades.get("rec1")
                rec2 = comp_grades.get("rec2")
                
                # Aplicar recuperação 1º semestre (substitui menor entre B1 e B2)
                if rec1 is not None:
                    if b1 <= b2 and rec1 > b1:
                        b1 = rec1
                    elif b2 < b1 and rec1 > b2:
                        b2 = rec1
                
                # Aplicar recuperação 2º semestre (substitui menor entre B3 e B4)
                if rec2 is not None:
                    if b3 <= b4 and rec2 > b3:
                        b3 = rec2
                    elif b4 < b3 and rec2 > b4:
                        b4 = rec2
                
                # Calcular total e média
                total = b1 + b2 + b3 + b4
                media = total / 4
                
                comp_grades["totalPoints"] = total
                comp_grades["finalAverage"] = media
            
            # Determinar resultado final
            result = "CURSANDO"
            status = (enrollment.get("status") or "").lower()
            
            if status in ["desistencia", "desistente"]:
                result = "DESISTENTE"
            elif status in ["transferencia", "transferido"]:
                result = "TRANSFERIDO"
            else:
                # Verificar médias
                averages = [g.get("finalAverage") for g in grades_by_component.values() if g.get("finalAverage") is not None]
                if averages:
                    all_approved = all(avg >= 6 for avg in averages)
                    if all_approved:
                        result = "APROVADO"
                    else:
                        failed_count = sum(1 for avg in averages if avg < 6)
                        if failed_count >= 3:
                            result = "REPROVADO"
            
            # Adicionar dados do aluno
            students_data.append({
                "studentId": student_id,
                "studentName": student.get("full_name", ""),
                "sex": "M" if student.get("sex", "").lower() in ["m", "masculino"] else "F",
                "grades": grades_by_component,
                "result": result
            })
        
        # Ordenar por nome
        students_data.sort(key=lambda x: x.get("studentName", ""))
        
        # Gerar PDF
        pdf_buffer = generate_livro_promocao_pdf(
            school=school,
            class_info=class_info,
            students_data=students_data,
            courses=courses,
            academic_year=academic_year,
            mantenedora=mantenedora
        )
        
        # Gerar nome do arquivo
        turma_nome = class_info.get("name", "turma").replace(" ", "_")
        filename = f"livro_promocao_{turma_nome}_{academic_year}.pdf"
        
        return Response(
            content=pdf_buffer.getvalue(),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao gerar Livro de Promoção: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")

@api_router.get("/documents/batch/{class_id}/{document_type}")
async def get_batch_documents(
    class_id: str,
    document_type: str,
    academic_year: int = 2025,
    request: Request = None
):
    """
    Gera um único PDF consolidado com todos os documentos da turma.
    
    document_type: 'boletim', 'ficha_individual', 'certificado'
    """
    from PyPDF2 import PdfMerger
    
    current_user = await AuthMiddleware.get_current_user(request)
    
    # Validar tipo de documento
    valid_types = ['boletim', 'ficha_individual', 'certificado']
    if document_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Tipo de documento inválido. Use: {', '.join(valid_types)}")
    
    # Buscar turma
    class_info = await db.classes.find_one({"id": class_id}, {"_id": 0})
    if not class_info:
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    
    # Validar elegibilidade para certificado (9º Ano ou EJA 4ª Etapa)
    if document_type == 'certificado':
        grade_level = str(class_info.get('grade_level', '')).lower()
        education_level = str(class_info.get('education_level', '')).lower()
        
        is_9ano = '9' in grade_level and 'ano' in grade_level
        is_eja_4etapa = ('eja' in education_level or 'eja' in grade_level) and ('4' in grade_level or 'etapa' in grade_level)
        
        if not (is_9ano or is_eja_4etapa):
            raise HTTPException(
                status_code=400, 
                detail="Certificado disponível apenas para turmas do 9º Ano ou EJA 4ª Etapa"
            )
    
    # Buscar escola da turma
    school = await db.schools.find_one({"id": class_info.get("school_id")}, {"_id": 0})
    if not school:
        school = {"name": "Escola Municipal"}
    
    # Buscar mantenedora
    mantenedora = await db.mantenedora.find_one({}, {"_id": 0})
    
    # Buscar calendário letivo para data fim do 4º bimestre
    calendario_letivo = await db.calendar.find_one({
        "year": academic_year
    }, {"_id": 0})
    
    # Buscar alunos matriculados na turma
    enrollments = await db.enrollments.find(
        {"class_id": class_id, "status": "active", "academic_year": academic_year},
        {"_id": 0}
    ).to_list(1000)
    
    if not enrollments:
        raise HTTPException(status_code=404, detail="Nenhum aluno matriculado nesta turma")
    
    student_ids = [e['student_id'] for e in enrollments]
    enrollment_map = {e['student_id']: e for e in enrollments}
    
    # Buscar dados dos alunos
    students = await db.students.find(
        {"id": {"$in": student_ids}},
        {"_id": 0}
    ).sort("full_name", 1).to_list(1000)
    
    if not students:
        raise HTTPException(status_code=404, detail="Alunos não encontrados")
    
    # Buscar componentes curriculares para o boletim
    courses = []
    if document_type in ['boletim', 'ficha_individual']:
        courses = await db.courses.find({}, {"_id": 0}).to_list(100)
    
    # Criar merger para juntar os PDFs
    merger = PdfMerger()
    
    try:
        for student in students:
            enrollment = enrollment_map.get(student['id'], {})
            
            # Buscar notas do aluno se necessário
            grades = []
            if document_type in ['boletim', 'ficha_individual']:
                grades = await db.grades.find(
                    {"student_id": student['id'], "academic_year": academic_year},
                    {"_id": 0}
                ).to_list(100)
            
            # Gerar PDF individual
            if document_type == 'boletim':
                pdf_buffer = generate_boletim_pdf(
                    student=student,
                    school=school,
                    enrollment=enrollment,
                    class_info=class_info,
                    grades=grades,
                    courses=courses,
                    academic_year=str(academic_year),
                    mantenedora=mantenedora,
                    calendario_letivo=calendario_letivo
                )
            elif document_type == 'ficha_individual':
                # Buscar frequência do aluno
                attendances = await db.attendance.find(
                    {"class_id": class_id, "academic_year": academic_year, "records.student_id": student['id']},
                    {"_id": 0}
                ).to_list(1000)
                
                attendance_data = {"present": 0, "absent": 0, "justified": 0, "total": 0}
                for att in attendances:
                    for record in att.get('records', []):
                        if record['student_id'] == student['id']:
                            attendance_data['total'] += 1
                            if record['status'] == 'P':
                                attendance_data['present'] += 1
                            elif record['status'] == 'F':
                                attendance_data['absent'] += 1
                            elif record['status'] == 'J':
                                attendance_data['justified'] += 1
                
                pdf_buffer = generate_ficha_individual_pdf(
                    student=student,
                    school=school,
                    enrollment=enrollment,
                    class_info=class_info,
                    grades=grades,
                    courses=courses,
                    attendance_data=attendance_data,
                    academic_year=academic_year,
                    mantenedora=mantenedora,
                    calendario_letivo=calendario_letivo
                )
            elif document_type == 'certificado':
                pdf_buffer = generate_certificado_pdf(
                    student=student,
                    school=school,
                    class_info=class_info,
                    enrollment=enrollment,
                    academic_year=academic_year,
                    mantenedora=mantenedora
                )
            
            # Adicionar ao merger
            merger.append(pdf_buffer)
        
        # Gerar PDF final consolidado
        output_buffer = BytesIO()
        merger.write(output_buffer)
        merger.close()
        output_buffer.seek(0)
        
        # Nome do arquivo
        class_name = class_info.get('name', 'turma').replace(' ', '_')
        type_names = {
            'boletim': 'Boletins',
            'ficha_individual': 'Fichas_Individuais',
            'certificado': 'Certificados'
        }
        filename = f"{type_names.get(document_type, document_type)}_{class_name}_{academic_year}.pdf"
        
        return StreamingResponse(
            output_buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"'
            }
        )
        
    except Exception as e:
        logger.error(f"Erro ao gerar documentos em lote: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")

# ============= PRÉ-MATRÍCULA ENDPOINTS (PÚBLICOS) =============

@api_router.post("/pre-matricula", response_model=PreMatricula, status_code=status.HTTP_201_CREATED)
async def create_pre_matricula(pre_matricula: PreMatriculaCreate):
    """Cria uma nova pré-matrícula (rota pública - não requer autenticação)"""
    # Verifica se a escola existe e tem pré-matrícula ativa
    school = await db.schools.find_one(
        {"id": pre_matricula.school_id, "pre_matricula_ativa": True, "status": "active"},
        {"_id": 0}
    )
    
    if not school:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Escola não encontrada ou pré-matrícula não está ativa"
        )
    
    # Cria a pré-matrícula
    pre_matricula_obj = PreMatricula(**pre_matricula.model_dump())
    doc = pre_matricula_obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    
    await db.pre_matriculas.insert_one(doc)
    
    return pre_matricula_obj

@api_router.get("/pre-matriculas", response_model=List[PreMatricula])
async def list_pre_matriculas(
    request: Request,
    school_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = 100
):
    """Lista pré-matrículas (apenas admin, secretário, diretor)"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor'])(request)
    
    query = {}
    
    # Filtro por escola
    if school_id:
        query['school_id'] = school_id
    elif current_user['role'] not in ['admin']:
        # Não-admin só vê das escolas vinculadas
        query['school_id'] = {"$in": current_user['school_ids']}
    
    # Filtro por status
    if status_filter:
        query['status'] = status_filter
    
    pre_matriculas = await db.pre_matriculas.find(
        query, {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    
    return pre_matriculas

@api_router.get("/pre-matriculas/{pre_matricula_id}", response_model=PreMatricula)
async def get_pre_matricula(pre_matricula_id: str, request: Request):
    """Busca pré-matrícula por ID"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor'])(request)
    
    pre_matricula = await db.pre_matriculas.find_one(
        {"id": pre_matricula_id}, {"_id": 0}
    )
    
    if not pre_matricula:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pré-matrícula não encontrada"
        )
    
    # Verifica acesso à escola
    if current_user['role'] not in ['admin']:
        if pre_matricula['school_id'] not in current_user['school_ids']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acesso negado a esta pré-matrícula"
            )
    
    return pre_matricula

@api_router.put("/pre-matriculas/{pre_matricula_id}/status")
async def update_pre_matricula_status(
    pre_matricula_id: str,
    request: Request,
    new_status: str = Query(..., description="Novo status: analisando, aprovada, rejeitada"),
    rejection_reason: Optional[str] = None
):
    """Atualiza status da pré-matrícula"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor'])(request)
    
    if new_status not in ['analisando', 'aprovada', 'rejeitada']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status inválido"
        )
    
    update_data = {
        "status": new_status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "analyzed_by": current_user['id'],
        "analyzed_at": datetime.now(timezone.utc).isoformat()
    }
    
    if new_status == 'rejeitada' and rejection_reason:
        update_data['rejection_reason'] = rejection_reason
    
    result = await db.pre_matriculas.update_one(
        {"id": pre_matricula_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pré-matrícula não encontrada"
        )
    
    return {"message": "Status atualizado com sucesso"}

@api_router.post("/pre-matriculas/{pre_matricula_id}/convert")
async def convert_pre_matricula_to_student(
    pre_matricula_id: str,
    request: Request,
    class_id: Optional[str] = Query(None, description="ID da turma para matricular o aluno")
):
    """
    Converte uma pré-matrícula aprovada em um novo aluno.
    Cria o registro do aluno com os dados da pré-matrícula.
    """
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor'])(request)
    
    # Buscar a pré-matrícula
    pre_matricula = await db.pre_matriculas.find_one(
        {"id": pre_matricula_id}, {"_id": 0}
    )
    
    if not pre_matricula:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pré-matrícula não encontrada"
        )
    
    # Verificar se a pré-matrícula está aprovada
    if pre_matricula.get('status') != 'aprovada':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas pré-matrículas aprovadas podem ser convertidas em alunos"
        )
    
    # Verificar se já foi convertida
    if pre_matricula.get('converted_student_id'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta pré-matrícula já foi convertida em aluno"
        )
    
    # Buscar a escola para obter o próximo número de matrícula
    school = await db.schools.find_one(
        {"id": pre_matricula['school_id']}, {"_id": 0}
    )
    
    if not school:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escola não encontrada"
        )
    
    # Gerar número de matrícula único
    current_year = datetime.now().year
    student_count = await db.students.count_documents({"school_id": pre_matricula['school_id']})
    enrollment_number = f"{current_year}{str(student_count + 1).zfill(5)}"
    
    # Mapear parentesco para tipo de responsável legal
    parentesco_map = {
        'mae': 'mother',
        'pai': 'father',
        'avo': 'other',
        'tio': 'other',
        'responsavel': 'other',
        'outro': 'other'
    }
    
    # Criar o documento do aluno
    student_id = str(uuid.uuid4())
    student_data = {
        "id": student_id,
        "school_id": pre_matricula['school_id'],
        "enrollment_number": enrollment_number,
        "full_name": pre_matricula.get('aluno_nome'),
        "birth_date": pre_matricula.get('aluno_data_nascimento'),
        "sex": pre_matricula.get('aluno_sexo'),
        "cpf": pre_matricula.get('aluno_cpf'),
        
        # Responsável
        "guardian_name": pre_matricula.get('responsavel_nome'),
        "guardian_cpf": pre_matricula.get('responsavel_cpf'),
        "guardian_phone": pre_matricula.get('responsavel_telefone'),
        "guardian_relationship": pre_matricula.get('responsavel_parentesco'),
        "legal_guardian_type": parentesco_map.get(pre_matricula.get('responsavel_parentesco', ''), 'other'),
        
        # Turma (se fornecida)
        "class_id": class_id,
        
        # Observações
        "observations": f"Aluno criado a partir da pré-matrícula. Email do responsável: {pre_matricula.get('responsavel_email', 'N/A')}",
        
        # Status
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Inserir o aluno
    await db.students.insert_one(student_data)
    
    # Atualizar a pré-matrícula como convertida
    await db.pre_matriculas.update_one(
        {"id": pre_matricula_id},
        {"$set": {
            "status": "convertida",
            "converted_student_id": student_id,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    # Registrar no histórico do aluno
    history_doc = {
        "id": str(uuid.uuid4()),
        "student_id": student_id,
        "school_id": pre_matricula['school_id'],
        "school_name": school.get('name', 'N/A'),
        "class_id": class_id,
        "class_name": None,
        "action_type": "matricula",
        "previous_status": None,
        "new_status": "active",
        "observations": f"Matrícula criada a partir de pré-matrícula online (ID: {pre_matricula_id})",
        "user_id": current_user['id'],
        "user_name": current_user.get('full_name', current_user.get('email')),
        "action_date": datetime.now(timezone.utc).isoformat()
    }
    
    # Se tiver turma, buscar o nome
    if class_id:
        class_doc = await db.classes.find_one({"id": class_id}, {"_id": 0, "name": 1})
        if class_doc:
            history_doc["class_name"] = class_doc.get('name')
    
    await db.student_history.insert_one(history_doc)
    
    # Registrar no audit log
    await db.audit_logs.insert_one({
        "id": str(uuid.uuid4()),
        "action": "create",
        "collection": "students",
        "document_id": student_id,
        "user_id": current_user['id'],
        "user_email": current_user.get('email'),
        "user_role": current_user.get('role'),
        "user_name": current_user.get('full_name'),
        "school_id": pre_matricula['school_id'],
        "school_name": school.get('name'),
        "description": f"Aluno '{pre_matricula.get('aluno_nome')}' criado a partir de pré-matrícula online",
        "new_value": {
            "full_name": pre_matricula.get('aluno_nome'),
            "enrollment_number": enrollment_number,
            "pre_matricula_id": pre_matricula_id
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": "info",
        "category": "academic"
    })
    
    return {
        "message": "Pré-matrícula convertida em aluno com sucesso",
        "student_id": student_id,
        "enrollment_number": enrollment_number,
        "student_name": pre_matricula.get('aluno_nome')
    }

# ============= ANNOUNCEMENT ENDPOINTS =============

def can_user_create_announcement(user: dict, recipient: dict) -> bool:
    """Verifica se o usuário pode criar um aviso para os destinatários especificados"""
    user_role = user.get('role', '')
    user_school_links = user.get('school_links', [])
    user_school_ids = [link['school_id'] for link in user_school_links]
    
    recipient_type = recipient.get('type', '')
    
    # Admin pode enviar para qualquer um
    if user_role == 'admin':
        return True
    
    # Secretário, Diretor, Coordenador - limitado à escola
    if user_role in ['secretario', 'diretor', 'coordenador']:
        if recipient_type == 'school':
            # Só pode enviar para escolas vinculadas
            target_schools = recipient.get('school_ids', [])
            return all(s in user_school_ids for s in target_schools)
        elif recipient_type == 'class':
            # Classes precisam ser da escola vinculada (verificar no momento da criação)
            return True
        elif recipient_type == 'individual':
            # Pode enviar para usuários da escola
            return True
        elif recipient_type == 'role':
            # Pode enviar para roles dentro da escola
            return True
    
    # Professor - limitado às turmas
    if user_role == 'professor':
        if recipient_type in ['class', 'individual']:
            # Verificar se as turmas são vinculadas ao professor
            return True
        return False
    
    return False

async def get_announcement_target_users(db, recipient: dict, sender: dict) -> List[str]:
    """Obtém a lista de user_ids que devem receber o aviso"""
    target_user_ids = []
    recipient_type = recipient.get('type', '')
    sender_role = sender.get('role', '')
    sender_school_ids = [link['school_id'] for link in sender.get('school_links', [])]
    
    if recipient_type == 'individual':
        # Usuários específicos
        target_user_ids = recipient.get('user_ids', [])
    
    elif recipient_type == 'role':
        # Todos os usuários com os papéis especificados
        target_roles = recipient.get('target_roles', [])
        query = {'role': {'$in': target_roles}, 'status': 'active'}
        
        # Se não for admin, limitar à escola
        if sender_role != 'admin':
            query['school_links.school_id'] = {'$in': sender_school_ids}
        
        users = await db.users.find(query, {'_id': 0, 'id': 1}).to_list(10000)
        target_user_ids = [u['id'] for u in users]
    
    elif recipient_type == 'school':
        # Todos os usuários das escolas
        school_ids = recipient.get('school_ids', [])
        users = await db.users.find(
            {'school_links.school_id': {'$in': school_ids}, 'status': 'active'},
            {'_id': 0, 'id': 1}
        ).to_list(10000)
        target_user_ids = [u['id'] for u in users]
    
    elif recipient_type == 'class':
        # Alunos/responsáveis das turmas (via matrículas)
        class_ids = recipient.get('class_ids', [])
        enrollments = await db.enrollments.find(
            {'class_id': {'$in': class_ids}, 'status': 'active'},
            {'_id': 0, 'student_id': 1}
        ).to_list(10000)
        
        student_ids = [e['student_id'] for e in enrollments]
        
        # Buscar usuários dos alunos (se houver) e responsáveis
        students = await db.students.find(
            {'id': {'$in': student_ids}},
            {'_id': 0, 'user_id': 1, 'guardian_id': 1}
        ).to_list(10000)
        
        for student in students:
            if student.get('user_id'):
                target_user_ids.append(student['user_id'])
            # Buscar usuário do responsável
            if student.get('guardian_id'):
                guardian = await db.guardians.find_one(
                    {'id': student['guardian_id']},
                    {'_id': 0, 'user_id': 1}
                )
                if guardian and guardian.get('user_id'):
                    target_user_ids.append(guardian['user_id'])
    
    return list(set(target_user_ids))  # Remover duplicatas

@api_router.get("/notifications/unread-count", response_model=NotificationCount)
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

# ============= FIM USER PROFILE ENDPOINTS =============

# ============= DEBUG ENDPOINT - COMPONENTES CURRICULARES =============

@api_router.get("/debug/courses/{class_id}")
async def debug_courses_for_class(class_id: str, request: Request = None):
    """
    Debug: Retorna informações detalhadas sobre os componentes curriculares
    que seriam usados no boletim de uma turma específica.
    """
    current_user = await AuthMiddleware.get_current_user(request)
    
    # Buscar turma
    class_info = await db.classes.find_one({"id": class_id}, {"_id": 0})
    if not class_info:
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    
    # Buscar escola
    school_id = class_info.get("school_id")
    school = await db.schools.find_one({"id": school_id}, {"_id": 0})
    if not school:
        raise HTTPException(status_code=404, detail="Escola não encontrada")
    
    # Determinar nível de ensino e série
    nivel_ensino = class_info.get('nivel_ensino')
    grade_level = class_info.get('grade_level', '')
    grade_level_lower = grade_level.lower() if grade_level else ''
    
    # Inferir nivel_ensino se não definido
    if not nivel_ensino:
        if any(x in grade_level_lower for x in ['berçário', 'bercario', 'maternal', 'pré', 'pre']):
            nivel_ensino = 'educacao_infantil'
        elif any(x in grade_level_lower for x in ['1º ano', '2º ano', '3º ano', '4º ano', '5º ano', '1 ano', '2 ano', '3 ano', '4 ano', '5 ano']):
            nivel_ensino = 'fundamental_anos_iniciais'
        elif any(x in grade_level_lower for x in ['6º ano', '7º ano', '8º ano', '9º ano', '6 ano', '7 ano', '8 ano', '9 ano']):
            nivel_ensino = 'fundamental_anos_finais'
        elif any(x in grade_level_lower for x in ['eja', 'etapa']):
            if any(x in grade_level_lower for x in ['3', '4', 'final']):
                nivel_ensino = 'eja_final'
            else:
                nivel_ensino = 'eja'
    
    escola_integral = school.get('atendimento_integral', False)
    
    # Determinar o tipo de atendimento/programa da TURMA
    turma_atendimento = class_info.get('atendimento_programa', '')
    turma_integral = turma_atendimento == 'atendimento_integral'
    
    # Buscar todos os componentes do nível
    courses_query = {}
    if nivel_ensino:
        courses_query['nivel_ensino'] = nivel_ensino
    
    all_courses = await db.courses.find(courses_query, {"_id": 0}).to_list(100)
    
    # Filtrar componentes
    filtered_courses = []
    excluded_courses = []
    
    for course in all_courses:
        atendimento = course.get('atendimento_programa')
        course_grade_levels = course.get('grade_levels', [])
        course_name = course.get('name', 'N/A')
        
        # Verificar atendimento - baseado na TURMA, não na escola
        if atendimento == 'transversal_formativa':
            pass
        elif atendimento == 'atendimento_integral':
            if not turma_integral:
                excluded_courses.append({
                    "name": course_name,
                    "reason": f"atendimento_integral e turma não é integral (turma_atendimento={turma_atendimento})",
                    "course_data": course
                })
                continue
        elif atendimento and atendimento not in ['atendimento_integral', 'transversal_formativa']:
            if turma_atendimento != atendimento:
                excluded_courses.append({
                    "name": course_name,
                    "reason": f"atendimento={atendimento} diferente do atendimento da turma={turma_atendimento}",
                    "course_data": course
                })
                continue
        
        # Verificar grade_levels
        if course_grade_levels:
            if grade_level and grade_level not in course_grade_levels:
                excluded_courses.append({
                    "name": course_name,
                    "reason": f"grade_levels={course_grade_levels} não inclui '{grade_level}'",
                    "course_data": course
                })
                continue
        
        filtered_courses.append(course)
    
    return {
        "class_info": {
            "id": class_id,
            "name": class_info.get('name'),
            "grade_level": grade_level,
            "nivel_ensino_original": class_info.get('nivel_ensino'),
            "nivel_ensino_inferido": nivel_ensino,
            "atendimento_programa": turma_atendimento  # Adicionado
        },
        "school_info": {
            "id": school_id,
            "name": school.get('name'),
            "atendimento_integral": escola_integral,
            "atendimentos": {k: v for k, v in school.items() if k.startswith('atendimento') or k.endswith('_integral')}
        },
        "turma_info": {
            "atendimento_programa": turma_atendimento,
            "turma_integral": turma_integral
        },
        "total_courses_found": len(all_courses),
        "total_courses_filtered": len(filtered_courses),
        "total_courses_excluded": len(excluded_courses),
        "included_courses": [{"name": c.get('name'), "id": c.get('id'), "grade_levels": c.get('grade_levels', []), "atendimento": c.get('atendimento_programa')} for c in filtered_courses],
        "excluded_courses": excluded_courses
    }

# ============= MANUTENÇÃO E LIMPEZA =============

@api_router.get("/maintenance/orphan-check")
async def check_orphan_data(request: Request):
    """
    Verifica dados órfãos no sistema.
    Apenas admin pode executar.
    """
    current_user = await AuthMiddleware.require_roles(['admin'])(request)
    
    results = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'orphans': [],
        'summary': {
            'enrollments': 0,
            'grades': 0,
            'school_assignments': 0,
            'teacher_assignments': 0,
            'total': 0
        }
    }
    
    # Verifica matrículas órfãs
    enrollments = await db.enrollments.find({}, {"_id": 0, "id": 1, "student_id": 1, "school_id": 1, "class_id": 1}).to_list(10000)
    for enrollment in enrollments:
        issues = []
        student = await db.students.find_one({"id": enrollment.get('student_id')})
        if not student:
            issues.append("Aluno não encontrado")
        school = await db.schools.find_one({"id": enrollment.get('school_id')})
        if not school:
            issues.append("Escola não encontrada")
        if enrollment.get('class_id'):
            class_doc = await db.classes.find_one({"id": enrollment.get('class_id')})
            if not class_doc:
                issues.append("Turma não encontrada")
        if issues:
            results['orphans'].append({'type': 'enrollment', 'id': enrollment.get('id'), 'issues': issues})
            results['summary']['enrollments'] += 1
    
    # Verifica lotações órfãs
    assignments = await db.school_assignments.find({}, {"_id": 0, "id": 1, "staff_id": 1, "school_id": 1}).to_list(10000)
    for assignment in assignments:
        issues = []
        staff = await db.staff.find_one({"id": assignment.get('staff_id')})
        if not staff:
            issues.append("Servidor não encontrado")
        school = await db.schools.find_one({"id": assignment.get('school_id')})
        if not school:
            issues.append("Escola não encontrada")
        if issues:
            results['orphans'].append({'type': 'school_assignment', 'id': assignment.get('id'), 'issues': issues})
            results['summary']['school_assignments'] += 1
    
    # Verifica alocações de professores órfãs
    teacher_assignments = await db.teacher_assignments.find({}, {"_id": 0, "id": 1, "staff_id": 1, "school_id": 1, "class_id": 1}).to_list(10000)
    for assignment in teacher_assignments:
        issues = []
        staff = await db.staff.find_one({"id": assignment.get('staff_id')})
        if not staff:
            issues.append("Servidor não encontrado")
        school = await db.schools.find_one({"id": assignment.get('school_id')})
        if not school:
            issues.append("Escola não encontrada")
        class_doc = await db.classes.find_one({"id": assignment.get('class_id')})
        if not class_doc:
            issues.append("Turma não encontrada")
        if issues:
            results['orphans'].append({'type': 'teacher_assignment', 'id': assignment.get('id'), 'issues': issues})
            results['summary']['teacher_assignments'] += 1
    
    results['summary']['total'] = (
        results['summary']['enrollments'] +
        results['summary']['grades'] +
        results['summary']['school_assignments'] +
        results['summary']['teacher_assignments']
    )
    
    return results

@api_router.delete("/maintenance/orphan-cleanup")
async def cleanup_orphan_data(request: Request, dry_run: bool = True):
    """
    Remove dados órfãos do sistema.
    Apenas admin pode executar.
    Use dry_run=false para executar a limpeza real.
    """
    current_user = await AuthMiddleware.require_roles(['admin'])(request)
    
    # Primeiro, obtém lista de órfãos
    orphan_check = await check_orphan_data(request)
    
    if dry_run:
        return {
            'mode': 'dry_run',
            'message': 'Nenhuma alteração foi feita. Use dry_run=false para executar a limpeza.',
            'would_delete': orphan_check['summary']
        }
    
    deleted = {
        'enrollments': 0,
        'school_assignments': 0,
        'teacher_assignments': 0,
        'total': 0
    }
    
    for orphan in orphan_check['orphans']:
        try:
            if orphan['type'] == 'enrollment':
                await db.enrollments.delete_one({"id": orphan['id']})
                deleted['enrollments'] += 1
            elif orphan['type'] == 'school_assignment':
                await db.school_assignments.delete_one({"id": orphan['id']})
                deleted['school_assignments'] += 1
            elif orphan['type'] == 'teacher_assignment':
                await db.teacher_assignments.delete_one({"id": orphan['id']})
                deleted['teacher_assignments'] += 1
        except Exception as e:
            pass
    
    deleted['total'] = deleted['enrollments'] + deleted['school_assignments'] + deleted['teacher_assignments']
    
    # Registra auditoria da limpeza
    await audit_service.log(
        action='delete',
        collection='system',
        user=current_user,
        request=request,
        description=f"Executou limpeza de dados órfãos: {deleted['total']} registros removidos",
        extra_data=deleted
    )
    
    return {
        'mode': 'executed',
        'deleted': deleted
    }

@api_router.get("/maintenance/duplicate-courses")
async def check_duplicate_courses(request: Request):
    """
    Verifica componentes curriculares duplicados.
    Apenas admin pode executar.
    """
    current_user = await AuthMiddleware.require_roles(['admin'])(request)
    
    courses = await db.courses.find({}, {"_id": 0}).to_list(500)
    
    # Agrupar por nome + nivel_ensino
    groups = {}
    for course in courses:
        key = (course.get('name', ''), course.get('nivel_ensino', ''))
        if key not in groups:
            groups[key] = []
        groups[key].append(course)
    
    # Encontrar duplicados
    duplicates = []
    for key, courses_list in groups.items():
        if len(courses_list) > 1:
            duplicates.append({
                'name': key[0],
                'nivel_ensino': key[1],
                'count': len(courses_list),
                'courses': courses_list
            })
    
    return {
        'total_duplicates': len(duplicates),
        'duplicates': duplicates
    }

@api_router.post("/maintenance/consolidate-courses")
async def consolidate_duplicate_courses(request: Request, dry_run: bool = True):
    """
    Consolida componentes curriculares duplicados.
    Apenas admin pode executar.
    Une os grade_levels de componentes com mesmo nome e nivel_ensino.
    """
    current_user = await AuthMiddleware.require_roles(['admin'])(request)
    
    # Obter duplicados
    dup_check = await check_duplicate_courses(request)
    
    if dry_run:
        return {
            'mode': 'dry_run',
            'message': 'Nenhuma alteração foi feita. Use dry_run=false para executar.',
            'would_consolidate': dup_check
        }
    
    consolidated = []
    
    for dup in dup_check['duplicates']:
        courses_list = dup['courses']
        if len(courses_list) < 2:
            continue
        
        # Escolher o primeiro como base
        base_course = courses_list[0]
        base_id = base_course.get('id')
        
        # Unir grade_levels de todos os duplicados
        all_grade_levels = set()
        for c in courses_list:
            grade_levels = c.get('grade_levels', [])
            if grade_levels:
                all_grade_levels.update(grade_levels)
        
        # Atualizar o componente base com todos os grade_levels
        if all_grade_levels:
            sorted_levels = sorted(list(all_grade_levels), key=lambda x: (
                0 if 'º Ano' in x else 1,
                int(''.join(filter(str.isdigit, x)) or 0)
            ))
            await db.courses.update_one(
                {"id": base_id},
                {"$set": {"grade_levels": sorted_levels}}
            )
        
        # Remover os duplicados (manter apenas o primeiro)
        removed_ids = []
        for c in courses_list[1:]:
            await db.courses.delete_one({"id": c.get('id')})
            removed_ids.append(c.get('id'))
        
        consolidated.append({
            'name': dup['name'],
            'nivel_ensino': dup['nivel_ensino'],
            'kept_id': base_id,
            'removed_ids': removed_ids,
            'unified_grade_levels': sorted_levels if all_grade_levels else []
        })
    
    # Registra auditoria
    await audit_service.log(
        action='update',
        collection='courses',
        user=current_user,
        request=request,
        description=f"Consolidou {len(consolidated)} componentes curriculares duplicados",
        extra_data={'consolidated': consolidated}
    )
    
    return {
        'mode': 'executed',
        'consolidated': consolidated,
        'total': len(consolidated)
    }

# ============= UNIDADE MANTENEDORA ENDPOINTS =============

@api_router.get("/mantenedora", response_model=Mantenedora)
async def get_mantenedora(request: Request = None):
    """Busca a Unidade Mantenedora (única) - Endpoint público para exibição de dados institucionais"""
    # Não requer autenticação - dados públicos da instituição
    mantenedora = await db.mantenedora.find_one({}, {"_id": 0})
    
    if not mantenedora:
        # Criar uma mantenedora padrão se não existir
        default_mantenedora = {
            "id": str(uuid.uuid4()),
            "nome": "Prefeitura Municipal de Floresta do Araguaia",
            "cnpj": "",
            "codigo_inep": "",
            "natureza_juridica": "Pública Municipal",
            "cep": "",
            "logradouro": "",
            "numero": "",
            "complemento": "",
            "bairro": "",
            "municipio": "Floresta do Araguaia",
            "estado": "PA",
            "telefone": "",
            "celular": "",
            "email": "",
            "site": "",
            "responsavel_nome": "",
            "responsavel_cargo": "Prefeito(a)",
            "responsavel_cpf": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None
        }
        await db.mantenedora.insert_one(default_mantenedora)
        return default_mantenedora
    
    return mantenedora

@api_router.put("/mantenedora", response_model=Mantenedora)
async def update_mantenedora(
    mantenedora_update: MantenedoraUpdate,
    request: Request = None
):
    """Atualiza a Unidade Mantenedora"""
    current_user = await AuthMiddleware.get_current_user(request)
    
    # Verificar permissão (apenas admin e semed podem editar)
    if current_user.get('role') not in ['admin', 'semed']:
        raise HTTPException(status_code=403, detail="Sem permissão para editar a mantenedora")
    
    # Buscar mantenedora existente
    mantenedora = await db.mantenedora.find_one({}, {"_id": 0})
    
    if not mantenedora:
        # Criar se não existir
        mantenedora = {
            "id": str(uuid.uuid4()),
            "nome": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.mantenedora.insert_one(mantenedora)
    
    # Atualizar campos
    update_data = mantenedora_update.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.mantenedora.update_one(
        {"id": mantenedora["id"]},
        {"$set": update_data}
    )
    
    # Retornar atualizado
    updated = await db.mantenedora.find_one({"id": mantenedora["id"]}, {"_id": 0})
    return updated

# ============= AUDIT LOG ENDPOINTS =============

@api_router.get("/audit-logs")
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
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'semed'])(request)
    
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

@api_router.get("/audit-logs/user/{user_id}")
async def get_user_audit_logs(user_id: str, request: Request, limit: int = 20):
    """Retorna atividades recentes de um usuário específico"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'semed'])(request)
    
    logs = await audit_service.get_user_activity(user_id, limit)
    return {'items': logs}

@api_router.get("/audit-logs/document/{collection}/{document_id}")
async def get_document_audit_history(collection: str, document_id: str, request: Request):
    """Retorna histórico de alterações de um documento específico"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'semed', 'diretor'])(request)
    
    logs = await audit_service.get_document_history(collection, document_id)
    return {'items': logs}

@api_router.get("/audit-logs/critical")
async def get_critical_audit_events(request: Request, hours: int = 24):
    """Retorna eventos críticos das últimas X horas"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'semed'])(request)
    
    logs = await audit_service.get_critical_events(hours)
    return {'items': logs, 'hours': hours}

@api_router.get("/audit-logs/stats")
async def get_audit_stats(request: Request, days: int = 7):
    """Retorna estatísticas de auditoria"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'semed'])(request)
    
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

# Include modular routers FIRST (take precedence over legacy routes in api_router)
# PATCH 4.x: Routers modulares têm preferência sobre rotas legadas
users_router = setup_users_router(db, audit_service, sandbox_db)
schools_router = setup_schools_router(db, audit_service, sandbox_db)
courses_router = setup_courses_router(db, audit_service)
classes_router = setup_classes_router(db, audit_service, sandbox_db)
guardians_router = setup_guardians_router(db, audit_service)
enrollments_router = setup_enrollments_router(db, audit_service)
sync_router = setup_sync_router(db, AuthMiddleware)
medical_certificates_router = setup_medical_certificates_router(db, AuthMiddleware)
students_router = setup_students_router(db, audit_service, sandbox_db)
grades_router = setup_grades_router(db, audit_service, verify_academic_year_open_or_raise, verify_bimestre_edit_deadline_or_raise, sandbox_db)
attendance_router = setup_attendance_router(db, audit_service, sandbox_db)
calendar_router = setup_calendar_router(db, audit_service, sandbox_db)
staff_router = setup_staff_router(db, audit_service, None, sandbox_db)  # ftp_upload_func=None for now
announcements_router = setup_announcements_router(db, audit_service, connection_manager, sandbox_db)
analytics_router = setup_analytics_router(db, audit_service, sandbox_db)
class_schedule_router = setup_class_schedule_router(db, audit_service, sandbox_db)

# Routers modulares (prioridade)
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

# Dashboard de Acompanhamento de Diários
diary_dashboard_router = create_diary_dashboard_router()
app.include_router(diary_dashboard_router, prefix="/api")

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

# CORS middleware
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
