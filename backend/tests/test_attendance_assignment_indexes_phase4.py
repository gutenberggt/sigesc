"""Guards dos índices físicos da Frequência DVD Fase 4."""

import pytest

from services.attendance_assignment_scope import (
    ASSIGNMENT_SESSION_KEY_SCOPE,
    ensure_attendance_assignment_indexes,
)


class FakeIndexCollection:
    def __init__(self, info=None):
        self.info = dict(info or {})
        self.created = []
        self.dropped = []

    async def index_information(self):
        return dict(self.info)

    async def drop_index(self, name):
        self.dropped.append(name)
        self.info.pop(name, None)

    async def create_index(self, keys, **kwargs):
        self.created.append((keys, kwargs))
        self.info[kwargs.get("name")] = {
            "key": keys,
            "partialFilterExpression": kwargs.get("partialFilterExpression"),
        }
        return kwargs.get("name")


class FakeDb:
    def __init__(self, attendance_info=None):
        self.attendance = FakeIndexCollection(attendance_info)
        self.attendance_documentary = FakeIndexCollection()

    def __getitem__(self, name):
        return getattr(self, name)


@pytest.mark.asyncio
async def test_indice_legado_e_recriado_com_filtro_que_exclui_assignment_session():
    db = FakeDb({
        "ux_attendance_class_date_course_aula": {
            "partialFilterExpression": None,
        }
    })
    await ensure_attendance_assignment_indexes(db)
    assert "ux_attendance_class_date_course_aula" in db.attendance.dropped
    recreated = next(
        kwargs for _keys, kwargs in db.attendance.created
        if kwargs.get("name") == "ux_attendance_class_date_course_aula"
    )
    assert recreated["unique"] is True
    assert recreated["partialFilterExpression"] == {"attendance_key_scope": None}


@pytest.mark.asyncio
async def test_assignment_session_oficial_tem_unicidade_por_assignment():
    db = FakeDb()
    await ensure_attendance_assignment_indexes(db)
    assignment_idx = next(
        (keys, kwargs) for keys, kwargs in db.attendance.created
        if kwargs.get("name") == "ux_attendance_assignment_session"
    )
    keys, kwargs = assignment_idx
    assert ("assignment_id", 1) in keys
    assert kwargs["unique"] is True
    assert kwargs["partialFilterExpression"] == {
        "attendance_key_scope": ASSIGNMENT_SESSION_KEY_SCOPE
    }


@pytest.mark.asyncio
async def test_pdf_only_tem_colecao_documental_e_indice_proprio():
    db = FakeDb()
    await ensure_attendance_assignment_indexes(db)
    names = {kwargs.get("name") for _keys, kwargs in db.attendance_documentary.created}
    assert "ux_attendance_documentary_assignment_session" in names
    assert "ix_attendance_documentary_tenant_assignment_date" in names


@pytest.mark.asyncio
async def test_indice_legado_ja_evoluido_nao_e_dropado_novamente():
    db = FakeDb({
        "ux_attendance_class_date_course_aula": {
            "partialFilterExpression": {"attendance_key_scope": None},
        }
    })
    await ensure_attendance_assignment_indexes(db)
    assert db.attendance.dropped == []
