# P0 #250 — Fase 2.1: paridade HTTP/projeção das notas para os 21 estudantes

Data: 2026-08-30  
Status: **READY_FOR_REVIEW**

## Contexto

A Fase 2 read-only classificou o caso como `PROMOTION_BYCLASS_STUDENT_SET_DIVERGENCE` e confirmou:

- 9 `teacher_assignments` ativos e 9 componentes resolvidos;
- 21 estudantes no universo montado pelo Livro de Promoção;
- 22 estudantes no universo montado pelo endpoint `/grades/by-class`;
- 22 documentos de nota por componente, dos quais 21 possuem ao menos um campo acadêmico registrado;
- zero grupos duplicados por estudante/componente;
- IDs de curso e estudante representados como `string`;
- documentos de nota existentes nos 9 `course_id` alocados.

Essa divergência de roster deve ser tratada separadamente, mas não explica por si só por que um estudante que já pertence aos 21 do Livro pode ter nota visível em **Notas** e `-` na **Promoção**.

## Objetivo da Fase 2.1

Comparar o comportamento HTTP real e a projeção aplicada pelo frontend **somente para a interseção canônica dos 21 estudantes já usados pelo Livro de Promoção**, sem incluir o 22º estudante nesta fase.

O caso esperado possui:

- 21 estudantes;
- 9 componentes autorizados por `/professor/turmas`;
- 189 pares `student_id × course_id`.

A auditoria responde, sem publicar identidade ou valor acadêmico:

1. se `GET /grades?student_id=...&class_id=...&academic_year=2026` possui documento persistido para cada um dos 189 pares;
2. se `GET /grades/by-class/{class_id}/{course_id}?academic_year=2026` possui a linha correspondente para cada um dos mesmos 189 pares;
3. quantas linhas `by-class` ficam fora do universo dos 21 estudantes do Livro;
4. se há diferença de presença de documento entre os dois caminhos HTTP;
5. se há diferença de presença de `b1`, `b2`, `b3`, `b4`, `rec_s1` ou `rec_s2`;
6. se os valores desses campos divergem entre os dois caminhos — a comparação ocorre apenas em memória e **somente a contagem de divergências é emitida**;
7. se a projeção equivalente a `filterPromotionGradesForClass` descarta algum documento autorizado;
8. se a comparação estrita `course.id === grade.course_id` usada posteriormente em `Promotion.jsx` poderia falhar por divergência de tipo;
9. quantos estudantes possuem documento nos 9 componentes e quantos possuem ao menos um campo acadêmico registrado.

## Paridade HTTP observada pelo coletor

O coletor executa dentro do container backend já ativo e usa exatamente os caminhos consumidos pela aplicação:

- `GET /professor/turmas?academic_year=2026` — SSoT do entitlement docente;
- `GET /students?class_id=<class_id>&page_size=10000`;
- `GET /enrollments?class_id=<class_id>`;
- `GET /grades?student_id=<student_id>&class_id=<class_id>&academic_year=2026` — caminho atual do Livro de Promoção;
- `GET /grades/by-class/<class_id>/<course_id>?academic_year=2026` — caminho da tela de Notas.

O roster dos 21 é reconstruído com a mesma regra presente em `Promotion.jsx`: estudantes diretos da turma mais matrículas válidas (`active/ativo`, transferência e desistência) no ano letivo, buscando o cadastro do estudante apenas quando necessário para complementar históricos.

## Sessão de professor sem login mutável

A auditoria **não chama `/auth/login`**, porque o login grava auditoria e violaria o escopo read-only estrito.

Dentro do backend já implantado:

1. usuário, `staff`, escola e turma do caso são resolvidos apenas por leitura no MongoDB;
2. o escopo escolar é reproduzido a partir das lotações ativas, com fallback legado para `school_links`;
3. `auth_utils.create_access_token()` gera um access token curto em memória com papel `professor`;
4. o token é usado somente nos GETs locais para `http://127.0.0.1:8001/api`;
5. o token nunca é escrito em arquivo, log, artifact, comentário ou saída JSON.

## Classificações possíveis

