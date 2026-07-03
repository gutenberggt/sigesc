# ENTREGA 03 — Dashboards (arquitetura definitiva)

> **Onda 2 · Prioridade #3.** READ-ONLY. Não apenas inventário — decisão de
> responsabilidade e arquitetura final, alinhada ao SSoT (dashboards **consomem**
> indicadores, nunca os calculam).

## 1. Os 14 dashboards — responsabilidade, público e indicadores
| Dashboard | Público | Responsabilidade definitiva | Indicadores que DEVEM permanecer | O que deve MIGRAR |
|---|---|---|---|---|
| **AnalyticsDashboard** (2.404 ln) | Gestão/Admin | **Operacional da rede** (visão profunda) | A1,A2,A4,B1,C1,C2,F1,F3,F4 | política pública → Executivo |
| **PmeAnosFinais** (303) | SEMED/Gestão | Indicadores PME (política) | A1/C4,C3,D1,D2 | fundir no Executivo |
| **PmeExternalIndicators** (248) | SEMED | Metas/indicadores manuais PME (H1) | H1 | — (entrada de dados) |
| **SemedPanel** (221) | SEMED/Secretário | Visão executiva (cards) | resumo A1,B1,F1 | fundir no Executivo |
| **RankingGestores** (194) | Gestão/SEMED | Comparativo | F1,F2 | virar *view* do Operacional/Executivo |
| **DiaryDashboard** (528) | Gestão/Escola | Cumprimento pedagógico | E1,E2 | manter especializado |
| **BuscaAtivaDashboard** (622) | Gestão/Social | Infrequência/evasão | B2 | manter especializado |
| **BolsaFamilia** (634) | Gestão/Secretário | Condicionalidade PBF | B3 | manter especializado |
| **VaccineDashboard** (654) | Saúde/Admin | Saúde escolar | (saúde) | manter especializado |
| **AssocialDashboard** (402) | Assistência | Serviço social | (social) | manter especializado |
| **PmpiEngine** (629) | Gestão | Risco/intervenções | G1-G3 | consumir Motor (risco unificado) |
| **ProfessorDashboard** (416) | Professor | Portal do professor | (turmas) | manter (fora do BI de rede) |
| **AlunoDashboard** (296) | Aluno | Portal do aluno | (boletim) | manter (fora do BI de rede) |
| **Dashboard.js** (856) | Todos | **Hub de navegação + KPIs** | KPIs topo | não é dashboard analítico |

## 2. Sobreposições confirmadas
- **Analytics × PME × SemedPanel × Ranking** → mesmos indicadores de rede, públicos
  diferentes, **4 implementações de cálculo**. É o principal alvo de consolidação.
- **BuscaAtiva × BolsaFamilia** → ambos sobre frequência (B1) — devem consumir a MESMA base.
- **PmpiEngine** → risco duplicado (G1-G3) entre motores.

## 3. Componentes compartilháveis (hoje duplicados)
Extrair uma biblioteca `components/analytics/`:
`KpiCard`, `TrendChart`, `DistributionChart`, `RankingTable`, `RaceDistributionChart`,
`AttendanceHeatmap`, `FilterBar` (ano→nível→escola→zona), `IndicatorProvider`
(hook que busca de `/api/bi/*`). Hoje recharts aparece isolado em Analytics(24),
PME(14), Diary(13), Dashboard-hub(10), PME-ext(4) — sem reuso.

## 4. Arquitetura definitiva dos dashboards
```
                    Motor de Indicadores (SSoT) → API /api/bi/*
                                     │
     ┌───────────────────────────────┼───────────────────────────────┐
     ▼                                ▼                                ▼
 DASHBOARD OPERACIONAL        DASHBOARD EXECUTIVO            DASHBOARDS ESPECIALIZADOS
 (gestão/admin)              (SEMED/secretário)             ┌────────────────────────┐
 ← AnalyticsDashboard        ← PME + SemedPanel + Ranking   │ Diário (E1/E2)         │
 A1,A2,A4,B1,C1,C2,          A1,C3,C4,D1,D2,F1,F2,          │ Busca Ativa (B2)       │
 F1,F3,F4                    H1 (metas)                     │ Bolsa Família (B3)     │
                                                            │ Saúde · Social         │
                                                            │ Risco/PMPI (G1-G3)     │
                                                            └────────────────────────┘
        ── biblioteca compartilhada components/analytics/ (KpiCard, Charts, FilterBar) ──
 PORTAIS (Professor · Aluno) — endpoints próprios, fora do BI de rede.
 HUB (Dashboard.js) — navegação + KPIs de topo (consome /api/bi resumo).
```

## 5. Decisões
1. **Consolidar dados, especializar telas** (não fundir tudo numa só tela).
2. **Convergir** PME + SemedPanel + Ranking → **Dashboard Executivo**.
3. **RankingGestores** → *view* (não dashboard autônomo).
4. **Especializados e Portais** permanecem.
5. **Nenhum dashboard novo** antes do Motor de Indicadores.
6. **Regra SSoT:** todo gráfico consome `/api/bi/*`; zero cálculo em página/componente.

## 6. Estado final desejado
- **3 dashboards de rede** (Operacional, Executivo, Hub) + **N especializados** + **2 portais**.
- **1 biblioteca** de componentes de visualização compartilhada.
- **1 fonte** de indicadores (Motor). Consistência garantida entre todas as telas.
