"""
Reprodução do BUG + validação do fix (regime POR COMPONENTE) com seed isolado.

Cenário (school_id dedicado → isolamento total do resultado do endpoint):
  - 1 turma `fundamental_anos_finais` (regime by_component)
  - Professor T leciona SOMENTE o componente A (grade: 1 aula/semana, segundas)
  - Componente A: 4 frequências lançadas (2 no prazo, 2 atrasadas) + 2 conteúdos
  - Componente B (de OUTRO professor, mesma turma): 120 frequências

Antes do fix, o numerador somava TODOS os lançamentos da turma (A+B=124)
contra um denominador "1 por turma/dia" (~110) → estourava e cravava 100%.
Depois do fix, o professor T deve ficar bem abaixo de 100% e
diario_real_pct > diario_pct (por causa dos 2 lançamentos atrasados).
"""
import os
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

_fe = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _fe["REACT_APP_BACKEND_URL"]).rstrip("/")
_be = dotenv_values("/app/backend/.env")

YEAR = 2026
SCHOOL = "TEST_PERF_SCHOOL"
MANT = "TEST_PERF_MANT"
CLASS = "TEST_PERF_CLASS_FINAIS"
COURSE_A = "TEST_PERF_COURSE_A"
COURSE_B = "TEST_PERF_COURSE_B"
TEACHER = "TEST_PERF_TEACHER_A"
TEACHER_B = "TEST_PERF_TEACHER_B"
MARK = {"test_perf_fixture": True}

A_DATES = ["2026-02-02", "2026-02-09", "2026-03-02", "2026-03-09"]  # segundas-feiras
ON_TIME = A_DATES[:2]
N_CONTENT_A = 2

PERF = f"{BASE_URL}/api/analytics/teachers/performance"


def _iso(d, plus_days):
    return (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=plus_days)).replace(
        tzinfo=timezone.utc).isoformat()


@pytest.fixture(scope="module")
def db():
    return MongoClient(_be["MONGO_URL"])[_be["DB_NAME"]]


def _purge(db):
    for coll in ("schools", "classes", "staff", "teacher_assignments",
                 "teacher_class_assignments", "attendance", "learning_objects"):
        db[coll].delete_many(MARK)


@pytest.fixture(scope="module", autouse=True)
def seed(db):
    _purge(db)
    now = datetime.now(timezone.utc).isoformat()
    db.schools.insert_one({**MARK, "id": SCHOOL, "name": "TEST PERF SCHOOL",
                           "mantenedora_id": MANT, "status": "active",
                           "anos_letivos_ativos": [YEAR], "created_at": now})
    db.classes.insert_one({**MARK, "id": CLASS, "name": "TEST 6 ANO PERF",
                           "education_level": "fundamental_anos_finais",
                           "grade_level": "6", "school_id": SCHOOL,
                           "mantenedora_id": MANT, "academic_year": YEAR,
                           "shift": "morning", "created_at": now})
    for tid, name in ((TEACHER, "TEST PERF Professor A"), (TEACHER_B, "TEST PERF Professor B")):
        db.staff.insert_one({**MARK, "id": tid, "nome": name, "school_id": SCHOOL,
                            "mantenedora_id": MANT, "created_at": now})
    # Alocações: professor A -> componente A; professor B -> componente B
    db.teacher_assignments.insert_many([
        {**MARK, "id": "TEST_PERF_TA_A", "staff_id": TEACHER, "class_id": CLASS,
         "course_id": COURSE_A, "status": "ativo", "academic_year": YEAR,
         "school_id": SCHOOL, "mantenedora_id": MANT, "created_at": now},
        {**MARK, "id": "TEST_PERF_TA_B", "staff_id": TEACHER_B, "class_id": CLASS,
         "course_id": COURSE_B, "status": "ativo", "academic_year": YEAR,
         "school_id": SCHOOL, "mantenedora_id": MANT, "created_at": now},
    ])
    # Grade horária: A = 1 aula/semana (segunda); B = 5 aulas/semana
    db.teacher_class_assignments.insert_many([
        {**MARK, "id": "TEST_PERF_TCA_A", "teacher_id": TEACHER, "class_id": CLASS,
         "school_id": SCHOOL, "component_id": COURSE_A, "shift": "morning",
         "weekly_slots": [{"weekday": 1, "aula_numero": 1}],
         "valid_from": f"{YEAR}-02-01", "valid_until": None, "deleted": False},
        {**MARK, "id": "TEST_PERF_TCA_B", "teacher_id": TEACHER_B, "class_id": CLASS,
         "school_id": SCHOOL, "component_id": COURSE_B, "shift": "morning",
         "weekly_slots": [{"weekday": w, "aula_numero": 2} for w in (1, 2, 3, 4, 5)],
         "valid_from": f"{YEAR}-02-01", "valid_until": None, "deleted": False},
    ])
    # Frequência componente A: 2 no prazo (+1 dia), 2 atrasadas (+10 dias)
    att = []
    for d in A_DATES:
        att.append({**MARK, "id": f"TEST_PERF_ATT_A_{d}", "class_id": CLASS,
                    "course_id": COURSE_A, "date": d, "academic_year": YEAR,
                    "attendance_type": "by_course", "aula_numero": 1, "version": 1,
                    "records": [], "created_at": _iso(d, 1 if d in ON_TIME else 10)})
    # Frequência componente B (outro professor): 120 lançamentos "perfeitos"
    base = datetime(YEAR, 2, 2)
    for i in range(120):
        d = (base + timedelta(days=i)).strftime("%Y-%m-%d")
        att.append({**MARK, "id": f"TEST_PERF_ATT_B_{i}", "class_id": CLASS,
                    "course_id": COURSE_B, "date": d, "academic_year": YEAR,
                    "attendance_type": "by_course", "aula_numero": 2, "version": 1,
                    "records": [], "created_at": _iso(d, 0)})
    db.attendance.insert_many(att)
    # Conteúdo: 2 para A, 200 para B
    lo = [{**MARK, "id": f"TEST_PERF_LO_A_{i}", "class_id": CLASS, "course_id": COURSE_A,
           "academic_year": YEAR, "date": A_DATES[i], "created_at": now}
          for i in range(N_CONTENT_A)]
    lo += [{**MARK, "id": f"TEST_PERF_LO_B_{i}", "class_id": CLASS, "course_id": COURSE_B,
            "academic_year": YEAR,
            "date": (base + timedelta(days=i)).strftime("%Y-%m-%d"), "created_at": now}
           for i in range(120)]
    db.learning_objects.insert_many(lo)
    yield
    _purge(db)


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "gutenberg@sigesc.com", "password": "@Celta2007"}, timeout=60)
    assert r.status_code == 200, r.text[:300]
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


