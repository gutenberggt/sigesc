#!/usr/bin/env python3
"""Guard de nomenclatura institucional do SIGESC.

Política:
- linguagem visível nova usa Estudante / Estudantes;
- legado técnico deliberado (role="aluno", /aluno, slugs etc.) permanece;
- documentação viva (README.md + docs/**/*.md) é verificada integralmente;
- código de produto é verificado apenas nas linhas adicionadas pelo diff.

Sem dependências externas. Projetado para GitHub Actions e execução local.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Documento que, por definição, precisa citar os termos proibidos para explicar a regra.
DOC_PATH_ALLOWLIST = {
    "docs/NOMENCLATURA_INSTITUCIONAL.md",
}

# Evidência histórica / testes não são linguagem de produto vigente.
DIFF_EXCLUDED_PREFIXES = (
    "memory/",
    "test_reports/",
    "backend/tests/",
    "backend/seeds/",
    "backend/scripts/",
    "frontend/src/__tests__/",
)

# Áreas de código onde uma string adicionada pode chegar à experiência do usuário.
DIFF_SCOPES = (
    "frontend/src/",
    "backend/routers/",
    "backend/services/",
    "backend/utils/",
    "backend/pdf/",
    "backend/audit_service.py",
)

# Formas que não devem reaparecer como linguagem institucional.
LEGACY_TERM_RE = re.compile(
    r"(?i)(?<![\w])(?:aluno\(a\)|alunos\(as\)|aluno|aluna|alunos|alunas)(?![\w])"
)
BAD_ESTUDANTE_FLEX_RE = re.compile(
    r"(?i)(?<![\w])(?:estudante\(a\)|estudantes\(as\))(?![\w])"
)

# O papel técnico continua sendo aluno. Esta regra impede migração acidental de auth.
TECHNICAL_ROLE_ESTUDANTE_RE = re.compile(
    r"(?i)(?:\brole\b|\broles\b|userRole|currentRole|hasRole|allowed_roles|allowedRoles|perfil)"
    r".{0,80}[\"']estudante[\"']|"
    r"[\"']estudante[\"'].{0,80}(?:\brole\b|\broles\b|userRole|currentRole|hasRole|allowed_roles|allowedRoles|perfil)"
)

# Remove somente a ocorrência técnica "aluno" quando ela está associada a papel/autorização.
TECHNICAL_ROLE_ALUNO_RE = re.compile(
    r"(?i)((?:\brole\b|\broles\b|userRole|currentRole|hasRole|allowed_roles|allowedRoles|perfil)"
    r".{0,80}?)[\"']aluno[\"']|"
    r"[\"']aluno[\"'](.{0,80}?(?:\brole\b|\broles\b|userRole|currentRole|hasRole|allowed_roles|allowedRoles|perfil))"
)

INLINE_WAIVER = "nomenclature-allow"


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    message: str
    text: str


def run_git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} falhou ({proc.returncode}): {proc.stderr.strip()}"
        )
    return proc.stdout


def is_comment_only(line: str) -> bool:
    stripped = line.strip()
    return (
        stripped.startswith("#")
        or stripped.startswith("//")
        or stripped.startswith("/*")
        or stripped.startswith("*")
        or stripped.startswith("<!--")
    )


def remove_role_aluno_segments(line: str) -> str:
    """Remove apenas o literal técnico aluno de contextos de role/perfil.

    Mantém o restante da linha para que, por exemplo,
    `{ aluno: "Aluno" }` continue acusando o label visual "Aluno".
    """
    result = line
    # Substituição iterativa porque uma linha pode ter mais de um papel.
    for _ in range(8):
        match = TECHNICAL_ROLE_ALUNO_RE.search(result)
        if not match:
            break
        start, end = match.span()
        segment = result[start:end]
        segment = re.sub(r"(?i)[\"']aluno[\"']", '"__ROLE_ALUNO__"', segment, count=1)
        result = result[:start] + segment + result[end:]
    return result


def sanitize_allowed_contexts(path: str, line: str) -> str:
    if INLINE_WAIVER in line:
        return ""

    value = line

    # Rotas e slugs legados deliberadamente preservados.
    value = re.sub(r"(?i)/aluno(?=/|[\"'`\s]|$)", "/__LEGACY_ROLE_ROUTE__", value)
    value = re.sub(r"(?i)\bcadastro-aluno\b", "cadastro-__LEGACY__", value)
    value = re.sub(r"(?i)\bdocumentos-aluno\b", "documentos-__LEGACY__", value)

    # Nomes de arquivos/componentes legados não casam com a regex de palavra inteira,
    # mas mantemos proteção explícita para documentação textual.
    for name in ("AlunoDashboard", "BoletimAluno", "AlunoTab"):
        value = value.replace(name, "__LEGACY_COMPONENT__")

    # Variante histórica que DEVE continuar no validador para ser rejeitada.
    if path.endswith("backend/utils/diary_constants.py") or path.endswith("docs/DIARY_API_CONTRACT.md"):
        value = value.replace("Aluno dependência", "__FORBIDDEN_LEGACY_LABEL__")

    value = remove_role_aluno_segments(value)
    return value


def check_line(path: str, line_no: int, line: str, *, allow_comment: bool) -> list[Violation]:
    if INLINE_WAIVER in line:
        return []
    if allow_comment and is_comment_only(line):
        return []

    violations: list[Violation] = []
    sanitized = sanitize_allowed_contexts(path, line)

    if TECHNICAL_ROLE_ESTUDANTE_RE.search(line):
        violations.append(
            Violation(
                path,
                line_no,
                'Papel técnico deve continuar "aluno"; "estudante" é rótulo institucional, não valor de auth.',
                line.rstrip(),
            )
        )

    if BAD_ESTUDANTE_FLEX_RE.search(sanitized):
        violations.append(
            Violation(
                path,
                line_no,
                'Não use "Estudante(a)"/"Estudantes(as)"; use Estudante/Estudantes.',
                line.rstrip(),
            )
        )

    if LEGACY_TERM_RE.search(sanitized):
        violations.append(
            Violation(
                path,
                line_no,
                'Nomenclatura institucional nova deve usar "Estudante/Estudantes". Se for exceção legítima, documente com "nomenclature-allow".',
                line.rstrip(),
            )
        )

    return violations


def check_live_docs() -> list[Violation]:
    violations: list[Violation] = []
    targets = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
    for path in targets:
        if not path.exists():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel in DOC_PATH_ALLOWLIST:
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            # Em documentação, inclusive exemplos em blocos de código são verificados;
            # exceções técnicas são tratadas por sanitize_allowed_contexts.
            violations.extend(check_line(rel, line_no, line, allow_comment=False))
    return violations


def in_diff_scope(path: str) -> bool:
    if any(path.startswith(prefix) for prefix in DIFF_EXCLUDED_PREFIXES):
        return False
    return any(path == scope or path.startswith(scope) for scope in DIFF_SCOPES)


def resolve_base() -> str:
    explicit = os.getenv("NOMENCLATURE_BASE")
    if explicit:
        return explicit

    event = os.getenv("GITHUB_EVENT_NAME", "")
    base_ref = os.getenv("GITHUB_BASE_REF", "")
    if event == "pull_request" and base_ref:
        return f"origin/{base_ref}"

    # Push para main: compara apenas o commit que acabou de entrar.
    return "HEAD^"


def parse_added_lines(diff: str) -> list[tuple[str, int, str]]:
    items: list[tuple[str, int, str]] = []
    current_path: str | None = None
    new_line = 0

    hunk_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

    for raw in diff.splitlines():
        if raw.startswith("+++ b/"):
            current_path = raw[6:]
            continue
        if raw.startswith("@@"):
            match = hunk_re.match(raw)
            if match:
                new_line = int(match.group(1))
            continue
        if current_path is None:
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            items.append((current_path, new_line, raw[1:]))
            new_line += 1
        elif raw.startswith("-") and not raw.startswith("---"):
            # Remoção não avança número da linha nova.
            continue
        else:
            new_line += 1

    return items


def check_added_product_lines() -> list[Violation]:
    base = resolve_base()
    diff = run_git("diff", "--unified=0", "--no-color", f"{base}...HEAD")
    violations: list[Violation] = []
    for path, line_no, line in parse_added_lines(diff):
        if not in_diff_scope(path):
            continue
        violations.extend(check_line(path, line_no, line, allow_comment=True))
    return violations


def self_test() -> None:
    def messages(path: str, text: str) -> list[str]:
        return [v.message for v in check_line(path, 1, text, allow_comment=False)]

    assert messages("frontend/src/X.jsx", '<span>Aluno</span>')
    assert messages("backend/routers/x.py", 'detail="Alunos não encontrados"')
    assert not messages("backend/routers/x.py", 'if role == "aluno":')
    assert not messages("frontend/src/App.js", 'path="/aluno"')
    assert not messages("frontend/src/T.js", "slug: 'cadastro-aluno'")
    assert not messages("backend/utils/diary_constants.py", '"Aluno dependência",')
    assert messages("frontend/src/X.jsx", '<span>Estudante(a)</span>')
    assert any("Papel técnico" in m for m in messages("backend/x.py", 'if role == "estudante":'))
    assert not messages("frontend/src/X.jsx", '"Programa Oficial do Aluno" // nomenclature-allow: externo')


def emit(violations: list[Violation]) -> int:
    if not violations:
        print("Nomenclature guard: OK — nenhuma regressão Aluno × Estudante detectada.")
        return 0

    print(f"Nomenclature guard: {len(violations)} violação(ões) detectada(s).", file=sys.stderr)
    for item in violations:
        # Formato entendido pelo GitHub Actions como annotation.
        safe_msg = item.message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::error file={item.path},line={item.line}::{safe_msg}", file=sys.stderr)
        print(f"  {item.path}:{item.line}: {item.text}", file=sys.stderr)
    return 1


def main() -> int:
    self_test()
    violations = check_live_docs()
    violations.extend(check_added_product_lines())

    # Remove duplicatas que podem ser detectadas pelas duas camadas em docs alterados.
    unique: dict[tuple[str, int, str], Violation] = {}
    for item in violations:
        unique[(item.path, item.line, item.message)] = item
    return emit(list(unique.values()))


if __name__ == "__main__":
    raise SystemExit(main())
