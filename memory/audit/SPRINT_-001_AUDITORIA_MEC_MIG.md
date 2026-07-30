# Sprint −001 — Auditoria Arquitetural de Continuidade da Integração MEC Gestão Presente

> **Caráter:** exclusivamente investigativo e documental. Nenhuma funcionalidade foi
> reescrita, substituída ou removida nesta Sprint.
> **Data:** Jun/2026 · **Base:** evidências diretas do código-fonte e do banco de dados.
> **Autor:** Auditoria arquitetural SIGESC (MIG — Módulo de Integração Governamental).

---

## 0. Descoberta central (leia primeiro)

Ao inspecionar o código, o termo "MEC" no SIGESC corresponde a **três subsistemas distintos**
que precisam ser separados para evitar confusão de escopo:

| # | Subsistema | O que é | Situação |
|---|------------|---------|----------|
| **A** | **Integração MEC Gestão Presente / CMDE** | Página de configuração + cliente HTTP para a API CMDE (elegibilidades, mapeamento de alunos, status). **É o alvo desta auditoria e do MIG.** | Estrutura básica pronta; **NÃO configurada / NÃO em produção** |
| **B** | **Bolsa Família / Busca Ativa (frequência PBF→MEC)** | Catálogo oficial de motivos MEC v4.2, cálculo de frequência mensal, motor de sugestão de motivos, tracking PBF | **Em produção e em uso** (dados reais no banco) |
| **C** | **Códigos MEC do currículo (BNCC)** | Índices `mec_code`/`mec_subcode`/`mec_version` em grupos curriculares | Em uso, **não é integração de API** — fora do escopo do MIG |

O MIG (primeira integração = CMDE) diz respeito ao **subsistema A**. O subsistema B é uma
fonte de dados/valor a ser **reaproveitada** (catálogo de motivos, frequência), não substituída.
O subsistema C não tem relação com o MIG.

---

## Etapa 1 — Localização das Auditorias Existentes

Documentação relevante encontrada em `/app/memory/` e `/app/memory/audit/`:

| Documento | Data | Objetivo / Escopo | Conclusões / Situação |
|-----------|------|-------------------|-----------------------|
| `memory/audit/13_INTEGRACOES.md` | Onda 1/2 | Inventário de integrações externas | **Parcialmente válida.** Lista MongoDB, JWT, Emergent LLM/Claude, Resend, FTP, HMAC, QR/segno. **NÃO menciona CMDE/Gestão Presente** — está incompleta quanto ao MEC. Marcada "PENDENTE — Onda 2". |
| `memory/ARCHITECTURE_BASELINE.md` | Jul/2026 | Baseline arquitetural do backend/frontend | Válida como visão geral; não cobre CMDE. |
| `memory/audit/06_APIS.md`, `11_ROTAS.md`, `09_SERVICES.md` | — | Inventário de APIs/rotas/serviços | Válidas como método; precisam de complemento CMDE (este documento supre). |
| `memory/audit/18_AVALIACAO_ARQUITETURAL.md`, `16_CODIGO_DUPLICADO.md`, `17_CODIGO_OBSOLETO.md` | — | Avaliação/dívida técnica geral | Válidas; não citam CMDE. |
| `memory/audit/000.1/*` (BI) | — | Auditoria de prontidão para BI | Válida para BI; sem relação direta com MEC. |
| `memory/audit/20_ROADMAP.md` | — | Roadmap geral | Válido; MIG não estava previsto explicitamente. |

**Divergência identificada:** nenhuma auditoria anterior catalogou a Integração CMDE
(`mec_integration.py` + `MECIntegration.js`). O doc `13_INTEGRACOES.md` está **desatualizado**
por omissão. **Não há documento de arquitetura do MIG** no repositório — apenas a proposta
descrita nesta Sprint. Esta auditoria passa a ser a fonte única sobre o assunto.

---

## Etapa 2 — Inventário Completo da Implementação Atual

### 2.1 Backend (Subsistema A — CMDE)

