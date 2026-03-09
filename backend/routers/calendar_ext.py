"""
Router para Calendário Estendido.
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


router = APIRouter(tags=["Calendário Estendido"])


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

    @router.get("/calendario-letivo/{ano_letivo}/periodos")
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


    @router.get("/calendario-letivo/{ano_letivo}/status-edicao")
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



    return router
