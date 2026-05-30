import asyncio, os
from motor.motor_asyncio import AsyncIOMotorClient


async def main():
    c = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = c[os.environ['DB_NAME']]
    print('DB_NAME=', os.environ['DB_NAME'])
    nsch = await db.schools.count_documents({})
    print('total schools:', nsch)
    # schools with most active students
    pipe = [
        {'$match': {'status': 'active'}},
        {'$group': {'_id': '$school_id', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 8},
    ]
    async for d in db.students.aggregate(pipe):
        sch = await db.schools.find_one({'id': d['_id']}, {'_id': 0, 'name': 1})
        print('  school', d['_id'], (sch or {}).get('name'), 'active=', d['count'])

    # Distinct grade_level values across classes
    print('\n--- distinct classes.grade_level ---')
    gl = await db.classes.distinct('grade_level')
    print(sorted([repr(x) for x in gl]))
    print('\n--- distinct students.student_series ---')
    ss = await db.students.distinct('student_series')
    print(sorted([repr(x) for x in ss])[:60])


asyncio.run(main())
