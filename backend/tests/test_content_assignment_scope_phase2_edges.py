"""DVD Fase 2 — casos-limite de resolução do conteúdo."""

import pytest

from services.content_assignment_scope import (
    ContentAssignmentScopeError,
    resolve_content_assignment_for_create,
)
from tests.test_content_assignment_scope_phase2 import FakeDb, _assignment, _user


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
