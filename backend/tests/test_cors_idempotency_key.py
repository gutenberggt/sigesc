from __future__ import annotations

import ast
from pathlib import Path


SERVER = Path(__file__).resolve().parents[1] / "server.py"
PREPARE_PAGE = Path(__file__).resolve().parents[2] / "frontend" / "public" / "admin-retificacao-prepare.html"


def _cors_allow_headers() -> list[str]:
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "add_middleware":
            continue
        if not node.args:
            continue
        middleware = node.args[0]
        if not isinstance(middleware, ast.Name) or middleware.id != "CORSMiddleware":
            continue
        for keyword in node.keywords:
            if keyword.arg != "allow_headers":
                continue
            assert isinstance(keyword.value, (ast.List, ast.Tuple)), "allow_headers deve permanecer explícito"
            return [
                item.value
                for item in keyword.value.elts
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            ]
    raise AssertionError("Configuração CORSMiddleware/allow_headers não encontrada em backend/server.py")


def test_prepare_page_uses_idempotency_key_header() -> None:
    html = PREPARE_PAGE.read_text(encoding="utf-8")
    assert "'Idempotency-Key':idempotencyKey" in html


def test_cors_allows_idempotency_key_required_by_prepare_execution() -> None:
    headers = {value.lower() for value in _cors_allow_headers()}
    assert "idempotency-key" in headers, (
        "A página F2.3C envia Idempotency-Key no prepare-execution. "
        "Sem esse header na allowlist CORS, o preflight do navegador falha e fetch() retorna 'Failed to fetch'."
    )
