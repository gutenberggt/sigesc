from fastapi import FastAPI, APIRouter, HTTPException, status, Depends, Request, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import shutil
import json
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime, timezone
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
    Mantenedora, MantenedoraUpdate
)
from auth_utils import (
    hash_password, verify_password, create_access_token, 
    create_refresh_token, decode_token, get_school_ids_from_links
)
from auth_middleware import AuthMiddleware
from pdf_generator import (
    generate_boletim_pdf,
    generate_declaracao_matricula_pdf,
    generate_declaracao_frequencia_pdf,
    generate_ficha_individual_pdf,
    generate_certificado_pdf
)
from ftp_upload import upload_to_ftp, delete_from_ftp
from grade_calculator import calculate_and_update_grade

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'sigesc_db')]

# Create the main app
app = FastAPI(title="SIGESC API", version="1.0.0")

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
        {"_id": 0, "id": 1, "full_name": 1}
    )
    
    if not staff:
        # Tenta buscar pelo nome do usuário
        user = await db.users.find_one({"email": user_email}, {"_id": 0, "full_name": 1})
        if user and user.get('full_name'):
            staff = await db.staff.find_one(
                {"full_name": {"$regex": f"^{user['full_name']}$", "$options": "i"}},
                {"_id": 0, "id": 1, "full_name": 1}
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
    school_links = []
    
    for lotacao in lotacoes:
        funcao = lotacao.get('funcao', 'professor')
        school_id = lotacao.get('school_id')
        
        # Adiciona aos school_links com a função específica
        school_links.append({
            "school_id": school_id,
            "role": funcao
        })
        
        # Verifica se é o role de maior hierarquia
        role_priority = ROLE_HIERARCHY.get(funcao, 0)
        if role_priority > highest_priority:
            highest_priority = role_priority
            highest_role = funcao
    
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
async def login(credentials: LoginRequest):
    """Autentica usuário e retorna tokens"""
    # Busca usuário
    user_doc = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos"
        )
    
    user = UserInDB(**user_doc)
    
    # Verifica senha
    if not verify_password(credentials.password, user.password_hash):
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
    """Retorna informações do usuário autenticado"""
    current_user = await AuthMiddleware.get_current_user(request)
    
    user_doc = await db.users.find_one({"id": current_user['id']}, {"_id": 0})
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado"
        )
    
    return UserResponse(**user_doc)

# ============= USER ROUTES (Admin only) =============

@api_router.get("/users", response_model=List[UserResponse])
async def list_users(request: Request, skip: int = 0, limit: int = 1000):
    """Lista usuários (apenas admin e semed)"""
    current_user = await AuthMiddleware.require_roles(['admin', 'semed'])(request)
    
    users = await db.users.find({}, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
    
    # Remove password_hash de todos
    for user in users:
        user.pop('password_hash', None)
    
    return users

@api_router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, request: Request):
    """Busca usuário por ID"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'semed'])(request)
    
    user_doc = await db.users.find_one({"id": user_id}, {"_id": 0})
    
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado"
        )
    
    user_doc.pop('password_hash', None)
    return UserResponse(**user_doc)

@api_router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, user_update: UserUpdate, request: Request):
    """Atualiza usuário"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
    
    # Busca usuário
    user_doc = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado"
        )
    
    # Prepara atualização
    update_data = user_update.model_dump(exclude_unset=True)
    
    if update_data:
        await db.users.update_one(
            {"id": user_id},
            {"$set": update_data}
        )
    
    # Retorna usuário atualizado
    updated_user = await db.users.find_one({"id": user_id}, {"_id": 0})
    updated_user.pop('password_hash', None)
    
    return UserResponse(**updated_user)

@api_router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: str, request: Request):
    """Deleta usuário definitivamente do sistema"""
    current_user = await AuthMiddleware.require_roles(['admin'])(request)
    
    # Verificar se o usuário existe
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado"
        )
    
    # Não permitir excluir o próprio usuário
    if user_id == current_user['id']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível excluir seu próprio usuário"
        )
    
    # Excluir definitivamente o usuário
    result = await db.users.delete_one({"id": user_id})
    
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao excluir usuário"
        )
    
    return None

# ============= SCHOOL ROUTES =============

