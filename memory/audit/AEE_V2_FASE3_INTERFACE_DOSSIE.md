# AEE v2 — Fase 3: Interface do Dossiê Individual AEE

Data: 21/08/2026  
Status: implementação em branch / PR de validação

## 1. Objetivo

Conectar a especificação canônica da Fase 1 e a persistência sidecar versionada da Fase 2 a uma interface utilizável pelos profissionais do AEE, sem substituir abruptamente os fluxos históricos do Diário AEE.

A página passa a se apresentar como **Diário AEE V2.0**.

## 2. Estratégia de adoção

A Fase 3 utiliza adoção controlada por Plano:

1. o usuário abre o **Dossiê Individual AEE V2** a partir da tabela de Planos;
2. a simples abertura faz somente leituras;
3. se não houver sidecar, a interface informa que a fonte efetiva continua sendo o Plano legado;
4. somente o comando explícito **Inicializar Dossiê V2** executa o bootstrap;
5. o bootstrap projeta o Plano existente para `v1.r1` sem regravar `planos_aee`;
6. cada salvamento de seção gera snapshot imutável;
7. a ativação depende do gate de requisitos obrigatórios da Fase 2;
8. após ativação, uma revisão futura é aberta como nova versão, mantendo a versão anterior vigente até a nova ativação.

## 3. Navegação do Dossiê

A primeira interface expõe:

- Visão Geral;
- Estudo de Caso;
- PAEE;
- PEI;
- Agenda;
- Atendimentos;
- Articulação;
- Evolução;
- Histórico.

### Visão Geral

Mostra:

- fonte efetiva (`legacy` ou `sidecar_active`);
- versão V2 vigente;
- versão V2 em elaboração/revisão;
- situação de Estudo de Caso, PAEE e PEI;
- bloqueadores de ativação;
- ação de inicialização, ativação ou abertura de nova versão conforme o estado.

### Estudo de Caso

Permite registrar/complementar:

- fundamentação pedagógica da identificação para o AEE;
- demanda inicial e contexto escolar;
- barreiras;
- potencialidades;
- demandas de apoio;
- comunicação e participação;
- participação e contribuições do estudante;
- contribuições da família;
- estratégias/recursos de acessibilidade;
- articulação com rede de proteção quando necessária.

### PAEE

Permite registrar/complementar:

- barreiras prioritárias;
- objetivos;
- materiais e recursos;
- indicadores de progresso;
- frequência de revisão e critérios de ajuste;
- demandas de formação;
- acionamentos da rede de proteção;
- avaliações de Tecnologia Assistiva, CAA e apoios humanos.

A interface preserva a distinção entre `not_assessed` e `not_needed`.

### PEI

Permite registrar/complementar:

- atividades do AEE;
- articulação com Sala Comum;
- combinados com professor regente;
- acessibilidade curricular;
- acessibilidade didático-pedagógica;
- acessibilidade avaliativa;
- **Adaptações por Componente Curricular/Campos de Experiência**;
- acompanhamento/monitoramento;
- devolutivas à família.

O campo técnico permanece `adaptacoes_por_componente` para preservar compatibilidade.

### Agenda

Mantém carga horária e sessões de atendimento no sidecar versionado.

### Registros históricos

Atendimentos, articulações e evoluções são apresentados em modo leitura dentro do Dossiê, mas continuam sendo gravados pelos fluxos legados atuais nesta fase. Isso evita duplicação de SSoT antes da definição de seus ciclos de retificação/cancelamento.

### Histórico

Lista snapshots do Dossiê com:

- versão documental;
- revisão;
- operação;
- data/autoria;
- hash SHA-256;
- indicação da versão vigente.

## 4. Concorrência

Cada salvamento envia:

- `expected_head_revision`;
- `expected_working_snapshot_id`.

Resposta `409` provoca recarga do Dossiê e informa o conflito ao usuário. Não existe política de last-write-wins.

## 5. Alterações de apresentação solicitadas

### Título

De:

`Diário AEE`

Para:

`Diário AEE V2.0`

A visão consolidada também usa o novo nome.

### Articulação com a Sala Comum

De:

`Adaptações por Componente Curricular`

Para:

`Adaptações por Componente Curricular/Campos de Experiência`

A alteração foi refletida:

- no modal legado do Plano AEE;
- no PEI do Dossiê V2;
- no PDF do Plano AEE.

Não houve alteração do nome técnico do campo.

## 6. Invariantes

- `planos_aee` não é migrada nem regravada pela UI V2;
- abrir o Dossiê não cria sidecar automaticamente;
- nenhum ID histórico é recriado;
- atendimentos, articulações e evoluções não são duplicados;
- versão vigente não é sobrescrita por versão em elaboração;
- campos legados permanecem compatíveis;
- perfis somente leitura continuam sem ações de escrita.

## 7. Gate permanente

`backend/tests/test_aee_v2_fase3_ui_contract.py` protege:

- título `Diário AEE V2.0`;
- presença do entrypoint do Dossiê;
- bootstrap explicitamente acionado pelo usuário;
- uso do contrato de optimistic locking;
- novo rótulo curricular/campos de experiência;
- preservação de `adaptacoes_por_componente`;
- leitura dos registros legados sem novos endpoints de escrita nesses domínios.

O teste integra `.github/workflows/aee-v2-contract.yml`.

## 8. Fora do escopo desta fase

- deploy em produção;
- migração automática de todos os Planos;
- substituição dos fluxos de criação/edição de Atendimentos;
- cancelamento/retificação versionada de Atendimentos;
- upload/documentos anexos no sidecar;
- substituição automática dos PDFs históricos por documentos V2.
