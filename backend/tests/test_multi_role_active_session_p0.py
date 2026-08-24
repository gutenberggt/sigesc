from datetime import datetime
from pathlib import Path

import pytest

from role_context import get_authorized_roles, resolve_role_context


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, length=None):
        if length is None:
            return list(self.docs)
        return list(self.docs)[:length]


class _Collection:
    def __init__(self, docs):
        self.docs = list(docs)

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                if projection:
                    result = {}
                    for key, enabled in projection.items():
                        if key == "_id" or not enabled:
                            continue
                        if key in doc:
                            result[key] = doc[key]
                    return result
                return dict(doc)
        return None

    def find(self, query, projection=None):
        matches = []
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                if projection:
                    result = {}
                    for key, enabled in projection.items():
                        if key == "_id" or not enabled:
                            continue
                        if key in doc:
                            result[key] = doc[key]
                    matches.append(result)
                else:
                    matches.append(dict(doc))
        return _Cursor(matches)


class _DB:
    def __init__(self, *, staff, assignments):
        self.staff = _Collection(staff)
        self.school_assignments = _Collection(assignments)


def _user_doc():
    return {
        "id": "user-1",
        "email": "professor@sigesc.com",
        "role": "professor",
        "roles": ["professor", "coordenador"],
        "school_links": [
            {
                "school_id": "legacy-school",
                "roles": ["professor", "coordenador"],
                "class_ids": [],
            }
        ],
    }


def test_authorized_roles_preserve_principal_and_additional_roles():
    user = _user_doc()
    assert get_authorized_roles(user) == ["professor", "coordenador"]


@pytest.mark.asyncio
async def test_role_context_school_scope_is_independent_of_lotacao_funcao():
    year = datetime.now().year
    db = _DB(
        staff=[{"id": "staff-1", "user_id": "user-1"}],
        assignments=[
            {
                "staff_id": "staff-1",
                "school_id": "school-professor",
                "funcao": "professor",
                "status": "ativo",
                "academic_year": year,
            },
            {
                "staff_id": "staff-1",
                "school_id": "school-coordenador",
                "funcao": "coordenador",
                "status": "ativo",
                "academic_year": year,
            },
        ],
    )

    professor = await resolve_role_context(db, _user_doc(), "professor", academic_year=year)
    coordenador = await resolve_role_context(db, _user_doc(), "coordenador", academic_year=year)

    expected_schools = ["school-professor", "school-coordenador"]

    assert professor["source"] == "lotacoes"
    assert professor["school_ids"] == expected_schools
    assert all(link["roles"] == ["professor"] for link in professor["school_links"])

    assert coordenador["source"] == "lotacoes"
    assert coordenador["school_ids"] == expected_schools
    assert all(link["roles"] == ["coordenador"] for link in coordenador["school_links"])


@pytest.mark.asyncio
async def test_authorized_role_keeps_school_scope_when_lotacao_funcao_differs():
    year = datetime.now().year
    db = _DB(
        staff=[{"id": "staff-1", "user_id": "user-1"}],
        assignments=[
            {
                "staff_id": "staff-1",
                "school_id": "school-coordenador",
                "funcao": "coordenador",
                "status": "ativo",
                "academic_year": year,
            }
        ],
    )

    professor = await resolve_role_context(db, _user_doc(), "professor", academic_year=year)

    assert professor["source"] == "lotacoes"
    assert professor["has_active_assignments"] is True
    assert professor["has_role_assignment"] is True
    assert professor["school_ids"] == ["school-coordenador"]
    assert professor["school_links"] == [
        {
            "school_id": "school-coordenador",
            "roles": ["professor"],
            "class_ids": [],
        }
    ]


