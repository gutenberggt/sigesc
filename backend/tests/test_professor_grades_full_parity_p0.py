"""Guards do PR #54 — Por Estudante, Boletim e entrada por vínculo."""

from pathlib import Path

from services.teacher_grade_access import _assignment_authorization_date


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
    assert 'TEACHER_STUDENT_GRADE_SCOPE_DENIED' in TEACHER_SCOPE


def test_escopo_e_ancorado_no_ano_e_preserva_historico_com_evidencia():
    assert 'def _year_bounds(' in TEACHER_SCOPE
    assert 'def _assignment_authorization_date(' in TEACHER_SCOPE
    assert '"valid_from": {"$lte": year_end}' in TEACHER_SCOPE
    assert '{"valid_until": {"$gte": year_start}}' in TEACHER_SCOPE
    assert 'academic_year": {"$in": [int(academic_year), str(int(academic_year))]}' in TEACHER_SCOPE
    assert 'grade_rows = await db.grades.find(' in TEACHER_SCOPE
    assert 'inclusive após transferência/remanejamento' in TEACHER_SCOPE
    assert 'if int(academic_year) == date.today().year:' in TEACHER_SCOPE


def test_intersecao_temporal_do_vinculo_rejeita_ano_estranho_e_respeita_fim():
    assignment = {
        "valid_from": "2026-08-18",
        "valid_until": "2026-12-20",
    }
    assert _assignment_authorization_date(assignment, 2026) == "2026-08-18"
    assert _assignment_authorization_date(assignment, 2025) is None
    assert _assignment_authorization_date(assignment, 2027) is None
    assert _assignment_authorization_date(
        assignment,
        2026,
        reference_date="2026-09-01",
    ) == "2026-09-01"
    assert _assignment_authorization_date(
        assignment,
        2026,
        reference_date="2026-01-10",
    ) is None


def test_escopo_por_estudante_resolve_assignment_por_componente_e_reusa_pr53():
    assert '@base_router.get("/dvd/teacher-students")' in STUDENT_SCOPE
    assert '@base_router.get("/by-student/{student_id}")' in STUDENT_SCOPE
    assert 'resolve_grade_assignment(' in STUDENT_SCOPE
    assert '_decorate_context_with_legacy_history(' in STUDENT_SCOPE
    assert '_project_grade_for_assignment(grade, context)' in STUDENT_SCOPE
    assert 'GRADE_STUDENT_SCOPE_AMBIGUOUS' in STUDENT_SCOPE


def test_primeiro_lancamento_tem_linha_autorizada_sem_criar_dado_no_read_model():
    assert 'def _empty_grade(' in STUDENT_SCOPE
    assert 'scope.component_id is None' in STUDENT_SCOPE
    assert 'scope_keys.add((scope.class_id, scope.component_id))' in STUDENT_SCOPE
    assert '"has_grade_record": bool(grade.get("id"))' in STUDENT_SCOPE
    assert 'gradeCreationByStudentCourse' in BRIDGE
    assert 'payload.class_id = creationScope.classId' in BRIDGE
    assert 'config.url = appendAssignmentId(url, assignmentId)' in BRIDGE


def test_componente_duplicado_entre_turmas_falha_fechado():
    assert 'GRADE_STUDENT_COMPONENT_MULTI_CLASS_AMBIGUOUS' in STUDENT_SCOPE
    assert 'classes_by_course' in STUDENT_SCOPE
    assert 'if len(class_ids) > 1' in STUDENT_SCOPE
    assert 'gradeCreationByStudentCourse.set(simpleKey, null)' in BRIDGE


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


def test_bridge_nao_prende_leitura_ou_edicao_agregada_ao_assignment_raiz():
    assert "url.includes('/grades/by-student/')" in BRIDGE
    assert "url.includes('/grades/dvd/teacher-students')" in BRIDGE
    assert 'gradeAssignmentById' in BRIDGE
    assert 'gradeAssignmentByScope' in BRIDGE
    assert 'gradeCreationByStudentCourse' in BRIDGE
    assert '/grades/dvd/teacher-students' in BRIDGE
    assert 'assignment raiz de outro componente' in BRIDGE


def test_ui_bloqueia_campos_historicos_e_preserva_conceitos():
    assert 'dvd_read_only_fields' in ALUNO_TAB
    assert 'dvd_locked_fields' in ALUNO_TAB
    assert 'Histórico read-only' in ALUNO_TAB
    assert 'ConceitoSelect' in ALUNO_TAB
    assert 'usaAvaliacaoConceitual' in ALUNO_TAB
    assert 'calcularMaiorConceito' in ALUNO_TAB
    assert 'dvd_read_only_fields' in GRADES_TABLE
    assert 'dvd_locked_fields' in GRADES_TABLE
    assert 'Histórico anterior ao Diário por Vínculo' in GRADES_TABLE


def test_boletim_online_indice_dependencia_e_pdf_exigem_escopo_docente():
    assert 'ensure_teacher_student_grade_access' in BULLETINS
    assert 'role == "professor"' in BULLETINS
    assert 'if str(item.get("class_id") or "") in memberships' in BULLETINS
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
