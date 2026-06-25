#!/usr/bin/env python3
"""
Harness de Homologação ISOLADA — Transferência Institucional.

Cria um sandbox COMPLETAMENTE ISOLADO do ciclo real de dados:
  - 1 mantenedora dedicada (id começa com 'HMLSBX-MANT')
  - 2 escolas (origem + destino) na mesma mantenedora
  - 1 calendário letivo no destino
  - N turmas (com school_history), alunos e amostras de TODOS os domínios
    (matrículas, frequência, notas, conteúdo, AEE, Bolsa Família)
Todos os documentos recebem a marca `homolog_sandbox: True` e ids com prefixo
'HMLSBX-' → o teardown remove tudo com segurança, sem tocar em dados reais.

Subcomandos:
  seed       Cria/garante o sandbox e imprime IDs + baseline.
  baseline   Imprime contagens e amostras atuais (read-only).
  validate   Verifica alinhamento de school_id e integridade (read-only).
             --expect dest|origin
  teardown   Remove TODO o sandbox (idempotente).

Uso:
  python scripts/homolog_transfer_sandbox.py seed
  python scripts/homolog_transfer_sandbox.py validate --expect dest
  python scripts/homolog_transfer_sandbox.py teardown
"""
from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

TAG = {"homolog_sandbox": True}
PFX = "HMLSBX-"
MANT_ID = f"{PFX}MANT-001"
ORIGIN_ID = f"{PFX}SCHOOL-ORIGIN"
DEST_ID = f"{PFX}SCHOOL-DEST"
YEAR = 2025
LEVEL = "educacao_infantil"
N_CLASSES = 2
N_STUDENTS_PER_CLASS = 3

CLASS_ANCHORED = ["students", "enrollments", "attendance", "grades", "content_entries",
                  "student_dependencies", "teacher_class_assignments"]
STUDENT_ANCHORED = ["planos_aee", "atendimentos_aee", "evolucoes_aee", "articulacoes_aee",
                    "bolsa_familia_tracking"]

GREEN, RED, YEL, RST = "\033[92m", "\033[91m", "\033[93m", "\033[0m"


def _now():
    return datetime.now(timezone.utc).isoformat()


def class_ids():
    return [c["id"] for c in db.classes.find({"id": {"$regex": f"^{PFX}CLASS-"}}, {"_id": 0, "id": 1})]


def student_ids():
    return [s["id"] for s in db.students.find({"id": {"$regex": f"^{PFX}STU-"}}, {"_id": 0, "id": 1})]


