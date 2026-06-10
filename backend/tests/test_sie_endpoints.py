"""SIE — Student Intelligence Engine FASE 0 endpoint tests.

Cobre os 7 endpoints sob /api/sie:
- GET /config, PUT /config (autorização)
- GET /students/{id}, POST /students/{id}/compute (persistência + idempotência)
- POST /compute (batch)
- GET /risk, GET /alerts, GET /students/{id}/snapshots
- Multi-tenant: verifica que docs persistidos têm mantenedora_id e não vazam _id.
"""
import os
import time
import pytest
import requests

_BACKEND_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not _BACKEND_URL:
    # Fallback to frontend/.env when running pytest from backend dir
    try:
        with open("/app/frontend/.env") as fh:
            for line in fh:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    _BACKEND_URL = line.split("=", 1)[1].strip().strip('"')
                    break
    except Exception:
        pass
assert _BACKEND_URL, "REACT_APP_BACKEND_URL not set"
BASE_URL = _BACKEND_URL.rstrip("/")
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASS = "@Celta2007"
COORD_EMAIL = "professor.teste@sigesc.com"
COORD_PASS = "Professor@2026"
TENANT_ID = "a991c1ac-56b1-46a8-b122-effedbe19b21"  # SEMED Floresta do Araguaia


def _login(email: str, password: str):
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    data = r.json()
    return data["access_token"], data["csrf_token"]


@pytest.fixture(scope="module")
def admin_headers():
    token, csrf = _login(ADMIN_EMAIL, ADMIN_PASS)
    return {
        "Authorization": f"Bearer {token}",
        "X-CSRF-Token": csrf,
        "X-Mantenedora-Id": TENANT_ID,
        "Content-Type": "application/json",
    }


@pytest.fixture(scope="module")
def coord_headers():
    try:
        token, csrf = _login(COORD_EMAIL, COORD_PASS)
        return {
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": csrf,
            "Content-Type": "application/json",
        }
    except Exception:
        pytest.skip("Coordenador account unavailable")


@pytest.fixture(scope="module")
def sample_student_id(admin_headers):
    """Pega um student_id real via /api/students (preferindo um com notas em 2026)."""
    r = requests.get(f"{BASE_URL}/api/students?limit=50", headers=admin_headers, timeout=30)
    assert r.status_code == 200, f"students list: {r.status_code} {r.text[:200]}"
    payload = r.json()
    items = payload.get("items") or payload.get("students") or payload if isinstance(payload, list) else payload.get("items", [])
    if isinstance(payload, dict) and not items:
        items = payload.get("data", [])
    assert items, "No students returned"
    sid = items[0].get("id")
    assert sid, f"Student missing id: {items[0]}"
    return sid


# ===================== CONFIG =====================

