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
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routers.dedup_enrollments import (  # noqa: E402
    _normalize_created_at,
    _record_dedup_run,
    _execution_fingerprint,
    _acquire_lock,
    _release_lock,
    _idempotent_lookup,
    _idempotent_save,
)
from pymongo.errors import DuplicateKeyError  # noqa: E402


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
    """In-memory fake suficiente para os helpers de lock/idempotency.

    Suporta:
      - insert_one (com DuplicateKeyError se _id ou (key,target) já existir)
      - find_one (match exato em campos top-level)
      - replace_one (com filtro {_id, expires_at:{$lte: now}}) → modified_count
      - delete_one (filtro {_id, holder})
      - create_index (registra; usado pra simular uniqueness)
    """
    def __init__(self):
        self.docs: list = []
        self.indexes: list = []

    async def create_index(self, keys, **kwargs):
        self.indexes.append({"keys": keys, "kwargs": kwargs})

    def _has_unique_id(self) -> bool:
        # _id é sempre único por convenção MongoDB
        return True

    def _has_unique_key_target(self) -> bool:
        for ix in self.indexes:
            if ix["kwargs"].get("unique") and ix["keys"] == [("key", 1), ("target", 1)]:
                return True
        return False

    async def insert_one(self, doc):
        # uniqueness por _id
        if "_id" in doc:
            for d in self.docs:
                if d.get("_id") == doc["_id"]:
                    raise DuplicateKeyError(f"dup _id={doc['_id']}")
        # uniqueness por (key, target) se índice criado
        if self._has_unique_key_target() and "key" in doc and "target" in doc:
            for d in self.docs:
                if d.get("key") == doc["key"] and d.get("target") == doc["target"]:
                    raise DuplicateKeyError(f"dup (key,target)")
        self.docs.append(dict(doc))
        return type("R", (), {"inserted_id": doc.get("_id") or "fake"})()

    async def find_one(self, query, projection=None):
        for d in self.docs:
            if self._matches(d, query):
                return dict(d)
        return None

    async def replace_one(self, query, new_doc, upsert=False):
        for i, d in enumerate(self.docs):
            if self._matches(d, query):
                self.docs[i] = dict(new_doc)
                return type("R", (), {"modified_count": 1, "matched_count": 1})()
        return type("R", (), {"modified_count": 0, "matched_count": 0})()

    async def delete_one(self, query):
        for i, d in enumerate(self.docs):
            if self._matches(d, query):
                del self.docs[i]
                return type("R", (), {"deleted_count": 1})()
        return type("R", (), {"deleted_count": 0})()

    @staticmethod
    def _matches(doc, query) -> bool:
        for k, v in query.items():
            actual = doc.get(k)
            if isinstance(v, dict) and "$lte" in v:
                if actual is None or actual > v["$lte"]:
                    return False
            elif isinstance(v, dict) and "$lt" in v:
                if actual is None or actual >= v["$lt"]:
                    return False
            else:
                if actual != v:
                    return False
        return True


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


# ---------------------------------------------------------------------------
# [Sprint 1.1 — Hardening] Idempotency-Key + Lock + Execution Fingerprint
# ---------------------------------------------------------------------------
def _aio(coro):
    """Roda corotina em event loop novo (test helper)."""
    import asyncio
    return asyncio.run(coro)


def test_execution_fingerprint_deterministic_same_day():
    """Mesmo (target, mode, dia UTC) → mesmo fingerprint."""
    t1 = datetime(2026, 5, 26, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 5, 26, 23, 59, 59, tzinfo=timezone.utc)
    fp1 = _execution_fingerprint("dedup_enrollments", "apply", t1)
    fp2 = _execution_fingerprint("dedup_enrollments", "apply", t2)
    assert fp1 == fp2
    assert len(fp1) == 16  # hex truncado


def test_execution_fingerprint_changes_per_target():
    when = datetime(2026, 5, 26, 12, 0, 0, tzinfo=timezone.utc)
    fp_a = _execution_fingerprint("dedup_enrollments", "apply", when)
    fp_b = _execution_fingerprint("dedup_disabilities", "apply", when)
    assert fp_a != fp_b


def test_execution_fingerprint_changes_per_mode():
    when = datetime(2026, 5, 26, 12, 0, 0, tzinfo=timezone.utc)
    fp_dry = _execution_fingerprint("dedup_enrollments", "dry_run", when)
    fp_app = _execution_fingerprint("dedup_enrollments", "apply", when)
    assert fp_dry != fp_app


def test_record_dedup_run_includes_execution_fingerprint():
    """`dedup_runs` agora carrega `execution_fingerprint` automaticamente."""
    db = _FakeDB()
    now = datetime(2026, 5, 26, 12, tzinfo=timezone.utc)
    _aio(_record_dedup_run(
        db,
        mode="apply",
        target="dedup_enrollments",
        summary={}, diff={"duplicates_removed": [], "kept_records": []},
        actor={"user_id": "u1", "email": "g@x.com", "role": "super_admin"},
        started_at=now, finished_at=now, duration_ms=0,
    ))
    doc = db["dedup_runs"].docs[0]
    assert "execution_fingerprint" in doc
    assert doc["execution_fingerprint"] == _execution_fingerprint(
        "dedup_enrollments", "apply", now
    )


# ---- LOCK ----

