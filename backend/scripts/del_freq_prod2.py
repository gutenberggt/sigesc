import asyncio, os, re, sys, unicodedata
from motor.motor_asyncio import AsyncIOMotorClient
try:
    from dotenv import load_dotenv; load_dotenv()
except Exception:
    pass

ALUNA = "Maria Helena Cardoso da Costa Rodrigues"
TURMA = "2º Ano D"
ESCOLA = "E M E I E F Paroquial Curupira"
DATA_INI = "02-13"   # 13/02 (MM-DD)
DATA_FIM = "03-26"   # 26/03 (MM-DD)
APPLY = "--apply" in sys.argv

def _dbname():
    n = os.environ.get("DB_NAME")
    if n:
        return n
    url = os.environ.get("MONGO_URL", "")
    m = re.search(r"/([^/?]+)(\?|$)", url.split("://", 1)[-1])
    return (m.group(1) if m and m.group(1) else "sigesc")

def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("\u00ba", "").replace("\u00b0", "").replace("\u00aa", "")
    return re.sub(r"\s+", " ", s).strip()

async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[_dbname()]
    print("[DB]", _dbname())

    schools = await db.schools.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(100000)
    alvo = _norm(ESCOLA)
    esc = [s for s in schools if alvo in _norm(s.get("name"))]
    if not esc:
        esc = [s for s in schools if "paroquial curupira" in _norm(s.get("name"))]
    print("\n[ESCOLA] candidatos: %d" % len(esc))
    for s in esc:
        print("   - %s  (id=%s)" % (s["name"], s["id"]))
    if len(esc) != 1:
        print("!! ABORTADO: escola nao unica.")
        return
    school = esc[0]

    turmas = await db.classes.find({"school_id": school["id"]},
        {"_id": 0, "id": 1, "name": 1, "grade_level": 1, "academic_year": 1}).to_list(100000)
    at = _norm(TURMA)
    trm = [t for t in turmas if _norm(t.get("name")) == at] or [t for t in turmas if at in _norm(t.get("name"))]
    print("\n[TURMA] candidatos: %d" % len(trm))
    for t in trm:
        print("   - %s (serie=%s, ano=%s, id=%s)" % (t["name"], t.get("grade_level"), t.get("academic_year"), t["id"]))
    if len(trm) != 1:
        print("!! ABORTADO: turma nao unica.")
        return
    turma = trm[0]
    year = turma.get("academic_year")
    if not year:
        print("!! ABORTADO: turma sem academic_year.")
        return
    d_ini, d_fim = "%s-%s" % (year, DATA_INI), "%s-%s" % (year, DATA_FIM)
    print("\n[PERIODO] %s -> %s (ano letivo=%s)" % (d_ini, d_fim, year))

    aa = _norm(ALUNA)
    primeiro = ALUNA.split()[0]
    cand = await db.students.find({"$or": [
        {"full_name": {"$regex": primeiro, "$options": "i"}},
        {"name": {"$regex": primeiro, "$options": "i"}}]},
        {"_id": 0, "id": 1, "full_name": 1, "name": 1, "class_id": 1}).to_list(100000)
    exatos = [a for a in cand if _norm(a.get("full_name") or a.get("name")) == aa]
    base = exatos or cand
    enr = await db.enrollments.find({"class_id": turma["id"]}, {"_id": 0, "student_id": 1}).to_list(100000)
    ids = {e.get("student_id") for e in enr}
    def na_turma(a):
        return a.get("class_id") == turma["id"] or a.get("id") in ids
    alunas = [a for a in base if na_turma(a)]
    print("\n[ALUNA] candidatas na turma: %d" % len(alunas))
    for a in alunas:
        print("   - %s (id=%s)" % (a.get("full_name") or a.get("name"), a["id"]))
    if len(alunas) != 1:
        print("   (todas por primeiro nome:)")
        for a in base:
            print("       * %s (id=%s, class_id=%s, na_turma=%s)" % (a.get("full_name") or a.get("name"), a["id"], a.get("class_id"), na_turma(a)))
        print("!! ABORTADO: aluna nao unica na turma.")
        return
    sid = alunas[0]["id"]

    docs = await db.attendance.find({"class_id": turma["id"], "date": {"$gte": d_ini, "$lte": d_fim}},
        {"_id": 0, "id": 1, "date": 1, "course_id": 1, "records": 1}).to_list(100000)
    docs.sort(key=lambda d: (d.get("date") or "", d.get("course_id") or ""))
    afet = []
    for d in docs:
        meus = [r for r in (d.get("records") or []) if r.get("student_id") == sid]
        if meus:
            afet.append((d["id"], d["date"], ",".join(str(r.get("status")) for r in meus)))
    print("\n[FREQUENCIA] docs no periodo: %d | com registro da aluna: %d" % (len(docs), len(afet)))
    for aid, dt, st in afet:
        print("   - %s  status=%s  (attendance_id=%s)" % (dt, st, aid))
    if not afet:
        print("\nNada a remover.")
        return
    if not APPLY:
        print("\n*** DRY-RUN *** nada foi alterado. Seriam removidos %d registro(s)." % len(afet))
        print("Para aplicar: adicione  --apply")
        return
    total = 0
    for aid, dt, st in afet:
        res = await db.attendance.update_one({"id": aid}, {"$pull": {"records": {"student_id": sid}}})
        total += res.modified_count
        print("   [OK] %s removido (modified=%d)" % (dt, res.modified_count))
    print("\n=== CONCLUIDO === removido em %d documento(s)." % total)

asyncio.run(main())