- `PROMOTION_ROSTER_DRIFT` — o universo atual do Livro deixou de ser 21;
- `PROFESSOR_ENTITLEMENT_DRIFT` — `/professor/turmas` deixou de fornecer exatamente 9 componentes;
- `HTTP_DUPLICATE_IDENTITY_ROWS` — um dos caminhos HTTP produz mais de um registro para o mesmo par estudante/componente;
- `FRONTEND_STRICT_IDENTITY_TYPE_DIVERGENCE` — o JSON entregue criaria falha na comparação estrita de IDs do frontend;
- `HTTP_DOCUMENT_DIVERGENCE_FOR_PROMOTION_21` — documento persistido aparece em um caminho e não no outro para algum dos 189 pares;
- `HTTP_VALUE_DIVERGENCE_FOR_PROMOTION_21` — o mesmo campo acadêmico possui valores diferentes nos dois caminhos, sem que os valores sejam emitidos;
- `HTTP_FIELD_PRESENCE_DIVERGENCE_FOR_PROMOTION_21` — presença/ausência de campo diverge;
- `GENERIC_HTTP_MISSING_GRADE_DOCUMENTS_FOR_PROMOTION_21` — o caminho atual da Promoção não possui os 189 documentos esperados;
- `BYCLASS_HTTP_MISSING_ROWS_FOR_PROMOTION_21` — o caminho da tela Notas não projeta os 189 pares esperados;
- `HTTP_AND_FRONTEND_PROJECTION_PARITY_FOR_PROMOTION_21` — os dois caminhos são equivalentes para os 21 × 9 e a projeção por ID não explica os `-`.

## Limites de segurança

A Fase 2.1 é deliberadamente read-only:

- MongoDB: apenas `find`/leitura;
- HTTP: somente `GET`;
- sem `POST`, `PUT`, `PATCH` ou `DELETE` contra o SIGESC;
- sem login real;
- sem alteração de `grades`, `students`, `enrollments`, `teacher_assignments`, `courses` ou qualquer outra coleção;
- sem restart, rebuild ou deploy;
- sem emissão de nomes, IDs ou documentos de estudantes;
- sem emissão de valores de nota;
- sem persistência ou emissão do token efêmero;
- evidência técnica privada em GitHub Actions por 90 dias.

O workflow contém gate AST que falha se o coletor adquirir qualquer chamada de mutação MongoDB ou método HTTP de escrita.

## Execução protegida em produção

A execução real somente fica disponível depois de revisão, CI verde, merge em `main` e autorização explícita do owner em uma issue nova.

Título canônico:

`[P0-250-F2.1-AUDIT] <TARGET_SHA>`

Corpo canônico:

```text
P0_250_F2_1_AUDIT=AUTHORIZED
CONFIRMATION=VERIFY_P0_250_F2_1_HTTP_PROJECTION_READ_ONLY
TARGET_SHA=<40-hex da main revisada>
```

O workflow confirma novamente que `main` ainda aponta exatamente para `TARGET_SHA`. Se `main` tiver avançado, a execução falha fechada.

## Critério de decisão após a Fase 2.1

### Se houver divergência HTTP

A correção deverá mirar o caminho que altera/perde documento ou campo, mantendo o roster de 21 separado da questão 21 × 22. Nenhuma remediação de banco fica automaticamente autorizada.

### Se houver divergência de projeção/identidade no frontend

A correção deverá ser estritamente por identidade (`student_id`, `class_id`, `course_id`, `academic_year`), sem mapeamento por nome e com regressão 21 × 9.

### Se houver paridade total para os 189 pares

O problema deixa de ser atribuído aos documentos/IDs e o próximo foco deve ser o runtime do frontend entregue ao navegador: bundle efetivamente publicado, estado/cache/PWA e sequência de renderização. Nesse cenário, trocar o endpoint da Promoção sem evidência seria apenas deslocar o problema e não é autorizado por esta fase.

## O que esta fase NÃO faz

- não corrige o 22º estudante;
- não troca `GET /grades` por `GET /grades/by-class` em `Promotion.jsx`;
- não altera nota;
- não faz backfill;
- não consolida registros;
- não faz merge ou deploy automaticamente;
- não encerra a issue #250 por si só.
