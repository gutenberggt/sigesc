"""Scope Creep Guard — Assessment Policy v1.

Cada sprint possui manifesto explícito. O guard falha se uma PR de Assessment
Policy alterar arquivos fora do domínio/entregáveis aprovados para aquela fase.
Arquivos compartilhados de integração podem, porém, ser alterados por PRs de
outros domínios sem transformar essas PRs em uma sprint de Assessment Policy.
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
    "backend/tests/test_assessment_policy_conflict_checker_v1.py",
    "memory/audit/ASSESSMENT_POLICY_V1_SPRINT_002_RESOLVER.md",
}

CALCULATOR_EXACT = COMMON_EXACT | {
    ".github/workflows/assessment-policy-calculator.yml",
    "backend/assessment_policy/__init__.py",
    "backend/assessment_policy/calculator.py",
    "backend/assessment_policy/exceptions.py",
    "backend/assessment_policy/recovery.py",
    "backend/assessment_policy/validator.py",
    "backend/tests/test_assessment_policy_calculator_v1.py",
    "backend/tests/test_assessment_policy_recovery_v1.py",
    "memory/audit/ASSESSMENT_POLICY_V1_SPRINT_003_CALCULATOR.md",
}

OUTCOME_EXACT = COMMON_EXACT | {
    ".github/workflows/assessment-policy-outcome.yml",
    "backend/assessment_policy/__init__.py",
    "backend/assessment_policy/exceptions.py",
    "backend/assessment_policy/models.py",
    "backend/assessment_policy/outcome.py",
    "backend/assessment_policy/validator.py",
    "backend/tests/test_assessment_policy_outcome_v1.py",
    "memory/audit/ASSESSMENT_POLICY_V1_SPRINT_004_OUTCOME.md",
}

SHADOW_EXACT = COMMON_EXACT | {
    ".github/workflows/assessment-policy-shadow.yml",
    "backend/assessment_policy/exceptions.py",
    "backend/assessment_policy/shadow.py",
    "backend/tests/test_assessment_policy_shadow_v1.py",
    "memory/audit/ASSESSMENT_POLICY_V1_SPRINT_005_SHADOW.md",
}

SHADOW_RUNNER_EXACT = COMMON_EXACT | {
    ".github/workflows/assessment-policy-shadow-runner.yml",
    "backend/assessment_policy/shadow_runner.py",
    "backend/tests/test_assessment_policy_shadow_runner_v1.py",
    "memory/audit/ASSESSMENT_POLICY_V1_SPRINT_006_SHADOW_RUNNER.md",
}

ASSISTED_CONFIG_EXACT = COMMON_EXACT | {
    ".github/workflows/assessment-policy-assisted-config.yml",
    "backend/assessment_policy/assisted_config.py",
    "backend/assessment_policy/pilot_runner.py",
    "backend/routers/assessment_policy_admin.py",
    "backend/routers/__init__.py",
    "backend/server.py",
    "backend/tests/test_assessment_policy_assisted_config_v1.py",
    "backend/tests/test_assessment_policy_pilot_runner_v1.py",
    "frontend/src/components/assessment-policy/AssessmentPolicyPanel.jsx",
    "frontend/src/pages/Mantenedora.js",
    "frontend/src/services/api.js",
    "memory/audit/ASSESSMENT_POLICY_V1_SPRINT_007_ASSISTED_CONFIG.md",
}

OPERATIONAL_BINDING_EXACT = COMMON_EXACT | {
    ".github/workflows/assessment-policy-operational-binding.yml",
    "backend/assessment_policy/operational_binding.py",
    "backend/tests/test_assessment_policy_operational_binding_v1.py",
    "memory/audit/ASSESSMENT_POLICY_V1_SPRINT_008_F0_OPERATIONAL_READINESS_ARCHITECTURE.md",
    "memory/audit/ASSESSMENT_POLICY_V1_SPRINT_008_F1_OPERATIONAL_BINDING.md",
}

PREFIX_BY_PHASE = {
    # Sprints históricas nasceram com criação ampla do pacote. Preservamos seus
    # manifestos para eventual manutenção da branch, sem ampliar as fases novas.
    "foundation": ("backend/assessment_policy/",),
    "resolver": ("backend/assessment_policy/",),
    "calculator": (),
    "outcome": (),
    "shadow": (),
    "shadow-runner": (),
    "assisted-config": (),
    "operational-binding": (),
    "unknown": (),
}

# Arquivos que pertencem inequivocamente ao domínio Assessment Policy. Arquivos
# compartilhados de integração (routers/__init__.py, server.py, Mantenedora.js,
# services/api.js) ficam de fora: eles podem disparar os testes de regressão do
# módulo sem obrigar uma PR de outro domínio a adotar o nome de uma sprint AP.
ASSESSMENT_OWNED_EXACT = {
    ".github/scripts/assessment_policy_scope_guard.py",
    "backend/routers/assessment_policy_admin.py",
}

ASSESSMENT_OWNED_PREFIXES = (
    ".github/workflows/assessment-policy-",
    "backend/assessment_policy/",
    "backend/tests/test_assessment_policy_",
    "frontend/src/components/assessment-policy/",
    "memory/audit/ASSESSMENT_POLICY_V1_",
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


def _manifest() -> tuple[str, set[str], tuple[str, ...]]:
    head_ref = (
        os.environ.get("GITHUB_HEAD_REF", "")
        or os.environ.get("GITHUB_REF_NAME", "")
    ).strip()

    if "assessment-policy-operational-binding" in head_ref:
        phase = "operational-binding"
        return phase, OPERATIONAL_BINDING_EXACT, PREFIX_BY_PHASE[phase]
    if "assessment-policy-assisted-config" in head_ref:
        phase = "assisted-config"
        return phase, ASSISTED_CONFIG_EXACT, PREFIX_BY_PHASE[phase]
    # A fase mais específica precisa vir primeiro, pois
    # "assessment-policy-shadow-runner" contém "assessment-policy-shadow".
    if "assessment-policy-shadow-runner" in head_ref:
        phase = "shadow-runner"
        return phase, SHADOW_RUNNER_EXACT, PREFIX_BY_PHASE[phase]
    if "assessment-policy-shadow" in head_ref:
        phase = "shadow"
        return phase, SHADOW_EXACT, PREFIX_BY_PHASE[phase]
    if "assessment-policy-outcome" in head_ref:
        phase = "outcome"
        return phase, OUTCOME_EXACT, PREFIX_BY_PHASE[phase]
    if "assessment-policy-calculator" in head_ref:
        phase = "calculator"
        return phase, CALCULATOR_EXACT, PREFIX_BY_PHASE[phase]
    if "assessment-policy-resolver" in head_ref:
        phase = "resolver"
        return phase, RESOLVER_EXACT, PREFIX_BY_PHASE[phase]
    if "assessment-policy-foundation" in head_ref:
        phase = "foundation"
        return phase, FOUNDATION_EXACT, PREFIX_BY_PHASE[phase]

    return "unknown", COMMON_EXACT, PREFIX_BY_PHASE["unknown"]


def _is_allowed(
    path: str,
    exact_allowed: set[str],
    prefix_allowed: tuple[str, ...],
) -> bool:
    if path in exact_allowed:
        return True
    return any(path.startswith(prefix) for prefix in prefix_allowed)


def _is_assessment_owned(path: str) -> bool:
    if path in ASSESSMENT_OWNED_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in ASSESSMENT_OWNED_PREFIXES)


def main() -> int:
    if not Path(".git").exists():
        print("ASSESSMENT_POLICY_SCOPE_GUARD=SKIP_NO_GIT")
        return 0

    phase, exact_allowed, prefix_allowed = _manifest()
    changed = _changed_files()

    print(f"ASSESSMENT_POLICY_SCOPE_GUARD_PHASE={phase}")
    print("ASSESSMENT_POLICY_SCOPE_GUARD_FILES=")
    for path in changed:
        marker = (
            "ALLOW"
            if _is_allowed(path, exact_allowed, prefix_allowed)
            else "DENY"
        )
        print(f"  [{marker}] {path}")

    # Uma PR alheia ao Assessment Policy pode alterar arquivos compartilhados
    # que também são pontos de integração do módulo. Nessa situação o workflow
    # deve executar seus testes de regressão, mas o scope guard da sprint não
    # pode falhar apenas porque a branch pertence a outro domínio. Se houver
    # qualquer arquivo inequivocamente próprio do Assessment Policy, mantemos o
    # fail-closed e exigimos uma branch/fase reconhecida.
    if phase == "unknown":
        owned = sorted(path for path in changed if _is_assessment_owned(path))
        if owned:
            print("ASSESSMENT_POLICY_SCOPE_GUARD=FAIL_UNKNOWN_PHASE")
            print("Arquivos próprios de Assessment Policy em branch sem fase reconhecida:")
            for path in owned:
                print(f"  - {path}")
            return 1
        print("ASSESSMENT_POLICY_SCOPE_GUARD=SKIP_SHARED_INTEGRATION_ONLY")
        return 0

    unexpected = sorted(
        path
        for path in changed
        if not _is_allowed(path, exact_allowed, prefix_allowed)
    )
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