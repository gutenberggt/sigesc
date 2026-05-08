"""
Tests para o módulo genérico de observabilidade (utils/observability.py).

Garante que o canal isolado funciona corretamente para reuso pelo Diário (Fase 2).
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.observability import MetricChannel


@pytest.fixture
def ch():
    c = MetricChannel("test", latency_buckets_ms=[5, 10, 50, 100])
    yield c
    c.reset_for_tests()


class TestMetricChannel:
    def test_snapshot_vazio(self, ch):
        snap = ch.snapshot()
        assert snap["channel"] == "test"
        assert snap["requests_total"] == 0
        assert snap["p95_latency_ms"] is None
        assert snap["p99_latency_ms"] is None
        assert snap["mode"] == "instance-local"
        assert snap["replica_aware"] is False

    def test_record_basico(self, ch):
        ch.record(duration_ms=8.0, tenant_id="T1")
        ch.record(duration_ms=15.0, tenant_id="T1")
        ch.record(duration_ms=22.0, tenant_id="T2")
        snap = ch.snapshot()
        assert snap["requests_total"] == 3
        assert snap["avg_latency_ms"] == pytest.approx(15.0, rel=1e-2)

    def test_top_tenants(self, ch):
        for _ in range(5):
            ch.record(duration_ms=1, tenant_id="T1")
        for _ in range(2):
            ch.record(duration_ms=1, tenant_id="T2")
        snap = ch.snapshot()
        top = snap["top_tenants"]
        assert top[0]["tenant_id"] == "T1" and top[0]["count"] == 5
        assert top[1]["tenant_id"] == "T2" and top[1]["count"] == 2

    def test_p95_via_histogram(self, ch):
        for _ in range(95):
            ch.record(duration_ms=5)
        for _ in range(5):
            ch.record(duration_ms=100)
        snap = ch.snapshot()
        assert snap["p95_latency_ms"] in (5.0, 10.0, 100.0)
        assert snap["p99_latency_ms"] >= snap["p95_latency_ms"]

    def test_labels_agrupam(self, ch):
        ch.record(duration_ms=1, labels={"cache_hit": True, "class_id": "C1"})
        ch.record(duration_ms=1, labels={"cache_hit": True, "class_id": "C1"})
        ch.record(duration_ms=1, labels={"cache_hit": False, "class_id": "C2"})
        snap = ch.snapshot()
        cache = {x["value"]: x["count"] for x in snap["labels"]["cache_hit"]}
        assert cache["true"] == 2
        assert cache["false"] == 1

    def test_bucket_counters_acumulam(self, ch):
        ch.record(duration_ms=1, bucket_counters={"students_regular": 25, "students_dep": 2})
        ch.record(duration_ms=1, bucket_counters={"students_regular": 18, "students_dep": 1})
        snap = ch.snapshot()
        assert snap["counters"]["students_regular"] == 43
        assert snap["counters"]["students_dep"] == 3

    def test_errors_e_rate_limited(self, ch):
        ch.record(duration_ms=1, is_error=True)
        ch.record(duration_ms=1, is_error=True)
        ch.record(duration_ms=1, is_rate_limited=True)
        snap = ch.snapshot()
        assert snap["errors"] == 2
        assert snap["rate_limited"] == 1

    def test_canais_isolados(self):
        a = MetricChannel("A", latency_buckets_ms=[5, 50])
        b = MetricChannel("B", latency_buckets_ms=[5, 50])
        a.record(duration_ms=10)
        a.record(duration_ms=10)
        snap_a = a.snapshot()
        snap_b = b.snapshot()
        assert snap_a["requests_total"] == 2
        assert snap_b["requests_total"] == 0

    def test_hash_label_estavel(self):
        h1 = MetricChannel.hash_label("ana silva")
        h2 = MetricChannel.hash_label("ana silva")
        h3 = MetricChannel.hash_label("ana silvaa")
        assert h1 == h2
        assert h1 != h3
        assert len(h1) == 8
