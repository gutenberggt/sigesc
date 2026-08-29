# P0-F7.9D5 — Last-mile execution preflight

Data: 2026-08-29

## Objetivo

Revalidar, imediatamente antes do desenho do executor de remediação, os 23 vínculos selados pela P0-F7.9D4. A etapa continua read-only e não autoriza nem executa escrita em produção.

## Fonte selada

A entrada exclusiva é o plano P0-F7.9D4 `SEALED_PROPOSAL_ONLY_NON_EXECUTABLE`, com 23 entradas e `plan_sha256` válido.

## Snapshot mínimo de produção

O coletor gerado localmente executa exatamente cinco leituras/comandos:

1. `hello` sanitizado para classificar a topologia MongoDB;
2. `countDocuments` do subconjunto estrutural de `teacher_assignments`;
3. `find` bounded dos vínculos-fonte e possíveis colisões de destino;
4. `find` bounded das turmas envolvidas;
5. `find` bounded dos componentes de destino.

Não lê estudantes, matrículas, notas ou frequência. Não lê nome, CPF ou e-mail de professor. `staff_id` é usado apenas para detectar duplicidade lógica professor + turma + componente + ano.

## Revalidações offline

O analisador exige, por entrada:

- vínculo-fonte ainda existente e ativo;
- tenant, escola, turma, ano e `course_id` de origem idênticos ao plano selado;
- `staff_id` presente;
- inexistência de vínculo ativo do mesmo `staff_id` para o componente-alvo na mesma turma/ano;
- turma atual ainda existente e no mesmo escopo;
- componente-alvo atual ainda existente;
- aceitação do componente-alvo pela função canônica `validate_teacher_assignment_curriculum`;
- política de escrita atual igual à política selada.

Classificações possíveis:

- `CLEAR_FOR_EXECUTION_AUTHORIZATION`;
- `ACTIVE_TARGET_ALREADY_EXISTS`;
- `SOURCE_DRIFT_REVIEW_REQUIRED`;
- `TARGET_CURRICULUM_REJECTED`.

## Topologia e estratégia futura

A D5 não presume transação. O `hello` determina a estratégia obrigatória para uma fase futura e separadamente autorizada:

- replica set com sessões e wire version compatível: `MONGODB_MULTI_DOCUMENT_TRANSACTION_REQUIRED`;
- cluster sharded compatível: `MONGODB_MULTI_DOCUMENT_TRANSACTION_REQUIRED`;
- standalone ou transação indisponível: `CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED`.

Nenhum executor é incluído nesta etapa.

## Invariantes de segurança

- produção: READ-ONLY;
- query budget: 5;
- `teacher_assignments` bounded em 200 registros;
- turmas bounded em 50;
- componentes bounded em 50;
- sem Python/backend exec em produção;
- sem escrita MongoDB;
- sem remediação;
- reutilização da SSoT curricular vigente;
- política `FAIL_CLOSED_NO_PARTIAL_GUESSING`;
- escrita futura exige autorização explícita separada.
