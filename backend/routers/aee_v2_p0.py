"""AEE v2 — salvaguardas P0 de integridade, autoria e leitura do professor.

Autorizado explicitamente pelo proprietário do produto em 21/08/2026.
Hotfix de leitura do professor autorizado explicitamente em 31/08/2026.

Esta camada segue o padrão de hardening já usado no SIGESC: o router legado do
Diário AEE permanece intacto e apenas os endpoints críticos são envolvidos.

Objetivos P0:
- impedir que novos Planos/Atendimentos atribuam como professor AEE um usuário
  administrativo apenas porque foi ele quem executou a operação;
- separar ator da alteração (created_by/updated_by) do professor AEE responsável;
- impedir hard delete de Plano AEE que já represente documento vigente/histórico
  ou que possua atendimentos, evoluções ou articulações vinculadas;
- preservar o histórico de atendimentos quando registros antigos carregarem
  identidade de professor incompatível, herdando a leitura do Plano AEE;
- restaurar a projeção das turmas AEE em /professor/turmas sem incluir o AEE no
  DVD v1, usando vínculo AEE legado e Plano AEE como fallback compatível;
- preservar integralmente IDs, enums e payloads legados nesta fase.
"""

from __future__ import annotations

from datetime import datetime
import importlib
from typing import Any, Iterable, Optional

from fastapi import HTTPException, Request, status

from auth_middleware import AuthMiddleware
from models import (
    AtendimentoAEE,
    AtendimentoAEECreate,
    AtendimentoAEEUpdate,
    PlanoAEE,
    PlanoAEECreate,
    PlanoAEEUpdate,
)


AEE_STATUS_LABELS = {
    "rascunho": "Em elaboração",
    "ativo": "Vigente",
    "revisao": "Em revisão",
    "encerrado": "Encerrado",
}

# Mantém exatamente o contrato de autorização do DELETE legado. O hardening P0
# restringe o que pode ser apagado, mas não amplia quem pode executar a ação.
AEE_PLAN_DELETE_ROLES = [
    "super_admin",
    "gerente",
    "admin",
    "admin_teste",
    "coordenador",
    "apoio_pedagogico",
    "auxiliar_secretaria",
    "secretario",
]


def aee_status_label(value: Optional[str]) -> str:
    """Rótulo pedagógico sem alterar o enum persistido no legado."""
    if not value:
        return "Não informado"
    return AEE_STATUS_LABELS.get(value, value)


def _remove_route(base_router, path: str, method: str):
    for route in list(base_router.routes):
        if (
            getattr(route, "path", None) == path
            and method.upper() in (getattr(route, "methods", set()) or set())
        ):
            endpoint = route.endpoint
            base_router.routes.remove(route)
            return endpoint
    return None


def _model_copy(model: Any, **updates: Any):
    """Compatibilidade Pydantic v2/v1 para cópia de payload tipado."""
    if hasattr(model, "model_copy"):
        return model.model_copy(update=updates)
    return model.copy(update=updates)


def _result_id(result: Any) -> Optional[str]:
    if isinstance(result, dict):
        return result.get("id")
    return getattr(result, "id", None)


def _set_result_professor(result: Any, professor_id: str, professor_nome: Optional[str]):
    if isinstance(result, dict):
        result["professor_aee_id"] = professor_id
        result["professor_aee_nome"] = professor_nome
        return result
    try:
        result.professor_aee_id = professor_id
        result.professor_aee_nome = professor_nome
    except Exception:
        pass
    return result


