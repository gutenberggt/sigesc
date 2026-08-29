# P0-F7.9 — Adjudicação de Componente Curricular

Data: 2026-08-28

## Objetivo

Converter os resultados consolidados da P0-F7.8.2 em decisões explícitas de componente curricular, preservando a separação entre decisão de componente, decisão de carga horária e qualquer futura execução em produção.

A fase é integralmente offline. Ela consome somente os relatórios privados P0-F7.5 e P0-F7.8.2 já existentes no computador do responsável.

## Estado de entrada obrigatório

A P0-F7.8.2 deve estar em `PASS`, com:

- 3 casos documentados;
- `snapshot_drift_cases = 0`;
- zero leitura de estudantes, matrículas, notas e frequência;
- zero mutação;
- zero decisão automática de carga horária;
- executor não autorizado.

As políticas de entrada são fixadas pela cadeia anterior:

1. Caso 1 — `STRONG_CURRICULAR_PREFERENCE_SOURCE`;
2. Caso 2 — `BOTH_CURRICULARLY_INCOMPATIBLE_REQUIRES_ADJUDICATION`;
3. Caso 3 — `BOTH_REVIEW_TIER_REQUIRES_ADJUDICATION`.

Qualquer alteração nesses estados bloqueia a P0-F7.9.

## Tratamento por caso

### Caso 1

A preferência curricular técnica por `source` é transportada como resultado técnico da SSoT. Não há decisão humana de componente nesta fase para esse caso, porque a P0-F7.8.2 já confirmou rank curricular forte para `source` e ausência de preferência forte no `target`.

Isso não constitui autorização de banco, remapeamento, exclusão ou alteração de carga horária.

### Caso 2

`source` e `target` possuem `LEVEL_MISMATCH`. Portanto, a estação não permite selecionar nenhum deles.

A decisão humana permitida é:

- selecionar um candidato alternativo de mesmo nome e nível exato já presente no relatório P0-F7.8.2; ou
- adiar a decisão e exigir revisão cadastral do escopo curricular.

O candidato alternativo não é injetado automaticamente pelo resolver e continua sujeito a decisão institucional.

### Caso 3

`source` e `target` permanecem em rank curricular de revisão. A estação permite:

- selecionar `source`;
- selecionar `target`;
- adiar a decisão e exigir revisão cadastral do escopo curricular.

A evidência histórica de identidade pode ser exibida como contexto, mas não é convertida em recomendação automática.

## Exclusão explícita: carga horária

A divergência semanal `2h x 3h` não pode ser decidida, registrada ou inferida pela P0-F7.9.

Qualquer decisão de carga horária será uma fase separada, com política própria e evidência institucional própria.

## Estação privada

O comando `build` gera HTML autocontido com CSP `connect-src 'none'`. O navegador não precisa de rede.

A exportação contém somente:

- responsável;
- confirmação de autoridade;
- decisões humanas dos Casos 2 e 3;
- justificativas;
- IDs técnicos necessários à selagem;
- flags explícitas de ausência de decisão de carga e executor.

## Selagem

O comando `seal` valida novamente:

- SHA do P0-F7.5;
- SHA do P0-F7.8.2;
- encadeamento P0-F7.5 -> P0-F7.8.2;
- políticas dos 3 casos;
- decisão permitida para cada caso;
- `selected_course_id` contra o contrato derivado dos relatórios;
- justificativa obrigatória;
- autoridade institucional;
- ausência de decisão de carga;
- ausência de autorização de executor.

O manifesto P0-F7.9 recebe SHA-256 canônico.

## Fronteira operacional

O runner oficial usa inspeção AST para impedir superfície de MongoDB, clientes HTTP, subprocessos remotos e mutadores de banco. O wrapper PowerShell não contém SSH, SCP, Docker, `mongosh` ou chamadas web.

## Invariantes

- `production_access = false`;
- `database_access = false`;
- `database_mutation = false`;
- `workload_decision_performed = false`;
- `production_writes_executed = false`;
- `executor_authorized = false`;
- `not_authorization_for_executor = true`.

## Próxima fase

Se os Casos 2 e 3 forem efetivamente adjudicados, a divergência de carga horária poderá ser tratada em uma fase específica posterior. Se algum caso for adiado, o executor de consolidação continua bloqueado para aquele caso.

Nenhuma escrita em produção é autorizada por este artefato.
