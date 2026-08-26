#!/usr/bin/env python3
"""TOMBSTONE — backfill/dedup legado de números de matrícula.

RETIRADO por segurança em 26/08/2026.

A versão histórica deste utilitário tratava ``students`` e ``enrollments`` como
coleções independentes para deduplicação/backfill de ``enrollment_number``.
Isso permite gerar identidades diferentes para o mesmo estudante e é
incompatível com a arquitetura canônica atual, na qual o vínculo regular ativo
em ``enrollments`` governa a projeção numérica em ``students``.

O antigo ``--apply`` e a criação de índice foram removidos de propósito. Este
arquivo permanece apenas como tombstone operacional para bloquear runbooks ou
comandos antigos com uma mensagem inequívoca.

Reconciliações atuais exigem processo governado: evidência histórica, preflight
read-only, manifesto selado, quarentena de exceções, revalidação imediatamente
antes da escrita e recibo da execução autorizada.

Este módulo NÃO importa driver MongoDB, NÃO conecta ao banco e NÃO possui
primitivas de escrita.
"""

from __future__ import annotations

import sys

RETIREMENT_CODE = "LEGACY_ENROLLMENT_BACKFILL_RETIRED"


def main() -> int:
    print(
        f"{RETIREMENT_CODE}: scripts/backfill_dedup_enrollment.py foi aposentado. "
        "Não use --apply nem gere números independentemente por coleção. "
        "Use somente reconciliação governada de identidade de matrícula.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
