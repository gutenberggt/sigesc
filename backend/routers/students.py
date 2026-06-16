"""
Router de Alunos - SIGESC
PATCH 4.x: Rotas de alunos extraídas do server.py

Endpoints para gestão de alunos incluindo:
- CRUD básico
- Remanejamento de turma
- Transferência entre escolas
- Histórico de movimentações
"""

from fastapi import APIRouter, HTTPException, status, Request, Query
from fastapi.responses import StreamingResponse
from typing import Optional, List
from datetime import datetime, timezone
from pydantic import BaseModel
from io import BytesIO
import uuid
import re
import logging
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from models import Student, StudentCreate, StudentUpdate
from auth_middleware import AuthMiddleware
from tenant_scope import apply_tenant_filter, assert_same_tenant, resolve_tenant_id_for_create, get_mantenedora_scope
from utils.serie_canonical import canonicalize_serie, UNRECOGNIZED_KEY

router = APIRouter(prefix="/students", tags=["Alunos"])

logger = logging.getLogger(__name__)


def _is_filled(v):
    return v is not None and str(v).strip() != ""


def _compute_student_completeness(student: dict) -> int:
    """Calcula a % de completude do cadastro do aluno (0-100).

    ESPELHADO com o frontend (utils/registrationCompleteness.js). Conjunto
    AMPLIADO de 14 critérios: obrigatórios + documento + telefone do responsável
    + turma + matrícula. Mantenha os dois lados em sincronia.
    """
    s = student or {}
    checks = [
        _is_filled(s.get("full_name")),
        _is_filled(s.get("birth_date")),
        _is_filled(s.get("sex")),
        _is_filled(s.get("nationality")),
        _is_filled(s.get("color_race")),
        _is_filled(s.get("comunidade_tradicional")),
        _is_filled(s.get("birth_city")),
        _is_filled(s.get("birth_state")),
        _is_filled(s.get("mother_name")),
        _is_filled(s.get("legal_guardian_type")),
        # Documento: CPF, NIS ou Certidão Civil
        any(_is_filled(s.get(k)) for k in ("cpf", "nis", "civil_certificate_number")),
        # Telefone de algum responsável
        any(_is_filled(s.get(k)) for k in ("mother_phone", "father_phone", "guardian_phone")),
        _is_filled(s.get("class_id")),
        _is_filled(s.get("enrollment_number")),
    ]
    total = len(checks)
    filled = sum(1 for c in checks if c)
    return round(filled / total * 100) if total else 0


# --- Completude em AGGREGATION (espelha _compute_student_completeness) ---
# Usado para contar alunos por faixa (verde/amarelo/vermelho) sobre TODO o
# conjunto filtrado e para filtrar a lista server-side por faixa.
def _agg_filled(field: str):
    """Expr que retorna True se o campo está preenchido (não vazio após trim)."""
    return {"$gt": [{"$strLenCP": {"$trim": {"input": {"$toString": {"$ifNull": [f"${field}", ""]}}}}}, 0]}


def _agg_any(*fields):
    return {"$or": [_agg_filled(f) for f in fields]}


# Mesmos 14 critérios de _compute_student_completeness, na MESMA ordem.
_COMPLETENESS_CRITERIA_EXPR = [
    _agg_filled("full_name"),
    _agg_filled("birth_date"),
    _agg_filled("sex"),
    _agg_filled("nationality"),
    _agg_filled("color_race"),
    _agg_filled("comunidade_tradicional"),
    _agg_filled("birth_city"),
    _agg_filled("birth_state"),
    _agg_filled("mother_name"),
    _agg_filled("legal_guardian_type"),
    _agg_any("cpf", "nis", "civil_certificate_number"),
    _agg_any("mother_phone", "father_phone", "guardian_phone"),
    _agg_filled("class_id"),
    _agg_filled("enrollment_number"),
]


def _completeness_pct_stage():
    """$addFields que calcula `_pct` (0-100) idêntico ao cálculo do Python."""
    n = len(_COMPLETENESS_CRITERIA_EXPR)
    return {"$addFields": {
        "_pct": {"$round": [{"$multiply": [
            {"$divide": [
                {"$add": [{"$cond": [c, 1, 0]} for c in _COMPLETENESS_CRITERIA_EXPR]},
                n,
            ]}, 100]}, 0]}
    }}


# Condições de faixa sobre `_pct` (espelham completenessColor: verde>=80,
# amarelo 50-79, vermelho <50).
_BAND_EXPR = {
    "green": {"$gte": ["$_pct", 80]},
    "yellow": {"$and": [{"$gte": ["$_pct", 50]}, {"$lt": ["$_pct", 80]}]},
    "red": {"$lt": ["$_pct", 50]},
}


