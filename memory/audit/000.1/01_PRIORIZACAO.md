# 000.1 · 1 — Priorização dos Problemas

> Matriz de priorização de TODOS os achados da Onda 1. READ-ONLY.
> Esforço: S(≤2d) · M(≤1sem) · L(≤3sem) · XL(>1mês). Risco/Impacto: Baixo/Médio/Alto.

## Tabela mestra
| ID | Achado | Prio | Esforço | Risco | Impacto | Dependências |
|---|---|---|---|---|---|---|
| **D6** | Valores de `status` legados fora do `Literal` (ex.: `enrollments.status='inactive'`) → 500 silencioso | **P0** | S | Baixo | Alto | nenhuma (padrão `with_critical_mutation` já existe) |
| **D7** | RBAC desigual: ~39 routers com checagem manual (risco de brecha, ex. bug `require_permission(None)`) | **P0** | M | Médio | Alto | matriz de permissões |
| **D2** | Vínculo aluno↔turma triplicado (`enrollments`×`students.class_id`×`class_students`) | **P0** | XL | **Alto** | Alto | grade horária, matrículas, promoção, relatórios |
| **D1** | Grade horária WRITE≠READ (`class_schedules`×`teacher_assignments`×`teacher_allocations`) | **P1** | L | **Alto** | Alto | diário, frequência, carga horária |
| **NEW-BI** | Ausência de Motor de Indicadores + camada de BI dedicada | **P1** | XL | Médio | **Alto** | snapshots, analytics, PME |
| **D10** | Rate limiting subutilizado (1 router) | **P1** | S | Baixo | Médio | — |
| **D5** | Motores de risco sobrepostos (academic/attendance/overall/diagnostic) | **P1** | L | Médio | Alto | alertas, PMPI, SIE |
| **D8** | Snapshots com múltiplos padrões e sem retenção unificada | **P2** | L | Médio | Médio | diário, BI, IA |
| **D3** | `StudentsComplete.js` >3.800 linhas | **P2** | M | Médio | Médio | — |
| **D4** | `server.py` (859) / `models.py` (~3.000) monólitos | **P2** | L | Médio | Médio | testes de regressão |
| **DASH** | Dashboards fragmentados sem arquitetura definitiva | **P2** | L | Médio | Alto | Motor de Indicadores |
| **INFRA** | MongoDB single-node; APScheduler in-process (risco de job duplicado em réplicas) | **P2** | M | Médio | Alto | deploy Coolify |
| **D9** | Legados (`mantenedora` singular, `render_jobs`×`document_render_jobs`, `App_old.js`, `server.py.bak`) | **P3** | S | Baixo | Baixo | confirmação de não-uso |
| **D11** | Arquivos de teste/backup soltos na raiz | **P3** | S | Baixo | Baixo | — |
| **ROUTE** | Nomenclatura de rotas PT/EN inconsistente | **P3** | S | Baixo | Baixo | — |

## Racional dos P0
- **D6** — barato e elimina 500 em produção; sem risco (coerção + saneamento idempotente).
- **D7** — segurança/integridade: superfície de autorização deve ser fechada antes de qualquer expansão.
- **D2** — é a **raiz** de bugs recorrentes (multisseriada, livro de promoção, frequência). É XL/Alto risco, então **não se corrige "no susto"**: entra como P0 de **planejamento** agora (decisão + design), execução faseada na Onda B do roadmap. Marca-se P0 porque cada nova feature sobre esse modelo aumenta o custo de correção.

## Observação estratégica
O par **D1+D2** (modelagem duplicada) representa o maior risco estrutural.
A recomendação é **congelar novas features que ampliem essas superfícies** até
que a decisão de consolidação (doc 3) seja aprovada.
