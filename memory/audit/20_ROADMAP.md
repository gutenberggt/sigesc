# ENTREGA 20 — Roadmap Arquitetural

> Auditoria READ-ONLY · Jun/2026. Roadmap baseado em evidência (Entregas 01–19).
> Prioridades: **P0** (fundação/risco), **P1** (evolução estruturante), **P2** (expansão).
> Nenhuma ação abaixo foi executada nesta sprint (apenas planejamento).

## Curto Prazo (0–3 meses) — melhorias rápidas / consolidação
| Prioridade | Ação | Justificativa | Débito |
|---|---|---|---|
| P0 | **Sanear valores de `status` legados** (matrículas/alunos) via `with_critical_mutation` | evita 500 silenciosos e ambiguidade | D6 |
| P0 | **Auditar RBAC dos ~39 routers** sem `require_roles`/`require_permission` | fechar superfície de autorização | D7 |
| P1 | **Ampliar rate limiting** (login, refresh, export, geração de PDF) | mitigar abuso/DoS | D10 |
| P1 | **Limpeza de repo:** mover/remover `App_old.js`, `server.py.bak`, `*.tar.gz`, `fix_*/verify_*` da raiz | higiene e clareza | D9/D11 |
| P1 | **Quebrar `StudentsComplete.js`** (>3.800 linhas) em componentes | manutenibilidade | D3 |
| P2 | Padronizar nomenclatura de rotas (PT vs EN) | consistência | — |
| P2 | Publicar contrato OpenAPI curado (`/docs` versionado) | preparar consumidores externos/BI | — |

## Médio Prazo (3–6 meses) — refatorações importantes
| Prioridade | Ação | Justificativa | Débito |
|---|---|---|---|
| P0 | **Consolidar vínculo aluno↔turma numa fonte única** (`enrollments`) com views derivadas; depreciar `students.class_id`/`class_students` | elimina classe inteira de bugs recorrentes | D2 |
| P0 | **Concluir remoção controlada do legado de grade horária** (`class_schedules` → modelo novo; aposentar dual-read/bridges) | fim do WRITE≠READ | D1 |
| P1 | **Unificar motores de risco** (academic/attendance/overall/diagnostic) num scoring canônico com pesos configuráveis | coerência e reutilização | D5 |
| P1 | **Estratégia única de snapshots** + política de retenção unificada | reduzir duplicação e custo | D8 |
| P1 | **Modularizar `server.py`/`models.py`** (router groups + models por domínio) | testabilidade e navegação | D4 |
| P1 | **MongoDB replica set + backup automatizado** em produção; worker dedicado p/ APScheduler | resiliência e escala | — |

## Longo Prazo (6–12 meses) — evoluções estruturais
| Prioridade | Ação | Justificativa |
|---|---|---|
| P0 | **Motor de Indicadores canônico e configurável** (definição declarativa + materialização) — base de toda a Análise/PME/BI | hoje **inexistente**; habilita BI real |
| P1 | **Camada de Business Intelligence dedicada** (marts materializados por mantenedora/escola/série, cache incremental) | dashboards escaláveis; ver [21](21_BUSINESS_INTELLIGENCE.md) |
| P1 | **Metas Estratégicas** (planejamento + acompanhamento) sobre `monthly_goals` | fechar lacuna ❌ da matriz |
| P1 | **Fase B Offline** — sincronização avançada de Conteúdo/Diário | continuidade do offline-first |
| P2 | **Módulo BNCC independente integrado com IA** | tarefa futura do PRD |
| P2 | **Amadurecer o SIE** (Student Intelligence Engine) sobre o motor de indicadores unificado | inteligência preditiva |
| P2 | **Integração MEC** (Educacenso / Sistema Presença) | interoperabilidade governamental |

## Princípio-guia (constituição)
> **Consolidar antes de expandir.** Toda nova feature deve primeiro consultar
> `ARCHITECTURE_BASELINE.md` e reutilizar módulos/coleções existentes. Evitar
> criar 4ª representação de dados que já existem (vínculo, grade, snapshot, risco).

## Sequenciamento recomendado
1. **Onda A (Curto P0/P1):** saneamento de status + auditoria RBAC + rate limit + limpeza.
2. **Onda B (Médio P0):** consolidação do vínculo aluno↔turma e da grade horária.
3. **Onda C (Médio/Longo P0/P1):** Motor de Indicadores → BI → Metas → unificação de risco.
4. **Onda D (Longo P2):** BNCC+IA, SIE, MEC, Fase B offline.
