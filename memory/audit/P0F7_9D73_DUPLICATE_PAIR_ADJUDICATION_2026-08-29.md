# P0-F7.9D7.3 — Adjudicação do par duplicado e plano revisado

Data: 2026-08-29

## Estado de entrada confirmado

A P0-F7.9D7.2 foi executada contra produção em modo bounded read-only e analisada offline.

Resultado operacional confirmado:

- `status = PASS`;
- `classification = ACTIVE_DUPLICATE_SEMANTIC_PAIR_REQUIRES_CONSOLIDATION`;
- 2 `teacher_assignments` ativos;
- mesmo professor, escola, turma e ano;
- 1 grupo de colisão;
- divergência de `carga_horaria_semanal` preservada;
- 5 de 5 queries executadas;
- zero mutação;
- zero write;
- zero dado de estudante.

Relatório D7.2 real selado:

`228e809edbe151797b055f12c467243e9b5db1db6bb64107a3f27fd83b1d7ea3`

A D7.3 recusa qualquer D7.2 com SHA diferente.

## Objetivo

Converter a conclusão forense em uma adjudicação humana explícita e, somente se as duas decisões forem resolvidas, construir um plano revisado determinístico e não executável.

As decisões são independentes:

1. **survivor** — qual dos dois vínculos permanece ativo;
2. **workload** — qual dos dois valores semanais já existentes no par deve prevalecer.

Nenhum algoritmo escolhe automaticamente qualquer uma das duas decisões.

## Regra de aposentadoria do duplicado

O código de produção atual bloqueia hard delete de `teacher_assignments` e orienta encerramento/inativação de passivo histórico por atualização de status.

Assim, a D7.3 fixa:

- hard delete proibido;
- vínculo não sobrevivente planejado para `status = inativo`;
- curso e carga históricos do vínculo aposentado não são reescritos pela adjudicação;
- qualquer execução futura deve ser auditável e protegida por CAS.

## Estação privada offline

O comando `Build` gera:

- HTML autocontido, com `connect-src 'none'`;
- template JSON da decisão.

A estação mostra, para cada membro do par:

- `assignment_id`;
- ordinal D4/D7.1;
- componente de origem;
- carga semanal atual;
- datas de criação/atualização;
- resumo de auditoria;
- slots do componente de origem.

Slots são apenas evidência operacional e não equivalem automaticamente a horas semanais.

A exportação humana exige:

- responsável institucional;
- confirmação de autoridade;
- decisão de survivor ou `DEFER`;
- justificativa do survivor quando selecionado;
- decisão de workload entre os valores já existentes ou `DEFER`;
- justificativa de workload quando selecionado;
- confirmação explícita de inativação do não sobrevivente.

A exportação mantém obrigatoriamente:

- `production_write_authorized = false`;
- `executor_authorized = false`.

## Plano revisado

Se survivor ou workload permanecerem adiados:

- o manifesto pode ser selado;
- `revised_plan_ready = false`;
- `operations = []`;
- executor permanece bloqueado.

Se ambas as decisões forem resolvidas, a D7.3 constrói exatamente:

1. 21 operações `REMAP_COURSE` das entradas não colidentes da D7.1;
2. 1 operação `RETIRE_DUPLICATE_ASSIGNMENT`, alterando somente `status -> inativo`;
3. 1 operação `CONSOLIDATE_SURVIVOR`, alterando `course_id` para o target compartilhado e, somente se necessário, `carga_horaria_semanal` para o valor humano selecionado.

Total planejado: **23 updates documentais**.

Esse total numericamente igual ao lote histórico não reutiliza a autorização anterior. O conteúdo, a ordem, as pré-condições e as mutações são diferentes.

## Ordenação fail-closed

Dentro do par:

`RETIRE_DUPLICATE_ASSIGNMENT` deve ocorrer antes de `CONSOLIDATE_SURVIVOR`.

Isso evita criar temporariamente dois vínculos ativos no mesmo tuple futuro.

Rollback futuro deve ocorrer em ordem inversa.

## Próximos gates obrigatórios

Mesmo com `revised_plan_ready = true`, a D7.3 ainda não autoriza produção.

Antes de qualquer write são obrigatórios:

1. novo last-mile preflight contra o estado atual;
2. novo CAS dry-run do plano revisado;
3. validação de pós-condições e rollback;
4. cálculo e selagem do executor revisado;
5. **nova autorização humana explícita para escrita em produção**.

A antiga autorização de 23 writes é formalmente não reutilizável.

## Segurança

- `PRODUCTION_ACCESS=NO`;
- `DATABASE_ACCESS=NO`;
- `DATABASE_MUTATION=NO`;
- `PRODUCTION_WRITES=NO`;
- `EXECUTOR_AUTHORIZED=NO`;
- zero SSH/SCP/Docker/mongosh no wrapper;
- zero cliente de banco ou rede no adjudicador;
- zero dado de estudante;
- `staff_id` não é exposto;
- hard delete proibido.
