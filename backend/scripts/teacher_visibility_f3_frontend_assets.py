#!/usr/bin/env python3
"""TEACHER-VISIBILITY-F3 — auditoria pública read-only dos assets do frontend.

Confirma se produção entrega a release esperada, um Service Worker versionado por
SHA e bundles contendo os bridges atuais de conteúdo/frequência. Não autentica,
não consulta Mongo e executa somente HTTP GET em recursos públicos.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "https://sigesc.aprenderdigital.top"
MAX_TEXT_BYTES = 8 * 1024 * 1024
MAX_JS_ASSETS = 20


def _headers_subset(headers: Any) -> dict[str, str]:
    wanted = {"cache-control", "content-type", "etag", "last-modified"}
    return {
        key.lower(): value
        for key, value in headers.items()
        if key.lower() in wanted
    }


def _http_get(url: str, *, max_bytes: int = MAX_TEXT_BYTES) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "*/*",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": "sigesc-teacher-visibility-f3-readonly",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise RuntimeError(f"TEACHER_VISIBILITY_F3_RESPONSE_TOO_LARGE:{url}")
        return {
            "status": int(response.status),
            "url": response.geturl(),
            "headers": _headers_subset(response.headers),
            "body": body,
        }


def extract_script_sources(html: str) -> list[str]:
    sources = re.findall(
        r"<script\b[^>]*\bsrc=[\"']([^\"']+\.js(?:\?[^\"']*)?)[\"']",
        html,
        flags=re.IGNORECASE,
    )
    out: list[str] = []
    for source in sources:
        if source not in out:
            out.append(source)
    return out


def evaluate_snapshot(snapshot: dict[str, Any], expected_sha: str) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []

    if snapshot.get("version", {}).get("git_sha") != expected_sha:
        failures.append("PUBLIC_VERSION_SHA_MISMATCH")

    sw = snapshot.get("service_worker", {})
    if not sw.get("expected_release_sha_present"):
        failures.append("SERVICE_WORKER_RELEASE_SHA_MISSING")
    if not sw.get("placeholder_absent"):
        failures.append("SERVICE_WORKER_PLACEHOLDER_PRESENT")
    if not (sw.get("skip_waiting") and sw.get("clients_claim") and sw.get("sha_cache_name")):
        failures.append("SERVICE_WORKER_UPDATE_CONTRACT_MISSING")

    js = snapshot.get("javascript", {})
    if int(js.get("asset_count") or 0) <= 0:
        failures.append("INDEX_NO_JS_ASSETS")
    if not js.get("content_bridge_signature"):
        failures.append("CONTENT_BRIDGE_SIGNATURE_MISSING")
    if not js.get("attendance_bridge_signature"):
        failures.append("ATTENDANCE_BRIDGE_SIGNATURE_MISSING")

    sw_cache = str((sw.get("headers") or {}).get("cache-control") or "").lower()
    if "immutable" in sw_cache:
        warnings.append("SERVICE_WORKER_CACHE_POLICY_IMMUTABLE")

    return {
        "status": "PASS" if not failures else "FAIL",
        "classification": (
            "PUBLIC_FRONTEND_ASSETS_CURRENT"
            if not failures
            else "PUBLIC_FRONTEND_ASSET_DRIFT"
        ),
        "failures": failures,
        "warnings": warnings,
    }


def run_live_audit() -> dict[str, Any]:
    expected_sha = os.environ.get("EXPECTED_PRODUCTION_SHA", "").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise RuntimeError("TEACHER_VISIBILITY_F3_EXPECTED_SHA_INVALID")

    base = os.environ.get("SIGESC_FRONTEND_BASE", DEFAULT_BASE_URL).rstrip("/")
    nonce = f"{expected_sha[:12]}-{int(time.time())}"

    version_response = _http_get(f"{base}/version.json?f3={nonce}")
    version_payload = json.loads(version_response["body"].decode("utf-8"))

    sw_response = _http_get(f"{base}/sw.js?f3={nonce}")
    sw_text = sw_response["body"].decode("utf-8", errors="replace")

    index_response = _http_get(f"{base}/?f3={nonce}")
    index_text = index_response["body"].decode("utf-8", errors="replace")
    script_sources = extract_script_sources(index_text)
    if len(script_sources) > MAX_JS_ASSETS:
        raise RuntimeError(f"TEACHER_VISIBILITY_F3_TOO_MANY_JS_ASSETS:{len(script_sources)}")

    assets: list[dict[str, Any]] = []
    combined_parts: list[str] = []
    for source in script_sources:
        absolute = urllib.parse.urljoin(f"{base}/", source)
        separator = "&" if "?" in absolute else "?"
        response = _http_get(f"{absolute}{separator}f3={nonce}")
        body = response["body"]
        combined_parts.append(body.decode("utf-8", errors="ignore"))
        assets.append({
            "path": urllib.parse.urlsplit(absolute).path,
            "status": response["status"],
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "headers": response["headers"],
        })

    combined_js = "\n".join(combined_parts)
    content_bridge_signature = any(
        signature in combined_js
        for signature in (
            "DVD_LEGACY_CONTENT_READ_ONLY",
            "CONTENT_RELOAD_REQUIRED",
            "Este conteúdo pertence ao histórico anterior ao Diário por Vínculo",
        )
    )
    attendance_bridge_signature = any(
        signature in combined_js
        for signature in (
            "__sigescAttendanceDvdBridgeInstalled",
            "/attendance/dvd/context/",
        )
    )

    snapshot = {
        "version": {
            "status": version_response["status"],
            "git_sha": version_payload.get("git_sha"),
            "headers": version_response["headers"],
        },
        "service_worker": {
            "status": sw_response["status"],
            "headers": sw_response["headers"],
            "expected_release_sha_present": expected_sha in sw_text,
            "placeholder_absent": "__SIGESC_GIT_SHA__" not in sw_text,
            "skip_waiting": "skipWaiting" in sw_text,
            "clients_claim": "clients.claim" in sw_text,
            "sha_cache_name": "RELEASE_SHA.slice(0, 12)" in sw_text,
            "sha256": hashlib.sha256(sw_response["body"]).hexdigest(),
        },
        "index": {
            "status": index_response["status"],
            "headers": index_response["headers"],
            "script_count": len(script_sources),
        },
        "javascript": {
            "asset_count": len(assets),
            "assets": assets,
            "content_bridge_signature": content_bridge_signature,
            "attendance_bridge_signature": attendance_bridge_signature,
        },
    }
    evaluation = evaluate_snapshot(snapshot, expected_sha)

    return {
        "schema": "TEACHER_VISIBILITY_F3_PUBLIC_FRONTEND_ASSETS_V1",
        "target": "production-public-frontend",
        "expected_production_sha": expected_sha,
        "http_methods": ["GET"],
        "authentication_used": False,
        "database_access": False,
        "production_writes": False,
        **evaluation,
        **snapshot,
    }


if __name__ == "__main__":
    result = run_live_audit()
    print("TEACHER_VISIBILITY_F3_JSON=" + json.dumps(result, ensure_ascii=False, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(2)
