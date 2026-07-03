# ENTREGA 21 — Business Intelligence (domínio arquitetural)

> **Onda 2 · Prioridade Máxima #1.** READ-ONLY (não implementar).
> Objetivo estratégico: transformar o SIGESC IA numa **Plataforma de Inteligência
> para Gestão Educacional**, com o BI como **domínio próprio** da arquitetura,
> ancorado no **Motor de Indicadores (SSoT)**.

## 1. Por que BI é um domínio (e não uma tela)
A auditoria mostrou que os dados existem, mas a lógica analítica está **duplicada e
espalhada** por endpoints/páginas. Elevar o BI a **domínio arquitetural** significa:
uma fonte única de cálculo (Motor de Indicadores), uma camada de dados analítica
(marts), uma API dedicada e telas que apenas consomem. Isso garante **consistência,
escala e menor custo de evolução**.

## 2. Arquitetura do domínio BI (camadas e responsabilidades)
```
┌──────────────────────────────────────────────────────────────────────────┐
│ D0 · OLTP (existente) — coleções transacionais (students, grades, ...)     │
│      Responsabilidade: registrar o que acontece. NÃO calcula indicador.    │
├──────────────────────────────────────────────────────────────────────────┤
│ D1 · MODELO DIMENSIONAL (novo) — dimensões + fatos derivados do OLTP       │
│      dim_escola · dim_turma · dim_aluno · dim_tempo · dim_componente ·     │
│      dim_serie · dim_demografia | fato_matricula · fato_frequencia ·       │
│      fato_nota · fato_ocorrencia · fato_cobertura                          │
├──────────────────────────────────────────────────────────────────────────┤
│ D2 · MOTOR DE INDICADORES (novo, SSoT) — definição declarativa + cálculo   │
│      bi_indicator_defs: { id, nome, fórmula, dimensões, granularidade,     │
│      fonte, refresh, cache, materializável }                               │
│      services/indicators/: biblioteca de cálculo canônica (única no sistema)│
├──────────────────────────────────────────────────────────────────────────┤
│ D3 · MARTS MATERIALIZADOS (novo) — resultados pré-agregados + cache        │
│      mart_rendimento · mart_frequencia · mart_matricula · mart_cobertura   │
│      atualizados por ETL incremental (worker dedicado, idempotente)        │
├──────────────────────────────────────────────────────────────────────────┤
│ D4 · API DE BI (nova) — /api/bi/indicators · /api/bi/query (dimensional)   │
│      RLS por tenant/escola; contrato estável; versionado                   │
├──────────────────────────────────────────────────────────────────────────┤
│ D5 · CONSUMIDORES — Dashboards (Operacional/Executivo/Especializados) ·    │
│      Relatórios · IA (insight sobre conhecimento estruturado)              │
└──────────────────────────────────────────────────────────────────────────┘
```

## 3. Novos módulos necessários
| Módulo | Papel |
|---|---|
| `services/indicators/registry.py` | catálogo declarativo dos indicadores (SSoT) |
| `services/indicators/calculators.py` | biblioteca canônica de cálculo (frequência, média, distorção, ...) |
| `services/bi_etl/` | ETL incremental OLTP→marts (worker + `with_critical_mutation`) |
| `routers/bi.py` | API dimensional `/api/bi/*` (RLS) |
| coleções | `bi_indicator_defs`, `bi_refresh_log`, `mart_*` |
| Metas Estratégicas | evolução de `monthly_goals` (baseline × meta × realizado) |

## 4. Módulos reaproveitados (não reescrever)
- `analytics.py` / `pme_anos_finais.py` — **migrar** a lógica para `services/indicators` (dedup).
- `bf_network_stats` — já materializa snapshots → **modelo de referência** de mart.
- `with_critical_mutation` — jobs de refresh idempotentes com lock/rollback.
- Snapshots (após unificação D8) — mecanismo base dos marts.
- `llm_client` (Claude) — camada de insight.
- `tenant_scope` — RLS na API de BI.

## 5. Impactos
- **Banco:** +coleções dimensionais/marts/defs; índices por dimensão; storage extra.
  **Pré-requisito:** replica set + backup antes do ETL em produção.
- **API:** novo namespace `/api/bi/*`; endpoints de agregação ad-hoc do `analytics.py`
  são **depreciados gradualmente** (passam a delegar ao Motor).
- **Dashboard Analítico (→ Operacional):** deixa de calcular; **consome marts** (mais rápido/consistente).
- **Dashboard Executivo:** nasce da convergência PME + SemedPanel + Ranking sobre o Motor.
- **Performance:** fim do recomputo por request; suporta rede com muitas escolas.

## 6. Cronograma (BI-0 → BI-4)
| Fase | Entrega | Pré-condição |
|---|---|---|
| **BI-0** | Consolidar dados: vínculo (D2), status (D6), snapshots (D8) | decisões 000.1 |
| **BI-1** | Motor de Indicadores + biblioteca canônica (dedup de métricas, D5) | BI-0 |
| **BI-2** | Modelo dimensional + ETL incremental + marts | BI-1 |
| **BI-3** | API de BI + Dashboard Operacional/Executivo sobre marts | BI-2 |
| **BI-4** | Metas Estratégicas + insight por IA + (futuro) MEC | BI-3 |

## 7. Riscos e mitigação
- **Consistência OLTP→mart:** refresh incremental idempotente + reconciliação.
- **Migração dupla temporária:** Motor lê OLTP como fallback até marts maduros.
- **Bloqueio duro:** **não iniciar BI-1** sem vínculo aluno↔turma unificado (D2) — fatos
  de matrícula exigem fonte única confiável.

## 8. Definição de "pronto" do domínio BI
1. 100% dos indicadores de rede vêm do Motor (zero cálculo em dashboards).
2. Dashboards Operacional/Executivo consomem exclusivamente `/api/bi/*`.
3. Marts com refresh incremental auditável e RLS por tenant.
4. IA consome conhecimento estruturado (indicadores), não OLTP.

> Ver também: [04 — Indicadores](04_INDICADORES.md), [03 — Dashboards](03_DASHBOARDS.md),
> [14 — IA](14_INTELIGENCIA_ARTIFICIAL.md), [000.1/07 — Plano de BI](000.1/07_PLANO_BI.md).
