#!/usr/bin/env python3
"""
STANDALONE — Corrige `classes.grade_level` vazio derivando a SERIE do NOME da turma.

Nao depende de nenhum import do projeto (canonicalizador embutido), portanto roda
em QUALQUER container, mesmo que utils/serie_canonical.py nao esteja presente.

SEGURANCA:
    - Por padrao roda em DRY-RUN (apenas mostra o que SERIA alterado).
    - So grava no banco com a flag --apply.
    - Turmas MULTISSERIADAS/combinadas NAO sao alteradas (revisao manual).

USO (dentro do container de producao, WORKDIR /app):
    python3 scripts/fix_grade_level_standalone.py                 # DRY-RUN
    python3 scripts/fix_grade_level_standalone.py --csv /tmp/p.csv
    python3 scripts/fix_grade_level_standalone.py --school "Nivalda"
    python3 scripts/fix_grade_level_standalone.py --apply         # GRAVA
"""

import os
import re
import sys
import csv
import argparse
import unicodedata
from typing import Optional

from pymongo import MongoClient


# ----------------------------------------------------------------------------
# Canonicalizador embutido (espelho de utils/serie_canonical.py)
# ----------------------------------------------------------------------------
def _strip_accents(s: str) -> str:
    return ''.join(
        c for c in unicodedata.normalize('NFD', s)
        if unicodedata.category(c) != 'Mn'
    )


def _normalize(raw: str) -> str:
    s = _strip_accents(raw or '')
    s = s.upper()
    s = s.replace('\u00ba', ' ').replace('\u00b0', ' ').replace('\u00aa', ' ').replace('\u1d43', ' ')
    s = re.sub(r'[\-_/.,]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


_ORDINAL_WORDS = {
    'PRIMEIRO': 1, 'PRIMEIRA': 1, 'SEGUNDO': 2, 'SEGUNDA': 2,
    'TERCEIRO': 3, 'TERCEIRA': 3, 'QUARTO': 4, 'QUARTA': 4,
    'QUINTO': 5, 'QUINTA': 5, 'SEXTO': 6, 'SEXTA': 6,
    'SETIMO': 7, 'SETIMA': 7, 'OITAVO': 8, 'OITAVA': 8,
    'NONO': 9, 'NONA': 9,
}
_ROMAN = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5}


def _detect_number(norm: str, max_n: int) -> Optional[int]:
    tokens = norm.split(' ')
    for t in tokens:
        if t.isdigit():
            n = int(t)
            if 1 <= n <= max_n:
                return n
    for t in tokens:
        if t in _ORDINAL_WORDS:
            return _ORDINAL_WORDS[t]
    for t in tokens:
        if t in _ROMAN:
            n = _ROMAN[t]
            if 1 <= n <= max_n:
                return n
    return None


def canonicalize_serie(raw: Optional[str]) -> Optional[str]:
    if not raw or not str(raw).strip():
        return None
    norm = _normalize(str(raw))
    if not norm:
        return None
    if norm.startswith('EJA '):
        norm = norm[4:].strip()
    if 'ETAPA' in norm:
        n = _detect_number(norm, 4)
        return f"{n}\u00aa ETAPA" if n else None
    if 'ANO' in norm:
        n = _detect_number(norm, 9)
        return f"{n}\u00ba ANO" if n else None

    def _infantil_level(default_to_i=True):
        n = _detect_number(norm, 5)
        if n in (1, 2):
            return n
        if n is None and default_to_i:
            return 1
        return None

    if 'BERCARIO' in norm or 'BERCARIA' in norm:
        lvl = _infantil_level()
        return f"BER\u00c7\u00c1RIO {'II' if lvl == 2 else 'I'}" if lvl else None
    if 'MATERNAL' in norm:
        lvl = _infantil_level()
        return f"MATERNAL {'II' if lvl == 2 else 'I'}" if lvl else None
    _tokens = norm.split(' ')
    is_pre = (
        'PRE' in _tokens
        or 'PRE ESCOLA' in norm
        or any(t.startswith('PREESCOL') or t.startswith('PRESCOL') for t in _tokens)
    )
    if is_pre:
        lvl = _infantil_level()
        return f"PR\u00c9 {'II' if lvl == 2 else 'I'}" if lvl else None
    return None


