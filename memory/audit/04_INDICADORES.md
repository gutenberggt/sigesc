# ENTREGA 04 — Catálogo de Indicadores (documento central da plataforma)

> **Onda 2 · Prioridade Máxima #2.** READ-ONLY. Base de código: `analytics.py`,
> `pme_anos_finais.py`, `bf_network_stats.py`, `grade_calculator.py`,
> `attendance_utils.py`, motores de risco, `diary_dashboard.py`.
>
> **Princípio SSoT:** a partir da definição do Motor de Indicadores, todo indicador
> abaixo terá **uma única implementação canônica**. Este catálogo é a especificação
> de referência para essa migração.

## Legenda de campos
Nome · Objetivo · **Fórmula** · Fonte · Dependências · **Granularidade** (rede/escola/turma/aluno)
· Frequência · Responsável (produtor) · Dashboards consumidores · APIs · Parametrizável? · Cache? · Materializável?

---

## GRUPO A — Rendimento / Aprovação
### A1. Taxa de Aprovação/Reprovação
- **Objetivo:** % de alunos aprovados vs. reprovados/retidos no ano.
- **Fórmula:** `aprovados / total_com_resultado`; resultado derivado do status de
  matrícula (`progressed`/`reclassified`→aprovado; `dropout`→abandono; `transferred`;
  `cancelled`) OU do cálculo de média (turmas numéricas).
- **Fonte:** `enrollments.status` + `grades`. **Dependências:** média (A2), status canônico (D6), vínculo (D2).
- **Granularidade:** rede/escola/turma/série/aluno. **Frequência:** diária/on-demand. **Responsável:** Motor (futuro) / hoje `analytics.py` + `pme_anos_finais.py`.
- **Dashboards:** Analytics, PME, SemedPanel, Ranking. **APIs:** `analytics/overview`, `analytics/schools/ranking`, `pme/analytics`.
- **Parametrizável:** sim (regra de aprovação vem da mantenedora). **Cache:** sim. **Materializável:** sim (`mart_rendimento`).

### A2. Média (ponderada) por componente/aluno
- **Objetivo:** desempenho numérico oficial.
- **Fórmula:** `(B1×2 + B2×3 + B3×2 + B4×3) / 10`; recuperação semestral substitui a MENOR
  nota do semestre (empate → maior peso), só se a rec for maior.
- **Fonte:** `grades`. **Dependências:** `grade_calculator`, `gradeHelpers` (front). **Granularidade:** aluno→turma→escola→rede.
- **Frequência:** on-demand. **Dashboards:** Boletim, Promoção, Analytics (`grades/by-subject`,`grades/by-period`,`distribution/grades`), PME. **APIs:** `analytics/grades/*`, `grades/*`.
- **Parametrizável:** sim (pesos/média de aprovação). **Cache:** parcial. **Materializável:** sim.
- ⚠️ **Duplicação:** cálculo replicado em `grade_calculator` (back), `gradeHelpers` (front), `analytics`, `pme`, boletim/promoção.

### A3. Média conceitual (Ed. Infantil / 1º-2º ano)
- **Objetivo:** resultado de turmas conceituais. **Fórmula:** Média = MAIOR conceito; status
  "Em andamento"/"Concluiu a etapa"/"Promovido(a)".
- **Fonte:** `grades` (conceitos). **Responsável:** `grade_calculator.determinar_resultado_documento`.
- **Granularidade:** aluno/turma. **Materializável:** sim. ⚠️ lógica compartilhada com A2.

### A4. Distribuição de notas
- **Objetivo:** histograma de faixas de nota. **Fórmula:** contagem por faixa.
- **API:** `analytics/distribution/grades`. **Dashboards:** Analytics. **Materializável:** sim.

## GRUPO B — Frequência
### B1. Taxa de Frequência (mensal/anual)
- **Objetivo:** % de presença. **Fórmula:** `dias_presentes / dias_letivos`, com
  **consolidação diária**: presença em ≥50% das aulas do dia = dia PRESENTE.
