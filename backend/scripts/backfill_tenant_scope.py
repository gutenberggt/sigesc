"""
Backfill de mantenedora_id — Fase 2 Multi-tenancy.

Estampa mantenedora_id em coleções que ainda não têm, derivando via school_id → schools.mantenedora_id,
com fallbacks por class_id / student_id / staff_id. Se houver apenas 1 mantenedora cadastrada, usa
essa como fallback global para registros sem parent identificável.

Uso:
    python3 -m scripts.backfill_tenant_scope          # dry-run
    python3 -m scripts.backfill_tenant_scope --apply  # aplica as escritas
"""
import os, sys, asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
load_dotenv('/app/backend/.env')

APPLY = '--apply' in sys.argv

# Coleções a processar e como derivar tenant
# regras: ordem de preferência de lookup
COLLECTIONS = [
    # (coleção, [("campo", "coleção_lookup")])
    ('aee_estudantes',     [('school_id', 'schools'), ('class_id', 'classes'), ('student_id', 'students')]),
    ('attendance',         [('class_id', 'classes')]),
    ('audit_logs',         [('school_id', 'schools')]),
    ('class_schedules',    [('school_id', 'schools'), ('class_id', 'classes')]),
    ('hr_audit_logs',      [('school_id', 'schools'), ('payroll_id', 'school_payrolls')]),
    ('medical_certificates',[('student_id', 'students'), ('school_id', 'schools')]),
    ('messages',           [('school_id', 'schools')]),
    ('payroll_competencies',[]),  # global → usa fallback
    ('promotion_book_counters',[]),
    ('promotion_books',    [('class_id', 'classes')]),
    ('school_payrolls',    [('school_id', 'schools'), ('competency_id', 'payroll_competencies')]),
    ('student_history',    [('school_id', 'schools'), ('class_id', 'classes'), ('student_id', 'students')]),
    ('vaccine_status',     [('student_id', 'students')]),
    ('user_profiles',      [('user_id', 'users')]),
    ('connections',        [('user_id', 'users')]),
]

async def main():
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ['DB_NAME']]
    
    # Descobre mantenedora fallback (se houver apenas 1)
    mantenedoras = await db.mantenedoras.find({}, {'_id': 0, 'id': 1}).to_list(10)
    fallback_mid = mantenedoras[0]['id'] if len(mantenedoras) == 1 else None
    print(f"Mantenedoras existentes: {len(mantenedoras)} | fallback: {fallback_mid}\n")
    
    # Pré-carrega mapas de lookup (tudo pequeno)
    print("Pré-carregando mapas de lookup...")
    schools_map = {s['id']: s.get('mantenedora_id') for s in await db.schools.find({}, {'_id': 0, 'id': 1, 'mantenedora_id': 1}).to_list(10000)}
    classes_map = {c['id']: c.get('mantenedora_id') for c in await db.classes.find({}, {'_id': 0, 'id': 1, 'mantenedora_id': 1}).to_list(10000)}
    students_map = {s['id']: s.get('mantenedora_id') for s in await db.students.find({}, {'_id': 0, 'id': 1, 'mantenedora_id': 1}).to_list(100000)}
    users_map = {u['id']: u.get('mantenedora_id') for u in await db.users.find({}, {'_id': 0, 'id': 1, 'mantenedora_id': 1}).to_list(10000)}
    sp_map = {p['id']: p.get('mantenedora_id') for p in await db.school_payrolls.find({}, {'_id': 0, 'id': 1, 'mantenedora_id': 1}).to_list(10000)}
    pc_map = {c['id']: c.get('mantenedora_id') for c in await db.payroll_competencies.find({}, {'_id': 0, 'id': 1, 'mantenedora_id': 1}).to_list(10000)}
    lookup = {
        'schools': schools_map, 'classes': classes_map, 'students': students_map,
        'users': users_map, 'school_payrolls': sp_map, 'payroll_competencies': pc_map,
    }
    
    total_updates = 0
    total_fallback = 0
    total_orphan = 0
    
    for coll_name, rules in COLLECTIONS:
        count_missing = await db[coll_name].count_documents({'$or': [{'mantenedora_id': {'$exists': False}}, {'mantenedora_id': None}]})
        if count_missing == 0:
            continue
        print(f"\n→ {coll_name}: {count_missing} docs sem tenant")
        
        updates_by_mid = {}  # mid → [doc_ids]
        orphans = []
        async for doc in db[coll_name].find({'$or': [{'mantenedora_id': {'$exists': False}}, {'mantenedora_id': None}]}, {'_id': 1, 'school_id': 1, 'class_id': 1, 'student_id': 1, 'user_id': 1, 'competency_id': 1, 'payroll_id': 1}):
            mid = None
            for field, lookup_coll in rules:
                val = doc.get(field)
                if val and val in lookup.get(lookup_coll, {}):
                    mid = lookup[lookup_coll][val]
                    if mid:
                        break
            if not mid:
                mid = fallback_mid
                if mid:
                    total_fallback += 1
            if mid:
                updates_by_mid.setdefault(mid, []).append(doc['_id'])
            else:
                orphans.append(doc['_id'])
        
        for mid, ids in updates_by_mid.items():
            print(f"   tenant={mid[:8]}...  ids={len(ids)}")
            if APPLY:
                await db[coll_name].update_many({'_id': {'$in': ids}}, {'$set': {'mantenedora_id': mid}})
            total_updates += len(ids)
        
        if orphans:
            print(f"   ORFÃOS (sem fallback): {len(orphans)} — serão ignorados")
            total_orphan += len(orphans)
    
    print(f"\n{'APLICADO' if APPLY else 'DRY-RUN'}: {total_updates} updates  |  fallback usado: {total_fallback}  |  órfãos: {total_orphan}")

asyncio.run(main())
