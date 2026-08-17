"""DVD Fase 2 — evolução idempotente dos índices de conteúdo."""

import pytest

from startup.indexes import _ensure_content_entry_logical_indexes


class FakeContentEntries:
    def __init__(self, info):
        self.info = info
        self.dropped = []
        self.created = []

    async def index_information(self):
        return self.info

    async def drop_index(self, name):
        self.dropped.append(name)

    async def create_index(self, keys, **kwargs):
        self.created.append((keys, kwargs))
        return kwargs.get("name")


class FakeDb:
    def __init__(self, info):
        self.content_entries = FakeContentEntries(info)


@pytest.mark.asyncio
async def test_indice_antigo_e_evoluido_uma_vez():
    db = FakeDb({
        "ux_content_entry_logical": {
            "partialFilterExpression": {"deleted": False}
        }
    })
    await _ensure_content_entry_logical_indexes(db)
    assert db.content_entries.dropped == ["ux_content_entry_logical"]
    names = [kwargs["name"] for _, kwargs in db.content_entries.created]
    assert names == [
        "ux_content_entry_logical",
        "ux_content_entry_assignment",
        "ix_content_assignment_date",
    ]


@pytest.mark.asyncio
async def test_indice_legado_ja_evoluido_nao_e_dropado_novamente():
    desired = {"deleted": False, "assignment_id": None}
    db = FakeDb({
        "ux_content_entry_logical": {
            "partialFilterExpression": desired
        }
    })
    await _ensure_content_entry_logical_indexes(db)
    assert db.content_entries.dropped == []


@pytest.mark.asyncio
async def test_unicidade_dvd_e_por_assignment_nao_por_teacher():
    db = FakeDb({})
    await _ensure_content_entry_logical_indexes(db)
    specs = {kwargs["name"]: (keys, kwargs) for keys, kwargs in db.content_entries.created}

    legacy_keys, legacy = specs["ux_content_entry_logical"]
    assert ("teacher_id", 1) in legacy_keys
    assert legacy["unique"] is True
    assert legacy["partialFilterExpression"] == {"deleted": False, "assignment_id": None}

    dvd_keys, dvd = specs["ux_content_entry_assignment"]
    assert ("assignment_id", 1) in dvd_keys
    assert ("teacher_id", 1) not in dvd_keys
    assert dvd["unique"] is True
    assert dvd["partialFilterExpression"] == {
        "deleted": False,
        "assignment_id": {"$gt": ""},
    }