| Artefato | Arquivo | Finalidade | Estado | Utilização |
|----------|---------|-----------|--------|------------|
| Router MEC | `backend/routers/mec_integration.py` (232 linhas) | Config + consulta CMDE + mapeamento + status | Funcional (parcial) | Registrado; endpoints ativos |
| Registro do router | `backend/server.py:101,480,568` | `setup_router(db)` + `include_router(prefix="/api")` | OK | Em produção (montado) |
| Cliente HTTP | **inline** `httpx.AsyncClient(timeout=30)` dentro do endpoint `elegibilidades` | Chamada real à API CMDE | Rudimentar | Só em `/mec/elegibilidades` |
| Mapa de ambientes | dict `MEC_ENVIRONMENTS` (hmg/prod) | URLs base CMDE v1 | OK | Usado |
| Autenticação (SIGESC) | `AuthMiddleware.require_permission(db,'nav-mec-button',['super_admin'])` | Restringe a super_admin | OK | Todos os endpoints |
| Autenticação (CMDE) | header `Authorization: Bearer <api_key>` | Auth na API MEC | OK (básico) | `/mec/elegibilidades` |
| Persistência de config | coleção `db.mec_integration` (doc único, upsert) | Guardar env/chaves/responsável | OK | 1 doc esperado |

**Endpoints existentes (todos sob `/api`):**
- `GET  /api/mec/config` — retorna config (oculta chave privada).
- `PUT  /api/mec/config` — grava env, api_key, server_ip, pgp_public_key, pgp_private_key, dados do responsável; define `status`.
- `GET  /api/mec/elegibilidades` — **única chamada externa real** à CMDE (por CPF/NIS, por INEP, ou paginada).
- `GET  /api/mec/students/mapping` — verifica prontidão (CPF/NIS/INEP) dos alunos para envio.
- `GET  /api/mec/sync/status` — contadores agregados (alunos com CPF/NIS, escolas com INEP) + status/último sync.

**NÃO existem no backend CMDE:** service dedicado, DTOs/schemas Pydantic, validadores, mappers,
repositories, middlewares próprios, workers, schedulers, filas, processamento em lote, retentativas,
serviço de auditoria/log específico, monitoramento.

### 2.2 Backend (Subsistema B — Bolsa Família / frequência MEC) — reaproveitável

| Artefato | Arquivo | Finalidade | Estado |
|----------|---------|-----------|--------|
| Router BF | `backend/routers/bolsa_familia.py` (1537 linhas) | Motivos MEC v4.2, frequência mensal, sugestão de motivo, tracking | **Em produção** |
| Serviços BF | `services/bf_network_stats.py`, `bf_reason_suggestion.py`, `bf_legacy_migration.py` | Estatísticas de rede, motor de sugestão, migração legado | Em uso |
| Seed | `seeds/seed_mec_frequency_reasons.py` | Catálogo oficial de grupos/motivos MEC | Executado (25 grupos / 58 motivos no banco) |
| Testes | `tests/test_bf_*.py`, `tests/test_bolsa_familia_*.py` (10+ arquivos) | Cobertura funcional | Presentes |

### 2.3 Frontend

| Artefato | Arquivo | Observações |
|----------|---------|-------------|
| Página CMDE | `frontend/src/pages/MECIntegration.js` (415 linhas) | Rota `/admin/mec` (App.js:126,795). Usa **axios direto** (não usa a camada `services/api.js`). |
| Nav/permissão | permissão `nav-mec-button` | Controla acesso ao menu |
| Página BF | `frontend/src/pages/BolsaFamilia.js` | Subsistema B |
| Dashboard Busca Ativa | `frontend/src/pages/BuscaAtivaDashboard.jsx` | Subsistema B |
| Componentes BF | `components/ReasonCombobox.jsx`, `components/LegacyMigrationDialog.jsx` | Subsistema B |

**Mapa de navegação (CMDE):** `Menu (nav-mec-button)` → `/admin/mec` → `MECIntegration`
→ consome `GET /mec/config`, `GET /mec/sync/status`, `GET /mec/students/mapping`, `PUT /mec/config`.
A página **NÃO** consome `/mec/elegibilidades` (endpoint existe no backend, sem uso no front).

Conteúdo da página: header + status badge · 4 cards de status (alunos ativos, com CPF, com NIS,
escolas com INEP) · guia passo-a-passo (PGP → e-mail MEC → chaves → configurar) · formulário de
config · links Swagger (hmg/prod) · tabela de mapeamento (alunos incompletos, top 50).

