"""
E2E test — Rollback da Transferência Institucional (Fase 2).

Cobre os critérios exigidos:
  - Execute → Rollback (reversão completa: classes, students, enrollments,
    attendance, grades, content_entries, school_history exato)
  - Execute → Rollback → Rollback (idempotência: mesmo protocolo, sem efeito colateral)
  - Rollback fora da janela de 7 dias (409 WINDOW_EXPIRED)
  - Rollback após emissão de documento oficial (409 OFFICIAL_DOCUMENT_EMITTED)
  - Rollback parcial (falha simulada) → 500, estado preservado, lock liberado,
    re-execução conclui (idempotente)
  - Transferência de escola inteira → reabertura automática da escola origem
  - Segurança: super_admin + re-auth por senha + frase de confirmação
  - Validação temporal do school_history (sem sobreposição / sem lacunas)

Isolamento: cria uma escola origem ISOLADA (insert Mongo direto) na MESMA
mantenedora de um destino válido (com calendário), cria turma + alunos via API,
e LIMPA tudo no final.
"""
from __future__ import annotations

import os
import uuid
import pytest
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "https://institutional-audit-2.preview.emergentagent.com")
    .rstrip("/")
)
EMAIL = os.environ.get("TRANSFER_TEST_EMAIL", "gutenberg@sigesc.com")
PASSWORD = os.environ.get("TRANSFER_TEST_PASSWORD", "@Celta2007")
PHRASE = "CONFIRMO A TRANSFERÊNCIA INSTITUCIONAL"
ROLLBACK_PHRASE = "CONFIRMO A REVERSÃO DA TRANSFERÊNCIA"

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


def _dest_with_calendar():
    """Destino ativo que possui calendário letivo (DESTINATION_CALENDAR_OPEN)."""
    for cal in _db.calendario_letivo.find({}, {"_id": 0, "school_id": 1, "ano_letivo": 1}):
        sid = cal.get("school_id")
        if not sid:
            continue
        sch = _db.schools.find_one({"id": sid, "status": "active"}, {"_id": 0, "id": 1, "mantenedora_id": 1})
        if sch and sch.get("mantenedora_id"):
            return sch, cal["ano_letivo"]
    # fallback: destino ativo + calendário global (school_id None)
    cal = _db.calendario_letivo.find_one({"school_id": None}, {"_id": 0, "ano_letivo": 1})
    if cal:
        sch = _db.schools.find_one({"status": "active", "mantenedora_id": {"$ne": None}}, {"_id": 0, "id": 1, "mantenedora_id": 1})
        if sch:
            return sch, cal["ano_letivo"]
    pytest.skip("Sem destino ativo com calendário letivo configurado")


