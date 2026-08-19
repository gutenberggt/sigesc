"""Guards do PR #54 — Por Estudante, Boletim e entrada por vínculo."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
TEACHER_SCOPE = (ROOT / "services" / "teacher_grade_access.py").read_text(encoding="utf-8")
STUDENT_SCOPE = (ROOT / "routers" / "grades_dvd_student_scope.py").read_text(encoding="utf-8")
BULLETINS = (ROOT / "routers" / "bulletins.py").read_text(encoding="utf-8")
BULLETIN_PDF = (ROOT / "routers" / "bulletin_pdf.py").read_text(encoding="utf-8")
ROUTERS_INIT = (ROOT / "routers" / "__init__.py").read_text(encoding="utf-8")
DASHBOARD = (REPO / "frontend" / "src" / "pages" / "ProfessorDashboard.js").read_text(encoding="utf-8")
BRIDGE = (REPO / "frontend" / "src" / "services" / "gradesDvdBridge.js").read_text(encoding="utf-8")
ALUNO_TAB = (REPO / "frontend" / "src" / "components" / "grades" / "AlunoTab.jsx").read_text(encoding="utf-8")
GRADES_TABLE = (REPO / "frontend" / "src" / "components" / "grades" / "GradesTable.jsx").read_text(encoding="utf-8")


def test_entrada_rapida_de_notas_nasce_de_meus_diarios():
    assert 'data-testid="menu-lancar-notas"' in DASHBOARD
    assert 'onClick={openFromMyDiaries}' in DASHBOARD
    assert 'Escolha o diário/vínculo abaixo' in DASHBOARD


def test_roster_do_professor_deriva_de_assignment_e_capability_grades():
    assert '"teacher_id": teacher_id' in TEACHER_SCOPE
    assert 'action=DiaryAction.GRADES' in TEACHER_SCOPE
    assert 'profile is DiaryProfile.SHARED' in TEACHER_SCOPE
    assert 'student_scope is StudentScope.GROUP' in TEACHER_SCOPE
    assert 'grades_official_owner' in TEACHER_SCOPE
    assert 'status": "active"' in TEACHER_SCOPE
    assert 'TEACHER_STUDENT_GRADE_SCOPE_DENIED' in TEACHER_SCOPE


def test_escopo_por_estudante_resolve_assignment_por_componente_e_reusa_pr53():
    assert '@base_router.get("/dvd/teacher-students")' in STUDENT_SCOPE
    assert '@base_router.get("/by-student/{student_id}")' in STUDENT_SCOPE
    assert 'resolve_grade_assignment(' in STUDENT_SCOPE
    assert '_decorate_context_with_legacy_history(' in STUDENT_SCOPE
    assert '_project_grade_for_assignment(grade, context)' in STUDENT_SCOPE
    assert 'GRADE_STUDENT_SCOPE_AMBIGUOUS' in STUDENT_SCOPE
    assert 'dvd_assignment_id' not in STUDENT_SCOPE or '_project_grade_for_assignment' in STUDENT_SCOPE


def test_read_models_de_escopo_nao_escrevem_em_notas():
    forbidden = (
        '.grades.insert_one(',
        '.grades.update_one(',
        '.grades.update_many(',
        '.grades.delete_one(',
        '.grades.delete_many(',
    )
    for source in (TEACHER_SCOPE, STUDENT_SCOPE):
        for token in forbidden:
            assert token not in source


def test_bridge_nao_prende_leitura_agregada_ao_assignment_raiz():
    assert "url.includes('/grades/by-student/')" in BRIDGE
    assert "url.includes('/grades/dvd/teacher-students')" in BRIDGE
    assert 'gradeAssignmentById' in BRIDGE
    assert 'gradeAssignmentByScope' in BRIDGE
    assert '/grades/dvd/teacher-students' in BRIDGE


def test_ui_bloqueia_campos_historicos_sem_depender_so_do_backend():
    assert 'dvd_read_only_fields' in ALUNO_TAB
    assert 'dvd_locked_fields' in ALUNO_TAB
    assert 'Histórico read-only' in ALUNO_TAB
    assert 'ConceitoSelect' in ALUNO_TAB
    assert 'usaAvaliacaoConceitual' in ALUNO_TAB
    assert 'dvd_read_only_fields' in GRADES_TABLE
    assert 'dvd_locked_fields' in GRADES_TABLE
    assert 'Histórico anterior ao Diário por Vínculo' in GRADES_TABLE


def test_boletim_online_e_pdf_exigem_roster_para_professor():
    assert 'ensure_teacher_student_grade_access' in BULLETINS
    assert 'role == "professor"' in BULLETINS
    assert 'TEACHER_DEPENDENCY_BULLETIN_SCOPE_DENIED' in BULLETINS
    assert 'ensure_teacher_student_grade_access' in BULLETIN_PDF
    assert 'role == "professor" and job.get("document_type") == "bulletin"' in BULLETIN_PDF
    assert 'BULLETIN_JOB_SCOPE_UNRESOLVED' in BULLETIN_PDF


def test_ordem_de_instalacao_preserva_fase5_pr53_e_pr54():
    assert 'configured = install_grades_dvd_adapter(' in ROUTERS_INIT
    assert 'configured = install_grades_dvd_hardening(' in ROUTERS_INIT
    assert 'configured = install_grades_dvd_parity(' in ROUTERS_INIT
    assert 'return install_grades_dvd_student_scope(' in ROUTERS_INIT
    assert ROUTERS_INIT.index('install_grades_dvd_adapter(') < ROUTERS_INIT.index('install_grades_dvd_hardening(')
    assert ROUTERS_INIT.index('install_grades_dvd_hardening(') < ROUTERS_INIT.index('install_grades_dvd_parity(')
    assert ROUTERS_INIT.index('install_grades_dvd_parity(') < ROUTERS_INIT.index('install_grades_dvd_student_scope(')
