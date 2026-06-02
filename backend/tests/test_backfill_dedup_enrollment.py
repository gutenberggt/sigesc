"""Regressão da lógica de backfill/dedup de matrículas (scripts/backfill_dedup_enrollment.py).

Testa as peças puras (sem efeitos no banco):
  - _sort_key: escolhe o registro MAIS ANTIGO.
  - NumberFactory (modo dry-run): gera números únicos sequenciais que não
    colidem com os já existentes.
"""
import asyncio
import importlib.util
import os

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "backfill_dedup_enrollment.py")
spec = importlib.util.spec_from_file_location("backfill_dedup_enrollment", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_sort_key_picks_oldest():
    older = {"created_at": "2024-01-01T00:00:00", "enrollment_date": "2024-02-01"}
    newer = {"created_at": "2026-05-01T00:00:00", "enrollment_date": "2026-05-01"}
    no_date = {}
    ordered = sorted([newer, no_date, older], key=mod._sort_key)
    assert ordered[0] is older
    assert ordered[-1] is no_date  # sem data vai por último


def test_number_factory_dry_run_is_unique_and_sequential():
    existing = {"202600005", "202600006"}
    factory = mod.NumberFactory(db=None, year=2026, apply=False, start_seq=10, existing=existing)
    nums = asyncio.get_event_loop().run_until_complete(_collect(factory, 5))
    # Únicos
    assert len(set(nums)) == 5
    # Não colidem com existentes
    assert not (set(nums) & existing)
    # Formato ano + 5 dígitos
    for n in nums:
        assert n.startswith("2026") and len(n) == 9
    # Sequenciais a partir de start_seq+1
    assert nums[0] == "202600011"


def test_number_factory_skips_existing_collisions():
    # start_seq=4 -> próximo seria 202600005 (existente) e 202600006 (existente),
    # então deve pular para 202600007.
    existing = {"202600005", "202600006"}
    factory = mod.NumberFactory(db=None, year=2026, apply=False, start_seq=4, existing=existing)
    first = asyncio.get_event_loop().run_until_complete(factory.next())
    assert first == "202600007"


async def _collect(factory, n):
    return [await factory.next() for _ in range(n)]
