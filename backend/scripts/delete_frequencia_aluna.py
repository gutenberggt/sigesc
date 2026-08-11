"""
Remove a FREQUÊNCIA de UMA aluna em um intervalo de datas, com segurança.

Aluna : "Kathally Ynara Borges da Silva"
Turma : "2º Ano D"
Escola: "E M E I E F Paroquial Curupira"
Período (inclusive): 26/02 a 31/03 do ANO LETIVO da turma.

COMO A FREQUÊNCIA É ARMAZENADA (Anos Iniciais / diário):
  1 documento por TURMA por DIA, com um array `records` = [{student_id, status}, ...].
  Portanto "apagar a frequência da aluna" = remover as ENTRADAS DELA do array
  `records` desses documentos (NÃO apagar o documento inteiro — isso afetaria os
  demais alunos da turma).

SEGURANÇA:
  - DRY-RUN por padrão: apenas MOSTRA o que seria alterado. Nada é gravado.
  - Só grava de verdade com a flag  --apply
  - Aborta se a escola/turma/aluna forem ambíguas (mais de um resultado).

COMO RODAR NO DROPLET (sigesc-prod-01):
    cd /app/backend            # ou o caminho do backend no servidor
    python scripts/delete_frequencia_aluna.py            # DRY-RUN (não altera nada)
    python scripts/delete_frequencia_aluna.py --apply    # aplica de fato
"""
import asyncio
import os
import re
import sys
import unicodedata

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

ALUNA = "Kathally Ynara Borges da Silva"
TURMA = "2º Ano D"
ESCOLA = "E M E I E F Paroquial Curupira"
DATA_INI = "02-26"   # 26/02  (MM-DD)
DATA_FIM = "03-31"   # 31/03  (MM-DD)

APPLY = "--apply" in sys.argv


