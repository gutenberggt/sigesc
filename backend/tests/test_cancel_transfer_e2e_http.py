"""
E2E test — Cancelar Transferência (Iter 76).

Cenário (Ema): aluno é transferido (status='transferred') e, em seguida, a
transferência é cancelada. O aluno deve voltar para a MESMA TURMA como se
nada tivesse ocorrido, sem bloqueios.

Cobre:
  - POST /api/students/{id}/cancel-transfer com class_id no body → 200
  - Pós-cancelamento: student.status='active', class_id e school_id restaurados
  - Enrollment original revertido de 'transferred' para 'active'
  - Histórico tem entrada `transferencia_cancelada` (auditoria)
  - Cancel para aluno NÃO transferido → 400
  - Cancel sem matrícula transferida correspondente → 404
"""
from __future__ import annotations

import os
import uuid
import requests
import pytest

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "https://autosave-drafts.preview.emergentagent.com")
    .rstrip("/")
)
EMAIL = "gutenberg@sigesc.com"
PASSWORD = "@Celta2007"


@pytest.fixture(scope="module")
def auth():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200
    data = r.json()
    token = data.get("access_token") or data.get("token")
    csrf = data.get("csrf_token") or ""
    s.headers.update({
        "Authorization": f"Bearer {token}",
        "X-CSRF-Token": csrf,
        "Content-Type": "application/json",
    })
    return s


@pytest.fixture
def setup_world(auth):
    """Cria 1 escola (reusa existente) + 1 turma e cleanup."""
    sfx = uuid.uuid4().hex[:8]
    rs = auth.get(f"{BASE_URL}/api/schools", timeout=15)
    assert rs.status_code == 200
    schools = rs.json()
    if isinstance(schools, dict):
        schools = schools.get("items") or schools.get("schools") or []
    assert schools
    school_id = schools[0]["id"]

    class_id_requested = f"repro_cls_cancel_{sfx}"
    rc = auth.post(f"{BASE_URL}/api/classes", json={
        "id": class_id_requested,
        "name": f"Pré I C Cancel-Repro {sfx}",
        "school_id": school_id,
        "grade_level": "Pré I",
        "education_level": "educacao_infantil",
        "academic_year": 2026,
        "shift": "morning",
    }, timeout=15)
    assert rc.status_code in (200, 201), f"create class: {rc.status_code} {rc.text[:300]}"
    # Backend gera novo UUID — usa o retornado pela API.
    class_id = rc.json()["id"]

    yield {"school": school_id, "class": class_id, "sfx": sfx}

    auth.delete(f"{BASE_URL}/api/classes/{class_id}")


def _create_active_student(auth, *, name, school_id, class_id):
    r = auth.post(f"{BASE_URL}/api/students", json={
        "full_name": name,
        "birth_date": "2019-05-01",
        "sex": "feminino",
        "school_id": school_id,
        "class_id": class_id,
        "status": "active",
        "no_documents_justification": "test",
    }, timeout=20)
    assert r.status_code in (200, 201), f"{r.status_code} {r.text[:300]}"
    return r.json()["id"]


def test_cancel_transfer_restores_student_to_same_class(auth, setup_world):
    """Caso feliz: aluno transferido → cancela → volta à mesma turma."""
    ctx = setup_world
    sid = _create_active_student(
        auth,
        name=f"Ema Cancel Repro {ctx['sfx']}",
        school_id=ctx["school"],
        class_id=ctx["class"],
    )
    try:
        # 1) Transfere
        r1 = auth.put(f"{BASE_URL}/api/students/{sid}",
                      json={"status": "transferred"}, timeout=30)
        assert r1.status_code == 200, r1.text[:300]
        assert r1.json().get("status") in ("transferred", "transferido")

        # 2) Cancela transferência
        r2 = auth.post(
            f"{BASE_URL}/api/students/{sid}/cancel-transfer",
            json={"class_id": ctx["class"]},
            timeout=30,
        )
        assert r2.status_code == 200, f"{r2.status_code} {r2.text[:400]}"
        body = r2.json()
        assert body.get("class_id") == ctx["class"]
        assert body.get("school_id") == ctx["school"]
        assert body["student"].get("status") in ("active", "Ativo")
        assert body["student"].get("class_id") == ctx["class"]

        # 3) Confere histórico — última ação é transferencia_cancelada
        rh = auth.get(f"{BASE_URL}/api/students/{sid}/history", timeout=15)
        assert rh.status_code == 200
        hist = rh.json()
        types = [h.get("action_type") for h in hist]
        assert "transferencia_cancelada" in types, f"types={types}"

        # 4) Enrollment original deve estar como active (não transferred)
        re_ = auth.get(f"{BASE_URL}/api/enrollments",
                       params={"student_id": sid, "class_id": ctx["class"]},
                       timeout=15)
        assert re_.status_code == 200
        enrollments = re_.json()
        active = [e for e in enrollments if e.get("status") == "active"]
        assert active, f"Nenhum enrollment ativo. enrollments={enrollments}"

        # 5) Aluno aparece na listagem da turma sem o label "Transferido"
        rd = auth.get(f"{BASE_URL}/api/classes/{ctx['class']}/details", timeout=20)
        assert rd.status_code == 200
        students_in_class = rd.json().get("students") or []
        my = next((s for s in students_in_class if s.get("id") == sid), None)
        assert my is not None
        # Após o cancelamento, NÃO deve mais mostrar o label antigo de transferência
        # (action_info_map só pega de enrollments inativos, e o atual já é active).
        assert my.get("action_label") == "", f"Esperava action_label vazio, got: {my}"
    finally:
        auth.delete(f"{BASE_URL}/api/students/{sid}")


def test_cancel_transfer_on_active_student_returns_400(auth, setup_world):
    """Aluno ATIVO não pode ter transferência cancelada (não há o que cancelar)."""
    ctx = setup_world
    sid = _create_active_student(
        auth,
        name=f"Joana Ativa Cancel Repro {ctx['sfx']}",
        school_id=ctx["school"],
        class_id=ctx["class"],
    )
    try:
        r = auth.post(
            f"{BASE_URL}/api/students/{sid}/cancel-transfer",
            json={"class_id": ctx["class"]},
            timeout=15,
        )
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"
        assert "Transferido" in r.text or "transferred" in r.text.lower()
    finally:
        auth.delete(f"{BASE_URL}/api/students/{sid}")


def test_cancel_transfer_invalid_student_returns_404(auth, setup_world):
    r = auth.post(
        f"{BASE_URL}/api/students/UNKNOWN_xx/cancel-transfer",
        json={"class_id": setup_world["class"]},
        timeout=15,
    )
    assert r.status_code == 404


def test_cancel_transfer_without_body_uses_latest_transfer(auth, setup_world):
    """Sem class_id no body, usa a matrícula transferida mais recente."""
    ctx = setup_world
    sid = _create_active_student(
        auth,
        name=f"Carla NoBody Cancel Repro {ctx['sfx']}",
        school_id=ctx["school"],
        class_id=ctx["class"],
    )
    try:
        auth.put(f"{BASE_URL}/api/students/{sid}", json={"status": "transferred"}, timeout=15)
        r = auth.post(f"{BASE_URL}/api/students/{sid}/cancel-transfer", json={}, timeout=20)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        assert r.json().get("class_id") == ctx["class"]
    finally:
        auth.delete(f"{BASE_URL}/api/students/{sid}")


def test_cancel_transfer_requires_auth():
    r = requests.post(
        f"{BASE_URL}/api/students/anyone/cancel-transfer",
        json={}, timeout=10,
    )
    assert r.status_code in (401, 403)
