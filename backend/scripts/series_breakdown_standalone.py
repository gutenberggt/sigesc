#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STANDALONE — DETALHAMENTO de series (mesma regra do painel) p/ comparar com a tela.

Mostra, para o filtro escolhido:
  - total de alunos ATIVOS
  - contagem por SERIE canonica (codigo NOVO: canonicalizador + reconciliacao)
  - "SERIE NAO RECONHECIDA" (se houver)
  - soma e verificacao se bate com o total

Serve para PROVAR se o problema esta nos DADOS ou no CODIGO IMPLANTADO:
  - Se a soma aqui == total de ativos -> dados OK, o app implantado esta com
    codigo ANTIGO (precisa redeploy).
  - Se a soma < total -> ainda ha alunos sem serie (mostra onde).

USO (dentro do container, WORKDIR /app):
    python3 scripts/series_breakdown_standalone.py --school "Nivalda"
    python3 scripts/series_breakdown_standalone.py          # rede toda
"""

import os
import re
import sys
import argparse
import unicodedata
from collections import defaultdict

from pymongo import MongoClient

_ORDINAL_WORDS = {
    'PRIMEIRO': 1, 'PRIMEIRA': 1, 'SEGUNDO': 2, 'SEGUNDA': 2,
    'TERCEIRO': 3, 'TERCEIRA': 3, 'QUARTO': 4, 'QUARTA': 4,
    'QUINTO': 5, 'QUINTA': 5, 'SEXTO': 6, 'SEXTA': 6,
    'SETIMO': 7, 'SETIMA': 7, 'OITAVO': 8, 'OITAVA': 8,
    'NONO': 9, 'NONA': 9,
}
_ROMAN = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5}
UNRECOGNIZED_KEY = "SERIE NAO RECONHECIDA"


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
        return f"{n}a ETAPA" if n else None
    if 'ANO' in norm:
        n = _detect_number(norm, 9)
        return f"{n}o ANO" if n else None

    def _infantil_level(default_to_i=True):
        n = _detect_number(norm, 5)
        if n in (1, 2):
            return n
        if n is None and default_to_i:
            return 1
        return None

    if 'BERCARIO' in norm or 'BERCARIA' in norm:
        lvl = _infantil_level()
        return f"BERCARIO {'II' if lvl == 2 else 'I'}" if lvl else None
    if 'MATERNAL' in norm:
        lvl = _infantil_level()
        return f"MATERNAL {'II' if lvl == 2 else 'I'}" if lvl else None
    _tokens = norm.split(' ')
    is_pre = ('PRE' in _tokens or 'PRE ESCOLA' in norm
              or any(t.startswith('PREESCOL') or t.startswith('PRESCOL') for t in _tokens))
    if is_pre:
        lvl = _infantil_level()
        return f"PRE {'II' if lvl == 2 else 'I'}" if lvl else None
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
    ap.add_argument("--mongo-url")
    ap.add_argument("--db")
    args = ap.parse_args()

    mongo = args.mongo_url or _load_env("MONGO_URL")
    dbn = args.db or _load_env("DB_NAME")
    if not mongo or not dbn:
        print("[ERRO] Defina MONGO_URL/DB_NAME.")
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
        print(f"Escola: {sch.get('name')} ({sch['id']})")

    total = db.students.count_documents(match)

    cls_cache = {}

    def grade_of(cid):
        if not cid:
            return None
        if cid not in cls_cache:
            d = db.classes.find_one({"id": cid}, {"_id": 0, "grade_level": 1})
            cls_cache[cid] = (d or {}).get("grade_level")
        return cls_cache[cid]

    series_counts = defaultdict(int)
    raw_unrec = defaultdict(int)
    cur = db.students.find(match, {"_id": 0, "class_id": 1, "student_series": 1})
    for s in cur:
        ss = s.get("student_series")
        effective = ss if (ss and str(ss).strip()) else grade_of(s.get("class_id"))
        canon = canonicalize_serie(effective)
        if canon:
            series_counts[canon] += 1
        else:
            series_counts[UNRECOGNIZED_KEY] += 1
            raw_unrec[(str(effective).strip() if effective and str(effective).strip() else "(vazio)")] += 1

    print("=" * 70)
    print(f"DETALHAMENTO DE SERIES (codigo NOVO) — alunos ativos: {total}")
    print("=" * 70)
    soma = 0
    for label in sorted(series_counts):
        print(f"   {label}: {series_counts[label]}")
        soma += series_counts[label]
    print("-" * 70)
    print(f"   SOMA das series: {soma}   |   Total ativos: {total}   |   "
          f"{'BATE OK' if soma == total else 'NAO BATE (dif=%d)' % (total - soma)}")

    if raw_unrec:
        print("\n>>> Valores brutos das NAO RECONHECIDAS:")
        for v, n in sorted(raw_unrec.items(), key=lambda x: -x[1]):
            print(f"       {n:>4} x  {v}")

    print("\nConcluido.")


if __name__ == "__main__":
    main()
