# 000.1 · 7 — Plano de Business Intelligence (proposta arquitetural)

> Proposta de arquitetura futura. **Sem implementação** — somente planejamento.

## 1. Arquitetura sugerida (camadas)
```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. OLTP (atual)  — coleções transacionais (students, grades, ...)     │
├─────────────────────────────────────────────────────────────────────┤
│ 2. INGESTÃO/ETL  — job de consolidação (worker dedicado) que lê OLTP  │
│    e alimenta os marts (incremental por tenant/escola/período)        │
├─────────────────────────────────────────────────────────────────────┤
│ 3. MODELO DIMENSIONAL (novo)                                          │
│    Dimensões: dim_escola · dim_turma · dim_aluno · dim_tempo ·        │
│               dim_componente · dim_serie · dim_demografia             │
│    Fatos: fato_matricula · fato_frequencia · fato_nota ·              │
│           fato_ocorrencia · fato_cobertura                            │
├─────────────────────────────────────────────────────────────────────┤
│ 4. MOTOR DE INDICADORES (novo)  — definição declarativa               │
│    { id, nome, fórmula, dimensões, granularidade, fonte, refresh }    │
│    → biblioteca de cálculo canônica (services/indicators)             │
├─────────────────────────────────────────────────────────────────────┤
│ 5. MARTS MATERIALIZADOS (novo)  — coleções pré-agregadas + cache      │
├─────────────────────────────────────────────────────────────────────┤
│ 6. API DE BI (nova)  — /api/bi/indicators, /api/bi/query (dimensional)│
├─────────────────────────────────────────────────────────────────────┤
│ 7. DASHBOARDS  — Operacional · Executivo · Especializados (consomem 6)│
│    + IA (Claude) para narrativa/insight sobre os marts                │
└─────────────────────────────────────────────────────────────────────┘
```

## 2. Novos módulos necessários
- `services/indicators/` — registry declarativo + biblioteca de cálculo canônica.
- `services/bi_etl/` — job de consolidação incremental (worker dedicado).
- `routers/bi.py` — API dimensional (`/api/bi/*`) com RLS por tenant.
- Coleções de marts: `mart_frequencia`, `mart_rendimento`, `mart_matricula`,
  `mart_cobertura` (+ `bi_indicator_defs`, `bi_refresh_log`).
- `monthly_goals` evoluído → módulo de **Metas Estratégicas**.

## 3. Módulos reaproveitados
- `analytics.py` / `pme_anos_finais.py` (lógica de cálculo → migrar p/ `services/indicators`).
- `bf_network_stats` (já materializa snapshots — modelo de mart).
- `with_critical_mutation` (jobs de refresh idempotentes).
- Snapshots existentes (unificados em D8) como base dos marts.
- IA (`llm_client`) para camada de insight.

## 4. Cronograma recomendado (alinhado ao Roadmap)
| Fase | Entrega | Prazo |
|---|---|---|
| BI-0 | Pré-requisitos: unificar vínculo (D2) + status (D6) + snapshots (D8) | Médio prazo |
| BI-1 | Motor de Indicadores + biblioteca de cálculo canônica (dedup de métricas) | Médio/Longo |
| BI-2 | Modelo dimensional + ETL incremental + marts | Longo |
| BI-3 | API de BI + Dashboard Operacional/Executivo sobre marts | Longo |
| BI-4 | Metas Estratégicas + insight por IA + (futuro) integração MEC | Longo |

## 5. Impactos
- **Banco:** +coleções de marts e defs; índices dimensionais; storage adicional (aceitável).
  Necessário **replica set** + backup antes do ETL rodar em produção.
- **API:** novo namespace `/api/bi/*` (RLS por tenant); depreciar gradualmente endpoints
  de agregação ad-hoc do `analytics.py` (migram para o motor).
- **Dashboard Analítico (Operacional):** deixa de calcular; passa a **consumir marts**
  (mais rápido, consistente).
- **Dashboard Executivo:** nasce da convergência PME+SemedPanel+Ranking sobre o motor.
- **Performance:** elimina recomputo por request; habilita rede com muitas escolas.

## 6. Riscos e mitigação
- **Consistência OLTP→mart:** refresh incremental idempotente + reconciliação (padrão existente).
- **Duplicação temporária:** durante migração, motor lê OLTP como fallback até marts maduros.
- **Pré-condição dura:** **não iniciar BI-1** sem resolver D2 (vínculo) — fatos de matrícula
  dependem de fonte única confiável.

> **Princípio:** BI se constrói **de baixo para cima** (dados consistentes → motor →
> marts → dashboards), nunca criando telas antes da fundação de indicadores.
