"""SIGESC IA — Business Intelligence (Core Domain).

Fundação do Motor de Indicadores (Single Source of Truth).

IMPORTANTE (Sprint BI-1A): este pacote é APENAS infraestrutura/arquitetura.
- Não implementa indicadores.
- Não é registrado no `server.py` (zero impacto no comportamento em runtime).
- Não acessa MongoDB diretamente (depende apenas de Data Providers via interfaces).

Camadas (baixo acoplamento, alta coesão):
    models          -> enums e vocabulário do domínio
    contracts       -> DTOs imutáveis (definição, execução, resultado, observabilidade)
    interfaces      -> portas (ABCs SOLID) para substituição de implementações (DI)
    registry        -> Formula Registry (registro oficial de fórmulas/definições)
    calculators     -> Strategy Pattern para cálculo (apenas base, sem indicadores)
    aggregation     -> agregação por granularidade
    cache           -> provedores de cache (no-op default)
    materialization -> materialização em marts
    traceability    -> rastreabilidade de cada cálculo
    observability   -> métricas do Motor
    core            -> orquestração (BIEngine) dependente apenas de interfaces
    di              -> composição/wiring (Dependency Injection)
    api             -> contratos da futura API BI (NÃO cria endpoints)
    tests           -> mocks/fixtures/builders/helpers (sem testes de indicadores)
"""

__version__ = "0.1.0-BI-1A"
__engine_version__ = "0.1.0"

__all__ = ["__version__", "__engine_version__"]
