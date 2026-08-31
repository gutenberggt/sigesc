"""P0 AEE — escopo fail-closed de Turma AEE para o perfil Professor.

Autorizado explicitamente pelo proprietário do produto em 31/08/2026 após
homologação do hotfix #292 revelar exposição cruzada da listagem de estudantes
entre professoras AEE da mesma escola.

Objetivos desta camada:
- resolver as Turmas AEE autorizadas a partir do vínculo docente legado e da
  identidade histórica user.id <-> staff.id, sem incluir o AEE no DVD v1;
- projetar essas turmas em ``GET /professor/turmas`` para que o seletor da tela
  do Diário AEE permaneça disponível ao professor;
- filtrar ``GET /aee/estudantes`` no backend pela Turma AEE autorizada;
- falhar fechado: professor sem Turma AEE resolvida recebe lista vazia, nunca a
  lista global de estudantes AEE da escola;
- não migrar, reescrever ou fazer backfill de qualquer documento histórico.
"""

from __future__ import annotations

from datetime import datetime
import importlib
from typing import Any, Optional

from fastapi import HTTPException, Request

from auth_middleware import AuthMiddleware


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


def _same_academic_year(value: Any, expected: int) -> bool:
    """Aceita int/string; ``None`` só é tolerado no vínculo AEE legado."""
    if value is None:
        return True
    return str(value) == str(expected)


async def _resolve_professor_staff(db, current_user: dict) -> Optional[dict]:
    uid = current_user.get("id")
    if uid:
        staff = await db.staff.find_one(
            {"user_id": uid},
            {"_id": 0, "id": 1, "email": 1, "user_id": 1},
        )
        if staff:
            return staff

    email = current_user.get("email")
    if email:
        return await db.staff.find_one(
            {"email": email},
            {"_id": 0, "id": 1, "email": 1, "user_id": 1},
        )
    return None


async def resolve_professor_aee_class_ids(
    db,
    current_user: dict,
    *,
    academic_year: Optional[int] = None,
    school_id: Optional[str] = None,
) -> set[str]:
    """Resolve apenas Turmas AEE comprovadamente pertencentes ao professor.

    Fontes aceitas, em ordem aditiva:
    1. ``teacher_assignments`` ativo do ``staff.id`` ligado ao usuário;
    2. Plano AEE histórico do próprio professor, aceitando ``professor_aee_id``
       tanto como ``user.id`` quanto como o antigo ``staff.id``; ``created_by``
       continua como compatibilidade já existente no AEE.

    Todo candidato é validado contra ``classes.atendimento_programa == 'aee'``
    e, quando informado, contra a escola selecionada. Assim um vínculo regular
    nunca é promovido a AEE apenas por compartilhar professor/ano.
    """
    if current_user.get("role") != "professor" or not current_user.get("id"):
        return set()

    year = academic_year if academic_year is not None else datetime.now().year
    uid = str(current_user.get("id"))
    staff = await _resolve_professor_staff(db, current_user)

    professor_identity_ids = {uid}
    if staff and staff.get("id"):
        professor_identity_ids.add(str(staff.get("id")))

    candidate_class_ids: set[str] = set()

    if staff and staff.get("id"):
        assignments = await db.teacher_assignments.find(
            {
                "staff_id": staff.get("id"),
                "status": {"$in": ["ativo", "active"]},
            },
            {"_id": 0, "class_id": 1, "academic_year": 1},
        ).to_list(1000)
        for assignment in assignments:
            if not _same_academic_year(assignment.get("academic_year"), year):
                continue
            class_id = assignment.get("class_id")
            if class_id:
                candidate_class_ids.add(str(class_id))

    plan_query: dict[str, Any] = {
        "$or": [
            {"professor_aee_id": {"$in": list(professor_identity_ids)}},
            {"created_by": uid},
        ]
    }
    if school_id:
        plan_query["school_id"] = school_id

    plan_docs = await db.planos_aee.find(
        plan_query,
        {"_id": 0, "student_id": 1, "academic_year": 1},
    ).to_list(2000)
    student_ids = {
        item.get("student_id")
        for item in plan_docs
        if (
            item.get("student_id")
            and item.get("academic_year") is not None
            and str(item.get("academic_year")) == str(year)
        )
    }
    if student_ids:
        students = await db.students.find(
            {"id": {"$in": list(student_ids)}},
            {"_id": 0, "atendimento_programa_class_id": 1},
        ).to_list(2000)
        for student in students:
            class_id = student.get("atendimento_programa_class_id")
            if class_id:
                candidate_class_ids.add(str(class_id))

    if not candidate_class_ids:
        return set()

    classes = await db.classes.find(
        {"id": {"$in": list(candidate_class_ids)}},
        {"_id": 0, "id": 1, "school_id": 1, "atendimento_programa": 1},
    ).to_list(2000)

    allowed: set[str] = set()
    for turma in classes:
        if (turma.get("atendimento_programa") or "").strip().lower() != "aee":
            continue
        if school_id and str(turma.get("school_id") or "") != str(school_id):
            continue
        turma_id = turma.get("id")
        if turma_id:
            allowed.add(str(turma_id))
    return allowed


