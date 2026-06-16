import asyncio, os, sys
import httpx
from motor.motor_asyncio import AsyncIOMotorClient

API = "http://localhost:8001"
EMAIL = "gutenberg@sigesc.com"
PWD = "@Celta2007"

async def main():
    mongo = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = mongo[os.environ["DB_NAME"]]

    # iterate active students until we find one whose school has another class
    cursor = db.students.find({"status": {"$in": ["active", "Ativo"]}, "class_id": {"$nin": [None, ""]}}, {"_id": 0})
    student = None; other = None
    async for s in cursor:
        school_id = s.get("school_id"); cur_class = s.get("class_id")
        if not school_id: continue
        o = await db.classes.find_one({"school_id": school_id, "id": {"$ne": cur_class}}, {"_id": 0, "id": 1, "name": 1})
        if o:
            student = s; other = o; break
    if not student:
        print("NO suitable student found"); return
    cur_class = student["class_id"]
    print("STUDENT", student["id"], student.get("full_name"), "cur_class", cur_class, "-> new_class", other["id"], other.get("name"))

    async with httpx.AsyncClient(base_url=API, timeout=30) as c:
        r = await c.post("/api/auth/login", json={"email": EMAIL, "password": PWD})
        print("login", r.status_code)
        data = r.json()
        csrf = data.get("csrf_token")
        headers = {"X-CSRF-Token": csrf, "Authorization": f"Bearer {data.get('access_token')}"}
        # relocate
        r2 = await c.put(f"/api/students/{student['id']}", json={"class_id": other["id"]}, headers=headers)
        print("relocate", r2.status_code)
        print(r2.text[:2000])

asyncio.run(main())
