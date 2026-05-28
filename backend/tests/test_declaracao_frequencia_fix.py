"""
E2E test — Declaração de Frequência (Iter 76 bug fix).

Bug: o endpoint `/api/documents/declaracao-frequencia/{student_id}` consultava
`db.attendance.find({"student_id": student_id, ...})` mas esse campo NÃO existe
no top-level. O schema real é `{class_id, date, records: [{student_id, status}]}`.
Resultado: lista vazia → 0 faltas → PDF sempre exibia 100%.

Fix: query agora usa `records.student_id` e itera os subdocumentos.

Testes cobertos:
  1) Sem faltas → 100% (sanidade).
  2) 3 faltas inseridas → percentual <100% (e exato dentro da margem letiva).
  3) Atestado médico cobrindo a data de falta → essa falta deve ser
     descontada (não conta como falta).
"""
from __future__ import annotations

import os
import uuid
import requests
import pytest
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import re

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "https://mutacoes-criticas.preview.emergentagent.com")
    .rstrip("/")
)
EMAIL = "gutenberg@sigesc.com"
PASSWORD = "@Celta2007"
TENANT = "fix_mant_v1"
STU_FELIPE = "fix_stu_felipe"
CLASS_V1 = "fix_cl_v1"
YEAR = 2026


@pytest.fixture(scope="module")
def auth():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200
    d = r.json()
    tok = d.get("access_token") or d.get("token")
    csrf = d.get("csrf_token") or ""
    s.headers.update({
        "Authorization": f"Bearer {tok}",
        "X-CSRF-Token": csrf,
        "X-Mantenedora-Id": TENANT,
        "Content-Type": "application/json",
    })
    if s.get(f"{BASE_URL}/api/students/{STU_FELIPE}", timeout=10).status_code == 404:
        pytest.skip("Fixture seed_dependency_diary_fixture ausente.")
    return s


@pytest.fixture
def db():
    mongo_url = os.environ.get("MONGO_URL")
    if not mongo_url:
        pytest.skip("MONGO_URL não disponível para acesso direto.")
    db_name = os.environ.get("DB_NAME", "sigesc")
    client = AsyncIOMotorClient(mongo_url)
    yield client[db_name]
    client.close()


def _extract_pdf_text(content: bytes) -> str:
    """Helper opcional via pdfplumber. Se indisponível, retorna ''."""
    try:
        import pdfplumber
        from io import BytesIO
        with pdfplumber.open(BytesIO(content)) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception:
        return ""


def _percent_in_pdf(text: str) -> float | None:
    m = re.search(r"Percentual de frequência:\s*([\d.,]+)\s*%", text)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def _absent_days_in_pdf(text: str) -> int | None:
    m = re.search(r"Dias de (?:falta|ausência)s?:\s*(\d+)", text)
    if m:
        return int(m.group(1))
    # Fallback: total - presença
    m1 = re.search(r"Total de dias letivos:\s*(\d+)", text)
    m2 = re.search(r"Dias de presença:\s*(\d+)", text)
    if m1 and m2:
        return int(m1.group(1)) - int(m2.group(1))
    return None


def test_declaracao_frequencia_baseline_no_faltas(auth):
    """Sem faltas no seed → 100% (sanidade)."""
    r = auth.get(f"{BASE_URL}/api/documents/declaracao-frequencia/{STU_FELIPE}",
                 params={"academic_year": YEAR}, timeout=60)
    assert r.status_code == 200, r.text[:300]
    text = _extract_pdf_text(r.content)
    if not text:
        pytest.skip("pdfplumber indisponível — apenas valida HTTP.")
    pct = _percent_in_pdf(text)
    assert pct is not None, f"Percentual não localizado: {text[:300]}"
    assert pct == 100.0, f"Esperava 100% (sem faltas no seed). got {pct}%"


def test_declaracao_frequencia_with_faltas(auth, db):
    """Insere 3 faltas, valida que percentual cai abaixo de 100% e dias
    de falta = 3."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    inserted_ids = []
    base_date = ["2026-02-09", "2026-02-10", "2026-02-11"]
    try:
        for d in base_date:
            doc = {
                "id": str(uuid.uuid4()),
                "class_id": CLASS_V1,
                "date": d,
                "academic_year": YEAR,
                "attendance_type": "daily",
                "period": "regular",
                "records": [{"student_id": STU_FELIPE, "status": "F"}],
            }
            loop.run_until_complete(db.attendance.insert_one(doc))
            inserted_ids.append(doc["id"])

        r = auth.get(f"{BASE_URL}/api/documents/declaracao-frequencia/{STU_FELIPE}",
                     params={"academic_year": YEAR}, timeout=60)
        assert r.status_code == 200
        text = _extract_pdf_text(r.content)
        if not text:
            pytest.skip("pdfplumber indisponível.")
        pct = _percent_in_pdf(text)
        absent_days = _absent_days_in_pdf(text)
        assert pct is not None and pct < 100.0, \
            f"Percentual deve cair abaixo de 100% após faltas. got {pct}%"
        assert absent_days == 3, \
            f"Esperava 3 dias de falta no PDF. got {absent_days}. text={text[:500]}"
    finally:
        loop.run_until_complete(
            db.attendance.delete_many({"id": {"$in": inserted_ids}})
        )
        loop.close()


def test_declaracao_frequencia_medical_certificate_overrides_falta(auth, db):
    """Insere 2 faltas + atestado médico cobrindo 1 dia. Apenas 1 falta deve
    persistir no cálculo."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    inserted_att = []
    inserted_cert = None
    try:
        for d in ["2026-02-16", "2026-02-17"]:
            doc = {
                "id": str(uuid.uuid4()),
                "class_id": CLASS_V1,
                "date": d,
                "academic_year": YEAR,
                "attendance_type": "daily",
                "period": "regular",
                "records": [{"student_id": STU_FELIPE, "status": "F"}],
            }
            loop.run_until_complete(db.attendance.insert_one(doc))
            inserted_att.append(doc["id"])

        cert = {
            "id": str(uuid.uuid4()),
            "student_id": STU_FELIPE,
            "start_date": "2026-02-16",
            "end_date": "2026-02-16",
            "reason": "test",
        }
        loop.run_until_complete(db.medical_certificates.insert_one(cert))
        inserted_cert = cert["id"]

        r = auth.get(f"{BASE_URL}/api/documents/declaracao-frequencia/{STU_FELIPE}",
                     params={"academic_year": YEAR}, timeout=60)
        assert r.status_code == 200
        text = _extract_pdf_text(r.content)
        if not text:
            pytest.skip("pdfplumber indisponível.")
        absent_days = _absent_days_in_pdf(text)
        assert absent_days == 1, \
            f"Esperava 1 dia de falta (atestado cobre 1 das 2). got {absent_days}"
    finally:
        loop.run_until_complete(
            db.attendance.delete_many({"id": {"$in": inserted_att}})
        )
        if inserted_cert:
            loop.run_until_complete(
                db.medical_certificates.delete_one({"id": inserted_cert})
            )
        loop.close()
