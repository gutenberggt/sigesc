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
from routers.student_dependencies import setup_student_dependencies_router
from routers.class_schedule import setup_class_schedule_router
from routers.diary_dashboard import create_diary_dashboard_router
from routers.diary import setup_diary_router
from routers.content_entries import setup_content_entries_router
from routers.teacher_class_assignments import setup_teacher_class_assignments_router
from routers.calendar_diary_state import setup_calendar_diary_state_router
from routers.diary_snapshots import setup_diary_snapshots_router
from routers.academic_events import setup_academic_events_router
from routers.closure import setup_closure_router
from routers.render_jobs import setup_render_jobs_router
from routers.bulletins import setup_bulletins_router
from routers.bulletin_pdf import setup_bulletin_pdf_router
from routers.history_pdf import setup_history_pdf_router
from utils.academic_event_lens import ensure_indexes as _ensure_event_indexes
from utils.render_jobs import ensure_indexes as _ensure_render_indexes
from routers.dependency_completions import (
    setup_dependency_completions_router,
    setup_public_verification_router,
    setup_admin_completions_backfill_router,
    ensure_indexes as _ensure_completions_indexes,
)
from routers.aee import setup_aee_router
from routers.auth import setup_router as setup_auth_router
from routers.mantenedoras import create_mantenedoras_router
from routers.admin_observability import setup_admin_observability_router

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
from routers import monthly_reports as monthly_reports_mod
from routers import content_review as content_review_mod
from routers import text_improvement as text_improvement_mod

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

# Render worker (Passo 4) — single-process background task.
import asyncio
_render_worker_task: asyncio.Task | None = None
_render_worker_stop: asyncio.Event | None = None

@app.on_event("startup")
async def create_indexes():
    """Startup: índices, serviços externos, multi-tenant bootstrap, self-heal e seeds.

    Extraído para `startup/*` (Fev/2026). Ordem de execução preservada.
    """
    try:
        # Serviços externos (snapshots, verifiable_docs, monthly_reports)
        from startup.seeds import init_external_services, run_all_seeds
        await init_external_services(db, client)

        # Índices MongoDB
        from startup.indexes import create_all_indexes
        await create_all_indexes(db)

        # Bootstrap multi-tenant + self-heal idempotente
        from startup.multi_tenant import bootstrap_initial_mantenedora, self_heal_tenant_data
        await bootstrap_initial_mantenedora(db)
        await self_heal_tenant_data(db)

        # Sandbox + token blacklist
        await sandbox_service.initialize(client)
        token_blacklist.set_db(db)
        await token_blacklist.ensure_index()

        # Seeds (AEE templates, BNCC Computação)
        await run_all_seeds(db)

        # Fase 2.5 — índices de dependency_completions (idempotente)
        await _ensure_completions_indexes(db)
        # Fase 3 — índices de academic_events (idempotente)
        await _ensure_event_indexes(db)
        # Passo 4 — índices de document_render_jobs (idempotente)
        await _ensure_render_indexes(db)

        # Fase 5 (Mai/2026) — índices de diary_snapshots (idempotente)
        from services import diary_snapshot_service as _diary_snap_svc
        await _diary_snap_svc.ensure_indexes(db)

        # Verifiable Documents MVP — índices novos + backfill de verification_token
        from services import verifiable_docs_service as _vdsvc
        await _vdsvc.ensure_indexes(db)
        try:
            n = await _vdsvc.backfill_verification_tokens(db)
            if n:
                logger.info(f"[startup] verification_token backfill: {n} docs atualizados")
        except Exception as e:
            logger.warning(f"[startup] backfill verification_token falhou: {e}")

        # Sanidade crítica: SNAPSHOT_HMAC_SECRET é o que prova "SIGESC emitiu este doc".
        # Sem ele, todos os docs verificarão como 'assinatura inválida/ausente'.
        _hmac_env = os.environ.get("SNAPSHOT_HMAC_SECRET", "")
        if not _hmac_env:
            logger.error(
                "[startup] CRITICAL: SNAPSHOT_HMAC_SECRET ausente no processo Python — "
                "todos os documentos verificarão como assinatura inválida. "
                "Configure a variável de ambiente (runtime, não build) com uma string "
                "longa estável (64 hex chars recomendado) e REINICIE o container."
            )
        else:
            logger.info(
                "[startup] SNAPSHOT_HMAC_SECRET carregado: len=%d chars (head=%s..., tail=...%s)",
                len(_hmac_env),
                _hmac_env[:4],
                _hmac_env[-4:],
            )

        # Passo 4 — worker de render jobs (in-process, single-loop)
        if os.environ.get("DISABLE_RENDER_WORKER", "").lower() not in {"1", "true", "yes"}:
            from services.render_worker import run_worker_loop
            from utils.render_jobs import register_render_handler
            from services.bulletin_renderer import render_bulletin_handler
            from services.history_renderer import render_history_handler
            import asyncio as _asyncio

            # Base URL para o QR Code de verificação pública
            _public_base = (
                os.environ.get("PUBLIC_VERIFY_BASE_URL")
                or os.environ.get("APP_FRONTEND_URL")
                or os.environ.get("REACT_APP_BACKEND_URL")
                or ""
            )

            async def _bulletin_handler_wrapper(job: dict):
                return await render_bulletin_handler(job, db=db, public_base_url=_public_base)

            async def _history_handler_wrapper(job: dict):
                return await render_history_handler(job, db=db, public_base_url=_public_base)

            register_render_handler("bulletin", _bulletin_handler_wrapper)
            register_render_handler("history", _history_handler_wrapper)

            # Fase 5 (Mai/2026) — handler do snapshot do Diário Escolar.
            from services.diary_pdf_handler import render_diary_handler

            async def _diary_handler_wrapper(job: dict):
                return await render_diary_handler(job, db=db, public_base_url=_public_base)

            register_render_handler("diary_period", _diary_handler_wrapper)
            logger.info("[startup] handlers 'bulletin', 'history' e 'diary_period' registrados (base=%s)", _public_base)

            global _render_worker_task, _render_worker_stop
            _render_worker_stop = _asyncio.Event()
            _render_worker_task = _asyncio.create_task(
                run_worker_loop(db, stop_event=_render_worker_stop)
            )
            logger.info("[startup] render worker task scheduled")

    except Exception as e:
        logger.error(f"Erro no startup: {e}")

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

