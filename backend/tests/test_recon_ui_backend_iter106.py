"""Iteration 106 — Sanity backend checks for History Reconstruction UI.

Covers:
- super_admin can dry-run
- coordenador (non super_admin) receives 403 on dry-run/execute/receipt
- dry-run does NOT mutate (re-run returns same counts)
"""
import os
import json
import base64
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE}/api"


def _csrf_from_jwt(token):
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload.get("csrf")
    except Exception:
        return None


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    tok = r.json()["access_token"]
    return tok, _csrf_from_jwt(tok)


def _hdr(tok_tuple):
    tok, csrf = tok_tuple
    h = {"Authorization": f"Bearer {tok}"}
    if csrf:
        h["X-CSRF-Token"] = csrf
    return h


@pytest.fixture(scope="module")
def super_token():
    return _login("gutenberg@sigesc.com", "@Celta2007")


@pytest.fixture(scope="module")
def coord_token():
    # Try known coordinator credentials; skip if env doesn't have one
    for creds in [
        ("coordenador@sigesc.com", "coordenador123"),
        ("kledbyaschenkel@sigesc.com", "856567"),
        ("ricleidegoncalves@gmail.com", "Professor@2026"),
    ]:
        try:
            return _login(*creds)
        except AssertionError:
            continue
    pytest.skip("No non-super_admin coordinator credentials available in this env")


def test_super_admin_dryrun_school_scope(super_token):
    r = requests.get(f"{API}/schools", headers=_hdr(super_token), timeout=30)
    assert r.status_code == 200
    schools = r.json()
    assert len(schools) > 0, "no schools available"
    sid = schools[0]["id"]
    body = {"scope": "school", "school_id": sid}
    r1 = requests.post(f"{API}/admin/history-reconstruction/dry-run", json=body,
                       headers=_hdr(super_token), timeout=180)
    assert r1.status_code == 200, r1.text
    data = r1.json()
    for k in ("students_in_scope", "movements_detected", "to_consolidate"):
        assert k in data, f"missing {k} in {data}"
    # Idempotency of dry-run: second call returns same counts
    r2 = requests.post(f"{API}/admin/history-reconstruction/dry-run", json=body,
                       headers=_hdr(super_token), timeout=180)
    assert r2.status_code == 200
    assert r2.json()["movements_detected"] == data["movements_detected"]


def test_coordenador_forbidden_dryrun(coord_token):
    r = requests.post(
        f"{API}/admin/history-reconstruction/dry-run",
        json={"scope": "school", "school_id": "any"},
        headers=_hdr(coord_token),
        timeout=30,
    )
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"


def test_coordenador_forbidden_execute(coord_token):
    r = requests.post(
        f"{API}/admin/history-reconstruction/execute",
        json={"scope": "school", "school_id": "any", "reason": "teste teste teste"},
        headers=_hdr(coord_token),
        timeout=30,
    )
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"


def test_coordenador_forbidden_receipt(coord_token):
    r = requests.get(
        f"{API}/admin/history-reconstruction/RECON-2026-000001/receipt",
        headers=_hdr(coord_token),
        timeout=30,
    )
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"
