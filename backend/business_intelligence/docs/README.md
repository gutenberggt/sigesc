# Domínio Business Intelligence — SIGESC IA (Sprint BI-1A)

Fundação do **Motor de Indicadores** (Single Source of Truth). Este pacote é
**infraestrutura pura**: não implementa indicadores, não cria endpoints, não é
importado pelo `server.py` e não acessa MongoDB. Zero impacto no comportamento.

## Estrutura
```
business_intelligence/
├── models/          # enums do domínio (Grain, IndicatorCategory, FormulaType, ...)
├── contracts/       # DTOs: definitions | execution | results | observability
├── interfaces/      # portas SOLID (IRegistry, ICalculator, IAggregator, ICacheProvider,
│                    #   IMaterializer, ITraceabilityProvider, IDataProvider, IObservabilityProvider)
├── registry/        # FormulaRegistry (Registry First) + erros
├── calculators/     # BaseCalculator (Strategy) + CalculatorRegistry (dispatcher)
├── aggregation/     # agregação por granularidade (GrainLadder + IdentityAggregator)
├── cache/           # NullCacheProvider (no-op)
├── materialization/ # NullMaterializer (no-op)
├── traceability/    # NullTraceabilityProvider (no-op)
├── observability/   # NullObservabilityProvider (no-op)
├── core/            # BIEngine (orquestração; depende só de interfaces)
├── di/              # BIContainer + build_default_engine (wiring)
├── api/             # contratos da futura API BI (DTOs; SEM endpoints)
├── tests/           # mocks, builders, fixtures, helpers + smoke test da arquitetura
└── docs/            # esta documentação
```

## Como será usado (próximas sprints)
```python
from business_intelligence.di import BIContainer
container = BIContainer()
container.registry = MongoFormulaRegistry(db)        # BI-2
container.data_provider = SigescDataProvider(db)     # BI-2 (única porta p/ Mongo)
container.calculators.register(RatioCalculator())    # BI-2 (reusa attendance_utils)
container.materializer = MongoMaterializer(db)       # BI-3
engine = container.build_engine()
result = await engine.compute(IndicatorRequest(code="IND-FREQ", grain=Grain.ESCOLA, ...))
```

## Princípios aplicados
- **SSoT** — só o Motor produz indicadores.
- **Registry First** — toda fórmula nasce no `FormulaRegistry`.
- **Open/Closed** — novos indicadores via `register`, sem mudar o Engine.
- **Strategy** — cálculo plugável por `ICalculator`.
- **Dependency Inversion** — Engine depende de interfaces; nunca de MongoDB.
- **Versionamento** — `code@version`, com ACTIVE/DEPRECATED (compat. retroativa).
- **Extensibilidade** — `IDataProvider` abstrai origem (SIGESC/MEC/INEP/FNDE/IBGE/CSV/Excel/manual).
