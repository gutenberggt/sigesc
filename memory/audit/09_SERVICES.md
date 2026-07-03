# ENTREGA 09 — Services (foco: consumidos por dashboards / camada analítica)

> **Onda 2 · Prioridade #4.** READ-ONLY. Classificação: **exclusivo · compartilhado
> · duplicado · candidato à unificação**. Alinhado ao SSoT.

## 1. Services que alimentam dashboards / indicadores
| Service | Alimenta | Classe | Destino no SSoT |
|---|---|---|---|
| `pmpi_compute.py` | PmpiEngine, risco | compartilhado | mover cálculo → Motor |
| `academic_risk_engine.py` | risco acadêmico (G1) | **duplicado** (scoring) | **unificar** em `indicators/risco` |
| `attendance_risk_engine.py` | risco frequência (G2) | **duplicado** | **unificar** |
| `overall_risk_engine.py` | risco geral (G3) | **duplicado** | **unificar** |
| `diagnostic_engine.py` | diagnóstico/risco | compartilhado | consumir scoring unificado |
| `alert_engine.py` | alertas (`alert_rules`) | compartilhado | consome indicadores do Motor |
| `intervention_detector.py` | intervenções | compartilhado | consome risco unificado |
| `bf_network_stats.py` | BolsaFamilia, BuscaAtiva (B1/B3) | **duplicado** (frequência) | fonte-modelo de mart; mover cálculo → Motor |
| `bf_reason_suggestion.py` | BF (motivos) | exclusivo | manter |
| `attendance_utils.py` | frequência (B1) — canônico atual | **compartilhado (semi-canônico)** | **promover a base** do Motor p/ frequência |
| `grade_calculator.py` | média/resultado (A1/A2/A3) | **compartilhado (semi-canônico)** | **promover a base** do Motor p/ notas |
| `school_calendar_helper.py` | dias letivos (base de B1/E2) | compartilhado | manter (dependência do Motor) |
| `monthly_report_service.py` | relatórios mensais | compartilhado | consumir Motor |
| `monthly_report_scheduler.py` / `_email.py` | agendamento/envio | exclusivo | manter |
| `sie_service.py` | Student Intelligence | parcial | consumir Motor |
| `pedagogical_consolidation.py` / `history_consolidator.py` | histórico/consolidação | compartilhado | manter |

## 2. Services de renderização/documento (não são indicadores)
`bulletin_renderer`, `history_renderer`, `snapshot_pdf`, `diary_pdf_handler`,
`school_docs_service`, `school_doc_templates`, `document_files`, `render_worker`,
`verifiable_docs_service` → **exclusivos de documentos**; consomem indicadores/resultados,
não devem recalcular (ex.: boletim deve exibir a média do Motor, não recomputar).

## 3. Bridges legadas (candidatas a remoção pós-migração)
`legacy_schedule_bridge.py`, `legacy_content_bridge.py`,
`grade_legacy_migration_service.py`, `curriculum_v2_migration.py`,
`bf_legacy_migration.py` → **transitórios**; aposentar após consolidação (D1/D9).

## 4. Diagnóstico
- 🔴 **Duplicação de cálculo:** frequência (`attendance_utils` × `bf_network_stats` ×
  risco de frequência) e média/resultado (`grade_calculator` × `gradeHelpers` front ×
  `analytics` × `pme`).
- 🟢 **Bons candidatos a "base canônica":** `attendance_utils` (frequência) e
  `grade_calculator` (notas) já concentram muita regra — devem ser **absorvidos/expostos**
  pela biblioteca `services/indicators/` como implementação única.
- 🔴 **Motores de risco:** unificar num scoring só (D5).

## 5. Proposta
1. Criar `services/indicators/` como **fachada única** que reusa `attendance_utils` e
   `grade_calculator` internamente (não reescrever regra — **promover** a canônica).
2. Motores de risco → um `services/indicators/risco.py` parametrizável.
3. `bf_network_stats` → consome `indicators.frequencia()` (deixa de recalcular).
4. Renderers/relatórios → consomem resultados do Motor.
5. Marcar bridges legadas com data de aposentadoria.

> Detalhe completo de TODOS os ~44 services (inclui os não-analíticos) fica para o
> fechamento da Onda 2, conforme repriorização do arquiteto (foco atual = camada de dados/BI).
