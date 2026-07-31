# SPRINT 002.f0 — GAP ANALYSIS: Contrato Oficial CMDE × Arquitetura Atual

> **Natureza:** análise/planejamento apenas. **Nenhum código novo, nenhuma alteração de código,
> nenhum provider oficial, nenhuma chamada ao MEC.**
> **Fontes oficiais consultadas** (jun/2026): documentação Swagger/Redoc do MEC Gestão Presente
> (`api-cmde.gestaopresente.mec.gov.br/v1/documentation`), Cartilha de Uso da API MEC Gestão
> Presente (gov.br), Manual SGP, Manual de Envio dos Dados ao Sistema Presente (Frequência),
> Portaria da Plataforma MEC Gestão Presente.
> **Aviso de fidelidade:** a Cartilha e os PDFs oficiais estão atrás de proteção anti-bot/CAPTCHA
> e a documentação Swagger exige credenciais de adesão (ofício + PGP + IP autorizado). Portanto,
> os **fatos estruturais** abaixo são confirmados pelas fontes oficiais citadas, mas o **schema
> campo-a-campo, enums, códigos de erro, tamanhos máximos e regras exatas de caracteres NÃO puderam
> ser lidos diretamente** e permanecem como **BLOQUEADOR #1** (obter o contrato oficial completo).

---

## 1. Resumo executivo
A arquitetura construída nas Sprints 000–002.e (isolamento Core/Providers/CMDE, fila durável com
máquina de estados, Worker+Retry, Simulador plugável, feature flags, auditoria com correlation_id,
Batch Builder por lotes, idempotência determinística) está **majoritariamente compatível** com o
modelo oficial do CMDE, que é **assíncrono e orientado a lotes**. A camada de orquestração
(fila/worker/scheduler/dashboard) pode ser reutilizada quase integralmente.

Existem, porém, **5 GAPs estruturais de alto impacto** entre nossa implementação de transporte
(hoje só o Simulador é ativo) e o contrato oficial:
1. **Versão/rotas**: usamos `/v1` com envio por item; o oficial usa **`api/v2/lotes`** (assíncrono).
2. **Autenticação**: usamos Bearer estático; o oficial exige **token via rota de auth com validade
   de 5 minutos + auto-renovação**.
3. **Modelo de envio**: hoje síncrono por item; o oficial é **criar lote → consultar status →
   consultar erros** (assíncrono, com recibo/`lote_id`).
4. **PGP**: adesão exige **chave PGP** (assinatura/criptografia) — hoje temos apenas a abstração
   `CryptoProvider` inerte.
5. **Rede/adesão**: **IP autorizado** + ofício de adesão são pré-requisitos operacionais.

**Conclusão:** o **núcleo operacional NÃO precisa ser refeito**. A Sprint 002.f deve concentrar-se
no **Provider Oficial** (transporte v2 + token + lote assíncrono + PGP no Mapper/Serializer) e na
adaptação da reconciliação para o modelo assíncrono. **A implementação real permanece BLOQUEADA**
até a obtenção do contrato oficial completo e das credenciais de adesão.

---

## 2. Fatos oficiais confirmados (estruturais)
| Tópico | Fato oficial (fonte) | Situação |
|---|---|---|
| Base URL | `api-cmde.gestaopresente.mec.gov.br/v1` (prod) e `...hmg...` (homolog) | Confirmado |
| Modelo de envio | **Lotes**: `POST api/v2/lotes`, `GET api/v2/lotes/{lote_id}`, `GET api/v2/lotes/{lote_id}/erros` | Confirmado |
| Autenticação | **Bearer token** obtido em rota de auth; **validade ~5 min**; renovar automaticamente | Confirmado |
| Escopo de dados | Estudantes + **frequências** enviadas | Confirmado |
| Adesão | Ofício + **chave PGP** anexa + IP da máquina + dados do responsável | Confirmado |
| Encoding | Páginas/documentação em **UTF-8** | Parcial (charset), regras de campo pendentes |
| Schema de payload de frequência | Campos/tipos/enums/tamanhos/erros | **NÃO confirmado (BLOQUEADOR)** |
| Rate limits / limites de lote / paginação de erros | Mencionados na cartilha, valores exatos | **NÃO confirmado** |

---

## 3. Comparação item a item (arquitetura atual × contrato oficial)

### 3.1 Transporte (`CmdeClient` + `BaseGovClient`)
- **Atual:** `base_url .../v1`; header `Authorization: Bearer {api_key}` **estático**; `Content-Type
  application/json`; timeout 30s; retry (502/503/504); `X-Correlation-Id` nosso. Métodos GET de
  elegibilidades (herdado). Sem POST de lote de frequência.