def build_professor_plan_access_query(
    professor_user_id: str,
    *,
    plano_aee_id: Optional[str] = None,
    student_id: Optional[str] = None,
    school_id: Optional[str] = None,
    academic_year: Optional[int] = None,
) -> dict:
    """Replica a política de leitura do Plano AEE para dependências históricas.

    O Plano é a âncora de autorização. ``created_by`` permanece somente como
    compatibilidade histórica para registros anteriores ao saneamento de
    ``professor_aee_id``; não cria um novo conceito de ownership.
    """
    query: dict[str, Any] = {
        "$or": [
            {"professor_aee_id": professor_user_id},
            {"created_by": professor_user_id},
        ]
    }
    if plano_aee_id:
        query["id"] = plano_aee_id
    if student_id:
        query["student_id"] = student_id
    if school_id:
        query["school_id"] = school_id
    if academic_year is not None:
        query["academic_year"] = academic_year
    return query


async def _require_write(request: Request, write_roles: Iterable[str]) -> dict:
    user = await AuthMiddleware.get_current_user(request)
    if user.get("role") not in set(write_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seu perfil permite apenas visualização no módulo AEE",
        )
    return user


async def resolve_aee_responsible_professor(
    db,
    *,
    student_id: str,
    requested_id: Optional[str] = None,
    requested_nome: Optional[str] = None,
    current_user: Optional[dict] = None,
) -> tuple[str, Optional[str]]:
    """Resolve o professor AEE responsável sem confundir autoria com responsabilidade.

    Ordem de resolução:
    1. professor alocado à turma AEE do estudante (fonte preferencial);
    2. professor explicitamente informado, desde que seja usuário com role professor;
    3. usuário atual, somente quando ele próprio possui role professor.

    Usuários administrativos nunca são usados como fallback de professor AEE.
    """
    student = await db.students.find_one(
        {"id": student_id},
        {"_id": 0, "id": 1, "atendimento_programa_class_id": 1},
    )
    if not student:
        raise HTTPException(status_code=404, detail="Estudante não encontrado")

    aee_class_id = student.get("atendimento_programa_class_id")
    if aee_class_id:
        assignment = await db.teacher_assignments.find_one(
            {
                "class_id": aee_class_id,
                "status": {"$in": ["ativo", "active"]},
            },
            {"_id": 0, "staff_id": 1},
        )
        if assignment and assignment.get("staff_id"):
            staff = await db.staff.find_one(
                {"id": assignment.get("staff_id")},
                {"_id": 0, "id": 1, "nome": 1, "email": 1, "user_id": 1},
            )
            if staff:
                linked_user = None
                if staff.get("user_id"):
                    linked_user = await db.users.find_one(
                        {"id": staff.get("user_id"), "role": "professor"},
                        {"_id": 0, "id": 1, "full_name": 1},
                    )
                if not linked_user and staff.get("email"):
                    linked_user = await db.users.find_one(
                        {"email": staff.get("email"), "role": "professor"},
                        {"_id": 0, "id": 1, "full_name": 1},
                    )
                if linked_user and linked_user.get("id"):
                    return (
                        linked_user.get("id"),
                        staff.get("nome") or linked_user.get("full_name"),
                    )

    if requested_id:
        requested_user = await db.users.find_one(
            {"id": requested_id, "role": "professor"},
            {"_id": 0, "id": 1, "full_name": 1},
        )
        if requested_user and requested_user.get("id"):
            return (
                requested_user.get("id"),
                requested_nome or requested_user.get("full_name"),
            )

    if current_user and current_user.get("role") == "professor" and current_user.get("id"):
        return (
            current_user.get("id"),
            current_user.get("full_name") or current_user.get("email"),
        )

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "AEE_RESPONSIBLE_PROFESSOR_UNRESOLVED",
            "message": (
                "Não foi possível determinar o professor AEE responsável. "
                "Vincule um professor à turma AEE do estudante ou informe um "
                "usuário com perfil Professor. O usuário administrativo que "
                "executa a operação não será registrado como professor AEE."
            ),
        },
    )


async def get_plan_dependency_counts(db, plano_id: str) -> dict[str, int]:
    """Conta vínculos que transformam o Plano em documento histórico."""
    return {
        "atendimentos": await db.atendimentos_aee.count_documents({"plano_aee_id": plano_id}),
        "evolucoes": await db.evolucoes_aee.count_documents({"plano_aee_id": plano_id}),
        "articulacoes": await db.articulacoes_aee.count_documents({"plano_aee_id": plano_id}),
    }


