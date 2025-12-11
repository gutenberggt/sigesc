from fastapi import FastAPI, APIRouter, HTTPException, status, Depends, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone

# Import models and utilities
from models import (
    User, UserCreate, UserUpdate, UserResponse, UserInDB,
    LoginRequest, TokenResponse, RefreshTokenRequest,
    School, SchoolCreate, SchoolUpdate,
    Class, ClassCreate, ClassUpdate,
    Course, CourseCreate, CourseUpdate,
    Student, StudentCreate, StudentUpdate,
    Guardian, GuardianCreate, GuardianUpdate,
    Enrollment, EnrollmentCreate, EnrollmentUpdate,
    Grade, GradeCreate, GradeUpdate,
    Attendance, AttendanceCreate, AttendanceUpdate,
    Notice, NoticeCreate, NoticeUpdate,
    Document, DocumentCreate
)
from auth_utils import (
    hash_password, verify_password, create_access_token, 
    create_refresh_token, decode_token, get_school_ids_from_links
)
from auth_middleware import AuthMiddleware
from grade_calculator import calculate_and_update_grade

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'sigesc_db')]

# Create the main app
app = FastAPI(title="SIGESC API", version="1.0.0")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
    
    # Cria tokens
    school_ids = get_school_ids_from_links(user.school_links)
    token_data = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "school_ids": school_ids
    }
    
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token({"sub": user.id})
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse(**user.model_dump(exclude={'password_hash'}))
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
    
    # Cria novos tokens
    school_ids = get_school_ids_from_links(user.school_links)
    token_data = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "school_ids": school_ids
    }
    
    access_token = create_access_token(token_data)
    new_refresh_token = create_refresh_token({"sub": user.id})
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        user=UserResponse(**user.model_dump(exclude={'password_hash'}))
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
async def list_users(request: Request, skip: int = 0, limit: int = 100):
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
    """Deleta usuário (soft delete - muda status para inactive)"""
    current_user = await AuthMiddleware.require_roles(['admin'])(request)
    
    result = await db.users.update_one(
        {"id": user_id},
        {"$set": {"status": "inactive"}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado"
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

# Include the router in the main app
app.include_router(api_router)

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
