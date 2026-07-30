# SPRINT 000 — Plano de Refatoração Arquitetural do MIG (Pré-Implementação)

> **Caráter:** exclusivamente de planejamento. **NENHUM código foi implementado ou alterado.**
> **Base:** Sprint −001 (`memory/audit/SPRINT_-001_AUDITORIA_MEC_MIG.md`) + convenções reais do
> backend (`core/`, `business_intelligence/`, padrão `setup_router(db)`).
> **Princípio norteador:** *Reaproveitar sempre que possível, refatorar quando necessário,
> reescrever apenas com justificativa técnica objetiva.*
> **Status:** aguardando **aprovação formal**. Nenhuma implementação inicia antes disso.

---

## 0. Escopo e limites desta refatoração

O objetivo é criar a **Fundação do MIG** (Módulo de Integração Governamental) refatorando o
embrião CMDE existente, **sem alterar comportamento** de endpoints, frontend ou banco. Os
componentes operacionais assíncronos (Queue, Workers, Scheduler, Batch, Event Bus) têm seus
**lugares reservados** na arquitetura, mas sua **implementação** pertence a sprints posteriores
de infraestrutura — não a esta refatoração. Isto respeita a restrição "não implementar novos
endpoints do CMDE" e "não alterar regras de negócio existentes".

---

## 1. Arquitetura Alvo

Modela-se o MIG como um **pacote modular** espelhando o precedente `business_intelligence/`,
com três camadas claramente separadas: **Core (reutilizável)**, **Providers (contrato)** e
**CMDE (específico)**.

### 1.1 Estrutura de diretórios (alvo)
```
backend/
├── routers/
│   └── mec_integration.py        # (MANTIDO) router fino — só orquestra, delega ao CmdeService
├── mig/                          # (NOVO) Módulo de Integração Governamental
│   ├── __init__.py
│   ├── core/                     # Infra REUTILIZÁVEL — agnóstica de provider
│   │   ├── __init__.py
│   │   ├── http_client.py        # BaseGovClient (httpx: timeout, headers, logging, hook retry)
│   │   ├── retry.py              # RetryManager (backoff exponencial) — [estrutura, uso na fundação: opcional]
│   │   ├── audit.py              # MigAuditService — adapta auditoria existente do sistema
│   │   ├── monitoring.py         # MigMonitoring — coleta métricas de execução
│   │   ├── validation.py         # ValidationEngine — regras genéricas por payload
│   │   ├── mapping.py            # MappingEngine (base) — SIGESC ↔ provider
│   │   ├── feature_flags.py      # FeatureFlags — ambiente/on-off/rollout
│   │   └── exceptions.py         # Exceções tipadas (MigError, MigAuthError, MigUpstreamError...)
│   ├── providers/                # Contrato comum de provider governamental
│   │   ├── __init__.py
│   │   └── base.py               # GovProvider (interface: authenticate/query/send/status)
│   └── cmde/                     # ESPECÍFICO do CMDE — particularidades isoladas
│       ├── __init__.py
│       ├── client.py             # CmdeClient(BaseGovClient) — CLIENTE HTTP ÚNICO do CMDE
│       ├── config_repo.py        # CmdeConfigRepository — acesso a db.mec_integration + ambientes
│       ├── dtos.py               # DTOs/Schemas Pydantic (Config, Elegibilidade, MappingRow, Status)
│       ├── mapper.py             # CmdeMapper — aluno/escola → payload CMDE
│       ├── validators.py         # Regras de prontidão CMDE (CPF/NIS/INEP)
│       └── service.py            # CmdeService — orquestra config, elegibilidades, mapping, status
│   # (RESERVADO p/ sprints futuras: mig/core/queue.py, workers.py, scheduler.py, batch.py, events.py)
└── frontend/src/
    ├── services/api.js           # (ADAPTAR) + objeto `mecAPI` (camada única de chamadas)
    └── pages/MECIntegration.js   # (REFATORAR) consumir `mecAPI` em vez de axios direto
```

