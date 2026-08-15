"""
Sprint 000 — Testes da Fundação do MIG (CMDE).

E4 (paridade): CmdeService reproduz exatamente as respostas dos endpoints atuais.
Unitários: mapper/validators e mapeamento de erros do BaseGovClient para exceções tipadas.
"""
import sys, os, asyncio
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_env():
    # Carrega backend/.env se as vars não estiverem no ambiente
    from pathlib import Path
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()

from motor.motor_asyncio import AsyncIOMotorClient
from mig.cmde.service import CmdeService
from mig.cmde.mapper import CmdeMapper
from mig.cmde import validators
from mig.core.http_client import BaseGovClient
from mig.core.exceptions import MigAuthError, MigForbiddenError, MigTimeoutError, MigUnavailableError, MigConfigError


# ---------- Unitários: mapper/validators ----------
def test_mapper_validators():
    row = CmdeMapper.build_mapping_row(
        {"id": "1", "full_name": "Estudante X", "cpf": "", "nis": "123", "inep_code": ""},
        {"name": "Escola Y", "inep_code": "15175600"})
    assert row["ready"] is False and row["missing_fields"] == ["CPF"], row
    row2 = CmdeMapper.build_mapping_row(
        {"id": "2", "full_name": "Estudante Z", "cpf": "111", "nis": "222", "inep_code": ""},
        {"name": "Escola W", "inep_code": "999"})
    assert row2["ready"] is True and row2["missing_fields"] == [], row2
    # sem INEP da escola → não pronto, INEP Escola faltante
    row3 = CmdeMapper.build_mapping_row(
        {"id": "3", "full_name": "A", "cpf": "1", "nis": "", "inep_code": ""}, {})
    assert row3["ready"] is False and row3["missing_fields"] == ["NIS", "INEP Escola"], row3
    print("OK unit: mapper/validators")


