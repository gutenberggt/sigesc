import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')

async def generate_enrollment_numbers():
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ.get('DB_NAME', 'sigesc_db')]
    
    # Buscar alunos sem número de matrícula
    query = {"$or": [
        {"enrollment_number": None}, 
        {"enrollment_number": ""}, 
        {"enrollment_number": {"$exists": False}}
    ]}
    
    students = await db.students.find(query, {"_id": 0, "id": 1}).to_list(10000)
    total = len(students)
    print(f"Encontrados {total} alunos sem número de matrícula")
    
    if total == 0:
        print("Nenhum aluno para atualizar!")
        return
    
    # Encontrar o maior número de matrícula existente para continuar a sequência
    existing = await db.students.find(
        {"enrollment_number": {"$regex": "^2025"}},
        {"_id": 0, "enrollment_number": 1}
    ).to_list(10000)
    
    max_seq = 0
    for s in existing:
        try:
            num = int(s.get('enrollment_number', '0')[4:])  # Pega os dígitos após "2025"
            if num > max_seq:
                max_seq = num
        except:
            pass
    
    print(f"Maior sequencial existente: {max_seq}")
    
    # Gerar números de matrícula
    updated = 0
    errors = 0
    
    for i, student in enumerate(students):
        seq = max_seq + i + 1
        enrollment_number = f"2025{seq:05d}"  # Formato: 2025XXXXX
        
        try:
            result = await db.students.update_one(
                {"id": student['id']},
                {"$set": {"enrollment_number": enrollment_number}}
            )
            if result.modified_count > 0:
                updated += 1
        except Exception as e:
            errors += 1
            print(f"Erro ao atualizar aluno {student['id']}: {e}")
        
        # Mostrar progresso a cada 500
        if (i + 1) % 500 == 0:
            print(f"Progresso: {i + 1}/{total} ({((i+1)/total*100):.1f}%)")
    
    print(f"\n✅ Concluído!")
    print(f"   - Alunos atualizados: {updated}")
    print(f"   - Erros: {errors}")
    print(f"   - Faixa de matrículas: 2025{(max_seq+1):05d} até 2025{(max_seq+total):05d}")
    
    client.close()

asyncio.run(generate_enrollment_numbers())
