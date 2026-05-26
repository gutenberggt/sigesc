"""
[Sprint 1.1 — Extração arquitetural] Testes do orquestrador
`with_critical_mutation` em `/app/backend/lib/critical_mutation.py`.

Cobre:
  - Fluxo feliz: lock adquirido, executor roda, run gravado, payload enriquecido
  - Idempotency replay: 2ª chamada com mesma key retorna cache sem reexecutar
  - Concorrência: 2ª chamada concorrente recebe HTTPException 409
  - Sem Idempotency-Key: comportamento legacy preservado
  - Liberação do lock após falha do executor
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.critical_mutation import (  # noqa: E402
    with_critical_mutation,
)


# ---------------------------------------------------------------------------
# Fakes mínimos para FastAPI Request/Response e Mongo
# ---------------------------------------------------------------------------
class _FakeRequest:
    def __init__(self, headers=None):
        self.headers = headers or {}


class _FakeResponse:
    def __init__(self):
        self.headers = {}


class _FakeCollection:
    def __init__(self):
        self.docs: list = []
        self.indexes: list = []

    async def create_index(self, keys, **kwargs):
        self.indexes.append({"keys": keys, "kwargs": kwargs})

    def _has_unique_key_target(self) -> bool:
        for ix in self.indexes:
            if ix["kwargs"].get("unique") and ix["keys"] == [("key", 1), ("target", 1)]:
                return True
        return False

    async def insert_one(self, doc):
        if "_id" in doc:
            for d in self.docs:
                if d.get("_id") == doc["_id"]:
                    raise DuplicateKeyError(f"dup _id={doc['_id']}")
        if self._has_unique_key_target() and "key" in doc and "target" in doc:
            for d in self.docs:
                if d.get("key") == doc["key"] and d.get("target") == doc["target"]:
                    raise DuplicateKeyError("dup (key,target)")
        # uniqueness for run_id (uniq index)
        for ix in self.indexes:
            if ix["kwargs"].get("unique") and ix["keys"] == "run_id":
                for d in self.docs:
                    if d.get("run_id") == doc.get("run_id"):
                        raise DuplicateKeyError("dup run_id")
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


def _aio(coro):
    return asyncio.run(coro)


def _common_kwargs(db):
    return dict(
        target="test_target",
        runs_collection="test_runs",
        locks_collection="test_locks",
        idempotency_collection="test_idemp",
    )


# ---------------------------------------------------------------------------
# Cenários
# ---------------------------------------------------------------------------
def test_happy_path_executor_runs_and_run_recorded():
    db = _FakeDB()
    req = _FakeRequest(); res = _FakeResponse()
    actor = {"id": "u1", "email": "g@x.com", "role": "super_admin"}

    async def executor():
        return {
            "mode": "dry_run",
            "summary": {"affected": 10},
            "diff": {"duplicates_removed": [], "kept_records": []},
            "payload": {"affected_students": 10, "dry_run": True},
        }

    payload = _aio(with_critical_mutation(
        db, actor=actor, request=req, response=res, executor=executor,
        **_common_kwargs(db),
    ))

    # Payload enriquecido
    assert payload["affected_students"] == 10
    assert "run_id" in payload
    assert "started_at" in payload and "finished_at" in payload
    assert "duration_ms" in payload

    # Run gravado na collection certa
    runs = db["test_runs"].docs
    assert len(runs) == 1
    assert runs[0]["target"] == "test_target"
    assert runs[0]["mode"] == "dry_run"
    assert runs[0]["actor"]["email"] == "g@x.com"
    assert "execution_fingerprint" in runs[0]

    # Lock foi LIBERADO ao final (try/finally)
    assert len(db["test_locks"].docs) == 0


def test_idempotency_replay_returns_cached_without_reexecuting():
    db = _FakeDB()
    actor = {"id": "u1", "email": "g@x.com", "role": "super_admin"}
    executor_calls = {"count": 0}

    async def executor():
        executor_calls["count"] += 1
        return {
            "mode": "apply",
            "summary": {"x": 1}, "diff": {},
            "payload": {"data": "first-run"},
        }

    # 1ª chamada — executa
    req1 = _FakeRequest({"Idempotency-Key": "k-abc"}); res1 = _FakeResponse()
    p1 = _aio(with_critical_mutation(
        db, actor=actor, request=req1, response=res1, executor=executor,
        **_common_kwargs(db),
    ))
    assert executor_calls["count"] == 1
    assert res1.headers.get("X-Idempotent-Replay") == "false"
    first_run_id = p1["run_id"]

    # 2ª chamada com MESMA key — NÃO executa, retorna cache
    req2 = _FakeRequest({"Idempotency-Key": "k-abc"}); res2 = _FakeResponse()
    p2 = _aio(with_critical_mutation(
        db, actor=actor, request=req2, response=res2, executor=executor,
        **_common_kwargs(db),
    ))
    assert executor_calls["count"] == 1  # NÃO subiu
    assert res2.headers.get("X-Idempotent-Replay") == "true"
    assert p2["run_id"] == first_run_id
    assert p2["data"] == "first-run"


def test_concurrent_call_raises_409_with_lock_info():
    """Lock pré-existente válido → 2ª chamada recebe 409."""
    db = _FakeDB()
    actor = {"id": "u1", "email": "g@x.com", "role": "super_admin"}

    # Simula lock já segurado por outro ator
    future = datetime.now(timezone.utc) + timedelta(minutes=5)
    db["test_locks"].docs.append({
        "_id": "test_target",
        "holder": "alice:abcdef",
        "acquired_at": datetime.now(timezone.utc),
        "expires_at": future,
    })

    async def executor():
        raise AssertionError("executor NÃO deve rodar — lock em uso")

    req = _FakeRequest(); res = _FakeResponse()
    with pytest.raises(HTTPException) as exc:
        _aio(with_critical_mutation(
            db, actor=actor, request=req, response=res, executor=executor,
            **_common_kwargs(db),
        ))

    assert exc.value.status_code == 409
    detail = exc.value.detail
    assert detail["lock_holder"] == "alice:abcdef"
    assert detail["target"] == "test_target"
    assert "expires_at" in detail


def test_no_idempotency_key_keeps_legacy_behavior():
    """Sem header → executa normal, sem cache, sem header de replay."""
    db = _FakeDB()
    actor = {"id": "u1", "email": "g@x.com", "role": "super_admin"}

    async def executor():
        return {"mode": "apply", "summary": {}, "diff": {}, "payload": {"ok": True}}

    req = _FakeRequest()  # sem Idempotency-Key
    res = _FakeResponse()
    payload = _aio(with_critical_mutation(
        db, actor=actor, request=req, response=res, executor=executor,
        **_common_kwargs(db),
    ))

    assert payload["ok"] is True
    assert "X-Idempotent-Replay" not in res.headers
    # Cache não foi tocado
    assert len(db["test_idemp"].docs) == 0


def test_lock_released_after_executor_failure():
    """Se executor lança exceção, o lock DEVE ser liberado mesmo assim."""
    db = _FakeDB()
    actor = {"id": "u1", "email": "g@x.com", "role": "super_admin"}

    async def executor():
        raise RuntimeError("falha simulada no executor")

    req = _FakeRequest(); res = _FakeResponse()
    with pytest.raises(RuntimeError, match="falha simulada"):
        _aio(with_critical_mutation(
            db, actor=actor, request=req, response=res, executor=executor,
            **_common_kwargs(db),
        ))

    # Lock liberado — não deve impedir próxima chamada
    assert len(db["test_locks"].docs) == 0


def test_different_targets_dont_share_lock():
    """Locks são por target; targets distintos rodam em paralelo."""
    db = _FakeDB()
    actor = {"id": "u1", "email": "g@x.com", "role": "super_admin"}

    async def executor():
        return {"mode": "apply", "summary": {}, "diff": {}, "payload": {"ok": True}}

    req = _FakeRequest(); res = _FakeResponse()

    p1 = _aio(with_critical_mutation(
        db, target="target_A", actor=actor, request=req, response=res,
        executor=executor,
        runs_collection="runs_A",
        locks_collection="locks_A",
        idempotency_collection="idemp_A",
    ))
    p2 = _aio(with_critical_mutation(
        db, target="target_B", actor=actor, request=req, response=res,
        executor=executor,
        runs_collection="runs_B",
        locks_collection="locks_B",
        idempotency_collection="idemp_B",
    ))

    assert p1["ok"] is True
    assert p2["ok"] is True
    # Runs em coleções separadas
    assert len(db["runs_A"].docs) == 1
    assert len(db["runs_B"].docs) == 1


def test_payload_run_id_injected_automatically():
    """O wrapper injeta `run_id` no payload sem o executor precisar saber dele."""
    db = _FakeDB()
    actor = {"id": "u1", "email": "g@x.com", "role": "super_admin"}

    async def executor():
        # Payload sem run_id — wrapper deve injetar
        return {"mode": "apply", "summary": {}, "diff": {}, "payload": {"x": 42}}

    req = _FakeRequest(); res = _FakeResponse()
    payload = _aio(with_critical_mutation(
        db, actor=actor, request=req, response=res, executor=executor,
        **_common_kwargs(db),
    ))

    assert payload["x"] == 42
    assert payload["run_id"] == db["test_runs"].docs[0]["run_id"]
