"""
Tests para router de Student Dependencies (Fase 1).

Cobre:
- Permissões (papéis permitidos vs bloqueados).
- Validação de dependency_mode no aluno.
- Validação de limite de componentes (lendo da mantenedora).
- Validação de duplicidade.
- CRUD básico (create / list / update / delete).
- Summary.
"""
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi import HTTPException


def _make_db(student=None, mantenedora=None, deps=None, count=0):
    """Cria um db mock leve com os métodos usados no router."""
    deps = deps or []
    db = MagicMock()
    db.students = MagicMock()
    db.students.find_one = AsyncMock(return_value=student)
    db.mantenedoras = MagicMock()
    db.mantenedoras.find_one = AsyncMock(return_value=mantenedora)
    # student_dependencies
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=deps)
    db.student_dependencies = MagicMock()
    db.student_dependencies.find = MagicMock(return_value=cursor)
    db.student_dependencies.find_one = AsyncMock(return_value=None)
    db.student_dependencies.count_documents = AsyncMock(return_value=count)
    db.student_dependencies.insert_one = AsyncMock(return_value=None)
    db.student_dependencies.update_one = AsyncMock(return_value=None)
    db.student_dependencies.delete_one = AsyncMock(return_value=None)
    # classes & courses
    classes_cursor = MagicMock()
    classes_cursor.to_list = AsyncMock(return_value=[])
    db.classes = MagicMock()
    db.classes.find = MagicMock(return_value=classes_cursor)
    courses_cursor = MagicMock()
    courses_cursor.to_list = AsyncMock(return_value=[])
    db.courses = MagicMock()
    db.courses.find = MagicMock(return_value=courses_cursor)
    return db


def _make_auth(role="super_admin", mantenedora_id="mant-1"):
    am = MagicMock()
    am.get_current_user = AsyncMock(return_value={
        "id": "u-1", "email": f"{role}@x.com", "role": role,
        "mantenedora_id": mantenedora_id,
    })
    return am


def _get_handler(router, method: str, path_suffix: str):
    for r in router.routes:
        if path_suffix in getattr(r, "path", "") and method in getattr(r, "methods", set()):
            return r.endpoint
    raise AssertionError(f"Rota {method} {path_suffix} não encontrada")


@pytest.mark.asyncio
async def test_create_bloqueia_aluno_sem_dependency_mode():
    from routers.student_dependencies import setup_student_dependencies_router

    db = _make_db(student={"id": "s1", "dependency_mode": "none"})
    auth = _make_auth("super_admin")
    router = setup_student_dependencies_router(db, auth)
    handler = _get_handler(router, "POST", "/student-dependencies")

    from models import StudentDependencyCreate
    payload = StudentDependencyCreate(
        student_id="s1", school_id="sch-1", class_id="cl-1",
        course_id="co-1", academic_year=2026, origin_academic_year=2025,
    )
    with pytest.raises(HTTPException) as exc:
        await handler(request=MagicMock(), payload=payload)
    assert exc.value.status_code == 400
    assert "dependência" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_create_valida_limite_da_mantenedora():
    from routers.student_dependencies import setup_student_dependencies_router

    db = _make_db(
        student={"id": "s1", "dependency_mode": "with_dependency"},
        mantenedora={"aprovacao_com_dependencia": True, "max_componentes_dependencia": 2},
        count=2,  # Já tem 2 ativas, limite é 2 → próxima deve falhar
    )
    auth = _make_auth("admin")
    router = setup_student_dependencies_router(db, auth)
    handler = _get_handler(router, "POST", "/student-dependencies")

    from models import StudentDependencyCreate
    payload = StudentDependencyCreate(
        student_id="s1", school_id="sch-1", class_id="cl-1",
        course_id="co-1", academic_year=2026, origin_academic_year=2025,
    )
    with pytest.raises(HTTPException) as exc:
        await handler(request=MagicMock(), payload=payload)
    assert exc.value.status_code == 400
    assert "excede" in exc.value.detail.lower() or "limite" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_create_bloqueia_duplicidade_componente_ano_origem():
    from routers.student_dependencies import setup_student_dependencies_router

    db = _make_db(
        student={"id": "s1", "dependency_mode": "with_dependency"},
        mantenedora={"aprovacao_com_dependencia": True, "max_componentes_dependencia": 5},
        count=0,
    )
    # Simula dep duplicada
    db.student_dependencies.find_one = AsyncMock(return_value={"id": "existing"})
    auth = _make_auth("secretario")
    router = setup_student_dependencies_router(db, auth)
    handler = _get_handler(router, "POST", "/student-dependencies")

    from models import StudentDependencyCreate
    payload = StudentDependencyCreate(
        student_id="s1", school_id="sch-1", class_id="cl-1",
        course_id="co-1", academic_year=2026, origin_academic_year=2025,
    )
    with pytest.raises(HTTPException) as exc:
        await handler(request=MagicMock(), payload=payload)
    assert exc.value.status_code == 400
    assert "duplic" in exc.value.detail.lower() or "já existe" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_create_sucesso_com_role_permitido():
    from routers.student_dependencies import setup_student_dependencies_router

    db = _make_db(
        student={"id": "s1", "dependency_mode": "with_dependency"},
        mantenedora={"aprovacao_com_dependencia": True, "max_componentes_dependencia": 5},
        count=1,
    )
    auth = _make_auth("diretor")
    router = setup_student_dependencies_router(db, auth)
    handler = _get_handler(router, "POST", "/student-dependencies")

    from models import StudentDependencyCreate
    payload = StudentDependencyCreate(
        student_id="s1", school_id="sch-1", class_id="cl-1",
        course_id="co-1", academic_year=2026, origin_academic_year=2025,
    )
    result = await handler(request=MagicMock(), payload=payload)
    assert result.get("id")
    assert "sucesso" in result.get("message", "").lower()


