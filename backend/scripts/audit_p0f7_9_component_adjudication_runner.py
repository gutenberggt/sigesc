"""Official P0-F7.9 runner with AST-based offline/read-only guard."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

CORE_PATH = Path(__file__).resolve().with_name("audit_p0f7_9_component_adjudication.py")
spec = importlib.util.spec_from_file_location("p0f79_core", CORE_PATH)
core = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(core)

PHASE_ID = core.PHASE_ID
P0F75_PHASE = core.P0F75_PHASE
P0F782_PHASE = core.P0F782_PHASE
CASE1_POLICY = core.CASE1_POLICY
CASE2_POLICY = core.CASE2_POLICY
CASE3_POLICY = core.CASE3_POLICY
DECISION_SELECT_ALTERNATIVE = core.DECISION_SELECT_ALTERNATIVE
DECISION_SELECT_SOURCE = core.DECISION_SELECT_SOURCE
DECISION_SELECT_TARGET = core.DECISION_SELECT_TARGET
DECISION_DEFER = core.DECISION_DEFER
_canonical_sha256 = core._canonical_sha256
validate_inputs = core.validate_inputs
decision_contract = core.decision_contract
build_html = core.build_html
validate_human_decisions = core.validate_human_decisions
seal_manifest = core.seal_manifest


def assert_offline_only() -> None:
    """Inspect executable AST instead of matching guard literals in source text."""
    source = CORE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_import_roots = {"motor", "pymongo", "subprocess", "requests", "httpx"}
    forbidden_call_names = {"MongoClient", "AsyncIOMotorClient"}
    mutator_attrs = {
        "insert_one", "insert_many", "update_one", "update_many", "replace_one",
        "delete_one", "delete_many", "bulk_write", "find_one_and_update",
        "find_one_and_delete", "find_one_and_replace",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", 1)[0] in forbidden_import_roots:
                    raise RuntimeError(f"OFFLINE_BOUNDARY_FAILED:import:{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root in forbidden_import_roots:
                raise RuntimeError(f"OFFLINE_BOUNDARY_FAILED:import:{node.module}")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in forbidden_call_names:
                raise RuntimeError(f"OFFLINE_BOUNDARY_FAILED:call:{func.id}")
            if isinstance(func, ast.Attribute) and func.attr in mutator_attrs:
                raise RuntimeError(f"READ_ONLY_BOUNDARY_FAILED:call:{func.attr}")

    # The official CLI must expose only build/seal, never executor verbs.
    cli_strings = {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    if "apply" in cli_strings or "rollback" in cli_strings:
        raise RuntimeError("EXECUTOR_SURFACE_FORBIDDEN")


core.assert_offline_only = assert_offline_only


def main() -> None:
    assert_offline_only()
    core.main()


if __name__ == "__main__":
    main()
