from fastapi import FastAPI, APIRouter, HTTPException, status, Depends, Request, UploadFile, File, WebSocket, WebSocketDisconnect, Response
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
    AuditLog, AuditLogFilter
)
from auth_utils import (
    hash_password, verify_password, create_access_token, 
    create_refresh_token, decode_token, get_school_ids_from_links
)
from auth_middleware import AuthMiddleware
from audit_service import audit_service
from pdf_generator import (
    generate_boletim_pdf,
    generate_declaracao_matricula_pdf,
    generate_declaracao_frequencia_pdf,
    generate_ficha_individual_pdf,
    generate_certificado_pdf,
    generate_class_details_pdf,
    generate_livro_promocao_pdf
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
    setup_enrollments_router
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'sigesc_db')]

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
        
        logger.info("Índices MongoDB criados/verificados com sucesso")
    except Exception as e:
        logger.error(f"Erro ao criar índices MongoDB: {e}")

# Create uploads directory
UPLOADS_DIR = ROOT_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

# Mount static files for uploads
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
    # Busca usuário
    user_doc = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    
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
    
    # Determina role efetivo baseado nas lotações (para roles que podem ter lotação)
    effective_role = user.role
    effective_school_links = user.school_links or []
    
    if user.role in ['professor', 'secretario', 'coordenador', 'diretor']:
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
        "school_ids": school_ids
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
        description=f"Login realizado: {user.full_name}"
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
    """Renova access token usando refresh token"""
    payload = decode_token(refresh_request.refresh_token)
    
    if not payload or payload.get('type') != 'refresh':
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido"
        )
    
    user_id = payload.get('sub')
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
    new_refresh_token = create_refresh_token({"sub": user.id})
    
    # Retorna usuário com role efetivo
    user_response_data = user.model_dump(exclude={'password_hash'})
    user_response_data['role'] = effective_role
    user_response_data['school_links'] = effective_school_links
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        user=UserResponse(**user_response_data)
    )

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
        {"_id": 0, "student_id": 1, "enrollment_number": 1}
    ).to_list(1000)
    
    student_ids = [e['student_id'] for e in enrollments]
    enrollment_map = {e['student_id']: e.get('enrollment_number') for e in enrollments}
    
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
            
            students_list.append({
                "id": student.get('id'),
                "full_name": student.get('full_name'),
                "enrollment_number": enrollment_map.get(student.get('id')),
                "birth_date": student.get('birth_date'),
                "guardian_name": guardian_name,
                "guardian_phone": guardian_phone
            })
    
    return {
        "class": class_doc,
        "school": school,
        "teachers": teachers,
        "students": students_list,
        "total_students": len(students_list)
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

@api_router.get("/students")
async def list_students(request: Request, school_id: Optional[str] = None, class_id: Optional[str] = None, skip: int = 0, limit: int = 5000):
    """Lista alunos"""
    current_user = await AuthMiddleware.get_current_user(request)
    
    # Constrói filtro
    filter_query = {}
    
    if current_user['role'] in ['admin', 'semed']:
        if school_id:
            filter_query['school_id'] = school_id
        if class_id:
            filter_query['class_id'] = class_id
    else:
        # Outros papéis veem apenas das escolas vinculadas
        if school_id and school_id in current_user['school_ids']:
            filter_query['school_id'] = school_id
        else:
            filter_query['school_id'] = {"$in": current_user['school_ids']}
        
        if class_id:
            filter_query['class_id'] = class_id
    
    students = await db.students.find(filter_query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
    
    # Garante que todos os campos existam (compatibilidade com registros antigos)
    for student in students:
        student.setdefault('full_name', '')
        student.setdefault('inep_code', None)
        student.setdefault('sex', None)
        student.setdefault('nationality', 'Brasileira')
        student.setdefault('birth_city', None)
        student.setdefault('birth_state', None)
        student.setdefault('color_race', None)
        student.setdefault('cpf', None)
        student.setdefault('rg', None)
        student.setdefault('nis', None)
        student.setdefault('status', 'active')
        student.setdefault('authorized_persons', [])
        student.setdefault('benefits', [])
        student.setdefault('disabilities', [])
        student.setdefault('documents_urls', [])
    
    return students

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
    
    # Admin e SEMED têm acesso a todas as escolas
    if current_user.get('role') not in ['admin', 'semed']:
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


@api_router.get("/students/{student_id}/history")
async def get_student_history(student_id: str, request: Request):
    """Retorna o histórico de movimentações do aluno"""
    current_user = await AuthMiddleware.get_current_user(request)
    
    # Verifica se aluno existe
    student = await db.students.find_one({"id": student_id}, {"_id": 0, "school_id": 1})
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aluno não encontrado"
        )
    
    # Busca histórico ordenado por data (mais recente primeiro)
    history = await db.student_history.find(
        {"student_id": student_id},
        {"_id": 0}
    ).sort("action_date", -1).to_list(100)
    
    return history


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

@api_router.get("/grades")
async def list_grades(
    request: Request, 
    student_id: Optional[str] = None,
    class_id: Optional[str] = None,
    course_id: Optional[str] = None,
    academic_year: Optional[int] = None
):
    """Lista notas com filtros opcionais"""
    current_user = await AuthMiddleware.get_current_user(request)
    
    filter_query = {}
    
    if student_id:
        filter_query['student_id'] = student_id
    if class_id:
        filter_query['class_id'] = class_id
    if course_id:
        filter_query['course_id'] = course_id
    if academic_year:
        filter_query['academic_year'] = academic_year
    
    grades = await db.grades.find(filter_query, {"_id": 0}).to_list(1000)
    return grades


@api_router.get("/grades/by-class/{class_id}/{course_id}")
async def get_grades_by_class(class_id: str, course_id: str, request: Request, academic_year: Optional[int] = None):
    """Busca todas as notas de uma turma para um componente curricular"""
    current_user = await AuthMiddleware.get_current_user(request)
    
    if not academic_year:
        academic_year = datetime.now().year
    
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
    
    # Busca notas existentes
    grades = await db.grades.find(
        {"class_id": class_id, "course_id": course_id, "academic_year": academic_year},
        {"_id": 0}
    ).to_list(1000)
    
    # Mapeia notas por student_id
    grades_map = {g['student_id']: g for g in grades}
    
    # Monta lista com todos os alunos e suas notas
    result = []
    for student in students:
        grade = grades_map.get(student['id'], {
            'student_id': student['id'],
            'class_id': class_id,
            'course_id': course_id,
            'academic_year': academic_year,
            'b1': None, 'b2': None, 'b3': None, 'b4': None,
            'rec_s1': None, 'rec_s2': None,
            'recovery': None, 'final_average': None, 'status': 'cursando'
        })
        # Adiciona enrollment_number da matrícula se disponível
        student_data = {
            'id': student['id'],
            'full_name': student['full_name'],
            'enrollment_number': enrollment_numbers.get(student['id']) or student.get('enrollment_number')
        }
        result.append({
            'student': student_data,
            'grade': grade
        })
    
    return result


@api_router.get("/grades/by-student/{student_id}")
async def get_grades_by_student(student_id: str, request: Request, academic_year: Optional[int] = None):
    """Busca todas as notas de um aluno"""
    current_user = await AuthMiddleware.get_current_user(request)
    
    if not academic_year:
        academic_year = datetime.now().year
    
    # Busca dados do aluno
    student = await db.students.find_one({"id": student_id}, {"_id": 0})
    if not student:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    
    # Busca notas do aluno
    grades = await db.grades.find(
        {"student_id": student_id, "academic_year": academic_year},
        {"_id": 0}
    ).to_list(100)
    
    # Busca componentes curriculares para enriquecer dados
    course_ids = list(set(g['course_id'] for g in grades))
    courses = await db.courses.find({"id": {"$in": course_ids}}, {"_id": 0}).to_list(100)
    courses_map = {c['id']: c for c in courses}
    
    # Enriquece notas com dados do componente
    for grade in grades:
        course = courses_map.get(grade['course_id'], {})
        grade['course_name'] = course.get('name', 'N/A')
    
    return {
        'student': student,
        'grades': grades,
        'academic_year': academic_year
    }


@api_router.post("/grades", response_model=Grade)
async def create_grade(grade_data: GradeCreate, request: Request):
    """Cria ou atualiza nota de um aluno"""
    # Coordenador PODE editar notas (área do diário)
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'professor', 'coordenador'])(request)
    
    # Verifica se já existe nota para este aluno/turma/componente/ano
    existing = await db.grades.find_one({
        "student_id": grade_data.student_id,
        "class_id": grade_data.class_id,
        "course_id": grade_data.course_id,
        "academic_year": grade_data.academic_year
    }, {"_id": 0})
    
    if existing:
        # Atualiza nota existente
        update_data = grade_data.model_dump(exclude_unset=True, exclude={'student_id', 'class_id', 'course_id', 'academic_year'})
        update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
        
        await db.grades.update_one(
            {"id": existing['id']},
            {"$set": update_data}
        )
        
        # Recalcula média
        updated = await calculate_and_update_grade(db, existing['id'])
        return Grade(**updated)
    
    # Cria nova nota
    grade_dict = grade_data.model_dump()
    grade_dict['id'] = str(uuid.uuid4())
    grade_dict['created_at'] = datetime.now(timezone.utc).isoformat()
    grade_dict['final_average'] = None
    grade_dict['status'] = 'cursando'
    
    await db.grades.insert_one(grade_dict)
    
    # Calcula média se houver notas
    if any([grade_data.b1, grade_data.b2, grade_data.b3, grade_data.b4]):
        updated = await calculate_and_update_grade(db, grade_dict['id'])
        return Grade(**updated)
    
    return Grade(**grade_dict)


