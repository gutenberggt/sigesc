"""
Observabilidade reutilizável — sliding window 15min em buckets de 1min.

[Fev/2026] Extraído do pipeline de autocomplete (`students_search.py`) para
permitir reuso em outros endpoints sensíveis (Diário Fase 2, Boletim, Frequência).

Cada `MetricChannel` é um silo independente — métricas do autocomplete não
contaminam métricas do diário.

Uso típico:

    from utils.observability import MetricChannel

    diary_metrics = MetricChannel("diary", latency_buckets_ms=[5, 10, 25, 50, 100, 250, 500])

    # Em cada handler:
    t0 = time.monotonic()
    ...  # query
    diary_metrics.record(
        duration_ms=(time.monotonic() - t0) * 1000,
        tenant_id=current_user["mantenedora_id"],
        labels={"class_id": class_id, "course_id": course_id, "cache_hit": False},
        bucket_counters={"students_regular": len(reg), "students_dep": len(deps)},
    )

    # No endpoint admin:
    snap = diary_metrics.snapshot()

Modo: in-memory, instance-local (replica_aware=False). Roadmap Fase 2 = Redis/Mongo capped.
"""
from __future__ import annotations

import hashlib
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

OBSERVABILITY_WINDOW_MINUTES = 15


def _current_bucket_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


class MetricChannel:
    """Silo isolado de métricas para um único endpoint/feature."""

    def __init__(
        self,
        name: str,
        latency_buckets_ms: Optional[list[int]] = None,
        window_minutes: int = OBSERVABILITY_WINDOW_MINUTES,
        track_label_top_n: int = 10,
    ):
        self.name = name
        self.latency_buckets_ms = latency_buckets_ms or [1, 2, 5, 10, 25, 50, 100, 250, 500, 1000]
        self.window_minutes = window_minutes
        self.track_label_top_n = track_label_top_n
        self._buckets: dict[str, dict] = {}

    def _new_bucket(self) -> dict:
        return {
            "requests": 0,
            "latency_sum_ms": 0.0,
            "latency_hist": [0] * (len(self.latency_buckets_ms) + 1),
            "tenants": Counter(),
            "labels": {},  # nome_label → Counter()
            "counters": Counter(),  # contadores agregados (ex.: students_regular_total)
            "errors": 0,
            "rate_limited": 0,
        }

    def _gc(self) -> None:
        if not self._buckets:
            return
        cutoff = datetime.now(timezone.utc).timestamp() - (self.window_minutes * 60 + 30)
        stale = []
        for k in self._buckets:
            try:
                ts = datetime.strptime(k, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc).timestamp()
                if ts < cutoff:
                    stale.append(k)
            except Exception:
                stale.append(k)
        for k in stale:
            self._buckets.pop(k, None)

    def _latency_idx(self, ms: float) -> int:
        for i, edge in enumerate(self.latency_buckets_ms):
            if ms <= edge:
                return i
        return len(self.latency_buckets_ms)

    @staticmethod
    def hash_label(value: str) -> str:
        """Para labels potencialmente sensíveis (queries livres etc.)."""
        return hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]

    # ------------------------------------------------------------------
    def record(
        self,
        *,
        duration_ms: float,
        tenant_id: Optional[str] = None,
        labels: Optional[dict] = None,
        bucket_counters: Optional[dict] = None,
        is_error: bool = False,
        is_rate_limited: bool = False,
    ) -> None:
        self._gc()
        key = _current_bucket_key()
        b = self._buckets.setdefault(key, self._new_bucket())

        b["requests"] += 1
        b["latency_sum_ms"] += duration_ms
        b["latency_hist"][self._latency_idx(duration_ms)] += 1
        if tenant_id:
            b["tenants"][tenant_id] += 1
        if is_error:
            b["errors"] += 1
        if is_rate_limited:
            b["rate_limited"] += 1
        if labels:
            for lname, lval in labels.items():
                if lval is None:
                    continue
                if isinstance(lval, bool):
                    lval = "true" if lval else "false"
                ctr = b["labels"].setdefault(lname, Counter())
                ctr[str(lval)] += 1
        if bucket_counters:
            for k, v in bucket_counters.items():
                b["counters"][k] += v

    # ------------------------------------------------------------------
    def _p_from_hist(self, hist: list[int], pct: float) -> Optional[float]:
        total = sum(hist)
        if not total:
            return None
        threshold = total * pct
        cum = 0
        for i, c in enumerate(hist):
            cum += c
            if cum >= threshold:
                if i < len(self.latency_buckets_ms):
                    return float(self.latency_buckets_ms[i])
                return float(self.latency_buckets_ms[-1] * 2)
        return float(self.latency_buckets_ms[-1] * 2)

    def snapshot(self) -> dict:
        self._gc()
        if not self._buckets:
            return {
                "channel": self.name,
                "window": f"{self.window_minutes}m",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "mode": "instance-local",
                "replica_aware": False,
                "requests_total": 0,
                "avg_latency_ms": 0.0,
                "p95_latency_ms": None,
                "p99_latency_ms": None,
                "errors": 0,
                "rate_limited": 0,
                "top_tenants": [],
                "labels": {},
                "counters": {},
            }
        agg_hist = [0] * (len(self.latency_buckets_ms) + 1)
        total_req = 0
        total_lat = 0.0
        total_err = 0
        total_rl = 0
        agg_tenants: Counter = Counter()
        agg_labels: dict[str, Counter] = {}
        agg_counters: Counter = Counter()
        for b in self._buckets.values():
            total_req += b["requests"]
            total_lat += b["latency_sum_ms"]
            total_err += b["errors"]
            total_rl += b["rate_limited"]
            for i, c in enumerate(b["latency_hist"]):
                agg_hist[i] += c
            agg_tenants.update(b["tenants"])
            for ln, ctr in b["labels"].items():
                agg_labels.setdefault(ln, Counter()).update(ctr)
            agg_counters.update(b["counters"])
        avg = total_lat / total_req if total_req else 0.0
        return {
            "channel": self.name,
            "window": f"{self.window_minutes}m",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "instance-local",
            "replica_aware": False,
            "requests_total": total_req,
            "avg_latency_ms": round(avg, 2),
            "p95_latency_ms": self._p_from_hist(agg_hist, 0.95),
            "p99_latency_ms": self._p_from_hist(agg_hist, 0.99),
            "errors": total_err,
            "rate_limited": total_rl,
            "top_tenants": [
                {"tenant_id": t, "count": c}
                for t, c in agg_tenants.most_common(self.track_label_top_n)
            ],
            "labels": {
                ln: [{"value": v, "count": c} for v, c in ctr.most_common(self.track_label_top_n)]
                for ln, ctr in agg_labels.items()
            },
            "counters": dict(agg_counters),
        }

    def reset_for_tests(self) -> None:
        self._buckets.clear()


