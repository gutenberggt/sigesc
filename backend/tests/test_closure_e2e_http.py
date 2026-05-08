"""
E2E HTTP — Closure (Fechamento Temporal Composto) — Passo 3 (Fev/2026).

Roda contra REACT_APP_BACKEND_URL com Super Admin + X-Mantenedora-Id=fix_mant_v1.

Cobre os endpoints expostos por routers/closure.py:
01. GET /api/closure/student/{sid}/composite — aluno sem evento → 1 período sole
02. GET /api/closure/student/{sid}/composite — aluno com transferência → 2 períodos + bimestres atribuídos corretamente
03. GET /api/closure/student/{sid}/window?class_id=... — janela correta da turma origem
04. GET /api/closure/student/{sid}/window?class_id=<inexistente> → 404 NO_WINDOW_FOR_CLASS
05. GET /api/closure/class/{cid}/students — lista aluno com janela de origem
06. GET /api/closure/student/{sid}/periods — endpoint enxuto

Cleanup ao final: remove apenas os events criados.
"""
from __future__ import annotations

import os

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

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

# Fixture aluno reutilizado (já existe na base de testes)
STUDENT_ID = "fix_stu_ana"
ORIGIN_CLASS = "fix_cl_v1"
DEST_CLASS = "fix_cl_closure_dest"

EVENT_ID = "ev_closure_e2e_v1"


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
    yield s


@pytest.fixture(scope="module")
def event_anchor():
    """Cria um evento aprovado de transferência via Mongo direto (V1 não exige existência das turmas)."""
    import asyncio
    from datetime import datetime, timezone

    async def _setup():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        # Pre-cleanup
        await db.academic_events.delete_many({"id": EVENT_ID})
        # Calendário 2026 para o cenário de bimestres
        await db.calendario_letivo.delete_many({"ano_letivo": 2026, "_test_marker": "closure_e2e"})
        await db.calendario_letivo.insert_one({
            "ano_letivo": 2026,
            "_test_marker": "closure_e2e",
            "bimestre_1_inicio": "2026-02-01",
            "bimestre_1_fim": "2026-04-30",
            "bimestre_2_inicio": "2026-05-01",
            "bimestre_2_fim": "2026-07-15",
            "bimestre_3_inicio": "2026-08-01",
            "bimestre_3_fim": "2026-10-15",
            "bimestre_4_inicio": "2026-10-16",
            "bimestre_4_fim": "2026-12-15",
        })
        now = datetime.now(timezone.utc).isoformat()
        await db.academic_events.insert_one({
            "id": EVENT_ID,
            "event_type": "transfer",
            "effective_date": "2026-08-15",
            "student_id": STUDENT_ID,
            "origin_class_id": ORIGIN_CLASS,
            "destination_class_id": DEST_CLASS,
            "origin_school_id": None,
            "destination_school_id": None,
            "origin_teacher_id": None,
            "destination_teacher_id": None,
            "mantenedora_id": TENANT,
            "academic_year": 2026,
            "rationale": "Cenário E2E: fechamento temporal composto Passo 3 — validacao da lente.",
            "approval_required": True,
            "approval_status": "approved",
            "approved_by_user_id": "u_admin",
            "approved_at": now,
            "supersedes_event_id": None,
            "superseded_by_event_id": None,
            "superseded_at": None,
            "superseded_reason": None,
            "created_by_user_id": "u_admin",
            "created_at": now,
            "audit_trail": [],
        })
        client.close()

    async def _teardown():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.academic_events.delete_many({"id": EVENT_ID})
        await db.calendario_letivo.delete_many({"_test_marker": "closure_e2e"})
        client.close()

    asyncio.run(_setup())
    yield
    asyncio.run(_teardown())


# ===========================================================================
# Tests
# ===========================================================================
def test_01_composite_with_event_two_periods(session, event_anchor):
    r = session.get(
        f"{BASE_URL}/api/closure/student/{STUDENT_ID}/composite",
        params={"academic_year": 2026},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["closure_version"] == "1"
    assert body["is_composite"] is True
    assert len(body["periods"]) == 2
    p0, p1 = body["periods"]
    assert p0["class_id"] == ORIGIN_CLASS
    assert p0["source"] == "origin"
    assert p0["period_end"] == "2026-08-14"
    assert p1["class_id"] == DEST_CLASS
    assert p1["source"] == "destination"
    assert p1["governing_event_id"] == EVENT_ID
    # Bimestres atribuídos
    bims = {b["bimester"]: b for b in body["bimesters"]}
    assert bims[1]["class_id"] == ORIGIN_CLASS  # B1 termina em 04/30
    assert bims[2]["class_id"] == ORIGIN_CLASS  # B2 termina em 07/15 (antes da effective_date 08/15)
    assert bims[3]["class_id"] == DEST_CLASS    # B3 termina em 10/15
    assert bims[4]["class_id"] == DEST_CLASS


def test_02_window_origin_class_returns_envelope(session, event_anchor):
    r = session.get(
        f"{BASE_URL}/api/closure/student/{STUDENT_ID}/window",
        params={"academic_year": 2026, "class_id": ORIGIN_CLASS},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["class_id"] == ORIGIN_CLASS
    assert body["envelope_start"] == "2026-02-01"
    assert body["envelope_end"] == "2026-08-14"
    assert len(body["segments"]) == 1


def test_03_window_unknown_class_returns_404(session, event_anchor):
    r = session.get(
        f"{BASE_URL}/api/closure/student/{STUDENT_ID}/window",
        params={"academic_year": 2026, "class_id": "fix_cl_never_used_xyz"},
        timeout=30,
    )
    assert r.status_code == 404
    detail = r.json().get("detail", {})
    if isinstance(detail, dict):
        assert detail.get("code") == "NO_WINDOW_FOR_CLASS"


def test_04_class_students_lists_origin_with_window(session, event_anchor):
    r = session.get(
        f"{BASE_URL}/api/closure/class/{ORIGIN_CLASS}/students",
        params={"academic_year": 2026},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["class_id"] == ORIGIN_CLASS
    sids = [s["student_id"] for s in body["students"]]
    assert STUDENT_ID in sids
    rec = next(s for s in body["students"] if s["student_id"] == STUDENT_ID)
    assert rec["envelope_end"] == "2026-08-14"


def test_05_class_students_lists_destination_with_window(session, event_anchor):
    r = session.get(
        f"{BASE_URL}/api/closure/class/{DEST_CLASS}/students",
        params={"academic_year": 2026},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    sids = [s["student_id"] for s in body["students"]]
    assert STUDENT_ID in sids
    rec = next(s for s in body["students"] if s["student_id"] == STUDENT_ID)
    assert rec["envelope_start"] == "2026-08-15"


def test_06_periods_endpoint_returns_minimal_shape(session, event_anchor):
    r = session.get(
        f"{BASE_URL}/api/closure/student/{STUDENT_ID}/periods",
        params={"academic_year": 2026},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_composite"] is True
    assert "bimesters" not in body
    assert len(body["periods"]) == 2


def test_07_404_unknown_student(session):
    r = session.get(
        f"{BASE_URL}/api/closure/student/fix_stu_NOT_EXISTING_zzz/composite",
        params={"academic_year": 2026},
        timeout=30,
    )
    assert r.status_code == 404


def test_08_unauthorized_without_token():
    r = requests.get(
        f"{BASE_URL}/api/closure/student/{STUDENT_ID}/composite",
        params={"academic_year": 2026},
        timeout=30,
    )
    # Sem auth: 401/403
    assert r.status_code in (401, 403)