@api_router.put("/grades/{grade_id}", response_model=Grade)
async def update_grade(grade_id: str, grade_update: GradeUpdate, request: Request):
    """Atualiza notas de um aluno"""
    # Coordenador PODE editar notas (área do diário)
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'professor', 'coordenador'])(request)
    
    grade = await db.grades.find_one({"id": grade_id}, {"_id": 0})
    if not grade:
        raise HTTPException(status_code=404, detail="Nota não encontrada")
    
    update_data = grade_update.model_dump(exclude_unset=True)
    update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
    
    await db.grades.update_one(
        {"id": grade_id},
        {"$set": update_data}
    )
    
    # Recalcula média
    updated = await calculate_and_update_grade(db, grade_id)
    return Grade(**updated)


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

@api_router.post("/upload")
async def upload_file(
    request: Request, 
    file: UploadFile = File(...), 
    file_type: Optional[str] = "default"
):
    """Upload de arquivo (foto, documento, laudo, etc.) para servidor externo via FTP"""
    current_user = await AuthMiddleware.get_current_user(request)
    
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

@api_router.get("/calendar/events")
async def list_calendar_events(
    request: Request,
    academic_year: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    event_type: Optional[str] = None
):
    """Lista eventos do calendário com filtros opcionais"""
    await AuthMiddleware.get_current_user(request)
    
    query = {}
    
    if academic_year:
        query["academic_year"] = academic_year
    
    if start_date and end_date:
        # Eventos que intersectam com o período
        query["$or"] = [
            {"start_date": {"$gte": start_date, "$lte": end_date}},
            {"end_date": {"$gte": start_date, "$lte": end_date}},
            {"$and": [{"start_date": {"$lte": start_date}}, {"end_date": {"$gte": end_date}}]}
        ]
    elif start_date:
        query["end_date"] = {"$gte": start_date}
    elif end_date:
        query["start_date"] = {"$lte": end_date}
    
    if event_type:
        query["event_type"] = event_type
    
    events = await db.calendar_events.find(query, {"_id": 0}).sort("start_date", 1).to_list(1000)
    return events