### 1.2 Responsabilidades por camada
| Camada | Responsabilidade | NÃO pode |
|--------|------------------|----------|
| **Router** (`mec_integration.py`) | Autenticação/permissão, parse de request, chamar `CmdeService`, formatar resposta HTTP | Conter regra de negócio; chamar `httpx` |
| **Service** (`cmde/service.py`) | Orquestrar caso de uso (config, elegibilidades, mapping, status) usando client/mapper/validators/repo | Fazer chamada HTTP direta (usa `CmdeClient`) |
| **Client** (`cmde/client.py` + `core/http_client.py`) | **Única** porta de saída HTTP ao CMDE (timeout, headers, erros tipados, hook de retry/audit) | Conhecer regras de negócio |
| **Config Repo** (`cmde/config_repo.py`) | Ler/gravar `db.mec_integration`; resolver ambiente/URL; proteger chave privada | Expor segredos |
| **Mapper/Validators/DTOs** | Traduzir e validar dados SIGESC↔CMDE | Efeitos colaterais/IO |
| **Core** | Infra reutilizável por qualquer provider futuro | Depender de particularidade CMDE |
| **Providers/base** | Contrato que futuros órgãos implementam | Implementação concreta |

### 1.3 Relacionamento entre componentes (separação exigida)
- **Core de Integração** = `mig/core/*` (reutilizável, agnóstico).
- **Providers** = `mig/providers/base.py` (contrato) → CMDE é a 1ª implementação.
- **Serviços específicos do CMDE** = `mig/cmde/*` (isola tudo que é CMDE).

---

## 2. Inventário das Alterações

| Caminho atual | Situação atual | Ação | Justificativa técnica |
|---------------|----------------|------|-----------------------|
| `backend/routers/mec_integration.py` | Router com regra + httpx inline (232 l.) | **Refatorar** | Manter contrato dos 5 endpoints; extrair regra/HTTP p/ service/client. Router vira fino. |
| `backend/server.py` (l.101,480,568) | Registra `setup_router(db)` + include prefix `/api` | **Manter** | Ponto de montagem estável; `setup_router` passa a instanciar `CmdeService`. |
| `backend/mig/__init__.py` | — | **Criar** | Pacote MIG. |
| `backend/mig/core/http_client.py` | — | **Criar** | `BaseGovClient` (httpx resiliente). |
| `backend/mig/core/exceptions.py` | — | **Criar** | Exceções tipadas do MIG. |
| `backend/mig/core/audit.py` | — | **Criar** | `MigAuditService` (adapta auditoria existente). |
| `backend/mig/core/monitoring.py` | — | **Criar** | Métricas de execução. |
| `backend/mig/core/validation.py` | — | **Criar** | Motor de validação genérico. |
| `backend/mig/core/mapping.py` | — | **Criar** | Motor de mapeamento base. |
| `backend/mig/core/feature_flags.py` | — | **Criar** | Feature flags (ambiente/on-off). |
| `backend/mig/core/retry.py` | — | **Criar (estrutura)** | Contrato de retry; uso pleno em sprint de infra. |
| `backend/mig/providers/base.py` | — | **Criar** | Interface `GovProvider`. |
| `backend/mig/cmde/client.py` | — | **Criar** | Cliente único CMDE. |
| `backend/mig/cmde/config_repo.py` | — | **Criar** | Acesso a `db.mec_integration`. |
| `backend/mig/cmde/dtos.py` | — | **Criar** | DTOs Pydantic. |
| `backend/mig/cmde/mapper.py` | — | **Criar** | Mapper aluno/escola → CMDE. |
| `backend/mig/cmde/validators.py` | — | **Criar** | Regras de prontidão (extraídas de `students/mapping`). |
| `backend/mig/cmde/service.py` | — | **Criar** | Orquestrador dos casos de uso. |
| `backend/tests/test_mig_cmde.py` | — | **Criar** | Cobertura unit + regressão dos 5 endpoints. |
| `frontend/src/services/api.js` | Sem `mecAPI` | **Adaptar** | Adicionar `mecAPI` (aditivo, sem quebra). |
| `frontend/src/pages/MECIntegration.js` | axios direto (415 l.) | **Refatorar** | Trocar axios por `mecAPI`; comportamento idêntico. |
| Campos `pgp_public_key`/`pgp_private_key` em `db.mec_integration` | Armazenados, nunca usados | **Descontinuar (condicional)** | Decisão de aprovação: usar de fato (assinar/criptografar) OU remover. Ver §6. |
| `backend/routers/bolsa_familia.py` + `services/bf_*` (Subsistema B) | Em produção | **Manter** | Fora do escopo; será *consumido* pelo MIG futuramente, não alterado agora. |
| Índices/campos `mec_code/mec_subcode` (currículo — Subsistema C) | Em uso | **Manter** | Não é integração; não tocar. |