def filter_professor_aee_students(
    items: list[dict],
    allowed_class_ids: set[str],
) -> list[dict]:
    """Aplica o escopo de Turma AEE à projeção de estudantes.

    ``atendimento_programa_class_id`` é a fonte preferencial. ``class_id`` só é
    fallback para registros realmente antigos que ainda não possuem o campo AEE.
    Quando o campo AEE existe e aponta para outra turma, ``class_id`` não pode
    reabrir acesso por coincidência com a turma de origem.
    """
    if not allowed_class_ids:
        return []

    allowed = {str(value) for value in allowed_class_ids if value}
    filtered: list[dict] = []
    for item in items or []:
        aee_class_id = item.get("atendimento_programa_class_id")
        if aee_class_id:
            if str(aee_class_id) in allowed:
                filtered.append(item)
            continue
        legacy_class_id = item.get("class_id")
        if legacy_class_id and str(legacy_class_id) in allowed:
            filtered.append(item)
    return filtered


async def _build_professor_turmas_projection(
    db,
    current_user: dict,
    *,
    academic_year: Optional[int] = None,
) -> list[dict]:
    """Replica a projeção legado e acrescenta apenas AEE autorizado.

    Para turmas regulares preserva-se o status legado ``ativo`` e o ano exato
    já exigido por ``/professor/turmas``. O alias ``active`` e ano ausente só
    são tolerados para AEE. Alocações AEE sem ``course_id`` não derrubam mais o
    endpoint: a turma continua válida e não recebe componente artificial.
    """
    year = academic_year if academic_year is not None else datetime.now().year
    staff = await _resolve_professor_staff(db, current_user)
    allowed_aee_ids = await resolve_professor_aee_class_ids(
        db,
        current_user,
        academic_year=year,
    )

    assignments: list[dict] = []
    if staff and staff.get("id"):
        assignments = await db.teacher_assignments.find(
            {
                "staff_id": staff.get("id"),
                "status": {"$in": ["ativo", "active"]},
            },
            {"_id": 0},
        ).to_list(2000)

    turmas_dict: dict[str, dict] = {}
    for assignment in assignments:
        assignment_year = assignment.get("academic_year")
        if not _same_academic_year(assignment_year, year):
            continue
        class_id = assignment.get("class_id")
        if not class_id:
            continue
        class_id = str(class_id)
        turma = await db.classes.find_one({"id": class_id}, {"_id": 0})
        if not turma:
            continue

        is_aee = (turma.get("atendimento_programa") or "").strip().lower() == "aee"
        if is_aee:
            if class_id not in allowed_aee_ids:
                continue
        else:
            # Preserva exatamente o contrato legado para turma regular: status
            # "ativo" e academic_year int igual ao ano solicitado.
            if assignment.get("status") != "ativo" or assignment_year != year:
                continue

        if class_id not in turmas_dict:
            school = None
            if turma.get("school_id"):
                school = await db.schools.find_one(
                    {"id": turma.get("school_id")},
                    {"_id": 0, "name": 1},
                )
            turma = dict(turma)
            turma["school_name"] = school.get("name", "") if school else ""
            turma["componentes"] = []
            turmas_dict[class_id] = turma

        course_id = assignment.get("course_id")
        if not course_id:
            continue
        course = await db.courses.find_one({"id": course_id}, {"_id": 0})
        if course:
            turmas_dict[class_id]["componentes"].append(
                {
                    "id": course.get("id"),
                    "name": course.get("name"),
                    "workload": course.get("workload"),
                    "assignment_id": assignment.get("id"),
                }
            )

    # Fallback histórico: um Plano AEE autorizado pode comprovar a turma mesmo
    # quando o teacher_assignment foi saneado/desativado. Somente classes AEE
    # validadas pelo resolver entram aqui.
    missing_aee_ids = allowed_aee_ids.difference(turmas_dict.keys())
    if missing_aee_ids:
        classes = await db.classes.find(
            {"id": {"$in": list(missing_aee_ids)}},
            {"_id": 0},
        ).to_list(1000)
        for turma in classes:
            turma_id = str(turma.get("id") or "")
            if not turma_id or turma_id not in allowed_aee_ids:
                continue
            if (turma.get("atendimento_programa") or "").strip().lower() != "aee":
                continue
            school = None
            if turma.get("school_id"):
                school = await db.schools.find_one(
                    {"id": turma.get("school_id")},
                    {"_id": 0, "name": 1},
                )
            item = dict(turma)
            item["school_name"] = school.get("name", "") if school else ""
            item["componentes"] = []
            turmas_dict[turma_id] = item

    if not staff and not turmas_dict:
        raise HTTPException(status_code=404, detail="Perfil de professor não encontrado")

    return sorted(
        turmas_dict.values(),
        key=lambda item: (
            (item.get("school_name") or "").casefold(),
            (item.get("name") or "").casefold(),
            str(item.get("id") or ""),
        ),
    )


