"""
E2E HTTP tests for Phase 2 Diary endpoint canônico via PUBLIC URL.
Exercita autenticação real (super_admin), CSRF, X-Mantenedora-Id e
valida shape do payload + integração GET grades/by-class e GET attendance/by-class.
"""
from __future__ import annotations

import os
import requests
import pytest

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "https://legacy-bridge-compat.preview.emergentagent.com"
EMAIL = "gutenberg@sigesc.com"
PASSWORD = "@Celta2007"
TENANT = "fix_mant_v1"
CLASS_ID = "fix_cl_v1"
COURSE_MAT = "fix_co_mat_v1"
COURSE_PT = "fix_co_pt_v1"
YEAR = 2026


@pytest.fixture(scope="module")
def auth():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    token = data.get("access_token") or data.get("token")
    csrf = data.get("csrf_token")
    assert token, f"no token in login response: {data.keys()}"
    s.headers.update({
        "Authorization": f"Bearer {token}",
        "X-CSRF-Token": csrf or "",
        "X-Mantenedora-Id": TENANT,
        "Content-Type": "application/json",
    })
    return s


def test_diary_canonical_endpoint_shape(auth):
    r = auth.get(f"{BASE_URL}/api/diary/class/{CLASS_ID}/course/{COURSE_MAT}?academic_year={YEAR}", timeout=30)
    assert r.status_code == 200, f"{r.status_code} {r.text[:500]}"
    data = r.json()
    assert data.get("contract_version") == 1
    assert "items" in data and isinstance(data["items"], list)
    meta = data.get("meta") or data.get("summary") or {}
    # Owner exigência: meta com contadores
    assert meta.get("regular_count") == 9, f"meta={meta}"
    assert meta.get("dependency_count") == 1
    assert meta.get("total") == 10
    assert meta.get("has_dependencies") is True
    assert meta.get("dependency_ratio_pct") == 10.0
    # Sem divisor fake no array items
    for it in data["items"]:
        assert "is_divider" not in it
    # Heitor é a única dep
    deps = [it for it in data["items"] if it["is_dependency"]]
    assert len(deps) == 1
    assert deps[0]["student_id"] == "fix_stu_heitor"
    assert deps[0]["dependency_id"] == "fix_dep_heitor_mat"
    assert deps[0]["display_label"] == "Dependência"
    # Regulares vêm primeiro
    first_dep_idx = next(i for i, it in enumerate(data["items"]) if it["is_dependency"])
    for it in data["items"][:first_dep_idx]:
        assert it["is_dependency"] is False


def test_grades_by_class_includes_dependency(auth):
    r = auth.get(f"{BASE_URL}/api/grades/by-class/{CLASS_ID}/{COURSE_MAT}?academic_year={YEAR}", timeout=30)
    assert r.status_code == 200, f"{r.status_code} {r.text[:500]}"
    data = r.json()
    # endpoint retorna LISTA direta de {student, grade}
    assert isinstance(data, list)
    heitor = next((row for row in data if (row.get("student") or {}).get("id") == "fix_stu_heitor"), None)
    assert heitor is not None
    student = heitor["student"]
    assert student.get("is_dependency") is True
    assert student.get("dependency_id") == "fix_dep_heitor_mat"
    # Heitor (dep) deve vir DEPOIS dos regulares
    heitor_idx = next(i for i, r2 in enumerate(data) if (r2.get("student") or {}).get("id") == "fix_stu_heitor")
    for row in data[:heitor_idx]:
        assert (row.get("student") or {}).get("is_dependency") in (False, None)


def test_attendance_by_class_includes_dependency(auth):
    r = auth.get(f"{BASE_URL}/api/attendance/by-class/{CLASS_ID}/2026-03-15?course_id={COURSE_MAT}", timeout=30)
    assert r.status_code == 200, f"{r.status_code} {r.text[:500]}"
    data = r.json()
    students = data.get("students") or []
    assert isinstance(students, list) and len(students) > 0
    heitor = next((s for s in students if s.get("id") == "fix_stu_heitor"), None)
    assert heitor is not None, f"Heitor não em attendance/by-class. ids={[s.get('id') for s in students]}"
    assert heitor.get("is_dependency") is True
    assert heitor.get("dependency_id") == "fix_dep_heitor_mat"


