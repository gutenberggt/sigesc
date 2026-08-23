# AEE V2 — Fase 6.6: Escopo Arquitetural de Coerência Operacional da Fonte Efetiva

**Data-base:** 2026-08-23  
**Status:** PROPOSTA ARQUITETURAL — SEM IMPLEMENTAÇÃO  
**Pré-requisito:** Fase 6.5B homologada e encerrada em produção  
**Marco anterior:** `memory/audit/AEE_V2_FASE6_5B_HOMOLOGACAO_PRODUCAO_2026-08-23.md`

## 1. Objetivo deste documento

Definir formalmente a próxima fase do AEE V2 antes de qualquer alteração de código, conforme o gate estabelecido no encerramento da Fase 6.5B.

A Fase 6.6 recebe o nome:

> **Coerência Operacional da Fonte Efetiva do Plano AEE**

Seu objetivo é eliminar a coexistência ambígua de duas autoridades operacionais para o mesmo Plano AEE depois que um Dossiê V2 é inicializado ou ativado.

A Fase 6.6 **não migra dados**, **não regrava snapshots existentes** e **não elimina o legado**. Ela organiza leitura, apresentação e governança de mutações para que o conceito de **Fonte Efetiva**, já homologado nas Fases 6.1–6.5, seja coerente também nas superfícies de listagem, visualização e ações do Plano.

Este documento não autoriza implementação automática. Cada subfase definida abaixo deverá ser implementada em PR próprio, passar pelos gates e receber homologação operacional antes do avanço seguinte.

---

## 2. Evidência do GAP atual

A arquitetura já possui uma Fonte Efetiva canônica:

- sem `active_snapshot_id`, a fonte oficial continua sendo a projeção do Plano legado;
- com `active_snapshot_id` íntegro, a fonte oficial passa a ser `sidecar_active`;
- ponteiro ativo quebrado/corrompido é erro de integridade e não produz fallback silencioso.

Esse contrato já alimenta:

- agenda do Diário AEE;
- agenda do PDF do Diário AEE;
- leitura individual aditiva do Plano AEE;
- PDF individual do Plano AEE.

A Fase 6.5B homologou em produção um caso real em que:

- Plano legado: `status = rascunho`;
- snapshot V2 vigente: `lifecycle.status = active`;
- Fonte Efetiva: `sidecar_active`;
- projeção para o contrato do PDF: `status = ativo`;
- documento final: `Situação do Plano: Vigente`.

Entretanto, `GET /aee/planos` ainda consulta e devolve diretamente `planos_aee`, e o frontend usa `plano.status` da listagem para renderizar a situação. Assim, o mesmo Plano pode ter a Fonte Efetiva oficialmente Vigente e continuar sendo apresentado como `Em elaboração` na listagem tradicional.

O modal tradicional de visualização também recebe diretamente o objeto da listagem, sem buscar a Fonte Efetiva individual antes de exibir os campos.

Há ainda um risco maior: a interface tradicional mantém o fluxo `PUT /aee/planos/{plano_id}` e a duplicação `POST /aee/planos/{plano_id}/duplicate`. O P0 atual protege autoria e hard delete, mas a atualização tradicional continua delegando ao update do documento `planos_aee`. Portanto, depois de criado um head V2, ainda é possível manter duas trilhas de edição que não se sincronizam automaticamente.

Esse estado é um **split-brain operacional**:

1. o legado permanece âncora histórica;
2. o Dossiê V2 pode ser a Fonte Efetiva;
3. algumas telas usam o legado;
4. PDF/Diário podem usar o V2;
5. o formulário legado ainda pode modificar a âncora;
6. a duplicação legado pode copiar conteúdo anterior à versão efetiva.

A Fase 6.6 existe para encerrar essa ambiguidade sem fazer migração destrutiva.

---

## 3. Decisão arquitetural principal

### 3.1 `planos_aee` permanece âncora histórica

O documento legado continua existindo e mantém seu `id` como `legacy_plano_id` da cadeia V2.

Nenhum registro legado será apagado, substituído em massa ou sincronizado de volta automaticamente a partir do sidecar.

### 3.2 Um Plano com `head` V2 passa a ser administrado pelo Dossiê V2

A criação de `aee_dossier_v2_heads` representa a transição de governança do Plano para o fluxo versionado.

