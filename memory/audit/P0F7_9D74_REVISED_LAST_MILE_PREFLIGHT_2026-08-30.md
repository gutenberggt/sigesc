# P0-F7.9D7.4 — Last-mile preflight e CAS dry-run do plano revisado

Data: 2026-08-30

## Entrada selada

A etapa consome exclusivamente o relatório selado produzido pela P0-F7.9D7.3.1.

SHA esperado e imutável:

`b6cfcfd3fec964fe58ebdcc7aea6e9fe1953207d7178da35b7e1bd4dea8c39fb`

O relatório deve continuar com:

- `revised_plan_ready = true`;
- `revised_document_updates = 23`;
- `production_write_authorized = false`;
- `database_mutation = false`;
- `production_writes = false`;
- `remediation_executed = false`;
- plano revisado `executable = false`;
- autorização antiga de 23 writes não reutilizável.

## Política curricular encadeada

A cadeia D7.3.1 é validada novamente antes da coleta:

- componente: Geografia;
- nível: `eja_final`;
- séries/etapas: 3 e 4;
- regra multissérie: `MAX_ANNUAL_WORKLOAD`;
- `80ha / 8 = 10hm`;
- `10hm / 5 = 2hs`;
- equivalência `80ha / 40 = 2hs`;
- carga semanal canônica: 2h;
- carga não é escolha humana.

## Plano revisado

A etapa aceita exatamente 23 operações:

1. 21 `REMAP_COURSE`;
2. 1 `RETIRE_DUPLICATE_ASSIGNMENT`;
3. 1 `CONSOLIDATE_SURVIVOR`.

Os dois últimos passos devem permanecer nesta ordem:

`RETIRE_DUPLICATE_ASSIGNMENT -> CONSOLIDATE_SURVIVOR`

O vínculo aposentado só pode receber `status = inativo`; hard delete continua proibido.

## Coletor bounded read-only

`backend/scripts/build_p0f7_9d74_revised_preflight_snapshot_js.py`

O coletor gerado realiza exatamente 5 chamadas de leitura:

1. `hello` para topologia MongoDB;
2. contagem bounded de `teacher_assignments` relevantes;
3. leitura dos vínculos fonte e possíveis colisões de destino;
4. leitura das turmas correntes;
5. leitura dos cursos-alvo correntes.

A projeção de `teacher_assignments` contém apenas campos necessários ao CAS e à detecção estrutural de colisões. Não são lidos nomes de docentes nem dados de estudantes.

Não existe primitiva de escrita no coletor.

## Analisador offline

`backend/scripts/audit_p0f7_9d74_revised_preflight_offline.py`

O analisador:

- não possui cliente MongoDB;
- não possui cliente HTTP/rede;
- valida o SHA exato do plano revisado;
- valida tenant, ano, escola, turma e assignment de cada operação;
- revalida cada `cas_expected`;
- reaplica a SSoT `validate_teacher_assignment_curriculum` para cada operação que muda `course_id`;
- simula as 23 operações na ordem selada;
- detecta colisão ativa no tuple `tenant + ano + escola + turma + staff + course`;
- valida a pós-condição do par duplicado;
- simula rollback em ordem reversa;
- compara `status`, `course_id` e `carga_horaria_semanal` com o estado original depois do rollback.

O relatório somente pode marcar `clear_for_executor_sealing = true` quando:

- 23/23 CAS estiverem claros;
- a simulação forward estiver limpa;
- as pós-condições do par estiverem corretas;
- o rollback reverso restaurar o estado original.

Mesmo nesse caso:

- `production_write_authorized = false`;
- `executor_authorized = false`;
- `database_mutation = false`;
- `production_writes = false`.

## Estratégia de execução futura

A topologia é classificada novamente:

- replica set/sharded com suporte: `MONGODB_MULTI_DOCUMENT_TRANSACTION_REQUIRED`;
- standalone/sem transação: `CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED`.

Nenhum executor é criado nesta etapa.

## Gate seguinte

Somente se a D7.4 real, contra snapshot atual de produção, retornar todos os gates claros deverá ser construída uma etapa separada de selagem do executor revisado.

Essa futura etapa continuará sem autorização automática de escrita em produção. A execução real exigirá autorização humana explícita e específica para o SHA final do executor/plano.

## Segurança

- `DATABASE_MUTATION=NO`;
- `PRODUCTION_WRITES=NO`;
- `EXECUTOR_AUTHORIZED=NO`;
- `REMEDIATION_EXECUTED=NO`;
- zero hard delete;
- zero dado de estudante;
- zero nome de docente;
- fail-closed em qualquer drift de SHA, CAS, currículo, colisão, pós-condição ou rollback.