# ---------- Unitários: mapeamento de erros do BaseGovClient ----------
def _fake_client_returning(status_code, text="erro", json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.json = MagicMock(return_value=(json_data if json_data is not None else {"ok": True}))

    class _Ctx:
        def __init__(self_, *a, **k):
            pass
        async def __aenter__(self_):
            m = MagicMock()
            async def _req(*a, **k):
                return resp
            m.request = _req
            return m
        async def __aexit__(self_, *a):
            return False
    return _Ctx


async def _run_client_error_cases():
    import mig.core.http_client as hc
    for code, exc in [(401, MigAuthError), (403, MigForbiddenError)]:
        with patch.object(hc.httpx, "AsyncClient", _fake_client_returning(code)):
            c = BaseGovClient("http://x", provider="cmde")
            try:
                await c.get("/y"); assert False, "deveria levantar"
            except exc:
                pass
    # 200 retorna json
    with patch.object(hc.httpx, "AsyncClient", _fake_client_returning(200, json_data={"a": 1})):
        c = BaseGovClient("http://x", provider="cmde")
        assert await c.get("/y") == {"a": 1}
    print("OK unit: BaseGovClient status mapping")


# ---------- Paridade contra baseline (DB real) ----------
BASELINE_STATUS = {"students_total": 19, "students_with_cpf": 18, "students_with_nis": 19,
                   "schools_total": 6, "schools_with_inep": 6}
BASELINE_MAPPING = {"total": 19, "ready_count": 0, "not_ready_count": 19}


async def _run_parity():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    svc = CmdeService(db)

    status = await svc.sync_status()
    assert status["details"] == BASELINE_STATUS, status["details"]
    assert status["status"] == "not_configured" and status["environment"] == "homologacao"

    mapping = await svc.students_mapping()
    assert mapping["total"] == BASELINE_MAPPING["total"], mapping["total"]
    assert mapping["ready_count"] == BASELINE_MAPPING["ready_count"], mapping["ready_count"]
    assert mapping["not_ready_count"] == BASELINE_MAPPING["not_ready_count"]
    # shape das linhas idêntico ao endpoint atual
    sample = mapping["students"][0]
    assert set(sample.keys()) == {"id", "full_name", "cpf", "nis", "inep_code",
                                  "school_name", "school_inep", "ready", "missing_fields"}, sample.keys()

    cfg = await svc.get_config()
    assert cfg["status"] == "not_configured" and cfg["environment"] == "homologacao"
    # PGP removido (decisão Sprint 000)
    assert "pgp_public_key" not in cfg and "pgp_private_key_configured" not in cfg, cfg

    # elegibilidades sem config → MigConfigError (mesma msg do baseline)
    try:
        await svc.query(search="123"); assert False
    except MigConfigError as e:
        assert "não configurada" in e.message.lower()
    print("OK paridade: sync_status, students_mapping, get_config, query(400)")


# ---------- Sprint 001: audit persistente, retry, feature flags ----------
async def _run_sprint001():
    from mig.core.audit import MigAuditService, COLLECTION
    from mig.core.feature_flags import FeatureFlagService
    from mig.core.retry import run_with_retry, RetryPolicy
    from mig.core.exceptions import MigTimeoutError, MigAuthError, MigConfigError

    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    TP = "cmde_test_sprint001"

    # --- Audit persistente + métricas derivadas ---
    audit = MigAuditService(db)
    await db[COLLECTION].delete_many({"provider": TP})
    await audit.record({"provider": TP, "tenant": "t1", "operation": "elegibilidades",
                        "status": "success", "duration_ms": 120, "records_processed": 5,
                        "started_at": "x", "finished_at": "y"})
    await audit.record({"provider": TP, "tenant": "t1", "operation": "elegibilidades",
                        "status": "error", "duration_ms": 80, "records_processed": 0,
                        "http_status": 503, "error_code": "MigUnavailableError",
                        "error_message": "down", "started_at": "x", "finished_at": "z"})
    m = await audit.metrics(provider=TP, tenant="t1")
    assert m["total_calls"] == 2 and m["success"] == 1 and m["error"] == 1, m
    assert m["success_rate"] == 50.0 and m["avg_latency_ms"] == 100.0, m
    assert m["volume_processed"] == 5 and len(m["recent_failures"]) == 1, m
    ev = await audit.recent(provider=TP, tenant="t1", limit=10)
    assert len(ev) == 2
    await db[COLLECTION].delete_many({"provider": TP})
    print("OK sprint001: auditoria persistente + métricas agregadas")

    # --- RetryManager ---
    calls = {"n": 0}
    async def _flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise MigTimeoutError("timeout")  # 504 recuperável
        return {"ok": True}
    res = await run_with_retry(_flaky, RetryPolicy(max_attempts=3, base_delay_seconds=0.01))
    assert res.value == {"ok": True} and res.attempts == 2, res

    calls2 = {"n": 0}
    async def _fatal():
        calls2["n"] += 1
        raise MigAuthError("no")  # 401 não recuperável
    try:
        await run_with_retry(_fatal, RetryPolicy(max_attempts=3, base_delay_seconds=0.01))
        assert False
    except MigAuthError:
        assert calls2["n"] == 1, "não recuperável não deve retentar"
    print("OK sprint001: RetryManager (recuperável retenta, fatal não)")

    # --- Feature flags dinâmicas ---
    flags = FeatureFlagService(db)
    from mig.core.feature_flags import COLLECTION as FCOL
    await db[FCOL].delete_many({"flag": "cmde.elegibilidades", "tenant": "tX"})
    assert await flags.is_enabled("cmde.elegibilidades", "tX", "homologacao") is True  # default
    await flags.set_flag("cmde.elegibilidades", False, tenant="tX", environment="homologacao", actor="admin")
    assert await flags.is_enabled("cmde.elegibilidades", "tX", "homologacao") is False  # override
    assert await flags.is_enabled("cmde.elegibilidades", "outro", "homologacao") is True  # não afeta outro tenant
    eff = await flags.effective("tX", "homologacao")
    assert eff["cmde.elegibilidades"] is False and eff["cmde.enabled"] is True, eff
    await db[FCOL].delete_many({"flag": "cmde.elegibilidades", "tenant": "tX"})
    print("OK sprint001: feature flags dinâmicas por tenant/ambiente")

    # --- Service: flag desabilitada bloqueia query mesmo sem config? (config vem antes) ---
    # query sem config continua 400 (paridade) — já coberto em _run_parity
    svc = CmdeService(db)
    fx = await svc.feature_flags(context={"tenant": None})
    assert {"cmde.enabled", "cmde.elegibilidades", "cmde.retry"}.issubset(set(fx["flags"].keys())), fx
    print("OK sprint001: service.feature_flags/metrics/audit_events")


# ---------- Sprint 001.1: hardening (correlation_id, audit de flags, paginação, carga) ----------
async def _run_sprint011():
    from mig.core.audit import MigAuditService, COLLECTION
    from mig.core.ids import generate_correlation_id
    from mig.core.exceptions import MigTimeoutError, MigUnavailableError
    import mig.cmde.service as service_mod

    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    # correlation_id formato CMDE-YYYYMMDD-XXXXX
    cid = generate_correlation_id("CMDE")
    assert cid.startswith("CMDE-") and len(cid.split("-")) == 3 and len(cid.split("-")[2]) == 5, cid

    # --- Auditoria de Feature Flag (P0) ---
    svc = CmdeService(db)
    await db["mig_feature_flags"].delete_many({"flag": "cmde.retry", "tenant": "ff_t"})
    await db[COLLECTION].delete_many({"tenant": "ff_t"})
    await svc.set_feature_flag("cmde.retry", False, context={"tenant": "ff_t", "actor": "admin@x"}, environment="homologacao")
    ev = await db[COLLECTION].find_one({"tenant": "ff_t", "operation": "FEATURE_FLAG_UPDATED"}, {"_id": 0})
    assert ev and ev["feature"] == "cmde.retry" and ev["previous_value"] is True and ev["new_value"] is False, ev
    assert ev["actor"] == "admin@x" and ev["correlation_id"] and ev["environment"] == "homologacao", ev
    await db["mig_feature_flags"].delete_many({"flag": "cmde.retry", "tenant": "ff_t"})
    await db[COLLECTION].delete_many({"tenant": "ff_t"})
    print("OK sprint011: auditoria de FEATURE_FLAG_UPDATED (old/new/actor/correlation_id)")

    # --- Paginação e filtros (P1) ---
    audit = MigAuditService(db)
    TT = "pg_t"
    await db[COLLECTION].delete_many({"tenant": TT})
    for i in range(7):
        await audit.record({"provider": "cmde", "tenant": TT, "operation": "elegibilidades",
                            "status": "success" if i % 2 == 0 else "error", "records_processed": i,
                            "started_at": "x", "finished_at": "y"})
    p1 = await audit.query_events(provider="cmde", tenant=TT, page=1, page_size=5)
    assert p1["total"] == 7 and len(p1["events"]) == 5 and p1["total_pages"] == 2, p1
    p2 = await audit.query_events(provider="cmde", tenant=TT, page=2, page_size=5)
    assert len(p2["events"]) == 2, p2
    only_err = await audit.query_events(provider="cmde", tenant=TT, status="error")
    assert only_err["total"] == 3 and all(e["status"] == "error" for e in only_err["events"]), only_err
    # ordenação desc por created_at
    dates = [e["created_at"] for e in p1["events"]]
    assert dates == sorted(dates, reverse=True), "deve ordenar desc"
    await db[COLLECTION].delete_many({"tenant": TT})
    print("OK sprint011: paginação + filtro status + ordenação desc")

    # --- Carga/resiliência (P1): multi-tenant concorrente + retry + erro definitivo ---
    class _FakeClient:
        def __init__(self, fail_times=0, always_fail=False, **kw):
            self.fail_times = fail_times; self.always_fail = always_fail; self._n = 0
            self.last_attempts = 0
        async def elegibilidade_por_documento(self, doc):
            self._n += 1; self.last_attempts = self._n
            if self.always_fail:
                raise MigUnavailableError("down")
            if self._n <= self.fail_times:
                raise MigTimeoutError("timeout")
            return [{"id": 1}, {"id": 2}]

    orig_client = service_mod.CmdeClient
    LT_TENANTS = ["lt_a", "lt_b", "lt_c"]
    await db[COLLECTION].delete_many({"tenant": {"$in": LT_TENANTS + ["lt_fail"]}})

    svc2 = CmdeService(db)
    async def _fake_raw():
        return {"api_key": "x", "environment": "homologacao"}
    svc2.config_repo.get_raw = _fake_raw
    async def _noop(_): return None
    svc2.config_repo.touch_last_sync = _noop

    try:
        # sucesso imediato, 3 tenants em paralelo (retry mecânico já coberto no unit)
        service_mod.CmdeClient = lambda **kw: _FakeClient(fail_times=0, **kw)
        await asyncio.gather(*[
            svc2.query(search="123", context={"tenant": t, "actor": "u"}) for t in LT_TENANTS
        ])
        # erro definitivo
        service_mod.CmdeClient = lambda **kw: _FakeClient(always_fail=True, **kw)
        try:
            await svc2.query(search="123", context={"tenant": "lt_fail", "actor": "u"})
            assert False
        except MigUnavailableError:
            pass
    finally:
        service_mod.CmdeClient = orig_client

    # consistência: 1 evento por tenant de sucesso, com correlation_id único
    for t in LT_TENANTS:
        evs = await db[COLLECTION].find({"tenant": t}, {"_id": 0}).to_list(10)
        assert len(evs) == 1 and evs[0]["status"] == "success" and evs[0]["attempts"] == 1, (t, evs)
        assert evs[0]["records_processed"] == 2 and evs[0]["correlation_id"], evs
    fail_evs = await db[COLLECTION].find({"tenant": "lt_fail"}, {"_id": 0}).to_list(10)
    assert len(fail_evs) == 1 and fail_evs[0]["status"] == "error" and fail_evs[0]["http_status"] == 503, fail_evs
    cids = {(await db[COLLECTION].find_one({"tenant": t}))["correlation_id"] for t in LT_TENANTS}
    assert len(cids) == 3, "correlation_ids devem ser únicos por execução"
    await db[COLLECTION].delete_many({"tenant": {"$in": LT_TENANTS + ["lt_fail"]}})
    print("OK sprint011: carga multi-tenant, retry, erro definitivo, sem duplicação")

    # --- Retry integrado ao BaseGovClient (503,503,200 → ok em 3 tentativas) ---
    import mig.core.http_client as hc
    from mig.core.retry import RetryPolicy as _RP
    rcalls = {"n": 0}
    def _retry_ctx(*a, **k):
        class _C:
            def __init__(s, *aa, **kk): pass
            async def __aenter__(s):
                m = MagicMock()
                async def _req(*aa, **kk):
                    rcalls["n"] += 1
                    r = MagicMock()
                    if rcalls["n"] >= 3:
                        r.status_code = 200; r.json = MagicMock(return_value={"ok": 1}); r.text = ""
                    else:
                        r.status_code = 503; r.text = "down"
                    return r
                m.request = _req; return m
            async def __aexit__(s, *aa): return False
        return _C()
    with patch.object(hc.httpx, "AsyncClient", _retry_ctx):
        c = BaseGovClient("http://x", provider="cmde", retry_policy=_RP(max_attempts=3, base_delay_seconds=0.01))
        out = await c.get("/y")
        assert out == {"ok": 1} and c.last_attempts == 3, (out, c.last_attempts)
    print("OK sprint011: retry integrado no BaseGovClient (503,503,200)")

    # --- Métricas preparadas para CMDE futuro ---
    m = await svc2.metrics(context={"tenant": None})
    for k in ("students_sent", "students_accepted", "students_rejected", "processing_rate"):
        assert k in m, m
    print("OK sprint011: métricas preparadas para envio CMDE (Sprint 002)")


if __name__ == "__main__":
    test_mapper_validators()
    asyncio.run(_run_client_error_cases())
    asyncio.run(_run_parity())
    asyncio.run(_run_sprint001())
    asyncio.run(_run_sprint011())
    print("\nSPRINT 000/001/001.1 — TODOS OS TESTES PASSARAM ✅")
