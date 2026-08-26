#!/usr/bin/env python3
"""TOMBSTONE — gerador legado de números de matrícula.

RETIRADO por segurança em 26/08/2026.

Este script escrevia diretamente em ``students.enrollment_number`` sem passar
pela fonte canônica de matrículas e sem validar a identidade institucional já
existente em ``enrollments``. Esse comportamento é incompatível com a regra
atual do SIGESC e pode recriar divergências de identidade.

Qualquer saneamento de números deve usar processo governado, com evidência
histórica, preflight read-only, manifesto selado e revalidação imediatamente
antes de eventual escrita.

Este arquivo permanece no repositório somente como tombstone para que comandos
ou runbooks antigos falhem de forma explícita em vez de executar lógica legada.
Ele NÃO conecta ao MongoDB e NÃO possui caminho de escrita.
"""

from __future__ import annotations

import sys

RETIREMENT_CODE = "LEGACY_ENROLLMENT_NUMBER_WRITER_RETIRED"


def main() -> int:
    print(
        f"{RETIREMENT_CODE}: generate_enrollment_numbers.py foi aposentado. "
        "Use somente a reconciliação governada de identidade de matrícula.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
