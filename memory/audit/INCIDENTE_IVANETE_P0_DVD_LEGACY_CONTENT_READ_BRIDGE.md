# INCIDENTE P0 — DVD x histórico legado de conteúdos

Data: 2026-08-19
Status: diagnóstico confirmado; implementação pendente
Branch de trabalho: `agent/dvd-legacy-content-read-bridge`

## 1. Resumo executivo

Após o cutover do Diário por Vínculo Docente (DVD), professores com `assignment_id` ativo passaram a consultar conteúdo pedagógico exclusivamente em `content_entries` por meio do `frontend/src/services/contentDvdBridge.js`.

O acervo histórico, porém, permanece em `learning_objects` e não foi migrado/reassociado retroativamente. Em produção, na auditoria de 2026-08-19, havia:

- 30.383 `learning_objects` no recorte 2026 da auditoria DVD;
- 7.220 `learning_objects` em turmas que já possuem DVD ativo;
- 0 `content_entries` ativos no momento da auditoria;
- 228 vínculos DVD ativos;
- 14 turmas `fully_cutover` e 17 `partially_cutover`.

O efeito é perda de VISIBILIDADE, não perda comprovada dos documentos históricos.

## 2. Caso sentinela — Ivanete Silva Santos

Professora: Ivanete Silva Santos

- `user_id`: `85d25c91-2013-4e00-878f-4b092a8eeb36`
- `staff_id`: `04198568-c27c-47fc-aaae-0e21f5d173f5`
- escola: E M E I E F Cristo Redentor
- `school_id`: `0d8089af-8597-4b7a-8d8e-63afe84730d6`
- turma: `1º AO 5º ANO`
- `class_id`: `d622ab6f-8add-49df-a34c-4e580f844d1e`

Vínculos DVD ativos a partir de `2026-08-18`:

- Ciências — `assignment_id=afeccdbb-3004-53a9-8841-159b20be7db1`
- Educação Física — `assignment_id=6727021e-6694-52ff-bb4a-1e75a3eccc1d`
- História — `assignment_id=150dbf45-19c7-54ee-9a0a-933ca6a0daf6`
- Matemática — `assignment_id=900ba446-6b2f-51a8-93d3-913852727385`

Histórico preservado em `learning_objects` nessa turma:

- Ciências: 9 registros
- História: 9 registros
- Educação Física: 8 registros
- Matemática: 18 registros
- total: 44 registros

Todos permanecem associados à autoria histórica real de Ivanete; `content_entries` relacionados a ela = 0.

## 3. Root cause confirmado

`contentDvdBridge.js`, quando existe `assignment_id`, transforma a listagem antiga de `/learning-objects` em `/content-entries`.

O endpoint `GET /content-entries` lê somente `db.content_entries`; portanto o legado deixa de aparecer.

Os testes de harmonização da Fase 38F também cristalizam a expectativa de fonte exclusivamente canônica no DVD, inclusive no PDF. O conceito precisa ser corrigido: `content_entries` é canônico para ESCRITA e para o período DVD, mas o histórico pré-cutover deve continuar visível.

## 4. Invariantes obrigatórios

1. NÃO migrar `learning_objects` para `content_entries`.
2. NÃO gerar `assignment_id` retroativo.
3. NÃO alterar `recorded_by`, autoria, datas ou IDs históricos.
4. NÃO apagar ou regravar documentos legados.
5. Toda escrita nova DVD permanece exclusivamente em `content_entries`.
6. O histórico legado deve ser somente leitura no contexto DVD.
7. `main` e produção não devem ser alteradas durante desenvolvimento/validação.
8. Multi-tenancy e autorização por vínculo devem permanecer fail-closed.
9. AEE continua fora do escopo deste P0.
10. Não executar scripts de migração/restore/rollback para resolver este incidente.

## 5. Arquitetura-alvo

Quando `GET /content-entries` receber `assignment_id`:

