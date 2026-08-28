# P0-F3 — Análise Semântica de Colisões de Componentes Duplicados

Data: 2026-08-28  
Modo: **READ-ONLY**  
Base: `main@27bf0ae81b6965b4ba7fa2e99c5520956855b9af`

## 1. Contexto

O P0-F confirmou três grupos nominais duplicados em produção, todos com dois IDs atuais referenciados: Ciências, Geografia e História. O P0-F2 encontrou candidato histórico mantido único nos três grupos, mas também 177 sinais conservadores de sobreposição e 36 documentos compartilhados.

Esses sinais não podem ser usados diretamente como prova de colisão: o P0-F2 deliberadamente emprega escopos amplos. Em especial, `class_schedules` armazena a grade inteira da turma no mesmo documento, e frequência de Anos Finais distingue aulas por `aula_numero`.

## 2. Objetivo

Refinar o P0-F2 com as chaves de negócio efetivamente observadas nos writers do SIGESC, sem modificar nenhum dado e sem declarar nenhum par automaticamente seguro para consolidação.

## 3. Semânticas auditadas

### Grades
Writer: `(student_id, class_id, course_id, academic_year)`.

Após colapsar o componente, P0-F3 compara registros com a mesma chave restante `(student_id, class_id, academic_year)` e classifica campos `dependency_id`, `b1..b4`, `rec_s1`, `rec_s2`, `recovery` e `observations` como:
- `EXACT_EQUIVALENT`;
- `COMPLEMENTARY_MERGEABLE`;
- `VALUE_CONFLICT`;
- `MULTIPLICITY_CONFLICT`.

Valores de notas não aparecem nos exemplos do manifesto nem no resumo compacto.

### Attendance — Anos Finais
Writer canônico: turma + data + componente, com `period` quando não regular e `aula_numero` para Anos Finais/EJA final.

Após colapsar o componente, a chave analisada é `(class_id, date, period(default=regular), aula_numero)`. Registros dos alunos são comparados por `student_id` usando apenas status e `dependency_id` para determinar compatibilidade ou conflito. Nenhum nome de aluno é emitido.

### Learning objects
Writer impede duplicidade em `(class_id, course_id, date)`. Após colapso, a chave é `(class_id, date)`.

O conteúdo pedagógico é comparado internamente nos campos persistidos, mas o relatório expõe apenas hash de chave, IDs de documento e nomes dos campos divergentes — nunca o texto pedagógico.

### Teacher assignments
O writer impede vínculo ativo repetido para `(staff_id, class_id, course_id, academic_year)`. P0-F3 verifica colisões ativas após colapso, distinguindo vínculos ordinários, substituições e metadados divergentes.

### Teacher class assignments / DVD
A coleção permite múltiplos vínculos. A colisão real é calculada pela própria semântica operacional do módulo: mesmo professor + mesma turma + vigência sobreposta + slot semanal sobreposto. Coexistência sem interseção temporal/horária não é tratada como colisão.

### Class schedules
Um mesmo documento pode conter ambos os IDs sem erro. P0-F3 só sinaliza colisão material quando slots dos dois IDs ocupam o mesmo `(dia, número da aula)`. Slots distintos no mesmo documento são coexistência normal.

### Student dependencies
A regra do writer é `(student_id, course_id, origin_academic_year, status=active)`. Após colapso, a chave é `(student_id, origin_academic_year, status=active)`.

## 4. Fail-closed

`COURSE_REFERENCE_SPECS` continua sendo a SSoT das referências persistentes. Caso uma coleção registrada tenha referências aos pares e não possua analisador semântico nesta fase, o grupo é classificado `UNANALYZED_REFERENCES_BLOCKED`.

## 5. Classificações de grupo

- `NO_UNIQUE_HISTORICAL_KEPT_BLOCKED`
- `UNANALYZED_REFERENCES_BLOCKED`
- `SEMANTIC_DATA_CONFLICTS_FOUND_BLOCKED`
- `SEMANTIC_COLLISIONS_REQUIRE_DETERMINISTIC_PLAN`
- `NO_SEMANTIC_COLLISIONS_REQUIRES_REVIEW`

**Nenhuma classificação significa `SAFE_TO_MERGE`.**

## 6. Segurança

- sem `--apply`;
- sem `--rollback`;
- sem mutadores MongoDB;
- sem remapeamento;
- sem merge de documentos;
- sem exclusão, criação ou desativação de cursos;
- sem alteração de writers;
- sem alteração em AEE;
- valores pedagógicos sensíveis redigidos dos exemplos compactos;
- qualquer executor futuro exige PR próprio, backup imutável, manifesto, CAS, rollback, pós-check e autorização humana separada para escrita em produção.
