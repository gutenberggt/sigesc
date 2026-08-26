"""Geração de matrícula (enrollment_number) — FONTE ÚNICA do sistema.

Toda matrícula DEVE ser gerada por esta função, que usa um contador ATÔMICO
(`enrollment_counters`, via find_one_and_update $inc) para garantir unicidade e
evitar colisões/reuso de números.

NÃO gere matrícula de outra forma (nada de count+1, Math.random, prefixos AUTO,
etc.). Geradores não-atômicos causam colisões (ver auditoria de Mai/2026).

Fase 1 — continuidade da identidade institucional:
fluxos de movimentação podem instalar, via ContextVar, um resolvedor de uso único
que devolve o número institucional já pertencente ao estudante. O override é
estritamente contextual ao request/coroutine; se o resolvedor retornar ``None``,
o gerador atômico normal continua sendo usado.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from pymongo import ReturnDocument


EnrollmentNumberResolver = Callable[[object, int], Awaitable[Optional[str]]]


@dataclass
class EnrollmentNumberOverrideState:
    """Estado observável de um override contextual de uso único."""

    resolver: EnrollmentNumberResolver
    consumed: bool = False
    resolved_number: Optional[str] = None


_enrollment_number_override: ContextVar[Optional[EnrollmentNumberOverrideState]] = (
    ContextVar("sigesc_enrollment_number_override", default=None)
)


@contextmanager
def enrollment_number_override_once(resolver: EnrollmentNumberResolver):
    """Instala um resolvedor contextual para a PRÓXIMA geração de matrícula.

    O resolvedor recebe ``(db, academic_year)`` e pode retornar:
    - um número institucional existente, que será usado sem incrementar contador;
    - ``None``, para delegar ao gerador atômico padrão.

    ContextVar impede vazamento entre requests concorrentes. O estado retornado
    permite ao wrapper confirmar se o ponto de geração foi realmente alcançado.
    """

    state = EnrollmentNumberOverrideState(resolver=resolver)
    token = _enrollment_number_override.set(state)
    try:
        yield state
    finally:
        _enrollment_number_override.reset(token)


async def generate_enrollment_number(db, academic_year: int) -> str:
    """Retorna uma matrícula única no formato `AAAA` + 5 dígitos sequenciais.

    Ex.: 202600001, 202600002, ...

    O contador é inicializado (uma única vez por ano) a partir do maior número
    já existente em `enrollments` daquele ano, para não colidir com dados legados.

    Quando um fluxo de movimentação instala ``enrollment_number_override_once``,
    o número institucional permanente pode conservar o prefixo do ano em que foi
    originalmente atribuído. Isso é intencional: o ano da matrícula acadêmica
    continua em ``academic_year``; o número identifica o estudante na rede.
    """
    override = _enrollment_number_override.get()
    if override is not None and not override.consumed:
        resolved = await override.resolver(db, academic_year)
        override.consumed = True
        override.resolved_number = str(resolved).strip() if resolved else None
        if override.resolved_number:
            return override.resolved_number

    counter_id = f"counter_{academic_year}"

    existing = await db.enrollment_counters.find_one({"_id": counter_id})
    if not existing:
        last = await db.enrollments.find_one(
            {"academic_year": academic_year},
            sort=[("enrollment_number", -1)],
        )
        start_seq = 0
        if last and last.get("enrollment_number"):
            try:
                start_seq = int(str(last["enrollment_number"])[-5:])
            except (ValueError, TypeError):
                start_seq = 0
        await db.enrollment_counters.update_one(
            {"_id": counter_id},
            {"$setOnInsert": {"sequence": start_seq}},
            upsert=True,
        )

    result = await db.enrollment_counters.find_one_and_update(
        {"_id": counter_id},
        {"$inc": {"sequence": 1}},
        return_document=ReturnDocument.AFTER,
    )
    return f"{academic_year}{str(result['sequence']).zfill(5)}"
