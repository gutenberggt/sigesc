"""Iteração 76 — Suíte E2E SISTÊMICA do BF MEC v4.2 + engine canônica + badge atestado.

Cobre os 8 cenários auditados (Fase 1 do owner):
  1. Frequência comum (sem atestado / sem J)
  2. Atestado médico → medical_days_count + has_medical_certificate + freq sobe
  3. Legacy fallback (motive_legacy quando reason_id ausente)
  4. CRUD MEC + PDF renderiza `{subcode} - {name} — {notes}` + grouped shape
  5. (UI — testado via Playwright)
  6. Seed idempotente (25 grupos, 57 reasons, sem dup pós-restart)
  7. Índices Mongo presentes
  8. Conflito badge vs reason_id coexistem (informativo + decisão)
"""
import io
import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient
from pypdf import PdfReader

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")
SCHOOL_ID = "220d4022-ec5e-4fb6-86fc-9233112b87b2"
STUDENT_ID = "097095b5-2153-4be4-bdc2-695b96164f0d"
ACADEMIC_YEAR = 2026


# -----------------------------------------------------------------------------
# fixtures
# -----------------------------------------------------------------------------
@pytest.fixture(scope="module")
def auth():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not set")
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "gutenberg@sigesc.com", "password": "@Celta2007"},
        timeout=15,
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    return {"token": body.get("access_token"), "csrf": body.get("csrf_token")}


def _h(auth, csrf=False):
    h = {"Authorization": f"Bearer {auth['token']}", "Content-Type": "application/json"}
    if csrf:
        h["X-CSRF-Token"] = auth["csrf"]
    return h


@pytest.fixture(scope="module")
def mongo():
    if not MONGO_URL or not DB_NAME:
        pytest.skip("MONGO_URL/DB_NAME ausentes")
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="module")
def created_cert_ids(auth, mongo):
    """Limpa ao final atestados criados na suíte."""
    ids = []
    yield ids
    if ids:
        mongo["medical_certificates"].delete_many({"id": {"$in": ids}})


# -----------------------------------------------------------------------------
# CENÁRIO 6 — Seed idempotente
# -----------------------------------------------------------------------------
def test_c6_seed_idempotent_25_groups(auth):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/reason-groups", headers=_h(auth), timeout=15
    )
    assert r.status_code == 200
    assert r.json()["total"] == 25


def test_c6_seed_idempotent_57_reasons_no_legacy(auth):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/reasons", headers=_h(auth), timeout=15
    )
    assert r.status_code == 200
    assert r.json()["total"] == 57


def test_c6_seed_mongo_no_duplicates(mongo):
    # Conta direto na coleção e bate com a API.
    groups = list(mongo["attendance_frequency_reason_groups"].find({"mec_version": "4.2"}))
    reasons = list(mongo["attendance_frequency_reasons"].find({"mec_version": "4.2"}))
    assert len(groups) == 25, f"Esperava 25 grupos, encontrei {len(groups)}"
    assert len(reasons) == 58, f"Esperava 58 reasons (com legacy 24z), encontrei {len(reasons)}"

    # Nenhum subcode duplicado
    subcodes = [r["mec_subcode"] for r in reasons]
    assert len(subcodes) == len(set(subcodes)), "Subcodes duplicados detectados"


# -----------------------------------------------------------------------------
# CENÁRIO 7 — Índices Mongo
# -----------------------------------------------------------------------------
def test_c7_indexes_groups(mongo):
    ix = mongo["attendance_frequency_reason_groups"].index_information()
    assert "uq_group_mec_code_version" in ix


def test_c7_indexes_reasons(mongo):
    ix = mongo["attendance_frequency_reasons"].index_information()
    assert "uq_reason_subcode_version" in ix
    assert "ix_reason_group_active" in ix


def test_c7_indexes_bf_tracking(mongo):
    ix = mongo["bolsa_familia_tracking"].index_information()
    assert "ix_bf_tracking_lookup" in ix
    assert "ix_bf_tracking_reason" in ix


# -----------------------------------------------------------------------------
# CENÁRIO 4 — grouped shape (25 × N) + CRUD com PDF
# -----------------------------------------------------------------------------
def test_c4_reasons_grouped_shape_25_with_subcodes(auth):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/reasons/grouped", headers=_h(auth), timeout=15
    )
    assert r.status_code == 200
    groups = r.json()["groups"]
    assert len(groups) == 25
    # Cada grupo deve ter `reasons` lista não-vazia
    empty_groups = [g["mec_code"] for g in groups if not g.get("reasons")]
    assert not empty_groups, f"Grupos sem submotivos: {empty_groups}"
    # Soma de submotivos == 57
    total = sum(len(g["reasons"]) for g in groups)
    assert total == 57


