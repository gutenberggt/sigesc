# P0 #250 — F2.10A: política canônica para `LEGACY_ONLY / NO_CANONICAL_TEMPLATE`

## 1. Problema

A F2.9A separou corretamente os casos que podiam herdar, sem hipótese, um envelope
DVD de vínculos irmãos. O dry-run global registrou **881 pares** bloqueados
exclusivamente por `NO_CANONICAL_TEMPLATE` dentro do universo de revisão. Esses
casos possuem alocação pedagógica legada ativa, mas não possuem um vínculo DVD
operacional irmão que permita copiar com segurança perfil, validade, escopo,
substituição, ownership de notas e demais atributos ricos.

A F2.9A tratou corretamente esse estado como não gravável. A F2.10A resolve agora
o problema conceitual: **ausência de template DVD não é, por si só, ausência de
entitlement docente**.

## 2. Decisão arquitetural

A partir desta fase, o SIGESC deve separar formalmente duas dimensões:

1. **Entitlement pedagógico canônico** — prova que um usuário professor está
   alocado a `tenant + escola + ano + turma + componente`.
2. **Envelope operacional DVD** — configura como esse vínculo participa do
   Diário por Vínculo: validade temporal operacional, horários, profile,
   `student_scope`, substituição e ownership oficial de notas.

Consequência: um professor pode possuir **entitlement canônico válido sem DVD
operacional habilitado**. `diary_settings.enabled=false` ou ausência de
`diary_settings` não poderá mais ser interpretada como inexistência de vínculo
pedagógico.

Essa decisão consolida a direção já adotada na F2.8: autorização acadêmica e
capacidade DVD são dimensões diferentes.

## 3. Novo tipo semântico

A F2.10B deverá introduzir um discriminador semântico explícito em
`teacher_class_assignments`:

- `CANONICAL_ENTITLEMENT` — vínculo pedagógico canônico, sem inferir capacidades
  DVD;
- `OPERATIONAL_DVD` — vínculo canônico com envelope DVD explícito e validado;
- `LEGACY_MIGRATION_SYNTHETIC` / variantes — artefatos sintéticos de migração de
  grade, que continuam sem representar ownership pedagógico.

A F2.10A **não altera ainda o schema persistido** e não grava esse discriminador.
Ela apenas torna a política executável em código puro.

## 4. Regra para `NO_CANONICAL_TEMPLATE`

Um caso pode ser promovido de:

`REQUIRES_REVIEW / NO_CANONICAL_TEMPLATE`

para:

`PLAN_CANONICAL_ENTITLEMENT_ONLY`

somente quando `NO_CANONICAL_TEMPLATE` for o **único** motivo de revisão e o
upstream tiver comprovado, de forma unívoca:

- `staff_id -> users.id`;
- papel primário `professor`;
- turma existente e no escopo da fase;
- tenant da turma;
- escola da turma;
- `course_id` exato e existente;
- exatamente uma alocação legada ativa para a chave natural;
- ausência de duplicidade DVD, drift sintético ou colisão de identidade.

Se existir qualquer segundo bloqueador, o caso permanece `KEEP_REVIEW`.

## 5. O que pode ser preservado sem hipótese

O entitlement-only preserva apenas os fatos estruturais já provados:

- `teacher_id = users.id` resolvido;
- `class_id` exato;
- `component_id = teacher_assignments.course_id` exato;
- `mantenedora_id` ancorado na turma;
- `school_id` ancorado na turma;
- `academic_year` do vínculo legado.

Nenhum nome de professor, turma ou componente é usado para remapeamento.

## 6. O que é deliberadamente desconhecido

A F2.10A proíbe defaults para os campos abaixo:

- `diary_settings.profile` (`regular`, `integrator`, `shared`);
- `diary_settings.student_scope`;
- `weekly_slots`;
- `valid_from` e `valid_until` do envelope operacional DVD;
- `is_substitute`;
- `grades_official_owner`;
- `shift`.

Esses campos permanecem `unknown/null` no modelo conceitual de entitlement-only.
A existência de notas, ausência de notas, nome do componente, turno da turma ou
perfil observado em outro contexto **não autoriza inferência automática**.

Em especial:

