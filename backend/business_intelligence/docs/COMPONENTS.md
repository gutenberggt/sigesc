# Componentes do Domínio BI — objetivo · responsabilidade · dependências · uso

| Componente | Objetivo | Responsabilidade | Depende de | Uso previsto |
|---|---|---|---|---|
| `models/enums` | vocabulário | valores canônicos | — | tipagem de todo o domínio |
| `contracts/definitions` | definição declarativa | espelhar `bi_indicator_defs` | enums | registrada no Registry |
| `contracts/execution` | intenção + contextos | transporte de request/contexto | enums | Engine → portas |
| `contracts/results` | resultado + trace | valor oficial rastreável | enums | saída do Engine |
| `contracts/observability` | métricas | eventos/contadores | — | ObservabilityProvider |
| `interfaces/ports` | portas SOLID | abstrações substituíveis | contracts | DI / testes / Engine |
| `registry/FormulaRegistry` | Registry First | versionar/servir definições | interfaces, contracts | fonte oficial de fórmulas |
| `calculators/BaseCalculator` | Strategy | cálculo plugável | interfaces | estratégias por fórmula (BI-2) |
| `calculators/CalculatorRegistry` | dispatcher | selecionar estratégia | interfaces | resolução no Engine |
| `aggregation/GrainLadder` | granularidade | ordem de agregação | enums | subir grão por composição |
| `aggregation/IdentityAggregator` | no-op | passthrough | interfaces | fundação/testes |
| `cache/NullCacheProvider` | cache off | no-op | interfaces | fundação; troca por Redis/Mongo |
| `materialization/NullMaterializer` | marts off | no-op | interfaces | fundação; troca em BI-3 |
| `traceability/NullTraceabilityProvider` | rastreio off | no-op | interfaces | fundação; persistência futura |
| `observability/NullObservabilityProvider` | métricas off | no-op | interfaces | fundação |
| `core/BIEngine` | orquestração | fluxo oficial de cálculo | apenas interfaces | ponto único de execução |
| `di/BIContainer` | wiring | compor Engine | todas as impls no-op | troca de implementações |
| `api/contracts` | contrato API | DTOs `/api/bi/*` | enums | referência p/ BI-4 (sem endpoints) |
| `tests/*` | scaffolding | mocks/builders/fixtures/smoke | tudo | validar arquitetura |

## Governança (respostas obrigatórias desta sprint)
- **Qual problema resolve?** ausência de uma base para o Motor de Indicadores (SSoT).
- **Qual benefício traz?** infraestrutura extensível, de baixo acoplamento, pronta para BI-2+.
- **Qual impacto possui?** nenhum em runtime (pacote isolado, não importado pelo app).
- **Como será testada?** smoke test da arquitetura (4 testes) + mocks para orquestração.
- **Como poderá ser revertida?** removendo o diretório `business_intelligence/` (nada depende dele).
- **Como prepara a próxima fase?** define contratos/interfaces/registry que BI-2 preencherá.
