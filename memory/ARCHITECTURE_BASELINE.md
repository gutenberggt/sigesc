# ARCHITECTURE_BASELINE.md — SIGESC IA
### A "Constituição" arquitetural do projeto · Baseline oficial

> **Status:** Onda 1 concluída (Jun/2026) · Onda 2 pendente de aprovação.
> **Natureza:** documento vivo, READ-ONLY nesta sprint (nenhum código alterado).
> **Regra de ouro:** *toda sprint futura DEVE consultar este documento antes de
> propor novas funcionalidades — para reutilizar a arquitetura existente e evitar
> duplicidade.* **Consolidar antes de expandir.**

---

## 1. Visão Geral
O **SIGESC IA** é um **Sistema Integrado de Gestão Escolar multi-tenant (SaaS)**
para secretarias municipais de educação. Núcleo: gestão de escolas, turmas,
alunos, matrículas, servidores, folha, notas, frequência, diário, documentos
oficiais verificáveis, movimentação institucional e uma camada crescente de
inteligência (risco, alertas, IA generativa). Opera **offline-first (PWA)** e
com **isolamento de dados por mantenedora** (Row-Level Security fail-closed).

**Stack:** React 19 (CRA/PWA) · FastAPI 0.110 (Python 3.11) · MongoDB 7 (Motor async)
· deploy Coolify v4 + Traefik. IA via Claude (emergentintegrations/Anthropic).
E-mail via Resend. Arquivos via FTP.

## 2. Resumo Executivo (métricas)
| Dimensão | Qtde | | Dimensão | Qtde |
|---|---|---|---|---|
| Routers backend | 89 | | Páginas React | 77 |
| Endpoints HTTP | 574 | | Componentes React | 105 (46 shadcn) |
| Services de domínio | ~44 | | Hooks | 17 |
| Coleções MongoDB | 102 | | Contexts | 9 |
| Índices | ~190 | | Rotas (`<Route>`) | 86 |
| Papéis (roles) | 16 | | API clients (front) | 38 |
| Arquivos de teste | 173 | | Iterações de teste | 113 |
| LOC backend (s/ testes) | ~83.7k | | LOC frontend | ~82.6k |

**Diagnóstico em uma frase:** arquitetura **madura e coesa no core operacional**,
com governança destrutiva de referência (transfer/rollback) e offline-first real;
os riscos estão em **modelagem duplicada** (grade horária e vínculo aluno↔turma),
**arquivos-monólito** e **preparo para BI/escala**.

## 3. Princípios Arquiteturais (adotados/observados)
1. **Multi-tenant fail-closed** — sem tenant → zero dados; super_admin bypass controlado.
2. **Defense-in-depth de autorização** — RBAC + matriz dinâmica + RLS + escopo de escola.
3. **Mutações destrutivas governadas** — dry-run + idempotência + lock + auditoria + rollback (`with_critical_mutation`).
4. **Offline-first** — a sessão e o trabalho do professor sobrevivem à ausência de rede.
5. **Documentos verificáveis** — todo documento oficial tem trilha e verificação pública (QR).
6. **Contrato JSON limpo** — UUID em `id`, nunca ObjectId no contrato; `field_validator` tolera legado.
7. **Consolidar antes de expandir** — reutilizar coleções/módulos; não criar Nª representação de dados existentes.
8. **Baseline viva** — este documento é atualizado a cada mudança estrutural.
9. **Single Source of Truth de Indicadores (SSoT)** — *nenhum indicador pode ser
   calculado dentro de dashboards, páginas ou componentes.* Todo indicador é
   produzido **exclusivamente pelo Motor de Indicadores** (futuro domínio), a
   única fonte oficial de cálculo do sistema. Dashboards/IA/relatórios apenas
   **consomem** o resultado. Este princípio orienta todas as evoluções futuras.

## 3.1 Diretriz permanente — checklist obrigatório de reuso (antes de implementar)
> Toda nova funcionalidade DEVE responder, **antes** da implementação:
> 1. Existe algum **dado** semelhante no sistema?
> 2. Existe algum **indicador** equivalente?
> 3. Existe algum **Service** reutilizável?
> 4. Existe alguma **API** reutilizável?
> 5. Existe algum **Dashboard** que já consome essa informação?
> 6. O cálculo **deveria** ser responsabilidade do **Motor de Indicadores**?
>
> **Se qualquer resposta for "sim" → a prioridade é REUTILIZAR, nunca duplicar.**