---

## 3. Arquivos Novos (detalhe)

| Arquivo | Finalidade | Responsabilidade | Dependências | Impacto esperado |
|---------|-----------|------------------|--------------|------------------|
| `mig/core/http_client.py` | Cliente HTTP base | `BaseGovClient.request()` com timeout/headers/erros tipados/logging + ganchos p/ retry e audit | `httpx`, `core/exceptions`, `core/audit` | Centraliza saída HTTP; nenhum impacto externo |
| `mig/core/exceptions.py` | Erros do MIG | `MigError`, `MigAuthError(401)`, `MigForbidden(403)`, `MigUpstreamError`, `MigTimeout` | — | Padroniza tradução p/ HTTP no router |
| `mig/core/audit.py` | Auditoria de chamadas | Registrar request/response (sem segredos) | infra de auditoria existente / `db` | Rastreabilidade; grava em coleção de log |
| `mig/core/monitoring.py` | Métricas | Contadores latência/sucesso/erro | — | Alimenta Dashboard Técnico (futuro) |
| `mig/core/validation.py` | Validação genérica | Aplicar regras declarativas a payloads | `dtos` | Base p/ prontidão e envio |
| `mig/core/mapping.py` | Mapeamento base | Utilidades de tradução campo↔campo | — | Reuso por múltiplos providers |
| `mig/core/feature_flags.py` | Feature flags | Ler flags (ambiente, on/off, rollout) | `db`/config | Liga/desliga integração com segurança |
| `mig/core/retry.py` | Retry (estrutura) | Contrato `RetryPolicy`/backoff | `core/exceptions` | Uso pleno em sprint de infra |
| `mig/providers/base.py` | Contrato de provider | Interface `GovProvider` (authenticate/query/send/status) | `core` | Habilita múltiplos órgãos |
| `mig/cmde/client.py` | Cliente CMDE único | Compor `BaseGovClient` + auth Bearer + URLs de ambiente | `core/http_client`, `config_repo` | **Única** via HTTP ao CMDE |
| `mig/cmde/config_repo.py` | Repositório de config | CRUD em `db.mec_integration`; nunca expor chave privada | `db` | Isola persistência |
| `mig/cmde/dtos.py` | DTOs Pydantic | `MecConfigDTO`, `ElegibilidadeDTO`, `MappingRowDTO`, `SyncStatusDTO` | `pydantic` | Contratos tipados |
| `mig/cmde/mapper.py` | Mapper CMDE | aluno/escola → payload CMDE | `dtos` | Preparação p/ envio |
| `mig/cmde/validators.py` | Regras de prontidão | CPF/NIS/INEP (migrado de `students/mapping`) | `dtos` | Regra fora do router |
| `mig/cmde/service.py` | Orquestrador | Casos de uso dos 5 endpoints | client, repo, mapper, validators | Coração da refatoração |
| `tests/test_mig_cmde.py` | Testes | Unit (service/mapper/validators) + regressão dos endpoints | pytest, httpx mock | Segurança da refatoração |
| `frontend/src/services/api.js` (adição `mecAPI`) | Camada de API | `getConfig/updateConfig/getStatus/getMapping/consultarElegibilidades` | axios existente | Aditivo |

