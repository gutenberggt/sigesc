"""Layer 1 (P0 Fev/2026) — Validação canônica de frequência válida no BF.

Garante que a engine `services/attendance_utils.compute_monthly_valid_absences`
aplica corretamente as regras MEC alinhadas à frequência institucional:

  - Falta comum (`F`) sem atestado → CONTA como falta válida (reduz frequência).
  - Status `J` (justificado pelo professor) → NÃO conta como falta válida.
  - Dia coberto por atestado médico → NÃO conta como falta válida
    (atestado vence o status original — regra Fev/2026).
  - Registros com `dependency_id` → ignorados (não contaminam cálculo regular).

Os 4 casos abaixo são EXIGIDOS pelo owner como condição de aceite do fix:
  | Cenário                            | Frequência esperada |
  | ---------------------------------- | ------------------- |
  | 20 dias, 5 faltas comuns           | 75%                 |
  | 20 dias, 5 atestados               | 100%                |
  | 20 dias, 5 justificadas            | 100%                |
  | 20 dias, 3 faltas + 2 atestados    | 85%                 |
"""
import pytest

from services.attendance_utils import compute_monthly_valid_absences


SCHOOL_DAYS = 20
ACADEMIC_MONTH = 3  # março
STUDENT_ID = "student_001"


def _build_attendance_doc(day: int, status: str, student_id: str = STUDENT_ID):
    """Helper: monta documento `attendance` do mês de março/2026."""
    return {
        "date": f"2026-03-{day:02d}",
        "records": [
            {"student_id": student_id, "status": status},
        ],
    }


def _calc_pct(school_days: int, valid_absences: int) -> float:
    """Replica EXATAMENTE a fórmula do BF (`bolsa_familia.py`):
    `((school_days - absences) / school_days) * 100`, arredondado em 1 casa.
    """
    if school_days <= 0:
        return 0.0
    return round(((school_days - valid_absences) * 100) / school_days, 1)


def test_case1_20days_5_common_faults_returns_75pct():
    """Caso 1: 20 dias letivos, 5 faltas COMUNS (sem atestado, sem J) → 75%."""
    docs = []
    # 5 faltas (dias 1-5) + 15 presenças (dias 6-20)
    for d in range(1, 6):
        docs.append(_build_attendance_doc(d, "F"))
    for d in range(6, 21):
        docs.append(_build_attendance_doc(d, "P"))

    absences = compute_monthly_valid_absences(
        docs, medical_days_by_student={}, student_ids={STUDENT_ID}
    )
    valid_absences = absences.get(STUDENT_ID, {}).get(ACADEMIC_MONTH, 0)
    assert valid_absences == 5, f"esperava 5 faltas válidas, obteve {valid_absences}"
    assert _calc_pct(SCHOOL_DAYS, valid_absences) == 75.0


def test_case2_20days_5_medical_certificates_returns_100pct():
    """Caso 2: 20 dias, 5 dias cobertos por atestado → 100% (atestado vence)."""
    docs = []
    # Os 5 primeiros dias o aluno aparece como F no diário, MAS tem atestado.
    for d in range(1, 6):
        docs.append(_build_attendance_doc(d, "F"))
    for d in range(6, 21):
        docs.append(_build_attendance_doc(d, "P"))

    # 5 dias cobertos por atestado
    medical_days_by_student = {
        STUDENT_ID: {f"2026-03-{d:02d}" for d in range(1, 6)}
    }
    absences = compute_monthly_valid_absences(
        docs, medical_days_by_student=medical_days_by_student, student_ids={STUDENT_ID}
    )
    valid_absences = absences.get(STUDENT_ID, {}).get(ACADEMIC_MONTH, 0)
    assert valid_absences == 0, f"esperava 0 faltas válidas (atestado vence), obteve {valid_absences}"
    assert _calc_pct(SCHOOL_DAYS, valid_absences) == 100.0


def test_case3_20days_5_justified_returns_100pct():
    """Caso 3: 20 dias, 5 faltas JUSTIFICADAS (status J) → 100%."""
    docs = []
    for d in range(1, 6):
        docs.append(_build_attendance_doc(d, "J"))  # justificada pelo professor
    for d in range(6, 21):
        docs.append(_build_attendance_doc(d, "P"))

    absences = compute_monthly_valid_absences(
        docs, medical_days_by_student={}, student_ids={STUDENT_ID}
    )
    valid_absences = absences.get(STUDENT_ID, {}).get(ACADEMIC_MONTH, 0)
    assert valid_absences == 0, f"esperava 0 (J não conta), obteve {valid_absences}"
    assert _calc_pct(SCHOOL_DAYS, valid_absences) == 100.0


