"""
Pipeline de autocomplete + observabilidade de busca de alunos.

Diretriz arquitetural SIGESC [Fev/2026] — ver /app/docs/SEARCH_ARCHITECTURE.md.

Componentes:
- Cache server-side leve (TTL 5s, tenant-aware, instrumentado).
- Rate limit per-user (sliding window in-memory).
- Mascaramento de CPF.
- Telemetria com janela deslizante 15min em buckets de 1min:
    * latência via histogram buckets (p95 incremental, sem sort).
    * cache hit/miss.
    * query_length_distribution.
    * top queries (SHA1 truncado da query NORMALIZADA — sem PII reversível trivial).
    * top tenants.
    * rate_limited_requests.
- Aviso explícito: métricas são instance-local (não consolidadas em multi-réplica).

NÃO persiste nada — restart zera. Roadmap (Fase 2 docs): Redis ou Mongo capped.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import logging
from collections import defaultdict, Counter
from datetime import datetime, timezone
from typing import Optional, Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# ============================================================================
# Constantes
# ============================================================================
CACHE_TTL_SECONDS = 5         # TTL curto: autocomplete muda a cada keystroke
CACHE_MAX_ENTRIES = 1000      # cap simples; LRU-like via timestamp

RATE_LIMIT_MAX_CALLS = 30
RATE_LIMIT_WINDOW_SECONDS = 60

OBSERVABILITY_WINDOW_MINUTES = 15

# Histogram buckets de latência (ms) — bordas inclusivas à direita.
# p95 calculado por inversão de CDF a partir destes buckets.
LATENCY_BUCKETS_MS = [1, 2, 5, 10, 25, 50, 100, 250, 500, 1000]

TOP_N_QUERIES = 20
TOP_N_TENANTS = 10


# ============================================================================
# Cache server-side (in-memory, TTL deslizante)
# ============================================================================
_cache: dict[str, tuple[float, Any]] = {}
_cache_hits = 0  # contadores globais (também alimentam o bucket atual)
_cache_misses = 0


def _now() -> float:
    return time.monotonic()


def _normalize_filters_hash(filters: Optional[dict]) -> str:
    """Hash estável dos filtros (json.dumps sort_keys=True)."""
    if not filters:
        return "noflt"
    payload = json.dumps(filters, sort_keys=True, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8]


def make_cache_key(tenant_id: Optional[str], q_norm: str, filters: Optional[dict]) -> str:
    return f"{tenant_id or 'none'}|{q_norm}|{_normalize_filters_hash(filters)}"


def cache_get(key: str) -> Optional[Any]:
    """Retorna valor cacheado se ainda vigente; senão None.

    TTL **deslizante**: ao consumir, NÃO renova (autocomplete muda rápido,
    renovar mantém entradas obsoletas no quente). Apenas valida expiração.
    """
    global _cache_hits, _cache_misses
    entry = _cache.get(key)
    if entry is None:
        _cache_misses += 1
        return None
    expires_at, value = entry
    if _now() > expires_at:
        _cache.pop(key, None)
        _cache_misses += 1
        return None
    _cache_hits += 1
    return value


def cache_set(key: str, value: Any) -> None:
    if len(_cache) >= CACHE_MAX_ENTRIES:
        # Evict expirados primeiro
        now = _now()
        expired = [k for k, (exp, _) in _cache.items() if exp <= now]
        for k in expired:
            _cache.pop(k, None)
        # Se ainda lotado, descarta o mais antigo (timestamp == expires_at - TTL)
        if len(_cache) >= CACHE_MAX_ENTRIES:
            oldest = min(_cache.items(), key=lambda kv: kv[1][0])
            _cache.pop(oldest[0], None)
    _cache[key] = (_now() + CACHE_TTL_SECONDS, value)


def _cache_memory_estimate_kb() -> float:
    """Estimativa grossa de memória do cache em KB.

    Aproxima por len(json) — preciso o suficiente para detectar tendência.
    """
    if not _cache:
        return 0.0
    sample = list(_cache.values())[:50]
    sample_bytes = sum(len(json.dumps(v[1], default=str)) for v in sample)
    avg = sample_bytes / max(len(sample), 1)
    return round((avg * len(_cache)) / 1024, 2)


# ============================================================================
# Rate limit per-user (sliding window simples)
# ============================================================================
_rate_buckets: dict[str, list[float]] = defaultdict(list)
_rate_limited_total = 0  # alimenta bucket atual


def check_autocomplete_rate_limit(user_id: str) -> None:
    """Levanta 429 se exceder. Atualiza contador de telemetria."""
    global _rate_limited_total
    if not user_id:
        return
    now = _now()
    bucket = _rate_buckets[user_id]
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    while bucket and bucket[0] < cutoff:
        bucket.pop(0)
    if len(bucket) >= RATE_LIMIT_MAX_CALLS:
        _rate_limited_total += 1
        # Registra rate limit no bucket atual de telemetria
        _record_event(rate_limited=True)
        raise HTTPException(
            status_code=429,
            detail="Muitas buscas em sequência. Aguarde alguns segundos."
        )
    bucket.append(now)


# ============================================================================
# Mascaramento
# ============================================================================
def mask_cpf(cpf: Optional[str]) -> Optional[str]:
    if not cpf:
        return None
    digits = re.sub(r"\D", "", cpf)
    if len(digits) != 11:
        return None
    return f"***.{digits[3:6]}.***-{digits[9:11]}"


# ============================================================================
# Sliding window 15min em buckets de 1min
# ============================================================================
def _current_bucket_key() -> str:
    """ISO 8601 truncado ao minuto (UTC). Estável p/ agregação."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def _new_bucket() -> dict:
    return {
        "requests": 0,
        "fallback": 0,
        "empty": 0,
        "rate_limited": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        # histogram de latência (índice == bucket borda; último = "overflow")
        "latency_hist": [0] * (len(LATENCY_BUCKETS_MS) + 1),
        "latency_sum_ms": 0.0,
        # query length: 2,3,4,5,6,7+
        "qlen": Counter(),
        # SHA1 truncado da q_norm — sem PII reversível trivial
        "q_hashes": Counter(),
        # tenant breakdown
        "tenants": Counter(),
    }


