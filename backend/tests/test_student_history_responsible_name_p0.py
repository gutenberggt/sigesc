from pathlib import Path

import pytest
from fastapi import APIRouter, Request

from auth_middleware import AuthMiddleware
from routers.student_history_responsible_name import (
    ROUTE_PATH,
    install_student_history_responsible_name,
)


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _length):
        return list(self.rows)


class _UsersCollection:
    def __init__(self, rows):
        self.rows = rows
        self.find_calls = []

    def find(self, query, projection):
        self.find_calls.append((query, projection))
        return _Cursor(self.rows)


class _Db:
    def __init__(self, users):
        self.users = _UsersCollection(users)


@pytest.mark.asyncio
async def test_history_projects_full_name_without_backfill(monkeypatch):
    base_router = APIRouter(prefix="/students")

    @base_router.get("/{student_id}/history")
    async def canonical_history(student_id: str, request: Request):
        assert student_id == "student-1"
        return [
            {"user_id": "user-1", "user_name": "legacy-one@example.com"},
            {"user_name": "legacy-two@example.com"},
            {"user_id": "missing", "user_name": "missing@example.com"},
            {"user_name": "Nome já persistido"},
        ]

    db = _Db(
        [
            {
                "id": "user-1",
                "full_name": "Maria da Silva",
                "email": "legacy-one@example.com",
            },
            {
                "id": "user-2",
                "full_name": "João Pereira",
                "email": "legacy-two@example.com",
            },
        ]
    )

    async def _current_user(_request):
        return {"id": "viewer", "is_sandbox": False}

    monkeypatch.setattr(AuthMiddleware, "get_current_user", _current_user)

    install_student_history_responsible_name(base_router, db)
    route = next(
        route
        for route in base_router.routes
        if route.path == ROUTE_PATH and "GET" in (route.methods or set())
    )

    result = await route.endpoint(student_id="student-1", request=object())

    assert result[0]["user_name"] == "Maria da Silva"
    assert result[1]["user_name"] == "João Pereira"
    assert result[2]["user_name"] == "missing@example.com"
    assert result[3]["user_name"] == "Nome já persistido"
    assert len(db.users.find_calls) == 1


def test_history_table_allows_wrapping_in_every_column():
    repo_root = Path(__file__).resolve().parents[2]
    css = (repo_root / "frontend" / "src" / "index.css").read_text(encoding="utf-8")

    assert "Histórico do Estudante — Turma/Observações" in css
    assert "+ .overflow-x-auto > table.min-w-full.text-sm th" in css
    assert "+ .overflow-x-auto > table.min-w-full.text-sm td" in css
    assert "white-space: normal !important;" in css
    assert "overflow-wrap: anywhere;" in css