def plan_hard_delete_allowed(plan_status: Optional[str], dependencies: dict[str, int]) -> bool:
    """Hard delete só é permitido para rascunho realmente vazio."""
    return plan_status == "rascunho" and not any(int(v or 0) > 0 for v in dependencies.values())


def install_aee_v2_p0(base_router, db, audit_service, *, write_roles: Iterable[str]):
    if getattr(base_router, "_aee_v2_p0_installed", False):
        return base_router

    current_create_plan = _remove_route(base_router, "/aee/planos", "POST")
    current_update_plan = _remove_route(base_router, "/aee/planos/{plano_id}", "PUT")
    current_delete_plan = _remove_route(base_router, "/aee/planos/{plano_id}", "DELETE")
    current_duplicate_plan = _remove_route(base_router, "/aee/planos/{plano_id}/duplicate", "POST")
    current_from_template = _remove_route(base_router, "/aee/planos/from-template", "POST")
    current_create_attendance = _remove_route(base_router, "/aee/atendimentos", "POST")
    current_list_attendance = _remove_route(base_router, "/aee/atendimentos", "GET")
    current_update_attendance = _remove_route(
        base_router, "/aee/atendimentos/{atendimento_id}", "PUT"
    )

    required = {
        "POST /aee/planos": current_create_plan,
        "PUT /aee/planos/{plano_id}": current_update_plan,
        "DELETE /aee/planos/{plano_id}": current_delete_plan,
        "POST /aee/planos/{plano_id}/duplicate": current_duplicate_plan,
        "POST /aee/planos/from-template": current_from_template,
        "POST /aee/atendimentos": current_create_attendance,
        "GET /aee/atendimentos": current_list_attendance,
        "PUT /aee/atendimentos/{atendimento_id}": current_update_attendance,
    }
    missing = [name for name, endpoint in required.items() if endpoint is None]
    if missing:
        raise RuntimeError(
            "AEE v2 P0 não pôde ser instalado; rotas esperadas ausentes: " + ", ".join(missing)
        )

    @base_router.post("/planos", response_model=PlanoAEE, status_code=status.HTTP_201_CREATED)
    async def p0_create_plan(plano_data: PlanoAEECreate, request: Request):
        current_user = await _require_write(request, write_roles)

        student = await db.students.find_one(
            {"id": plano_data.student_id}, {"_id": 0, "full_name": 1}
        )
        if not student:
            raise HTTPException(status_code=404, detail="Estudante não encontrado")

        existing = await db.planos_aee.find_one(
            {
                "student_id": plano_data.student_id,
                "academic_year": plano_data.academic_year,
                "status": {"$in": ["ativo", "rascunho"]},
            },
            {"_id": 0, "status": 1},
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{student.get('full_name', 'Este estudante')} já possui um Plano AEE "
                    f"{aee_status_label(existing.get('status')).lower()} no ano letivo "
                    f"{plano_data.academic_year}. Edite o plano existente em vez de criar um novo."
                ),
            )

        professor_id, professor_nome = await resolve_aee_responsible_professor(
            db,
            student_id=plano_data.student_id,
            requested_id=plano_data.professor_aee_id,
            requested_nome=plano_data.professor_aee_nome,
            current_user=current_user,
        )
        safe_data = _model_copy(
            plano_data,
            professor_aee_id=professor_id,
            professor_aee_nome=professor_nome,
        )
        result = await current_create_plan(safe_data, request)
        plano_id = _result_id(result)
        if plano_id:
            await db.planos_aee.update_one(
                {"id": plano_id},
                {
                    "$set": {
                        "created_by": current_user.get("id"),
                        "updated_by": current_user.get("id"),
                    }
                },
            )
        return result

    @base_router.put("/planos/{plano_id}")
    async def p0_update_plan(
        plano_id: str,
        plano_update: PlanoAEEUpdate,
        request: Request,
    ):
        current_user = await _require_write(request, write_roles)
        existing = await db.planos_aee.find_one({"id": plano_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Plano AEE não encontrado")

        # P0: edição geral não pode trocar silenciosamente o professor responsável.
        # Reatribuição terá fluxo explícito próprio em fase posterior.
        safe_update = _model_copy(
            plano_update,
            professor_aee_id=existing.get("professor_aee_id"),
            professor_aee_nome=existing.get("professor_aee_nome"),
        )
        result = await current_update_plan(plano_id, safe_update, request)
        await db.planos_aee.update_one(
            {"id": plano_id}, {"$set": {"updated_by": current_user.get("id")}}
        )
        if isinstance(result, dict):
            result["updated_by"] = current_user.get("id")
        return result

    @base_router.delete("/planos/{plano_id}")
    async def p0_delete_plan(plano_id: str, request: Request):
        # Autorização vem antes de qualquer consulta ao documento/dependências,
        # evitando vazamento de existência ou contagens a perfis sem permissão.
        await AuthMiddleware.require_roles(AEE_PLAN_DELETE_ROLES)(request)

        existing = await db.planos_aee.find_one({"id": plano_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Plano AEE não encontrado")

        dependencies = await get_plan_dependency_counts(db, plano_id)
        if not plan_hard_delete_allowed(existing.get("status"), dependencies):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "AEE_PLAN_HARD_DELETE_BLOCKED",
                    "message": (
                        "O Plano AEE não pode ser excluído fisicamente. Somente um Plano "
                        "Em elaboração e sem qualquer registro vinculado pode ser removido. "
                        "Planos Vigentes, Em revisão, Encerrados ou com histórico devem ser "
                        "preservados."
                    ),
                    "status": existing.get("status"),
                    "status_label": aee_status_label(existing.get("status")),
                    "dependencies": dependencies,
                },
            )

        return await current_delete_plan(plano_id, request)

    @base_router.post(
        "/planos/{plano_id}/duplicate",
        status_code=status.HTTP_201_CREATED,
    )
    async def p0_duplicate_plan(plano_id: str, request: Request):
        current_user = await _require_write(request, write_roles)
        original = await db.planos_aee.find_one({"id": plano_id}, {"_id": 0})
        if not original:
            raise HTTPException(status_code=404, detail="Plano AEE não encontrado")

        try:
            body = await request.json()
        except Exception:
            body = {}
        target_student_id = (body or {}).get("target_student_id") or original.get("student_id")

        professor_id, professor_nome = await resolve_aee_responsible_professor(
            db,
            student_id=target_student_id,
            requested_id=original.get("professor_aee_id"),
            requested_nome=original.get("professor_aee_nome"),
            current_user=current_user,
        )

        result = await current_duplicate_plan(plano_id, request)
        new_id = _result_id(result)
        if new_id:
            await db.planos_aee.update_one(
                {"id": new_id},
                {
                    "$set": {
                        "professor_aee_id": professor_id,
                        "professor_aee_nome": professor_nome,
                        "updated_by": current_user.get("id"),
                    }
                },
            )
        return _set_result_professor(result, professor_id, professor_nome)

    @base_router.post(
        "/planos/from-template",
        response_model=PlanoAEE,
        status_code=status.HTTP_201_CREATED,
    )
    async def p0_create_plan_from_template(request: Request):
        current_user = await _require_write(request, write_roles)
        try:
            body = await request.json()
        except Exception:
            body = {}
        student_id = (body or {}).get("student_id")
        if not student_id:
            return await current_from_template(request)

        requested_id = current_user.get("id") if current_user.get("role") == "professor" else None
        requested_nome = (
            (current_user.get("full_name") or current_user.get("email"))
            if current_user.get("role") == "professor"
            else None
        )
        professor_id, professor_nome = await resolve_aee_responsible_professor(
            db,
            student_id=student_id,
            requested_id=requested_id,
            requested_nome=requested_nome,
            current_user=current_user,
        )

        result = await current_from_template(request)
        new_id = _result_id(result)
        if new_id:
            await db.planos_aee.update_one(
                {"id": new_id},
                {
                    "$set": {
                        "professor_aee_id": professor_id,
                        "professor_aee_nome": professor_nome,
                        "updated_by": current_user.get("id"),
                    }
                },
            )
        return _set_result_professor(result, professor_id, professor_nome)

    @base_router.post(
        "/atendimentos",
        response_model=AtendimentoAEE,
        status_code=status.HTTP_201_CREATED,
    )
    async def p0_create_attendance(
        atendimento_data: AtendimentoAEECreate,
        request: Request,
    ):
        current_user = await _require_write(request, write_roles)
        plano = await db.planos_aee.find_one(
            {"id": atendimento_data.plano_aee_id}, {"_id": 0}
        )
        if not plano:
            raise HTTPException(status_code=404, detail="Plano AEE não encontrado")

        professor_id, professor_nome = await resolve_aee_responsible_professor(
            db,
            student_id=plano.get("student_id"),
            requested_id=plano.get("professor_aee_id"),
            requested_nome=plano.get("professor_aee_nome"),
            current_user=current_user,
        )
        safe_data = _model_copy(
            atendimento_data,
            professor_aee_id=professor_id,
            professor_aee_nome=professor_nome,
            student_id=plano.get("student_id"),
        )
        result = await current_create_attendance(safe_data, request)
        atendimento_id = _result_id(result)
        if atendimento_id:
            await db.atendimentos_aee.update_one(
                {"id": atendimento_id},
                {
                    "$set": {
                        "created_by": current_user.get("id"),
                        "updated_by": current_user.get("id"),
                    }
                },
            )
        return result

    @base_router.get("/atendimentos")
    async def p0_list_attendances(
        request: Request,
        plano_aee_id: Optional[str] = None,
        student_id: Optional[str] = None,
        school_id: Optional[str] = None,
        academic_year: Optional[int] = None,
        data_inicio: Optional[str] = None,
        data_fim: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ):
        """Lista atendimentos; Professor herda o escopo do Plano AEE.

        Registros históricos podem ter ``professor_aee_id`` ausente, staff.id ou
        outro identificador legado. A autorização não é inferida do atendimento:
        primeiro resolvemos os Planos que o professor pode ler e só então
        buscamos suas dependências. Assim o Dossiê mantém o histórico completo
        sem ampliar acesso a Planos de outros professores.
        """
        current_user = await AuthMiddleware.get_current_user(request)
        if current_user.get("role") != "professor":
            return await current_list_attendance(
                request=request,
                plano_aee_id=plano_aee_id,
                student_id=student_id,
                school_id=school_id,
                academic_year=academic_year,
                data_inicio=data_inicio,
                data_fim=data_fim,
                skip=skip,
                limit=limit,
            )

        uid = current_user.get("id")
        if not uid:
            return {"items": [], "total": 0}

        plan_query = build_professor_plan_access_query(
            uid,
            plano_aee_id=plano_aee_id,
            student_id=student_id,
            school_id=school_id,
            academic_year=academic_year,
        )
        accessible_plans = await db.planos_aee.find(
            plan_query,
            {"_id": 0, "id": 1},
        ).to_list(2000)
        accessible_plan_ids = [item.get("id") for item in accessible_plans if item.get("id")]

        filter_query: dict[str, Any] = {
            "plano_aee_id": {"$in": accessible_plan_ids}
        }
        if student_id:
            filter_query["student_id"] = student_id
        if school_id:
            filter_query["school_id"] = school_id
        if academic_year is not None:
            filter_query["academic_year"] = academic_year
        if data_inicio or data_fim:
            filter_query["data"] = {}
            if data_inicio:
                filter_query["data"]["$gte"] = data_inicio
            if data_fim:
                filter_query["data"]["$lte"] = data_fim

        atendimentos = await db.atendimentos_aee.find(
            filter_query,
            {"_id": 0},
        ).sort("data", -1).skip(skip).limit(limit).to_list(limit)

        for atendimento in atendimentos:
            student = await db.students.find_one(
                {"id": atendimento.get("student_id")},
                {"_id": 0, "full_name": 1},
            )
            atendimento["student_name"] = student.get("full_name") if student else "N/A"

        total = await db.atendimentos_aee.count_documents(filter_query)
        return {"items": atendimentos, "total": total}

    @base_router.put("/atendimentos/{atendimento_id}")
    async def p0_update_attendance(
        atendimento_id: str,
        atendimento_update: AtendimentoAEEUpdate,
        request: Request,
    ):
        current_user = await _require_write(request, write_roles)
        existing = await db.atendimentos_aee.find_one(
            {"id": atendimento_id}, {"_id": 0}
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Atendimento não encontrado")

        # Mesma regra dos Planos: edição do registro não reatribui o responsável.
        safe_update = _model_copy(
            atendimento_update,
            professor_aee_id=existing.get("professor_aee_id"),
            professor_aee_nome=existing.get("professor_aee_nome"),
        )
        result = await current_update_attendance(atendimento_id, safe_update, request)
        await db.atendimentos_aee.update_one(
            {"id": atendimento_id}, {"$set": {"updated_by": current_user.get("id")}}
        )
        if isinstance(result, dict):
            result["updated_by"] = current_user.get("id")
        return result

    setattr(base_router, "_aee_v2_p0_installed", True)
    return base_router


def install_aee_professor_turmas(base_router, db):
    """Restaura turmas AEE no endpoint legado consumido pela tela do AEE.

    O AEE continua explicitamente fora do DVD v1. O endpoint geral do professor
    segue retornando suas turmas usuais e recebe, de forma aditiva, apenas turmas
    AEE comprovadas por ``teacher_assignments`` legado ou por Plano AEE já
    autorizado ao próprio professor (fallback para dados históricos saneados de
    forma incompleta).
    """
    if getattr(base_router, "_aee_professor_turmas_installed", False):
        return base_router

    current_get_turmas = _remove_route(base_router, "/professor/turmas", "GET")
    if current_get_turmas is None:
        raise RuntimeError("AEE P0 não pôde proteger GET /professor/turmas")

    @base_router.get("/professor/turmas")
    async def p0_professor_turmas(
        request: Request,
        academic_year: Optional[int] = None,
    ):
        base_items = list(await current_get_turmas(request, academic_year) or [])
        current_user = await AuthMiddleware.get_current_user(request)
        if current_user.get("role") != "professor" or not current_user.get("id"):
            return base_items

        staff = await db.staff.find_one(
            {"user_id": current_user.get("id")},
            {"_id": 0, "id": 1, "email": 1},
        )
        if not staff and current_user.get("email"):
            staff = await db.staff.find_one(
                {"email": current_user.get("email")},
                {"_id": 0, "id": 1, "email": 1},
            )
        if not staff:
            return base_items

        year = academic_year if academic_year is not None else datetime.now().year
        aee_class_ids: set[str] = set()

        # Fonte operacional AEE permanece no vínculo legado, não no DVD.
        legacy_assignments = await db.teacher_assignments.find(
            {
                "staff_id": staff.get("id"),
                "status": {"$in": ["ativo", "active"]},
            },
            {"_id": 0, "class_id": 1, "academic_year": 1},
        ).to_list(1000)
        for assignment in legacy_assignments:
            assignment_year = assignment.get("academic_year")
            if assignment_year is not None and str(assignment_year) != str(year):
                continue
            if assignment.get("class_id"):
                aee_class_ids.add(str(assignment.get("class_id")))

        # Compatibilidade histórica: Planos já visíveis ao professor provam o
        # vínculo pedagógico mesmo quando o teacher_assignment antigo foi
        # desativado/saneado durante a evolução dos vínculos docentes.
        plan_docs = await db.planos_aee.find(
            {
                "$or": [
                    {"professor_aee_id": current_user.get("id")},
                    {"created_by": current_user.get("id")},
                ]
            },
            {"_id": 0, "student_id": 1, "academic_year": 1},
        ).to_list(1000)
        student_ids = {
            item.get("student_id")
            for item in plan_docs
            if item.get("student_id") and str(item.get("academic_year")) == str(year)
        }
        if student_ids:
            students = await db.students.find(
                {"id": {"$in": list(student_ids)}},
                {"_id": 0, "atendimento_programa_class_id": 1},
            ).to_list(1000)
            for student in students:
                if student.get("atendimento_programa_class_id"):
                    aee_class_ids.add(str(student.get("atendimento_programa_class_id")))

        if not aee_class_ids:
            return base_items

        classes = await db.classes.find(
            {"id": {"$in": list(aee_class_ids)}},
            {"_id": 0},
        ).to_list(1000)
        existing_ids = {str(item.get("id")) for item in base_items if item.get("id")}

        for turma in classes:
            if (turma.get("atendimento_programa") or "").strip().lower() != "aee":
                continue
            turma_id = str(turma.get("id") or "")
            if not turma_id or turma_id in existing_ids:
                continue

            school = None
            if turma.get("school_id"):
                school = await db.schools.find_one(
                    {"id": turma.get("school_id")},
                    {"_id": 0, "name": 1},
                )
            turma["school_name"] = school.get("name", "") if school else ""
            turma["componentes"] = []
            base_items.append(turma)
            existing_ids.add(turma_id)

        base_items.sort(
            key=lambda item: (
                (item.get("school_name") or "").casefold(),
                (item.get("name") or "").casefold(),
                str(item.get("id") or ""),
            )
        )
        return base_items

    setattr(base_router, "_aee_professor_turmas_installed", True)
    return base_router


def install_aee_professor_turmas_setup(professor_module):
    """Envolve ``routers.professor.setup_router`` sem alterar o módulo legado."""
    if getattr(professor_module, "_aee_professor_turmas_setup_installed", False):
        return

    original_setup = professor_module.setup_router

    def wrapped_setup(db, audit_service=None, sandbox_db=None, **kwargs):
        configured = original_setup(
            db,
            audit_service=audit_service,
            sandbox_db=sandbox_db,
            **kwargs,
        )
        return install_aee_professor_turmas(configured, db)

    professor_module.setup_router = wrapped_setup
    professor_module._aee_professor_turmas_setup_installed = True


def install_aee_v2_p0_setup(aee_module):
    """Envolve os setups AEE/Professor antes de ``server.py`` importá-los."""
    if getattr(aee_module, "_aee_v2_p0_setup_installed", False):
        return

    original_setup = aee_module.setup_aee_router
    write_roles = tuple(getattr(aee_module, "ROLES_AEE_WRITE", ()))

    def wrapped_setup(db, audit_service):
        configured = original_setup(db, audit_service)
        return install_aee_v2_p0(
            configured,
            db,
            audit_service,
            write_roles=write_roles,
        )

    aee_module.setup_aee_router = wrapped_setup
    aee_module._aee_v2_p0_setup_installed = True

    # Import tardio evita ciclo no carregamento do pacote ``routers``. O módulo
    # Professor continua legado; apenas seu GET /professor/turmas recebe a
    # projeção AEE aditiva necessária à tela do Diário AEE.
    professor_module = importlib.import_module("routers.professor")
    install_aee_professor_turmas_setup(professor_module)
