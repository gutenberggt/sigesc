"""Fase 3C (Fev/2026) — Migração legacy → MEC estruturado.

Valida `services/bf_legacy_migration.py` + endpoints:
  - `classify_legacy_text` mapeia keywords PT-BR para subcódigos MEC.
  - Fallback `24z` quando nada matchea.
  - Preview NÃO persiste.
  - Apply é idempotente (não re-migra docs já estruturados).
  - Confidence respeita o limiar configurado.
"""
import os
import asyncio
from datetime import datetime, timezone

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

from services.bf_legacy_migration import (
    classify_legacy_text,
    LEGACY_UNCLASSIFIED_SUBCODE,
    ENGINE_VERSION,
)

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASS = "@Celta2007"
QA_PREFIX = "qa-legacy-"
ACADEMIC_YEAR = 2094


# ============================================================================
# UNIT — engine pura
# ============================================================================

@pytest.mark.parametrize("text,expected_subcode", [
    ("Aluno com atestado médico", "1a"),
    ("Está doente", "1a"),
    ("Gripe forte", "1a"),
    ("Tinha consulta no hospital", "1a"),
    ("Problemas psicológicos", "1b"),
    ("Em tratamento de depressão", "1b"),
    ("Pré-natal", "1c"),
    ("Óbito do pai", "2b"),
    ("Faleceu o avô", "2b"),
    ("Mãe doente", "2a"),
    ("Enchente na cidade", "3a"),
    ("Faltou transporte escolar", "3b"),
    ("Ônibus quebrou", "3b"),
    ("Estrada interditada por causa da lama", "3c"),
    ("Mora longe da escola", "3f"),
    ("Aluno suspenso", "4a"),
    ("Viagem escolar/olimpíada", "5a"),
    ("Sofreu bullying", "6a"),
    ("Gravidez de risco", "8a"),
    ("Grávida", "8b"),
    ("Situação de rua", "9a"),
    ("Trabalho infantil", "10b"),
    ("Briga na escola - violência escolar", "11a"),
    ("Menor aprendiz", "12d"),
    ("Está fazendo estágio", "12b"),
    ("Abuso sexual", "13a"),
    ("Desmotivado pelos estudos", "14a"),
    ("Abandonou a escola", "15a"),
    ("Separação dos pais", "16a"),
    ("Cuidar dos irmãos menores", "16b"),
    ("Negligência familiar", "16d"),
    ("Sem uniforme", "16e"),
    ("Sem material escolar", "16f"),
    ("Sem certidão de nascimento", "17a"),
    ("Sem vaga", "19a"),
    ("Greve dos professores", "20a"),
    ("Escola fechada para reforma", "20c"),
    ("Sem merenda", "20d"),
    ("Aluno não localizado", "21a"),
    ("Calamidade pública", "22a"),
    ("Aluno preso na FUNASE", "23a"),
])
def test_classify_legacy_keyword_matches(text, expected_subcode):
    result = classify_legacy_text(text)
    assert result["suggested_subcode"] == expected_subcode, (
        f"texto '{text}' esperava {expected_subcode}, obteve {result['suggested_subcode']}"
    )
    assert result["matched"] is True
    assert result["confidence"] > 0.0


def test_classify_fallback_for_random_text():
    result = classify_legacy_text("blablabla xyz abc 123")
    assert result["matched"] is False
    assert result["fallback_used"] is True
    assert result["suggested_subcode"] == LEGACY_UNCLASSIFIED_SUBCODE
    assert result["confidence"] == 0.0


def test_classify_empty_text():
    for t in ["", "   ", None]:
        result = classify_legacy_text(t)
        assert result["fallback_used"] is True
        assert result["suggested_subcode"] == LEGACY_UNCLASSIFIED_SUBCODE


def test_classify_is_accent_insensitive():
    """'óbito' e 'obito' devem dar o mesmo match."""
    a = classify_legacy_text("Óbito do pai")
    b = classify_legacy_text("obito do pai")
    assert a["suggested_subcode"] == b["suggested_subcode"] == "2b"


def test_classify_engine_version_constant():
    assert ENGINE_VERSION == "1.0"


# ============================================================================
# E2E — endpoints HTTP
# ============================================================================

@pytest.fixture(scope="module")
def auth():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not set")
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        timeout=15,
    )
    body = r.json()
    return {"token": body["access_token"], "csrf": body["csrf_token"]}


def _h(auth, csrf=False):
    h = {"Authorization": f"Bearer {auth['token']}"}
    if csrf:
        h["X-CSRF-Token"] = auth["csrf"]
    return h


