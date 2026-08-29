# P0-F7.9C1 — Auditoria curricular paginada por escola

Data: 2026-08-29

## Estado de entrada

A P0-F7.9C0 foi selada com `STATUS=PASS` para 2026:

- escolas: 23;
- turmas: 234;
- turmas sem nível explícito: 13;
- teacher_assignments: 2220;
- teacher_assignments ativos: 2220;
- componentes: 71;
- estratégia obrigatória: `PAGED_BY_SCHOOL_SNAPSHOT`.

Nenhuma remediação histórica foi executada.

## Objetivo

Quantificar, em toda a rede e com baixo impacto operacional, os vínculos docentes que hoje seriam aceitos ou bloqueados pela fronteira de integridade curricular P0-F7.9B.

## Arquitetura

### Referência global pequena

Um coletor read-only executa exatamente duas consultas bounded e tenant-scoped:

1. escolas, com `id`, `name` e `mantenedora_id`;
2. componentes, somente com os metadados curriculares necessários.

Limites: no máximo 50 escolas e 150 componentes. Os totais devem coincidir exatamente com o inventário P0-F7.9C0.

### Página por escola

É gerado localmente um coletor independente para cada escola da referência. Cada página executa exatamente quatro consultas:

1. `countDocuments` de turmas da escola/ano;
2. `countDocuments` de teacher_assignments da escola/ano;
3. leitura bounded das turmas mínimas;
4. leitura bounded dos teacher_assignments mínimos.

Limites fail-closed por escola:

- 100 turmas;
- 600 teacher_assignments.

Se qualquer escola ultrapassar um limite, o coletor daquela escola falha antes da leitura dos documentos e deve ser subdividido em uma etapa posterior; o limite nunca é ampliado automaticamente.

## Minimização de dados

Não são coletados estudantes, matrículas, notas, frequência ou identidade do professor. `staff_id`, nome, CPF, e-mail e outros campos de identidade docente não fazem parte do snapshot P0-F7.9C1.

Os teacher_assignments contêm somente os identificadores técnicos necessários para classificar o vínculo e permitir eventual remediação futura auditável.

## SSoT curricular

O analisador offline não replica `_curricular_fit` nem regras de compatibilidade. Cada vínculo é classificado chamando `validate_teacher_assignment_curriculum` de `services.teacher_assignment_integrity`, exatamente a fronteira introduzida pela P0-F7.9B.

Códigos como `TEACHER_ASSIGNMENT_LEVEL_MISMATCH`, `TEACHER_ASSIGNMENT_CLASS_LEVEL_REQUIRED`, `TEACHER_ASSIGNMENT_SERIES_MISMATCH` e `TEACHER_ASSIGNMENT_SERIES_SCOPE_REVIEW_REQUIRED` são, portanto, os mesmos códigos de bloqueio do writer atual.

Vínculos cujo registro de turma ou componente não esteja disponível na fotografia recebem códigos exclusivamente forenses `AUDIT_CLASS_RECORD_MISSING` ou `AUDIT_COURSE_RECORD_MISSING`.

## Contratos de fechamento

A análise só retorna `PASS` se:

- as 23 escolas tiverem exatamente uma página;
- tenant e ano forem idênticos em todas as cadeias;
- as páginas estiverem encadeadas por SHA à referência e ao P0-F7.9C0;
- a soma de turmas for exatamente 234;
- a soma de teacher_assignments for exatamente 2220;
- a soma de ativos for exatamente 2220;
- a contagem de turmas sem nível explícito for exatamente 13;
- a referência contiver exatamente 71 componentes;
- não houver IDs duplicados entre páginas.

## Saída

O relatório final agrega:

- compatíveis;
- incompatíveis/bloqueados por código de integridade;
- totais por escola;
- quantidade ativa de `educacao_infantil -> eja_final`;
- achados individuais somente dos vínculos não compatíveis, sem identidade docente.

## Segurança

- produção: apenas `mongosh` read-only bounded;
- Python em produção: proibido;
- backend `exec` para análise: proibido;
- escrita MongoDB: zero;
- restart de MongoDB, Docker ou host: proibido;
- remediação histórica: zero nesta fase.

A P0-F7.9C1 é somente diagnóstico. Qualquer P0-F7.9D de correção histórica exige etapa separada, plano de remediação, rollback e autorização explícita de escrita em produção.
