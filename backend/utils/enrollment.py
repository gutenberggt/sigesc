"""Geração de matrícula (enrollment_number) — FONTE ÚNICA do sistema.

Toda matrícula DEVE ser gerada por esta função, que usa um contador ATÔMICO
(`enrollment_counters`, via find_one_and_update $inc) para garantir unicidade e
evitar colisões/reuso de números.

NÃO gere matrícula de outra forma (nada de count+1, Math.random, prefixos AUTO,
etc.). Geradores não-atômicos causam colisões (ver auditoria de Mai/2026).
"""

from pymongo import ReturnDocument


async def generate_enrollment_number(db, academic_year: int) -> str:
    """Retorna uma matrícula única no formato `AAAA` + 5 dígitos sequenciais.

    Ex.: 202600001, 202600002, ...

    O contador é inicializado (uma única vez por ano) a partir do maior número
    já existente em `enrollments` daquele ano, para não colidir com dados legados.
    """
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
