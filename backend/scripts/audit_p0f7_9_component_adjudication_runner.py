"""Official P0-F7.9 runner with AST-based offline/read-only guard."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import Any, Mapping

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
decision_contract = core.decision_contract
build_html = core.build_html
validate_human_decisions = core.validate_human_decisions
seal_manifest = core.seal_manifest


class _P0F782FullReportView(dict):
    """Compatibility view for canonical full P0-F7.8.2 reports.

    The full JSON stores mutation/executor guarantees under `summary` and
    `safety`. The compact stdout projection also exposes equivalent top-level
    flags. Older P0-F7.9 validation accidentally required those compact-only
    top-level flags in the full file.

    Missing compact-only flags are exposed as False to the legacy core
    validator without altering the underlying key set, so the embedded SHA is
    still verified against the original, unmodified report.
    """

    _COMPACT_ONLY_FALSE_DEFAULTS = {"database_mutation", "executor_authorized"}

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._COMPACT_ONLY_FALSE_DEFAULTS and key not in self:
            return False
        return super().get(key, default)


_original_validate_inputs = core.validate_inputs


def validate_inputs(
    p0f75: Mapping[str, Any], p0f782: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate the canonical full-report contract fail-closed.

    Safety must be explicit in the full report. Compact stdout top-level flags
    are optional because they were never part of the persisted P0-F7.8.2 JSON.
    If such top-level flags are present, the legacy core still requires False.
    """
    safety = p0f782.get("safety") or {}
    if not isinstance(safety, Mapping):
        raise ValueError("P0F7_8_2_SAFETY_INVALID")
    if safety.get("database_mutation") is not False:
        raise ValueError("P0F7_8_2_SAFETY_DATABASE_MUTATION_INVALID")
    if safety.get("production_writes_executed") is not False:
        raise ValueError("P0F7_8_2_SAFETY_PRODUCTION_WRITES_INVALID")
    if safety.get("not_authorization_for_executor") is not True:
        raise ValueError("P0F7_8_2_SAFETY_EXECUTOR_GUARD_INVALID")
    if "executor_authorized" in safety and safety.get("executor_authorized") is not False:
        raise ValueError("P0F7_8_2_SAFETY_EXECUTOR_FLAG_INVALID")

    view = _P0F782FullReportView(p0f782)
    return _original_validate_inputs(p0f75, view)


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

    cli_strings = {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    if "apply" in cli_strings or "rollback" in cli_strings:
        raise RuntimeError("EXECUTOR_SURFACE_FORBIDDEN")


core.assert_offline_only = assert_offline_only
core.validate_inputs = validate_inputs


def main() -> None:
    assert_offline_only()
    core.main()


if __name__ == "__main__":
    main()
