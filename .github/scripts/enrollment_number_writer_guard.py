#!/usr/bin/env python3
"""Guard global dos escritores de ``enrollment_number`` do SIGESC.

Objetivo:
- congelar a superfície atual de código capaz de gravar ``enrollment_number`` em
  ``students`` ou ``enrollments``;
- rejeitar novos escritores, inclusive em arquivos já excepcionados;
- manter as exceções legadas explícitas e auditáveis até sua aposentadoria;
- impedir que o PUT genérico de matrícula aceite o identificador como campo editável.

O detector usa AST e uma análise de taint simples para reconhecer payloads diretos
ou variáveis que recebem ``enrollment_number`` antes de serem passadas a primitivas
Mongo de escrita. Não depende de Mongo, FastAPI ou bibliotecas externas.
"""
from __future__ import annotations

import ast
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET_COLLECTIONS = {"students", "enrollments"}
WRITE_METHODS = {
    "insert_one",
    "insert_many",
    "update_one",
    "update_many",
    "replace_one",
    "find_one_and_update",
    "find_one_and_replace",
    "bulk_write",
}
EXCLUDED_PREFIXES = (
    "backend/tests/",
    "backend/__pycache__/",
)


@dataclass(frozen=True, order=True)
class WriterKey:
    path: str
    function: str
    collection: str
    method: str


@dataclass(frozen=True)
class WriterSite:
    key: WriterKey
    line: int


# Inventário deliberadamente estrito. A contagem faz parte do contrato: adicionar
# outra chamada de escrita dentro de uma função já autorizada também quebra o guard.
EXPECTED_WRITERS = Counter(
    {
        # Serviço canônico: fonte autorizada para novos vínculos/projeções.
        WriterKey(
            "backend/services/enrollment_service.py",
            "rebuild_student_home_projection",
            "students",
            "update_one",
        ): 1,
        WriterKey(
            "backend/services/enrollment_service.py",
            "create_active_enrollment",
            "enrollments",
            "insert_one",
        ): 1,
        WriterKey(
            "backend/services/enrollment_service.py",
            "create_active_enrollment",
            "students",
            "update_one",
        ): 1,

        # Continuidade institucional: handoff controlado do mesmo número histórico.
        WriterKey(
            "backend/routers/student_enrollment_identity_continuity.py",
            "resolve_and_prepare_identity_handoff",
            "enrollments",
            "update_one",
        ): 1,
        WriterKey(
            "backend/routers/student_enrollment_identity_continuity.py",
            "_rollback_release_if_safe",
            "enrollments",
            "update_one",
        ): 1,
        WriterKey(
            "backend/routers/student_enrollment_identity_continuity.py",
            "_finalize_projection_and_audit",
            "students",
            "update_one",
        ): 1,

        # Exceções LEGADAS existentes. Não são autorização arquitetural para novos
        # fluxos; ficam congeladas até refatoração específica para o serviço canônico.
        WriterKey(
            "backend/routers/students.py",
            "setup_students_router.create_student",
            "students",
            "insert_one",
        ): 1,
        WriterKey(
            "backend/routers/students.py",
            "setup_students_router.create_student",
            "enrollments",
            "insert_one",
        ): 1,
        WriterKey(
            "backend/routers/students.py",
            "setup_students_router.repair_enrollment_numbers",
            "enrollments",
            "update_one",
        ): 1,
        WriterKey(
            "backend/routers/students.py",
            "setup_students_router.repair_enrollment_numbers",
            "enrollments",
            "insert_one",
        ): 1,
        WriterKey(
            "backend/routers/students.py",
            "setup_students_router.repair_enrollment_numbers",
            "students",
            "update_one",
        ): 1,
        WriterKey(
            "backend/routers/students.py",
            "setup_students_router.update_student",
            "enrollments",
            "update_one",
        ): 1,
        WriterKey(
            "backend/routers/students.py",
            "setup_students_router.update_student",
            "enrollments",
            "insert_one",
        ): 2,
        WriterKey(
            "backend/routers/students.py",
            "setup_students_router.update_student",
            "students",
            "update_one",
        ): 1,
        WriterKey(
            "backend/routers/students.py",
            "setup_students_router.transfer_student",
            "enrollments",
            "insert_one",
        ): 1,

        # Reconciliação nominal governada: read-only por padrão, apply com token.
        WriterKey(
            "backend/scripts/reconcile_enrollment_p0_legacy_relocation_2026.py",
            "run",
            "enrollments",
            "update_one",
        ): 1,

        # Harnesses de homologação isolada, identificados por prefixos próprios.
        WriterKey(
            "backend/scripts/homolog_transfer_sandbox.py",
            "_build_sandbox",
            "enrollments",
            "insert_one",
        ): 1,
        WriterKey(
            "backend/scripts/_audit_student_movement.py",
            "seed",
            "enrollments",
            "insert_one",
        ): 1,
    }
)

