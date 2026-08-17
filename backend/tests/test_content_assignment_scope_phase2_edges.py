"""DVD Fase 2 — casos-limite de resolução do conteúdo."""

import pytest

from services.content_assignment_scope import (
    ContentAssignmentScopeError,
    authorize_content_record,
    resolve_content_assignment_for_create,
)


def _get(doc, path):
    value = doc
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _matches(doc, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(doc, option) for option in expected):
                return False
            continue
        value = _get(doc, key)
        if isinstance(expected, dict):
            for op, target in expected.items():
                if op == "$lte" and not (value is not None and value <= target):
                    return False
                if op == "$gte" and not (value is not None and value >= target):
                    return False
        elif value != expected:
            return False
    return True


class FakeCursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, _limit):
        return [dict(d) for d in self.docs]


class FakeCollection:
    def __init__(self, docs):
        self.docs = [dict(d) for d in docs]

    def find(self, query, projection=None):
        docs = [d for d in self.docs if _matches(d, query)]
        if projection:
            included = [k for k, enabled in projection.items() if enabled and k != "_id"]
            if included:
                docs = [{k: _get(d, k) for k in included} for d in docs]
        return FakeCursor(docs)

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _matches(doc, query):
                if not projection:
                    return dict(doc)
                included = [k for k, enabled in projection.items() if enabled and k != "_id"]
                if included:
                    return {k: _get(doc, k) for k in included}
                excluded = {k for k, enabled in projection.items() if not enabled}
                return {k: v for k, v in doc.items() if k not in excluded}
        return None


class FakeDb:
    def __init__(self, assignments, content_entries=None):
        self.teacher_class_assignments = FakeCollection(assignments)
        self.classes = FakeCollection([{
            "id": "class-1",
            "school_id": "school-1",
            "mantenedora_id": "tenant-1",
            "education_level": "fundamental_anos_iniciais",
            "grade_level": "3º Ano",
            "atendimento_programa": None,
        }])
        if content_entries is not None:
            self.content_entries = FakeCollection(content_entries)


def _assignment(aid="a-1", component="math"):
    return {
        "id": aid,
        "teacher_id": "teacher-1",
        "teacher_name": "Professor 1",
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
            "profile": "regular",
            "student_scope": "all",
        },
    }


def _user():
    return {
        "id": "teacher-1",
        "role": "professor",
        "school_ids": ["school-1"],
        "mantenedora_id": "tenant-1",
    }


@pytest.mark.asyncio
async def test_componente_omitido_nao_transforma_assignment_especifico_em_legado():
    with pytest.raises(ContentAssignmentScopeError) as exc:
        await resolve_content_assignment_for_create(
            FakeDb([_assignment(component="math")]),
            _user(),
            class_id="class-1",
            component_id=None,
            on_date="2026-08-17",
        )
    assert exc.value.code == "CONTENT_COMPONENT_MISMATCH"


@pytest.mark.asyncio
async def test_componente_omitido_com_multiplos_vinculos_proprios_e_ambiguo():
    with pytest.raises(ContentAssignmentScopeError) as exc:
        await resolve_content_assignment_for_create(
            FakeDb([
                _assignment("a-1", component="math"),
                _assignment("a-2", component="portuguese"),
            ]),
            _user(),
            class_id="class-1",
            component_id=None,
            on_date="2026-08-17",
        )
    assert exc.value.code == "DVD_CONTENT_ASSIGNMENT_AMBIGUOUS"


@pytest.mark.asyncio
async def test_assignment_class_wide_continua_auto_resolvivel_sem_componente():
    result = await resolve_content_assignment_for_create(
        FakeDb([_assignment(component=None)]),
        _user(),
        class_id="class-1",
        component_id=None,
        on_date="2026-08-17",
    )
    assert result.dvd_enabled is True
    assert result.assignment_id == "a-1"


@pytest.mark.asyncio
async def test_upsert_nao_sobrescreve_registro_com_proveniencia_corrompida():
    corrupted = {
        "id": "content-corrupt",
        "assignment_id": "a-1",
        "teacher_id": "teacher-2",
        "class_id": "class-1",
        "component_id": "math",
        "date": "2026-08-17",
        "deleted": False,
    }
    with pytest.raises(ContentAssignmentScopeError) as exc:
        await resolve_content_assignment_for_create(
            FakeDb([_assignment()], content_entries=[corrupted]),
            _user(),
            class_id="class-1",
            component_id="math",
            on_date="2026-08-17",
            assignment_id="a-1",
        )
    assert exc.value.code == "CONTENT_PROVENANCE_MISMATCH"


@pytest.mark.asyncio
async def test_registro_historico_nao_desaparece_se_assignment_mudar_componente():
    # O conteúdo foi registrado em Matemática quando esse era o componente do
    # vínculo; posteriormente a configuração administrativa do assignment mudou.
    historical = {
        "id": "content-old",
        "assignment_id": "a-1",
        "teacher_id": "teacher-1",
        "class_id": "class-1",
        "component_id": "math",
        "date": "2026-08-17",
        "deleted": False,
    }
    ctx = await authorize_content_record(
        FakeDb([_assignment(component="portuguese")]),
        _user(),
        historical,
        action="view",
    )
    assert ctx.is_owner is True
