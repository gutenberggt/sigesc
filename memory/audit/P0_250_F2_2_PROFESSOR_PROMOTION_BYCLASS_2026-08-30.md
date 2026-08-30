# P0 #250 — Fase 2.2 — Promoção do professor alinhada ao `/grades/by-class`

Data: 2026-08-30

## Contexto comprovado pela Fase 2.1

A auditoria read-only em produção no SHA `8b6b57be511c26633e2391113279228dec4ff531` classificou o caso como:

`HTTP_DOCUMENT_DIVERGENCE_FOR_PROMOTION_21`

Para o caso-canário da professora Abadia Alves Martins, 5º ANO A, ano 2026:

- roster canônico da Promoção: 21 estudantes;
- componentes autorizados pelo vínculo docente: 9;
- universo esperado: 189 pares estudante × componente;
- caminho genérico `GET /grades`: 42 pares documentais;
- caminho `GET /grades/by-class/{class_id}/{course_id}`: 189 pares dentro do roster da Promoção;
- divergências documentais: 147 = 7 componentes × 21 estudantes;
- incompatibilidades de tipo de `course_id`: 0;
- o `by-class` também retornou 9 linhas de um 22º estudante fora do roster da Promoção, uma por componente.

A evidência localizou o defeito no caminho de leitura/projeção do Livro de Promoção para professor; não autorizou nem indicou correção de banco.

## Correção F2.2

Somente o caminho `restrictToProfessor` de `Promotion.jsx` passa a usar a mesma unidade de consulta já adotada pela tela de Notas:

`GET /grades/by-class/{class_id}/{course_id}?academic_year={ano}`

A Promoção realiza uma requisição por componente exibível/autorizado e agrega as respostas pelo roster canônico da própria tela.

No caso-canário, isso troca 21 consultas genéricas por estudante por 9 consultas canônicas por componente.

## Invariantes preservadas

1. A autorização curricular continua vindo de `/professor/turmas` e permanece fail-closed.
2. Nenhum componente é recuperado por nome ou por fallback sem `course_id` autorizado.
3. A projeção só aceita a turma selecionada.
4. Somente estudantes presentes no roster canônico da Promoção são agregados; o 22º estudante retornado pelo endpoint `by-class` é descartado.
5. Pares estudante × componente repetidos são deduplicados defensivamente.
6. Perfis de gestão preservam o caminho existente de `GET /grades` por estudante, sem mudança funcional nesta fase.
7. Não há alteração de backend, notas, matrículas, vínculos docentes ou banco de dados.

## Regressão obrigatória

`frontend/src/utils/promotionParity.test.js` contém cenário sintético com:

- 21 estudantes da Promoção;
- 9 componentes autorizados;
- 189 pares esperados;
- um 22º estudante presente em cada resposta `by-class`, que deve ser excluído;
- um 10º componente não autorizado, que deve permanecer invisível.

Critérios do teste:

- mapa final com exatamente 21 estudantes;
- exatamente 189 pares projetados;
- exatamente 9 componentes por estudante;
- ausência do 22º estudante;
- ausência do 10º componente.

## CI

Além do CI geral, que já executa `promotionParity.test.js` e o build de produção do frontend, a Fase 2.2 adiciona um gate dedicado para validar:

- regressão 21 × 9;
- uso de `gradesAPI.getByClass(...)` no ramo professor;
- preservação de `gradesAPI.getAll(...)` no ramo de gestão;
- filtragem por roster, turma e `course_id` autorizado;
- deduplicação defensiva.

## Limites desta fase

A Fase 2.2 não:

- corrige o 22º estudante na origem do endpoint `by-class`;
- altera notas;
- executa backfill;
- altera alocações docentes;
- amplia RBAC;
- faz merge automático;
- faz deploy automático.

## Gate de integração e publicação

Esta é uma alteração funcional de frontend. Após CI verde e revisão, o merge em `main` exige autorização humana explícita. Depois do merge, a correção só chegará aos usuários após deployment da nova `main` em produção e verificação pós-deploy do caso-canário.