A partir desse momento:

- o legado continua servindo como âncora e, enquanto não houver versão ativa, pode continuar sendo a **Fonte Efetiva oficial** conforme a regra 6.1A;
- porém o legado deixa de ser um segundo editor concorrente do conteúdo pedagógico;
- alterações do conteúdo versionado devem ocorrer pelo Dossiê V2;
- qualquer exceção administrativa futura deverá ter fluxo explícito, auditável e separado — nunca um PUT legado silencioso.

### 3.3 Não haverá dual-write

A Fase 6.6 **não** criará sincronização automática V2 → legado nem legado → V2.

Dual-write seria estruturalmente frágil porque exigiria manter dois modelos com semânticas diferentes em consistência transacional permanente.

A estratégia aprovada é:

> **uma Fonte Efetiva + uma âncora histórica preservada.**

---

## 4. Superfícies funcionais da Fase 6.6

Entram no escopo:

1. `GET /aee/planos` — listagem e filtros;
2. visualização tradicional do Plano na aba Planos;
3. status e resumo de agenda exibidos na listagem;
4. ação tradicional de Editar Plano;
5. ação de Duplicar Plano;
6. indicação visual de que o Plano é gerenciado pelo Dossiê V2;
7. governança de `PUT /aee/planos/{plano_id}` quando existe head V2;
8. governança de `POST /aee/planos/{plano_id}/duplicate` quando existe head V2;
9. observabilidade e auditoria das decisões de Fonte Efetiva nessas superfícies.

Continuam preservados:

- criação de novo Plano legado quando ainda não existe Dossiê V2;
- criação a partir de modelo para um novo Plano;
- resolver central 6.1A;
- Dossiê V2 e snapshots imutáveis;
- Diário e PDFs já homologados;
- delete guard 6.0A;
- regras de autorização atuais, salvo bloqueios adicionais de integridade definidos nesta fase.

---

## 5. Contrato de governança por estado

A Fase 6.6 deve distinguir quatro estados operacionais.

### Estado A — Plano sem head V2

- `v2_managed = false`;
- Fonte Efetiva: `legacy`;
- listagem permanece compatível com o legado;
- edição tradicional continua permitida conforme RBAC atual;
- duplicação tradicional continua permitida conforme regras atuais;
- inicialização do Dossiê V2 permanece ação explícita.

### Estado B — Head V2 com versão em trabalho, sem snapshot ativo

- `v2_managed = true`;
- Fonte Efetiva oficial ainda é `legacy`, conforme 6.1A;
- a listagem deve deixar claro que há Dossiê V2 em elaboração/revisão;
- conteúdo oficial exibido pode continuar refletindo o legado até a ativação;
- **edição tradicional do Plano deve ser bloqueada**, porque o Plano já possui cadeia versionada;
- o usuário deve editar pelo Dossiê V2;
- duplicação legado do Plano deve ser bloqueada até existir duplicação V2-aware.

### Estado C — Head V2 com `active_snapshot_id` íntegro

- `v2_managed = true`;
- Fonte Efetiva: `sidecar_active`;
- status/resumo operacional da listagem devem refletir o snapshot vigente;
- versão/revisão vigente devem ser identificáveis;
- edição tradicional deve ser bloqueada;
- ação primária de edição deve abrir o Dossiê V2;
- duplicação legado deve ser bloqueada;
- PDF/Diário continuam usando as regras já homologadas.

### Estado D — Head/snapshot com falha de integridade

- `v2_managed = true`;
- `effective_source = null`;
- `effective_error` obrigatório;
- nenhum fallback silencioso deve afirmar que o legado voltou a ser a Fonte Efetiva;
- leitura legado pode ser preservada apenas como referência de continuidade visual;
- ações mutáveis devem ficar bloqueadas até resolução da integridade;
- evento operacional deve ser registrado em nível visível na produção.

---

## 6. Read model canônico da listagem

A listagem não deve carregar o Dossiê inteiro para cada linha. Deve receber um resumo operacional aditivo e estável.

Contrato proposto:

```text
v2_managed: bool

effective_source:
  legacy | sidecar_active | null

effective_version:
  active_snapshot_id
  document_version
  revision
  working_snapshot_id (quando aplicável)

effective_summary:
  lifecycle_status
  legacy_compatible_status
  schedule_summary

effective_error:
  code
  message

mutation_policy:
  legacy_allowed
  dossier_v2_required
  blocked_integrity
```

`effective_summary` deve conter somente o necessário para a listagem e decisões de UX. Não deve replicar todo `AEEDossierV2`.

### 6.1 Status compatível

Para `sidecar_active`, o lifecycle V2 deve ser projetado para o vocabulário já consumido pela tela:

- `active` → `ativo` → **Vigente**;
- demais estados devem seguir mapeamento canônico já adotado no módulo.

O valor legado original deve continuar acessível para diagnóstico/rollback lógico, sem ser confundido com a situação efetiva.

### 6.2 Agenda resumida

A listagem deve usar somente campos de agenda que ela efetivamente representa.

Se o resumo atual da tela não for capaz de representar sem perda uma agenda V2 heterogênea, a UI não deve inventar um único horário. Deve apresentar um resumo neutro, por exemplo quantidade de sessões/dias, ou encaminhar o usuário ao Dossiê.

A regra é a mesma já consolidada nos PDFs: **nunca achatar informação com perda silenciosa**.

---

## 7. Filtros, total e paginação

A implementação não poderá continuar aplicando `status_filter` apenas sobre `planos_aee.status` quando houver Planos V2 ativos.

Exemplo que deve ser tratado corretamente:

- legado: `rascunho`;
- V2 ativo: `active` → `ativo`;
- filtro solicitado: `ativo`.

Esse Plano deve pertencer ao resultado efetivo, mesmo que a consulta Mongo legado isolada não o encontrasse por `status=ativo`.

Portanto:

1. filtros de identidade/escopo continuam sendo aplicados com segurança (`school_id`, `student_id`, `academic_year`, professor/RBAC);
2. a camada V2 resolve o resumo efetivo dos candidatos;
3. `status_filter` passa a ser avaliado sobre o status efetivo;
4. `total` deve refletir o conjunto após a regra efetiva;
5. paginação deve ser aplicada de modo consistente com esse total.

### 7.1 Proibição de N+1 introduzido pela Fase 6.6

A nova camada não deve executar uma consulta de head e uma consulta de snapshot para cada linha.

Deve existir resolução em lote, com quantidade de round-trips Mongo limitada independentemente da quantidade de itens da página/candidato:

- consulta dos heads dos `legacy_plano_id` relevantes;
- consulta dos snapshots ativos/working necessários;
- validação de integridade equivalente ao resolver canônico;
- montagem dos summaries em memória.

A otimização existente ou não existente do enriquecimento de estudantes fica fora desta fase; a 6.6 apenas não pode acrescentar novo N+1 de Fonte Efetiva.

---

## 8. Governança das mutações legado

### 8.1 `PUT /aee/planos/{plano_id}`

Quando não existe head V2, comportamento atual preservado.

Quando existe head V2, o PUT legado deve falhar fechado com `409 Conflict` e código funcional estável, por exemplo:

```text
AEE_V2_LEGACY_PLAN_WRITE_BLOCKED
```

Mensagem esperada em linguagem humana:

> Este Plano é gerenciado pelo Dossiê AEE V2. Faça a alteração no Dossiê para preservar o histórico e o versionamento.

Não haverá tentativa de replicar o PUT no sidecar.

### 8.2 `POST /aee/planos/{plano_id}/duplicate`

Quando o Plano não possui head V2, comportamento atual preservado.

Quando existe head V2, a duplicação legado deve ser bloqueada nesta fase.

Justificativa: duplicar diretamente `planos_aee` pode copiar uma versão anterior ao conteúdo efetivo vigente.

Uma futura duplicação V2-aware deverá ter contrato próprio e decidir explicitamente quais seções pedagógicas podem ser copiadas para outro estudante ou período.

### 8.3 `DELETE /aee/planos/{plano_id}`

A Fase 6.0A já protege Planos com head V2.

A 6.6 não cria um segundo delete guard. Apenas alinha a interface para que o usuário não receba uma ação enganosa quando a exclusão já é proibida pelo backend.

### 8.4 Criação de Plano e criação por modelo

Continuam permitidas para novos Planos, conforme regras atuais.

