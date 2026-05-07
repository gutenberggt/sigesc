"""
Testes do pipeline de autocomplete + observabilidade.

Cobre:
- mask_cpf
- check_autocomplete_rate_limit (per-user, isolamento)
- cache server-side (TTL, hit/miss, eviction)
- record_autocomplete_call → snapshot (latência, fallback, cache_hit, qlen, top_*)
- p95 via histogram
- normalização de filters_hash (ordem-independente)

Diretriz arquitetural: /app/docs/SEARCH_ARCHITECTURE.md
"""
import os
import sys
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.students_search import (
    mask_cpf,
    check_autocomplete_rate_limit,
    record_autocomplete_call,
    get_observability_snapshot,
    make_cache_key,
    cache_get,
    cache_set,
    hash_query,
    _normalize_filters_hash,
    _reset_all_for_tests,
    CACHE_TTL_SECONDS,
)


@pytest.fixture(autouse=True)
def reset_state():
    """Limpa todo o estado in-memory antes de cada teste."""
    _reset_all_for_tests()
    yield
    _reset_all_for_tests()


# ============================================================================
# mask_cpf
# ============================================================================
class TestMaskCpf:
    def test_cpf_formatado(self):
        assert mask_cpf("123.456.789-01") == "***.456.***-01"

    def test_cpf_apenas_digitos(self):
        assert mask_cpf("12345678901") == "***.456.***-01"

    def test_cpf_invalido_retorna_none(self):
        assert mask_cpf("12345") is None
        assert mask_cpf("") is None
        assert mask_cpf(None) is None


# ============================================================================
# Rate limit
# ============================================================================
class TestRateLimit:
    def test_permite_até_30_chamadas(self):
        for _ in range(30):
            check_autocomplete_rate_limit("user-A")
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            check_autocomplete_rate_limit("user-A")
        assert exc.value.status_code == 429

    def test_isola_users(self):
        for _ in range(30):
            check_autocomplete_rate_limit("user-A")
        # B continua livre
        check_autocomplete_rate_limit("user-B")  # sem exceção

    def test_rate_limit_aparece_no_snapshot(self):
        for _ in range(30):
            check_autocomplete_rate_limit("user-A")
        from fastapi import HTTPException
        for _ in range(3):
            try:
                check_autocomplete_rate_limit("user-A")
            except HTTPException:
                pass
        snap = get_observability_snapshot()
        assert snap["rate_limited_requests"] == 3

    def test_user_id_vazio_não_trava(self):
        for _ in range(100):
            check_autocomplete_rate_limit("")  # sem exceção


# ============================================================================
# Cache
# ============================================================================
class TestCache:
    def test_hit_e_miss(self):
        key = make_cache_key("tenant-1", "ana", {"status": "active"})
        assert cache_get(key) is None  # miss
        cache_set(key, {"items": [{"id": "1"}], "used_fallback": False})
        out = cache_get(key)
        assert out is not None
        assert out["items"][0]["id"] == "1"

    def test_filters_hash_ordem_independente(self):
        a = _normalize_filters_hash({"a": 1, "b": 2})
        b = _normalize_filters_hash({"b": 2, "a": 1})
        assert a == b, "filters_hash deve ser estável independente da ordem do dict"

    def test_cache_key_separa_tenants(self):
        k1 = make_cache_key("tenant-1", "ana", {})
        k2 = make_cache_key("tenant-2", "ana", {})
        assert k1 != k2

    def test_ttl_expira(self):
        # TTL é 5s; vamos esperar simbolicamente alterando o monotonic.
        # Para teste rápido, força expiração via patch direto no timestamp.
        from utils.students_search import _cache, _now
        key = make_cache_key("t", "abc", {})
        cache_set(key, {"x": 1})
        # Força expiração movendo o expires_at para o passado
        old_exp, val = _cache[key]
        _cache[key] = (_now() - 1, val)
        assert cache_get(key) is None  # detecta expiração e remove
        assert key not in _cache


