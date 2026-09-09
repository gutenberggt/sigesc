from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend" / "scripts" / "enrollment_rectification_f2_3c_pilot.py"
WORKFLOW = ROOT / ".github" / "workflows" / "enrollment-rectification-f2-3c-pilot.yml"


def _script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_pilot_has_no_direct_mongo_mutator_calls():
    tree = ast.parse(_script())
    forbidden = {
        "insert_one", "insert_many", "update_one", "update_many", "replace_one",
        "delete_one", "delete_many", "bulk_write", "find_one_and_update",
        "find_one_and_delete", "find_one_and_replace", "drop", "drop_database",
        "create_index", "create_indexes", "rename",
    }
    hits = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in forbidden
    }
    assert not hits


def test_pilot_reuses_canonical_saga_and_mt1():
    source = _script()
    for marker in (
        "build_rectification_dry_run",
        "prepare_rectification_saga_execution",
        "execute_rectification_saga",
        "rollback_rectification_saga",
        "resolve_operational_tenant_context",
        "DOCUMENT_ACKNOWLEDGEMENT",
    ):
        assert marker in source
    assert 'os.environ[EXECUTION_FLAG] = "true"' in source
    assert source.count('os.environ[EXECUTION_FLAG] = "false"') >= 2
    assert '"process_local_ephemeral"' in source


def test_tooling_carries_no_raw_identity_values():
    text = _script() + "\n" + _workflow()
    # Identity must arrive only as salted hashes from the closed prior gate.
    assert not re.search(r"\b\d{11}\b", text)
    assert not re.search(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", text)
    assert not re.search(r"\b\d{2}/\d{2}/\d{4}\b", text)
    assert "full_name" in _script()  # schema field is allowed; literal person name is not needed.
    assert "F2_3_NAME_HASH" in text
    assert "F2_3_DOB_HASH" in text
    assert "F2_3_CPF_HASH" in text


def test_workflow_requires_dedicated_reauthentication_secrets():
    flow = _workflow()
    assert "secrets.SIGESC_F2_3C_OPERATOR_EMAIL" in flow
    assert "secrets.SIGESC_F2_3C_REAUTH_PASSWORD" in flow
    assert "environment: production" in flow
    remote = [
        line.strip()
        for line in flow.splitlines()
        if line.strip().startswith("remote_command=")
    ]
    assert len(remote) == 1
    assert "REAUTH_PASSWORD" not in remote[0]
    assert "OPERATOR_EMAIL" not in remote[0]
    assert "-e ENROLLMENT_RECTIFICATION_EXECUTION_ENABLED=false" in remote[0]


def test_workflow_reads_identity_from_closed_prior_gate_instead_of_republishing_pii():
    flow = _workflow()
    assert "'IDENTITY_SOURCE_ISSUE':'601'" in flow or "'IDENTITY_SOURCE_ISSUE': '601'" in flow
    assert "get('/issues/601')" in flow
    assert "COMPONENT_SALT" in flow
    assert "NAME_HASH" in flow
    assert "DOB_HASH" in flow
    assert "CPF_HASH" in flow


def test_final_gate_requires_applied_validated_and_closed_flag():
    flow = _workflow()
    assert "test \"$status\" = 'APPLIED_VALIDATED'" in flow
    assert "test \"${{ steps.flag_verify.outcome }}\" = success" in flow or "test \"${{ steps.flag_verify.outcome }}\" = 'success'" in flow
    assert "F2_3C_FLAG_CLOSED=PASS" in flow
