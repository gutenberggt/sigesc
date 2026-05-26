"""
[Sprint 1.0] Testes do dedup de matrículas duplicadas.

Cobre a regra (i) combo:
  1. Preferência por matrícula cujo school_id == students.school_id
  2. Entre preferenciais, escolhe a mais recente (created_at)
  3. Fallback: mais recente de todas

E o bug fix crítico:
  4. Mistura de datetime tz-naive + tz-aware NÃO deve estourar TypeError
     (regressão observada em produção em /api/admin/students/duplicate-enrollments/dedup)
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routers.dedup_enrollments import _normalize_created_at  # noqa: E402


def _pick_canonical(student_school_id, enrollments):
    """Reproduz a regra do router usando o mesmo `_normalize_created_at` real."""
    preferenciais = [
        e for e in enrollments
        if e.get("school_id") == student_school_id and student_school_id
    ]
    if preferenciais:
        return max(preferenciais, key=lambda e: _normalize_created_at(e.get("created_at")))
    if not enrollments:
        return None
    return max(enrollments, key=lambda e: _normalize_created_at(e.get("created_at")))


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


# ---------------------------------------------------------------------------
# Regressões do bug "can't compare offset-naive and offset-aware datetimes"
# (Sprint 1.0 — visto no prod ao rodar POST /duplicate-enrollments/dedup)
# ---------------------------------------------------------------------------
def test_normalize_naive_datetime_becomes_utc_aware():
    naive = datetime(2024, 5, 1, 10, 0, 0)
    out = _normalize_created_at(naive)
    assert out.tzinfo is not None
    assert out.utcoffset().total_seconds() == 0


def test_normalize_aware_datetime_passes_through():
    aware = datetime(2024, 5, 1, 10, 0, 0, tzinfo=timezone.utc)
    out = _normalize_created_at(aware)
    assert out == aware


def test_normalize_iso_string_without_tz_becomes_utc():
    out = _normalize_created_at("2024-05-01T10:00:00")
    assert out.tzinfo is not None


def test_canonical_mix_naive_and_aware_datetimes_no_typeerror():
    """REGRESSÃO: misturar datetimes naive + aware quebrava `max()` com TypeError."""
    enrolls = [
        {"id": "A", "school_id": "school-1",
         "created_at": datetime(2024, 1, 1)},  # naive
        {"id": "B", "school_id": "school-1",
         "created_at": datetime(2025, 6, 1, tzinfo=timezone.utc)},  # aware
        {"id": "C", "school_id": "school-1",
         "created_at": "2024-12-01T00:00:00"},  # string sem tz
    ]
    # Não deve estourar TypeError; deve eleger a mais recente (B = 2025-06)
    canonical = _pick_canonical("school-1", enrolls)
    assert canonical["id"] == "B"


def test_canonical_mix_naive_aware_with_string_z_no_typeerror():
    """REGRESSÃO: cobrir o formato ISO com sufixo 'Z' (UTC) misturado a naive."""
    enrolls = [
        {"id": "A", "school_id": "school-1",
         "created_at": "2024-01-01T00:00:00Z"},  # aware via 'Z'
        {"id": "B", "school_id": "school-1",
         "created_at": datetime(2025, 6, 1)},  # naive datetime
    ]
    canonical = _pick_canonical("school-1", enrolls)
    assert canonical["id"] == "B"