---

## 4. Arquivos Existentes (o que fica / sai / migra)

### 4.1 `backend/routers/mec_integration.py` — **Refatorar**
- **Permanece:** definição dos 5 endpoints com **mesmos caminhos e contratos**; `require_permission('nav-mec-button', ['super_admin'])`; `setup_router(db)`.
- **Sai (removido do router):** chamadas `httpx` inline; leitura/gravação direta de `db`; montagem manual do mapeamento; dict `MEC_ENVIRONMENTS`; tratamento de erro embutido.
- **Migra para novos componentes:** HTTP → `cmde/client.py`; regra dos casos de uso → `cmde/service.py`; ambientes/config → `cmde/config_repo.py`; mapeamento → `cmde/mapper.py`; prontidão → `cmde/validators.py`; erros → `core/exceptions.py`.

### 4.2 `backend/server.py` — **Manter**
- **Permanece:** `from routers import mec_integration as mec_mod`, `mec_mod.setup_router(db)`, `include_router(prefix="/api")`.
- **Ajuste mínimo interno (dentro de `setup_router`):** instanciar `CmdeService` e injetá-lo nos handlers. Sem mudança na assinatura nem no ponto de montagem.

### 4.3 `frontend/src/pages/MECIntegration.js` — **Refatorar**
- **Permanece:** toda a UI, `data-testid`, estados, fluxo de telas.
- **Sai:** uso direto de `axios` e da constante `API` local.
- **Migra:** chamadas para `mecAPI` de `services/api.js`. Comportamento observável **idêntico**.

### 4.4 `frontend/src/services/api.js` — **Adaptar (aditivo)**
- **Permanece:** tudo existente.
- **Adiciona:** objeto `mecAPI` com os 5 métodos. Nenhuma remoção.

---

## 5. Componentes Reaproveitados (preservação justificada)

| Componente | Reaproveitamento | Como |
|------------|------------------|------|
| `db.mec_integration` (schema/coleção) | 🟩 Inalterado | Modelo adequado; acesso passa a ser via `config_repo`, sem migração de dados |
| `MEC_ENVIRONMENTS` (hmg/prod) | 🟦 Reorganizado | Movido para `config_repo`/`feature_flags`; mesmos valores |
| Lógica de prontidão CPF/NIS/INEP (`students/mapping`) | 🟦 Pequena adaptação | Extraída para `validators.py`, mesma regra |
| Contadores de status (`sync/status`) | 🟦 Pequena adaptação | Movidos para `service.py`; alimentarão o Dashboard Técnico |
| Página `MECIntegration.js` (UX/guia/links) | 🟨 Reorganizado (front) | Mantém UI; só troca a camada de dados |
| Catálogo de motivos MEC v4.2 + motor de frequência (Subsistema B) | 🟩 Inalterado | Em produção; será consumido pelo MIG no futuro, sem alteração agora |
| Permissão `nav-mec-button` / `super_admin` | 🟩 Inalterado | Mantém modelo de acesso |
| Índices curriculares `mec_*` (Subsistema C) | 🟩 Inalterado | Sem relação com integração |

---

## 6. Componentes Reescritos (justificativa objetiva)

| Componente | Por que **adaptar não basta** |
|------------|-------------------------------|
| **Cliente HTTP** (httpx inline → `CmdeClient`/`BaseGovClient`) | O código atual acopla a chamada HTTP ao handler do endpoint, sem ponto único de saída, sem timeout/retry/backoff configuráveis, sem logging/auditoria estruturados e sem erros tipados. Não é adaptável in-place porque a **responsabilidade** (transporte) está no lugar errado (router). Exige extração para camada própria — é reescrita da camada de transporte, preservando a lógica de negócio. |
| **Armazenamento inerte de chave PGP** (decisão na aprovação) | Guardar `pgp_private_key`/`pgp_public_key` sem nenhum uso de assinatura/criptografia é dívida e risco de segurança. Só há duas saídas tecnicamente válidas: (a) **usar de fato** (assinar/criptografar payloads no `CmdeClient`) ou (b) **remover os campos**. Manter como está não é aceitável. **Requer decisão do aprovador.** |

