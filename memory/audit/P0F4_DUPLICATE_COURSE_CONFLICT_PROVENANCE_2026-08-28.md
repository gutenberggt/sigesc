# P0-F4 — Dossiê de Proveniência dos Conflitos de Cursos Duplicados

Data: 2026-08-28  
Modo: **READ-ONLY**

## 1. Contexto

O P0-F3 refinou os sinais conservadores do P0-F2 e confirmou conflitos semânticos reais nos três grupos duplicados de `courses` dos Anos Finais.

Resultado de produção que motivou esta fase:

- 3 grupos com candidato histórico único;
- 68 `hard_conflicts`;
- 183 `collision_items`;
- 0 referências em coleções não analisadas;
- classificação dos 3 grupos: `SEMANTIC_DATA_CONFLICTS_FOUND_BLOCKED`.

A distribuição observada foi:

- Ciências: 20 conflitos duros em `learning_objects`;
- Geografia: 1 conflito de nota, 9 de frequência e 1 de objeto de conhecimento;
- História: 2 conflitos de nota, 24 de frequência e 11 de objetos de conhecimento.

Esses números são evidência de diagnóstico. Nenhum deles autoriza consolidação.

## 2. Objetivo

O P0-F4 não resolve os conflitos. Ele produz um dossiê técnico para apoiar uma futura decisão institucional, reunindo somente metadados seguros de proveniência e auditoria dos documentos envolvidos nos conflitos duros identificados pelo P0-F3.

## 3. Princípio central

Não existe, no contrato atual do SIGESC, uma regra geral dizendo que:

- o documento mais novo vence;
- o documento mais antigo vence;
- o UUID historicamente mantido vence;
- o usuário que atualizou por último vence;
- o registro com mais eventos de auditoria vence.

Portanto, timestamps e trilhas de auditoria são **evidência**, não regra automática de autoridade pedagógica.

## 4. Dados permitidos no dossiê

O P0-F4 trabalha com allow-list explícita de metadados, incluindo, quando existentes:

- IDs técnicos de documento, curso, turma, escola, estudante e vínculo;
- ano letivo, data, período e número da aula;
- `created_at`, `updated_at`, `created_by`, `updated_by`, `recorded_by`;
- `version`, `assignment_id`, `source`;
- metadados de migração;
- `copied_from_id` e `copied_at`;
- contagem e intervalo temporal dos eventos de auditoria;
- quantidade de atores distintos e ações de auditoria.

## 5. Dados proibidos no dossiê

Não podem ser emitidos pelo P0-F4:

- valores `b1`, `b2`, `b3`, `b4`, recuperações ou médias;
- status individuais de presença/falta;
- arrays `records` de frequência;
- textos de `content`, `observations`, `methodology`, `resources`;
- habilidades, adaptações ou evidências pedagógicas;
- `old_value` ou `new_value` de logs de auditoria.

## 6. Estados de proveniência

Cada conflito recebe apenas uma classificação de disponibilidade de evidência:

- `BILATERAL_PROVENANCE_WITH_AUDIT`;
- `BILATERAL_PROVENANCE_NO_COMPLETE_AUDIT`;
- `PARTIAL_PROVENANCE`;
- `SPARSE_PROVENANCE`.

Nenhum desses estados escolhe fonte ou destino como vencedor.

## 7. Requisitos de resolução

Os conflitos são separados por necessidade institucional:

- `PEDAGOGICAL_GRADE_DECISION_REQUIRED`;
- `ATTENDANCE_DECISION_REQUIRED`;
- `PEDAGOGICAL_CONTENT_DECISION_REQUIRED`;
- `SCHEDULE_DECISION_REQUIRED`;
- `UNSUPPORTED_CONFLICT_TYPE_BLOCKED`.

## 8. Gate de completude

O P0-F4 chama o P0-F3 com limite amplo de exemplos e exige que a quantidade de conflitos documentados seja exatamente igual ao total de `hard_conflicts` encontrado na execução corrente do P0-F3.

Se isso não ocorrer, o status será:

`BLOCKED_INCOMPLETE_CONFLICT_COVERAGE`

Não haverá inferência para preencher lacunas.

## 9. Invariantes

- sem `--apply`;
- sem `--rollback`;
- sem mutadores MongoDB;
- sem alteração de writers;
- sem remapeamento de `course_id`/`component_id`;
- sem criação, exclusão ou desativação de cursos;
- sem escolha automática de curso canônico;
- sem decisão automática sobre nota, frequência ou conteúdo;
- sem alteração no AEE;
- `database_mutation = false` em todas as saídas.

## 10. Próxima etapa possível

Somente depois da execução do P0-F4 em produção e da leitura do dossiê será possível projetar uma matriz de resolução institucional P0-F5.

Essa futura matriz deverá separar, no mínimo:

1. conflitos que exigem decisão pedagógica humana;
2. registros equivalentes que poderão ser deduplicados mecanicamente;
3. registros complementares que poderão ser unidos por regra explícita;
4. conflitos de vínculo docente que exigem decisão operacional;
5. qualquer caso sem proveniência suficiente, que continuará fail-closed.

Nenhum executor de escrita deve existir antes dessa classificação e de nova autorização humana explícita.
