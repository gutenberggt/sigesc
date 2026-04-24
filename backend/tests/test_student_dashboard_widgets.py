"""Tests for /aluno dashboard widgets: upcoming-events, announcements, and
announcement targeting for aluno users."""
import os
import uuid
import pytest
import requests

def _load_frontend_env():
    env_path = "/app/frontend/.env"
    try:
        with open(env_path) as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    return None

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _load_frontend_env() or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not configured"

STUDENT_EMAIL = "aluno@sigesc.com"
STUDENT_PASS = "aluno123"
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASS = "@Celta2007"
MANTENEDORA_ID = "a991c1ac-56b1-46a8-b122-effedbe19b21"
STUDENT_USER_ID = "92207223-0af8-446c-abfe-b2810dbbc48c"
STUDENT_CLASS_ID = "9f71ed93"  # prefix; find full from student enrollments

API = BASE_URL + "/api"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def student_token():
    return _login(STUDENT_EMAIL, STUDENT_PASS)


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


# ===== upcoming-events =====
class TestUpcomingEvents:
    def test_student_can_fetch_upcoming_events(self, student_token):
        r = requests.get(
            f"{API}/student/me/upcoming-events",
            headers={"Authorization": f"Bearer {student_token}"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "events" in data
        assert "today" in data
        assert "school_id" in data
        assert isinstance(data["events"], list)
        # seed: 13 sábados letivos 2026
        assert len(data["events"]) >= 1
        ev = data["events"][0]
        for key in ("id", "name", "event_type", "start_date"):
            assert key in ev, f"event missing key {key}: {ev}"


# ===== announcements =====
class TestAnnouncements:
    def test_student_receives_seed_announcement(self, student_token):
        r = requests.get(
            f"{API}/student/me/announcements",
            headers={"Authorization": f"Bearer {student_token}"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "announcements" in data and "total" in data
        anns = data["announcements"]
        assert isinstance(anns, list)
        assert data["total"] == len(anns)
        assert len(anns) >= 1, "Aluno deveria ter pelo menos 1 aviso seed"
        titles = [a.get("title") for a in anns]
        assert any("Reunião de pais" in (t or "") for t in titles), \
            f"Aviso seed não encontrado; títulos={titles}"
        a0 = anns[0]
        for key in ("id", "title", "content", "sender_name", "sender_role", "created_at", "is_read"):
            assert key in a0

    def test_non_student_403(self, admin_token):
        r = requests.get(
            f"{API}/student/me/announcements",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "X-Mantenedora-Id": MANTENEDORA_ID,
            },
            timeout=15,
        )
        assert r.status_code == 403, f"esperava 403, recebeu {r.status_code} {r.text}"


# ===== Class-targeted announcement includes student =====
class TestClassTargetedAnnouncement:
    def test_class_announcement_reaches_student(self, student_token, admin_token):
        # Find student's class_id via /student/me/report-card
        r = requests.get(
            f"{API}/student/me/report-card",
            headers={"Authorization": f"Bearer {student_token}"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        class_id = r.json()["turma"]["id"]
        school_id = r.json()["escola"]["id"]
        assert class_id

        title = f"TEST_class_aviso_{uuid.uuid4().hex[:8]}"
        payload = {
            "title": title,
            "content": "Turma — aviso de teste automatizado",
            "recipient": {"type": "class", "class_ids": [class_id]},
            "priority": "normal",
        }
        r = requests.post(
            f"{API}/announcements",
            json=payload,
            headers={
                "Authorization": f"Bearer {admin_token}",
                "X-Mantenedora-Id": MANTENEDORA_ID,
            },
            timeout=20,
        )
        assert r.status_code in (200, 201), f"criar aviso: {r.status_code} {r.text}"
        created = r.json()
        # AnnouncementResponse (pydantic) não expõe target_user_ids — validamos
        # via endpoint do aluno logo abaixo (efeito observável).

        # Confirma via endpoint do aluno
        r = requests.get(
            f"{API}/student/me/announcements?limit=20",
            headers={"Authorization": f"Bearer {student_token}"},
            timeout=15,
        )
        assert r.status_code == 200
        titles = [a.get("title") for a in r.json().get("announcements", [])]
        assert title in titles, f"Aviso {title} não apareceu para o aluno; {titles}"

        # cleanup (best-effort)
        ann_id = created.get("id")
        if ann_id:
            requests.delete(
                f"{API}/announcements/{ann_id}",
                headers={
                    "Authorization": f"Bearer {admin_token}",
                    "X-Mantenedora-Id": MANTENEDORA_ID,
                },
                timeout=10,
            )
