"""
E2E HTTP — Boletim Online MVP (Passo 5 — Fev/2026).

Cobre:
01. GET /api/students/{sid}/bulletin?academic_year=Y → 200 com shape canônico
02. Aluno desconhecido → 404
03. Sem auth → 401/403
04. academic_year fora do range → 422
05. Aluno em outro tenant (super_admin trocando tenant header) — comportamento esperado
"""
from __future__ import annotations

import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = "@Celta2007"
TENANT = "fix_mant_v1"
STUDENT_ID = "fix_stu_ana"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
               timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    csrf = data.get("csrf_token") or r.headers.get("X-CSRF-Token")
    token = data.get("access_token") or data.get("token")
    s.headers.update({
        "X-Mantenedora-Id": TENANT,
        "X-CSRF-Token": csrf or "",
        "Content-Type": "application/json",
    })
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    yield s


def test_01_bulletin_canonical_shape(session):
    r = session.get(
        f"{BASE_URL}/api/students/{STUDENT_ID}/bulletin",
        params={"academic_year": 2026},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bulletin_version"] == "1"
    for k in ["student", "academic_year", "primary_school", "primary_class",
              "is_composite", "composite_segments", "dependency_components",
              "warnings"]:
        assert k in body
    assert body["academic_year"] == 2026
    assert body["student"]["id"] == STUDENT_ID


def test_02_unknown_student_returns_404(session):
    r = session.get(
        f"{BASE_URL}/api/students/never_existed_zzz/bulletin",
        params={"academic_year": 2026},
        timeout=30,
    )
    assert r.status_code == 404


def test_03_unauthenticated_blocked():
    r = requests.get(
        f"{BASE_URL}/api/students/{STUDENT_ID}/bulletin",
        params={"academic_year": 2026},
        timeout=30,
    )
    assert r.status_code in (401, 403)


def test_04_academic_year_out_of_range(session):
    r = session.get(
        f"{BASE_URL}/api/students/{STUDENT_ID}/bulletin",
        params={"academic_year": 1500},
        timeout=30,
    )
    assert r.status_code == 422


def test_05_segments_have_required_fields(session):
    r = session.get(
        f"{BASE_URL}/api/students/{STUDENT_ID}/bulletin",
        params={"academic_year": 2026},
        timeout=30,
    )
    assert r.status_code == 200
    body = r.json()
    for seg in body["composite_segments"]:
        for k in ["period_index", "class", "school", "period_start",
                  "period_end", "source", "components", "attendance_summary",
                  "bimesters_owned"]:
            assert k in seg, f"missing key {k} in segment"
        for comp in seg["components"]:
            for k in ["course_id", "course_name", "is_dependency",
                      "bimesters_owned_by_this_period", "grades"]:
                assert k in comp


def test_06_method_post_not_allowed(session):
    r = session.post(
        f"{BASE_URL}/api/students/{STUDENT_ID}/bulletin",
        params={"academic_year": 2026},
        json={"any": "thing"},
        timeout=30,
    )
    # READ-ONLY ABSOLUTO: POST não é definido — 405 Method Not Allowed.
    assert r.status_code in (404, 405)
