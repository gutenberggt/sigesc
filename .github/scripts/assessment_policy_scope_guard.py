"""Scope Creep Guard — Assessment Policy Foundation v1.

Falha o CI se a branch de foundation alterar arquivos fora do escopo aprovado.
É deliberadamente específico desta sprint; sprints futuras terão manifests
próprios em vez de ampliar silenciosamente este allowlist.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


EXACT_ALLOWED = {
    ".github/scripts/assessment_policy_scope_guard.py",
    ".github/workflows/assessment-policy-foundation.yml",
    "backend/tests/test_assessment_policy_foundation_v1.py",
    "backend/tests/test_assessment_policy_registry_v1.py",
    "memory/audit/ASSESSMENT_POLICY_V1_SPRINT_001_FOUNDATION.md",
    "memory/audit/ASSESSMENT_POLICY_V1_DEPENDENCY_MATRIX.md",
}

PREFIX_ALLOWED = (
    "backend/assessment_policy/",
)


def _run(*args: str) -> str:
    result = subprocess.run(
        args,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def _changed_files() -> list[str]:
    base_ref = os.environ.get("GITHUB_BASE_REF", "").strip()

    if base_ref:
        remote_ref = f"origin/{base_ref}"
        try:
            _run("git", "rev-parse", "--verify", remote_ref)
            output = _run("git", "diff", "--name-only", f"{remote_ref}...HEAD")
            return [line.strip() for line in output.splitlines() if line.strip()]
        except subprocess.CalledProcessError:
            pass

    output = _run("git", "diff", "--name-only", "HEAD^")
    return [line.strip() for line in output.splitlines() if line.strip()]


def _is_allowed(path: str) -> bool:
    if path in EXACT_ALLOWED:
        return True
    return any(path.startswith(prefix) for prefix in PREFIX_ALLOWED)


def main() -> int:
    if not Path(".git").exists():
        print("ASSESSMENT_POLICY_SCOPE_GUARD=SKIP_NO_GIT")
        return 0

    changed = _changed_files()
    unexpected = sorted(path for path in changed if not _is_allowed(path))

    print("ASSESSMENT_POLICY_SCOPE_GUARD_FILES=")
    for path in changed:
        marker = "ALLOW" if _is_allowed(path) else "DENY"
        print(f"  [{marker}] {path}")

    if unexpected:
        print("ASSESSMENT_POLICY_SCOPE_GUARD=FAIL")
        print("Arquivos fora do escopo Foundation:")
        for path in unexpected:
            print(f"  - {path}")
        return 1

    print("ASSESSMENT_POLICY_SCOPE_GUARD=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