# ============================================================================
# Canal pré-registrado para o Diário (Fase 2 — instrumentação pronta)
# ============================================================================
diary_metrics = MetricChannel(
    "diary",
    latency_buckets_ms=[5, 10, 25, 50, 100, 250, 500, 1000, 2500],
)


def record_diary_load(
    *,
    duration_ms: float,
    tenant_id: Optional[str],
    regular_count: int,
    dependency_count: int,
    cache_hit: bool = False,
    is_error: bool = False,
    is_rate_limited: bool = False,
    class_id: Optional[str] = None,
    course_id: Optional[str] = None,
    dependency_ratio_pct: Optional[float] = None,
    excess_dep: bool = False,
) -> None:
    """Helper canônico para instrumentar carregamento do Diário (Fase 2).

    Padroniza a estrutura registrada para que `GET /api/admin/observability/diary`
    sempre tenha `counters.regular_total`, `counters.dependency_total`, labels
    `cache_hit`/`class_id`/`course_id` consistentes.

    `dependency_ratio_pct` e `excess_dep` são gravados em buckets dedicados para
    detectar uso anormal/explosão de vínculos (cf. contrato §18 + exigência §8/§9).

    NÃO chame `diary_metrics.record` diretamente — sempre passe por aqui.
    Ver `/app/docs/DIARY_API_CONTRACT.md` (item 9).
    """
    bucket_counters = {
        "regular_total": regular_count,
        "dependency_total": dependency_count,
        "items_total": regular_count + dependency_count,
    }
    if dependency_ratio_pct is not None:
        # acumula soma e amostras para média móvel sem PII
        bucket_counters["dependency_ratio_sum_x100"] = int(round(dependency_ratio_pct * 100))
        bucket_counters["dependency_ratio_samples"] = 1
    if excess_dep:
        bucket_counters["excess_dep_loads"] = 1
    diary_metrics.record(
        duration_ms=duration_ms,
        tenant_id=tenant_id,
        labels={
            "cache_hit": cache_hit,
            "class_id": class_id,
            "course_id": course_id,
            "excess_dep": excess_dep,
        },
        bucket_counters=bucket_counters,
        is_error=is_error,
        is_rate_limited=is_rate_limited,
    )
