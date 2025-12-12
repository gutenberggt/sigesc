import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')

async def verify():
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ.get('DB_NAME', 'sigesc_db')]
    
    # Verificar alunos sem matrícula
    sem_matricula = await db.students.count_documents({
        "$or": [
            {"enrollment_number": None}, 
            {"enrollment_number": ""}, 
            {"enrollment_number": {"$exists": False}}
        ]
    })
    
    # Total de alunos
    total = await db.students.count_documents({})
    
    # Exemplos de alunos com matrícula
    exemplos = await db.students.find(
        {"enrollment_number": {"$regex": "^2025"}},
        {"_id": 0, "full_name": 1, "enrollment_number": 1}
    ).sort("enrollment_number", 1).limit(5).to_list(5)
    
    print(f"📊 Verificação:")
    print(f"   - Total de alunos: {total}")
    print(f"   - Alunos SEM matrícula: {sem_matricula}")
    print(f"   - Alunos COM matrícula: {total - sem_matricula}")
    
    print(f"\n📋 Primeiros 5 alunos com matrícula gerada:")
    for s in exemplos:
        print(f"   - {s.get('enrollment_number')} | {s.get('full_name', 'N/A')[:40]}")
    
    client.close()

asyncio.run(verify())
