import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')

async def fix_status():
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ.get('DB_NAME', 'sigesc_db')]
    
    # Atualizar todos os alunos com status null ou inexistente para 'active'
    result = await db.students.update_many(
        {"$or": [
            {"status": None},
            {"status": ""},
            {"status": {"$exists": False}}
        ]},
        {"$set": {"status": "active"}}
    )
    
    print(f"✅ Alunos atualizados para status 'active': {result.modified_count}")
    
    # Verificar
    ativos = await db.students.count_documents({"status": "active"})
    inativos = await db.students.count_documents({"status": {"$ne": "active"}})
    print(f"   - Alunos ativos: {ativos}")
    print(f"   - Alunos com outros status: {inativos}")
    
    client.close()

asyncio.run(fix_status())