@api_router.post("/schools", response_model=School, status_code=status.HTTP_201_CREATED)
async def create_school(school: SchoolCreate, request: Request):
    """Cria nova escola (apenas admin)"""
    current_user = await AuthMiddleware.require_roles(['admin'])(request)
    
    school_obj = School(**school.model_dump())
    doc = school_obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    
    await db.schools.insert_one(doc)
    
    return school_obj

@api_router.get("/schools", response_model=List[School])
async def list_schools(request: Request, skip: int = 0, limit: int = 100):
    """Lista escolas"""
    current_user = await AuthMiddleware.get_current_user(request)
    
    # Admin e SEMED veem todas as escolas
    if current_user['role'] in ['admin', 'semed']:
        schools = await db.schools.find({}, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
    else:
        # Outros papéis veem apenas escolas vinculadas
        schools = await db.schools.find(
            {"id": {"$in": current_user['school_ids']}},
            {"_id": 0}
        ).skip(skip).limit(limit).to_list(limit)
    
    return schools

@api_router.get("/schools/{school_id}", response_model=School)
async def get_school(school_id: str, request: Request):
    """Busca escola por ID"""
    current_user = await AuthMiddleware.verify_school_access(request, school_id)
    
    school = await db.schools.find_one({"id": school_id}, {"_id": 0})
    
    if not school:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escola não encontrada"
        )
    
    return School(**school)

@api_router.put("/schools/{school_id}", response_model=School)
async def update_school(school_id: str, school_update: SchoolUpdate, request: Request):
    """Atualiza escola"""
    current_user = await AuthMiddleware.require_roles(['admin'])(request)
    
    update_data = school_update.model_dump(exclude_unset=True)
    
    if update_data:
        result = await db.schools.update_one(
            {"id": school_id},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Escola não encontrada"
            )
    
    updated_school = await db.schools.find_one({"id": school_id}, {"_id": 0})
    return School(**updated_school)

@api_router.delete("/schools/{school_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_school(school_id: str, request: Request):
    """Deleta escola definitivamente"""
    current_user = await AuthMiddleware.require_roles(['admin'])(request)
    
    result = await db.schools.delete_one({"id": school_id})
    
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escola não encontrada"
        )
    
    return None

# ============= CLASS (TURMA) ROUTES =============

@api_router.post("/classes", response_model=Class, status_code=status.HTTP_201_CREATED)
async def create_class(class_data: ClassCreate, request: Request):
    """Cria nova turma"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
    
    # Verifica acesso à escola
    await AuthMiddleware.verify_school_access(request, class_data.school_id)
    
    class_obj = Class(**class_data.model_dump())
    doc = class_obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    
    await db.classes.insert_one(doc)
    
    return class_obj

@api_router.get("/classes", response_model=List[Class])
async def list_classes(request: Request, school_id: Optional[str] = None, skip: int = 0, limit: int = 100):
    """Lista turmas"""
    current_user = await AuthMiddleware.get_current_user(request)
    
    # Constrói filtro
    filter_query = {}
    
    if current_user['role'] in ['admin', 'semed']:
        # Admin e SEMED podem filtrar por escola ou ver todas
        if school_id:
            filter_query['school_id'] = school_id
    else:
        # Outros papéis veem apenas das escolas vinculadas
        if school_id and school_id in current_user['school_ids']:
            filter_query['school_id'] = school_id
        else:
            filter_query['school_id'] = {"$in": current_user['school_ids']}
    
    classes = await db.classes.find(filter_query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
    
    return classes

@api_router.get("/classes/{class_id}", response_model=Class)
async def get_class(class_id: str, request: Request):
    """Busca turma por ID"""
    current_user = await AuthMiddleware.get_current_user(request)
    
    class_doc = await db.classes.find_one({"id": class_id}, {"_id": 0})
    
    if not class_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turma não encontrada"
        )
    
    # Verifica acesso à escola da turma
    await AuthMiddleware.verify_school_access(request, class_doc['school_id'])
    
    return Class(**class_doc)

@api_router.put("/classes/{class_id}", response_model=Class)
async def update_class(class_id: str, class_update: ClassUpdate, request: Request):
    """Atualiza turma"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
    
    # Busca turma
    class_doc = await db.classes.find_one({"id": class_id}, {"_id": 0})
    if not class_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turma não encontrada"
        )
    
    # Verifica acesso
    await AuthMiddleware.verify_school_access(request, class_doc['school_id'])
    
    update_data = class_update.model_dump(exclude_unset=True)
    
    if update_data:
        await db.classes.update_one(
            {"id": class_id},
            {"$set": update_data}
        )
    
    updated_class = await db.classes.find_one({"id": class_id}, {"_id": 0})
    return Class(**updated_class)