## 4. Matriz de Capacidades (resumo — completo em [audit/19](audit/19_MATRIZ_CAPACIDADES.md))
| Área | Status |
|---|---|
| Multi-tenancy / RLS | ✅ |
| Gestão escolar (escolas/turmas/alunos/matrículas) | ✅ |
| Notas / Frequência / Diário | ✅ |
| Documentos oficiais + verificação QR | ✅ |
| Transferência institucional + rollback | ✅ |
| Bolsa Família | ✅ |
| Painel PME (todos os níveis) | ✅ |
| Offline-first (PWA) | ✅ |
| RH / Folha | ⚠ |
| Currículo v2 / Grade horária | ⚠ (WRITE≠READ) |
| Analytics / Relatórios mensais / Alertas / Risco | ⚠ |
| Student Intelligence Engine (SIE) | ⚠ |
| Integração MEC | ⚠/❌ |
| **Motor de Indicadores** | ❌ |
| **Metas Estratégicas** | ❌ |
| **BNCC + IA** | ❌ |
| **Camada de BI dedicada** | ❌ |
| **Sync offline de Conteúdo/Diário (Fase B)** | ❌ |

## 5. Roadmap (resumo — completo em [audit/20](audit/20_ROADMAP.md))
- **Curto (0–3m):** sanear status legados, auditar RBAC manual, ampliar rate limit, limpar repo, quebrar `StudentsComplete.js`.
- **Médio (3–6m):** consolidar vínculo aluno↔turma; concluir remoção do legado de grade horária; unificar motores de risco; snapshots únicos; modularizar `server.py`/`models.py`; replica set + backup.
- **Longo (6–12m):** **Motor de Indicadores** → **BI dedicada** → Metas Estratégicas → Fase B offline → BNCC+IA → SIE → MEC.

## 6. Riscos e Débitos prioritários
- 🔴 **D1** Grade horária WRITE≠READ (3 coleções).
- 🔴 **D2** Vínculo aluno↔turma triplicado (`enrollments`/`students.class_id`/`class_students`).
- 🟡 **D3** `StudentsComplete.js` >3.800 linhas · **D4** `server.py`/`models.py` monólitos.
- 🟡 **D5** Motores de risco sobrepostos · **D6** status legados · **D7** RBAC desigual · **D8** snapshots múltiplos.
- ⚫ **D9** legados (`mantenedora` singular, `render_jobs`×`document_render_jobs`, `App_old.js`, `server.py.bak`).

## 6.1 Decisões arquiteturais (Sprint 000.1)
As decisões priorizadas derivadas destes achados estão em
[`EXECUTIVE_ARCHITECT_REVIEW.md`](EXECUTIVE_ARCHITECT_REVIEW.md) + `audit/000.1/`
(priorização P0–P3, mapa de dependências, plano de refatoração, BI readiness,
decisão de dashboards/indicadores e plano de BI). **A Onda 2 só inicia após a
validação dessas decisões.**

## 7. Índice da documentação da auditoria
**Onda 1 (entregue):**
- [00 — Sumário/Métricas](audit/00_SUMARIO.md)
- [01 — Arquitetura Geral](audit/01_ARQUITETURA_GERAL.md)
- [02 — Inventário de Módulos](audit/02_INVENTARIO_MODULOS.md)
- [05 — Banco de Dados](audit/05_BANCO_DADOS.md)
- [06 — APIs](audit/06_APIS.md)
- [11 — Rotas](audit/11_ROTAS.md)
- [12 — Permissões](audit/12_PERMISSOES.md)
- [18 — Avaliação Arquitetural](audit/18_AVALIACAO_ARQUITETURAL.md)
- [19 — Matriz de Capacidades](audit/19_MATRIZ_CAPACIDADES.md)
- [20 — Roadmap](audit/20_ROADMAP.md)

**Onda 2 (pendente de aprovação):** 03 Dashboards · 04 Indicadores · 07 Componentes ·
08 Hooks · 09 Services · 10 Contexts · 13 Integrações · 14 IA · 15 Relatórios ·
16 Código Duplicado · 17 Código Obsoleto · 21 Business Intelligence.

---
*Última atualização: Jun/2026 (Sprint 000 — Onda 1). Manter sincronizado a cada mudança estrutural.*
