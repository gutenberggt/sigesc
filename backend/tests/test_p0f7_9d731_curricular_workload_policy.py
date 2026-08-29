from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from utils.curricular_workload_policy import CurricularWorkloadPolicyError, resolve_curricular_workload  # noqa: E402


def resolve(component, level, series):
    return resolve_curricular_workload(component_name=component, class_level=level, class_series=series)


def test_geografia_fundamental_final_matrix():
    expected = {6: (120, 3), 7: (80, 2), 8: (80, 2), 9: (80, 2)}
    for year, pair in expected.items():
        out = resolve("Geografia", "fundamental_anos_finais", [f"{year}º ANO"])
        assert (out["canonical_annual_workload"], out["canonical_weekly_workload"]) == pair


def test_historia_fundamental_final_matrix():
    expected = {6: (80, 2), 7: (80, 2), 8: (120, 3), 9: (80, 2)}
    for year, pair in expected.items():
        out = resolve("História", "fundamental_anos_finais", [f"{year}º ANO"])
        assert (out["canonical_annual_workload"], out["canonical_weekly_workload"]) == pair


def test_ciencias_fundamental_final_matrix():
    expected = {6: (80, 2), 7: (120, 3), 8: (80, 2), 9: (120, 3)}
    for year, pair in expected.items():
        out = resolve("Ciências", "fundamental_anos_finais", [f"{year}º ANO"])
        assert (out["canonical_annual_workload"], out["canonical_weekly_workload"]) == pair


@pytest.mark.parametrize("component", ["Geografia", "História", "Ciências"])
def test_initial_levels_are_80h(component):
    for level, series in [("fundamental_anos_iniciais", ["3º ANO"]), ("eja", ["EJA 2ª ETAPA"])]:
        out = resolve(component, level, series)
        assert out["canonical_annual_workload"] == 80
        assert out["canonical_weekly_workload"] == 2


def test_eja_final_rules():
    geo = resolve("Geografia", "eja_final", ["EJA 3ª ETAPA", "EJA 4ª ETAPA"])
    hist = resolve("História", "eja_final", ["EJA 3ª ETAPA"])
    sci = resolve("Ciências", "eja_final", ["EJA 4ª ETAPA"])
    assert geo["multigrade"] is True
    assert geo["multigrade_rule"] == "MAX_ANNUAL_WORKLOAD"
    assert (geo["canonical_annual_workload"], geo["canonical_weekly_workload"]) == (80, 2)
    assert (hist["canonical_annual_workload"], hist["canonical_weekly_workload"]) == (80, 2)
    assert (sci["canonical_annual_workload"], sci["canonical_weekly_workload"]) == (120, 3)


def test_multigrade_uses_greatest_workload():
    cases = [
        ("Geografia", ["6º ANO", "7º ANO"]),
        ("História", ["7º ANO", "8º ANO"]),
        ("Ciências", ["6º ANO", "7º ANO"]),
    ]
    for component, series in cases:
        out = resolve(component, "fundamental_anos_finais", series)
        assert out["multigrade"] is True
        assert out["canonical_annual_workload"] == 120
        assert out["canonical_weekly_workload"] == 3


def test_variable_rule_fails_closed_without_series():
    with pytest.raises(CurricularWorkloadPolicyError) as exc:
        resolve("Geografia", "fundamental_anos_finais", [])
    assert exc.value.code == "CURRICULAR_WORKLOAD_SERIES_REQUIRED"


def test_other_components_are_outside_policy():
    assert resolve("Matemática", "fundamental_anos_finais", ["6º ANO"])["applies"] is False