Nenhum outro componente será reescrito — todo o restante é reaproveitado ou refatorado.

---

## 7. Arquitetura de Dependências (fluxo de chamadas)

```
Frontend (MECIntegration.js) ──► services/api.js (mecAPI) ──► /api/mec/*
                                                                   │
                                                                   ▼
                                              routers/mec_integration.py  (FINO)
                                              - auth/permissão
                                              - parse request / format response
                                              - NENHUMA regra, NENHUM httpx
                                                                   │  (chama)
                                                                   ▼
                                                     mig/cmde/service.py (CmdeService)
                     ┌───────────────┬───────────────┬───────────────┬───────────────┐
                     ▼               ▼               ▼               ▼               ▼
              cmde/config_repo   cmde/validators  cmde/mapper    cmde/dtos     cmde/client.py
              (db.mec_integration)  (prontidão)   (SIGESC→CMDE)  (contratos)        │
                     │                                                             ▼
                db.students / db.schools                                  core/http_client (BaseGovClient)
                                                                          + core/retry + core/audit + core/monitoring
                                                                                     │
                                                                                     ▼
                                                                            API CMDE (hmg/prod)
```

**Invariantes garantidas pelo desenho:**
- **Routers não contêm regra de negócio** (só auth + orquestração + formatação).
- **Serviços não fazem HTTP direto** — sempre via `CmdeClient`.
- **Toda comunicação externa passa pelo cliente único** (`core/http_client` → `cmde/client`).

---

## 8. Plano de Execução (ordem que minimiza regressão)

> Cada etapa é **aditiva/refatoração comportamentalmente neutra**; a troca do router para o
> service é a única com potencial de regressão e vem só depois de o service estar testado.

| # | Etapa | Objetivo | Arquivos | Validação |
|---|-------|----------|----------|-----------|
| E1 | **Scaffolding do pacote** | Criar `mig/` + `core/exceptions.py` + `providers/base.py` | novos (sem uso ainda) | Import OK; app sobe; zero impacto |
| E2 | **Core HTTP + Audit/Monitoring/Flags** | `BaseGovClient`, audit, monitoring, feature_flags, retry (estrutura) | `mig/core/*` | Unit tests do client (httpx mock) |
| E3 | **CMDE isolado (sem plugar)** | `config_repo`, `dtos`, `validators`, `mapper`, `client`, `service` | `mig/cmde/*` | Unit tests service/mapper/validators; paridade de saída vs router atual |
| E4 | **Testes de paridade** | Garantir que `CmdeService` reproduz exatamente as respostas atuais | `tests/test_mig_cmde.py` | Comparar payloads endpoint-a-endpoint |
| E5 | **Troca do router** | Router passa a delegar ao `CmdeService`; remover httpx/regra | `routers/mec_integration.py`, `server.py` | Regressão dos 5 endpoints (curl) idêntica ao baseline |
| E6 | **Frontend `mecAPI`** | Adicionar camada `mecAPI` (aditivo) | `services/api.js` | Compila; sem uso ainda |
| E7 | **Refatorar página** | Trocar axios direto por `mecAPI` | `MECIntegration.js` | Screenshot + fluxo idêntico |
| E8 | **Decisão PGP** | Aplicar decisão aprovada (usar ou remover) | `client.py`/`config_repo.py` ou remoção | Teste conforme decisão |

---

## 9. Compatibilidade

