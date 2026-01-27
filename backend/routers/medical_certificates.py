"""
Router de Atestados Médicos - SIGESC
Gerencia registro de atestados médicos de alunos
"""
from fastapi import APIRouter, HTTPException, status, Request
from typing import List, Optional
from datetime import datetime, timezone
import logging

from models import (
    MedicalCertificate, 
    MedicalCertificateCreate, 
    MedicalCertificateUpdate
)

logger = logging.getLogger(__name__)

def setup_medical_certificates_router(db, auth_middleware):
    """Configura o router de atestados médicos"""
    
    router = APIRouter(prefix="/medical-certificates", tags=["Atestados Médicos"])
    
    @router.post("", response_model=dict)
    async def create_medical_certificate(request: Request, certificate: MedicalCertificateCreate):
        """
        Cria um novo atestado médico para um aluno.
        Apenas secretários e administradores podem registrar.
        """
        current_user = await auth_middleware.get_current_user(request)
        
        # Verificar permissão (apenas secretário e admin)
        if current_user['role'] not in ['admin', 'secretario']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Apenas secretários e administradores podem registrar atestados médicos"
            )
        
        # Validar datas
        try:
            start = datetime.strptime(certificate.start_date, "%Y-%m-%d")
            end = datetime.strptime(certificate.end_date, "%Y-%m-%d")
            if end < start:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A data final não pode ser anterior à data inicial"
                )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Formato de data inválido. Use YYYY-MM-DD"
            )
        
        # Verificar se o aluno existe
        student = await db.students.find_one({"id": certificate.student_id})
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aluno não encontrado"
            )
        
        # Verificar sobreposição de atestados
        existing = await db.medical_certificates.find_one({
            "student_id": certificate.student_id,
            "$or": [
                {
                    "start_date": {"$lte": certificate.end_date},
                    "end_date": {"$gte": certificate.start_date}
                }
            ]
        })
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Já existe um atestado médico para este aluno no período de {existing['start_date']} a {existing['end_date']}"
            )
        
        # Criar o atestado
        cert_data = MedicalCertificate(
            **certificate.model_dump(),
            created_by=current_user['id'],
            created_by_name=current_user.get('full_name', current_user.get('email'))
        )
        
        cert_dict = cert_data.model_dump()
        cert_dict['created_at'] = cert_dict['created_at'].isoformat()
        
        await db.medical_certificates.insert_one(cert_dict)
        
        logger.info(f"[MedicalCertificate] Atestado criado para aluno {certificate.student_id} por {current_user['email']}")
        
        return {
            "message": "Atestado médico registrado com sucesso",
            "id": cert_data.id,
            "student_id": certificate.student_id,
            "period": f"{certificate.start_date} a {certificate.end_date}"
        }
    
    @router.get("/student/{student_id}", response_model=List[dict])
    async def get_student_certificates(request: Request, student_id: str):
        """
        Lista todos os atestados médicos de um aluno.
        """
        current_user = await auth_middleware.get_current_user(request)
        
        certificates = await db.medical_certificates.find(
            {"student_id": student_id},
            {"_id": 0}
        ).sort("start_date", -1).to_list(100)
        
        return certificates
    
    @router.get("/check/{student_id}/{date}", response_model=dict)
    async def check_certificate_for_date(request: Request, student_id: str, date: str):
        """
        Verifica se existe atestado médico para um aluno em uma data específica.
        Usado pela tela de frequência para bloquear lançamento.
        """
        current_user = await auth_middleware.get_current_user(request)
        
        certificate = await db.medical_certificates.find_one({
            "student_id": student_id,
            "start_date": {"$lte": date},
            "end_date": {"$gte": date}
        }, {"_id": 0})
        
        if certificate:
            return {
                "has_certificate": True,
                "certificate_id": certificate['id'],
                "reason": certificate.get('reason', 'Atestado Médico'),
                "period": f"{certificate['start_date']} a {certificate['end_date']}"
            }
        
        return {"has_certificate": False}
    
    @router.get("/check-bulk/{date}", response_model=dict)
    async def check_certificates_bulk(request: Request, date: str, student_ids: str = ""):
        """
        Verifica atestados médicos para múltiplos alunos em uma data.
        student_ids deve ser uma string separada por vírgulas.
        Retorna um dicionário com student_id como chave.
        """
        current_user = await auth_middleware.get_current_user(request)
        
        if not student_ids:
            return {"certificates": {}}
        
        ids_list = [s.strip() for s in student_ids.split(",") if s.strip()]
        
        certificates = await db.medical_certificates.find({
            "student_id": {"$in": ids_list},
            "start_date": {"$lte": date},
            "end_date": {"$gte": date}
        }, {"_id": 0}).to_list(500)
        
        # Criar dicionário por student_id
        result = {}
        for cert in certificates:
            result[cert['student_id']] = {
                "certificate_id": cert['id'],
                "reason": cert.get('reason', 'Atestado Médico'),
                "period": f"{cert['start_date']} a {cert['end_date']}"
            }
        
        return {"certificates": result}
    
    @router.get("/{certificate_id}", response_model=dict)
    async def get_certificate(request: Request, certificate_id: str):
        """
        Obtém detalhes de um atestado médico específico.
        """
        current_user = await auth_middleware.get_current_user(request)
        
        certificate = await db.medical_certificates.find_one(
            {"id": certificate_id},
            {"_id": 0}
        )
        
        if not certificate:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Atestado médico não encontrado"
            )
        
        return certificate
    
    @router.put("/{certificate_id}", response_model=dict)
    async def update_certificate(request: Request, certificate_id: str, update: MedicalCertificateUpdate):
        """
        Atualiza um atestado médico.
        Apenas secretários e administradores podem atualizar.
        """
        current_user = await auth_middleware.get_current_user(request)
        
        if current_user['role'] not in ['admin', 'secretario']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Apenas secretários e administradores podem atualizar atestados médicos"
            )
        
        # Verificar se existe
        existing = await db.medical_certificates.find_one({"id": certificate_id})
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Atestado médico não encontrado"
            )
        
        # Preparar dados de atualização
        update_data = {k: v for k, v in update.model_dump().items() if v is not None}
        
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nenhum dado para atualizar"
            )
        
        # Validar datas se fornecidas
        start = update_data.get('start_date', existing['start_date'])
        end = update_data.get('end_date', existing['end_date'])
        
        try:
            start_dt = datetime.strptime(start, "%Y-%m-%d")
            end_dt = datetime.strptime(end, "%Y-%m-%d")
            if end_dt < start_dt:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A data final não pode ser anterior à data inicial"
                )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Formato de data inválido. Use YYYY-MM-DD"
            )
        
        update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
        
        await db.medical_certificates.update_one(
            {"id": certificate_id},
            {"$set": update_data}
        )
        
        logger.info(f"[MedicalCertificate] Atestado {certificate_id} atualizado por {current_user['email']}")
        
        return {"message": "Atestado médico atualizado com sucesso"}
    
    @router.delete("/{certificate_id}", response_model=dict)
    async def delete_certificate(request: Request, certificate_id: str):
        """
        Exclui um atestado médico.
        APENAS ADMINISTRADORES podem excluir.
        """
        current_user = await auth_middleware.get_current_user(request)
        
        # Verificar permissão - APENAS admin
        if current_user['role'] != 'admin':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Apenas administradores podem excluir atestados médicos"
            )
        
        # Verificar se existe
        existing = await db.medical_certificates.find_one({"id": certificate_id})
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Atestado médico não encontrado"
            )
        
        await db.medical_certificates.delete_one({"id": certificate_id})
        
        logger.info(f"[MedicalCertificate] Atestado {certificate_id} excluído por {current_user['email']}")
        
        return {"message": "Atestado médico excluído com sucesso"}
    
    @router.get("", response_model=List[dict])
    async def list_certificates(
        request: Request,
        student_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100
    ):
        """
        Lista atestados médicos com filtros opcionais.
        """
        current_user = await auth_middleware.get_current_user(request)
        
        query = {}
        
        if student_id:
            query["student_id"] = student_id
        
        if start_date:
            query["end_date"] = {"$gte": start_date}
        
        if end_date:
            if "start_date" not in query:
                query["start_date"] = {}
            query["start_date"]["$lte"] = end_date
        
        certificates = await db.medical_certificates.find(
            query,
            {"_id": 0}
        ).sort("created_at", -1).to_list(limit)
        
        return certificates
    
    return router
