# P0-F7.9D7.2 — Forense read-only do par duplicado

Data: 2026-08-29

## Origem

A primeira execução autorizada da P0-F7.9D7 aplicou 21 CAS, detectou `P0F79D7_IMMEDIATE_COLLISION` no ordinal 22 e executou rollback compensatório integral: 21 forward writes e 21 rollback writes. A P0-F7.9D7.1 comprovou a causa: duas propostas de Geografia da turma `MULTI 3º E 4º ETAPA` convergem para o mesmo tuple futuro `staff + escola + turma + target_course + ano`.

A P0-F7.9D7.1 selou:

- 23 propostas totais;
- 21 não colidentes;
- 2 bloqueadas;
- 1 grupo de colisão;
- `execution_gate_open=false`.

## Objetivo

A P0-F7.9D7.2 coleta somente evidência necessária para adjudicar o par bloqueado. Ela não decide automaticamente qual `teacher_assignment` sobrevive e não decide automaticamente a divergência de `carga_horaria_semanal`.

O coletor bounded mongosh lê apenas:

1. os dois `teacher_assignments` bloqueados;
2. resumos de `audit_logs` desses dois documentos;
3. a turma afetada;
4. os três `courses` envolvidos (dois sources e o target compartilhado);
5. `class_schedules` somente para contagem de slots por course_id.

Não lê estudantes, matrículas, notas ou frequência.

## Contrato de saída

O analisador offline confirma ou bloqueia:

- mesmo professor sem expor `staff_id` no relatório;
- mesma escola/turma/ano;
- ambos ativos;
- ausência de substituição;
- course_ids ainda iguais aos sources selados;
- target compartilhado único;
- divergência semanal ainda presente;
- continuidade temporal/auditável de cada documento;
- contagem de slots por componente como evidência operacional, sem convertê-la em carga horária.

A classificação esperada é:

`ACTIVE_DUPLICATE_SEMANTIC_PAIR_REQUIRES_CONSOLIDATION`

## Decisões deliberadamente não automáticas

A etapa mantém separadas duas decisões humanas:

1. **survivor** — qual dos dois `teacher_assignments` deve permanecer como o único vínculo ativo após uma futura consolidação;
2. **workload** — qual valor semanal deve prevalecer na consolidação (`2h` versus `3h`), caso uma política/canonicidade posterior determine alteração.

A identidade curricular já apontada para o caso EJA não é usada como autorização automática para escolher o documento sobrevivente nem para converter carga anual/slots em carga semanal.

## Segurança

- collector somente read-only;
- query budget fixo = 5;
- analyzer exclusivamente offline;
- zero Python em produção;
- zero writer primitive;
- zero student data;
- `staff_id` usado somente internamente para confirmar mesma pessoa e omitido do relatório;
- nenhuma reutilização da antiga autorização de 23 writes;
- qualquer plano revisado exigirá nova autorização explícita de escrita em produção.