- presença de notas não transforma automaticamente o caso em `regular`;
- ausência de notas não transforma automaticamente o caso em `integrator`;
- múltiplos professores não transformam automaticamente o vínculo em `shared`;
- `student_scope=all` não deve ser criado apenas porque não existe artefato de
  grupo conhecido.

## 7. Semântica temporal

Para `CANONICAL_ENTITLEMENT`, o escopo institucional primário será
`academic_year`.

A F2.10A não retrodata `valid_from` e não inventa `valid_until`. Esses campos
continuam pertencendo ao envelope operacional DVD.

Isso evita declarar, sem evidência, que um professor tinha responsabilidade
operacional DVD desde 1º de janeiro ou desde o início das aulas. A compatibilidade
histórica de leitura continua separada até a convergência dos leitores.

## 8. Efeito esperado nos módulos

Após a implementação das fases seguintes, a autorização base deverá obedecer a
uma única SSoT de entitlement:

`professor + tenant + ano + escola + turma + componente`

`=> exatamente um CANONICAL_ENTITLEMENT`

Notas, Frequência, Promoção, `/professor/turmas` e Conteúdo deverão consultar a
mesma camada canônica de entitlement.

O DVD passa a responder apenas pela capacidade operacional adicional daquele
entitlement. Assim:

- entitlement existe + DVD regular/shared válido -> usa capacidades DVD;
- entitlement existe + sem DVD -> mantém compatibilidade funcional legada sem
  voltar a decidir autorização pelo legado;
- nenhum entitlement -> fail-closed.

## 9. Relação com a F2.7

A F2.7 continua temporariamente necessária porque ainda combina **origens de
conteúdo** durante o cutover parcial.

A F2.10A não autoriza remover o fallback. A retirada só ocorrerá quando:

1. todos os entitlements elegíveis estiverem canônicos;
2. os leitores deixarem de usar `teacher_assignments` como fonte de autorização;
3. a origem histórica de conteúdo legado tiver estratégia própria de
   compatibilidade/migração;
4. auditoria global comprovar zero gap relevante.

Portanto, devemos separar duas retiradas:

- primeiro: remover o **fallback de autorização** para o legado;
- depois: remover o **fallback de dados históricos**, quando a migração de
  conteúdo estiver concluída.

## 10. Plano de execução posterior

### F2.10B — contrato persistido e resolver canônico

Sem mutação de produção:

- evoluir `teacher_class_assignments` para reconhecer
  `assignment_semantics=canonical_entitlement`;
- adicionar `academic_year` explícito para entitlement-only;
- permitir ausência de `weekly_slots`/validade/diary somente nesse tipo;
- manter requisitos atuais rígidos para `OPERATIONAL_DVD`;
- tornar a classificação semântica retrocompatível;
- criar serviço canônico de entitlement sem conectar ainda todos os leitores.

### F2.10C — planner global read-only

Rerodar o universo após a F2.9C e classificar os atuais casos
`NO_CANONICAL_TEMPLATE` em:

- `PLAN_CANONICAL_ENTITLEMENT_ONLY`;
- `KEEP_REVIEW`.

A contagem histórica de 881 é referência; qualquer executor futuro deverá usar
novo snapshot, novo seal e SHA exato.

### F2.10D — backfill controlado

Somente após autorização explícita de mutação:

- criar entitlements canônicos em lotes selados;
- zero inferência de envelope DVD;
- idempotência por chave natural;
- preflight, CAS/colisão, pós-check, receipt e rollback compensatório.

### F2.10E — convergência dos leitores

Migrar autorização de `/professor/turmas`, Notas, Frequência, Conteúdo e Promoção
para o serviço canônico de entitlement.

### F2.10F — retirada do legado como SSoT de autorização

Somente após auditoria global de paridade:

- zero componente elegível sem entitlement canônico;
- zero duplicidade crítica;
- zero widening de RBAC;
- paridade entre módulos.

`teacher_assignments` poderá então permanecer apenas como compatibilidade
histórica durante a fase final ou ser aposentado por migração específica.

## 11. Boundary da F2.10A

Esta fase contém somente:

- política executável pura;
- testes sintéticos;
- documentação arquitetural;
- guard de CI.

Não altera routers, schemas persistidos, leitores, RBAC ou dados. Não executa
MongoDB, não lê dados de produção, não habilita DVD e não exige deploy funcional.

A issue #250 permanece aberta.
