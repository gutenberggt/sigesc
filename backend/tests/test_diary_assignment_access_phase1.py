"""Fase 1 — autorização central do Diário por Vínculo Docente.

Testes unitários puros: sem HTTP, sem Mongo real e sem alterar dados.
"""

import pytest

from services.diary_assignment_access import (
    DiaryAction,
    DiaryAssignmentAccessError,
    attendance_is_official_for_context,
    authorize_assignment_access,
    effective_diary_settings,
    is_assignment_active_on,
)
from services.diary_assignment_contract import AttendancePurpose, DiaryProfile, StudentScope


class FakeCollection:
    def __init__(self, docs):
        self.docs = [dict(d) for d in docs]

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                if not projection:
                    return dict(doc)

                included = [
                    key for key, enabled in projection.items()
                    if enabled and key != "_id"
                ]
                if included:
                    return {key: doc.get(key) for key in included}

                excluded = {key for key, enabled in projection.items() if not enabled}
                return {key: value for key, value in doc.items() if key not in excluded}
        return None


class FakeDb:
    def __init__(self, assignments, classes):
        self.teacher_class_assignments = FakeCollection(assignments)
        self.classes = FakeCollection(classes)


def _class(**overrides):
    doc = {
        "id": "class-1",
        "school_id": "school-1",
        "mantenedora_id": "tenant-1",
        "education_level": "fundamental_anos_iniciais",
        "grade_level": "3º Ano",
        "atendimento_programa": None,
    }
    doc.update(overrides)
    return doc


def _settings(profile="regular", *, enabled=True, student_scope="all"):
    return {
        "enabled": enabled,
        "schema_version": 1,
        "profile": profile,
        "student_scope": student_scope,
    }


def _assignment(**overrides):
    doc = {
        "id": "assignment-1",
        "teacher_id": "teacher-1",
        "class_id": "class-1",
        "component_id": "math",
        "school_id": "school-1",
        "valid_from": "2026-02-01",
        "valid_until": "2026-12-20",
        "deleted": False,
        "diary_settings": _settings(),
    }
    doc.update(overrides)
    return doc


def _user(**overrides):
    doc = {
        "id": "teacher-1",
        "role": "professor",
        "school_ids": ["school-1"],
        "mantenedora_id": "tenant-1",
    }
    doc.update(overrides)
    return doc


def _db(assignment=None, klass=None):
    return FakeDb([assignment or _assignment()], [klass or _class()])


async def _deny(code, coro):
    with pytest.raises(DiaryAssignmentAccessError) as exc:
        await coro
    assert exc.value.code == code


def test_vinculo_legado_nao_e_habilitado_implicitamente():
    settings = effective_diary_settings(_assignment(diary_settings=None))
    assert settings.enabled is False
    assert settings.profile is DiaryProfile.REGULAR


def test_group_so_e_valido_para_shared():
    with pytest.raises(DiaryAssignmentAccessError) as exc:
        effective_diary_settings(_assignment(diary_settings=_settings("regular", student_scope="group")))
    assert exc.value.code == "INVALID_GROUP_SCOPE"


def test_validade_temporal_e_inclusiva():
    a = _assignment(valid_from="2026-03-01", valid_until="2026-03-31")
    assert is_assignment_active_on(a, "2026-03-01")
    assert is_assignment_active_on(a, "2026-03-31")
    assert not is_assignment_active_on(a, "2026-02-28")
    assert not is_assignment_active_on(a, "2026-04-01")


@pytest.mark.asyncio
async def test_professor_proprietario_regular_acessa_todas_capacidades():
    db = _db()
    for action in (DiaryAction.VIEW, DiaryAction.CONTENT, DiaryAction.ATTENDANCE, DiaryAction.GRADES):
        ctx = await authorize_assignment_access(
            db, _user(), "assignment-1", action=action, on_date="2026-08-17"
        )
        assert ctx.is_owner is True
        assert ctx.management_override is False
        assert ctx.settings.profile is DiaryProfile.REGULAR
        assert attendance_is_official_for_context(ctx) is True


@pytest.mark.asyncio
async def test_professor_nao_pode_usar_assignment_de_outro_professor():
    await _deny(
        "ASSIGNMENT_ACCESS_DENIED",
        authorize_assignment_access(
            _db(), _user(id="teacher-2"), "assignment-1", action="content", on_date="2026-08-17"
        ),
    )


@pytest.mark.asyncio
async def test_mesmo_id_sem_papel_pedagogico_nao_mantem_propriedade_de_escrita():
    antigo_professor = _user(role="secretario")
    await _deny(
        "ASSIGNMENT_ACCESS_DENIED",
        authorize_assignment_access(
            _db(), antigo_professor, "assignment-1", action="content", on_date="2026-08-17"
        ),
    )


