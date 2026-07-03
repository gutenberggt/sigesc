# 000.1 · 4 — Business Intelligence Readiness

> Análise de prontidão para uma camada de BI. READ-ONLY (não implementar).

## Pergunta central
**O SIGESC IA já possui estrutura suficiente para suportar uma camada de BI?**
**Resposta: PARCIALMENTE — os DADOS existem; a INFRAESTRUTURA analítica NÃO.**

O sistema é rico em dados transacionais (OLTP) mas não possui camada analítica
(OLAP/marts) nem um motor de indicadores canônico. Hoje os "indicadores" são
calculados **on-the-fly** por endpoint, lendo coleções transacionais — o que
funciona em pequena escala, mas não sustenta BI multi-rede com performance.

## O que já existe 🟢
- **Dados transacionais completos:** `grades`, `attendance`, `enrollments`,
  `students` (demografia via `color_race`), `content_entries`, `diary_snapshots`,
  `curriculum_coverage_stats`, `bolsa_familia_tracking`, `payroll_*`.
- **Agregações prontas (endpoints):** `analytics.py` (overview, tendência de matrícula,
  frequência mensal, notas por componente/período, ranking de escolas, performance de
  alunos/professores, distribuição de notas) e `pme_anos_finais.py` (rendimento,
  distorção idade-série, cor/raça por nível/escola).
- **Alguns snapshots materializados:** `bf_network_stats_snapshots`, `ai_analysis_snapshots`.
- **IA para narrativa/insight** (Claude) já integrada.

## O que falta ❌ (para BI de verdade)
1. **Motor de Indicadores canônico** — definição declarativa (fórmula, dimensões,
   granularidade, fonte) versionada; hoje a lógica está espalhada e duplicada.
2. **Camada de marts materializados** — tabelas/coleções pré-agregadas por
   tenant/escola/série/período, atualizadas incrementalmente (não recalcular por request).
3. **Modelo dimensional** — dimensões (escola, turma, aluno, tempo, componente, série,
   demografia) + fatos (matrícula, frequência, nota, ocorrência) explícitos.
4. **Cache/refresh incremental** e **job de consolidação** dedicado.
5. **Metas Estratégicas** (baseline vs. meta vs. realizado) — `monthly_goals` incipiente.

## Quais modelos precisam evoluir
- Unificar **vínculo aluno↔turma** (D2) — pré-condição para fatos de matrícula confiáveis.
- Unificar **snapshots** (D8) — reaproveitar como mecanismo de marts.
- Padronizar **status/série** (D6 + canonicalização) — dimensões consistentes.

## Indicadores que JÁ podem ser calculados (dados existem)
Taxa de aprovação/reprovação, média por componente/série/escola, frequência
mensal/anual, infrequência (busca ativa), distorção idade-série, distribuição por
cor/raça, cobertura curricular, condicionalidade PBF, cumprimento de diário,
ranking de escolas/gestores, performance de professores.

## Indicadores que dependem de FONTE EXTERNA
- Dados MEC (Educacenso, Sistema Presença), IDEB/SAEB, censo populacional (para
  taxas líquidas de atendimento), Bolsa Família (base CadÚnico).

## Indicadores que dependem de CADASTRO MANUAL
- Metas estratégicas da secretaria, indicadores PME externos (`pme_external_indicators`
  — já previsto), planos de ação/intervenção.

## Veredito
> Avançar para BI **exige primeiro** o Motor de Indicadores + marts (doc 7).
> Os dados estão prontos; a arquitetura analítica precisa ser construída.
> **Não** construir mais dashboards ad-hoc sobre queries transacionais.
