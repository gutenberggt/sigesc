"""Fase 3A (Fev/2026) — Agregados institucionais BF.

Valida `services/bf_network_stats.py`:
  - Pipeline `$facet` única produz shape estável.
  - `stats_version` presente.
  - Filtros (`academic_year`) escopam corretamente.
  - Documentos sem reason_id NÃO entram nos agregados.
  - Followup retorna apenas casos severity≥N ou requires_followup=True.

Testes E2E HTTP — pré-popula tracking real, audita resposta dos endpoints.
"""
import os
import uuid
import asyncio
from datetime import datetime, timezone

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASS = "@Celta2007"
QA_PREFIX = "qa-stats-"
ACADEMIC_YEAR = 2099  # ano isolado para QA


@pytest.fixture(scope="module")
def auth():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not set")
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    return {"token": body["access_token"], "csrf": body["csrf_token"]}


def _h(auth):
    return {"Authorization": f"Bearer {auth['token']}"}


@pytest.fixture(scope="module")
def seeded_data():
    """Pré-popula trackings QA isolados em academic_year=2099.

    - 5 docs reason 1a (HEALTH, severity 2) na escola SCA
    - 3 docs reason 11a (VIOLENCE, severity 5, requires_followup=True) na SCB
    - 4 docs reason 3b (ACCESS, severity 3, requires_followup=True) na SCA
    - 2 docs reason 10b (CHILD_LABOR, severity 5) na SCC
    - 1 doc SEM reason_id (deve ser IGNORADO pelo agregado)
    """
    async def _setup():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        reasons = await db.attendance_frequency_reasons.find(
            {"mec_version": "4.2"}, {"_id": 0, "id": 1, "mec_subcode": 1}
        ).to_list(200)
        by_sub = {r["mec_subcode"]: r["id"] for r in reasons}
        await db.bolsa_familia_tracking.delete_many({"student_id": {"$regex": f"^{QA_PREFIX}"}})
        # Cria 2 escolas QA com nomes
        await db.schools.delete_many({"id": {"$in": ["qa-sc-A", "qa-sc-B", "qa-sc-C"]}})
        await db.schools.insert_many([
            {"id": "qa-sc-A", "name": "QA School A"},
            {"id": "qa-sc-B", "name": "QA School B"},
            {"id": "qa-sc-C", "name": "QA School C"},
        ])
        now = datetime.now(timezone.utc).isoformat()
        docs = []
        for i in range(5):
            docs.append({"student_id": f"{QA_PREFIX}h{i}", "school_id": "qa-sc-A",
                         "month": "3", "academic_year": ACADEMIC_YEAR,
                         "reason_id": by_sub["1a"], "updated_at": now})
        for i in range(3):
            docs.append({"student_id": f"{QA_PREFIX}v{i}", "school_id": "qa-sc-B",
                         "month": "3", "academic_year": ACADEMIC_YEAR,
                         "reason_id": by_sub["11a"], "updated_at": now})
        for i in range(4):
            docs.append({"student_id": f"{QA_PREFIX}t{i}", "school_id": "qa-sc-A",
                         "month": "4", "academic_year": ACADEMIC_YEAR,
                         "reason_id": by_sub["3b"], "updated_at": now})
        for i in range(2):
            docs.append({"student_id": f"{QA_PREFIX}c{i}", "school_id": "qa-sc-C",
                         "month": "5", "academic_year": ACADEMIC_YEAR,
                         "reason_id": by_sub["10b"], "updated_at": now})
        # 1 doc SEM reason_id — deve ser ignorado
        docs.append({"student_id": f"{QA_PREFIX}noreason", "school_id": "qa-sc-A",
                     "month": "3", "academic_year": ACADEMIC_YEAR,
                     "reason_id": None, "updated_at": now})
        await db.bolsa_familia_tracking.insert_many(docs)
        yield_data = {"total_docs_with_reason": 14}
        return yield_data

    data = asyncio.run(_setup())
    yield data
    # Teardown
    async def _teardown():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.bolsa_familia_tracking.delete_many({"student_id": {"$regex": f"^{QA_PREFIX}"}})
        await db.schools.delete_many({"id": {"$in": ["qa-sc-A", "qa-sc-B", "qa-sc-C"]}})
    asyncio.run(_teardown())


def test_network_stats_shape_and_version(auth, seeded_data):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/stats/network?academic_year={ACADEMIC_YEAR}&force_refresh=true",
        headers=_h(auth), timeout=20,
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    expected_keys = {"stats_version", "generated_at", "scope", "total_with_reason",
                     "by_category", "by_severity", "requires_followup",
                     "severity_5_plus", "top_schools", "top_subcodes", "cached"}
    assert expected_keys.issubset(set(body.keys()))
    assert body["stats_version"] == "v1.0"
    assert body["scope"]["academic_year"] == ACADEMIC_YEAR