LEGACY_KEYS = {
    key
    for key in EXPECTED_WRITERS
    if key.path == "backend/routers/students.py"
}


class LocalNodeWalker:
    """Percorre uma função sem absorver o corpo de funções/classes aninhadas."""

    @staticmethod
    def walk(statements: list[ast.stmt]):
        stack: list[ast.AST] = list(reversed(statements))
        while stack:
            node = stack.pop()
            yield node
            children = list(ast.iter_child_nodes(node))
            for child in reversed(children):
                if isinstance(
                    child,
                    (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
                ):
                    continue
                stack.append(child)


def _contains_enrollment_literal(node: ast.AST | None) -> bool:
    if node is None:
        return False
    return any(
        isinstance(item, ast.Constant) and item.value == "enrollment_number"
        for item in ast.walk(node)
    )


def _names_in(node: ast.AST | None) -> set[str]:
    if node is None:
        return set()
    return {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}


def _subscript_key(node: ast.Subscript) -> str | None:
    value = node.slice
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    return None


def _target_base_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Subscript):
        return _target_base_name(node.value)
    if isinstance(node, ast.Attribute):
        return _target_base_name(node.value)
    return None


def _collect_tainted_names(nodes: list[ast.AST]) -> set[str]:
    tainted: set[str] = set()

    # Subscript assignment: payload["enrollment_number"] = ...
    for node in nodes:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Subscript) and _subscript_key(target) == "enrollment_number":
                    base = _target_base_name(target.value)
                    if base:
                        tainted.add(base)

    # Fixed point para aliases e dicionários construídos antes da escrita.
    changed = True
    while changed:
        changed = False
        for node in nodes:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value_tainted = _contains_enrollment_literal(value) or bool(
                _names_in(value) & tainted
            )
            if not value_tainted:
                continue
            for target in targets:
                if isinstance(target, ast.Name) and target.id not in tainted:
                    tainted.add(target.id)
                    changed = True
    return tainted


def _collect_collection_aliases(nodes: list[ast.AST]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in nodes:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        collection = _collection_name(node.value, aliases)
        if collection not in TARGET_COLLECTIONS:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                aliases[target.id] = collection
    return aliases


def _collection_name(node: ast.AST | None, aliases: dict[str, str]) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return aliases.get(node.id)
    if isinstance(node, ast.Attribute) and node.attr in TARGET_COLLECTIONS:
        return node.attr
    if isinstance(node, ast.Subscript):
        key = _subscript_key(node)
        if key in TARGET_COLLECTIONS:
            return key
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "get_collection" and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and first.value in TARGET_COLLECTIONS:
                return str(first.value)
    return None


def _mutation_payload(call: ast.Call, method: str) -> ast.AST | None:
    if method in {"insert_one", "insert_many", "bulk_write"}:
        if call.args:
            return call.args[0]
        for kw in call.keywords:
            if kw.arg in {"document", "documents", "requests"}:
                return kw.value
        return None

    # update/replace/find_one_and_*. O primeiro arg é filtro, o segundo é payload.
    if len(call.args) >= 2:
        return call.args[1]
    for kw in call.keywords:
        if kw.arg in {"update", "replacement"}:
            return kw.value
    return None


def _payload_is_tainted(payload: ast.AST | None, tainted: set[str]) -> bool:
    return _contains_enrollment_literal(payload) or bool(_names_in(payload) & tainted)


def _iter_functions(tree: ast.AST):
    def recurse(body: list[ast.stmt], prefix: str = ""):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = f"{prefix}.{node.name}" if prefix else node.name
                yield qualname, node
                yield from recurse(node.body, qualname)
            elif isinstance(node, ast.ClassDef):
                class_prefix = f"{prefix}.{node.name}" if prefix else node.name
                yield from recurse(node.body, class_prefix)

    yield from recurse(getattr(tree, "body", []))


def scan_file(path: Path) -> list[WriterSite]:
    rel = path.relative_to(ROOT).as_posix()
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=rel)
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise RuntimeError(f"Não foi possível analisar {rel}: {exc}") from exc

    sites: list[WriterSite] = []
    for qualname, fn in _iter_functions(tree):
        nodes = list(LocalNodeWalker.walk(fn.body))
        tainted = _collect_tainted_names(nodes)
        aliases = _collect_collection_aliases(nodes)

        for node in nodes:
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            method = node.func.attr
            if method not in WRITE_METHODS:
                continue
            collection = _collection_name(node.func.value, aliases)
            if collection not in TARGET_COLLECTIONS:
                continue
            payload = _mutation_payload(node, method)
            if not _payload_is_tainted(payload, tainted):
                continue
            sites.append(
                WriterSite(
                    WriterKey(rel, qualname, collection, method),
                    getattr(node, "lineno", 1),
                )
            )
    return sites