- **Oficial:** `api/v2/lotes` (POST assíncrono) + GETs de status/erros; **token dinâmico 5 min**;
  provável exigência de payload **assinado/criptografado com PGP**; possíveis limites de tamanho de
  lote e rate limit (429).
- **Compatível:** transporte HTTP base (httpx), timeout, logging, tradução de erros, correlation id.
- **Incompatível / adaptar:** versão de rota (v1→v2), aquisição/renovação de token, POST de lote,
  polling assíncrono, PGP, tratamento de 429.

### 3.2 Autenticação
- **Atual:** chave estática em `api_key` (config por tenant). 401 → `MigAuthError` (definitivo,
  **não** retenta).
- **Oficial:** token de curta duração (5 min) → precisa de **TokenProvider** que autentica, cacheia
  e renova; 401 em token expirado deve **renovar e retentar** (não é falha definitiva).
- **GAP:** ausência de gestão de token; classificação de 401 como definitivo conflita com expiração.

### 3.3 Payload / DTOs (`FrequencyItemDTO`, `CmdeFrequencyPayloadDTO`)
- **Atual:** `FrequencyItemDTO(student_id, cpf, nis, inep_aluno, school_inep, competencia,
  dias_letivos, faltas_validas, frequencia_percentual, situacao)`; competência `AAAA-MM`.
  `CmdeFrequencyPayloadDTO` é **placeholder** (correlation_id, tenant, competencia, school_inep,
  items[]).
- **Oficial:** schema exato **NÃO confirmado**. Sinais das fontes: identificadores CPF/NIS + INEP
  (aluno e escola), competência `AAAA-MM`, medidas de frequência por competência. Estrutura de lote
  = array de registros.
- **GAP:** o payload real (nomes de campos, se usa total de aulas × presenças ou faltas, obrigatoriedade
  exata de CPF vs NIS vs INEP, enums de situação, tamanhos) **precisa ser confirmado**. Nosso modelo
  cobre os dados-fonte necessários; a tradução final é responsabilidade do **Mapper/Serializer**.

### 3.4 Mapper (`CmdeMapper` / futuro `FrequencyMapper`)
- **Atual:** `CmdeMapper.build_mapping_row` (elegibilidades). O Batch Builder produz `payload_snapshot`
  a partir do SSoT. Não há serializer para o payload oficial de lote.
- **Oficial:** exige serialização para o schema v2 + eventual **normalização de caracteres**
  (caixa alta/acentos/cedilha/til/tamanho) e **assinatura PGP**.
- **GAP:** criar `FrequencyMapper` (SIGESC→schema oficial) e um `Serializer` que aplica normalização
  **exclusivamente aqui** — o SSoT (`students`, `schools`, `attendance`) **nunca** é alterado.

### 3.5 FrequencyBatch
- **Atual:** `FrequencyBatch{competencia, scope, status(draft/ready/processing/completed/partial/
  failed), totals, correlation_id}`; itens agrupados por `batch_size`.
- **Oficial:** o **lote** é a unidade oficial (`lote_id` retornado). Nosso conceito de batch **mapeia
  diretamente** ao lote oficial.
- **Compatível (forte):** precisamos apenas **persistir o `lote_id`/protocolo oficial** no batch e
  passar a consultar status/erros por ele.

### 3.6 SendReceipt
- **Atual:** `{queue_item_id, batch_id, correlation_id, mec_protocol, http_status, accepted,
  rejection_code, rejection_reason, raw_response_hash, received_at}`.
- **Oficial:** recibo por **lote** (`lote_id`/protocolo) + erros por registro via
  `GET /lotes/{id}/erros`; possíveis `transaction_id`/`request_id`/correlation retornado pelo MEC.
- **GAP:** adicionar campos `mec_lote_id`, `mec_transaction_id`, `mec_request_id`,
  `mec_correlation_id` e timestamps de submissão/consulta. Estrutura de recibo por item permanece
  válida (preenchida a partir do endpoint de erros do lote).

### 3.7 CmdeFrequencyPort / FrequencySimulator / Worker
- **Atual:** `enviar_frequencia(payload) -> CmdeFrequencyResponseDTO` **síncrono** (resposta com
  itens aceitos/rejeitados imediatamente). Worker processa **1 item por vez**.
- **Oficial:** **assíncrono** — `POST lote` retorna `lote_id` (aceite de recebimento) e o resultado
  por registro vem depois em `GET /lotes/{id}/erros`.
