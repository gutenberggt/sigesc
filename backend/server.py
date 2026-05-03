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
from routers.mantenedoras import create_mantenedoras_router

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
from routers import student_history as student_history_mod
from routers import vaccines as vaccines_mod
from routers import mec_integration as mec_mod
from routers import bolsa_familia as bolsa_mod
from routers import pmpi as pmpi_mod
from routers import pmpi_engine as pmpi_engine_mod
from routers import pmpi_ai as pmpi_ai_mod
from routers import action_plans as action_plans_mod
from routers import student_portal as student_portal_mod
from routers import admin_student_users as admin_student_users_mod
from routers import permission_overrides as permission_overrides_mod
from routers import spellcheck as spellcheck_mod
from routers import curriculum as curriculum_mod
from routers import curriculum_import as curriculum_import_mod
from routers import curriculum_v2 as curriculum_v2_mod
from routers import interventions as interventions_mod
from routers import tenant_admin as tenant_admin_mod
from routers import snapshots as snapshots_mod
from routers import verifiable_docs as verifiable_docs_mod
from routers import school_documents as school_docs_mod

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

# PATCH 3.3: Inicializa o blacklist top-level (set_db é sync; ensure_index roda no startup event)
# Garante que mesmo se startup event falhar, blacklist tem db.
token_blacklist.set_db(db)

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
        # G1.5: índices TTL e unique para snapshots auditáveis
        from services.snapshot_service import ensure_ttl_index as _ensure_snap_ttl
        await _ensure_snap_ttl(db)
        # G1.6: índices para verifiable_documents (code único, lookups)
        from services.verifiable_docs_service import ensure_indexes as _ensure_vd_idx
        await _ensure_vd_idx(db)
        # Índices para students
        await db.students.create_index("id", unique=True)
        await db.students.create_index("cpf", sparse=True)
        await db.students.create_index("school_id")
        await db.students.create_index("class_id")
        await db.students.create_index([("full_name", 1)],
            collation={"locale": "pt", "strength": 1},
            name="full_name_pt_collation"
        )
        await db.students.create_index([("status", 1), ("school_id", 1)])
        
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
        await db.staff.create_index([("nome", 1)],
            collation={"locale": "pt", "strength": 1},
            name="nome_pt_collation"
        )
        
        # Índices para school_assignments (lotações)
        await db.school_assignments.create_index("id", unique=True)
        await db.school_assignments.create_index([("staff_id", 1), ("academic_year", 1)])
        await db.school_assignments.create_index([("school_id", 1), ("academic_year", 1)])
        
        # Índices para teacher_assignments (alocações)
        await db.teacher_assignments.create_index("id", unique=True)
        await db.teacher_assignments.create_index([("staff_id", 1), ("academic_year", 1)])
        await db.teacher_assignments.create_index([("class_id", 1), ("course_id", 1)])
        await db.teacher_assignments.create_index([("class_id", 1), ("status", 1)])
        
        # Índices para attendance (frequência) - compound para queries por componente
        await db.attendance.create_index([("class_id", 1), ("course_id", 1), ("academic_year", 1)])

        # Índices para connections e messages (mensageiro)
        await db.connections.create_index("id", unique=True)
        await db.connections.create_index([("requester_id", 1), ("receiver_id", 1)])
        await db.messages.create_index([("connection_id", 1), ("created_at", -1)])
        await db.messages.create_index([("sender_id", 1), ("receiver_id", 1)])
        
        # Índices para courses (componentes)
        await db.courses.create_index("id", unique=True)
        await db.courses.create_index("nivel_ensino")

        # ===== ÍNDICES ADICIONAIS PARA PERFORMANCE DE PDFs (2026-02) =====
        # learning_objects PDF: busca por class_id + academic_year + date (range)
        await db.learning_objects.create_index(
            [("class_id", 1), ("academic_year", 1), ("date", 1)],
            name="lo_class_year_date"
        )
        await db.learning_objects.create_index(
            [("class_id", 1), ("course_id", 1), ("academic_year", 1)],
            name="lo_class_course_year"
        )
        # enrollments por class_id+status (Livro de Promoção filtra por status)
        await db.enrollments.create_index(
            [("class_id", 1), ("status", 1), ("academic_year", 1)],
            name="enr_class_status_year"
        )
        # calendar_events filtrados por academic_year (tipo string ou int)
        await db.calendar_events.create_index("academic_year", name="calevents_year")
        # calendario_letivo por ano_letivo
        await db.calendario_letivo.create_index(
            [("ano_letivo", 1), ("school_id", 1)], name="cal_year_school"
        )

        # ===== Índices Multi-tenant (Mantenedora) =====
        await db.mantenedoras.create_index("id", unique=True)
        # Índices compostos nas principais coleções para aceleração com filtro por tenant
        for coll in ("schools", "staff", "students", "classes", "courses",
                     "enrollments", "grades", "learning_objects", "calendar_events",
                     "calendario_letivo", "school_assignments", "teacher_assignments",
                     "payroll_items", "announcements", "action_plans"):
            try:
                await db[coll].create_index("mantenedora_id", name=f"{coll[:15]}_mid")
            except Exception:
                pass
        # Índices específicos de action_plans
        try:
            await db.action_plans.create_index("id", unique=True)
            await db.action_plans.create_index([("school_id", 1), ("status", 1)])
        except Exception:
            pass
        # Índices PMPI Engine (Onda 2)
        try:
            await db.alert_rules.create_index("id", unique=True)
            await db.alert_rules.create_index([("mantenedora_id", 1), ("active", 1)])
            await db.alerts.create_index("id", unique=True)
            await db.alerts.create_index([("mantenedora_id", 1), ("status", 1), ("detected_at", -1)])
            await db.alerts.create_index([("rule_id", 1), ("school_id", 1), ("status", 1)])
            await db.monthly_goals.create_index("id", unique=True)
            await db.monthly_goals.create_index([("mantenedora_id", 1), ("month", 1), ("school_id", 1)], unique=True)
        except Exception:
            pass

        # ===== Bootstrap multi-tenant: cria mantenedora inicial se não houver nenhuma =====
        # Nota: a migração do legado db.mantenedora (singular) já foi executada e a coleção
        # foi droppada. Mantém-se apenas o bootstrap para instalações totalmente novas.
        try:
            existing = await db.mantenedoras.count_documents({})
            if existing == 0:
                import uuid as _uuid
                import datetime as _dt
                mid = str(_uuid.uuid4())
                await db.mantenedoras.insert_one({
                    "id": mid, "name": "Mantenedora Principal", "ativo": True,
                    "created_at": _dt.datetime.now(_dt.timezone.utc),
                })

                # Marca documentos pré-existentes com a mantenedora principal
                for coll in ("schools", "staff", "students", "classes", "courses",
                             "enrollments", "grades", "learning_objects", "calendar_events",
                             "calendario_letivo", "school_assignments", "teacher_assignments",
                             "payroll_items", "announcements", "users"):
                    try:
                        await db[coll].update_many(
                            {"mantenedora_id": {"$exists": False}},
                            {"$set": {"mantenedora_id": mid}}
                        )
                    except Exception:
                        pass
                logger.info(f"Multi-tenant: mantenedora principal criada (id={mid}).")

                # Promover o primeiro admin a super_admin (cross-tenant)
                first_admin = await db.users.find_one({"role": "admin"}, {"_id": 0, "id": 1, "email": 1})
                if first_admin:
                    await db.users.update_one(
                        {"id": first_admin["id"]},
                        {"$set": {"role": "super_admin"}}
                    )
                    logger.info(f"Multi-tenant: {first_admin.get('email')} promovido a super_admin.")
        except Exception as exc:
            logger.warning(f"Multi-tenant: bootstrap ignorado: {exc}")

        # ===== Self-healing idempotente (roda sempre no startup) =====
        # Produção pode ter código novo mas dados pré-migração. Este bloco:
        # 1. Garante que existe pelo menos 1 super_admin (promove o primeiro admin legado);
        # 2. Preenche mantenedora_id ausente em documentos de todas as coleções tenant-scoped,
        #    usando a primeira mantenedora cadastrada como fallback. É idempotente (só atualiza
        #    documentos que não têm o campo).
        try:
            any_super = await db.users.find_one(
                {"$or": [{"role": "super_admin"}, {"roles": "super_admin"}]},
                {"_id": 0, "id": 1},
            )
            first_mant = await db.mantenedoras.find_one({}, {"_id": 0, "id": 1, "nome": 1, "name": 1})
            first_mant_id = first_mant.get("id") if first_mant else None

            if not any_super:
                legacy_admin = await db.users.find_one(
                    {"role": "admin", "is_primary": True},
                    {"_id": 0, "id": 1, "email": 1},
                ) or await db.users.find_one(
                    {"role": "admin"},
                    {"_id": 0, "id": 1, "email": 1},
                )
                if legacy_admin:
                    await db.users.update_one(
                        {"id": legacy_admin["id"]},
                        {"$set": {"role": "super_admin", "is_primary": True}},
                    )
                    logger.info(
                        f"Self-heal: {legacy_admin.get('email')} promovido a super_admin (is_primary=True)."
                    )

            if first_mant_id:
                total_healed = 0
                for coll in ("schools", "staff", "students", "classes", "courses",
                             "enrollments", "grades", "learning_objects", "calendar_events",
                             "calendario_letivo", "school_assignments", "teacher_assignments",
                             "payroll_items", "announcements", "users", "pre_matriculas",
                             "mantenedora_documentos"):
                    try:
                        res = await db[coll].update_many(
                            {"$or": [
                                {"mantenedora_id": {"$exists": False}},
                                {"mantenedora_id": None},
                                {"mantenedora_id": ""},
                            ]},
                            {"$set": {"mantenedora_id": first_mant_id}},
                        )
                        if res.modified_count:
                            total_healed += res.modified_count
                            logger.info(
                                f"Self-heal: backfill mantenedora_id em {coll}: {res.modified_count} docs."
                            )
                    except Exception:
                        pass
                if total_healed:
                    logger.info(f"Self-heal: total de {total_healed} documentos migrados.")
        except Exception as exc:
            logger.warning(f"Self-heal multi-tenant ignorado: {exc}")
        
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

        # Feb 2026: Seed idempotente dos 8 modelos institucionais de Plano AEE.
        try:
            from seeds.aee_templates_seed import seed_aee_templates
            await seed_aee_templates(db)
        except Exception as exc:
            logger.warning(f"Seed AEE templates: ignorado por erro: {exc}")

        # May 2026: Seed idempotente do Currículo (BNCC complementar de Computação).
        try:
            from seeds.seed_computacao_bncc import seed_computacao
            stats = await seed_computacao(db)
            logger.info(f"Seed Currículo Computação: {stats}")
        except Exception as exc:
            logger.warning(f"Seed Currículo Computação: ignorado por erro: {exc}")
        
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
student_history_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)
vaccines_mod.setup_router(db)
mec_mod.setup_router(db)
bolsa_mod.setup_router(db)
pmpi_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)
pmpi_engine_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)
pmpi_ai_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)
action_plans_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)
student_portal_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)
admin_student_users_mod.setup_router(db, audit_service, sandbox_db, **_shared_kwargs)

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
app.include_router(create_mantenedoras_router(db))

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
app.include_router(student_history_mod.router, prefix="/api")
app.include_router(vaccines_mod.router, prefix="/api")
app.include_router(mec_mod.router, prefix="/api")
app.include_router(bolsa_mod.router, prefix="/api")
app.include_router(pmpi_mod.router, prefix="/api")
app.include_router(pmpi_engine_mod.router, prefix="/api")
app.include_router(pmpi_ai_mod.router, prefix="/api")
app.include_router(action_plans_mod.router, prefix="/api")
app.include_router(student_portal_mod.router, prefix="/api")
app.include_router(admin_student_users_mod.router, prefix="/api")
permission_overrides_mod.setup_router(db, audit_service)
app.include_router(permission_overrides_mod.router, prefix="/api")
spellcheck_mod.setup_router()
app.include_router(spellcheck_mod.router, prefix="/api")
app.include_router(curriculum_mod.setup_router(db), prefix="/api")
app.include_router(curriculum_import_mod.setup_router(db), prefix="/api")
app.include_router(curriculum_v2_mod.setup_router(db), prefix="/api")
app.include_router(interventions_mod.setup_router(db), prefix="/api")
app.include_router(tenant_admin_mod.setup_router(db), prefix="/api")
app.include_router(snapshots_mod.setup_router(db), prefix="/api")
_vd_public, _vd_admin = verifiable_docs_mod.setup_router(db, limiter=limiter)
app.include_router(_vd_public, prefix="/api")
app.include_router(_vd_admin, prefix="/api")
app.include_router(school_docs_mod.setup_router(db), prefix="/api")

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

