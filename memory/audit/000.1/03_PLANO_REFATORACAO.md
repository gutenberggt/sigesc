# 000.1 · 3 — Plano de Refatoração

> Decisão por achado: **corrigir · manter · isolar · substituir · unificar** —
> com justificativa técnica. READ-ONLY (nenhuma alteração executada).

## D1 — Grade horária WRITE≠READ → **UNIFICAR**
- **Decisão:** unificar em `teacher_class_assignments` (modelo novo) como fonte única;
  aposentar `class_schedules` (legado) e `teacher_allocations` após período de observação.
- **Justificativa:** a migração já ocorreu em prod (1182/1182 assignments); manter 3
  representações perpetua risco de divergência (dado escrito num lugar e lido de outro).
- **Como:** desligar dual-read por feature-flag → validar painel de integridade → remover
  bridges (`legacy_schedule_bridge`) → drop controlado da coleção legada com backup.
- **Pré-condição:** suíte de regressão de grade/diário/frequência ampliada.

## D2 — Vínculo aluno↔turma triplicado → **UNIFICAR** (fonte única = `enrollments`)
- **Decisão:** eleger `enrollments` como **fonte canônica** do vínculo; `students.class_id`
  e `class_students` passam a ser **derivados/depreciados** (view/campo calculado).
- **Justificativa:** é a raiz de bugs recorrentes (fallback multisseriada, livro de promoção,
  contagem de frequência). Uma fonte única elimina a classe inteira de defeitos.
- **Como (faseado, alto risco):** (1) auditar divergências atuais entre as 3 fontes; (2)
  dual-write com reconciliação; (3) migrar leituras para `enrollments`; (4) depreciar as demais.
- **Pré-condição:** flag + rollback + testes; NÃO iniciar sem aprovação explícita (P0 de decisão, execução Onda B).

## D3 — `StudentsComplete.js` (>3.800 linhas) → **ISOLAR/SUBSTITUIR (decompor)**
- **Decisão:** quebrar em `IndicadoresPanel`, `FiltrosBar`, `ListaAlunos`, `StudentFormModal`.
- **Justificativa:** dívida anotada no PRD; reduz risco de regressão e acelera evolução.
- **Como:** extração incremental sem mudar comportamento (refactor puro + snapshot de UI).

## D4 — `server.py`/`models.py` monólitos → **ISOLAR (modularizar)**
- **Decisão:** agrupar registro de routers por domínio; dividir `models.py` em `models/<dominio>.py`.
- **Justificativa:** testabilidade e navegação; sem mudança de contrato.

## D5 — Motores de risco sobrepostos → **UNIFICAR**
- **Decisão:** um **scoring canônico** (`risk_engine`) com pesos configuráveis por dimensão
  (acadêmico, frequência, geral); `diagnostic_engine`/`alert_engine` consomem esse scoring.
- **Justificativa:** coerência dos indicadores de risco e reutilização; base para SIE/PMPI.

## D6 — Status legados fora do `Literal` → **CORRIGIR (sanear dados)**
- **Decisão:** migração idempotente (`with_critical_mutation`) normalizando valores legados
  (`inactive→cancelled`, etc.); manter `field_validator` de tolerância como rede de segurança.
- **Justificativa:** elimina 500 silenciosos; barato e de baixo risco. **Ação P0 imediata.**

## D7 — RBAC desigual → **CORRIGIR (padronizar)**
- **Decisão:** auditar os ~39 routers sem `require_roles`/`require_permission`; aplicar o
  padrão (RBAC + matriz) e adicionar testes de autorização por router.
- **Justificativa:** fechar superfície de segurança antes de expandir. **P0.**

## D8 — Snapshots múltiplos → **UNIFICAR (estratégia + retenção)**
- **Decisão:** padrão único de snapshot (envelope comum) + política de retenção central;
  `diary`/`student`/`ai` como *tipos* de um mesmo mecanismo.
- **Justificativa:** reduz custo/duplicação e habilita marts de BI.

## D9 — Legados → **SUBSTITUIR/REMOVER (controlado)**
- **Decisão:** confirmar não-uso de `mantenedora` (singular), `App_old.js`, `server.py.bak`,
  e consolidar `render_jobs`×`document_render_jobs`; remover com backup.
- **Justificativa:** higiene; baixo risco após confirmação por análise estática. **P3.**

## D10 — Rate limiting → **CORRIGIR (ampliar)**
- **Decisão:** aplicar `@limiter.limit` em login/refresh/export/PDF. **P1, baixo esforço.**

## D11 / ROUTE — Higiene de repo / nomenclatura → **CORRIGIR (baixa prioridade)**
- **Decisão:** mover artefatos soltos p/ `scripts/`/`archive/`; padronizar rotas gradualmente. **P3.**

## INFRA — Persistência/jobs → **ISOLAR/EVOLUIR**
- **Decisão:** planejar **replica set** MongoDB + backup automatizado; mover APScheduler p/
  worker dedicado com lock distribuído (padrão já existe). **P2.**

## Resumo das decisões
| Decisão | Itens |
|---|---|
| **Corrigir** | D6, D7, D10, D11, ROUTE |
| **Unificar** | D1, D2, D5, D8, NEW-BI (indicadores) |
| **Isolar/Modularizar** | D3, D4, INFRA |
| **Substituir/Remover** | D9 |
| **Manter (sem ação)** | núcleo transfer/rollback, offline-first, auth (já maduros) |
