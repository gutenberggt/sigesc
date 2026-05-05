"""
Auditoria: compara CH manual armazenada vs CH calculada pela função central.

Uso:
    cd /app/backend && python scripts/audit_carga_horaria.py [--limit N] [--save]

- `--limit N`   limita a N servidores (default: todos os ativos).
- `--save`      grava resultado em `/app/backend/scripts/audit_ch_report.json`.

Saída (stdout): resumo + lista das maiores divergências (top 20 por valor absoluto).
Sempre imprime cabeçalho mesmo quando não há divergências.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Permite rodar como script standalone do diretório backend/
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(BACKEND_DIR / '.env')

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from utils.carga_horaria_calculator import (  # noqa: E402
    calcular_carga_horaria_servidor,
    calcular_carga_por_lotacao,
)


def _get_db():
    mongo_url = os.environ['MONGO_URL']
    db_name = os.environ['DB_NAME']
    client = AsyncIOMotorClient(mongo_url)
    return client[db_name]


async def audit(limit=None, save=False):
    db = _get_db()
    query = {'status': {'$in': ['ativo', 'afastado', 'licenca', 'ferias']}}
    cursor = db.staff.find(query, {'_id': 0, 'id': 1, 'nome': 1, 'matricula': 1, 'cargo': 1, 'carga_horaria_semanal': 1})
    if limit:
        cursor = cursor.limit(limit)
    staff_list = await cursor.to_list(5000)

    results_servidor = []
    results_lotacao = []

    for s in staff_list:
        sid = s['id']
        ch_manual = s.get('carga_horaria_semanal') or 0
        ch_calc = await calcular_carga_horaria_servidor(db, sid, modo='atual')

        diff = ch_calc - ch_manual
        results_servidor.append({
            'staff_id': sid,
            'nome': s.get('nome'),
            'matricula': s.get('matricula'),
            'cargo': s.get('cargo'),
            'ch_manual_servidor': ch_manual,
            'ch_calc_servidor': ch_calc,
            'diff': diff,
        })

        # Cada lotação ativa
        lotacoes = await db.school_assignments.find(
            {'staff_id': sid, 'status': 'ativo'},
            {'_id': 0, 'id': 1, 'school_id': 1, 'carga_horaria': 1}
        ).to_list(50)
        for lot in lotacoes:
            ch_lot_manual = lot.get('carga_horaria') or 0
            ch_lot_calc = await calcular_carga_por_lotacao(db, sid, lot['school_id'], modo='atual')
            results_lotacao.append({
                'staff_id': sid,
                'nome': s.get('nome'),
                'school_id': lot['school_id'],
                'lotacao_id': lot.get('id'),
                'ch_manual_lotacao': ch_lot_manual,
                'ch_calc_lotacao': ch_lot_calc,
                'diff': ch_lot_calc - ch_lot_manual,
            })

    # Resumo
    div_servidor = [r for r in results_servidor if r['diff'] != 0]
    div_lotacao = [r for r in results_lotacao if r['diff'] != 0]

    summary = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'totals': {
            'staff_avaliados': len(results_servidor),
            'lotacoes_avaliadas': len(results_lotacao),
            'divergencias_servidor': len(div_servidor),
            'divergencias_lotacao': len(div_lotacao),
            'pct_divergencia_servidor': round(100 * len(div_servidor) / max(1, len(results_servidor)), 2),
            'pct_divergencia_lotacao': round(100 * len(div_lotacao) / max(1, len(results_lotacao)), 2),
        },
    }

    print('=' * 70)
    print('AUDITORIA CARGA HORÁRIA — manual (atual) vs calculado (nova função)')
    print('=' * 70)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print()
    print('TOP 20 DIVERGÊNCIAS DE SERVIDOR (por |diff|):')
    print('-' * 70)
    for r in sorted(div_servidor, key=lambda x: -abs(x['diff']))[:20]:
        print(f"  {r['matricula']:>10} | {r['nome'][:40]:<40} | manual={r['ch_manual_servidor']:>3}h | calc={r['ch_calc_servidor']:>3}h | diff={r['diff']:+}h")

    print()
    print('TOP 20 DIVERGÊNCIAS DE LOTAÇÃO (por |diff|):')
    print('-' * 70)
    for r in sorted(div_lotacao, key=lambda x: -abs(x['diff']))[:20]:
        print(f"  staff={r['staff_id'][:8]} | school={r['school_id'][:8]} | manual={r['ch_manual_lotacao']:>3}h | calc={r['ch_calc_lotacao']:>3}h | diff={r['diff']:+}h | {r['nome'][:30]}")

    if save:
        out = {
            'summary': summary,
            'servidor': results_servidor,
            'lotacao': results_lotacao,
        }
        out_path = SCRIPT_DIR / 'audit_ch_report.json'
        out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
        print(f'\nRelatório completo salvo em: {out_path}')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--save', action='store_true')
    args = parser.parse_args()
    asyncio.run(audit(limit=args.limit, save=args.save))