def test_observability_snapshot_has_dep_metrics(auth):
    r = auth.get(f"{BASE_URL}/api/admin/observability/diary", timeout=30)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    snap = r.json()
    # Aceita snapshot direto ou wrapping
    payload = snap.get("snapshot") or snap
    # campos novos exigidos
    assert "avg_dependency_ratio_pct" in payload, f"keys={list(payload.keys())}"
    assert "excess_dep_loads" in payload, f"keys={list(payload.keys())}"


# ---------- Anti-spoof on POST /api/grades ----------

def _grade_payload(student_id, dep_id, course_id=COURSE_MAT):
    return {
        "student_id": student_id,
        "class_id": CLASS_ID,
        "course_id": course_id,
        "academic_year": YEAR,
        "bimester": 1,
        "grade_type": "prova",
        "grade_value": 7.0,
        "dependency_id": dep_id,
    }


def test_post_grades_dep_valida_aceita(auth):
    r = auth.post(f"{BASE_URL}/api/grades", json=_grade_payload("fix_stu_heitor", "fix_dep_heitor_mat"), timeout=30)
    # aceita 200 ou 201; pode retornar 409 se já existe → ok também
    assert r.status_code in (200, 201, 409), f"{r.status_code} {r.text[:400]}"


def test_post_grades_student_mismatch_422(auth):
    r = auth.post(f"{BASE_URL}/api/grades", json=_grade_payload("fix_stu_felipe", "fix_dep_heitor_mat"), timeout=30)
    assert r.status_code == 422, f"{r.status_code} {r.text[:300]}"
    body = r.json()
    detail = body.get("detail") or {}
    if isinstance(detail, list):
        detail = detail[0] if detail else {}
    code = (detail.get("code") if isinstance(detail, dict) else None) or body.get("code")
    assert code == "DEPENDENCY_COHERENCE_STUDENT_MISMATCH", f"body={body}"


def test_post_grades_course_mismatch_422(auth):
    r = auth.post(f"{BASE_URL}/api/grades", json=_grade_payload("fix_stu_heitor", "fix_dep_heitor_mat", course_id=COURSE_PT), timeout=30)
    assert r.status_code == 422, f"{r.status_code} {r.text[:300]}"
    body = r.json()
    detail = body.get("detail") or {}
    if isinstance(detail, list):
        detail = detail[0] if detail else {}
    code = (detail.get("code") if isinstance(detail, dict) else None) or body.get("code")
    assert code == "DEPENDENCY_COHERENCE_COURSE_MISMATCH", f"body={body}"


def test_post_grades_dep_inativa_422(auth):
    # Ivo dep cancelada
    payload = _grade_payload("fix_stu_ivo", "fix_dep_ivo_cancelled")
    r = auth.post(f"{BASE_URL}/api/grades", json=payload, timeout=30)
    assert r.status_code == 422, f"{r.status_code} {r.text[:300]}"
    body = r.json()
    detail = body.get("detail") or {}
    if isinstance(detail, list):
        detail = detail[0] if detail else {}
    code = (detail.get("code") if isinstance(detail, dict) else None) or body.get("code")
    assert code == "DEPENDENCY_COHERENCE_INACTIVE", f"body={body}"


def test_post_grades_dep_inexistente_422(auth):
    payload = _grade_payload("fix_stu_heitor", "DOES_NOT_EXIST")
    r = auth.post(f"{BASE_URL}/api/grades", json=payload, timeout=30)
    assert r.status_code == 422, f"{r.status_code} {r.text[:300]}"
    body = r.json()
    detail = body.get("detail") or {}
    if isinstance(detail, list):
        detail = detail[0] if detail else {}
    code = (detail.get("code") if isinstance(detail, dict) else None) or body.get("code")
    assert code == "DEPENDENCY_COHERENCE_NOT_FOUND", f"body={body}"
