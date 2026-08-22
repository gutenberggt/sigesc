"""PR #83 — regressão P0 para conteúdo anterior ao cutover DVD.

Caso real de produção reproduzido como contrato:
Ivanilde Freire Batista da Silva -> 3º/4º/5º ANO -> Arte -> 01/06/2026,
com teacher_class_assignment DVD iniciado em 18/08/2026.
"""

from pathlib import Path

import pytest

from services.content_assignment_scope import resolve_content_assignment_for_create


TEACHER_ID = "3dfbbfad-3582-4ddc-9964-e93fc5265d0c"
CLASS_ID = "c90830dc-ae94-4412-811e-e98e6a5dfc7a"
ARTE_ID = "401e43d4-5dd5-4158-a082-265363412893"
ASSIGNMENT_ID = "77fd25ee-5157-54d0-9806-81dae056d7b3"
SCHOOL_ID = "44bde9d5-67c0-4aeb-98b9-f74b3896dca6"
TENANT_ID = "fb68737e-a7c5-4877-8c07-8a237f464f4f"


class FakeCursor:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]

    async def to_list(self, _limit):
        return [dict(doc) for doc in self.docs]


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
    included = [key for key, enabled in projection.items() if enabled and key != "_id"]
    if included:
        return {key: _get(doc, key) for key in included}
    excluded = {key for key, enabled in projection.items() if not enabled}
    return {key: value for key, value in doc.items() if key not in excluded}


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _matches(doc, query):
                return _project(doc, projection)
        return None

    def find(self, query, projection=None):
        return FakeCursor([
            _project(doc, projection)
            for doc in self.docs
            if _matches(doc, query)
        ])


class FakeDb:
    def __init__(self):
        self.teacher_class_assignments = FakeCollection([{
            "id": ASSIGNMENT_ID,
            "teacher_id": TEACHER_ID,
            "teacher_name": "Ivanilde Freire Batista da Silva",
            "class_id": CLASS_ID,
            "class_name": "3º/4º/5º ANO",
            "school_id": SCHOOL_ID,
            "mantenedora_id": TENANT_ID,
            "component_id": ARTE_ID,
            "weekly_slots": [{
                "weekday": 5,
                "aula_numero": 1,
                "start_time": "07:00",
                "end_time": "08:00",
            }],
            "valid_from": "2026-08-18",
            "valid_until": None,
            "source": "import",
            "deleted": False,
            "diary_settings": {
                "enabled": True,
                "schema_version": 1,
                "profile": "regular",
                "student_scope": "all",
            },
        }])
        self.classes = FakeCollection([{
            "id": CLASS_ID,
            "school_id": SCHOOL_ID,
            "mantenedora_id": TENANT_ID,
            "education_level": "fundamental_anos_iniciais",
            "grade_level": "3º ANO",
            "is_multi_grade": True,
            "series": ["3º ANO", "4º ANO", "5º ANO"],
            "atendimento_programa": "",
        }])
        self.content_entries = FakeCollection([])


def _user():
    return {
        "id": TEACHER_ID,
        "role": "professor",
        "school_ids": [SCHOOL_ID],
        "mantenedora_id": TENANT_ID,
    }


@pytest.mark.asyncio
async def test_ivanilde_arte_0106_resolve_backfill_sem_retroagir_vinculo():
    result = await resolve_content_assignment_for_create(
        FakeDb(),
        _user(),
        class_id=CLASS_ID,
        component_id=ARTE_ID,
        on_date="2026-06-01",
    )

    assert result.dvd_enabled is True
    assert result.assignment_id == ASSIGNMENT_ID
    assert result.teacher_id == TEACHER_ID
    assert result.historical_backfill is True
    assert result.access_context.assignment["valid_from"] == "2026-08-18"
    assert result.access_context.settings.capabilities.content_enabled is True


@pytest.mark.asyncio
async def test_ivanilde_arte_0106_assignment_explicito_tambem_autoriza_backfill():
    result = await resolve_content_assignment_for_create(
        FakeDb(),
        _user(),
        class_id=CLASS_ID,
        component_id=ARTE_ID,
        on_date="2026-06-01",
        assignment_id=ASSIGNMENT_ID,
    )

    assert result.assignment_id == ASSIGNMENT_ID
    assert result.historical_backfill is True
    assert result.access_context.assignment["valid_from"] == "2026-08-18"


@pytest.mark.asyncio
async def test_data_do_cutover_continua_fluxo_dvd_normal():
    result = await resolve_content_assignment_for_create(
        FakeDb(),
        _user(),
        class_id=CLASS_ID,
        component_id=ARTE_ID,
        on_date="2026-08-18",
    )

    assert result.dvd_enabled is True
    assert result.assignment_id == ASSIGNMENT_ID
    assert result.historical_backfill is False


def test_frontend_intercepta_check_create_e_copy_historicos_antes_do_legado():
    resolver = Path(
        "../frontend/src/services/contentDvdHistoricalBackfillResolver.js"
    ).read_text(encoding="utf-8")
    hook = Path("../frontend/src/hooks/useDiaryPrefill.js").read_text(encoding="utf-8")

    assert "target < String(item.valid_from).slice(0, 10)" in resolver
    assert "isCheckDateUrl(url) && method === 'get'" in resolver
    assert "method === 'post' && /\\/learning-objects\\/?$/" in resolver
    assert "isCopyUrl(url) && method === 'post'" in resolver
    assert "payload.assignment_id = historical.assignment_id" in resolver
    assert "config.url = canonicalBase" in resolver
    assert "contentDvdHistoricalBackfillResolver" in hook
