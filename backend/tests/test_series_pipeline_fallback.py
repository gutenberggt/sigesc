# -*- coding: utf-8 -*-
"""
Regressão do bug "Série não reconhecida" nos Indicadores da Rede.

Bug: alunos cujo campo `student_series` estava AUSENTE (não apenas null/"")
eram contados como "Série não reconhecida" porque o `$cond` do pipeline mantinha
o valor "missing" (já que `$ne: [missing, null]` é TRUE no MongoDB) e não caía no
fallback para `classes.grade_level`.

Fix: `vars.ss = $trim($ifNull(student_series, ""))` — coage null/missing/espaços
para "" e cai corretamente no fallback do grade_level.

Este teste replica o MESMO pipeline de `routers/students.py` (_grade_effective)
contra um banco temporário e garante que todos os casos caem no grupo certo.
"""

import os
import uuid
import pytest
from pymongo import MongoClient

from utils.serie_canonical import canonicalize_serie, UNRECOGNIZED_KEY


def _mongo_url():
    url = os.environ.get("MONGO_URL")
    if url:
        return url
    env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    for line in open(env, encoding="utf-8"):
        line = line.strip()
        if line.startswith("MONGO_URL="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


# Pipeline IDÊNTICO ao de routers/students.py (mantém os dois em sincronia).
def _series_pipeline():
    return [
        {"$match": {"status": "active"}},
        {"$lookup": {"from": "classes", "localField": "class_id",
                     "foreignField": "id", "as": "_class"}},
        {"$addFields": {
            "_grade_effective": {
                "$let": {
                    "vars": {"ss": {"$trim": {"input": {"$ifNull": ["$student_series", ""]}}}},
                    "in": {
                        "$cond": [
                            {"$ne": ["$$ss", ""]},
                            "$$ss",
                            {"$arrayElemAt": ["$_class.grade_level", 0]},
                        ]
                    }
                }
            }
        }},
        {"$group": {"_id": "$_grade_effective", "count": {"$sum": 1}}},
    ]


@pytest.fixture()
def tmp_db():
    url = _mongo_url()
    if not url:
        pytest.skip("MONGO_URL indisponível")
    client = MongoClient(url)
    name = f"test_series_pipeline_{uuid.uuid4().hex[:8]}"
    db = client[name]
    yield db
    client.drop_database(name)
    client.close()


def _series_counts(db):
    sc = {}
    for d in db.students.aggregate(_series_pipeline()):
        raw = d["_id"] or ""
        canon = canonicalize_serie(raw)
        key = canon or UNRECOGNIZED_KEY
        sc[key] = sc.get(key, 0) + d["count"]
    return sc


def test_missing_student_series_cai_no_fallback_grade_level(tmp_db):
    """student_series AUSENTE deve usar o grade_level da turma (não vira SNR)."""
    cid = "cls-mat2"
    tmp_db.classes.insert_one({"id": cid, "name": "Maternal II F", "grade_level": "Maternal II"})
    # student_series AUSENTE (campo não existe)
    tmp_db.students.insert_one({"id": "s1", "status": "active", "class_id": cid})
    sc = _series_counts(tmp_db)
    assert sc.get("MATERNAL II") == 1
    assert UNRECOGNIZED_KEY not in sc


def test_null_e_vazio_e_espacos_caem_no_fallback(tmp_db):
    cid = "cls-pre1"
    tmp_db.classes.insert_one({"id": cid, "name": "Pré I A", "grade_level": "Pré-Escola I"})
    tmp_db.students.insert_many([
        {"id": "s_null", "status": "active", "class_id": cid, "student_series": None},
        {"id": "s_empty", "status": "active", "class_id": cid, "student_series": ""},
        {"id": "s_spaces", "status": "active", "class_id": cid, "student_series": "   "},
    ])
    sc = _series_counts(tmp_db)
    assert sc.get("PRÉ I") == 3
    assert UNRECOGNIZED_KEY not in sc


def test_student_series_valido_tem_prioridade_sobre_grade_level(tmp_db):
    """Multisseriada: student_series preenchido prevalece sobre o grade_level."""
    cid = "cls-multi"
    tmp_db.classes.insert_one({"id": cid, "name": "Multi", "grade_level": "1º Ano"})
    tmp_db.students.insert_one({"id": "s2", "status": "active", "class_id": cid,
                                "student_series": "3º Ano"})
    sc = _series_counts(tmp_db)
    assert sc.get("3º ANO") == 1
    assert "1º ANO" not in sc


def test_reconciliacao_soma_bate_com_total(tmp_db):
    cid = "cls-mat1"
    tmp_db.classes.insert_one({"id": cid, "name": "Maternal I", "grade_level": "Maternal I"})
    docs = [{"id": f"a{i}", "status": "active", "class_id": cid} for i in range(5)]
    docs.append({"id": "orf", "status": "active", "class_id": "inexistente"})  # vira SNR
    tmp_db.students.insert_many(docs)
    sc = _series_counts(tmp_db)
    assert sc.get("MATERNAL I") == 5
    assert sc.get(UNRECOGNIZED_KEY) == 1
    assert sum(sc.values()) == 6
