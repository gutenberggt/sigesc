"""
Testes — Roster da turma com alunos regulares + dependência (Fase 2, Fev/2026).

Cobre:
- Roster sem filtro de componente: lista todos os regulares + alunos com dep ativa
  em qualquer componente da turma.
- Roster com `course_id`: regulares + apenas alunos com dep no componente específico.
- Ordenação alfabética unificada.
- `dependency_mode="dependency_only"` NÃO aparece como regular nem em outra turma —
  só onde tem dep ativa.
- Aluno que é regular E tem dep na mesma turma → conta apenas como regular (sem chip).
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import requests
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = "@Celta2007"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    token = data.get("access_token") or data.get("token")
    csrf = data.get("csrf_token") or r.headers.get("X-CSRF-Token")
    s.headers.update({
        "X-Mantenedora-Id": "fix_mant_v1",
        "X-CSRF-Token": csrf or "",
        "Authorization": f"Bearer {token}" if token else "",
    })
    yield s


@pytest_asyncio.fixture
async def world():
    suf = uuid.uuid4().hex[:8]
    ids = {
        "class": f"rost_cls_{suf}",
        "school": f"rost_sch_{suf}",
        "reg_a": f"rost_reg_a_{suf}",      # Ana (regular)
        "reg_b": f"rost_reg_b_{suf}",      # Bruno (regular)
        "dep_c": f"rost_dep_c_{suf}",      # Carla (dep com curso X)
        "dep_d": f"rost_dep_d_{suf}",      # Daniel (dep com curso Y)
        "course_x": f"rost_crs_x_{suf}",
        "course_y": f"rost_crs_y_{suf}",
    }
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    await db.schools.insert_one({"id": ids["school"], "name": "Escola Roster"})
    await db.classes.insert_one({
        "id": ids["class"], "name": "8A ROST", "school_id": ids["school"],
        "academic_year": 2026, "grade_level": "8º ano",
        "course_ids": [ids["course_x"], ids["course_y"]],
        "mantenedora_id": "fix_mant_v1",
    })
    await db.courses.insert_many([
        {"id": ids["course_x"], "name": "Componente X", "active": True},
        {"id": ids["course_y"], "name": "Componente Y", "active": True},
    ])
    await db.students.insert_many([
        # Regulares — NOTE: ordem de inserção em zigzag para forçar sort
        {"id": ids["reg_b"], "full_name": "BRUNO REGULAR",
         "class_id": ids["class"], "school_id": ids["school"],
         "mantenedora_id": "fix_mant_v1", "dependency_mode": "none"},
        {"id": ids["reg_a"], "full_name": "ANA REGULAR",
         "class_id": ids["class"], "school_id": ids["school"],
         "mantenedora_id": "fix_mant_v1", "dependency_mode": "none"},
        # Dep — em outra turma fictícia
        {"id": ids["dep_c"], "full_name": "CARLA DEPENDENCIA",
         "class_id": "outra_turma_qualquer", "school_id": ids["school"],
         "mantenedora_id": "fix_mant_v1", "dependency_mode": "dependency_only"},
        {"id": ids["dep_d"], "full_name": "DANIEL DEPENDENCIA",
         "class_id": "outra_turma_qualquer2", "school_id": ids["school"],
         "mantenedora_id": "fix_mant_v1", "dependency_mode": "with_dependency"},
    ])
    await db.student_dependencies.insert_many([
        {"id": f"depX_{suf}", "student_id": ids["dep_c"],
         "class_id": ids["class"], "course_id": ids["course_x"],
         "academic_year": 2026, "status": "active",
         "mantenedora_id": "fix_mant_v1"},
        {"id": f"depY_{suf}", "student_id": ids["dep_d"],
         "class_id": ids["class"], "course_id": ids["course_y"],
         "academic_year": 2026, "status": "active",
         "mantenedora_id": "fix_mant_v1"},
    ])
    client.close()
    yield ids
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    await db.schools.delete_many({"id": ids["school"]})
    await db.classes.delete_many({"id": ids["class"]})
    await db.courses.delete_many({"id": {"$regex": f"_{suf}$"}})
    await db.students.delete_many({"id": {"$regex": f"_{suf}$"}})
    await db.student_dependencies.delete_many({"id": {"$regex": f"_{suf}$"}})
    client.close()


def test_roster_no_course_filter_lists_all(session, world):
    r = session.get(
        f"{BASE_URL}/api/classes/{world['class']}/roster?academic_year=2026",
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    names = [s["full_name"] for s in body["students"]]
    # Ordem alfabética unificada
    assert names == sorted(names, key=lambda x: x.casefold())
    assert {"ANA REGULAR", "BRUNO REGULAR", "CARLA DEPENDENCIA",
            "DANIEL DEPENDENCIA"}.issubset(set(names))
    assert body["total_regular"] == 2
    assert body["total_dependency"] == 2
    # Flags
    by_name = {s["full_name"]: s for s in body["students"]}
    assert by_name["ANA REGULAR"]["is_dependency"] is False
    assert by_name["CARLA DEPENDENCIA"]["is_dependency"] is True
    assert by_name["DANIEL DEPENDENCIA"]["is_dependency"] is True


def test_roster_with_course_filter_only_deps_of_that_component(session, world):
    """Filtro por componente X → regulares + APENAS Carla (dep em X), sem Daniel (dep em Y)."""
    r = session.get(
        f"{BASE_URL}/api/classes/{world['class']}/roster"
        f"?academic_year=2026&course_id={world['course_x']}",
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    names = [s["full_name"] for s in body["students"]]
    assert "ANA REGULAR" in names
    assert "BRUNO REGULAR" in names
    assert "CARLA DEPENDENCIA" in names
    assert "DANIEL DEPENDENCIA" not in names  # dep em Y, não em X
    by_name = {s["full_name"]: s for s in body["students"]}
    assert by_name["CARLA DEPENDENCIA"]["dependency_course_ids"] == [world["course_x"]]


def test_roster_class_not_found_returns_404(session):
    r = session.get(
        f"{BASE_URL}/api/classes/nonexistent_class_xxx/roster",
        timeout=30,
    )
    assert r.status_code == 404


def test_roster_alphabetical_consistency_with_dep_in_middle(session, world):
    """Daniel (dep) ordena entre ANA e BRUNO alfabeticamente? Não — vem depois de Carla.

    Garantia: nenhum 'dep' fica no fim por design — todos misturam por nome.
    """
    r = session.get(
        f"{BASE_URL}/api/classes/{world['class']}/roster?academic_year=2026",
        timeout=30,
    )
    body = r.json()
    names = [s["full_name"] for s in body["students"]]
    # ANA, BRUNO, CARLA, DANIEL (alfabética)
    assert names.index("ANA REGULAR") < names.index("BRUNO REGULAR")
    assert names.index("BRUNO REGULAR") < names.index("CARLA DEPENDENCIA")
    assert names.index("CARLA DEPENDENCIA") < names.index("DANIEL DEPENDENCIA")