# Dependência de Estudos (Fase 1) — entidade própria, ver /app/docs/STUDENT_DEPENDENCY.md
from tenant_scope import apply_tenant_filter as _apply_tenant_filter_for_deps
student_dependencies_router = setup_student_dependencies_router(
    db, AuthMiddleware, audit_service=audit_service,
    apply_tenant_filter=_apply_tenant_filter_for_deps,
)
diary_dashboard_router = create_diary_dashboard_router()
diary_router = setup_diary_router(db)
content_entries_router = setup_content_entries_router(db, audit_service, sandbox_db)
teacher_class_assignments_router = setup_teacher_class_assignments_router(db, audit_service, sandbox_db)
calendar_diary_state_router = setup_calendar_diary_state_router(db)
diary_snapshots_router = setup_diary_snapshots_router(db, audit_service=audit_service)
completions_router = setup_dependency_completions_router(db, audit_service=audit_service)
public_verify_router = setup_public_verification_router(db)
admin_completions_router = setup_admin_completions_backfill_router(db)
academic_events_router = setup_academic_events_router(db, audit_service=audit_service)
closure_router = setup_closure_router(db)
render_jobs_router = setup_render_jobs_router(db, audit_service=audit_service)
bulletins_router = setup_bulletins_router(db)
bulletin_pdf_router = setup_bulletin_pdf_router(db, audit_service=audit_service)
history_pdf_router = setup_history_pdf_router(db, audit_service=audit_service)
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

# Observabilidade (admin) — endpoint super_admin only com audit log
admin_observability_router = setup_admin_observability_router(audit_service, db=db)
app.include_router(admin_observability_router, prefix="/api")

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
app.include_router(student_dependencies_router, prefix="/api")
app.include_router(class_schedule_router, prefix="/api")
app.include_router(diary_dashboard_router, prefix="/api")
app.include_router(diary_router, prefix="/api")
app.include_router(content_entries_router, prefix="/api")
app.include_router(teacher_class_assignments_router, prefix="/api")
app.include_router(calendar_diary_state_router, prefix="/api")
app.include_router(diary_snapshots_router, prefix="/api")
app.include_router(completions_router, prefix="/api")
app.include_router(public_verify_router, prefix="/api")
app.include_router(admin_completions_router, prefix="/api")
app.include_router(academic_events_router, prefix="/api")
app.include_router(closure_router, prefix="/api")
app.include_router(render_jobs_router, prefix="/api")
app.include_router(bulletins_router, prefix="/api")
app.include_router(bulletin_pdf_router, prefix="/api")
app.include_router(history_pdf_router, prefix="/api")
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
app.include_router(monthly_reports_mod.setup_router(db), prefix="/api")
app.include_router(content_review_mod.setup_router(db), prefix="/api")
app.include_router(text_improvement_mod.setup_router(db), prefix="/api")

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
from typing import Optional

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


