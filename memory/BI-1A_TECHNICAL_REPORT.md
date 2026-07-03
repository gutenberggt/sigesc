# BI-1A — Relatório Técnico (Fundação do Domínio Business Intelligence)

> Sprint de **infraestrutura**. Comportamento funcional do sistema **inalterado**
> (usuário final não percebe diferença). Sem migrações, sem mudança de regras,
> sem alterar dashboards/indicadores/coleções. Concluída em Jun/2026.

## 1. O que foi criado, por quê e como será usado
Criado o domínio **`/app/backend/business_intelligence/`** (Core Domain), a fundação
arquitetural do Motor de Indicadores (SSoT).

| Bloco | O que foi criado | Por quê | Uso nas próximas fases |
|---|---|---|---|
| `models/enums` | vocabulário do domínio (Grain, Category, FormulaType, RefreshStrategy, ...) | linguagem única | tipagem de definições/execução |
| `contracts/` | DTOs de definição, execução, resultado, observabilidade | contratos estáveis (imutáveis) | trânsito entre Engine e portas |
| `interfaces/ports` | 8 portas SOLID (Registry, Calculator, Aggregator, Cache, Materializer, Traceability, DataProvider, Observability) | inversão de dependência | implementações concretas em BI-2/BI-3 |
| `registry/FormulaRegistry` | registro versionado de definições (Registry First) | toda fórmula nasce aqui | popular com indicadores em BI-2 |
| `calculators/` | Strategy base + dispatcher | cálculo plugável | estratégias reais (reusando `attendance_utils`/`grade_calculator`) em BI-2 |
| `aggregation/` | escada de grãos + agregador identidade | agregação por composição | agregadores reais em BI-2 |
| `cache` / `materialization` / `traceability` / `observability` | providers **no-op** | montar Engine sem efeito colateral | trocar por Redis/Mongo/persistência em BI-3 |
| `core/BIEngine` | orquestração (fluxo oficial) | ponto único de execução | servir `/api/bi/*` em BI-4 |
| `di/BIContainer` | wiring por injeção | substituir implementações | compor Engine de produção |
| `api/contracts` | DTOs de `/api/bi/*` | contrato documental | implementar router em BI-4 |
| `tests/` | mocks, builders, fixtures, smoke (4 testes) | validar arquitetura | base para testes de indicadores em BI-2 |
| `docs/` | README + COMPONENTS | rastreabilidade técnica | referência viva |

**Validação:** `pytest ... test_scaffolding_smoke.py` → **4 passed**. Import do pacote
OK. `grep business_intelligence server.py routers/ services/` → **0 referências**
(isolamento total). Backend health **200**, sem restart.

## 2. Diagrama arquitetural atualizado (onde o BI se integra)
```
┌───────────────────────────── SIGESC IA (atual, inalterado) ─────────────────────────────┐
│  React PWA  ──/api──►  FastAPI (89 routers, 574 endpoints)  ──►  MongoDB (OLTP, 102 coll) │
└───────────────────────────────────────────────────────────────────────────────────────────┘
                                                    ▲
                                                    │ (BI-2+: SigescDataProvider — ÚNICA porta p/ Mongo)
        ┌─────────────────── NOVO Core Domain: business_intelligence/ (isolado hoje) ─────────┐
        │  Registry ─ Contracts ─ Interfaces ─ Calculators ─ Aggregation ─ Cache ─             │
        │  Materialization ─ Traceability ─ Observability ─ [ BIEngine ] ─ DI ─ API(contratos)  │
        └───────────────────────────────────────────┬───────────────────────────────────────────┘
                                                     │ (BI-4: router /api/bi/* registrado no server.py)
                                     Dashboards · Relatórios · Alertas · IA (consumidores)
```
Hoje: o bloco novo existe, é testável, mas **não está conectado** ao app (nenhum
`include_router`, nenhum import em `server.py`). A conexão ocorre em fases futuras.

## 3. Avaliação de impacto
| Dimensão | Impacto | Observação |
|---|---|---|
| **Performance** | **Nulo** | código não é carregado pelo processo do backend (não importado) |
| **Memória** | **Nulo em runtime** | +~30 KB de arquivos em disco; nada residente |
| **Segurança** | **Nulo/positivo** | sem novos endpoints; DIP impede acoplamento a Mongo; RLS previsto no contrato |
| **Manutenção** | **Positivo** | baixo acoplamento, alta coesão, contratos claros, testes de fundação |
| **Escalabilidade** | **Positivo** | Registry declarativo suporta centenas de indicadores sem mudança estrutural |

## 4. Critérios de aceite (todos atendidos)
✅ domínio BI estruturado · ✅ Registry preparado · ✅ contratos definidos ·
✅ interfaces definidas · ✅ modelos definidos · ✅ rastreabilidade projetada ·
✅ observabilidade preparada · ✅ arquitetura pronta p/ o Motor ·
✅ **comportamento do sistema rigorosamente idêntico**.

## 5. Requisitos arquiteturais atendidos
SSoT ✔ · Registry First ✔ · Open/Closed ✔ · Strategy Pattern ✔ ·
Dependency Inversion (sem dependência de MongoDB) ✔ · Versionamento ✔ ·
Extensibilidade (SIGESC/MEC/INEP/FNDE/IBGE/CSV/Excel/manual via `IDataProvider`) ✔.

> Próxima sprint: **BI-1B — Consolidação dos Dados** (ver `BI-1B_PLAN.md`). Só inicia
> após aprovação desta BI-1A, pois envolverá alterações estruturais e migrações.