@pytest.mark.asyncio
async def test_create_bloqueia_role_nao_permitido():
    from routers.student_dependencies import setup_student_dependencies_router
    db = _make_db()
    auth = _make_auth("aluno")
    router = setup_student_dependencies_router(db, auth)
    handler = _get_handler(router, "POST", "/student-dependencies")
    from models import StudentDependencyCreate
    payload = StudentDependencyCreate(
        student_id="s1", school_id="sch-1", class_id="cl-1",
        course_id="co-1", academic_year=2026, origin_academic_year=2025,
    )
    with pytest.raises(HTTPException) as exc:
        await handler(request=MagicMock(), payload=payload)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_summary_retorna_contadores():
    from routers.student_dependencies import setup_student_dependencies_router
    db = _make_db(
        student={"id": "s1", "dependency_mode": "with_dependency"},
        mantenedora={"aprovacao_com_dependencia": True, "max_componentes_dependencia": 3},
        deps=[
            {"status": "active"}, {"status": "active"},
            {"status": "completed"}, {"status": "failed"},
        ],
    )
    auth = _make_auth("secretario")
    router = setup_student_dependencies_router(db, auth)
    handler = _get_handler(router, "GET", "/summary")
    result = await handler(request=MagicMock(), student_id="s1")
    assert result["dependency_mode"] == "with_dependency"
    assert result["limit"] == 3
    assert result["active"] == 2
    assert result["completed"] == 1
    assert result["failed"] == 1
    assert result["total"] == 4


@pytest.mark.asyncio
async def test_create_valida_modo_not_enabled_na_mantenedora():
    """Mesmo com dependency_mode='dependency_only', se a mantenedora não habilitou cursar_apenas_dependencia, falha."""
    from routers.student_dependencies import setup_student_dependencies_router
    db = _make_db(
        student={"id": "s1", "dependency_mode": "dependency_only"},
        mantenedora={"aprovacao_com_dependencia": True, "cursar_apenas_dependencia": False,
                     "max_componentes_dependencia": 3},
        count=0,
    )
    auth = _make_auth("admin")
    router = setup_student_dependencies_router(db, auth)
    handler = _get_handler(router, "POST", "/student-dependencies")
    from models import StudentDependencyCreate
    payload = StudentDependencyCreate(
        student_id="s1", school_id="sch-1", class_id="cl-1",
        course_id="co-1", academic_year=2026, origin_academic_year=2025,
    )
    with pytest.raises(HTTPException) as exc:
        await handler(request=MagicMock(), payload=payload)
    assert exc.value.status_code == 400
