"""
Router para Professor.
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


router = APIRouter(tags=["Professor"])


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

    @router.get("/professor/me")
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


    @router.get("/professor/turmas")
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


    @router.get("/professor/turmas/{class_id}/alunos")
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


    @router.get("/professor/turmas/{class_id}/componentes/{course_id}/notas")
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


    @router.get("/professor/turmas/{class_id}/componentes/{course_id}/frequencia")
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



    return router
