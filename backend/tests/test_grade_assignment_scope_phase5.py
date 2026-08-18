"""Guards puros da Fase 5 — Notas/Conceitos por Vínculo Docente."""

import pytest

from services.grade_assignment_scope import (
    GradeAssignmentScopeError,
    apply_grade_field_ownership,
    changed_grade_fields,
    owned_fields_for_assignment,
    resolve_grade_assignment,
    resolve_own_grade_assignment,
)


def _get(doc, dotted):
    value = doc
    for part in dotted.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _match(doc, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_match(doc, clause) for clause in expected):
                return False
            continue
        actual = _get(doc, key)
        if isinstance(expected, dict):
            if "$lte" in expected and not (actual is not None and actual <= expected["$lte"]):
                return False
            if "$gte" in expected and not (actual is not None and actual >= expected["$gte"]):
                return False
            if "$in" in expected and actual not in expected["$in"]:
                return False
            continue
        if actual != expected:
            return False
    return True


def _project(doc, projection):
    if not projection:
        return dict(doc)
    included = [key for key, enabled in projection.items() if enabled and key != "_id"]
    if included:
        return {key: _get(doc, key) for key in included}
    return {key: value for key, value in doc.items() if projection.get(key, 1)}


class FakeCursor:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]

    async def to_list(self, _limit):
        return [dict(doc) for doc in self.docs]


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _match(doc, query):
                return _project(doc, projection)
        return None

    def find(self, query, projection=None):
        return FakeCursor([
            _project(doc, projection)
            for doc in self.docs
            if _match(doc, query)
        ])


class FakeDb:
    def __init__(self, assignments=None, klass=None):
        self.teacher_class_assignments = FakeCollection(assignments or [_assignment()])
        self.classes = FakeCollection([klass or _class()])


def _settings(profile="regular", student_scope="all"):
    return {
        "enabled": True,
        "schema_version": 1,
        "profile": profile,
        "student_scope": student_scope,
    }


def _assignment(**overrides):
    doc = {
        "id": "a-1",
        "teacher_id": "teacher-1",
        "teacher_name": "Professora Um",
        "class_id": "c-1",
        "class_name": "3º ANO A",
        "component_id": "math",
        "school_id": "s-1",
        "weekly_slots": [
            {"weekday": 1, "aula_numero": 2, "start_time": "08:00", "end_time": "08:50"},
        ],
        "valid_from": "2026-02-01",
        "valid_until": "2026-12-20",
        "deleted": False,
        "diary_settings": _settings(),
    }
    doc.update(overrides)
    return doc


def _class(**overrides):
    doc = {
        "id": "c-1",
        "school_id": "s-1",
        "mantenedora_id": "tenant-1",
        "education_level": "fundamental_anos_iniciais",
        "grade_level": "3º Ano",
        "atendimento_programa": None,
    }
    doc.update(overrides)
    return doc


def _user(**overrides):
    doc = {
        "id": "teacher-1",
        "role": "professor",
        "school_ids": ["s-1"],
        "mantenedora_id": "tenant-1",
    }
    doc.update(overrides)
    return doc


PERIODS = {
    1: ("2026-02-01", "2026-04-30"),
    2: ("2026-05-01", "2026-07-15"),
    3: ("2026-07-16", "2026-09-30"),
    4: ("2026-10-01", "2026-12-20"),
}


@pytest.mark.asyncio
async def test_regular_resolve_notas_sem_alterar_regime_avaliativo():
    context = await resolve_grade_assignment(
        FakeDb(), _user(), "a-1", class_id="c-1", course_id="math", on_date="2026-08-17"
    )
    assert context.profile.value == "regular"
    assert context.assignment_id == "a-1"
    assert context.snapshot["component_id"] == "math"
    assert context.snapshot["assignment_profile_at_record"] == "regular"


