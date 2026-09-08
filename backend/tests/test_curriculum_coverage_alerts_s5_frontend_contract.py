from pathlib import Path


def _root():
    return Path(__file__).resolve().parents[2]


def test_global_bell_surfaces_curriculum_alerts():
    text = (_root() / "frontend" / "src" / "components" / "notifications" / "NotificationBell.js").read_text(encoding="utf-8")
    assert "curriculumAlertsAPI" in text
    assert "unread_curriculum_alerts" in text
    assert "Cobertura curricular" in text
    assert "curriculum-alerts-inbox" in text
    assert "'/professor#meus-diarios'" in text
    assert "'/semed/panel'" in text


def test_alert_feed_no_longer_exposes_weekly_punitive_escalation_language():
    text = (_root() / "frontend" / "src" / "pages" / "Interventions.jsx").read_text(encoding="utf-8")
    assert "Alertas de Cobertura Curricular" in text
    assert "informativo e preventivo" in text
    assert "últimos 15 dias letivos" in text
    assert "Nível 3 — Secretaria" not in text
    assert "cobra a ação da gestão semanalmente" not in text
    assert "Bimestre fechado <90%" not in text


def test_curriculum_alert_api_uses_existing_intervention_inbox():
    text = (_root() / "frontend" / "src" / "services" / "curriculumAlerts.js").read_text(encoding="utf-8")
    assert "/intervencoes/notifications" in text
    assert "markAsRead" in text