A criação do Plano legado continua sendo a criação da âncora inicial. A transição para governança V2 continua ocorrendo somente após bootstrap explícito do Dossiê.

---

## 9. Comportamento de interface

A UI deve refletir o estado real sem remover o acesso ao histórico.

### Plano sem V2

- mantém ações atuais;
- mantém Editar Plano;
- mantém Duplicar conforme regras atuais;
- oferece Inicializar/Abrir Dossiê V2 conforme comportamento existente.

### Plano gerenciado por V2

- badge ou indicação legível de **Dossiê V2**;
- status exibido a partir da Fonte Efetiva quando houver snapshot ativo;
- versão/revisão podem ser exibidas de forma compacta;
- **Editar** deve conduzir ao Dossiê V2, e não ao `PlanoAEEModal` legado;
- Visualizar deve usar o read model efetivo, não o objeto legado cru da lista;
- Duplicar deve ficar indisponível com explicação enquanto não existir duplicação V2-aware;
- Excluir deve refletir a indisponibilidade já garantida pelo delete guard.

### Falha de integridade

- apresentar aviso claro;
- não mascarar o problema como simples retorno ao legado;
- bloquear ações de escrita;
- preservar acesso de leitura suficiente para suporte/auditoria.

---

## 10. Estratégia de execução em subfases

A Fase 6.6 deve ser executada incrementalmente.

### Fase 6.6A — Listagem em Shadow Mode

**Natureza:** read-only.

Objetivos:

- construir resolver batch de summaries;
- comparar lista legado × Fonte Efetiva;
- medir divergências de status e agenda;
- detectar heads working, sidecar ativos e erros de integridade;
- registrar diagnóstico sem alterar resposta HTTP ou frontend.

Evento sugerido:

```text
AEE_V2_PLAN_LIST_SHADOW
```

Nenhuma mutação é autorizada nesta subfase.

### Fase 6.6B — Contrato aditivo da listagem

Objetivos:

- adicionar `v2_managed`, `effective_source`, `effective_version`, `effective_summary`, `effective_error` e `mutation_policy`;
- preservar integralmente os campos legado atuais;
- frontend ainda pode continuar usando o legado até homologação do contrato;
- validar filtros/paginação efetivos em testes antes do cutover visual.

### Fase 6.6C — Cutover controlado da leitura/UX

Objetivos:

- listagem passa a exibir status/resumo da Fonte Efetiva;
- visualização deixa de usar o objeto legado cru;
- `status_filter`, total e paginação passam a obedecer à situação efetiva;
- campos legado necessários para rollback lógico permanecem disponíveis;
- homologação real deve usar pelo menos um caso `sidecar_active` conhecido.

Evento sugerido:

```text
AEE_V2_PLAN_LIST_EFFECTIVE
```

### Fase 6.6D — Governança de escrita

Objetivos:

- bloquear PUT legado quando existe head V2;
- bloquear duplicação legado quando existe head V2;
- alinhar botões/ações do frontend à política do backend;
- manter criação de novas âncoras legado sem alteração;
- preservar delete guard 6.0A.

Evento sugerido para tentativa bloqueada:

```text
AEE_V2_LEGACY_PLAN_WRITE_BLOCKED
```

Cada subfase exige PR próprio, gates verdes e autorização explícita para merge/deploy.

---

## 11. Invariantes obrigatórias

Nenhuma implementação da 6.6 poderá violar:

1. nenhum `updateMany`/migração em massa de `planos_aee`;
2. nenhum write provocado por GET/listagem;
3. nenhum snapshot V2 existente pode ser regravado;
4. hashes e encadeamento de snapshots permanecem intactos;
5. nenhuma sincronização reversa automática V2 → legado;
6. nenhum dual-write legado + V2;
7. `legacy_plano_id` permanece âncora estável;
8. erro de integridade não pode produzir fallback silencioso;
9. professor/RBAC não pode ganhar acesso adicional pela nova camada;
10. filtros de professor devem preservar o escopo atual;
11. frontend não pode decidir sozinho a autoridade da fonte; backend continua canônico;
12. ações bloqueadas no frontend também precisam ser bloqueadas no backend;
13. a camada V2 não deve introduzir N+1 de heads/snapshots;
14. `backend/routers/aee.py` e demais arquivos marcados como bloqueados só poderão ser modificados com autorização explícita; preferir adapters externos quando tecnicamente seguro;
15. Diário, PDFs e Dossiê já homologados não podem regredir.