- **GAP (arquitetural):** a porta precisa evoluir para 2 operações: `enviar_lote(payload)->{lote_id}`
  e `consultar_resultado(lote_id)->itens`. O Worker/Reconciliação passam a: submeter lote → estado
  intermediário (aguardando processamento) → polling → reconciliar por registro.
  **O Simulador já cobre os cenários (aceite/rejeição/erro/timeout/invalid)** e pode ganhar um modo
  assíncrono facilmente (retornar lote_id + resultado em 2 chamadas).

### 3.8 Retry (`RetryPolicy` / `CMDE_DEFAULT`)
- **Atual:** recuperáveis = 502/503/504; definitivos = 400/401/403; backoff exponencial;
  `max_attempts=3`; idempotência por `idempotency_key`.
- **Oficial:** manter recuperáveis 5xx/timeout; **adicionar 429 (rate limit)** como recuperável com
  backoff; **401 por token expirado** deve disparar **renovação de token + retry** (não definitivo);
  respeitar limites de lote/rate. Idempotência de lote deve usar chave por (tenant, competência,
  escopo, versão) — já temos `compute_idempotency_key`.
- **GAP:** tratar 429; reclassificar 401-expiração; confirmar limites oficiais.

### 3.9 Auditoria
- **Atual:** eventos com `correlation_id` (nosso), operation, status, records_*, http_status,
  attempts, duration, actor, tenant, environment.
- **Oficial (a registrar):** **protocolo/`lote_id` oficial**, `transaction_id`, `request_id`,
  **correlation id retornado pelo MEC**, hashes de payload/recibo, timestamps de submissão e de
  consulta de status.
- **GAP:** adicionar esses campos ao evento de auditoria (aditivo, sem quebrar schema atual).

---

