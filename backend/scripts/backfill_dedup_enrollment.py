#!/usr/bin/env python3
"""
[P1] Backfill + Deduplicação de números de matrícula (enrollment_number).

Sana o passivo de matrículas AUSENTES (vazias) e DUPLICADAS no SIGESC, nas
coleções `students` (identidade do aluno) e `enrollments` (matrícula por ano).
Ao final, pode aplicar um ÍNDICE ÚNICO PARCIAL para impedir reincidência.

REGRAS (alinhadas com o usuário — Fev/2026):
  - DUPLICADAS: mantém a matrícula do registro/aluno MAIS ANTIGO (menor
    created_at / enrollment_date) e GERA nova matrícula para os demais.
  - AUSENTES (vazias/nulas): preenche com nova matrícula via gerador ATÔMICO
    central (`utils.enrollment.generate_enrollment_number`).
  - O contador atômico é "sememeado" (via $max) acima do maior número já
    existente no ano, para nunca colidir com dados legados.

SEGURANÇA:
  - Por PADRÃO roda em --dry-run (NÃO altera nada). Apenas reporta o plano.
  - Para EXECUTAR de fato é OBRIGATÓRIO passar --apply.
  - O índice único só é criado com --apply E --create-index.

Uso:
  cd /app/backend
  python3 scripts/backfill_dedup_enrollment.py                  # dry-run (relatório)
  python3 scripts/backfill_dedup_enrollment.py --apply          # executa backfill+dedup
  python3 scripts/backfill_dedup_enrollment.py --apply --create-index  # + índice único
  python3 scripts/backfill_dedup_enrollment.py --year 2026      # ano dos novos números
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime

# Garante que `utils.enrollment` seja importável (raiz = /app/backend)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Carrega .env (mesma estratégia dos outros scripts do projeto)
for env_path in [
    '.env', '../.env', 'backend/.env',
    os.path.join(os.path.dirname(__file__), '.env'),
    os.path.join(os.path.dirname(__file__), '..', '.env'),
]:
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    val = val.strip().strip('"').strip("'")
                    if key.strip() not in os.environ:
                        os.environ[key.strip()] = val
        break

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import ReturnDocument  # noqa: E402

EMPTY_FILTER = {"$or": [
    {"enrollment_number": {"$exists": False}},
    {"enrollment_number": None},
    {"enrollment_number": ""},
]}


def _sort_key(doc):
    """Chave de ordenação para achar o registro/aluno MAIS ANTIGO.

    Usa a menor data disponível entre enrollment_date e created_at. Registros
    sem nenhuma data vão por último (mantemos por estabilidade os com data).
    """
    candidates = []
    for field in ("enrollment_date", "created_at"):
        v = doc.get(field)
        if v:
            candidates.append(str(v))
    return min(candidates) if candidates else "9999-99-99"


async def _compute_seed_max(db, year):
    """Maior sufixo numérico (5 dígitos) já usado no ano, em ambas as coleções."""
    prefix = str(year)
    regex = {"$regex": f"^{prefix}\\d{{5}}$"}
    maxv = 0
    for coll in (db.students, db.enrollments):
        docs = await coll.find(
            {"enrollment_number": regex}, {"_id": 0, "enrollment_number": 1}
        ).sort("enrollment_number", -1).limit(1).to_list(1)
        if docs:
            try:
                maxv = max(maxv, int(docs[0]["enrollment_number"][-5:]))
            except (ValueError, TypeError):
                pass
    return maxv


class NumberFactory:
    """Gera números de matrícula únicos, evitando colisões com dados existentes.

    Em --apply usa o gerador atômico real (counter no Mongo). Em dry-run
    simula a sequência localmente, sem tocar no banco.
    """

    def __init__(self, db, year, apply, start_seq, existing):
        self.db = db
        self.year = year
        self.apply = apply
        self._sim_seq = start_seq
        # conjunto de números já "usados" (existentes + recém-gerados)
        self._used = set(existing)

    async def next(self):
        while True:
            if self.apply:
                from utils.enrollment import generate_enrollment_number
                num = await generate_enrollment_number(self.db, self.year)
            else:
                self._sim_seq += 1
                num = f"{self.year}{str(self._sim_seq).zfill(5)}"
            if num not in self._used:
                self._used.add(num)
                return num


async def _all_existing_numbers(db):
    nums = set()
    for coll in (db.students, db.enrollments):
        docs = await coll.find(
            {"enrollment_number": {"$gt": ""}}, {"_id": 0, "enrollment_number": 1}
        ).to_list(None)
        for d in docs:
            nums.add(d["enrollment_number"])
    return nums


async def dedup_collection(db, coll, coll_name, owner_field, factory, apply):
    """Deduplica enrollment_number numa coleção.

    Mantém o doc mais antigo; regenera para os demais. Retorna estatísticas.
    """
    pipeline = [
        {"$match": {"enrollment_number": {"$gt": ""}}},
        {"$group": {
            "_id": "$enrollment_number",
            "count": {"$sum": 1},
            "docs": {"$push": {
                "oid": "$_id",
                "owner": f"${owner_field}",
                "created_at": "$created_at",
                "enrollment_date": "$enrollment_date",
            }},
        }},
        {"$match": {"count": {"$gt": 1}}},
    ]
    groups = await coll.aggregate(pipeline).to_list(None)

    print(f"\n  [{coll_name}] números duplicados: {len(groups)}")
    regen = 0
    for g in groups:
        number = g["_id"]
        docs = sorted(g["docs"], key=_sort_key)
        keeper = docs[0]
        losers = docs[1:]
        print(f"    - '{number}' usado por {g['count']} registros; "
              f"mantém owner={keeper['owner']} (mais antigo), "
              f"regenera {len(losers)}.")
        for loser in losers:
            new_num = await factory.next()
            regen += 1
            print(f"        owner={loser['owner']}  {number} -> {new_num}")
            if apply:
                await coll.update_one(
                    {"_id": loser["oid"], "enrollment_number": number},
                    {"$set": {"enrollment_number": new_num}},
                )
    return regen


async def backfill_collection(db, coll, coll_name, factory, apply):
    """Preenche enrollment_number ausente/vazio."""
    cursor = coll.find(EMPTY_FILTER, {"_id": 1, "id": 1, "full_name": 1})
    docs = await cursor.to_list(None)
    print(f"\n  [{coll_name}] registros sem matrícula: {len(docs)}")
    filled = 0
    for d in docs:
        new_num = await factory.next()
        filled += 1
        label = d.get("full_name") or d.get("id") or str(d["_id"])
        if filled <= 20:  # evita poluir log em massa
            print(f"    + {label}: (vazio) -> {new_num}")
        if apply:
            await coll.update_one(
                {"_id": d["_id"]},
                {"$set": {"enrollment_number": new_num}},
            )
    if filled > 20:
        print(f"    ... (+{filled - 20} outros)")
    return filled


async def create_unique_index(db, coll, coll_name, apply):
    """Cria índice ÚNICO PARCIAL (apenas strings não-vazias)."""
    index_name = "uq_enrollment_number"
    # Verifica duplicatas remanescentes antes de tentar criar
    pipeline = [
        {"$match": {"enrollment_number": {"$gt": ""}}},
        {"$group": {"_id": "$enrollment_number", "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}},
        {"$count": "dups"},
    ]
    r = await coll.aggregate(pipeline).to_list(1)
    remaining = r[0]["dups"] if r else 0
    if remaining:
        print(f"  [{coll_name}] ⚠ ABORTADO índice: ainda há {remaining} "
              f"duplicatas. Rode o dedup antes.")
        return False
    if not apply:
        print(f"  [{coll_name}] (dry-run) criaria índice único parcial "
              f"'{index_name}' em enrollment_number.")
        return True
    await coll.create_index(
        "enrollment_number",
        unique=True,
        name=index_name,
        partialFilterExpression={"enrollment_number": {"$gt": ""}},
    )
    print(f"  [{coll_name}] ✓ índice único '{index_name}' criado.")
    return True


async def main():
    parser = argparse.ArgumentParser(description="Backfill + dedup de matrículas")
    parser.add_argument("--apply", action="store_true",
                        help="Executa de fato (sem isto, roda em dry-run).")
    parser.add_argument("--create-index", action="store_true",
                        help="Cria índice único parcial ao final.")
    parser.add_argument("--year", type=int, default=datetime.now().year,
                        help="Ano usado nos novos números (default: ano atual).")
    args = parser.parse_args()

    apply = args.apply
    year = args.year

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("❌ MONGO_URL ou DB_NAME ausente no ambiente.")
        sys.exit(1)

    db = AsyncIOMotorClient(mongo_url)[db_name]

    print("=" * 70)
    print(f"  BACKFILL + DEDUP DE MATRÍCULAS — SIGESC (DB: {db_name})")
    print(f"  Ano dos novos números: {year}")
    print(f"  Modo: {'APPLY (ALTERA O BANCO)' if apply else 'DRY-RUN (somente relatório)'}")
    print("=" * 70)

    # --- Auditoria inicial ---
    st_total = await db.students.count_documents({})
    st_empty = await db.students.count_documents(EMPTY_FILTER)
    en_total = await db.enrollments.count_documents({})
    en_empty = await db.enrollments.count_documents(EMPTY_FILTER)
    print(f"\n[AUDITORIA] students: {st_total} total, {st_empty} sem matrícula")
    print(f"[AUDITORIA] enrollments: {en_total} total, {en_empty} sem matrícula")

    # --- Prepara fábrica de números ---
    seed = await _compute_seed_max(db, year)
    print(f"\n[SEED] maior sufixo no ano {year}: {seed}")
    if apply:
        await db.enrollment_counters.update_one(
            {"_id": f"counter_{year}"},
            {"$max": {"sequence": seed}},
            upsert=True,
        )
        ctr = await db.enrollment_counters.find_one({"_id": f"counter_{year}"})
        seed = ctr.get("sequence", seed)

    existing = await _all_existing_numbers(db)
    factory = NumberFactory(db, year, apply, seed, existing)

    # --- Fase 1: Dedup (resolve colisões ANTES do índice) ---
    print("\n" + "-" * 70)
    print("FASE 1 — DEDUPLICAÇÃO")
    print("-" * 70)
    regen_st = await dedup_collection(db, db.students, "students", "id", factory, apply)
    regen_en = await dedup_collection(db, db.enrollments, "enrollments", "student_id", factory, apply)

    # --- Fase 2: Backfill (preenche vazios) ---
    print("\n" + "-" * 70)
    print("FASE 2 — BACKFILL DE VAZIOS")
    print("-" * 70)
    fill_st = await backfill_collection(db, db.students, "students", factory, apply)
    fill_en = await backfill_collection(db, db.enrollments, "enrollments", factory, apply)

    # --- Fase 3: Índice único (opcional) ---
    print("\n" + "-" * 70)
    print("FASE 3 — ÍNDICE ÚNICO PARCIAL")
    print("-" * 70)
    if args.create_index:
        await create_unique_index(db, db.students, "students", apply)
        await create_unique_index(db, db.enrollments, "enrollments", apply)
    else:
        print("  (pulado — passe --create-index para criar)")

    # --- Resumo ---
    print("\n" + "=" * 70)
    print("RESUMO")
    print("=" * 70)
    print(f"  Dedup students  : {regen_st} números regenerados")
    print(f"  Dedup enrollments: {regen_en} números regenerados")
    print(f"  Backfill students  : {fill_st} preenchidos")
    print(f"  Backfill enrollments: {fill_en} preenchidos")
    if not apply:
        print("\n[DRY-RUN] Nenhuma alteração foi feita. Use --apply para executar.")
    else:
        print("\n[APPLY] Alterações aplicadas com sucesso.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