_buckets: dict[str, dict] = {}


def _gc_old_buckets() -> None:
    """Remove buckets fora da janela de 15 min."""
    if not _buckets:
        return
    now = datetime.now(timezone.utc)
    cutoff = now.timestamp() - (OBSERVABILITY_WINDOW_MINUTES * 60 + 30)
    stale = []
    for k in _buckets.keys():
        try:
            ts = datetime.strptime(k, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc).timestamp()
            if ts < cutoff:
                stale.append(k)
        except Exception:
            stale.append(k)  # chave malformada — drop
    for k in stale:
        _buckets.pop(k, None)


def _record_event(*, rate_limited: bool = False) -> None:
    """Registra evento mínimo (rate_limited)."""
    _gc_old_buckets()
    key = _current_bucket_key()
    bucket = _buckets.setdefault(key, _new_bucket())
    if rate_limited:
        bucket["rate_limited"] += 1


def _latency_to_bucket_index(duration_ms: float) -> int:
    for i, edge in enumerate(LATENCY_BUCKETS_MS):
        if duration_ms <= edge:
            return i
    return len(LATENCY_BUCKETS_MS)  # overflow


def hash_query(q_norm: str) -> str:
    """SHA1 truncado da query JÁ NORMALIZADA (lowercase, sem acentos, trim)."""
    return hashlib.sha1(q_norm.encode("utf-8")).hexdigest()[:8]


def record_autocomplete_call(
    *,
    q_norm: str,
    duration_ms: float,
    used_fallback: bool,
    result_count: int,
    cache_hit: bool,
    tenant_id: Optional[str],
) -> None:
    """Registra um evento completo de autocomplete no bucket atual."""
    _gc_old_buckets()
    key = _current_bucket_key()
    bucket = _buckets.setdefault(key, _new_bucket())

    bucket["requests"] += 1
    if used_fallback:
        bucket["fallback"] += 1
    if result_count == 0:
        bucket["empty"] += 1
    if cache_hit:
        bucket["cache_hits"] += 1
    else:
        bucket["cache_misses"] += 1

    bucket["latency_sum_ms"] += duration_ms
    bucket["latency_hist"][_latency_to_bucket_index(duration_ms)] += 1

    qlen = len(q_norm)
    qlen_key = "7+" if qlen >= 7 else str(qlen)
    bucket["qlen"][qlen_key] += 1

    bucket["q_hashes"][hash_query(q_norm)] += 1

    if tenant_id:
        bucket["tenants"][tenant_id] += 1

    # Log estruturado periódico (cada 100 chamadas neste bucket)
    if bucket["requests"] % 100 == 0:
        avg = bucket["latency_sum_ms"] / max(bucket["requests"], 1)
        fb_pct = 100.0 * bucket["fallback"] / max(bucket["requests"], 1)
        logger.info(
            "[autocomplete:students] bucket=%s requests=%d avg=%.1fms fallback=%.1f%%",
            key, bucket["requests"], avg, fb_pct,
        )


