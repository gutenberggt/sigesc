"""Builders de objetos de teste (padrão Builder) para o domínio BI."""
from __future__ import annotations

from ..contracts.definitions import (
    IndicatorDefinition, FormulaSpec, SourceSpec, ParameterSpec,
    KpiSpec, RefreshSpec, CacheSpec, MaterializationSpec,
)
from ..contracts.execution import IndicatorRequest
from ..models.enums import (
    Grain, IndicatorCategory, FormulaType, SourceKind, Unit,
    IndicatorStatus, RefreshStrategy, ParameterType,
)


def build_definition(
    *,
    code: str = "IND-TEST",
    version: int = 1,
    status: IndicatorStatus = IndicatorStatus.ACTIVE,
    formula_type: FormulaType = FormulaType.RATIO,
    materialized: bool = False,
    cached: bool = False,
) -> IndicatorDefinition:
    """Cria uma definição de teste (não representa indicador de produção)."""
    return IndicatorDefinition(
        code=code,
        version=version,
        name="Indicador de Teste",
        category=IndicatorCategory.FREQUENCIA,
        formula=FormulaSpec(type=formula_type, numerator="a", denominator="b"),
        source=SourceSpec(kind=SourceKind.OLTP, provider="fake", collections=("x",)),
        unit=Unit.PERCENT,
        status=status,
        supported_grains=(Grain.ALUNO, Grain.TURMA, Grain.ESCOLA, Grain.REDE),
        default_grain=Grain.ESCOLA,
        parameters=(ParameterSpec(key="limiar", type=ParameterType.FLOAT, default=0.5),),
        refresh=RefreshSpec(
            strategy=RefreshStrategy.MATERIALIZED if materialized else RefreshStrategy.REALTIME
        ),
        cache=CacheSpec(enabled=cached, ttl_seconds=60 if cached else 0),
        materialization=MaterializationSpec(
            enabled=materialized, mart="mart_test", incremental_key="date"
        ),
        kpi=KpiSpec(is_kpi=True, target=0.9),
    )


def build_request(
    *, code: str = "IND-TEST", grain: Grain = Grain.ESCOLA, scope_id: str = "esc-1",
) -> IndicatorRequest:
    return IndicatorRequest(
        code=code, grain=grain, scope_id=scope_id, academic_year=2026, period="mes",
    )
