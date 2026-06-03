"""
Regressão Iter 76 — Bug "Network Error" ao rematricular aluno transferido.

Cenário (relatado pelo usuário):
  Ema estudava na "Pré I C", pediu transferência (status=transferred), e depois
  voltou para se matricular na "Pré I B" (mesma escola). Antes da correção,
  retornava 409 "Este aluno já possui matrícula ativa na turma ''..." porque o
  branch de REMANEJAMENTO disparava (criando uma matrícula), e em seguida o
  branch de REMATRÍCULA tentava criar OUTRA, resultando em erro.

Fix: branch de remanejamento agora só dispara quando `old_status` é 'active'.

Cobre também:
  - Remanejamento legítimo de aluno ATIVO entre turmas da mesma escola continua
    funcionando.
"""
from __future__ import annotations

import os
import uuid
import requests
import pytest

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "https://sla-trio-weighted.preview.emergentagent.com")
    .rstrip("/")
)
EMAIL = "gutenberg@sigesc.com"
PASSWORD = "@Celta2007"


@pytest.fixture(scope="module")
def auth():
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=30,
    )
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
def setup_school_and_classes(auth):
    """Cria 1 escola + 2 turmas (Pré I C origem, Pré I B destino)."""
    sfx = uuid.uuid4().hex[:8]
    school_id = f"repro_sch_{sfx}"
    cls_c = f"repro_cls_c_{sfx}"
    cls_b = f"repro_cls_b_{sfx}"

    # Usa escola existente do tenant default (mais simples que criar uma)
    rs = auth.get(f"{BASE_URL}/api/schools", timeout=20)
    assert rs.status_code == 200
    schools = rs.json()
    if isinstance(schools, dict):
        schools = schools.get("items") or schools.get("schools") or []
    assert schools, "Nenhuma escola disponível para o teste"
    school_id = schools[0]["id"]

    # Cria 2 turmas
    for cid, name in ((cls_c, f"Pré I C (Repro {sfx})"), (cls_b, f"Pré I B (Repro {sfx})")):
        rr = auth.post(f"{BASE_URL}/api/classes", json={
            "id": cid, "name": name, "school_id": school_id,
            "grade_level": "Pré I", "education_level": "educacao_infantil",
            "academic_year": 2026, "shift": "morning",
        }, timeout=15)
        assert rr.status_code in (200, 201), f"create class {name}: {rr.status_code} {rr.text[:200]}"

    yield {"school": school_id, "class_c": cls_c, "class_b": cls_b, "sfx": sfx}

    # Cleanup
    for cid in (cls_c, cls_b):
        auth.delete(f"{BASE_URL}/api/classes/{cid}")


def _create_student(auth, *, name, school_id, class_id):
    r = auth.post(f"{BASE_URL}/api/students", json={
        "full_name": name,
        "birth_date": "2019-05-01",
        "sex": "feminino",
        "school_id": school_id,
        "class_id": class_id,
        "status": "active",
        "no_documents_justification": "regressão",
    }, timeout=20)
    assert r.status_code in (200, 201), f"create student: {r.status_code} {r.text[:300]}"
    return r.json()["id"]


def test_rematricula_de_transferido_em_outra_turma_mesma_escola(auth, setup_school_and_classes):
    """REGRESSÃO: aluno transferido → rematrícula em outra turma da mesma escola.
    Antes do fix: 409 falso. Depois: 200 OK + status='active' + class_id=destino."""
    ctx = setup_school_and_classes
    sid = _create_student(
        auth,
        name=f"Ema Repro {ctx['sfx']}",
        school_id=ctx["school"],
        class_id=ctx["class_c"],
    )
    try:
        # 1) Transfere
        r1 = auth.put(f"{BASE_URL}/api/students/{sid}", json={"status": "transferred"}, timeout=30)
        assert r1.status_code == 200, f"transfer: {r1.status_code} {r1.text[:300]}"
        assert r1.json().get("status") in ("transferred", "transferido")

        # 2) Rematricula em outra turma da mesma escola — ESTA é a operação que
        #    antes do fix retornava 409 ("já possui matrícula ativa na turma ''").
        r2 = auth.put(f"{BASE_URL}/api/students/{sid}", json={
            "school_id": ctx["school"],
            "class_id": ctx["class_b"],
            "status": "active",
            "academic_year": 2026,
            "enrollment_date": "2026-02-11",
        }, timeout=60)
        assert r2.status_code == 200, f"rematricula: {r2.status_code} {r2.text[:400]}"
        body = r2.json()
        assert body.get("status") in ("active", "Ativo"), body
        assert body.get("class_id") == ctx["class_b"], body
        assert body.get("school_id") == ctx["school"], body
    finally:
        auth.delete(f"{BASE_URL}/api/students/{sid}")


def test_remanejamento_de_aluno_ativo_continua_funcionando(auth, setup_school_and_classes):
    """SANIDADE: aluno ATIVO mudando de turma na mesma escola = remanejamento
    legítimo. Não pode ser quebrado pelo fix."""
    ctx = setup_school_and_classes
    sid = _create_student(
        auth,
        name=f"Joana Ativa Repro {ctx['sfx']}",
        school_id=ctx["school"],
        class_id=ctx["class_c"],
    )
    try:
        # Aluno está ATIVO em Pré I C → move para Pré I B (remanejamento clássico)
        r = auth.put(f"{BASE_URL}/api/students/{sid}", json={
            "school_id": ctx["school"],
            "class_id": ctx["class_b"],
        }, timeout=30)
        assert r.status_code == 200, f"remanejar: {r.status_code} {r.text[:400]}"
        body = r.json()
        assert body.get("class_id") == ctx["class_b"]
        # Status continua ativo
        assert body.get("status") in ("active", "Ativo")

        # Verifica histórico → última ação deve ser remanejamento
        rh = auth.get(f"{BASE_URL}/api/students/{sid}/history", timeout=15)
        assert rh.status_code == 200
        hist = rh.json()
        assert any(h.get("action_type") == "remanejamento" for h in hist), \
            f"Esperava remanejamento no histórico, got: {[h.get('action_type') for h in hist]}"
    finally:
        auth.delete(f"{BASE_URL}/api/students/{sid}")


def test_rematricula_de_inativo_em_outra_turma_mesma_escola(auth, setup_school_and_classes):
    """Edge case: aluno cancelado/inativo → rematricula em outra turma da mesma escola."""
    ctx = setup_school_and_classes
    sid = _create_student(
        auth,
        name=f"Carla Inativa Repro {ctx['sfx']}",
        school_id=ctx["school"],
        class_id=ctx["class_c"],
    )
    try:
        # Marca como inativo
        auth.put(f"{BASE_URL}/api/students/{sid}", json={"status": "dropout"}, timeout=15)

        # Rematricula
        r = auth.put(f"{BASE_URL}/api/students/{sid}", json={
            "school_id": ctx["school"],
            "class_id": ctx["class_b"],
            "status": "active",
            "academic_year": 2026,
        }, timeout=60)
        assert r.status_code == 200, f"rematricula inativo: {r.status_code} {r.text[:400]}"
        assert r.json().get("class_id") == ctx["class_b"]
    finally:
        auth.delete(f"{BASE_URL}/api/students/{sid}")
