"""
Teste de regressão — bug "Erro ao salvar notas" (POST /api/grades/batch → 403).

Causa: uma nota MIGRADA (migrated_from_class_id) de um aluno fazia o endpoint em
lote lançar 403 e ABORTAR o salvamento de TODOS os alunos seguintes (a "linha 11"
relatada pelo professor). Fix: pular apenas a nota bloqueada e salvar as demais.

Reproduz com role `professor` (não pode editar notas migradas).
"""
from __future__ import annotations

import os
import uuid
import requests
import pytest
from pathlib import Path
from pymongo import MongoClient
from dotenv import load_dotenv

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from auth_utils import hash_password  # função de hash JÁ existente no app

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://autosave-drafts.preview.emergentagent.com").rstrip("/")
PROF_EMAIL = "professor.teste@sigesc.com"
PROF_PASS = "professor123"
_db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def prof_auth():
    # Define senha de teste reaproveitando o hashing existente (não altera lógica de auth).
    _db.users.update_one({"email": PROF_EMAIL}, {"$set": {"password_hash": hash_password(PROF_PASS)}})
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": PROF_EMAIL, "password": PROF_PASS}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    s.headers.update({"Authorization": f"Bearer {d.get('access_token') or d.get('token')}",
                      "X-CSRF-Token": d.get("csrf_token") or "", "Content-Type": "application/json"})
    return s


@pytest.fixture
def seed():
    sfx = uuid.uuid4().hex[:8]
    cid, course = f"cls-{sfx}", f"crs-{sfx}"
    s_norm, s_mig = f"stu-norm-{sfx}", f"stu-mig-{sfx}"
    year = 2099  # sem calendário/config → validadores de ano/bimestre liberam
    _db.classes.insert_one({"id": cid, "school_id": f"sch-{sfx}", "academic_year": year, "course_ids": [course]})
    _db.grades.insert_many([
        {"id": f"g-norm-{sfx}", "student_id": s_norm, "class_id": cid, "course_id": course,
         "academic_year": year, "b1": None, "migrated_from_class_id": None},
        {"id": f"g-mig-{sfx}", "student_id": s_mig, "class_id": cid, "course_id": course,
         "academic_year": year, "b1": 6.0, "migrated_from_class_id": f"old-{sfx}"},  # cadeado
    ])
    ctx = {"cid": cid, "course": course, "year": year, "s_norm": s_norm, "s_mig": s_mig,
           "g_norm": f"g-norm-{sfx}", "g_mig": f"g-mig-{sfx}"}
    yield ctx
    _db.classes.delete_one({"id": cid})
    _db.grades.delete_many({"class_id": cid})


def test_batch_skips_migrated_and_saves_others(prof_auth, seed):
    ctx = seed
    # Migrada PRIMEIRO (provava o abort antigo), normal depois.
    payload = [
        {"student_id": ctx["s_mig"], "class_id": ctx["cid"], "course_id": ctx["course"],
         "academic_year": ctx["year"], "b1": 9.0},   # tentativa de alterar a migrada (bloqueada)
        {"student_id": ctx["s_norm"], "class_id": ctx["cid"], "course_id": ctx["course"],
         "academic_year": ctx["year"], "b1": 7.0},    # deve salvar
    ]
    r = prof_auth.post(f"{BASE_URL}/api/grades/batch", json=payload, timeout=30)
    assert r.status_code == 200, f"esperava 200 (sem abort), veio {r.status_code}: {r.text[:300]}"
    body = r.json()
    assert body["updated"] == 1, body
    skipped_ids = [s["student_id"] for s in body.get("skipped", [])]
    assert ctx["s_mig"] in skipped_ids, body

    # Nota normal foi salva; nota migrada permanece intacta.
    g_norm = _db.grades.find_one({"id": ctx["g_norm"]})
    g_mig = _db.grades.find_one({"id": ctx["g_mig"]})
    assert g_norm["b1"] == 7.0, g_norm
    assert g_mig["b1"] == 6.0, "nota migrada NÃO pode ser alterada por professor"
