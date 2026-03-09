"""
Router para Mantenedora.
Extraído automaticamente de server.py.
"""

from fastapi import APIRouter, HTTPException, status, Request, Query, UploadFile, File
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse, JSONResponse
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import uuid
import json
import re
import io
import os
import ftplib

from models import *
from auth_middleware import AuthMiddleware
from text_utils import format_data_uppercase


router = APIRouter(tags=["Mantenedora"])


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências."""
    
    # Helper para obter DB correto (produção ou sandbox)
    def get_db_for_user(user: dict):
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db

    # Helpers passados via kwargs
    check_bimestre_edit_deadline = kwargs.get('check_bimestre_edit_deadline')
    verify_bimestre_edit_deadline_or_raise = kwargs.get('verify_bimestre_edit_deadline_or_raise')
    verify_academic_year_open_or_raise = kwargs.get('verify_academic_year_open_or_raise')
    check_academic_year_open = kwargs.get('check_academic_year_open')

    @router.get("/mantenedora", response_model=Mantenedora)
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


    @router.put("/mantenedora", response_model=Mantenedora)
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



    return router
