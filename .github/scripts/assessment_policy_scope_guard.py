"""Scope Creep Guard — Assessment Policy v1.

Cada sprint possui manifesto explícito. O guard falha se a PR alterar arquivos
fora do domínio/entregáveis aprovados para aquela fase. Isso evita ampliar
silenciosamente o escopo entre Foundation, Resolver e fases futuras.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


COMMON_EXACT = {
    ".github/scripts/assessment_policy_scope_guard.py",
}

FOUNDATION_EXACT = COMMON_EXACT | {
    ".github/workflows/assessment-policy-foundation.yml",
    "backend/tests/test_assessment_policy_foundation_v1.py",
    "backend/tests/test_assessment_policy_registry_v1.py",
    "memory/audit/ASSESSMENT_POLICY_V1_SPRINT_001_FOUNDATION.md",
    "memory/audit/ASSESSMENT_POLICY_V1_DEPENDENCY_MATRIX.md",
}

RESOLVER_EXACT = COMMON_EXACT | {
    ".github/workflows/assessment-policy-foundation.yml",
    ".github/workflows/assessment-policy-resolver.yml",
    "backend/tests/test_assessment_policy_resolver_v1.py",
    "backend/tests/test_assessment_policy_series_resolver_v1.py",
    "backend/tests/test_assessment_policy_context_builder_v1.py",
    "backend/tests/test_assessment_policy_conflict_checker_v1.py",
    "memory/audit/ASSESSMENT_POLICY_V1_SPRINT_002_RESOLVER.md",
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


def _manifest() -> tuple[str, set[str]]:
    head_ref = (
        os.environ.get("GITHUB_HEAD_REF", "")
        or os.environ.get("GITHUB_REF_NAME", "")
    ).strip()

    if "assessment-policy-resolver" in head_ref:
        return "resolver", RESOLVER_EXACT
    if "assessment-policy-foundation" in head_ref:
        return "foundation", FOUNDATION_EXACT

    # Fail-closed: uma branch não reconhecida não herda automaticamente o
    # manifesto mais permissivo de outra sprint.
    return "unknown", COMMON_EXACT


def _is_allowed(path: str, exact_allowed: set[str]) -> bool:
    if path in exact_allowed:
        return True
    return any(path.startswith(prefix) for prefix in PREFIX_ALLOWED)


def main() -> int:
    if not Path(".git").exists():
        print("ASSESSMENT_POLICY_SCOPE_GUARD=SKIP_NO_GIT")
        return 0

    phase, exact_allowed = _manifest()
    changed = _changed_files()
    unexpected = sorted(
        path for path in changed if not _is_allowed(path, exact_allowed)
    )

    print(f"ASSESSMENT_POLICY_SCOPE_GUARD_PHASE={phase}")
    print("ASSESSMENT_POLICY_SCOPE_GUARD_FILES=")
    for path in changed:
        marker = "ALLOW" if _is_allowed(path, exact_allowed) else "DENY"
        print(f"  [{marker}] {path}")

    if phase == "unknown":
        print("ASSESSMENT_POLICY_SCOPE_GUARD=FAIL_UNKNOWN_PHASE")
        return 1

    if unexpected:
        print("ASSESSMENT_POLICY_SCOPE_GUARD=FAIL")
        print(f"Arquivos fora do escopo da sprint {phase}:")
        for path in unexpected:
            print(f"  - {path}")
        return 1

    print("ASSESSMENT_POLICY_SCOPE_GUARD=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