# --------------------------------------------------------------------- SEED
def seed():
    teardown(silent=True)  # garante estado limpo e idempotente

    db.mantenedoras.insert_one({**TAG, "id": MANT_ID, "nome": "MANTENEDORA HOMOLOG SANDBOX",
                                "name": "MANTENEDORA HOMOLOG SANDBOX", "created_at": _now()})
    for sid, nm in [(ORIGIN_ID, "ESCOLA ORIGEM (HOMOLOG)"), (DEST_ID, "ESCOLA DESTINO (HOMOLOG)")]:
        db.schools.insert_one({**TAG, "id": sid, "name": nm, "mantenedora_id": MANT_ID,
                               "status": "active", "niveis_ensino_oferecidos": [LEVEL],
                               "educacao_infantil": True, "created_at": _now()})
    db.calendario_letivo.insert_one({**TAG, "id": f"{PFX}CAL-{YEAR}", "ano_letivo": YEAR,
                                     "school_id": DEST_ID, "mantenedora_id": MANT_ID,
                                     "dias_letivos_previstos": 200})

    for k in range(N_CLASSES):
        cid = f"{PFX}CLASS-{k}"
        db.classes.insert_one({**TAG, "id": cid, "name": f"TURMA HOMOLOG {k}", "school_id": ORIGIN_ID,
                               "mantenedora_id": MANT_ID, "grade_level": "Pré I", "education_level": LEVEL,
                               "academic_year": YEAR, "shift": "morning",
                               "school_history": [{"school_id": ORIGIN_ID, "start_date": f"{YEAR}-01-01", "end_date": None}],
                               "created_at": _now()})
        for n in range(N_STUDENTS_PER_CLASS):
            sid = f"{PFX}STU-{k}-{n}"
            db.students.insert_one({**TAG, "id": sid, "full_name": f"Aluno Homolog {k}-{n}",
                                    "birth_date": "2019-05-01", "sex": "feminino", "school_id": ORIGIN_ID,
                                    "class_id": cid, "mantenedora_id": MANT_ID, "status": "active",
                                    "created_at": _now()})
            db.enrollments.insert_one({**TAG, "id": f"{PFX}ENR-{k}-{n}", "student_id": sid, "school_id": ORIGIN_ID,
                                       "class_id": cid, "academic_year": YEAR, "status": "active",
                                       "enrollment_number": f"H{k}{n}", "mantenedora_id": MANT_ID, "created_at": _now()})
            db.grades.insert_one({**TAG, "id": f"{PFX}GRD-{k}-{n}", "student_id": sid, "class_id": cid,
                                  "course_id": f"{PFX}COURSE", "academic_year": YEAR, "b1": 8.5,
                                  "mantenedora_id": MANT_ID, "created_at": _now()})
            # AEE + Bolsa Família somente no 1º aluno de cada turma
            if n == 0:
                db.planos_aee.insert_one({**TAG, "id": f"{PFX}AEE-{k}", "student_id": sid, "school_id": ORIGIN_ID,
                                          "academic_year": YEAR, "status": "ativo", "created_at": _now()})
                db.bolsa_familia_tracking.insert_one({**TAG, "student_id": sid, "school_id": ORIGIN_ID,
                                                      "academic_year": YEAR, "month": 3, "notes": "homolog",
                                                      "updated_at": _now()})
        # frequência + conteúdo por turma
        db.attendance.insert_one({**TAG, "id": f"{PFX}ATT-{k}", "class_id": cid, "date": f"{YEAR}-03-10",
                                  "course_id": f"{PFX}COURSE", "academic_year": YEAR, "records": [],
                                  "number_of_classes": 1, "mantenedora_id": MANT_ID, "created_at": _now()})
        db.content_entries.insert_one({**TAG, "id": f"{PFX}CNT-{k}", "class_id": cid, "course_id": f"{PFX}COURSE",
                                       "date": f"{YEAR}-03-10", "content": "Conteúdo homolog", "school_id": ORIGIN_ID,
                                       "status": "published", "deleted": False, "created_at": _now()})

    print(f"{GREEN}Sandbox criado.{RST}")
    print(f"  Mantenedora : {MANT_ID}")
    print(f"  Origem      : {ORIGIN_ID}  (ESCOLA ORIGEM (HOMOLOG))")
    print(f"  Destino     : {DEST_ID}  (ESCOLA DESTINO (HOMOLOG))")
    print(f"  Ano letivo  : {YEAR}  | Turmas: {N_CLASSES} | Alunos: {N_CLASSES*N_STUDENTS_PER_CLASS}")
    print()
    baseline()


# ----------------------------------------------------------------- BASELINE
def _counts():
    cids, sids = class_ids(), student_ids()
    out = {"classes": len(cids)}
    for coll in CLASS_ANCHORED:
        out[coll] = db[coll].count_documents({"class_id": {"$in": cids}})
    for coll in STUDENT_ANCHORED:
        out[coll] = db[coll].count_documents({"student_id": {"$in": sids}}) if sids else 0
    out["students_distinct"] = len(sids)
    return out


def baseline():
    print("Contagens atuais (sandbox):")
    for k, v in _counts().items():
        print(f"  {k:24s}: {v}")


