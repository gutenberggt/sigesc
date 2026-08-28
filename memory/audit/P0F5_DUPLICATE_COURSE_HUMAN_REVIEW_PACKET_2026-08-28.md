# P0-F5 — Pacote privado de revisão humana dos conflitos de courses duplicados

Data: 2026-08-28

## Objetivo

Transformar os conflitos duros identificados pelo P0-F3 e documentados pelo P0-F4 em **unidades explícitas de decisão humana**, sem qualquer alteração no banco e sem recomendação automática de qual valor deve prevalecer.

O P0-F4 demonstrou em produção:

- 68 conflitos duros com cobertura integral;
- 33 conflitos de frequência com proveniência bilateral e auditoria;
- 32 conflitos de conteúdo pedagógico;
- 3 conflitos de nota;
- nenhuma resolução automática autorizada.

O P0-F5 existe porque os metadados de proveniência são evidência, mas não constituem regra institucional para escolher o valor vencedor.

## Princípio de segurança

O P0-F5 é READ-ONLY e deliberadamente separa duas superfícies:

1. **stdout compacto e não sensível** — somente contagens, estados e hashes;
2. **pacote privado** — pode conter nomes de estudantes, notas, frequência e textos pedagógicos necessários à adjudicação humana.

O arquivo privado é obrigatório e gravado com permissão `0600`.

## Unidade de revisão

Cada conflito P0-F4 deve gerar ao menos uma unidade humana de revisão.

### Notas

Uma unidade por campo efetivamente divergente (`b1`, `b2`, `b3`, `b4`, recuperações, observações etc.).

A unidade contém:

- contexto de escola/turma/estudante;
- documento source e target;
- valor source e valor target;
- autoria técnica quando disponível;
- contrato de decisão vazio.

### Frequência

Uma unidade por estudante com valor divergente no mesmo contexto lógico `(turma, data, período, aula_numero)`.

Também são criadas unidades separadas para divergências documentais em `observations` e `number_of_classes`.

Estudantes presentes apenas de um lado não são tratados como conflito duro pelo P0-F3 e não recebem decisão no P0-F5; esses casos permanecem candidatos à união determinística em fase posterior.

### Objetos de conhecimento

Uma unidade por campo pedagógico divergente na mesma `(turma, data)`.

Pode envolver texto, listas de habilidades/adaptações, metodologia, recursos, evidência de aprendizagem etc. Nenhuma concatenação ou união é sugerida automaticamente.

## Decisões permitidas

O pacote apenas declara as opções de revisão:

- `KEEP_SOURCE`
- `KEEP_TARGET`
- `MANUAL_RECONCILIATION`

Todos os itens saem com `decision = null` e `status = PENDING_HUMAN_DECISION`.

O P0-F5 não é um arquivo executável de decisões e não pode ser consumido diretamente por qualquer executor futuro.

## Fail-closed

O status só pode ser `PASS` quando:

- o P0-F4 corrente também estiver `PASS`;
- todos os conflitos P0-F4 forem encontrados;
- todos puderem ser convertidos em pelo menos uma unidade de revisão;
- não houver multiplicidade ou forma de conflito não suportada pelo pacote.

Caso contrário:

`BLOCKED_INCOMPLETE_HUMAN_REVIEW_PACKET`

## Privacidade

O pacote privado pode conter dados educacionais pessoais e, portanto:

- nunca é impresso integralmente no terminal;
- não é enviado para GitHub Actions;
- não é anexado ao PR;
- não deve ser publicado em subdomínio ou diretório web;
- deve permanecer sob controle do operador em área restrita;
- o comando de produção deverá preservar SHA-256 e permissões do arquivo.

## Fora de escopo

O P0-F5 não:

- altera `courses`;
- altera notas;
- altera frequência;
- altera objetos de conhecimento;
- altera horários;
- altera vínculos docentes;
- cria alias ou merge de courses;
- escolhe automaticamente o lado source ou target;
- implementa executor;
- toca AEE.

## Próxima etapa após homologação

Após a execução em produção será possível medir quantas **unidades humanas de decisão** existem de fato. Somente então deverá ser definida a forma de adjudicação — por exemplo, pacote revisável, planilha assinada ou interface administrativa temporária.

Um executor de consolidação só poderá existir depois de:

1. decisões humanas completas e validadas;
2. plano determinístico por coleção;
3. backup imutável;
4. CAS/preconditions;
5. rollback;
6. pós-validação;
7. PR e CI próprios;
8. autorização humana explícita para merge;
9. autorização humana **separada** para escrita em produção.
