"""
Router de Servidores - SIGESC
PATCH 4.x: Rotas de servidores extraídas do server.py

Endpoints para gestão de servidores incluindo:
- CRUD básico
- Geração automática de matrícula
- Criação automática de usuário para professores
- Lotações e alocações
"""

from fastapi import APIRouter, HTTPException, status, Request, UploadFile, File
from typing import Optional
from datetime import datetime, timezone
import uuid

from models import Staff, StaffCreate, StaffUpdate
from auth_middleware import AuthMiddleware

router = APIRouter(prefix="/staff", tags=["Servidores"])


def setup_staff_router(db, audit_service, ftp_upload_func=None, sandbox_db=None):
    """Configura o router de servidores com as dependências necessárias"""
    
    def get_db_for_user(user: dict):
        """Retorna o banco correto baseado no usuário"""
        if False:  # Sandbox desabilitado
            return sandbox_db
        return db

    async def generate_matricula(current_db):
        """Gera matrícula automática no formato ANO + sequencial"""
        year = datetime.now().year
        prefix = str(year)
        
        last_staff = await current_db.staff.find(
            {"matricula": {"$regex": f"^{prefix}"}},
            {"_id": 0, "matricula": 1}
        ).sort("matricula", -1).limit(1).to_list(1)
        
        if last_staff:
            last_num = int(last_staff[0]['matricula'][4:])
            new_num = last_num + 1
        else:
            new_num = 1
        
        return f"{prefix}{new_num:05d}"

    @router.get("")
    async def list_staff(request: Request, school_id: Optional[str] = None, cargo: Optional[str] = None, status: Optional[str] = None):
        """Lista todos os servidores"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario', 'semed'])(request)
        current_db = get_db_for_user(current_user)
        
        query = {}
        if cargo:
            query["cargo"] = cargo
        if status:
            query["status"] = status
        
        staff_list = await current_db.staff.find(query, {"_id": 0}).to_list(1000)
        
        if school_id:
            filtered_staff = []
            for staff in staff_list:
                lotacao = await current_db.school_assignments.find_one({
                    "staff_id": staff['id'],
                    "school_id": school_id,
                    "status": "ativo"
                }, {"_id": 0})
                if lotacao:
                    staff['lotacao_atual'] = lotacao
                    filtered_staff.append(staff)
            staff_list = filtered_staff
        
        return staff_list

    @router.get("/{staff_id}")
    async def get_staff(staff_id: str, request: Request):
        """Busca servidor por ID"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario', 'semed', 'diretor'])(request)
        current_db = get_db_for_user(current_user)
        
        staff = await current_db.staff.find_one({"id": staff_id}, {"_id": 0})
        if not staff:
            raise HTTPException(status_code=404, detail="Servidor não encontrado")
        
        lotacoes = await current_db.school_assignments.find({"staff_id": staff_id}, {"_id": 0}).to_list(100)
        for lot in lotacoes:
            school = await current_db.schools.find_one({"id": lot['school_id']}, {"_id": 0, "name": 1})
            if school:
                lot['school_name'] = school['name']
        staff['lotacoes'] = lotacoes
        
        if staff['cargo'] == 'professor':
            alocacoes = await current_db.teacher_assignments.find({"staff_id": staff_id}, {"_id": 0}).to_list(100)
            for aloc in alocacoes:
                turma = await current_db.classes.find_one({"id": aloc['class_id']}, {"_id": 0, "name": 1})
                course = await current_db.courses.find_one({"id": aloc['course_id']}, {"_id": 0, "name": 1})
                if turma:
                    aloc['class_name'] = turma['name']
                if course:
                    aloc['course_name'] = course['name']
            staff['alocacoes'] = alocacoes
        
        return staff

    @router.post("")
    async def create_staff(staff_data: StaffCreate, request: Request):
        """Cria novo servidor com matrícula automática e cria usuário se for professor"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        matricula = await generate_matricula(current_db)
        
        user_id = None
        cpf_limpo = None
        
        if staff_data.cargo == 'professor' and staff_data.email and staff_data.cpf:
            existing_user = await current_db.users.find_one({"email": staff_data.email})
            if existing_user:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Já existe um usuário cadastrado com o email {staff_data.email}"
                )
            
            cpf_limpo = ''.join(filter(str.isdigit, staff_data.cpf))
            if len(cpf_limpo) < 6:
                raise HTTPException(
                    status_code=400, 
                    detail="CPF inválido. O CPF deve ter pelo menos 6 dígitos para gerar a senha."
                )
            senha = cpf_limpo[:6]
            
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
            
            await current_db.users.insert_one(new_user)
            user_id = new_user["id"]
        
        staff_dict = staff_data.model_dump()
        staff_dict['user_id'] = user_id
        
        new_staff = Staff(
            matricula=matricula,
            **staff_dict
        )
        
        await current_db.staff.insert_one(new_staff.model_dump())
        
        result = await current_db.staff.find_one({"id": new_staff.id}, {"_id": 0})
        
        if user_id:
            result['_user_created'] = True
            result['_user_message'] = f"Usuário criado com email {staff_data.email} e senha: {cpf_limpo[:6]} (6 primeiros dígitos do CPF)"
        
        await audit_service.log(
            action='create',
            collection='staff',
            user=current_user,
            request=request,
            document_id=new_staff.id,
            description=f"Cadastrou servidor: {staff_data.nome} (Matrícula: {matricula})"
        )
        
        return result

    @router.put("/{staff_id}")
    async def update_staff(staff_id: str, staff_data: StaffUpdate, request: Request):
        """Atualiza servidor (matrícula não pode ser alterada)"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        existing = await current_db.staff.find_one({"id": staff_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Servidor não encontrado")
        
        update_data = {k: v for k, v in staff_data.model_dump().items() if v is not None}
        update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
        
        await current_db.staff.update_one({"id": staff_id}, {"$set": update_data})
        
        await audit_service.log(
            action='update',
            collection='staff',
            user=current_user,
            request=request,
            document_id=staff_id,
            description=f"Atualizou servidor: {existing.get('nome')}"
        )
        
        return await current_db.staff.find_one({"id": staff_id}, {"_id": 0})

    @router.delete("/{staff_id}")
    async def delete_staff(staff_id: str, request: Request):
        """Remove servidor"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste'])(request)
        current_db = get_db_for_user(current_user)
        
        existing = await current_db.staff.find_one({"id": staff_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Servidor não encontrado")
        
        active_assignments = await current_db.school_assignments.find_one({"staff_id": staff_id, "status": "ativo"})
        if active_assignments:
            raise HTTPException(status_code=400, detail="Servidor possui lotações ativas. Encerre-as primeiro.")
        
        await current_db.staff.delete_one({"id": staff_id})
        
        await audit_service.log(
            action='delete',
            collection='staff',
            user=current_user,
            request=request,
            document_id=staff_id,
            description=f"EXCLUIU servidor: {existing.get('nome')} (Matrícula: {existing.get('matricula')})"
        )
        
        return {"message": "Servidor removido com sucesso"}

    @router.post("/{staff_id}/photo")
    async def upload_staff_photo(staff_id: str, request: Request, file: UploadFile = File(...)):
        """Upload de foto do servidor"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        existing = await current_db.staff.find_one({"id": staff_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Servidor não encontrado")
        
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Arquivo deve ser uma imagem")
        
        content = await file.read()
        
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Arquivo muito grande (máx 5MB)")
        
        ext = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
        filename = f"staff/{staff_id}/photo.{ext}"
        
        if ftp_upload_func:
            try:
                url = await ftp_upload_func(content, filename)
                
                await current_db.staff.update_one(
                    {"id": staff_id},
                    {"$set": {"foto_url": url}}
                )
                
                return {"url": url}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Erro no upload: {str(e)}")
        else:
            import os
            from pathlib import Path
            
            uploads_dir = Path(__file__).parent.parent / "uploads" / "staff"
            uploads_dir.mkdir(parents=True, exist_ok=True)
            
            filepath = uploads_dir / f"{staff_id}.{ext}"
            with open(filepath, 'wb') as f:
                f.write(content)
            
            url = f"/api/uploads/staff/{staff_id}.{ext}"
            
            await current_db.staff.update_one(
                {"id": staff_id},
                {"$set": {"foto_url": url}}
            )
            
            return {"url": url}

    return router