def setup_students_router(db, audit_service, sandbox_db=None):
    """Configura o router de alunos com as dependências necessárias"""
    
    def get_db_for_user(user: dict):
        """Retorna o banco correto baseado no usuário"""
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db

    async def generate_enrollment_number(current_db, academic_year: int) -> str:
        """Gera número de matrícula. Delega para a FONTE ÚNICA atômica
        (utils.enrollment.generate_enrollment_number)."""
        from utils.enrollment import generate_enrollment_number as _gen_atomic
        return await _gen_atomic(current_db, academic_year)

    @router.post("", response_model=Student, status_code=status.HTTP_201_CREATED)
    async def create_student(student_data: StudentCreate, request: Request):
        """Cria novo aluno"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        # Verifica acesso à escola
        await AuthMiddleware.verify_school_access(request, student_data.school_id)
        
        # VALIDAÇÃO: Não permite status "Ativo" sem escola e turma definidas
        if student_data.status == 'active':
            if not student_data.school_id or not student_data.class_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Não é possível criar aluno com status 'Ativo' sem escola e turma definidas. O aluno precisa estar matriculado em uma turma."
                )
            # [Fase 0 — Contenção] Garante que a turma EXISTE e pertence à
            # escola do aluno. Impede criação de matrículas órfãs (class_id
            # apontando para turma inexistente ou de outra escola), que
            # contaminavam relatórios, dashboards e censo.
            class_check = await current_db.classes.find_one(
                {"id": student_data.class_id},
                {"_id": 0, "school_id": 1}
            )
            if not class_check:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Turma inexistente (class_id={student_data.class_id}). Selecione uma turma válida."
                )
            if class_check.get('school_id') != student_data.school_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="A turma selecionada pertence a outra escola. Selecione uma turma da mesma escola do aluno."
                )
        
        student_dict = student_data.model_dump()
        # Matrícula é SEMPRE gerada pelo backend (fonte ÚNICA atômica).
        # Ignora qualquer valor enviado pelo cliente para impedir colisões.
        student_dict['enrollment_number'] = None
        # [Fase 0 — Contenção] Deduplica `disabilities[]` preservando ordem.
        if isinstance(student_dict.get('disabilities'), list):
            seen = set()
            student_dict['disabilities'] = [
                d for d in student_dict['disabilities']
                if not (d in seen or seen.add(d))
            ]
        student_obj = Student(**student_dict)
        doc = student_obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()

        # [Mai/2026] Pré-computa índices de busca (case- e accent-insensitive)
        from text_utils import compute_name_indexes
        normalized, busca = compute_name_indexes(doc, 'full_name')
        if busca:
            doc['nome_normalizado'] = normalized
            doc['nome_busca'] = busca

        # [Mai/2026] Normalização leve de CAPS em campos textuais (observations).
        from utils.text_normalize import normalize_input_fields
        doc = normalize_input_fields(doc, "students")

        # Multi-tenancy: injeta mantenedora_id derivada da escola
        doc['mantenedora_id'] = await resolve_tenant_id_for_create(
            current_db, current_user, request, school_id=student_data.school_id
        )
        
        # Matrícula atômica: gerada ANTES de inserir e SOMENTE quando o aluno
        # será efetivamente matriculado (ativo + turma). A mesma matrícula é
        # usada no doc do aluno e no doc de enrollment (fonte única).
        new_enrollment_number = None
        if student_obj.class_id and student_obj.status == 'active':
            new_enrollment_number = await generate_enrollment_number(
                current_db, datetime.now().year
            )
            doc['enrollment_number'] = new_enrollment_number
            student_obj.enrollment_number = new_enrollment_number

        await current_db.students.insert_one(doc)
        
        # Se o aluno tem turma, cria a matrícula automaticamente
        if student_obj.class_id and student_obj.status == 'active':
            academic_year = datetime.now().year
            
            # Busca grade_level da turma para student_series
            class_info = await current_db.classes.find_one(
                {"id": student_obj.class_id}, {"_id": 0, "grade_level": 1}
            )
            
            enrollment_doc = {
                "id": str(uuid.uuid4()),
                "student_id": student_obj.id,
                "school_id": student_obj.school_id,
                "class_id": student_obj.class_id,
                "academic_year": academic_year,
                "status": "active",
                "student_series": student_data.student_series or (class_info.get('grade_level') if class_info else None),
                "enrollment_number": new_enrollment_number,
                "enrollment_date": student_data.enrollment_date or datetime.now().isoformat(),
                "created_at": datetime.now().isoformat()
            }
            await current_db.enrollments.insert_one(enrollment_doc)
        
        # Registra auditoria
        school = await current_db.schools.find_one({"id": student_data.school_id}, {"_id": 0, "name": 1})
        await audit_service.log(
            action='create',
            collection='students',
            user=current_user,
            request=request,
            document_id=student_obj.id,
            description=f"Cadastrou aluno: {student_obj.full_name}",
            school_id=student_data.school_id,
            school_name=school.get('name') if school else None,
            new_value={'full_name': student_obj.full_name, 'cpf': student_obj.cpf, 'class_id': student_obj.class_id}
        )
        
        return student_obj

    @router.get("/inconsistencies")
    async def get_student_inconsistencies(request: Request):
        """
        [Fase 0 — Contenção] Diagnóstico de inconsistências de integridade
        em alunos ATIVOS. Lista alunos com:
          - `class_id` ausente/nulo
          - `class_id` apontando para turma inexistente
          - `class_id` apontando para turma de outra escola
          - `school_id` ausente
          - `school_id` apontando para escola inexistente

        Retorna estrutura agregada (totais + amostra) para uso em banner
        administrativo de saúde de dados. Restrito a perfis administrativos.
        """
        current_user = await AuthMiddleware.require_roles(
            ['super_admin', 'admin', 'admin_teste', 'gerente', 'semed', 'semed1', 'semed2', 'semed3']
        )(request)
        current_db = get_db_for_user(current_user)

        # Filtro tenant-aware: super_admin vê tudo; demais limitados ao próprio tenant.
        base_filter = {"status": "active"}
        if current_user.get('role') != 'super_admin':
            tenant_id = current_user.get('mantenedora_id')
            if tenant_id:
                base_filter['mantenedora_id'] = tenant_id

        pipeline = [
            {"$match": base_filter},
            {"$lookup": {
                "from": "classes",
                "localField": "class_id",
                "foreignField": "id",
                "as": "_class",
            }},
            {"$lookup": {
                "from": "schools",
                "localField": "school_id",
                "foreignField": "id",
                "as": "_school",
            }},
            {"$addFields": {
                "_class_obj": {"$arrayElemAt": ["$_class", 0]},
                "_school_obj": {"$arrayElemAt": ["$_school", 0]},
            }},
            {"$addFields": {
                "_issues": {
                    "$concatArrays": [
                        {"$cond": [
                            {"$or": [
                                {"$eq": ["$class_id", None]},
                                {"$eq": ["$class_id", ""]},
                            ]},
                            ["sem_turma"], []
                        ]},
                        {"$cond": [
                            {"$and": [
                                {"$ne": ["$class_id", None]},
                                {"$ne": ["$class_id", ""]},
                                {"$eq": ["$_class_obj", None]},
                            ]},
                            ["turma_inexistente"], []
                        ]},
                        {"$cond": [
                            {"$and": [
                                {"$ne": ["$_class_obj", None]},
                                {"$ne": ["$_class_obj.school_id", "$school_id"]},
                            ]},
                            ["turma_outra_escola"], []
                        ]},
                        {"$cond": [
                            {"$or": [
                                {"$eq": ["$school_id", None]},
                                {"$eq": ["$school_id", ""]},
                            ]},
                            ["sem_escola"], []
                        ]},
                        {"$cond": [
                            {"$and": [
                                {"$ne": ["$school_id", None]},
                                {"$ne": ["$school_id", ""]},
                                {"$eq": ["$_school_obj", None]},
                            ]},
                            ["escola_inexistente"], []
                        ]},
                    ]
                }
            }},
            {"$match": {"_issues": {"$ne": []}}},
            {"$project": {
                "_id": 0,
                "id": 1,
                "full_name": 1,
                "school_id": 1,
                "school_name": "$_school_obj.name",
                "class_id": 1,
                "class_name": "$_class_obj.name",
                "issues": "$_issues",
            }},
            {"$sort": {"school_name": 1, "full_name": 1}},
        ]

        items = []
        counts_by_issue = {
            "sem_turma": 0,
            "turma_inexistente": 0,
            "turma_outra_escola": 0,
            "sem_escola": 0,
            "escola_inexistente": 0,
        }
        async for doc in current_db.students.aggregate(pipeline):
            for issue in doc.get("issues", []):
                counts_by_issue[issue] = counts_by_issue.get(issue, 0) + 1
            items.append(doc)

        return {
            "total": len(items),
            "counts_by_issue": counts_by_issue,
            "items": items,
        }

    @router.get("/enrollment-audit")
    async def get_enrollment_audit(request: Request):
        """[Auditoria] Painel read-only de saúde das matrículas (enrollment_number).

        Reporta, em tempo real, matrículas AUSENTES (vazias) e DUPLICADAS nas
        coleções `students` e `enrollments`, além do status do índice único.
        Espelha a auditoria do script scripts/backfill_dedup_enrollment.py.
        Restrito a perfis administrativos/secretaria. Tenant/escola-aware.
        """
        current_user = await AuthMiddleware.require_roles(
            ['super_admin', 'admin', 'admin_teste', 'gerente', 'semed',
             'semed1', 'semed2', 'semed3', 'secretario']
        )(request)
        current_db = get_db_for_user(current_user)

        role = current_user.get('role')
        base = {}
        if role != 'super_admin':
            tenant_id = current_user.get('mantenedora_id')
            if tenant_id:
                base['mantenedora_id'] = tenant_id
        if role == 'secretario':
            base['school_id'] = {"$in": current_user.get('school_ids', []) or []}

        empty_cond = {"$or": [
            {"enrollment_number": {"$exists": False}},
            {"enrollment_number": None},
            {"enrollment_number": ""},
        ]}

        result = {}
        owner_ids = set()
        for coll_name, owner_field in (("students", "id"), ("enrollments", "student_id")):
            coll = current_db[coll_name]
            total = await coll.count_documents(base)
            empty = await coll.count_documents({**base, **empty_cond})

            pipeline = [
                {"$match": {**base, "enrollment_number": {"$gt": ""}}},
                {"$group": {
                    "_id": "$enrollment_number",
                    "count": {"$sum": 1},
                    "owners": {"$addToSet": f"${owner_field}"},
                }},
                {"$match": {"count": {"$gt": 1}}},
                {"$sort": {"count": -1, "_id": 1}},
                {"$limit": 200},
            ]
            dups = []
            async for g in coll.aggregate(pipeline):
                for o in g.get("owners", []):
                    if o:
                        owner_ids.add(o)
                dups.append({
                    "enrollment_number": g["_id"],
                    "count": g["count"],
                    "owners": g.get("owners", []),
                })
            result[coll_name] = {
                "total": total,
                "empty": empty,
                "duplicate_groups": len(dups),
                "duplicates": dups,
            }

        # Amostra de alunos sem matrícula (para ação direta na secretaria)
        empty_students = []
        async for s in current_db.students.find(
            {**base, **empty_cond}, {"_id": 0, "id": 1, "full_name": 1, "school_id": 1}
        ).limit(200):
            empty_students.append(s)
            owner_ids.add(s["id"])
        result["students"]["empty_sample"] = empty_students

        # Resolve nomes dos alunos (owners das duplicatas + amostra de vazios)
        names = {}
        if owner_ids:
            async for s in current_db.students.find(
                {"id": {"$in": list(owner_ids)}},
                {"_id": 0, "id": 1, "full_name": 1},
            ):
                names[s["id"]] = s.get("full_name")
        result["owner_names"] = names

        st_idx = await current_db.students.index_information()
        en_idx = await current_db.enrollments.index_information()
        result["unique_index"] = {
            "students": "uq_enrollment_number" in st_idx,
            "enrollments": "uq_enrollment_number" in en_idx,
        }
        return result

    @router.post("/enrollment-audit/repair")
    async def repair_enrollment_numbers(request: Request):
        """[Auditoria] Repara matrículas SEM número (enrollment_number vazio).

        Acionável pelo painel de Auditoria. Tenant/escola-aware. Para cada
        registro vazio, atribui número via gerador ATÔMICO (utils.enrollment):
          1) Preenche matrículas (`enrollments`) vazias com número fresco.
          2) Preenche alunos (`students`) vazios espelhando o número da sua
             matrícula ativa; se não houver, gera fresco (e cria a matrícula
             quando o aluno está ativo com turma/escola).
        Idempotente: rodar de novo não altera quem já tem número.
        """
        from utils.enrollment import generate_enrollment_number

        current_user = await AuthMiddleware.require_roles(
            ['super_admin', 'admin', 'admin_teste', 'gerente', 'semed',
             'semed1', 'semed2', 'semed3', 'secretario']
        )(request)
        current_db = get_db_for_user(current_user)

        role = current_user.get('role')
        base = {}
        if role != 'super_admin':
            tenant_id = current_user.get('mantenedora_id')
            if tenant_id:
                base['mantenedora_id'] = tenant_id
        if role == 'secretario':
            base['school_id'] = {"$in": current_user.get('school_ids', []) or []}

        empty_cond = {"$or": [
            {"enrollment_number": {"$exists": False}},
            {"enrollment_number": None},
            {"enrollment_number": ""},
        ]}
        year = datetime.now().year

        fixed_enrollments = 0
        fixed_students = 0
        created_enrollments = 0

        # 1) Matrículas vazias → número fresco atômico (cada matrícula é única)
        async for e in current_db.enrollments.find(
            {**base, **empty_cond}, {"_id": 0, "id": 1}
        ):
            num = await generate_enrollment_number(current_db, year)
            await current_db.enrollments.update_one(
                {"id": e["id"]}, {"$set": {"enrollment_number": num}}
            )
            fixed_enrollments += 1

        # 2) Alunos vazios → espelha matrícula ativa; senão gera fresco (e cria matrícula)
        async for s in current_db.students.find(
            {**base, **empty_cond},
            {"_id": 0, "id": 1, "status": 1, "class_id": 1, "school_id": 1, "mantenedora_id": 1}
        ):
            sid = s["id"]
            enr = await current_db.enrollments.find_one(
                {"student_id": sid, "status": "active",
                 "enrollment_number": {"$gt": ""}},
                sort=[("created_at", -1)]
            )
            if enr and enr.get("enrollment_number"):
                num = enr["enrollment_number"]
            else:
                num = await generate_enrollment_number(current_db, year)
                # Cria a matrícula ausente quando o aluno está ativo com turma
                if s.get("status") == "active" and s.get("class_id") and s.get("school_id"):
                    class_info = await current_db.classes.find_one(
                        {"id": s["class_id"]}, {"_id": 0, "grade_level": 1}
                    )
                    await current_db.enrollments.insert_one({
                        "id": str(uuid.uuid4()),
                        "student_id": sid,
                        "school_id": s["school_id"],
                        "class_id": s["class_id"],
                        "academic_year": year,
                        "status": "active",
                        "enrollment_number": num,
                        "student_series": class_info.get("grade_level") if class_info else None,
                        "enrollment_date": datetime.now(timezone.utc).isoformat(),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "mantenedora_id": s.get("mantenedora_id"),
                    })
                    created_enrollments += 1
            await current_db.students.update_one(
                {"id": sid}, {"$set": {"enrollment_number": num}}
            )
            fixed_students += 1

        await audit_service.log(
            action='update',
            collection='enrollments',
            user=current_user,
            request=request,
            document_id='enrollment-audit-repair',
            description=(f"Reparo de matrículas sem número: "
                        f"{fixed_students} alunos, {fixed_enrollments} matrículas, "
                        f"{created_enrollments} matrículas criadas.")
        )

        return {
            "fixed_students": fixed_students,
            "fixed_enrollments": fixed_enrollments,
            "created_enrollments": created_enrollments,
        }

    # =====================================================================
    # Reparo em lote — sincroniza a série da MATRÍCULA com a do CADASTRO
    # (turmas multisseriadas). Copia `students.student_series` →
    # `enrollments.student_series` quando a matrícula ATIVA estiver sem série
    # mas o aluno possuir série definida. Assim os PDFs/diários por etapa
    # fecham sem depender do fallback em tempo de leitura.
    # =====================================================================
    _SERIES_ROLES = ['super_admin', 'admin', 'admin_teste', 'gerente', 'semed',
                     'semed1', 'semed2', 'semed3', 'secretario']

    def _series_scope_base(current_user):
        role = current_user.get('role')
        base = {}
        if role != 'super_admin':
            tenant_id = current_user.get('mantenedora_id')
            if tenant_id:
                base['mantenedora_id'] = tenant_id
        if role == 'secretario':
            base['school_id'] = {"$in": current_user.get('school_ids', []) or []}
        return base

    _EMPTY_SERIES_COND = {"$or": [
        {"student_series": {"$exists": False}},
        {"student_series": None},
        {"student_series": ""},
    ]}

    async def _collect_series_sync_candidates(current_db, base):
        """Retorna a lista de matrículas ativas sem série cujo aluno TEM série
        no cadastro: [{enrollment_id, student_id, target_series, class_id}]."""
        enrollments = await current_db.enrollments.find(
            {**base, "status": "active", **_EMPTY_SERIES_COND},
            {"_id": 0, "id": 1, "student_id": 1, "class_id": 1}
        ).to_list(None)
        student_ids = list({e.get('student_id') for e in enrollments if e.get('student_id')})
        student_map = {}
        if student_ids:
            async for s in current_db.students.find(
                {"id": {"$in": student_ids}, **{k: v for k, v in base.items() if k != 'mantenedora_id'}},
                {"_id": 0, "id": 1, "full_name": 1, "student_series": 1}
            ):
                ss = (s.get('student_series') or '').strip()
                if ss:
                    student_map[s['id']] = {"full_name": s.get('full_name', ''), "series": ss}
        candidates = []
        for e in enrollments:
            info = student_map.get(e.get('student_id'))
            if info:
                candidates.append({
                    "enrollment_id": e.get('id'),
                    "student_id": e.get('student_id'),
                    "full_name": info["full_name"],
                    "target_series": info["series"],
                    "class_id": e.get('class_id'),
                })
        return candidates

    @router.get("/series-sync/audit")
    async def audit_series_sync(request: Request):
        """[Auditoria] Preview do reparo de série: lista matrículas ativas SEM
        série cujo aluno já possui série no cadastro (serão preenchidas). Tenant/
        escola-aware e read-only."""
        current_user = await AuthMiddleware.require_roles(_SERIES_ROLES)(request)
        current_db = get_db_for_user(current_user)
        base = _series_scope_base(current_user)

        candidates = await _collect_series_sync_candidates(current_db, base)

        # Agrupa por turma para um resumo legível
        class_ids = list({c["class_id"] for c in candidates if c.get("class_id")})
        class_names = {}
        if class_ids:
            async for cl in current_db.classes.find(
                {"id": {"$in": class_ids}}, {"_id": 0, "id": 1, "name": 1}
            ):
                class_names[cl["id"]] = cl.get("name", "")

        return {
            "total_to_fix": len(candidates),
            "sample": [
                {
                    "student_id": c["student_id"],
                    "full_name": c["full_name"],
                    "target_series": c["target_series"],
                    "class_id": c["class_id"],
                    "class_name": class_names.get(c["class_id"], ""),
                }
                for c in candidates[:200]
            ],
        }

    @router.post("/series-sync/repair")
    async def repair_series_sync(request: Request):
        """[Auditoria] Copia a série do CADASTRO do aluno para a MATRÍCULA ATIVA
        quando esta estiver sem série. Tenant/escola-aware, idempotente e auditado.
        Resolve turmas multisseriadas onde o aluno tem série no cadastro mas a
        matrícula nasceu/migrou sem `student_series` (sumindo dos PDFs por etapa)."""
        current_user = await AuthMiddleware.require_roles(_SERIES_ROLES)(request)
        current_db = get_db_for_user(current_user)
        base = _series_scope_base(current_user)

        candidates = await _collect_series_sync_candidates(current_db, base)

        fixed = 0
        for c in candidates:
            res = await current_db.enrollments.update_one(
                {"id": c["enrollment_id"], **_EMPTY_SERIES_COND},
                {"$set": {"student_series": c["target_series"]}}
            )
            fixed += res.modified_count

        await audit_service.log(
            action='update',
            collection='enrollments',
            user=current_user,
            request=request,
            document_id='series-sync-repair',
            description=(f"Sincronização de série matrícula↔cadastro: "
                        f"{fixed} matrícula(s) preenchida(s) a partir de students.student_series.")
        )

        return {"fixed_enrollments": fixed, "candidates": len(candidates)}



    @router.get("/autocomplete")
    async def autocomplete_students(
        request: Request,
        q: str = Query(..., min_length=2, max_length=80, description="Termo de busca (mínimo 2 caracteres)"),
        limit: int = Query(10, ge=1, le=10),
        school_id: Optional[str] = None,
        class_id: Optional[str] = None,
        status: Optional[str] = None,
    ):
        """Autocomplete de alunos — server-side, indexado, observável.

        Diretriz: /app/docs/SEARCH_ARCHITECTURE.md
        - Prefix-first sobre `nome_busca` (índice composto tenant_id+nome_busca).
        - Fallback contains apenas se q tem >= 4 chars E prefix retornou < 3.
        - Cache server-side TTL 5s (tenant-aware).
        - CPF mascarado.
        - Rate limit 30 req/min/usuário.
        - Telemetria via janela deslizante 15min (consumir via /api/admin/observability/autocomplete).
        """
        import time as _time
        from text_utils import normalize_for_search
        from utils.students_search import (
            check_autocomplete_rate_limit,
            mask_cpf,
            make_cache_key,
            cache_get,
            cache_set,
            record_autocomplete_call,
        )

        t_start = _time.monotonic()
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)

        # Rate limit per-user (também registra evento de bloqueio na telemetria)
        check_autocomplete_rate_limit(current_user.get('id', '') or current_user.get('email', ''))

        # Normalização única (lowercase, sem acentos, trim, espaços colapsados)
        q_norm = (normalize_for_search(q) or '').strip()
        q_norm = re.sub(r'\s+', ' ', q_norm)
        if not q_norm or len(q_norm) < 2:
            return {"items": [], "used_fallback": False, "cache_hit": False}

        # Tenant id para cache key + telemetria
        tenant_id = current_user.get('mantenedora_id')

        # Filtros estáveis para hash de cache
        cache_filters = {
            'school_id': school_id, 'class_id': class_id,
            'status': status, 'limit': limit,
        }
        cache_key = make_cache_key(tenant_id, q_norm, cache_filters)

        # ---- Cache hit? ----
        cached = cache_get(cache_key)
        if cached is not None:
            duration_ms = (_time.monotonic() - t_start) * 1000
            record_autocomplete_call(
                q_norm=q_norm, duration_ms=duration_ms,
                used_fallback=cached.get('used_fallback', False),
                result_count=len(cached.get('items', [])),
                cache_hit=True, tenant_id=tenant_id,
            )
            return {**cached, "cache_hit": True}

        # ---- Cache miss → consulta Mongo ----
        q_escaped = re.escape(q_norm)

        base_filter: dict = {}
        if school_id:
            base_filter['school_id'] = school_id
        if class_id:
            base_filter['class_id'] = class_id
        if status:
            base_filter['status'] = status
        base_filter = apply_tenant_filter(base_filter, current_user, request)

        projection = {
            "_id": 0, "id": 1, "full_name": 1, "cpf": 1,
            "school_id": 1, "class_id": 1, "status": 1,
        }

        # Estratégia 1: PREFIX (caminho rápido, índice ix_tenant_nome_busca)
        prefix_filter = {**base_filter, 'nome_busca': {'$regex': f'^{q_escaped}'}}
        prefix_hits = await current_db.students.find(
            prefix_filter, projection
        ).limit(limit).to_list(limit)

        used_fallback = False
        results = list(prefix_hits)

        # Estratégia 2: CONTAINS — restrita: q >= 4 chars E prefix < 3 hits
        if len(prefix_hits) < 3 and len(q_norm) >= 4:
            seen_ids = {s.get('id') for s in prefix_hits}
            contains_filter = {**base_filter, 'nome_busca': {'$regex': q_escaped}}
            need = limit - len(prefix_hits)
            contains_hits = await current_db.students.find(
                contains_filter, projection
            ).limit(need + len(seen_ids)).to_list(need + len(seen_ids))
            for hit in contains_hits:
                if hit.get('id') not in seen_ids:
                    results.append(hit)
                    if len(results) >= limit:
                        break
            used_fallback = True

        # Enriquece com nomes (1 query batch cada)
        school_ids = list({s.get('school_id') for s in results if s.get('school_id')})
        class_ids = list({s.get('class_id') for s in results if s.get('class_id')})
        schools_map = {}
        classes_map = {}
        if school_ids:
            schools = await current_db.schools.find(
                {'id': {'$in': school_ids}}, {'_id': 0, 'id': 1, 'name': 1}
            ).to_list(len(school_ids))
            schools_map = {s['id']: s.get('name', '') for s in schools}
        if class_ids:
            classes = await current_db.classes.find(
                {'id': {'$in': class_ids}}, {'_id': 0, 'id': 1, 'name': 1}
            ).to_list(len(class_ids))
            classes_map = {c['id']: c.get('name', '') for c in classes}

        items = [
            {
                'id': s.get('id'),
                'full_name': s.get('full_name'),
                'cpf_masked': mask_cpf(s.get('cpf')),
                'school_id': s.get('school_id'),
                'school_name': schools_map.get(s.get('school_id'), ''),
                'class_id': s.get('class_id'),
                'class_name': classes_map.get(s.get('class_id'), ''),
                'status': s.get('status', 'active'),
            }
            for s in results
        ]

        payload = {"items": items, "used_fallback": used_fallback}
        cache_set(cache_key, payload)

        duration_ms = (_time.monotonic() - t_start) * 1000
        record_autocomplete_call(
            q_norm=q_norm, duration_ms=duration_ms,
            used_fallback=used_fallback, result_count=len(items),
            cache_hit=False, tenant_id=tenant_id,
        )

        return {**payload, "cache_hit": False}

    @router.get("")
    async def list_students(
        request: Request, 
        school_id: Optional[str] = None, 
        class_id: Optional[str] = None, 
        status: Optional[str] = None,
        search: Optional[str] = None,
        completeness_band: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
        skip: int = 0, 
        limit: int = 5000
    ):
        """Lista alunos com filtros, busca e paginação server-side"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        # Constrói filtro
        filter_query = {}
        
        # Papéis com visão tenant-wide dos alunos (apenas leitura para semed1/semed2):
        # admin, admin_teste, super_admin, gerente, semed, semed1 (Tutor), semed2 (Analista),
        # semed3 (Administração), secretario, ass_social, ass_social_2, agente_vacinas.
        # Alinhado com /app/frontend/src/pages/Users.js (`students: 'view'`) e com
        # /app/backend/routers/schools.py::list_schools.
        if current_user['role'] in ['admin', 'admin_teste', 'super_admin', 'gerente', 'semed', 'semed1', 'semed2', 'semed3', 'secretario', 'ass_social', 'ass_social_2', 'agente_vacinas']:
            if school_id:
                filter_query['school_id'] = school_id
            if class_id:
                # Verifica se é turma de programa especial (AEE, Reforço, etc.)
                target_class = await current_db.classes.find_one({"id": class_id}, {"_id": 0, "atendimento_programa": 1, "school_id": 1})
                atend = (target_class.get('atendimento_programa', '') or '').strip().lower() if target_class else ''
                if atend in ('aee', 'recomposicao_aprendizagem', 'reforco_escolar'):
                    # Busca alunos vinculados diretamente + via atendimento_programa_class_id
                    special_ids = set()
                    # Busca via planos_aee e atendimentos_aee para AEE
                    if atend == 'aee' and target_class:
                        tc_school = target_class.get('school_id', '')
                        planos = await current_db.planos_aee.find({"school_id": tc_school}, {"_id": 0, "student_id": 1}).to_list(1000)
                        for p in planos:
                            if p.get('student_id'): special_ids.add(p['student_id'])
                        atendimentos = await current_db.atendimentos_aee.find({"school_id": tc_school}, {"_id": 0, "student_id": 1}).to_list(1000)
                        for a in atendimentos:
                            if a.get('student_id'): special_ids.add(a['student_id'])
                    filter_query['$or'] = [
                        {'class_id': class_id},
                        {'atendimento_programa_class_id': class_id},
                    ]
                    if special_ids:
                        filter_query['$or'].append({'id': {'$in': list(special_ids)}})
                else:
                    filter_query['class_id'] = class_id
        else:
            # Outros papéis veem apenas das escolas vinculadas
            if school_id and school_id in current_user.get('school_ids', []):
                filter_query['school_id'] = school_id
            else:
                filter_query['school_id'] = {"$in": current_user.get('school_ids', [])}
            
            if class_id:
                target_class = await current_db.classes.find_one({"id": class_id}, {"_id": 0, "atendimento_programa": 1, "school_id": 1})
                atend = (target_class.get('atendimento_programa', '') or '').strip().lower() if target_class else ''
                if atend in ('aee', 'recomposicao_aprendizagem', 'reforco_escolar'):
                    special_ids = set()
                    if atend == 'aee' and target_class:
                        tc_school = target_class.get('school_id', '')
                        planos = await current_db.planos_aee.find({"school_id": tc_school}, {"_id": 0, "student_id": 1}).to_list(1000)
                        for p in planos:
                            if p.get('student_id'): special_ids.add(p['student_id'])
                        atendimentos = await current_db.atendimentos_aee.find({"school_id": tc_school}, {"_id": 0, "student_id": 1}).to_list(1000)
                        for a in atendimentos:
                            if a.get('student_id'): special_ids.add(a['student_id'])
                    filter_query['$or'] = [
                        {'class_id': class_id},
                        {'atendimento_programa_class_id': class_id},
                    ]
                    if special_ids:
                        filter_query['$or'].append({'id': {'$in': list(special_ids)}})
                else:
                    filter_query['class_id'] = class_id
        
        # Filtro por status
        if status:
            filter_query['status'] = status
        
        # Busca por nome ou CPF (Mai 2026: usa nome_busca indexado quando
        # disponível + fallback regex acent-insensitive em full_name).
        if search and len(search) >= 3:
            from utils.search_utils import accent_insensitive_regex
            from text_utils import normalize_for_search
            search_pattern = accent_insensitive_regex(search)
            search_clean = re.escape(search.replace('.', '').replace('-', '').replace('/', ''))
            search_normalized = normalize_for_search(search) or ''
            search_or = [
                # Caminho rápido: campo indexado nome_busca
                {'nome_busca': {'$regex': re.escape(search_normalized)}},
                # Fallback: full_name com regex acent-insensitive (registros não migrados)
                {'full_name': {'$regex': search_pattern, '$options': 'i'}},
                {'cpf': {'$regex': search_clean}},
            ]
            # Se já tem $or (turma especial), combina com $and
            if '$or' in filter_query:
                existing_or = filter_query.pop('$or')
                filter_query['$and'] = [
                    {'$or': existing_or},
                    {'$or': search_or}
                ]
            else:
                filter_query['$or'] = search_or
        
        # Multi-tenancy: aplica filtro por mantenedora
        filter_query = apply_tenant_filter(filter_query, current_user, request)
        
        # Conta total para paginação
        total = await current_db.students.count_documents(filter_query)

        # Filtro de ATIVOS (usado nos indicadores e na completude). Força
        # status='active' mesmo que `filterStatus` esteja setado para outro valor.
        active_filter = {**filter_query, 'status': 'active'}

        # Contagem por faixa de completude (verde/amarelo/vermelho) — considera
        # APENAS alunos ATIVOS (regra de negócio). Espelha o cálculo do Python.
        band_count_pipeline = [
            {"$match": active_filter},
            _completeness_pct_stage(),
            {"$addFields": {"_band": {"$switch": {"branches": [
                {"case": _BAND_EXPR["green"], "then": "green"},
                {"case": _BAND_EXPR["yellow"], "then": "yellow"},
            ], "default": "red"}}}},
            {"$group": {"_id": "$_band", "count": {"$sum": 1}}},
        ]
        completeness_counts = {"green": 0, "yellow": 0, "red": 0}
        async for doc in current_db.students.aggregate(band_count_pipeline):
            if doc["_id"] in completeness_counts:
                completeness_counts[doc["_id"]] = doc["count"]
        
        # Conta alunos ativos (para exibição no frontend)
        active_count = await current_db.students.count_documents(active_filter) if not status else (total if status == 'active' else 0)
        
        # Contagem por cor/raça
        race_counts = {}
        race_pipeline = [
            {"$match": active_filter},
            {"$group": {
                "_id": {"$ifNull": ["$color_race", "nao_informada"]},
                "count": {"$sum": 1}
            }}
        ]
        race_cursor = current_db.students.aggregate(race_pipeline)
        async for doc in race_cursor:
            race_key = doc["_id"] if doc["_id"] else "nao_informada"
            if race_key == "":
                race_key = "nao_informada"
            race_counts[race_key] = doc["count"]

        # Contagem por série.
        # PRIORIDADE: `students.student_series` (campo do aluno) →
        # `classes.grade_level` (fallback via lookup pela turma).
        #
        # Por quê essa ordem?
        # - Escolas MULTISSERIADAS (ex.: Jean Piaget): uma única turma
        #   "1º/6º ANO" pode ter alunos de séries diferentes. O
        #   `classes.grade_level` mostra só uma série, mas cada aluno
        #   tem sua série REAL em `students.student_series`.
        # - Escolas NORMAIS (ex.: Paulette Camille): muitos alunos
        #   têm `student_series` vazio. Para esses, usa
        #   `classes.grade_level` da turma onde está matriculado.
        #
        # IMPORTANTE: a normalização (uppercase + canonicalização) é feita
        # em Python — NÃO em MongoDB. `$toUpper` do MongoDB só opera sobre
        # ASCII básico (A-Z) e NÃO converte caracteres acentuados/cedilha
        # (ex.: `ç`, `á`). Em Python, `str.upper()` trata Unicode corretamente.
        series_pipeline = [
            {"$match": active_filter},
            {"$lookup": {
                "from": "classes",
                "localField": "class_id",
                "foreignField": "id",
                "as": "_class",
            }},
            {"$addFields": {
                "_grade_effective": {
                    "$let": {
                        # `$ifNull` coage null E campo AUSENTE para "" (string vazia).
                        # Sem isso, alunos cujo campo `student_series` está ausente
                        # mantêm o valor "missing" dentro do `$cond` (pois
                        # `$ne: [missing, null]` resolve para TRUE no MongoDB) e
                        # NÃO caem no fallback de `classes.grade_level`, indo parar
                        # erroneamente em "Série não reconhecida". O `$trim` ainda
                        # normaliza valores só-espaços. Espelha a regra `.strip()`
                        # usada nos scripts de diagnóstico (find_one).
                        "vars": {"ss": {"$trim": {"input": {"$ifNull": ["$student_series", ""]}}}},
                        "in": {
                            "$cond": [
                                {"$ne": ["$$ss", ""]},
                                "$$ss",
                                {"$arrayElemAt": ["$_class.grade_level", 0]},
                            ]
                        }
                    }
                }
            }},
            {"$group": {
                "_id": "$_grade_effective",  # raw — normaliza em Python
                "count": {"$sum": 1},
            }},
        ]
        series_counts = {}
        unmapped_series = {}
        async for doc in current_db.students.aggregate(series_pipeline):
            raw = (doc["_id"] or "")
            count = doc["count"]
            canon = canonicalize_serie(raw)
            if canon:
                series_counts[canon] = series_counts.get(canon, 0) + count
            else:
                # Reconciliação: tudo que não casa vai para "Série não reconhecida"
                series_counts[UNRECOGNIZED_KEY] = series_counts.get(UNRECOGNIZED_KEY, 0) + count
                raw_label = (str(raw).strip() or "(vazio)")
                unmapped_series[raw_label] = unmapped_series.get(raw_label, 0) + count

        # Auditoria: registra nomenclaturas de série não mapeadas para correção
        if unmapped_series:
            logger.warning(
                "[Indicadores] Séries não reconhecidas (filtro=%s): %s",
                {k: v for k, v in (filter_query or {}).items() if k in ("school_id", "mantenedora_id")},
                unmapped_series,
            )

        # Contagem por modalidade da turma (classes.atendimento_programa).
        # Fonte: `students.class_id` diretamente, juntado com `classes`.
        # Regular = atendimento_programa None/vazio.
        # Integral, Recomp. = valores específicos.
        # (AEE é calculado SEPARADAMENTE via coleção `planos_aee`.)
        modalidade_pipeline = [
            {"$match": active_filter},
            {"$lookup": {
                "from": "classes",
                "localField": "class_id",
                "foreignField": "id",
                "as": "_class",
            }},
            {"$addFields": {
                "_atend": {
                    "$toLower": {"$ifNull": [
                        {"$arrayElemAt": ["$_class.atendimento_programa", 0]},
                        "",
                    ]}
                }
            }},
            {"$group": {"_id": "$_atend", "count": {"$sum": 1}}},
        ]
        modalidade_counts = {"regular": 0, "atendimento_integral": 0, "aee": 0, "recomposicao_aprendizagem": 0}
        async for doc in current_db.students.aggregate(modalidade_pipeline):
            key = (doc["_id"] or "").strip()
            if not key:
                modalidade_counts["regular"] += doc["count"]
            elif key in modalidade_counts:
                modalidade_counts[key] += doc["count"]

        # AEE é tratado de forma SEPARADA: AEE não vem de
        # `classes.atendimento_programa`. Alunos com AEE permanecem na
        # turma regular/integral e ganham um PLANO AEE como apoio
        # adicional (coleção `planos_aee`). Conta alunos ATIVOS que
        # possuem pelo menos um registro nessa coleção.
        aee_pipeline = [
            {"$match": active_filter},
            {"$lookup": {
                "from": "planos_aee",
                "localField": "id",
                "foreignField": "student_id",
                "as": "_planos_aee",
            }},
            {"$match": {"_planos_aee": {"$ne": []}}},
            {"$count": "total"},
        ]
        aee_result = await current_db.students.aggregate(aee_pipeline).to_list(1)
        modalidade_counts["aee"] = aee_result[0]["total"] if aee_result else 0

        # Calcula skip com base na página
        effective_skip = (page - 1) * page_size if page > 0 else skip
        effective_limit = page_size if page > 0 else limit
        
        # Projeta os campos da listagem + os necessários para calcular a
        # completude do cadastro (estes últimos são removidos após o cálculo
        # para manter o payload leve).
        list_projection = {
            "_id": 0, "id": 1, "full_name": 1, "school_id": 1, "class_id": 1,
            "status": 1, "cpf": 1, "birth_date": 1, "sex": 1, "inep_code": 1,
            "student_series": 1, "atendimento_programa_class_id": 1,
            # Campos extras só para completude:
            "enrollment_number": 1, "nationality": 1, "color_race": 1,
            "comunidade_tradicional": 1, "birth_city": 1, "birth_state": 1,
            "mother_name": 1, "legal_guardian_type": 1, "nis": 1,
            "civil_certificate_number": 1, "mother_phone": 1, "father_phone": 1,
            "guardian_phone": 1,
        }
        
        students = await current_db.students.find(
            filter_query, list_projection
        ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).skip(effective_skip).limit(effective_limit).to_list(effective_limit)
        
        # Filtro por FAIXA de completude (verde/amarelo/vermelho): exige
        # calcular `_pct` no servidor. A faixa considera APENAS ATIVOS (mesmo
        # universo das contagens dos cards), então usa `active_filter` e o
        # `total`/`total_pages` passam a refletir a faixa selecionada.
        if completeness_band in _BAND_EXPR:
            page_pipeline = [
                {"$match": active_filter},
                _completeness_pct_stage(),
                {"$match": {"$expr": _BAND_EXPR[completeness_band]}},
                {"$sort": {"full_name": 1}},
                {"$skip": effective_skip},
                {"$limit": effective_limit},
                {"$project": list_projection},
            ]
            students = await current_db.students.aggregate(
                page_pipeline, collation={"locale": "pt", "strength": 1}
            ).to_list(effective_limit)
            total = completeness_counts[completeness_band]
        
        # Busca student_series das matrículas ativas (batch)
        student_ids = [s.get('id') for s in students if s.get('id')]
        if student_ids:
            enrollments = await current_db.enrollments.find(
                {"student_id": {"$in": student_ids}, "status": "active"},
                {"_id": 0, "student_id": 1, "student_series": 1}
            ).to_list(None)
            enrollment_series_map = {e['student_id']: e.get('student_series') for e in enrollments}
        else:
            enrollment_series_map = {}
        
        # Garante compatibilidade e calcula completude.
        # NÃO removemos os campos usados na completude: o frontend recalcula a %
        # da coluna "Completude" com o MESMO util do modal (registrationCompleteness),
        # garantindo que LISTA e "Editar Aluno(a)" nunca divirjam. Campos ausentes no
        # documento são incluídos como null para o cliente conseguir recalcular.
        _COMPLETENESS_SOURCE_FIELDS = [
            "full_name", "birth_date", "sex", "nationality", "color_race",
            "comunidade_tradicional", "birth_city", "birth_state", "mother_name",
            "legal_guardian_type", "cpf", "nis", "civil_certificate_number",
            "mother_phone", "father_phone", "guardian_phone", "class_id",
            "enrollment_number",
        ]
        for student in students:
            student.setdefault('full_name', '')
            student.setdefault('status', 'active')
            # Prefere a série da matrícula ativa; faz FALLBACK para a série do
            # cadastro do aluno quando a matrícula estiver sem série. Sem o fallback,
            # a coluna "ANO" some mesmo após salvar a série em "Editar Aluno(a)"
            # (ex.: turmas multisseriadas com matrícula sem `student_series`).
            student['student_series'] = enrollment_series_map.get(student.get('id')) or student.get('student_series')
            student['completeness'] = _compute_student_completeness(student)
            # Garante que TODOS os campos de completude existam no payload (null se
            # ausentes) para o recálculo no cliente bater com o backend e o modal.
            for _f in _COMPLETENESS_SOURCE_FIELDS:
                student.setdefault(_f, None)
        
        return {
            "items": students,
            "total": total,
            "active_count": active_count,
            "race_counts": race_counts,
            "series_counts": series_counts,
            "unmapped_series": unmapped_series,
            "modalidade_counts": modalidade_counts,
            "completeness_counts": completeness_counts,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }

    class StudentReportRequest(BaseModel):
        school_id: Optional[str] = None
        class_id: Optional[str] = None
        columns: List[str] = []

    @router.post("/report/pdf")
    async def generate_students_report_pdf(body: StudentReportRequest, request: Request):
        """Gera relatório PDF de alunos com colunas selecionadas"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)

        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from xml.sax.saxutils import escape as xml_escape
        import logging
        logger = logging.getLogger(__name__)

        # Filtrar apenas alunos ativos
        filter_query = {"status": "active"}
        if body.school_id:
            filter_query["school_id"] = body.school_id
        if body.class_id:
            filter_query["class_id"] = body.class_id

        # Definição das colunas disponíveis
        column_defs = {
            "full_name": {"label": "Nome Completo", "width": 50*mm},
            "birth_date": {"label": "Data Nasc.", "width": 22*mm},
            "sex": {"label": "Sexo", "width": 14*mm},
            "color_race": {"label": "Cor/Raça", "width": 18*mm},
            "inep_code": {"label": "Cód. INEP", "width": 22*mm},
            "naturalidade": {"label": "Naturalidade", "width": 35*mm},
            "cpf": {"label": "CPF", "width": 28*mm},
            "nis": {"label": "NIS", "width": 25*mm},
            "sus_number": {"label": "SUS", "width": 25*mm},
            "father_name": {"label": "Pai", "width": 40*mm},
            "mother_name": {"label": "Mãe", "width": 40*mm},
            "father_phone": {"label": "Tel. Pai", "width": 25*mm},
            "mother_phone": {"label": "Tel. Mãe", "width": 25*mm},
            "bolsa_familia": {"label": "Bolsa Família", "width": 18*mm},
            "has_disability": {"label": "Deficiência", "width": 18*mm},
            "has_laudo": {"label": "Laudo", "width": 14*mm},
        }

        selected_columns = [c for c in body.columns if c in column_defs]
        if not selected_columns:
            raise HTTPException(status_code=400, detail="Selecione pelo menos uma coluna")

        # Buscar nomes para cabeçalho
        school_name = ""
        class_name = ""
        if body.school_id:
            school_doc = await current_db.schools.find_one({"id": body.school_id}, {"_id": 0, "name": 1})
            school_name = school_doc.get("name", "") if school_doc else ""
        if body.class_id:
            class_doc = await current_db.classes.find_one({"id": body.class_id}, {"_id": 0, "name": 1})
            class_name = class_doc.get("name", "") if class_doc else ""

        # Projeção dos campos necessários
        projection = {"_id": 0, "full_name": 1}
        for col in selected_columns:
            if col == "bolsa_familia":
                projection["benefits"] = 1
            elif col == "has_laudo":
                projection["medical_report_url"] = 1
            elif col == "naturalidade":
                projection["birth_city"] = 1
                projection["birth_state"] = 1
            elif col not in ("bolsa_familia", "has_laudo"):
                projection[col] = 1

        students = await current_db.students.find(
            filter_query, projection
        ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).to_list(5000)

        # Mapa de cor/raça
        race_labels = {
            'branca': 'Branca', 'preta': 'Preta', 'parda': 'Parda',
            'amarela': 'Amarela', 'indigena': 'Indígena', 'cigano': 'Cigano',
            'quilombola': 'Quilombola', 'ribeirinho': 'Ribeirinho',
            'extrativista': 'Extrativista', 'nao_declarada': 'N/D'
        }

        # Calcular larguras com base nas colunas selecionadas
        num_col = 8*mm  # coluna do nº
        available_width = landscape(A4)[0] - 20*mm  # margens
        total_col_width = sum(column_defs[c]["width"] for c in selected_columns)
        scale = min(1.0, (available_width - num_col) / total_col_width) if total_col_width > 0 else 1.0

        col_widths = [num_col] + [column_defs[c]["width"] * scale for c in selected_columns]

        # Estilos
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=12, spaceAfter=2*mm, alignment=TA_CENTER)
        subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontSize=9, alignment=TA_CENTER, spaceAfter=1*mm)
        cell_style = ParagraphStyle('Cell', fontSize=6.5, leading=8, alignment=TA_LEFT)
        header_cell_style = ParagraphStyle('HeaderCell', fontSize=7, leading=8.5, alignment=TA_CENTER, textColor=colors.white)

        # Construir tabela
        header_row = [Paragraph("<b>Nº</b>", header_cell_style)]
        for col in selected_columns:
            header_row.append(Paragraph(f"<b>{column_defs[col]['label']}</b>", header_cell_style))

        data_rows = [header_row]
        for idx, s in enumerate(students, 1):
            row = [Paragraph(str(idx), cell_style)]
            for col in selected_columns:
                val = ""
                try:
                    if col == "full_name":
                        val = s.get("full_name", "")
                    elif col == "birth_date":
                        bd = s.get("birth_date", "")
                        if bd and len(str(bd)) >= 10 and "-" in str(bd):
                            parts = str(bd).split("T")[0].split("-")
                            if len(parts) == 3:
                                val = f"{parts[2]}/{parts[1]}/{parts[0]}"
                            else:
                                val = str(bd)
                        else:
                            val = str(bd) if bd else ""
                    elif col == "sex":
                        sex_val = s.get("sex", "")
                        val = "M" if sex_val == "masculino" else "F" if sex_val == "feminino" else ""
                    elif col == "color_race":
                        val = race_labels.get(s.get("color_race", ""), "")
                    elif col == "inep_code":
                        val = s.get("inep_code", "") or ""
                    elif col == "naturalidade":
                        city = s.get("birth_city", "") or ""
                        state = s.get("birth_state", "") or ""
                        if city and state:
                            val = f"{city}/{state}"
                        elif city:
                            val = city
                        elif state:
                            val = state
                    elif col == "cpf":
                        val = s.get("cpf", "") or ""
                    elif col == "nis":
                        val = s.get("nis", "") or ""
                    elif col == "sus_number":
                        val = s.get("sus_number", "") or ""
                    elif col == "father_name":
                        val = s.get("father_name", "") or ""
                    elif col == "mother_name":
                        val = s.get("mother_name", "") or ""
                    elif col == "father_phone":
                        val = s.get("father_phone", "") or ""
                    elif col == "mother_phone":
                        val = s.get("mother_phone", "") or ""
                    elif col == "bolsa_familia":
                        benefits = s.get("benefits", []) or []
                        if isinstance(benefits, list):
                            val = "Sim" if any("bolsa" in str(b).lower() for b in benefits) else "Não"
                        else:
                            val = "Não"
                    elif col == "has_disability":
                        val = "Sim" if s.get("has_disability") else "Não"
                    elif col == "has_laudo":
                        val = "Sim" if s.get("medical_report_url") else "Não"
                except Exception:
                    val = ""
                # Escapar caracteres XML para evitar erros no ReportLab Paragraph
                safe_val = xml_escape(str(val)) if val else ""
                row.append(Paragraph(safe_val, cell_style))
            data_rows.append(row)

        # Gerar PDF
        try:
            buffer = BytesIO()
            doc = SimpleDocTemplate(
                buffer, pagesize=landscape(A4),
                leftMargin=10*mm, rightMargin=10*mm,
                topMargin=10*mm, bottomMargin=10*mm
            )

            elements = []

            # Cabeçalho
            header_text = "RELATÓRIO DE ALUNOS"
            elements.append(Paragraph(header_text, title_style))
            if school_name:
                elements.append(Paragraph(xml_escape(school_name), subtitle_style))
            if class_name:
                elements.append(Paragraph(f"Turma: {xml_escape(class_name)}", subtitle_style))
            elements.append(Paragraph(f"Total: {len(students)} aluno(s) ativo(s)", subtitle_style))
            elements.append(Spacer(1, 3*mm))

            table = Table(data_rows, colWidths=col_widths, repeatRows=1)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTSIZE', (0, 0), (-1, -1), 7),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
                ('TOPPADDING', (0, 0), (-1, -1), 1.5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ]))
            elements.append(table)

            doc.build(elements)
            buffer.seek(0)

            filename = f"relatorio_alunos{'_' + class_name.replace(' ', '_') if class_name else ''}.pdf"
            return StreamingResponse(
                buffer,
                media_type="application/pdf",
                headers={"Content-Disposition": f'inline; filename="{filename}"'}
            )
        except Exception as e:
            logger.error(f"Erro ao gerar PDF do relatório: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")

    @router.get("/{student_id}", response_model=Student)
    async def get_student(student_id: str, request: Request):
        """Busca aluno por ID"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        student_doc = await current_db.students.find_one({"id": student_id}, {"_id": 0})
        
        if not student_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aluno não encontrado"
            )
        
        # Verifica acesso à escola do aluno
        await AuthMiddleware.verify_school_access(request, student_doc['school_id'])
        
        # Multi-tenancy: valida tenant
        assert_same_tenant(student_doc, current_user, request)
        
        return Student(**student_doc)

    @router.put("/{student_id}", response_model=Student)
    async def update_student(student_id: str, student_update: StudentUpdate, request: Request):
        """
        Atualiza aluno com suporte a:
        - Edição de dados básicos
        - Remanejamento (mudança de turma na mesma escola)
        - Preparação para transferência (mudança de status)
        
        NOTA: Coordenadores NÃO podem editar alunos (apenas visualizar).
        """
        current_user = await AuthMiddleware.require_roles_with_coordinator_edit(
            ['admin', 'admin_teste', 'secretario', 'coordenador', 'auxiliar_secretaria'], 
            'students'
        )(request)
        current_db = get_db_for_user(current_user)
        
        # Busca aluno
        student_doc = await current_db.students.find_one({"id": student_id}, {"_id": 0})
        if not student_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aluno não encontrado"
            )
        
        # Verifica permissões de acesso
        user_school_ids = current_user.get('school_ids', [])
        current_school_id = student_doc.get('school_id')
        student_status = student_doc.get('status', '')
        
        # Admin tem acesso total
        if current_user.get('role') in ['admin', 'admin_teste', 'super_admin', 'gerente']:
            pass
        elif current_user.get('role') == 'secretario':
            is_active = student_status in ['active', 'Ativo']
            is_from_user_school = current_school_id in user_school_ids if current_school_id else False
            
            if is_active and not is_from_user_school:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Você só pode editar alunos ativos da sua escola"
                )
        elif current_user.get('role') not in ['semed']:
            if current_school_id and current_school_id not in user_school_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Você não tem permissão para editar alunos desta escola"
                )
        
        update_data = student_update.model_dump(exclude_unset=True)
        
        if not update_data:
            return Student(**student_doc)

        # [Fev/2026] DEPENDÊNCIA DE ESTUDOS — guard
        # Mudar dependency_mode != 'none' → 'none' com vínculos ativos exige confirmação
        # explícita (header X-Confirm-Cancel-Dependencies: yes). Ver STUDENT_DEPENDENCY.md.
        new_dep_mode = update_data.get('dependency_mode')
        old_dep_mode = student_doc.get('dependency_mode') or 'none'
        if new_dep_mode is not None and new_dep_mode != old_dep_mode and new_dep_mode == 'none' and old_dep_mode != 'none':
            active_deps = await current_db.student_dependencies.count_documents({
                "student_id": student_id, "status": "active",
            })
            if active_deps > 0:
                confirm_header = (request.headers.get('X-Confirm-Cancel-Dependencies') or '').lower()
                if confirm_header != 'yes':
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "message": f"Aluno possui {active_deps} dependência(s) ativa(s). Cancele as dependências ou confirme para mantê-las desvinculadas (header X-Confirm-Cancel-Dependencies: yes).",
                            "active_dependencies": active_deps,
                            "requires_confirmation": True,
                        }
                    )
                # Confirmou — cancela todas as dependências ativas com motivo automático
                await current_db.student_dependencies.update_many(
                    {"student_id": student_id, "status": "active"},
                    {"$set": {
                        "status": "cancelled",
                        "status_reason": f"[auto] dependency_mode alterado para 'none' por {current_user.get('email', current_user.get('id'))}",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "updated_by": current_user.get('id'),
                    }}
                )
        
        # Extrai campos auxiliares ANTES de qualquer lógica de negócio
        custom_action_date = update_data.pop('action_date', None)
        action_hint = update_data.pop('action_hint', None)
        
        # [Mai/2026] CAPS lock automático removido — preserva capitalização do usuário.
        
        # Detecta tipo de operação
        old_class_id = student_doc.get('class_id')
        old_school_id = student_doc.get('school_id')
        old_status = student_doc.get('status')
        new_class_id = update_data.get('class_id', old_class_id)
        new_school_id = update_data.get('school_id', old_school_id)
        new_status = update_data.get('status', old_status)
        
        # VALIDAÇÃO: Não permite status "Ativo" sem escola e turma definidas
        if new_status == 'active':
            final_school_id = new_school_id or old_school_id
            final_class_id = new_class_id or old_class_id
            
            if not final_school_id or not final_class_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Não é possível definir o status como 'Ativo' sem escola e turma definidas. O aluno precisa estar matriculado em uma turma."
                )
            # [Fase 0 — Contenção] Garante que a turma EXISTE e pertence à
            # escola do aluno antes de manter/definir status 'Ativo'.
            class_check = await current_db.classes.find_one(
                {"id": final_class_id},
                {"_id": 0, "school_id": 1}
            )
            if not class_check:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Turma inexistente (class_id={final_class_id}). Selecione uma turma válida."
                )
            if class_check.get('school_id') != final_school_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="A turma selecionada pertence a outra escola. Selecione uma turma da mesma escola do aluno."
                )

        # [Fase 0 — Contenção] Deduplica `disabilities[]` (se enviado).
        if isinstance(update_data.get('disabilities'), list):
            seen = set()
            update_data['disabilities'] = [
                d for d in update_data['disabilities']
                if not (d in seen or seen.add(d))
            ]
        
        action_type = 'edicao'
        history_obs = None
        
        # Verifica se é mudança de turma (remanejamento, progressão ou reclassificação)
        # IMPORTANTE: este fluxo só vale para alunos ATIVOS. Alunos transferidos/
        # inativos/desistentes/cancelados que voltam para outra turma devem cair
        # no fluxo de rematrícula (linha ~946), não de remanejamento.
        is_active_class_change = (
            new_class_id and new_class_id != old_class_id
            and new_school_id == old_school_id
            and old_status in ('active', 'Ativo')
        )
        if is_active_class_change:
            if action_hint == 'progressao':
                action_type = 'progressao'
                enrollment_inactive_status = 'progressed'
            elif action_hint == 'reclassificacao':
                action_type = 'reclassificacao'
                enrollment_inactive_status = 'reclassified'
            else:
                action_type = 'remanejamento'
                enrollment_inactive_status = 'relocated'
            
            academic_year = datetime.now().year
            
            # Marca a matrícula antiga como inativa (mantém registro na turma de origem)
            await current_db.enrollments.update_one(
                {"student_id": student_id, "school_id": old_school_id, "class_id": old_class_id, "status": "active", "academic_year": academic_year},
                {"$set": {"status": enrollment_inactive_status}}
            )
            
            # Cria nova matrícula ativa na turma de destino
            old_enrollment = await current_db.enrollments.find_one(
                {"student_id": student_id, "school_id": old_school_id, "class_id": old_class_id, "academic_year": academic_year},
                {"_id": 0}
            )
            # Mantém o número da matrícula de origem (mesma identidade do aluno).
            # Se a matrícula de origem estiver SEM número (passivo legado), gera um
            # número atômico fresco em vez de propagar None — assim a nova matrícula
            # nunca nasce "sem número".
            carried_number = old_enrollment.get("enrollment_number") if old_enrollment else None
            if not carried_number:
                carried_number = await generate_enrollment_number(current_db, academic_year)
                update_data['enrollment_number'] = carried_number
            new_enrollment = {
                "id": str(uuid.uuid4()),
                "student_id": student_id,
                "school_id": old_school_id,
                "class_id": new_class_id,
                "academic_year": academic_year,
                "status": "active",
                "enrollment_number": carried_number,
                "student_series": update_data.get('student_series') or (old_enrollment.get("student_series") if old_enrollment else None),
                "enrollment_date": (f"{custom_action_date}T12:00:00+00:00" if custom_action_date else datetime.now(timezone.utc).isoformat())
            }
            await current_db.enrollments.insert_one(new_enrollment)
            
            new_class = await current_db.classes.find_one({"id": new_class_id}, {"_id": 0, "name": 1})
            if action_type == 'progressao':
                history_obs = f"Progressão para turma: {new_class.get('name') if new_class else new_class_id}"
            elif action_type == 'reclassificacao':
                history_obs = f"Reclassificado para turma: {new_class.get('name') if new_class else new_class_id}"
            else:
                history_obs = f"Remanejado para turma: {new_class.get('name') if new_class else new_class_id}"
        
        # Proteção contra re-matrícula quando aluno já está ativo (UI stale / clique duplo)
        if new_status == 'active' and old_status == 'active' and new_class_id and new_class_id == old_class_id:
            # Aluno já está ativo nesta turma - ignora silenciosamente (idempotente)
            pass
        elif new_status == 'active' and old_status == 'active' and new_class_id and new_class_id != old_class_id:
            # Aluno já ativo tentando mudar de turma - tratar como remanejamento, não matrícula
            pass
        
        # Verifica se é mudança de status para transferência
        if new_status != old_status:
            if new_status == 'transferred':
                action_type = 'transferencia_saida'
                history_obs = "Aluno marcado para transferência"
                
                await current_db.enrollments.update_many(
                    {"student_id": student_id, "status": "active"},
                    {"$set": {"status": "transferred"}}
                )
            
            elif new_status == 'dropout':
                action_type = 'desistencia'
                history_obs = "Aluno registrado como desistente"
                
                await current_db.enrollments.update_many(
                    {"student_id": student_id, "status": "active"},
                    {"$set": {"status": "dropout"}}
                )
            
            elif new_status == 'cancelled':
                action_type = 'cancelamento'
                history_obs = "Matrícula cancelada"
                academic_year = datetime.now().year
                
                # Busca matrículas ativas para obter class_ids e school_ids antes de deletar
                active_enrollments_cursor = current_db.enrollments.find(
                    {"student_id": student_id, "status": "active"},
                    {"_id": 0, "class_id": 1, "school_id": 1, "id": 1}
                )
                active_enrollments = await active_enrollments_cursor.to_list(50)
                cancelled_class_ids = list(set(e.get('class_id') for e in active_enrollments if e.get('class_id')))
                
                # 1. Remover aluno dos registros de frequência das turmas
                if cancelled_class_ids:
                    await current_db.attendance.update_many(
                        {"class_id": {"$in": cancelled_class_ids}},
                        {"$pull": {"records": {"student_id": student_id}}}
                    )
                
                # 2. Deletar notas do aluno nas turmas
                if cancelled_class_ids:
                    await current_db.grades.delete_many(
                        {"student_id": student_id, "class_id": {"$in": cancelled_class_ids}}
                    )
                
                # 3. Deletar as matrículas ativas (não apenas marcar como cancelled)
                await current_db.enrollments.delete_many(
                    {"student_id": student_id, "status": "active"}
                )
                
                # 4. Status do aluno: inativo, sem escola e turma
                update_data['status'] = 'inactive'
                update_data['school_id'] = ''
                update_data['class_id'] = ''
                new_status = 'inactive'
            
            # Se está sendo matriculado (de transferido/inativo para ativo)
            elif new_status == 'active' and old_status in ['transferred', 'inactive', 'dropout', None, '']:
                action_type = 'matricula'
                academic_year = update_data.get('academic_year', datetime.now().year)
                
                # Verifica o tipo da turma de destino
                target_class = await current_db.classes.find_one(
                    {"id": new_class_id}, {"_id": 0, "atendimento_programa": 1, "name": 1}
                )
                target_programa = (target_class.get('atendimento_programa', '') or '').strip().lower() if target_class else ''
                
                # Turmas especiais que permitem matrícula mesmo com aluno já ativo
                turmas_especiais = {'aee', 'recomposicao_aprendizagem', 'reforco_escolar'}
                is_turma_especial = target_programa in turmas_especiais
                
                # Se NÃO é turma especial, verifica se aluno já está ativo em turma regular
                if not is_turma_especial:
                    # Busca TODAS as matrículas ativas do aluno no mesmo ano
                    active_cursor = current_db.enrollments.find({
                        "student_id": student_id,
                        "academic_year": academic_year,
                        "status": "active"
                    })
                    active_enrollments = await active_cursor.to_list(50)
                    
                    for enr in active_enrollments:
                        enr_class = await current_db.classes.find_one(
                            {"id": enr.get('class_id')},
                            {"_id": 0, "atendimento_programa": 1, "name": 1}
                        )
                        enr_programa = (enr_class.get('atendimento_programa', '') or '').strip().lower() if enr_class else ''
                        
                        if enr_programa not in turmas_especiais:
                            turma_nome = enr_class.get('name', '') if enr_class else ''
                            raise HTTPException(
                                status_code=status.HTTP_409_CONFLICT,
                                detail=f"Este aluno já possui matrícula ativa na turma '{turma_nome}' no ano letivo {academic_year}. Para rematrícula, primeiro cancele ou transfira a matrícula atual."
                            )
                
                # Verifica se já existe matrícula ativa na MESMA turma
                existing_enrollment = await current_db.enrollments.find_one({
                    "student_id": student_id,
                    "class_id": new_class_id,
                    "academic_year": academic_year,
                    "status": "active"
                })
                
                if existing_enrollment:
                    turma_nome = target_class.get('name', '') if target_class else ''
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Este aluno já está matriculado nesta turma '{turma_nome}' no ano letivo {academic_year}."
                    )
                
                if not existing_enrollment and new_school_id and new_class_id:
                    # Gera número de matrícula (atômico)
                    new_enrollment_number = await generate_enrollment_number(current_db, academic_year)
                    # Espelha no doc do aluno — garante que ele NÃO fique "sem número".
                    update_data['enrollment_number'] = new_enrollment_number
                    
                    # Cria nova matrícula
                    new_enrollment = {
                        "id": str(uuid.uuid4()),
                        "student_id": student_id,
                        "school_id": new_school_id,
                        "class_id": new_class_id,
                        "academic_year": academic_year,
                        "enrollment_number": new_enrollment_number,
                        "student_series": update_data.get('student_series') or (target_class.get('grade_level') if target_class else None),
                        "status": "active",
                        "enrollment_date": update_data.get('enrollment_date') or (f"{custom_action_date}T12:00:00+00:00" if custom_action_date else datetime.now(timezone.utc).isoformat()),
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    try:
                        await current_db.enrollments.insert_one(new_enrollment)
                    except DuplicateKeyError:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail="Este aluno já possui matrícula ativa nesta turma. Não é possível duplicar."
                        )
                    
                    new_class = await current_db.classes.find_one({"id": new_class_id}, {"_id": 0, "name": 1})
                    history_obs = f"Matriculado na turma {new_class.get('name') if new_class else new_class_id} - Ano letivo {academic_year} - Matrícula: {new_enrollment_number}"
        
        # Remove academic_year do update_data pois não é campo do aluno
        update_data.pop('academic_year', None)

        # [Mai/2026] Normalização leve de CAPS em campos textuais (observations).
        from utils.text_normalize import normalize_input_fields
        update_data = normalize_input_fields(update_data, "students")

        # Atualiza o aluno
        await current_db.students.update_one(
            {"id": student_id},
            {"$set": update_data}
        )
        
        # Propaga student_series para a(s) matrícula(s) ativa(s) do aluno.
        # IMPORTANTE: não filtra por academic_year — em turmas multisseriadas a
        # série do aluno (etapa) precisa refletir na matrícula independentemente do
        # ano da matrícula, senão o aluno some dos PDFs/diários por etapa (que leem
        # enrollments.student_series). A matrícula ativa é sempre a vigente.
        if 'student_series' in update_data:
            await current_db.enrollments.update_many(
                {"student_id": student_id, "status": "active"},
                {"$set": {"student_series": update_data['student_series']}}
            )
        
        # Propaga enrollment_date para a matrícula ativa (se foi alterado)
        if 'enrollment_date' in update_data:
            await current_db.enrollments.update_one(
                {"student_id": student_id, "status": "active", "academic_year": datetime.now().year},
                {"$set": {"enrollment_date": update_data['enrollment_date']}}
            )
        
        # Busca dados para o histórico
        school = await current_db.schools.find_one({"id": new_school_id or old_school_id}, {"_id": 0, "name": 1})
        class_info = await current_db.classes.find_one({"id": new_class_id or old_class_id}, {"_id": 0, "name": 1})
        
        # Define a data da ação: usa a data informada pelo usuário ou a data atual
        if custom_action_date:
            history_action_date = f"{custom_action_date}T12:00:00+00:00"
        else:
            history_action_date = datetime.now(timezone.utc).isoformat()
        
        # Define class_id do histórico: para remanejamento/progressão, usa a turma de ORIGEM
        history_class_id = old_class_id if action_type in ('remanejamento', 'progressao', 'reclassificacao') else (new_class_id or old_class_id)
        
        # Registra no histórico
        history_entry = {
            "id": str(uuid.uuid4()),
            "student_id": student_id,
            "school_id": new_school_id or old_school_id,
            "school_name": school.get('name') if school else 'N/A',
            "class_id": history_class_id,
            "class_name": class_info.get('name') if class_info else 'N/A',
            "action_type": action_type,
            "previous_status": old_status,
            "new_status": new_status,
            "observations": history_obs,
            "user_id": current_user.get('id'),
            "user_name": current_user.get('full_name') or current_user.get('email'),
            "action_date": history_action_date
        }
        
        await current_db.student_history.insert_one(history_entry)
        
        # Registra auditoria
        await audit_service.log(
            action='update',
            collection='students',
            user=current_user,
            request=request,
            document_id=student_id,
            description=f"Atualizou aluno: {student_doc.get('full_name')} - {action_type}",
            school_id=new_school_id or old_school_id,
            school_name=school.get('name') if school else None,
            old_value={'class_id': old_class_id, 'school_id': old_school_id, 'status': old_status},
            new_value={'class_id': new_class_id, 'school_id': new_school_id, 'status': new_status},
            extra_data={'action_type': action_type, 'observations': history_obs}
        )
        
        updated_student = await current_db.students.find_one({"id": student_id}, {"_id": 0})
        return Student(**updated_student)

    @router.get("/{student_id}/history")
    async def get_student_history(student_id: str, request: Request):
        """Retorna o histórico de movimentações do aluno"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        student = await current_db.students.find_one({"id": student_id}, {"_id": 0, "school_id": 1})
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aluno não encontrado"
            )
        
        history = await current_db.student_history.find(
            {"student_id": student_id},
            {"_id": 0}
        ).sort("action_date", -1).to_list(100)
        
        return history

    @router.post("/{student_id}/transfer")
    async def transfer_student(student_id: str, request: Request):
        """
        Transfere aluno para outra escola.
        Requer que o aluno esteja com status 'transferred' na escola de origem.
        """
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        body = await request.json()
        new_school_id = body.get('school_id')
        new_class_id = body.get('class_id')
        academic_year = body.get('academic_year', datetime.now().year)
        
        if not new_school_id or not new_class_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="school_id e class_id são obrigatórios"
            )
        
        student = await current_db.students.find_one({"id": student_id}, {"_id": 0})
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aluno não encontrado"
            )
        
        if student.get('status') != 'transferred':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="O aluno precisa estar com status 'Transferido' para ser matriculado em outra escola"
            )
        
        if student.get('school_id') == new_school_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A escola de destino deve ser diferente da escola atual"
            )
        
        new_school = await current_db.schools.find_one({"id": new_school_id}, {"_id": 0, "name": 1})
        new_class = await current_db.classes.find_one({"id": new_class_id}, {"_id": 0, "name": 1, "grade_level": 1})
        
        if not new_school or not new_class:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Escola ou turma de destino não encontrada"
            )
        
        # Gera número de matrícula (atômico)
        new_enrollment_number = await generate_enrollment_number(current_db, academic_year)
        
        # Cria nova matrícula
        enrollment_id = str(uuid.uuid4())
        new_enrollment = {
            "id": enrollment_id,
            "student_id": student_id,
            "school_id": new_school_id,
            "class_id": new_class_id,
            "academic_year": academic_year,
            "enrollment_number": new_enrollment_number,
            "student_series": student.get('student_series') or (new_class.get('grade_level') if new_class else None),
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await current_db.enrollments.insert_one(new_enrollment)
        
        # Atualiza dados do aluno
        await current_db.students.update_one(
            {"id": student_id},
            {"$set": {
                "school_id": new_school_id,
                "class_id": new_class_id,
                "status": "active"
            }}
        )
        
        # Registra no histórico
        history_entry = {
            "id": str(uuid.uuid4()),
            "student_id": student_id,
            "school_id": new_school_id,
            "school_name": new_school.get('name'),
            "class_id": new_class_id,
            "class_name": new_class.get('name'),
            "enrollment_id": enrollment_id,
            "action_type": "transferencia_entrada",
            "previous_status": "transferred",
            "new_status": "active",
            "observations": f"Transferido da escola anterior. Nova matrícula: {new_enrollment_number}",
            "user_id": current_user.get('id'),
            "user_name": current_user.get('full_name') or current_user.get('email'),
            "action_date": datetime.now(timezone.utc).isoformat()
        }
        
        await current_db.student_history.insert_one(history_entry)
        
        updated_student = await current_db.students.find_one({"id": student_id}, {"_id": 0})
        return {
            "message": "Aluno transferido com sucesso",
            "student": updated_student,
            "enrollment": new_enrollment
        }

    @router.post("/{student_id}/cancel-transfer")
    async def cancel_transfer(student_id: str, request: Request):
        """Reverte uma transferência recém-emitida do aluno.

        Cenário: aluno pediu transferência (status='transferred') e desistiu,
        querendo voltar para a MESMA TURMA como se nada tivesse ocorrido.

        Comportamento:
          - Exige `status='transferred'` no aluno.
          - Aceita `class_id` opcional via query/body para informar a turma de
            origem da transferência. Sem `class_id`, usa o `class_id` do
            histórico de transferência mais recente.
          - Reverte o enrollment com `status='transferred'` para `status='active'`.
          - Restaura `student.status='active'`, `class_id` e `school_id`.
          - Registra entrada `transferencia_cancelada` no histórico (auditoria).
          - NÃO cria nenhum bloqueio acadêmico (não há `academic_events`
            associados à transferência, e o histórico de cancelamento não
            participa do composite closure / lens temporal).
        """
        current_user = await AuthMiddleware.require_roles(
            ['admin', 'admin_teste', 'secretario', 'super_admin', 'gerente']
        )(request)
        current_db = get_db_for_user(current_user)

        # class_id pode vir via query string ou body
        target_class_id: Optional[str] = request.query_params.get('class_id')
        if not target_class_id:
            try:
                body = await request.json()
                if isinstance(body, dict):
                    target_class_id = body.get('class_id')
            except Exception:
                target_class_id = None

        student = await current_db.students.find_one({"id": student_id}, {"_id": 0})
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        if student.get('status') != 'transferred':
            raise HTTPException(
                status_code=400,
                detail="Só é possível cancelar transferência de aluno com status 'Transferido'."
            )

        # Localiza o enrollment a ser revertido (mais recente com status='transferred')
        enr_query = {"student_id": student_id, "status": "transferred"}
        if target_class_id:
            enr_query["class_id"] = target_class_id
        enrollment = await current_db.enrollments.find_one(
            enr_query, {"_id": 0}, sort=[("academic_year", -1), ("created_at", -1)]
        )
        if not enrollment:
            raise HTTPException(
                status_code=404,
                detail="Matrícula transferida não encontrada para este aluno."
            )

        class_id = enrollment.get('class_id')
        school_id = enrollment.get('school_id')

        # Reverte a matrícula
        await current_db.enrollments.update_one(
            {"id": enrollment['id']}, {"$set": {"status": "active"}}
        )

        # Restaura o aluno
        await current_db.students.update_one(
            {"id": student_id},
            {"$set": {
                "status": "active",
                "class_id": class_id,
                "school_id": school_id,
            }}
        )

        # Histórico (auditoria) — não bloqueia nada
        class_doc = await current_db.classes.find_one(
            {"id": class_id}, {"_id": 0, "name": 1}
        )
        school_doc = await current_db.schools.find_one(
            {"id": school_id}, {"_id": 0, "name": 1}
        )
        history_entry = {
            "id": str(uuid.uuid4()),
            "student_id": student_id,
            "school_id": school_id,
            "school_name": school_doc.get('name') if school_doc else None,
            "class_id": class_id,
            "class_name": class_doc.get('name') if class_doc else None,
            "action_type": "transferencia_cancelada",
            "previous_status": "transferred",
            "new_status": "active",
            "observations": "Transferência cancelada — aluno restaurado na turma de origem.",
            "user_id": current_user.get('id'),
            "user_name": current_user.get('full_name') or current_user.get('email'),
            "action_date": datetime.now(timezone.utc).isoformat(),
        }
        await current_db.student_history.insert_one(history_entry)

        # Auditoria
        await audit_service.log(
            action='update',
            collection='students',
            user=current_user,
            request=request,
            document_id=student_id,
            description=f"Cancelou transferência do aluno {student.get('full_name', 'N/A')}",
            school_id=school_id,
            school_name=school_doc.get('name') if school_doc else None,
            old_value={'status': 'transferred', 'class_id': student.get('class_id')},
            new_value={'status': 'active', 'class_id': class_id},
            extra_data={'action_type': 'transferencia_cancelada'},
        )

        updated_student = await current_db.students.find_one({"id": student_id}, {"_id": 0})
        return {
            "message": "Transferência cancelada com sucesso. Aluno restaurado na turma de origem.",
            "student": Student(**updated_student).model_dump(),
            "class_id": class_id,
            "school_id": school_id,
        }

    @router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_student(student_id: str, request: Request):
        """Deleta aluno"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        student_doc = await current_db.students.find_one({"id": student_id}, {"_id": 0})
        if not student_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aluno não encontrado"
            )
        
        await AuthMiddleware.verify_school_access(request, student_doc['school_id'])
        
        result = await current_db.students.delete_one({"id": student_id})
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aluno não encontrado"
            )
        
        # Registra auditoria
        school = await current_db.schools.find_one({"id": student_doc.get('school_id')}, {"_id": 0, "name": 1})
        await audit_service.log(
            action='delete',
            collection='students',
            user=current_user,
            request=request,
            document_id=student_id,
            description=f"EXCLUIU aluno: {student_doc.get('full_name')} (CPF: {student_doc.get('cpf', 'N/A')})",
            school_id=student_doc.get('school_id'),
            school_name=school.get('name') if school else None,
            old_value={'full_name': student_doc.get('full_name'), 'cpf': student_doc.get('cpf'), 'class_id': student_doc.get('class_id')}
        )
        
        return None

    @router.post("/{student_id}/copy-data")
    async def copy_student_data_to_new_class(student_id: str, request: Request):
        """
        Copia dados de frequência e notas do aluno da turma de origem para a turma de destino.
        Usado durante remanejamento, progressão, reclassificação e transferência interna.

        Regra Feb 2026 (uniformizada): copia FREQUÊNCIA + NOTAS em TODAS as ações.
        - Cada registro copiado recebe `migrated_from_class_id` (id da turma origem) e
          `migrated_at` (timestamp ISO).
        - Para grades: a flag fica no documento.
        - Para attendance: a flag fica em records[].record_do_aluno.

        Edição posterior dos registros migrados é restrita a secretario, gerente,
        super_admin e admin (via validação no save de grades/attendance).

        Os dados na turma de origem são mantidos, mas ficam bloqueados para edição
        no bimestre que contém a action_date e nos posteriores (ver grades.py / attendance.py).
        """
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'super_admin', 'gerente', 'secretario'])(request)
        current_db = get_db_for_user(current_user)

        body = await request.json()
        source_class_id = body.get('source_class_id')
        target_class_id = body.get('target_class_id')
        copy_type = body.get('copy_type', 'remanejamento')  # remanejamento | progressao | reclassificacao | transferencia
        academic_year = body.get('academic_year', datetime.now().year)

        if not source_class_id or not target_class_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="source_class_id e target_class_id são obrigatórios"
            )

        student = await current_db.students.find_one({"id": student_id}, {"_id": 0})
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aluno não encontrado"
            )

        migrated_at_iso = datetime.now(timezone.utc).isoformat()
        copied_data = {"attendance_records": 0, "grades_records": 0}

        # ============== Frequência ==============
        attendances = await current_db.attendance.find({
            "class_id": source_class_id,
            "academic_year": academic_year,
            "records.student_id": student_id
        }, {"_id": 0}).to_list(1000)

        for att in attendances:
            existing = await current_db.attendance.find_one({
                "class_id": target_class_id,
                "date": att['date'],
                "academic_year": academic_year
            })

            student_record = None
            for rec in att.get('records', []):
                if rec['student_id'] == student_id:
                    student_record = dict(rec)  # copia para não mutar origem
                    break

            if not student_record:
                continue

            # Marca como migrado
            student_record['migrated_from_class_id'] = source_class_id
            student_record['migrated_at'] = migrated_at_iso

            if existing:
                existing_records = [r for r in existing.get('records', []) if r['student_id'] != student_id]
                existing_records.append(student_record)
                await current_db.attendance.update_one(
                    {"id": existing['id']},
                    {"$set": {"records": existing_records}}
                )
            else:
                new_attendance = {
                    "id": str(uuid.uuid4()),
                    "class_id": target_class_id,
                    "date": att['date'],
                    "academic_year": academic_year,
                    "records": [student_record],
                    "period": att.get('period', 'regular'),
                    "course_id": att.get('course_id'),
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                await current_db.attendance.insert_one(new_attendance)

            copied_data["attendance_records"] += 1

        # ============== Notas ==============
        # Regra Feb 2026: copia notas em TODAS as 4 ações (antes era só remanejamento)
        grades = await current_db.grades.find({
            "class_id": source_class_id,
            "student_id": student_id,
            "academic_year": academic_year
        }, {"_id": 0}).to_list(200)

        for grade in grades:
            existing_grade = await current_db.grades.find_one({
                "class_id": target_class_id,
                "student_id": student_id,
                "course_id": grade.get('course_id'),
                "academic_year": academic_year
            })

            if existing_grade:
                continue  # idempotente — não sobrescreve nota já existente no destino

            new_grade = {
                **grade,
                "id": str(uuid.uuid4()),
                "class_id": target_class_id,
                "migrated_from_class_id": source_class_id,
                "migrated_at": migrated_at_iso,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await current_db.grades.insert_one(new_grade)
            copied_data["grades_records"] += 1

        return {
            "message": f"Dados copiados com sucesso ({copy_type})",
            "student_id": student_id,
            "source_class_id": source_class_id,
            "target_class_id": target_class_id,
            "copied_data": copied_data
        }

    # ============= CPF VALIDATION =============

    def validate_cpf_algorithm(cpf: str) -> bool:
        """Valida CPF usando o algoritmo oficial brasileiro."""
        if not cpf:
            return False
        numbers = ''.join(filter(str.isdigit, cpf))
        if len(numbers) != 11:
            return False
        if len(set(numbers)) == 1:
            return False
        total = sum(int(numbers[i]) * (10 - i) for i in range(9))
        remainder = (total * 10) % 11
        if remainder == 10:
            remainder = 0
        if remainder != int(numbers[9]):
            return False
        total = sum(int(numbers[i]) * (11 - i) for i in range(10))
        remainder = (total * 10) % 11
        if remainder == 10:
            remainder = 0
        if remainder != int(numbers[10]):
            return False
        return True

    @router.get("/validate-cpf/{cpf}")
    async def validate_cpf(cpf: str, request: Request):
        """Valida se um CPF é válido usando o algoritmo oficial."""
        await AuthMiddleware.get_current_user(request)
        cpf_numbers = ''.join(filter(str.isdigit, cpf))
        is_valid = validate_cpf_algorithm(cpf_numbers)
        return {
            "cpf": cpf_numbers,
            "is_valid": is_valid,
            "message": "CPF válido" if is_valid else "CPF inválido"
        }

    @router.get("/check-cpf-duplicate/{cpf}")
    async def check_cpf_duplicate(
        cpf: str,
        request: Request,
        context: str = Query("student", description="Contexto: 'student' ou 'staff'"),
        exclude_id: Optional[str] = Query(None, description="ID para excluir da verificação")
    ):
        """Verifica se um CPF já está cadastrado no sistema."""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        cpf_numbers = ''.join(filter(str.isdigit, cpf))
        if len(cpf_numbers) != 11:
            return {"is_duplicate": False, "message": "CPF incompleto"}
        
        duplicates = []
        def normalize_cpf(cpf_value):
            if not cpf_value:
                return ""
            return ''.join(filter(str.isdigit, str(cpf_value)))
        
        cpf_regex = '.*'.join(cpf_numbers)
        
        student_query = {"cpf": {"$regex": cpf_regex}}
        if context == "student" and exclude_id:
            student_query["id"] = {"$ne": exclude_id}
        student_with_cpf = await current_db.students.find_one(student_query, {"_id": 0, "id": 1, "full_name": 1, "cpf": 1})
        if student_with_cpf and normalize_cpf(student_with_cpf.get("cpf")) == cpf_numbers:
            if context != "staff":
                duplicates.append({
                    "type": "student",
                    "name": student_with_cpf.get("full_name"),
                    "message": f"CPF já cadastrado para o aluno: {student_with_cpf.get('full_name')}"
                })
        
        staff_query = {"cpf": {"$regex": cpf_regex}}
        if context == "staff" and exclude_id:
            staff_query["id"] = {"$ne": exclude_id}
        staff_with_cpf = await current_db.staff.find_one(staff_query, {"_id": 0, "id": 1, "nome": 1, "cpf": 1})
        if staff_with_cpf and normalize_cpf(staff_with_cpf.get("cpf")) == cpf_numbers:
            if context != "student":
                duplicates.append({
                    "type": "staff",
                    "name": staff_with_cpf.get("nome"),
                    "message": f"CPF já cadastrado para o servidor: {staff_with_cpf.get('nome')}"
                })
        
        parent_query = {"$or": [
            {"father_cpf": {"$regex": cpf_regex}},
            {"mother_cpf": {"$regex": cpf_regex}}
        ]}
        parent_student = await current_db.students.find_one(parent_query, {"_id": 0, "id": 1, "full_name": 1, "father_name": 1, "mother_name": 1, "father_cpf": 1, "mother_cpf": 1})
        if parent_student:
            if context != "staff":
                parent_name = None
                if normalize_cpf(parent_student.get("father_cpf")) == cpf_numbers:
                    parent_name = parent_student.get("father_name", "Pai")
                elif normalize_cpf(parent_student.get("mother_cpf")) == cpf_numbers:
                    parent_name = parent_student.get("mother_name", "Mãe")
                if parent_name:
                    duplicates.append({
                        "type": "parent",
                        "name": parent_name,
                        "student_name": parent_student.get("full_name"),
                        "message": f"CPF já cadastrado como responsável ({parent_name}) do aluno: {parent_student.get('full_name')}"
                    })
        
        return {
            "cpf": cpf_numbers,
            "is_duplicate": len(duplicates) > 0,
            "duplicates": duplicates,
            "message": duplicates[0]["message"] if duplicates else "CPF disponível"
        }

    return router
