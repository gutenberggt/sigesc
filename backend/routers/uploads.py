"""
Router para Uploads.
Extraído automaticamente de server.py.
"""

from fastapi import APIRouter, HTTPException, status, Request, UploadFile, File
from fastapi.responses import FileResponse
from typing import Optional
from pathlib import Path
import uuid
import os
import logging

from models import *
from auth_middleware import AuthMiddleware
from ftp_upload import upload_to_ftp

logger = logging.getLogger(__name__)

# Constantes
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.pdf', '.doc', '.docx', '.webp'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
UPLOADS_DIR = Path("/app/backend/uploads")
UPLOADS_DIR.mkdir(exist_ok=True)
CERTIFICADOS_DIR = UPLOADS_DIR / "certificados"
CERTIFICADOS_DIR.mkdir(exist_ok=True)


router = APIRouter(tags=["Uploads"])


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências."""
    
    # Helper para obter DB correto (produção ou sandbox)
    def get_db_for_user(user: dict):
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db



    @router.post("/upload/certificado")
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


    @router.post("/upload")
    async def upload_file(
        request: Request, 
        file: UploadFile = File(...), 
        file_type: Optional[str] = "default"
    ):
        """Upload de arquivo (foto, documento, laudo, etc.) para servidor externo via FTP"""
        # Qualquer usuário autenticado pode fazer upload de foto de perfil
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


    @router.delete("/upload/{filename}")
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


    @router.get("/uploads/{filename}")
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


    @router.get("/uploads/staff/{filename}")
    async def get_staff_photo(filename: str):
        """Serve foto do servidor"""
        from fastapi.responses import FileResponse
        filepath = f"/app/backend/uploads/staff/{filename}"
        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="Foto não encontrada")
        return FileResponse(filepath)

    # ============= OBJETOS DE CONHECIMENTO =============

    from models import LearningObject, LearningObjectCreate, LearningObjectUpdate



    return router
