#!/usr/bin/env python3
"""
Corrige o campo `classes.grade_level` vazio derivando a SÉRIE do NOME da turma.

Resolve a maior parte dos casos de "Série não reconhecida" nos Indicadores da
Rede, que ocorrem porque a turma tem nome (ex.: "Maternal I C", "2º ANO A") mas
o campo estruturado `grade_level` está em branco.

SEGURANÇA:
    - Por padrão roda em DRY-RUN (apenas mostra o que SERIA alterado).
    - Só grava no banco com a flag --apply.
    - Turmas MULTISSERIADAS/combinadas (ex.: "Maternal I e II", "3º,4º E 5º ANOS",
      "SALA UNIFICADA...") NÃO são alteradas — entram na lista de revisão manual,
      pois a série correta varia por aluno (deve ir em students.student_series).

USO:
    cd /app && python3 scripts/fix_grade_level_from_turma.py            # DRY-RUN
    cd /app && python3 scripts/fix_grade_level_from_turma.py --school "Nivalda"
    cd /app && python3 scripts/fix_grade_level_from_turma.py --csv /tmp/fix_preview.csv
    cd /app && python3 scripts/fix_grade_level_from_turma.py --apply    # GRAVA
"""

import os
import re
import sys
import csv
import argparse

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from pymongo import MongoClient  # noqa: E402
from utils.serie_canonical import canonicalize_serie, _normalize  # noqa: E402


def _detect_grade_numbers(name):
    """Extrai os números de série presentes no nome (dígitos, romanos isolados
    e palavras-ordinais). Usado para detectar turmas COMBINADAS (2+ séries)."""
    norm = _normalize(name)
    nums = set()
    roman = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5}
    ordinais = {
        'PRIMEIRO': 1, 'PRIMEIRA': 1, 'SEGUNDO': 2, 'SEGUNDA': 2,
        'TERCEIRO': 3, 'TERCEIRA': 3, 'QUARTO': 4, 'QUARTA': 4,
        'QUINTO': 5, 'QUINTA': 5, 'SEXTO': 6, 'SEXTA': 6,
        'SETIMO': 7, 'OITAVO': 8, 'NONO': 9,
    }
    for t in norm.split(' '):
        if t.isdigit():
            nums.add(int(t))
        elif t in roman:
            nums.add(roman[t])
        elif t in ordinais:
            nums.add(ordinais[t])
    return nums, norm