# ----------------------------------------------------------------------------
# Deteccao de turmas combinadas/multisseriadas
# ----------------------------------------------------------------------------
def _detect_grade_numbers(name):
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
    nums, norm = _detect_grade_numbers(name)
    if 'UNIFICADA' in norm or 'MULTI' in norm or 'ANOS' in norm:
        return True
    if len(nums) >= 2:
        return True
    return False


def _load_env(key):
    val = os.environ.get(key)
    if val:
        return val
    # tenta .env do backend (cwd ou /app)
    for base in (os.getcwd(), '/app', os.path.dirname(os.path.dirname(os.path.abspath(__file__)))):
        env_path = os.path.join(base, '.env')
        if os.path.exists(env_path):
            for line in open(env_path, encoding='utf-8'):
                line = line.strip()
                if line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                if k.strip() == key:
                    return v.strip().strip('"').strip("'")
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--school", help="Nome (parcial) ou id da escola")
    parser.add_argument("--apply", action="store_true", help="GRAVA as alteracoes")
    parser.add_argument("--csv", help="Exporta o preview/relatorio para CSV")
    parser.add_argument("--mongo-url")
    parser.add_argument("--db")
    args = parser.parse_args()

    mongo = args.mongo_url or _load_env("MONGO_URL")
    dbn = args.db or _load_env("DB_NAME")
    if not mongo or not dbn:
        print("[ERRO] Defina MONGO_URL/DB_NAME (ou use --mongo-url/--db).")
        sys.exit(2)

    db = MongoClient(mongo)[dbn]

    school_filter = {}
    if args.school:
        sch = db.schools.find_one({"id": args.school}, {"_id": 0, "id": 1, "name": 1}) or \
            db.schools.find_one({"name": {"$regex": args.school, "$options": "i"}}, {"_id": 0, "id": 1, "name": 1})
        if not sch:
            print(f"[ERRO] Escola nao encontrada: {args.school!r}")
            sys.exit(1)
        school_filter = {"school_id": sch["id"]}
        print(f"Filtrando escola: {sch.get('name')} ({sch['id']})")

    cls_query = {
        **school_filter,
        "$or": [
            {"grade_level": {"$in": [None, ""]}},
            {"grade_level": {"$exists": False}},
        ],
    }

    fixable = []
    manual = []
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
            manual.append((sn, cid, name, "Nome nao reconhecido", n_alunos))
        else:
            fixable.append((sn, cid, name, canon, n_alunos))

    modo = "APLICANDO (grava no banco)" if args.apply else "DRY-RUN (nenhuma alteracao)"
    print("=" * 80)
    print(f"CORRECAO DE grade_level A PARTIR DO NOME DA TURMA - {modo}")
    print("=" * 80)

    fix_alunos = sum(x[4] for x in fixable)
    print(f"\n[OK] Turmas AUTO-CORRIGIVEIS: {len(fixable)}  ({fix_alunos} alunos ativos)")
    for sn in sorted(set(x[0] for x in fixable)):
        print(f"\n  # {sn}")
        for (s, cid, name, canon, n) in sorted([x for x in fixable if x[0] == sn], key=lambda y: y[2]):
            print(f"     - {name!r}  ->  grade_level = {canon!r}   ({n} aluno(s))")

    man_alunos = sum(x[4] for x in manual)
    print(f"\n[!] Turmas para REVISAO MANUAL: {len(manual)}  ({man_alunos} alunos ativos)")
    for (sn, cid, name, motivo, n) in sorted(manual, key=lambda y: (y[0], y[2])):
        print(f"     - [{sn}] {name!r}  ->  {motivo}   ({n} aluno(s))")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["tipo", "escola", "class_id", "turma", "proposto_ou_motivo", "alunos_ativos"])
            for (sn, cid, name, canon, n) in fixable:
                w.writerow(["AUTO", sn, cid, name, canon, n])
            for (sn, cid, name, motivo, n) in manual:
                w.writerow(["MANUAL", sn, cid, name, motivo, n])
        print(f"\n[OK] Relatorio CSV: {args.csv}")

    if args.apply:
        updated = 0
        for (sn, cid, name, canon, n) in fixable:
            res = db.classes.update_one({"id": cid}, {"$set": {"grade_level": canon}})
            updated += res.modified_count
        print(f"\n[APLICADO] {updated} turma(s) atualizada(s) com grade_level derivado do nome.")
        print("As turmas de REVISAO MANUAL acima NAO foram alteradas.")
    else:
        print("\n(DRY-RUN) Nada foi alterado. Para gravar, rode novamente com --apply")

    print("\nConcluido.")


if __name__ == "__main__":
    main()
