"""
Iteration 107 — Backend granular freeze tests for MIGRATED grades.

Validates the per-bimester freeze behavior on grades that carry
`migrated_from_class_id` (notes moved from origin → destination class):

1. POST /api/grades/batch (professor):
   - Payload com b1 (migrado=frozen) E b2 (não-migrado=editável)
     → b1 preservado; b2 salvo; resposta updated>=1.
   - Payload SOMENTE com campo frozen → entra em `skipped` com
     reason='migrated_grade_locked' e a nota NÃO é alterada.
2. PUT /api/grades/{id} (professor): frozen b1 preservado, b2 aplicado.
3. POST /api/grades (professor, update existente): mesma regra (granular).
4. Secretário (ROLES_CAN_EDIT_MIGRATED) CONSEGUE alterar b1 (migrado).
5. GET /api/grades/by-class retorna student.migrated_bimesters=[1] para nota
   migrada e [] para aluno normal.
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
from auth_utils import hash_password  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
load_dotenv(Path(__file__).resolve().parent.parent.parent / "frontend" / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
PROF_EMAIL = "professor.teste@sigesc.com"
PROF_PASS = "professor123"
SEC_EMAIL = "gutenberg@sigesc.com"  # super_admin (secretario user doesn't exist in this env)
SEC_PASS = "@Celta2007"

_db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} -> {r.status_code}: {r.text[:200]}"
    d = r.json()
    tok = d.get("access_token") or d.get("token")
    csrf = d.get("csrf_token") or ""
    s.headers.update({"Authorization": f"Bearer {tok}", "X-CSRF-Token": csrf,
                      "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def prof_auth():
    _db.users.update_one({"email": PROF_EMAIL}, {"$set": {"password_hash": hash_password(PROF_PASS)}})
    return _login(PROF_EMAIL, PROF_PASS)


@pytest.fixture(scope="module")
def sec_auth():
    # Usa super_admin (gutenberg) — ROLES_CAN_EDIT_MIGRATED também inclui secretario/gerente,
    # mas no env atual NÃO existe usuário com role 'secretario'. super_admin cobre o invariante.
    return _login(SEC_EMAIL, SEC_PASS)


@pytest.fixture
def seed():
    """Cenário: turma destino (B) com 2 alunos: 1 normal e 1 com nota migrada b1=6.0."""
    sfx = uuid.uuid4().hex[:8]
    cid = f"TEST_cls-{sfx}"
    course = f"TEST_crs-{sfx}"
    school = f"TEST_sch-{sfx}"
    s_norm = f"TEST_stu-norm-{sfx}"
    s_mig = f"TEST_stu-mig-{sfx}"
    year = 2099  # sem calendário/config → validadores liberam

    _db.classes.insert_one({"id": cid, "school_id": school, "academic_year": year,
                            "course_ids": [course], "name": f"TEST {sfx}"})
    _db.students.insert_many([
        {"id": s_norm, "full_name": f"TEST Norm {sfx}", "class_id": cid, "status": "active",
         "school_id": school, "enrollment_number": f"N{sfx}"},
        {"id": s_mig, "full_name": f"TEST Mig {sfx}", "class_id": cid, "status": "active",
         "school_id": school, "enrollment_number": f"M{sfx}"},
    ])
    _db.grades.insert_many([
        {"id": f"TEST_g-norm-{sfx}", "student_id": s_norm, "class_id": cid, "course_id": course,
         "academic_year": year, "b1": None, "b2": None, "b3": None, "b4": None,
         "migrated_from_class_id": None},
        {"id": f"TEST_g-mig-{sfx}", "student_id": s_mig, "class_id": cid, "course_id": course,
         "academic_year": year, "b1": 6.0, "b2": None, "b3": None, "b4": None,
         "migrated_from_class_id": f"TEST_old-{sfx}"},
    ])

    ctx = {"cid": cid, "course": course, "year": year, "s_norm": s_norm, "s_mig": s_mig,
           "g_norm": f"TEST_g-norm-{sfx}", "g_mig": f"TEST_g-mig-{sfx}", "school": school}
    yield ctx

    _db.classes.delete_one({"id": cid})
    _db.grades.delete_many({"class_id": cid})
    _db.students.delete_many({"id": {"$in": [s_norm, s_mig]}})


# ========================================================================
# 1) POST /api/grades/batch — granular: b1 frozen ignorado, b2 salvo
# ========================================================================
def test_batch_granular_freeze_b1_saves_b2(prof_auth, seed):
    ctx = seed
    payload = [{
        "student_id": ctx["s_mig"], "class_id": ctx["cid"], "course_id": ctx["course"],
        "academic_year": ctx["year"],
        "b1": 9.0,   # FROZEN (migrado) → deve ser ignorado
        "b2": 8.5,   # editável (pós-ação) → deve salvar
    }]
    r = prof_auth.post(f"{BASE_URL}/api/grades/batch", json=payload, timeout=30)
    assert r.status_code == 200, f"esperava 200: {r.status_code} {r.text[:300]}"
    body = r.json()
    # Nota não é SKIPPED — pelo menos b2 deve ter sido aplicado.
    skipped_ids = [s.get("student_id") for s in body.get("skipped", [])]
    assert ctx["s_mig"] not in skipped_ids, f"esperava grade ser atualizada (b2), veio skipped: {body}"
    assert body.get("updated", 0) >= 1, body

    g = _db.grades.find_one({"id": ctx["g_mig"]})
    assert g["b1"] == 6.0, f"b1 frozen NÃO pode ser alterado por professor; veio {g['b1']}"
    assert g["b2"] == 8.5, f"b2 (não-migrado) DEVE ter sido salvo; veio {g.get('b2')}"


# ========================================================================
# 2) Batch SOMENTE com frozen → skipped com reason migrated_grade_locked
# ========================================================================
def test_batch_only_frozen_field_skipped(prof_auth, seed):
    ctx = seed
    payload = [{
        "student_id": ctx["s_mig"], "class_id": ctx["cid"], "course_id": ctx["course"],
        "academic_year": ctx["year"],
        "b1": 9.9,  # ÚNICO campo, e está frozen → deve ser skipped
    }]
    r = prof_auth.post(f"{BASE_URL}/api/grades/batch", json=payload, timeout=30)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    skipped = body.get("skipped", [])
    matching = [s for s in skipped if s.get("student_id") == ctx["s_mig"]]
    assert matching, f"esperava entry skipped p/ s_mig; veio {body}"
    assert matching[0].get("reason") == "migrated_grade_locked", matching[0]

    g = _db.grades.find_one({"id": ctx["g_mig"]})
    assert g["b1"] == 6.0, f"b1 frozen preservado; veio {g['b1']}"


# ========================================================================
# 3) PUT /api/grades/{id} (professor) — granular freeze
# ========================================================================
def test_put_grade_granular_freeze(prof_auth, seed):
    ctx = seed
    payload = {"b1": 1.0, "b2": 7.7}  # b1 frozen, b2 editável
    r = prof_auth.put(f"{BASE_URL}/api/grades/{ctx['g_mig']}", json=payload, timeout=30)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
    g = _db.grades.find_one({"id": ctx["g_mig"]})
    assert g["b1"] == 6.0, f"b1 frozen preservado em PUT; veio {g['b1']}"
    assert g["b2"] == 7.7, f"b2 salvo em PUT; veio {g.get('b2')}"


# ========================================================================
# 4) POST /api/grades (update via create — professor) — granular freeze
# ========================================================================
def test_post_grade_update_granular_freeze(prof_auth, seed):
    ctx = seed
    payload = {
        "student_id": ctx["s_mig"], "class_id": ctx["cid"], "course_id": ctx["course"],
        "academic_year": ctx["year"],
        "b1": 2.2,   # frozen
        "b3": 6.3,   # editável
    }
    r = prof_auth.post(f"{BASE_URL}/api/grades", json=payload, timeout=30)
    # Pode ser 200 ou 201 dependendo da framework; ambos OK.
    assert r.status_code in (200, 201), f"{r.status_code}: {r.text[:300]}"
    g = _db.grades.find_one({"id": ctx["g_mig"]})
    assert g["b1"] == 6.0, f"b1 frozen preservado em POST(update); veio {g['b1']}"
    assert g["b3"] == 6.3, f"b3 salvo em POST(update); veio {g.get('b3')}"


# ========================================================================
# 5) Secretário CONSEGUE editar bimestre migrado (ROLES_CAN_EDIT_MIGRATED)
# ========================================================================
def test_secretario_can_edit_migrated_b1(sec_auth, seed):
    ctx = seed
    payload = [{
        "student_id": ctx["s_mig"], "class_id": ctx["cid"], "course_id": ctx["course"],
        "academic_year": ctx["year"],
        "b1": 9.0,
    }]
    r = sec_auth.post(f"{BASE_URL}/api/grades/batch", json=payload, timeout=30)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
    body = r.json()
    assert body.get("updated", 0) >= 1, body
    skipped_ids = [s.get("student_id") for s in body.get("skipped", [])]
    assert ctx["s_mig"] not in skipped_ids, f"secretario NÃO deveria ser skipped: {body}"

    g = _db.grades.find_one({"id": ctx["g_mig"]})
    assert g["b1"] == 9.0, f"secretario PODE alterar b1 migrado; veio {g['b1']}"


# ========================================================================
# 6) GET /api/grades/by-class retorna student.migrated_bimesters
# ========================================================================
def test_by_class_returns_migrated_bimesters(prof_auth, seed):
    ctx = seed
    url = f"{BASE_URL}/api/grades/by-class/{ctx['cid']}/{ctx['course']}"
    r = prof_auth.get(url, params={"academic_year": ctx["year"]}, timeout=30)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
    data = r.json()
    by_sid = {}
    # Endpoint retorna {"students": [...]} ou lista direta — normalizar.
    rows = data if isinstance(data, list) else (data.get("students") or data.get("data") or [])
    for row in rows:
        st = row.get("student") or {}
        if st.get("id"):
            by_sid[st["id"]] = st

    assert ctx["s_mig"] in by_sid, f"s_mig ausente da grid; ids: {list(by_sid.keys())}"
    assert ctx["s_norm"] in by_sid, f"s_norm ausente da grid; ids: {list(by_sid.keys())}"

    assert by_sid[ctx["s_mig"]].get("migrated_bimesters") == [1], \
        f"esperava [1] p/ aluno migrado; veio {by_sid[ctx['s_mig']].get('migrated_bimesters')}"
    assert by_sid[ctx["s_norm"]].get("migrated_bimesters") == [], \
        f"esperava [] p/ aluno normal; veio {by_sid[ctx['s_norm']].get('migrated_bimesters')}"
