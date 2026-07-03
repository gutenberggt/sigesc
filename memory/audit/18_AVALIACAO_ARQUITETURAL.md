# ENTREGA 18 — Avaliação Arquitetural

> Auditoria READ-ONLY · Jun/2026. Diagnóstico técnico do estado atual. 🟢🟡🔴⚫.

## 1. Pontos fortes 🟢
- **Isolamento multi-tenant blindado** (fail-closed + auditoria + testes de tenant).
- **Operações destrutivas com governança exemplar:** transferência institucional e
  reconstrução de histórico com **dry-run + idempotência + lock + rollback (janela 7d)
  + recibo verificável (QR)**. Padrão reutilizável `with_critical_mutation`.
- **Segurança de sessão madura:** JWT em cookie HttpOnly, refresh rotativo com
  preservação de tenant, blacklist/revogação, CSRF, rate limit disponível.
- **Offline-first real (PWA):** Service Worker com precache de chunks, Dexie/IndexedDB,
  autosave anti-perda, indicador permanente de status/sincronização — adequado a escolas rurais.
- **Qualidade/CI:** 173 arquivos de teste + gate de regressão bloqueante (`make regression`).
- **Domínio educacional profundo:** regras reais (sábado letivo, consolidação de frequência,
  conceitual×numérico, distorção idade-série, condicionalidade PBF, BNCC, AEE).
- **Documentos oficiais robustos** com verificação pública por QR.

## 2. Pontos fracos / Débitos técnicos 🟡🔴
| # | Débito | Severidade | Evidência |
|---|---|---|---|
| D1 | **Anti-pattern WRITE≠READ na grade horária** (3 coleções: `class_schedules` legado × `teacher_assignments` × `teacher_allocations`) | 🔴 | dual-read/bridges ainda ativos pós-migração |
| D2 | **Vínculo aluno↔turma triplicado** (`enrollments` × `students.class_id` × `class_students`) | 🔴 | fonte de bugs recorrentes (multisseriada, livro de promoção) |
| D3 | **`StudentsComplete.js` > 3.800 linhas** | 🟡 | dívida anotada no PRD (quebrar em IndicadoresPanel/Filtros/Lista) |
| D4 | **`server.py` monolítico** (859 linhas, registra 89 routers) e `models.py` (~3.000 linhas) | 🟡 | dificulta navegação/testes isolados |
| D5 | **Motores de risco potencialmente sobrepostos** (academic/attendance/overall/diagnostic + alert_engine + pmpi_compute) | 🟡 | validar unificação de scoring |
| D6 | **Valores de status legados** fora dos `Literal` Pydantic (`enrollments.status='inactive'`) | 🟡 | causava 500; corrigido com coerção, mas dado não saneado |
| D7 | **RBAC desigual** (~39 routers com checagem manual) | 🟡 | precedente do bug `require_permission(None)` |
| D8 | **Snapshots com múltiplos padrões** (`snapshots`/`diary_snapshots`/`student_snapshots`/`ai_analysis_snapshots`) | 🟡 | estratégia de retenção não unificada |
| D9 | **Coleções/rotas legadas** (`mantenedora` singular, `render_jobs`×`document_render_jobs`, `App_old.js`, `server.py.bak`) | ⚫ | candidatos a remoção controlada |
| D10 | **Rate limiting subutilizado** (1 router) | 🟡 | ampliar em login/refresh/export/PDF |
| D11 | **Arquivos de teste/backup soltos na raiz** (`backend_test.py`, `*.tar.gz`, `fix_*.py`, `verify_*.py`) | 🟡 | poluição de repo |

## 3. Gargalos de performance
- **Livro de Promoção / relatórios por turma:** N+1 de `gradesAPI.getAll` por aluno
  (loop de promessas) — aceitável em turmas pequenas, custoso em turmas grandes.
- **Dashboards analíticos / PME:** agregações que leem várias coleções por request;
  sem cache dedicado além de `pdf_cache`. Candidatos a **materialização** (snapshots/BI).
- **`StudentsComplete.js`:** render de listas grandes (page_size 10.000 em alguns fluxos).
- **PDFs pesados:** já mitigado com jobs assíncronos + polling.

## 4. Escalabilidade
- **Backend stateless** (JWT) → escala horizontal viável atrás do Traefik.
- **MongoDB single-node** (compose Coolify) → ponto único; sem réplica/sharding declarados.
  Recomenda-se **replica set** para produção e políticas de backup automatizadas.
- **Jobs (APScheduler) in-process** → em múltiplas réplicas do backend, risco de execução
  duplicada; considerar lock distribuído (já existe padrão) ou worker dedicado.

## 5. Manutenibilidade
- **Boa modularização por domínio** (routers/services), porém alguns arquivos-monólito (D3/D4).
- **Padrões reutilizáveis fortes** (`with_critical_mutation`, `setup_router`, PDF jobs).
- **Documentação viva** (PRD/changelog extensos) — excelente rastreabilidade histórica.

## 6. Segurança
- 🟢 Multi-tenant fail-closed, cookies HttpOnly, revogação, auditoria de divergências.
- 🟡 Ampliar rate limit e revisar RBAC manual; publicar contrato de API para consumidores externos.
- 🟢 Operações destrutivas com re-auth e frase de confirmação.

## 7. Reutilização / Acoplamento / Coesão / Complexidade
- **Reutilização:** alta em mutações críticas, PDF, tenant scope; **baixa** em componentes
  de UI grandes (a detalhar na Onda 2 — [07](07_COMPONENTES.md)).
- **Acoplamento:** núcleo (`students/classes/enrollments/attendance/grades`) com alto
  raio de impacto — mudanças exigem regressão ampla.
- **Coesão:** boa por módulo; sofrível nos monólitos (D3/D4).
- **Complexidade:** concentrada em grade horária, diário/snapshots, transfer e risco/IA.

## 8. Conclusão executiva
Arquitetura **madura e coesa para o core operacional**, com governança destrutiva
de referência e offline-first real. Os riscos concentram-se em **modelagem duplicada
(grade horária e vínculo aluno↔turma)**, **monólitos de arquivo** e **preparação para BI/escala**
(materialização de indicadores, replica set, unificação de motores de risco). Nenhum
bloqueador crítico aberto; a evolução deve priorizar **consolidação antes de expansão**.
