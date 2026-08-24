from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ROLE_CONTEXT = REPO_ROOT / "backend" / "role_context.py"


def test_role_context_does_not_gate_school_scope_by_lotacao_funcao():
    source = ROLE_CONTEXT.read_text(encoding="utf-8")

    assert 'if funcao != active_role' not in source
    assert '"funcao": 1' not in source
    assert '"has_role_assignment": True' in source
    assert 'school_assignments.funcao' in source
    assert 'MUST NOT' in source