# ----------------------------------------------------------------- VALIDATE
def validate(expect):
    target = DEST_ID if expect == "dest" else ORIGIN_ID
    cids, sids = class_ids(), student_ids()
    ok_all = True

    def check(label, cond, detail=""):
        nonlocal ok_all
        ok_all = ok_all and cond
        print(f"  [{GREEN+'PASS'+RST if cond else RED+'FALL'+RST}] {label} {detail}")

    print(f"Validação pós-operação — esperado: school_id == {expect.upper()} ({target})")

    # 1) turmas
    cls_ok = db.classes.count_documents({"id": {"$in": cids}, "school_id": target}) == len(cids)
    check("Turmas no destino/origem esperado", cls_ok)

    # 2) school_history íntegro (sem sobreposição/lacuna, último segmento coerente)
    hist_ok = True
    for c in db.classes.find({"id": {"$in": cids}}, {"_id": 0, "school_id": 1, "school_history": 1}):
        h = c.get("school_history") or []
        # segmentos não podem ter mais de 1 aberto
        open_segs = [s for s in h if s.get("end_date") is None]
        if expect == "dest":
            cond = len(open_segs) == 1 and open_segs[0].get("school_id") == DEST_ID
        else:
            # após rollback: nenhum segmento aberto apontando ao destino
            cond = not any(s.get("school_id") == DEST_ID and s.get("end_date") is None for s in h)
        hist_ok = hist_ok and cond
    check("school_history coerente (sem sobreposição/lacuna)", hist_ok)

    # 3) alunos / matrículas
    check("Alunos no esperado", db.students.count_documents({"id": {"$in": sids}, "school_id": target}) == len(sids))
    check("Matrículas no esperado",
          db.enrollments.count_documents({"class_id": {"$in": cids}, "school_id": target}) ==
          db.enrollments.count_documents({"class_id": {"$in": cids}}))

    # 4) conteúdo / AEE / Bolsa Família (carregam school_id)
    check("Conteúdo no esperado",
          db.content_entries.count_documents({"class_id": {"$in": cids}, "school_id": target}) ==
          db.content_entries.count_documents({"class_id": {"$in": cids}}))
    check("AEE (planos) no esperado",
          db.planos_aee.count_documents({"student_id": {"$in": sids}, "school_id": target}) ==
          db.planos_aee.count_documents({"student_id": {"$in": sids}}))
    check("Bolsa Família no esperado",
          db.bolsa_familia_tracking.count_documents({"student_id": {"$in": sids}, "school_id": target}) ==
          db.bolsa_familia_tracking.count_documents({"student_id": {"$in": sids}}))

    # 5) sem perda de dados (frequência/notas continuam vinculadas por class_id)
    check("Frequência preservada (count > 0)", db.attendance.count_documents({"class_id": {"$in": cids}}) > 0)
    check("Notas preservadas (count > 0)", db.grades.count_documents({"class_id": {"$in": cids}}) > 0)

    # 6) status da escola origem
    origin = db.schools.find_one({"id": ORIGIN_ID}, {"_id": 0, "status": 1}) or {}
    if expect == "dest":
        check("Escola origem ENCERRADA (sem turmas)", origin.get("status") == "encerrada",
              f"(status={origin.get('status')})")
    else:
        check("Escola origem REABERTA (active)", origin.get("status") == "active",
              f"(status={origin.get('status')})")

    print(f"\nRESULTADO: {GREEN+'TUDO OK'+RST if ok_all else RED+'FALHA — ver itens FALL'+RST}")
    return ok_all


# ----------------------------------------------------------------- TEARDOWN
def teardown(silent=False):
    cids, sids = class_ids(), student_ids()
    removed = {}
    # coleções com a marca
    marked = ["mantenedoras", "schools", "calendario_letivo", "classes",
              "students", "enrollments", "attendance", "grades", "content_entries",
              "planos_aee", "bolsa_familia_tracking"]
    for coll in marked:
        r = db[coll].delete_many(TAG)
        if r.deleted_count:
            removed[coll] = r.deleted_count
    # auditoria/recibos do sandbox (por class_ids ou ids de escola)
    r = db.school_transfer_audit.delete_many({"$or": [
        {"class_ids": {"$in": cids}} if cids else {"_id": None},
        {"origin_school_id": ORIGIN_ID}, {"destination_school_id": DEST_ID}]})
    if r.deleted_count:
        removed["school_transfer_audit"] = r.deleted_count
    r = db.verifiable_documents.delete_many({"entity_type": "school_transfer", "school_id": DEST_ID})
    if r.deleted_count:
        removed["verifiable_documents"] = r.deleted_count
    r = db.academic_events.delete_many({"$or": [
        {"origin_class_id": {"$regex": f"^{PFX}CLASS-"}},
        {"destination_class_id": {"$regex": f"^{PFX}CLASS-"}}]})
    if r.deleted_count:
        removed["academic_events"] = r.deleted_count
    if not silent:
        print(f"{YEL}Teardown concluído.{RST} Removidos: {removed or 'nada (já limpo)'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["seed", "baseline", "validate", "teardown"])
    p.add_argument("--expect", choices=["dest", "origin"], default="dest")
    a = p.parse_args()
    if a.command == "seed":
        seed()
    elif a.command == "baseline":
        baseline()
    elif a.command == "validate":
        sys.exit(0 if validate(a.expect) else 1)
    elif a.command == "teardown":
        teardown()
