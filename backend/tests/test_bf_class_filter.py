"""Backend tests for BolsaFamilia class_id filter (Fev/2026)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://school-integrity-fix.preview.emergentagent.com").rstrip("/")

SCHOOL_ID = "220d4022-ec5e-4fb6-86fc-9233112b87b2"
CLASS_2ANO = "9f71ed93-c55f-44d2-87a9-c8567ccddd6a"      # 2 Ano - 1 aluno
CLASS_6ANO = "3da4e569-6522-432c-9b42-1e344a2f0c69"      # 6 ANO A - 2 alunos
CLASS_9ANO = "e78fac69-50db-43e4-aee4-5c8ddee9334c"      # 9 ano - 1 aluno
CLASS_AEE = "73844918-60b1-4c62-b6cb-a21a35cc49c1"        # AEE - 0 BF

ADMIN = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


# -- /students endpoint ----------------------------------------------------
def test_students_no_class_filter_returns_all_bf(headers):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/students",
        params={"school_id": SCHOOL_ID, "academic_year": 2026},
        headers=headers,
        timeout=30,
    )
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert "students" in data
    assert data["total"] == len(data["students"])
    assert data["total"] >= 4, f"expected >= 4 BF students, got {data['total']}"


def test_students_with_class_2ano_returns_1(headers):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/students",
        params={"school_id": SCHOOL_ID, "academic_year": 2026, "class_id": CLASS_2ANO},
        headers=headers,
        timeout=30,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1, f"2 Ano expected 1 BF student, got {data['total']}"


def test_students_with_class_6ano_returns_2(headers):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/students",
        params={"school_id": SCHOOL_ID, "academic_year": 2026, "class_id": CLASS_6ANO},
        headers=headers,
        timeout=30,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2, f"6 ANO A expected 2 BF students, got {data['total']}"


def test_students_with_class_aee_returns_0(headers):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/students",
        params={"school_id": SCHOOL_ID, "academic_year": 2026, "class_id": CLASS_AEE},
        headers=headers,
        timeout=30,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["students"] == []


# -- /pdf endpoint ---------------------------------------------------------
def test_pdf_no_class_returns_200_all(headers):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/pdf/{SCHOOL_ID}",
        params={"academic_year": 2026, "month_start": 2, "month_end": 3},
        headers=headers,
        timeout=60,
    )
    assert r.status_code == 200, r.text[:300]
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert len(r.content) > 1000


def test_pdf_with_class_6ano_returns_200(headers):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/pdf/{SCHOOL_ID}",
        params={"academic_year": 2026, "month_start": 2, "month_end": 3, "class_id": CLASS_6ANO},
        headers=headers,
        timeout=60,
    )
    assert r.status_code == 200, r.text[:300]
    assert r.headers.get("content-type", "").startswith("application/pdf")


def test_pdf_with_class_aee_returns_404(headers):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/pdf/{SCHOOL_ID}",
        params={"academic_year": 2026, "month_start": 2, "month_end": 3, "class_id": CLASS_AEE},
        headers=headers,
        timeout=60,
    )
    assert r.status_code == 404, r.text[:300]
    detail = r.json().get("detail", "")
    assert "turma" in detail.lower(), f"unexpected detail: {detail}"


def test_pdf_size_differs_with_and_without_filter(headers):
    r_all = requests.get(
        f"{BASE_URL}/api/bolsa-familia/pdf/{SCHOOL_ID}",
        params={"academic_year": 2026, "month_start": 2, "month_end": 3},
        headers=headers, timeout=60,
    )
    r_one = requests.get(
        f"{BASE_URL}/api/bolsa-familia/pdf/{SCHOOL_ID}",
        params={"academic_year": 2026, "month_start": 2, "month_end": 3, "class_id": CLASS_2ANO},
        headers=headers, timeout=60,
    )
    assert r_all.status_code == 200 and r_one.status_code == 200
    # PDF com 4 alunos deve ser maior do que PDF com 1 aluno
    assert len(r_all.content) > len(r_one.content)
