# P0 #250 — F2.9B: seal dos 48 targets seguros para backfill

## Objetivo

A F2.9A identificou **48** criações canônicas `teacher_class_assignments` que
podem ser derivadas de forma unívoca, mantendo **883** pares em revisão e sem
autorizar qualquer escrita.

A F2.9B transforma somente esses 48 targets em um **manifesto privado selado**,
adequado para uma fase posterior de backfill controlado. Esta fase continua
read-only em relação ao MongoDB.

## Fonte aprovada

A F2.9B só aceita exatamente a evidência homologada da F2.9A:

- main SHA: `794cf799a8f4091d35401d45d8203109b4e5dd0d`;
- planner blob SHA: `42178d99c479ab43d4345c4a5346cac6735eefd3`;
- run: `33350397799`;
- ano letivo: `2026`;
- reference date: `2026-08-31`;
- plan SHA-256: `fbfe46dd455e45ad65c510d75022d52918c8993c21cc76593f1915d5324fb177`;
- decision manifest SHA-256: `8dec6b3544ac01ecda5c4f84fba382816c51248e63a04704c8a79ee674877c27`;
- input state SHA-256: `c080d9deb83ce3d08fa2aa2ffc5b88f11f85f19570fcf4c77771db79d6c67cca`.

Qualquer drift nesses valores bloqueia o seal.

## Reuso da SSoT F2.9A

A F2.9B não copia o algoritmo de reconciliação. Ela executa o planner F2.9A e
intercepta somente a função que serializa o `decision_manifest`, capturando o
mesmo objeto que o planner usa para calcular seus hashes.

Com isso, os 48 targets selados precisam satisfazer simultaneamente:

1. decisão `PLAN_CREATE_CANONICAL_ASSIGNMENT`;
2. zero `review_reasons`;
3. exatamente 48 linhas;
4. IDs e chaves naturais sem duplicidade;
5. shape estrito do target DVD;
6. SHA-256 da lista de targets idêntico ao `plan_sha256` homologado;
7. SHA-256 do decision manifest idêntico ao seal F2.9A.

## Precondições vivas antes do seal

Além da paridade integral da F2.9A, o seal verifica no MongoDB, sem escrita:

- exatamente um `teacher_assignment` legado ativo para cada source key;
- ausência do `target_assignment.id` determinístico em `teacher_class_assignments`;
- quando o target é `grades_official_owner=true`, ausência de outro proprietário
  oficial ativo para a mesma turma/componente na reference date.

Se qualquer uma dessas condições falhar, o conjunto de 48 não é selado.

## Manifesto privado

Cada operação contém:

- `operation=INSERT_TEACHER_CLASS_ASSIGNMENT`;
- chave legada de origem;
- documento target completo;
- SHA-256 individual do target;
- precondições seladas;
- contrato de rollback `DELETE_INSERTED_IF_EXACT_PROJECTED_MATCH`.

O rollback futuro só poderá remover um documento inserido se sua projeção ainda
for exatamente igual ao target selado. Mudança posterior no documento deve
bloquear remoção automática.

O manifesto privado produz três seals:

- `sealed_targets_sha256` — deve ser igual ao plan SHA-256 F2.9A;
- `sealed_operations_sha256` — inclui operação, source key, precondições e
  contrato de rollback;
- `sealed_bundle_sha256` — sela o bundle privado completo, exceto o próprio campo
  de hash.

## Privacidade

O artifact privado pode conter IDs internos necessários ao backfill futuro. Eles
não são impressos em logs nem publicados no comentário da issue #250.

O receipt público contém somente:

- contagem 48;
- classificação;
- hashes da evidência e do bundle;
- run/artifact metadata;
- flags explícitas de que apply não está autorizado.

## Workflow exact-SHA

O job de produção só aceita issue criada pelo owner e presa ao SHA exato de
`main`. Também verifica que o blob do planner F2.9A continua exatamente igual ao
homologado.

O workflow envia as fontes F2.9A e F2.9B por stdin ao backend em execução e usa o
MongoDB somente para leitura. O manifesto privado é redirecionado para arquivo no
runner e enviado como GitHub Actions artifact; ele não é ecoado no log.

## O que esta fase NÃO faz

A F2.9B não:

- insere `teacher_class_assignments`;
- altera `teacher_assignments`;
- altera Notas, Frequência, Conteúdo ou Promoção;
- migra os 881 casos `NO_CANONICAL_TEMPLATE`;
- resolve o `COURSE_UNRESOLVED` ou o `LEGACY_DUPLICATE`;
- autoriza apply;
- fecha a issue #250.

A futura fase de backfill deve exigir autorização humana explícita separada e
referenciar simultaneamente o target count, `sealed_bundle_sha256` e o digest do
artifact privado desta fase.