@pytest.mark.asyncio
async def test_secretario_permission_uses_active_school_even_when_lotado_as_apoio():
    year = datetime.now().year
    user = {
        "id": "secretario-user",
        "email": "secretario@sigesc.com",
        "role": "secretario",
        "roles": ["secretario"],
        "school_links": [],
    }
    db = _DB(
        staff=[{"id": "staff-secretario", "user_id": "secretario-user"}],
        assignments=[
            {
                "staff_id": "staff-secretario",
                "school_id": "school-apoio",
                "funcao": "apoio",
                "status": "ativo",
                "academic_year": year,
            }
        ],
    )

    context = await resolve_role_context(db, user, "secretario", academic_year=year)

    assert context["source"] == "lotacoes"
    assert context["school_ids"] == ["school-apoio"]
    assert context["has_active_assignments"] is True
    assert context["has_role_assignment"] is True
    assert context["school_links"] == [
        {
            "school_id": "school-apoio",
            "roles": ["secretario"],
            "class_ids": [],
        }
    ]


def test_switch_role_never_mutates_principal_role_in_database():
    source = (BACKEND_ROOT / "routers" / "users.py").read_text(encoding="utf-8")

    assert '"$set": {"role": new_role}' not in source
    assert "Troca somente o papel ativo da sessão" in source
    assert '"active_role": new_role' in source
    assert '"role": new_role' in source


def test_login_starts_in_principal_role_and_refresh_preserves_active_role():
    source = (BACKEND_ROOT / "routers" / "auth.py").read_text(encoding="utf-8")

    assert "funcao_priority" not in source
    assert "effective_role = user.role" in source
    assert "effective_role = payload.get('active_role') or user.role" in source
    assert '"active_role": effective_role' in source
    assert "user_doc['role'] = current_user.get('role') or user_doc.get('role')" in source


def test_frontend_rotates_entire_session_after_role_switch():
    source = (
        REPO_ROOT / "frontend" / "src" / "contexts" / "AuthContext.js"
    ).read_text(encoding="utf-8")

    assert "access_token: newAccessToken" in source
    assert "refresh_token: newRefreshToken" in source
    assert "csrf_token: newCsrfToken" in source
    assert "setAccessToken(newAccessToken)" in source
    assert "setRefreshToken(newRefreshToken)" in source
    assert "setCsrfToken(newCsrfToken)" in source
    assert "setUser(sessionUser)" in source
    assert "saveUserDataLocally(sessionUser)" in source


def test_multi_role_switcher_exists_only_in_blue_dashboard_headers():
    layout = (
        REPO_ROOT / "frontend" / "src" / "components" / "Layout.js"
    ).read_text(encoding="utf-8")
    dashboard = (
        REPO_ROOT / "frontend" / "src" / "pages" / "Dashboard.js"
    ).read_text(encoding="utf-8")
    professor_dashboard = (
        REPO_ROOT / "frontend" / "src" / "pages" / "ProfessorDashboard.js"
    ).read_text(encoding="utf-8")

    # A barra branca superior é somente global/navigation; nunca deve duplicar
    # a troca de papel que pertence ao bloco azul de identificação do dashboard.
    assert "global-role-switcher-button" not in layout
    assert "global-role-switcher-menu" not in layout
    assert "switchRole" not in layout
    assert "getAvailableRoles" not in layout

    # Dashboard comum: mantém o seletor já existente no bloco azul.
    assert "const { user, switchRole, getAvailableRoles } = useAuth();" in dashboard
    assert "Trocar Papel" in dashboard
    assert "availableRoles.map((role)" in dashboard
    assert "const result = await switchRole(newRole);" in dashboard

    # Professor possui home própria e, por isso, precisa do mesmo seletor dentro
    # do seu próprio cabeçalho azul, nunca no Layout global.
    assert "const { user, switchRole, getAvailableRoles } = useAuth();" in professor_dashboard
    assert 'data-testid="professor-role-switcher-button"' in professor_dashboard
    assert 'data-testid="professor-role-switcher-menu"' in professor_dashboard
    assert "availableRoles.map((role)" in professor_dashboard
    assert "const result = await switchRole(newRole);" in professor_dashboard
    assert "window.location.assign('/dashboard');" in professor_dashboard

    # /dashboard continua sendo o roteador canônico pós-troca: professor é
    # encaminhado à sua home própria; os demais papéis permanecem no dashboard.
    assert "if (isProfessor)" in dashboard
    assert '<Navigate to="/professor" replace />' in dashboard