def python_targets() -> list[Path]:
    targets = sorted((ROOT / "backend").rglob("*.py"))
    # Inclui scripts Python na raiz (ex.: tombstones históricos).
    targets.extend(sorted(ROOT.glob("*.py")))
    result = []
    for path in targets:
        rel = path.relative_to(ROOT).as_posix()
        if any(rel.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
            continue
        result.append(path)
    return result


def inventory() -> tuple[Counter[WriterKey], list[WriterSite]]:
    sites: list[WriterSite] = []
    for path in python_targets():
        sites.extend(scan_file(path))
    return Counter(site.key for site in sites), sites


def _generic_enrollment_update_is_sanitized() -> bool:
    path = ROOT / "backend" / "routers" / "enrollments.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for qualname, fn in _iter_functions(tree):
        if qualname != "setup_router.update_enrollment":
            continue
        for node in LocalNodeWalker.walk(fn.body):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if not (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "update_data"
                and node.func.attr == "pop"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "enrollment_number"
            ):
                continue
            return True
    return False


def self_test() -> None:
    sample = ast.parse(
        """
async def writer(db):
    payload = {"status": "active"}
    payload["enrollment_number"] = "202600001"
    await db.enrollments.update_one({"id": "x"}, {"$set": payload})

async def reader(db):
    row = await db.enrollments.find_one({"enrollment_number": "202600001"})
    await db.enrollments.update_one({"id": row["id"]}, {"$set": {"status": "active"}})
"""
    )
    functions = dict(_iter_functions(sample))
    writer_nodes = list(LocalNodeWalker.walk(functions["writer"].body))
    reader_nodes = list(LocalNodeWalker.walk(functions["reader"].body))
    writer_taint = _collect_tainted_names(writer_nodes)
    reader_taint = _collect_tainted_names(reader_nodes)
    assert "payload" in writer_taint
    assert not reader_taint

    writer_calls = [n for n in writer_nodes if isinstance(n, ast.Call)]
    update_call = next(
        n
        for n in writer_calls
        if isinstance(n.func, ast.Attribute) and n.func.attr == "update_one"
    )
    assert _collection_name(update_call.func.value, {}) == "enrollments"
    assert _payload_is_tainted(_mutation_payload(update_call, "update_one"), writer_taint)


def emit(actual: Counter[WriterKey], sites: list[WriterSite]) -> int:
    ok = True

    if not _generic_enrollment_update_is_sanitized():
        print(
            "::error file=backend/routers/enrollments.py::PUT genérico de matrícula deve remover enrollment_number de update_data antes de persistir.",
            file=sys.stderr,
        )
        ok = False

    extra = actual - EXPECTED_WRITERS
    missing = EXPECTED_WRITERS - actual

    if extra:
        ok = False
        print("Enrollment writer guard: escritores NOVOS/não autorizados:", file=sys.stderr)
        line_by_key: dict[WriterKey, int] = {}
        for site in sites:
            line_by_key.setdefault(site.key, site.line)
        for key, count in sorted(extra.items()):
            line = line_by_key.get(key, 1)
            msg = (
                f"escritor não autorizado de enrollment_number: {key.function} -> "
                f"{key.collection}.{key.method} (excesso={count})"
            )
            print(f"::error file={key.path},line={line}::{msg}", file=sys.stderr)
            print(f"  {key.path}:{line}: {msg}", file=sys.stderr)

    if missing:
        ok = False
        print(
            "Enrollment writer guard: inventário esperado mudou (escritor removido/alterado). "
            "Atualize a allowlist deliberadamente no mesmo PR:",
            file=sys.stderr,
        )
        for key, count in sorted(missing.items()):
            print(
                f"  MISSING x{count}: {key.path} :: {key.function} -> {key.collection}.{key.method}",
                file=sys.stderr,
            )

    if not ok:
        return 1

    print(f"Enrollment writer guard: OK — {sum(actual.values())} escrita(s) inventariada(s).")
    if LEGACY_KEYS:
        print(
            "Enrollment writer guard: LEGACY FROZEN — students.py permanece exceção explícita; "
            "nenhum novo escritor nesse router é aceito sem alterar este inventário."
        )
    return 0


def main() -> int:
    self_test()
    actual, sites = inventory()
    return emit(actual, sites)


if __name__ == "__main__":
    raise SystemExit(main())