- **Fonte:** `attendance` + `calendario_letivo` (dias letivos, sábado letivo). **Dependências:** `attendance_utils.compute_monthly_valid_absences`, `school_calendar_helper`.
- **Granularidade:** aluno→turma→escola→rede→mês. **Frequência:** diária. **Responsável:** `attendance_utils` (hoje).
- **Dashboards:** Analytics (`attendance/monthly`), BuscaAtiva, BolsaFamilia, PME. **APIs:** `analytics/attendance/monthly`, `attendance/*`, `bolsa_familia`.
- **Parametrizável:** sim (limiar diário 50%). **Cache:** sim. **Materializável:** sim (`mart_frequencia`).
- 🔴 **Duplicação crítica:** frequência calculada em ≥4 lugares (analytics, BF, PME, risco de frequência) com implementações distintas.

### B2. Infrequência / Busca Ativa
- **Objetivo:** alunos abaixo do limiar (risco de evasão). **Fórmula:** `1 - B1`, com corte configurável.
- **Fonte:** `attendance`. **Dashboards:** BuscaAtiva, Intervenções. **Materializável:** sim (derivado de B1).

### B3. Condicionalidade Bolsa Família (PBF)
- **Objetivo:** cumprimento de frequência PBF. **Fórmula:** frequência apurada vs. limiares
  MEC **60%** (4–5 anos) / **75%** (6–17 anos); consolidação ≥50%/dia (regra local).
- **Fonte:** `bolsa_familia_tracking` + `attendance`. **Responsável:** `bf_network_stats`, `bf_reason_suggestion`.
- **Granularidade:** aluno→escola→rede. **Dashboards:** BolsaFamilia, BuscaAtiva. **Materializável:** sim (`bf_network_stats_snapshots` — já existe). ⚠️ deriva de B1.

## GRUPO C — Matrícula / Fluxo
### C1. Total de Matrículas / Ativos
- **Fórmula:** contagem por `enrollments.status` (ativos = active/progressed/reclassified).
- **Fonte:** `enrollments`. **Granularidade:** rede/escola/turma/série/zona. **APIs:** `analytics/overview`, `pme/analytics`. **Materializável:** sim (`mart_matricula`). **Dependência dura:** vínculo (D2).

### C2. Tendência de Matrícula
- **Fórmula:** série temporal de C1 por período. **API:** `analytics/enrollments/trend`. **Materializável:** sim.

### C3. Distorção Idade-Série
- **Objetivo:** alunos com idade acima da adequada à série. **Fórmula:** `idade_no_ano - idade_esperada(série) ≥ 2 anos`.
- **Fonte:** `students.birth_date` + série (via `student_series`/`grade_level`). **Responsável:** `pme_anos_finais`.
- **Granularidade:** aluno→série→escola→rede. **Dashboards:** PME. **API:** `pme/analytics`. **Materializável:** sim. **Parametrizável:** sim (limiar de anos).

### C4. Rendimento por status (aprovado/abandono/transferido/cursando/cancelado)
- **Fórmula:** contagem por `outcome_map(status)`. **Fonte:** `enrollments`. **Dashboards:** PME. **Materializável:** sim. ⚠️ equivalente a A1 sob outra ótica.

## GRUPO D — Demografia (recortes)
### D1. Distribuição por Cor/Raça
- **Fórmula:** contagem por `students.color_race` (bucket `nao_informada`). **Fonte:** `students`.
- **Granularidade:** rede/escola/série. **Dashboards:** PME, Indicadores da Rede. **API:** `pme/analytics`, `students`. **Materializável:** sim.
- ⚠️ **Nota crítica:** usar `color_race` (EN); `cor_raca` (legado) está vazio em prod.

### D2. Alunos com Deficiência (PcD) / com NIS / por Zona (urbana/rural)
- **Fórmula:** contagem por `disabilities` / `nis` / `schools.zona_localizacao`. **Fonte:** `students`, `schools`.
- **Dashboards:** PME. **Materializável:** sim.

## GRUPO E — Currículo / Diário
### E1. Cobertura Curricular
- **Objetivo:** % de habilidades/conteúdos previstos efetivamente registrados.
- **Fonte:** `curriculum_coverage_stats`, `content_entries`, `bncc_skills`. **Dashboards:** Cobertura, DiaryDashboard. **Materializável:** sim (parcialmente já é).