def test_case4_20days_3_faults_2_medical_returns_85pct():
    """Caso 4: 20 dias, 3 faltas comuns + 2 dias com atestado → 85%."""
    docs = []
    # 3 faltas comuns (dias 1-3)
    for d in range(1, 4):
        docs.append(_build_attendance_doc(d, "F"))
    # 2 dias com F mas COBERTOS por atestado (dias 4-5)
    for d in range(4, 6):
        docs.append(_build_attendance_doc(d, "F"))
    # 15 presenças (dias 6-20)
    for d in range(6, 21):
        docs.append(_build_attendance_doc(d, "P"))

    medical_days_by_student = {
        STUDENT_ID: {"2026-03-04", "2026-03-05"},  # 2 dias de atestado
    }
    absences = compute_monthly_valid_absences(
        docs, medical_days_by_student=medical_days_by_student, student_ids={STUDENT_ID}
    )
    valid_absences = absences.get(STUDENT_ID, {}).get(ACADEMIC_MONTH, 0)
    assert valid_absences == 3, f"esperava 3 faltas válidas (3F + 2 atestado descontados), obteve {valid_absences}"
    assert _calc_pct(SCHOOL_DAYS, valid_absences) == 85.0


# ============================================================================
# Casos adicionais de defesa em profundidade
# ============================================================================

def test_dependency_records_are_ignored():
    """Registros com `dependency_id` NÃO devem contar para regular (P0)."""
    docs = [
        {
            "date": "2026-03-01",
            "records": [
                {"student_id": STUDENT_ID, "status": "F"},
                {"student_id": STUDENT_ID, "status": "F", "dependency_id": "dep_xyz"},
            ],
        },
    ]
    absences = compute_monthly_valid_absences(
        docs, medical_days_by_student={}, student_ids={STUDENT_ID}
    )
    # Apenas 1 falta válida (a com dependency_id é ignorada).
    assert absences.get(STUDENT_ID, {}).get(ACADEMIC_MONTH) == 1


def test_records_from_other_students_ignored_when_filter_set():
    """Filtro de student_ids restringe scope corretamente."""
    docs = [
        {
            "date": "2026-03-10",
            "records": [
                {"student_id": "student_A", "status": "F"},
                {"student_id": "student_B", "status": "F"},
            ],
        },
    ]
    absences = compute_monthly_valid_absences(
        docs, medical_days_by_student={}, student_ids={"student_A"}
    )
    assert absences.get("student_A", {}).get(ACADEMIC_MONTH) == 1
    assert "student_B" not in absences


def test_absences_split_per_month():
    """Faltas em meses diferentes ficam em buckets separados."""
    docs = [
        _build_attendance_doc(5, "F"),  # março
        {"date": "2026-04-15", "records": [{"student_id": STUDENT_ID, "status": "F"}]},
        {"date": "2026-04-20", "records": [{"student_id": STUDENT_ID, "status": "F"}]},
    ]
    absences = compute_monthly_valid_absences(
        docs, medical_days_by_student={}, student_ids={STUDENT_ID}
    )
    assert absences[STUDENT_ID][3] == 1  # março
    assert absences[STUDENT_ID][4] == 2  # abril


def test_empty_records_returns_empty():
    """Documento sem records ou records sem student_id devem ser ignorados."""
    docs = [
        {"date": "2026-03-01", "records": []},
        {"date": "2026-03-02", "records": [{"status": "F"}]},  # sem student_id
        {"date": "2026-03-03"},  # sem records
        {"records": [{"student_id": STUDENT_ID, "status": "F"}]},  # sem date
    ]
    absences = compute_monthly_valid_absences(
        docs, medical_days_by_student={}, student_ids={STUDENT_ID}
    )
    assert absences == {}


def test_alternative_status_aliases():
    """Aceita aliases legados: 'absent', 'ausente', 'falta'."""
    docs = [
        {"date": "2026-03-01", "records": [{"student_id": STUDENT_ID, "status": "absent"}]},
        {"date": "2026-03-02", "records": [{"student_id": STUDENT_ID, "status": "ausente"}]},
        {"date": "2026-03-03", "records": [{"student_id": STUDENT_ID, "status": "falta"}]},
        {"date": "2026-03-04", "records": [{"student_id": STUDENT_ID, "status": "F"}]},
        {"date": "2026-03-05", "records": [{"student_id": STUDENT_ID, "status": "justified"}]},
    ]
    absences = compute_monthly_valid_absences(
        docs, medical_days_by_student={}, student_ids={STUDENT_ID}
    )
    # 4 faltas (3 aliases + F) + 0 do justified
    assert absences[STUDENT_ID][3] == 4
