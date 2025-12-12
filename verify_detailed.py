import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')

async def verify():
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ.get('DB_NAME', 'sigesc_db')]
    
    # Verificar total de alunos
    total = await db.students.count_documents({})
    print(f"Total de alunos no banco: {total}")
    
    # Verificar alunos com enrollment_number
    com_matricula = await db.students.count_documents({"enrollment_number": {"$exists": True, "$ne": None, "$ne": ""}})
    print(f"Alunos com enrollment_number: {com_matricula}")
    
    # Verificar alguns registros específicos da Floresta do Araguaia
    floresta_school = await db.schools.find_one({"name": {"$regex": "Floresta", "$options": "i"}})
    if floresta_school:
        print(f"\nEscola: {floresta_school['name']} (ID: {floresta_school['id'][:8]}...)")
        
        # Contar alunos dessa escola
        alunos_floresta = await db.students.count_documents({"school_id": floresta_school['id']})
        print(f"Alunos nesta escola: {alunos_floresta}")
        
        # Verificar alguns registros
        exemplos = await db.students.find(
            {"school_id": floresta_school['id']},
            {"_id": 0, "full_name": 1, "enrollment_number": 1}
        ).limit(10).to_list(10)
        
        print(f"\nPrimeiros 10 alunos da Floresta do Araguaia:")
        for s in exemplos:
            print(f"  - Matrícula: '{s.get('enrollment_number', 'N/A')}' | Nome: {s.get('full_name', 'N/A')[:40]}")
    
    client.close()

asyncio.run(verify())
