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

from routers.dedup_enrollments import (  # noqa: E402
    _normalize_created_at,
    _record_dedup_run,
)


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



# ---------------------------------------------------------------------------
# Trilha de auditoria: persistência em `dedup_runs`
# ---------------------------------------------------------------------------
class _FakeCollection:
    def __init__(self):
        self.docs = []
        self.indexes = []

    async def create_index(self, keys, **kwargs):
        self.indexes.append({"keys": keys, "kwargs": kwargs})

    async def insert_one(self, doc):
        self.docs.append(doc)
        return type("R", (), {"inserted_id": "fake"})()


class _FakeDB:
    def __init__(self):
        self._colls = {}

    def __getitem__(self, name):
        if name not in self._colls:
            self._colls[name] = _FakeCollection()
        return self._colls[name]


def test_record_dedup_run_persists_full_envelope():
    """Garante que `_record_dedup_run` gera run_id, monta envelope completo e insere."""
    import asyncio

    db = _FakeDB()
    started = datetime(2026, 5, 26, 10, 0, 0, tzinfo=timezone.utc)
    finished = datetime(2026, 5, 26, 10, 0, 1, tzinfo=timezone.utc)

    run_id = asyncio.run(_record_dedup_run(
        db,
        mode="dry_run",
        target="dedup_enrollments",
        summary={"affected_students": 2, "would_inactivate": 3, "inactivated": 0},
        diff={"duplicates_removed": [{"enrollment_id": "x"}], "kept_records": [{"enrollment_id": "y"}]},
        actor={"user_id": "u1", "email": "g@x.com", "role": "super_admin"},
        started_at=started,
        finished_at=finished,
        duration_ms=1000,
    ))

    assert run_id  # UUID gerado
    docs = db["dedup_runs"].docs
    assert len(docs) == 1
    doc = docs[0]
    # Envelope schema definido pelo usuário
    assert doc["run_id"] == run_id
    assert doc["mode"] == "dry_run"
    assert doc["target"] == "dedup_enrollments"
    assert doc["summary"]["would_inactivate"] == 3
    assert doc["diff"]["duplicates_removed"][0]["enrollment_id"] == "x"
    assert doc["actor"]["email"] == "g@x.com"
    assert doc["duration_ms"] == 1000
    assert doc["created_at"] == finished.isoformat()
    assert "environment" in doc  # mesmo que default


def test_record_dedup_run_apply_mode_marker():
    """`mode='apply'` deve ser gravado fielmente (não confundir com dry_run)."""
    import asyncio
    db = _FakeDB()
    now = datetime.now(timezone.utc)
    asyncio.run(_record_dedup_run(
        db,
        mode="apply",
        target="dedup_enrollments",
        summary={"affected_students": 1, "would_inactivate": 1, "inactivated": 1},
        diff={"duplicates_removed": [], "kept_records": []},
        actor={"user_id": "u1", "email": "g@x.com", "role": "super_admin"},
        started_at=now,
        finished_at=now,
        duration_ms=0,
    ))
    assert db["dedup_runs"].docs[0]["mode"] == "apply"
