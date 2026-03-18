"""
Script de migração: Define datas retroativas no histórico de alunos.
- Matrículas: 15 de janeiro do ano letivo
- Transferências: 10 de março do ano letivo
- Cancelamentos: 18 de janeiro do ano letivo
"""
import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()


async def migrate():
    client = AsyncIOMotorClient(os.environ.get('MONGO_URL'))
    db = client[os.environ.get('DB_NAME')]

    # Busca todos os registros de histórico sem data customizada ou com data do sistema
    all_history = await db.student_history.find({}, {"_id": 0, "id": 1, "action_type": 1, "action_date": 1}).to_list(None)

    updated = 0
    skipped = 0

    for entry in all_history:
        action_type = entry.get('action_type', '')
        entry_id = entry.get('id')
        if not entry_id:
            continue

        # Extrai o ano do action_date existente para usar no mapeamento
        action_date = entry.get('action_date', '')
        year = 2026  # Default
        if action_date:
            try:
                year = int(str(action_date)[:4])
            except (ValueError, TypeError):
                pass

        # Mapeamento de datas retroativas
        date_map = {
            'matricula': f"{year}-01-15T12:00:00+00:00",
            'transferencia_saida': f"{year}-03-10T12:00:00+00:00",
            'transferencia_entrada': f"{year}-03-10T12:00:00+00:00",
            'cancelamento': f"{year}-01-18T12:00:00+00:00",
        }

        new_date = date_map.get(action_type)
        if new_date:
            await db.student_history.update_one(
                {"id": entry_id},
                {"$set": {"action_date": new_date}}
            )
            updated += 1
        else:
            skipped += 1

    print(f"Migração concluída: {updated} registros atualizados, {skipped} ignorados (tipo não mapeado)")
    client.close()


if __name__ == '__main__':
    asyncio.run(migrate())