## 4. GAPs consolidados, impacto e ação
| # | GAP | Impacto | Ação necessária | Bloqueia 002.f? |
|---|---|---|---|---|
| G1 | Rota v1 (por item) × **v2/lotes** (assíncrono) | Alto | Provider Oficial v2 + fluxo lote/polling | Sim (precisa contrato) |
| G2 | Bearer estático × **token 5 min + refresh** | Alto | `CmdeTokenProvider` (auth/cache/refresh) no transporte | Sim |
| G3 | Envio síncrono por item × **lote assíncrono** | Alto | Evoluir `CmdeFrequencyPort` (enviar_lote + consultar_resultado); adaptar Worker/Reconciliação | Sim |
| G4 | **PGP** exigido | Alto | Implementar assinatura/criptografia no `Serializer` (Mapper), via `CryptoProvider` | Sim (chave PGP + contrato) |
| G5 | Schema de payload/erros/limites/normalização **não confirmado** | Alto | Obter Swagger/cartilha oficiais; definir `FrequencyMapper` + normalização | **Sim (BLOQUEADOR #1)** |
| G6 | 401-expiração tratado como definitivo; **429** ausente | Médio | Ajustar `RetryPolicy`/transporte (refresh+retry; 429 recuperável) | Não (ajuste localizado) |
| G7 | Auditoria sem ids oficiais (lote/transaction/request/correlation MEC) | Médio | Campos aditivos no evento de auditoria | Não |
| G8 | Recibo por lote (`lote_id`) + erros por registro | Médio | Campos aditivos no `SendReceipt`; reconciliação por endpoint de erros | Não |
| G9 | IP autorizado + adesão (ofício/PGP) | Operacional | Processo administrativo com o MEC | Sim (externo) |

---

## 5. O que NÃO precisa mudar (compatível — reduz escopo da 002.f)
- **Isolamento arquitetural** Core/Providers/CMDE e router fino: adequado.
- **Fila durável** (`MongoFrequencyQueue`) + máquina de estados + lease/requeue/backpressure/
  dead-letter: reutilizável integralmente (o modelo assíncrono encaixa em RESERVED→PROCESSING→
  aguardando resultado→SUCCESS/FAILED).
- **Scheduler** (flags/janela/lock/auditoria) e **Dashboard** (métricas/flags/preview/dead-letters):
  reutilizáveis sem mudança estrutural.
- **Batch Builder** (SSoT read-only, dry-run, prontidão, idempotência): o conceito de batch já
  corresponde ao lote oficial.
- **Simulador CMDE**: permanece como provider de homologação; ganha apenas um **modo assíncrono**
  (retornar `lote_id` + resultado em 2 chamadas) para espelhar o oficial.
- **Idempotência determinística** (`compute_idempotency_key`) e **correlation_id ponta a ponta**:
  adequados; alinham com idempotência de lote.
- **SSoT**: permanece **intocado** — nenhuma exigência do MEC pode alterar dados originais.

---

## 6. Bloqueadores
1. **[#1] Contrato oficial completo** (Swagger/cartilha): schema de payload de frequência, enums,
   códigos de erro, tamanhos máximos, limites de lote/rate, formato de recibo. *Sem isto, o
   `FrequencyMapper`/`Serializer` e o Provider v2 não podem ser finalizados.*
2. **Regras oficiais de normalização de caracteres** (UTF-8/ASCII, caixa alta, acentos, til,
   cedilha, comprimento) — **normalização SOMENTE no Mapper/Serializer; SSoT nunca alterado.**
3. **Chave PGP + credenciais de adesão** (ofício, IP autorizado, ambiente de homologação).
4. **Unidade de apuração aceita pelo MEC** (consolidação por dia ≥50%/dia vs. carga horária).
5. **Limiares 60%/75%** — apenas para relatório, nunca para bloquear envio.

## 7. Riscos
- **Retrabalho no Mapper** se o schema oficial divergir do payload placeholder — mitigado por manter
  o mapper isolado e o SSoT como fonte.
- **Token de 5 min** sob carga: risco de expiração no meio de um lote longo — mitigar com refresh
  proativo e retry idempotente.
- **PGP**: complexidade de gestão/rotação de chaves; risco de vazamento — manter chaves em secret
  store, nunca no código/SSoT.
- **Rate limit/limite de lote**: risco de rejeição em massa — respeitar limites via backpressure
  (já existe) e tamanho de lote configurável (já existe `batch_size`).
- **Assíncrono**: itens podem ficar "aguardando resultado" — a máquina de estados precisa de um
  estado/tempo de polling; risco de itens presos → mitigado por lease/requeue e dead-letter.
- **Normalização acidental do SSoT**: risco alto de conformidade — mitigado pela regra dura
  "normalizar só no serializer".

## 8. Plano de adaptação (para a 002.f, após destravar os bloqueadores)
1. Obter contrato oficial + credenciais de adesão (PGP, IP, homologação). **(externo)**
2. `CmdeTokenProvider` (auth 5 min + cache + refresh) no transporte; ajustar retry (401-refresh, 429).
3. Evoluir `CmdeFrequencyPort` para modelo assíncrono (`enviar_lote` + `consultar_resultado`) e
   espelhar no Simulador (modo assíncrono).
4. `FrequencyMapper` (SIGESC→schema oficial) + `Serializer` com normalização de caracteres e
   assinatura/criptografia PGP — **sem tocar o SSoT**.
5. Campos aditivos: `SendReceipt` (`mec_lote_id`, `transaction_id`, `request_id`, `mec_correlation_id`)
   e auditoria (mesmos + hashes/timestamps).
6. Adaptar Worker/Reconciliação ao ciclo submeter-lote → polling status/erros → reconciliar.
7. Feature flag `cmde.frequency.simulator` seleciona Simulador × Provider Oficial (rollout gradual).
8. Homologação com Simulador → homologação MEC (IP/PGP) → dry-run em produção → piloto por tenant →
   rollout (com gate humano).

## 9. Recomendação técnica — Provider Oficial
- Implementar `CmdeFrequencyClient` (transporte v2 assíncrono) **herdando `BaseGovClient`**,
  compondo `CmdeTokenProvider` e o `Serializer`(PGP). Ele implementa o **mesmo `CmdeFrequencyPort`**
  do Simulador, garantindo troca por feature flag sem alterar Worker/Queue/Scheduler.
- Manter o **Simulador como default** até a homologação MEC concluída; o Provider Oficial entra
  atrás de flag, por tenant.
- **Não iniciar a 002.f de implementação** enquanto os Bloqueadores #1–#3 não forem resolvidos.

## 10. Veredito de escopo da 002.f
- **Reutilizável sem mudança:** Queue, Worker (orquestração), Scheduler, Dashboard, Batch Builder,
  idempotência, correlation_id, feature flags, auditoria/métricas base.
- **A construir na 002.f (transporte/serialização):** TokenProvider, Provider Oficial v2 (lote
  assíncrono), FrequencyMapper+Serializer(PGP), ajustes de retry (401-refresh/429), campos aditivos
  de recibo/auditoria, modo assíncrono do Simulador, adaptação da reconciliação.
- **Evidência:** a arquitetura 000–002.e **atende à orquestração** do modelo oficial; os GAPs
  concentram-se **exclusivamente na camada de transporte/serialização** e em **pré-requisitos
  externos (contrato/PGP/adesão)** — o que **reduz o escopo da 002.f** ao Provider Oficial.
