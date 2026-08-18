"""Guards puros da Fase 4 — Frequência por Vínculo Docente."""

import pytest

from services.attendance_assignment_scope import (
    ASSIGNMENT_SESSION_KEY_SCOPE,
    DOCUMENTARY_ATTENDANCE_COLLECTION,
    OFFICIAL_ATTENDANCE_COLLECTION,
    AttendanceAssignmentScopeError,
    attendance_provenance_fields,
    authorize_historical_attendance,
    logical_attendance_query,
    professor_has_active_dvd_for_class,
    resolve_attendance_assignment,
    resolve_session_aula_numero,
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


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _match(doc, query):
                return _project(doc, projection)
        return None


class FakeDb:
    def __init__(self, assignment=None, klass=None):
        self.teacher_class_assignments = FakeCollection([assignment or _assignment()])
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
        "shift": "integral",
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


@pytest.mark.asyncio
async def test_regular_preserva_class_daily_oficial_sem_fragmentar_componente():
    context = await resolve_attendance_assignment(
        FakeDb(), _user(), "a-1", class_id="c-1", on_date="2026-08-17"
    )
    assert context.profile.value == "regular"
    assert context.attendance_mode.value == "class_daily"
    assert context.attendance_purpose.value == "official"
    assert context.storage_collection == OFFICIAL_ATTENDANCE_COLLECTION
    assert context.effective_course_id is None
    assert resolve_session_aula_numero(context, None) is None
    query = logical_attendance_query(context, on_date="2026-08-17", aula_numero=None)
    assert query == {"class_id": "c-1", "date": "2026-08-17", "course_id": None}
    assert "assignment_id" not in query


@pytest.mark.asyncio
async def test_integrator_e_fisicamente_documental_e_pdf_only():
    assignment = _assignment(diary_settings=_settings("integrator"))
    context = await resolve_attendance_assignment(
        FakeDb(assignment=assignment), _user(), "a-1", on_date="2026-08-17"
    )
    assert context.attendance_mode.value == "assignment_session"
    assert context.attendance_purpose.value == "pdf_only"
    assert context.storage_collection == DOCUMENTARY_ATTENDANCE_COLLECTION
    assert context.effective_course_id == "math"
    assert resolve_session_aula_numero(context, None) == 2


@pytest.mark.asyncio
async def test_shared_all_e_assignment_session_oficial():
    assignment = _assignment(diary_settings=_settings("shared"))
    context = await resolve_attendance_assignment(
        FakeDb(assignment=assignment), _user(), "a-1", on_date="2026-08-17"
    )
    aula = resolve_session_aula_numero(context, None)
    query = logical_attendance_query(context, on_date="2026-08-17", aula_numero=aula)
    assert context.storage_collection == OFFICIAL_ATTENDANCE_COLLECTION
    assert context.attendance_purpose.value == "official"
    assert query["assignment_id"] == "a-1"
    assert query["course_id"] == "math"
    assert query["aula_numero"] == 2
    assert query["attendance_key_scope"] == ASSIGNMENT_SESSION_KEY_SCOPE


@pytest.mark.asyncio
async def test_shared_group_falha_fechado_sem_inventar_membros():
    assignment = _assignment(diary_settings=_settings("shared", "group"))
    with pytest.raises(AttendanceAssignmentScopeError) as exc:
        await resolve_attendance_assignment(
            FakeDb(assignment=assignment), _user(), "a-1", on_date="2026-08-17"
        )
    assert exc.value.code == "ATTENDANCE_GROUP_SCOPE_UNRESOLVED"


@pytest.mark.asyncio
async def test_multiplos_slots_exigem_sessao_explicita():
    assignment = _assignment(
        diary_settings=_settings("integrator"),
        weekly_slots=[
            {"weekday": 1, "aula_numero": 2, "start_time": "08:00", "end_time": "08:50"},
            {"weekday": 1, "aula_numero": 4, "start_time": "10:00", "end_time": "10:50"},
        ],
    )
    context = await resolve_attendance_assignment(
        FakeDb(assignment=assignment), _user(), "a-1", on_date="2026-08-17"
    )
    assert [slot["aula_numero"] for slot in context.session_slots] == [2, 4]
    with pytest.raises(AttendanceAssignmentScopeError) as exc:
        resolve_session_aula_numero(context, None)
    assert exc.value.code == "ASSIGNMENT_SESSION_SLOT_REQUIRED"
    assert resolve_session_aula_numero(context, 4) == 4


@pytest.mark.asyncio
async def test_slot_forjado_e_rejeitado():
    assignment = _assignment(diary_settings=_settings("shared"))
    context = await resolve_attendance_assignment(
        FakeDb(assignment=assignment), _user(), "a-1", on_date="2026-08-17"
    )
    with pytest.raises(AttendanceAssignmentScopeError) as exc:
        resolve_session_aula_numero(context, 9)
    assert exc.value.code == "ASSIGNMENT_SESSION_SLOT_INVALID"


@pytest.mark.asyncio
async def test_proveniencia_deriva_do_vinculo_e_nao_do_cliente():
    assignment = _assignment(diary_settings=_settings("integrator"))
    context = await resolve_attendance_assignment(
        FakeDb(assignment=assignment), _user(), "a-1", on_date="2026-08-17"
    )
    fields = attendance_provenance_fields(context, aula_numero=2)
    assert fields["assignment_id"] == "a-1"
    assert fields["teacher_id"] == "teacher-1"
    assert fields["class_id"] == "c-1"
    assert fields["component_id"] == "math"
    assert fields["attendance_mode"] == "assignment_session"
    assert fields["attendance_purpose"] == "pdf_only"
    assert fields["assignment_profile_at_record"] == "integrator"


@pytest.mark.asyncio
async def test_historico_nao_pode_reclassificar_pdf_only_como_oficial():
    assignment = _assignment(diary_settings=_settings("integrator"))
    db = FakeDb(assignment=assignment)
    context = await resolve_attendance_assignment(
        db, _user(), "a-1", on_date="2026-08-17"
    )
    snapshot = attendance_provenance_fields(context, aula_numero=2)
    historical = await authorize_historical_attendance(db, _user(), snapshot)
    assert historical.attendance_purpose.value == "pdf_only"
    tampered = {**snapshot, "attendance_purpose": "official"}
    with pytest.raises(AttendanceAssignmentScopeError) as exc:
        await authorize_historical_attendance(db, _user(), tampered)
    assert exc.value.code == "ATTENDANCE_PROVENANCE_MISMATCH"


@pytest.mark.asyncio
async def test_tenant_incompativel_falha_antes_de_criar_contexto():
    with pytest.raises(AttendanceAssignmentScopeError) as exc:
        await resolve_attendance_assignment(
            FakeDb(), _user(mantenedora_id="tenant-2"), "a-1", on_date="2026-08-17"
        )
    assert exc.value.code == "TENANT_ACCESS_DENIED"


@pytest.mark.asyncio
async def test_aee_permanece_fora_da_frequencia_dvd():
    db = FakeDb(klass=_class(atendimento_programa="aee"))
    with pytest.raises(AttendanceAssignmentScopeError) as exc:
        await resolve_attendance_assignment(db, _user(), "a-1", on_date="2026-08-17")
    assert exc.value.code == "CLASS_OUT_OF_DVD_SCOPE"


@pytest.mark.asyncio
async def test_professor_com_vinculo_dvd_ativo_dispara_guard_anti_bypass():
    assert await professor_has_active_dvd_for_class(
        FakeDb(), _user(), class_id="c-1", on_date="2026-08-17"
    ) is True


@pytest.mark.asyncio
async def test_gestao_nao_e_bloqueada_pelo_guard_anti_bypass_do_professor():
    assert await professor_has_active_dvd_for_class(
        FakeDb(), _user(role="admin"), class_id="c-1", on_date="2026-08-17"
    ) is False
