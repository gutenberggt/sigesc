"""P0 — contrato híbrido de leitura avaliativa do Professor.

O Professor pode coexistir com dois modelos de vínculo no mesmo ano letivo:
- DVD: ``teacher_class_assignments`` é canônico e deve prevalecer;
- legado: ``teacher_assignments`` continua canônico quando a turma/componente
  não está protegida pelo DVD.

Esses guards evitam que telas agregadas (Livro de Promoção, Por Estudante,
Boletim e sync offline) decidam o modelo apenas por ``role == professor``.
"""
from pathlib import Path

from services.teacher_grade_access import (
    TeacherGradeScope,
    _is_dvd_protected_scope,
    resolve_teacher_grade_scope,
)


ROOT = Path(__file__).resolve().parents[1]
TEACHER_SCOPE = (ROOT / "services" / "teacher_grade_access.py").read_text(encoding="utf-8")
HARDENING = (ROOT / "routers" / "grades_dvd_hardening.py").read_text(encoding="utf-8")
STUDENT_SCOPE = (ROOT / "routers" / "grades_dvd_student_scope.py").read_text(encoding="utf-8")
BULLETINS = (ROOT / "routers" / "bulletins.py").read_text(encoding="utf-8")
BULLETIN_PDF = (ROOT / "routers" / "bulletin_pdf.py").read_text(encoding="utf-8")


def _scope(*, source, assignment_id, class_id="c1", component_id="co1"):
    return TeacherGradeScope(
        assignment_id=assignment_id,
        class_id=class_id,
        component_id=component_id,
        school_id="s1",
        mantenedora_id="m1",
        profile="regular" if source == "dvd" else "legacy",
        student_scope="all",
        valid_from="2026-01-01",
        valid_until="2026-12-31",
        source=source,
        legacy_assignment_id=(assignment_id if source == "legacy" else None),
    )


def test_escopo_docente_declara_origem_dvd_ou_legacy():
    assert 'source: str = "dvd"' in TEACHER_SCOPE
    assert 'legacy_assignment_id: Optional[str] = None' in TEACHER_SCOPE
    assert '"staff_id": staff["id"]' in TEACHER_SCOPE
    assert 'db.teacher_assignments.find(' in TEACHER_SCOPE


def test_dvd_prevalece_e_impede_fallback_legacy_no_mesmo_escopo():
    assert 'def _is_dvd_protected_scope(' in TEACHER_SCOPE
    assert 'if _is_dvd_protected_scope(' in TEACHER_SCOPE
    assert 'source="legacy"' in TEACHER_SCOPE

    scopes = [
        _scope(source="legacy", assignment_id="legacy-a"),
        _scope(source="dvd", assignment_id="dvd-a"),
    ]
    resolved = resolve_teacher_grade_scope(scopes, class_id="c1", course_id="co1")
    assert resolved is not None
    assert resolved.source == "dvd"
    assert resolved.assignment_id == "dvd-a"


def test_legacy_e_usado_quando_nao_existe_dvd_aplicavel():
    scopes = [_scope(source="legacy", assignment_id="legacy-a")]
    resolved = resolve_teacher_grade_scope(scopes, class_id="c1", course_id="co1")
    assert resolved is not None
    assert resolved.source == "legacy"


def test_protecao_dvd_cobre_componente_exato_e_regencia():
    exact = [{"class_id": "c1", "component_id": "co1"}]
    assert _is_dvd_protected_scope(exact, "c1", "co1") is True
    assert _is_dvd_protected_scope(exact, "c1", "co2") is False

    regencia = [{"class_id": "c1", "component_id": None}]
    assert _is_dvd_protected_scope(regencia, "c1", "co1") is True
    assert _is_dvd_protected_scope(regencia, "c1", "co2") is True


def test_leitura_agregada_de_grades_filtra_por_escopo_hibrido():
    assert 'list_teacher_grade_scopes(' in HARDENING
    assert 'scope.source == "legacy"' in HARDENING
    assert 'scope.source == "dvd"' in HARDENING
    assert 'grade_ownership' in HARDENING


def test_por_estudante_suporta_linhas_dvd_e_legacy_sem_forjar_assignment():
    assert 'scope.source == "dvd"' in STUDENT_SCOPE
    assert 'scope.source == "legacy"' in STUDENT_SCOPE
    assert 'history_source": "grades_legacy"' in STUDENT_SCOPE
    assert 'dvd_assignment_id": None' in STUDENT_SCOPE


def test_boletim_online_e_pdf_reusam_o_mesmo_resolvedor_hibrido():
    assert 'ensure_teacher_student_grade_access' in BULLETINS
    assert 'ensure_teacher_student_grade_access' in BULLETIN_PDF


def test_sync_pull_de_notas_preserva_legacy_e_ownership_dvd():
    assert 'legacy_scope_clauses' in HARDENING
    assert 'dvd_scope_clauses' in HARDENING
    assert 'scope.source == "legacy"' in HARDENING
    assert '_mask_grade_for_teacher' in HARDENING
