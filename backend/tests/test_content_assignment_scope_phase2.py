"""DVD Fase 2 — escopo/autorização de `content_entries` por assignment."""

import pytest

from services.content_assignment_scope import (
    ContentAssignmentScopeError,
    authorize_content_record,
    filter_visible_content_entries,
    resolve_content_assignment_for_create,
)


class FakeCursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, _limit):
        return [dict(d) for d in self.docs]


def _get(doc, path):
    value = doc
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _match_value(value, expected):
    if isinstance(expected, dict):
        for op, target in expected.items():
            if op == "$lte" and not (value is not None and value <= target):
                return False
            if op == "$gte" and not (value is not None and value >= target):
                return False
        return True
    return value == expected


def _matches(doc, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(doc, option) for option in expected):
                return False
            continue
        if not _match_value(_get(doc, key), expected):
            return False
    return True


def _project(doc, projection):
    if not projection:
        return dict(doc)
    included = [k for k, enabled in projection.items() if enabled and k != "_id"]
    if included:
        return {k: _get(doc, k) for k in included}
    excluded = {k for k, enabled in projection.items() if not enabled}
    return {k: v for k, v in doc.items() if k not in excluded}


class FakeCollection:
    def __init__(self, docs):
        self.docs = [dict(d) for d in docs]

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _matches(doc, query):
                return _project(doc, projection)
        return None

    def find(self, query, projection=None):
        docs = [_project(d, projection) for d in self.docs if _matches(d, query)]
        return FakeCursor(docs)


class FakeDb:
    def __init__(self, assignments=None, classes=None):
        self.teacher_class_assignments = FakeCollection(assignments or [])
        self.classes = FakeCollection(classes or [_klass()])


def _klass(**overrides):
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