### 2.4 Banco de Dados (evidências reais)

| Coleção | Docs | Papel | Suporte à integração |
|---------|------|-------|----------------------|
| `mec_integration` | **0 (config = None)** | Config CMDE (doc único) | Estrutura pronta, **nunca configurada neste ambiente** |
| `attendance_frequency_reason_groups` | **25** | Grupos oficiais MEC v4.2 | Subsistema B — pronto |
| `attendance_frequency_reasons` | **58** | Submotivos MEC v4.2 | Subsistema B — pronto |
| `bolsa_familia_tracking` | **6** | Tracking PBF/Busca Ativa | Subsistema B — em uso |
| `bf_network_stats_snapshots` | 0 | Snapshots de estatística | Subsistema B — vazio |
| `students` / `schools` | — | Campos `cpf`, `nis`, `inep_code` consumidos pelo mapeamento CMDE | Fonte de dados |

Índices `mec_code/mec_subcode/mec_version` (`startup/indexes.py:293-310`) pertencem ao
**currículo (BNCC — Subsistema C)**, não à CMDE. **Não há** coleções de sincronização, lote,
auditoria ou log dedicadas à CMDE.

---

## Etapa 3 — Fluxo Atual (com base no código, não por inferência)

| Capacidade | Existe? | Arquivo responsável / Evidência |
|------------|---------|--------------------------------|
| Autenticação (SIGESC) | ✅ Sim | `mec_integration.py` — `require_permission('nav-mec-button', ['super_admin'])` em todos os endpoints |
| Autenticação (CMDE) | ✅ Básica | Bearer `api_key` em `/mec/elegibilidades` |
| Consulta (query CMDE) | ✅ Sim | `GET /mec/elegibilidades` (httpx real) |
| Sincronização (2 vias) | ⚠️ Parcial | Apenas registra `last_sync` após consulta; não há sync agendado nem 2 vias |
| Envio (push de dados) | ❌ Não | Nenhum endpoint de envio/POST à CMDE |
| Processamento em lote | ❌ Não | Inexistente |
| Consulta de lote | ❌ Não | Inexistente |
| Tratamento de erro | ⚠️ Básico | `mec_integration.py:134-143` (401/403/timeout/connect → HTTPException). Sem retry/backoff |
| Auditoria | ❌ Não (dedicada) | Não há AuditService para CMDE. (Existe auditoria genérica no sistema, não acoplada à CMDE) |
| Logs | ⚠️ Mínimo | `logger = logging.getLogger(__name__)` declarado; poucos usos |
| Monitoramento | ❌ Não | Inexistente |
| Retentativas | ❌ Não | Inexistente |
| Dashboard | ⚠️ Configuração | `MECIntegration.js` — cards de prontidão de dados, sem métricas de integração/execução |
| PGP (assinatura/cripto) | ❌ Não (só armazena) | Chaves PGP são **gravadas** mas **nunca usadas** para assinar/criptografar payloads |

**Resumo:** a implementação atual é um **"cadastro de credenciais + verificador de prontidão de
dados + 1 consulta de elegibilidade"**. Não há ainda o ciclo operacional de integração
(envio, lote, fila, retry, auditoria, monitoramento).

---

## Etapa 4 — Mapa de Dependências

```
                         ┌───────────────────────────────┐
                         │  MECIntegration.js (/admin/mec)│  (axios direto)
                         └───────────────┬───────────────┘
                                         │ /api/mec/*
                         ┌───────────────▼───────────────┐
                         │  routers/mec_integration.py    │
                         │  (require_permission super_adm)│
                         └───┬───────┬───────┬───────┬────┘
                             │       │       │       │
        db.mec_integration ◄─┘       │       │       └─► httpx ─► API CMDE (hmg/prod)
        (config/chaves)              │       │
                                     ▼       ▼
                          db.students     db.schools
                       (cpf,nis,inep_code) (inep_code)
                                     │
              (compartilha fontes com Subsistema B — Bolsa Família)
                                     │
        ┌────────────────────────────┴───────────────────────────────┐
        ▼                                                              ▼
  bolsa_familia.py ──► attendance / attendance_frequency_reasons  bolsa_familia_tracking
  (frequência, motivos MEC v4.2, sugestão)                        (Busca Ativa PBF)
```

