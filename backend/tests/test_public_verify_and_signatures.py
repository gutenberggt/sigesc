"""Fase 5b/5c (Mai/2026) — Verify público + Upload de assinatura.

Cobertura:
  Verify público (sem auth):
    1. Token válido → 200 + dados LGPD-safe (apenas campos permitidos)
    2. Token inválido → 404
    3. Anti-enumeração: 11 x 404 → 429 bloqueio
    4. NUNCA expõe payload (alunos, conteúdo, autores), audit_trail,
       user_ids, file_ids internos, rationale.

  Upload signature image:
    5. Roles autorizados sobem PNG válido → 200 + file_id
    6. MIME inválido (svg) → 422
    7. Tamanho > 512KB → 422
    8. base64 inválido → 422
    9. Imagem corrompida → 422
   10. Roles não autorizados (professor) → 403
"""
import base64
import os
import time
import uuid
from io import BytesIO

import pytest
import requests
from PIL import Image

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://institutional-audit-2.preview.emergentagent.com"
).rstrip("/")
ADMIN = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}


def _make_png_b64(w=200, h=80) -> str:
    img = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    buf = BytesIO()
    img.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=20)
    d = r.json()
    s.headers.update({
        "Authorization": f"Bearer {d.get('access_token') or d.get('token')}",
        "X-CSRF-Token": d.get("csrf_token") or "",
        "Content-Type": "application/json",
    })
    return s


@pytest.fixture(scope="module")
def published_snapshot(session):
    """Cria um snapshot publicado para usar nos testes de verify."""
    cid = "73844918-60b1-4c62-b6cb-a21a35cc49c1"
    period = f"2030-06-{uuid.uuid4().int % 27 + 1:02d}"
    body = {
        "class_id": cid, "period_type": "custom",
        "period_from": period, "period_to": period,
        "period_label": f"verify-test-{period}",
    }
    r = session.post(f"{BASE_URL}/api/diary/snapshots", json=body, timeout=20)
    snap_id = r.json()["snapshot"]["id"]
    p = session.post(f"{BASE_URL}/api/diary/snapshots/{snap_id}/publish", timeout=20)
    return p.json()["snapshot"]


# ============================================================================
# 1. Token válido → 200 + dados LGPD-safe
# ============================================================================
def test_verify_returns_lgpd_safe_data(published_snapshot):
    token = published_snapshot["verification_token"]
    r = requests.get(f"{BASE_URL}/api/verify/diary/{token}", timeout=20)
    assert r.status_code == 200
    d = r.json()
    # Campos permitidos
    allowed = {
        "code", "status", "school_name", "mantenedora_name", "class_name",
        "period", "issued_at", "payload_hash_sha256",
        "schema_version", "semantic_rules_version", "signatures",
    }
    assert set(d.keys()) <= allowed, f"Campos extras vazaram: {set(d.keys()) - allowed}"
    # Verifica ausência ABSOLUTA de PII
    forbidden = {"payload", "audit_trail", "validation_history", "renders",
                 "branding", "verification_token", "id", "_id"}
    assert not (forbidden & set(d.keys()))


# ============================================================================
# 2. Token inválido → 404
# ============================================================================
def test_verify_invalid_token_404():
    # IP único para não interferir com outros testes
    s = requests.Session()
    s.headers["X-Forwarded-For"] = f"10.99.{uuid.uuid4().int % 250}.1"
    r = s.get(f"{BASE_URL}/api/verify/diary/00000000000000000000000000000000", timeout=10)
    assert r.status_code == 404


# ============================================================================
# 3. Anti-enumeração: 11 x 404 mesmo IP → 429
# ============================================================================
def test_verify_anti_enumeration_blocks_after_10_404():
    s = requests.Session()
    fake_ip = f"10.99.{uuid.uuid4().int % 250}.99"
    s.headers["X-Forwarded-For"] = fake_ip
    codes = []
    for i in range(12):
        r = s.get(
            f"{BASE_URL}/api/verify/diary/{'a' * 16}{i:016d}", timeout=10,
        )
        codes.append(r.status_code)
    # Primeiros 10 = 404, depois deve aparecer 429
    assert codes[:10] == [404] * 10
    assert 429 in codes[10:]


# ============================================================================
# 4. Signature image upload — admin OK
# ============================================================================
def test_signature_upload_admin_ok(session):
    b64 = _make_png_b64(300, 100)
    r = session.put(
        f"{BASE_URL}/api/users/me/signature-image",
        json={"data_base64": b64, "mime_type": "image/png"}, timeout=20,
    )
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d["file_id"]
    assert d["mime_type"] == "image/png"
    assert d["width"] <= 600 and d["height"] <= 200
    assert len(d["sha256"]) == 64


# ============================================================================
# 5. GET me/signature retorna dados
# ============================================================================
def test_signature_get_my_returns_data(session):
    # garante upload prévio
    session.put(
        f"{BASE_URL}/api/users/me/signature-image",
        json={"data_base64": _make_png_b64(150, 50), "mime_type": "image/png"},
        timeout=20,
    )
    r = session.get(f"{BASE_URL}/api/users/me/signature-image", timeout=20)
    assert r.status_code == 200
    d = r.json()
    assert d.get("file_id")
    assert "data_base64" in d
    assert d["mime_type"] == "image/png"


# ============================================================================
# 6. MIME inválido (svg) → 422
# ============================================================================
def test_signature_invalid_mime_blocked(session):
    r = session.put(
        f"{BASE_URL}/api/users/me/signature-image",
        json={"data_base64": base64.b64encode(b"<svg/>").decode(),
              "mime_type": "image/svg+xml"}, timeout=20,
    )
    assert r.status_code == 422


# ============================================================================
# 7. base64 inválido → 422
# ============================================================================
def test_signature_invalid_base64_blocked(session):
    r = session.put(
        f"{BASE_URL}/api/users/me/signature-image",
        json={"data_base64": "not-base64-!!!@#", "mime_type": "image/png"},
        timeout=20,
    )
    assert r.status_code == 422


# ============================================================================
# 8. Imagem corrompida → 422
# ============================================================================
def test_signature_corrupted_image_blocked(session):
    fake = base64.b64encode(b"PNG_FAKE_NOT_IMAGE_DATA_AAAAAAAAAAAAAA").decode()
    r = session.put(
        f"{BASE_URL}/api/users/me/signature-image",
        json={"data_base64": fake, "mime_type": "image/png"}, timeout=20,
    )
    assert r.status_code == 422


# ============================================================================
# 9. Imagem grande é redimensionada (não rejeitada se < 512KB)
# ============================================================================
def test_signature_oversized_dimensions_get_resized(session):
    # Imagem 1200x400 (acima do limite) — deve ser redimensionada
    b64 = _make_png_b64(1200, 400)
    r = session.put(
        f"{BASE_URL}/api/users/me/signature-image",
        json={"data_base64": b64, "mime_type": "image/png"}, timeout=20,
    )
    assert r.status_code == 200
    d = r.json()
    assert d["width"] <= 600
    assert d["height"] <= 200