def _is_combined(name):
    """True se a turma parece MULTISSERIADA/combinada (não auto-corrigível)."""
    nums, norm = _detect_grade_numbers(name)
    if 'UNIFICADA' in norm or 'MULTI' in norm or 'ANOS' in norm:
        return True
    if len(nums) >= 2:
        return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--school", help="Nome (parcial) ou id da escola")
    parser.add_argument("--apply", action="store_true", help="GRAVA as alterações")
    parser.add_argument("--csv", help="Exporta o preview/relatório para CSV")
    parser.add_argument("--mongo-url")
    parser.add_argument("--db")
    args = parser.parse_args()

    mongo = args.mongo_url or os.environ.get("MONGO_URL")
    dbn = args.db or os.environ.get("DB_NAME")
    if (not mongo or not dbn):
        env_path = os.path.join(BACKEND_DIR, ".env")
        if os.path.exists(env_path):
            for line in open(env_path, encoding="utf-8"):
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    v = v.strip().strip('"').strip("'")
                    if k.strip() == "MONGO_URL" and not mongo:
                        mongo = v
                    if k.strip() == "DB_NAME" and not dbn:
                        dbn = v
    if not mongo or not dbn:
        print("[ERRO] Defina MONGO_URL/DB_NAME (ou use --mongo-url/--db).")
        sys.exit(2)

    db = MongoClient(mongo)[dbn]

    # Filtro de escola (opcional)
    school_filter = {}
    if args.school:
        sch = db.schools.find_one({"id": args.school}, {"_id": 0, "id": 1, "name": 1}) or \
            db.schools.find_one({"name": {"$regex": args.school, "$options": "i"}}, {"_id": 0, "id": 1, "name": 1})
        if not sch:
            print(f"[ERRO] Escola não encontrada: {args.school!r}")
            sys.exit(1)
        school_filter = {"school_id": sch["id"]}
        print(f"Filtrando escola: {sch.get('name')} ({sch['id']})")

    # Turmas com grade_level vazio/ausente
    cls_query = {
        **school_filter,
        "$or": [
            {"grade_level": {"$in": [None, ""]}},
            {"grade_level": {"$exists": False}},
        ],
    }

    fixable = []   # (school_name, class_id, class_name, proposed, n_alunos)
    manual = []    # (school_name, class_id, class_name, motivo, n_alunos)
    school_cache = {}

    def school_name(sid):
        if sid not in school_cache:
            d = db.schools.find_one({"id": sid}, {"_id": 0, "name": 1})
            school_cache[sid] = (d or {}).get("name") or f"(sem nome: {sid})"
        return school_cache[sid]

    for c in db.classes.find(cls_query, {"_id": 0, "id": 1, "name": 1, "school_id": 1}):
        cid = c.get("id")
        name = c.get("name") or ""
        n_alunos = db.students.count_documents({"class_id": cid, "status": "active"})
        sn = school_name(c.get("school_id"))
        if _is_combined(name):
            manual.append((sn, cid, name, "Turma combinada/multisseriada", n_alunos))
            continue
        canon = canonicalize_serie(name)
        if not canon:
            manual.append((sn, cid, name, "Nome não reconhecido", n_alunos))
        else:
            fixable.append((sn, cid, name, canon, n_alunos))

    # ---- Relatório ----
    modo = "APLICANDO (grava no banco)" if args.apply else "DRY-RUN (nenhuma alteração)"
    print("=" * 80)
    print(f"CORREÇÃO DE grade_level A PARTIR DO NOME DA TURMA — {modo}")
    print("=" * 80)

    fix_alunos = sum(x[4] for x in fixable)
    print(f"\n✔ Turmas AUTO-CORRIGÍVEIS: {len(fixable)}  ({fix_alunos} alunos ativos)")
    for sn in sorted(set(x[0] for x in fixable)):
        print(f"\n  ■ {sn}")
        for (s, cid, name, canon, n) in sorted([x for x in fixable if x[0] == sn], key=lambda y: y[2]):
            print(f"     - {name!r}  →  grade_level = {canon!r}   ({n} aluno(s))")

    man_alunos = sum(x[4] for x in manual)
    print(f"\n⚠ Turmas para REVISÃO MANUAL: {len(manual)}  ({man_alunos} alunos ativos)")
    for (sn, cid, name, motivo, n) in sorted(manual, key=lambda y: (y[0], y[2])):
        print(f"     - [{sn}] {name!r}  →  {motivo}   ({n} aluno(s))")

    # ---- CSV (opcional) ----
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["tipo", "escola", "class_id", "turma", "proposto_ou_motivo", "alunos_ativos"])
            for (sn, cid, name, canon, n) in fixable:
                w.writerow(["AUTO", sn, cid, name, canon, n])
            for (sn, cid, name, motivo, n) in manual:
                w.writerow(["MANUAL", sn, cid, name, motivo, n])
        print(f"\n[OK] Relatório CSV: {args.csv}")

    # ---- Aplica ----
    if args.apply:
        updated = 0
        for (sn, cid, name, canon, n) in fixable:
            res = db.classes.update_one({"id": cid}, {"$set": {"grade_level": canon}})
            updated += res.modified_count
        print(f"\n[APLICADO] {updated} turma(s) atualizada(s) com grade_level derivado do nome.")
        print("As turmas de REVISÃO MANUAL acima NÃO foram alteradas.")
    else:
        print("\n(DRY-RUN) Nada foi alterado. Para gravar, rode novamente com --apply")

    print("\nConcluído.")


if __name__ == "__main__":
    main()
