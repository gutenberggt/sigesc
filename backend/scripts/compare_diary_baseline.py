"""
Snapshot e comparação automática de baseline do Diário (Fase 2).

[Fev/2026] Exigência §4 do contrato congelado.

Modos:
  --record   : grava o baseline atual em /app/baselines/diary_baseline.json
  --compare  : compara o estado atual contra o baseline e exibe regressões
  --runs N   : número de chamadas para média (default 10)

Uso típico:
    python -m scripts.compare_diary_baseline --record
    python -m scripts.compare_diary_baseline --compare
    python -m scripts.compare_diary_baseline --compare --threshold 1.5

Regressões emitidas (exit 1) se ultrapassarem `threshold` (default 1.5x):
- payload_size_bytes
- p95_latency_ms
- queries_count

Sem baseline → grava o primeiro automaticamente.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from utils.diary_loader import DiaryLoadStats, load_diary_items  # noqa: E402

# IDs da fixture v1 (cf. seed_dependency_diary_fixture.py)
FIXTURE_TENANT = "fix_mant_v1"
FIXTURE_CLASS = "fix_cl_v1"
FIXTURE_COURSE = "fix_co_mat_v1"
FIXTURE_YEAR = 2026

BASELINE_DIR = Path("/app/baselines")
BASELINE_FILE = BASELINE_DIR / "diary_baseline.json"


async def measure(db, runs: int) -> dict:
    """Executa `runs` cargas e retorna métricas agregadas."""
    durations = []
    queries_counts = []
    payload_size = 0
    items_total = 0
    regular_count = 0
    dependency_count = 0
    last_payload = None

    for _ in range(runs):
        with DiaryLoadStats() as stats:
            payload = await load_diary_items(
                db=db,
                class_id=FIXTURE_CLASS,
                course_id=FIXTURE_COURSE,
                academic_year=FIXTURE_YEAR,
                tenant_id=FIXTURE_TENANT,
                stats=stats,
            )
        durations.append(stats.duration_ms)
        queries_counts.append(stats.queries)
        last_payload = payload

    if last_payload:
        payload_size = len(json.dumps(last_payload, ensure_ascii=False).encode("utf-8"))
        items_total = last_payload["meta"]["total"]
        regular_count = last_payload["meta"]["regular_count"]
        dependency_count = last_payload["meta"]["dependency_count"]

    durations_sorted = sorted(durations)
    avg_ms = statistics.mean(durations) if durations else 0
    p95_idx = int(len(durations_sorted) * 0.95) - 1 if durations_sorted else 0
    p95_ms = durations_sorted[max(0, p95_idx)] if durations_sorted else 0
    p99_idx = int(len(durations_sorted) * 0.99) - 1 if durations_sorted else 0
    p99_ms = durations_sorted[max(0, p99_idx)] if durations_sorted else 0

    return {
        "runs": runs,
        "avg_latency_ms": round(avg_ms, 3),
        "p95_latency_ms": round(p95_ms, 3),
        "p99_latency_ms": round(p99_ms, 3),
        "max_latency_ms": round(max(durations), 3) if durations else 0,
        "queries_count": int(statistics.mode(queries_counts)) if queries_counts else 0,
        "payload_size_bytes": payload_size,
        "items_total": items_total,
        "regular_count": regular_count,
        "dependency_count": dependency_count,
        "fixture": {
            "tenant": FIXTURE_TENANT,
            "class_id": FIXTURE_CLASS,
            "course_id": FIXTURE_COURSE,
            "academic_year": FIXTURE_YEAR,
        },
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _save_baseline(metrics: dict) -> None:
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    BASELINE_FILE.write_text(json.dumps(metrics, indent=2, ensure_ascii=False))
    print(f"[baseline] gravado em {BASELINE_FILE}")


def _load_baseline() -> dict | None:
    if not BASELINE_FILE.exists():
        return None
    return json.loads(BASELINE_FILE.read_text())


def _compare(baseline: dict, current: dict, threshold: float) -> int:
    """Retorna 0 se OK, 1 se regressão detectada."""
    print("\n=== Comparação de baseline (Diário) ===")
    print(f"Threshold: {threshold}x")
    print(f"Baseline em: {baseline.get('captured_at')}")
    print(f"Atual em:    {current.get('captured_at')}\n")

    fields = [
        ("payload_size_bytes", "Tamanho payload (bytes)"),
        ("p95_latency_ms", "p95 latência (ms)"),
        ("p99_latency_ms", "p99 latência (ms)"),
        ("queries_count", "Queries Mongo"),
        ("avg_latency_ms", "Média latência (ms)"),
    ]

    regressions: list[str] = []
    for key, label in fields:
        b = baseline.get(key, 0) or 0
        c = current.get(key, 0) or 0
        if b == 0:
            ratio = 0
            symbol = "—"
        else:
            ratio = c / b
            symbol = "OK" if ratio < threshold else "🚨"
        print(f"  {symbol}  {label}: baseline={b}  atual={c}  ratio={ratio:.2f}x")
        if ratio >= threshold and key in {"payload_size_bytes", "p95_latency_ms", "queries_count"}:
            regressions.append(f"{label} cresceu {ratio:.2f}x")

    print()
    if regressions:
        print("🚨 REGRESSÕES DETECTADAS:")
        for r in regressions:
            print(f"   - {r}")
        return 1
    print("✅ Sem regressão crítica.")
    return 0


async def main_async(args) -> int:
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    if args.record:
        metrics = await measure(db, args.runs)
        _save_baseline(metrics)
        print(json.dumps(metrics, indent=2, ensure_ascii=False))
        return 0

    if args.compare:
        baseline = _load_baseline()
        current = await measure(db, args.runs)
        if not baseline:
            print("[baseline] não existia — gravando current como baseline inicial.")
            _save_baseline(current)
            print(json.dumps(current, indent=2, ensure_ascii=False))
            return 0
        return _compare(baseline, current, args.threshold)

    # Default: print metrics
    metrics = await measure(db, args.runs)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Baseline diário (Fase 2).")
    parser.add_argument("--record", action="store_true", help="Grava baseline atual.")
    parser.add_argument("--compare", action="store_true", help="Compara contra baseline.")
    parser.add_argument("--runs", type=int, default=10, help="Quantidade de chamadas (default 10).")
    parser.add_argument("--threshold", type=float, default=1.5, help="Tolerância (default 1.5x).")
    args = parser.parse_args()
    rc = asyncio.run(main_async(args))
    sys.exit(rc)
