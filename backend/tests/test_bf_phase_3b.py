"""Fase 3B (Fev/2026) — Extensões backend: filtro `category` + snapshots.

Valida:
  - `/followup?category=VIOLENCE` filtra por categoria MEC.
  - `/followup?school_id=X` filtra por escola.
  - `/export?category=VIOLENCE` gera arquivo com sufixo correto.
  - `POST /stats/network/snapshot` persiste e é idempotente (mesmo dia → upsert).
  - `GET /stats/snapshots` retorna série temporal.
"""
import os
import asyncio
from datetime import datetime, timezone, timedelta

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASS = "@Celta2007"
QA_PREFIX = "qa-3b-"
ACADEMIC_YEAR = 2097


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


@pytest.fixture(scope="module")
def seeded():
    async def _setup():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.bolsa_familia_tracking.delete_many({"student_id": {"$regex": f"^{QA_PREFIX}"}})
        await db.bf_network_stats_snapshots.delete_many({"scope.academic_year": ACADEMIC_YEAR})
        reasons = await db.attendance_frequency_reasons.find(
            {"mec_subcode": {"$in": ["11a", "3b", "10b", "1a"]}, "mec_version": "4.2"},
            {"_id": 0, "id": 1, "mec_subcode": 1},
        ).to_list(10)
        by_sub = {r["mec_subcode"]: r["id"] for r in reasons}
        now = datetime.now(timezone.utc).isoformat()
        docs = [
            {"student_id": f"{QA_PREFIX}v1", "school_id": "qa-sa", "month": "3",
             "academic_year": ACADEMIC_YEAR, "reason_id": by_sub["11a"],
             "notes": "Violência", "updated_at": now},
            {"student_id": f"{QA_PREFIX}v2", "school_id": "qa-sb", "month": "3",
             "academic_year": ACADEMIC_YEAR, "reason_id": by_sub["11a"],
             "notes": "", "updated_at": now},
            {"student_id": f"{QA_PREFIX}t1", "school_id": "qa-sa", "month": "4",
             "academic_year": ACADEMIC_YEAR, "reason_id": by_sub["3b"],
             "notes": "", "updated_at": now},
            {"student_id": f"{QA_PREFIX}c1", "school_id": "qa-sb", "month": "5",
             "academic_year": ACADEMIC_YEAR, "reason_id": by_sub["10b"],
             "notes": "", "updated_at": now},
        ]
        await db.bolsa_familia_tracking.insert_many(docs)

    asyncio.run(_setup())
    yield
    async def _teardown():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.bolsa_familia_tracking.delete_many({"student_id": {"$regex": f"^{QA_PREFIX}"}})
        await db.bf_network_stats_snapshots.delete_many({"scope.academic_year": ACADEMIC_YEAR})
    asyncio.run(_teardown())


# ============================================================================
# CATEGORY FILTER
# ============================================================================

def test_followup_filter_by_category_violence(auth, seeded):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/stats/network/followup?academic_year={ACADEMIC_YEAR}&severity_min=1&category=VIOLENCE",
        headers=_h(auth), timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    qa_cases = [c for c in body["cases"] if c["student_id"].startswith(QA_PREFIX)]
    # Apenas v1 e v2 são VIOLENCE
    assert len(qa_cases) == 2
    for c in qa_cases:
        assert c["category"] == "VIOLENCE"


def test_followup_filter_by_school(auth, seeded):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/stats/network/followup?academic_year={ACADEMIC_YEAR}&severity_min=1&school_id=qa-sa",
        headers=_h(auth), timeout=15,
    )
    body = r.json()
    qa_cases = [c for c in body["cases"] if c["student_id"].startswith(QA_PREFIX)]
    # qa-sa tem v1 (VIOLENCE) e t1 (ACCESS)
    assert len(qa_cases) == 2
    for c in qa_cases:
        assert c["school_id"] == "qa-sa"