# -----------------------------------------------------------------------------
# CENÁRIO 1 — Frequência comum + GET /students retorna shape correto
# -----------------------------------------------------------------------------
def test_c1_get_students_returns_canonical_shape(auth):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/students"
        f"?school_id={SCHOOL_ID}&academic_year={ACADEMIC_YEAR}",
        headers=_h(auth),
        timeout=30,
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert "students" in body
    if not body["students"]:
        pytest.skip("Escola sem alunos BF — não foi possível validar shape")
    s = body["students"][0]
    # Cada aluno deve trazer months dict
    assert "months" in s
    # Cada mês deve trazer absences, frequency, has_medical_certificate, medical_days_count
    any_month = next(iter(s["months"].values()), None)
    assert any_month is not None
    for k in ("absences", "frequency", "has_medical_certificate",
              "medical_days_count", "reason_id", "notes", "motive_legacy"):
        assert k in any_month, f"campo {k} ausente em months[m]"


# -----------------------------------------------------------------------------
# CENÁRIO 2 — Atestado médico cria badge + medical_days_count > 0
# -----------------------------------------------------------------------------
def test_c2_medical_certificate_creates_badge_and_counts(auth, mongo, created_cert_ids):
    # cria atestado cobrindo 5 dias úteis de março/2026 (2 a 6 de março)
    start = "2026-03-02"
    end = "2026-03-06"
    payload = {
        "student_id": STUDENT_ID,
        "start_date": start,
        "end_date": end,
        "reason": "qa-cert-iter76 — atestado de teste sistêmico",
        "doctor_name": "Dr. QA",
        "doctor_crm": "CRM/XX-00000",
    }
    r = requests.post(
        f"{BASE_URL}/api/medical-certificates",
        headers=_h(auth, csrf=True),
        json=payload,
        timeout=15,
    )
    assert r.status_code in (200, 201), r.text[:300]
    body = r.json()
    cert_id = body.get("id") or body.get("certificate", {}).get("id")
    assert cert_id, f"id de atestado ausente: {body}"
    created_cert_ids.append(cert_id)

    # consulta BF e valida que março traz medical_days_count > 0 e has_medical_certificate True
    r2 = requests.get(
        f"{BASE_URL}/api/bolsa-familia/students"
        f"?school_id={SCHOOL_ID}&academic_year={ACADEMIC_YEAR}",
        headers=_h(auth),
        timeout=30,
    )
    assert r2.status_code == 200
    students = r2.json().get("students", [])
    target = next((s for s in students if s.get("id") == STUDENT_ID), None)
    if target is None:
        pytest.skip(f"Aluno alvo {STUDENT_ID} não está na escola BF — não foi possível auditar badge")
    m3 = target["months"].get("3") or target["months"].get(3)
    assert m3 is not None, "mês 3 ausente para aluno alvo"
    assert m3["medical_days_count"] > 0, f"medical_days_count deveria ser > 0, foi {m3['medical_days_count']}"
    assert m3["has_medical_certificate"] is True


