"""P0 Auth — autoria global da auditoria em impersonação."""

from types import SimpleNamespace

import pytest

from services import impersonation_audit_policy as policy


class FakeAudit:
    def __init__(self):
        self.calls = []

    async def log(self, *args, **kwargs):
        self.calls.append((args, kwargs))


def fake_request():
    return SimpleNamespace(
        cookies={"sigesc_access": "signed-token"},
        headers={},
        query_params={},
    )


def impersonation_payload():
    return {
        "type": "access",
        "sub": "target-1",
        "email": "target@example.org",
        "role": "professor",
        "impersonation": True,
        "impersonation_session_id": "session-1",
        "impersonation_actor_id": "super-1",
        "impersonation_actor_email": "super@example.org",
        "impersonation_actor_name": "Super Admin Fixture",
        "impersonation_subject_name": "Usuário Fixture",
    }


@pytest.mark.asyncio
async def test_request_assinado_forca_super_admin_mesmo_com_user_reconstruido(monkeypatch):
    monkeypatch.setattr(policy, "decode_token", lambda token: impersonation_payload())
    audit = FakeAudit()
    policy.install_impersonation_request_audit_policy(audit)

    # Simula uma rota que descartou os metadados de impersonação e reconstruiu user.
    await audit.log(
        action="update",
        collection="grades",
        user={"id": "target-1", "email": "target@example.org", "role": "professor"},
        request=fake_request(),
        description="Alterou nota",
    )

    _, kwargs = audit.calls[-1]
    assert kwargs["user"] == {
        "id": "super-1",
        "email": "super@example.org",
        "role": "super_admin",
        "full_name": "Super Admin Fixture",
    }
    meta = kwargs["extra_data"]["impersonation"]
    assert meta["session_id"] == "session-1"
    assert meta["subject_user_id"] == "target-1"
    assert meta["subject_role"] == "professor"
    assert kwargs["description"].startswith("[IMPERSONAÇÃO]")


@pytest.mark.asyncio
async def test_request_normal_nao_altera_autoria(monkeypatch):
    monkeypatch.setattr(
        policy,
        "decode_token",
        lambda token: {"type": "access", "sub": "user-1", "role": "professor"},
    )
    audit = FakeAudit()
    policy.install_impersonation_request_audit_policy(audit)
    original_user = {"id": "user-1", "email": "user@example.org", "role": "professor"}

    await audit.log(
        action="update",
        collection="grades",
        user=original_user,
        request=fake_request(),
        description="Alterou nota",
    )

    _, kwargs = audit.calls[-1]
    assert kwargs["user"] == original_user
    assert kwargs.get("extra_data") is None
    assert kwargs["description"] == "Alterou nota"


@pytest.mark.asyncio
async def test_chamada_sem_request_mantem_compatibilidade(monkeypatch):
    monkeypatch.setattr(policy, "decode_token", lambda token: impersonation_payload())
    audit = FakeAudit()
    policy.install_impersonation_request_audit_policy(audit)
    original_user = {"id": "user-1", "role": "professor"}

    await audit.log(
        action="update",
        collection="grades",
        user=original_user,
        description="Alterou nota",
    )

    _, kwargs = audit.calls[-1]
    assert kwargs["user"] == original_user
