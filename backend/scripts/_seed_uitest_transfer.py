import os, uuid, requests
from datetime import datetime, timezone
from pathlib import Path
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

dest = None; year = None
for cal in db.calendario_letivo.find({}, {"_id": 0, "school_id": 1, "ano_letivo": 1}):
    sid = cal.get("school_id")
    if not sid:
        continue
    sch = db.schools.find_one({"id": sid, "status": "active"}, {"_id": 0, "id": 1, "mantenedora_id": 1, "name": 1})
    if sch and sch.get("mantenedora_id"):
        dest = sch; year = cal["ano_letivo"]; break
assert dest is not None or True
if not dest:
    cal = db.calendario_letivo.find_one({"school_id": None}, {"_id": 0, "ano_letivo": 1})
    if cal:
        sch = db.schools.find_one({"status": "active", "mantenedora_id": {"$ne": None}},
                                  {"_id": 0, "id": 1, "mantenedora_id": 1, "name": 1})
        if sch:
            dest = sch; year = cal["ano_letivo"]
assert dest, "no dest with calendar"

sfx = uuid.uuid4().hex[:6]
origin_id = f"uitest-origin-{sfx}"
db.schools.insert_one({"id": origin_id, "name": f"ESCOLA UITEST ORIGEM {sfx}",
                       "mantenedora_id": dest["mantenedora_id"], "status": "active",
                       "niveis_ensino_oferecidos": [], "created_at": datetime.now(timezone.utc).isoformat()})

s = requests.Session()
d = s.post(f"{BASE}/api/auth/login", json={"email": "gutenberg@sigesc.com", "password": "@Celta2007"}, timeout=30).json()
s.headers.update({"Authorization": f"Bearer {d.get('access_token') or d.get('token')}",
                  "X-CSRF-Token": d.get("csrf_token") or "", "Content-Type": "application/json"})
cid = s.post(f"{BASE}/api/classes", json={"name": f"UITEST {sfx}", "school_id": origin_id,
             "grade_level": "Pré I", "education_level": "educacao_infantil",
             "academic_year": year, "shift": "morning"}, timeout=20).json()["id"]
for n in range(2):
    s.post(f"{BASE}/api/students", json={"full_name": f"UITEST Aluno {sfx}-{n}", "birth_date": "2019-05-01",
           "sex": "feminino", "school_id": origin_id, "class_id": cid, "status": "active",
           "no_documents_justification": "test"}, timeout=20)
print("SEED_ORIGIN_NAME=ESCOLA UITEST ORIGEM " + sfx)
print("SEED_DEST_NAME=" + dest["name"])
print("origin_id=" + origin_id + " class_id=" + cid)
