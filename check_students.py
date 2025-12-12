import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')

async def check():
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ.get('DB_NAME', 'sigesc_db')]
    
    # Contar alunos
    total = await db.students.count_documents({})
    print(f"Total de alunos: {total}")
    
    # Verificar alguns registros
    students = await db.students.find({}, {"_id": 0, "id": 1, "full_name": 1, "enrollment_number": 1, "cpf": 1, "school_id": 1}).limit(5).to_list(5)
    print("\nExemplos de alunos:")
    for s in students:
        print(f"  - ID: {s.get('id', 'N/A')[:8]}... | Matrícula: {s.get('enrollment_number', 'VAZIO')} | Nome: {s.get('full_name', 'N/A')[:30]}")
    
    # Contar alunos SEM enrollment_number
    sem_matricula = await db.students.count_documents({"$or": [{"enrollment_number": None}, {"enrollment_number": ""}, {"enrollment_number": {"$exists": False}}]})
    print(f"\nAlunos SEM número de matrícula: {sem_matricula}")
    
    # Verificar escolas
    schools = await db.schools.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(100)
    print(f"\nEscolas ({len(schools)}):")
    for s in schools:
        count = await db.students.count_documents({"school_id": s['id']})
        print(f"  - {s['name']}: {count} alunos")
    
    client.close()

asyncio.run(check())
