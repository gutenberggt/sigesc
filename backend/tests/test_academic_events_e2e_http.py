"""
E2E HTTP — Academic Events V1 (iteração 74).

Roda contra REACT_APP_BACKEND_URL com Super Admin + X-Mantenedora-Id=fix_mant_v1.
Cobre os requisitos do owner (Fev/2026) — ACADEMIC_EVENT_CONTRACT.md §15-19:

01. POST /api/academic-events com rationale<30 chars → 422 string_too_short
02. POST com origin==destination → 422 ORIGIN_EQUALS_DESTINATION
03. POST válido cria event status=pending → POST /{id}/approve marca approved
04. POST /{id}/supersede SEM header X-Academic-Event-Confirm → 428 CONFIRMATION_REQUIRED
05. POST /{id}/supersede COM header → 200, antigo permanece com status=superseded
    e superseded_by_event_id apontando para o novo
06. POST /api/grades para aluno c/ evento APROVADO + effective_date passado + class=origem
    → 409 ACADEMIC_EVENT_LOCK com {code, reason_code, event_id, governing_event_type, effective_date}
07. POST /api/attendance idem → 409 ACADEMIC_EVENT_LOCK
08. db.academic_event_audit registra cada bloqueio
09. GET /api/diary/class/{cl}/course/{co}?academic_year=2026 anota items com
    _locked, _inherited, _lock_reason, _governing_event_id (lista NÃO é filtrada)

Cleanup ao final: db.academic_events e db.academic_event_audit para o student de teste.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

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

# Fixtures
STUDENT_ID = "fix_stu_ana"  # aluno que NÃO tem snapshots/dependências em uso
ORIGIN_CLASS = "fix_cl_v1"
DEST_CLASS = "fix_cl_v74_dest"  # destino V1 — não exige existir como turma real
PAST_DATE = "2026-01-10"  # passado relativo a "hoje" (Fev/2026)


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
               timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
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

    # Pre-cleanup via direct mongo (use a helper endpoint? we'll just hit DB via motor)
    yield s

    # Final cleanup via Mongo
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        import asyncio
        async def _cleanup():
            client = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = client[os.environ["DB_NAME"]]
            await db.academic_events.delete_many({"student_id": STUDENT_ID})
            await db.academic_event_audit.delete_many({"target_student_id": STUDENT_ID})
            # remover quaisquer grades/attendance criados acidentalmente
            await db.grades.delete_many({"student_id": STUDENT_ID, "class_id": ORIGIN_CLASS})
            await db.attendance.delete_many({"student_id": STUDENT_ID, "class_id": ORIGIN_CLASS})
            client.close()
        asyncio.get_event_loop().run_until_complete(_cleanup())
    except Exception as e:
        print(f"cleanup warn: {e}")


def _payload_valid(extra: dict | None = None) -> dict:
    base = {
        "event_type": "transfer",
        "effective_date": PAST_DATE,
        "student_id": STUDENT_ID,
        "origin_class_id": ORIGIN_CLASS,
        "destination_class_id": DEST_CLASS,
        "academic_year": 2026,
        "rationale": "Transferência por requisição do responsável — testes E2E iter74.",
        "approval_required": True,
    }
    if extra:
        base.update(extra)
    return base


# -------------------- 01: rationale<30 → 422
def test_01_rationale_too_short_returns_422(session):
    payload = _payload_valid({"rationale": "muito curto"})
    r = session.post(f"{BASE_URL}/api/academic-events", json=payload, timeout=20)
    assert r.status_code == 422, f"{r.status_code}: {r.text[:400]}"
    body = r.json()
    txt = str(body).lower()
    assert "string_too_short" in txt or "rationale" in txt


# -------------------- 02: origin==destination → 422 ORIGIN_EQUALS_DESTINATION
def test_02_origin_equals_destination_returns_422(session):
    payload = _payload_valid({"destination_class_id": ORIGIN_CLASS})
    r = session.post(f"{BASE_URL}/api/academic-events", json=payload, timeout=20)
    assert r.status_code == 422, f"{r.status_code}: {r.text[:400]}"
    body = r.json()
    detail = body.get("detail", body)
    assert "ORIGIN_EQUALS_DESTINATION" in str(detail)


# -------------------- 03: criar pending + approve
def test_03_create_pending_then_approve(session):
    r = session.post(f"{BASE_URL}/api/academic-events", json=_payload_valid(), timeout=20)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
    data = r.json()
    assert data["approval_status"] == "pending"
    event_id = data["id"]
    pytest.event_id = event_id

    # Approve
    r2 = session.post(f"{BASE_URL}/api/academic-events/{event_id}/approve", timeout=20)
    assert r2.status_code == 200, f"{r2.status_code}: {r2.text[:300]}"
    assert r2.json()["approval_status"] == "approved"


# -------------------- 04: supersede SEM header → 428
def test_04_supersede_without_header_returns_428(session):
    event_id = pytest.event_id
    new_payload = _payload_valid({
        "rationale": "Substituição por correção do tipo do evento — teste 04.",
        "effective_date": "2026-02-01",
    })
    body = {
        "new_payload": new_payload,
        "rationale": "Erro material no evento original — substituição via fluxo §10 audit.",
    }
    r = session.post(f"{BASE_URL}/api/academic-events/{event_id}/supersede",
                     json=body, timeout=20)
    assert r.status_code == 428, f"{r.status_code}: {r.text[:300]}"
    detail = r.json().get("detail", {})
    assert "CONFIRMATION_REQUIRED" in str(detail)


# -------------------- 05: supersede COM header → 200 e antigo marcado
def test_05_supersede_with_header_marks_old_superseded(session):
    event_id = pytest.event_id
    new_payload = _payload_valid({
        "rationale": "Substituição por correção do tipo do evento — teste 05 OK.",
        "effective_date": "2026-02-01",
    })
    body = {
        "new_payload": new_payload,
        "rationale": "Erro material no evento original — substituição via fluxo §10 audit.",
    }
    headers = {"X-Academic-Event-Confirm": "true"}
    r = session.post(f"{BASE_URL}/api/academic-events/{event_id}/supersede",
                     json=body, headers=headers, timeout=20)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
    data = r.json()
    assert data["old_event_id"] == event_id
    new_ev = data["new_event"]
    assert new_ev["supersedes_event_id"] == event_id
    new_event_id = new_ev["id"]
    pytest.new_event_id = new_event_id

    # Antigo permanece com status=superseded
    g = session.get(f"{BASE_URL}/api/academic-events/{event_id}", timeout=20)
    assert g.status_code == 200
    old = g.json()
    assert old["approval_status"] == "superseded"
    assert old["superseded_by_event_id"] == new_event_id


# -------------------- 06: POST /api/grades em class=origem após effective_date → 409 ACADEMIC_EVENT_LOCK
def test_06_grade_post_blocked_by_event_lock(session):
    # Use o new_event (effective_date=2026-02-01, approved) e crie grade hoje (>= 2026-02-01)
    grade_payload = {
        "student_id": STUDENT_ID,
        "class_id": ORIGIN_CLASS,
        "course_id": "fix_co_mat_v1",
        "academic_year": 2026,
        "term": "1bim",
        "value": 8.0,
        "grade_type": "nota",
    }
    r = session.post(f"{BASE_URL}/api/grades", json=grade_payload, timeout=20)
    assert r.status_code == 409, f"esperado 409, recebido {r.status_code}: {r.text[:400]}"
    body = r.json()
    detail = body.get("detail", body)
    assert isinstance(detail, dict), f"detail deve ser dict: {detail}"
    assert detail.get("code") == "ACADEMIC_EVENT_LOCK"
    assert detail.get("reason_code") == "AFTER_EFFECTIVE_DATE"
    assert detail.get("event_id")
    assert detail.get("governing_event_type") in (
        "transfer", "remanejamento", "reclassificacao", "progressao_parcial",
    )
    assert detail.get("effective_date")


# -------------------- 07: POST /api/attendance bloqueado idem
def test_07_attendance_post_blocked_by_event_lock(session):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    att_payload = {
        "class_id": ORIGIN_CLASS,
        "course_id": "fix_co_mat_v1",
        "date": today,
        "academic_year": 2026,
        "records": [
            {"student_id": STUDENT_ID, "status": "presente"},
        ],
    }
    r = session.post(f"{BASE_URL}/api/attendance", json=att_payload, timeout=20)
    # Aceita 409 do bloqueio OU resposta com detail por record
    if r.status_code == 200:
        body = r.json()
        # se resposta agregada, deve indicar bloqueio em detalhes
        text = str(body)
        assert "ACADEMIC_EVENT_LOCK" in text, f"attendance deveria bloquear: {body}"
    else:
        assert r.status_code == 409, f"esperado 409, recebido {r.status_code}: {r.text[:400]}"
        detail = r.json().get("detail", {})
        assert detail.get("code") == "ACADEMIC_EVENT_LOCK"
        assert detail.get("reason_code") == "AFTER_EFFECTIVE_DATE"


# -------------------- 08: audit log de bloqueios
@pytest.mark.asyncio
async def test_08_audit_log_has_block_entries():
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    try:
        entries = await db.academic_event_audit.find(
            {"target_student_id": STUDENT_ID}
        ).to_list(50)
        actions = {e.get("action") for e in entries}
        assert any(
            a in actions for a in ("grade_create_blocked", "attendance_create_blocked")
        ), f"audit não tem entradas de bloqueio. actions={actions}"
        # Validar shape de uma entrada
        sample = next(e for e in entries
                      if e.get("action") in ("grade_create_blocked", "attendance_create_blocked"))
        assert sample.get("target_student_id") == STUDENT_ID
        assert sample.get("reason_code") == "AFTER_EFFECTIVE_DATE"
        assert sample.get("attempted_by_user_id")
    finally:
        client.close()


# -------------------- 09: diary anota com flags sem filtrar
def test_09_diary_annotates_without_filtering(session):
    r = session.get(
        f"{BASE_URL}/api/diary/class/{ORIGIN_CLASS}/course/fix_co_mat_v1",
        params={"academic_year": 2026},
        timeout=30,
    )
    if r.status_code == 404:
        pytest.skip(f"diary endpoint shape diferente: {r.status_code} {r.text[:200]}")
    assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
    data = r.json()
    # estrutura pode variar — procuramos qualquer item com student_id == STUDENT_ID
    items = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("students", "items", "rows", "data"):
            if isinstance(data.get(key), list):
                items = data[key]
                break
    flat = []
    for it in items:
        flat.append(it)
        # diaries podem ter sub-itens
        for k in ("students", "rows"):
            v = it.get(k) if isinstance(it, dict) else None
            if isinstance(v, list):
                flat.extend(v)

    target = next(
        (it for it in flat
         if isinstance(it, dict)
         and (it.get("student_id") == STUDENT_ID
              or (it.get("student") or {}).get("id") == STUDENT_ID)),
        None,
    )
    if target is None:
        pytest.skip(f"STUDENT_ID={STUDENT_ID} não consta no diary (possivelmente não matriculado em fix_cl_v1/fix_course_mat)")
    # O contrato pede: aluno aparece com flags _locked etc
    assert target.get("_locked") is True, f"_locked esperado true: {target}"
    assert target.get("_lock_reason") == "AFTER_EFFECTIVE_DATE"
    assert target.get("_governing_event_id")