@api_router.delete("/classes/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_class(class_id: str, request: Request):
    """Deleta turma"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
    
    # Busca turma
    class_doc = await db.classes.find_one({"id": class_id}, {"_id": 0})
    if not class_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turma não encontrada"
        )
    
    # Verifica acesso
    await AuthMiddleware.verify_school_access(request, class_doc['school_id'])
    
    result = await db.classes.delete_one({"id": class_id})
    
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turma não encontrada"
        )
    
    return None

# ============= COURSE (COMPONENTE CURRICULAR) ROUTES =============

@api_router.post("/courses", response_model=Course, status_code=status.HTTP_201_CREATED)
async def create_course(course_data: CourseCreate, request: Request):
    """Cria novo componente curricular (global para todas as escolas)"""
    current_user = await AuthMiddleware.require_roles(['admin'])(request)
    
    course_obj = Course(**course_data.model_dump())
    doc = course_obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    
    await db.courses.insert_one(doc)
    
    return course_obj

@api_router.get("/courses", response_model=List[Course])
async def list_courses(request: Request, nivel_ensino: Optional[str] = None, skip: int = 0, limit: int = 100):
    """Lista componentes curriculares (global)"""
    current_user = await AuthMiddleware.get_current_user(request)
    
    # Constrói filtro
    filter_query = {}
    
    if nivel_ensino:
        filter_query['nivel_ensino'] = nivel_ensino
    
    courses = await db.courses.find(filter_query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
    
    return courses

@api_router.get("/courses/{course_id}", response_model=Course)
async def get_course(course_id: str, request: Request):
    """Busca componente curricular por ID"""
    current_user = await AuthMiddleware.get_current_user(request)
    
    course_doc = await db.courses.find_one({"id": course_id}, {"_id": 0})
    
    if not course_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Componente curricular não encontrado"
        )
    
    return Course(**course_doc)

@api_router.put("/courses/{course_id}", response_model=Course)
async def update_course(course_id: str, course_update: CourseUpdate, request: Request):
    """Atualiza componente curricular"""
    current_user = await AuthMiddleware.require_roles(['admin'])(request)
    
    # Busca componente
    course_doc = await db.courses.find_one({"id": course_id}, {"_id": 0})
    if not course_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Componente curricular não encontrado"
        )
    
    update_data = course_update.model_dump(exclude_unset=True)
    
    if update_data:
        await db.courses.update_one(
            {"id": course_id},
            {"$set": update_data}
        )
    
    updated_course = await db.courses.find_one({"id": course_id}, {"_id": 0})
    return Course(**updated_course)

@api_router.delete("/courses/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_course(course_id: str, request: Request):
    """Deleta componente curricular"""
    current_user = await AuthMiddleware.require_roles(['admin'])(request)
    
    result = await db.courses.delete_one({"id": course_id})
    
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Componente curricular não encontrado"
        )
    
    return None

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
    """Atualiza aluno"""
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
    
    update_data = student_update.model_dump(exclude_unset=True)
    
    if update_data:
        await db.students.update_one(
            {"id": student_id},
            {"$set": update_data}
        )
    
    updated_student = await db.students.find_one({"id": student_id}, {"_id": 0})
    return Student(**updated_student)

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
    
    return None

# ============= GUARDIAN (RESPONSÁVEL) ROUTES =============

@api_router.post("/guardians", response_model=Guardian, status_code=status.HTTP_201_CREATED)
async def create_guardian(guardian_data: GuardianCreate, request: Request):
    """Cria novo responsável"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
    
    guardian_obj = Guardian(**guardian_data.model_dump())
    doc = guardian_obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    
    await db.guardians.insert_one(doc)
    
    return guardian_obj

@api_router.get("/guardians", response_model=List[Guardian])
async def list_guardians(request: Request, skip: int = 0, limit: int = 100):
    """Lista responsáveis"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'semed'])(request)
    
    guardians = await db.guardians.find({}, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
    
    return guardians

@api_router.get("/guardians/{guardian_id}", response_model=Guardian)
async def get_guardian(guardian_id: str, request: Request):
    """Busca responsável por ID"""
    current_user = await AuthMiddleware.get_current_user(request)
    
    guardian_doc = await db.guardians.find_one({"id": guardian_id}, {"_id": 0})
    
    if not guardian_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Responsável não encontrado"
        )
    
    return Guardian(**guardian_doc)

@api_router.put("/guardians/{guardian_id}", response_model=Guardian)
async def update_guardian(guardian_id: str, guardian_update: GuardianUpdate, request: Request):
    """Atualiza responsável"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
    
    update_data = guardian_update.model_dump(exclude_unset=True)
    
    if update_data:
        result = await db.guardians.update_one(
            {"id": guardian_id},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Responsável não encontrado"
            )
    
    updated_guardian = await db.guardians.find_one({"id": guardian_id}, {"_id": 0})
    return Guardian(**updated_guardian)

@api_router.delete("/guardians/{guardian_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_guardian(guardian_id: str, request: Request):
    """Deleta responsável"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
    
    result = await db.guardians.delete_one({"id": guardian_id})
    
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Responsável não encontrado"
        )
    
    return None

# ============= ENROLLMENT (MATRÍCULA) ROUTES =============

@api_router.post("/enrollments", response_model=Enrollment, status_code=status.HTTP_201_CREATED)
async def create_enrollment(enrollment_data: EnrollmentCreate, request: Request):
    """Cria nova matrícula"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
    
    enrollment_obj = Enrollment(**enrollment_data.model_dump())
    doc = enrollment_obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    
    await db.enrollments.insert_one(doc)
    
    # Sincroniza dados do aluno com a matrícula (school_id, class_id, status)
    await db.students.update_one(
        {"id": enrollment_data.student_id},
        {"$set": {
            "school_id": enrollment_data.school_id,
            "class_id": enrollment_data.class_id,
            "status": "active"
        }}
    )
    
    return enrollment_obj

@api_router.get("/enrollments", response_model=List[Enrollment])
async def list_enrollments(request: Request, student_id: Optional[str] = None, class_id: Optional[str] = None, skip: int = 0, limit: int = 100):
    """Lista matrículas"""
    current_user = await AuthMiddleware.get_current_user(request)
    
    filter_query = {}
    if student_id:
        filter_query['student_id'] = student_id
    if class_id:
        filter_query['class_id'] = class_id
    
    enrollments = await db.enrollments.find(filter_query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
    
    return enrollments

@api_router.get("/enrollments/{enrollment_id}", response_model=Enrollment)
async def get_enrollment(enrollment_id: str, request: Request):
    """Busca matrícula por ID"""
    current_user = await AuthMiddleware.get_current_user(request)
    
    enrollment_doc = await db.enrollments.find_one({"id": enrollment_id}, {"_id": 0})
    
    if not enrollment_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Matrícula não encontrada"
        )
    
    return Enrollment(**enrollment_doc)

@api_router.put("/enrollments/{enrollment_id}", response_model=Enrollment)
async def update_enrollment(enrollment_id: str, enrollment_update: EnrollmentUpdate, request: Request):
    """Atualiza matrícula"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
    
    # Busca matrícula atual para obter student_id
    existing_enrollment = await db.enrollments.find_one({"id": enrollment_id}, {"_id": 0})
    if not existing_enrollment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Matrícula não encontrada"
        )
    
    update_data = enrollment_update.model_dump(exclude_unset=True)
    
    if update_data:
        await db.enrollments.update_one(
            {"id": enrollment_id},
            {"$set": update_data}
        )
        
        # Sincroniza dados do aluno se school_id, class_id ou status mudaram
        student_update = {}
        if 'school_id' in update_data:
            student_update['school_id'] = update_data['school_id']
        if 'class_id' in update_data:
            student_update['class_id'] = update_data['class_id']
        if 'status' in update_data:
            # Se matrícula foi cancelada/transferida, atualiza status do aluno
            if update_data['status'] in ['cancelled', 'transferred']:
                student_update['status'] = 'transferred'
            elif update_data['status'] == 'active':
                student_update['status'] = 'active'
        
        if student_update:
            await db.students.update_one(
                {"id": existing_enrollment['student_id']},
                {"$set": student_update}
            )
    
    updated_enrollment = await db.enrollments.find_one({"id": enrollment_id}, {"_id": 0})
    return Enrollment(**updated_enrollment)

@api_router.delete("/enrollments/{enrollment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_enrollment(enrollment_id: str, request: Request):
    """Deleta matrícula"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario'])(request)
    
    result = await db.enrollments.delete_one({"id": enrollment_id})
    
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Matrícula não encontrada"
        )
    
    return None

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
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'professor'])(request)
    
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
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'professor'])(request)
    
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
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'professor'])(request)
    
    results = []
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
            
            await db.grades.update_one(
                {"id": existing['id']},
                {"$set": update_fields}
            )
            
            updated = await calculate_and_update_grade(db, existing['id'])
            results.append(updated)
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
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'professor'])(request)
    
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
        return await db.attendance.find_one({"id": new_attendance['id']}, {"_id": 0})

