"""Smoke test da arquitetura do domínio BI (Sprint BI-1A).

Valida a FUNDAÇÃO — não valida indicadores (não existem nesta fase):
- pacote importa limpo;
- Registry versiona/ativa/desativa;
- Container monta o Engine (estado no-op);
- Engine orquestra corretamente quando providers/calculators são injetados (mocks);
- Contratos de definição/execução/resultado instanciam.

Executar: pytest backend/business_intelligence/tests/test_scaffolding_smoke.py
"""
import asyncio

from ..registry.formula_registry import FormulaRegistry
from ..registry.errors import (
    DuplicateDefinitionError, NoActiveVersionError, IndicatorNotFoundError,
)
from ..calculators.base import NoCalculatorError
from ..models.enums import IndicatorStatus, Grain
from .builders import build_definition, build_request
from .fixtures import make_wired_engine, make_bare_container


def test_registry_versioning_and_activation():
    reg = FormulaRegistry()
    v1 = build_definition(version=1, status=IndicatorStatus.DEPRECATED)
    v2 = build_definition(version=2, status=IndicatorStatus.ACTIVE)
    reg.register(v1)
    reg.register(v2)
    assert reg.versions("IND-TEST") == [1, 2]
    assert reg.get("IND-TEST").version == 2          # ACTIVE de maior versão
    assert reg.get("IND-TEST", 1).status == IndicatorStatus.DEPRECATED
    assert reg.exists("IND-TEST") and not reg.exists("IND-XYZ")


def test_registry_rejects_duplicate_and_missing_active():
    reg = FormulaRegistry()
    reg.register(build_definition(version=1, status=IndicatorStatus.ACTIVE))
    try:
        reg.register(build_definition(version=1))
        assert False, "esperava DuplicateDefinitionError"
    except DuplicateDefinitionError:
        pass
    reg2 = FormulaRegistry()
    reg2.register(build_definition(version=1, status=IndicatorStatus.DRAFT))
    try:
        reg2.get("IND-TEST")
        assert False, "esperava NoActiveVersionError"
    except NoActiveVersionError:
        pass
    try:
        reg2.get("IND-NOPE")
        assert False, "esperava IndicatorNotFoundError"
    except IndicatorNotFoundError:
        pass


def test_foundation_engine_is_inert_without_data_provider():
    """Estado BI-1A: Engine monta, mas não serve indicadores (sem calculators/data)."""
    container = make_bare_container()
    engine = container.build_engine()
    container.registry.register(build_definition(status=IndicatorStatus.ACTIVE))
    assert engine.is_ready_for("IND-TEST") is False
    try:
        asyncio.get_event_loop().run_until_complete(engine.compute(build_request()))
        assert False, "esperava NoCalculatorError na fundação"
    except NoCalculatorError:
        pass


def test_engine_orchestrates_with_mocks():
    """Com mocks injetados, o fluxo completo produz um resultado rastreável."""
    engine = make_wired_engine()
    # registrar a definição no registry do engine (via container interno do fixture)
    # o fixture cria container próprio; registramos aqui uma definição equivalente:
    engine._registry.register(build_definition(status=IndicatorStatus.ACTIVE))  # noqa: SLF001 (teste)
    assert engine.is_ready_for("IND-TEST") is True
    result = asyncio.get_event_loop().run_until_complete(engine.compute(build_request()))
    assert result.code == "IND-TEST"
    assert abs(result.value - 0.87) < 1e-9
    assert result.grain == Grain.ESCOLA
    assert result.trace is not None and result.trace.indicator_code == "IND-TEST"


if __name__ == "__main__":
    test_registry_versioning_and_activation()
    test_registry_rejects_duplicate_and_missing_active()
    test_foundation_engine_is_inert_without_data_provider()
    test_engine_orchestrates_with_mocks()
    print("BI-1A scaffolding smoke: OK")