# G2 (Fev/2026) — CSRF protection (double-submit cookie pattern).
# Só valida quando auth veio via cookie (Authorization Bearer não é vulnerável a CSRF).
# Pula endpoints públicos de autenticação e rotas não-API.
from starlette.middleware.base import BaseHTTPMiddleware
from auth_utils import ACCESS_COOKIE_NAME, CSRF_COOKIE_NAME, CSRF_HEADER_NAME

_CSRF_EXEMPT_PREFIXES = (
    '/api/auth/login',
    '/api/auth/register',
    '/api/auth/refresh',  # refresh só precisa do refresh_token cookie válido
    '/api/auth/forgot-password',
    '/api/auth/reset-password',
    '/api/auth/confirm-email-change',
    '/api/auth/resend-email-change',
    '/api/tenant/branding/public',
    '/api/pre-matricula',
)
_CSRF_PROTECTED_METHODS = ('POST', 'PUT', 'PATCH', 'DELETE')


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method not in _CSRF_PROTECTED_METHODS:
            return await call_next(request)

        path = request.url.path
        if not path.startswith('/api/'):
            return await call_next(request)

        # Pula endpoints públicos/preflight/migração
        if any(path.startswith(p) for p in _CSRF_EXEMPT_PREFIXES):
            return await call_next(request)

        # Só exige CSRF quando auth vem por COOKIE (Bearer não é vulnerável)
        has_access_cookie = bool(request.cookies.get(ACCESS_COOKIE_NAME))
        if not has_access_cookie:
            return await call_next(request)

        cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
        header_token = request.headers.get(CSRF_HEADER_NAME)
        if not cookie_token or not header_token or cookie_token != header_token:
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token inválido ou ausente"},
            )
        return await call_next(request)


app.add_middleware(CSRFMiddleware)

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