class TestSIEConfig:
    def test_get_config_creates_defaults(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/sie/config", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        cfg = r.json()
        assert cfg.get("passing_grade") == 6.0
        bands = cfg.get("risk_bands") or {}
        assert bands.get("low_max") == 24
        assert bands.get("moderate_max") == 49
        assert bands.get("high_max") == 74
        ow = cfg.get("overall_weights") or {}
        assert ow.get("academic") == 55
        assert ow.get("attendance") == 45
        assert "_id" not in cfg

    def test_put_config_persists(self, admin_headers):
        # update to 7.0
        r = requests.put(
            f"{BASE_URL}/api/sie/config",
            headers=admin_headers,
            json={"passing_grade": 7.0},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("passing_grade") == 7.0
        # GET reflects
        r2 = requests.get(f"{BASE_URL}/api/sie/config", headers=admin_headers, timeout=30)
        assert r2.json().get("passing_grade") == 7.0
        # restore default
        r3 = requests.put(
            f"{BASE_URL}/api/sie/config",
            headers=admin_headers,
            json={"passing_grade": 6.0},
            timeout=30,
        )
        assert r3.status_code == 200
        assert r3.json().get("passing_grade") == 6.0

    def test_put_config_coordenador_forbidden(self, coord_headers):
        r = requests.put(
            f"{BASE_URL}/api/sie/config",
            headers=coord_headers,
            json={"passing_grade": 5.0},
            timeout=30,
        )
        # Espera 403; aceita 401 caso CSRF/role differ
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}: {r.text[:200]}"


# ===================== STUDENT LIVE & COMPUTE =====================

class TestSIEStudent:
    def test_get_student_live(self, admin_headers, sample_student_id):
        r = requests.get(
            f"{BASE_URL}/api/sie/students/{sample_student_id}",
            headers=admin_headers, timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "academic" in data and "attendance" in data and "overall" in data
        assert "score" in data["academic"]
        assert "score" in data["attendance"]
        ov = data["overall"]
        assert "overall_risk" in ov and "risk_level" in ov
        assert ov["risk_level"] in {"low", "moderate", "high", "critical"}
        diag = data.get("diagnostic") or {}
        assert "risk_factors" in diag
        assert isinstance(diag["risk_factors"], list)
        assert "factors" in ov  # explicabilidade
        assert "_id" not in data

    def test_post_compute_persists_and_idempotent(self, admin_headers, sample_student_id):
        # 1st compute
        r1 = requests.post(
            f"{BASE_URL}/api/sie/students/{sample_student_id}/compute",
            headers=admin_headers, timeout=60,
        )
        assert r1.status_code == 200, r1.text
        # 2nd compute — same day shouldn't duplicate
        r2 = requests.post(
            f"{BASE_URL}/api/sie/students/{sample_student_id}/compute",
            headers=admin_headers, timeout=60,
        )
        assert r2.status_code == 200

        # Verify only 1 risk_score appears in /risk for this student
        rr = requests.get(
            f"{BASE_URL}/api/sie/risk?limit=1000",
            headers=admin_headers, timeout=30,
        )
        assert rr.status_code == 200, rr.text
        items = rr.json().get("items", [])
        matches = [i for i in items if i.get("student_id") == sample_student_id]
        assert len(matches) == 1, f"expected exactly 1 risk row, got {len(matches)}"
        m = matches[0]
        assert "_id" not in m
        assert m.get("mantenedora_id") is not None
        assert m.get("student_name")  # populated
        assert "academic_risk" in m and "attendance_risk" in m and "overall_risk" in m

    def test_snapshots_endpoint(self, admin_headers, sample_student_id):
        r = requests.get(
            f"{BASE_URL}/api/sie/students/{sample_student_id}/snapshots",
            headers=admin_headers, timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("student_id") == sample_student_id
        assert isinstance(data.get("items"), list)
        # at least 1 snapshot after compute
        assert data.get("total", 0) >= 1
        for it in data["items"]:
            assert "_id" not in it
            assert "snapshot_date" in it


# ===================== BATCH & LISTAGENS =====================

class TestSIEBatch:
    def test_batch_compute_returns_stats(self, admin_headers):
        # restringe a 1 class para não sobrecarregar — descobre uma class qualquer
        rcls = requests.get(f"{BASE_URL}/api/classes?limit=10", headers=admin_headers, timeout=30)
        class_id = None
        if rcls.status_code == 200:
            data = rcls.json()
            items = data.get("items") if isinstance(data, dict) else data
            if items:
                class_id = items[0].get("id")
        url = f"{BASE_URL}/api/sie/compute"
        if class_id:
            url += f"?class_id={class_id}"
        r = requests.post(url, headers=admin_headers, timeout=120)
        assert r.status_code == 200, r.text
        stats = r.json()
        assert "processed" in stats
        assert "by_level" in stats
        for k in ("low", "moderate", "high", "critical"):
            assert k in stats["by_level"]
        assert "alerts_open" in stats

    def test_alerts_list(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/sie/alerts?resolved=false&limit=200",
            headers=admin_headers, timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        items = data.get("items", [])
        # Only abertos
        for it in items:
            assert it.get("resolved_at") is None
            assert "_id" not in it
            assert it.get("severity") in {"critical", "high", "medium", "low"}
        # Sorted by severity priority
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        seq = [sev_order.get(it["severity"], 9) for it in items]
        assert seq == sorted(seq), "alerts not sorted by severity asc"

    def test_risk_list_filters(self, admin_headers):
        # base call
        r = requests.get(
            f"{BASE_URL}/api/sie/risk?limit=50",
            headers=admin_headers, timeout=30,
        )
        assert r.status_code == 200, r.text
        items = r.json().get("items", [])
        # ordered by overall_risk desc
        risks = [i.get("overall_risk", 0) for i in items]
        assert risks == sorted(risks, reverse=True), "risk list not sorted desc"
        # level filter
        r2 = requests.get(
            f"{BASE_URL}/api/sie/risk?level=low&limit=50",
            headers=admin_headers, timeout=30,
        )
        assert r2.status_code == 200
        for it in r2.json().get("items", []):
            assert it.get("risk_level") == "low"