**Impacto de futuras alterações (CMDE/MIG):**
- **Alunos** (`students`): fonte primária (cpf, nis, inep_code, birth_date, class_id, school_id). Alta dependência.
- **Escolas** (`schools`): fonte de `inep_code`. Alta dependência.
- **Matrículas/Frequência/Diário**: hoje **não** ligados à CMDE, mas serão a base do envio de
  frequência (ponte natural com o Subsistema B).
- **Profissionais/Usuários/Permissões**: acoplamento via `nav-mec-button`/`super_admin`.
- **Configurações**: `db.mec_integration` isolada — baixo risco de efeito colateral.

Conclusão: alterar o cliente/serviço CMDE tem impacto **baixo** hoje (superfície pequena, sem
consumidores além da própria página). O risco cresce quando o envio de frequência for plugado
ao Subsistema B.

---

## Etapa 5 — Avaliação Arquitetural (matriz de reaproveitamento)

| Componente | Situação | Justificativa técnica |
|------------|----------|-----------------------|
| Persistência de config `db.mec_integration` | 🟩 Reaproveitar | Modelo simples e adequado; só falta versionar e nunca expor chave privada (já protegido) |
| Mapa de ambientes (hmg/prod) | 🟩 Reaproveitar | Correto; migrar para config/feature-flag no MIG |
| `GET /mec/students/mapping` (prontidão de dados) | 🟦 Reaproveitar com ajustes | Ótima base de "Validation/Mapping"; extrair para Validation Engine + Mapping Engine |
| `GET /mec/sync/status` (contadores) | 🟦 Reaproveitar com ajustes | Vira alimentação do Dashboard Técnico do MIG |
| Página `MECIntegration.js` | 🟨 Refatorar | Boa UX (guia/config/links); usar camada `services/api.js`, adicionar métricas de execução e virar Dashboard Técnico |
| Cliente HTTP inline (`httpx` no endpoint) | 🟧 Reescrever | Acoplado ao endpoint; sem retry/timeout configurável/logging estruturado; precisa virar **API Client único** |
| `GET /mec/elegibilidades` (lógica dentro do router) | 🟧 Reescrever | Regra de negócio no router; mover para service + client + mapper |
| Armazenamento de chaves PGP sem uso | 🟧 Reescrever | Guardar chave sem assinar/criptografar é dívida/risco; implementar uso real ou remover campos |
| Catálogo de motivos MEC v4.2 (Subsistema B) | 🟩 Reaproveitar | 25 grupos/58 motivos já seedados e testados; base do envio de frequência |
| Motor de sugestão / frequência (Subsistema B) | 🟩 Reaproveitar | Em produção, testado; será consumido pelo Batch Builder de frequência |
| Índices curriculares `mec_*` (Subsistema C) | 🟩 Reaproveitar (não tocar) | Não é integração; manter como está |

Não há, no CMDE, componentes classificados como 🟥 **Descontinuar** — a superfície é pequena e
tudo é aproveitável com refatoração. O único candidato a remoção é o **armazenamento inerte de
chave PGP** caso o MIG opte por outro modelo de credenciais.

---

## Etapa 6 — Comparação com a Arquitetura MIG (Matriz de Correspondência)

