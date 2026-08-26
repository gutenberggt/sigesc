#!/usr/bin/env python3
"""Guard global dos escritores de ``enrollment_number`` do SIGESC.

Falha quando a superfície de código capaz de gravar ``enrollment_number`` em
``students`` ou ``enrollments`` diverge do inventário revisado abaixo.

A detecção usa AST e taint estrutural de payloads. Filtros de leitura contendo
``enrollment_number`` não são tratados como escritores.
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
EXCLUDED_PREFIXES = ("backend/tests/", "backend/__pycache__/")


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


# A contagem também é contrato: uma chamada extra em função já autorizada falha.
EXPECTED_WRITERS = Counter(
    {
        # Serviço canônico.
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

        # Continuidade institucional controlada.
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

        # Legado CONGELADO. Estes itens não autorizam novos fluxos em students.py.
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

        # Reconciliação nominal governada: read-only por padrão + confirmação forte.
        WriterKey(
            "backend/scripts/reconcile_enrollment_p0_legacy_relocation_2026.py",
            "run",
            "enrollments",
            "update_one",
        ): 1,

        # Harnesses de homologação isolados por prefixo/tag e com teardown.
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

LEGACY_KEYS = {key for key in EXPECTED_WRITERS if key.path == "backend/routers/students.py"}


class LocalNodeWalker:
    """Percorre uma função sem incorporar corpos de funções/classes aninhadas."""

    @staticmethod
    def walk(statements: list[ast.stmt]):
        stack: list[ast.AST] = list(reversed(statements))
        while stack:
            node = stack.pop()
            yield node
            for child in reversed(list(ast.iter_child_nodes(node))):
                if isinstance(
                    child,
                    (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
                ):
                    continue
                stack.append(child)


def _subscript_key(node: ast.Subscript) -> str | None:
    if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
        return node.slice.value
    return None


def _base_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Subscript):
        return _base_name(node.value)
    if isinstance(node, ast.Attribute):
        return _base_name(node.value)
    return None


def _names_in(node: ast.AST | None) -> set[str]:
    if node is None:
        return set()
    return {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}


def _structurally_contains_field(node: ast.AST | None) -> bool:
    """Detecta o campo em estruturas de PAYLOAD, não em chamadas arbitrárias.

    Isto evita marcar `find_one({"enrollment_number": ...})` como taint. Chamadas
    reconhecidas como construtores de mutação (dict/UpdateOne/ReplaceOne/InsertOne)
    são inspecionadas recursivamente para suportar bulk_write.
    """
    if node is None:
        return False
    if isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value == "enrollment_number":
                return True
            if _structurally_contains_field(value):
                return True
        return False
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return any(_structurally_contains_field(item) for item in node.elts)
    if isinstance(node, ast.Call):
        func_name = None
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        if func_name not in {"dict", "UpdateOne", "ReplaceOne", "InsertOne"}:
            return False
        if any(kw.arg == "enrollment_number" for kw in node.keywords):
            return True
        return any(_structurally_contains_field(arg) for arg in node.args) or any(
            _structurally_contains_field(kw.value) for kw in node.keywords
        )
    return False


def _collect_tainted_names(nodes: list[ast.AST]) -> set[str]:
    tainted: set[str] = set()

    # payload["enrollment_number"] = ...
    for node in nodes:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Subscript) and _subscript_key(target) == "enrollment_number":
                base = _base_name(target.value)
                if base:
                    tainted.add(base)

    # Propaga estruturas de payload e aliases, mas nunca o conteúdo de chamadas
    # comuns de leitura como find_one/find.
    changed = True
    while changed:
        changed = False
        for node in nodes:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            value_tainted = _structurally_contains_field(value) or bool(
                _names_in(value) & tainted
            )
            if not value_tainted:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id not in tainted:
                    tainted.add(target.id)
                    changed = True
    return tainted


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


def _collection_aliases(nodes: list[ast.AST]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    changed = True
    while changed:
        changed = False
        for node in nodes:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            collection = _collection_name(node.value, aliases)
            if collection not in TARGET_COLLECTIONS:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and aliases.get(target.id) != collection:
                    aliases[target.id] = collection
                    changed = True
    return aliases


def _mutation_payload(call: ast.Call, method: str) -> ast.AST | None:
    if method in {"insert_one", "insert_many", "bulk_write"}:
        if call.args:
            return call.args[0]
        names = {"document", "documents", "requests"}
    else:
        if len(call.args) >= 2:
            return call.args[1]
        names = {"update", "replacement"}
    for kw in call.keywords:
        if kw.arg in names:
            return kw.value
    return None


def _payload_writes_field(payload: ast.AST | None, tainted: set[str]) -> bool:
    return _structurally_contains_field(payload) or bool(_names_in(payload) & tainted)


def _iter_functions(tree: ast.AST):
    def recurse(body: list[ast.stmt], prefix: str = ""):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}.{node.name}" if prefix else node.name
                yield name, node
                yield from recurse(node.body, name)
            elif isinstance(node, ast.ClassDef):
                name = f"{prefix}.{node.name}" if prefix else node.name
                yield from recurse(node.body, name)

    yield from recurse(getattr(tree, "body", []))


def scan_file(path: Path) -> list[WriterSite]:
    rel = path.relative_to(ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
    sites: list[WriterSite] = []

    for qualname, fn in _iter_functions(tree):
        nodes = list(LocalNodeWalker.walk(fn.body))
        tainted = _collect_tainted_names(nodes)
        aliases = _collection_aliases(nodes)
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
            if not _payload_writes_field(payload, tainted):
                continue
            sites.append(
                WriterSite(
                    WriterKey(rel, qualname, collection, method),
                    getattr(node, "lineno", 1),
                )
            )
    return sites


def python_targets() -> list[Path]:
    paths = sorted((ROOT / "backend").rglob("*.py")) + sorted(ROOT.glob("*.py"))
    return [
        path
        for path in paths
        if not any(
            path.relative_to(ROOT).as_posix().startswith(prefix)
            for prefix in EXCLUDED_PREFIXES
        )
    ]


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
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "update_data"
                and node.func.attr == "pop"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "enrollment_number"
            ):
                return True
    return False


def self_test() -> None:
    sample = ast.parse(
        '''
async def writer(db):
    payload = {"status": "active"}
    payload["enrollment_number"] = "202600001"
    await db.enrollments.update_one({"id": "x"}, {"$set": payload})

async def direct(db):
    await db.students.update_one({"id": "x"}, {"$set": {"enrollment_number": "202600001"}})

async def reader(db):
    row = await db.enrollments.find_one({"enrollment_number": "202600001"})
    await db.enrollments.update_one({"id": row["id"]}, {"$set": {"status": "active"}})
'''
    )
    functions = dict(_iter_functions(sample))

    writer_nodes = list(LocalNodeWalker.walk(functions["writer"].body))
    writer_taint = _collect_tainted_names(writer_nodes)
    assert "payload" in writer_taint

    reader_nodes = list(LocalNodeWalker.walk(functions["reader"].body))
    assert not _collect_tainted_names(reader_nodes)

    direct_nodes = list(LocalNodeWalker.walk(functions["direct"].body))
    direct_call = next(
        node
        for node in direct_nodes
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "update_one"
    )
    assert _payload_writes_field(_mutation_payload(direct_call, "update_one"), set())


def emit(actual: Counter[WriterKey], sites: list[WriterSite]) -> int:
    ok = True

    if not _generic_enrollment_update_is_sanitized():
        print(
            "::error file=backend/routers/enrollments.py::PUT genérico deve remover enrollment_number antes do Mongo.",
            file=sys.stderr,
        )
        ok = False

    extra = actual - EXPECTED_WRITERS
    missing = EXPECTED_WRITERS - actual
    line_by_key: dict[WriterKey, int] = {}
    for site in sites:
        line_by_key.setdefault(site.key, site.line)

    if extra:
        ok = False
        print("Enrollment writer guard: escritor(es) NOVO(S)/não autorizado(s):", file=sys.stderr)
        for key, count in sorted(extra.items()):
            line = line_by_key.get(key, 1)
            msg = (
                f"writer não autorizado: {key.function} -> "
                f"{key.collection}.{key.method} (excesso={count})"
            )
            print(f"::error file={key.path},line={line}::{msg}", file=sys.stderr)
            print(f"  {key.path}:{line}: {msg}", file=sys.stderr)

    if missing:
        ok = False
        print(
            "Enrollment writer guard: baseline mudou; revise remoção/alteração antes de atualizar o inventário:",
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
    print(
        f"Enrollment writer guard: LEGACY FROZEN — {sum(EXPECTED_WRITERS[k] for k in LEGACY_KEYS)} "
        "escrita(s) em students.py permanecem explicitamente congeladas."
    )
    return 0


def main() -> int:
    self_test()
    actual, sites = inventory()
    return emit(actual, sites)


if __name__ == "__main__":
    raise SystemExit(main())
