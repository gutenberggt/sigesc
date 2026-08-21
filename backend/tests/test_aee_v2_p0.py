"""Testes unitários das salvaguardas P0 do AEE v2.

Não usam MongoDB, FastAPI real, HTTP ou dados de produção. O módulo é carregado
com stubs mínimos para que estas invariantes possam integrar o gate leve do CI.
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
import types

import pytest


class FakeHTTPException(Exception):
    def __init__(self, status_code, detail=None):
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


class FakeStatus:
    HTTP_201_CREATED = 201
    HTTP_403_FORBIDDEN = 403
    HTTP_409_CONFLICT = 409
    HTTP_422_UNPROCESSABLE_ENTITY = 422


def _load_p0_module():
    """Carrega o módulo diretamente, sem executar ``routers/__init__.py``."""
    fastapi_stub = types.ModuleType("fastapi")
    fastapi_stub.HTTPException = FakeHTTPException
    fastapi_stub.Request = object
    fastapi_stub.status = FakeStatus()

    auth_stub = types.ModuleType("auth_middleware")

    class FakeAuthMiddleware:
        pass

    auth_stub.AuthMiddleware = FakeAuthMiddleware

    models_stub = types.ModuleType("models")
    for model_name in (
        "AtendimentoAEE",
        "AtendimentoAEECreate",
        "AtendimentoAEEUpdate",
        "PlanoAEE",
        "PlanoAEECreate",
        "PlanoAEEUpdate",
    ):
        setattr(models_stub, model_name, type(model_name, (), {}))

    old_modules = {
        name: sys.modules.get(name)
        for name in ("fastapi", "auth_middleware", "models")
    }
    sys.modules["fastapi"] = fastapi_stub
    sys.modules["auth_middleware"] = auth_stub
    sys.modules["models"] = models_stub

    try:
        module_path = Path(__file__).resolve().parents[1] / "routers" / "aee_v2_p0.py"
        spec = importlib.util.spec_from_file_location("aee_v2_p0_under_test", module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        return module
    finally:
        for name, previous in old_modules.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


P0 = _load_p0_module()


class FakeCollection:
    def __init__(self, documents=None):
        self.documents = list(documents or [])

    @staticmethod
    def _matches(document, query):
        for key, expected in query.items():
            if isinstance(expected, dict) and "$in" in expected:
                if document.get(key) not in expected["$in"]:
                    return False
                continue
            if document.get(key) != expected:
                return False
        return True

    async def find_one(self, query, projection=None):
        for document in self.documents:
            if self._matches(document, query):
                if not projection:
                    return dict(document)
                return {
                    key: value
                    for key, value in document.items()
                    if key != "_id" and projection.get(key, 0)
                }
        return None


class FakeDB:
    def __init__(self, *, students=None, assignments=None, staff=None, users=None):
        self.students = FakeCollection(students)
        self.teacher_assignments = FakeCollection(assignments)
        self.staff = FakeCollection(staff)
        self.users = FakeCollection(users)


def test_status_labels_are_presentation_only():
    assert P0.aee_status_label("rascunho") == "Em elaboração"
    assert P0.aee_status_label("ativo") == "Vigente"
    assert P0.aee_status_label("revisao") == "Em revisão"
    assert P0.aee_status_label("encerrado") == "Encerrado"
    assert P0.aee_status_label("legado_desconhecido") == "legado_desconhecido"


def test_hard_delete_only_allows_empty_draft():
    empty = {"atendimentos": 0, "evolucoes": 0, "articulacoes": 0}
    assert P0.plan_hard_delete_allowed("rascunho", empty) is True

    for plan_status in ("ativo", "revisao", "encerrado"):
        assert P0.plan_hard_delete_allowed(plan_status, empty) is False

    assert P0.plan_hard_delete_allowed(
        "rascunho", {"atendimentos": 1, "evolucoes": 0, "articulacoes": 0}
    ) is False
    assert P0.plan_hard_delete_allowed(
        "rascunho", {"atendimentos": 0, "evolucoes": 1, "articulacoes": 0}
    ) is False
    assert P0.plan_hard_delete_allowed(
        "rascunho", {"atendimentos": 0, "evolucoes": 0, "articulacoes": 1}
    ) is False


def test_responsible_professor_prefers_aee_class_assignment():
    db = FakeDB(
        students=[{"id": "student-1", "atendimento_programa_class_id": "aee-class-1"}],
        assignments=[{"class_id": "aee-class-1", "status": "ativo", "staff_id": "staff-1"}],
        staff=[{
            "id": "staff-1",
            "nome": "Professora AEE Titular",
            "email": "aee@sigesc.test",
            "user_id": "user-prof-1",
        }],
        users=[
            {"id": "user-prof-1", "role": "professor", "full_name": "Professora AEE Titular"},
            {"id": "user-admin", "role": "admin", "full_name": "Administrador"},
        ],
    )

    professor_id, professor_nome = asyncio.run(
        P0.resolve_aee_responsible_professor(
            db,
            student_id="student-1",
            requested_id="user-admin",
            requested_nome="Administrador",
            current_user={"id": "user-admin", "role": "admin", "full_name": "Administrador"},
        )
    )

    assert professor_id == "user-prof-1"
    assert professor_nome == "Professora AEE Titular"


def test_responsible_professor_accepts_explicit_professor_user():
    db = FakeDB(
        students=[{"id": "student-2", "atendimento_programa_class_id": None}],
        users=[{"id": "user-prof-2", "role": "professor", "full_name": "Professor AEE"}],
    )

    professor_id, professor_nome = asyncio.run(
        P0.resolve_aee_responsible_professor(
            db,
            student_id="student-2",
            requested_id="user-prof-2",
            requested_nome=None,
            current_user={"id": "user-admin", "role": "admin"},
        )
    )

    assert professor_id == "user-prof-2"
    assert professor_nome == "Professor AEE"


def test_admin_actor_is_never_used_as_responsible_professor_fallback():
    db = FakeDB(
        students=[{"id": "student-3", "atendimento_programa_class_id": None}],
        users=[{"id": "user-admin", "role": "admin", "full_name": "Administrador"}],
    )

    with pytest.raises(FakeHTTPException) as exc_info:
        asyncio.run(
            P0.resolve_aee_responsible_professor(
                db,
                student_id="student-3",
                requested_id="user-admin",
                requested_nome="Administrador",
                current_user={"id": "user-admin", "role": "admin", "full_name": "Administrador"},
            )
        )

    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert detail["code"] == "AEE_RESPONSIBLE_PROFESSOR_UNRESOLVED"
    assert "administrativo" in detail["message"].lower()