@api_router.delete("/attendance/{attendance_id}")
async def delete_attendance(attendance_id: str, request: Request):
    """Remove um registro de frequência"""
    current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'professor'])(request)
    
    # Verifica se existe
    existing = await db.attendance.find_one({"id": attendance_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Registro de frequência não encontrado")
    
    # Remove o registro
    result = await db.attendance.delete_one({"id": attendance_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Erro ao remover frequência")
    
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
    
    return await db.school_assignments.find_one({"id": assignment_id}, {"_id": 0})

@api_router.delete("/school-assignments/{assignment_id}")
async def delete_school_assignment(assignment_id: str, request: Request):
    """Remove lotação"""
    await AuthMiddleware.require_roles(['admin'])(request)
    
    existing = await db.school_assignments.find_one({"id": assignment_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Lotação não encontrada")
    
    await db.school_assignments.delete_one({"id": assignment_id})
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
    
    existing = await db.learning_objects.find_one({"id": object_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    
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
    
    # Buscar disciplinas da turma
    courses = await db.courses.find({
        "class_id": class_id
    }, {"_id": 0}).to_list(50)
    
    # Se não houver disciplinas específicas da turma, buscar todas
    if not courses:
        courses = await db.courses.find({}, {"_id": 0}).to_list(50)
    
    # Buscar dados da mantenedora
    mantenedora = await db.mantenedora.find_one({}, {"_id": 0})
    
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
            mantenedora=mantenedora
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
    nivel_ensino = class_info.get('nivel_ensino', 'fundamental_anos_iniciais')
    school_id = student.get('school_id')
    
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
    courses = await db.courses.find(courses_filter, {"_id": 0}).to_list(100)
    
    # Se não encontrar componentes, buscar todos do nível
    if not courses:
        courses = await db.courses.find({"nivel_ensino": nivel_ensino}, {"_id": 0}).to_list(100)
    
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
            mantenedora=mantenedora
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
    """Gera o Certificado de Conclusão em PDF"""
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
    
    # Gerar PDF
    try:
        pdf_buffer = generate_certificado_pdf(
            student=student,
            school=school,
            class_info=class_info,
            enrollment=enrollment,
            academic_year=academic_year
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
    
    # Buscar escola da turma
    school = await db.schools.find_one({"id": class_info.get("school_id")}, {"_id": 0})
    if not school:
        school = {"name": "Escola Municipal"}
    
    # Buscar mantenedora
    mantenedora = await db.mantenedora.find_one({}, {"_id": 0})
    
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
                    mantenedora=mantenedora
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
                    mantenedora=mantenedora
                )
            elif document_type == 'certificado':
                pdf_buffer = generate_certificado_pdf(
                    student=student,
                    school=school,
                    class_info=class_info,
                    enrollment=enrollment,
                    academic_year=academic_year
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

# ============= UNIDADE MANTENEDORA ENDPOINTS =============

@api_router.get("/mantenedora", response_model=Mantenedora)
async def get_mantenedora(request: Request = None):
    """Busca a Unidade Mantenedora (única)"""
    current_user = await AuthMiddleware.get_current_user(request)
    
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

# Include the router in the main app
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