def test_followup_filter_category_and_school_combined(auth, seeded):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/stats/network/followup?academic_year={ACADEMIC_YEAR}&severity_min=1&category=VIOLENCE&school_id=qa-sa",
        headers=_h(auth), timeout=15,
    )
    qa_cases = [c for c in r.json()["cases"] if c["student_id"].startswith(QA_PREFIX)]
    # Apenas v1 (VIOLENCE em qa-sa)
    assert len(qa_cases) == 1
    assert qa_cases[0]["student_id"] == f"{QA_PREFIX}v1"


def test_export_with_category_in_filename(auth, seeded):
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/stats/network/followup/export?format=xlsx&academic_year={ACADEMIC_YEAR}&category=VIOLENCE",
        headers=_h(auth), timeout=15,
    )
    assert r.status_code == 200
    cd = r.headers.get("content-disposition", "")
    assert "violence" in cd.lower()
    assert ".xlsx" in cd


# ============================================================================
# SNAPSHOTS
# ============================================================================

def test_snapshot_persists(auth, seeded):
    r = requests.post(
        f"{BASE_URL}/api/bolsa-familia/stats/network/snapshot?academic_year={ACADEMIC_YEAR}",
        headers=_h(auth, csrf=True), timeout=15,
    )
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body["saved"] is True
    assert body["scope"]["academic_year"] == ACADEMIC_YEAR


def test_snapshot_idempotent_same_day(auth, seeded):
    """Mesmo dia + mesmo scope → upsert (não duplica)."""
    requests.post(
        f"{BASE_URL}/api/bolsa-familia/stats/network/snapshot?academic_year={ACADEMIC_YEAR}",
        headers=_h(auth, csrf=True), timeout=15,
    )
    requests.post(
        f"{BASE_URL}/api/bolsa-familia/stats/network/snapshot?academic_year={ACADEMIC_YEAR}",
        headers=_h(auth, csrf=True), timeout=15,
    )
    list_r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/stats/snapshots?academic_year={ACADEMIC_YEAR}",
        headers=_h(auth), timeout=15,
    )
    series = list_r.json()["series"]
    # Apenas 1 snapshot (mesmo dia)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_snaps = [s for s in series if s["snapshot_date"] == today]
    assert len(today_snaps) == 1


def test_snapshot_list_shape(auth, seeded):
    requests.post(
        f"{BASE_URL}/api/bolsa-familia/stats/network/snapshot?academic_year={ACADEMIC_YEAR}",
        headers=_h(auth, csrf=True), timeout=15,
    )
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/stats/snapshots?academic_year={ACADEMIC_YEAR}",
        headers=_h(auth), timeout=15,
    )
    body = r.json()
    assert "stats_version" in body
    assert "series" in body
    assert body["total"] >= 1
    s0 = body["series"][0]
    # Shape para gráficos
    for k in ("snapshot_date", "total_with_reason", "by_category", "by_severity",
              "requires_followup", "severity_5_plus"):
        assert k in s0


def test_snapshot_payload_contains_real_stats(auth, seeded):
    """Snapshot deve refletir os agregados atuais."""
    requests.post(
        f"{BASE_URL}/api/bolsa-familia/stats/network/snapshot?academic_year={ACADEMIC_YEAR}",
        headers=_h(auth, csrf=True), timeout=15,
    )
    r = requests.get(
        f"{BASE_URL}/api/bolsa-familia/stats/snapshots?academic_year={ACADEMIC_YEAR}",
        headers=_h(auth), timeout=15,
    )
    s = r.json()["series"][0]
    # 4 docs com reason_id (v1, v2, t1, c1)
    assert s["total_with_reason"] == 4
    # 2 VIOLENCE
    assert s["by_category"].get("VIOLENCE") == 2
    # severity 5+: 2 VIOLENCE + 1 CHILD_LABOR = 3
    assert s["severity_5_plus"] == 3