def install_aee_professor_student_scope(base_router, db):
    """Fecha GET /aee/estudantes pela Turma AEE do professor."""
    if getattr(base_router, "_aee_professor_student_scope_installed", False):
        return base_router

    current_list_students = _remove_route(base_router, "/aee/estudantes", "GET")
    if current_list_students is None:
        raise RuntimeError("AEE P0 não pôde proteger GET /aee/estudantes")

    @base_router.get("/estudantes")
    async def p0_list_estudantes_aee(
        request: Request,
        school_id: str,
        academic_year: int,
    ):
        current_user = await AuthMiddleware.get_current_user(request)
        if current_user.get("role") != "professor":
            return await current_list_students(
                request=request,
                school_id=school_id,
                academic_year=academic_year,
            )

        allowed_class_ids = await resolve_professor_aee_class_ids(
            db,
            current_user,
            academic_year=academic_year,
            school_id=school_id,
        )
        if not allowed_class_ids:
            return []

        items = await current_list_students(
            request=request,
            school_id=school_id,
            academic_year=academic_year,
        )
        return filter_professor_aee_students(items or [], allowed_class_ids)

    setattr(base_router, "_aee_professor_student_scope_installed", True)
    return base_router


def install_aee_professor_turma_scope(base_router, db):
    """Torna /professor/turmas tolerante ao legado AEE e fail-closed."""
    if getattr(base_router, "_aee_professor_turma_scope_installed", False):
        return base_router

    current_get_turmas = _remove_route(base_router, "/professor/turmas", "GET")
    if current_get_turmas is None:
        raise RuntimeError("AEE P0 não pôde proteger GET /professor/turmas")

    @base_router.get("/professor/turmas")
    async def p0_professor_turmas(
        request: Request,
        academic_year: Optional[int] = None,
    ):
        current_user = await AuthMiddleware.get_current_user(request)
        if current_user.get("role") != "professor":
            return await current_get_turmas(request, academic_year)
        return await _build_professor_turmas_projection(
            db,
            current_user,
            academic_year=academic_year,
        )

    setattr(base_router, "_aee_professor_turma_scope_installed", True)
    return base_router


def install_aee_professor_scope_setup(aee_module):
    """Envolve os setups AEE/Professor após as salvaguardas P0 existentes."""
    if getattr(aee_module, "_aee_professor_scope_setup_installed", False):
        return

    original_aee_setup = aee_module.setup_aee_router

    def wrapped_aee_setup(db, audit_service):
        configured = original_aee_setup(db, audit_service)
        return install_aee_professor_student_scope(configured, db)

    aee_module.setup_aee_router = wrapped_aee_setup
    aee_module._aee_professor_scope_setup_installed = True

    professor_module = importlib.import_module("routers.professor")
    if getattr(professor_module, "_aee_professor_scope_setup_installed", False):
        return

    original_professor_setup = professor_module.setup_router

    def wrapped_professor_setup(db, audit_service=None, sandbox_db=None, **kwargs):
        configured = original_professor_setup(
            db,
            audit_service=audit_service,
            sandbox_db=sandbox_db,
            **kwargs,
        )
        return install_aee_professor_turma_scope(configured, db)

    professor_module.setup_router = wrapped_professor_setup
    professor_module._aee_professor_scope_setup_installed = True