| Arquitetura MIG | Implementação Atual | Situação | Ação Recomendada |
|-----------------|---------------------|----------|------------------|
| **API Client** | `httpx.AsyncClient` inline em `mec_integration.py` (`elegibilidades`) | 🟧 | Extrair para **cliente CMDE único** (`services/mig/cmde_client.py`) com timeout/retry/logging |
| **Event Bus** | Não existe | 🟥 | Implementar (desacoplar produtores/consumidores de eventos de integração) |
| **Queue Manager** | Não existe (sem Redis/fila) | 🟥 | Implementar (fila de jobs de envio/lote); avaliar Redis ou coleção Mongo como fila |
| **Retry Manager** | Não existe | 🟥 | Implementar (backoff exponencial + dead-letter) |
| **Monitoring** | Não existe (apenas contadores de dados) | 🟥 | Implementar métricas de execução (latência, sucesso/erro, filas) |
| **Audit Service** | Não dedicado (sem log de chamadas CMDE) | 🟧 | Adaptar auditoria existente do sistema ao padrão MIG (registrar cada request/response) |
| **Validation Engine** | Parcial: `students/mapping` valida CPF/NIS/INEP | 🟦 | Reaproveitar como base; generalizar regras por payload/versão |
| **Mapping Engine** | Parcial: montagem do dict aluno→MEC em `students/mapping` | 🟦 | Extrair para mapper dedicado SIGESC↔CMDE |
| **Batch Builder** | Não existe | 🟥 | Implementar (montar lotes de elegibilidade/frequência) |
| **Workers** | Não existem | 🟥 | Implementar (consumidores da fila) |
| **Scheduler** | Não existe | 🟥 | Implementar (sync periódico/agendado) |
| **Dashboard Técnico** | Página "Integração MEC Gestão Presente" (`MECIntegration.js`) | 🟨 | Evoluir e incorporar métricas de execução/filas/erros |
| **Feature Flags** | Não existe (só env hmg/prod) | 🟥 | Implementar (ligar/desligar integração, ambientes, gradual rollout) |

**Aderência global ao MIG (subsistema A):** ~**15–20%**. Existe a camada de configuração,
uma consulta funcional, e um embrião de validação/mapeamento. Falta toda a espinha dorsal
operacional (bus, fila, retry, workers, scheduler, monitoramento, feature flags, auditoria dedicada).

---

## Etapa 7 — Débito Técnico

| Item | Tipo | Criticidade | Evidência |
|------|------|-------------|-----------|
| Chaves PGP armazenadas mas nunca usadas p/ assinar/criptografar | Risco de segurança / código inerte | **Alta** | `mec_integration.py:73-75` grava; nenhum uso posterior |
| Cliente HTTP acoplado ao endpoint (sem retry/backoff) | Risco de manutenção/resiliência | **Alta** | `mec_integration.py:113-143` |
| Regra de negócio dentro do router (sem service/DTO/mapper) | Manutenibilidade | Média | `elegibilidades`, `students/mapping` |
| Página usa `axios` direto em vez de `services/api.js` | Inconsistência de padrão | Média | `MECIntegration.js:6-8,40-68` |
| `GET /mec/elegibilidades` existe no backend mas sem consumidor no front | Endpoint órfão/parcial | Média | Nenhuma chamada em `MECIntegration.js` |
| Sem auditoria/log estruturado das chamadas CMDE | Rastreabilidade | Média | `logger` declarado, uso mínimo |
| `13_INTEGRACOES.md` desatualizado (omite CMDE) | Dívida documental | Baixa | Etapa 1 |
| Ausência total de testes para `mec_integration.py` | Cobertura | Média | Nenhum `test_mec_integration*.py` |
| Sem tratamento para config ausente na página (assume defaults) | Robustez | Baixa | Backend já retorna defaults; ok |

**Não há duplicação relevante** entre CMDE (A) e Bolsa Família (B): são responsabilidades
distintas que compartilham fontes (`students`/`schools`) — o que é esperado.

---

## Etapa 8 — Relatório Executivo

### 8.1 Resumo Executivo
- **Estado geral:** a Integração MEC Gestão Presente (CMDE) existe como **cadastro de credenciais
  + verificador de prontidão + 1 consulta de elegibilidade**. **Não está configurada nem em
  produção** (coleção `mec_integration` vazia).
- **Conclusão estimada (vs MIG):** ~**15–20%**.
- **Riscos:** (1) chaves PGP inertes; (2) cliente HTTP sem resiliência; (3) ausência de
  auditoria/monitoramento; (4) endpoint de elegibilidades sem uso.
- **Oportunidades:** (1) reaproveitar validação/mapeamento e o Dashboard existente; (2)
  reaproveitar **integralmente** o catálogo de motivos MEC v4.2 e o motor de frequência do
  Bolsa Família como base do envio de frequência; (3) superfície pequena → refatoração de baixo risco.

### 8.2 Inventário — ver Etapa 2.
### 8.3 Fluxos — ver Etapa 3.
### 8.4 Arquitetura Atual — ver diagrama Etapa 4.
### 8.5 Comparação Atual × MIG — ver Etapa 6.