| Dimensão | Garantia |
|----------|----------|
| **Endpoints** | Mesmos caminhos (`/api/mec/config`, `/elegibilidades`, `/students/mapping`, `/sync/status`), métodos e formatos de resposta. E4 assegura paridade antes de E5. |
| **Frontend** | UI e `data-testid` preservados; apenas a origem das chamadas muda (E7). |
| **Banco** | `db.mec_integration` **sem migração**; mesmos campos (exceto decisão PGP em E8, isolada). |
| **APIs atuais** | Nenhuma renomeação/remoção; contratos idênticos. |
| **Permissões** | `nav-mec-button`/`super_admin` inalterados. |

**Riscos conhecidos:** (1) divergência sutil de payload no service (mitigado por E4);
(2) decisão PGP com remoção de campos afeta docs já salvos (isolar em E8 + rollback dedicado).

---

## 10. Estratégia de Testes

| Tipo | O que cobre | Ferramenta |
|------|-------------|------------|
| **Unitário** | `CmdeClient` (mock httpx: 200/401/403/timeout/connect), `validators`, `mapper`, `config_repo` | pytest + httpx MockTransport |
| **Integração** | `CmdeService` end-to-end com CMDE mockado | pytest |
| **Paridade/Regressão** | Cada endpoint antes×depois retorna o mesmo shape (baseline capturado em E4) | pytest + snapshots |
| **Endpoints existentes** | `curl` autenticado nos 5 endpoints (via `REACT_APP_BACKEND_URL`) | curl + checagem de status/JSON |
| **Frontend** | Carregar `/admin/mec`, salvar config, "Verificar Dados" — fluxo idêntico | screenshot / testing_agent |

Nenhuma etapa é considerada concluída sem a validação correspondente verde.

---

## 11. Estratégia de Rollback

| Etapa | Como desfazer | Impacto do rollback | Dependências |
|-------|---------------|---------------------|--------------|
| E1–E4 | Remover pacote `mig/` (código não referenciado) | Zero (nada plugado) | Nenhuma |
| E5 (troca do router) | Reverter `mec_integration.py` para a versão que usa httpx inline (git) | Volta ao comportamento atual | `mig/` pode permanecer |
| E6–E7 (frontend) | Reverter `MECIntegration.js`/`api.js` (git); `mecAPI` é aditivo | Página volta ao axios direto | Nenhuma |
| E8 (PGP) | Se remoção: restaurar campos + backfill do doc; se uso: desligar via feature flag | Config PGP; isolado a 1 doc | `config_repo` |

**Garantia:** todas as etapas são reversíveis via `git` (plataforma faz commit por passo) e o
MIG só se torna "ativo no caminho crítico" em E5 — que tem rollback de 1 arquivo.

---

## 12. Matriz de Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|:------------:|:-------:|-----------|
| Regressão de payload ao trocar router→service | Média | Alto | E4 (testes de paridade) obrigatório antes de E5; snapshots do baseline |
| Quebra de compatibilidade de endpoint | Baixa | Alto | Manter caminhos/contratos; regressão via curl |
| Perda de funcionalidade da página | Baixa | Médio | `mecAPI` espelha chamadas atuais; screenshot pós-E7 |
| Duplicação de lógica (regra em 2 lugares) | Média | Médio | E5 remove regra do router no mesmo passo em que service assume; revisão |
| Aumento de acoplamento | Baixa | Médio | Invariantes da §7 (router sem regra, service sem HTTP, client único) |
| Remoção indevida de campos PGP | Baixa | Alto | Decisão explícita do aprovador (§6) + rollback dedicado (E8) |
| Nova dependência injustificada | Baixa | Baixo | Reutilizar `httpx`/`pydantic` já presentes; nenhuma lib nova prevista |

---

## 13. Matriz de Correspondência Atualizada (MIG × Implementação)