@pytest.mark.asyncio
async def test_integrador_tem_conteudo_e_frequencia_pdf_only_mas_nao_notas():
    a = _assignment(diary_settings=_settings("integrator"))
    db = _db(assignment=a)

    content = await authorize_assignment_access(
        db, _user(), "assignment-1", action="content", on_date="2026-08-17"
    )
    attendance = await authorize_assignment_access(
        db, _user(), "assignment-1", action="attendance", on_date="2026-08-17"
    )
    assert content.settings.profile is DiaryProfile.INTEGRATOR
    assert attendance.settings.capabilities.attendance_required is False
    assert attendance.settings.capabilities.attendance_purpose is AttendancePurpose.PDF_ONLY
    assert attendance_is_official_for_context(attendance) is False

    await _deny(
        "CAPABILITY_DENIED",
        authorize_assignment_access(
            db, _user(), "assignment-1", action="grades", on_date="2026-08-17"
        ),
    )


@pytest.mark.asyncio
async def test_shared_pode_usar_student_scope_group():
    a = _assignment(diary_settings=_settings("shared", student_scope="group"))
    ctx = await authorize_assignment_access(
        _db(assignment=a), _user(), "assignment-1", action="grades", on_date="2026-08-17"
    )
    assert ctx.settings.profile is DiaryProfile.SHARED
    assert ctx.settings.student_scope is StudentScope.GROUP
    assert ctx.settings.capabilities.attendance_purpose is AttendancePurpose.OFFICIAL


@pytest.mark.asyncio
async def test_vinculo_sem_dvd_habilitado_e_bloqueado():
    await _deny(
        "DVD_NOT_ENABLED",
        authorize_assignment_access(
            _db(assignment=_assignment(diary_settings=None)),
            _user(),
            "assignment-1",
            on_date="2026-08-17",
        ),
    )


@pytest.mark.asyncio
async def test_vinculo_fora_da_vigencia_e_bloqueado():
    await _deny(
        "ASSIGNMENT_NOT_ACTIVE",
        authorize_assignment_access(
            _db(), _user(), "assignment-1", action="view", on_date="2027-01-10"
        ),
    )


@pytest.mark.asyncio
async def test_anos_finais_ficam_fora_mesmo_com_settings_habilitados():
    klass = _class(
        education_level="fundamental_anos_finais",
        grade_level="6º Ano",
    )
    await _deny(
        "CLASS_OUT_OF_DVD_SCOPE",
        authorize_assignment_access(
            _db(klass=klass), _user(), "assignment-1", on_date="2026-08-17"
        ),
    )


@pytest.mark.asyncio
async def test_aee_fica_fora_mesmo_em_etapa_elegivel():
    klass = _class(atendimento_programa="aee")
    await _deny(
        "CLASS_OUT_OF_DVD_SCOPE",
        authorize_assignment_access(
            _db(klass=klass), _user(), "assignment-1", on_date="2026-08-17"
        ),
    )


@pytest.mark.asyncio
async def test_gestor_pode_visualizar_vinculo_de_outro_professor_na_mesma_escola():
    manager = _user(id="coord-1", role="coordenador")
    ctx = await authorize_assignment_access(
        _db(), manager, "assignment-1", action="view", on_date="2026-08-17"
    )
    assert ctx.is_owner is False
    assert ctx.management_override is False


@pytest.mark.asyncio
async def test_gestor_nao_edita_implicitamente_sem_override_explicito():
    manager = _user(id="coord-1", role="coordenador")
    await _deny(
        "ASSIGNMENT_ACCESS_DENIED",
        authorize_assignment_access(
            _db(), manager, "assignment-1", action="content", on_date="2026-08-17"
        ),
    )


@pytest.mark.asyncio
async def test_override_gerencial_expresso_respeita_capability_do_perfil():
    manager = _user(id="coord-1", role="coordenador")
    ctx = await authorize_assignment_access(
        _db(),
        manager,
        "assignment-1",
        action="content",
        on_date="2026-08-17",
        allow_management_override=True,
    )
    assert ctx.management_override is True

    integrator = _assignment(diary_settings=_settings("integrator"))
    await _deny(
        "CAPABILITY_DENIED",
        authorize_assignment_access(
            _db(assignment=integrator),
            manager,
            "assignment-1",
            action="grades",
            on_date="2026-08-17",
            allow_management_override=True,
        ),
    )


@pytest.mark.asyncio
async def test_escola_e_tenant_sao_guardrails_independentes():
    professor_sem_escola = _user(school_ids=["school-2"])
    await _deny(
        "SCHOOL_ACCESS_DENIED",
        authorize_assignment_access(
            _db(), professor_sem_escola, "assignment-1", on_date="2026-08-17"
        ),
    )

    professor_outro_tenant = _user(mantenedora_id="tenant-2")
    await _deny(
        "TENANT_ACCESS_DENIED",
        authorize_assignment_access(
            _db(), professor_outro_tenant, "assignment-1", on_date="2026-08-17"
        ),
    )


@pytest.mark.asyncio
async def test_contexto_esperado_impede_troca_de_turma_ou_componente():
    await _deny(
        "CLASS_MISMATCH",
        authorize_assignment_access(
            _db(),
            _user(),
            "assignment-1",
            expected_class_id="class-2",
            on_date="2026-08-17",
        ),
    )
    await _deny(
        "COMPONENT_MISMATCH",
        authorize_assignment_access(
            _db(),
            _user(),
            "assignment-1",
            expected_component_id="portuguese",
            on_date="2026-08-17",
        ),
    )