def test_lock_acquire_when_no_existing_doc():
    db = _FakeDB()
    acquired, doc = _aio(_acquire_lock(db, "dedup_enrollments", "alice"))
    assert acquired is True
    assert doc["holder"] == "alice"
    assert doc["_id"] == "dedup_enrollments"
    # Doc realmente foi inserido
    assert len(db["dedup_locks"].docs) == 1


def test_lock_acquire_blocks_concurrent_caller():
    """Segunda chamada concorrente recebe `acquired=False` com info do holder."""
    db = _FakeDB()
    a1, doc1 = _aio(_acquire_lock(db, "dedup_enrollments", "alice", ttl_seconds=600))
    assert a1 is True

    a2, doc2 = _aio(_acquire_lock(db, "dedup_enrollments", "bob", ttl_seconds=600))
    assert a2 is False
    assert doc2["holder"] == "alice"  # Bob vê quem está segurando


def test_lock_release_only_by_holder():
    """Release com holder errado NÃO remove o lock."""
    db = _FakeDB()
    _aio(_acquire_lock(db, "dedup_enrollments", "alice"))
    _aio(_release_lock(db, "dedup_enrollments", "bob"))  # holder errado
    assert len(db["dedup_locks"].docs) == 1  # ainda lá
    # Release pelo holder real
    _aio(_release_lock(db, "dedup_enrollments", "alice"))
    assert len(db["dedup_locks"].docs) == 0


def test_lock_can_be_reacquired_after_release():
    """Após release, próxima chamada consegue o lock."""
    db = _FakeDB()
    _aio(_acquire_lock(db, "dedup_enrollments", "alice"))
    _aio(_release_lock(db, "dedup_enrollments", "alice"))
    a2, _ = _aio(_acquire_lock(db, "dedup_enrollments", "bob"))
    assert a2 is True


def test_lock_takes_over_expired_lock():
    """Lock expirado (TTL ainda não rodou) é assumido pelo próximo caller."""
    db = _FakeDB()
    # Insere manualmente um lock JÁ expirado
    past = datetime.now(timezone.utc) - timedelta(minutes=20)
    db["dedup_locks"].docs.append({
        "_id": "dedup_enrollments",
        "holder": "alice-old",
        "acquired_at": past,
        "expires_at": past,
    })
    acquired, doc = _aio(_acquire_lock(db, "dedup_enrollments", "bob"))
    assert acquired is True
    assert doc["holder"] == "bob"


def test_lock_granular_per_target():
    """Locks são por target → diferentes targets não bloqueiam um ao outro."""
    db = _FakeDB()
    a1, _ = _aio(_acquire_lock(db, "dedup_enrollments", "alice"))
    a2, _ = _aio(_acquire_lock(db, "dedup_disabilities", "alice"))
    assert a1 is True
    assert a2 is True
    assert len(db["dedup_locks"].docs) == 2


# ---- IDEMPOTENCY ----

def test_idempotent_lookup_miss_returns_none():
    db = _FakeDB()
    cached = _aio(_idempotent_lookup(db, "key-xxx", "dedup_enrollments"))
    assert cached is None


def test_idempotent_save_then_lookup_hits():
    db = _FakeDB()
    response = {"run_id": "r1", "inactivated": 195, "dry_run": False}
    _aio(_idempotent_save(db, "key-aaa", "dedup_enrollments", "r1", response))
    cached = _aio(_idempotent_lookup(db, "key-aaa", "dedup_enrollments"))
    assert cached is not None
    assert cached["response"]["inactivated"] == 195
    assert cached["response"]["run_id"] == "r1"


def test_idempotent_save_duplicate_key_does_not_raise():
    """Race: duas saves com mesma key → segunda é silenciosamente ignorada."""
    db = _FakeDB()
    resp_a = {"run_id": "r1", "inactivated": 195}
    resp_b = {"run_id": "r2", "inactivated": 999}
    _aio(_idempotent_save(db, "key-zzz", "dedup_enrollments", "r1", resp_a))
    # Não deve estourar — apenas loga e segue
    _aio(_idempotent_save(db, "key-zzz", "dedup_enrollments", "r2", resp_b))
    # Doc mantido é o primeiro
    cached = _aio(_idempotent_lookup(db, "key-zzz", "dedup_enrollments"))
    assert cached["response"]["run_id"] == "r1"


def test_idempotent_different_keys_independent():
    db = _FakeDB()
    _aio(_idempotent_save(db, "k1", "dedup_enrollments", "r1", {"x": 1}))
    _aio(_idempotent_save(db, "k2", "dedup_enrollments", "r2", {"x": 2}))
    c1 = _aio(_idempotent_lookup(db, "k1", "dedup_enrollments"))
    c2 = _aio(_idempotent_lookup(db, "k2", "dedup_enrollments"))
    assert c1["response"]["x"] == 1
    assert c2["response"]["x"] == 2


def test_idempotent_same_key_different_targets_are_independent():
    """A unicidade é (key, target). Mesma key em outro target é livre."""
    db = _FakeDB()
    _aio(_idempotent_save(db, "k1", "dedup_enrollments", "r1", {"a": 1}))
    _aio(_idempotent_save(db, "k1", "dedup_disabilities", "r2", {"a": 2}))
    c_a = _aio(_idempotent_lookup(db, "k1", "dedup_enrollments"))
    c_b = _aio(_idempotent_lookup(db, "k1", "dedup_disabilities"))
    assert c_a["response"]["a"] == 1
    assert c_b["response"]["a"] == 2