| Arquitetura MIG | Equivalente existente | Situação | Ação prevista / Justificativa |
|-----------------|-----------------------|----------|-------------------------------|
| **API Client** | `httpx` inline em `mec_integration.py` | 🟧 | → `mig/cmde/client.py` + `core/http_client.py` (cliente único; transporte na camada correta) |
| **Config/Secrets** | `db.mec_integration` + `MEC_ENVIRONMENTS` | 🟩/🟦 | → `cmde/config_repo.py` (reaproveita schema; reorganiza ambientes) |
| **Validation Engine** | prontidão em `students/mapping` | 🟦 | → `cmde/validators.py` + `core/validation.py` (extrair regra) |
| **Mapping Engine** | montagem aluno→MEC em `students/mapping` | 🟦 | → `cmde/mapper.py` + `core/mapping.py` |
| **Audit Service** | auditoria genérica do sistema (não acoplada) | 🟦 | → `core/audit.py` (adaptar ao padrão MIG) |
| **Monitoring** | contadores de dados em `sync/status` | 🟦 | → `core/monitoring.py` + `cmde/service.py` |
| **Dashboard Técnico** | página "Integração MEC Gestão Presente" | 🟨 | Evoluir; nesta sprint só refatora camada de dados (mecAPI) |
| **Feature Flags** | env hmg/prod | 🟦 | → `core/feature_flags.py` (generalizar) |
| **Retry Manager** | não existe | 🟥 | Criar **estrutura** (`core/retry.py`); uso pleno em sprint de infra |
| **Event Bus** | não existe | 🟥 | Reservado — sprint de infra |
| **Queue Manager** | não existe | 🟥 | Reservado — sprint de infra |
| **Workers** | não existem | 🟥 | Reservado — sprint de infra |
| **Scheduler** | não existe | 🟥 | Reservado — sprint de infra |
| **Batch Builder** | não existe | 🟥 | Reservado — sprint de infra |
| **Provider Contract** | não existe | 🟥 | Criar `providers/base.py` (habilita futuros órgãos) |

---

## 14. Entregáveis (todos contidos neste documento)
Plano de Refatoração ✔ · Arquitetura Alvo (§1) ✔ · Inventário de Arquivos (§2–4) ✔ ·
Plano de Execução (§8) ✔ · Matriz de Correspondência Atualizada (§13) ✔ · Matriz de Riscos (§12) ✔ ·
Plano de Testes (§10) ✔ · Plano de Rollback (§11) ✔. **Nenhuma funcionalidade implementada.**

---

## Critérios de Aceite — Respostas objetivas
1. **Arquitetura final?** Pacote `mig/` (core reutilizável + providers + cmde específico) com router fino — §1.
2. **Arquivos criados?** 15 backend (`mig/**`, `tests/test_mig_cmde.py`) + `mecAPI` — §2/§3.
3. **Arquivos modificados?** `routers/mec_integration.py` (refatorar), `server.py` (ajuste interno mínimo), `MECIntegration.js` (refatorar), `services/api.js` (aditivo) — §2/§4.
4. **Inalterados?** `db.mec_integration` (schema), permissões, Subsistema B (Bolsa Família), Subsistema C (currículo) — §5.
5. **Reaproveitados?** Config/ambientes, prontidão, contadores, UX da página, catálogo v4.2, permissões — §5.
6. **Refatorados?** Router, página, camada de dados do front — §2/§4.
7. **Reescritos e por quê?** Apenas o cliente HTTP (transporte na camada errada) e a decisão sobre PGP inerte (segurança) — §6.
8. **Ordem de implementação?** E1→E8 (scaffolding → core → cmde → paridade → troca do router → mecAPI → página → PGP) — §8.
9. **Compatibilidade garantida como?** Contratos idênticos + testes de paridade antes da troca + banco sem migração — §9.
10. **Rollback?** Reversível por `git` em cada etapa; caminho crítico só em E5 (1 arquivo) — §11.

---

*Fim do Plano de Refatoração (Sprint 000). Documento de planejamento — nenhuma implementação
foi iniciada. Aguardando aprovação formal para autorizar a Sprint de implementação da
Fundação do MIG (Etapas E1–E8).*
