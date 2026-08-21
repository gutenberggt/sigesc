# AEE v2 — Fase 2: Persistência Aditiva e Versionamento

Data: 21/08/2026  
Status: implementação em branch; sem deploy e sem migração de produção

## 1. Objetivo

Adicionar persistência nativa ao Dossiê AEE v2 sem alterar ou substituir os documentos históricos da coleção `planos_aee`.

A Fase 2 transforma o contrato canônico da Fase 1 em um sidecar versionado com:

1. snapshots imutáveis;
2. versionamento documental independente da versão do schema;
3. uma versão vigente e, simultaneamente, uma versão em elaboração/revisão;
4. optimistic locking;
5. trilha criptográfica por SHA-256 encadeado;
6. APIs separadas para Estudo de Caso, PAEE, PEI e cronograma;
7. validação explícita antes da vigência.

## 2. Base normativa verificada

### Decreto nº 12.686/2025, com redação do Decreto nº 12.773/2025

Fonte oficial:  
https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/decreto/d12686.htm

O desenho preserva os seguintes princípios:

- Estudo de Caso como etapa inicial necessária;
- resultado do Estudo de Caso fundamentando PAEE e PEI;
- envolvimento do estudante e da família;
- atualização contínua dos documentos pedagógicos;
- inexistência de requisito de diagnóstico, laudo ou CID para oferta do AEE.

### Portaria MEC nº 421/2026

Fonte oficial:  
https://mecnormas.mec.gov.br/pesquisa/detalhar/11240

Regras relevantes para o versionamento:

- PAEE e PEI são documentos individualizados de natureza pedagógica e atualização contínua;
- a rede pode adotar documento único, preservados os conteúdos mínimos de ambos;
- PAEE e PEI devem ser revistos anualmente em compatibilidade com a avaliação contínua do estudante.

### Portaria MEC nº 550/2026

Fonte oficial:  
https://mecnormas.mec.gov.br/pesquisa/detalhar/12723

A alteração publicada em junho de 2026 atingiu o art. 29 da Portaria nº 421/2026 e não modificou os requisitos pedagógicos utilizados neste desenho.

## 3. Regra mestra de preservação

A Fase 2 **não executa escrita em `planos_aee`**.

O Plano AEE atual continua existindo com:

- mesmo `id`;
- mesmos atendimentos vinculados;
- mesmas evoluções;
- mesmas articulações;
- mesmos documentos e PDFs históricos;
- mesma autoria e datas legadas.

O sidecar utiliza `legacy_plano_id` apenas como referência estável.

## 4. Coleções novas

### `aee_dossier_v2_heads`

Um documento por Plano AEE legado.

Função: guardar apenas o estado operacional atual do versionamento.

Campos principais:

```text
id
legacy_plano_id
student_id
school_id
academic_year
active_snapshot_id
working_snapshot_id
head_revision
next_document_version
created_at / created_by
updated_at / updated_by
```

`active_snapshot_id` aponta para a versão v2 atualmente vigente.

`working_snapshot_id` aponta para a versão atualmente em elaboração ou revisão.

É permitido existir:

```text
active_snapshot_id  = v1 vigente
working_snapshot_id = v2 em revisão
```

Isso impede deixar o estudante sem documento vigente enquanto a próxima versão é construída.

### `aee_dossier_v2_snapshots`

Coleção append-only.

Cada salvamento cria um documento novo. Um snapshot nunca é atualizado ou apagado pelo fluxo da Fase 2.

Campos principais:

```text
id
legacy_plano_id
schema_version = 2
document_version
revision
operation
changed_section
parent_snapshot_id
parent_hash
base_active_snapshot_id
snapshot_hash
dossier
created_at / created_by
actor_name / actor_role
```

## 5. Duas dimensões de versão

### Schema

```text
schema_version = 2
```

Identifica a estrutura canônica do AEE v2.

### Documento pedagógico

```text
v1
v2
v3
...
```

Cada versão documental pode possuir várias revisões técnicas de salvamento:

```text
v1.r1  bootstrap
v1.r2  Estudo de Caso atualizado
v1.r3  PAEE atualizado
v1.r4  PEI atualizado
v1.r5  ativação
```

Ao iniciar revisão anual ou nova revisão pedagógica:

```text
v1.r5  continua Vigente
v2.r1  fica Em revisão
```

## 6. Integridade criptográfica

Cada snapshot possui `snapshot_hash` SHA-256 calculado sobre:

- ID do snapshot;
- Plano legado relacionado;
- versão documental;
- revisão;
- operação;
- hash do snapshot pai;
- conteúdo canônico completo do Dossiê.

Exemplo:

```text
v1.r1 hash A
   ↓
v1.r2 parent_hash=A / hash B
   ↓
v1.r3 parent_hash=B / hash C
```

Alteração posterior do conteúdo provoca divergência entre o hash armazenado e o hash recalculado.

## 7. Optimistic locking

O head possui:

```text
head_revision
working_snapshot_id
```

Toda escrita deve informar os valores que o cliente leu.

Exemplo:

```text
expected_head_revision = 4
expected_working_snapshot_id = snapshot-X
```

Se outra sessão já tiver salvo uma alteração, o update recebe HTTP `409 Conflict` e deve recarregar o Dossiê.

Não existe política de “última gravação vence”.

## 8. Bootstrap

Endpoint:

```text
POST /api/aee/planos/{plano_id}/dossie-v2/bootstrap
```

Fluxo:

1. lê `planos_aee`;
2. usa o mapeador legado da Fase 1;
3. cria `v1.r1` no sidecar;
4. define `working_snapshot_id = v1.r1`;
5. não define versão v2 vigente ainda;
6. o Plano legado continua sendo a fonte efetiva até a ativação da primeira versão v2.

O bootstrap é idempotente por `legacy_plano_id`.

## 9. Edição por seção

Endpoints:

```text
PATCH /api/aee/planos/{plano_id}/dossie-v2/sections/study-case
PATCH /api/aee/planos/{plano_id}/dossie-v2/sections/paee
PATCH /api/aee/planos/{plano_id}/dossie-v2/sections/pei
PATCH /api/aee/planos/{plano_id}/dossie-v2/sections/schedule
```

Cada operação:

1. valida o payload Pydantic;
2. valida optimistic locking;
3. carrega o snapshot de trabalho;
4. cria uma cópia canônica em memória;
5. substitui somente a seção solicitada;
6. gera novo snapshot imutável;
7. move `working_snapshot_id` para o novo snapshot;
8. incrementa `head_revision`.

## 10. Validação para vigência

Endpoint:

```text
GET /api/aee/planos/{plano_id}/dossie-v2/activation-validation
```

Para tornar uma versão vigente:

- `study_case.state` deve ser `complete`;
- `paee.state` deve ser `complete`;
- `pei.state` deve ser `complete`;
- nenhuma lacuna classificada como `required` pela especificação canônica pode permanecer.

A validação não transforma automaticamente ausência em `not_needed`.

Apoios com conclusão de não necessidade devem possuir decisão pedagógica explícita no campo de avaliação correspondente.

## 11. Ativação

Endpoint:

```text
POST /api/aee/planos/{plano_id}/dossie-v2/activate
```

A ativação:

1. valida optimistic locking;
2. executa a validação de requisitos;
3. cria um novo snapshot imutável com `lifecycle.status = active`;
4. move `active_snapshot_id` para esse snapshot;
5. limpa `working_snapshot_id`;
6. preserva todas as versões e revisões anteriores.

## 12. Nova revisão documental

Endpoint:

```text
POST /api/aee/planos/{plano_id}/dossie-v2/revisions
```

Só pode ser aberto quando:

- existe uma versão v2 vigente;
- não existe outra versão em trabalho.

Exemplo:

```text
active  → v1.r5
working → null
```

Após abertura:

```text
active  → v1.r5
working → v2.r1
```

A versão vigente não é retirada de vigência durante a elaboração da revisão.

## 13. Leitura do estado

Endpoint:

```text
GET /api/aee/planos/{plano_id}/dossie-v2/state
```

Retorna:

- head;
- snapshot vigente, quando existir;
- snapshot de trabalho, quando existir;
- `effective_source`.

Valores de `effective_source`:

```text
legacy
sidecar_active
```

Enquanto nenhuma versão v2 tiver sido ativada, o Plano legado continua sendo a fonte efetiva.

## 14. Histórico

Endpoint:

```text
GET /api/aee/planos/{plano_id}/dossie-v2/snapshots
```

Lista metadados de snapshots sem devolver o conteúdo integral de todos eles em uma única resposta.

Isso permite auditoria de:

- versão;
- revisão;
- operação;
- autoria;
- data;
- hash;
- encadeamento.

## 15. Permissões

A Fase 2 não amplia os papéis definidos pelo Diário AEE.

Para professor, além do papel de escrita, o Plano deve estar relacionado ao usuário como:

- `professor_aee_id`; ou
- `created_by` legado.

Perfis administrativos continuam submetidos às permissões já existentes no módulo.

## 16. O que a Fase 2 não faz

- não altera `planos_aee`;
- não migra em lote;
- não exclui registros legados;
- não muda atendimentos;
- não muda evoluções;
- não muda articulações;
- não altera PDF histórico;
- não muda a UI do Diário AEE;
- não faz deploy automático em produção.

## 17. Critérios de aceite

- [ ] bootstrap não altera o dicionário/documento legado;
- [ ] snapshot adulterado falha na verificação SHA-256;
- [ ] snapshots são append-only;
- [ ] índice único impede duplicidade de `document_version + revision`;
- [ ] optimistic locking rejeita cliente obsoleto;
- [ ] primeira ativação muda `effective_source` para `sidecar_active`;
- [ ] nova revisão mantém versão anterior vigente;
- [ ] validação bloqueia ativação de seções incompletas;
- [ ] router de persistência não possui escrita em `planos_aee`;
- [ ] gate específico AEE v2 passa;
- [ ] CI geral e regressão com backend/Mongo passam.
