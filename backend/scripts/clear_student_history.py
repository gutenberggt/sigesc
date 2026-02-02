#!/usr/bin/env python3
"""
Script para apagar todos os históricos de alunos (student_history)
Execute este script diretamente no servidor de produção.

USO:
  python3 clear_student_history.py

ATENÇÃO: Esta ação é IRREVERSÍVEL! Faça backup antes de executar.
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone
import os

# Configuração do MongoDB - ajuste conforme necessário
# Em produção, geralmente o MONGO_URL está no .env
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'sigesc_db')


async def clear_student_history():
    """Apaga todos os registros da coleção student_history"""
    
    print("=" * 60)
    print("SCRIPT: Limpeza de Histórico de Alunos")
    print("=" * 60)
    print(f"Conectando ao MongoDB: {MONGO_URL[:30]}...")
    print(f"Banco de dados: {DB_NAME}")
    print()
    
    # Conecta ao MongoDB
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    try:
        # Conta registros antes de apagar
        count_before = await db.student_history.count_documents({})
        print(f"Total de registros encontrados: {count_before}")
        
        if count_before == 0:
            print("Nenhum registro para apagar.")
            return
        
        # Mostra alguns exemplos do que será apagado
        print("\nExemplos de registros que serão apagados:")
        print("-" * 40)
        
        samples = await db.student_history.find({}, {"_id": 0}).limit(5).to_list(5)
        for i, sample in enumerate(samples, 1):
            print(f"{i}. Aluno: {sample.get('student_id', 'N/A')[:8]}...")
            print(f"   Ação: {sample.get('action_type', 'N/A')}")
            print(f"   Data: {sample.get('action_date', 'N/A')}")
            print(f"   Obs: {sample.get('observations', 'N/A')[:50]}..." if sample.get('observations') else "   Obs: N/A")
            print()
        
        # Confirmação
        print("-" * 40)
        print(f"\n⚠️  ATENÇÃO: Você está prestes a APAGAR {count_before} registros!")
        print("   Esta ação é IRREVERSÍVEL!\n")
        
        confirmacao = input("Digite 'SIM' para confirmar a exclusão: ")
        
        if confirmacao.strip().upper() != 'SIM':
            print("\n❌ Operação cancelada pelo usuário.")
            return
        
        # Executa a exclusão
        print("\nApagando registros...")
        result = await db.student_history.delete_many({})
        
        print(f"\n✅ {result.deleted_count} registros apagados com sucesso!")
        
        # Verifica se realmente foi apagado
        count_after = await db.student_history.count_documents({})
        print(f"Registros restantes: {count_after}")
        
        # Log da operação
        log_entry = {
            "action": "clear_student_history",
            "deleted_count": result.deleted_count,
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "description": "Limpeza manual de histórico de alunos via script"
        }
        await db.admin_logs.insert_one(log_entry)
        print("\nLog da operação registrado em admin_logs.")
        
    except Exception as e:
        print(f"\n❌ ERRO: {str(e)}")
        raise
    finally:
        client.close()
        print("\nConexão fechada.")


async def preview_only():
    """Apenas mostra o que seria apagado, sem apagar"""
    
    print("=" * 60)
    print("MODO PREVIEW - Apenas visualização (nada será apagado)")
    print("=" * 60)
    
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    try:
        count = await db.student_history.count_documents({})
        print(f"\nTotal de registros na coleção student_history: {count}")
        
        # Agrupa por tipo de ação
        pipeline = [
            {"$group": {"_id": "$action_type", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        
        action_types = await db.student_history.aggregate(pipeline).to_list(100)
        
        if action_types:
            print("\nRegistros por tipo de ação:")
            for at in action_types:
                print(f"  - {at['_id'] or 'N/A'}: {at['count']} registros")
        
        # Agrupa por escola
        pipeline_schools = [
            {"$group": {"_id": "$school_id", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        
        schools = await db.student_history.aggregate(pipeline_schools).to_list(10)
        
        if schools:
            print("\nTop 10 escolas com mais registros:")
            for s in schools:
                school = await db.schools.find_one({"id": s['_id']}, {"name": 1})
                school_name = school.get('name', 'N/A') if school else 'N/A'
                print(f"  - {school_name}: {s['count']} registros")
        
    finally:
        client.close()


if __name__ == "__main__":
    import sys
    
    print("\n" + "=" * 60)
    print("  LIMPEZA DE HISTÓRICO DE ALUNOS - SIGESC")
    print("=" * 60)
    print("\nOpções:")
    print("  1. Preview (apenas visualizar)")
    print("  2. Executar limpeza")
    print("  0. Sair")
    print()
    
    opcao = input("Escolha uma opção: ").strip()
    
    if opcao == "1":
        asyncio.run(preview_only())
    elif opcao == "2":
        asyncio.run(clear_student_history())
    else:
        print("Saindo...")
