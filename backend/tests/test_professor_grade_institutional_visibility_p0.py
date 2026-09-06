"""P0 — notas institucionais visíveis a todo professor com escopo autorizado.

O ownership continua sendo autorização de ESCRITA. Ele não pode transformar uma
nota salva da turma/componente em célula vazia para outro professor autorizado.
"""

from pathlib import Path
from types import SimpleNamespace

from routers.grades_dvd_institutional_visibility import (
    _project_authorized_grade_for_assignment,
    _project_authorized_grade_for_teacher,
)


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
VISIBILITY = (ROOT / "routers" / "grades_dvd_institutional_visibility.py").read_text(
    encoding="utf-8"
)
ROUTERS_INIT = (ROOT / "routers" / "__init__.py").read_text(encoding="utf-8")
GRADE_SCOPE = (ROOT / "services" / "grade_assignment_scope.py").read_text(
    encoding="utf-8"
)
PROMOTION = (REPO / "frontend" / "src" / "pages" / "Promotion.jsx").read_text(
    encoding="utf-8"
)


def _grade():
    return {
        "id": "g1",
        "student_id": "student-1",
        "class_id": "class-5a",
        "course_id": "lingua-portuguesa",
        "academic_year": 2026,
        "b1": 8.0,
        "b2": 9.0,
        "b3": None,
        "b4": None,
        "rec_s1": None,
        "rec_s2": None,
        "recovery": None,
        "observations": "Bom desempenho",
        "final_average": 8.5,
        "status": "cursando",
        "grade_ownership": {
            "b1": {
                "assignment_id": "assignment-anterior",
                "teacher_id": "teacher-anterior",
            },
            "b2": {
                "assignment_id": "assignment-atual",
                "teacher_id": "teacher-atual",
            },
            "observations": {
                "assignment_id": "assignment-anterior",
                "teacher_id": "teacher-anterior",
            },
        },
    }


def test_vinculo_autorizado_enxerga_valores_de_outro_assignment_sem_receber_autoria():
    context = SimpleNamespace(
        assignment_id="assignment-atual",
        snapshot={},
    )

    projected = _project_authorized_grade_for_assignment(
        _grade(),
        context,
        mask_foreign=True,
    )

    # Regressão José Pereira Barbosa / 5º A: valor institucional não some.
    assert projected["b1"] == 8.0
    assert projected["b2"] == 9.0
    assert projected["final_average"] == 8.5
    assert projected["status"] == "cursando"

    # O campo alheio é visível, porém continua bloqueado para escrita.
    assert "b1" in projected["dvd_locked_fields"]
    assert "observations" in projected["dvd_locked_fields"]
    assert "b2" in projected["dvd_owned_fields"]

    # Snapshot do outro vínculo não é exposto ao professor.
    assert set(projected["grade_ownership"]) == {"b2"}


def test_leitura_agregada_nao_descarta_registro_sem_autoria_do_professor_atual():
    projected = _project_authorized_grade_for_teacher(
        _grade(),
        "teacher-novo",
    )

    assert projected["b1"] == 8.0
    assert projected["b2"] == 9.0
    assert projected["final_average"] == 8.5
    assert set(projected["dvd_locked_fields"]) >= {"b1", "b2", "observations"}
    assert projected["grade_ownership"] == {}


def test_visibilidade_e_instalada_depois_da_paridade_e_antes_do_student_scope():
    assert "install_grades_dvd_institutional_visibility" in ROUTERS_INIT
    assert ROUTERS_INIT.index("install_grades_dvd_parity(") < ROUTERS_INIT.index(
        "install_grades_dvd_institutional_visibility()"
    )
    assert ROUTERS_INIT.index("install_grades_dvd_institutional_visibility()") < ROUTERS_INIT.index(
        "return install_grades_dvd_student_scope("
    )


def test_livro_de_promocao_consulta_notas_por_turma_componente_do_professor():
    assert "gradesAPI.getByClass" in PROMOTION
    assert "buildPromotionGradesByStudentFromByClass" in PROMOTION
    assert "filterPromotionGradesForClass" in PROMOTION


def test_sync_filtra_por_escopo_autorizado_e_nao_por_teacher_id_do_ownership():
    assert "list_teacher_grade_scopes(" in VISIBILITY
    assert "resolve_teacher_grade_scope(" in VISIBILITY
    assert "scope_clauses" in VISIBILITY
    assert "grade_ownership.{field}.teacher_id" not in VISIBILITY
    assert "sync_mod.fetch_collection_data_paginated = institutional_fetch" in VISIBILITY


def test_correcao_de_leitura_nao_remove_trava_de_escrita_por_ownership():
    assert "GRADE_FIELD_OWNED_BY_OTHER_ASSIGNMENT" in GRADE_SCOPE
    assert "GRADE_LEGACY_FIELD_REQUIRES_REVIEW" in GRADE_SCOPE
    assert "apply_grade_field_ownership" not in VISIBILITY
    assert ".grades.update_one(" not in VISIBILITY
    assert ".grades.insert_one(" not in VISIBILITY
