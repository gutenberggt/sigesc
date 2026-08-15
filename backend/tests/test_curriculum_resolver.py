"""
Testes — Curriculum Resolver (Evidence-First, Fev/2026).

Cobre os 5 cenários canônicos do resolver:
1. Class com matriz curricular explícita + evidência → componentes vindos do class.course_ids,
   anotados com source e evidence_score.
2. Duplicidade por nome com evidência em apenas um → vencedor por higher_evidence,
   warning DUPLICATE_COURSE_NAME emitido, perdedor em dropped_by_dedupe.
3. Turma sem course_ids + sem evidência → fallback por nivel_ensino acionado +
   warning CLASS_WITHOUT_CURRICULUM_MATRIX.
4. Turma sem course_ids COM evidência → fallback NÃO acionado (apenas evidência) +
   warning CLASS_WITHOUT_CURRICULUM_MATRIX.
5. Caso AMANDA: turma sem course_ids + nivel_ensino retornando duas "Ciências",
   apenas a com nota deve aparecer no resultado final.
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

from utils.curriculum_resolver import resolve_curriculum  # noqa: E402


@pytest_asyncio.fixture
async def db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    yield db
    client.close()


@pytest_asyncio.fixture
async def world(db):
    """Mundo isolado por teste."""
    suf = uuid.uuid4().hex[:8]
    ids = {
        "student": f"cr_stu_{suf}",
        "class": f"cr_class_{suf}",
        "school": f"cr_school_{suf}",
        "course_mat": f"cr_course_mat_{suf}",
        "course_pt": f"cr_course_pt_{suf}",
        "course_cie_a": f"cr_course_cie_a_{suf}",
        "course_cie_b": f"cr_course_cie_b_{suf}",
        "course_fallback_a": f"cr_course_fb_a_{suf}",
        "course_fallback_b": f"cr_course_fb_b_{suf}",
    }
    yield ids
    cleanup = [
        (db.students, {"id": ids["student"]}),
        (db.classes, {"id": ids["class"]}),
        (db.schools, {"id": ids["school"]}),
        (db.courses, {"id": {"$regex": f"_{suf}$"}}),
        (db.grades, {"student_id": ids["student"]}),
        (db.attendance, {"class_id": ids["class"]}),
        (db.teacher_assignments, {"class_id": ids["class"]}),
    ]
    for coll, flt in cleanup:
        await coll.delete_many(flt)


async def _seed_basic(db, ids, *, course_ids=None, nivel_ensino="fundamental_anos_finais"):
    await db.schools.insert_one({"id": ids["school"], "name": "Escola Teste CR"})
    await db.classes.insert_one({
        "id": ids["class"], "name": "7 ANO TESTE CR",
        "school_id": ids["school"],
        "course_ids": course_ids if course_ids is not None else [],
        "academic_year": 2026,
        "grade_level": "7º ano",
        "nivel_ensino": nivel_ensino,
        "atendimento_programa": "regular",
    })
    await db.students.insert_one({
        "id": ids["student"], "full_name": "ALUNO TESTE CR",
        "class_id": ids["class"], "school_id": ids["school"],
        "student_series": "7º ano",
    })
    await db.courses.insert_many([
        {"id": ids["course_mat"], "name": "Matemática", "active": True,
         "nivel_ensino": nivel_ensino, "atendimento_programa": "regular"},
        {"id": ids["course_pt"], "name": "Português", "active": True,
         "nivel_ensino": nivel_ensino, "atendimento_programa": "regular"},
    ])


@pytest.mark.asyncio
async def test_evidence_only_with_explicit_matrix(db, world):
    """class.course_ids preenchido + 1 nota → ambos cursos aparecem,
    com 'mat' marcado como evidence (com score) e 'pt' como class (score 0)."""
    await _seed_basic(db, world, course_ids=[world["course_mat"], world["course_pt"]])
    await db.grades.insert_one({
        "student_id": world["student"], "class_id": world["class"],
        "course_id": world["course_mat"], "academic_year": 2026,
        "b1": 8.0,
    })

    r = await resolve_curriculum(
        db, student_id=world["student"], class_id=world["class"], academic_year=2026,
    )
    by_id = {c["course_id"]: c for c in r["components"]}
    assert world["course_mat"] in by_id
    assert world["course_pt"] in by_id
    assert by_id[world["course_mat"]]["source"] == "evidence"
    assert by_id[world["course_mat"]]["evidence_score"] == 1
    assert by_id[world["course_pt"]]["source"] == "class"
    assert by_id[world["course_pt"]]["evidence_score"] == 0
    # Sem warning de matrix ausente
    codes = {w["code"] for w in r["warnings"]}
    assert "CLASS_WITHOUT_CURRICULUM_MATRIX" not in codes


@pytest.mark.asyncio
async def test_duplicate_name_resolved_by_evidence(db, world):
    """Dois cursos 'Ciências' no class.course_ids, só um tem nota → vencedor por
    higher_evidence, warning emitido, perdedor em dropped_by_dedupe."""
    await db.courses.insert_many([
        {"id": world["course_cie_a"], "name": "Ciências", "active": True,
         "nivel_ensino": "fundamental_anos_finais"},
        {"id": world["course_cie_b"], "name": "Ciências", "active": False,
         "nivel_ensino": "fundamental_anos_finais"},
    ])
    await _seed_basic(db, world, course_ids=[world["course_cie_a"], world["course_cie_b"]])
    await db.grades.insert_one({
        "student_id": world["student"], "class_id": world["class"],
        "course_id": world["course_cie_a"], "academic_year": 2026, "b1": 7.0,
    })

    r = await resolve_curriculum(
        db, student_id=world["student"], class_id=world["class"], academic_year=2026,
    )
    ciencias = [c for c in r["components"]
                if (c.get("course_name") or "").casefold() == "ciências"]
    assert len(ciencias) == 1
    assert ciencias[0]["course_id"] == world["course_cie_a"]
    assert ciencias[0]["dedupe_kept_reason"] == "higher_evidence"

    dup = [w for w in r["warnings"] if w["code"] == "DUPLICATE_COURSE_NAME"]
    assert len(dup) == 1
    assert dup[0]["winner_course_id"] == world["course_cie_a"]
    assert dup[0]["resolved_by_evidence"] is True

    dropped = r["debug"]["dropped_by_dedupe"]
    assert any(d["course_id"] == world["course_cie_b"] for d in dropped)


@pytest.mark.asyncio
async def test_class_without_matrix_and_no_evidence_triggers_fallback(db, world):
    """Turma virgem (sem course_ids, sem teacher_assignments, sem evidência) →
    fallback por nivel_ensino + warning CLASS_WITHOUT_CURRICULUM_MATRIX."""
    await _seed_basic(db, world, course_ids=[])

    r = await resolve_curriculum(
        db, student_id=world["student"], class_id=world["class"], academic_year=2026,
    )
    codes = {w["code"] for w in r["warnings"]}
    assert "CLASS_WITHOUT_CURRICULUM_MATRIX" in codes
    fallback_step = next(s for s in r["debug"]["resolution_path"]
                         if s.get("step") == "nivel_ensino_fallback")
    assert fallback_step["activated"] is True
    # Fallback puxou os cursos do nível
    cids = {c["course_id"] for c in r["components"]}
    assert world["course_mat"] in cids
    assert world["course_pt"] in cids
    # Sources
    for c in r["components"]:
        assert c["source"] == "fallback"


@pytest.mark.asyncio
async def test_class_without_matrix_but_with_evidence_skips_fallback(db, world):
    """Sem course_ids MAS com evidência → fallback NÃO acionado."""
    await _seed_basic(db, world, course_ids=[])
    await db.grades.insert_one({
        "student_id": world["student"], "class_id": world["class"],
        "course_id": world["course_mat"], "academic_year": 2026, "b1": 9.0,
    })

    r = await resolve_curriculum(
        db, student_id=world["student"], class_id=world["class"], academic_year=2026,
    )
    fallback_step = next(s for s in r["debug"]["resolution_path"]
                         if s.get("step") == "nivel_ensino_fallback")
    assert fallback_step["activated"] is False
    assert fallback_step["skip_reason"] == "has_academic_evidence"
    # Apenas mat (com evidência) aparece
    cids = {c["course_id"] for c in r["components"]}
    assert cids == {world["course_mat"]}


@pytest.mark.asyncio
async def test_amanda_scenario_no_course_ids_two_ciencias_in_level(db, world):
    """Caso AMANDA: turma sem course_ids, dois cursos 'Ciências' no mesmo nivel_ensino,
    aluno com nota em apenas um. Resolução final deve mostrar APENAS 1 Ciências."""
    # 2 cursos 'Ciências' no mesmo nível — ambos puxados pelo fallback
    await db.courses.insert_many([
        {"id": world["course_cie_a"], "name": "Ciências", "active": True,
         "nivel_ensino": "fundamental_anos_finais"},
        {"id": world["course_cie_b"], "name": "Ciências", "active": True,
         "nivel_ensino": "fundamental_anos_finais"},
    ])
    await _seed_basic(db, world, course_ids=[])
    # Aluna tem nota em UM dos cursos — esse é o canonical
    await db.grades.insert_one({
        "student_id": world["student"], "class_id": world["class"],
        "course_id": world["course_cie_a"], "academic_year": 2026,
        "b1": 8.0, "final_average": 8.0,
    })

    r = await resolve_curriculum(
        db, student_id=world["student"], class_id=world["class"], academic_year=2026,
    )
    # Como há evidência, fallback NÃO é acionado — só aparece o curso com nota
    ciencias = [c for c in r["components"]
                if (c.get("course_name") or "").casefold() == "ciências"]
    assert len(ciencias) == 1, f"Esperado 1 'Ciências', veio {len(ciencias)}: {ciencias}"
    assert ciencias[0]["course_id"] == world["course_cie_a"]
    assert ciencias[0]["source"] == "evidence"
    # NÃO há warning de duplicidade (não houve concorrência: só uma chegou na resolução)
    dup = [w for w in r["warnings"] if w["code"] == "DUPLICATE_COURSE_NAME"]
    assert len(dup) == 0
    # Fallback marcado como skip por evidência
    fb = next(s for s in r["debug"]["resolution_path"]
              if s.get("step") == "nivel_ensino_fallback")
    assert fb["activated"] is False
    assert fb["skip_reason"] == "has_academic_evidence"


@pytest.mark.asyncio
async def test_teacher_assignments_used_when_no_class_course_ids(db, world):
    """class.course_ids vazio + teacher_assignments preenchido → cursos das assignments
    são usados, fallback NÃO acionado."""
    await _seed_basic(db, world, course_ids=[])
    await db.teacher_assignments.insert_one({
        "class_id": world["class"], "course_id": world["course_mat"],
        "status": "active", "teacher_id": "any",
    })

    r = await resolve_curriculum(
        db, student_id=world["student"], class_id=world["class"], academic_year=2026,
    )
    cids = {c["course_id"]: c for c in r["components"]}
    assert world["course_mat"] in cids
    assert cids[world["course_mat"]]["source"] == "teacher_assignment"
    # Fallback não acionado (tem matrix via teacher_assignment)
    fb = next(s for s in r["debug"]["resolution_path"]
              if s.get("step") == "nivel_ensino_fallback")
    assert fb["activated"] is False
    assert fb["skip_reason"] == "has_curriculum_matrix"


@pytest.mark.asyncio
async def test_resolver_is_deterministic(db, world):
    """Mesmo input → mesma saída (pureza)."""
    await _seed_basic(db, world, course_ids=[world["course_mat"], world["course_pt"]])
    r1 = await resolve_curriculum(
        db, student_id=world["student"], class_id=world["class"], academic_year=2026,
    )
    r2 = await resolve_curriculum(
        db, student_id=world["student"], class_id=world["class"], academic_year=2026,
    )
    ids1 = [c["course_id"] for c in r1["components"]]
    ids2 = [c["course_id"] for c in r2["components"]]
    assert ids1 == ids2