# ============================================================================
# Snapshot / observabilidade
# ============================================================================
class TestObservabilitySnapshot:
    def test_snapshot_vazio(self):
        snap = get_observability_snapshot()
        assert snap["requests_total"] == 0
        assert snap["mode"] == "instance-local"
        assert snap["replica_aware"] is False
        assert "warning" in snap
        assert snap["window"] == "15m"
        assert snap["p95_latency_ms"] is None
        assert snap["top_queries"] == []
        assert snap["top_tenants"] == []
        # config reportada
        assert snap["config"]["cache_ttl_seconds"] == CACHE_TTL_SECONDS
        assert snap["config"]["rate_limit_per_minute"] == 30

    def test_metricas_basicas(self):
        # 3 chamadas: 1 fallback, 1 vazia, 1 cache hit
        record_autocomplete_call(q_norm="ana", duration_ms=8, used_fallback=False,
                                 result_count=1, cache_hit=False, tenant_id="T1")
        record_autocomplete_call(q_norm="silva", duration_ms=20, used_fallback=True,
                                 result_count=2, cache_hit=False, tenant_id="T1")
        record_autocomplete_call(q_norm="zzz", duration_ms=5, used_fallback=False,
                                 result_count=0, cache_hit=True, tenant_id="T2")
        snap = get_observability_snapshot()
        assert snap["requests_total"] == 3
        assert snap["fallback_contains_pct"] == pytest.approx(33.33, rel=1e-2)
        assert snap["empty_results_pct"] == pytest.approx(33.33, rel=1e-2)
        assert snap["cache_hit_pct"] == pytest.approx(33.33, rel=1e-2)

    def test_top_queries_anonimizadas(self):
        # Mesma query → mesmo hash → agrupa
        record_autocomplete_call(q_norm="joao", duration_ms=5, used_fallback=False,
                                 result_count=2, cache_hit=False, tenant_id="T1")
        record_autocomplete_call(q_norm="joao", duration_ms=6, used_fallback=False,
                                 result_count=2, cache_hit=False, tenant_id="T1")
        record_autocomplete_call(q_norm="maria", duration_ms=7, used_fallback=False,
                                 result_count=1, cache_hit=False, tenant_id="T1")
        snap = get_observability_snapshot()
        # Top deve ter 2 entradas, "joao" com count=2
        assert len(snap["top_queries"]) == 2
        first = snap["top_queries"][0]
        assert first["count"] == 2
        # Hash != query (anonimizado)
        assert first["q_hash"] == hash_query("joao")
        assert "joao" not in str(snap["top_queries"])

    def test_top_tenants(self):
        for _ in range(5):
            record_autocomplete_call(q_norm="x", duration_ms=1, used_fallback=False,
                                     result_count=1, cache_hit=False, tenant_id="T1")
        for _ in range(2):
            record_autocomplete_call(q_norm="y", duration_ms=1, used_fallback=False,
                                     result_count=1, cache_hit=False, tenant_id="T2")
        snap = get_observability_snapshot()
        assert snap["top_tenants"][0] == {"tenant_id": "T1", "count": 5}
        assert snap["top_tenants"][1] == {"tenant_id": "T2", "count": 2}

    def test_query_length_distribution(self):
        for q in ["an", "ana", "anar", "anare", "anareli", "anarelinha"]:
            record_autocomplete_call(q_norm=q, duration_ms=1, used_fallback=False,
                                     result_count=1, cache_hit=False, tenant_id="T1")
        snap = get_observability_snapshot()
        d = snap["query_length_distribution"]
        assert d["2"] == 1
        assert d["3"] == 1
        assert d["4"] == 1
        assert d["5"] == 1
        # 7 e 10 chars caem em "7+"
        assert d["7+"] == 2

    def test_p95_via_histogram(self):
        # Latências: 50x 5ms + 5x 100ms → p95 deve cair na borda 100
        for _ in range(50):
            record_autocomplete_call(q_norm="ana", duration_ms=5, used_fallback=False,
                                     result_count=1, cache_hit=False, tenant_id="T1")
        for _ in range(5):
            record_autocomplete_call(q_norm="ana", duration_ms=100, used_fallback=False,
                                     result_count=1, cache_hit=False, tenant_id="T1")
        snap = get_observability_snapshot()
        assert snap["p95_latency_ms"] == 100.0  # bucket onde p95 cai

    def test_avg_latency(self):
        for ms in [10, 20, 30]:
            record_autocomplete_call(q_norm="ana", duration_ms=ms, used_fallback=False,
                                     result_count=1, cache_hit=False, tenant_id="T1")
        snap = get_observability_snapshot()
        assert snap["avg_latency_ms"] == pytest.approx(20.0, rel=1e-2)