@pytest.fixture
def seeded_legacy():
    """Pré-popula trackings legacy com textos variados."""
    async def _setup():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.bolsa_familia_tracking.delete_many({"student_id": {"$regex": f"^{QA_PREFIX}"}})
        now = datetime.now(timezone.utc).isoformat()
        docs = [
            {"student_id": f"{QA_PREFIX}1", "school_id": "sch", "month": "3",
             "academic_year": ACADEMIC_YEAR, "reason_id": None,
             "motive_legacy": "Aluno com atestado médico", "updated_at": now},
            {"student_id": f"{QA_PREFIX}2", "school_id": "sch", "month": "3",
             "academic_year": ACADEMIC_YEAR, "reason_id": None,
             "motive_legacy": "Faltou transporte escolar", "updated_at": now},
            {"student_id": f"{QA_PREFIX}3", "school_id": "sch", "month": "4",
             "academic_year": ACADEMIC_YEAR, "reason_id": None,
             "motive_legacy": "Óbito do pai", "updated_at": now},
            {"student_id": f"{QA_PREFIX}4", "school_id": "sch", "month": "4",
             "academic_year": ACADEMIC_YEAR, "reason_id": None,
             "motive_legacy": "xyz blabla random", "updated_at": now},  # fallback
            {"student_id": f"{QA_PREFIX}5", "school_id": "sch", "month": "5",
             "academic_year": ACADEMIC_YEAR, "reason_id": "should-be-skipped",
             "motive_legacy": "Já estruturado", "updated_at": now},  # já tem reason_id
        ]
        await db.bolsa_familia_tracking.insert_many(docs)
    asyncio.run(_setup())
    yield
    async def _teardown():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.bolsa_familia_tracking.delete_many({"student_id": {"$regex": f"^{QA_PREFIX}"}})
    asyncio.run(_teardown())


def test_preview_does_not_persist(auth, seeded_legacy):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/migrate-legacy/preview?academic_year={ACADEMIC_YEAR}",
        headers=_h(auth), timeout=15,
    )
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    # 4 candidatos (o 5º foi excluído porque já tem reason_id)
    assert body["total_candidates"] == 4
    assert body["classified"] == 3  # 1a, 3b, 2b
    assert body["unclassified"] == 1  # xyz blabla
    # samples têm shape correto
    sample = body["samples"][0]
    assert "legacy_text" in sample
    assert "suggested_subcode" in sample
    assert "confidence" in sample
    # Confirma que NADA foi alterado no banco — recheca contagens
    r2 = requests.get(
        f"{BASE_URL}/api/bolsa-familia/migrate-legacy/preview?academic_year={ACADEMIC_YEAR}",
        headers=_h(auth), timeout=15,
    )
    assert r2.json()["total_candidates"] == 4


def test_apply_with_confidence_filter(auth, seeded_legacy):
    """confidence_min=0.85 sem fallback → migra apenas 3 (atestado, transporte, óbito)."""
    r = requests.post(
        f"{BASE_URL}/api/bolsa-familia/migrate-legacy/apply?academic_year={ACADEMIC_YEAR}&confidence_min=0.85&include_fallback=false",
        headers=_h(auth, csrf=True), timeout=20,
    )
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body["migrated"] == 3
    assert body["skipped_fallback"] == 1  # xyz blabla
    assert body["errors_count"] == 0
    assert "1a" in body["by_subcode"]
    assert "3b" in body["by_subcode"]
    assert "2b" in body["by_subcode"]


def test_apply_is_idempotent(auth, seeded_legacy):
    """Segunda chamada não deve re-migrar nada."""
    # 1ª aplica
    requests.post(
        f"{BASE_URL}/api/bolsa-familia/migrate-legacy/apply?academic_year={ACADEMIC_YEAR}&confidence_min=0.85",
        headers=_h(auth, csrf=True), timeout=20,
    )
    # 2ª deve não encontrar candidatos
    r = requests.post(
        f"{BASE_URL}/api/bolsa-familia/migrate-legacy/apply?academic_year={ACADEMIC_YEAR}&confidence_min=0.85",
        headers=_h(auth, csrf=True), timeout=20,
    )
    body = r.json()
    # Os 3 migrados na primeira agora têm reason_id != null → não entram no query
    # O 4 (fallback) ainda está null e foi pulado (skipped_fallback)
    # O 5 já tinha reason_id desde início
    assert body["migrated"] == 0


def test_apply_with_include_fallback_classifies_unclassified(auth, seeded_legacy):
    """include_fallback=true marca não-classificados como 24z."""
    r = requests.post(
        f"{BASE_URL}/api/bolsa-familia/migrate-legacy/apply?academic_year={ACADEMIC_YEAR}&confidence_min=0.85&include_fallback=true",
        headers=_h(auth, csrf=True), timeout=20,
    )
    body = r.json()
    # 3 keyword + 1 fallback = 4
    assert body["migrated"] == 4
    assert "24z" in body["by_subcode"]
    assert body["by_subcode"]["24z"] == 1


def test_apply_persists_audit_metadata(auth, seeded_legacy):
    """Documentos migrados ganham `legacy_migration` audit block."""
    requests.post(
        f"{BASE_URL}/api/bolsa-familia/migrate-legacy/apply?academic_year={ACADEMIC_YEAR}&confidence_min=0.85",
        headers=_h(auth, csrf=True), timeout=20,
    )

    async def _check():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        doc = await db.bolsa_familia_tracking.find_one(
            {"student_id": f"{QA_PREFIX}1"},
            {"_id": 0, "legacy_migration": 1, "reason_id": 1},
        )
        return doc

    doc = asyncio.run(_check())
    assert doc is not None
    assert doc.get("reason_id") is not None  # migrado
    assert "legacy_migration" in doc
    audit = doc["legacy_migration"]
    assert "migrated_at" in audit
    assert "engine_version" in audit
    assert "confidence" in audit
    assert "original_legacy_text" in audit
    assert audit["original_legacy_text"] == "Aluno com atestado médico"
