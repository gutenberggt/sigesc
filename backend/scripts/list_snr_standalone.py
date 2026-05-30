#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AUTOSSUFICIENTE — lista alunos ATIVOS com "Série não reconhecida"
(mesma regra do painel "Indicadores da Rede"), agrupados por ESCOLA e por
SÉRIE (nomenclatura bruta do cadastro).

Não depende de nenhum módulo interno do projeto — só de `pymongo`.

USO:
    python3 list_snr_standalone.py
    python3 list_snr_standalone.py --school "Nivalda"
    python3 list_snr_standalone.py --serie "PRÉ-ESCOLA I"
    python3 list_snr_standalone.py --csv /tmp/series_nao_reconhecidas.csv
    python3 list_snr_standalone.py --names-only

Conexão com o banco (em ordem de prioridade):
    1) variáveis de ambiente MONGO_URL e DB_NAME
    2) parâmetros --mongo-url e --db
    3) um arquivo .env encontrado em caminhos comuns
"""

import os
import re
import sys
import csv
import argparse
import unicodedata

UNRECOGNIZED = None  # canonicalize devolve None quando não reconhece

# ----------------------------------------------------------------------------
# Canonicalizador de séries (CÓPIA EXATA de utils/serie_canonical.py)
# ----------------------------------------------------------------------------
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
    s = s.replace('º', ' ').replace('°', ' ').replace('ª', ' ').replace('ᵃ', ' ')
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
    """Retorna o rótulo canônico (UPPERCASE) ou None se não reconhecido."""
    if not raw or not str(raw).strip():
        return None
    norm = _normalize(str(raw))
    if not norm:
        return None
    if norm.startswith('EJA '):
        norm = norm[4:].strip()
    if 'ETAPA' in norm:
        n = _detect_number(norm, 4)
        return f"{n}ª ETAPA" if n else None
    if 'ANO' in norm:
        n = _detect_number(norm, 9)
        return f"{n}º ANO" if n else None

    def _infantil_level(default_to_i=True):
        n = _detect_number(norm, 5)
        if n in (1, 2):
            return n
        if n is None and default_to_i:
            return 1
        return None

    if 'BERCARIO' in norm or 'BERCARIA' in norm:
        lvl = _infantil_level()
        return f"BERÇÁRIO {'II' if lvl == 2 else 'I'}" if lvl else None
    if 'MATERNAL' in norm:
        lvl = _infantil_level()
        return f"MATERNAL {'II' if lvl == 2 else 'I'}" if lvl else None
    _tokens = norm.split(' ')
    is_pre = ('PRE' in _tokens or 'PRE ESCOLA' in norm
              or any(t.startswith('PREESCOL') or t.startswith('PRESCOL') for t in _tokens))
    if is_pre:
        lvl = _infantil_level()
        return f"PRÉ {'II' if lvl == 2 else 'I'}" if lvl else None
    return None


# ----------------------------------------------------------------------------
def _resolve_conn(args):
    mongo = args.mongo_url or os.environ.get("MONGO_URL")
    db = args.db or os.environ.get("DB_NAME")
    if mongo and db:
        return mongo, db
    candidates = [
        "/app/backend/.env", "./backend/.env", "./.env",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
    ]
    for path in candidates:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    v = v.strip().strip('"').strip("'")
                    if k.strip() == "MONGO_URL" and not mongo:
                        mongo = v
                    if k.strip() == "DB_NAME" and not db:
                        db = v
            if mongo and db:
                break
    return mongo, db


def main():
    parser = argparse.ArgumentParser(description="Lista alunos com série não reconhecida.")
    parser.add_argument("--school")
    parser.add_argument("--serie")
    parser.add_argument("--mantenedora")
    parser.add_argument("--csv")
    parser.add_argument("--names-only", action="store_true")
    parser.add_argument("--mongo-url")
    parser.add_argument("--db")
    args = parser.parse_args()

    try:
        from pymongo import MongoClient
    except ImportError:
        print("[ERRO] pymongo não instalado. Rode DENTRO do container do backend,")
        print("       ou instale: pip3 install pymongo")
        sys.exit(2)

    mongo_url, db_name = _resolve_conn(args)
    if not mongo_url or not db_name:
        print("[ERRO] Não encontrei MONGO_URL/DB_NAME.")
        print("       Passe: --mongo-url \"mongodb://...\" --db \"<nome_do_banco>\"")
        print("       (Dentro do container: docker exec <id> printenv MONGO_URL DB_NAME)")
        sys.exit(2)

    client = MongoClient(mongo_url)
    db = client[db_name]

    match = {"status": "active"}
    if args.mantenedora:
        match["mantenedora_id"] = args.mantenedora
    if args.school:
        sch = db.schools.find_one({"id": args.school}, {"_id": 0, "id": 1, "name": 1})
        if not sch:
            sch = db.schools.find_one({"name": {"$regex": args.school, "$options": "i"}},
                                      {"_id": 0, "id": 1, "name": 1})
        if not sch:
            print(f"[ERRO] Escola não encontrada para: {args.school!r}")
            sys.exit(1)
        match["school_id"] = sch["id"]
        print(f"Filtrando escola: {sch.get('name')} ({sch['id']})")

    pipeline = [
        {"$match": match},
        {"$lookup": {"from": "classes", "localField": "class_id",
                     "foreignField": "id", "as": "_class"}},
        {"$addFields": {
            "_grade_effective": {"$let": {
                "vars": {"ss": "$student_series"},
                "in": {"$cond": [
                    {"$and": [{"$ne": ["$$ss", None]}, {"$ne": ["$$ss", ""]}]},
                    "$$ss", {"$arrayElemAt": ["$_class.grade_level", 0]}]}}},
            "_class_name": {"$arrayElemAt": ["$_class.name", 0]},
        }},
        {"$project": {"_id": 0, "id": 1, "full_name": 1, "cpf": 1,
                      "school_id": 1, "_grade_effective": 1, "_class_name": 1}},
    ]

    by_school = {}
    total = 0
    for s in db.students.aggregate(pipeline):
        raw = s.get("_grade_effective")
        if canonicalize_serie(raw) is not None:
            continue
        raw_label = (str(raw).strip() if raw and str(raw).strip() else "(vazio)")
        if args.serie and raw_label.lower() != args.serie.strip().lower():
            continue
        by_school.setdefault(s.get("school_id"), {}).setdefault(raw_label, []).append(s)
        total += 1

    school_names = {}
    for sid in by_school:
        doc = db.schools.find_one({"id": sid}, {"_id": 0, "name": 1})
        school_names[sid] = (doc or {}).get("name") or f"(sem nome: {sid})"

    print("=" * 78)
    print(f"ALUNOS ATIVOS COM 'SÉRIE NÃO RECONHECIDA': {total}")
    print("=" * 78)

    rows = []
    for sid in sorted(by_school, key=lambda x: school_names.get(x, "")):
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
                    print(f"       - {nome}  | CPF: {a.get('cpf') or '—'}  | Turma: {a.get('_class_name') or '—'}")
                rows.append({"escola": school_names[sid], "school_id": sid,
                             "serie_cadastrada": raw_label, "aluno": a.get("full_name") or "",
                             "cpf": a.get("cpf") or "", "turma": a.get("_class_name") or "",
                             "student_id": a.get("id") or ""})

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["escola", "school_id", "serie_cadastrada",
                                              "aluno", "cpf", "turma", "student_id"])
            w.writeheader()
            w.writerows(rows)
        print(f"\n[OK] CSV exportado: {args.csv}  ({len(rows)} linhas)")
    print("\nConcluído.")


if __name__ == "__main__":
    main()