---

## 12. Observabilidade obrigatória

Logs devem ser estruturados e sem dados pessoais desnecessários.

### Shadow

Deve registrar, no mínimo:

- fase;
- filtros técnicos relevantes sem PII;
- total de candidatos;
- `legacy_count`;
- `working_v2_count`;
- `sidecar_active_count`;
- divergências de status;
- divergências de agenda/resumo;
- erros de integridade;
- tempo de resolução batch.

### Cutover

Deve registrar:

- quantidade de itens retornados;
- fontes efetivas usadas;
- quantidade de summaries V2 aplicados;
- blockers;
- erro, quando houver.

### Governança de escrita

Tentativa de PUT/duplicate em Plano gerenciado por V2 deve gerar evento com:

- operação;
- `legacy_plano_id`;
- existência de head;
- existência de active/working snapshot;
- código de bloqueio;
- ator apenas no mecanismo institucional de auditoria já existente, evitando duplicação de PII em log técnico.

Eventos com integridade quebrada ou mutação bloqueada devem ser visíveis no nível de logging usado em produção.

---

## 13. Testes obrigatórios

O `AEE v2 - Contract Guard` deve ganhar cobertura específica para a 6.6.

### Resolver/listagem

- Plano sem head permanece `legacy`;
- head working sem active: `v2_managed=true`, Fonte Efetiva oficial ainda legado;
- sidecar ativo: summary vem do snapshot vigente;
- active snapshot inexistente: erro de integridade, sem fallback falso;
- active snapshot de outro Plano: erro de identidade;
- snapshot adulterado: integridade falha;
- lote com combinação legacy + working + active;
- nenhum N+1 de heads/snapshots.

### Filtros/paginação

- `status_filter=ativo` inclui Plano cujo legado é `rascunho` mas sidecar ativo é `active`;
- `status_filter=rascunho` não inclui esse mesmo Plano após cutover efetivo;
- total e paginação refletem o filtro efetivo;
- school/student/year/professor continuam respeitados;
- professor não enxerga Plano fora de seu escopo atual.

### UI

- status `active` aparece como **Vigente**;
- Plano V2-managed não abre editor legado;
- ação de edição conduz ao Dossiê V2;
- Visualizar não usa silenciosamente o objeto legado cru;
- duplicação V2-managed não é oferecida como se fosse segura;
- erro de integridade produz aviso e bloqueia mutações.

### Backend de mutações

- PUT sem head segue comportamento legado;
- PUT com head retorna 409;
- duplicate sem head segue comportamento legado;
- duplicate com head retorna 409;
- DELETE continua protegido pela Fase 6.0A;
- criação de novo Plano não é afetada;
- nenhuma tentativa bloqueada altera Mongo.

### Regressão

Devem continuar verdes:

- `AEE v2 - Contract Guard`;
- `CI - Build & Lint`;
- `Gate - Transferência (Regressão)`;
- guards P0 correlatos já existentes.

---

## 14. Preflight de produção antes de cada cutover

Antes da 6.6C e da 6.6D deverá ser executada auditoria read-only em produção para levantar:

- total de heads V2;
- heads sem active snapshot;
- heads com active snapshot;
- heads/snapshots com erro de integridade;
- distribuição legacy × sidecar_active;
- divergências de status entre legado e Fonte Efetiva;
- divergências de agenda nos campos representados pela lista;
- quantidade de Planos que seriam afetados pelos guards de PUT/duplicate.

Nenhum backfill deve ser executado como parte desse preflight.

---

## 15. Critérios de homologação da Fase 6.6

A fase só poderá ser encerrada quando:

1. listagem de Plano com `sidecar_active` apresentar a situação efetiva correta;
2. o caso homologado `rascunho legado` × `active V2` aparecer como **Vigente** na interface;
3. visualização tradicional não apresentar dados efetivos como se fossem legado atual;
4. `status_filter` e total usarem semântica efetiva;
5. tentativa de editar Plano V2-managed pelo PUT legado retornar bloqueio explícito;
6. frontend conduzir a edição ao Dossiê V2;
7. duplicação legado de Plano V2-managed estiver bloqueada;
8. zero writes forem realizados por listagem/Shadow;
9. zero snapshots históricos forem alterados;
10. nenhuma regressão for observada em Diário/PDFs/Dossiê;
11. observabilidade estiver visível em produção;
12. gates críticos estiverem verdes.