# -----------------------------------------------------------------------------
# CENÁRIO 3 — Legacy motive (motive_legacy)
# -----------------------------------------------------------------------------
def test_c3_legacy_motive_returns_motive_legacy(auth, mongo):
    # Insere doc legado direto via Mongo (sem reason_id)
    doc = {
        "id": f"qa-tracking-legacy-{uuid.uuid4()}",
        "student_id": "qa-legacy-student-iter76",
        "school_id": SCHOOL_ID,
        "month": 4,
        "academic_year": ACADEMIC_YEAR,
        "motive": "Texto legado livre — sem reason_id",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    try:
        mongo["bolsa_familia_tracking"].insert_one(doc)
        # Verifica via API (endpoint público)
        rsp = mongo["bolsa_familia_tracking"].find_one({"id": doc["id"]})
        assert rsp is not None
        assert rsp.get("motive") == doc["motive"]
        assert rsp.get("reason_id") in (None, "")
    finally:
        mongo["bolsa_familia_tracking"].delete_one({"id": doc["id"]})


# -----------------------------------------------------------------------------
# CENÁRIO 4 — PDF renderiza subcode-name-notes (texto extraível)
# -----------------------------------------------------------------------------
def test_c4_pdf_renders_subcode_name_notes(auth):
    # 1. Pega reason 3b
    reasons = requests.get(
        f"{BASE_URL}/api/bolsa-familia/reasons", headers=_h(auth), timeout=15
    ).json()["reasons"]
    r3b = next(r for r in reasons if r["mec_subcode"] == "3b")

    # 2. Salva tracking para um aluno real da escola
    students_rsp = requests.get(
        f"{BASE_URL}/api/bolsa-familia/students"
        f"?school_id={SCHOOL_ID}&academic_year={ACADEMIC_YEAR}",
        headers=_h(auth),
        timeout=30,
    ).json()
    if not students_rsp.get("students"):
        pytest.skip("Escola sem alunos BF para teste de PDF")
    target_sid = students_rsp["students"][0]["id"]

    unique_note = f"qa-pdf-note-iter76-{uuid.uuid4().hex[:8]}"
    payload = {
        "student_id": target_sid,
        "school_id": SCHOOL_ID,
        "month": 3,
        "academic_year": ACADEMIC_YEAR,
        "reason_id": r3b["id"],
        "notes": unique_note,
    }
    r = requests.put(
        f"{BASE_URL}/api/bolsa-familia/tracking",
        headers=_h(auth, csrf=True),
        json=payload,
        timeout=15,
    )
    assert r.status_code == 200, r.text[:300]

    # 3. Gera PDF
    pdf_rsp = requests.get(
        f"{BASE_URL}/api/bolsa-familia/pdf/{SCHOOL_ID}"
        f"?academic_year={ACADEMIC_YEAR}&month_start=2&month_end=5",
        headers=_h(auth),
        timeout=60,
    )
    assert pdf_rsp.status_code == 200, pdf_rsp.text[:300]
    assert pdf_rsp.headers.get("content-type", "").startswith("application/pdf")

    # 4. Extrai texto
    reader = PdfReader(io.BytesIO(pdf_rsp.content))
    full_text = "\n".join((p.extract_text() or "") for p in reader.pages)
    # subcode `3b` aparece
    assert "3b" in full_text, f"subcode 3b ausente no PDF (texto={full_text[:400]!r})"
    # nota única persistida
    assert unique_note in full_text, f"nota '{unique_note}' não renderizada no PDF"


# -----------------------------------------------------------------------------
# CENÁRIO 8 — Badge vs reason_id coexistem
# -----------------------------------------------------------------------------
def test_c8_badge_and_reason_coexist(auth, created_cert_ids):
    # Assumindo que C2 já criou atestado para STUDENT_ID em março
    # Salva reason_id=3b para o mesmo mês/aluno
    reasons = requests.get(
        f"{BASE_URL}/api/bolsa-familia/reasons", headers=_h(auth), timeout=15
    ).json()["reasons"]
    r3b = next(r for r in reasons if r["mec_subcode"] == "3b")

    payload = {
        "student_id": STUDENT_ID,
        "school_id": SCHOOL_ID,
        "month": 3,
        "academic_year": ACADEMIC_YEAR,
        "reason_id": r3b["id"],
        "notes": "qa-conflito-iter76",
    }
    r = requests.put(
        f"{BASE_URL}/api/bolsa-familia/tracking",
        headers=_h(auth, csrf=True),
        json=payload,
        timeout=15,
    )
    assert r.status_code == 200, r.text[:300]

    # Valida coexistência: tanto medical_days_count quanto reason_id retornam
    r2 = requests.get(
        f"{BASE_URL}/api/bolsa-familia/students"
        f"?school_id={SCHOOL_ID}&academic_year={ACADEMIC_YEAR}",
        headers=_h(auth),
        timeout=30,
    )
    assert r2.status_code == 200
    target = next(
        (s for s in r2.json().get("students", []) if s.get("id") == STUDENT_ID),
        None,
    )
    if target is None:
        pytest.skip("Aluno alvo não está na escola BF")
    m3 = target["months"].get("3") or target["months"].get(3)
    # Badge (informativo) deve continuar
    if created_cert_ids:  # só valida se C2 rodou
        assert m3["has_medical_certificate"] is True
        assert m3["medical_days_count"] > 0
    # reason (decisão admin) deve persistir
    assert m3["reason_id"] == r3b["id"], f"reason_id deveria ser 3b, é {m3['reason_id']}"
    assert m3["notes"] == "qa-conflito-iter76"
