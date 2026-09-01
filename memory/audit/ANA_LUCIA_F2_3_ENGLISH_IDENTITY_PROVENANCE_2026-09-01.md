# ANA-LUCIA-F2.3 — Auditoria de Proveniência das Duas Identidades de Língua Inglesa

Data: 2026-09-01  
Modo: **READ-ONLY**  
Professora-alvo: Ana Lucia Faria Pinto  
Ano letivo: 2026  
Escopo nominal: Língua Inglesa / 6º A–D e 9º A–D

## 1. Contexto

A F2.1 demonstrou que oito pares de Língua Inglesa não apresentavam `learning_objects` sob o `course_id` usado pelos vínculos atuais. A F2.2 encontrou histórico atribuível à professora nas mesmas turmas sob outra identidade técnica também denominada “Língua Inglesa”.

A F2.3 deve responder **qual é a proveniência estrutural dessas duas identidades**, sem escolher automaticamente qual documento de `courses` deve sobreviver e sem executar qualquer remapeamento.

## 2. Perguntas obrigatórias

1. Quais documentos de `courses` participam efetivamente dos oito pares?
2. Qual fingerprint está sendo usado pelos vínculos ativos atuais da professora?
3. Qual fingerprint concentra os registros legados 2026 de conteúdo/frequência?
4. O par forma colisão pela identidade nominal P0 `(mantenedora_id, name.casefold(), nivel_ensino.casefold())`?
5. Qual a ordem declarada de `created_at`/`updated_at` dos dois documentos?
6. Há trilha em `audit_logs` para criação/alteração/consolidação desses componentes?
7. Quais coleções persistentes referenciam cada identidade e com que abrangência em 2026?
8. A matriz da turma (`classes.course_ids`), `teacher_assignments`, `teacher_allocations` e `teacher_class_assignments` convergem para a mesma identidade operacional atual?
9. Há linhagem `copied_from_id` que ajude a explicar como o histórico foi associado à identidade legada?
10. O problema é restrito aos oito pares ou existem referências globais em outras turmas/escolas?

## 3. Boundary de segurança

A execução de produção é autorizada apenas após merge do collector e abertura de gate owner-scoped contendo SHA exato de `main`.

É proibido:

- escrever no MongoDB;
- executar login ou qualquer HTTP da aplicação;
- ler `attendance.records`;
- consultar coleções de estudante/matrícula;
- ler valores de notas, status individuais de frequência ou texto pedagógico;
- projetar `audit_logs.old_value`, `new_value` ou `description`;
- emitir IDs técnicos brutos;
- fazer merge, backfill, remapeamento, exclusão ou saneamento.

O relatório público usa somente fingerprints SHA-256 truncados para identidades técnicas.

## 4. Fontes estruturais

A auditoria cobre a mesma superfície de referências de `backend/services/course_reference_integrity.py`:

- `teacher_assignments.course_id`;
- `teacher_allocations.course_id`;
- `teacher_class_assignments.component_id`;
- `class_schedules.schedule_slots.course_id`;
- `grades.course_id` — apenas metadados estruturais;
- `attendance.course_id` — sem `records`;
- `content_entries.component_id` — sem conteúdo pedagógico;
- `learning_objects.course_id` — sem texto pedagógico;
- `student_dependencies.course_id` — sem dados pessoais.

Adicionalmente, a F2.3 conta a presença das identidades em `classes.course_ids` e resume a trilha técnica em `audit_logs`.

## 5. Critério de autoridade operacional

A F2.3 pode declarar **identidade operacional corrente** quando os oito `teacher_assignments` ativos de Ana Lucia para os pares alvo convergirem para um único `course_id` e a identidade alternativa não aparecer nesses vínculos ativos.

Essa conclusão não equivale a autorização para consolidar cursos. `created_at`, maior volume histórico ou uso operacional atual são **evidência**, não regra automática para apagar/remapear a outra identidade.

## 6. Classificação esperada

Se a identidade dos vínculos atuais for única e a identidade alternativa concentrar os registros históricos, a classificação é:

`CURRENT_BINDING_VS_LEGACY_DATA_IDENTITY_SPLIT`

Se as duas identidades ainda estiverem ativas nos vínculos, a execução deve produzir `MIXED_ACTIVE_BINDINGS_REQUIRE_REVIEW`.

## 7. Entregáveis

- snapshot JSON read-only da execução em produção;
- diagnóstico Markdown publicado no issue de rastreamento #314;
- artifact GitHub Actions com retenção de 90 dias;
- nenhum deploy e nenhuma alteração de dados.

Qualquer fase posterior de reconciliação deverá começar por **preflight read-only de colisão semântica/referencial**, jamais por atualização direta de `course_id`.
