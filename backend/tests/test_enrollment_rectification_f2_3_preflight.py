"""Preflight estrutural da F2.3 sem qualquer write acadêmico.

Estes testes provam que a execução da saga falha antes de tocar no banco quando
a feature flag operacional não está explicitamente habilitada.
"""

import pytest

from services.enrollment_rectification_saga import (
    EXECUTION_FLAG,
    RectificationSagaError,
    execute_rectification_saga,
    saga_execution_enabled,
)


class _ForbiddenDB:
    """Falha o teste caso a execução tente qualquer acesso ao banco."""

    def __getitem__(self, key):
        raise AssertionError(f"acesso indevido ao banco com feature flag off: {key}")

    def __getattr__(self, name):
        raise AssertionError(f"acesso indevido ao banco com feature flag off: {name}")


@pytest.mark.parametrize("configured", [None, "", "false", "FALSE", "0", "no"])
def test_saga_execution_flag_is_fail_closed_by_default(monkeypatch, configured):
    if configured is None:
        monkeypatch.delenv(EXECUTION_FLAG, raising=False)
    else:
        monkeypatch.setenv(EXECUTION_FLAG, configured)

    assert saga_execution_enabled() is False


def test_saga_execution_flag_requires_explicit_true(monkeypatch):
    monkeypatch.setenv(EXECUTION_FLAG, "  TrUe  ")
    assert saga_execution_enabled() is True


@pytest.mark.asyncio
async def test_execute_fails_closed_before_any_database_access(monkeypatch):
    monkeypatch.delenv(EXECUTION_FLAG, raising=False)

    with pytest.raises(RectificationSagaError) as caught:
        await execute_rectification_saga(
            _ForbiddenDB(),
            prepare_id="preflight-prepare-id-00000000000000000001",
            tenant_id="tenant-preflight",
            actor={"id": "operator-preflight", "role": "super_admin"},
            document_acknowledgement="preflight-acknowledgement-not-used",
        )

    assert caught.value.code == "RECTIFICATION_EXECUTION_DISABLED"
    assert caught.value.status_code == 503
