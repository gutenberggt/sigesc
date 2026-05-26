"""
Router de Turmas - SIGESC
Endpoints para gestão de turmas (classes).
"""

from fastapi import APIRouter, HTTPException, status, Request
from typing import List, Optional

from models import Class, ClassCreate, ClassUpdate
from auth_middleware import AuthMiddleware
from utils.cache import cache, CACHE_TTL_CLASSES
from tenant_scope import apply_tenant_filter, assert_same_tenant, resolve_tenant_id_for_create, get_mantenedora_scope

router = APIRouter(prefix="/classes", tags=["Turmas"])


def setup_router(db, audit_service, sandbox_db=None):
    """Configura o router com as dependências necessárias"""
    
    def get_db_for_user(user: dict):
        """Retorna o banco correto baseado no usuário"""
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db

    @router.post("", response_model=Class, status_code=status.HTTP_201_CREATED)
    async def create_class(class_data: ClassCreate, request: Request):
        """Cria nova turma"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        # Verifica acesso à escola
        await AuthMiddleware.verify_school_access(request, class_data.school_id)
        
        # [Mai/2026] CAPS lock automático removido — preserva capitalização do usuário.
        class_dict = class_data.model_dump()
        class_obj = Class(**class_dict)
        doc = class_obj.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        
        # Multi-tenancy: injeta mantenedora_id derivada da escola
        doc['mantenedora_id'] = await resolve_tenant_id_for_create(
            current_db, current_user, request, school_id=class_data.school_id
        )
        
        await current_db.classes.insert_one(doc)
        
        cache.invalidate('classes')
        return class_obj

    @router.get("")
    async def list_classes(request: Request, school_id: Optional[str] = None, skip: int = 0, limit: int = 1000):
        """Lista turmas"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        tenant_id = get_mantenedora_scope(current_user, request)
        
        cache_params = {
            'role': current_user['role'],
            'school_ids': sorted(current_user.get('school_ids', [])),
            'tenant': tenant_id or 'ALL',
            'school_id': school_id, 'skip': skip, 'limit': limit
        }
        cached = cache.get('classes', cache_params)
        if cached is not None:
            return cached
        
        # Constrói filtro
        filter_query = {}
        
        # Papéis com visão tenant-wide das turmas (apenas leitura para semed1/semed2):
        # admin, admin_teste, super_admin, gerente, semed, semed1 (Tutor), semed2 (Analista),
        # semed3 (Administração), secretario, ass_social, ass_social_2, agente_vacinas.
        # Alinhado com /app/frontend/src/pages/Users.js (`classes: 'view'`) e com
        # /app/backend/routers/schools.py::list_schools.
        if current_user['role'] in ['admin', 'admin_teste', 'super_admin', 'gerente', 'semed', 'semed1', 'semed2', 'semed3', 'secretario', 'ass_social', 'ass_social_2', 'agente_vacinas']:
            if school_id:
                filter_query['school_id'] = school_id
        else:
            # Outros papéis veem apenas das escolas vinculadas
            if school_id and school_id in current_user.get('school_ids', []):
                filter_query['school_id'] = school_id
            else:
                filter_query['school_id'] = {"$in": current_user.get('school_ids', [])}
        
        # Multi-tenancy: aplica filtro por mantenedora
        filter_query = apply_tenant_filter(filter_query, current_user, request)
        
        classes = await current_db.classes.find(filter_query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
        
        # Ordenar: números primeiro, depois letras, ambos em ordem natural
        import re
        def class_sort_key(c):
            name = (c.get('name') or '').strip()
            starts_with_digit = bool(name and name[0].isdigit())
            # Extrair número inicial para ordenação natural
            m = re.match(r'^(\d+)', name)
            num = int(m.group(1)) if m else float('inf')
            return (0 if starts_with_digit else 1, num, name.lower())
        
        classes.sort(key=class_sort_key)
        
        # Adicionar contagem de alunos matriculados por turma
        if classes:
            class_ids = [c['id'] for c in classes]
            pipeline = [
                {"$match": {"class_id": {"$in": class_ids}, "status": "active"}},
                {"$group": {"_id": "$class_id", "count": {"$sum": 1}}}
            ]
            counts = await current_db.enrollments.aggregate(pipeline).to_list(1000)
            count_map = {c['_id']: c['count'] for c in counts}
            for c in classes:
                c['student_count'] = count_map.get(c['id'], 0)
        
        cache.set('classes', cache_params, classes, CACHE_TTL_CLASSES)
        return classes

    @router.get("/{class_id}", response_model=Class)
    async def get_class(class_id: str, request: Request):
        """Busca turma por ID"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        class_doc = await current_db.classes.find_one({"id": class_id}, {"_id": 0})
        
        if not class_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Turma não encontrada"
            )
        
        # Verifica acesso à escola da turma
        await AuthMiddleware.verify_school_access(request, class_doc['school_id'])
        
        # Multi-tenancy: valida tenant
        assert_same_tenant(class_doc, current_user, request)
        
        return Class(**class_doc)

    @router.put("/{class_id}", response_model=Class)
    async def update_class(class_id: str, class_update: ClassUpdate, request: Request):
        """Atualiza turma"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        # Busca turma
        class_doc = await current_db.classes.find_one({"id": class_id}, {"_id": 0})
        if not class_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Turma não encontrada"
            )
        
        # Verifica acesso
        await AuthMiddleware.verify_school_access(request, class_doc['school_id'])
        assert_same_tenant(class_doc, current_user, request)
        
        update_data = class_update.model_dump(exclude_unset=True)
        
        # [Mai/2026] CAPS lock automático removido — preserva capitalização do usuário.
        
        if update_data:
            await current_db.classes.update_one(
                {"id": class_id},
                {"$set": update_data}
            )
        
        updated_class = await current_db.classes.find_one({"id": class_id}, {"_id": 0})
        cache.invalidate('classes')
        return Class(**updated_class)

    @router.delete("/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_class(class_id: str, request: Request):
        """Deleta turma"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        # Busca turma
        class_doc = await current_db.classes.find_one({"id": class_id}, {"_id": 0})
        if not class_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Turma não encontrada"
            )
        
        # Verifica acesso
        await AuthMiddleware.verify_school_access(request, class_doc['school_id'])
        assert_same_tenant(class_doc, current_user, request)

        # [Fev/2026] Bloqueia exclusão se houver dependência ativa vinculada a esta turma.
        # Ver /app/docs/STUDENT_DEPENDENCY.md.
        active_deps = await current_db.student_dependencies.count_documents({
            "class_id": class_id, "status": "active",
        })
        if active_deps > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Não é possível excluir esta turma: {active_deps} aluno(s) com dependência de estudos ativa vinculada(s). Cancele/conclua as dependências antes."
            )

        # [Fase 0 — Contenção] Bloqueia exclusão se houver alunos ATIVOS
        # vinculados à turma. Impede gerar matrículas órfãs (class_id
        # apontando para turma deletada), que contaminam relatórios e censo.
        active_students = await current_db.students.count_documents({
            "class_id": class_id, "status": "active",
        })
        if active_students > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Não é possível excluir esta turma: {active_students} aluno(s) ativo(s) vinculado(s). Transfira/inative os alunos antes de excluir a turma."
            )
        
        result = await current_db.classes.delete_one({"id": class_id})
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Turma não encontrada"
            )
        
        cache.invalidate('classes')
        return None

    @router.get("/{class_id}/curriculum")
    async def get_class_curriculum(class_id: str, request: Request):
        """Retorna a matriz curricular efetiva da turma.

        Une duas fontes de cadastro:
          - `class.course_ids` (matriz explícita, se houver);
          - `teacher_assignments` (vínculos professor↔disciplina↔turma ativos).

        Hidrata com o documento de `courses` para retornar id+nome+programa.
        Usado pelo modal de Dependência de Estudos para listar SOMENTE
        os componentes pertinentes à turma escolhida.

        Não é específico de aluno (não consulta `grades`/`attendance`).
        """
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)

        cls = await current_db.classes.find_one(
            {"id": class_id},
            {"_id": 0, "id": 1, "name": 1, "course_ids": 1, "school_id": 1,
             "academic_year": 1, "atendimento_programa": 1,
             "is_multi_grade": 1, "series": 1, "grade_level": 1},
        )
        if not cls:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Turma não encontrada"
            )

        seen: set[str] = set()
        ordered_ids: list[str] = []

        for cid in (cls.get("course_ids") or []):
            if cid and cid not in seen:
                seen.add(cid)
                ordered_ids.append(cid)

        async for a in current_db.teacher_assignments.find(
            {"class_id": class_id,
             "status": {"$in": ["active", "Ativo", "ativo"]}},
            {"_id": 0, "course_id": 1},
        ):
            cid = a.get("course_id")
            if cid and cid not in seen:
                seen.add(cid)
                ordered_ids.append(cid)

        components: list[dict] = []
        if ordered_ids:
            docs = await current_db.courses.find(
                {"id": {"$in": ordered_ids}},
                {"_id": 0, "id": 1, "name": 1, "active": 1,
                 "atendimento_programa": 1, "optativo": 1, "grade_levels": 1},
            ).to_list(500)
            by_id = {d["id"]: d for d in docs}
            for cid in ordered_ids:
                d = by_id.get(cid)
                if not d:
                    continue
                components.append({
                    "id": d["id"],
                    "name": d.get("name"),
                    "active": bool(d.get("active", True)),
                    "atendimento_programa": d.get("atendimento_programa") or "regular",
                    "optativo": bool(d.get("optativo", False)),
                    # [Fev/2026] Lista de séries para que o front filtre componentes
                    # quando a turma é multisseriada (2+ séries). Vem do cadastro
                    # do componente em `courses.grade_levels`. Pode ser vazio →
                    # interpreta como "aplica a todas as séries da turma".
                    "grade_levels": d.get("grade_levels") or [],
                })
        # Ordena alfabeticamente para UI estável
        components.sort(key=lambda c: (c.get("name") or "").casefold())

        return {
            "class_id": cls["id"],
            "class_name": cls.get("name"),
            "school_id": cls.get("school_id"),
            "academic_year": cls.get("academic_year"),
            "atendimento_programa": cls.get("atendimento_programa") or "regular",
            # [Fev/2026] Necessário para o modal de Dependência de Estudos
            # decidir se mostra o seletor "Série da dependência" antes do
            # componente curricular (case multisseriada).
            "is_multi_grade": bool(cls.get("is_multi_grade")),
            "series": cls.get("series") or [],
            "grade_level": cls.get("grade_level"),
            "sources": {
                "class_course_ids_count": len(cls.get("course_ids") or []),
                "teacher_assignments_count": len(ordered_ids) - len(cls.get("course_ids") or []),
                "total_unique": len(ordered_ids),
            },
            "components": components,
        }

    @router.get("/{class_id}/roster")
    async def get_class_roster(
        class_id: str,
        request: Request,
        course_id: Optional[str] = None,
        academic_year: Optional[int] = None,
    ):
        """Roster da turma — alunos regulares + alunos em dependência.

        Comportamento:
          - Lista alunos `regulares` matriculados na turma (`students.class_id == class_id`).
          - Adiciona alunos com `student_dependencies` ATIVAS apontando para esta
            turma. Filtra por `course_id` se informado (caso de diário por componente).
          - Sem `course_id`: inclui qualquer aluno com dep ativa em qualquer
            componente da turma (deduplicado).
          - Ordenação **alfabética por `full_name`** misturando regulares e
            dep (decisão 2b — chip 'DEP' fica a cargo do frontend via flag
            `is_dependency`).

        Cada item: `{id, full_name, registration_number, photo_url, is_dependency,
        dependency_course_ids?, dependency_origin_year?, dependency_class_id?}`.

        Usado pelo Diário (lançamento de notas/frequência) e por outras telas
        que listam alunos efetivamente "pertencentes" à composição da turma.
        """
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)

        cls = await current_db.classes.find_one(
            {"id": class_id},
            {"_id": 0, "id": 1, "name": 1, "school_id": 1, "academic_year": 1},
        )
        if not cls:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Turma não encontrada"
            )
        year = academic_year or cls.get("academic_year") or 0

        # 1) Regulares — matriculados na turma (alunos não exclusivamente dep)
        regular_filter = {
            "class_id": class_id,
            "$or": [
                {"dependency_mode": {"$ne": "dependency_only"}},
                {"dependency_mode": {"$exists": False}},
            ],
        }
        regular_students = await current_db.students.find(
            regular_filter,
            {"_id": 0, "id": 1, "full_name": 1, "registration_number": 1,
             "photo_url": 1, "dependency_mode": 1},
        ).to_list(2000)

        # 2) Dependências — alunos com dep ativa na turma (opcional: + course_id)
        dep_filter: dict = {
            "class_id": class_id,
            "status": "active",
        }
        if year:
            dep_filter["academic_year"] = year
        if course_id:
            dep_filter["course_id"] = course_id

        deps_by_student: dict[str, dict] = {}
        async for d in current_db.student_dependencies.find(
            dep_filter,
            {"_id": 0, "student_id": 1, "course_id": 1,
             "origin_academic_year": 1, "origin_class_id": 1},
        ):
            sid = d.get("student_id")
            if not sid:
                continue
            entry = deps_by_student.setdefault(sid, {
                "course_ids": set(),
                "origin_years": set(),
                "origin_class_ids": set(),
            })
            if d.get("course_id"):
                entry["course_ids"].add(d["course_id"])
            if d.get("origin_academic_year"):
                entry["origin_years"].add(d["origin_academic_year"])
            if d.get("origin_class_id"):
                entry["origin_class_ids"].add(d["origin_class_id"])

        # Hidrata alunos de dep (que podem não estar matriculados nesta turma)
        dep_student_ids = list(deps_by_student.keys())
        dep_students_docs: dict[str, dict] = {}
        if dep_student_ids:
            async for s in current_db.students.find(
                {"id": {"$in": dep_student_ids}},
                {"_id": 0, "id": 1, "full_name": 1, "registration_number": 1,
                 "photo_url": 1, "dependency_mode": 1},
            ):
                dep_students_docs[s["id"]] = s

        # 3) Monta lista final — regular primeiro (todos com is_dependency=False),
        # depois dep (filtrando os já regulares — não duplica).
        regular_ids = {s["id"] for s in regular_students}
        items: list[dict] = []
        for s in regular_students:
            items.append({
                "id": s["id"],
                "full_name": s.get("full_name") or "",
                "registration_number": s.get("registration_number"),
                "photo_url": s.get("photo_url"),
                "is_dependency": False,
                "dependency_course_ids": [],
                "dependency_origin_year": None,
                "dependency_class_id": None,
            })
        for sid, info in deps_by_student.items():
            if sid in regular_ids:
                # Aluno é regular E tem dep nessa mesma turma — situação rara,
                # mas trate como regular (chip dep não faz sentido aqui).
                continue
            s = dep_students_docs.get(sid)
            if not s:
                continue
            items.append({
                "id": s["id"],
                "full_name": s.get("full_name") or "",
                "registration_number": s.get("registration_number"),
                "photo_url": s.get("photo_url"),
                "is_dependency": True,
                "dependency_course_ids": sorted(info["course_ids"]),
                "dependency_origin_year": (
                    max(info["origin_years"]) if info["origin_years"] else None
                ),
                "dependency_class_id": (
                    next(iter(info["origin_class_ids"]))
                    if info["origin_class_ids"] else None
                ),
            })

        # Ordem alfabética unificada
        items.sort(key=lambda x: (x.get("full_name") or "").casefold())

        return {
            "class_id": cls["id"],
            "class_name": cls.get("name"),
            "school_id": cls.get("school_id"),
            "academic_year": year,
            "course_id": course_id,
            "students": items,
            "total_regular": sum(1 for i in items if not i["is_dependency"]),
            "total_dependency": sum(1 for i in items if i["is_dependency"]),
            "total": len(items),
        }

    return router