def _assignment(aid="a-1", teacher="teacher-1", component="math", profile="regular", **overrides):
    doc = {
        "id": aid,
        "teacher_id": teacher,
        "teacher_name": f"Professor {teacher}",
        "class_id": "class-1",
        "component_id": component,
        "school_id": "school-1",
        "mantenedora_id": "tenant-1",
        "valid_from": "2026-02-01",
        "valid_until": "2026-12-20",
        "deleted": False,
        "diary_settings": {
            "enabled": True,
            "schema_version": 1,
            "profile": profile,
            "student_scope": "all",
        },
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


def _entry(**overrides):
    doc = {
        "id": "content-1",
        "assignment_id": "a-1",
        "assignment_profile_at_record": "regular",
        "assignment_schema_version_at_record": 1,
        "teacher_id": "teacher-1",
        "class_id": "class-1",
        "school_id": "school-1",
        "mantenedora_id": "tenant-1",
        "component_id": "math",
        "date": "2026-08-17",
        "deleted": False,
    }
    doc.update(overrides)
    return doc


async def _expect_error(code, coro):
    with pytest.raises(ContentAssignmentScopeError) as exc:
        await coro
    assert exc.value.code == code


@pytest.mark.asyncio
async def test_sem_dvd_ativo_preserva_caminho_legado():
    result = await resolve_content_assignment_for_create(
        FakeDb(), _user(), class_id="class-1", component_id="math", on_date="2026-08-17"
    )
    assert result.dvd_enabled is False
    assert result.assignment_id is None
    assert result.teacher_id == "teacher-1"


@pytest.mark.asyncio
async def test_vinculo_unico_do_professor_e_auto_resolvido():
    result = await resolve_content_assignment_for_create(
        FakeDb([_assignment()]),
        _user(),
        class_id="class-1",
        component_id="math",
        on_date="2026-08-17",
    )
    assert result.dvd_enabled is True
    assert result.assignment_id == "a-1"
    assert result.teacher_id == "teacher-1"


@pytest.mark.asyncio
async def test_dvd_ativo_de_outro_professor_nao_cai_no_legado():
    await _expect_error(
        "DVD_CONTENT_ASSIGNMENT_REQUIRED",
        resolve_content_assignment_for_create(
            FakeDb([_assignment(teacher="teacher-2")]),
            _user(),
            class_id="class-1",
            component_id="math",
            on_date="2026-08-17",
        ),
    )


@pytest.mark.asyncio
async def test_multiplos_vinculos_do_mesmo_professor_exigem_assignment_explicito():
    await _expect_error(
        "DVD_CONTENT_ASSIGNMENT_AMBIGUOUS",
        resolve_content_assignment_for_create(
            FakeDb([_assignment("a-1"), _assignment("a-2")]),
            _user(),
            class_id="class-1",
            component_id="math",
            on_date="2026-08-17",
        ),
    )


@pytest.mark.asyncio
async def test_assignment_explicito_de_outro_professor_e_negado():
    await _expect_error(
        "ASSIGNMENT_ACCESS_DENIED",
        resolve_content_assignment_for_create(
            FakeDb([_assignment(teacher="teacher-2")]),
            _user(),
            class_id="class-1",
            component_id="math",
            on_date="2026-08-17",
            assignment_id="a-1",
        ),
    )


@pytest.mark.asyncio
async def test_teacher_id_do_payload_nao_pode_divergir_do_assignment():
    await _expect_error(
        "CONTENT_TEACHER_MISMATCH",
        resolve_content_assignment_for_create(
            FakeDb([_assignment()]),
            _user(),
            class_id="class-1",
            component_id="math",
            on_date="2026-08-17",
            assignment_id="a-1",
            provided_teacher_id="teacher-2",
        ),
    )


@pytest.mark.asyncio
async def test_assignment_de_outro_componente_e_negado():
    await _expect_error(
        "CONTENT_COMPONENT_MISMATCH",
        resolve_content_assignment_for_create(
            FakeDb([_assignment(component="portuguese")]),
            _user(),
            class_id="class-1",
            component_id="math",
            on_date="2026-08-17",
            assignment_id="a-1",
        ),
    )


@pytest.mark.asyncio
async def test_assignment_class_wide_autoriza_componente_da_turma():
    result = await resolve_content_assignment_for_create(
        FakeDb([_assignment(component=None)]),
        _user(),
        class_id="class-1",
        component_id="math",
        on_date="2026-08-17",
        assignment_id="a-1",
    )
    assert result.dvd_enabled is True


@pytest.mark.asyncio
async def test_integrador_pode_registrar_conteudo():
    result = await resolve_content_assignment_for_create(
        FakeDb([_assignment(profile="integrator")]),
        _user(),
        class_id="class-1",
        component_id="math",
        on_date="2026-08-17",
        assignment_id="a-1",
    )
    assert result.access_context.settings.capabilities.content_enabled is True
    assert result.access_context.settings.capabilities.grades_enabled is False


@pytest.mark.asyncio
async def test_registro_legado_nao_e_submetido_ao_dvd():
    assert await authorize_content_record(FakeDb(), _user(), _entry(assignment_id=None)) is None


@pytest.mark.asyncio
async def test_dono_visualiza_registro_dvd_historico_na_data_do_vinculo():
    ctx = await authorize_content_record(
        FakeDb([_assignment(valid_until="2026-08-17")]),
        _user(),
        _entry(),
        action="view",
    )
    assert ctx.is_owner is True


@pytest.mark.asyncio
async def test_professor_nao_visualiza_registro_dvd_de_outro_professor():
    await _expect_error(
        "ASSIGNMENT_ACCESS_DENIED",
        authorize_content_record(
            FakeDb([_assignment(teacher="teacher-2")]),
            _user(),
            _entry(teacher_id="teacher-2"),
            action="view",
        ),
    )


@pytest.mark.asyncio
async def test_inconsistencia_de_proveniencia_e_bloqueada():
    await _expect_error(
        "ASSIGNMENT_SNAPSHOT_MISMATCH",
        authorize_content_record(
            FakeDb([_assignment()]),
            _user(),
            _entry(teacher_id="teacher-2"),
            action="view",
        ),
    )


@pytest.mark.asyncio
async def test_gestor_visualiza_consolidado_respeitando_escopo():
    manager = _user(id="coord-1", role="coordenador")
    ctx = await authorize_content_record(
        FakeDb([_assignment()]), manager, _entry(), action="view"
    )
    assert ctx.is_owner is False


@pytest.mark.asyncio
async def test_escrita_gerencial_exige_override_do_consumidor():
    manager = _user(id="coord-1", role="coordenador")
    db = FakeDb([_assignment()])
    await _expect_error(
        "ASSIGNMENT_ACCESS_DENIED",
        authorize_content_record(db, manager, _entry(), action="content"),
    )
    ctx = await authorize_content_record(
        db,
        manager,
        _entry(),
        action="content",
        allow_management_override=True,
    )
    assert ctx.management_override is True


@pytest.mark.asyncio
async def test_tenant_fail_closed_tambem_no_conteudo():
    await _expect_error(
        "TENANT_ACCESS_DENIED",
        authorize_content_record(
            FakeDb([_assignment()]),
            _user(mantenedora_id=None),
            _entry(),
            action="view",
        ),
    )


@pytest.mark.asyncio
async def test_filtro_preserva_legado_e_oculta_dvd_de_outro_professor():
    assignments = [_assignment("a-1"), _assignment("a-2", teacher="teacher-2")]
    entries = [
        _entry(id="legacy", assignment_id=None),
        _entry(id="mine", assignment_id="a-1"),
        _entry(id="other", assignment_id="a-2", teacher_id="teacher-2"),
    ]
    visible = await filter_visible_content_entries(FakeDb(assignments), _user(), entries)
    assert [e["id"] for e in visible] == ["legacy", "mine"]
