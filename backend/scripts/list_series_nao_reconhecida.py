#!/usr/bin/env python3
"""
Lista os alunos ATIVOS com "Série não reconhecida" (mesma regra do painel
"Indicadores da Rede"), agrupados por ESCOLA e por SÉRIE (nomenclatura bruta
do cadastro).

Usa o MESMO canonicalizador do sistema (utils/serie_canonical.py), portanto o
total bate com o indicador. A série efetiva de cada aluno segue a mesma
prioridade do backend: `students.student_series` → `classes.grade_level`.

COMO RODAR (no servidor, via SSH):
    cd /app/backend
    python scripts/list_series_nao_reconhecida.py

OPÇÕES:
    --school   "<nome ou id da escola>"   filtra uma escola específica
    --serie    "<nomenclatura bruta>"     filtra uma nomenclatura (ex.: "PRÉ-ESCOLA I")
    --mantenedora "<id>"                  filtra por mantenedora (multi-tenant)
    --csv      <caminho.csv>              também exporta a lista para CSV
    --names-only                          imprime só nomes (sem CPF/turma)

EXEMPLOS:
    python scripts/list_series_nao_reconhecida.py
    python scripts/list_series_nao_reconhecida.py --school "Nivalda"
    python scripts/list_series_nao_reconhecida.py --serie "PRÉ-ESCOLA I"
    python scripts/list_series_nao_reconhecida.py --csv /tmp/series_nao_reconhecidas.csv
"""

import os
import sys
import csv
import argparse

# Permite importar utils.* quando rodado de qualquer diretório
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from pymongo import MongoClient  # noqa: E402
from utils.serie_canonical import canonicalize_serie  # noqa: E402


def _load_env():
    """Garante MONGO_URL / DB_NAME a partir do ambiente ou de backend/.env."""
    if os.environ.get("MONGO_URL") and os.environ.get("DB_NAME"):
        return
    env_path = os.path.join(BACKEND_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main():
    parser = argparse.ArgumentParser(description="Lista alunos com série não reconhecida.")
    parser.add_argument("--school", help="Nome (parcial) ou id da escola")
    parser.add_argument("--serie", help="Nomenclatura bruta da série (ex.: 'PRÉ-ESCOLA I')")
    parser.add_argument("--mantenedora", help="Filtra por mantenedora_id (multi-tenant)")
    parser.add_argument("--csv", help="Caminho para exportar CSV")
    parser.add_argument("--names-only", action="store_true", help="Imprime só nomes")
    args = parser.parse_args()

    _load_env()
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = MongoClient(mongo_url)
    db = client[db_name]

    # ---- Monta filtro de alunos ATIVOS ----
    match = {"status": "active"}
    if args.mantenedora:
        match["mantenedora_id"] = args.mantenedora
    if args.school:
        # tenta por id direto; senão resolve por nome (regex)
        sch = db.schools.find_one({"id": args.school}, {"_id": 0, "id": 1, "name": 1})
        if not sch:
            sch = db.schools.find_one(
                {"name": {"$regex": args.school, "$options": "i"}},
                {"_id": 0, "id": 1, "name": 1},
            )
        if not sch:
            print(f"[ERRO] Escola não encontrada para: {args.school!r}")
            sys.exit(1)
        match["school_id"] = sch["id"]
        print(f"Filtrando escola: {sch.get('name')} ({sch['id']})")

    pipeline = [
        {"$match": match},
        {"$lookup": {
            "from": "classes",
            "localField": "class_id",
            "foreignField": "id",
            "as": "_class",
        }},
        {"$addFields": {
            "_grade_effective": {
                "$let": {
                    "vars": {"ss": "$student_series"},
                    "in": {
                        "$cond": [
                            {"$and": [
                                {"$ne": ["$$ss", None]},
                                {"$ne": ["$$ss", ""]},
                            ]},
                            "$$ss",
                            {"$arrayElemAt": ["$_class.grade_level", 0]},
                        ]
                    },
                }
            },
            "_class_name": {"$arrayElemAt": ["$_class.name", 0]},
        }},
        {"$project": {
            "_id": 0, "id": 1, "full_name": 1, "cpf": 1,
            "school_id": 1, "_grade_effective": 1, "_class_name": 1,
        }},
    ]

    # school_id -> { raw_serie -> [students] }
    by_school = {}
    total = 0
    for s in db.students.aggregate(pipeline):
        raw = s.get("_grade_effective")
        if canonicalize_serie(raw) is not None:
            continue  # série reconhecida -> ignora
        raw_label = (str(raw).strip() if raw and str(raw).strip() else "(vazio)")
        if args.serie and raw_label.lower() != args.serie.strip().lower():
            continue
        by_school.setdefault(s.get("school_id"), {}).setdefault(raw_label, []).append(s)
        total += 1

    # Resolve nomes das escolas
    school_ids = list(by_school.keys())
    school_names = {}
    for sid in school_ids:
        doc = db.schools.find_one({"id": sid}, {"_id": 0, "name": 1})
        school_names[sid] = (doc or {}).get("name") or f"(sem nome: {sid})"

    # ---- Saída no terminal ----
    print("=" * 78)
    print(f"ALUNOS ATIVOS COM 'SÉRIE NÃO RECONHECIDA': {total}")
    print("=" * 78)

    csv_rows = []
    for sid in sorted(school_ids, key=lambda x: school_names.get(x, "")):
        series_map = by_school[sid]
        sch_total = sum(len(v) for v in series_map.values())
        print(f"\n■ {school_names[sid]}  —  {sch_total} aluno(s)")
        for raw_label in sorted(series_map.keys()):
            alunos = sorted(series_map[raw_label], key=lambda a: (a.get("full_name") or ""))
            print(f"   • Série cadastrada: {raw_label!r}  —  {len(alunos)} aluno(s)")
            for a in alunos:
                nome = a.get("full_name") or "(sem nome)"
                if args.names_only:
                    print(f"       - {nome}")
                else:
                    cpf = a.get("cpf") or "—"
                    turma = a.get("_class_name") or "—"
                    print(f"       - {nome}  | CPF: {cpf}  | Turma: {turma}")
                csv_rows.append({
                    "escola": school_names[sid],
                    "school_id": sid,
                    "serie_cadastrada": raw_label,
                    "aluno": a.get("full_name") or "",
                    "cpf": a.get("cpf") or "",
                    "turma": a.get("_class_name") or "",
                    "student_id": a.get("id") or "",
                })

    # ---- Exporta CSV (opcional) ----
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "escola", "school_id", "serie_cadastrada",
                "aluno", "cpf", "turma", "student_id",
            ])
            writer.writeheader()
            writer.writerows(csv_rows)
        print(f"\n[OK] CSV exportado: {args.csv}  ({len(csv_rows)} linhas)")

    print("\nConcluído.")


if __name__ == "__main__":
    main()
