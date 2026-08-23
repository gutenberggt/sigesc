import json
import logging

from aee_v2 import plano_pdf_effective as mod


def _capture_log(monkeypatch):
    records = []

    def capture(level, message, *args, **kwargs):
        records.append((level, message, args, kwargs))

    monkeypatch.setattr(mod.logger, "log", capture)
    return records


def test_sidecar_active_cutover_is_warning(monkeypatch):
    records = _capture_log(monkeypatch)
    context = {
        "status": "effective",
        "plan_source": "sidecar_active",
        "effective_source": "sidecar_active",
        "legacy_plano_id": "plan-1",
        "effective_version": {"document_version": 1, "revision": 14},
        "blockers": [],
        "applied": {
            "status": "effective",
            "plan_source": "sidecar_active",
            "sessions_total": 1,
            "blockers": [],
        },
    }

    mod._log_cutover(context)

    assert len(records) == 1
    level, message, args, _ = records[0]
    assert level == logging.WARNING
    assert message == "AEE_V2_PLANO_PDF_EFFECTIVE %s"
    payload = json.loads(args[0])
    assert payload["effective_source"] == "sidecar_active"
    assert payload["blockers"] == 0


def test_blocked_cutover_is_warning(monkeypatch):
    records = _capture_log(monkeypatch)
    context = {
        "status": "blocked",
        "plan_source": "legacy",
        "effective_source": None,
        "legacy_plano_id": "plan-2",
        "effective_version": None,
        "blockers": [{"code": "AEE_V2_PLANO_PDF_PREFLIGHT_UNAVAILABLE"}],
    }

    mod._log_cutover(context)

    assert len(records) == 1
    level, _, args, _ = records[0]
    assert level == logging.WARNING
    payload = json.loads(args[0])
    assert payload["status"] == "blocked"
    assert payload["blockers"] == 1


def test_clean_legacy_cutover_stays_info(monkeypatch):
    records = _capture_log(monkeypatch)
    context = {
        "status": "legacy",
        "plan_source": "legacy",
        "effective_source": "legacy",
        "legacy_plano_id": "plan-3",
        "effective_version": None,
        "blockers": [],
    }

    mod._log_cutover(context)

    assert len(records) == 1
    level, _, args, _ = records[0]
    assert level == logging.INFO
    payload = json.loads(args[0])
    assert payload["effective_source"] == "legacy"
    assert payload["blockers"] == 0
