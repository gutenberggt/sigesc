"""
E2E test — Transferência Institucional de Turmas (Re-homing / Opção A).

Cobre a Fase 1 (Backend):
  - POST /dry-run: contagens, validações bloqueantes, geração de token, sem mutação
  - POST /execute: re-autenticação por senha, frase de confirmação, re-homing,
    school_history, academic_events, auditoria, idempotência
  - GET / e GET /{protocol}: histórico e detalhe
  - Segurança: somente super_admin; senha/frase incorretas barram a operação

Estratégia de isolamento: cria 1 turma de teste (ano letivo com calendário
existente) na escola de origem + 2 alunos, executa a transferência para uma
2ª escola da MESMA mantenedora, valida e LIMPA tudo via Mongo direto no final.
"""
from __future__ import annotations

import os
import uuid
import pytest
import requests
from pathlib import Path
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "https://autosave-drafts.preview.emergentagent.com")
    .rstrip("/")
)
EMAIL = "gutenberg@sigesc.com"
PASSWORD = "@Celta2007"
PHRASE = "CONFIRMO A TRANSFERÊNCIA INSTITUCIONAL"

_mc = MongoClient(os.environ["MONGO_URL"])
_db = _mc[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def auth():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    s.headers.update({
        "Authorization": f"Bearer {data.get('access_token') or data.get('token')}",
        "X-CSRF-Token": data.get("csrf_token") or "",
        "Content-Type": "application/json",
    })
    return s


def _pick_two_schools_same_mantenedora():
    """Encontra origem (com >=1 turma) e destino (ativa) na mesma mantenedora."""
    schools = list(_db.schools.find({"status": "active"}, {"_id": 0, "id": 1, "mantenedora_id": 1}))
    by_tenant = {}
    for s in schools:
        by_tenant.setdefault(s.get("mantenedora_id"), []).append(s["id"])
    for tenant, ids in by_tenant.items():
        if tenant and len(ids) >= 2:
            # origem = a que já tem turmas (evita fechar a escola por engano)
            origin = next((i for i in ids if _db.classes.count_documents({"school_id": i}) > 0), ids[0])
            dest = next(i for i in ids if i != origin)
            return origin, dest
    pytest.skip("Sem 2 escolas ativas na mesma mantenedora para testar")


def _calendar_year_for(school_id):
    cal = _db.calendario_letivo.find_one({"school_id": {"$in": [school_id, None]}}, {"_id": 0, "ano_letivo": 1})
    return cal["ano_letivo"] if cal else 2025


@pytest.fixture
def world(auth):
    origin, dest = _pick_two_schools_same_mantenedora()
    year = _calendar_year_for(dest)
    sfx = uuid.uuid4().hex[:8]

    rc = auth.post(f"{BASE_URL}/api/classes", json={
        "name": f"TRANSF-TEST {sfx}",
        "school_id": origin,
        "grade_level": "Pré I",
        "education_level": "educacao_infantil",
        "academic_year": year,
        "shift": "morning",
    }, timeout=20)
    assert rc.status_code in (200, 201), f"create class: {rc.status_code} {rc.text[:300]}"
    class_id = rc.json()["id"]

    student_ids = []
    for n in range(2):
        rs = auth.post(f"{BASE_URL}/api/students", json={
            "full_name": f"Aluno Transf {sfx}-{n}",
            "birth_date": "2019-05-01",
            "sex": "feminino",
            "school_id": origin,
            "class_id": class_id,
            "status": "active",
            "no_documents_justification": "test",
        }, timeout=20)
        assert rs.status_code in (200, 201), rs.text[:300]
        student_ids.append(rs.json()["id"])

    ctx = {"origin": origin, "dest": dest, "class_id": class_id, "year": year, "students": student_ids}
    yield ctx

    # ---- cleanup (Mongo direto, pois rollback é Fase 2) ----
    for sid in student_ids:
        _db.students.delete_one({"id": sid})
        _db.enrollments.delete_many({"student_id": sid})
    _db.classes.delete_one({"id": class_id})
    _db.enrollments.delete_many({"class_id": class_id})
    _db.attendance.delete_many({"class_id": class_id})
    _db.academic_events.delete_many({"event_type": "transferencia_institucional", "origin_class_id": class_id})
    _db.school_transfer_audit.delete_many({"class_ids": class_id})


def _dry_run(auth, ctx):
    return auth.post(f"{BASE_URL}/api/admin/school-transfer/dry-run", json={
        "origin_school_id": ctx["origin"],
        "destination_school_id": ctx["dest"],
        "class_ids": [ctx["class_id"]],
    }, timeout=30)


# ---------------------------------------------------------------- DRY RUN
def test_dry_run_counts_and_token(auth, world):
    r = _dry_run(auth, world)
    assert r.status_code == 200, r.text[:400]
    d = r.json()
    assert d["dry_run_token"]
    assert d["counts"]["classes"] == 1
    assert d["counts"]["students"] == 2
    assert d["can_execute"] is True, d.get("blocking_failures")
    # dry-run NÃO muta: turma continua na origem
    assert _db.classes.find_one({"id": world["class_id"]})["school_id"] == world["origin"]


def test_dry_run_blocks_cross_mantenedora(auth, world):
    # destino de outra mantenedora → SAME_MANTENEDORA deve bloquear
    other = _db.schools.find_one(
        {"status": "active", "mantenedora_id": {"$ne": _db.schools.find_one({"id": world['origin']})["mantenedora_id"]}},
        {"_id": 0, "id": 1},
    )
    if not other:
        pytest.skip("Sem escola de outra mantenedora")
    r = auth.post(f"{BASE_URL}/api/admin/school-transfer/dry-run", json={
        "origin_school_id": world["origin"],
        "destination_school_id": other["id"],
        "class_ids": [world["class_id"]],
    }, timeout=30)
    assert r.status_code == 200
    codes = [v["code"] for v in r.json()["blocking_failures"]]
    assert "SAME_MANTENEDORA" in codes
    assert r.json()["can_execute"] is False


# ---------------------------------------------------------------- SECURITY
def test_execute_wrong_password_401(auth, world):
    token = _dry_run(auth, world).json()["dry_run_token"]
    r = auth.post(f"{BASE_URL}/api/admin/school-transfer/execute", json={
        "dry_run_token": token, "password": "WRONG", "reason": "Extincao da unidade teste", "confirmation_text": PHRASE,
    }, timeout=30)
    assert r.status_code == 401
    assert _db.classes.find_one({"id": world["class_id"]})["school_id"] == world["origin"]


def test_execute_wrong_phrase_400(auth, world):
    token = _dry_run(auth, world).json()["dry_run_token"]
    r = auth.post(f"{BASE_URL}/api/admin/school-transfer/execute", json={
        "dry_run_token": token, "password": PASSWORD, "reason": "Extincao da unidade teste", "confirmation_text": "nope",
    }, timeout=30)
    assert r.status_code == 400


def test_dry_run_requires_auth():
    r = requests.post(f"{BASE_URL}/api/admin/school-transfer/dry-run",
                      json={"origin_school_id": "x", "destination_school_id": "y", "class_ids": ["z"]}, timeout=15)
    assert r.status_code in (401, 403)


# ---------------------------------------------------------------- EXECUTE (happy path)
def test_execute_rehoming_and_idempotency(auth, world):
    token = _dry_run(auth, world).json()["dry_run_token"]
    r = auth.post(f"{BASE_URL}/api/admin/school-transfer/execute", json={
        "dry_run_token": token, "password": PASSWORD,
        "reason": "Extincao da unidade escolar teste", "confirmation_text": PHRASE,
    }, timeout=60)
    assert r.status_code == 200, r.text[:500]
    body = r.json()
    assert body["success"] is True
    protocol = body["protocol"]
    assert protocol.startswith("TRANSF-")
    assert body["modified_counts"]["classes"] == 1
    assert body["students_moved"] == 2

    # re-homing efetivo
    cls = _db.classes.find_one({"id": world["class_id"]})
    assert cls["school_id"] == world["dest"]
    # school_history: origem fechada + destino aberto
    hist = cls.get("school_history")
    assert hist and hist[-1]["school_id"] == world["dest"] and hist[-1]["end_date"] is None
    assert hist[-2]["school_id"] == world["origin"] and hist[-2]["end_date"] is not None
    # alunos seguiram
    assert _db.students.count_documents({"class_id": world["class_id"], "school_id": world["dest"]}) == 2
    # academic_events institucional
    ev = _db.academic_events.find_one({"event_type": "transferencia_institucional", "origin_class_id": world["class_id"]})
    assert ev and ev["protocol"] == protocol and ev["approval_status"] == "approved"
    # auditoria com IP/operador e SEM vazar senha
    aud = _db.school_transfer_audit.find_one({"protocol": protocol})
    assert aud["status"] == "executed" and aud["executed_by"]["email"] == EMAIL
    assert "password" not in {k.lower() for k in aud.keys()}

    # idempotência: reexecutar o mesmo token não duplica
    r2 = auth.post(f"{BASE_URL}/api/admin/school-transfer/execute", json={
        "dry_run_token": token, "password": PASSWORD,
        "reason": "Extincao da unidade escolar teste", "confirmation_text": PHRASE,
    }, timeout=30)
    assert r2.status_code == 200 and r2.json().get("already_executed") is True
    assert _db.academic_events.count_documents(
        {"event_type": "transferencia_institucional", "origin_class_id": world["class_id"]}
    ) == 1

    # GET detail + list
    rd = auth.get(f"{BASE_URL}/api/admin/school-transfer/{protocol}", timeout=15)
    assert rd.status_code == 200 and rd.json()["protocol"] == protocol
    rl = auth.get(f"{BASE_URL}/api/admin/school-transfer", params={"status": "executed"}, timeout=15)
    assert rl.status_code == 200 and any(i["protocol"] == protocol for i in rl.json()["items"])