@pytest.fixture(scope="module")
def rows(client, seed):
    r = client.get(PERF, params={"academic_year": YEAR, "school_id": SCHOOL, "limit": 50},
                   timeout=240)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:500]}"
    data = r.json()["data"]
    print("SEEDED RESULT:", data)
    return {t["teacher_id"]: t for t in data}


class TestByComponentFix:
    def test_both_teachers_returned(self, rows):
        assert set(rows) == {TEACHER, TEACHER_B}, rows.keys()

    def test_no_inflation_for_low_coverage_teacher(self, rows):
        t = rows[TEACHER]
        assert t["sla_freq"] < 60, f"sla_freq inflado: {t}"
        assert t["diario_real_pct"] < 100 and t["diario_pct"] < 100, t
        # 4 lançamentos contra ~22 segundas previstas → cobertura ~18%
        assert 0 < t["sla_freq"] <= 25, t

    def test_invariant_strict_when_late_launches(self, rows):
        t = rows[TEACHER]
        assert t["diario_real_pct"] > t["diario_pct"], (
            f"cobertura pura deveria exceder o SLA (2 de 4 atrasados): {t}")

    def test_coverage_is_double_the_sla(self, rows):
        """2 de 4 no prazo → freq_coverage ≈ 2 × sla_freq (derivado das colunas)."""
        t = rows[TEACHER]
        freq_coverage = t["sla_freq"] + (t["diario_real_pct"] - t["diario_pct"]) / 0.4
        assert abs(freq_coverage - 2 * t["sla_freq"]) <= 1.0, (
            f"freq_coverage derivado={freq_coverage} vs 2×sla={2 * t['sla_freq']} ({t})")

    def test_other_teacher_component_does_not_leak(self, rows):
        """Professor B tem 120 lançamentos; isso não pode elevar o professor A."""
        a, b = rows[TEACHER], rows[TEACHER_B]
        assert b["sla_freq"] > a["sla_freq"], (a, b)
        assert a["sla_conteudo"] <= 25, a

    def test_pdf_with_seed(self, client, seed):
        r = client.get(f"{PERF}/pdf", params={"academic_year": YEAR, "school_id": SCHOOL},
                       timeout=240)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        assert r.content[:4] == b"%PDF"
