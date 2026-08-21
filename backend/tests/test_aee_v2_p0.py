"""Testes unitários das salvaguardas P0 do AEE v2.

Não usam MongoDB, HTTP ou dados de produção. O objetivo é certificar as regras
que precisam permanecer invariantes durante a evolução do Diário AEE.
"""

import asyncio
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, "/app/backend")

from routers.aee_v2_p0 import (  # noqa: E402
    aee_status_label,
    plan_hard_delete_allowed,
    resolve_aee_responsible_professor,
)


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
    assert aee_status_label("rascunho") == "Em elaboração"
    assert aee_status_label("ativo") == "Vigente"
    assert aee_status_label("revisao") == "Em revisão"
    assert aee_status_label("encerrado") == "Encerrado"
    assert aee_status_label("legado_desconhecido") == "legado_desconhecido"


def test_hard_delete_only_allows_empty_draft():
    empty = {"atendimentos": 0, "evolucoes": 0, "articulacoes": 0}
    assert plan_hard_delete_allowed("rascunho", empty) is True

    for plan_status in ("ativo", "revisao", "encerrado"):
        assert plan_hard_delete_allowed(plan_status, empty) is False

    assert plan_hard_delete_allowed(
        "rascunho", {"atendimentos": 1, "evolucoes": 0, "articulacoes": 0}
    ) is False
    assert plan_hard_delete_allowed(
        "rascunho", {"atendimentos": 0, "evolucoes": 1, "articulacoes": 0}
    ) is False
    assert plan_hard_delete_allowed(
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
        resolve_aee_responsible_professor(
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
        resolve_aee_responsible_professor(
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

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            resolve_aee_responsible_professor(
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
