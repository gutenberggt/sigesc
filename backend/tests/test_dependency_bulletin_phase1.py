"""
Testes — Boletim de Dependência (Fase 1, Fev/2026).

Cobre os 3 cenários de `dependency_mode`:
  - "none" → catálogo só com boletim regular.
  - "with_dependency" → catálogo com regular + N boletins de dep (1 por turma).
  - "dependency_only" → catálogo SEM regular; apenas dep.

E o builder `build_student_dependency_bulletin`:
  - Inclui APENAS course_ids das dependências ativas na turma alvo.
  - Frequência só conta para os componentes da dep.
  - Warning quando aluno não tem deps ativas na turma alvo.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.bulletin_builder import (  # noqa: E402
    build_student_dependency_bulletin,
    list_student_bulletins,
)


@pytest_asyncio.fixture
async def db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    yield client[os.environ["DB_NAME"]]
    client.close()


@pytest_asyncio.fixture
async def world(db):
    suf = uuid.uuid4().hex[:8]
    ids = {
        "student": f"depb_stu_{suf}",
        "class_reg": f"depb_cls_reg_{suf}",
        "class_dep_a": f"depb_cls_depA_{suf}",
        "class_dep_b": f"depb_cls_depB_{suf}",
        "school": f"depb_school_{suf}",
        "course_mat": f"depb_course_mat_{suf}",
        "course_pt": f"depb_course_pt_{suf}",
        "course_cie": f"depb_course_cie_{suf}",
        "course_hist": f"depb_course_hist_{suf}",
    }
    await db.schools.insert_one({"id": ids["school"], "name": "Escola Teste DEP"})
    await db.classes.insert_many([
        {"id": ids["class_reg"], "name": "7A REG", "school_id": ids["school"],
         "course_ids": [ids["course_mat"], ids["course_pt"]],
         "academic_year": 2026, "grade_level": "7º ano",
         "nivel_ensino": "fundamental_anos_finais"},
        {"id": ids["class_dep_a"], "name": "8A DEP", "school_id": ids["school"],
         "academic_year": 2026, "grade_level": "8º ano",
         "nivel_ensino": "fundamental_anos_finais"},
        {"id": ids["class_dep_b"], "name": "9A DEP", "school_id": ids["school"],
         "academic_year": 2026, "grade_level": "9º ano",
         "nivel_ensino": "fundamental_anos_finais"},
    ])
    await db.courses.insert_many([
        {"id": ids["course_mat"], "name": "Matemática", "active": True},
        {"id": ids["course_pt"], "name": "Português", "active": True},
        {"id": ids["course_cie"], "name": "Ciências", "active": True},
        {"id": ids["course_hist"], "name": "História", "active": True},
    ])
    yield ids
    # cleanup
    await db.schools.delete_many({"id": ids["school"]})
    await db.classes.delete_many({"id": {"$in": [
        ids["class_reg"], ids["class_dep_a"], ids["class_dep_b"]]}})
    await db.courses.delete_many({"id": {"$regex": f"_{suf}$"}})
    await db.students.delete_many({"id": ids["student"]})
    await db.student_dependencies.delete_many({"student_id": ids["student"]})
    await db.grades.delete_many({"student_id": ids["student"]})


# ---------------- list_student_bulletins ----------------

@pytest.mark.asyncio
async def test_catalog_none_mode_regular_only(db, world):
    await db.students.insert_one({
        "id": world["student"], "full_name": "ALUNO NONE",
        "class_id": world["class_reg"], "school_id": world["school"],
        "dependency_mode": "none",
    })
    items = await list_student_bulletins(db, student_id=world["student"], academic_year=2026)
    assert len(items) == 1
    assert items[0]["type"] == "regular"
    assert items[0]["class_id"] == world["class_reg"]


@pytest.mark.asyncio
async def test_catalog_with_dependency_regular_plus_deps(db, world):
    await db.students.insert_one({
        "id": world["student"], "full_name": "ALUNO COM DEP",
        "class_id": world["class_reg"], "school_id": world["school"],
        "dependency_mode": "with_dependency",
    })
    # Dependências ativas em 2 turmas distintas
    await db.student_dependencies.insert_many([
        {"id": "dep_1", "student_id": world["student"],
         "class_id": world["class_dep_a"], "course_id": world["course_cie"],
         "academic_year": 2026, "status": "active"},
        {"id": "dep_2", "student_id": world["student"],
         "class_id": world["class_dep_b"], "course_id": world["course_hist"],
         "academic_year": 2026, "status": "active"},
    ])
    items = await list_student_bulletins(db, student_id=world["student"], academic_year=2026)
    types = [i["type"] for i in items]
    class_ids = {i["class_id"] for i in items if i["type"] == "dependency"}
    assert types.count("regular") == 1
    assert types.count("dependency") == 2
    assert class_ids == {world["class_dep_a"], world["class_dep_b"]}


@pytest.mark.asyncio
async def test_catalog_dependency_only_excludes_regular(db, world):
    await db.students.insert_one({
        "id": world["student"], "full_name": "ALUNO SO DEP",
        "class_id": world["class_reg"], "school_id": world["school"],
        "dependency_mode": "dependency_only",
    })
    await db.student_dependencies.insert_one({
        "id": "dep_only_1", "student_id": world["student"],
        "class_id": world["class_dep_a"], "course_id": world["course_cie"],
        "academic_year": 2026, "status": "active",
    })
    items = await list_student_bulletins(db, student_id=world["student"], academic_year=2026)
    types = [i["type"] for i in items]
    assert "regular" not in types
    assert types == ["dependency"]


# ---------------- build_student_dependency_bulletin ----------------

@pytest.mark.asyncio
async def test_dependency_bulletin_only_dep_course_ids(db, world):
    await db.students.insert_one({
        "id": world["student"], "full_name": "ALUNO DEP",
        "class_id": world["class_reg"], "school_id": world["school"],
        "dependency_mode": "with_dependency",
    })
    # 2 deps na mesma turma alvo
    await db.student_dependencies.insert_many([
        {"id": "dep_x", "student_id": world["student"],
         "class_id": world["class_dep_a"], "course_id": world["course_cie"],
         "academic_year": 2026, "status": "active"},
        {"id": "dep_y", "student_id": world["student"],
         "class_id": world["class_dep_a"], "course_id": world["course_hist"],
         "academic_year": 2026, "status": "active"},
    ])
    # Outra dep na outra turma — não deve aparecer
    await db.student_dependencies.insert_one({
        "id": "dep_z", "student_id": world["student"],
         "class_id": world["class_dep_b"], "course_id": world["course_mat"],
         "academic_year": 2026, "status": "active",
    })

    bul = await build_student_dependency_bulletin(
        db, student_id=world["student"],
        target_class_id=world["class_dep_a"], academic_year=2026,
    )
    assert bul["bulletin_type"] == "dependency"
    assert bul["target_class_id"] == world["class_dep_a"]
    course_ids = {c["course_id"] for c in bul["composite_segments"][0]["components"]}
    assert course_ids == {world["course_cie"], world["course_hist"]}
    # course_mat (na outra turma de dep) NÃO deve estar aqui
    assert world["course_mat"] not in course_ids


@pytest.mark.asyncio
async def test_dependency_bulletin_warns_when_no_active_deps(db, world):
    await db.students.insert_one({
        "id": world["student"], "full_name": "ALUNO SEM DEP",
        "class_id": world["class_reg"], "school_id": world["school"],
        "dependency_mode": "with_dependency",
    })
    bul = await build_student_dependency_bulletin(
        db, student_id=world["student"],
        target_class_id=world["class_dep_a"], academic_year=2026,
    )
    codes = {w["code"] for w in bul["warnings"]}
    assert "NO_ACTIVE_DEPENDENCIES" in codes
    assert bul["composite_segments"] == []


@pytest.mark.asyncio
async def test_dependency_bulletin_class_not_found(db, world):
    await db.students.insert_one({
        "id": world["student"], "full_name": "ALUNO",
        "class_id": world["class_reg"], "school_id": world["school"],
        "dependency_mode": "with_dependency",
    })
    bul = await build_student_dependency_bulletin(
        db, student_id=world["student"],
        target_class_id="turma_inexistente", academic_year=2026,
    )
    codes = {w["code"] for w in bul["warnings"]}
    assert "DEPENDENCY_CLASS_NOT_FOUND" in codes