### 8.6 Recomendações
- **Curto prazo (fundação, baixo risco):**
  1. Extrair **API Client CMDE único** (`services/mig/cmde_client.py`) com timeout/retry/logging; migrar `elegibilidades` para ele.
  2. Introduzir **camada de serviço + DTOs/mappers** e mover regra do router.
  3. Padronizar frontend via `services/api.js` (criar `mecAPI`).
  4. Decidir o destino das chaves PGP (usar de fato ou remover campos).
  5. Adicionar testes de `mec_integration.py`.
- **Médio prazo (operação):**
  6. Implementar **Audit Service** (log de request/response CMDE) e **Monitoring** (métricas).
  7. Implementar **Validation Engine** e **Mapping Engine** a partir de `students/mapping`.
  8. Evoluir a página para **Dashboard Técnico** (execuções, filas, erros).
  9. Implementar **Feature Flags** (ambiente, ligar/desligar, rollout gradual).
- **Longo prazo (escala/assíncrono):**
  10. **Queue Manager + Workers + Scheduler + Retry Manager + Batch Builder** para envio de
      frequência/elegibilidade em lote, consumindo o Subsistema B (motivos/frequência).
  11. **Event Bus** para desacoplar produtores/consumidores.

### 8.7 Plano de Migração para o MIG
| Ação | Itens |
|------|-------|
| **Manter** | `db.mec_integration`; mapa de ambientes; guia/UX da página; catálogo de motivos MEC v4.2 (B); motor de frequência/sugestão (B); índices curriculares (C) |
| **Mover** | Lógica de `elegibilidades` e `students/mapping` → services/client/mapper dedicados; chamadas do frontend → `services/api.js` |
| **Substituir** | `httpx` inline → API Client único com resiliência; tratamento de erro básico → Retry/Audit/Monitoring |
| **Remover** | Campos de chave PGP se o MIG não usar PGP; (avaliar) endpoint `elegibilidades` órfão até haver consumidor |

---

## Critérios de Aceite — Respostas com evidência

1. **O que já existe?** Página `/admin/mec` (`MECIntegration.js`) + router `mec_integration.py` (5 endpoints) + coleção `mec_integration`. Além disso, o Subsistema B (Bolsa Família/frequência MEC) completo.
2. **O que realmente funciona?** Config (GET/PUT), status agregado, mapeamento de prontidão e **1 consulta real** de elegibilidades (`httpx`). Subsistema B funciona em produção.
3. **O que está em produção?** Subsistema B (25 grupos/58 motivos, 6 trackings). **CMDE NÃO** — `mec_integration` está vazia.
4. **O que ainda é apenas estrutura?** Todo o CMDE de envio/lote/fila/retry/auditoria/monitoramento/scheduler/feature-flags (não existe). PGP armazenado é estrutura inerte.
5. **O que pode ser reutilizado?** Config, ambientes, validação/mapeamento, Dashboard (UX), e integralmente o catálogo de motivos + motor de frequência (B).
6. **O que deve ser refatorado?** Cliente HTTP inline, regra no router, frontend com axios direto, Dashboard → Técnico.
7. **O que deve ser descartado?** Armazenamento inerte de PGP (se não usado); endpoint órfão `elegibilidades` até ter consumidor.
8. **Esforço estimado para implantar o MIG?** Fundação (curto prazo) ~1 sprint; operação (médio) ~1–2 sprints; escala assíncrona (longo) ~2–3 sprints. Total estimado **4–6 sprints**.
9. **Impacto da migração?** **Baixo** hoje (superfície pequena, único consumidor é a própria página). Cresce ao plugar o envio de frequência ao Subsistema B — exigirá contrato claro entre A e B.
10. **Primeira Sprint de desenvolvimento pós-auditoria?** **Sprint 001 — Fundação MIG:** API Client CMDE único (timeout/retry/logging) + camada de serviço/DTO/mapper + `mecAPI` no frontend + decisão sobre PGP + testes. É pré-requisito de baixo risco para todo o resto.

---

*Documento gerado como entregável único da Sprint −001. Nenhum código foi modificado.
Contém: Relatório de Auditoria, Inventário, Mapa de Componentes, Mapa de Dependências,
Mapa de Fluxos, Matriz de Reaproveitamento, Débitos Técnicos, Comparativo Atual × MIG,
Matriz de Correspondência e Plano de Migração.*
