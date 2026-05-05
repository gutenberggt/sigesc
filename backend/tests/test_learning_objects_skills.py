"""
May 2026 — Sprint B: integra Currículo no Registro de Conteúdos.
Valida que o campo `skill_codigos` é aceito, persistido e devolvido pelo CRUD.
"""
import os
import pytest
import httpx


BACKEND = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://text-hygiene-queue.preview.emergentagent.com",
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
    r = httpx.get(f"{BACKEND}/api/classes", headers=_h(token), timeout=20)
    r.raise_for_status()
    classes = r.json()
    assert len(classes) > 0, "Nenhuma turma cadastrada para testar."
    r2 = httpx.get(f"{BACKEND}/api/courses", headers=_h(token), timeout=20)
    r2.raise_for_status()
    courses = r2.json()
    assert len(courses) > 0, "Nenhum componente curricular cadastrado."
    return classes[0]["id"], courses[0]["id"]


def test_learning_object_with_skill_codigos(token, class_and_course):
    class_id, course_id = class_and_course
    payload = {
        "class_id": class_id,
        "course_id": course_id,
        "date": "2026-05-15",
        "academic_year": 2026,
        "content": "Aula sobre algoritmos",
        "number_of_classes": 1,
        "skill_codigos": ["EF03CO01", "EF04CO01"],
    }
    r = httpx.post(
        f"{BACKEND}/api/learning-objects",
        headers=_h(token),
        json=payload,
        timeout=20,
    )
    assert r.status_code in (200, 201), r.text
    created = r.json()
    assert created["skill_codigos"] == ["EF03CO01", "EF04CO01"]
    lo_id = created["id"]

    try:
        # Confirma que vem persistido no GET
        r = httpx.get(
            f"{BACKEND}/api/learning-objects?class_id={class_id}",
            headers=_h(token),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        items = r.json()
        match = next((i for i in items if i["id"] == lo_id), None)
        assert match is not None, "Registro não retornou na listagem"
        assert match["skill_codigos"] == ["EF03CO01", "EF04CO01"]

        # Atualiza removendo uma habilidade
        r = httpx.put(
            f"{BACKEND}/api/learning-objects/{lo_id}",
            headers=_h(token),
            json={"skill_codigos": ["EF03CO01"]},
            timeout=20,
        )
        assert r.status_code == 200, r.text

        # Confirma update
        r = httpx.get(
            f"{BACKEND}/api/learning-objects?class_id={class_id}",
            headers=_h(token),
            timeout=20,
        )
        match = next((i for i in r.json() if i["id"] == lo_id), None)
        assert match["skill_codigos"] == ["EF03CO01"]
    finally:
        httpx.delete(
            f"{BACKEND}/api/learning-objects/{lo_id}",
            headers=_h(token),
            timeout=20,
        )


def test_learning_object_without_skill_codigos_defaults_to_empty(token, class_and_course):
    """Retrocompatibilidade: se o cliente não enviar skill_codigos, recebe lista vazia."""
    class_id, course_id = class_and_course
    payload = {
        "class_id": class_id,
        "course_id": course_id,
        "date": "2026-05-16",
        "academic_year": 2026,
        "content": "Aula sem habilidade vinculada",
        "number_of_classes": 1,
    }
    r = httpx.post(
        f"{BACKEND}/api/learning-objects",
        headers=_h(token),
        json=payload,
        timeout=20,
    )
    assert r.status_code in (200, 201), r.text
    created = r.json()
    assert created.get("skill_codigos") == []

    httpx.delete(
        f"{BACKEND}/api/learning-objects/{created['id']}",
        headers=_h(token),
        timeout=20,
    )
