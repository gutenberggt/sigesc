"""P0 Auth — impersonação segura pelo Super Administrador."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

from routers import auth_impersonation as imp


BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
AUTH_SOURCE = (BACKEND / "routers" / "auth.py").read_text(encoding="utf-8")
IMP_SOURCE = (BACKEND / "routers" / "auth_impersonation.py").read_text(encoding="utf-8")
AUTH_CONTEXT = (REPO / "frontend" / "src" / "contexts" / "AuthContext.js").read_text(encoding="utf-8")
USERS_UI = (REPO / "frontend" / "src" / "pages" / "Users.js").read_text(encoding="utf-8")
LAYOUT_UI = (REPO / "frontend" / "src" / "components" / "Layout.js").read_text(encoding="utf-8")
SESSION_UI = (REPO / "frontend" / "src" / "services" / "impersonationSession.js").read_text(encoding="utf-8")


class FakeCollection:
    def __init__(self, docs=()):
        self.docs = [dict(doc) for doc in docs]

    async def find_one(self, query, projection=None, **_kwargs):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                if not projection:
                    return dict(doc)
                return {
                    key: value
                    for key, value in doc.items()
                    if projection.get(key, 1)
                }
        return None


class FakeDb:
    def __init__(self, users):
        self.users = FakeCollection(users)


class FakeAudit:
    def __init__(self):
        self.calls = []

    async def log(self, *args, **kwargs):
        self.calls.append((args, kwargs))


def actor_doc(**overrides):
    doc = {
        "id": "super-1",
        "email": "super@example.org",
        "full_name": "Super Admin Fixture",
        "role": "super_admin",
        "roles": ["super_admin"],
        "status": "active",
        "password_hash": "fixture-hash",
        "school_links": [],
    }
    doc.update(overrides)
    return doc


def target_doc(**overrides):
    doc = {
        "id": "target-1",
        "email": "target@example.org",
        "full_name": "Usuário Fixture",
        "role": "admin",
        "roles": ["admin"],
        "status": "active",
        "school_links": [],
    }
    doc.update(overrides)
    return doc


def current_actor(**overrides):
    user = {"id": "super-1", "email": "super@example.org", "role": "super_admin"}
    user.update(overrides)
    return user


def test_login_normal_nao_ganha_senha_mestra_ou_fallback_super_admin():
    login_block = AUTH_SOURCE.split('@router.post("/login"', 1)[1].split('@router.post("/refresh"', 1)[0]
    lowered = login_block.lower()
    assert "master_password" not in lowered
    assert "senha mestra" not in lowered
    assert "impersonation" not in lowered
    assert "verify_password(credentials.password, user.password_hash)" in login_block


@pytest.mark.asyncio
async def test_step_up_exige_super_admin_autenticado(monkeypatch):
    db = FakeDb([actor_doc(), target_doc()])
    monkeypatch.setattr(imp, "verify_password", lambda *_args: True)

    with pytest.raises(HTTPException) as exc:
        await imp._validated_actor_and_subject(
            db,
            current_user=current_actor(role="admin"),
            target_user_id="target-1",
            password="secret",
            active_role="admin",
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_step_up_rejeita_senha_errada_do_super_admin(monkeypatch):
    db = FakeDb([actor_doc(), target_doc()])
    monkeypatch.setattr(imp, "verify_password", lambda *_args: False)

    with pytest.raises(HTTPException) as exc:
        await imp._validated_actor_and_subject(
            db,
            current_user=current_actor(),
            target_user_id="target-1",
            password="wrong",
            active_role="admin",
        )
    assert exc.value.status_code == 401
    assert "Super Administrador" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_step_up_rejeita_usuario_inativo(monkeypatch):
    db = FakeDb([actor_doc(), target_doc(status="inactive")])
    monkeypatch.setattr(imp, "verify_password", lambda *_args: True)

    with pytest.raises(HTTPException) as exc:
        await imp._validated_actor_and_subject(
            db,
            current_user=current_actor(),
            target_user_id="target-1",
            password="secret",
            active_role="admin",
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_step_up_rejeita_outro_super_admin(monkeypatch):
    db = FakeDb([actor_doc(), target_doc(role="super_admin", roles=["super_admin"])])
    monkeypatch.setattr(imp, "verify_password", lambda *_args: True)

    with pytest.raises(HTTPException) as exc:
        await imp._validated_actor_and_subject(
            db,
            current_user=current_actor(),
            target_user_id="target-1",
            password="secret",
            active_role="super_admin",
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_step_up_rejeita_papel_que_nao_pertence_ao_usuario(monkeypatch):
    db = FakeDb([actor_doc(), target_doc()])
    monkeypatch.setattr(imp, "verify_password", lambda *_args: True)

    with pytest.raises(HTTPException) as exc:
        await imp._validated_actor_and_subject(
            db,
            current_user=current_actor(),
            target_user_id="target-1",
            password="secret",
            active_role="professor",
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_step_up_valido_preserva_contexto_do_usuario_alvo(monkeypatch):
    db = FakeDb([actor_doc(), target_doc()])
    monkeypatch.setattr(imp, "verify_password", lambda plain, hashed: plain == "secret" and hashed == "fixture-hash")

    actor, target, role, context = await imp._validated_actor_and_subject(
        db,
        current_user=current_actor(),
        target_user_id="target-1",
        password="secret",
        active_role="admin",
    )

    assert actor["id"] == "super-1"
    assert target["id"] == "target-1"
    assert role == "admin"
    assert context["school_ids"] == []


def test_claims_separam_ator_e_subject_sem_credencial():
    now = datetime.now(timezone.utc)
    claims = imp._impersonation_claims(
        actor=actor_doc(),
        subject=target_doc(),
        session_id="session-1",
        started_at=now,
        expires_at=now + timedelta(minutes=60),
    )
    assert claims["impersonation"] is True
    assert claims["impersonation_actor_id"] == "super-1"
    assert claims["impersonation_subject_name"] == "Usuário Fixture"
    assert "password" not in " ".join(claims.keys()).lower()


@pytest.mark.asyncio
async def test_auditoria_de_dominio_atribui_acao_ao_super_admin():
    audit = FakeAudit()
    imp._install_audit_actor_policy(audit)

    await audit.log(
        action="update",
        collection="grades",
        user={
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
        },
        description="Alterou nota",
    )

    _, kwargs = audit.calls[-1]
    assert kwargs["user"]["id"] == "super-1"
    assert kwargs["user"]["role"] == "super_admin"
    assert kwargs["extra_data"]["impersonation"]["subject_user_id"] == "target-1"
    assert kwargs["description"].startswith("[IMPERSONAÇÃO]")


def test_sessao_tem_deadline_e_revogacao_propria_sem_revogar_usuario_real():
    assert "IMPERSONATION_MAX_MINUTES" in IMP_SOURCE
    assert "impersonation_expires_at" in IMP_SOURCE
    assert "IMPERSONATION_ACCESS_JTI_PREFIX" in IMP_SOURCE
    assert "reason=\"impersonation_stopped\"" in IMP_SOURCE
    assert "revoke_all_user_tokens" not in IMP_SOURCE


def test_operacoes_de_conta_e_sessao_ficam_bloqueadas_no_modo_de_teste():
    for path in (
        "/api/auth/logout",
        "/api/auth/logout-all",
        "/api/auth/change-account",
        "/api/auth/resend-email-change",
        "/api/users/switch-role",
    ):
        assert path in IMP_SOURCE


def test_frontend_exige_password_do_super_admin_e_nao_expoe_senha_mestra():
    assert "impersonation-superadmin-password" in USERS_UI
    assert "startImpersonationSession" in USERS_UI
    assert "master_password" not in USERS_UI.lower()
    assert "senha mestra" not in USERS_UI.lower()
    assert "password" not in SESSION_UI.split("localStorage.setItem", 1)[-1]


def test_frontend_impersonado_nao_persiste_sessao_offline_de_30_dias():
    assert "AuthContextLegacy" in AUTH_CONTEXT
    assert "impersonation?.active" in AUTH_CONTEXT
    assert "originalRemoveItem.call(this, USER_DATA_KEY)" in AUTH_CONTEXT
    assert "originalRemoveItem.call(this, LAST_LOGIN_KEY)" in AUTH_CONTEXT


def test_banner_global_identifica_ator_subject_e_permita_encerrar():
    assert "impersonation-banner" in LAYOUT_UI
    assert "stopImpersonationSession" in LAYOUT_UI
    assert "ator real" in LAYOUT_UI
    assert "stop-impersonation-button" in LAYOUT_UI
