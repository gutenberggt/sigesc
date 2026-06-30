"""
Regressão do bug: turma MULTISSERIADA — alunos do 1º ano não apareciam em Notas.

Cenário semeado:
- Class TST_JUA_CLASS (grade_level '1º ANO', escola 220d4022-ec5e-4fb6-86fc-9233112b87b2)
- Course TST_JUA_COURSE (Língua Portuguesa)
- Students:
    * TST_JUA_S1 (Aluno Primeiro Ano A) — matrícula SEM série -> fallback grade_level '1º ANO'
    * TST_JUA_S2 (Aluno Primeiro Ano B) — matrícula SEM série -> fallback grade_level '1º ANO'
    * TST_JUA_S3 (Aluno Segundo Ano) — matrícula com série ' 2º ANO' (espaço proposital)

Endpoints sob teste:
- GET /api/grades/by-class/{class_id}/{course_id}?academic_year=2026
- GET /api/classes/{class_id}/details
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://history-rebuild-2.preview.emergentagent.com").rstrip("/")
CLASS_ID = "TST_JUA_CLASS"
COURSE_ID = "TST_JUA_COURSE"
ACADEMIC_YEAR = 2026


@pytest.fixture(scope="module")
def token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "gutenberg@sigesc.com", "password": "@Celta2007"},
        timeout=20,
    )
    assert r.status_code == 200, f"Login falhou: {r.status_code} {r.text}"
    d = r.json()
    tok = d.get("access_token") or d.get("token")
    assert tok, f"Token ausente: {d}"
    return tok


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------- Grid de Notas: fallback série -> grade_level ----------

class TestGradesByClassFallback:
    def test_grid_returns_three_students(self, headers):
        r = requests.get(
            f"{BASE_URL}/api/grades/by-class/{CLASS_ID}/{COURSE_ID}",
            params={"academic_year": ACADEMIC_YEAR},
            headers=headers,
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 3, f"Esperado 3 alunos, veio {len(data)}: {[d['student']['id'] for d in data]}"

    def test_first_year_students_use_grade_level_fallback(self, headers):
        r = requests.get(
            f"{BASE_URL}/api/grades/by-class/{CLASS_ID}/{COURSE_ID}",
            params={"academic_year": ACADEMIC_YEAR},
            headers=headers,
            timeout=20,
        )
        assert r.status_code == 200
        by_id = {row["student"]["id"]: row["student"] for row in r.json()}

        assert "TST_JUA_S1" in by_id
        assert "TST_JUA_S2" in by_id
        # Fallback: matrícula sem série -> usa class.grade_level ('1º ANO')
        assert by_id["TST_JUA_S1"]["student_series"] == "1º ANO", (
            f"S1 deveria ter fallback '1º ANO', veio {by_id['TST_JUA_S1']['student_series']!r}"
        )
        assert by_id["TST_JUA_S2"]["student_series"] == "1º ANO"

    def test_second_year_student_preserves_enrollment_series(self, headers):
        r = requests.get(
            f"{BASE_URL}/api/grades/by-class/{CLASS_ID}/{COURSE_ID}",
            params={"academic_year": ACADEMIC_YEAR},
            headers=headers,
            timeout=20,
        )
        by_id = {row["student"]["id"]: row["student"] for row in r.json()}
        assert "TST_JUA_S3" in by_id
        # Mantém a série da matrícula (com espaço proposital para validar normalização no FE)
        assert by_id["TST_JUA_S3"]["student_series"].strip() == "2º ANO", (
            f"S3 deveria ter '2º ANO' (com possível espaço), veio {by_id['TST_JUA_S3']['student_series']!r}"
        )

    def test_filter_by_first_year_series_lists_two(self, headers):
        """Simula o filtro do frontend (normalização: remove º/°/ª, acentos, espaços, lowercase)."""
        import re
        import unicodedata

        def norm(s):
            if not s:
                return ""
            s = unicodedata.normalize("NFD", str(s))
            s = "".join(c for c in s if unicodedata.category(c) != "Mn")
            s = re.sub(r"[^a-zA-Z0-9]", "", s).lower()
            return s

        r = requests.get(
            f"{BASE_URL}/api/grades/by-class/{CLASS_ID}/{COURSE_ID}",
            params={"academic_year": ACADEMIC_YEAR},
            headers=headers,
            timeout=20,
        )
        assert r.status_code == 200
        rows = r.json()
        target = norm("1º ANO")
        filtered = [row for row in rows if norm(row["student"].get("student_series")) == target]
        assert len(filtered) == 2, f"Filtro '1º ANO' deveria render 2 alunos, veio {len(filtered)}"
        ids = sorted([row["student"]["id"] for row in filtered])
        assert ids == ["TST_JUA_S1", "TST_JUA_S2"]

    def test_filter_by_second_year_series_lists_one(self, headers):
        import re
        import unicodedata

        def norm(s):
            if not s:
                return ""
            s = unicodedata.normalize("NFD", str(s))
            s = "".join(c for c in s if unicodedata.category(c) != "Mn")
            s = re.sub(r"[^a-zA-Z0-9]", "", s).lower()
            return s

        r = requests.get(
            f"{BASE_URL}/api/grades/by-class/{CLASS_ID}/{COURSE_ID}",
            params={"academic_year": ACADEMIC_YEAR},
            headers=headers,
            timeout=20,
        )
        rows = r.json()
        target = norm("2º ANO")
        filtered = [row for row in rows if norm(row["student"].get("student_series")) == target]
        assert len(filtered) == 1
        assert filtered[0]["student"]["id"] == "TST_JUA_S3"


# ---------- Class Details: dropdown de séries ----------

class TestClassDetailsDropdown:
    def test_details_lists_two_distinct_series(self, headers):
        r = requests.get(f"{BASE_URL}/api/classes/{CLASS_ID}/details", headers=headers, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        students = d.get("students") or []
        assert len(students) == 3
        series_norm = sorted({(s.get("student_series") or "").strip() for s in students})
        assert series_norm == ["1º ANO", "2º ANO"], f"Dropdown deveria listar 1º e 2º ANO, veio {series_norm}"

    def test_dropdown_matches_grid_series_set(self, headers):
        """Cross-endpoint consistency: as séries do dropdown devem casar com as séries do grid (normalizado)."""
        grid = requests.get(
            f"{BASE_URL}/api/grades/by-class/{CLASS_ID}/{COURSE_ID}",
            params={"academic_year": ACADEMIC_YEAR},
            headers=headers,
            timeout=20,
        ).json()
        details = requests.get(f"{BASE_URL}/api/classes/{CLASS_ID}/details", headers=headers, timeout=20).json()

        grid_series = {(row["student"].get("student_series") or "").strip() for row in grid}
        details_series = {(s.get("student_series") or "").strip() for s in details.get("students", [])}
        assert grid_series == details_series, (
            f"Séries divergem entre grid={grid_series} e dropdown={details_series}"
        )