1. validar o vínculo com a infraestrutura central de autorização do DVD;
2. validar `class_id` e `component_id` contra o vínculo;
3. obter `valid_from` do vínculo;
4. consultar `content_entries` normalmente para o vínculo;
5. consultar `learning_objects` elegíveis ANTES de `valid_from`;
6. normalizar os documentos legados para o contrato de leitura;
7. combinar e ordenar a resposta;
8. não persistir absolutamente nada durante o merge.

Fronteira temporal:

- `date < assignment.valid_from` => histórico legado elegível;
- `date >= assignment.valid_from` => somente `content_entries` do DVD.

Para Ivanete, `valid_from=2026-08-18`.

## 6. Serviço recomendado

Criar `backend/services/content_history_bridge.py`.

Responsabilidades sugeridas:

- resolver e autorizar o `assignment_id` para VIEW;
- reaproveitar `services.diary_assignment_access.authorize_assignment_access`;
- não duplicar política de autorização;
- obter tenant/escola/turma/componente do contexto autorizado;
- construir query histórica somente leitura;
- normalizar legado;
- ordenar/mesclar resposta;
- deduplicar defensivamente por identidade histórica sem alterar documentos.

O serviço não deve conter FastAPI nem gravar no MongoDB.

## 7. Autorização e seleção histórica

Não basta buscar todos os conteúdos da turma/componente e atribuí-los ao professor atual.

O documento histórico deve preservar `recorded_by` original.

Para a visão do professor proprietário, o histórico retornado deve ser compatível com:

- `class_id` do vínculo;
- `course_id/component_id` do vínculo;
- período anterior ao `valid_from`;
- tenant da turma/vínculo;
- autoria histórica pertinente ao contexto do professor (`recorded_by`), sem inventar autoria administrativa.

Se a implementação precisar ampliar autoria histórica além de `recorded_by == assignment.teacher_id`, deverá fazê-lo somente mediante regra explícita e testada de proveniência legada. Não inferir autoria silenciosamente.

## 8. Contrato normalizado para legado

Um item legado devolvido pela visão DVD deve preservar os campos originais e acrescentar metadados de leitura, por exemplo:

```json
{
  "id": "<id histórico>",
  "class_id": "...",
  "course_id": "...",
  "component_id": "...",
  "date": "2026-02-10",
  "content": "...",
  "teacher_id": "<recorded_by histórico>",
  "recorded_by": "<recorded_by histórico>",
  "assignment_id": null,
  "source": "learning_objects",
  "legacy": true,
  "read_only": true
}
```

Não definir `assignment_id` do vínculo atual em documento histórico.

Um item DVD continua com `source=content_entries`, `legacy=false`, `read_only=false` e seu `assignment_id` real.

## 9. Frontend

`frontend/src/services/contentDvdBridge.js` deve continuar roteando NOVAS ESCRITAS para `content_entries`.

Entretanto:

- deve aceitar itens `legacy=true` retornados na listagem;
- não deve substituir `source` se o backend já informar `learning_objects`;
- deve impedir PUT/DELETE/correct/publish de item `read_only=true` ou `legacy=true`;
- apresentar erro institucional claro se o usuário tentar editar histórico legado;
- não executar merge de fontes no navegador. O merge pertence ao backend.

## 10. GET individual

Se a UI necessitar buscar um item individual ao editar/visualizar, o contrato deve diferenciar legado e canônico de forma explícita.

Não permitir que um ID de `learning_objects` seja tratado como `content_entries` e convertido silenciosamente para um novo registro.

Opções aceitáveis:

- o frontend usar o registro legado já presente no cache/listagem para visualização; ou
- endpoint de leitura individual suportar fonte legada de modo autorizado e read-only.

Em qualquer caso, tentativa de escrita em legado deve falhar fechado.

## 11. PDF

O PDF do Diário por Vínculo deve usar a mesma visão histórica consolidada.