# ============================================================================
# Snapshot agregado (consumido pelo endpoint de observabilidade)
# ============================================================================
def _p95_from_histogram(hist: list[int]) -> Optional[float]:
    """Calcula p95 invertendo CDF do histograma. None se vazio."""
    total = sum(hist)
    if total == 0:
        return None
    threshold = total * 0.95
    cumulative = 0
    for i, count in enumerate(hist):
        cumulative += count
        if cumulative >= threshold:
            # Borda direita do bucket (overflow → última borda * 2 como upper)
            if i < len(LATENCY_BUCKETS_MS):
                return float(LATENCY_BUCKETS_MS[i])
            return float(LATENCY_BUCKETS_MS[-1] * 2)
    return float(LATENCY_BUCKETS_MS[-1] * 2)


def get_observability_snapshot() -> dict:
    """Snapshot agregado da janela 15min em buckets de 1min."""
    _gc_old_buckets()

    # Agrega todos os buckets vivos
    total_req = 0
    total_fallback = 0
    total_empty = 0
    total_rate_limited = 0
    total_cache_hits = 0
    total_cache_misses = 0
    total_latency_sum = 0.0
    agg_hist = [0] * (len(LATENCY_BUCKETS_MS) + 1)
    agg_qlen: Counter = Counter()
    agg_q_hashes: Counter = Counter()
    agg_tenants: Counter = Counter()

    for bucket in _buckets.values():
        total_req += bucket["requests"]
        total_fallback += bucket["fallback"]
        total_empty += bucket["empty"]
        total_rate_limited += bucket["rate_limited"]
        total_cache_hits += bucket["cache_hits"]
        total_cache_misses += bucket["cache_misses"]
        total_latency_sum += bucket["latency_sum_ms"]
        for i, c in enumerate(bucket["latency_hist"]):
            agg_hist[i] += c
        agg_qlen.update(bucket["qlen"])
        agg_q_hashes.update(bucket["q_hashes"])
        agg_tenants.update(bucket["tenants"])

    avg_latency = (total_latency_sum / total_req) if total_req else 0.0
    p95 = _p95_from_histogram(agg_hist)
    cache_total = total_cache_hits + total_cache_misses
    cache_hit_pct = (100.0 * total_cache_hits / cache_total) if cache_total else 0.0
    fallback_pct = (100.0 * total_fallback / total_req) if total_req else 0.0
    empty_pct = (100.0 * total_empty / total_req) if total_req else 0.0

    return {
        "window": f"{OBSERVABILITY_WINDOW_MINUTES}m",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "instance-local",
        "replica_aware": False,
        "warning": (
            "Métricas voláteis (in-memory). Se o backend rodar em múltiplas réplicas, "
            "este snapshot reflete APENAS a réplica que respondeu esta chamada."
        ),
        # Performance
        "requests_total": total_req,
        "avg_latency_ms": round(avg_latency, 2),
        "p95_latency_ms": round(p95, 2) if p95 is not None else None,
        # Qualidade UX
        "empty_results_pct": round(empty_pct, 2),
        "fallback_contains_pct": round(fallback_pct, 2),
        # Infra / cache
        "cache_hit_pct": round(cache_hit_pct, 2),
        "cache_entries": len(_cache),
        "cache_memory_estimate_kb": _cache_memory_estimate_kb(),
        # Segurança
        "rate_limited_requests": total_rate_limited,
        # UX detalhada
        "query_length_distribution": dict(sorted(agg_qlen.items(), key=lambda kv: kv[0])),
        # Top — anonimizado
        "top_queries": [
            {"q_hash": h, "count": c}
            for h, c in agg_q_hashes.most_common(TOP_N_QUERIES)
        ],
        "top_tenants": [
            {"tenant_id": t, "count": c}
            for t, c in agg_tenants.most_common(TOP_N_TENANTS)
        ],
        # Configuração reportada (para o consumidor saber o setup)
        "config": {
            "cache_ttl_seconds": CACHE_TTL_SECONDS,
            "rate_limit_per_minute": RATE_LIMIT_MAX_CALLS,
            "latency_buckets_ms": LATENCY_BUCKETS_MS,
            "window_minutes": OBSERVABILITY_WINDOW_MINUTES,
        },
    }


# ============================================================================
# Helpers para testes/admin (reset)
# ============================================================================
def _reset_all_for_tests() -> None:
    """Limpa estado in-memory. SOMENTE para tests. Não usar em runtime."""
    global _cache_hits, _cache_misses, _rate_limited_total
    _cache.clear()
    _rate_buckets.clear()
    _buckets.clear()
    _cache_hits = 0
    _cache_misses = 0
    _rate_limited_total = 0