def test_network_stats_totals(auth, seeded_data):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/stats/network?academic_year={ACADEMIC_YEAR}&force_refresh=true",
        headers=_h(auth), timeout=20,
    )
    body = r.json()
    # 5+3+4+2 = 14 com reason_id (o doc sem reason_id deve ser ignorado)
    assert body["total_with_reason"] == 14
    # by_category: HEALTH=5, VIOLENCE=3, ACCESS=4, CHILD_LABOR=2
    assert body["by_category"]["HEALTH"] == 5
    assert body["by_category"]["VIOLENCE"] == 3
    assert body["by_category"]["ACCESS"] == 4
    assert body["by_category"]["CHILD_LABOR"] == 2


def test_network_stats_severity_buckets(auth, seeded_data):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/stats/network?academic_year={ACADEMIC_YEAR}&force_refresh=true",
        headers=_h(auth), timeout=20,
    )
    body = r.json()
    # 1a=sev2 (5), 3b=sev3 (4), 11a=sev5 (3), 10b=sev5 (2)
    assert body["by_severity"]["2"] == 5
    assert body["by_severity"]["3"] == 4
    assert body["by_severity"]["5"] == 5
    # severity_5_plus: 3 + 2 = 5
    assert body["severity_5_plus"] == 5


def test_network_stats_requires_followup(auth, seeded_data):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/stats/network?academic_year={ACADEMIC_YEAR}&force_refresh=true",
        headers=_h(auth), timeout=20,
    )
    body = r.json()
    # 11a (3) + 3b (4) + 10b (2) = 9 com requires_followup=True
    assert body["requires_followup"] == 9


def test_network_stats_top_schools_have_names(auth, seeded_data):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/stats/network?academic_year={ACADEMIC_YEAR}&force_refresh=true",
        headers=_h(auth), timeout=20,
    )
    body = r.json()
    qa_schools = {s["school_id"]: s for s in body["top_schools"] if s["school_id"].startswith("qa-sc-")}
    assert "qa-sc-A" in qa_schools
    assert qa_schools["qa-sc-A"]["school_name"] == "QA School A"
    assert qa_schools["qa-sc-A"]["count"] == 9  # 5 HEALTH + 4 ACCESS


def test_network_stats_caching(auth, seeded_data):
    """1ª chamada cached=false; 2ª (sem force_refresh) cached=true."""
    r1 = requests.get(
        f"{BASE_URL}/api/bolsa-familia/stats/network?academic_year={ACADEMIC_YEAR}&force_refresh=true",
        headers=_h(auth), timeout=20,
    )
    assert r1.json().get("cached") is False
    r2 = requests.get(
        f"{BASE_URL}/api/bolsa-familia/stats/network?academic_year={ACADEMIC_YEAR}",
        headers=_h(auth), timeout=20,
    )
    assert r2.json().get("cached") is True


def test_network_followup_severity_5(auth, seeded_data):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/stats/network/followup?academic_year={ACADEMIC_YEAR}&severity_min=5",
        headers=_h(auth), timeout=20,
    )
    assert r.status_code == 200
    body = r.json()
    # Apenas trackings com severity≥5 ou requires_followup=True
    # 3 VIOLENCE (sev5, followup) + 2 CHILD_LABOR (sev5) + 4 ACCESS (requires_followup) = 9
    qa_only = [c for c in body["cases"] if c["student_id"].startswith(QA_PREFIX)]
    assert len(qa_only) == 9
    # Cada caso tem denormalizações
    sample = qa_only[0]
    expected_keys = {"student_id", "school_id", "school_name", "month", "reason_subcode",
                     "reason_name", "severity_level", "requires_followup", "category"}
    assert expected_keys.issubset(set(sample.keys()))


def test_network_followup_sorted_by_severity_desc(auth, seeded_data):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/stats/network/followup?academic_year={ACADEMIC_YEAR}&severity_min=1",
        headers=_h(auth), timeout=20,
    )
    body = r.json()
    qa_only = [c for c in body["cases"] if c["student_id"].startswith(QA_PREFIX)]
    severities = [c["severity_level"] for c in qa_only]
    # Confirma ordem decrescente
    assert severities == sorted(severities, reverse=True)


def test_network_followup_limit_enforced(auth, seeded_data):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/stats/network/followup?academic_year={ACADEMIC_YEAR}&severity_min=1&limit=3",
        headers=_h(auth), timeout=20,
    )
    body = r.json()
    assert body["total"] <= 3
    assert body["scope"]["limit"] == 3


def test_docs_without_reason_id_excluded(auth, seeded_data):
    """`qa-stats-noreason` foi inserido sem reason_id — não deve aparecer."""
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/stats/network/followup?academic_year={ACADEMIC_YEAR}&severity_min=1",
        headers=_h(auth), timeout=20,
    )
    body = r.json()
    ids = [c["student_id"] for c in body["cases"]]
    assert f"{QA_PREFIX}noreason" not in ids
