"""DVD Fase 3 — leitura segura de Meus Diários.

Testes unitários puros: sem HTTP e sem Mongo real.
"""

import pytest

from services.teacher_diaries import list_teacher_diaries


def _get(doc, dotted):
    value = doc
    for part in dotted.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _matches(doc, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(doc, clause) for clause in expected):
                return False
            continue
        actual = _get(doc, key)
        if isinstance(expected, dict):
            if "$lte" in expected and not (actual is not None and actual <= expected["$lte"]):
                return False
            if "$gte" in expected and not (actual is not None and actual >= expected["$gte"]):
                return False
            continue
        if actual != expected:
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


class FakeCursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, _limit):
        return [dict(d) for d in self.docs]


class FakeCollection:
    def __init__(self, docs):
        self.docs = [dict(d) for d in docs]

    def find(self, query, projection=None):
        return FakeCursor([_project(d, projection) for d in self.docs if _matches(d, query)])

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _matches(doc, query):
                return _project(doc, projection)
        return None


class FakeDb:
    def __init__(self, assignments=None, classes=None, schools=None, courses=None):
        self.teacher_class_assignments = FakeCollection(assignments or [])
        self.classes = FakeCollection(classes or [])
        self.schools = FakeCollection(schools or [])
        self.courses = FakeCollection(courses or [])


def _settings(profile="regular", *, enabled=True, student_scope="all"):
    return {
        "enabled": enabled,
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
        "valid_from": "2026-02-01",
        "valid_until": "2026-12-20",
        "is_substitute": False,
        "deleted": False,
        "diary_settings": _settings(),
    }
    doc.update(overrides)
    return doc


def _class(**overrides):
    doc = {
        "id": "c-1",
        "name": "3º ANO A",
        "school_id": "s-1",
        "mantenedora_id": "tenant-1",
        "academic_year": 2026,
        "education_level": "fundamental_anos_iniciais",
        "grade_level": "3º Ano",
        "shift": "integral",
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


def _db(assignment=None, klass=None):
    return FakeDb(
        assignments=[assignment or _assignment()],
        classes=[klass or _class()],
        schools=[{"id": "s-1", "name": "Escola Municipal"}],
        courses=[{"id": "math", "name": "Matemática"}],
    )


@pytest.mark.asyncio
async def test_lista_somente_diario_vigente_do_professor_logado():
    result = await list_teacher_diaries(
        _db(), _user(), academic_year=2026, reference_date="2026-08-17"
    )
    assert result["total"] == 1
    item = result["items"][0]
    assert item["assignment_id"] == "a-1"
    assert item["teacher_id"] == "teacher-1"
    assert item["class_name"] == "3º ANO A"
    assert item["school_name"] == "Escola Municipal"
    assert item["component_name"] == "Matemática"


@pytest.mark.asyncio
async def test_regular_expoe_capacidades_derivadas_do_contrato():
    result = await list_teacher_diaries(_db(), _user(), reference_date="2026-08-17")
    caps = result["items"][0]["capabilities"]
    assert caps == {
        "content_enabled": True,
        "attendance_enabled": True,
        "attendance_required": True,
        "attendance_mode": "class_daily",
        "attendance_purpose": "official",
        "grades_enabled": True,
    }


@pytest.mark.asyncio
async def test_integrador_expoe_frequencia_pdf_only_e_sem_notas():
    assignment = _assignment(diary_settings=_settings("integrator"))
    result = await list_teacher_diaries(
        _db(assignment=assignment), _user(), reference_date="2026-08-17"
    )
    item = result["items"][0]
    assert item["profile"] == "integrator"
    assert item["capabilities"]["attendance_required"] is False
    assert item["capabilities"]["attendance_mode"] == "assignment_session"
    assert item["capabilities"]["attendance_purpose"] == "pdf_only"
    assert item["capabilities"]["grades_enabled"] is False


@pytest.mark.asyncio
async def test_shared_preserva_student_scope_group():
    assignment = _assignment(diary_settings=_settings("shared", student_scope="group"))
    result = await list_teacher_diaries(
        _db(assignment=assignment), _user(), reference_date="2026-08-17"
    )
    assert result["items"][0]["profile"] == "shared"
    assert result["items"][0]["student_scope"] == "group"


@pytest.mark.asyncio
async def test_aee_e_fase_fora_do_escopo_sao_fail_closed():
    result = await list_teacher_diaries(
        _db(klass=_class(atendimento_programa="aee")),
        _user(),
        reference_date="2026-08-17",
    )
    assert result["items"] == []
    assert result["blocked_total"] == 1


@pytest.mark.asyncio
async def test_tenant_incompativel_nao_aparece_no_dashboard():
    result = await list_teacher_diaries(
        _db(), _user(mantenedora_id="tenant-2"), reference_date="2026-08-17"
    )
    assert result["items"] == []
    assert result["blocked_total"] == 1


@pytest.mark.asyncio
async def test_filtro_de_ano_letivo_nao_reclassifica_vinculo():
    result = await list_teacher_diaries(
        _db(), _user(), academic_year=2025, reference_date="2026-08-17"
    )
    assert result["items"] == []
    assert result["blocked_total"] == 0


@pytest.mark.asyncio
async def test_vinculo_desabilitado_ou_expirado_nem_e_candidato():
    disabled = _assignment(id="a-disabled", diary_settings=_settings(enabled=False))
    expired = _assignment(id="a-expired", valid_until="2026-07-31")
    db = FakeDb(
        assignments=[disabled, expired],
        classes=[_class()],
        schools=[{"id": "s-1", "name": "Escola Municipal"}],
        courses=[{"id": "math", "name": "Matemática"}],
    )
    result = await list_teacher_diaries(db, _user(), reference_date="2026-08-17")
    assert result["total"] == 0
    assert result["blocked_total"] == 0


@pytest.mark.asyncio
async def test_assignment_de_outro_professor_nunca_entra_na_consulta():
    other = _assignment(id="a-other", teacher_id="teacher-2")
    db = FakeDb(
        assignments=[other],
        classes=[_class()],
        schools=[{"id": "s-1", "name": "Escola Municipal"}],
        courses=[{"id": "math", "name": "Matemática"}],
    )
    result = await list_teacher_diaries(db, _user(), reference_date="2026-08-17")
    assert result["items"] == []
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_assignment_class_wide_e_representado_sem_inventar_componente():
    assignment = _assignment(component_id=None)
    result = await list_teacher_diaries(
        _db(assignment=assignment), _user(), reference_date="2026-08-17"
    )
    item = result["items"][0]
    assert item["component_id"] is None
    assert item["component_name"] is None


@pytest.mark.asyncio
async def test_usuario_sem_id_falha_fechado_com_lista_vazia():
    result = await list_teacher_diaries(_db(), {"role": "professor"}, reference_date="2026-08-17")
    assert result == {"items": [], "total": 0, "blocked_total": 0}