---

## 16. Estratégia de rollback

Rollback deve ser granular por subfase.

### 6.6A

Remover o installer Shadow. Não há impacto de dados.

### 6.6B

Retirar os campos aditivos da listagem. Campos legado continuam intactos.

### 6.6C

Desativar o cutover visual/efetivo e retornar à apresentação legado, preservando summaries para diagnóstico se desejado. Nenhum dado precisa ser restaurado.

### 6.6D

O guard de escrita deve ser tratado como proteção de integridade, não como transformação de dados. Caso precise ser revertido por incidente técnico, a reversão deve ser deliberada e documentada, pois reabrir PUT/duplicate legado em Planos com head V2 reintroduz o risco de dual-authority.

Não existe rollback de banco porque a 6.6 não introduz migração nem alteração histórica.

---

## 17. Impacto de dados

### Não haverá

- migração de `planos_aee`;
- backfill em massa;
- atualização automática de status legado;
- atualização automática de agenda legado;
- exclusão de documentos;
- recriação de IDs;
- alteração de snapshots existentes;
- sincronização de heads;
- bootstrap automático de Planos ainda legacy-only.

### Poderá haver futuramente, somente após implementação da 6.6D

- bloqueios 409 em operações legado incompatíveis com a governança V2;
- novos logs/auditorias de tentativa bloqueada;
- campos aditivos de read model na resposta da listagem.

---

## 18. Fora do escopo da Fase 6.6

Ficam explicitamente fora:

- cancelamento/retificação versionada de Atendimentos AEE;
- hard delete atual de Atendimentos AEE;
- versionamento de Articulações com Sala Comum;
- versionamento de Evoluções/Sínteses;
- anexos/documentos do Dossiê;
- migração em massa dos Planos existentes para V2;
- duplicação V2-aware;
- reatribuição de professor AEE em Plano já versionado;
- remoção física do legado;
- alteração da estrutura de hashes dos snapshots;
- refatoração geral do router AEE;
- mudança normativa/pedagógica do contrato do Dossiê.

---

## 19. Próxima dívida arquitetural após a 6.6

Há uma dívida já registrada desde o P0 e reiterada nas Fases 1–3: o ciclo de vida dos **Atendimentos AEE** ainda não possui cancelamento/retificação versionada.

O backend atual permite atualização in-place do atendimento e hard delete físico do documento.

Esse tema é candidato natural à fase sucessora, mas **não recebe numeração canônica neste documento**. Seu contrato deverá ser definido somente depois da homologação da 6.6, evitando abrir duas migrações arquiteturais simultâneas.

A futura fase deverá decidir, entre outros pontos:

- atendimento como evento histórico imutável ou head + revisões;
- cancelamento em vez de exclusão física;
- retificação com motivo, autor e encadeamento;
- impacto em frequência/KPIs/PDFs;
- preservação de IDs antigos;
- política para atendimentos históricos já existentes.

---

## 20. Gate de autorização para implementação

A Fase 6.6 somente poderá receber código após aprovação explícita deste escopo.

A ordem obrigatória será:

1. aprovar este documento arquitetural;
2. implementar **6.6A Shadow Mode** em PR exclusivo;
3. validar CI e produção;
4. documentar o resultado;
5. somente então autorizar 6.6B;
6. repetir o mesmo ciclo para 6.6C;
7. somente após homologação da leitura efetiva autorizar 6.6D.

Não deve existir PR único implementando 6.6A–6.6D de uma vez.

---

## 21. Decisão proposta

> **PROPOSTA:** instituir a Fase 6.6 — Coerência Operacional da Fonte Efetiva do Plano AEE, com execução incremental 6.6A → 6.6B → 6.6C → 6.6D.

A motivação não é acrescentar funcionalidade nova, mas consolidar a autoridade já criada: depois da homologação da 6.5B, o SIGESC precisa garantir que **listagem, visualização, PDF, Diário e mutações do Plano não apresentem ou produzam versões concorrentes da verdade**.
