"""
Diagnóstico do Desempenho de UM professor — reproduz EXATAMENTE o cálculo do
endpoint /api/analytics/teachers/performance e imprime cada número intermediário,
para verificar se "Diários 100% / Diários (60%) 100%" está correto.

COMO RODAR (no droplet sigesc-prod-01):
    cd /app/backend        # ou o caminho do backend no servidor
    python scripts/diagnostico_professor.py "Ivanilde Freire Batista da Silva" 2026
"""
import asyncio, os, sys
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
load_dotenv()
from motor.motor_asyncio import AsyncIOMotorClient


def year_filter(year):
    return {'$in': [str(year), year]}


async def main():
    nome = sys.argv[1] if len(sys.argv) > 1 else "Ivanilde"
    ano = int(sys.argv[2]) if len(sys.argv) > 2 else 2026
    c = AsyncIOMotorClient(os.environ['MONGO_URL']); db = c[os.environ['DB_NAME']]

    # 1) Achar o staff_id do professor (por nome em staff e users)
    ids = set()
    async for s in db.staff.find({'$or': [{'nome': {'$regex': nome, '$options': 'i'}},
                                          {'full_name': {'$regex': nome, '$options': 'i'}}]},
                                 {'_id': 0, 'id': 1, 'nome': 1, 'full_name': 1}):
        ids.add(s['id']); print("staff:", s['id'], s.get('nome') or s.get('full_name'))
    async for u in db.users.find({'full_name': {'$regex': nome, '$options': 'i'}},
                                 {'_id': 0, 'id': 1, 'full_name': 1}):
        ids.add(u['id']); print("user :", u['id'], u.get('full_name'))
    if not ids:
        print("Professor não encontrado."); return

    # 2) Alocações (turma x componente)
    allocs = await db.teacher_assignments.find(
        {'staff_id': {'$in': list(ids)}}, {'_id': 0, 'class_id': 1, 'course_id': 1, 'staff_id': 1}
    ).to_list(5000)
    pairs = [(a.get('class_id'), a.get('course_id')) for a in allocs]
    class_ids = sorted({cid for cid, _ in pairs if cid})
    print(f"\nAlocações: {len(pairs)} par(es) turma×componente | turmas distintas: {len(class_ids)}")
    for cid, coid in pairs:
        cls = await db.classes.find_one({'id': cid}, {'_id': 0, 'name': 1, 'grade_level': 1, 'education_level': 1})
        crs = await db.courses.find_one({'id': coid}, {'_id': 0, 'name': 1})
        print(f"   turma={cls.get('name') if cls else cid} ({cls.get('grade_level') if cls else '?'}) | componente={crs.get('name') if crs else coid}")

    # 3) Período (início 1º bimestre -> hoje)
    cal = await db.calendario_letivo.find_one({'ano_letivo': ano}, {'_id': 0})
    if not cal:
        cal = await db.calendario_letivo.find_one({'ano_letivo': str(ano)}, {'_id': 0})
    period_end = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    total_dias = 0; dias_periodo = 0
    if cal:
        blocked = set(cal.get('dias_nao_letivos', []) or [])
        sab = set(cal.get('sabados_letivos', []) or [])
        for n in (1, 2, 3, 4):
            ini = cal.get(f'bimestre_{n}_inicio'); fim = cal.get(f'bimestre_{n}_fim')
            if not ini or not fim:
                continue
            d = datetime.strptime(str(ini)[:10], '%Y-%m-%d')
            fimd = datetime.strptime(str(fim)[:10], '%Y-%m-%d')
            while d <= fimd:
                ds = d.strftime('%Y-%m-%d'); dow = d.weekday()
                if dow != 6 and ds not in blocked and (dow != 5 or ds in sab):
                    total_dias += 1
                    if ds <= period_end:
                        dias_periodo += 1
                d += timedelta(days=1)
    print(f"\nCalendário {ano}: {'OK' if cal else 'NÃO ENCONTRADO'} | dias letivos ANO={total_dias} | dias letivos ATÉ HOJE({period_end})={dias_periodo}")
    dias_ref = dias_periodo if dias_periodo > 0 else total_dias

    # 4) FREQUÊNCIA — como o endpoint calcula (agrupa por TURMA, conta TODOS os componentes)
    cutoff = period_end
    total_docs = 0; on_time = 0; distinct_classday = set()
    async for att in db.attendance.find(
        {'class_id': {'$in': class_ids}, 'date': {'$regex': f'^{ano}', '$lte': cutoff}, 'created_at': {'$ne': None}},
        {'_id': 0, 'class_id': 1, 'course_id': 1, 'date': 1, 'created_at': 1, 'version': 1, 'updated_at': 1}
    ):
        try:
            dd = (datetime.fromisoformat(str(att['created_at']).replace('Z', '+00:00')).date()
                  - datetime.strptime(str(att['date'])[:10], '%Y-%m-%d').date()).days
        except Exception:
            continue
        total_docs += 1
        distinct_classday.add((att['class_id'], str(att['date'])[:10]))
        modified = (att.get('version') or 1) > 1 or att.get('updated_at') is not None
        if dd <= 3 and not modified:
            on_time += 1
    freq_expected = len(class_ids) * dias_ref
    freq_cov = round(min(total_docs / freq_expected * 100, 100), 1) if freq_expected else 0
    sla_freq = round(min(on_time / freq_expected * 100, 100), 1) if freq_expected else 0
    print(f"\nFREQUÊNCIA (endpoint agrupa por TURMA, soma todos os componentes):")
    print(f"   docs lançados (período) = {total_docs} | no prazo(<=3d, não alterados) = {on_time}")
    print(f"   dias-turma DISTINTOS lançados = {len(distinct_classday)}  (se < docs, há +1 doc por dia = múltiplos componentes/turnos)")
    print(f"   previstos = turmas({len(class_ids)}) x dias_periodo({dias_ref}) = {freq_expected}")
    print(f"   -> Cobertura(Diários) = {freq_cov}%   SLA(Diários 60%) = {sla_freq}%")
    if total_docs > freq_expected:
        print("   ⚠️ ATENÇÃO: docs > previstos → numerador maior que denominador → CAP em 100% (possível 100% inflado).")

    # 5) CONTEÚDO
    lo = await db.learning_objects.count_documents({'class_id': {'$in': class_ids}, 'academic_year': year_filter(ano)})
    exp_lo = len(class_ids) * dias_ref
    sla_cont = round(min(lo / exp_lo * 100, 100), 1) if exp_lo else 0
    print(f"\nCONTEÚDO: registrados={lo} | previstos={exp_lo} -> {sla_cont}%"
          + ("  ⚠️ registrados > previstos → CAP 100%" if lo > exp_lo else ""))

    # 6) NOTAS (7 dias após fim do bimestre, só bimestres encerrados)
    deadlines = {}
    if cal:
        for n in (1, 2, 3, 4):
            fim = cal.get(f'bimestre_{n}_fim')
            if fim and str(fim)[:10] <= period_end:
                deadlines[n] = (datetime.strptime(str(fim)[:10], '%Y-%m-%d') + timedelta(days=7)).strftime('%Y-%m-%d')
    print(f"\nNOTAS: bimestres encerrados no período = {list(deadlines.keys())} | prazos(fim+7d) = {deadlines}")
    n_exp = n_lan = n_ok = 0
    seen = set()
    for cid, coid in pairs:
        if not cid or not coid or (cid, coid) in seen:
            continue
        seen.add((cid, coid))
        agg = await db.grades.aggregate([
            {'$match': {'class_id': cid, 'course_id': coid, 'academic_year': year_filter(ano)}},
            {'$group': {'_id': None,
                        'b1': {'$max': {'$cond': [{'$ne': ['$b1', None]}, 1, 0]}},
                        'b2': {'$max': {'$cond': [{'$ne': ['$b2', None]}, 1, 0]}},
                        'b3': {'$max': {'$cond': [{'$ne': ['$b3', None]}, 1, 0]}},
                        'b4': {'$max': {'$cond': [{'$ne': ['$b4', None]}, 1, 0]}},
                        'first_at': {'$min': '$created_at'}}}
        ]).to_list(1)
        has = agg[0] if agg else {}
        fa = str(has.get('first_at') or '')[:10]
        for n, dl in deadlines.items():
            n_exp += 1
            if has.get(f'b{n}'):
                n_lan += 1
                if fa and fa <= dl:
                    n_ok += 1
    notas_cov = round(n_lan / n_exp * 100, 1) if n_exp else 100.0
    sla_notas = round(n_ok / n_exp * 100, 1) if n_exp else 100.0
    print(f"   previstas={n_exp} lançadas={n_lan} no_prazo={n_ok} | 1º created_at usado como referência (aprox.)")
    print(f"   -> Cobertura(Diários) = {notas_cov}%   SLA(Diários 60%) = {sla_notas}%")

    # 7) RESULTADO FINAL
    diario_60 = round(min((sla_freq * 4 + sla_cont * 3 + sla_notas * 3) / 10, 100), 1)
    diario = round(min((freq_cov * 4 + sla_cont * 3 + notas_cov * 3) / 10, 100), 1)
    print(f"\n=== RESULTADO ===")
    print(f"   Diários        = {diario}%")
    print(f"   Diários (60%)  = {diario_60}%")
    print("   (Pesos: Frequência 4, Conteúdo 3, Notas 3)")

asyncio.run(main())
