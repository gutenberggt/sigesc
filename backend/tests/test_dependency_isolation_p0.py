"""
Testes P0 — Dependência NÃO contamina cálculo regular.

[Fev/2026] Exigência operacional do owner.

Regra crítica: notas e frequência registradas com `dependency_id != null` são
referentes a dependência de ANO ANTERIOR e jamais devem entrar:
- na média anual da turma (cálculo regular)
- na % de frequência regular
- nos relatórios sintéticos (ranking / aprovação / dashboards)

Estes testes são a última barreira contra regressão.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.grade_dependency_filters import (  # noqa: E402
    is_regular_attendance_record,
    is_regular_grade,
    keep_regular_only,
    regular_only_aggregate_match,
    regular_only_filter,
    with_regular_only,
)
from utils.dependency_enums import (  # noqa: E402
    DEPENDENCY_STATUS_VALUES,
    DEPENDENCY_TYPE_VALUES,
    is_active_status,
    normalize_dependency_status,
    normalize_dependency_type,
    validate_dependency_status,
    validate_dependency_type,
)


@pytest_asyncio.fixture
async def db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    yield client[os.environ["DB_NAME"]]
    client.close()


# =========================================================================
# 1. Filtros Mongo
# =========================================================================
def test_regular_only_filter_shape():
    assert regular_only_filter() == {"dependency_id": {"$in": [None]}}


def test_regular_only_aggregate_match_shape():
    assert regular_only_aggregate_match() == {"dependency_id": {"$in": [None]}}


def test_with_regular_only_does_not_mutate_input():
    base = {"class_id": "X", "academic_year": 2026}
    out = with_regular_only(base)
    assert "dependency_id" not in base
    assert out["dependency_id"] == {"$in": [None]}
    assert out["class_id"] == "X"


# =========================================================================
# 2. Defesa Python — `is_regular_*`
# =========================================================================
def test_is_regular_grade_true_quando_sem_dep_id():
    assert is_regular_grade({"id": "g1", "b1": 7.5}) is True
    assert is_regular_grade({"id": "g1", "dependency_id": None}) is True


def test_is_regular_grade_false_quando_dep_id_presente():
    assert is_regular_grade({"id": "g1", "dependency_id": "dep_x"}) is False


def test_is_regular_grade_false_quando_grade_none():
    assert is_regular_grade(None) is False


def test_is_regular_attendance_record_true_quando_sem_dep_id():
    assert is_regular_attendance_record({"student_id": "s1", "status": "P"}) is True


def test_is_regular_attendance_record_false_quando_dep_id_presente():
    rec = {"student_id": "s1", "status": "P", "dependency_id": "dep_x"}
    assert is_regular_attendance_record(rec) is False


def test_keep_regular_only_filtra_correctamente():
    items = [
        {"id": "g1", "b1": 8},
        {"id": "g2", "b1": 7, "dependency_id": "dep_x"},
        {"id": "g3", "b1": 9, "dependency_id": None},
    ]
    out = keep_regular_only(items)
    assert [it["id"] for it in out] == ["g1", "g3"]


# =========================================================================
# 3. End-to-end: dependência NÃO contamina média regular (Mongo)
# =========================================================================
@pytest.mark.asyncio
async def test_dependency_grade_not_affect_regular_average(db):
    """
    Cenário: turma com 3 alunos regulares (médias 8, 7, 6) + 1 aluno em
    dependência com nota 0. A média da turma deve ser (8+7+6)/3 = 7.0,
    não (8+7+6+0)/4 = 5.25.
    """
    # Cria seeds isolados (idempotentes via prefixo `p0_test_`)
    cid = "p0_test_class_avg"
    coid = "p0_test_course_avg"
    year = 2026

    # Limpa qualquer resíduo
    await db.grades.delete_many({"class_id": cid})

    docs = [
        {"id": "p0_g_a", "student_id": "p0_s_a", "class_id": cid, "course_id": coid,
         "academic_year": year, "b1": 8.0, "dependency_id": None},
        {"id": "p0_g_b", "student_id": "p0_s_b", "class_id": cid, "course_id": coid,
         "academic_year": year, "b1": 7.0, "dependency_id": None},
        {"id": "p0_g_c", "student_id": "p0_s_c", "class_id": cid, "course_id": coid,
         "academic_year": year, "b1": 6.0, "dependency_id": None},
        # Esta nota é DEPENDÊNCIA — NÃO deve entrar na média da turma
        {"id": "p0_g_dep", "student_id": "p0_s_dep", "class_id": cid, "course_id": coid,
         "academic_year": year, "b1": 0.0, "dependency_id": "p0_dep_xyz"},
    ]
    await db.grades.insert_many(docs)

    # Calcula média via aggregate respeitando o filtro híbrido
    pipeline = [
        {"$match": {"class_id": cid, "academic_year": year, **regular_only_aggregate_match()}},
        {"$group": {"_id": None, "avg": {"$avg": "$b1"}, "n": {"$sum": 1}}},
    ]
    result = await db.grades.aggregate(pipeline).to_list(1)
    assert result, "agregação não retornou nada"
    assert result[0]["n"] == 3, f"esperado 3 regulares, veio {result[0]['n']}"
    assert abs(result[0]["avg"] - 7.0) < 0.01, f"média esperada 7.0, veio {result[0]['avg']}"

    # Cleanup
    await db.grades.delete_many({"class_id": cid})


@pytest.mark.asyncio
async def test_dependency_attendance_not_affect_regular_frequency(db):
    """
    Cenário: 4 sessões de aula, aluno regular P/P/F/P (75%) + um record
    duplicado para o mesmo aluno marcado com dependency_id (= F que
    pertence à dependência de outro ano). A frequência regular deve
    ignorar o record com dependency_id e devolver 75% (3/4).
    """
    cid = "p0_test_class_freq"
    sid = "p0_test_student_freq"
    year = 2026

    await db.attendance.delete_many({"class_id": cid})

    # 4 sessões de aula, aluno tem P/P/F/P (regular) e em uma sessão tem ALÉM
    # disso um record com dependency_id = F (relativo à dep do ano anterior).
    sessions = [
        {"id": f"p0_a_{i}", "class_id": cid, "date": f"2026-03-{i:02d}",
         "academic_year": year, "records": records}
        for i, records in [
            (1, [{"student_id": sid, "status": "P"}]),
            (2, [{"student_id": sid, "status": "P"}]),
            (3, [{"student_id": sid, "status": "F"},
                 {"student_id": sid, "status": "F", "dependency_id": "p0_dep_old"}]),
            (4, [{"student_id": sid, "status": "P"}]),
        ]
    ]
    await db.attendance.insert_many(sessions)

    # Replicação simplificada da lógica de cálculo de % com defesa Python.
    total = 0
    present = 0
    cursor = db.attendance.find({"class_id": cid}, {"_id": 0})
    async for att in cursor:
        for rec in att.get("records", []):
            if not is_regular_attendance_record(rec):
                continue  # pula record de dependência
            if rec.get("student_id") != sid:
                continue
            total += 1
            if rec.get("status") == "P":
                present += 1

    pct = round((present / total) * 100, 2) if total else 0
    assert total == 4, f"esperado 4 records regulares, veio {total}"
    assert present == 3
    assert pct == 75.0

    await db.attendance.delete_many({"class_id": cid})


@pytest.mark.asyncio
async def test_dependency_student_not_counted_twice_in_reports(db):
    """
    Cenário: aluno aparece como regular E tem nota com dependency_id. A
    contagem de alunos no relatório deve ser 1, não 2.
    """
    cid = "p0_test_class_nodupe"
    sid = "p0_test_student_dupe"
    year = 2026

    await db.grades.delete_many({"class_id": cid})

    # Mesmo student_id em dois grades: regular + dep
    docs = [
        {"id": "p0_reg", "student_id": sid, "class_id": cid, "course_id": "co_x",
         "academic_year": year, "b1": 7.5, "dependency_id": None},
        {"id": "p0_dep", "student_id": sid, "class_id": cid, "course_id": "co_x",
         "academic_year": year, "b1": 5.0, "dependency_id": "p0_dep_xyz"},
    ]
    await db.grades.insert_many(docs)

    # Distinct de student_id usando filtro regular-only
    student_ids = await db.grades.distinct(
        "student_id", {"class_id": cid, **regular_only_filter()}
    )
    assert len(student_ids) == 1
    assert student_ids == [sid]

    await db.grades.delete_many({"class_id": cid})


# =========================================================================
# 4. Enums centralizados — normalização
# =========================================================================
def test_dependency_status_values_are_canonical():
    assert DEPENDENCY_STATUS_VALUES == ("active", "completed", "failed", "cancelled")


def test_dependency_type_values_are_canonical():
    assert DEPENDENCY_TYPE_VALUES == ("none", "with_dependency", "dependency_only")


@pytest.mark.parametrize("raw,expected", [
    ("active", "active"),
    ("ACTIVE", "active"),
    ("Active", "active"),
    ("ativo", "active"),
    ("Ativa", "active"),
    ("CONCLUÍDO", "completed"),
    ("concluida", "completed"),
    ("reprovado", "failed"),
    ("FAILED", "failed"),
    ("CANCELADA", "cancelled"),
    ("Canceled", "cancelled"),
])
def test_normalize_dependency_status_aliases(raw, expected):
    assert normalize_dependency_status(raw) == expected


def test_normalize_dependency_status_falha_quando_invalido():
    with pytest.raises(ValueError):
        normalize_dependency_status("alguma_coisa_invalida")


def test_normalize_dependency_status_none_returns_none():
    assert normalize_dependency_status(None) is None
    assert normalize_dependency_status("") is None


@pytest.mark.parametrize("raw,expected", [
    ("with_dependency", "with_dependency"),
    ("with-dependency", "with_dependency"),
    ("withDependency", "with_dependency"),
    ("Com_Dependencia", "with_dependency"),
    ("dependency_only", "dependency_only"),
    ("dependency-only", "dependency_only"),
    ("dependencyOnly", "dependency_only"),
    ("apenas_dependencia", "dependency_only"),
    ("none", "none"),
    ("nenhum", "none"),
])
def test_normalize_dependency_type_aliases(raw, expected):
    assert normalize_dependency_type(raw) == expected


def test_validate_dependency_status_obrigatorio():
    with pytest.raises(ValueError):
        validate_dependency_status(None)
    assert validate_dependency_status("active") == "active"


def test_validate_dependency_type_obrigatorio():
    with pytest.raises(ValueError):
        validate_dependency_type(None)
    assert validate_dependency_type("none") == "none"


def test_is_active_status_helper():
    assert is_active_status("active") is True
    assert is_active_status("ATIVO") is True
    assert is_active_status("completed") is False
    assert is_active_status("garbage") is False
    assert is_active_status(None) is False
