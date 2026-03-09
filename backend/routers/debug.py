"""
Router para Debug.
Extraído de server.py durante a refatoração modular.
"""

from fastapi import APIRouter, HTTPException, status, Request
from fastapi.responses import FileResponse
from typing import Optional
from pathlib import Path
import os
import logging

from models import *
from auth_middleware import AuthMiddleware

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Debug"])

ROOT_DIR = Path(__file__).parent.parent
STATIC_DIR = ROOT_DIR / "static"


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências."""

    def get_db_for_user(user: dict):
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db

    ENABLE_BACKUP_DOWNLOAD = os.environ.get('ENABLE_BACKUP_DOWNLOAD', 'false').lower() == 'true'

    @router.get("/debug/ftp-config")
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

    @router.get("/download-backup")
    async def download_backup(request: Request):
        """Download database backup file - RESTRITO"""
        if not ENABLE_BACKUP_DOWNLOAD:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Download de backup desativado por segurança. Contate o administrador."
            )
        current_user = await AuthMiddleware.require_roles(['admin'])(request)
        backup_path = STATIC_DIR / "backup_sigesc.tar.gz"
        if backup_path.exists():
            return FileResponse(
                path=str(backup_path),
                filename="backup_sigesc.tar.gz",
                media_type="application/gzip"
            )
        return {"error": "Backup file not found"}

    @router.get("/download-uploads")
    async def download_uploads(request: Request):
        """Download uploads backup file - RESTRITO"""
        if not ENABLE_BACKUP_DOWNLOAD:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Download de backup desativado por segurança. Contate o administrador."
            )
        current_user = await AuthMiddleware.require_roles(['admin'])(request)
        backup_path = STATIC_DIR / "uploads_backup.tar.gz"
        if backup_path.exists():
            return FileResponse(
                path=str(backup_path),
                filename="uploads_backup.tar.gz",
                media_type="application/gzip"
            )
        return {"error": "Uploads backup file not found"}

    @router.get("/debug/courses/{class_id}")
    async def debug_courses_for_class(class_id: str, request: Request = None):
        """Debug: Retorna informações detalhadas sobre os componentes curriculares de uma turma."""
        current_user = await AuthMiddleware.get_current_user(request)

        class_info = await db.classes.find_one({"id": class_id}, {"_id": 0})
        if not class_info:
            raise HTTPException(status_code=404, detail="Turma não encontrada")

        school_id = class_info.get("school_id")
        school = await db.schools.find_one({"id": school_id}, {"_id": 0})
        if not school:
            raise HTTPException(status_code=404, detail="Escola não encontrada")

        nivel_ensino = class_info.get('nivel_ensino')
        grade_level = class_info.get('grade_level', '')
        grade_level_lower = grade_level.lower() if grade_level else ''

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
        turma_atendimento = class_info.get('atendimento_programa', '')
        turma_integral = turma_atendimento == 'atendimento_integral'

        courses_query = {}
        if nivel_ensino:
            courses_query['nivel_ensino'] = nivel_ensino

        all_courses = await db.courses.find(courses_query, {"_id": 0}).to_list(100)

        filtered_courses = []
        excluded_courses = []

        for course in all_courses:
            atendimento = course.get('atendimento_programa')
            course_grade_levels = course.get('grade_levels', [])
            course_name = course.get('name', 'N/A')

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
                "atendimento_programa": turma_atendimento
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

    return router
