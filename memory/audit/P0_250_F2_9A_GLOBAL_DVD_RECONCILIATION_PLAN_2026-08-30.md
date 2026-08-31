# P0 #250 — F2.9A: planner/dry-run global de reconciliação docente/DVD

## Contexto

A F2.8 mediu globalmente o passivo entre `teacher_assignments` e
`teacher_class_assignments` para 2026. O resultado confirmou que o cutover ainda é
parcial: existem pares elegíveis já cobertos pelo DVD e uma população relevante
que permanece somente no legado ou exige revisão estrutural.

A F2.9A não corrige dados. Ela converte o inventário em um **plano determinístico
read-only**, separando o subconjunto que pode ser derivado sem hipótese dos casos
que precisam de decisão humana ou saneamento prévio.

## Objetivo

Para cada chave legada ativa:

`staff_id + class_id + course_id + academic_year`

o planner decide uma única ação lógica:

- `NOOP_ALREADY_CANONICAL`;
- `PLAN_CREATE_CANONICAL_ASSIGNMENT`;
- `NOOP_OUT_OF_DVD_SCOPE`;
- `REQUIRES_REVIEW`.

Nenhuma dessas decisões é executada pela F2.9A.

## Regras de derivação segura

Uma criação só é planejada quando todas as condições abaixo são simultaneamente
verdadeiras:

1. existe exatamente uma alocação legada ativa para a chave natural;
2. `staff_id -> users.id` resolve de forma unívoca;
3. o usuário mantém papel primário `professor`;
4. turma está no escopo DVD v1 e, quando declarado, pertence a 2026;
5. tenant e escola da turma estão resolvidos e compatíveis com usuário, lotação e
   eventuais campos persistidos no legado;
6. `course_id` existe de forma unívoca no tenant compatível;
7. não há artefato `legacy_migration` em drift colidindo com a turma/componente;
8. não existe vínculo operacional DVD válido cobrindo aquele componente;
9. existem vínculos operacionais DVD válidos irmãos na mesma turma;
10. todos os irmãos válidos produzem **um único envelope canônico efetivo**.

O componente é preservado pelo `course_id` exato. Nome de componente nunca é
usado para remapeamento.

## Envelope canônico

A criação planejada herda somente campos cuja semântica já é canônica e cuja
combinação é unívoca entre os irmãos válidos:

- `valid_from`;
- `valid_until`;
- `diary_settings.enabled`;
- `diary_settings.schema_version`;
- `diary_settings.profile`;
- `diary_settings.student_scope`;
- `is_substitute`;
- `grades_official_owner`;
- `shift`, quando presente.

Tenant e escola **não** são copiados de outro vínculo: são ancorados na turma.
`teacher_id` vem do `users.id` resolvido. `component_id` vem do `course_id` legado
exato.

Se os irmãos válidos divergirem em validade, perfil, escopo, substituição,
propriedade oficial de notas ou turno, o planner retorna
`AMBIGUOUS_CANONICAL_TEMPLATE` em vez de escolher arbitrariamente.

Campos desconhecidos em `diary_settings` também bloqueiam automação com
`UNSUPPORTED_TEMPLATE_FIELDS`, preservando compatibilidade futura de schema.

## Classes legado-only

`LEGACY_ONLY_CLASS` não possui vínculo DVD operacional válido na turma capaz de
fornecer um envelope canônico. A F2.9A **não inventa**:

- perfil (`regular`, `integrator`, `shared`);
- validade;
- escopo de estudantes;
- substituição;
- proprietário oficial de notas.

Esses casos ficam `REQUIRES_REVIEW / NO_CANONICAL_TEMPLATE`.

## Separação semântica de `teacher_class_assignments`

O planner reutiliza `teacher_class_assignment_semantics.py` para impedir que
linhas sintéticas de `source=legacy_migration` sejam tratadas como propriedade
pedagógica DVD. Apenas `OPERATIONAL_DVD` pode servir de cobertura ou template.
`LEGACY_MIGRATION_DRIFT` relevante bloqueia criação automática.

## Idempotência planejada

Cada criação recebe internamente um ID determinístico UUIDv5 derivado de:

`academic_year + tenant + school + teacher(user) + class + component`

com namespace estável específico da F2.9A. Repetir o planner no mesmo estado gera
o mesmo target lógico.

Além disso, o resultado produz três seals SHA-256:

- `input_state_sha256`: estado estrutural lido;
- `plan_sha256`: payloads das criações planejadas;
- `decision_manifest_sha256`: todas as decisões por chave natural.

Os payloads e IDs que compõem esses hashes permanecem internos. O snapshot público
emite somente contagens, classificações e hashes.

## Motivos de revisão

A F2.9A pode classificar como `REQUIRES_REVIEW`:

- `CLASS_NOT_FOUND`;
- `CLASS_YEAR_MISMATCH`;
- `LEGACY_DUPLICATE`;
- `IDENTITY_UNRESOLVED`;
- `USER_ROLE_NOT_PROFESSOR`;
- `TENANT_SCOPE_UNRESOLVED`;
- `SCHOOL_SCOPE_MISSING`;
- `LEGACY_SCHOOL_MISMATCH`;
- `LEGACY_TENANT_MISMATCH`;
- `COURSE_UNRESOLVED`;
- `COURSE_AMBIGUOUS`;
- `LEGACY_MIGRATION_DRIFT`;
- `DVD_DUPLICATE_COVERAGE`;
- `DVD_PRESENT_INVALID`;
- `NO_CANONICAL_TEMPLATE`;
- `AMBIGUOUS_CANONICAL_TEMPLATE`;
- `UNSUPPORTED_TEMPLATE_FIELDS`;
- `TARGET_ID_COLLISION`.

Nenhum desses estados é auto-corrigido.

## Classificação global

O dry-run retorna uma das classificações:

- `GLOBAL_DVD_RECONCILIATION_PLAN_READY` — há criações seguras e zero revisão;
- `GLOBAL_DVD_RECONCILIATION_PLAN_PARTIAL_REVIEW_REQUIRED` — há criações seguras
  e também casos bloqueados;
- `GLOBAL_DVD_RECONCILIATION_PLAN_REVIEW_ONLY` — nenhum create seguro e há revisão;
- `GLOBAL_DVD_RECONCILIATION_PLAN_CLEAN` — não há create nem revisão pendente no
  universo avaliado.

Mesmo `PLAN_READY` **não autoriza escrita**.

## Boundary de produção

O workflow de produção da F2.9A só pode ser disparado por issue criada pelo owner
com SHA exato de `main` e confirmação literal. Ele:

- acessa MongoDB somente para leitura;
- não chama HTTP da aplicação;
- não lê notas, frequência, conteúdo ou estudantes;
- não emite IDs, PII ou payloads do plano;
- não contém mutadores MongoDB;
- grava como artefato apenas o snapshot agregado;
- comenta o agregado na issue #250;
- encerra somente a issue-gate temporária, nunca a #250.

A execução real do backfill pertence a uma fase posterior e requer autorização
humana explícita separada, com preflight, seal, contagem esperada, snapshot,
CAS/idempotência, pós-check e rollback compensatório quando aplicável.

## Limites desta PR

Esta PR contém somente:

- planner read-only;
- regressões sintéticas;
- workflow owner-only/exact-SHA para dry-run;
- documentação.

Não altera routers, frontend, RBAC, notas, frequência, conteúdo ou promoção. Não
faz deploy funcional e não executa mutação em produção.
