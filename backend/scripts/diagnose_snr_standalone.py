#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STANDALONE — DIAGNOSTICO DE CAUSA-RAIZ de "Serie nao reconhecida".

Replica EXATAMENTE a regra do painel "Indicadores da Rede"
(_grade_effective = student_series OU classes.grade_level) e, para cada aluno
ATIVO que cai em "Serie nao reconhecida", classifica o MOTIVO exato:

  A) student_series PREENCHIDO mas nao reconhecido  -> valor invalido no aluno
  B) student_series vazio + turma SEM grade_level    -> corrigir grade_level
  C) student_series vazio + grade_level PREENCHIDO mas nao reconhecido
  D) student_series vazio + TURMA ORFA (class_id nao existe em classes)
  E) student_series vazio + aluno SEM class_id

Imprime um RESUMO por motivo e por VALOR bruto (com contagem), e por ESCOLA.
Nao altera nada no banco. So leitura.

USO (dentro do container, WORKDIR /app):
    python3 scripts/diagnose_snr_standalone.py
    python3 scripts/diagnose_snr_standalone.py --csv /tmp/snr_diag.csv
    python3 scripts/diagnose_snr_standalone.py --school "Nivalda"
"""

import os
import re
import sys
import csv
import argparse
import unicodedata
from collections import defaultdict

from pymongo import MongoClient


# ---- Canonicalizador (copia de utils/serie_canonical.py) -------------------
_ORDINAL_WORDS = {
    'PRIMEIRO': 1, 'PRIMEIRA': 1, 'SEGUNDO': 2, 'SEGUNDA': 2,
    'TERCEIRO': 3, 'TERCEIRA': 3, 'QUARTO': 4, 'QUARTA': 4,
    'QUINTO': 5, 'QUINTA': 5, 'SEXTO': 6, 'SEXTA': 6,
    'SETIMO': 7, 'SETIMA': 7, 'OITAVO': 8, 'OITAVA': 8,
    'NONO': 9, 'NONA': 9,
}
_ROMAN = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5}


def _strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn')


def _normalize(raw):
    s = _strip_accents(raw or '')
    s = s.upper()
    s = s.replace('\u00ba', ' ').replace('\u00b0', ' ').replace('\u00aa', ' ').replace('\u1d43', ' ')
    s = re.sub(r'[\-_/.,]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _detect_number(norm, max_n):
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


def canonicalize_serie(raw):
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
    is_pre = ('PRE' in _tokens or 'PRE ESCOLA' in norm
              or any(t.startswith('PREESCOL') or t.startswith('PRESCOL') for t in _tokens))
    if is_pre:
        lvl = _infantil_level()
        return f"PR\u00c9 {'II' if lvl == 2 else 'I'}" if lvl else None
    return None


def _load_env(key):
    val = os.environ.get(key)
    if val:
        return val
    for base in (os.getcwd(), '/app', os.path.dirname(os.path.dirname(os.path.abspath(__file__)))):
        p = os.path.join(base, '.env')
        if os.path.exists(p):
            for line in open(p, encoding='utf-8'):
                line = line.strip()
                if line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                if k.strip() == key:
                    return v.strip().strip('"').strip("'")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--school")
    ap.add_argument("--csv")
    ap.add_argument("--mongo-url")
    ap.add_argument("--db")
    args = ap.parse_args()

    mongo = args.mongo_url or _load_env("MONGO_URL")
    dbn = args.db or _load_env("DB_NAME")
    if not mongo or not dbn:
        print("[ERRO] Defina MONGO_URL/DB_NAME (ou use --mongo-url/--db).")
        sys.exit(2)
    db = MongoClient(mongo)[dbn]

    match = {"status": "active"}
    if args.school:
        sch = db.schools.find_one({"id": args.school}, {"_id": 0, "id": 1, "name": 1}) or \
            db.schools.find_one({"name": {"$regex": args.school, "$options": "i"}}, {"_id": 0, "id": 1, "name": 1})
        if not sch:
            print(f"[ERRO] Escola nao encontrada: {args.school!r}")
            sys.exit(1)
        match["school_id"] = sch["id"]
        print(f"Filtrando escola: {sch.get('name')} ({sch['id']})")

    # Cache de turmas (id -> {name, grade_level})
    cls_cache = {}

    def get_class(cid):
        if cid not in cls_cache:
            d = db.classes.find_one({"id": cid}, {"_id": 0, "name": 1, "grade_level": 1})
            cls_cache[cid] = d  # pode ser None (orfa)
        return cls_cache[cid]

    school_cache = {}

    def school_name(sid):
        if sid not in school_cache:
            d = db.schools.find_one({"id": sid}, {"_id": 0, "name": 1})
            school_cache[sid] = (d or {}).get("name") or f"(sem nome: {sid})"
        return school_cache[sid]

    # Contadores
    cause_counts = defaultdict(int)        # motivo -> N
    value_counts = defaultdict(int)        # (motivo, valor) -> N
    school_cause = defaultdict(lambda: defaultdict(int))  # escola -> motivo -> N
    rows = []
    total = 0

    cur = db.students.find(
        match,
        {"_id": 0, "id": 1, "full_name": 1, "school_id": 1, "class_id": 1, "student_series": 1},
    )
    for s in cur:
        ss = s.get("student_series")
        cid = s.get("class_id")
        cls = get_class(cid) if cid else None
        grade = (cls or {}).get("grade_level")
        cls_name = (cls or {}).get("name")

        effective = ss if (ss and str(ss).strip()) else grade
        if canonicalize_serie(effective) is not None:
            continue  # reconhecido, ok

        total += 1
        # Classifica motivo
        if ss and str(ss).strip():
            motivo = "A) student_series invalido"
            valor = str(ss).strip()
        elif not cid:
            motivo = "E) aluno SEM class_id"
            valor = "(sem class_id)"
        elif cls is None:
            motivo = "D) turma ORFA (class_id nao existe)"
            valor = f"class_id={cid}"
        elif not grade or not str(grade).strip():
            motivo = "B) turma SEM grade_level"
            valor = f"turma '{cls_name}'"
        else:
            motivo = "C) grade_level invalido"
            valor = f"{str(grade).strip()} (turma '{cls_name}')"

        cause_counts[motivo] += 1
        value_counts[(motivo, valor)] += 1
        school_cause[school_name(s.get("school_id"))][motivo] += 1
        rows.append({
            "escola": school_name(s.get("school_id")),
            "aluno": s.get("full_name") or "",
            "student_id": s.get("id") or "",
            "motivo": motivo,
            "student_series": ss or "",
            "class_id": cid or "",
            "turma": cls_name or "",
            "grade_level": grade or "",
        })

    print("=" * 80)
    print(f"DIAGNOSTICO 'SERIE NAO RECONHECIDA' — total de alunos ativos afetados: {total}")
    print("=" * 80)

    print("\n>>> RESUMO POR MOTIVO:")
    for motivo in sorted(cause_counts):
        print(f"   {motivo}: {cause_counts[motivo]} aluno(s)")

    print("\n>>> DETALHE POR VALOR (top por motivo):")
    by_motivo = defaultdict(list)
    for (motivo, valor), n in value_counts.items():
        by_motivo[motivo].append((n, valor))
    for motivo in sorted(by_motivo):
        print(f"\n   {motivo}:")
        for n, valor in sorted(by_motivo[motivo], reverse=True):
            print(f"       {n:>4} x  {valor}")

    print("\n>>> POR ESCOLA:")
    for sn in sorted(school_cause):
        tot = sum(school_cause[sn].values())
        print(f"\n   # {sn}  ({tot} aluno(s))")
        for motivo in sorted(school_cause[sn]):
            print(f"       - {motivo}: {school_cause[sn][motivo]}")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=[
                "escola", "aluno", "student_id", "motivo",
                "student_series", "class_id", "turma", "grade_level"])
            w.writeheader()
            w.writerows(rows)
        print(f"\n[OK] CSV detalhado: {args.csv}  ({len(rows)} linhas)")

    print("\nConcluido.")


if __name__ == "__main__":
    main()