@api_router.get("/calendar/events/{event_id}")
async def get_calendar_event(event_id: str, request: Request):
    """Obtém um evento específico"""
    await AuthMiddleware.get_current_user(request)
    
    event = await db.calendar_events.find_one({"id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    return event

@api_router.post("/calendar/events", status_code=status.HTTP_201_CREATED)
async def create_calendar_event(event: CalendarEventCreate, request: Request):
    """Cria um novo evento no calendário"""
    await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
    
    # Define cor padrão se não fornecida
    event_dict = event.model_dump()
    if not event_dict.get('color'):
        event_dict['color'] = EVENT_COLORS.get(event_dict['event_type'], '#6B7280')
    
    new_event = {
        "id": str(uuid.uuid4()),
        **event_dict,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.calendar_events.insert_one(new_event)
    return await db.calendar_events.find_one({"id": new_event["id"]}, {"_id": 0})

@api_router.put("/calendar/events/{event_id}")
async def update_calendar_event(event_id: str, event: CalendarEventUpdate, request: Request):
    """Atualiza um evento existente"""
    await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
    
    existing = await db.calendar_events.find_one({"id": event_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    
    update_data = {k: v for k, v in event.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.calendar_events.update_one({"id": event_id}, {"$set": update_data})
    return await db.calendar_events.find_one({"id": event_id}, {"_id": 0})

@api_router.delete("/calendar/events/{event_id}")
async def delete_calendar_event(event_id: str, request: Request):
    """Remove um evento do calendário"""
    await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
    
    result = await db.calendar_events.delete_one({"id": event_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    return {"message": "Evento removido com sucesso"}

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
                elif event_type == 'sabado_letivo':
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
    
    # Admin e secretário sempre podem editar
    if user_role in ['admin', 'secretario']:
        return {
            "ano_letivo": ano_letivo,
            "pode_editar_todos": True,
            "motivo": "Usuário com permissão de administração",
            "bimestres": [
                {"bimestre": i, "pode_editar": True, "data_limite": None, "motivo": "Permissão administrativa"}
                for i in range(1, 5)
            ]
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
    calendario = await db.calendario_letivo.find_one(
        {"ano_letivo": ano_letivo},
        {"_id": 0}
    )
    
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

@api_router.get("/attendance/settings/{academic_year}")
async def get_attendance_settings(academic_year: int, request: Request):
    """Obtém configurações de frequência para o ano letivo"""
    await AuthMiddleware.get_current_user(request)
    
    settings = await db.attendance_settings.find_one(
        {"academic_year": academic_year}, 
        {"_id": 0}
    )
    
    if not settings:
        # Retorna configurações padrão
        return {
            "academic_year": academic_year,
            "allow_future_dates": False
        }
    
    return settings

@api_router.put("/attendance/settings/{academic_year}")
async def update_attendance_settings(academic_year: int, request: Request, allow_future_dates: bool):
    """Atualiza configurações de frequência (apenas Admin/Secretário)"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
    
    existing = await db.attendance_settings.find_one({"academic_year": academic_year})
    
    if existing:
        await db.attendance_settings.update_one(
            {"academic_year": academic_year},
            {"$set": {
                "allow_future_dates": allow_future_dates,
                "updated_by": current_user['id'],
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
    else:
        await db.attendance_settings.insert_one({
            "id": str(uuid.uuid4()),
            "academic_year": academic_year,
            "allow_future_dates": allow_future_dates,
            "updated_by": current_user['id'],
            "updated_at": datetime.now(timezone.utc).isoformat()
        })
    
    return await db.attendance_settings.find_one({"academic_year": academic_year}, {"_id": 0})

@api_router.get("/attendance/check-date/{date}")
async def check_attendance_date(date: str, request: Request):
    """
    Verifica se uma data é válida para lançamento de frequência.
    Considera: dia letivo, feriados, finais de semana, permissão de data futura.
    """
    current_user = await AuthMiddleware.get_current_user(request)
    
    # Verifica se é data futura
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    is_future = date > today
    
    # Busca configurações do ano
    year = int(date.split("-")[0])
    settings = await db.attendance_settings.find_one({"academic_year": year}, {"_id": 0})
    allow_future = settings.get("allow_future_dates", False) if settings else False
    
    # Verifica se usuário pode lançar em data futura
    can_use_future = current_user['role'] in ['admin', 'secretario'] and allow_future
    
    # Verifica eventos do calendário nessa data (feriados, etc.)
    events = await db.calendar_events.find({
        "start_date": {"$lte": date},
        "end_date": {"$gte": date}
    }, {"_id": 0}).to_list(100)
    
    # Verifica se é dia letivo
    is_school_day = True
    blocking_events = []
    
    for event in events:
        if not event.get('is_school_day', True):
            is_school_day = False
            blocking_events.append(event)
    
    # Verifica se é final de semana
    date_obj = datetime.strptime(date, "%Y-%m-%d")
    is_weekend = date_obj.weekday() in [5, 6]  # Sábado=5, Domingo=6
    
    # Determina se pode lançar
    can_record = is_school_day and not is_weekend
    if is_future and not can_use_future:
        can_record = False
    
    return {
        "date": date,
        "is_school_day": is_school_day,
        "is_weekend": is_weekend,
        "is_future": is_future,
        "allow_future_dates": allow_future,
        "can_record": can_record,
        "blocking_events": blocking_events,
        "message": (
            "Data futura não permitida" if is_future and not can_use_future
            else "Final de semana" if is_weekend
            else "Dia não letivo" if not is_school_day
            else "Liberado para lançamento"
        )
    }

@api_router.get("/attendance/by-class/{class_id}/{date}")
async def get_attendance_by_class(
    class_id: str, 
    date: str, 
    request: Request,
    course_id: Optional[str] = None,
    period: str = "regular"
):
    """
    Obtém frequência de uma turma em uma data.
    Se course_id fornecido, busca frequência por componente curricular.
    """
    await AuthMiddleware.get_current_user(request)
    
    # Busca dados da turma
    turma = await db.classes.find_one({"id": class_id}, {"_id": 0})
    if not turma:
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    
    # Determina tipo de frequência baseado no nível de ensino
    education_level = turma.get('education_level', '')
    
    # Anos Iniciais = frequência diária, Anos Finais = por componente
    if education_level in ['fundamental_anos_iniciais', 'eja']:
        attendance_type = 'daily'
    else:
        attendance_type = 'by_component'
    
    # Para Escola Integral e Aulas Complementares, sempre por componente
    if period in ['integral', 'complementar']:
        attendance_type = 'by_component'
    
    # Busca frequência existente
    query = {
        "class_id": class_id,
        "date": date,
        "period": period
    }
    
    if attendance_type == 'by_component' and course_id:
        query["course_id"] = course_id
    
    attendance = await db.attendance.find_one(query, {"_id": 0})
    
    # Busca alunos matriculados na turma através da coleção enrollments
    # Extrai o ano letivo da data selecionada
    academic_year = int(date.split("-")[0])
    
    # Busca matrículas ativas na turma
    enrollments = await db.enrollments.find(
        {"class_id": class_id, "status": "active", "academic_year": academic_year},
        {"_id": 0, "student_id": 1, "enrollment_number": 1}
    ).to_list(1000)
    
    # Coleta IDs dos alunos matriculados
    student_ids = [e['student_id'] for e in enrollments]
    enrollment_numbers = {e['student_id']: e.get('enrollment_number') for e in enrollments}
    
    # Busca dados dos alunos matriculados
    # Não filtra por status do aluno pois a matrícula ativa já indica que está estudando
    students = []
    if student_ids:
        students_cursor = await db.students.find(
            {"id": {"$in": student_ids}},
            {"_id": 0, "id": 1, "full_name": 1, "enrollment_number": 1}
        ).sort("full_name", 1).to_list(1000)
        students = students_cursor
    
    # Monta resposta com alunos e seus status de frequência
    records_map = {}
    if attendance and attendance.get('records'):
        for record in attendance['records']:
            records_map[record['student_id']] = record['status']
    
    result = {
        "class_id": class_id,
        "class_name": turma.get('name'),
        "education_level": education_level,
        "date": date,
        "attendance_type": attendance_type,
        "course_id": course_id,
        "period": period,
        "attendance_id": attendance.get('id') if attendance else None,
        "observations": attendance.get('observations') if attendance else None,
        "students": [
            {
                "id": s['id'],
                "full_name": s['full_name'],
                "enrollment_number": enrollment_numbers.get(s['id']) or s.get('enrollment_number'),
                "status": records_map.get(s['id'], None)  # None = não lançado
            }
            for s in students
        ]
    }
    
    return result

@api_router.post("/attendance")
async def save_attendance(attendance: AttendanceCreate, request: Request):
    """Salva ou atualiza frequência de uma turma"""
    # Coordenador PODE editar frequência (área do diário)
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'professor', 'coordenador'])(request)
    user_role = current_user.get('role', '')
    
    # Verifica se o ano letivo está aberto (apenas para não-admins)
    if user_role != 'admin':
        class_doc = await db.classes.find_one(
            {"id": attendance.class_id},
            {"_id": 0, "school_id": 1}
        )
        if class_doc:
            await verify_academic_year_open_or_raise(
                class_doc['school_id'],
                attendance.academic_year
            )
    
    # Verifica a data limite de edição por bimestre (apenas para não-admins e não-secretarios)
    if user_role not in ['admin', 'secretario']:
        # Determina qual bimestre a data de frequência pertence
        calendario = await db.calendario_letivo.find_one(
            {"ano_letivo": attendance.academic_year},
            {"_id": 0}
        )
        if calendario:
            attendance_date = attendance.date
            for i in range(1, 5):
                inicio = calendario.get(f"bimestre_{i}_inicio")
                fim = calendario.get(f"bimestre_{i}_fim")
                if inicio and fim and attendance_date >= inicio and attendance_date <= fim:
                    await verify_bimestre_edit_deadline_or_raise(attendance.academic_year, i, user_role)
                    break
    
    # Verifica se pode lançar nessa data
    date_check = await check_attendance_date(attendance.date, request)
    if not date_check['can_record']:
        raise HTTPException(
            status_code=400, 
            detail=f"Não é possível lançar frequência: {date_check['message']}"
        )
    
    # Verifica se já existe
    query = {
        "class_id": attendance.class_id,
        "date": attendance.date,
        "period": attendance.period
    }
    
    if attendance.attendance_type == 'by_component' and attendance.course_id:
        query["course_id"] = attendance.course_id
    
    existing = await db.attendance.find_one(query)
    
    if existing:
        # Atualiza existente
        await db.attendance.update_one(
            {"id": existing['id']},
            {"$set": {
                "records": [r.model_dump() for r in attendance.records],
                "observations": attendance.observations,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        # Auditoria de atualização de frequência
        class_info = await db.classes.find_one({"id": attendance.class_id}, {"_id": 0, "name": 1, "school_id": 1})
        await audit_service.log(
            action='update',
            collection='attendance',
            user=current_user,
            request=request,
            document_id=existing['id'],
            description=f"Atualizou frequência da turma {class_info.get('name', 'N/A')} em {attendance.date}",
            school_id=class_info.get('school_id') if class_info else None,
            academic_year=attendance.academic_year,
            extra_data={'date': attendance.date, 'records_count': len(attendance.records)}
        )
        
        return await db.attendance.find_one({"id": existing['id']}, {"_id": 0})
    else:
        # Cria novo
        new_attendance = {
            "id": str(uuid.uuid4()),
            "class_id": attendance.class_id,
            "date": attendance.date,
            "academic_year": attendance.academic_year,
            "attendance_type": attendance.attendance_type,
            "course_id": attendance.course_id,
            "period": attendance.period,
            "records": [r.model_dump() for r in attendance.records],
            "observations": attendance.observations,
            "created_by": current_user['id'],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.attendance.insert_one(new_attendance)
        
        # Auditoria de criação de frequência
        class_info = await db.classes.find_one({"id": attendance.class_id}, {"_id": 0, "name": 1, "school_id": 1})
        await audit_service.log(
            action='create',
            collection='attendance',
            user=current_user,
            request=request,
            document_id=new_attendance['id'],
            description=f"Lançou frequência da turma {class_info.get('name', 'N/A')} em {attendance.date}",
            school_id=class_info.get('school_id') if class_info else None,
            academic_year=attendance.academic_year,
            extra_data={'date': attendance.date, 'records_count': len(attendance.records)}
        )
        
        return await db.attendance.find_one({"id": new_attendance['id']}, {"_id": 0})

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

@api_router.get("/staff")
async def list_staff(request: Request, school_id: Optional[str] = None, cargo: Optional[str] = None, status: Optional[str] = None):
    """Lista todos os servidores"""
    await AuthMiddleware.require_roles(['admin', 'secretario', 'semed'])(request)
    
    query = {}
    if cargo:
        query["cargo"] = cargo
    if status:
        query["status"] = status
    
    staff_list = await db.staff.find(query, {"_id": 0}).to_list(1000)
    
    # Se filtrar por escola, verificar lotações
    if school_id:
        filtered_staff = []
        for staff in staff_list:
            lotacao = await db.school_assignments.find_one({
                "staff_id": staff['id'],
                "school_id": school_id,
                "status": "ativo"
            }, {"_id": 0})
            if lotacao:
                staff['lotacao_atual'] = lotacao
                filtered_staff.append(staff)
        staff_list = filtered_staff
    
    return staff_list

@api_router.get("/staff/{staff_id}")
async def get_staff(staff_id: str, request: Request):
    """Busca servidor por ID"""
    await AuthMiddleware.require_roles(['admin', 'secretario', 'semed', 'diretor'])(request)
    
    staff = await db.staff.find_one({"id": staff_id}, {"_id": 0})
    if not staff:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")
    
    # Buscar lotações
    lotacoes = await db.school_assignments.find({"staff_id": staff_id}, {"_id": 0}).to_list(100)
    for lot in lotacoes:
        school = await db.schools.find_one({"id": lot['school_id']}, {"_id": 0, "name": 1})
        if school:
            lot['school_name'] = school['name']
    staff['lotacoes'] = lotacoes
    
    # Se for professor, buscar alocações de turmas
    if staff['cargo'] == 'professor':
        alocacoes = await db.teacher_assignments.find({"staff_id": staff_id}, {"_id": 0}).to_list(100)
        for aloc in alocacoes:
            turma = await db.classes.find_one({"id": aloc['class_id']}, {"_id": 0, "name": 1})
            course = await db.courses.find_one({"id": aloc['course_id']}, {"_id": 0, "name": 1})
            if turma:
                aloc['class_name'] = turma['name']
            if course:
                aloc['course_name'] = course['name']
        staff['alocacoes'] = alocacoes
    
    return staff

async def generate_matricula():
    """Gera matrícula automática no formato ANO + sequencial (ex: 202500001)"""
    year = datetime.now().year
    prefix = str(year)
    
    # Busca última matrícula do ano
    last_staff = await db.staff.find(
        {"matricula": {"$regex": f"^{prefix}"}},
        {"_id": 0, "matricula": 1}
    ).sort("matricula", -1).limit(1).to_list(1)
    
    if last_staff:
        last_num = int(last_staff[0]['matricula'][4:])
        new_num = last_num + 1
    else:
        new_num = 1
    
    return f"{prefix}{new_num:05d}"

@api_router.post("/staff")
async def create_staff(staff_data: StaffCreate, request: Request):
    """Cria novo servidor com matrícula automática e cria usuário se for professor"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
    
    # Gera matrícula automática
    matricula = await generate_matricula()
    
    user_id = None
    
    # Se for professor e tiver email e CPF, cria usuário automaticamente
    if staff_data.cargo == 'professor' and staff_data.email and staff_data.cpf:
        # Verifica se já existe usuário com este email
        existing_user = await db.users.find_one({"email": staff_data.email})
        if existing_user:
            raise HTTPException(
                status_code=400, 
                detail=f"Já existe um usuário cadastrado com o email {staff_data.email}"
            )
        
        # Extrai os 6 primeiros dígitos do CPF (sem pontos e traços)
        cpf_limpo = ''.join(filter(str.isdigit, staff_data.cpf))
        if len(cpf_limpo) < 6:
            raise HTTPException(
                status_code=400, 
                detail="CPF inválido. O CPF deve ter pelo menos 6 dígitos para gerar a senha."
            )
        senha = cpf_limpo[:6]
        
        # Cria o usuário do professor
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        
        new_user = {
            "id": str(uuid.uuid4()),
            "full_name": staff_data.nome,
            "email": staff_data.email,
            "password_hash": pwd_context.hash(senha),
            "role": "professor",
            "status": "active",
            "avatar_url": staff_data.foto_url,
            "school_links": [],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.users.insert_one(new_user)
        user_id = new_user["id"]
    
    # Cria o servidor
    staff_dict = staff_data.model_dump()
    staff_dict['user_id'] = user_id
    
    new_staff = Staff(
        matricula=matricula,
        **staff_dict
    )
    
    await db.staff.insert_one(new_staff.model_dump())
    
    result = await db.staff.find_one({"id": new_staff.id}, {"_id": 0})
    
    # Adiciona informação sobre criação do usuário
    if user_id:
        result['_user_created'] = True
        result['_user_message'] = f"Usuário criado com email {staff_data.email} e senha: {cpf_limpo[:6]} (6 primeiros dígitos do CPF)"
    
    return result

@api_router.put("/staff/{staff_id}")
async def update_staff(staff_id: str, staff_data: StaffUpdate, request: Request):
    """Atualiza servidor (matrícula não pode ser alterada)"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
    
    existing = await db.staff.find_one({"id": staff_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")
    
    update_data = {k: v for k, v in staff_data.model_dump().items() if v is not None}
    update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
    
    await db.staff.update_one({"id": staff_id}, {"$set": update_data})
    
    return await db.staff.find_one({"id": staff_id}, {"_id": 0})

@api_router.delete("/staff/{staff_id}")
async def delete_staff(staff_id: str, request: Request):
    """Remove servidor"""
    await AuthMiddleware.require_roles(['admin'])(request)
    
    existing = await db.staff.find_one({"id": staff_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")
    
    # Verifica se tem lotações ativas
    active_assignments = await db.school_assignments.find_one({"staff_id": staff_id, "status": "ativo"})
    if active_assignments:
        raise HTTPException(status_code=400, detail="Servidor possui lotações ativas. Encerre-as primeiro.")
    
    await db.staff.delete_one({"id": staff_id})
    return {"message": "Servidor removido com sucesso"}

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
    
    # Buscar escola
    school_id = class_info.get("school_id") or student.get("school_id")
    school = await db.schools.find_one({"id": school_id}, {"_id": 0})
    if not school:
        school = {"name": "Escola Municipal", "cnpj": "N/A", "phone": "N/A", "city": "Município"}
    
    # Buscar notas do aluno
    grades = await db.grades.find({
        "student_id": student_id,
        "academic_year": academic_year
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
    
    # Determinar se a escola oferece atendimento integral
    escola_integral = school.get('atendimento_integral', False)
    logger.info(f"Boletim: escola_integral={escola_integral}")
    
    # Construir query para buscar componentes curriculares
    courses_query = {}
    
    # Filtrar por nível de ensino (OBRIGATÓRIO se temos um nível)
    if nivel_ensino:
        courses_query['nivel_ensino'] = nivel_ensino
    
    # Buscar componentes do nível de ensino
    all_courses = await db.courses.find(courses_query, {"_id": 0}).to_list(100)
    logger.info(f"Boletim: {len(all_courses)} componentes encontrados para nivel_ensino={nivel_ensino}")
    
    # Filtrar componentes baseado no atendimento/programa
    filtered_courses = []
    excluded_courses = []  # Para debug
    for course in all_courses:
        atendimento = course.get('atendimento_programa')
        course_grade_levels = course.get('grade_levels', [])
        course_name = course.get('name', 'N/A')
        
        # Componentes Transversais/Formativos aparecem em TODAS as escolas
        if atendimento == 'transversal_formativa':
            # Sempre incluir - é transversal a todas as escolas
            pass
        # Verificar se o componente é específico de Escola Integral
        elif atendimento == 'atendimento_integral':
            # Só incluir se a escola é integral
            if not escola_integral:
                excluded_courses.append(f"{course_name} (excluído: atendimento_integral e escola não é integral)")
                continue
        # Verificar se o componente é de outro atendimento (AEE, reforço, etc)
        elif atendimento and atendimento not in ['atendimento_integral', 'transversal_formativa']:
            # Verificar se a escola oferece esse atendimento
            escola_oferece = school.get(atendimento, False)
            if not escola_oferece:
                excluded_courses.append(f"{course_name} (excluído: atendimento={atendimento} não oferecido pela escola)")
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
    
    # Buscar calendário letivo para obter os dias letivos
    calendario_letivo = await db.calendario_letivo.find_one({
        "ano_letivo": int(academic_year),
        "school_id": None  # Calendário geral
    }, {"_id": 0})
    
    # Calcular total de dias letivos do ano
    dias_letivos_ano = 200  # Padrão LDB
    if calendario_letivo:
        dias_letivos_ano = (
            (calendario_letivo.get('bimestre_1_dias_letivos') or 0) +
            (calendario_letivo.get('bimestre_2_dias_letivos') or 0) +
            (calendario_letivo.get('bimestre_3_dias_letivos') or 0) +
            (calendario_letivo.get('bimestre_4_dias_letivos') or 0)
        )
        # Se não tiver dias por bimestre, usar o total previsto
        if dias_letivos_ano == 0:
            dias_letivos_ano = calendario_letivo.get('dias_letivos_previstos', 200) or 200
    
    # Gerar PDF
    try:
        pdf_buffer = generate_boletim_pdf(
            student=student,
            school=school,
            enrollment=enrollment,
            class_info=class_info,
            grades=grades,
            courses=courses,
            academic_year=academic_year,
            mantenedora=mantenedora,
            dias_letivos_ano=dias_letivos_ano,
            calendario_letivo=calendario_letivo
        )
        
        filename = f"boletim_{student.get('full_name', 'aluno').replace(' ', '_')}_{academic_year}.pdf"
        
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
            academic_year=academic_year,
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
    
    # Calcular frequência do aluno
    # Buscar todas as presenças do aluno
    attendances = await db.attendance.find({
        "student_id": student_id,
        "academic_year": academic_year
    }, {"_id": 0}).to_list(500)
    
    # Calcular estatísticas
    total_days = len(attendances)
    present_days = sum(1 for a in attendances if a.get('status') in ['present', 'P'])
    absent_days = sum(1 for a in attendances if a.get('status') in ['absent', 'F', 'A'])
    
    # Se não houver dados, usar valores padrão
    if total_days == 0:
        # Estimar dias letivos (aproximadamente 200 dias por ano)
        total_days = 200
        present_days = 180
        absent_days = 20
    
    frequency_percentage = (present_days / total_days * 100) if total_days > 0 else 0
    
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
            academic_year=academic_year,
            period=f"ano letivo de {academic_year}",
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
    
    # Buscar escola
    school = await db.schools.find_one({"id": student.get("school_id")}, {"_id": 0})
    if not school:
        school = {"name": "Escola Municipal", "city": "Município"}
    
    # Buscar turma
    class_info = await db.classes.find_one({"id": student.get("class_id")}, {"_id": 0})
    if not class_info:
        class_info = {"name": "N/A", "grade_level": "N/A", "shift": "N/A"}
    
    # Buscar matrícula
    enrollment = await db.enrollments.find_one(
        {"student_id": student_id, "academic_year": academic_year},
        {"_id": 0}
    )
    if not enrollment:
        enrollment = {"registration_number": student.get("enrollment_number", "N/A")}
    
    # Buscar notas do aluno
    grades = await db.grades.find(
        {"student_id": student_id, "academic_year": academic_year},
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
    
    # Verificar se a escola oferece atendimento integral
    escola_integral = school.get('atendimento_integral', False)
    logger.info(f"Ficha Individual: escola_integral={escola_integral}")
    
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
    
    # Filtrar componentes baseado no atendimento/programa
    filtered_courses = []
    excluded_courses = []  # Para debug
    for course in all_courses:
        atendimento = course.get('atendimento_programa')
        course_grade_levels = course.get('grade_levels', [])
        course_name = course.get('name', 'N/A')
        
        # Componentes Transversais/Formativos aparecem em TODAS as escolas
        if atendimento == 'transversal_formativa':
            # Sempre incluir - é transversal a todas as escolas
            pass
        # Verificar se o componente é específico de Escola Integral
        elif atendimento == 'atendimento_integral':
            if not escola_integral:
                excluded_courses.append(f"{course_name} (excluído: atendimento_integral e escola não é integral)")
                continue
        # Verificar se o componente é de outro atendimento (AEE, reforço, etc)
        elif atendimento and atendimento not in ['atendimento_integral', 'transversal_formativa']:
            escola_oferece = school.get(atendimento, False)
            if not escola_oferece:
                excluded_courses.append(f"{course_name} (excluído: atendimento={atendimento} não oferecido pela escola)")
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
    
    # Buscar dados de frequência por componente
    attendance_data = {}
    for course in courses:
        course_id = course.get('id')
        
        # Buscar frequência do componente (se houver registros específicos)
        att_records = await db.attendance.find(
            {
                "student_id": student_id,
                "course_id": course_id,
                "academic_year": academic_year
            },
            {"_id": 0}
        ).to_list(100)
        
        if att_records:
            total_classes = sum(a.get('total_classes', 0) for a in att_records)
            total_absences = sum(a.get('absences', 0) for a in att_records)
            if total_classes > 0:
                freq_pct = ((total_classes - total_absences) / total_classes) * 100
            else:
                freq_pct = 100.0
            attendance_data[course_id] = {
                'total_classes': total_classes,
                'absences': total_absences,
                'frequency_percentage': freq_pct
            }
        else:
            # Buscar frequência geral do aluno
            general_att = await db.attendance.find(
                {"student_id": student_id, "academic_year": academic_year},
                {"_id": 0}
            ).to_list(100)
            
            if general_att:
                total_classes = sum(a.get('total_classes', 0) for a in general_att)
                total_absences = sum(a.get('absences', 0) for a in general_att)
                if total_classes > 0:
                    freq_pct = ((total_classes - total_absences) / total_classes) * 100
                else:
                    freq_pct = 100.0
            else:
                total_classes = 0
                total_absences = 0
                freq_pct = 100.0
            
            attendance_data[course_id] = {
                'total_classes': total_classes,
                'absences': total_absences,
                'frequency_percentage': freq_pct
            }
    
    # Buscar dados da mantenedora
    mantenedora = await db.mantenedora.find_one({}, {"_id": 0})
    
    # Buscar calendário letivo para data fim do 4º bimestre
    calendario_letivo = await db.calendar.find_one({
        "year": academic_year
    }, {"_id": 0})
    
    # Gerar PDF
    try:
        pdf_buffer = generate_ficha_individual_pdf(
            student=student,
            school=school,
            class_info=class_info,
            enrollment=enrollment,
            academic_year=academic_year,
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
                
                period = grade.get("period", "")
                grade_value = grade.get("grade")
                
                # Mapear períodos
                period_map = {
                    "P1": "b1", "P2": "b2", "P3": "b3", "P4": "b4",
                    "REC1": "rec1", "REC2": "rec2"
                }
                
                if period in period_map:
                    grades_by_component[course_id][period_map[period]] = grade_value
            
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

@api_router.post("/announcements", response_model=AnnouncementResponse, status_code=status.HTTP_201_CREATED)
async def create_announcement(announcement_data: AnnouncementCreate, request: Request):
    """Criar um novo aviso"""
    current_user = await AuthMiddleware.get_current_user(request)
    
    # Buscar dados completos do usuário
    user_data = await db.users.find_one({'id': current_user['id']}, {'_id': 0})
    if not user_data:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    # Verificar permissão
    if not can_user_create_announcement(user_data, announcement_data.recipient.model_dump()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para enviar avisos para esses destinatários"
        )
    
    # Buscar foto do remetente
    profile = await db.user_profiles.find_one({'user_id': current_user['id']}, {'_id': 0})
    sender_foto = profile.get('foto_url') if profile else None
    
    # Criar aviso
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
    
    # Obter lista de usuários destinatários para facilitar buscas
    target_users = await get_announcement_target_users(db, announcement_data.recipient.model_dump(), user_data)
    announcement['target_user_ids'] = target_users
    
    await db.announcements.insert_one(announcement)
    
    # Notificar via WebSocket
    for user_id in target_users:
        await connection_manager.send_notification(user_id, {
            'type': 'new_announcement',
            'announcement': {
                'id': announcement['id'],
                'title': announcement['title'],
                'sender_name': announcement['sender_name']
            }
        })
    
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

@api_router.get("/announcements", response_model=List[AnnouncementResponse])
async def list_announcements(request: Request, skip: int = 0, limit: int = 50):
    """Listar avisos do usuário atual"""
    current_user = await AuthMiddleware.get_current_user(request)
    user_id = current_user['id']
    
    # Buscar avisos onde o usuário é destinatário ou remetente
    announcements = await db.announcements.find(
        {'$or': [
            {'target_user_ids': user_id},
            {'sender_id': user_id}
        ]},
        {'_id': 0}
    ).sort('created_at', -1).skip(skip).limit(limit).to_list(limit)
    
    # Buscar status de leitura
    read_statuses = await db.announcement_reads.find(
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

@api_router.get("/announcements/{announcement_id}", response_model=AnnouncementResponse)
async def get_announcement(announcement_id: str, request: Request):
    """Obter detalhes de um aviso"""
    current_user = await AuthMiddleware.get_current_user(request)
    user_id = current_user['id']
    
    announcement = await db.announcements.find_one(
        {'id': announcement_id},
        {'_id': 0}
    )
    
    if not announcement:
        raise HTTPException(status_code=404, detail="Aviso não encontrado")
    
    # Verificar se o usuário tem acesso
    if user_id not in announcement.get('target_user_ids', []) and user_id != announcement['sender_id']:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    # Buscar status de leitura
    read_status = await db.announcement_reads.find_one(
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

@api_router.put("/announcements/{announcement_id}", response_model=AnnouncementResponse)
async def update_announcement(announcement_id: str, update_data: AnnouncementUpdate, request: Request):
    """Atualizar um aviso (apenas o remetente pode editar)"""
    current_user = await AuthMiddleware.get_current_user(request)
    
    announcement = await db.announcements.find_one({'id': announcement_id}, {'_id': 0})
    
    if not announcement:
        raise HTTPException(status_code=404, detail="Aviso não encontrado")
    
    if announcement['sender_id'] != current_user['id'] and current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Apenas o remetente pode editar o aviso")
    
    # Atualizar campos
    update_fields = {}
    if update_data.title is not None:
        update_fields['title'] = update_data.title
    if update_data.content is not None:
        update_fields['content'] = update_data.content
    if update_data.recipient is not None:
        update_fields['recipient'] = update_data.recipient.model_dump()
        # Recalcular destinatários
        target_users = await get_announcement_target_users(db, update_data.recipient.model_dump(), current_user)
        update_fields['target_user_ids'] = target_users
    
    update_fields['updated_at'] = datetime.now(timezone.utc).isoformat()
    
    await db.announcements.update_one(
        {'id': announcement_id},
        {'$set': update_fields}
    )
    
    # Buscar aviso atualizado
    updated = await db.announcements.find_one({'id': announcement_id}, {'_id': 0})
    
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

@api_router.delete("/announcements/{announcement_id}")
async def delete_announcement(announcement_id: str, request: Request):
    """Excluir um aviso (apenas o remetente ou admin pode excluir)"""
    current_user = await AuthMiddleware.get_current_user(request)
    
    announcement = await db.announcements.find_one({'id': announcement_id}, {'_id': 0})
    
    if not announcement:
        raise HTTPException(status_code=404, detail="Aviso não encontrado")
    
    if announcement['sender_id'] != current_user['id'] and current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Apenas o remetente ou admin pode excluir o aviso")
    
    # Excluir aviso e leituras relacionadas
    await db.announcements.delete_one({'id': announcement_id})
    await db.announcement_reads.delete_many({'announcement_id': announcement_id})
    
    return {"message": "Aviso excluído com sucesso"}

@api_router.post("/announcements/{announcement_id}/read")
async def mark_announcement_read(announcement_id: str, request: Request):
    """Marcar um aviso como lido"""
    current_user = await AuthMiddleware.get_current_user(request)
    user_id = current_user['id']
    
    announcement = await db.announcements.find_one({'id': announcement_id}, {'_id': 0})
    
    if not announcement:
        raise HTTPException(status_code=404, detail="Aviso não encontrado")
    
    # Verificar se o usuário tem acesso
    if user_id not in announcement.get('target_user_ids', []) and user_id != announcement['sender_id']:
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    # Verificar se já foi lido
    existing = await db.announcement_reads.find_one(
        {'announcement_id': announcement_id, 'user_id': user_id}
    )
    
    if not existing:
        await db.announcement_reads.insert_one({
            'id': str(uuid.uuid4()),
            'announcement_id': announcement_id,
            'user_id': user_id,
            'read_at': datetime.now(timezone.utc).isoformat()
        })
    
    return {"message": "Aviso marcado como lido"}

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
        
        # Verificar atendimento
        if atendimento == 'transversal_formativa':
            pass
        elif atendimento == 'atendimento_integral':
            if not escola_integral:
                excluded_courses.append({
                    "name": course_name,
                    "reason": f"atendimento_integral e escola não é integral (escola_integral={escola_integral})",
                    "course_data": course
                })
                continue
        elif atendimento and atendimento not in ['atendimento_integral', 'transversal_formativa']:
            escola_oferece = school.get(atendimento, False)
            if not escola_oferece:
                excluded_courses.append({
                    "name": course_name,
                    "reason": f"atendimento={atendimento} não oferecido pela escola",
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
            "nivel_ensino_inferido": nivel_ensino
        },
        "school_info": {
            "id": school_id,
            "name": school.get('name'),
            "atendimento_integral": escola_integral,
            "atendimentos": {k: v for k, v in school.items() if k.startswith('atendimento') or k.endswith('_integral')}
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


# Include the router in the main app
app.include_router(api_router)

# Include modular routers
users_router = setup_users_router(db, audit_service)
schools_router = setup_schools_router(db, audit_service)
courses_router = setup_courses_router(db, audit_service)
classes_router = setup_classes_router(db, audit_service)
guardians_router = setup_guardians_router(db, audit_service)
enrollments_router = setup_enrollments_router(db, audit_service)

app.include_router(users_router, prefix="/api")
app.include_router(schools_router, prefix="/api")
app.include_router(courses_router, prefix="/api")
app.include_router(classes_router, prefix="/api")
app.include_router(guardians_router, prefix="/api")
app.include_router(enrollments_router, prefix="/api")

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
