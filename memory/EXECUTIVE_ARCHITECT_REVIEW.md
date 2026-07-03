# EXECUTIVE_ARCHITECT_REVIEW.md — SIGESC IA
### Revisão Arquitetural Executiva · Sprint 000.1 (Consolidação) · Jun/2026

> Documento de **decisão** derivado da auditoria (Sprint 000/Onda 1). READ-ONLY.
> Referência para todas as futuras decisões de arquitetura. Complementa
> `ARCHITECTURE_BASELINE.md`. Detalhes em `audit/000.1/`.

---

## 1. Resumo da auditoria
O SIGESC IA é um SaaS multi-tenant de gestão escolar de **grande porte**
(89 routers · **574 endpoints** · **102 coleções** · **~166 mil LOC** · 77 páginas ·
173 arquivos de teste). O core operacional (escolas, turmas, alunos, matrículas,
notas, frequência, diário, documentos, transferência institucional) é **maduro e
bem testado**, com destaques de engenharia: isolamento multi-tenant *fail-closed*,
operações destrutivas com dry-run+idempotência+rollback, e offline-first real (PWA).

Nesta escala, **decisões de arquitetura passam a valer mais que velocidade** — daí
a pausa estratégica desta sprint para transformar achados em decisões antes de
produzir mais documentação (Onda 2) ou código.

## 2. Principais riscos
| Risco | Sev. | Consequência se ignorado |
|---|---|---|
| 🔴 Grade horária WRITE≠READ (3 coleções) | Alta | inconsistência de grade/diário/frequência |
| 🔴 Vínculo aluno↔turma triplicado | Alta | bugs recorrentes; manutenção cara; fatos de BI não confiáveis |
| 🟡 Motores de risco/indicadores duplicados | Média | métricas divergentes entre dashboards |
| 🟡 Monólitos (`StudentsComplete.js`, `server.py`, `models.py`) | Média | evolução lenta e arriscada |
| 🟡 RBAC desigual (~39 routers manuais) | Média | brecha de autorização |
| ❌ Sem Motor de Indicadores / BI dedicado | Alta (estratégico) | impossível escalar analítico/BI |
| 🟡 MongoDB single-node / jobs in-process | Média | ponto único; jobs duplicados em réplica |

## 3. Prioridades (matriz)
- **P0 (imediato):** D6 sanear status legados · D7 auditar/fechar RBAC · **D2 decidir/desenhar** a unificação do vínculo aluno↔turma (execução faseada).
- **P1 (próximas sprints):** D1 unificar grade horária · Motor de Indicadores (fundação de BI) · D10 rate limiting · D5 unificar motores de risco.
- **P2:** D8 snapshots unificados · D3/D4 quebrar monólitos · arquitetura de dashboards · INFRA (replica set + worker).
- **P3:** D9 remover legados · D11 higiene de repo · nomenclatura de rotas.

## 4. Decisões arquiteturais recomendadas
1. **Congelar** ampliação das superfícies duplicadas (D1/D2) até aprovação do design de unificação.
2. **Unificar dados, especializar telas:** dashboards devem consumir uma **fonte única de
   indicadores**; não criar novos dashboards antes do Motor de Indicadores.
3. **BI de baixo para cima:** dados consistentes (D2/D6/D8) → Motor de Indicadores →
   marts materializados → dashboards Operacional/Executivo. Nunca telas antes da fundação.
4. **Segurança primeiro:** fechar RBAC (D7) e ampliar rate limit (D10) antes de expandir.
5. **Modularizar sem mudar comportamento** (D3/D4) com snapshots de regressão.
6. **Preparar produção para escala:** replica set + backup + worker de jobs dedicado.

## 5. Oportunidades
- Reaproveitar `analytics.py`/`pme`/`bf_network_stats` como base do Motor de Indicadores.
- Reusar `with_critical_mutation` para ETL idempotente de BI.
- IA (Claude) já integrada → camada de **insight narrativo** sobre marts.
- Convergir PME + SemedPanel + Ranking num **Dashboard Executivo** coeso.
- Base de dados já suporta ~18 indicadores de rede sem fonte externa.

## 6. Débitos técnicos (consolidado)
D1 grade horária · D2 vínculo triplicado · D3/D4 monólitos · D5 risco duplicado ·
D6 status legado · D7 RBAC · D8 snapshots · D9 legados · D10 rate limit ·
D11 higiene · INFRA persistência/jobs · **NEW-BI** motor de indicadores/BI ausente.

## 7. Cronograma sugerido (12 meses)
| Trimestre | Foco | Itens |
|---|---|---|
| **T1 (0–3m)** | Fundação/segurança | D6, D7, D10, higiene (D9/D11), quebrar `StudentsComplete.js` (D3); **design** da unificação do vínculo (D2) |
| **T2 (3–6m)** | Consolidação de dados | Executar D2 (vínculo) faseado + D1 (grade horária); D8 snapshots; INFRA (replica set/worker) |
| **T3 (6–9m)** | Fundação analítica | Motor de Indicadores + biblioteca canônica (dedup de métricas, D5); modelo dimensional + ETL |
| **T4 (9–12m)** | BI & dashboards | Marts + API de BI; Dashboard Operacional/Executivo; Metas Estratégicas; insight por IA |

## 8. Gate para iniciar a Onda 2
A **Onda 2** (documentação detalhada) deve ser executada **para validar e apoiar
estas decisões** — não apenas gerar mais documentação. Recomenda-se priorizar, na
Onda 2: Dashboards (03), Indicadores (04), Services (09) e BI (21), pois sustentam
diretamente a estratégia de BI aqui definida.

---
### Anexos (audit/000.1/)
1. [Priorização](audit/000.1/01_PRIORIZACAO.md) ·
2. [Mapa de Dependências](audit/000.1/02_MAPA_DEPENDENCIAS.md) ·
3. [Plano de Refatoração](audit/000.1/03_PLANO_REFATORACAO.md) ·
4. [BI Readiness](audit/000.1/04_BI_READINESS.md) ·
5. [Dashboards](audit/000.1/05_DASHBOARDS_DECISAO.md) ·
6. [Indicadores](audit/000.1/06_INDICADORES_DECISAO.md) ·
7. [Plano de BI](audit/000.1/07_PLANO_BI.md)

*Sprint 000.1 concluída em Jun/2026. Nenhum código foi alterado.*
