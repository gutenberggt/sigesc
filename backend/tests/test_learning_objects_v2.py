"""Feb 2026 — Testa `adaptation_ids` em learning_objects (modelo multi-camadas v2)."""
import os
import httpx
import pytest
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BACKEND = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://depend-registry.preview.emergentagent.com",
).rstrip("/")
SUPER_ADMIN = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}


@pytest.fixture(scope="module")
def token():
    r = httpx.post(f"{BACKEND}/api/auth/login", json=SUPER_ADMIN, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def class_and_course(token):
    classes = httpx.get(f"{BACKEND}/api/classes", headers=_h(token), timeout=20).json()
    courses = httpx.get(f"{BACKEND}/api/courses", headers=_h(token), timeout=20).json()
    return classes[0]["id"], courses[0]["id"]


@pytest.fixture(scope="module")
def adaptation_ids(token):
    """Pega 4 adaptation_ids existentes para os testes."""
    r = httpx.get(
        f"{BACKEND}/api/curriculum/adaptations?limit=4",
        headers=_h(token), timeout=15,
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) >= 4, f"Apenas {len(items)} adaptations; rode migração antes."
    return [a["adaptation_id"] for a in items]


def test_create_with_adaptation_ids(token, class_and_course, adaptation_ids):
    class_id, course_id = class_and_course
    payload = {
        "class_id": class_id, "course_id": course_id,
        "date": "2026-05-20", "academic_year": 2026,
        "content": "Aula com adaptation_ids v2",
        "number_of_classes": 1,
        "adaptation_ids": adaptation_ids[:2],
    }
    r = httpx.post(f"{BACKEND}/api/learning-objects", headers=_h(token), json=payload, timeout=20)
    assert r.status_code in (200, 201), r.text
    created = r.json()
    assert created["adaptation_ids"] == adaptation_ids[:2]
    lo_id = created["id"]
    try:
        # Confirma update
        r = httpx.put(
            f"{BACKEND}/api/learning-objects/{lo_id}",
            headers=_h(token),
            json={"adaptation_ids": [adaptation_ids[0]]},
            timeout=20,
        )
        assert r.status_code == 200, r.text
    finally:
        httpx.delete(f"{BACKEND}/api/learning-objects/{lo_id}", headers=_h(token), timeout=20)


def test_create_rejects_more_than_3(token, class_and_course, adaptation_ids):
    class_id, course_id = class_and_course
    payload = {
        "class_id": class_id, "course_id": course_id,
        "date": "2026-05-21", "academic_year": 2026,
        "content": "Tentativa com 4 habilidades",
        "number_of_classes": 1,
        "adaptation_ids": adaptation_ids[:4],  # 4 > 3
    }
    r = httpx.post(f"{BACKEND}/api/learning-objects", headers=_h(token), json=payload, timeout=20)
    assert r.status_code == 422, r.text  # validator bate
    assert "3" in r.text.lower() or "máximo" in r.text.lower()


def test_coverage_reports_used_adaptations(token, class_and_course, adaptation_ids):
    class_id, course_id = class_and_course
    payload = {
        "class_id": class_id, "course_id": course_id,
        "date": "2026-05-22", "academic_year": 2026,
        "content": "Cobertura",
        "number_of_classes": 1,
        "adaptation_ids": [adaptation_ids[0]],
    }
    r = httpx.post(f"{BACKEND}/api/learning-objects", headers=_h(token), json=payload, timeout=20)
    assert r.status_code in (200, 201), r.text
    lo_id = r.json()["id"]
    try:
        r = httpx.get(
            f"{BACKEND}/api/curriculum/coverage?class_id={class_id}&academic_year=2026",
            headers=_h(token), timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["totals"]["covered"] >= 1
    finally:
        httpx.delete(f"{BACKEND}/api/learning-objects/{lo_id}", headers=_h(token), timeout=20)