@pytest.mark.asyncio
async def test_integrator_nao_pode_lancar_notas():
    assignment = _assignment(diary_settings=_settings("integrator"))
    with pytest.raises(GradeAssignmentScopeError) as exc:
        await resolve_grade_assignment(
            FakeDb([assignment]), _user(), "a-1",
            class_id="c-1", course_id="math", on_date="2026-08-17",
        )
    assert exc.value.code == "CAPABILITY_DENIED"


@pytest.mark.asyncio
async def test_regencia_component_id_none_pode_avaliar_componente_da_turma():
    context = await resolve_grade_assignment(
        FakeDb([_assignment(component_id=None)]), _user(), "a-1",
        class_id="c-1", course_id="port", on_date="2026-08-17",
    )
    assert context.course_id == "port"
    assert context.snapshot["assignment_component_id"] is None


@pytest.mark.asyncio
async def test_componente_explicito_divergente_falha_fechado():
    with pytest.raises(GradeAssignmentScopeError) as exc:
        await resolve_grade_assignment(
            FakeDb(), _user(), "a-1",
            class_id="c-1", course_id="port", on_date="2026-08-17",
        )
    assert exc.value.code == "COMPONENT_MISMATCH"


@pytest.mark.asyncio
async def test_shared_exige_owner_oficial_explicito():
    assignment = _assignment(diary_settings=_settings("shared"))
    with pytest.raises(GradeAssignmentScopeError) as exc:
        await resolve_grade_assignment(
            FakeDb([assignment]), _user(), "a-1",
            class_id="c-1", course_id="math", on_date="2026-08-17",
        )
    assert exc.value.code == "SHARED_GRADE_OWNER_REQUIRED"


@pytest.mark.asyncio
async def test_shared_owner_unico_pode_avaliar():
    assignment = _assignment(
        diary_settings=_settings("shared"), grades_official_owner=True
    )
    context = await resolve_grade_assignment(
        FakeDb([assignment]), _user(), "a-1",
        class_id="c-1", course_id="math", on_date="2026-08-17",
    )
    assert context.profile.value == "shared"


@pytest.mark.asyncio
async def test_shared_group_continua_fail_closed_sem_lista_de_membros():
    assignment = _assignment(
        diary_settings=_settings("shared", "group"), grades_official_owner=True
    )
    with pytest.raises(GradeAssignmentScopeError) as exc:
        await resolve_grade_assignment(
            FakeDb([assignment]), _user(), "a-1",
            class_id="c-1", course_id="math", on_date="2026-08-17",
        )
    assert exc.value.code == "GRADE_GROUP_SCOPE_UNRESOLVED"


@pytest.mark.asyncio
async def test_shared_nao_owner_nao_pode_avaliar():
    assignments = [
        _assignment(id="a-1", diary_settings=_settings("shared")),
        _assignment(
            id="a-2", teacher_id="teacher-2", teacher_name="Professora Dois",
            diary_settings=_settings("shared"), grades_official_owner=True,
        ),
    ]
    with pytest.raises(GradeAssignmentScopeError) as exc:
        await resolve_grade_assignment(
            FakeDb(assignments), _user(), "a-1",
            class_id="c-1", course_id="math", on_date="2026-08-17",
        )
    assert exc.value.code == "SHARED_GRADE_OWNER_DENIED"


@pytest.mark.asyncio
async def test_auto_resolve_um_unico_vinculo_do_professor():
    context = await resolve_own_grade_assignment(
        FakeDb(), _user(), class_id="c-1", course_id="math", on_date="2026-08-17"
    )
    assert context is not None
    assert context.assignment_id == "a-1"


@pytest.mark.asyncio
async def test_auto_resolve_multiplos_vinculos_falha_ambiguo():
    assignments = [
        _assignment(id="a-1"),
        _assignment(id="a-2", component_id=None),
    ]
    with pytest.raises(GradeAssignmentScopeError) as exc:
        await resolve_own_grade_assignment(
            FakeDb(assignments), _user(), class_id="c-1", course_id="math", on_date="2026-08-17"
        )
    assert exc.value.code == "GRADE_ASSIGNMENT_AMBIGUOUS"


