"""
[Sprint 1.0] Testes do dedup de matrículas duplicadas.

Cobre a regra (i) combo:
  1. Preferência por matrícula cujo school_id == students.school_id
  2. Entre preferenciais, escolhe a mais recente (created_at)
  3. Fallback: mais recente de todas
"""
from datetime import datetime, timezone


def _pick_canonical(student_school_id, enrollments):
    """Reproduz a regra do router para fins de teste."""
    def _ts(e):
        ts = e.get("created_at")
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                return datetime.min.replace(tzinfo=timezone.utc)
        return datetime.min.replace(tzinfo=timezone.utc)

    preferenciais = [
        e for e in enrollments
        if e.get("school_id") == student_school_id and student_school_id
    ]
    if preferenciais:
        return max(preferenciais, key=_ts)
    return max(enrollments, key=_ts) if enrollments else None


def test_canonical_picks_matching_school():
    """Quando uma matrícula bate com escola atual do aluno, ela é canonical."""
    enrolls = [
        {"id": "A", "school_id": "school-1", "created_at": "2024-01-01T00:00:00+00:00"},
        {"id": "B", "school_id": "school-2", "created_at": "2025-01-01T00:00:00+00:00"},
    ]
    canonical = _pick_canonical("school-1", enrolls)
    assert canonical["id"] == "A", "Deve preferir a que bate com school-1 mesmo sendo mais antiga"


def test_canonical_picks_latest_when_multiple_match_school():
    """Várias matrículas batem com a escola atual → mais recente vence."""
    enrolls = [
        {"id": "A", "school_id": "school-1", "created_at": "2024-01-01T00:00:00+00:00"},
        {"id": "B", "school_id": "school-1", "created_at": "2025-06-01T00:00:00+00:00"},
        {"id": "C", "school_id": "school-1", "created_at": "2024-12-01T00:00:00+00:00"},
    ]
    canonical = _pick_canonical("school-1", enrolls)
    assert canonical["id"] == "B"


def test_canonical_fallback_latest_when_none_match():
    """Nenhuma bate com escola atual → fallback para mais recente de todas."""
    enrolls = [
        {"id": "A", "school_id": "school-2", "created_at": "2024-01-01T00:00:00+00:00"},
        {"id": "B", "school_id": "school-3", "created_at": "2025-12-01T00:00:00+00:00"},
    ]
    canonical = _pick_canonical("school-1", enrolls)
    assert canonical["id"] == "B"


def test_canonical_with_student_school_none():
    """Aluno sem school_id → fallback direto para mais recente."""
    enrolls = [
        {"id": "A", "school_id": "school-1", "created_at": "2024-01-01T00:00:00+00:00"},
        {"id": "B", "school_id": "school-2", "created_at": "2025-06-01T00:00:00+00:00"},
    ]
    canonical = _pick_canonical(None, enrolls)
    assert canonical["id"] == "B"


def test_canonical_with_datetime_objects():
    """Aceita created_at como datetime, não só string."""
    enrolls = [
        {"id": "A", "school_id": "school-1",
         "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc)},
        {"id": "B", "school_id": "school-1",
         "created_at": datetime(2025, 6, 1, tzinfo=timezone.utc)},
    ]
    canonical = _pick_canonical("school-1", enrolls)
    assert canonical["id"] == "B"


def test_canonical_with_missing_created_at():
    """Matrículas sem created_at são consideradas as mais antigas."""
    enrolls = [
        {"id": "A", "school_id": "school-1"},  # sem created_at
        {"id": "B", "school_id": "school-1",
         "created_at": "2024-01-01T00:00:00+00:00"},
    ]
    canonical = _pick_canonical("school-1", enrolls)
    assert canonical["id"] == "B"