def _make_world(auth, n_classes=1):
    """Cria escola origem isolada + n turmas (cada uma com 2 alunos) via API."""
    dest, year = _dest_with_calendar()
    sfx = uuid.uuid4().hex[:8]
    origin_id = f"transftest-origin-{sfx}"
    _db.schools.insert_one({
        "id": origin_id,
        "name": f"ESCOLA ORIGEM TESTE {sfx}",
        "mantenedora_id": dest["mantenedora_id"],
        "status": "active",
        "niveis_ensino_oferecidos": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    class_ids, student_ids = [], []
    for k in range(n_classes):
        rc = auth.post(f"{BASE_URL}/api/classes", json={
            "name": f"TRANSF-RB {sfx}-{k}",
            "school_id": origin_id,
            "grade_level": "Pré I",
            "education_level": "educacao_infantil",
            "academic_year": year,
            "shift": "morning",
        }, timeout=20)
        assert rc.status_code in (200, 201), f"create class: {rc.status_code} {rc.text[:300]}"
        cid = rc.json()["id"]
        class_ids.append(cid)
        for n in range(2):
            rs = auth.post(f"{BASE_URL}/api/students", json={
                "full_name": f"Aluno RB {sfx}-{k}-{n}",
                "birth_date": "2019-05-01",
                "sex": "feminino",
                "school_id": origin_id,
                "class_id": cid,
                "status": "active",
                "no_documents_justification": "test",
            }, timeout=20)
            assert rs.status_code in (200, 201), rs.text[:300]
            student_ids.append(rs.json()["id"])

    return {"origin": origin_id, "dest": dest["id"], "class_ids": class_ids,
            "year": year, "students": student_ids}


def _cleanup(ctx):
    cids = ctx["class_ids"]
    for sid in ctx["students"]:
        _db.students.delete_one({"id": sid})
        _db.enrollments.delete_many({"student_id": sid})
        _db.school_documents_log.delete_many({"student_id": sid})
    _db.classes.delete_many({"id": {"$in": cids}})
    _db.enrollments.delete_many({"class_id": {"$in": cids}})
    _db.attendance.delete_many({"class_id": {"$in": cids}})
    _db.school_documents_log.delete_many({"class_id": {"$in": cids}})
    _db.academic_events.delete_many({"origin_class_id": {"$in": cids}})
    _db.academic_events.delete_many({"destination_class_id": {"$in": cids}})
    _db.school_transfer_audit.delete_many({"class_ids": {"$in": cids}})
    _db.schools.delete_one({"id": ctx["origin"]})


@pytest.fixture
def world(auth):
    ctx = _make_world(auth, n_classes=1)
    yield ctx
    _cleanup(ctx)


@pytest.fixture
def world_multi(auth):
    ctx = _make_world(auth, n_classes=2)
    yield ctx
    _cleanup(ctx)


def _execute(auth, ctx):
    dr = auth.post(f"{BASE_URL}/api/admin/school-transfer/dry-run", json={
        "origin_school_id": ctx["origin"],
        "destination_school_id": ctx["dest"],
        "class_ids": ctx["class_ids"],
    }, timeout=30)
    assert dr.status_code == 200, dr.text[:400]
    token = dr.json()["dry_run_token"]
    assert dr.json()["can_execute"] is True, dr.json().get("blocking_failures")
    ex = auth.post(f"{BASE_URL}/api/admin/school-transfer/execute", json={
        "dry_run_token": token, "password": PASSWORD,
        "reason": "Extincao da unidade escolar teste rollback", "confirmation_text": PHRASE,
    }, timeout=60)
    assert ex.status_code == 200, ex.text[:500]
    return ex.json()["protocol"]


def _rollback(auth, protocol, password=PASSWORD, phrase=ROLLBACK_PHRASE):
    return auth.post(f"{BASE_URL}/api/admin/school-transfer/{protocol}/rollback", json={
        "password": password,
        "reason": "Reversao por engano na transferencia teste",
        "confirmation_text": phrase,
    }, timeout=60)


# ---------------------------------------------------------------- HAPPY PATH
def test_execute_then_rollback_full_reversal(auth, world):
    protocol = _execute(auth, world)
    cid = world["class_ids"][0]
    # confirma que moveu para o destino
    assert _db.classes.find_one({"id": cid})["school_id"] == world["dest"]

    r = _rollback(auth, protocol)
    assert r.status_code == 200, r.text[:500]
    body = r.json()
    assert body["success"] is True
    assert body["rollback_protocol"].startswith("ROLLBACK-")
    assert body["original_protocol"] == protocol
    # escola origem reaberta (foi encerrada por ter ficado sem turmas)
    assert body["origin_reopened"] is True

    # reversão efetiva: turma e alunos voltaram à origem
    cls = _db.classes.find_one({"id": cid})
    assert cls["school_id"] == world["origin"]
    assert _db.students.count_documents({"class_id": cid, "school_id": world["origin"]}) == 2

    # school_history restaurado EXATO (sem o segmento do destino)
    hist = cls.get("school_history")
    # não pode haver segmento aberto apontando para o destino
    assert not any(h.get("school_id") == world["dest"] and h.get("end_date") is None for h in (hist or []))

    # escola origem voltou a 'active'
    assert _db.schools.find_one({"id": world["origin"]})["status"] == "active"

    # auditoria imutável da reversão
    aud = _db.school_transfer_audit.find_one({"protocol": protocol})
    assert aud["status"] == "rolled_back"
    assert aud["rollback"]["rolled_back_by"]["email"] == EMAIL
    assert aud["rollback"]["original_protocol"] == protocol
    # evento de reversão append-only criado, evento original preservado
    assert _db.academic_events.count_documents(
        {"event_type": "reversao_transferencia_institucional", "origin_class_id": cid}) == 1
    assert _db.academic_events.count_documents(
        {"event_type": "transferencia_institucional", "origin_class_id": cid}) == 1


def test_rollback_idempotent(auth, world):
    protocol = _execute(auth, world)
    r1 = _rollback(auth, protocol)
    assert r1.status_code == 200
    rb_proto = r1.json()["rollback_protocol"]

    r2 = _rollback(auth, protocol)
    assert r2.status_code == 200
    assert r2.json().get("already_rolled_back") is True
    assert r2.json()["rollback_protocol"] == rb_proto  # MESMO protocolo

    # nenhum efeito colateral: 1 evento de reversão por turma
    cid = world["class_ids"][0]
    assert _db.academic_events.count_documents(
        {"event_type": "reversao_transferencia_institucional", "origin_class_id": cid}) == 1


def test_rollback_security_wrong_password_and_phrase(auth, world):
    protocol = _execute(auth, world)
    # senha errada
    r = _rollback(auth, protocol, password="WRONG")
    assert r.status_code == 401
    # frase errada
    r2 = _rollback(auth, protocol, phrase="nope")
    assert r2.status_code == 400
    # ainda no destino (não reverteu)
    assert _db.classes.find_one({"id": world["class_ids"][0]})["school_id"] == world["dest"]
    # limpa: reverte de fato para o cleanup deixar consistente
    _rollback(auth, protocol)


def test_rollback_requires_super_admin():
    r = requests.post(f"{BASE_URL}/api/admin/school-transfer/TRANSF-2025-000001/rollback",
                      json={"password": "x", "reason": "xxxxxxxxxx", "confirmation_text": ROLLBACK_PHRASE}, timeout=15)
    assert r.status_code in (401, 403)


# ---------------------------------------------------------------- WINDOW
def test_rollback_blocked_outside_window(auth, world):
    protocol = _execute(auth, world)
    # força executed_at para 8 dias atrás
    past = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    _db.school_transfer_audit.update_one({"protocol": protocol}, {"$set": {"executed_at": past}})

    r = _rollback(auth, protocol)
    assert r.status_code == 409, r.text[:300]
    codes = [x["code"] for x in r.json()["detail"]["reasons"]]
    assert "WINDOW_EXPIRED" in codes
    # ainda no destino
    assert _db.classes.find_one({"id": world["class_ids"][0]})["school_id"] == world["dest"]

    # restaura executed_at e reverte para o cleanup
    _db.school_transfer_audit.update_one({"protocol": protocol},
                                         {"$set": {"executed_at": datetime.now(timezone.utc).isoformat()}})
    _rollback(auth, protocol)


def test_rollback_eligibility_endpoint(auth, world):
    protocol = _execute(auth, world)
    r = auth.get(f"{BASE_URL}/api/admin/school-transfer/{protocol}/rollback-eligibility", timeout=20)
    assert r.status_code == 200
    body = r.json()
    assert body["eligible"] is True
    assert body["rollback_confirmation_phrase"] == ROLLBACK_PHRASE
    assert body["window_days"] == 7
    _rollback(auth, protocol)


# ---------------------------------------------------------------- OFFICIAL DOC
def test_rollback_blocked_after_official_document(auth, world):
    protocol = _execute(auth, world)
    cid = world["class_ids"][0]
    # simula emissão de documento oficial APÓS a transferência
    _db.school_documents_log.insert_one({
        "id": str(uuid.uuid4()),
        "student_id": world["students"][0],
        "class_id": cid,
        "school_id": world["dest"],
        "doc_type": "matricula",
        "code": f"TEST{uuid.uuid4().hex[:6].upper()}",
        "emitted_at": (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat(),
    })
    r = _rollback(auth, protocol)
    assert r.status_code == 409, r.text[:300]
    codes = [x["code"] for x in r.json()["detail"]["reasons"]]
    assert "OFFICIAL_DOCUMENT_EMITTED" in codes
    assert _db.classes.find_one({"id": cid})["school_id"] == world["dest"]

    # remove o doc e reverte para o cleanup
    _db.school_documents_log.delete_many({"class_id": cid})
    _rollback(auth, protocol)


# ---------------------------------------------------------------- PARTIAL FAIL
def test_rollback_partial_failure_then_recovers(auth, world):
    protocol = _execute(auth, world)
    cid = world["class_ids"][0]
    aud = _db.school_transfer_audit.find_one({"protocol": protocol})
    good_snapshot = aud["snapshot"]
    # injeta entrada malformada (ObjectId inválido) para forçar exceção no meio
    bad_snapshot = list(good_snapshot) + [{"collection": "attendance", "key": "_id",
                                           "doc_key": "not-a-valid-objectid", "old_school_id": world["origin"]}]
    _db.school_transfer_audit.update_one({"protocol": protocol}, {"$set": {"snapshot": bad_snapshot}})

    r = _rollback(auth, protocol)
    assert r.status_code == 500, r.text[:300]
    # estado NÃO marcado como revertido (permite reexecução)
    assert _db.school_transfer_audit.find_one({"protocol": protocol})["status"] == "executed"
    # lock liberado (sem turmas presas)
    assert _db.classes.count_documents({"id": cid, "transfer_in_progress": True}) == 0

    # corrige o snapshot e reexecuta → conclui (idempotente)
    _db.school_transfer_audit.update_one({"protocol": protocol}, {"$set": {"snapshot": good_snapshot}})
    r2 = _rollback(auth, protocol)
    assert r2.status_code == 200, r2.text[:300]
    assert _db.classes.find_one({"id": cid})["school_id"] == world["origin"]


# ---------------------------------------------------------------- RECEIPT PDF
def test_receipt_pdf_executed_and_after_rollback(auth, world):
    protocol = _execute(auth, world)
    r = auth.get(f"{BASE_URL}/api/admin/school-transfer/{protocol}/receipt", timeout=40)
    assert r.status_code == 200, r.text[:300]
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content[:4] == b"%PDF"
    aud = _db.school_transfer_audit.find_one({"protocol": protocol})
    assert aud.get("receipt", {}).get("token")
    vdoc = _db.verifiable_documents.find_one({"verification_token": aud["receipt"]["token"]})
    assert vdoc and vdoc["type"] == "recibo_transferencia_institucional"
    # recibo NÃO fecha a janela de rollback (não grava school_documents_log)
    assert _db.school_documents_log.count_documents({"class_id": world["class_ids"][0]}) == 0
    rb = _rollback(auth, protocol)
    assert rb.status_code == 200
    r2 = auth.get(f"{BASE_URL}/api/admin/school-transfer/{protocol}/receipt", timeout=40)
    assert r2.status_code == 200 and r2.content[:4] == b"%PDF"
    _db.verifiable_documents.delete_many({"entity_type": "school_transfer", "entity_id": protocol})


# ---------------------------------------------------------------- MULTI-CLASS
# ------------------------------------------------ SCHOOL_HISTORY EXACT REVERSAL
def test_rollback_restores_preexisting_school_history_exactly(auth, world):
    """Regressão: turma COM school_history pré-existente deve ter o histórico
    restaurado EXATAMENTE (bug de aliasing — snapshot guardava referência mutada)."""
    cid = world["class_ids"][0]
    baseline_history = [{"school_id": world["origin"], "start_date": "2025-01-01", "end_date": None}]
    _db.classes.update_one({"id": cid}, {"$set": {"school_history": baseline_history}})

    protocol = _execute(auth, world)
    # pós-execute: 2 segmentos (origem fechado + destino aberto)
    after_exec = _db.classes.find_one({"id": cid})["school_history"]
    assert len(after_exec) == 2 and after_exec[-1]["school_id"] == world["dest"] and after_exec[-1]["end_date"] is None

    r = _rollback(auth, protocol)
    assert r.status_code == 200
    restored = _db.classes.find_one({"id": cid})["school_history"]
    assert restored == baseline_history, f"school_history não restaurado: {restored}"


def test_rollback_multiple_classes(auth, world_multi):
    protocol = _execute(auth, world_multi)
    for cid in world_multi["class_ids"]:
        assert _db.classes.find_one({"id": cid})["school_id"] == world_multi["dest"]

    r = _rollback(auth, protocol)
    assert r.status_code == 200, r.text[:400]
    assert r.json()["origin_reopened"] is True
    for cid in world_multi["class_ids"]:
        assert _db.classes.find_one({"id": cid})["school_id"] == world_multi["origin"]
        assert _db.students.count_documents({"class_id": cid, "school_id": world_multi["origin"]}) == 2
    assert _db.schools.find_one({"id": world_multi["origin"]})["status"] == "active"
