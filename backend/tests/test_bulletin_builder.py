"""
Testes — Bulletin Builder (Boletim Online MVP — Passo 5).

Cobre:
- Aluno sem evento → 1 segmento sole com componentes da turma.
- Aluno com 1 transferência → 2 segmentos com notas filtradas por class_id.
- Bimestres atribuídos por período corretamente.
- Notas de dependência aparecem em lista paralela (não contaminam regular).
- Aluno inexistente → STUDENT_NOT_FOUND warning.
- Read-only puro: builder não mutatestate.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.bulletin_builder import build_student_bulletin  # noqa: E402

STUDENT = "bb_stu_v1"
MANT = "bb_mant_v1"
YEAR = 2026
CLASS_A = "bb_class_A"
CLASS_B = "bb_class_B"
COURSE_MAT = "bb_course_mat"
COURSE_PT = "bb_course_pt"
SCHOOL_ID = "bb_school_v1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest_asyncio.fixture
async def db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    yield db
    client.close()


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(db):
    cleanup_filters = [
        (db.students, {"id": STUDENT}),
        (db.enrollments, {"student_id": STUDENT}),
        (db.classes, {"id": {"$in": [CLASS_A, CLASS_B]}}),
        (db.courses, {"id": {"$in": [COURSE_MAT, COURSE_PT]}}),
        (db.schools, {"id": SCHOOL_ID}),
        (db.grades, {"student_id": STUDENT}),
        (db.attendance, {"class_id": {"$in": [CLASS_A, CLASS_B]}}),
        (db.calendario_letivo, {"ano_letivo": YEAR, "_test_marker": "bb"}),
        (db.academic_events, {"student_id": STUDENT}),
    ]
    for coll, flt in cleanup_filters:
        await coll.delete_many(flt)
    yield
    for coll, flt in cleanup_filters:
        await coll.delete_many(flt)


async def _seed_world(db, *, with_event: bool = False):
    """Seed mínimo: aluno, turmas, escola, cursos, calendário, enrollment."""
    await db.schools.insert_one({"id": SCHOOL_ID, "name": "Escola Teste BB",
                                 "mantenedora_id": MANT})
    await db.students.insert_one({
        "id": STUDENT, "full_name": "Aluno Boletim Teste",
        "registration_number": "BB-001",
        "class_id": CLASS_A, "school_id": SCHOOL_ID,
        "mantenedora_id": MANT, "dependency_mode": "none",
    })
    await db.classes.insert_many([
        {"id": CLASS_A, "name": "Turma 5A", "school_id": SCHOOL_ID,
         "grade_level": "5º Ano", "course_ids": [COURSE_MAT, COURSE_PT],
         "mantenedora_id": MANT, "academic_year": YEAR},
        {"id": CLASS_B, "name": "Turma 5B", "school_id": SCHOOL_ID,
         "grade_level": "5º Ano", "course_ids": [COURSE_MAT, COURSE_PT],
         "mantenedora_id": MANT, "academic_year": YEAR},
    ])
    await db.courses.insert_many([
        {"id": COURSE_MAT, "name": "Matemática", "mantenedora_id": MANT},
        {"id": COURSE_PT, "name": "Português", "mantenedora_id": MANT},
    ])
    await db.enrollments.insert_one({
        "id": f"enr_{STUDENT}",
        "student_id": STUDENT, "class_id": CLASS_A, "academic_year": YEAR,
        "status": "active", "mantenedora_id": MANT, "school_id": SCHOOL_ID,
        "created_at": _now_iso(),
    })
    await db.calendario_letivo.insert_one({
        "ano_letivo": YEAR,
        "_test_marker": "bb",
        "bimestre_1_inicio": "2026-02-01", "bimestre_1_fim": "2026-04-30",
        "bimestre_2_inicio": "2026-05-01", "bimestre_2_fim": "2026-07-15",
        "bimestre_3_inicio": "2026-08-01", "bimestre_3_fim": "2026-10-15",
        "bimestre_4_inicio": "2026-10-16", "bimestre_4_fim": "2026-12-15",
    })
    if with_event:
        await db.academic_events.insert_one({
            "id": "ev_bb_transfer",
            "event_type": "transfer",
            "effective_date": "2026-08-15",
            "student_id": STUDENT,
            "origin_class_id": CLASS_A,
            "destination_class_id": CLASS_B,
            "origin_school_id": SCHOOL_ID,
            "destination_school_id": SCHOOL_ID,
            "mantenedora_id": MANT, "academic_year": YEAR,
            "rationale": "Cenário de teste — boletim com fechamento composto.",
            "approval_required": True,
            "approval_status": "approved",
            "approved_by_user_id": "u",
            "approved_at": _now_iso(),
            "supersedes_event_id": None, "superseded_by_event_id": None,
            "created_by_user_id": "u", "created_at": _now_iso(),
            "audit_trail": [],
        })


# ===========================================================================
@pytest.mark.asyncio
async def test_no_event_returns_single_segment_with_courses(db):
    await _seed_world(db, with_event=False)
    # 1 nota regular em CLASS_A, COURSE_MAT
    await db.grades.insert_one({
        "id": "g_v1", "student_id": STUDENT, "academic_year": YEAR,
        "class_id": CLASS_A, "course_id": COURSE_MAT,
        "b1": 8.0, "b2": 7.5, "b3": 9.0, "b4": 8.5,
        "final_average": 8.3, "status": "aprovado",
        "mantenedora_id": MANT,
    })

    bul = await build_student_bulletin(
        db, student_id=STUDENT, academic_year=YEAR, mantenedora_id=MANT
    )
    assert bul["bulletin_version"] == "1"
    assert bul["is_composite"] is False
    assert len(bul["composite_segments"]) == 1
    seg = bul["composite_segments"][0]
    assert seg["class"]["id"] == CLASS_A
    assert seg["source"] == "sole"
    # 2 cursos + nota presente em MAT
    course_ids = {c["course_id"] for c in seg["components"]}
    assert COURSE_MAT in course_ids and COURSE_PT in course_ids
    mat = next(c for c in seg["components"] if c["course_id"] == COURSE_MAT)
    assert mat["grades"]["b1"] == 8.0
    assert mat["grades"]["final_average"] == 8.3
    pt = next(c for c in seg["components"] if c["course_id"] == COURSE_PT)
    assert pt["grades"]["b1"] is None  # sem nota → null


@pytest.mark.asyncio
async def test_with_transfer_creates_two_segments_with_correct_grades(db):
    await _seed_world(db, with_event=True)
    # Nota em CLASS_A (origem)
    await db.grades.insert_one({
        "id": "g_a", "student_id": STUDENT, "academic_year": YEAR,
        "class_id": CLASS_A, "course_id": COURSE_MAT,
        "b1": 7.0, "b2": 8.0, "mantenedora_id": MANT,
    })
    # Nota em CLASS_B (destino)
    await db.grades.insert_one({
        "id": "g_b", "student_id": STUDENT, "academic_year": YEAR,
        "class_id": CLASS_B, "course_id": COURSE_MAT,
        "b3": 9.0, "b4": 9.5, "mantenedora_id": MANT,
    })

    bul = await build_student_bulletin(
        db, student_id=STUDENT, academic_year=YEAR, mantenedora_id=MANT
    )
    assert bul["is_composite"] is True
    assert len(bul["composite_segments"]) == 2
    seg_a, seg_b = bul["composite_segments"]
    assert seg_a["class"]["id"] == CLASS_A
    assert seg_a["source"] == "origin"
    assert seg_b["class"]["id"] == CLASS_B
    assert seg_b["source"] == "destination"

    # Nota de CLASS_A só aparece no segmento de CLASS_A
    mat_a = next(c for c in seg_a["components"] if c["course_id"] == COURSE_MAT)
    assert mat_a["grades"]["b1"] == 7.0
    assert mat_a["grades"]["b3"] is None  # nota de B está em outro segmento

    mat_b = next(c for c in seg_b["components"] if c["course_id"] == COURSE_MAT)
    assert mat_b["grades"]["b1"] is None
    assert mat_b["grades"]["b3"] == 9.0
    assert mat_b["grades"]["b4"] == 9.5


@pytest.mark.asyncio
async def test_bimesters_owned_correctly_assigned(db):
    await _seed_world(db, with_event=True)
    bul = await build_student_bulletin(
        db, student_id=STUDENT, academic_year=YEAR, mantenedora_id=MANT
    )
    seg_a, seg_b = bul["composite_segments"]
    # Transferência em 08/15: B1 (fim 04/30) e B2 (fim 07/15) → CLASS_A
    # B3 (fim 10/15) e B4 (fim 12/15) → CLASS_B
    assert seg_a["bimesters_owned"] == [1, 2]
    assert seg_b["bimesters_owned"] == [3, 4]


@pytest.mark.asyncio
async def test_dependency_grades_listed_separately(db):
    await _seed_world(db, with_event=False)
    # Nota REGULAR
    await db.grades.insert_one({
        "id": "g_reg", "student_id": STUDENT, "academic_year": YEAR,
        "class_id": CLASS_A, "course_id": COURSE_MAT,
        "b1": 8.0, "mantenedora_id": MANT,
    })
    # Nota de DEPENDÊNCIA (mesmo aluno, mesmo curso, com dependency_id)
    await db.grades.insert_one({
        "id": "g_dep", "student_id": STUDENT, "academic_year": YEAR,
        "class_id": CLASS_A, "course_id": COURSE_PT,
        "b1": 6.0, "b2": 7.0,
        "dependency_id": "dep_v1",
        "mantenedora_id": MANT,
    })

    bul = await build_student_bulletin(
        db, student_id=STUDENT, academic_year=YEAR, mantenedora_id=MANT
    )
    seg = bul["composite_segments"][0]
    # PT no regular NÃO deve ter nota (porque a única é dep)
    pt = next(c for c in seg["components"] if c["course_id"] == COURSE_PT)
    assert pt["grades"]["b1"] is None
    assert pt["is_dependency"] is False  # ainda mostra a casca como component regular

    # Lista paralela de dependência preenchida
    assert len(bul["dependency_components"]) == 1
    dep = bul["dependency_components"][0]
    assert dep["course_id"] == COURSE_PT
    assert dep["is_dependency"] is True
    assert dep["dependency_id"] == "dep_v1"
    assert dep["grades"]["b1"] == 6.0


@pytest.mark.asyncio
async def test_unknown_student_returns_warning_shape(db):
    bul = await build_student_bulletin(
        db, student_id="never_existed", academic_year=YEAR, mantenedora_id=MANT
    )
    assert bul["student"] is None
    assert any(w["code"] == "STUDENT_NOT_FOUND" for w in bul["warnings"])
    assert bul["composite_segments"] == []


@pytest.mark.asyncio
async def test_attendance_summary_filters_dependency(db):
    await _seed_world(db, with_event=False)
    # Attendance regular
    await db.attendance.insert_one({
        "id": "att_1",
        "class_id": CLASS_A, "course_id": COURSE_MAT,
        "date": "2026-03-15",
        "records": [
            {"student_id": STUDENT, "status": "presente"},
            {"student_id": STUDENT, "status": "falta"},
        ],
        "mantenedora_id": MANT,
    })
    # Attendance de dependência (deve ser ignorada)
    await db.attendance.insert_one({
        "id": "att_dep",
        "class_id": CLASS_A, "course_id": COURSE_PT,
        "date": "2026-03-16",
        "records": [
            {"student_id": STUDENT, "status": "falta", "dependency_id": "dep_v1"},
        ],
        "mantenedora_id": MANT,
    })

    bul = await build_student_bulletin(
        db, student_id=STUDENT, academic_year=YEAR, mantenedora_id=MANT
    )
    summary = bul["composite_segments"][0]["attendance_summary"]
    assert summary["total_records"] == 2  # apenas regulares
    assert summary["present"] == 1
    assert summary["absent"] == 1
    assert summary["frequencia_pct"] == 50.0


@pytest.mark.asyncio
async def test_canonical_shape_keys_present(db):
    await _seed_world(db, with_event=False)
    bul = await build_student_bulletin(
        db, student_id=STUDENT, academic_year=YEAR, mantenedora_id=MANT
    )
    for k in ["bulletin_version", "student", "academic_year", "primary_school",
              "primary_class", "is_composite", "composite_segments",
              "dependency_components", "warnings"]:
        assert k in bul


@pytest.mark.asyncio
async def test_duplicate_course_name_dedupe_by_evidence(db):
    """Dois cursos distintos com mesmo nome ('Ciências') na mesma turma:
    o resolver evidence-first mantém APENAS o vencedor (curso com evidência)
    e emite warning DUPLICATE_COURSE_NAME. Boletim deixa de mostrar duas linhas.
    """
    COURSE_CIE_A = "bb_course_cie_a"
    COURSE_CIE_B = "bb_course_cie_b_ghost"

    await _seed_world(db, with_event=False)
    await db.courses.insert_many([
        {"id": COURSE_CIE_A, "name": "Ciências", "active": True, "mantenedora_id": MANT},
        {"id": COURSE_CIE_B, "name": "Ciências", "active": False, "mantenedora_id": MANT},
    ])
    await db.classes.update_one(
        {"id": CLASS_A},
        {"$set": {"course_ids": [COURSE_MAT, COURSE_PT, COURSE_CIE_A, COURSE_CIE_B]}},
    )
    # Apenas o "ativo" tem nota lançada (evidência acadêmica)
    await db.grades.insert_one({
        "id": "g_cie_a", "student_id": STUDENT, "academic_year": YEAR,
        "class_id": CLASS_A, "course_id": COURSE_CIE_A,
        "b1": 8.0, "final_average": 8.0, "mantenedora_id": MANT,
    })

    try:
        bul = await build_student_bulletin(
            db, student_id=STUDENT, academic_year=YEAR, mantenedora_id=MANT
        )
        seg = bul["composite_segments"][0]
        cie_components = [c for c in seg["components"]
                          if (c.get("course_name") or "").casefold() == "ciências"]
        # Dedupe evidence-first: APENAS o vencedor permanece
        assert len(cie_components) == 1, "Resolver deve manter apenas o vencedor"
        winner = cie_components[0]
        assert winner["course_id"] == COURSE_CIE_A, "Curso com evidência vence"
        assert winner["resolution_dedupe_reason"] == "higher_evidence"
        assert winner["resolution_evidence_score"] == 1
        # O fantasma foi descartado, mas o warning é emitido
        dup_warnings = [w for w in bul["warnings"]
                        if w.get("code") == "DUPLICATE_COURSE_NAME"]
        assert len(dup_warnings) == 1
        w = dup_warnings[0]
        assert w["course_name"] == "Ciências"
        assert w["class_id"] == CLASS_A
        assert set(w["course_ids"]) == {COURSE_CIE_A, COURSE_CIE_B}
        assert w["winner_course_id"] == COURSE_CIE_A
        assert w["resolved_by_evidence"] is True

        # debug do resolver expõe o descartado
        debug = seg["resolution_debug"]
        dropped_ids = {d["course_id"] for d in debug["dropped_by_dedupe"]}
        assert COURSE_CIE_B in dropped_ids
    finally:
        await db.courses.delete_many({"id": {"$in": [COURSE_CIE_A, COURSE_CIE_B]}})
        await db.grades.delete_many({"id": "g_cie_a"})


@pytest.mark.asyncio
async def test_class_without_curriculum_matrix_warning(db):
    """Turma sem `course_ids` deve emitir warning CLASS_WITHOUT_CURRICULUM_MATRIX."""
    await _seed_world(db, with_event=False)
    # Remove a matriz curricular da turma
    await db.classes.update_one({"id": CLASS_A}, {"$set": {"course_ids": []}})
    # Adiciona uma nota para ter evidência (assim o fallback amplo NÃO é acionado)
    await db.grades.insert_one({
        "id": "g_ev", "student_id": STUDENT, "academic_year": YEAR,
        "class_id": CLASS_A, "course_id": COURSE_MAT,
        "b1": 7.0, "mantenedora_id": MANT,
    })
    try:
        bul = await build_student_bulletin(
            db, student_id=STUDENT, academic_year=YEAR, mantenedora_id=MANT
        )
        codes = {w.get("code") for w in bul["warnings"]}
        assert "CLASS_WITHOUT_CURRICULUM_MATRIX" in codes
        # Sem matriz e com evidência → resolver inclui só o curso com nota
        seg = bul["composite_segments"][0]
        cids = {c["course_id"] for c in seg["components"]}
        assert COURSE_MAT in cids
        # Confirma resolution_path tem fallback DESLIGADO (tem evidência)
        debug = seg["resolution_debug"]
        fallback_step = next(s for s in debug["resolution_path"]
                             if s.get("step") == "nivel_ensino_fallback")
        assert fallback_step["activated"] is False
        assert fallback_step["skip_reason"] == "has_academic_evidence"
    finally:
        await db.grades.delete_many({"id": "g_ev"})
