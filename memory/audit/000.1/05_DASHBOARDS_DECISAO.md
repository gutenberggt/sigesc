# 000.1 · 5 — Dashboards: Decisão Arquitetural (PRIORIDADE MÁXIMA)

> Análise objetiva + arquitetura definitiva recomendada. READ-ONLY.

## 1. Quantos dashboards realmente existem?
**14 páginas do tipo dashboard** (evidência: linhas + uso de recharts):

| # | Página | Linhas | Gráficos (recharts) | Natureza |
|---|---|---|---|---|
| 1 | `AnalyticsDashboard.jsx` | 2.404 | 24 | **Analítico geral** (o mais rico) |
| 2 | `Dashboard.js` (hub de gestão) | 856 | 10 | **Hub/menu + KPIs** |
| 3 | `PmpiEngine.jsx` | 629 | 0 | Motor PMPI (cards/tabelas) |
| 4 | `BuscaAtivaDashboard.jsx` | 622 | 0 | Infrequência (tabelas) |
| 5 | `VaccineDashboard.js` | 654 | 0 | Saúde (tabelas) |
| 6 | `BolsaFamilia.js` | 634 | 0 | PBF (tabelas) |
| 7 | `DiaryDashboard.js` | 528 | 13 | Acompanhamento de diário |
| 8 | `ProfessorDashboard.js` | 416 | 0 | Portal do professor |
| 9 | `AssocialDashboard.js` | 402 | 0 | Assistência social |
| 10 | `PmeAnosFinais.jsx` | 303 | 14 | **Painel PME** (rendimento/distorção) |
| 11 | `AlunoDashboard.jsx` | 296 | 0 | Portal do aluno |
| 12 | `PmeExternalIndicators.jsx` | 248 | 4 | Indicadores externos PME |
| 13 | `SemedPanel.jsx` | 221 | 0 | Painel SEMED (cards) |
| 14 | `RankingGestores.jsx` | 194 | 0 | Ranking (tabela) |

**Com visualização gráfica real:** 5 (Analytics, PME, Diary, Dashboard-hub, PME-ext).
**Baseados em cards/tabelas:** 9.

## 2. Há sobreposição?
**Sim, moderada:**
- **Analytics × PME × SemedPanel × RankingGestores** — todos exibem indicadores de
  rede (rendimento, frequência, ranking de escolas) para públicos diferentes, com
  código de agregação próprio (duplicação de lógica).
- **BuscaAtiva × BolsaFamilia** — ambos giram em torno de frequência/infrequência.
- **DiaryDashboard × cobertura curricular** — cumprimento pedagógico.
- **Portais (Professor/Aluno)** — específicos, sem sobreposição (corretamente separados).

## 3. Responsabilidades (o que cada um deve ser)
| Dashboard | Responsabilidade definitiva |
|---|---|
| **Analytics** | Visão **operacional da rede** (gestão/admin) — visão profunda multi-indicador |
| **PME / SemedPanel** | Visão **estratégica/executiva** (SEMED) — indicadores de política pública |
| **RankingGestores** | Recorte comparativo (pode virar *view* do Analytics) |
| **DiaryDashboard** | Especializado: cumprimento de diário/conteúdo |
| **BuscaAtiva/BolsaFamilia** | Especializado: frequência/condicionalidade social |
| **Vaccine/Associal** | Especializado: saúde/assistência |
| **Professor/Aluno** | Portais — manter separados |
| **Dashboard.js** | **Hub de navegação** (não é dashboard analítico) |

## 4. Unificar ou especializar?
**Recomendação híbrida:**
- **Unificar a CAMADA DE DADOS** (não as telas): todos os indicadores de rede devem
  vir de **um Motor de Indicadores único** (doc 6/7), eliminando lógica duplicada.
- **Especializar a APRESENTAÇÃO por público:** manter dashboards distintos, porém
  como *"lentes"* sobre o mesmo motor:
  - **Dashboard Operacional** (gestão) ← evolução do `AnalyticsDashboard`.
  - **Dashboard Executivo** (SEMED/secretário) ← convergência PME + SemedPanel + Ranking.
  - **Dashboards especializados** (Diário, Busca Ativa/PBF, Saúde, Social) mantidos.
  - **Portais** (Professor/Aluno) mantidos.

## 5. Arquitetura definitiva recomendada dos dashboards
```
        ┌──────────────────────── Motor de Indicadores (novo) ────────────────────────┐
        │  definição declarativa (fórmula+dimensões+fonte) → marts materializados      │
        └───────────────┬───────────────────────────┬───────────────────┬────────────┘
                        ▼                           ▼                   ▼
              Dashboard OPERACIONAL       Dashboard EXECUTIVO     Dashboards ESPECIALIZADOS
              (gestão/admin)              (SEMED/secretário)      (Diário · BuscaAtiva/PBF ·
              ← AnalyticsDashboard        ← PME+SemedPanel+Rank    Saúde · Social)
                        │                           │                   │
                        └──────── componentes de gráfico compartilhados (recharts) ────┘
                                   (KpiCard, TrendChart, DistributionChart, RankingTable)
        Portais (Professor / Aluno) — consomem endpoints próprios, fora do BI de rede.
```

## 6. Ações recomendadas (sem implementar agora)
1. **P1:** criar biblioteca de componentes de gráfico compartilhados (hoje duplicados entre Analytics/PME/Diary).
2. **P1:** definir contrato único de "indicador" que os 3 níveis de dashboard consomem.
3. **P2:** convergir PME + SemedPanel + Ranking no **Dashboard Executivo**.
4. **P2:** transformar RankingGestores em *view* do Operacional.
5. **NÃO** criar novos dashboards antes do Motor de Indicadores.

> **Conclusão:** o problema não é "faltam dashboards" — é **falta de uma fonte
> única de indicadores** por trás deles. Unificar dados, especializar telas.
