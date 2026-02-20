"""
Script de Migração: Converter todos os campos de texto para CAIXA ALTA
Este script converte nomes e outros campos de texto para maiúsculas no banco de dados.
"""

from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

# Campos a serem convertidos por coleção
COLLECTIONS_CONFIG = {
    'students': [
        'full_name', 'father_name', 'mother_name', 'guardian_name',
        'address', 'neighborhood', 'city', 'state', 'birthplace_city', 'birthplace_state',
        'father_workplace', 'mother_workplace', 'guardian_workplace',
        'health_observations', 'special_needs_description', 'allergy_description',
        'previous_school', 'transfer_reason'
    ],
    'staff': [
        'full_name', 'address', 'neighborhood', 'city', 'state',
        'birthplace_city', 'birthplace_state', 'marital_status_spouse_name',
        'education_institution', 'education_course', 'specialization_area',
        'bank_name', 'bank_branch', 'pix_key'
    ],
    'schools': [
        'name', 'address', 'neighborhood', 'city', 'state',
        'principal_name', 'secretary_name', 'coordinator_name',
        'school_characteristic', 'authorization_recognition'
    ],
    'classes': [
        'name', 'room', 'shift', 'level', 'grade'
    ],
    'courses': [
        'name', 'code', 'description'
    ],
    'users': [
        'full_name'
    ],
    'enrollments': [
        'student_name', 'class_name', 'school_name'
    ]
}

# Campos que NÃO devem ser convertidos (emails, etc.)
EXCLUDED_FIELDS = ['email', 'father_email', 'mother_email', 'guardian_email', 'cpf', 'rg']


async def convert_to_uppercase(db, collection_name: str, fields: list):
    """Converte campos específicos para maiúsculas em uma coleção"""
    
    collection = db[collection_name]
    
    # Conta documentos totais
    total = await collection.count_documents({})
    print(f"\n📂 Coleção: {collection_name} ({total} documentos)")
    
    if total == 0:
        print("   ⏭️  Vazia, pulando...")
        return 0
    
    updated_count = 0
    
    # Busca todos os documentos
    cursor = collection.find({}, {"_id": 1} | {f: 1 for f in fields})
    
    async for doc in cursor:
        update_data = {}
        
        for field in fields:
            if field in doc and doc[field] and isinstance(doc[field], str):
                upper_value = doc[field].upper()
                if doc[field] != upper_value:
                    update_data[field] = upper_value
        
        if update_data:
            await collection.update_one(
                {"_id": doc["_id"]},
                {"$set": update_data}
            )
            updated_count += 1
    
    print(f"   ✅ {updated_count} documentos atualizados")
    return updated_count


async def run_migration():
    """Executa a migração completa"""
    
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'sigesc')
    
    print("=" * 60)
    print("🔄 MIGRAÇÃO: Conversão para CAIXA ALTA")
    print("=" * 60)
    print(f"Banco de dados: {db_name}")
    
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    total_updated = 0
    
    for collection_name, fields in COLLECTIONS_CONFIG.items():
        # Remove campos excluídos
        fields_to_update = [f for f in fields if f not in EXCLUDED_FIELDS]
        
        try:
            count = await convert_to_uppercase(db, collection_name, fields_to_update)
            total_updated += count
        except Exception as e:
            print(f"   ❌ Erro: {e}")
    
    print("\n" + "=" * 60)
    print(f"✅ MIGRAÇÃO CONCLUÍDA!")
    print(f"   Total de documentos atualizados: {total_updated}")
    print("=" * 60)
    
    client.close()


if __name__ == "__main__":
    asyncio.run(run_migration())