def _norm(s: str) -> str:
    """Minúsculas, sem acentos, colapsa espaços e normaliza ordinais (2º/2°/2o -> 2)."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = s.replace("º", "").replace("°", "").replace("ª", "")
    s = re.sub(r"\bano\b", "ano", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    # ---------------- 1) ESCOLA ----------------
    schools = await db.schools.find({}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1}).to_list(100000)
    alvo_escola = _norm(ESCOLA)
    esc = [s for s in schools if alvo_escola in _norm(s.get("name"))]
    if not esc:
        # busca mais frouxa por "paroquial curupira"
        esc = [s for s in schools if "paroquial curupira" in _norm(s.get("name"))]
    print(f"\n[ESCOLA] candidatos para '{ESCOLA}': {len(esc)}")
    for s in esc:
        print(f"   - {s['name']}  (id={s['id']})")
    if len(esc) != 1:
        print("!! ABORTADO: escola não encontrada de forma única. Ajuste ESCOLA no script.")
        return
    school = esc[0]

    # ---------------- 2) TURMA ----------------
    turmas = await db.classes.find(
        {"school_id": school["id"]},
        {"_id": 0, "id": 1, "name": 1, "grade_level": 1, "academic_year": 1, "education_level": 1},
    ).to_list(100000)
    alvo_turma = _norm(TURMA)
    trm = [t for t in turmas if _norm(t.get("name")) == alvo_turma]
    if not trm:
        trm = [t for t in turmas if alvo_turma in _norm(t.get("name"))]
    print(f"\n[TURMA] candidatos para '{TURMA}' na escola: {len(trm)}")
    for t in trm:
        print(f"   - {t['name']}  (série={t.get('grade_level')}, ano={t.get('academic_year')}, id={t['id']})")
    if len(trm) != 1:
        print("!! ABORTADO: turma não encontrada de forma única. Ajuste TURMA no script.")
        return
    turma = trm[0]
    year = turma.get("academic_year")
    if not year:
        print("!! ABORTADO: turma sem academic_year definido.")
        return
    d_ini = f"{year}-{DATA_INI}"
    d_fim = f"{year}-{DATA_FIM}"
    print(f"\n[PERÍODO] {d_ini}  ->  {d_fim}  (ano letivo da turma = {year})")

    # ---------------- 3) ALUNA ----------------
    alvo_aluna = _norm(ALUNA)
    # busca por nome (regex primeiro nome) e confirma vínculo com a turma
    primeiro = ALUNA.split()[0]
    cand = await db.students.find(
        {"$or": [
            {"full_name": {"$regex": primeiro, "$options": "i"}},
            {"name": {"$regex": primeiro, "$options": "i"}},
        ]},
        {"_id": 0, "id": 1, "full_name": 1, "name": 1, "class_id": 1},
    ).to_list(100000)
    # nome exato normalizado
    exatos = [a for a in cand if _norm(a.get("full_name") or a.get("name")) == alvo_aluna]
    base = exatos or cand

    # matrículas da turma (fonte de vínculo mais confiável)
    enr = await db.enrollments.find(
        {"class_id": turma["id"]}, {"_id": 0, "student_id": 1, "status": 1}
    ).to_list(100000)
    ids_na_turma = {e.get("student_id") for e in enr}

    def na_turma(a):
        return a.get("class_id") == turma["id"] or a.get("id") in ids_na_turma

    alunas = [a for a in base if na_turma(a)]
    print(f"\n[ALUNA] candidatas para '{ALUNA}' vinculadas à turma: {len(alunas)}")
    for a in alunas:
        print(f"   - {a.get('full_name') or a.get('name')}  (id={a['id']})")
    if len(alunas) != 1:
        print("   (todas as candidatas pelo primeiro nome, para conferência:)")
        for a in base:
            print(f"       * {a.get('full_name') or a.get('name')}  (id={a['id']}, class_id={a.get('class_id')}, na_turma={na_turma(a)})")
        print("!! ABORTADO: aluna não encontrada de forma única na turma. Confira acima.")
        return
    aluna = alunas[0]
    sid = aluna["id"]

    # ---------------- 4) DOCUMENTOS DE FREQUÊNCIA NO PERÍODO ----------------
    docs = await db.attendance.find(
        {"class_id": turma["id"], "date": {"$gte": d_ini, "$lte": d_fim}},
        {"_id": 0, "id": 1, "date": 1, "course_id": 1, "attendance_type": 1, "records": 1},
    ).to_list(100000)
    docs.sort(key=lambda d: (d.get("date") or "", d.get("course_id") or ""))

    afetados = []  # (attendance_id, date, status_atual)
    for d in docs:
        recs = d.get("records") or []
        meus = [r for r in recs if r.get("student_id") == sid]
        if meus:
            afetados.append((d["id"], d["date"], ",".join(str(r.get("status")) for r in meus)))

    print(f"\n[FREQUÊNCIA] documentos da turma no período: {len(docs)} | com registro da aluna: {len(afetados)}")
    for aid, dt, st in afetados:
        print(f"   - {dt}  status={st}  (attendance_id={aid})")

    if not afetados:
        print("\nNada a remover: a aluna não possui registros de frequência nesse período nessa turma.")
        return

    # ---------------- 5) APLICAR (ou apenas simular) ----------------
    if not APPLY:
        print(f"\n*** DRY-RUN *** — NADA foi alterado. Seriam removidos {len(afetados)} registro(s) da aluna.")
        print("Para aplicar de fato, rode novamente com:  --apply")
        return

    total = 0
    for aid, dt, st in afetados:
        res = await db.attendance.update_one(
            {"id": aid},
            {"$pull": {"records": {"student_id": sid}}},
        )
        total += res.modified_count
        print(f"   [OK] {dt}: removido (modified={res.modified_count})")

    print(f"\n=== CONCLUÍDO === registros de frequência da aluna removidos em {total} documento(s).")

asyncio.run(main())
