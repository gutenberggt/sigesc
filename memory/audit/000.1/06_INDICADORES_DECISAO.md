# 000.1 · 6 — Indicadores: Decisão

> READ-ONLY. Base: `analytics.py`, `pme_anos_finais.py`, `bf_network_stats.py`,
> `curriculum_coverage_stats`, motores de risco.

## 1. Quantos indicadores já existem?
**~20 indicadores identificáveis** (calculados por endpoints/serviços):

| Indicador | Origem | Tipo |
|---|---|---|
| Overview da rede (totais) | `analytics/overview` | calculado |
| Tendência de matrícula | `analytics/enrollments/trend` | calculado |
| Frequência mensal | `analytics/attendance/monthly` | calculado |
| Notas por componente | `analytics/grades/by-subject` | calculado |
| Notas por período | `analytics/grades/by-period` | calculado |
| Ranking de escolas | `analytics/schools/ranking` | calculado |
| Performance de alunos | `analytics/students/performance` | calculado |
| Performance de professores | `analytics/teachers/performance` | calculado |
| Distribuição de notas | `analytics/distribution/grades` | calculado |
| Rendimento por nível/escola (PME) | `pme/analytics` | calculado |
| Distorção idade-série (PME) | `pme/analytics` | calculado |
| Distribuição cor/raça (PME) | `pme/analytics` | calculado |
| Indicadores externos PME | `pme/external-indicators` | **estático (cadastro manual)** |
| Frequência PBF / condicionalidade | `bf_network_stats` | calculado |
| Cobertura curricular | `curriculum_coverage_stats` | calculado (materializado parcial) |
| Cumprimento de diário | `diary_dashboard` | calculado |
| Score de risco acadêmico | `academic_risk_engine` | calculado |
| Score de risco de frequência | `attendance_risk_engine` | calculado |
| Score de risco geral | `overall_risk_engine` | calculado |
| Ranking de gestão | `RankingGestores`/analytics | calculado |

## 2. Quantos são calculados vs. estáticos?
- **Calculados on-the-fly:** ~18 (recalculados a cada request).
- **Estáticos/cadastro manual:** ~2 (indicadores externos PME, metas).
- **Materializados (snapshot):** poucos (`bf_network_stats_snapshots`, cobertura parcial).

## 3. Quais são reutilizados?
- Frequência e média/rendimento aparecem em Analytics **e** PME **e** BF **e** risco —
  **mesma métrica, implementações diferentes**.
- Distorção idade-série e cor/raça: só no PME (bem localizados).

## 4. Quais possuem lógica duplicada? 🔴
- **Taxa de frequência** (analytics × PME × BF × risco de frequência) — 4 implementações.
- **Média/aprovação** (analytics × PME × risco acadêmico × boletim/promoção) — múltiplas.
- **Ranking de escolas** (analytics × RankingGestores).
- **Canonicalização de série** já foi centralizada (`serie_canonical`) — bom precedente.

## 5. Quais poderiam ser parametrizados?
Praticamente todos: um indicador = { fórmula, dimensões (escola/turma/série/tempo/
demografia), filtros, granularidade, fonte, política de refresh }. Hoje isso está
hard-coded em cada endpoint.

## 6. Decisão
- **UNIFICAR** as métricas duplicadas (frequência, média/aprovação, ranking) numa
  biblioteca de cálculo canônica (`services/indicators/`), consumida por todos os dashboards.
- **PARAMETRIZAR** via um **Motor de Indicadores** declarativo (doc 7).
- **MATERIALIZAR** os indicadores de rede em marts (refresh incremental) para escala.
- **MANTER** cadastro manual apenas onde não há fonte (metas, PME externo).

> **Achado-chave:** não faltam indicadores — falta **uma definição única** deles.
> A duplicação de cálculo é a maior dívida analítica atual.