Não manter regra independente que leia somente `content_entries`.

Idealmente reutilizar o mesmo serviço `content_history_bridge.py`, evitando divergência entre tela e PDF.

## 12. Testes mínimos obrigatórios

Adicionar/ajustar testes para cobrir:

1. vínculo sem histórico -> apenas `content_entries`;
2. histórico anterior ao `valid_from` -> aparece;
3. data imediatamente anterior ao `valid_from` -> legado aparece;
4. `learning_object` em `valid_from` ou depois -> NÃO entra pelo legado;
5. `content_entry` após `valid_from` -> aparece;
6. ordenação combinada por data/aula;
7. legado retorna `assignment_id=null`;
8. legado retorna `legacy=true`, `read_only=true`, `source=learning_objects`;
9. autoria histórica é preservada;
10. assignment de outro professor -> negado;
11. componente incompatível -> negado;
12. tenant incompatível -> negado;
13. PUT/DELETE/correct/publish em legado -> proibido;
14. fluxo sem `assignment_id` -> comportamento legado anterior permanece intacto;
15. PDF DVD incorpora histórico pré-cutover;
16. nenhum teste cria/migra documentos históricos para `content_entries`;
17. caso sentinela Ivanete: 9+9+8+18 = 44 itens históricos visíveis.

## 13. Teste de não-mutação

A implementação deve provar que uma simples listagem não altera contagens.

Antes/depois de GET:

- `learning_objects` deve permanecer com a mesma quantidade;
- `content_entries` deve permanecer com a mesma quantidade, exceto escritas explícitas realizadas por testes isolados;
- IDs dos 44 registros de Ivanete não mudam;
- nenhum desses 44 IDs aparece como novo documento em `content_entries`.

## 14. Backup baseline pré-correção

Backup integral criado no host de produção ANTES da implementação:

`/root/sigesc-backups/database/sigesc-full-20260819T140519Z.archive.gz`

- tamanho: `104243527` bytes
- gzip: OK
- SHA-256: `f4db1877202e4933335523e197f3ef63706f37bf60b4c3cfd0ef08674568b61a`
- banco: `sigesc`
- imagem Mongo: `mongo:7`
- mongodump: `100.16.1`

Este backup não deve ser restaurado durante a implementação. Serve como baseline de segurança.

## 15. Questão histórica separada

A base atual possui 50 `learning_objects` de Ivanete em 2026:

- 44 na turma `1º AO 5º ANO` entre 2026-02-09 e 2026-04-15;
- 6 na turma `6 AO 9º ANO` entre 2026-03-23 e 2026-04-16.

Não há atualmente registros dela depois de 2026-04-16. Isso é anterior ao cutover e NÃO deve ser misturado com a regressão de visibilidade de 18/08.

Não existe snapshot histórico local suficiente para provar se outros registros posteriores a abril nunca existiram ou foram excluídos pela rota legada (que historicamente usa hard delete). Portanto não afirmar perda física sem evidência.

## 16. Entregáveis esperados do P0

- serviço de bridge histórico;
- integração no `GET /content-entries` com `assignment_id`;
- integração equivalente no PDF DVD;
- proteção frontend para legado read-only;
- atualização dos testes da Fase 38F;
- testes novos do bridge;
- relatório de testes;
- evidência do caso Ivanete;
- nenhum script de migração;
- nenhum deploy automático.

## 17. Critério de aceite institucional

Ao abrir o Diário DVD de Ivanete Silva Santos na turma `1º AO 5º ANO`, os conteúdos históricos devem reaparecer:

- Ciências: 9
- História: 9
- Educação Física: 8
- Matemática: 18
- Total: 44

Os mesmos 44 documentos devem continuar existentes somente como documentos históricos originais em `learning_objects`.

A partir de `2026-08-18`, novas escritas devem ocorrer exclusivamente em `content_entries`, sob `assignment_id`, versionamento e auditoria canônica.