@pytest.mark.asyncio
async def test_campo_novo_recebe_snapshot_do_assignment():
    db = FakeDb()
    context = await resolve_grade_assignment(
        db, _user(), "a-1", class_id="c-1", course_id="math", on_date="2026-08-17"
    )
    existing = {"b1": None}
    changes = changed_grade_fields(existing, {"b1": 8.0})
    ownership = await apply_grade_field_ownership(
        db, _user(), existing, changes, context, periods=PERIODS
    )
    assert ownership["b1"]["assignment_id"] == "a-1"
    assert ownership["b1"]["teacher_id"] == "teacher-1"
    assert owned_fields_for_assignment({"grade_ownership": ownership}, "a-1") == {"b1"}


@pytest.mark.asyncio
async def test_legado_nao_nulo_nao_e_apropriado_automaticamente():
    db = FakeDb()
    context = await resolve_grade_assignment(
        db, _user(), "a-1", class_id="c-1", course_id="math", on_date="2026-08-17"
    )
    with pytest.raises(GradeAssignmentScopeError) as exc:
        await apply_grade_field_ownership(
            db, _user(), {"b1": 7.0}, {"b1": 8.0}, context, periods=PERIODS
        )
    assert exc.value.code == "GRADE_LEGACY_FIELD_REQUIRES_REVIEW"


@pytest.mark.asyncio
async def test_owner_historico_pode_atualizar_mesmo_campo_sem_trocar_autoria():
    db = FakeDb()
    context = await resolve_grade_assignment(
        db, _user(), "a-1", class_id="c-1", course_id="math", on_date="2026-08-17"
    )
    first = await apply_grade_field_ownership(
        db, _user(), {"b1": None}, {"b1": 8.0}, context, periods=PERIODS
    )
    existing = {"b1": 8.0, "grade_ownership": first}
    second = await apply_grade_field_ownership(
        db, _user(), existing, {"b1": 9.0}, context, periods=PERIODS
    )
    assert second["b1"] == first["b1"]


@pytest.mark.asyncio
async def test_professor_nao_edita_campo_de_outro_assignment():
    db = FakeDb()
    context = await resolve_grade_assignment(
        db, _user(), "a-1", class_id="c-1", course_id="math", on_date="2026-08-17"
    )
    other_owner = dict(context.snapshot)
    other_owner["assignment_id"] = "a-2"
    existing = {"b1": 8.0, "grade_ownership": {"b1": other_owner}}
    with pytest.raises(GradeAssignmentScopeError) as exc:
        await apply_grade_field_ownership(
            db, _user(), existing, {"b1": 9.0}, context, periods=PERIODS
        )
    assert exc.value.code == "GRADE_FIELD_OWNED_BY_OTHER_ASSIGNMENT"


@pytest.mark.asyncio
async def test_vinculo_sem_intersecao_com_bimestre_nao_pode_reivindicar_campo():
    assignment = _assignment(valid_from="2026-07-16")
    db = FakeDb([assignment])
    context = await resolve_grade_assignment(
        db, _user(), "a-1", class_id="c-1", course_id="math", on_date="2026-08-17"
    )
    with pytest.raises(GradeAssignmentScopeError) as exc:
        await apply_grade_field_ownership(
            db, _user(), {"b1": None}, {"b1": 8.0}, context, periods=PERIODS
        )
    assert exc.value.code == "GRADE_PERIOD_OUTSIDE_ASSIGNMENT"


@pytest.mark.asyncio
async def test_null_para_null_nao_cria_autoria_artificial():
    db = FakeDb()
    context = await resolve_grade_assignment(
        db, _user(), "a-1", class_id="c-1", course_id="math", on_date="2026-08-17"
    )
    ownership = await apply_grade_field_ownership(
        db, _user(), {"b1": None}, {}, context, periods=PERIODS
    )
    assert ownership == {}