def _csrf_from_jwt(token_str: str) -> Optional[str]:
    """Extrai o claim 'csrf' de um JWT sem validar assinatura/expiração.

    Validação completa é feita pelo auth middleware downstream — aqui só
    queremos comparar o claim com o header. Se o JWT for inválido, o
    auth middleware rejeita depois com 401.
    """
    try:
        from jose import jwt as _jwt
        payload = _jwt.get_unverified_claims(token_str)
        val = payload.get('csrf')
        return str(val) if val else None
    except Exception:
        return None


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

        # Identifica o access token: cookie OU Authorization Bearer
        # (qualquer um dos dois ativa proteção CSRF)
        access_token_str = request.cookies.get(ACCESS_COOKIE_NAME)
        auth_header = request.headers.get('Authorization', '')
        if not access_token_str and auth_header.startswith('Bearer '):
            access_token_str = auth_header[7:].strip()
        if not access_token_str:
            # Sem auth → não é alvo de CSRF (será rejeitado por 401 depois)
            return await call_next(request)

        header_token = request.headers.get(CSRF_HEADER_NAME)
        if not header_token:
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token inválido ou ausente"},
            )

        # Source of truth: claim 'csrf' embutido no JWT (cross-domain safe).
        # Fallback: cookie sigesc_csrf (double-submit clássico).
        jwt_csrf = _csrf_from_jwt(access_token_str)
        cookie_csrf = request.cookies.get(CSRF_COOKIE_NAME)

        if jwt_csrf and header_token == jwt_csrf:
            return await call_next(request)
        if cookie_csrf and header_token == cookie_csrf:
            return await call_next(request)

        return JSONResponse(
            status_code=403,
            content={"detail": "CSRF token inválido ou ausente"},
        )


app.add_middleware(CSRFMiddleware)

# ===== CORS — whitelist inteligente + regex opcional, sem quebrar ambientes =====
# [Fev/2026] Hardening: origin '*' é INCOMPATÍVEL com allow_credentials=True (RFC).
# Whitelist construída a partir de múltiplas fontes:
#   1. CORS_ORIGINS (lista por vírgula) — prioridade.
#   2. APP_FRONTEND_URL — a URL do frontend oficial (sempre incluída se existir).
#   3. REACT_APP_BACKEND_URL — útil quando o próprio backend faz callbacks pra si.
#   4. CORS_ORIGIN_REGEX — regex p/ múltiplos subdomínios (ex.: produção com ingress dinâmico).
#   5. Se NADA resolver, cai em modo permissivo com credentials=False (seguro + funcional).
_env_origins = set()

_cors_raw = (os.environ.get('CORS_ORIGINS') or '').strip()
if _cors_raw and _cors_raw != '*':
    for o in _cors_raw.split(','):
        o = o.strip().rstrip('/')
        if o:
            _env_origins.add(o)

for _env_key in ('APP_FRONTEND_URL', 'REACT_APP_BACKEND_URL', 'FRONTEND_URL'):
    _v = (os.environ.get(_env_key) or '').strip().rstrip('/')
    if _v:
        _env_origins.add(_v)

# Sempre permitir dev local (não afeta produção, que não usa essas origens).
_env_origins.update({
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:8001',
})

# Regex opcional para múltiplos subdomínios em produção.
# Ex.: CORS_ORIGIN_REGEX="https://.*\.aprenderdigital\.top"
_cors_regex = (os.environ.get('CORS_ORIGIN_REGEX') or '').strip() or None

if _env_origins or _cors_regex:
    _allowed_origins = sorted(_env_origins)
    _allow_creds = True
    logger.info(
        f"CORS: whitelist com {len(_allowed_origins)} origem(ns) "
        f"+ regex={'sim' if _cors_regex else 'não'}, credentials=True."
    )
else:
    # Último recurso: modo permissivo MAS sem credenciais (seguro por especificação).
    _allowed_origins = ["*"]
    _allow_creds = False
    logger.warning(
        "CORS: nenhuma origem configurada (CORS_ORIGINS/APP_FRONTEND_URL/CORS_ORIGIN_REGEX ausentes). "
        "Fallback para '*' com credentials=False."
    )

app.add_middleware(
    CORSMiddleware,
    allow_credentials=_allow_creds,
    allow_origins=_allowed_origins,
    allow_origin_regex=_cors_regex,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Requested-With"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    """Fecha conexão com MongoDB ao desligar"""
    # Para o render worker antes de fechar a conexão.
    try:
        if _render_worker_stop is not None:
            _render_worker_stop.set()
        if _render_worker_task is not None:
            await asyncio.wait_for(_render_worker_task, timeout=10)
    except Exception as e:
        logger.warning(f"render worker shutdown: {e}")
    client.close()
    logger.info("MongoDB connection closed")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
