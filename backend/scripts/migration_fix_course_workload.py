#!/usr/bin/env python3
"""
Script de Migração: Correção de Carga Horária por Série

Este script popula o campo `carga_horaria_por_serie` para componentes curriculares
que têm diferentes cargas horárias dependendo do nível de ensino.

O campo `carga_horaria_por_serie` é um Dict[str, int] onde:
- A chave é o nome da série (ex: "1º Ano", "6º Ano")
- O valor é a carga horária anual em horas

Execução:
    python scripts/migration_fix_course_workload.py [--dry-run] [--verbose]

Flags:
    --dry-run  : Mostra o que seria alterado sem fazer mudanças
    --verbose  : Exibe informações detalhadas
"""

import asyncio
import os
import sys
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Carregar variáveis de ambiente
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / '.env')

# Conexão MongoDB
mongo_url = os.environ['MONGO_URL']
db_name = os.environ.get('DB_NAME', 'sigesc_db')

# Mapeamento de séries por nível de ensino
SERIES_POR_NIVEL = {
    'educacao_infantil': ['Berçário I', 'Berçário II', 'Maternal I', 'Maternal II', 'Pré I', 'Pré II'],
    'fundamental_anos_iniciais': ['1º Ano', '2º Ano', '3º Ano', '4º Ano', '5º Ano'],
    'fundamental_anos_finais': ['6º Ano', '7º Ano', '8º Ano', '9º Ano']
}


def get_series_for_nivel(nivel_ensino: str) -> list:
    """Retorna a lista de séries para um nível de ensino."""
    return SERIES_POR_NIVEL.get(nivel_ensino, [])


async def analyze_courses(db, verbose: bool = False):
    """Analisa os cursos e identifica os que precisam de migração."""
    courses = await db.courses.find({}, {"_id": 0}).to_list(None)
    
    # Agrupar cursos por nome para identificar duplicados por nível
    by_name = {}
    for c in courses:
        name = c.get('name', '').strip()
        if name not in by_name:
            by_name[name] = []
        by_name[name].append(c)
    
    migrations = []
    
    for name, entries in by_name.items():
        if len(entries) > 1:
            # Componente com múltiplas entradas (diferentes níveis)
            # Criar mapeamento de carga horária por série
            carga_por_serie = {}
            
            for entry in entries:
                nivel = entry.get('nivel_ensino')
                workload = entry.get('workload', 0)
                series = get_series_for_nivel(nivel)
                
                for serie in series:
                    carga_por_serie[serie] = workload
            
            if verbose:
                print(f"\n{name}:")
                print(f"  Entradas encontradas: {len(entries)}")
                print(f"  Mapeamento gerado: {carga_por_serie}")
            
            # Adicionar migração para cada entrada deste componente
            for entry in entries:
                if not entry.get('carga_horaria_por_serie'):
                    migrations.append({
                        'id': entry.get('id'),
                        'name': name,
                        'nivel_ensino': entry.get('nivel_ensino'),
                        'carga_horaria_por_serie': carga_por_serie
                    })
    
    return migrations


async def run_migration(dry_run: bool = True, verbose: bool = False):
    """Executa a migração de carga horária."""
    print("=" * 60)
    print("SIGESC - Migração de Carga Horária por Série")
    print("=" * 60)
    
    if dry_run:
        print("\n⚠️  MODO DRY-RUN: Nenhuma alteração será feita\n")
    
    # Conectar ao MongoDB
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    print(f"Conectado ao banco: {db_name}")
    
    # Analisar cursos
    print("\nAnalisando componentes curriculares...")
    migrations = await analyze_courses(db, verbose)
    
    if not migrations:
        print("\n✅ Nenhum componente precisa de migração!")
        print("   Todos os componentes já possuem carga_horaria_por_serie ou são únicos.")
        return
    
    print(f"\n📋 {len(migrations)} componentes identificados para migração:\n")
    
    # Mostrar resumo das migrações
    for i, m in enumerate(migrations, 1):
        print(f"  {i}. {m['name']} ({m['nivel_ensino']})")
        print(f"     ID: {m['id']}")
        if verbose:
            print(f"     carga_horaria_por_serie: {m['carga_horaria_por_serie']}")
    
    if dry_run:
        print("\n" + "-" * 60)
        print("Para aplicar as alterações, execute sem --dry-run:")
        print("  python scripts/migration_fix_course_workload.py")
        print("-" * 60)
        return
    
    # Executar migração
    print("\n🔄 Aplicando migrações...")
    
    success = 0
    errors = 0
    
    for m in migrations:
        try:
            result = await db.courses.update_one(
                {"id": m['id']},
                {"$set": {"carga_horaria_por_serie": m['carga_horaria_por_serie']}}
            )
            
            if result.modified_count > 0:
                success += 1
                if verbose:
                    print(f"  ✅ {m['name']} ({m['nivel_ensino']})")
            else:
                print(f"  ⚠️  {m['name']}: Nenhuma alteração (já atualizado?)")
        except Exception as e:
            errors += 1
            print(f"  ❌ {m['name']}: {str(e)}")
    
    print("\n" + "=" * 60)
    print(f"✅ Migração concluída!")
    print(f"   - Componentes atualizados: {success}")
    print(f"   - Erros: {errors}")
    print("=" * 60)
    
    # Fechar conexão
    client.close()


def main():
    """Função principal."""
    dry_run = '--dry-run' in sys.argv
    verbose = '--verbose' in sys.argv or '-v' in sys.argv
    
    asyncio.run(run_migration(dry_run=dry_run, verbose=verbose))


if __name__ == '__main__':
    main()
