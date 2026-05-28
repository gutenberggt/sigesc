"""
[Fev/2026 — Spec owner Bolsa Família] Testes da consolidação diária
em `compute_monthly_valid_absences`.

Regra: agrupa registros por (student_id, date), calcula %presença e
converte em status diário binário (≥50% → presente, <50% → falta).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.attendance_utils import compute_monthly_valid_absences  # noqa: E402


def _by_course_day(date, sid, statuses, course_prefix="course"):
    """Helper: simula um dia em modo by_course gerando N docs de attendance
    (1 por componente) com 1 registro do aluno em cada."""
    return [
        {"date": date, "records": [{"student_id": sid, "status": st}]}
        for st in statuses
    ]


def test_consolidation_5_present_1_absent_no_falta():
    """5P + 1F em 6 aulas → 83% presença → DIA PRESENTE."""
    docs = _by_course_day("2026-03-10", "s1", ["P", "P", "P", "P", "P", "F"])
    out = compute_monthly_valid_absences(docs, {}, {"s1"})
    assert out.get("s1", {}).get(3, 0) == 0


def test_consolidation_2_present_4_absent_one_falta():
    """2P + 4F em 6 aulas → 33% presença → DIA FALTA (1 falta no mês)."""
    docs = _by_course_day("2026-03-10", "s1", ["P", "P", "F", "F", "F", "F"])
    out = compute_monthly_valid_absences(docs, {}, {"s1"})
    assert out.get("s1", {}).get(3) == 1


def test_consolidation_exactly_50_percent_is_present():
    """3P + 3F = 50% exato → PRESENTE (regra ≥ 50%)."""
    docs = _by_course_day("2026-03-10", "s1", ["P", "P", "P", "F", "F", "F"])
    out = compute_monthly_valid_absences(docs, {}, {"s1"})
    assert out.get("s1", {}).get(3, 0) == 0


def test_consolidation_all_absent_one_falta():
    """6F → 0% → FALTA."""
    docs = _by_course_day("2026-03-10", "s1", ["F"] * 6)
    out = compute_monthly_valid_absences(docs, {}, {"s1"})
    assert out.get("s1", {}).get(3) == 1


def test_consolidation_multiple_days_same_month():
    """Vários dias do mesmo mês cada um avaliado independentemente."""
    docs = (
        _by_course_day("2026-03-10", "s1", ["F", "F", "F", "F", "P", "P"])  # 33% → falta
        + _by_course_day("2026-03-11", "s1", ["P", "P", "P", "P", "P", "F"])  # 83% → presente
        + _by_course_day("2026-03-12", "s1", ["F", "F", "F", "F", "F", "F"])  # 0% → falta
    )
    out = compute_monthly_valid_absences(docs, {}, {"s1"})
    # 2 dias com <50% → 2 faltas em março
    assert out.get("s1", {}).get(3) == 2


def test_daily_mode_single_record_per_day_still_works():
    """`attendance_type='daily'` produz 1 registro só → 0% ou 100%, equivale ao comportamento antigo."""
    docs = [
        {"date": "2026-03-10", "records": [{"student_id": "s1", "status": "F"}]},
        {"date": "2026-03-11", "records": [{"student_id": "s1", "status": "P"}]},
    ]
    out = compute_monthly_valid_absences(docs, {}, {"s1"})
    assert out.get("s1", {}).get(3) == 1


def test_atestado_excludes_records_from_denominator():
    """Atestado tira o REGISTRO do denominador (não inverte 'F' em 'P').
    
    Cenário: 5F + 1P, mas o dia inteiro está sob atestado → 0 registros
    válidos → dia ignorado (não conta como presença nem como falta)."""
    docs = _by_course_day("2026-03-10", "s1", ["F", "F", "F", "F", "F", "P"])
    medical = {"s1": {"2026-03-10"}}
    out = compute_monthly_valid_absences(docs, medical, {"s1"})
    assert out.get("s1", {}).get(3, 0) == 0


def test_justified_excluded_from_denominator():
    """Justificada (`J`) sai do denominador. 3J + 2P + 1F → 2/3 ≈ 66% → presente."""
    docs = _by_course_day("2026-03-10", "s1", ["J", "J", "J", "P", "P", "F"])
    out = compute_monthly_valid_absences(docs, {}, {"s1"})
    assert out.get("s1", {}).get(3, 0) == 0


def test_justified_majority_with_one_absent_still_falta_if_under_50():
    """3J + 1P + 2F → após excluir J: 1P / (1P+2F) = 33% → FALTA."""
    docs = _by_course_day("2026-03-10", "s1", ["J", "J", "J", "P", "F", "F"])
    out = compute_monthly_valid_absences(docs, {}, {"s1"})
    assert out.get("s1", {}).get(3) == 1


def test_dependency_records_dont_contaminate():
    """Registros com `dependency_id` saem totalmente do cálculo regular."""
    docs = [
        {"date": "2026-03-10", "records": [
            {"student_id": "s1", "status": "F", "dependency_id": "dep1"},
            {"student_id": "s1", "status": "F", "dependency_id": "dep1"},
            {"student_id": "s1", "status": "P"},
            {"student_id": "s1", "status": "P"},
        ]}
    ]
    out = compute_monthly_valid_absences(docs, {}, {"s1"})
    # Só 2 registros válidos (ambos P) → 100% → presente
    assert out.get("s1", {}).get(3, 0) == 0


def test_invalidated_records_excluded():
    """Registros com `invalidated=True` saem do cálculo."""
    docs = [
        {"date": "2026-03-10", "records": [
            {"student_id": "s1", "status": "F", "invalidated": True},
            {"student_id": "s1", "status": "F", "invalidated": True},
            {"student_id": "s1", "status": "F"},
            {"student_id": "s1", "status": "P"},
        ]}
    ]
    out = compute_monthly_valid_absences(docs, {}, {"s1"})
    # Válidos: 1F + 1P → 50% → presente
    assert out.get("s1", {}).get(3, 0) == 0


def test_other_students_records_isolated_per_student_ids_filter():
    """student_ids filtra antes do agrupamento."""
    docs = [
        {"date": "2026-03-10", "records": [
            {"student_id": "s1", "status": "F"},
            {"student_id": "s1", "status": "F"},
            {"student_id": "s2", "status": "P"},
            {"student_id": "s2", "status": "P"},
        ]}
    ]
    out = compute_monthly_valid_absences(docs, {}, {"s1"})
    # s1 → 0% → falta
    assert out.get("s1", {}).get(3) == 1
    # s2 não está no filtro → não aparece
    assert "s2" not in out


def test_zero_valid_records_day_doesnt_count():
    """Dia inteiro coberto por atestado + J → denominador 0 → ignorado."""
    docs = [
        {"date": "2026-03-10", "records": [
            {"student_id": "s1", "status": "F"},
            {"student_id": "s1", "status": "J"},
        ]}
    ]
    medical = {"s1": {"2026-03-10"}}  # cobre o F
    out = compute_monthly_valid_absences(docs, medical, {"s1"})
    assert out.get("s1", {}).get(3, 0) == 0