### E2. Cumprimento de Diário
- **Objetivo:** % de aulas previstas com diário/frequência lançados. **Fonte:** `diary_snapshots`, `attendance`, grade horária. **Dashboards:** DiaryDashboard. **Dependência:** grade horária (D1). **Materializável:** sim.

## GRUPO F — Comparativos / Ranking
### F1. Ranking de Escolas / F2. Ranking de Gestão
- **Objetivo:** ordenar escolas/gestores por índice composto (rendimento+frequência+cobertura).
- **Fonte:** agrega A1/B1/E1. **Dashboards:** Analytics, RankingGestores, SemedPanel. **APIs:** `analytics/schools/ranking`. **Materializável:** sim (derivado). ⚠️ **duplicação** entre Analytics e RankingGestores.

### F3. Performance de Alunos / F4. Performance de Professores
- **Fórmula:** agregações de A2/B1 por aluno/professor. **APIs:** `analytics/students/performance`, `analytics/teachers/performance`. **Materializável:** sim.

## GRUPO G — Risco (motores)
### G1. Risco Acadêmico · G2. Risco de Frequência · G3. Risco Geral
- **Objetivo:** score preditivo de risco pedagógico. **Fórmula:** ponderação de A2/B1/histórico.
- **Fonte:** `student_risk_scores`, `academic_risk_engine`, `attendance_risk_engine`, `overall_risk_engine`, `diagnostic_engine`.
- **Granularidade:** aluno. **Dashboards:** PmpiEngine, Intervenções. **Materializável:** sim.
- 🔴 **Duplicação:** 3–4 motores com scoring sobreposto → **unificar** (D5) no Motor de Indicadores.

## GRUPO H — Externos / Manuais
### H1. Indicadores Externos PME
- **Objetivo:** metas/indicadores de política pública. **Fonte:** **cadastro manual** (`pme_external_indicators`).
- **Dashboards:** PmeExternalIndicators. **Materializável:** não (dado inserido). **RBAC:** SEMED só lê.

---

## Análise transversal
### Indicadores equivalentes
- **A1 ≡ C4** (aprovação por média × por status de matrícula) — unificar definição de "resultado".
- **B2, B3** derivam de **B1** (mesma base de frequência).
- **F1 ≈ F2** (ranking escola × gestor) — mesmo índice composto, recortes diferentes.

### Indicadores derivados (não recalcular; compor)
- B2 (infrequência) = 1 − B1 · B3 (PBF) = B1 vs. limiar · C2 = série temporal de C1 ·
  F1/F2/F3/F4 = agregações de A/B/E · G1-G3 = ponderação de A2/B1.

### Indicadores calculados em MÚLTIPLOS locais (dívida) 🔴
| Métrica | Locais atuais |
|---|---|
| Frequência (B1) | `analytics`, `bf_network_stats`, `pme`, `attendance_risk_engine` |
| Média/Aprovação (A1/A2) | `grade_calculator`, `gradeHelpers` (front), `analytics`, `pme`, boletim, promoção |
| Ranking (F1/F2) | `analytics`, `RankingGestores` |
| Resultado/Status | `pme.outcome_map`, `grade_calculator.determinar_resultado_documento` |

## Proposta de unificação (para o Motor de Indicadores)
1. **Definição canônica única** por indicador em `bi_indicator_defs` (fórmula + dimensões + fonte).
2. **Biblioteca de cálculo** `services/indicators/calculators.py` — implementação ÚNICA de:
   `frequencia()`, `media_ponderada()`, `resultado_final()`, `distorcao_idade_serie()`,
   `indice_composto()`, `risco()`. Todos os consumidores (analytics, PME, BF, boletim,
   risco, dashboards) passam a chamá-la.
3. **Derivados são composições** (nunca reimplementados): B2/B3/C2/F*/G* referenciam bases.
4. **Materialização** dos indicadores de rede em `mart_*` (refresh incremental).
5. **Proibição arquitetural (SSoT):** remover qualquer cálculo de indicador de páginas/
   componentes/dashboards; migrar para o Motor. `gradeHelpers` (front) passa a exibir,
   não calcular (ou consome resultado do backend).

> **Este catálogo é o insumo direto do `bi_indicator_defs`.** Cada linha acima vira
> uma definição declarativa versionada.
