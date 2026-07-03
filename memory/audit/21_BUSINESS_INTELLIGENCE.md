# ENTREGA 21 — Business Intelligence (análise de prontidão)

⏳ **PENDENTE — Onda 2** (análise aprofundada). Diagnóstico preliminar da Onda 1:

**O que já existe:** grande volume de dados estruturados (notas, frequência,
matrícula, diário, cobertura curricular, PBF), dashboards analíticos e Painel PME,
relatórios mensais agendados, IA (Claude) para análise/planos, snapshots diversos.

**O que pode ser reaproveitado:** `analytics.py`, `pme_anos_finais.py`,
`monthly_report_service.py`, `bf_network_stats.py`, `curriculum_coverage_stats`,
snapshots existentes como base de marts.

**O que deve ser refatorado:** unificar motores de risco/indicadores; padronizar
snapshots; materializar agregações (hoje calculadas por request).

**O que precisa ser criado (❌):** **Motor de Indicadores canônico e configurável**,
**camada de BI dedicada** (marts materializados por tenant/escola/série com cache
incremental), **Metas Estratégicas**.

**Dashboards que podem evoluir:** Analytics + PME + SemedPanel poderiam convergir
para uma camada BI única com especialização por público (gestão × SEMED × escola).

**Modelos de dados prontos para consumo:** `grades`, `attendance`, `enrollments`,
`students` (demografia via `color_race`), `curriculum_coverage_stats`,
`bolsa_familia_tracking` — já suportam a maioria dos indicadores de rede.

**Requer fonte externa/cadastro manual:** metas estratégicas, indicadores PME
externos (já há `pme_external_indicators`), dados MEC (Educacenso/Presença).
