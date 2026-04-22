"""Inspect collections to plan Phase 2 tenant scoping backfill."""
import os, asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
load_dotenv('/app/backend/.env')

async def main():
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ['DB_NAME']]
    colls = await db.list_collection_names()
    print(f'Total collections: {len(colls)}\n')
    for c in sorted(colls):
        total = await db[c].count_documents({})
        with_tenant = await db[c].count_documents({'mantenedora_id': {'$exists': True, '$ne': None}})
        sample = await db[c].find_one({}, {'_id': 0})
        has_school = isinstance(sample, dict) and 'school_id' in sample
        has_class = isinstance(sample, dict) and 'class_id' in sample
        has_school_ids = isinstance(sample, dict) and 'school_ids' in sample
        has_student = isinstance(sample, dict) and 'student_id' in sample
        has_staff = isinstance(sample, dict) and 'staff_id' in sample
        if total > 0:
            print(f'{c:40s}  total={total:5d}  tenant={with_tenant:5d}  school_id={has_school} class_id={has_class} school_ids={has_school_ids} student_id={has_student} staff_id={has_staff}')

asyncio.run(main())
