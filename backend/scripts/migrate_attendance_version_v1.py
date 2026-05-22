"""
Migração Fase 1 (Rodada 1) — Mai/2026.

Garante que TODOS os docs de `attendance` tenham `version` definido e
analisa se existem colisões para o UNIQUE composto
`{class_id, date, course_id, aula_numero}`.

NÃO deleta nada. NÃO modifica `records[]`. Apenas:
  - Adiciona `version=1` nos docs onde ausente.
  - Reporta colisões para revisão manual antes de aplicar o índice UNIQUE.

Idempotente. Pode rodar quantas vezes for necessário.

Uso:
    cd /app/backend && python scripts/migrate_attendance_version_v1.py
    cd /app/backend && python scripts/migrate_attendance_version_v1.py --dry-run
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()


async def main(dry_run: bool):
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = cli[os.environ["DB_NAME"]]

    print("=" * 60)
    print("MIGRAÇÃO Fase 1 — attendance.version")
    print(f"  MODE: {'DRY-RUN (não persiste)' if dry_run else 'APPLY'}")
    print("=" * 60)

    # 1) Backfill version=1 em docs sem o campo
    missing = await db.attendance.count_documents({"version": {"$exists": False}})
    print(f"\n[1/3] Docs sem `version`: {missing}")
    if missing > 0 and not dry_run:
        res = await db.attendance.update_many(
            {"version": {"$exists": False}},
            {"$set": {"version": 1, "_version_migrated_at": datetime.now(timezone.utc).isoformat()}},
        )
        print(f"      → {res.modified_count} docs atualizados com version=1")
    elif missing == 0:
        print("      → nada a fazer")

    # 2) Verifica colisões para o UNIQUE composto
    print("\n[2/3] Verificando colisões {class_id,date,course_id,aula_numero}...")
    pipeline = [
        {"$group": {
            "_id": {
                "class_id": "$class_id",
                "date": "$date",
                "course_id": "$course_id",
                "aula_numero": "$aula_numero",
            },
            "n": {"$sum": 1},
            "ids": {"$push": "$id"},
        }},
        {"$match": {"n": {"$gt": 1}}},
        {"$sort": {"n": -1}},
    ]
    collisions = await db.attendance.aggregate(pipeline).to_list(1000)
    print(f"      → colisões encontradas: {len(collisions)}")
    if collisions:
        print("      Amostra (até 10):")
        for c in collisions[:10]:
            print(f"        - {c['_id']} ({c['n']}x): {c['ids'][:3]}")
        print()
        print("      ATENÇÃO: aplicar UNIQUE composto AGORA falharia.")
        print("      Sugestão: revisar duplicidades manualmente OU normalizar")
        print("      `course_id` e `aula_numero` (null vs absent) antes.")
    else:
        print("      → seguro para aplicar UNIQUE composto.")

    # 3) Verificação final
    total = await db.attendance.count_documents({})
    with_version = await db.attendance.count_documents({"version": {"$exists": True}})
    print(f"\n[3/3] Estado final: {with_version}/{total} docs com version definido")

    print("\nFeito.")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    asyncio.run(main(dry))
