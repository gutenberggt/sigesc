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
        cookies={"sigesc_access": "signed-token-nao-usado-pela-politica"},
        headers={},
        query_params={},
        state=SimpleNamespace(),
    )


def effective_impersonated_user():
    return {
        "id": "target-1",
        "email": "target@example.org",
        "role": "professor",
        "full_name": "Usuário Fixture",
        "impersonation": True,
        "impersonation_session_id": "session-1",
        "actor_id": "super-1",
        "actor_email": "super@example.org",
        "actor_name": "Super Admin Fixture",
        "subject_name": "Usuário Fixture",
    }


@pytest.mark.asyncio
async def test_primeira_auditoria_autenticada_fixa_contexto_no_request_state():
    audit = FakeAudit()
    policy.install_impersonation_request_audit_policy(audit)
    request = fake_request()

    await audit.log(
        action="access",
        collection="impersonation",
        user=effective_impersonated_user(),
        request=request,
        description="Acesso autenticado",
    )

    context = getattr(request.state, policy.REQUEST_STATE_KEY)
    assert context["actor_id"] == "super-1"
    assert context["subject_user_id"] == "target-1"

    _, kwargs = audit.calls[-1]
    assert kwargs["user"]["id"] == "super-1"
    assert kwargs["user"]["role"] == "super_admin"
    assert kwargs["extra_data"]["impersonation"]["subject_role"] == "professor"


@pytest.mark.asyncio
async def test_user_reconstruido_continua_atribuido_ao_super_admin_na_mesma_request():
    audit = FakeAudit()
    policy.install_impersonation_request_audit_policy(audit)
    request = fake_request()

    # Primeira passagem corresponde ao contexto enriquecido pelo AuthMiddleware.
    await audit.log(
        action="access",
        collection="impersonation",
        user=effective_impersonated_user(),
        request=request,
        description="Acesso autenticado",
    )

    # Depois, uma rota pode reconstruir/encolher `user`; request.state é a SSoT.
    await audit.log(
        action="update",
        collection="grades",
        user={"id": "target-1", "email": "target@example.org", "role": "professor"},
        request=request,
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
async def test_request_totalmente_posicional_reutiliza_contexto_autenticado():
    audit = FakeAudit()
    policy.install_impersonation_request_audit_policy(audit)
    request = fake_request()

    await audit.log(
        action="access",
        collection="impersonation",
        user=effective_impersonated_user(),
        request=request,
        description="Acesso autenticado",
    )

    await audit.log(
        "update",
        "grades",
        {"id": "target-1", "email": "target@example.org", "role": "professor"},
        request,
        "grade-1",
        "Alterou nota",
        {"b1": 7.0},
        {"b1": 8.0},
        "school-1",
        "Escola Fixture",
        2026,
        {"origin": "fixture"},
    )

    args, kwargs = audit.calls[-1]
    assert kwargs == {}
    assert args[2]["id"] == "super-1"
    assert args[2]["role"] == "super_admin"
    assert args[5].startswith("[IMPERSONAÇÃO]")
    assert args[11]["origin"] == "fixture"
    assert args[11]["impersonation"]["subject_user_id"] == "target-1"


@pytest.mark.asyncio
async def test_token_bruto_sem_contexto_autenticado_nao_promove_autoria():
    audit = FakeAudit()
    policy.install_impersonation_request_audit_policy(audit)
    request = fake_request()
    original_user = {"id": "public-user", "email": "public@example.org", "role": "unknown"}

    await audit.log(
        action="access",
        collection="public-resource",
        user=original_user,
        request=request,
        description="Acesso público",
    )

    _, kwargs = audit.calls[-1]
    assert kwargs["user"] == original_user
    assert kwargs.get("extra_data") is None
    assert not hasattr(request.state, policy.REQUEST_STATE_KEY)


@pytest.mark.asyncio
async def test_request_normal_nao_altera_autoria():
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
async def test_chamada_sem_request_mantem_compatibilidade():
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
